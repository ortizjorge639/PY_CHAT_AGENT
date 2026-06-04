# Robust Agent Benchmark Report (v2)

**Date:** 2026-05-04 16:47:48
**Trials:** 10
**Questions per trial:** 8
**Total questions:** 80
**Total runtime:** 540.8s
**Model:** gpt-4o
**Table:** operations.Obsolescence_Results (500 rows)

## Overall Accuracy: **100.0%** (80/80)

## Per-Category Accuracy
| Category | Pass Rate | Avg Latency | Notes |
|----------|-----------|-------------|-------|
| Row Count (varied phrasing) | 100% (10/10) | 5.77s | |
| Part Lookup (with Details) | 100% (10/10) | 5.16s | |
| Part Lookup (NULL Details) | 100% (10/10) | 4.89s | |
| Part Lookup (NOT eligible status) | 100% (10/10) | 6.81s | |
| Fake Part Rejection | 100% (10/10) | 5.69s | |
| Status Distribution Query | 100% (10/10) | 7.71s | |
| Excel Export Request | 100% (10/10) | 8.34s | |
| Hallucination Resistance | 100% (10/10) | 8.61s | |

## Per-Trial Breakdown
| Trial | Q1:Count | Q2:Details | Q3:NullDet | Q4:NotElig | Q5:Fake | Q6:Distrib | Q7:Excel | Q8:Halluc | Score | Latency |
|-------|------|------|------|------|------|------|------|------|-------|---------|
| 1 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8/8 | 20.9s |
| 2 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8/8 | 43.4s |
| 3 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8/8 | 54.0s |
| 4 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8/8 | 59.3s |
| 5 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8/8 | 62.4s |
| 6 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8/8 | 60.6s |
| 7 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8/8 | 58.4s |
| 8 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8/8 | 58.3s |
| 9 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8/8 | 59.2s |
| 10 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 8/8 | 53.3s |

