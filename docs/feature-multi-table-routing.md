# Feature: Multi-Table Routing for `dimProducts`

Two tables share `PartNumber` but are never joined. The agent routes each question to the
correct table based on intent:

| User intent | Table |
|---|---|
| Scrap eligibility / Status / Disposition | Primary (obsolescence) |
| Description, Phase, product flags | `production.dimProducts` (supplemental) |

---

## What Already Works (no changes needed)

| File | Existing capability |
|---|---|
| `config/settings.py` | `sql_table_list` property already parses `SQL_TABLES` (comma-separated) falling back to `SQL_TABLE` |
| `data/loader.py` | `lookup_part()` already cross-searches all loaded tables with a `PartNumber` column |
| `agent/plugins/data_plugin.py` | All tools already accept `table_name` — the LLM can target either table once both are loaded |
| `agent/kernel.py` | `{table_roles}` placeholder already injects loaded table names and roles into the system prompt |

---

## Environment Variables

Add to `.env` / Azure App Service Application Settings:

```env
SQL_TABLES=production.<ObsolescenceTable>,production.dimProducts
SQL_PRIMARY_TABLE=production.<ObsolescenceTable>
```

`SQL_TABLE` (single-value, existing) remains for backward compatibility.

---

## File Changes

### 1. `config/settings.py`

Add one field and update `sql_table_list`:

```python
sql_supplemental_table: str = ""   # e.g. "production.dimProducts"

@property
def sql_table_list(self) -> list[str]:
    raw = self.sql_tables or self.sql_table
    tables = [t.strip() for t in raw.split(",") if t.strip()]
    if self.sql_supplemental_table and self.sql_supplemental_table not in tables:
        tables.append(self.sql_supplemental_table)
    return tables
```

---

### 2. `data/loader.py`

Replace the single-table block in `_load_sql()` with a loop. Keep all connection setup
and numeric-coercion logic unchanged; only the loading block changes:

```python
tables_to_load = s.sql_table_list
if not tables_to_load:
    conn.close()
    raise ValueError("No SQL tables configured. Set SQL_TABLE or SQL_TABLES.")

primary = (s.sql_primary_table or tables_to_load[0]).strip()

for table in tables_to_load:
    role = "primary" if table.strip() == primary else "supplemental"
    df = pd.read_sql(f"SELECT * FROM {_bracket_table_name(table)}", conn)
    df.columns = [str(c).strip() for c in df.columns]
    # keep existing numeric-coercion loop here
    self._tables[table] = df
    self._table_roles[table] = role
    logger.info("Loaded SQL table '%s' [%s] (%d rows, %d cols)", table, role, len(df), len(df.columns))

conn.close()
```

---

### 3. `agent/plugins/data_plugin.py`

Add `lookup_part_details` inside `create_data_tools()` and append it to the returned list.
This tool insulates the LLM from having to know the exact supplemental table name.

```python
def lookup_part_details(
    part_number: Annotated[str, Field(description="Part number to look up in the product catalogue")],
) -> str:
    result = loader.lookup_part(part_number)
    supplemental_rows: list[dict] = []
    supplemental_cols: list[str] = []
    for tname, rows in result.get("tables", {}).items():
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

Return list addition:
```python
return [...existing tools..., lookup_part_details]
```

---

### 4. `agent/kernel.py` — `SYSTEM_PROMPT_TEMPLATE`

Replace the `DOMAIN KNOWLEDGE` section and the single `Allowed columns` block with the
following. All other sections remain unchanged.

```
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

Tables are NEVER joined. Query each independently.

