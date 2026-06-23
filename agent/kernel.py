"""
Microsoft Agent Framework setup — Azure OpenAI agent with tool calling.
"""

import asyncio
import logging
import re
from typing import Any
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
from agent.plugins.viz_plugin import create_aggregated_chart, format_rows_as_markdown_chunks

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
- Controlled cross-table filtering is allowed only when the user asks
    for primary-table results filtered by supplemental-table attributes.
    Use PartNumber as the lookup key and return primary-table rows.

----------------------------------------------------------------
TABLE ROUTING RULES (STRICT)
----------------------------------------------------------------
- Scrap eligibility / Status / Disposition  → PRIMARY table
- Description / Phase / product flags       → call lookup_part_details(part_number=…)
- Unspecified part question                 → check PRIMARY first; use supplemental on follow-up
- Do NOT mix columns from different tables in one response unless the
    user explicitly asks for a primary-table result constrained by
    supplemental-table attributes.

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

CHART_KEYWORDS = ("chart", "graph", "visualization", "plot")
DATE_ADDED_ALIASES = ("date added", "dateadded")
PROCESSED_DATE_ALIASES = ("processed date", "processed_date")
MODEL_PROCESSED_DATE_ALIASES = ("model processed date", "modelprocesseddate")
TREND_ALIASES = ("trend", "over time")
BAR_ALIASES = ("bar", "column", "histogram")
PIE_ALIASES = ("pie", "donut", "doughnut")

PRIMARY_STATUS_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("product usage",), "Product USAGE"),
    (("component request",), "Component Request - Please review Logid"),
    (("open workorder", "open work order"), "Open WorkOrder"),
    (("open sales order",), "Open Sales Order"),
    (("sold in past two years", "sold past two years"), "Sold in Past Two Years"),
    (("need further review", "no bom"), "Need Further Review-NO BOM"),
    (("in whereused with parent", "whereused with parent"), "In WhereUsed with parent"),
    (("repair usage",), "REPAIR USAGE- Need Further review"),
    (("custom button",), "NOT eligible for scrap - Custom Button"),
    (("international powercord", "international power cord"), "NOT eligible for scrap - International Powercord"),
    (("bin stock",), "NOT eligible for scrap - Bin Stock"),
    (("bin location", "show bin"), "NOT eligible for scrap - Bin Location-[SHOW]"),
    (("not a physical part",), "NOT eligible for scrap - NOT A PHYSICAL PART"),
    (("no stock",), "No stock"),
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


