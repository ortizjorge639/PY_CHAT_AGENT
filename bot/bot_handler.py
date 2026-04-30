"""Bot Framework activity handler — routes user messages to the AI agent."""

import logging

from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import Activity, ActivityTypes

from agent.kernel import AgentKernel

logger = logging.getLogger(__name__)


class ChatBot(ActivityHandler):
    """Handles incoming Teams / Emulator messages and delegates to the SK agent."""

    def __init__(self, agent: AgentKernel) -> None:
        super().__init__()
        self._agent = agent
        self._processed_ids: dict[str, str] = {}  # conversation_id → last activity_id

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        """Process each user message through the AI agent."""
        user_text = (turn_context.activity.text or "").strip()
        if not user_text:
            await turn_context.send_activity("Please send a text message.")
            return

        # Dedup: skip if Teams retried the same activity
        conversation_id = turn_context.activity.conversation.id
        activity_id = turn_context.activity.id or ""
        if activity_id and self._processed_ids.get(conversation_id) == activity_id:
            logger.warning("Skipping duplicate activity %s", activity_id)
            return
        if activity_id:
            self._processed_ids[conversation_id] = activity_id
        logger.info(
            "Message from conversation %s: %s",
            conversation_id,
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
        await turn_context.send_activity(response["text"])

    async def on_members_added_activity(self, members_added, turn_context: TurnContext) -> None:
        """Send a welcome message when the bot joins a conversation."""
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    "👋 Hi! I'm the **Data Assistant**. Ask me anything about "
                    "the loaded datasets — counts, filters, summaries, and more."
                )
