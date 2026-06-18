"""
Microsoft Agent Framework setup — Azure OpenAI agent with tool calling.
"""

import asyncio
import logging
import re
from typing import Dict, Optional

try:
    from agent_framework import Agent
    from agent_framework.azure import AzureOpenAIChatClient
    _AGENT_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised in dependency-mismatch environments
    Agent = None  # type: ignore[assignment]
    AzureOpenAIChatClient = None  # type: ignore[assignment]
    _AGENT_IMPORT_ERROR = exc
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
PRIMARY TABLE (scrap-eligibility):
  PartNumber, Status, Details, Processed_Date, QOH, Reza's List

SUPPLEMENTAL TABLE — production.dimProducts (product catalogue):
  PartNumber, Description, Phase,
  IsTopLevelPart, IsConfiguredPart, IsConfiguredPartComponent,
  IsSerialized, IsLinkLicense, IsPhantomPart, IsBinItem,
  IsWebEnabled, IsNonPhysical,
  International_PowerCord, CustomButton,
  Effective Date, DateAdded,
  PartNumberPrefix, PartNumberModel, PartNumberSuffix

- Each row represents exactly one unique PartNumber.
- The Status column (primary table) is authoritative and determines the
  disposition, eligibility, or restriction associated with a part.
- The Details column provides additional explanation or structured context
  for the Status when such information is available.
- When a user asks about a specific PartNumber, you MUST retrieve
  the row using tools.
- Tables are NEVER joined. Query each independently.

----------------------------------------------------------------
TABLE ROUTING RULES (STRICT)
----------------------------------------------------------------
- Scrap eligibility / Status / Disposition  → PRIMARY table
- Description / Phase / product flags       → call lookup_part_details(part_number=…)
- Unspecified part question                 → check PRIMARY first; use supplemental on follow-up
- Do NOT mix columns from different tables in one response.

----------------------------------------------------------------
SPECIAL QUERY RULES (STRICT)
----------------------------------------------------------------
- When a user asks for "Reza's list" or "Reza list":
    You MUST query using:
        filter_column = "Reza's List"
        filter_value = "1"

- Do NOT search for the word "Reza" in any text column.

- When a user asks for parts that can be scrapped:
    You MUST query using:
        filter_column = "Status"
        filter_value = "May be eligible to be scrapped"

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
- Do not describe system behavior or explain how data is retrieved.
- Do not mention retrieving rows, tools, or internal processes.
- Keep responses concise and focused only on results.

Allowed columns (primary table):
- PartNumber
- Status
- Details
- Processed_Date
- QOH
- Reza's List

Allowed columns (supplemental table — production.dimProducts):
- PartNumber
- Description
- Phase
- IsTopLevelPart, IsConfiguredPart, IsConfiguredPartComponent
- IsSerialized, IsLinkLicense, IsPhantomPart, IsBinItem
- IsWebEnabled, IsNonPhysical
- International_PowerCord, CustomButton
- Effective Date, DateAdded
- PartNumberPrefix, PartNumberModel, PartNumberSuffix

