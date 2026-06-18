# Feature: Multi-Table Routing for `dimProducts` (Supplemental Table)

## Overview

The agent currently answers questions about a single **primary** table that tracks part
scrap-eligibility (PartNumber, Status, Details, Processed_Date, QOH, …).  The customer has
a second SQL table — `production.dimProducts` — that contains richer product-catalogue
information for the same parts (Description, Phase, CustomButton, International_PowerCord, …).

The two tables share a common `PartNumber` key.  They are **never joined**.  Instead, the
agent must route each user question to the correct table based on what the user is asking:

| User intent | Table |
|---|---|
| "Can part X be scrapped?" / "What is the status of X?" | Primary (obsolescence) table |
| "What is the description of part X?" / "Is X a custom button?" / "What phase is X in?" | `production.dimProducts` |

This document is a complete, file-by-file implementation plan for a future coding agent.

---

## Background — What Already Exists

| File | Relevant existing capability |
|---|---|
| `config/settings.py` | `sql_table` (single table), `sql_tables` (comma-separated), `sql_table_list` property (parses `sql_tables` or falls back to `sql_table`) |
| `data/loader.py` | `DataLoader._load_sql()` currently loads **only `sql_table`**; `_load_excel()` already loads all `.xlsx` files into separate tables; `lookup_part()` already searches all loaded tables with a `PartNumber` column |
| `agent/plugins/data_plugin.py` | `get_rows`, `query_table`, `list_tables`, `get_schema` already accept a `table_name` parameter — the LLM can already target either table once both are loaded |
| `agent/kernel.py` | System prompt uses `{table_roles}` placeholder (built from `DataLoader.get_table_roles()`) to describe available tables |

The minimal change required is therefore:
1. Teach `_load_sql()` to load **all** tables in `sql_table_list`.
2. Update the system prompt to route question types to the correct table.
3. Add a new `lookup_part_details` tool that retrieves `dimProducts` columns for a part number, so the LLM does not need to remember the exact SQL table name.
4. Cover both tables in existing tests and add new test cases.

---

## Environment Configuration

Add the following variables to the `.env` file (or Azure App Service Application Settings):

```env
# Existing (keep for backward-compat)
SQL_TABLE=production.SomeObsolescenceTable

# New — supplemental table
SQL_TABLES=production.SomeObsolescenceTable,production.dimProducts

# Which table is the "primary" one (scrap eligibility)
SQL_PRIMARY_TABLE=production.SomeObsolescenceTable
```

`SQL_TABLES` supersedes `SQL_TABLE`; `SQL_TABLE` is kept for backward compatibility when only
one table is needed.

---

## File-by-File Changes

---

### 1. `config/settings.py`

**Goal:** Add a clear `sql_supplemental_table` field so operators can name the dimProducts
table explicitly without relying on ordering inside `SQL_TABLES`.

```python
# config/settings.py  (additions only — do not remove existing fields)

sql_supplemental_table: str = ""   # e.g. "production.dimProducts"
```

The `sql_table_list` property already combines `sql_tables` / `sql_table`.  No changes
needed there, but when `sql_supplemental_table` is set it **must** be included in the list:

```python
@property
def sql_table_list(self) -> list[str]:
    raw = self.sql_tables or self.sql_table
    tables = [t.strip() for t in raw.split(",") if t.strip()]
    # Append supplemental table if not already present
    if self.sql_supplemental_table and self.sql_supplemental_table not in tables:
        tables.append(self.sql_supplemental_table)
    return tables
```

---

### 2. `data/loader.py`

**Goal:** `_load_sql()` must iterate over `sql_table_list` and load every table, assigning
roles based on `sql_primary_table`.

#### Current code (simplified)
```python
def _load_sql(self) -> None:
    ...
    table = s.sql_table.strip()
    df = pd.read_sql(f"SELECT * FROM {_bracket_table_name(table)}", conn)
    ...
    self._tables[table] = df
    self._table_roles[table] = "primary"
    conn.close()
```

#### Replacement
```python
def _load_sql(self) -> None:
    # (keep connection setup unchanged — only the table-loading loop changes)
    ...
    tables_to_load = s.sql_table_list
    if not tables_to_load:
        conn.close()
        raise ValueError("No SQL tables configured. Set SQL_TABLE or SQL_TABLES.")

    primary = (s.sql_primary_table or tables_to_load[0]).strip()

    for table in tables_to_load:
        table = table.strip()
        role = "primary" if table == primary else "supplemental"
        df = pd.read_sql(f"SELECT * FROM {_bracket_table_name(table)}", conn)
        df.columns = [str(c).strip() for c in df.columns]
        # Coerce numeric columns (keep existing logic)
        for col in df.columns:
            if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
                converted = pd.to_numeric(df[col], errors="coerce")
                if (converted.notna().sum() == df[col].notna().sum()
                        and converted.notna().sum() > 0):
                    df[col] = converted
        self._tables[table] = df
        self._table_roles[table] = role
        logger.info(
            "Loaded SQL table '%s' [%s] (%d rows, %d cols)",
            table, role, len(df), len(df.columns),
        )

    conn.close()
```

