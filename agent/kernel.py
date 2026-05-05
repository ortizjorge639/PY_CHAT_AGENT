"""Microsoft Agent Framework setup — Azure OpenAI agent with tool calling."""

import asyncio
import logging
import re
from typing import Dict, Optional

from agent_framework import Agent
from agent_framework import ChatOptions
from agent_framework.azure import AzureOpenAIChatClient

from config.settings import Settings
from data.loader import DataLoader
from agent.plugins.data_plugin import create_data_tools

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """\
You are a data assistant inside Microsoft Teams. Users ask natural-language
questions about tabular data and you answer with precise, factual results
derived strictly from the available dataset.

Data sources:
{table_roles}

----------------------------------------------------------------
TABLE SCHEMAS
----------------------------------------------------------------
{table_schemas}

----------------------------------------------------------------
DOMAIN KNOWLEDGE
----------------------------------------------------------------
- The primary table contains authoritative disposition/status data.
  Each row represents exactly one unique PartNumber.
- The Status column is authoritative and determines the disposition,
  eligibility, or restriction associated with a part.
- The Details column provides additional explanation or structured context
  for the Status when such information is available.
- Supplemental tables contain metadata (replacements, confidence, etc.).
- When a user asks about a specific PartNumber, ALWAYS call the
  lookup_part tool FIRST. It searches all tables automatically.
  NEVER use get_rows, query_table, or count_rows to look up a single part.
- If the user asks for a row by a non-PartNumber identifier
  (e.g. pklogid, LogDate), use get_row_by_id instead of query_table.
- If a column exists in multiple tables, clarify which table you are
  querying and why.

----------------------------------------------------------------
AUTHORITATIVE STATUS VALUES (primary table — EXACT MATCHING ONLY)
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
- NEVER invent column names. If unsure, call list_tables or get_schema first.

----------------------------------------------------------------
OUTPUT REQUIREMENT
----------------------------------------------------------------
- Never return an empty response.
"""

PART_NUMBER_PATTERN = re.compile(
    r"\b(?:[A-Z]{1,3}-)?\d{2,}-\d{2,}-\d{2,}[A-Z]*\b",
    re.IGNORECASE,
)


def extract_part_number(text: str) -> Optional[str]:
    match = PART_NUMBER_PATTERN.search(text)
    return match.group(0) if match else None


class AgentKernel:
    """Wraps the Microsoft Agent Framework with per-conversation sessions."""

    def __init__(self, settings: Settings, data_loader: DataLoader) -> None:
        self._data_buffer: list[str] = []
        self._file_buffer: list[dict] = []
        self._last_result_buffer: dict = {}
        self._lock = asyncio.Lock()
        client = AzureOpenAIChatClient(
            api_key=settings.azure_openai_api_key,
            endpoint=settings.azure_openai_endpoint,
            deployment_name=settings.azure_openai_deployment_name,
        )
        # Version 2 behavior retained (Teams Excel support)
        tools = create_data_tools(
            loader=data_loader,
            data_buffer=self._data_buffer,
            file_buffer=self._file_buffer,
            last_result=self._last_result_buffer,
            base_url=settings.base_url,
        )
        roles = data_loader.get_table_roles()
        table_roles_str = (
            "\n".join(f"  - {t} ({r})" for t, r in roles.items())
            if roles else "  (no tables loaded)"
        )

        schema_blocks = []
        for tbl in data_loader.list_tables():
            schema = data_loader.get_schema(tbl)
            cols = ", ".join(f"{c} ({t})" for c, t in schema.items())
            schema_blocks.append(f"  {tbl}: {cols}")
        table_schemas_str = "\n".join(schema_blocks) if schema_blocks else "  (none)"

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            table_roles=table_roles_str,
            table_schemas=table_schemas_str,
        )
        self._agent = Agent(
            client=client,
            instructions=system_prompt,
            tools=tools,
            default_options=ChatOptions(temperature=0),
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
        async with self._lock:
            self._data_buffer.clear()
            self._file_buffer.clear()
            self._last_result_buffer.clear()
            session = self._get_session(conversation_id)
            wants_list = "list" in user_message.lower()
            requested_part = extract_part_number(user_message)
            is_part_query = bool(requested_part)
            try:
                result = await self._agent.run(
                    user_message,
                    session=session,
                )
                model_text = result.text if result and result.text else ""
            except Exception:
                logger.exception("Agent error")
                model_text = ""
            data_chunks = list(dict.fromkeys(self._data_buffer))
            files = list(self._file_buffer)
            rows = self._last_result_buffer.get("rows")
            # Kernel-level EXACT MATCH SAFETY GUARD
            if is_part_query and rows:
                rows = [
                    r for r in rows
                    if str(r.get("PartNumber", "")).lower() == requested_part.lower()
                ]
            if is_part_query and rows:
                # Find the primary-table row (has Status) for formatted response
                primary_row = next((r for r in rows if r.get("Status")), None)
                if model_text.strip():
                    # Model produced a response from tool data — trust it
                    response_text = model_text.strip()
                elif primary_row:
                    part = primary_row.get("PartNumber", "Unknown PartNumber")
                    status = primary_row.get("Status")
                    raw_details = primary_row.get("Details")
                    # NaN-safe: pandas stores SQL NULL as float('nan'), which is truthy — must check explicitly
                    details = ("" if raw_details is None or (isinstance(raw_details, float) and raw_details != raw_details) else str(raw_details)).strip()
                    if details and details.lower() != "nan":
                        response_text = (
                            f"Part {part} has a status of \u201c{status}\u201d. "
                            f"Additional details: {details}"
                        )
                    else:
                        response_text = (
                            f"Part {part} has a status of \u201c{status}\u201d."
                        )
                else:
                    response_text = f"Data found for {requested_part}, but no Status field available."
            elif is_part_query and not rows and not model_text.strip():
                response_text = (
                    "I could not find any data for the requested PartNumber, "
                    "so I cannot determine whether it can be scrapped."
                )
            elif model_text.strip():
                response_text = model_text.strip()
            elif files:
                response_text = "The requested file has been generated."
            else:
                response_text = "No data was returned."
            return {
                "text": response_text,
                "data_chunks": data_chunks,
                "files": files,
            }
