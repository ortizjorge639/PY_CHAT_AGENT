"""Bot entry point — aiohttp server hosting Bot Framework + web chat endpoints."""

import base64
import json
import logging
import os
import sys

# Ensure the app's own directory is on the import path (required for
# Azure App Service where Oryx extracts to /tmp/ but doesn't cd into it).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aiohttp import web
from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity

from config.settings import Settings
from bot.bot_handler import ChatBot
from agent.kernel import AgentKernel
from data.loader import DataLoader

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
GENERATED_DIR = os.environ.get(
    "GENERATED_DIR",
    os.path.join(os.path.dirname(__file__), "generated"),
)

# ── Settings ────────────────────────────────────────────
settings = Settings()

# ── Logging ─────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ── Easy Auth helpers ───────────────────────────────────
EASY_AUTH_HEADER = "X-MS-CLIENT-PRINCIPAL-ID"
EASY_AUTH_PRINCIPAL = "X-MS-CLIENT-PRINCIPAL"
AUTH_EXEMPT_PATHS = {"/api/messages"}


def _get_user_group_ids(request: web.Request) -> set[str]:
    """Decode X-MS-CLIENT-PRINCIPAL and return the user's group Object IDs.

    Easy Auth injects this header as a base64-encoded JSON blob containing
    all claims from the identity token, including group memberships.
    Returns an empty set if the header is missing or malformed.
    """
    raw = request.headers.get(EASY_AUTH_PRINCIPAL, "")
    if not raw:
        return set()
    try:
        decoded = json.loads(base64.b64decode(raw))
        return {
            c["val"] for c in decoded.get("claims", []) if c.get("typ") == "groups"
        }
    except Exception as exc:
        logger.warning("Failed to decode %s: %s", EASY_AUTH_PRINCIPAL, exc)
        return set()


def _user_can_download(request: web.Request) -> bool:
    """Check if the current user is in the file download security group.

    Returns True if:
    - FILE_DOWNLOAD_GROUP_ID is not configured (no restriction), or
    - REQUIRE_AUTH is disabled (local dev), or
    - The user's groups contain the configured group ID.
    """
    if not settings.require_auth or not settings.file_download_group_id:
        return True
    return settings.file_download_group_id in _get_user_group_ids(request)


# ── Easy Auth middleware ────────────────────────────────
# When REQUIRE_AUTH=true, rejects web-UI requests that lack a valid
# identity, providing defense-in-depth on top of the platform-level
# Easy Auth gate.
# The /api/messages endpoint is excluded — Bot Framework has its own auth.
@web.middleware
async def easy_auth_middleware(request: web.Request, handler):
    if request.path not in AUTH_EXEMPT_PATHS and settings.require_auth:
        principal_id = request.headers.get(EASY_AUTH_HEADER)
        if not principal_id:
            logger.warning("Rejected unauthenticated request to %s", request.path)
            return web.Response(
                status=401,
                text="Authentication required. Please sign in via your organisation.",
            )
        logger.info(
            "Authenticated request to %s from principal %s",
            request.path,
            principal_id,
        )
    return await handler(request)

# ── Bot Framework adapter ──────────────────────────────
adapter_settings = BotFrameworkAdapterSettings(
    app_id=settings.microsoft_app_id,
    app_password=settings.microsoft_app_password,
    channel_auth_tenant=settings.microsoft_app_tenant_id or None,
)
adapter = BotFrameworkAdapter(adapter_settings)


async def _on_error(context: TurnContext, error: Exception) -> None:
    """Global error handler — logs the error and notifies the user."""
    logger.error("Unhandled bot error: %s", error, exc_info=True)
    await context.send_activity("Sorry, something went wrong. Please try again.")


adapter.on_turn_error = _on_error

# ── Data → Agent → Bot wiring ─────────────────────────
data_loader = DataLoader(settings)
agent_kernel = AgentKernel(settings, data_loader)
bot = ChatBot(agent_kernel)


# ── HTTP endpoint ──────────────────────────────────────
async def messages(req: web.Request) -> web.Response:
    """POST /api/messages — Bot Framework webhook."""
    try:
        body = await req.json()
        logger.info("Received activity type: %s", body.get("type", "unknown"))
        activity = Activity().deserialize(body)
        auth_header = req.headers.get("Authorization", "")

        response = await adapter.process_activity(activity, auth_header, bot.on_turn)

        if response:
            return web.json_response(data=response.body, status=response.status)
        return web.Response(status=201)
    except Exception as e:
        logger.error("Error processing request: %s", e, exc_info=True)
        return web.Response(status=500, text=str(e))


# ── Simple REST chat endpoint (web UI) ────────────────
async def chat_api(req: web.Request) -> web.Response:
    """POST /api/chat — simple JSON chat for the web UI."""
    try:
        body = await req.json()
        user_msg = (body.get("message") or "").strip()
        conv_id = body.get("conversation_id", "web-default")

        if not user_msg:
            return web.json_response({"reply": "Please send a message."})

        logger.info("Web chat [%s]: %s", conv_id, user_msg[:120])
        reply = await agent_kernel.ask(conv_id, user_msg)

        # Only include file download links if the user is in the download group
        can_download = _user_can_download(req)
        files = reply.get("files", []) if can_download else []

        return web.json_response({
            "reply": reply["text"],
            "data_chunks": reply.get("data_chunks", []),
            "files": files,
        })
    except Exception as e:
        logger.error("Chat API error: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


# ── Serve web UI ──────────────────────────────────────
async def index_page(req: web.Request) -> web.Response:
    """GET / — serve the chat web UI."""
    return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ── Gated file download endpoint ──────────────────────
async def download_file(req: web.Request) -> web.Response:
    """GET /api/files/{filename} — serve generated Excel files.

    Only users in the download security group can access these files.
    Returns 403 if the user lacks permission, 404 if the file doesn't exist.
    """
    if not _user_can_download(req):
        logger.warning(
            "Download denied for principal %s — not in download group",
            req.headers.get(EASY_AUTH_HEADER, "unknown"),
        )
        return web.Response(
            status=403,
            text="You do not have permission to download files. "
            "Contact your administrator to request access.",
        )

    filename = req.match_info["filename"]
    filepath = os.path.join(GENERATED_DIR, filename)

    # Prevent path traversal
    if not os.path.abspath(filepath).startswith(os.path.abspath(GENERATED_DIR)):
        return web.Response(status=403, text="Access denied.")

    if not os.path.isfile(filepath):
        return web.Response(status=404, text="File not found.")

    return web.FileResponse(filepath)


def main() -> None:
    """Start the aiohttp web server."""
    middlewares = []
    if settings.require_auth:
        middlewares.append(easy_auth_middleware)
        logger.info("Easy Auth middleware ENABLED — web UI requires authentication")
    else:
        logger.info("Easy Auth middleware DISABLED — set REQUIRE_AUTH=true for production")

    app = web.Application(middlewares=middlewares)
    app.router.add_get("/", index_page)
    app.router.add_post("/api/messages", messages)
    app.router.add_post("/api/chat", chat_api)
    app.router.add_static("/static", STATIC_DIR)
    app.router.add_get("/api/files/{filename}", download_file)

    # Azure App Service injects PORT env var; prefer it over settings for deployment
    port = int(os.environ.get("PORT", settings.bot_port))
    logger.info("Bot listening on http://0.0.0.0:%s", port)
    logger.info("Web chat UI at  http://localhost:%s", port)
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
