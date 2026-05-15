"""Data access layer — loads from Excel or SQL Server based on DATASOURCE flag."""

import logging
import time
from difflib import get_close_matches
from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import Settings

logger = logging.getLogger(__name__)

CHUNK_SIZE: int = 60


def _bracket_table_name(raw: str) -> str:
    """Safely bracket a SQL table name, handling schema-qualified and pre-bracketed values."""
    raw = raw.strip()
    if raw.startswith("["):
        return raw
    parts = raw.split(".", 1)
    return ".".join(f"[{p}]" for p in parts)


def _fuzzy_resolve(needle: str, haystack: list[str], label: str = "value") -> str:
    """Case-insensitive lookup with fuzzy fallback.

    1. Exact match → return as-is
    2. Case-insensitive match → return the canonical form
    3. Fuzzy match (>0.6 cutoff) → return best match
    4. No match → raise ValueError with suggestions
    """
    if needle in haystack:
        return needle

    lower_map = {h.lower(): h for h in haystack}
    if needle.lower() in lower_map:
        return lower_map[needle.lower()]

    matches = get_close_matches(needle.lower(), [h.lower() for h in haystack], n=1, cutoff=0.6)
    if matches:
        return lower_map[matches[0]]

    raise ValueError(
        f"{label} '{needle}' not found. Available: {haystack}"
    )


