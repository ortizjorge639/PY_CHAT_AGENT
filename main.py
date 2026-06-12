import base64
import asyncio
import contextlib
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
from bot.conversation_freshness_skill import ConversationFreshnessSkill
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

# ── Azure Monitor / OpenTelemetry ───────────────────────
if settings.applicationinsights_connection_string:
    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(
        connection_string=settings.applicationinsights_connection_string,
    )
    # Silence noisy Azure SDK HTTP logs (QuickPulse pings every few seconds)
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
    logging.getLogger("azure.monitor.opentelemetry.exporter").setLevel(logging.WARNING)
    logger.info("Azure Monitor OpenTelemetry enabled")


# ── Easy Auth helpers ───────────────────────────────────
EASY_AUTH_HEADER = "X-MS-CLIENT-PRINCIPAL-ID"
EASY_AUTH_PRINCIPAL = "X-MS-CLIENT-PRINCIPAL"
AUTH_EXEMPT_PATHS = {"/api/messages", "/robots933456.txt"}


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


def _get_easy_auth_context(request: web.Request) -> dict[str, str]:
    """Extract best-effort user context from Easy Auth headers for logging."""
    raw = request.headers.get(EASY_AUTH_PRINCIPAL, "")
    if not raw:
        return {"user_id": "", "user_name": ""}
    try:
        decoded = json.loads(base64.b64decode(raw))
    except Exception as exc:
        logger.warning("Failed to decode %s for logging: %s", EASY_AUTH_PRINCIPAL, exc)
        return {"user_id": "", "user_name": ""}

    claims = {claim.get("typ", ""): claim.get("val", "") for claim in decoded.get("claims", [])}
    return {
        "user_id": claims.get("oid") or claims.get("sub") or claims.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier", ""),
        "user_name": claims.get("name") or claims.get("preferred_username") or claims.get("upn") or "",
    }


def _activity_context(activity: Activity) -> dict[str, str]:
    """Extract consistent conversation and user details from a Bot Framework activity."""
    conversation_id = getattr(getattr(activity, "conversation", None), "id", "") or ""
    from_property = getattr(activity, "from_property", None)
    user_id = getattr(from_property, "id", "") or ""
    user_name = getattr(from_property, "name", "") or ""
    timestamp = str(getattr(activity, "timestamp", "") or "")
    return {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "user_name": user_name,
        "timestamp": timestamp,
    }


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
data_loader = DataLoader(settings, auto_load=False)
agent_kernel: AgentKernel | None = None
bot: ChatBot | None = None
conversation_freshness = ConversationFreshnessSkill()
_startup_state: dict[str, str | bool] = {
    "ready": False,
    "failed": False,
    "last_error": "",
}


def _is_ready() -> bool:
    return bool(_startup_state["ready"]) and bot is not None


def _warmup_message() -> str:
    if _startup_state["failed"]:
        return (
            "I'm still connecting to data sources after startup and can't answer yet. "
            "Please try again in about 30 seconds."
        )
    return "I'm warming up and loading data. Please try again in about 30 seconds."


async def _initialize_components_loop(app: web.Application) -> None:
    """Load data and construct agent in the background with retry on transient startup failures."""
    global agent_kernel, bot
    retry_delay_seconds = 15
    while not _is_ready():
        try:
            logger.info("Startup initialization: loading data...")
            data_loader.load_now()
            agent_kernel = AgentKernel(settings, data_loader)
            bot = ChatBot(agent_kernel, freshness=conversation_freshness)
            _startup_state["ready"] = True
            _startup_state["failed"] = False
            _startup_state["last_error"] = ""
            logger.info("Startup initialization complete; bot is ready to serve requests")
            return
        except Exception as exc:
            _startup_state["failed"] = True
            _startup_state["last_error"] = str(exc)
            logger.error("Startup initialization failed: %s", exc, exc_info=True)
            logger.warning(
                "Retrying startup initialization in %ds", retry_delay_seconds
            )
            await asyncio.sleep(retry_delay_seconds)


async def _data_refresh_loop(app: web.Application) -> None:
    """Periodically reload data from the configured source so queries reflect DB updates."""
    interval = settings.data_refresh_interval_minutes
    if interval <= 0:
        return
    delay = interval * 60
    logger.info("Data auto-refresh enabled: every %d minute(s)", interval)
    while True:
        await asyncio.sleep(delay)
        if _is_ready():
            logger.info("Auto-refresh: reloading data...")
            data_loader.reload()
            if agent_kernel:
                cleared = agent_kernel.reset_all_sessions()
                logger.info("Auto-refresh: cleared %d conversation session(s)", cleared)


async def _on_startup(app: web.Application) -> None:
    app["init_task"] = asyncio.create_task(_initialize_components_loop(app))
    app["refresh_task"] = asyncio.create_task(_data_refresh_loop(app))


