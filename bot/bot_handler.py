"""Bot Framework activity handler — routes user messages to the AI agent."""

import logging

from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import Activity, ActivityTypes, Attachment

from agent.kernel import AgentKernel
from bot.conversation_freshness_skill import ConversationFreshnessSkill

logger = logging.getLogger(__name__)


def _build_visualization_attachment(
    visualization: dict,
) -> Attachment | None:
    teams_payload = visualization.get("teams", {})
    image_data_uri = teams_payload.get("image_data_uri", "")
    image_url = teams_payload.get("image_url", "")
    image_source = image_data_uri or image_url
    title = visualization.get("title", "Chart")
    alt_text = teams_payload.get("alt_text", title)
    if not image_source:
        return None

    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content={
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": title,
                    "weight": "Bolder",
                    "wrap": True,
                },
                {
                    "type": "Image",
                    "url": image_source,
                    "altText": alt_text,
                    "size": "Stretch",
                },
            ],
        },
    )


class ChatBot(ActivityHandler):
    """Handles incoming Teams / Emulator messages and delegates to the SK agent."""

    def __init__(
        self,
        agent: AgentKernel,
        freshness: ConversationFreshnessSkill | None = None,
    ) -> None:
        super().__init__()
        self._agent = agent
        self._processed_ids: dict[str, str] = {}  # conversation_id → last activity_id
        self._freshness = freshness or ConversationFreshnessSkill()

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        """Process each user message through the AI agent."""
        user_text = (turn_context.activity.text or "").strip()
        if not user_text:
            await turn_context.send_activity("Please send a text message.")
            return

        user_id = turn_context.activity.from_property.id
        user_name = turn_context.activity.from_property.name
        conversation_id = turn_context.activity.conversation.id

        # Conversation reset command: clear only the current thread session.
        if self._freshness.is_reset_command(user_text):
            self._agent.reset_conversation(conversation_id)
            self._processed_ids.pop(conversation_id, None)
            self._freshness.apply_reset(user_id, conversation_id)
            logger.info(
                "Reset requested for conversation [%s] by user [%s] (%s)",
                conversation_id,
                user_id,
                user_name,
            )
            await turn_context.send_activity(
                "Session reset for this chat. You can continue here with a fresh context."
            )
            return

        decision = self._freshness.evaluate(user_id, conversation_id)
        if decision.should_block:
            logger.warning(
                "Stale conversation blocked. user_id=%s stale_conversation=%s",
                user_id,
                conversation_id,
            )
            await turn_context.send_activity(decision.stale_message or "This chat session is outdated.")
            return

        if decision.switched_from and decision.switched_to:
            logger.info(
                "Conversation switch detected. user_id=%s old_conversation=%s new_conversation=%s",
                user_id,
                decision.switched_from,
                decision.switched_to,
            )

        # Dedup: skip if Teams retried the same activity
        activity_id = turn_context.activity.id or ""
        if activity_id and self._processed_ids.get(conversation_id) == activity_id:
            logger.warning("Skipping duplicate activity %s", activity_id)
            return
        if activity_id:
            self._processed_ids[conversation_id] = activity_id
        logger.info(
            "User [%s] [%s] (%s): %s",
            conversation_id,
            user_id,
            user_name,
            user_text[:120],
        )

        # Show typing indicator while the agent works
        await turn_context.send_activity(Activity(type=ActivityTypes.typing))

        response = await self._agent.ask(conversation_id, user_text)

        # Send data chunks directly to the user (bypasses LLM)
        for chunk in response.get("data_chunks", []):
            await turn_context.send_activity(chunk)

        # Send download links for generated files
        for f in response.get("files", []):
            await turn_context.send_activity(
                f"📥 **Download full results:** [{f['name']}]({f['path']})"
            )

        # Send LLM commentary
        logger.info("Bot [%s]: %s", conversation_id, response["text"][:200])
        await turn_context.send_activity(response["text"])

        for visualization in response.get("visualizations", []):
            teams_payload = visualization.get("teams", {})
            has_image = bool(
                teams_payload.get("image_data_uri", "")
                or teams_payload.get("image_url", "")
            )
            attachment = _build_visualization_attachment(visualization)
            if not attachment:
                logger.info(
                    "Visualization skipped for conversation [%s]: chart image URL missing",
                    conversation_id,
                )
                continue
            mode = "inline-data-uri" if teams_payload.get("image_data_uri", "") else "image-url"
            logger.info(
                "Sending visualization attachment for conversation [%s] (title=%s, mode=%s)",
                conversation_id,
                visualization.get("title", "Chart"),
                mode if has_image else "fallback",
            )
            await turn_context.send_activity(
                Activity(
                    type=ActivityTypes.message,
                    attachments=[attachment],
                )
            )

    async def on_members_added_activity(self, members_added, turn_context: TurnContext) -> None:
        """Send a welcome message when the bot joins a conversation."""
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    "👋 Hi! I'm the **Data Assistant**. Ask me anything about "
                    "the loaded datasets — counts, filters, summaries, and more."
                )
