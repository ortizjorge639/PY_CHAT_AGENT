"""Script to fix double-spacing in kernel_customer.py"""
import pathlib

FIXED_CONTENT = '''\
"""
Microsoft Agent Framework setup \u2014 Azure OpenAI agent with tool calling.
"""

import asyncio
import logging
import re
from typing import Dict, Optional

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIChatClient

from config.settings import Settings
from data.loader import DataLoader
from agent.plugins.data_plugin import create_data_tools

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
AUTHORITATIVE STATUS VALUES (ENUM \u2014 EXACT MATCHING ONLY)
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

# Conservative pattern for detecting PartNumber-style queries
PART_NUMBER_PATTERN = re.compile(r"\\b\\d[\\w\\-]+\\b")


def extract_part_number(text: str) -> Optional[str]:
    match = PART_NUMBER_PATTERN.search(text)
    return match.group(0) if match else None


def wants_excel(text: str) -> bool:
    """
    Excel files should ONLY be returned when the user explicitly asks.
    """
    text = text.lower()
    return any(
        kw in text
        for kw in ("excel", "spreadsheet", "download", "export")
    )


# -------------------------------------------------------------------
# Agent Kernel
# -------------------------------------------------------------------

class AgentKernel:
    """
    Wraps the Microsoft Agent Framework with per-conversation sessions.
    """

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

        tools = create_data_tools(
            loader=data_loader,
            data_buffer=self._data_buffer,
            file_buffer=self._file_buffer,
            last_result=self._last_result_buffer,
            base_url=settings.base_url,
        )

        roles = data_loader.get_table_roles()
        table_roles_str = (
            "\\n".join(f"  - {t} ({r})" for t, r in roles.items())
            if roles else "  (no tables loaded)"
        )

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            table_roles=table_roles_str
        )

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
        async with self._lock:
            self._data_buffer.clear()
            self._file_buffer.clear()
            self._last_result_buffer.clear()

            session = self._get_session(conversation_id)

            wants_list = "list" in user_message.lower()
            excel_requested = wants_excel(user_message)

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

            # ------------------------------------------------------------
            # Case-insensitive exact-match guard
            # ------------------------------------------------------------
            if is_part_query and rows and requested_part:
                requested_norm = requested_part.upper()
                rows = [
                    r for r in rows
                    if str(r.get("PartNumber", "")).upper() == requested_norm
                ]

            # ------------------------------------------------------------
            # Response generation
            # ------------------------------------------------------------

            if is_part_query and not rows:
                response_text = (
                    "I could not find any data for the requested part number."
                )

            elif rows:
                if len(rows) == 1:
                    row = rows[0]
                    part = row.get("PartNumber", "Unknown PartNumber")
                    status = row.get("Status", "Unknown Status")

                    # Safe NaN handling
                    raw_details = row.get("Details")
                    details = raw_details.strip() if isinstance(raw_details, str) else ""

                    if details and details.lower() != "nan":
                        response_text = (
                            f"Part {part} has a status of \\u201c{status}\\u201d. "
                            f"Additional details: {details}"
                        )
                    else:
                        response_text = (
                            f"Part {part} has a status of \\u201c{status}\\u201d."
                        )
                else:
                    response_text = f"{len(rows)} records match your request."

            elif model_text.strip() and not is_part_query:
                response_text = model_text.strip()

            else:
                response_text = "No data was returned."

            # ------------------------------------------------------------
            # HARD UX RULE ENFORCEMENT
            # ------------------------------------------------------------

            data_chunks = data_chunks if wants_list else []
            files = files if excel_requested else []

            if excel_requested and files:
                response_text = "The Excel file has been generated."

            return {
                "text": response_text,
                "data_chunks": data_chunks,
                "files": files,
            }
'''

p = pathlib.Path(r'c:\Users\jortizflores\PY_CHAT_AGENT\agent\kernel_customer.py')
p.write_text(FIXED_CONTENT, encoding='utf-8', newline='\n')
print(f"Written {len(FIXED_CONTENT.splitlines())} lines")
