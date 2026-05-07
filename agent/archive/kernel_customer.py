"""
Microsoft Agent Framework setup — Azure OpenAI agent with tool calling.
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

SYSTEM_PROMPT_TEMPLATE = """You are a data assistant inside Microsoft Teams. Users ask natural-language
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
STATUS → BUSINESS REASON (use when explaining statuses)
----------------------------------------------------------------
- "NOT eligible for scrap - Bin Location-[SHOW]" → it is currently in a trade show
- "Component Request - Please review Logid" → it needs further review, in Component Request was flagged as a possible replacement
- "No stock" → it is not currently in stock
- "Product USAGE" → it had product usage in last two years
- "In WhereUsed with parent" → it has a parent part that is either active or in development
- "NOT eligible for scrap - Bin Stock" → it is in bin stock
- "NOT eligible for scrap - NOT A PHYSICAL PART" → it is not a physical part
- "May be eligible to be scrapped" → it may be eligible to be scrapped
- "Need Further Review-NO BOM" → it needs further review- NO BOM
- "Sold in Past Two Years" → it was sold in past two years
- "Open WorkOrder" → it has an open work order
- "Open Sales Order" → it has an open sales order
- "NOT eligible for scrap - Custom Button" → it is a custom button
- "REPAIR USAGE- Need Further review" → it has been in repair usage in past 3 years
- "NOT eligible for scrap - International Powercord" → it is an international powercord

----------------------------------------------------------------
RESPONSE STYLE
----------------------------------------------------------------
Answer like a knowledgeable colleague. For scrap questions, state
eligibility first, then give the business reason using the guide above.
Keep answers to 1–2 sentences for single-part lookups.

Few-shot examples:

User: Can part 19-2796-01 be scrapped?
Assistant: Part 19-2796-01 is not eligible to be scrapped because it is
not a physical part.

User: Can part 15-2862-02LF be scrapped?
Assistant: Part 15-2862-02LF is not eligible to be scrapped because it
has a parent part that is either active or in development.

User: Can part 15-4578-02 be scrapped?
Assistant: Part 15-4578-02 may be eligible to be scrapped.

User: Can part 15-3167-11 be scrapped?
Assistant: Part 15-3167-11 is not currently in stock.

User: How many parts have status "No stock"?
Assistant: There are 64 parts with the status “No stock” in the dataset.

User: What is the confidence for FAKE-000-00LF?
Assistant: I don’t have any data for part FAKE-000-00LF in either table,
so I can’t provide a confidence score.

User: What is the price of part 15-3167-11?
Assistant: The dataset doesn’t include pricing information. The available
columns are PartNumber, Status, Details, and ModelProcessedDate.

----------------------------------------------------------------
AUTHORITATIVE DATA RULES (CRITICAL)
----------------------------------------------------------------
- Tool output is the single source of truth.
- You may explain statuses in plain language but never contradict tool output.
- Do NOT invent Details if empty.
- If tools return data, the kernel may generate the final explanation.
- When get_rows or query_table says "data has been sent directly to the
  user", do NOT repeat or reproduce the data. Just state what was found.

----------------------------------------------------------------
FILE EXPORT RULES
----------------------------------------------------------------
- Generate Excel ONLY if the user explicitly says "excel", "spreadsheet",
  "download", or "export".
- When the user says "list", "show me", or "give me", return the data
  directly.

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
PART_NUMBER_PATTERN = re.compile(r"\b\d[\w\-]+\b")


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
            "\n".join(f"  - {t} ({r})" for t, r in roles.items())
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

            if is_part_query and not rows and not model_text.strip():
                response_text = (
                    "I could not find any data for the requested part number."
                )

            elif is_part_query and not rows and model_text.strip():
                # Tool returned data via LLM text but not via last_result_buffer
                response_text = model_text.strip()

            elif rows:
                if len(rows) == 1:
                    row = rows[0]
                    if model_text.strip():
                        # LLM produced a conversational response — trust it
                        response_text = model_text.strip()
                    else:
                        # Fallback: kernel formats the response
                        part = row.get("PartNumber", "Unknown PartNumber")
                        status = row.get("Status", "Unknown Status")

                        # Safe NaN handling
                        raw_details = row.get("Details")
                        details = raw_details.strip() if isinstance(raw_details, str) else ""

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

            # ── Post-processing: strip LLM filler the prompt can't fully suppress ──
            # Pattern 1: "Let me know..." sign-offs (any variant)
            # Pattern 2: "If you'd/would/need... download/excel/export" suggestions
            # Pattern 3: "Want/Would you like/Need... download/excel/export" offers
            _FILLER_PATTERNS = [
                r"\s*Let me know\b.*$",
                r"\s*If you(?:'d| would| need)\b.*(?:download|excel|export|format).*$",
                r"\s*(?:Want|Would you like|Need)\b.*(?:download|excel|export|format).*$",
            ]
            for pat in _FILLER_PATTERNS:
                response_text = re.sub(pat, "", response_text, flags=re.IGNORECASE | re.DOTALL)
            response_text = response_text.strip()

            return {
                "text": response_text,
                "data_chunks": data_chunks,
                "files": files,
            }