class DataLoader:
    """Loads tabular data from Excel files or SQL Server and exposes query helpers."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tables: dict[str, pd.DataFrame] = {}
        self._table_roles: dict[str, str] = {}  # table_name → "primary" | "supplemental"
        self._load()

    # ── loaders ──────────────────────────────────────────

    def _load(self) -> None:
        source = self._settings.datasource.lower()
        if source == "excel":
            self._load_excel()
        elif source == "sql":
            self._load_sql()
        else:
            raise ValueError(f"Unknown DATASOURCE: {self._settings.datasource!r}")

    def _load_excel(self) -> None:
        import re
        folder = Path(self._settings.excel_folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"Excel folder not found: {folder}")

        # Timestamp-prefixed files (e.g. 20260312154848_output.xlsx) are primary
        timestamp_pattern = re.compile(r"^\d{8,}_")

        for fp in sorted(folder.glob("*.xlsx")):
            if fp.name.startswith("~$"):
                continue  # skip Excel lock files
            xls = pd.ExcelFile(fp, engine="openpyxl")
            # Classify file role
            if timestamp_pattern.match(fp.stem):
                role = "primary"
            else:
                role = "supplemental"

            for sheet in xls.sheet_names:
                table_name = (
                    f"{fp.stem}__{sheet}" if len(xls.sheet_names) > 1 else fp.stem
                )
                df = pd.read_excel(xls, sheet_name=sheet)
                df.columns = [str(c).strip() for c in df.columns]
                self._tables[table_name] = df
                self._table_roles[table_name] = role
                logger.info(
                    "Loaded table '%s' [%s] (%d rows, %d cols)",
                    table_name,
                    role,
                    len(df),
                    len(df.columns),
                )

    @staticmethod
    def _detect_odbc_driver() -> str:
        """Auto-detect the best available SQL Server ODBC driver."""
        import pyodbc

        preferred = ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"]
        available = [d for d in pyodbc.drivers() if "SQL Server" in d]
        for driver in preferred:
            if driver in available:
                return driver
        if available:
            return available[0]
        raise RuntimeError(
            "No SQL Server ODBC driver found. "
            "Install 'ODBC Driver 17 for SQL Server' or 'ODBC Driver 18 for SQL Server' "
            "from https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server"
        )

    def _load_sql(self) -> None:
        try:
            import pyodbc  # deferred import — only needed for SQL data source
        except ImportError:
            raise ImportError(
                "pyodbc is required when DATASOURCE=sql. "
                "Install it with: pip install pyodbc>=5.0.0"
            ) from None

        s = self._settings
        driver = self._detect_odbc_driver()
        logger.info("Using ODBC driver: %s", driver)

        conn_str = (
            f"DRIVER={{{driver}}};"
            f"Server=tcp:{s.sql_server},{s.sql_port};"
            f"Database={s.sql_database};"
            f"UID={s.sql_username};"
            f"PWD={s.sql_password};"
            "Encrypt=yes;"
            "TrustServerCertificate=yes;"
            "Connection Timeout=60;"
        )
        logger.info("Connection string: %s", conn_str.replace(s.sql_password, "****"))

        max_retries = 3
        retry_delay = 5  # seconds
        for attempt in range(1, max_retries + 1):
            try:
                conn = pyodbc.connect(conn_str)
                break
            except pyodbc.OperationalError:
                if attempt == max_retries:
                    logger.error("SQL connection failed after %d attempts", max_retries)
                    raise
                logger.warning(
                    "SQL connect attempt %d/%d failed, retrying in %ds...",
                    attempt, max_retries, retry_delay,
                )
                time.sleep(retry_delay)

        tables = s.sql_table_list
        if not tables:
            conn.close()
            raise ValueError("No SQL tables configured. Set SQL_TABLES or SQL_TABLE.")

        primary = s.sql_primary_table or tables[0]

        for table in tables:
            df = pd.read_sql(f"SELECT * FROM {_bracket_table_name(table)}", conn)
            df.columns = [str(c).strip() for c in df.columns]
            # Coerce string columns that contain numeric values to numeric dtype
            for col in df.columns:
                if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
                    converted = pd.to_numeric(df[col], errors="coerce")
                    if converted.notna().sum() == df[col].notna().sum() and converted.notna().sum() > 0:
                        df[col] = converted
            role = "primary" if table == primary else "supplemental"
            self._tables[table] = df
            self._table_roles[table] = role
            logger.info(
                "Loaded SQL table '%s' [%s] (%d rows, %d cols)",
                table, role, len(df), len(df.columns),
            )

        conn.close()

    # ── public query API ─────────────────────────────────

    def list_tables(self) -> list[str]:
        """Return names of all loaded tables."""
        return list(self._tables.keys())

    def get_table_roles(self) -> dict[str, str]:
        """Return {table_name: role} for all tables."""
        return dict(self._table_roles)

    def get_schema(self, table_name: str) -> dict[str, str]:
        """Return {column_name: dtype} for a table."""
        df = self._get_table(table_name)
        return {col: str(df[col].dtype) for col in df.columns}

    def count_rows(
        self,
        table_name: str,
        filter_column: str | None = None,
        filter_value: str | None = None,
    ) -> int:
        """Exact row count, with optional single-column filter."""
        df = self._get_table(table_name)
        if filter_column and filter_value is not None:
            df = self._apply_filter(df, filter_column, filter_value)
        return len(df)

    def get_rows(
        self,
        table_name: str,
        filter_column: str | None = None,
        filter_value: str | None = None,
    ) -> dict[str, Any]:
        """Return ALL matching rows with metadata."""
        df = self._get_table(table_name)
        if filter_column and filter_value is not None:
            df = self._apply_filter(df, filter_column, filter_value)
        return {
            "table": table_name,
            "rows": df.to_dict(orient="records"),
            "total": len(df),
            "columns": list(df.columns),
        }

    def get_distinct_values(self, table_name: str, column: str) -> list[str]:
        """All unique non-null values in a column, sorted."""
        df = self._get_table(table_name)
        resolved = self._check_column(df, column, table_name)
        return sorted(df[resolved].dropna().unique().astype(str).tolist())

    def query_table(self, table_name: str, query_expr: str) -> dict[str, Any]:
        """Run a pandas DataFrame.query() expression and return all matching rows."""
        df = self._get_table(table_name)
        try:
            result = df.query(query_expr)
        except Exception as exc:
            raise ValueError(f"Invalid query expression: {exc}") from exc
        return {
            "table": table_name,
            "rows": result.to_dict(orient="records"),
            "total": len(result),
            "columns": list(result.columns),
        }

    def group_by(
        self,
        table_name: str,
        group_column: str,
        agg_column: str | None = None,
        agg_func: str = "count",
    ) -> list[dict[str, Any]]:
        """Group by a column with optional aggregation."""
        df = self._get_table(table_name)
        group_column = self._check_column(df, group_column, table_name)

        if agg_column:
            agg_column = self._check_column(df, agg_column, table_name)
            result = (
                df.groupby(group_column)[agg_column]
                .agg(agg_func)
                .reset_index()
            )
            result.columns = [group_column, f"{agg_func}_{agg_column}"]
        else:
            result = df.groupby(group_column).size().reset_index(name="count")

        return result.to_dict(orient="records")

    # ── helpers ──────────────────────────────────────────

    def lookup_part(self, part_number: str) -> dict[str, Any]:
        """Look up a part number across all tables that have a PartNumber column."""
        tables_result: dict[str, list[dict]] = {}
        columns_result: dict[str, list[str]] = {}

        for table_name, df in self._tables.items():
            if 'PartNumber' not in df.columns:
                continue
            matched = df[df['PartNumber'].astype(str).str.lower() == part_number.strip().lower()]
            if not matched.empty:
                tables_result[table_name] = matched.to_dict(orient='records')
                columns_result[table_name] = list(matched.columns)

        return {
            'part_number': part_number,
            'tables': tables_result,
            'columns_by_table': columns_result,
        }

    def lookup_row(self, table_name: str, column: str, value: str) -> dict[str, Any]:
        """Look up rows by any column+value pair in a specific table."""
        df = self._get_table(table_name)
        resolved_col = self._check_column(df, column, table_name)

        # Numeric comparison for numeric columns
        if pd.api.types.is_numeric_dtype(df[resolved_col]):
            try:
                num_val = float(value)
                matched = df[df[resolved_col] == num_val]
            except (ValueError, TypeError):
                matched = df[df[resolved_col].astype(str).str.lower() == value.strip().lower()]
        else:
            matched = df[df[resolved_col].astype(str).str.lower() == value.strip().lower()]

        return {
            'table': table_name,
            'column': resolved_col,
            'value': value,
            'rows': matched.to_dict(orient='records'),
            'total': len(matched),
            'columns': list(matched.columns),
        }


    def _get_table(self, table_name: str) -> pd.DataFrame:
        resolved = _fuzzy_resolve(table_name, list(self._tables.keys()), label="Table")
        if resolved != table_name:
            logger.info("Fuzzy-resolved table '%s' → '%s'", table_name, resolved)
        return self._tables[resolved]

    @staticmethod
    def _apply_filter(df: pd.DataFrame, column: str, value: str) -> pd.DataFrame:
        resolved_col = _fuzzy_resolve(column, list(df.columns), label="Column")
        if resolved_col != column:
            logger.info("Fuzzy-resolved column '%s' → '%s'", column, resolved_col)
        # Use numeric comparison for numeric columns to avoid "0.8" != "0.80"
        if pd.api.types.is_numeric_dtype(df[resolved_col]):
            try:
                num_val = float(value)
                return df[df[resolved_col] == num_val]
            except (ValueError, TypeError):
                pass
        # Fuzzy-match the filter value against actual unique values in the column
        unique_vals = df[resolved_col].dropna().astype(str).unique().tolist()
        if not unique_vals:
            return df.iloc[0:0]  # empty DataFrame with same columns
        try:
            resolved_val = _fuzzy_resolve(value, unique_vals, label="Value")
        except ValueError:
            # Value doesn't exist in the column — return empty (0 rows), not an error
            return df.iloc[0:0]
        return df[df[resolved_col].astype(str).str.lower() == resolved_val.lower()]

    @staticmethod
    def _check_column(df: pd.DataFrame, column: str, table_name: str) -> str:
        """Resolve column name with fuzzy matching. Returns the canonical name."""
        resolved = _fuzzy_resolve(column, list(df.columns), label="Column")
        if resolved != column:
            logger.info("Fuzzy-resolved column '%s' → '%s'", column, resolved)
        return resolved