async def _on_cleanup(app: web.Application) -> None:
    for key in ("init_task", "refresh_task"):
        task = app.get(key)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _send_warmup_response(turn_context: TurnContext) -> None:
    """Reply gracefully while startup is in progress so user messages are not silently lost."""
    if (turn_context.activity.type or "").lower() == "message":
        await turn_context.send_activity(_warmup_message())


# ── HTTP endpoint ──────────────────────────────────────
async def messages(req: web.Request) -> web.Response:
    """POST /api/messages — Bot Framework webhook."""
    try:
        body = await req.json()
        activity = Activity().deserialize(body)
        context = _activity_context(activity)
        logger.info(
            "Received bot activity type=%s conversation_id=%s user_id=%s user_name=%s timestamp=%s",
            body.get("type", "unknown"),
            context["conversation_id"],
            context["user_id"],
            context["user_name"],
            context["timestamp"],
        )
        auth_header = req.headers.get("Authorization", "")

        if not _is_ready():
            logger.warning(
                "Bot Framework message received before startup completed; returning warm-up response conversation_id=%s user_id=%s user_name=%s timestamp=%s",
                context["conversation_id"],
                context["user_id"],
                context["user_name"],
                context["timestamp"],
            )
            response = await adapter.process_activity(
                activity,
                auth_header,
                _send_warmup_response,
            )
            if response:
                return web.json_response(data=response.body, status=response.status)
            return web.Response(status=201)

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
        identity = _get_easy_auth_context(req)
        user_id = (
            identity["user_id"]
            or (body.get("user_id") or "").strip()
            or f"web-conversation:{conv_id}"
        )
        timestamp = body.get("timestamp") or ""

        if not user_msg:
            return web.json_response({"reply": "Please send a message."})

        if not _is_ready():
            logger.warning(
                "Web chat request received before startup completed conversation_id=%s user_id=%s user_name=%s timestamp=%s",
                conv_id,
                user_id,
                identity["user_name"],
                timestamp,
            )
            return web.json_response({"reply": _warmup_message()})

        if conversation_freshness.is_reset_command(user_msg):
            agent_kernel.reset_conversation(conv_id)
            conversation_freshness.apply_reset(user_id, conv_id)
            logger.info(
                "Web chat reset requested conversation_id=%s user_id=%s user_name=%s",
                conv_id,
                user_id,
                identity["user_name"],
            )
            return web.json_response({
                "reply": "Session reset for this chat. You can continue here with a fresh context.",
                "data_chunks": [],
                "files": [],
            })

        decision = conversation_freshness.evaluate(user_id, conv_id)
        if decision.should_block:
            logger.warning(
                "Web chat stale conversation blocked user_id=%s stale_conversation=%s",
                user_id,
                conv_id,
            )
            return web.json_response({
                "reply": decision.stale_message,
                "data_chunks": [],
                "files": [],
            })

        if decision.switched_from and decision.switched_to:
            logger.info(
                "Web chat conversation switch detected. user_id=%s old_conversation=%s new_conversation=%s",
                user_id,
                decision.switched_from,
                decision.switched_to,
            )

        logger.info(
            "User message conversation_id=%s user_id=%s user_name=%s timestamp=%s text=%s",
            conv_id,
            user_id,
            identity["user_name"],
            timestamp,
            user_msg[:120],
        )
        reply = await agent_kernel.ask(conv_id, user_msg)
        logger.info(
            "Bot message conversation_id=%s user_id=%s user_name=%s text=%s",
            conv_id,
            user_id,
            identity["user_name"],
            reply["text"][:200],
        )

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


# ── Data reload endpoint ──────────────────────────────
async def reload_data(req: web.Request) -> web.Response:
    """POST /api/reload — trigger a data refresh without restarting the app."""
    if not _is_ready():
        return web.json_response({"status": "error", "message": "App not ready yet"}, status=503)
    data_loader.reload()
    sessions_cleared = agent_kernel.reset_all_sessions() if agent_kernel else 0
    return web.json_response({
        "status": "ok",
        "tables": data_loader.list_tables(),
        "rows_per_table": {t: len(data_loader._tables[t]) for t in data_loader.list_tables()},
        "last_loaded_at": data_loader.last_loaded_at.isoformat() if data_loader.last_loaded_at else None,
        "sessions_cleared": sessions_cleared,
    })


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
    app.router.add_post("/api/reload", reload_data)
    app.router.add_static("/static", STATIC_DIR)
    app.router.add_get("/api/files/{filename}", download_file)
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)

    # Azure App Service injects PORT env var; prefer it over settings for deployment
    port = int(os.environ.get("PORT", settings.bot_port))
    logger.info("Bot listening on http://0.0.0.0:%s", port)
    logger.info("Web chat UI at  http://localhost:%s", port)
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
