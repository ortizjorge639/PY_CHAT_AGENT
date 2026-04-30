"""
Data access tools for the Microsoft Agent Framework.
 
All tools operate on SQL-backed tables via DataLoader.
Results are returned inline by default.
Excel files are generated ONLY when explicitly requested by the user.
"""
 
import json
import logging
import os
from typing import Annotated, Callable, List, Optional
from uuid import uuid4
 
import pandas as pd
from pydantic import Field
 
from data.loader import DataLoader, CHUNK_SIZE
 
logger = logging.getLogger(__name__)
 
# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------
 
GENERATED_DIR = os.environ.get(
    "GENERATED_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "generated"),
)
MAX_INLINE_ROWS: Optional[int] = None  # None = no auto-excel fallback
 
VALID_STATUS_VALUES = {
    "NOT eligible for scrap - Bin Location-[SHOW]",
    "Component Request - Please review Logid",
    "No stock",
    "Product USAGE",
    "In WhereUsed with parent",
    "NOT eligible for scrap - Bin Stock",
    "NOT eligible for scrap - NOT A PHYSICAL PART",
    "May be eligible to be scrapped",
    "Need Further Review-NO BOM",
    "Sold in Past Two Years",
    "Open WorkOrder",
    "Open Sales Order",
    "NOT eligible for scrap - Custom Button",
    "REPAIR USAGE- Need Further review",
    "NOT eligible for scrap - International Powercord",
}
 
# -------------------------------------------------------------------
# Helper functions
# -------------------------------------------------------------------
 
def _rows_to_chunks(rows: List[dict], columns: List[str]) -> List[str]:
    """Convert rows to markdown tables with chunking and NaN cleanup."""
    if not rows:
        return []
 
    chunks: List[str] = []
    total = len(rows)
 
    for i in range(0, total, CHUNK_SIZE):
        df = pd.DataFrame(rows[i : i + CHUNK_SIZE])
        df = df.reindex(columns=columns)
        df = df.where(pd.notna(df), "")
 
        header = f"**Rows {i + 1}–{min(i + CHUNK_SIZE, total)} of {total}**\n\n"
        chunks.append(header + df.to_markdown(index=False))
 
    return chunks
 
 
def _validate_status_filter(
    filter_column: Optional[str],
    filter_value: Optional[str],
) -> Optional[str]:
    """Validate Status filter values against the canonical enum."""
    if filter_column == "Status" and filter_value not in VALID_STATUS_VALUES:
        return json.dumps(
            {
                "error": "Invalid Status value",
                "allowed_values": sorted(VALID_STATUS_VALUES),
            },
            indent=2,
        )
    return None
 
 
def _store_last_result(
    last_result: dict,
    table_name: str,
    rows: List[dict],
    columns: List[str],
) -> None:
    """Persist last query result for conversational Excel exports."""
    last_result.clear()
    last_result.update(
        {
            "table": table_name,
            "rows": rows,
            "columns": columns,
        }
    )
 
 
# -------------------------------------------------------------------
# Tool factory
# -------------------------------------------------------------------
 
