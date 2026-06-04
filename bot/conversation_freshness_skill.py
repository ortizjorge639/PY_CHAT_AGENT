"""Reusable conversation freshness guard for Bot Framework handlers.

This module centralizes stale conversation detection and thread promotion so it
can be copied into another repository with minimal integration work.
"""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_STALE_MESSAGE = (
    "This chat session is outdated. Please continue in your most recent chat with the bot, "
    "or type 'reset' here to start fresh in this thread."
)


@dataclass(frozen=True)
class RouteDecision:
    """Outcome of evaluating a user message route."""

    should_block: bool
    stale_message: str | None = None
    switched_from: str | None = None
    switched_to: str | None = None


class ConversationFreshnessSkill:
    """Tracks active thread per user and blocks previously retired threads."""

    def __init__(self) -> None:
        self._latest_conversation_by_user: dict[str, str] = {}
        self._retired_conversations: set[tuple[str, str]] = set()
        self._reset_commands = {
            "reset",
            "/reset",
            "new",
            "/new",
            "start over",
            "new chat",
            "reset session",
        }

    def is_reset_command(self, text: str) -> bool:
        return text.strip().lower() in self._reset_commands

    def apply_reset(self, user_id: str, conversation_id: str) -> str | None:
        """Marks a conversation as active and retires any previous active thread."""
        previous = self._latest_conversation_by_user.get(user_id)
        if previous and previous != conversation_id:
            self._retired_conversations.add((user_id, previous))
        self._latest_conversation_by_user[user_id] = conversation_id
        self._retired_conversations.discard((user_id, conversation_id))
        return previous

    def evaluate(self, user_id: str, conversation_id: str) -> RouteDecision:
        """Evaluates whether an incoming message should be processed or blocked."""
        latest_for_user = self._latest_conversation_by_user.get(user_id)

        if latest_for_user and latest_for_user != conversation_id:
            if (user_id, conversation_id) in self._retired_conversations:
                return RouteDecision(
                    should_block=True,
                    stale_message=DEFAULT_STALE_MESSAGE,
                )

            # Auto-heal by promoting the newly seen thread and retiring the previous one.
            self._retired_conversations.add((user_id, latest_for_user))
            self._latest_conversation_by_user[user_id] = conversation_id
            return RouteDecision(
                should_block=False,
                switched_from=latest_for_user,
                switched_to=conversation_id,
            )

        if not latest_for_user:
            self._latest_conversation_by_user[user_id] = conversation_id

        return RouteDecision(should_block=False)
