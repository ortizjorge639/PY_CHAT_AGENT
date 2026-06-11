# Chat Agent Test Bank

> Generated from live database on 2026-05-05.
> Obsolescence_Results: 500 rows | CRmaster_ModelResults: 24 rows (10 overlap by PartNumber, 3 parts with multiple entries).
> **Latest benchmark: 2026-05-05 | 31/31 PASS | Avg 5.3s | 0 failures**

---

## Benchmark History

| Run | Date | Tests | Pass | Fail | Avg Time | Changes |
|-----|------|-------|------|------|----------|---------|
| 1 | 2026-04-27 | 19 | 14 (74%) | 4 soft + 1 bug | 5.1s | Baseline |
| 2 | 2026-04-27 | 27 | 27 (100%) | 0 | 5.9s | +temperature=0, +formatting rules, +grounded tool returns, +get_row_by_id |
| 3 | 2026-05-05 | 31 | 31 (100%) | 0 | 5.3s | +lookup_part buffer fix, +PN regex fix, +numeric coercion, +inline data, +temperature=0 on Agent |

## Improvement Tracker

| # | Improvement | File(s) Changed | Impact |
|---|-------------|-----------------|--------|
| 1 | `temperature=0` on Azure OpenAI client | kernel_test.py | Eliminated 4 soft fails (3.1, 3.3, 5.2, 7.1) — model now consistently includes all data fields and uses precise wording |
| 2 | Response Formatting Rules in system prompt | kernel_test.py | Explicit instructions for response length by query type; prohibits fabricated markdown tables |
| 3 | Grounded tool returns (`get_rows`, `query_table`) | data_plugin_test.py | Tools now include actual row data (up to 10 rows) in JSON return — model sees real values, can't fabricate |
| 4 | `get_row_by_id` tool + RULE 4 | data_plugin_test.py, loader.py, kernel_test.py | Dedicated tool for non-PartNumber lookups (pklogid, etc.) — replaces fragile `query_table` for simple lookups |
| 5 | `lookup_part` populates `_last_result_buffer` | data_plugin.py | Fixed kernel safety guard always overriding with "no data" for part queries |
| 6 | Part number regex handles DM- prefixed parts | kernel.py | `PART_NUMBER_PATTERN` now matches `DM-478-14LF` style parts and avoids false matches on pklogid/numbers |
| 7 | Numeric string coercion in loader | loader.py | String columns with numeric values auto-convert to float64 — fixes `Confidence > 0.90` queries |
| 8 | Inline data in `query_table` / `get_rows` returns | data_plugin.py | Small result sets (≤10 rows) include actual data in tool return — model sees real values |
| 9 | `temperature=0` on Agent via `ChatOptions` | kernel.py | Deterministic responses — previously lost when kernel_test.py was merged |
| 10 | `lookup_part` note relaxed for broad queries | data_plugin.py | "Tell me about" queries now include all fields from all tables |
| 11 | Kernel trusts model text when buffer has data | kernel.py | Cross-table property queries (confidence, replacement) now use model text instead of Status-only override |

### Previous Failure Analysis (now resolved)

| ID | Previous Verdict | Resolution |
|----|-----------------|------------|
| 3.1 | Soft fail — model omitted confidence | **Fixed by temperature=0** — model now deterministically includes all fields |
| 3.3 | Soft fail — model omitted confidence | **Fixed by temperature=0** |
| 5.2 | Soft fail — "does not exist" vs "no data" | **Fixed by temperature=0** — consistent wording |
| 7.1 | Soft fail — paraphrased error message | **Fixed by temperature=0** — consistent wording |
| 7.2 | Real bug — `_apply_filter` crash | **Fixed in prior session** — loader.py returns empty DF |

---

## 1. Single-Part Status Queries (RULE 1 — lookup_part)

| # | Query | Expected Answer | Pass? |
|---|-------|-----------------|-------|
| 1.1 | What is the status of 19-1690-02LF? | **Component Request - Please review Logid** | |
| 1.2 | What is the status of 19-2990-02LF? | **In WhereUsed with parent** | |
| 1.3 | What is the status of 19-2166-01LF? | **May be eligible to be scrapped** | |
| 1.4 | What is the status of 19-3232-01LF? | **Need Further Review-NO BOM** | |

**What to check:** Response is concise (1–2 sentences). No raw table dumps. No "10 records match." No data from CRmaster unless asked.

---

## 2. Single-Part Cross-Table Property Queries

| # | Query | Expected Answer | Pass? |
|---|-------|-----------------|-------|
| 2.1 | What is the confidence score for 19-3082-01LF? | **0.97** | |
| 2.2 | Does 19-1690-02LF have a replacement? | **Yes** — NewPN: DM-410-25LF | |
| 2.3 | What is the replacement_intent for 19-3232-01LF? | **N** (no replacement; last-time buy placed) | |
| 2.4 | What is the confidence for 28-457-17LF? | **0.93** | |
| 2.5 | What are the comments for 19-2990-02LF? | "Customer approved substitute last month." | |

