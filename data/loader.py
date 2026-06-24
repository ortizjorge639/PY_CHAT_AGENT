"""Data access layer — loads from Excel or SQL Server based on DATASOURCE flag."""

import logging
import time
from collections import OrderedDict
from datetime import datetime, timezone
from difflib import get_close_matches
from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import Settings

logger = logging.getLogger(__name__)

CHUNK_SIZE: int = 60
DATE_COLUMNS = {"DateAdded", "Processed_Date", "Effective Date"}
PART_NUMBER_COLUMN = "PartNumber"


def _bracket_table_name(raw: str) -> str:
    """Safely bracket a SQL table name, handling schema-qualified and pre-bracketed values."""
    raw = raw.strip()
    if raw.startswith("["):
        return raw
    parts = raw.split(".", 1)
    return ".".join(f"[{p}]" for p in parts)


def _normalize_table_name(raw: str) -> str:
    return raw.replace("[", "").replace("]", "").strip().lower()


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

    def __init__(self, settings: Settings, auto_load: bool = True) -> None:
        self._settings = settings
        self._tables: dict[str, pd.DataFrame] = {}
        self._table_roles: dict[str, str] = {}  # table_name → "primary" | "supplemental"
        self._cross_filter_cache: OrderedDict[tuple[Any, ...], frozenset[str]] = OrderedDict()
        self._cross_filter_cache_limit = 20
        self._is_loaded = False
        self._load_error: Exception | None = None
        self._last_loaded_at: datetime | None = None
        if auto_load:
            self.load_now()

    @property
    def is_loaded(self) -> bool:
        """Whether tables have been loaded successfully."""
        return self._is_loaded

    @property
    def load_error(self) -> Exception | None:
        """Most recent loading error, if any."""
        return self._load_error

    @property
    def last_loaded_at(self) -> datetime | None:
        """UTC timestamp of the most recent successful data load."""
        return self._last_loaded_at

    def load_now(self) -> None:
        """Load configured data source now. Safe to call multiple times."""
        if self._is_loaded:
            return
        try:
            self._load()
            self._is_loaded = True
            self._load_error = None
            self._last_loaded_at = datetime.now(timezone.utc)
        except Exception as exc:
            self._load_error = exc
            raise

    def reload(self) -> None:
        """Re-fetch data from the configured source, replacing in-memory tables.

        On success, queries immediately reflect the latest data.
        On failure, the previous data remains available and the error is logged.
        """
        logger.info("Data reload requested (last loaded: %s)", self._last_loaded_at)
        old_tables = self._tables
        old_roles = self._table_roles
        old_cache = self._cross_filter_cache
        self._tables = {}
        self._table_roles = {}
        self.clear_filter_cache()
        self._is_loaded = False
        try:
            self._load()
            self._is_loaded = True
            self._load_error = None
            self._last_loaded_at = datetime.now(timezone.utc)
            logger.info("Data reload complete — %d table(s) refreshed", len(self._tables))
        except Exception as exc:
            # Roll back to previous data so the app keeps working
            self._tables = old_tables
            self._table_roles = old_roles
            self._cross_filter_cache = old_cache
            self._is_loaded = True
            self._load_error = exc
            logger.error("Data reload failed, keeping previous data: %s", exc, exc_info=True)

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
                df = self._normalize_dataframe(df)
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

        tables_to_load = s.sql_table_list
        if not tables_to_load:
            conn.close()
            raise ValueError("No SQL tables configured. Set SQL_TABLE or SQL_TABLES.")

        primary = (s.sql_primary_table or tables_to_load[0]).strip()

        for table in tables_to_load:
            role = "primary" if table.strip() == primary else "supplemental"
            df = pd.read_sql(f"SELECT * FROM {_bracket_table_name(table)}", conn)
            df = self._align_sql_shape(table, df, conn)
            df = self._normalize_dataframe(df)
            # Coerce string columns that contain numeric values to numeric dtype
            for col in df.columns:
                if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
                    converted = pd.to_numeric(df[col], errors="coerce")
                    if converted.notna().sum() == df[col].notna().sum() and converted.notna().sum() > 0:
                        df[col] = converted
            self._tables[table] = df
            self._table_roles[table] = role
            logger.info(
                "Loaded SQL table '%s' [%s] (%d rows, %d cols)",
                table, role, len(df), len(df.columns),
            )

        conn.close()

    @staticmethod
    def _find_column_case_insensitive(columns: list[str], target: str) -> str | None:
        target_lower = target.lower()
        for column in columns:
            if str(column).strip().lower() == target_lower:
                return str(column)
        return None

    def _copy_column_if_missing(self, df: pd.DataFrame, source: str, target: str) -> None:
        if target in df.columns:
            return
        source_column = self._find_column_case_insensitive(list(df.columns), source)
        if source_column:
            df[target] = df[source_column]

    def _align_obsolescence_results(self, df: pd.DataFrame) -> pd.DataFrame:
        self._copy_column_if_missing(df, "p/c phase", "P/C Phase")
        self._copy_column_if_missing(df, "obsolete reserve", "Obsolete Reserve$")
        self._copy_column_if_missing(df, "reza's list", "Accounting List")
        self._copy_column_if_missing(df, "ModelProcessedDate", "Processed_Date")

        expected = [
            "PartNumber",
            "P/C Phase",
            "DateAdded",
            "QOH",
            "Obsolete Reserve$",
            "Nikhol's Comment",
            "Status",
            "Details",
            "RevisionLevel",
            "Accounting List",
            "Processed_Date",
        ]
        present_expected = [column for column in expected if column in df.columns]
        extras = [column for column in df.columns if column not in present_expected]
        return df[present_expected + extras]

    def _align_dim_products(self, df: pd.DataFrame, conn: Any) -> pd.DataFrame:
        if "International_PowerCord" not in df.columns and "Description" in df.columns:
            description = df["Description"].astype(str).str.upper()
            region_match = description.str.contains(
                r"AFRICA|AUSTRALIA|BRAZIL|CHINA|EURO|EUROPE|INDIA|ISRAEL|JAPAN|SWISS|UK|U\\.K\\.",
                regex=True,
                na=False,
            )
            cord_match = description.str.contains(
                r"PWR CORD|PWRCORD|AC CORD|AC POWER CORD|PWR,CORD",
                regex=True,
                na=False,
            )
            df["International_PowerCord"] = (region_match & cord_match).astype(int)

        if "CustomButton" not in df.columns:
            prefix_col = self._find_column_case_insensitive(list(df.columns), "PartNumberPrefix")
            model_col = self._find_column_case_insensitive(list(df.columns), "PartNumberModel")
            if prefix_col and model_col:
                allowed_models = {"152", "153", "154", "175", "176", "177", "181", "193", "194", "196", "197"}
                df["CustomButton"] = (
                    (df[prefix_col].astype(str) == "18")
                    & (df[model_col].astype(str).isin(allowed_models))
                ).astype(int)

        if "Effective Date" not in df.columns and "skDateEffectiveid" in df.columns:
            try:
                dim_date = pd.read_sql("SELECT skDateId, DateId FROM [common].[dimDate]", conn)
                dim_date = dim_date.rename(columns={"DateId": "Effective Date"})
                df = df.merge(dim_date, how="left", left_on="skDateEffectiveid", right_on="skDateId")
                if "skDateId" in df.columns:
                    df = df.drop(columns=["skDateId"])
            except Exception as exc:
                logger.warning("Could not derive Effective Date from common.dimDate: %s", exc)

        expected = [
            "skPartNumberId",
            "ProductId",
            "PartNumber",
            "PartNumberPrefix",
            "PartNumberModel",
            "PartNumberSuffix",
            "Description",
            "IsTopLevelPart",
            "IsConfiguredPart",
            "IsConfiguredPartComponent",
            "IsSerialized",
            "IsLinkLicense",
            "IsPhantomPart",
            "IsBinItem",
            "IsWebEnabled",
            "IsNonPhysical",
            "Effective Date",
            "International_PowerCord",
            "CustomButton",
        ]
        present_expected = [column for column in expected if column in df.columns]
        extras = [column for column in df.columns if column not in present_expected]
        return df[present_expected + extras]

    def _align_sql_shape(self, table_name: str, df: pd.DataFrame, conn: Any) -> pd.DataFrame:
        normalized = _normalize_table_name(table_name)
        if normalized.endswith("operations.obsolescence_results"):
            return self._align_obsolescence_results(df)
        if normalized.endswith("production.dimproducts"):
            return self._align_dim_products(df, conn)
        return df

    # ── public query API ─────────────────────────────────

    def list_tables(self) -> list[str]:
        """Return names of all loaded tables."""
        return list(self._tables.keys())

    def get_table_roles(self) -> dict[str, str]:
        """Return {table_name: role} for all tables."""
        return dict(self._table_roles)

    def get_tables_by_role(self, role: str) -> list[str]:
        return [table_name for table_name, table_role in self._table_roles.items() if table_role == role]

    def get_columns_by_role(self, role: str) -> list[str]:
        """Return unique column names for tables in a role, preserving first-seen order."""
        columns: list[str] = []
        seen: set[str] = set()
        for table_name in self.get_tables_by_role(role):
            table = self._tables.get(table_name)
            if table is None:
                continue
            for column in table.columns:
                if column in seen:
                    continue
                seen.add(str(column))
                columns.append(str(column))
        return columns

    def get_primary_table_name(self) -> str:
        primary_tables = self.get_tables_by_role("primary")
        if not primary_tables:
            raise ValueError("No primary table is loaded.")
        return primary_tables[0]

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

    def query_table_with_cross_filter(
        self,
        table_name: str,
        query_expr: str | None = None,
        supplemental_filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Filter a primary table by part numbers matched from supplemental-table filters."""
        if not supplemental_filters:
            if query_expr:
                return self.query_table(table_name, query_expr)
            return self.get_rows(table_name)

        df = self._get_table(table_name)
        result = df
        if query_expr:
            try:
                result = result.query(query_expr)
            except Exception as exc:
                raise ValueError(f"Invalid query expression: {exc}") from exc

        matching_parts = self._get_matching_parts_for_supplemental_filters(supplemental_filters)
        if PART_NUMBER_COLUMN not in result.columns:
            filtered = result.iloc[0:0]
        else:
            normalized_parts = result[PART_NUMBER_COLUMN].astype(str).str.strip().str.upper()
            filtered = result[normalized_parts.isin(matching_parts)]

        return {
            "table": table_name,
            "rows": filtered.to_dict(orient="records"),
            "total": len(filtered),
            "columns": list(filtered.columns),
        }

    def get_cross_filtered_frame(
        self,
        table_name: str,
        query_expr: str | None = None,
        supplemental_filters: dict[str, str] | None = None,
        include_all_supplemental: bool = False,
    ) -> pd.DataFrame:
        """Return a primary DataFrame merged with matching supplemental rows."""
        primary_df = self._get_table(table_name).copy()
        if query_expr:
            try:
                primary_df = primary_df.query(query_expr)
            except Exception as exc:
                raise ValueError(f"Invalid query expression: {exc}") from exc

        if not supplemental_filters and not include_all_supplemental:
            return primary_df

        supplemental_frames: list[pd.DataFrame] = []
        for supplemental_table in self.get_tables_by_role("supplemental"):
            supplemental_df = self._get_table(supplemental_table).copy()
            if PART_NUMBER_COLUMN not in supplemental_df.columns:
                continue
            filtered = supplemental_df
            if supplemental_filters:
                for column, value in supplemental_filters.items():
                    filtered = self._apply_filter(filtered, column, value)
                    if filtered.empty:
                        break
            if not filtered.empty:
                supplemental_frames.append(filtered)

        if not supplemental_frames:
            return primary_df.iloc[0:0].copy()

        combined_supplemental = pd.concat(supplemental_frames, ignore_index=True)
        combined_supplemental = combined_supplemental.drop_duplicates(subset=[PART_NUMBER_COLUMN], keep="first")
        return primary_df.merge(
            combined_supplemental,
            on=PART_NUMBER_COLUMN,
            how="inner",
            suffixes=("", "_supplemental"),
        )

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
            result = df.groupby(group_column).size().rename("count").reset_index()

        return result.to_dict(orient="records")

    # ── helpers ──────────────────────────────────────────

    def clear_filter_cache(self) -> None:
        self._cross_filter_cache.clear()

    def get_filter_cache_size(self) -> int:
        return len(self._cross_filter_cache)

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

    @staticmethod
    def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        normalized = df.copy()
        normalized.columns = [str(c).strip() for c in normalized.columns]
        for column in DATE_COLUMNS.intersection(normalized.columns):
            normalized[column] = pd.to_datetime(normalized[column], errors="coerce", utc=True)
        return normalized

    def _get_matching_parts_for_supplemental_filters(
        self,
        supplemental_filters: dict[str, str],
    ) -> frozenset[str]:
        cache_key = self._build_cross_filter_cache_key(supplemental_filters)
        cached = self._cross_filter_cache.get(cache_key)
        if cached is not None:
            self._cross_filter_cache.move_to_end(cache_key)
            return cached

        matching_parts: set[str] = set()
        supplemental_tables = [
            table_name
            for table_name, role in self._table_roles.items()
            if role == "supplemental"
        ]
        for supplemental_table in supplemental_tables:
            supplemental_df = self._get_table(supplemental_table)
            if PART_NUMBER_COLUMN not in supplemental_df.columns:
                continue
            filtered = supplemental_df
            for column, value in supplemental_filters.items():
                filtered = self._apply_filter(filtered, column, value)
                if filtered.empty:
                    break
            if filtered.empty:
                continue
            matching_parts.update(
                filtered[PART_NUMBER_COLUMN].dropna().astype(str).str.strip().str.upper().tolist()
            )

        frozen_parts = frozenset(matching_parts)
        self._cross_filter_cache[cache_key] = frozen_parts
        self._cross_filter_cache.move_to_end(cache_key)
        while len(self._cross_filter_cache) > self._cross_filter_cache_limit:
            self._cross_filter_cache.popitem(last=False)
        return frozen_parts

    def _build_cross_filter_cache_key(self, supplemental_filters: dict[str, str]) -> tuple[Any, ...]:
        normalized_filters = tuple(
            sorted((str(key).strip().lower(), str(value).strip().lower()) for key, value in supplemental_filters.items())
        )
        supplemental_tables = tuple(sorted(
            table_name for table_name, role in self._table_roles.items() if role == "supplemental"
        ))
        return supplemental_tables + normalized_filters


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