def create_data_tools(
    loader: DataLoader,
    data_buffer: list,
    file_buffer: list,
    last_result: dict,
) -> List[Callable[..., str]]:
    """Factory returning SQL-backed data tools for Agent Framework."""
 
    def list_tables() -> str:
        """List all available tables and their schemas."""
        return json.dumps(
            {t: loader.get_schema(t) for t in loader.list_tables()},
            indent=2,
            default=str,
        )
 
    def get_schema(
        table_name: Annotated[str, Field(description="Table name")],
    ) -> str:
        """Get column names and types for a table."""
        return json.dumps(loader.get_schema(table_name), indent=2, default=str)
 
    def count_rows(
        table_name: Annotated[str, Field(description="Table name")],
        filter_column: Annotated[str, Field(description="Optional filter column")] = "",
        filter_value: Annotated[str, Field(description="Optional filter value")] = "",
    ) -> str:
        """Return the exact number of rows matching the filter."""
        fc, fv = filter_column or None, filter_value or None
        error = _validate_status_filter(fc, fv)
        if error:
            return error
 
        return json.dumps(
            {
                "table": table_name,
                "count": loader.count_rows(table_name, fc, fv),
                "filter_column": fc,
                "filter_value": fv,
            },
            indent=2,
        )

    def get_rows(
        table_name: Annotated[str, Field(description="Table name")],
        filter_column: Annotated[str, Field(description="Optional filter column")] = "",
        filter_value: Annotated[str, Field(description="Optional filter value")] = "",
    ) -> str:
        """
        Retrieve rows and return them inline as markdown tables.
        This tool does NOT generate Excel files.
        """
        fc, fv = filter_column or None, filter_value or None
        error = _validate_status_filter(fc, fv)
        if error:
            return error
 
        result = loader.get_rows(table_name, fc, fv)
        if result["total"] == 0:
            return "No rows matched."
 
        _store_last_result(
            last_result,
            table_name,
            result["rows"],
            result["columns"],
        )
 
        cols = ", ".join(result["columns"])
        data_buffer.extend(
            _rows_to_chunks(result["rows"], result["columns"])
        )
        return (
            f"Retrieved {result['total']} rows from table '{table_name}' "
            f"(columns: {cols}). Data has been sent directly to the user "
            f"as inline messages. Do NOT fabricate or repeat the data. "
            f"If the user wants a downloadable Excel file, call export_to_excel."
        )

    def get_distinct_values(
        table_name: Annotated[str, Field(description="Table name")],
        column: Annotated[str, Field(description="Column name")],
    ) -> str:
        """Return sorted distinct values for a column."""
        if column == "Status":
            return json.dumps(sorted(VALID_STATUS_VALUES), indent=2)
 
        return json.dumps(
            loader.get_distinct_values(table_name, column),
            indent=2,
            default=str,
        )

    def query_table(
        table_name: Annotated[str, Field(description="Table name")],
        query_expr: Annotated[
            str, Field(description="Pandas DataFrame.query() expression")
        ],
    ) -> str:
        """
        Run a pandas-style query expression.
        Results are returned inline.
        """
        result = loader.query_table(table_name, query_expr)
        if result["total"] == 0:
            return "No rows matched."
 
        _store_last_result(
            last_result,
            table_name,
            result["rows"],
            result["columns"],
        )
 
        cols = ", ".join(result["columns"])
        data_buffer.extend(
            _rows_to_chunks(result["rows"], result["columns"])
        )
        return (
            f"Retrieved {result['total']} rows from table '{table_name}' "
            f"(columns: {cols}). Data has been sent directly to the user "
            f"as inline messages. Do NOT fabricate or repeat the data. "
            f"If the user wants a downloadable Excel file, call export_to_excel."
        )

    def group_by(
        table_name: Annotated[str, Field(description="Table name")],
        group_column: Annotated[str, Field(description="Group-by column")],
        agg_column: Annotated[
            str, Field(description="Column to aggregate (optional)")
        ] = "",
        agg_func: Annotated[
            str, Field(description="count, sum, mean, min, max")
        ] = "count",
    ) -> str:
        """Group and aggregate rows."""
        return json.dumps(
            loader.group_by(
                table_name,
                group_column,
                agg_column or None,
                agg_func,
            ),
            indent=2,
            default=str,
        )
 
    def export_to_excel(
        table_name: Annotated[str, Field(description="Table name (optional)")] = "",
        filter_column: Annotated[str, Field(description="Optional filter column")] = "",
        filter_value: Annotated[str, Field(description="Optional filter value")] = "",
    ) -> str:
        """
        Generate an Excel file.
 
        ONLY call this tool when the user explicitly asks for:
        - an Excel file
        - a spreadsheet
        - a download
        - an export
 
        If a previous query exists, that data is exported.
        Otherwise, a fresh query is executed.
        """
 
        # Case 1: Export previously retrieved data
        if last_result and "rows" in last_result:
            rows = last_result["rows"]
            columns = last_result["columns"]
            table = last_result.get("table", "data")
 
        # Case 2: Fresh query
        else:
            if not table_name:
                return "No previous data available. Please specify a table to export."
 
            fc, fv = filter_column or None, filter_value or None
            error = _validate_status_filter(fc, fv)
            if error:
                return error
 
            result = loader.get_rows(table_name, fc, fv)
            if result["total"] == 0:
                return "No matching rows. Excel not created."
 
            rows = result["rows"]
            columns = result["columns"]
            table = table_name
 
        os.makedirs(GENERATED_DIR, exist_ok=True)
        filename = f"{table}_{uuid4().hex[:8]}.xlsx"
        filepath = os.path.join(GENERATED_DIR, filename)

        df = pd.DataFrame(rows).reindex(columns=columns)
        df = df.where(pd.notna(df), "")
        df.to_excel(filepath, index=False, engine="openpyxl")
        logger.info("Generated Excel: %s (%d rows)", filename, len(rows))
 
        file_buffer.append(
            {
                "name": filename,
                "path": f"/api/files/{filename}",
            }
        )
 
        row_count = len(rows)
        last_result.clear()
        return (
            f"Excel file generated ({row_count} rows). "
            f"The download link has been automatically sent to the user. "
            f"Do NOT include any links, URLs, or file paths in your response."
        )
 
    return [
        list_tables,
        get_schema,
        count_rows,
        get_rows,
        get_distinct_values,
        query_table,
        group_by,
        export_to_excel,
    ]