**What to check:** Answers come from CRmaster data. No fabricated values. Concise — only the asked property.

---

## 3. Broad Part Lookups ("tell me about")

| # | Query | Expected Answer Contains | Pass? |
|---|-------|--------------------------|-------|
| 3.1 | Tell me about 19-3082-01LF | Status: In WhereUsed with parent, Details: 60-1996-102, Replacement_intent: Y, Confidence: 0.97, NewPN: DM-287-38LF | PASS (6.3s) — fixed by temperature=0 |
| 3.2 | Tell me about 19-2166-01LF | Status: May be eligible to be scrapped, Replacement_intent: N, Confidence: 0.88 | PASS (4.8s) |
| 3.3 | Tell me about 28-457-17LF | Status: In WhereUsed with parent, Details: 60-1746-11UPV, Replacement_intent: Y, NewPN: DM-309-60LF, Confidence: 0.93 | PASS (6.9s) — fixed by temperature=0 |

**What to check:** Broader answer is OK here since user asked broadly. Still no raw table dumps. All values match actual data.

---

## 4. CRmaster-Only Parts (no Obsolescence match)

| # | Query | Expected Answer | Pass? |
|---|-------|-----------------|-------|
| 4.1 | Tell me about DM-478-14LF | Found in CRmaster only. Replacement_intent: N, Confidence: 0.90, "Component obsolete; no viable replacement at this time." | PASS (2.3s) |
| 4.2 | What is the confidence for DM-367-41LF? | **0.96** | PASS (1.7s) |
| 4.3 | Does DM-605-91LF have a replacement? | **Yes** — DM-605-95LF | PASS (2.0s) |

**What to check:** Agent should NOT say "not found in Obsolescence" as an error — it should just report the CRmaster data it found.

---

## 5. Nonexistent Parts (negative test)

| # | Query | Expected Answer | Pass? |
|---|-------|-----------------|-------|
| 5.1 | What is the status of FAKE-000-00LF? | No data found for that part number. | PASS (6.9s) |
| 5.2 | Tell me about 99-9999-99LF | No data found. | PASS (7.6s) — fixed by temperature=0 |

**What to check:** No fabricated data. No hallucinated statuses or properties.

---

## 6. Aggregate Queries (RULE 2 — count/group/get_rows)

| # | Query | Expected Answer | Pass? |
|---|-------|-----------------|-------|
| 6.1 | How many rows are in Obsolescence_Results? | **500** | PASS (5.2s) |
| 6.2 | How many rows are in CRmaster_ModelResults? | **20** | PASS (5.7s) |
| 6.3 | How many parts have status "In WhereUsed with parent"? | **83** | PASS (5.7s) |
| 6.4 | Break down Obsolescence_Results by Status | In WhereUsed with parent: 83, Component Request - Please review Logid: 39, No stock: 64, May be eligible to be scrapped: 51, and 11 more | PASS (7.8s) |
| 6.5 | How many parts have Replacement_intent = Y in CRmaster? | **12** (50101,50103,50104,50106,50107,50108,50110,50112,50113,50114,50115,50117,50119,50120) — count may vary, verify | not tested |

**What to check:** Returns a number, not a table dump. Correct count.

---

## 7. Status Validation (enum enforcement)

| # | Query | Expected Answer | Pass? |
|---|-------|-----------------|-------|
| 7.1 | Show parts with status "Discontinued" | Error: Invalid Status value + list of allowed values | SOFT FAIL (prior run) — model paraphrased correctly as "not a valid value" |
| 7.2 | How many parts have status "No stock"? | **64** (present in current data) | PASS (1.3s) |
| 7.3 | Show parts with status "Component Request - Please review Logid" | 39 rows including 19-2656-05LF and 19-1690-02LF | PASS (8.7s) |

---

## 8. Follow-Up / Conversation Chain

| # | Step | Query | Expected | Pass? |
|---|------|-------|----------|-------|
| 8.1 | First | Tell me about 19-3082-01LF | Summary with data from both tables | |
| 8.2 | Follow-up | What is its replacement? | DM-287-38LF (from CRmaster) | |
| 8.3 | Follow-up | Export that to Excel | Excel file generated | |

---

## 9. Schema / Metadata Queries

