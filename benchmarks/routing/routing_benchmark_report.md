# Routing Benchmark Report

- **Timestamp (UTC):** 2026-06-18T13:53:08.037215Z
- **Trials:** 3
- **Questions/trial:** 10
- **Total evaluated:** 30
- **Matched-role accuracy:** 100.0%
- **Strict routing accuracy:** 100.0%
- **Solid threshold:** 85.0%
- **Solid:** YES
- **Execution mode:** `offline`
- **Chosen attempt:** `baseline`

## Dataset

- Primary table file stem: `20260618000000_obsolescence`
- Supplemental table file stem: `dimProducts`
- Data rows are deterministic and regenerated on each run.

## Per-question results

| Question ID | Expected role | Queried roles | Strict | Error |
|---|---|---|---|---|
| T1-Q1 | primary | primary | ✅ |  |
| T1-Q2 | primary | primary | ✅ |  |
| T1-Q3 | primary | primary | ✅ |  |
| T1-Q4 | supplemental | supplemental | ✅ |  |
| T1-Q5 | supplemental | supplemental | ✅ |  |
| T1-Q6 | supplemental | supplemental | ✅ |  |
| T1-Q7 | supplemental | supplemental | ✅ |  |
| T1-Q8 | supplemental | supplemental | ✅ |  |
| T1-Q9 | primary | primary | ✅ |  |
| T1-Q10 | primary | primary | ✅ |  |
| T2-Q1 | primary | primary | ✅ |  |
| T2-Q2 | primary | primary | ✅ |  |
| T2-Q3 | primary | primary | ✅ |  |
| T2-Q4 | supplemental | supplemental | ✅ |  |
| T2-Q5 | supplemental | supplemental | ✅ |  |
| T2-Q6 | supplemental | supplemental | ✅ |  |
| T2-Q7 | supplemental | supplemental | ✅ |  |
| T2-Q8 | supplemental | supplemental | ✅ |  |
| T2-Q9 | primary | primary | ✅ |  |
| T2-Q10 | primary | primary | ✅ |  |
| T3-Q1 | primary | primary | ✅ |  |
| T3-Q2 | primary | primary | ✅ |  |
| T3-Q3 | primary | primary | ✅ |  |
| T3-Q4 | supplemental | supplemental | ✅ |  |
| T3-Q5 | supplemental | supplemental | ✅ |  |
| T3-Q6 | supplemental | supplemental | ✅ |  |
| T3-Q7 | supplemental | supplemental | ✅ |  |
| T3-Q8 | supplemental | supplemental | ✅ |  |
| T3-Q9 | primary | primary | ✅ |  |
| T3-Q10 | primary | primary | ✅ |  |

## Attempts

| Attempt | Mode | Strict accuracy | Solid |
|---|---|---:|---|
| baseline | offline | 100.0% | YES |

## Learnings

- Routing is stable for the benchmark question set; strict table-role routing met the threshold.
- The benchmark captures real table calls from tool methods, so results reflect actual routing behavior.