----------------------------------------------------------------
TABLE ROUTING RULES (STRICT)
----------------------------------------------------------------
Scrap eligibility / Status / Disposition  → PRIMARY table
Description / Phase / product flags       → call lookup_part_details(part_number=…)
Unspecified part question                 → check PRIMARY first; use supplemental on follow-up
Do NOT mix columns from different tables in one response.
```

---

### 5. Test Database Table — `production.dimProducts`

> **This table must be created in the SQL Server instance used for local and CI testing.**
> Do NOT use an xlsx file for this table. The DDL below is the authoritative test fixture.

```sql
-- Run against the same database as the primary table (e.g. EXTRON_EDWPROD)
CREATE TABLE [production].[dimProducts] (
    [skPartNumberId]              INT            IDENTITY(1,1) NOT NULL,
    [ProductId]                   VARCHAR(50)    NOT NULL,
    [PartNumber]                  VARCHAR(50)    NOT NULL,
    [PartNumberPrefix]            VARCHAR(10)    NULL,
    [PartNumberModel]             VARCHAR(20)    NULL,
    [PartNumberSuffix]            VARCHAR(20)    NULL,
    [Description]                 VARCHAR(255)   NULL,
    [IsTopLevelPart]              BIT            NULL,
    [IsConfiguredPart]            BIT            NULL,
    [IsConfiguredPartComponent]   BIT            NULL,
    [IsSerialized]                BIT            NULL,
    [IsLinkLicense]               BIT            NULL,
    [IsPhantomPart]               BIT            NULL,
    [IsBinItem]                   BIT            NULL,
    [Phase]                       VARCHAR(50)    NULL,
    [IsWebEnabled]                BIT            NULL,
    [IsNonPhysical]               BIT            NULL,
    [skDateEffectiveid]           INT            NULL,
    [skDateAddedid]               INT            NULL,
    -- Computed columns (persisted so they are queryable via SELECT *)
    [International_PowerCord] AS (
        CASE
            WHEN (
                [Description] LIKE '%AFRICA%'   OR [Description] LIKE '%AUSTRALIA%' OR
                [Description] LIKE '%BRAZIL%'   OR [Description] LIKE '%CHINA%'     OR
                [Description] LIKE '%EURO%'     OR [Description] LIKE '%EUROPE%'    OR
                [Description] LIKE '%India%'    OR [Description] LIKE '%Israel%'    OR
                [Description] LIKE '%JAPAN%'    OR [Description] LIKE '%SWISS%'     OR
                [Description] LIKE '%UK%'       OR [Description] LIKE '%U.K.%'
            ) AND (
                [Description] LIKE '%PWR CORD%' OR [Description] LIKE '%PWRCORD%'  OR
                [Description] LIKE '%AC CORD%'  OR [Description] LIKE '%AC POWER CORD%' OR
                [Description] LIKE '%PWR,CORD%'
            )
            THEN 1 ELSE 0
        END
    ) PERSISTED,
    [CustomButton] AS (
        CASE
            WHEN [PartNumberPrefix] = '18'
             AND [PartNumberModel] IN ('152','153','154','175','176','177','181','193','194','196','197')
            THEN 1 ELSE 0
        END
    ) PERSISTED
);
```

**Seed data requirements for tests** (insert after CREATE TABLE):

| # | PartNumber | Description | PartNumberPrefix | PartNumberModel | Expected flags |
|---|---|---|---|---|---|
| 1 | Matches a PartNumber in the primary table | `PWR CORD EURO` | any | any | `International_PowerCord=1` |
| 2 | Matches a PartNumber in the primary table | `PWR CORD JAPAN` | any | any | `International_PowerCord=1` |
| 3 | Matches a PartNumber in the primary table | `WIDGET A` | `18` | `152` | `CustomButton=1` |
| 4 | Matches a PartNumber in the primary table | `WIDGET B` | `18` | `175` | `CustomButton=1` |
| 5–10 | Any, including at least 2 NOT in primary table | Standard descriptions | various | various | both flags `0` |

The `PartNumber` values for rows 1–4 **must** exist in `data/mock/test_200rows.xlsx` so
cross-table lookup tests can verify hits in both tables simultaneously.

---

### 6. Tests

Add to `main_test.py` or `tests/`:

```python
def test_multi_table_load():
    # Both tables are loaded; dimProducts role is "supplemental"
    tables = loader.list_tables()
    assert any("dimProducts" in t for t in tables)
    assert loader.get_table_roles().get("production.dimProducts") == "supplemental"

def test_lookup_part_cross_table():
    # PartNumber present in both tables returns two table entries
    result = loader.lookup_part("<part_in_both>")
    assert len(result["tables"]) == 2

def test_lookup_part_details_returns_supplemental_row():
    # Tool returns rows_retrieved > 0 and data lands in data_buffer
    ...

def test_primary_table_unaffected():
    # get_rows on primary table still returns Status column
    result = loader.get_rows("<primary_table>", "PartNumber", "<known_part>")
    assert result["total"] == 1
    assert "Status" in result["columns"]

def test_international_powercord_flag():
    result = loader.get_rows("production.dimProducts", "International_PowerCord", "1")
    assert result["total"] >= 2

def test_custom_button_flag():
    result = loader.get_rows("production.dimProducts", "CustomButton", "1")
    assert result["total"] >= 2

def test_backward_compat_single_table():
    # SQL_TABLES unset, SQL_TABLE set → only primary table loaded
    ...
```

---

## Edge Cases

| Scenario | Behaviour |
|---|---|
| PartNumber in primary only | `lookup_part_details` → `{"error": "…not found in product catalogue."}` |
| PartNumber in `dimProducts` only | `get_rows` on primary → `"No rows matched."` |
| `dimProducts` fails to load | `DataLoader.reload()` rolls back; `{table_roles}` reflects only primary; agent answers accordingly |
| `SQL_TABLES` unset, `SQL_TABLE` set | `sql_table_list` returns `[sql_table]`; single-table behaviour unchanged |

---

## Acceptance Criteria

- [ ] `_load_sql()` iterates `sql_table_list` and assigns `primary`/`supplemental` roles.
- [ ] `lookup_part_details` tool exists in `create_data_tools()` and returns supplemental rows.
- [ ] System prompt routes scrap questions to primary, detail questions to supplemental.
- [ ] `production.dimProducts` table created in test SQL Server with DDL above and seed rows.
- [ ] All existing tests pass.
- [ ] New tests (6 above) pass.
- [ ] `SQL_TABLE`-only config produces identical behaviour to current code.