**Important notes:**
- The table key in `self._tables` is the full qualified name (e.g. `production.dimProducts`).
  `_fuzzy_resolve` handles case-insensitive lookups so the LLM does not need exact casing.
- The existing `lookup_part()` method already iterates all loaded tables — it will
  automatically search `dimProducts` once it is loaded.  No changes needed there.

---

### 3. `agent/plugins/data_plugin.py`

**Goal:** Add a dedicated `lookup_part_details` tool so the LLM has a single, named action
for "look up dimProducts for a part number" without having to remember the exact table name.

Add this function inside `create_data_tools()`, alongside the existing tools:

```python
def lookup_part_details(
    part_number: Annotated[str, Field(description="Part number to look up in the product catalogue")],
) -> str:
    """
    Retrieve product-catalogue details for a part number from the supplemental
    dimProducts table.  Returns description, phase, flags (CustomButton,
    International_PowerCord, IsTopLevelPart, etc.).

    Tool NEVER decides how results are presented.
    """
    result = loader.lookup_part(part_number)
    tables = result.get("tables", {})

    # Find the supplemental table entry
    supplemental_rows: list[dict] = []
    supplemental_cols: list[str] = []
    for tname, rows in tables.items():
        if loader.get_table_roles().get(tname) == "supplemental":
            supplemental_rows = rows
            supplemental_cols = result["columns_by_table"].get(tname, [])
            break

    if not supplemental_rows:
        return json.dumps({"error": f"Part number '{part_number}' not found in product catalogue."})

    _store_last_result(last_result, "dimProducts", supplemental_rows, supplemental_cols)
    data_buffer.extend(_rows_to_chunks(supplemental_rows, supplemental_cols))

    return json.dumps({"rows_retrieved": len(supplemental_rows)})
```

Add `lookup_part_details` to the returned list:

```python
return [
    list_tables,
    get_schema,
    count_rows,
    get_rows,
    get_distinct_values,
    query_table,
    group_by,
    export_to_excel,
    lookup_part_details,          # ← new
]
```

---

### 4. `agent/kernel.py`

**Goal:** Update the system prompt so the LLM understands which table to use for each
question type and learns the key columns of `dimProducts`.

#### Changes to `SYSTEM_PROMPT_TEMPLATE`

Replace (or extend) the existing `DOMAIN KNOWLEDGE` and `SPECIAL QUERY RULES` sections:

```
----------------------------------------------------------------
DOMAIN KNOWLEDGE
----------------------------------------------------------------
There are two data sources.

PRIMARY TABLE (scrap-eligibility / obsolescence):
  - PartNumber   — unique part identifier
  - Status       — authoritative scrap-eligibility disposition
  - Details      — additional context for the Status
  - Processed_Date, QOH, "Reza's List", …

SUPPLEMENTAL TABLE — production.dimProducts (product catalogue):
  - PartNumber          — same identifier, links to the primary table
  - Description         — human-readable product description
  - Phase               — lifecycle phase (e.g. Active, Obsolete)
  - IsTopLevelPart      — 1/0 flag
  - IsConfiguredPart    — 1/0 flag
  - IsSerialized        — 1/0 flag
  - IsPhantomPart       — 1/0 flag
  - IsBinItem           — 1/0 flag
  - IsWebEnabled        — 1/0 flag
  - IsNonPhysical       — 1/0 flag
  - International_PowerCord — computed flag (1 if part is an international power cord)
  - CustomButton        — computed flag (1 if part is a custom button)
  - Effective Date, DateAdded, PartNumberPrefix, PartNumberModel, PartNumberSuffix, …

The tables are NEVER joined. Query each independently.

----------------------------------------------------------------
TABLE ROUTING RULES (STRICT)
----------------------------------------------------------------
When a user asks about SCRAP ELIGIBILITY, STATUS, or DISPOSITION:
  → Use the PRIMARY table.

When a user asks about DESCRIPTION, PHASE, PRODUCT FLAGS (CustomButton,
International_PowerCord, IsTopLevelPart, IsSerialized, etc.):
  → Use the SUPPLEMENTAL table (production.dimProducts) or call
    lookup_part_details(part_number=…).

When a user asks about a part number WITHOUT specifying what they
want to know, check the primary table FIRST. If the user then asks
follow-up questions about product details, use the supplemental table.

Do NOT mix columns from different tables in a single response.
```

#### Update `Allowed columns`

```
Allowed columns (primary table):
- PartNumber
- Status
- Details
- Processed_Date
- QOH
- Reza's List

Allowed columns (supplemental — dimProducts):
- PartNumber
- Description
- Phase
- IsTopLevelPart
- IsConfiguredPart
- IsConfiguredPartComponent
- IsSerialized
- IsLinkLicense
- IsPhantomPart
- IsBinItem
- IsWebEnabled
- IsNonPhysical
- International_PowerCord
- CustomButton
- Effective Date
- DateAdded
- PartNumberPrefix
- PartNumberModel
- PartNumberSuffix
```

---

### 5. `data/mock/` — Test Fixture