def _extract_phase_filter(text: str) -> Optional[str]:
    match = re.search(r"phase(?:\s*(?:=|is|of|in))?\s+([\w\-]+)", text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _extract_supplemental_filters(text: str) -> dict[str, str]:
    lowered = text.lower()
    filters: dict[str, str] = {}

    phase_filter = _extract_phase_filter(text)
    if phase_filter:
        filters["Phase"] = phase_filter

    if "custom button" in lowered or "custombutton" in lowered:
        filters["CustomButton"] = "1"

    if "international power" in lowered or "power cord" in lowered or "intl power" in lowered:
        filters["International_PowerCord"] = "1"

    return filters


def _extract_primary_status_filters(text: str) -> list[str]:
    lowered = text.lower()
    statuses: list[str] = []
    seen: set[str] = set()

    for keywords, canonical_status in PRIMARY_STATUS_KEYWORDS:
        if any(keyword in lowered for keyword in keywords) and canonical_status not in seen:
            statuses.append(canonical_status)
            seen.add(canonical_status)

    return statuses


def _build_primary_query_expr(user_message: str, wants_scrap: bool) -> str | None:
    explicit_statuses = _extract_primary_status_filters(user_message)
    if explicit_statuses:
        if len(explicit_statuses) == 1:
            status = explicit_statuses[0].replace("'", "\\'")
            return f"Status == '{status}'"
        escaped = [status.replace("'", "\\'") for status in explicit_statuses]
        serialized = ", ".join(f"'{value}'" for value in escaped)
        return f"Status in [{serialized}]"

    if wants_scrap:
        return "Status == 'May be eligible to be scrapped'"

    return None


def _mentions_scrappable_parts(text: str) -> bool:
    lowered = text.lower()
    return "scrap" in lowered or "scrapp" in lowered


def _is_line_chart_request(text: str) -> bool:
    return _is_chart_request(text)


def _is_chart_request(text: str) -> bool:
    lowered = text.lower()
    has_chart_keyword = any(keyword in lowered for keyword in CHART_KEYWORDS)
    has_trend_keyword = any(keyword in lowered for keyword in TREND_ALIASES)
    has_metric_hint = any(keyword in lowered for keyword in ("count", "counts", "x axis", "y axis", "by"))

    if "line chart" in lowered:
        return True
    if has_chart_keyword and has_metric_hint:
        return True
    if has_trend_keyword and ("scrap" in lowered or "count" in lowered):
        return True
    if "line" in lowered and (has_chart_keyword or has_trend_keyword):
        return True
    if any(alias in lowered for alias in BAR_ALIASES + PIE_ALIASES):
        return True
    return False


def _extract_chart_type(text: str) -> str:
    lowered = text.lower()
    if any(alias in lowered for alias in PIE_ALIASES):
        return "pie"
    if any(alias in lowered for alias in BAR_ALIASES):
        return "bar"
    return "line"


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _resolve_column_hint(hint: str, available_columns: list[str]) -> str | None:
    normalized_hint = _normalize_identifier(hint)
    if not normalized_hint:
        return None

    by_normalized = { _normalize_identifier(column): column for column in available_columns }
    if normalized_hint in by_normalized:
        return by_normalized[normalized_hint]

    partial_matches = [
        column for column in available_columns
        if normalized_hint in _normalize_identifier(column) or _normalize_identifier(column) in normalized_hint
    ]
    if partial_matches:
        return min(partial_matches, key=len)
    return None


def _requested_date_added(text: str) -> bool:
    lowered = text.lower()
    return any(alias in lowered for alias in DATE_ADDED_ALIASES)


def _supplemental_non_null_count(loader: DataLoader, column: str) -> int:
    total = 0
    for table_name in loader.get_tables_by_role("supplemental"):
        table = loader._tables.get(table_name)
        if table is None or column not in table.columns:
            continue
        total += int(table[column].notna().sum())
    return total


def _extract_chart_x_column(text: str, available_columns: list[str]) -> str:
    lowered = text.lower()
    if any(alias in lowered for alias in DATE_ADDED_ALIASES):
        for candidate in ("DateAdded", "DateAdded_supplemental"):
            if candidate in available_columns:
                return candidate
    if any(alias in lowered for alias in PROCESSED_DATE_ALIASES):
        for candidate in ("Processed_Date", "ModelProcessedDate"):
            if candidate in available_columns:
                return candidate
    if any(alias in lowered for alias in MODEL_PROCESSED_DATE_ALIASES):
        if "ModelProcessedDate" in available_columns:
            return "ModelProcessedDate"

    x_axis_match = re.search(r"x\s*axis\s*(?:is|=)\s*([\w\s/\-$']+)", text, flags=re.IGNORECASE)
    if x_axis_match:
        resolved = _resolve_column_hint(x_axis_match.group(1).strip(), available_columns)
        if resolved:
            return resolved

    chart_type = _extract_chart_type(text)
    if chart_type == "line":
        for candidate in ("DateAdded", "DateAdded_supplemental", "Processed_Date", "ModelProcessedDate"):
            if candidate in available_columns:
                return candidate
        raise ValueError("No supported date column is available for charting.")

    for candidate in ("Status", "P/C Phase", "Phase", "Processed_Date", "ModelProcessedDate", "PartNumber"):
        if candidate in available_columns:
            return candidate
    raise ValueError("No suitable x-axis column is available for charting.")


def _extract_chart_metric(text: str, available_columns: list[str]) -> tuple[str, str | None]:
    lowered = text.lower()
    if "y axis" in lowered and "count" in lowered:
        return ("count", None)
    if any(token in lowered for token in ("count", "counts", "number of")):
        return ("count", None)

    metric = "count"
    if any(token in lowered for token in ("average", "avg", "mean")):
        metric = "avg"
    elif any(token in lowered for token in ("sum", "total")):
        metric = "sum"

    y_axis_match = re.search(r"y\s*axis\s*(?:is|=)\s*([\w\s/\-$']+)", text, flags=re.IGNORECASE)
    if y_axis_match:
        y_hint = y_axis_match.group(1).strip()
        if _normalize_identifier(y_hint) == "count":
            return ("count", None)
        resolved = _resolve_column_hint(y_hint, available_columns)
        if resolved:
            return (metric if metric != "count" else "sum", resolved)

    metric_col_match = re.search(r"(?:sum|total|average|avg|mean)(?:\s+of)?\s+([\w\s/\-$']+)", text, flags=re.IGNORECASE)
    if metric_col_match:
        resolved = _resolve_column_hint(metric_col_match.group(1).strip(), available_columns)
        if resolved:
            return (metric if metric != "count" else "sum", resolved)

    return ("count", None)


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
        self._settings = settings
        self._data_loader = data_loader
        self._conversation_locks: Dict[str, asyncio.Lock] = {}
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

    def _get_lock(self, conversation_id: str) -> asyncio.Lock:
        if conversation_id not in self._conversation_locks:
            self._conversation_locks[conversation_id] = asyncio.Lock()
        return self._conversation_locks[conversation_id]

    def reset_conversation(self, conversation_id: str) -> None:
        """Clears the cached session so the next message starts fresh."""
        self._sessions.pop(conversation_id, None)
        self._conversation_locks.pop(conversation_id, None)

    def reset_all_sessions(self) -> int:
        """Clears all cached sessions and returns the number removed."""
        cleared = len(self._sessions)
        self._sessions.clear()
        self._conversation_locks.clear()
        return cleared

    def _handle_structured_data_request(self, user_message: str) -> dict[str, Any] | None:
        supplemental_filters = _extract_supplemental_filters(user_message)
        wants_scrap = _mentions_scrappable_parts(user_message)
        wants_list = "list" in user_message.lower()
        wants_chart = _is_chart_request(user_message)

        if not (wants_list or wants_chart):
            return None
        if not wants_scrap and not supplemental_filters and not wants_chart:
            return None

        primary_table = self._data_loader.get_primary_table_name()
        query_expr = _build_primary_query_expr(user_message, wants_scrap)

        if wants_chart:
            merged = self._data_loader.get_cross_filtered_frame(
                primary_table,
                query_expr=query_expr,
                supplemental_filters=supplemental_filters or None,
            )
            if _requested_date_added(user_message):
                has_date_added = any(column in merged.columns for column in ("DateAdded", "DateAdded_supplemental"))
                if not has_date_added:
                    available_date_columns = [
                        column
                        for column in ("ModelProcessedDate", "Processed_Date")
                        if column in merged.columns
                    ]
                    if available_date_columns:
                        options = ", ".join(available_date_columns)
                        return {
                            "text": f"DateAdded is not available in the current dataset. Available date columns: {options}.",
                            "data_chunks": [],
                            "files": [],
                            "visualizations": [],
                        }
                    return {
                        "text": "DateAdded is not available in the current dataset.",
                        "data_chunks": [],
                        "files": [],
                        "visualizations": [],
                    }
            if merged.empty:
                return {
                    "text": "No data was returned.",
                    "data_chunks": [],
                    "files": [],
                    "visualizations": [],
                }
            x_column = _extract_chart_x_column(user_message, list(merged.columns))
            chart_type = _extract_chart_type(user_message)
            y_metric, y_column = _extract_chart_metric(user_message, list(merged.columns))
            if y_metric in {"sum", "avg"} and not y_column:
                return {
                    "text": "Please specify a numeric y-axis column (for example: y axis is QOH).",
                    "data_chunks": [],
                    "files": [],
                    "visualizations": [],
                }
            if y_metric == "count":
                chart_title = f"Count by {x_column}"
            else:
                chart_title = f"{y_metric.upper()}({y_column}) by {x_column}"

            visualization = create_aggregated_chart(
                merged,
                chart_type=chart_type,
                x_column=x_column,
                y_metric=y_metric,
                y_column=y_column,
                title=chart_title,
                base_url=self._settings.base_url,
            )
            y_label = "count" if y_metric == "count" else f"{y_metric} of {y_column}"
            return {
                "text": f"Created a {chart_type} chart with {x_column} on the x-axis and {y_label} on the y-axis.",
                "data_chunks": [],
                "files": [],
                "visualizations": [visualization],
            }

        if wants_list and (wants_scrap or supplemental_filters):
            result = self._data_loader.query_table_with_cross_filter(
                primary_table,
                query_expr=query_expr,
                supplemental_filters=supplemental_filters or None,
            )
            if result["total"] == 0:
                if "Phase" in supplemental_filters and _supplemental_non_null_count(self._data_loader, "Phase") == 0:
                    return {
                        "text": "No data was returned because supplemental column Phase is empty in the current dataset.",
                        "data_chunks": [],
                        "files": [],
                        "visualizations": [],
                    }
                return {
                    "text": "No data was returned.",
                    "data_chunks": [],
                    "files": [],
                    "visualizations": [],
                }
            preferred_columns = [
                column for column in ["PartNumber", "Status", "Processed_Date"] if column in result["columns"]
            ] or result["columns"]
            return {
                "text": f"{result['total']} records match your request.",
                "data_chunks": format_rows_as_markdown_chunks(result["rows"], preferred_columns),
                "files": [],
                "visualizations": [],
            }

        return None

    # -------------------------------------------------------------------
    # MAIN ENTRY
    # -------------------------------------------------------------------

    async def ask(self, conversation_id: str, user_message: str) -> dict:
        async with self._get_lock(conversation_id):
            self._data_buffer.clear()
            self._file_buffer.clear()
            self._last_result_buffer.clear()
            structured_response = self._handle_structured_data_request(user_message)
            if structured_response is not None:
                return structured_response
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
                "visualizations": [],
            }
