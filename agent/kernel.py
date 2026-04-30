"""Microsoft Agent Framework setup — Azure OpenAI agent with tool calling."""

import asyncio
import logging

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIChatClient

from config.settings import Settings
from data.loader import DataLoader
from agent.plugins.data_plugin import create_data_tools

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """\
You are a data assistant inside Microsoft Teams. Users ask natural-language \
questions about tabular data and you answer with precise facts from the dataset.

Data sources:
{table_roles}

Rules:
1. Always call the available data functions — never guess or fabricate data. \
   If you are unsure, call a tool to verify. Never assume column names, table \
   names, values, counts, or statistics from memory — always look them up.
2. Answer concisely first. When a user asks a question, provide the direct \
   insight (a count, summary, or key finding) — do NOT retrieve or display full \
   row data unless the user explicitly asks for it (e.g. "show me the rows", \
   "give me the data", "list them").
3. Prefer count_rows, group_by, and get_distinct_values for answering questions. \
   Only use get_rows or query_table when the user wants to see the actual records.
4. Do NOT call download_as_excel unless the user explicitly asks for a file, \
   download, or export. When they do, call ONLY download_as_excel with the \
   appropriate table name and filter — do NOT call get_rows or query_table \
   first. download_as_excel handles everything itself.
5. When get_rows or query_table returns a summary saying data was sent directly \
   to the user, do NOT repeat or fabricate the row data. Simply acknowledge the \
   result and mention the query/filter used.
6. After presenting data, briefly state what query/filter you used and how many \
   rows matched.
7. If the data cannot answer a question, say "I don't have that information in \
   the dataset" — do NOT guess or use general knowledge.
8. The primary dataset is your main source of truth. Supplemental tables contain \
   additional context — only query them when the user specifically asks about \
   that data or when the primary dataset cannot answer the question.
9. NEVER generate download links, file URLs, or file paths in your response text. \
   The system automatically sends download links to the user. Just confirm the \
   file was generated — do not include any markdown links, paths, or URLs.
10. NEVER invent column names. If unsure, call list_tables or get_schema first. \
    NEVER reference a column or value you have not seen in a tool response.
"""


class AgentKernel:
    """Wraps the Microsoft Agent Framework with per-conversation sessions."""

    def __init__(self, settings: Settings, data_loader: DataLoader) -> None:
        # Shared buffers for data that bypasses the LLM
        self._data_buffer: list[str] = []
        self._file_buffer: list[dict] = []
        self._last_result_buffer: dict = {}  # stores last query result for on-demand download
        self._buffer_lock = asyncio.Lock()

        # Azure OpenAI chat client
        client = AzureOpenAIChatClient(
            api_key=settings.azure_openai_api_key,
            endpoint=settings.azure_openai_endpoint,
            deployment_name=settings.azure_openai_deployment_name,
        )

        # Data tools (bound to the shared buffers)
        tools = create_data_tools(
            data_loader, self._data_buffer, self._file_buffer, self._last_result_buffer
        )

        # Build dynamic system prompt with table roles
        roles = data_loader.get_table_roles()
        role_lines = []
        for table, role in roles.items():
            role_lines.append(f"  - {table} ({role})")
        table_roles_str = "\n".join(role_lines) if role_lines else "  (no tables loaded)"
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(table_roles=table_roles_str)

        # Build the agent
        self._agent = Agent(
            client=client,
            instructions=system_prompt,
            tools=tools,
        )

        # Per-conversation sessions (preserves chat history)
        self._sessions: dict[str, object] = {}
        logger.info(
            "AgentKernel initialised (deployment=%s)",
            settings.azure_openai_deployment_name,
        )

    def _get_session(self, conversation_id: str):
        """Return (or create) the AF session for a conversation."""
        if conversation_id not in self._sessions:
            self._sessions[conversation_id] = self._agent.create_session()
        return self._sessions[conversation_id]

    async def ask(self, conversation_id: str, user_message: str) -> dict:
        """Send a user message through the agent and return the reply.

        Returns:
            dict with "text" (LLM response), "data_chunks" (list of markdown
            tables), and "files" (list of generated file metadata) — all sent
            directly to the user, bypassing the LLM.
        """
        async with self._buffer_lock:
            self._data_buffer.clear()
            self._file_buffer.clear()
            session = self._get_session(conversation_id)

            try:
                result = await self._agent.run(
                    user_message,
                    session=session,
                )
                response_text = result.text if result else (
                    "I couldn't generate a response. Please try again."
                )
            except Exception as exc:
                logger.error("Agent error: %s", exc, exc_info=True)
                response_text = f"⚠️ Error processing your request: {exc}"

            data_chunks = list(self._data_buffer)
            files = list(self._file_buffer)
            self._data_buffer.clear()
            self._file_buffer.clear()

            return {"text": response_text, "data_chunks": data_chunks, "files": files}
