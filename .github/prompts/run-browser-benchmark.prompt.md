---
mode: agent
description: "Run benchmark tests through the browser UI at localhost:3978"
---

## Instructions

Run the test bank benchmarks visually through the browser GUI. Follow this workflow:

1. **Start the server** (if not already running): `python main_test.py` in async mode. Wait for "Running on http://0.0.0.0:3978".

2. **Open the browser** to `http://localhost:3978`.

3. **Load test cases** from `scripts/run_test_bank.py` — use the `build_tests()` function to identify queries and expected answers. If the user specifies `--section X`, only run that section's tests.

4. **Run each query one by one** through the GUI:
   - Fill the textbox with the query
   - Click Send
   - Wait for the bot response (8-10 seconds)
   - Capture the bot's last `.message.bot` text

5. **Evaluate** each response against the expected answer using the same logic as the benchmark checkers (contains keywords, exact values, numbers, etc.)

6. **Report results** in a table showing: Test ID, Query, Expected, Actual (truncated), Verdict (PASS/FAIL).

7. **Flag any failures** with details on what was expected vs what was returned.

## Default behavior
- If no section is specified, run 5 representative queries (one from each major category).
- If `--section 13` or similar is specified, run all tests from that section.
- If `--all` is specified, run the full test bank (warning: this takes several minutes).
