"""
Microsoft Agent Framework setup — Azure OpenAI agent with tool calling.
"""

import asyncio
import logging
from typing import Dict

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIChatClient

from config.settings import Settings
from data.loader import DataLoader
from agent.plugins.data_plugin_test import create_data_tools

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# FULL SYSTEM PROMPT
# -------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """\
You are a data assistant inside Microsoft Teams. Users ask natural-language
questions about tabular data and you answer with precise, factual results
derived strictly from the available dataset.

Data sources:
{table_roles}

----------------------------------------------------------------
DOMAIN KNOWLEDGE
----------------------------------------------------------------
- Each row represents exactly one unique PartNumber.
- The Status column is authoritative and determines the disposition,
  eligibility, or restriction associated with a part.
- The Details column provides additional explanation or structured context
  for the Status when such information is available.
- When a user asks about a specific PartNumber, you MUST retrieve
  the row using tools.

----------------------------------------------------------------
AUTHORITATIVE STATUS VALUES (ENUM — EXACT MATCHING ONLY)
----------------------------------------------------------------
You must use ONLY the following Status values exactly as written:

- NOT eligible for scrap - Bin Location-[SHOW]
- Component Request - Please review Logid
- No stock
- Product USAGE
- In WhereUsed with parent
- NOT eligible for scrap - Bin Stock
- NOT eligible for scrap - NOT A PHYSICAL PART
- May be eligible to be scrapped
- Need Further Review-NO BOM
- Sold in Past Two Years
- Open WorkOrder
- Open Sales Order
- NOT eligible for scrap - Custom Button
- REPAIR USAGE- Need Further review
- NOT eligible for scrap - International Powercord

Do NOT invent, alter, abbreviate, paraphrase, or substitute Status values.

----------------------------------------------------------------
AUTHORITATIVE DATA RULES (CRITICAL)
----------------------------------------------------------------
- Tool output is the single source of truth.
- Never reinterpret, override, or clarify data after tools run.
- Do NOT invent Details if empty.
- If tools return data, the kernel may generate the final explanation.

----------------------------------------------------------------
FILE EXPORT RULES
----------------------------------------------------------------
- Generate Excel ONLY if explicitly requested.

----------------------------------------------------------------
SYSTEM CONSTRAINTS
----------------------------------------------------------------
- Never contradict tool output.
- Never invent data or business rules.

Allowed columns:
- PartNumber
- Status
- Details
- ModelProcessedDate

----------------------------------------------------------------
OUTPUT REQUIREMENT
----------------------------------------------------------------
- Never return an empty response.
"""

# -------------------------------------------------------------------
# Agent Kernel
# -------------------------------------------------------------------

class AgentKernel:
    """
    Wraps the Microsoft Agent Framework with per-conversation sessions.
    """

    def __init__(self, settings: Settings, data_loader: DataLoader) -> None:
        # Buffers populated by tools
        self._data_buffer: list[str] = []
        self._file_buffer: list[dict] = []
        self._last_result_buffer: dict = {}

        self._lock = asyncio.Lock()

        # Azure OpenAI client
        client = AzureOpenAIChatClient(
            api_key=settings.azure_openai_api_key,
            endpoint=settings.azure_openai_endpoint,
            deployment_name=settings.azure_openai_deployment_name,
        )

        # Bind data tools
        tools = create_data_tools(
            loader=data_loader,
            data_buffer=self._data_buffer,
            file_buffer=self._file_buffer,
            last_result=self._last_result_buffer,
        )

        # Build system prompt
        roles = data_loader.get_table_roles()
        table_roles_str = (
            "\n".join(f"  - {t} ({r})" for t, r in roles.items())
            if roles else "  (no tables loaded)"
        )

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            table_roles=table_roles_str
        )

        # Agent instance
        self._agent = Agent(
            client=client,
            instructions=system_prompt,
            tools=tools,
        )

        self._sessions: Dict[str, object] = {}

        logger.info(
            "AgentKernel initialized (deployment=%s)",
            settings.azure_openai_deployment_name,
        )

    # -------------------------------------------------------------------
    # Session handling
    # -------------------------------------------------------------------

    def _get_session(self, conversation_id: str):
        if conversation_id not in self._sessions:
            self._sessions[conversation_id] = self._agent.create_session()
        return self._sessions[conversation_id]

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    async def ask(self, conversation_id: str, user_message: str) -> dict:
        """
        Send a user message through the agent and return the response.
        """
        async with self._lock:
            # Clear buffers at start of turn
            self._data_buffer.clear()
            self._file_buffer.clear()

            session = self._get_session(conversation_id)

            try:
                result = await self._agent.run(
                    user_message,
                    session=session,
                )
                model_text = result.text if result and result.text else ""
            except Exception as exc:
                logger.exception("Agent error")
                model_text = f"⚠️ Error processing request: {exc}"

            # ----------------------------------------------------------------
            # Snapshot tool buffers
            # ----------------------------------------------------------------

            data_chunks = list(self._data_buffer)
            files = list(self._file_buffer)

            # ----------------------------------------------------------------
            # De-duplicate identical markdown tables
            # ----------------------------------------------------------------

            seen = set()
            deduped_chunks = []
            for chunk in data_chunks:
                if chunk not in seen:
                    seen.add(chunk)
                    deduped_chunks.append(chunk)

            data_chunks = deduped_chunks

            # ----------------------------------------------------------------
            # Kernel-generated English response (authoritative, safe)
            # ----------------------------------------------------------------

            response_text = ""

            if data_chunks and self._last_result_buffer.get("rows"):
                rows = self._last_result_buffer["rows"]

                # ✅ Single-row (most common, e.g. one PartNumber)
                if len(rows) == 1:
                    row = rows[0]

                    part = row.get("PartNumber", "Unknown PartNumber")
                    status = row.get("Status", "Unknown Status")
                    details = row.get("Details")

                    # Normalize Details (handle pandas NaN, None, empty)
                    if details is None:
                        details = ""
                    else:
                        details = str(details).strip()

                    if details and details.lower() != "nan":
                        response_text = (
                            f"Part {part} has a status of "
                            f"\u201c{status}\u201d. Additional details: {details}"
                        )
                    else:
                        response_text = (
                            f"Part {part} has a status of "
                            f"\u201c{status}\u201d."
                        )

                # ✅ Multi-row result
                else:
                    response_text = (
                        f"{len(rows)} records match your request. "
                        f"The full results are shown below."
                    )

            elif files:
                response_text = "The requested file has been generated."

            elif model_text.strip():
                # Only allowed when NO tools were used
                response_text = model_text.strip()

            else:
                response_text = "No data was returned."

            # ----------------------------------------------------------------
            # Clear buffers to avoid reuse across turns
            # ----------------------------------------------------------------

            self._data_buffer.clear()
            self._file_buffer.clear()

            return {
                "text": response_text,
                "data_chunks": data_chunks,
                "files": files,
            }
