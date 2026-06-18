# Routing Benchmark Learnings

## What was added

- `scripts/run_routing_benchmark.py`
  - Builds a deterministic mock multi-table dataset on each run.
  - Tracks the exact table names queried by data tools per question.
  - Scores routing accuracy against expected table role (`primary` vs `supplemental`).
  - Writes:
    - `/home/runner/work/PY_CHAT_AGENT/PY_CHAT_AGENT/benchmarks/routing/routing_benchmark_results.json`
    - `/home/runner/work/PY_CHAT_AGENT/PY_CHAT_AGENT/benchmarks/routing/routing_benchmark_report.md`
  - Cleans temporary mock data automatically unless `--keep-data` is passed.

## Benchmark method

1. Generate two Excel tables with overlapping `PartNumber` values:
   - `20260618000000_obsolescence.xlsx` (treated as **primary** by existing loader role logic)
   - `dimProducts.xlsx` (treated as **supplemental**)
2. Ask a fixed question set containing:
   - scrap/status/QOH intents (expected **primary**)
   - description/phase/custom-button/international-powercord/serialized intents (expected **supplemental**)
3. Record table calls from `get_rows`, `count_rows`, `query_table`, `group_by`, `get_schema`, `get_distinct_values`.
4. Compute:
   - **Matched-role accuracy**: expected role appears in queried roles.
   - **Strict accuracy**: only one role queried, and it matches expected role.
5. Mark benchmark **solid** if strict accuracy >= 85%.

## Latest run

- Command:
  - `python scripts/run_routing_benchmark.py --trials 3 --mode auto`
- Result:
  - Strict accuracy: **100.0%**
  - Matched-role accuracy: **100.0%**
  - Solid: **YES**
  - Chosen attempt: `baseline`
  - Execution mode: `offline` (auto fallback, because live Azure credentials were not available in this environment)

## Practical guidance

- For true end-to-end LLM routing validation, run with live credentials:
  - `python scripts/run_routing_benchmark.py --trials 3 --mode live`
- Use `--mode auto` for CI/dev environments that may not have Azure credentials.
- Keep strict accuracy at or above 85% before accepting prompt or routing-rule changes.