----------------------------------------------------------------
OUTPUT REQUIREMENT
----------------------------------------------------------------
- Never return an empty response.
"""

# Conservative pattern for detecting PartNumber-style queries
PART_NUMBER_PATTERN = re.compile(r"\b\d[\w\-]+\b")

SUPPLEMENTAL_PART_KEYWORDS = (
    "description",
    "phase",
    "custom button",
    "international power",
    "power cord",
    "product flag",
    "product details",
    "part details",
    "lookup part details",
    "catalogue",
    "catalog",
    "serialized",
    "non-physical",
    "top level",
    "configured",
    "phantom",
    "bin item",
    "web enabled",
)

PRIMARY_PART_KEYWORDS = (
    "status",
    "scrap",
    "scrapped",
    "eligible",
    "eligibility",
    "disposition",
    "bom",
    "stock",
    "work order",
    "sales order",
    "where used",
)

def interpret_scrap_status(part: str, status: str) -> str:
    """
    Maps Status values to exact business-approved human responses.
    """
    if not status:
        return f"Part {part} scrap eligibility is unknown."

    status_map = {
        "NOT eligible for scrap - Bin Location-[SHOW]": (
            f"Part {part} is not eligible to be scrapped because it is currently in a trade show"
        ),
        "Component Request - Please review Logid": (
            f"Part {part} is not eligible to be scrapped because it needs further review, in Component Request was flagged as a possible replacement."
        ),
        "No stock": f"Part {part} is not currently in stock",
        "Product USAGE": (
            f"Part {part} is not eligible to be scrapped because it had product usage in last two years"
        ),
        "In WhereUsed with parent": (
            f"Part {part} is not eligible to be scrapped because it it used in a higher level assembly which is active"
        ),
        "NOT eligible for scrap - Bin Stock": (
            f"Part {part} is not eligible to be scrapped because it is in bin stock"
        ),
        "NOT eligible for scrap - NOT A PHYSICAL PART": (
            f"Part {part} is not eligible to be scrapped because it is not a physical part"
        ),
        "May be eligible to be scrapped": f"Part {part} may be eligible to be scrapped",
        "Need Further Review-NO BOM": (
            f"Part {part} is not eligible to be scrapped, it needs further review- NO BOM"
        ),
        "Sold in Past Two Years": (
            f"Part {part} is not eligible to be scrapped because it was sold in past two years"
        ),
        "Open WorkOrder": (
            f"Part {part} is not eligible to be scrapped because it has an open work order"
        ),
        "Open Sales Order": (
            f"Part {part} is not eligible to be scrapped because it has an open sales order"
        ),
        "NOT eligible for scrap - Custom Button": (
            f"Part {part} is not eligible to be scrapped because it is a custom button"
        ),
        "REPAIR USAGE- Need Further review": (
            f"Part {part} is not eligible to be scrapped because it has been in repair usage in past 3 years"
        ),
        "NOT eligible for scrap - International Powercord": (
            f"Part {part} is not eligible to be scrapped because it is an international powercord"
        ),
    }

    return status_map.get(status, f"Part {part} has a status of “{status}”.")


def extract_part_number(text: str) -> Optional[str]:
    match = PART_NUMBER_PATTERN.search(text)
    return match.group(0) if match else None


def classify_part_query_intent(text: str) -> str:
    lowered = text.lower()
    if any(keyword in lowered for keyword in SUPPLEMENTAL_PART_KEYWORDS):
        return "supplemental"
    if any(keyword in lowered for keyword in PRIMARY_PART_KEYWORDS):
        return "primary"
    return "unknown"

def wants_excel(text: str) -> bool:
    text = text.lower()
    return any(kw in text for kw in ("excel", "spreadsheet", "download", "export"))


def _as_bool_flag(value: object) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
    return None


def _format_supplemental_part_response(part: str, row: dict, user_message: str = "") -> str:
    """Build a concise fallback answer from supplemental product details."""
    lowered = user_message.lower()

    if "description" in lowered:
        value = row.get("Description")
        if value not in (None, "", [], {}):
            return f"Part {part} description: {value}"
        return f"Description was not available for part {part}."

    if "phase" in lowered:
        value = row.get("Phase")
        if value not in (None, "", [], {}):
            return f"Part {part} phase: {value}"
        return f"Phase was not available for part {part}."

    if "custom button" in lowered:
        value = _as_bool_flag(row.get("CustomButton"))
        if value is not None:
            return f"Part {part} is{' ' if value else ' not '}a custom button."
        return f"CustomButton was not available for part {part}."

    if "international power" in lowered or "power cord" in lowered:
        value = _as_bool_flag(row.get("International_PowerCord"))
        if value is not None:
            return f"Part {part} is{' ' if value else ' not '}an international power cord."
        return f"International_PowerCord was not available for part {part}."

    fields = [
        "Description",
        "Phase",
        "International_PowerCord",
        "CustomButton",
        "IsSerialized",
        "IsNonPhysical",
        "IsTopLevelPart",
        "IsConfiguredPart",
        "IsConfiguredPartComponent",
        "IsLinkLicense",
        "IsPhantomPart",
        "IsBinItem",
        "IsWebEnabled",
    ]
    parts = []
    for field in fields:
        value = row.get(field)
        if value in (None, "", [], {}):
            continue
        parts.append(f"{field}: {value}")

    if parts:
        return f"Part {part} product details: " + "; ".join(parts)

    return f"Product details were found for part {part}."


def _build_part_query_response(
    *,
    requested_part: str,
    rows: list[dict],
    model_text: str,
    source_role: str,
    user_message: str = "",
) -> str:
    """Choose the final answer for part-number queries based on table role."""
    if not rows:
        if source_role == "supplemental":
            return f"I couldn't find product details for part {requested_part}."
        return "I couldn't find anything for that part number."

    if source_role == "supplemental":
        return _format_supplemental_part_response(requested_part, rows[0], user_message)

    if len(rows) == 1:
        row = rows[0]
        part = row.get("PartNumber", "Unknown PartNumber")
        status = row.get("Status", "Unknown Status")
        return interpret_scrap_status(part, status)

    return f"{len(rows)} records match your request."

# -------------------------------------------------------------------
# AGENT KERNEL
# -------------------------------------------------------------------

class AgentKernel:
    def __init__(self, settings: Settings, data_loader: DataLoader) -> None:
        if _AGENT_IMPORT_ERROR is not None:
            raise ImportError(
                "Agent runtime dependencies are unavailable. "
                "Please install compatible versions of agent-framework and openai."
            ) from _AGENT_IMPORT_ERROR

        self._data_buffer: list[str] = []
        self._file_buffer: list[dict] = []
        self._last_result_buffer: dict = {}
        self._data_loader = data_loader
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
            if roles
            else "  (no tables loaded)"
        )
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(table_roles=table_roles_str)
        self._agent = Agent(
            client=client,
            instructions=system_prompt,
            tools=tools,
        )
        self._sessions: Dict[str, object] = {}

    def _get_session(self, conversation_id: str):
        if conversation_id not in self._sessions:
            self._sessions[conversation_id] = self._agent.create_session()
        return self._sessions[conversation_id]

    def reset_conversation(self, conversation_id: str) -> None:
        """Clears the cached session so the next message starts fresh."""
        self._sessions.pop(conversation_id, None)

    # -------------------------------------------------------------------
    # MAIN ENTRY
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
            part_query_intent = classify_part_query_intent(user_message) if is_part_query else "unknown"
            try:
                if is_part_query and part_query_intent in {"primary", "supplemental"}:
                    lookup = self._data_loader.lookup_part(requested_part or "")
                    roles = self._data_loader.get_table_roles()
                    for table_name, table_rows in lookup.get("tables", {}).items():
                        if roles.get(table_name) != part_query_intent:
                            continue
                        self._last_result_buffer.update(
                            {
                                "table": table_name,
                                "rows": table_rows,
                                "columns": lookup.get("columns_by_table", {}).get(table_name, []),
                            }
                        )
                        break
                    model_text = ""
                else:
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
            source_table = str(self._last_result_buffer.get("table", ""))
            source_role = self._data_loader.get_table_roles().get(source_table, "") if source_table else ""
            # ------------------------------------------------------------
            # CASE-INSENSITIVE MATCH (UNCHANGED)
            # ------------------------------------------------------------
            if is_part_query and rows and requested_part:
                requested_norm = requested_part.upper()
                rows = [r for r in rows if str(r.get("PartNumber", "")).upper() == requested_norm]
            # RESPONSE GENERATION (UPDATED SECTION ONLY)
            # ------------------------------------------------------------
            if is_part_query:
                response_text = _build_part_query_response(
                    requested_part=requested_part or "Unknown PartNumber",
                    rows=rows or [],
                    model_text=model_text,
                    source_role=source_role,
                    user_message=user_message,
                )

            elif rows:
                response_text = f"{len(rows)} records match your request."

            elif model_text.strip() and not is_part_query:
                response_text = model_text.strip()

            else:
                response_text = "No data was returned."
            # HARD UX RULE ENFORCEMENT (UNCHANGED)
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