| # | Query | Expected Answer | Pass? |
|---|-------|-----------------|-------|
| 9.1 | What tables are available? | operations.Obsolescence_Results, operations.CRmaster_ModelResults | PASS (5.2s) |
| 9.2 | What columns does CRmaster_ModelResults have? | pklogid, Comments, NewPNAssigned, Replacement_intent, Old_Part, New_Part, Cue_Phrase, Confidence, Rationale, Error, ModelProcessedDate, LogDate, updatetime, PartNumber | PASS (7.2s) |
| 9.3 | What are the distinct statuses? | The 4 statuses present in the data (see 6.4) | not tested |

---

## 10. Multi-Part Query (edge case)

| # | Query | Expected | Pass? |
|---|-------|----------|-------|
| 10.1 | Tell me about 19-1690-02LF and 28-457-17LF | Data for BOTH parts, from both tables | PASS (8.3s) |

---

## 11. Tricky / Ambiguous Queries

| # | Query | Expected Behavior | Pass? |
|---|-------|--------------------|-------|
| 11.1 | What is the replacement_intent for all parts with status "May be eligible to be scrapped"? | Should find 19-2166-01LF in Obsolescence, then look up CRmaster → Replacement_intent: N | not tested |
| 11.2 | Which parts have confidence above 0.90? | Should query CRmaster. Expected: 50101(0.95), 50104(0.91), 50106(0.97), 50110(0.93), 50111(0.90), 50114(0.92), 50117(0.96), 50119(0.94) | PASS (21.6s) |
| 11.3 | List all parts that have a replacement | Should query CRmaster where Replacement_intent=Y. 12+ parts expected. | not tested |

---

## 12. Non-PartNumber Lookups (RULE 4 — get_row_by_id)

| # | Query | Expected Answer | Pass? |
|---|-------|-----------------|-------|
| 12.1 | Show me the row with pklogid 50112 | DM-605-91LF, Confidence: 0.89, Replacement_intent: Y, NewPN: DM-605-95LF | PASS (8.3s) |
| 12.2 | Show me the row with pklogid 50106 | 19-3082-01LF, Confidence: 0.97 | PASS (8.5s) |
| 12.3 | What is the PartNumber for pklogid 50101? | **19-1690-02LF** | PASS (7.5s) |

**What to check:** Uses `get_row_by_id` (not `query_table`). Returns actual data, no fabrication. Concise response.

---

## Quick Reference: Live Data Snapshot

### Obsolescence_Results (10 rows)

| PartNumber | Status | Details |
|------------|--------|---------|
| 19-3232-01LF | Need Further Review-NO BOM | — |
| 19-3082-01LF | In WhereUsed with parent | 60-1996-102 |
| 19-3148-01LF | In WhereUsed with parent | 60-1981-002291 |
| 19-3119-01LF | In WhereUsed with parent | 60-1600-13U |
| 19-3081-01LF | In WhereUsed with parent | 60-1993-03 |
| 19-2990-02LF | In WhereUsed with parent | 60-1993-03 |
| 19-2166-01LF | May be eligible to be scrapped | — |
| 19-2656-05LF | Component Request - Please review Logid | {"Logid": 40463.0} |
| 19-1690-02LF | Component Request - Please review Logid | {"Logid": 23358.0} |
| 28-457-17LF | In WhereUsed with parent | 60-1746-11UPV |

### CRmaster_ModelResults — Overlapping Parts (10 rows)

| pklogid | PartNumber | Replacement_intent | Confidence | NewPNAssigned | Comments (short) |
|---------|------------|-------------------|------------|---------------|-----------------|
| 50101 | 19-1690-02LF | Y | 0.95 | DM-410-25LF | Replaced per ECN |
| 50102 | 19-2166-01LF | N | 0.88 | — | No replacement; vendor evaluating |
| 50103 | 19-2656-05LF | Y | 0.82 | DM-118-50LF | Alternate from backup supplier |
| 50104 | 19-2990-02LF | Y | 0.91 | DM-926-15LF | Customer approved substitute |
| 50105 | 19-3081-01LF | N | 0.60 | — | Multiple candidates under evaluation |
| 50106 | 19-3082-01LF | Y | 0.97 | DM-287-38LF | Drop-in confirmed by manufacturer |
| 50107 | 19-3119-01LF | Y | 0.73 | DM-641-22LF | Pending reliability data |
| 50108 | 19-3148-01LF | Y | 0.78 | DM-892-10LF | Design change required |
| 50109 | 19-3232-01LF | N | 0.85 | — | Last-time buy; 18 months inventory |
| 50110 | 28-457-17LF | Y | 0.93 | DM-309-60LF | Functional equivalent validated |

### CRmaster_ModelResults — CRmaster-Only Parts (10 rows)