## Detailed Question Log
| Trial | Q# | Category | Question | Pass | Latency |
|-------|----|----------|----------|------|---------|
| 1 | 1 | Row Count (varied phrasin | what's the total number of records? | ✅ | 3.0s |
| 1 | 2 | Part Lookup (with Details | what is the status of 15-1618-01A? | ✅ | 2.1s |
| 1 | 3 | Part Lookup (NULL Details | what's the status of part 15-3196-02A? | ✅ | 2.4s |
| 1 | 4 | Part Lookup (NOT eligible | can I scrap part 15-5803-01A? | ✅ | 2.3s |
| 1 | 5 | Fake Part Rejection | can part 00-0001-XX be scrapped? | ✅ | 4.0s |
| 1 | 6 | Status Distribution Query | break down the data by status | ✅ | 3.1s |
| 1 | 7 | Excel Export Request | export that to Excel | ✅ | 2.5s |
| 1 | 8 | Hallucination Resistance | show me the supplier for part 15-1539-01 | ✅ | 1.5s |
| 2 | 1 | Row Count (varied phrasin | count the rows in the table | ✅ | 2.5s |
| 2 | 2 | Part Lookup (with Details | look up part 15-2288-02A | ✅ | 2.6s |
| 2 | 3 | Part Lookup (NULL Details | look up 15-4312-21 for me | ✅ | 2.5s |
| 2 | 4 | Part Lookup (NOT eligible | can I scrap part 19-5905-02LF? | ✅ | 2.8s |
| 2 | 5 | Fake Part Rejection | can part 11-1111-11 be scrapped? | ✅ | 4.6s |
| 2 | 6 | Status Distribution Query | give me a count per status | ✅ | 8.8s |
| 2 | 7 | Excel Export Request | can I get a spreadsheet download? | ✅ | 8.9s |
| 2 | 8 | Hallucination Resistance | how many parts have status 'Discontinued'? | ✅ | 10.6s |
| 3 | 1 | Row Count (varied phrasin | how big is the dataset? | ✅ | 6.8s |
| 3 | 2 | Part Lookup (with Details | tell me about part number 15-1539-01 | ✅ | 5.2s |
| 3 | 3 | Part Lookup (NULL Details | is part 15-3167-11 scrap-eligible? | ✅ | 5.7s |
| 3 | 4 | Part Lookup (NOT eligible | can I scrap part 15-6632-02A? | ✅ | 6.1s |
| 3 | 5 | Fake Part Rejection | can part AA-BBBB-CC be scrapped? | ✅ | 8.3s |
| 3 | 6 | Status Distribution Query | show the status distribution | ✅ | 7.4s |
| 3 | 7 | Excel Export Request | generate an Excel file with those results | ✅ | 10.8s |
| 3 | 8 | Hallucination Resistance | what is the warranty status of part 15-1618-01A? | ✅ | 3.6s |
| 4 | 1 | Row Count (varied phrasin | what is the row count? | ✅ | 5.7s |
| 4 | 2 | Part Lookup (with Details | is 15-1618-01A eligible for scrap? | ✅ | 6.5s |
| 4 | 3 | Part Lookup (NULL Details | check 15-3196-02A | ✅ | 5.0s |
| 4 | 4 | Part Lookup (NOT eligible | can I scrap part 19-2796-01? | ✅ | 7.5s |
| 4 | 5 | Fake Part Rejection | can part 12-3456-NOPE be scrapped? | ✅ | 6.0s |
| 4 | 6 | Status Distribution Query | group the parts by their status | ✅ | 9.1s |
| 4 | 7 | Excel Export Request | download as xlsx please | ✅ | 8.7s |
| 4 | 8 | Hallucination Resistance | list all parts from the New York warehouse | ✅ | 10.8s |
| 5 | 1 | Row Count (varied phrasin | tell me how many entries are in the table | ✅ | 8.9s |
| 5 | 2 | Part Lookup (with Details | check part 15-2288-02A for me | ✅ | 5.5s |
| 5 | 3 | Part Lookup (NULL Details | what about 15-4312-21? | ✅ | 6.3s |
| 5 | 4 | Part Lookup (NOT eligible | can I scrap part 15-3126-02LF? | ✅ | 5.8s |
| 5 | 5 | Fake Part Rejection | can part 99-9999-01LF be scrapped? | ✅ | 7.2s |
| 5 | 6 | Status Distribution Query | what's the breakdown by status? | ✅ | 9.0s |
| 5 | 7 | Excel Export Request | I need that in a spreadsheet | ✅ | 8.2s |
| 5 | 8 | Hallucination Resistance | which parts were manufactured in 2025? | ✅ | 11.4s |
| 6 | 1 | Row Count (varied phrasin | total number of parts in the table? | ✅ | 6.0s |
| 6 | 2 | Part Lookup (with Details | what do we know about 15-1539-01? | ✅ | 6.1s |
| 6 | 3 | Part Lookup (NULL Details | tell me the disposition of 15-3167-11 | ✅ | 5.6s |
| 6 | 4 | Part Lookup (NOT eligible | can I scrap part 15-5803-01A? | ✅ | 6.6s |
| 6 | 5 | Fake Part Rejection | can part 00-0000-00 be scrapped? | ✅ | 6.7s |
| 6 | 6 | Status Distribution Query | count parts grouped by status | ✅ | 9.1s |
| 6 | 7 | Excel Export Request | create an Excel export | ✅ | 9.1s |
| 6 | 8 | Hallucination Resistance | show me parts with priority level High | ✅ | 11.4s |
| 7 | 1 | Row Count (varied phrasin | how many parts are there? | ✅ | 6.2s |
| 7 | 2 | Part Lookup (with Details | pull up 15-1618-01A | ✅ | 5.7s |
| 7 | 3 | Part Lookup (NULL Details | query part 15-3196-02A | ✅ | 5.4s |
| 7 | 4 | Part Lookup (NOT eligible | can I scrap part 19-5905-02LF? | ✅ | 6.2s |
| 7 | 5 | Fake Part Rejection | can part 55-0000-ZZ be scrapped? | ✅ | 7.5s |
| 7 | 6 | Status Distribution Query | summarize by status | ✅ | 8.2s |
| 7 | 7 | Excel Export Request | give me a downloadable file | ✅ | 8.8s |
| 7 | 8 | Hallucination Resistance | what's the cost to scrap part 15-4578-02? | ✅ | 10.4s |
| 8 | 1 | Row Count (varied phrasin | give me the record count | ✅ | 6.5s |
| 8 | 2 | Part Lookup (with Details | find part 15-2288-02A in the database | ✅ | 5.3s |
| 8 | 3 | Part Lookup (NULL Details | part 15-4312-21 — can we scrap it? | ✅ | 5.9s |
| 8 | 4 | Part Lookup (NOT eligible | can I scrap part 15-6632-02A? | ✅ | 13.7s |
| 8 | 5 | Fake Part Rejection | can part 78-1234-BOGUS be scrapped? | ✅ | 2.4s |
| 8 | 6 | Status Distribution Query | how are parts distributed across statuses? | ✅ | 5.7s |
| 8 | 7 | Excel Export Request | save that as Excel | ✅ | 9.1s |
| 8 | 8 | Hallucination Resistance | who approved the scrap for part 15-3126-02LF? | ✅ | 9.6s |
| 9 | 1 | Row Count (varied phrasin | what's the size of the data? | ✅ | 6.6s |
| 9 | 2 | Part Lookup (with Details | scrap eligibility for 15-1539-01? | ✅ | 6.4s |
| 9 | 3 | Part Lookup (NULL Details | status of 15-3167-11 please | ✅ | 4.5s |
| 9 | 4 | Part Lookup (NOT eligible | can I scrap part 19-2796-01? | ✅ | 10.6s |
| 9 | 5 | Fake Part Rejection | can part 42-0000-TEST be scrapped? | ✅ | 2.8s |
| 9 | 6 | Status Distribution Query | status summary please | ✅ | 8.6s |
| 9 | 7 | Excel Export Request | export to spreadsheet | ✅ | 8.5s |
| 9 | 8 | Hallucination Resistance | list parts from vendor Acme Corp | ✅ | 11.2s |
| 10 | 1 | Row Count (varied phrasin | how many rows does the table have | ✅ | 5.5s |
| 10 | 2 | Part Lookup (with Details | can part 15-1618-01A be scrapped? | ✅ | 6.1s |
| 10 | 3 | Part Lookup (NULL Details | can part 15-3196-02A be scrapped? | ✅ | 5.5s |
| 10 | 4 | Part Lookup (NOT eligible | can I scrap part 15-3126-02LF? | ✅ | 6.4s |
| 10 | 5 | Fake Part Rejection | can part 99-0000-FAKE be scrapped? | ✅ | 7.3s |
| 10 | 6 | Status Distribution Query | how many parts are in each status? | ✅ | 8.3s |
| 10 | 7 | Excel Export Request | please put the results into an excel file | ✅ | 8.6s |
| 10 | 8 | Hallucination Resistance | what is the price of part 15-3167-11? | ✅ | 5.5s |

## No failures — all questions passed in all trials! 🎉

## Methodology
- **Question variation:** Each trial uses different phrasings (10 variants per category)
- **Part rotation:** Real parts rotate across trials (different statuses, with/without Details)
- **Fake parts:** 10 different fake part numbers, verified not in DB
- **Hallucination tests:** Asks about non-existent columns (price, supplier, warranty, etc.)
- **Strict evaluation:** Part lookups verify exact status match + Details handling
- **NOT-eligible test:** Checks agent doesn't falsely say a part can be scrapped
- **Distribution test:** Verifies real counts appear, not fabricated numbers
- **Excel test:** Requires actual .xlsx file generation, not just text claim