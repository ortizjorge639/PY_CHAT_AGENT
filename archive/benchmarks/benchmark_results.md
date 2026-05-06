# Agent Benchmark Report

**Date:** 2026-05-04 15:27:49
**Trials:** 10
**Total runtime:** 256.3s
**Model:** gpt-4o
**Table:** operations.Obsolescence_Results (500 rows)

## Ground Truth
- **Total rows:** 500
- **Real part (scrappable):** `15-4578-02` → *May be eligible to be scrapped*
- **Fake part:** `99-0000-FAKE` → *not in database*

## Conversation Template
| # | Question |
|---|----------|
| 1 | How many rows does the table have? |
| 2 | Show me the rows |
| 3 | Please put the results into an Excel file |
| 4 | Can part 15-4578-02 be scrapped? |
| 5 | Can part 99-0000-FAKE be scrapped? |

## Per-Question Accuracy
| Question | Pass Rate | Avg Latency |
|----------|-----------|-------------|
| Q1: How many rows does the table have? | 100% (10/10) | 3.23s |
| Q2: Show me the rows | 100% (10/10) | 11.57s |
| Q3: Please put the results into an Excel file | 100% (10/10) | 1.91s |
| Q4: Can part 15-4578-02 be scrapped? | 100% (10/10) | 3.78s |
| Q5: Can part 99-0000-FAKE be scrapped? | 100% (10/10) | 4.21s |

## Overall Accuracy: **100.0%** (50/50)

## Per-Trial Breakdown
| Trial | Q1 | Q2 | Q3 | Q4 | Q5 | Score | Latency |
|-------|----|----|----|----|----| ------|---------|
| 1 | ✅ | ✅ | ✅ | ✅ | ✅ | 5/5 | 12.6s |
| 2 | ✅ | ✅ | ✅ | ✅ | ✅ | 5/5 | 12.5s |
| 3 | ✅ | ✅ | ✅ | ✅ | ✅ | 5/5 | 13.2s |
| 4 | ✅ | ✅ | ✅ | ✅ | ✅ | 5/5 | 16.5s |
| 5 | ✅ | ✅ | ✅ | ✅ | ✅ | 5/5 | 28.2s |
| 6 | ✅ | ✅ | ✅ | ✅ | ✅ | 5/5 | 28.9s |
| 7 | ✅ | ✅ | ✅ | ✅ | ✅ | 5/5 | 28.9s |
| 8 | ✅ | ✅ | ✅ | ✅ | ✅ | 5/5 | 82.7s |
| 9 | ✅ | ✅ | ✅ | ✅ | ✅ | 5/5 | 11.8s |
| 10 | ✅ | ✅ | ✅ | ✅ | ✅ | 5/5 | 11.6s |

## No failures — all questions passed in all trials! 🎉