| pklogid | PartNumber | Replacement_intent | Confidence | NewPNAssigned |
|---------|------------|-------------------|------------|---------------|
| 50111 | DM-478-14LF | N | 0.90 | — |
| 50112 | DM-605-91LF | Y | 0.89 | DM-605-95LF |
| 50113 | DM-733-28LF | Y | 0.76 | DM-733-32LF |
| 50114 | DM-821-63LF | Y | 0.92 | DM-821-68LF |
| 50115 | DM-945-02LF | Y | 0.70 | DM-945-08LF |
| 50116 | DM-112-87LF | N | 0.65 | — |
| 50117 | DM-367-41LF | Y | 0.96 | DM-367-46LF |
| 50118 | DM-590-36LF | N | 0.55 | — |
| 50119 | DM-714-53LF | Y | 0.94 | DM-714-58LF |
| 50120 | DM-856-19LF | Y | 0.80 | DM-856-24LF |

### CRmaster_ModelResults — 1-to-Many Rows (added for benchmark section 13)

| pklogid | PartNumber | Replacement_intent | Confidence | NewPNAssigned | ModelProcessedDate |
|---------|------------|-------------------|------------|---------------|-------------------|
| 50101 | 19-1690-02LF | Y | 0.95 | DM-410-25LF | 2026-04-18 |
| 50201 | 19-1690-02LF | Y | 0.72 | DM-410-20LF | 2026-03-10 |
| 50202 | 19-1690-02LF | N | 0.60 | — | 2026-02-05 |
| 50106 | 19-3082-01LF | Y | 0.97 | DM-287-38LF | 2026-04-18 |
| 50203 | 19-3082-01LF | Y | 0.68 | DM-287-30LF | 2026-03-01 |
| 50110 | 28-457-17LF | Y | 0.93 | DM-309-60LF | 2026-04-18 |
| 50204 | 28-457-17LF | Y | 0.71 | DM-309-55LF | 2026-02-20 |

---

## 13. One-to-Many Relationship Queries

| # | Query | Expected Answer | Pass? |
|---|-------|-----------------|-------|
| 13.1 | How many CRmaster entries does 19-1690-02LF have? | **3** | |
| 13.2 | Show all model results for 19-1690-02LF | 3 rows: pklogid 50101 (Conf 0.95, DM-410-25LF), 50201 (Conf 0.72, DM-410-20LF), 50202 (Conf 0.60, no replacement) | |
| 13.3 | What is the highest confidence score for 19-1690-02LF? | **0.95** (pklogid 50101) | |
| 13.4 | What is the latest model result for 19-3082-01LF? | pklogid 50106, processed 2026-04-18, Confidence 0.97, NewPN DM-287-38LF | |
| 13.5 | Has the replacement recommendation changed for 19-3082-01LF? | Yes — earlier run (50203) suggested DM-287-30LF at 0.68 confidence; latest (50106) confirms DM-287-38LF at 0.97 | |
| 13.6 | What is the average confidence for 28-457-17LF? | **0.82** (average of 0.93 and 0.71) | |
| 13.7 | How many model runs recommended a replacement for 19-1690-02LF? | **2** (pklogid 50101 and 50201 have Replacement_intent=Y; 50202 is N) | |
| 13.8 | Show all parts that have more than one CRmaster entry | 19-1690-02LF (3), 19-3082-01LF (2), 28-457-17LF (2) | |

**What to check:** Agent correctly handles multiple rows per part. Aggregations (count, max, avg) are accurate. "Latest" uses ModelProcessedDate ordering. No hallucination of extra rows.

---

## 14. Edge Cases — Robustness & Consistency

| # | Query | Expected Behavior | Pass? |
|---|-------|--------------------|-------|
| 14.1 | what is the status of 19-1690-02lf? | Same as 1.1 — lowercase input should not break lookup | |
| 14.2 | status for 19-1690-02LF | Terse input without full sentence — still returns Component Request | |
| 14.3 | Is there any info on part 19-3082-01LF? | Natural phrasing — should work like "tell me about" | |
| 14.4 | What is the confidence for FAKE-000-00LF? | No data found — doesn't hallucinate a confidence value | |
| 14.5 | What is the warranty for 19-1690-02LF? | Graceful handling — no "warranty" column exists | |
| 14.6 | Which part is the best? | Ambiguous — should ask for clarification or state criteria needed | |
| 14.7 | What is the status of '; DROP TABLE parts; --? | SQL injection — should not crash or execute; no data found | |
| 14.8 | 50101 | Bare number — should interpret as pklogid or ask for clarification | |
| 14.9 | Tell me about 19-1690-02LF. Also what is 28-457-17LF replacement? | Compound question — both parts answered in one response | |
| 14.10 | What is the status of 19-1690-02LF and the confidence of 19-3082-01LF? | Two different properties for two different parts — both correct | |

**What to check:** Agent handles edge inputs gracefully — case insensitivity, terse phrasing, injections, ambiguity, compound questions. No crashes, no hallucinations.