**Goal:** Create a second mock Excel file so automated tests can exercise the dimProducts
table locally without a SQL Server connection.

Create: `data/mock/dimProducts.xlsx`

The file must contain at minimum the following columns (matching the `production.dimProducts`
schema from the SQL in the problem statement):

```
PartNumber, Description, Phase, IsTopLevelPart, IsConfiguredPart,
IsConfiguredPartComponent, IsSerialized, IsLinkLicense, IsPhantomPart,
IsBinItem, IsWebEnabled, IsNonPhysical, International_PowerCord,
CustomButton, Effective Date, DateAdded, PartNumberPrefix,
PartNumberModel, PartNumberSuffix
```

Populate it with at least 10 representative rows that include:
- At least 2 `International_PowerCord = 1` rows (description contains "AFRICA" or "EURO" AND
  "PWR CORD")
- At least 2 `CustomButton = 1` rows (PartNumberPrefix = '18', PartNumberModel in the
  allowed list)
- Rows whose `PartNumber` values overlap with parts in the primary mock table
  (`data/mock/test_200rows.xlsx`) so cross-table lookup tests can be written

Use `scripts/populate_mock_data.py` as a model for how to generate the file programmatically.

---

### 6. Tests

#### `main_test.py` or `tests/` — integration smoke tests

Add/extend test cases to cover:

```python
# Verify both tables are loaded
def test_multi_table_load():
    loader = DataLoader(settings_with_both_tables)
    tables = loader.list_tables()
    assert any("dimProducts" in t for t in tables)
    roles = loader.get_table_roles()
    assert "supplemental" in roles.values()

# Verify lookup_part returns rows from both tables when PartNumber exists in both
def test_lookup_part_cross_table():
    loader = ...  # loaded with both mock files
    result = loader.lookup_part("60-100-01")  # a PartNumber present in both
    assert len(result["tables"]) == 2

# Verify lookup_part_details tool returns dimProducts data
def test_lookup_part_details_tool():
    ...  # call the tool, assert rows_retrieved > 0 and supplemental role

# Verify primary table query still works unchanged
def test_primary_table_unaffected():
    ...  # get_rows on primary table returns Status column

# Verify International_PowerCord flag is correctly computed in mock data
def test_international_powercord_flag():
    loader = ...
    result = loader.get_rows("dimProducts", "International_PowerCord", "1")
    assert result["total"] > 0

# Verify CustomButton flag
def test_custom_button_flag():
    loader = ...
    result = loader.get_rows("dimProducts", "CustomButton", "1")
    assert result["total"] > 0
```

Run tests with:
```bash
npm test          # existing harness
python -m pytest  # if pytest is configured
```

---

## Data Flow for a Two-Step User Query

Below is the expected tool-call sequence when a user asks a two-part question:

```
User: "Can part 60-100-01 be scrapped?"

  Agent → get_rows(table_name=<primary>, filter_column="PartNumber", filter_value="60-100-01")
  Tool  → rows_retrieved: 1
  Agent → "Part 60-100-01 may be eligible to be scrapped."

User: "What is the description of that part?"

  Agent → lookup_part_details(part_number="60-100-01")
  Tool  → rows_retrieved: 1  (data chunk sent to UI with Description column)
  Agent → "The description for part 60-100-01 is: <value from Description column>."
```

The two calls are independent. The agent never joins the two result sets or invents values
from one table while showing values from the other.

---

## Edge Cases to Handle

| Scenario | Expected behaviour |
|---|---|
| PartNumber exists in primary table but not in `dimProducts` | `lookup_part_details` returns `{"error": "Part number '…' not found in product catalogue."}` — agent replies that no catalogue entry exists |
| PartNumber exists only in `dimProducts` | `get_rows` on primary table returns "No rows matched." — agent says it has no scrap-eligibility data for that part |
| `dimProducts` table fails to load at startup | `DataLoader.reload()` rolls back to the previous state; only the primary table is available; the system prompt `{table_roles}` will reflect this and the agent will answer accordingly |
| User asks about a `dimProducts` column that doesn't exist in the primary table | `get_schema` will show the column is absent from the primary table — agent must look in the supplemental table instead |
| `SQL_TABLES` not configured but `SQL_TABLE` is set | `sql_table_list` falls back to `[sql_table]` — single-table behaviour is unchanged |

---

## Acceptance Criteria

A future coding agent can mark this feature complete when:

- [ ] `DataLoader._load_sql()` loads all tables in `sql_table_list` and assigns roles correctly.
- [ ] `lookup_part_details` tool is present in `create_data_tools()` and returns supplemental rows.
- [ ] System prompt routes scrap questions to the primary table and product-detail questions to `dimProducts`.
- [ ] `data/mock/dimProducts.xlsx` exists with representative rows (including flagged parts).
- [ ] All existing tests still pass.
- [ ] New tests cover: multi-table load, cross-table `lookup_part`, `International_PowerCord` flag, `CustomButton` flag.
- [ ] `SQL_TABLES=` set to a single table still produces identical behaviour to the current `SQL_TABLE=` approach (backward compatibility).
