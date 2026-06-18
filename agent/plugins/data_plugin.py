"""
Data access tools for the Microsoft Agent Framework.

TOOLS ARE STRICTLY NON-CONVERSATIONAL.
- Tools NEVER ask questions.
- Tools NEVER offer options.
- Tools ONLY return data or neutral status signals.

UX DECISIONS (lists, Excel, follow-ups) are owned by the kernel.
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

REZA_LIST_COLUMNS = [
    "PartNumber",
    "P/C Phase",
    "DateAdded",
    "QOH",
    "Obsolete Reserve$",
]

SCRAP_LIST_COLUMNS = [
    "PartNumber",
    "Status",
    "Processed_Date",
]

# -------------------------------------------------------------------
# Helper functions
# -------------------------------------------------------------------

def _rows_to_chunks(rows: List[dict], columns: List[str]) -> List[str]:
    """
    Convert rows to markdown tables with chunking.
    Tools do NOT decide whether chunks are shown — kernel decides.
    """
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
    """Validate Status values against the authoritative enum."""
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
    """
    Persist last query result for Excel export ONLY.
    Table name remains internal and is never exposed to the user.
    """
    last_result.clear()
    last_result.update(
        {
            "table": table_name,
            "rows": rows,
            "columns": columns,
        }
    )


def _is_reza_list_filter(
    filter_column: Optional[str],
    filter_value: Optional[str],
) -> bool:
    return (
        filter_column == "Reza's List"
        and str(filter_value).strip() in {"1", "1.0", "True", "true"}
    )


def _is_scrap_list_filter(
    filter_column: Optional[str],
    filter_value: Optional[str],
) -> bool:
    return (
        filter_column == "Status"
        and filter_value == "May be eligible to be scrapped"
    )


def _project_rows_and_columns(
    rows: List[dict],
    columns: List[str],
    filter_column: Optional[str] = None,
    filter_value: Optional[str] = None,
    query_expr: Optional[str] = None,
) -> tuple[List[dict], List[str]]:
    """
    Apply only the special column projections that are required.

    Reza's list:
      filter_column = "Reza's List"
      filter_value = 1

    Scrap list:
      filter_column = "Status"
      filter_value = "May be eligible to be scrapped"

    Everything else remains unchanged.
    """
    if not rows:
        return rows, columns

    if _is_reza_list_filter(filter_column, filter_value):
        projected_rows = [
            {col: row.get(col) for col in REZA_LIST_COLUMNS}
            for row in rows
        ]
        return projected_rows, REZA_LIST_COLUMNS

    if _is_scrap_list_filter(filter_column, filter_value):
        projected_rows = [
            {col: row.get(col) for col in SCRAP_LIST_COLUMNS}
            for row in rows
        ]
        return projected_rows, SCRAP_LIST_COLUMNS

    if query_expr:
        expr_lower = query_expr.lower()

        if "reza" in expr_lower and "list" in expr_lower:
            projected_rows = [
                {col: row.get(col) for col in REZA_LIST_COLUMNS}
                for row in rows
            ]
            return projected_rows, REZA_LIST_COLUMNS

        if "may be eligible to be scrapped" in expr_lower:
            projected_rows = [
                {col: row.get(col) for col in SCRAP_LIST_COLUMNS}
                for row in rows
            ]
            return projected_rows, SCRAP_LIST_COLUMNS

    return rows, columns

# -------------------------------------------------------------------
# Tool factory
# -------------------------------------------------------------------

def create_data_tools(
    loader: DataLoader,
    data_buffer: list,
    file_buffer: list,
    last_result: dict,
    base_url: str = "",
) -> List[Callable[..., str]]:
    """
    Factory returning STRICT, SQL-backed data tools.

    Tools:
    - Execute queries
    - Store results
    - Return neutral machine-safe signals

    Tools DO NOT:
    - Ask questions
    - Offer choices
    - Suggest exports
    """

    def list_tables() -> str:
        return json.dumps(
            {t: loader.get_schema(t) for t in loader.list_tables()},
            indent=2,
            default=str,
        )

    def get_schema(
        table_name: Annotated[str, Field(description="Table name")],
    ) -> str:
        return json.dumps(
            loader.get_schema(table_name),
            indent=2,
            default=str,
        )

    def count_rows(
        table_name: Annotated[str, Field(description="Table name")],
        filter_column: Annotated[str, Field(description="Optional filter column")] = "",
        filter_value: Annotated[str, Field(description="Optional filter value")] = "",
    ) -> str:
        fc, fv = filter_column or None, filter_value or None
        error = _validate_status_filter(fc, fv)
        if error:
            return error

        # ✅ Table name deliberately omitted
        return json.dumps(
            {
                "count": loader.count_rows(table_name, fc, fv),
            },
            indent=2,
        )

    def get_rows(
        table_name: Annotated[str, Field(description="Table name")],
        filter_column: Annotated[str, Field(description="Optional filter column")] = "",
        filter_value: Annotated[str, Field(description="Optional filter value")] = "",
    ) -> str:
        """
        Retrieve rows.
        Tool NEVER decides how results are presented.
        """
        fc, fv = filter_column or None, filter_value or None
        error = _validate_status_filter(fc, fv)
        if error:
            return error

        result = loader.get_rows(table_name, fc, fv)

        # ✅ Case-insensitive EXACT PartNumber match
        if fc == "PartNumber" and fv:
            requested = fv.upper()
            result["rows"] = [
                row
                for row in result["rows"]
                if str(row.get("PartNumber", "")).upper() == requested
            ]
            result["total"] = len(result["rows"])

        if result["total"] == 0:
            return "No rows matched."

        projected_rows, projected_columns = _project_rows_and_columns(
            rows=result["rows"],
            columns=result["columns"],
            filter_column=fc,
            filter_value=fv,
        )

        _store_last_result(
            last_result,
            table_name,
            projected_rows,
            projected_columns,
        )

        data_buffer.extend(
            _rows_to_chunks(projected_rows, projected_columns)
        )

        # ✅ Neutral signal ONLY (no table name)
        return json.dumps(
            {
                "rows_retrieved": len(projected_rows),
            }
        )

    def get_distinct_values(
        table_name: Annotated[str, Field(description="Table name")],
        column: Annotated[str, Field(description="Column name")],
    ) -> str:
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
        result = loader.query_table(table_name, query_expr)

        if result["total"] == 0:
            return "No rows matched."

        projected_rows, projected_columns = _project_rows_and_columns(
            rows=result["rows"],
            columns=result["columns"],
            query_expr=query_expr,
        )

        _store_last_result(
            last_result,
            table_name,
            projected_rows,
            projected_columns,
        )

        data_buffer.extend(
            _rows_to_chunks(projected_rows, projected_columns)
        )

        # ✅ Neutral signal ONLY (no table name)
        return json.dumps(
            {
                "rows_retrieved": len(projected_rows),
            }
        )

    def group_by(
        table_name: Annotated[str, Field(description="Table name")],
        group_column: Annotated[str, Field(description="Group-by column")],
        agg_column: Annotated[str, Field(description="Aggregate column")] = "",
        agg_func: Annotated[str, Field(description="count, sum, mean, min, max")] = "count",
    ) -> str:
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

    def lookup_part_details(
        part_number: Annotated[str, Field(description="Part number to look up in the product catalogue")],
    ) -> str:
        """Return product-catalogue details for a part from supplemental tables."""
        result = loader.lookup_part(part_number)
        supplemental_rows: list[dict] = []
        supplemental_cols: list[str] = []
        for tname, rows in result.get("tables", {}).items():
            if loader.get_table_roles().get(tname) == "supplemental":
                supplemental_rows = rows
                supplemental_cols = result["columns_by_table"].get(tname, [])
                break

        if not supplemental_rows:
            return json.dumps({"rows_retrieved": 0})

        _store_last_result(last_result, "product_catalogue", supplemental_rows, supplemental_cols)
        data_buffer.extend(_rows_to_chunks(supplemental_rows, supplemental_cols))
        return json.dumps({"rows_retrieved": len(supplemental_rows)})

    def export_to_excel(
        table_name: Annotated[str, Field(description="Table name (optional)")] = "",
        filter_column: Annotated[str, Field(description="Optional filter column")] = "",
        filter_value: Annotated[str, Field(description="Optional filter value")] = "",
    ) -> str:
        """
        Generate an Excel file.
        Tool assumes kernel has already validated user intent.
        """
        if last_result and "rows" in last_result:
            rows = last_result["rows"]
            columns = last_result["columns"]
            table = "obsolescence_results"
        else:
            if not table_name:
                return "No data available for export."

            fc, fv = filter_column or None, filter_value or None
            error = _validate_status_filter(fc, fv)
            if error:
                return error

            result = loader.get_rows(table_name, fc, fv)
            if result["total"] == 0:
                return "No rows available for export."

            projected_rows, projected_columns = _project_rows_and_columns(
                rows=result["rows"],
                columns=result["columns"],
                filter_column=fc,
                filter_value=fv,
            )

            rows = projected_rows
            columns = projected_columns
            table = table_name

        os.makedirs(GENERATED_DIR, exist_ok=True)
        filename = f"{table}_{uuid4().hex[:8]}.xlsx"
        filepath = os.path.join(GENERATED_DIR, filename)

        df = pd.DataFrame(rows).reindex(columns=columns)
        df = df.where(pd.notna(df), "")
        df.to_excel(filepath, index=False, engine="openpyxl")

        file_url = (
            f"{base_url}/api/files/{filename}"
            if base_url
            else f"/api/files/{filename}"
        )

        file_buffer.append(
            {
                "name": filename,
                "path": file_url,
            }
        )

        return json.dumps(
            {
                "excel_generated": True,
                "row_count": len(rows),
            }
        )

    return [
        list_tables,
        get_schema,
        count_rows,
        get_rows,
        get_distinct_values,
        query_table,
        group_by,
        lookup_part_details,
        export_to_excel,
    ]