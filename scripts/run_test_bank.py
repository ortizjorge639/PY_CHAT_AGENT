"""
Test Bank Benchmark Runner

Runs all test cases from TEST_BANK.md through the live AgentKernel
and evaluates responses against expected answers.

Usage:
    python scripts/run_test_bank.py
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from config.settings import Settings
from data.loader import DataLoader
from agent.kernel import AgentKernel

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("test_bank")
logger.setLevel(logging.INFO)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "benchmarks")


# ─────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    id: str
    section: str
    query: str
    expected: str
    check: Callable[[str, str], "TestResult"]


@dataclass
class TestResult:
    test_id: str
    section: str
    query: str
    expected: str
    actual: str
    passed: bool
    elapsed: float
    notes: str = ""


# ─────────────────────────────────────────────────────────────────
# Evaluation helpers
# ─────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase and strip extra whitespace for fuzzy comparison."""
    return re.sub(r"\s+", " ", text.lower().strip())


def check_contains_all(keywords: list[str]):
    """Return a checker that passes if ALL keywords are found in the response."""
    def _check(response: str, _expected: str) -> TestResult:
        norm = _normalize(response)
        missing = [k for k in keywords if k.lower() not in norm]
        passed = len(missing) == 0
        notes = f"Missing: {missing}" if missing else ""
        return TestResult("", "", "", "", response, passed, 0.0, notes)
    return _check


def check_contains_any(keywords: list[str]):
    """Return a checker that passes if ANY keyword is found in the response."""
    def _check(response: str, _expected: str) -> TestResult:
        norm = _normalize(response)
        found = [k for k in keywords if k.lower() in norm]
        passed = len(found) > 0
        notes = f"Found: {found}" if found else f"None of {keywords} found"
        return TestResult("", "", "", "", response, passed, 0.0, notes)
    return _check


def check_exact_value(value: str, case_sensitive: bool = False):
    """Return a checker that passes if the exact value appears in the response."""
    def _check(response: str, _expected: str) -> TestResult:
        if case_sensitive:
            passed = value in response
        else:
            passed = value.lower() in response.lower()
        notes = "" if passed else f"'{value}' not found in response"
        return TestResult("", "", "", "", response, passed, 0.0, notes)
    return _check


def check_number(expected_num: int):
    """Return a checker that passes if the expected number appears in the response."""
    def _check(response: str, _expected: str) -> TestResult:
        numbers = re.findall(r"\b(\d+)\b", response)
        int_numbers = [int(n) for n in numbers]
        passed = expected_num in int_numbers
        notes = f"Found numbers: {int_numbers}" if not passed else ""
        return TestResult("", "", "", "", response, passed, 0.0, notes)
    return _check


def check_no_data():
    """Return a checker that passes if the response indicates no data found."""
    def _check(response: str, _expected: str) -> TestResult:
        norm = _normalize(response)
        indicators = ["no data", "not found", "could not find", "no rows", "no results",
                       "doesn't exist", "does not exist", "no matching", "no information",
                       "no status or data available", "no status", "not available"]
        found = any(ind in norm for ind in indicators)
        notes = "" if found else "Response did not indicate 'no data found'"
        return TestResult("", "", "", "", response, found, 0.0, notes)
    return _check


def check_invalid_status():
    """Return a checker that passes if the response indicates invalid status."""
    def _check(response: str, _expected: str) -> TestResult:
        norm = _normalize(response)
        indicators = ["invalid", "not a valid", "not valid", "not recognized",
                       "allowed values", "valid status"]
        found = any(ind in norm for ind in indicators)
        notes = "" if found else "Response did not indicate invalid status"
        return TestResult("", "", "", "", response, found, 0.0, notes)
    return _check


def check_count_and_parts(expected_count: int, expected_parts: list[str]):
    """Check count appears AND at least some expected parts are mentioned."""
    def _check(response: str, _expected: str) -> TestResult:
        norm = _normalize(response)
        numbers = [int(n) for n in re.findall(r"\b(\d+)\b", response)]
        count_ok = expected_count in numbers
        parts_found = [p for p in expected_parts if p.lower() in norm]
        passed = count_ok and len(parts_found) >= 1
        notes = []
        if not count_ok:
            notes.append(f"Expected count {expected_count}, found {numbers}")
        if len(parts_found) < 1:
            notes.append(f"Expected some of {expected_parts}")
        return TestResult("", "", "", "", response, passed, 0.0, "; ".join(notes))
    return _check


def check_status_breakdown(expected_breakdown: dict[str, int]):
    """Check that status breakdown numbers appear in the response."""
    def _check(response: str, _expected: str) -> TestResult:
        norm = _normalize(response)
        missing = []
        for status, count in expected_breakdown.items():
            # Check that the status name and its count appear
            if status.lower() not in norm:
                missing.append(f"Status '{status}' not mentioned")
            elif str(count) not in response:
                missing.append(f"Count {count} for '{status}' not found")
        passed = len(missing) == 0
        notes = "; ".join(missing) if missing else ""
        return TestResult("", "", "", "", response, passed, 0.0, notes)
    return _check


def check_tables_listed(expected_tables: list[str]):
    """Check that table names are listed."""
    def _check(response: str, _expected: str) -> TestResult:
        norm = _normalize(response)
        missing = [t for t in expected_tables if t.lower() not in norm]
        passed = len(missing) == 0
        notes = f"Missing tables: {missing}" if missing else ""
        return TestResult("", "", "", "", response, passed, 0.0, notes)
    return _check


def check_columns_listed(expected_columns: list[str]):
    """Check that column names appear (at least most of them)."""
    def _check(response: str, _expected: str) -> TestResult:
        norm = _normalize(response)
        found = [c for c in expected_columns if c.lower() in norm]
        threshold = len(expected_columns) * 0.7  # 70% must be present
        passed = len(found) >= threshold
        notes = f"Found {len(found)}/{len(expected_columns)} columns" if not passed else ""
        return TestResult("", "", "", "", response, passed, 0.0, notes)
    return _check


def check_confidence_list(expected_parts_above: list[str]):
    """Check that parts with high confidence are listed."""
    def _check(response: str, _expected: str) -> TestResult:
        norm = _normalize(response)
        found = [p for p in expected_parts_above if p.lower() in norm]
        threshold = len(expected_parts_above) * 0.6
        passed = len(found) >= threshold
        notes = f"Found {len(found)}/{len(expected_parts_above)} expected parts" if not passed else ""
        return TestResult("", "", "", "", response, passed, 0.0, notes)
    return _check


# ─────────────────────────────────────────────────────────────────
# Test definitions (from TEST_BANK.md)
# ─────────────────────────────────────────────────────────────────

def build_tests() -> list[TestCase]:
    tests = []

    # ── 1. Single-Part Status Queries ────────────────────────────
    tests.append(TestCase(
        "1.1", "Single-Part Status",
        "What is the status of 19-1690-02LF?",
        "Component Request - Please review Logid",
        check_contains_all(["component request", "please review logid"]),
    ))
    tests.append(TestCase(
        "1.2", "Single-Part Status",
        "What is the status of 19-2990-02LF?",
        "In WhereUsed with parent",
        check_contains_all(["in whereused with parent"]),
    ))
    tests.append(TestCase(
        "1.3", "Single-Part Status",
        "What is the status of 19-2166-01LF?",
        "May be eligible to be scrapped",
        check_contains_all(["may be eligible to be scrapped"]),
    ))
    tests.append(TestCase(
        "1.4", "Single-Part Status",
        "What is the status of 19-3232-01LF?",
        "Need Further Review-NO BOM",
        check_contains_all(["need further review"]),
    ))

    # ── 2. Single-Part Cross-Table Property Queries ──────────────
    tests.append(TestCase(
        "2.1", "Cross-Table Property",
        "What is the confidence score for 19-3082-01LF?",
        "0.97",
        check_exact_value("0.97"),
    ))
    tests.append(TestCase(
        "2.2", "Cross-Table Property",
        "Does 19-1690-02LF have a replacement?",
        "Yes — NewPN: DM-410-25LF",
        check_contains_all(["dm-410-25lf"]),
    ))
    tests.append(TestCase(
        "2.3", "Cross-Table Property",
        "What is the replacement_intent for 19-3232-01LF?",
        "N",
        check_contains_any(["replacement_intent: n", "replacement_intent is n",
                            "replacement intent: n", "replacement intent is n",
                            ": n", "\"n\"", "is **n**", "is n"]),
    ))
    tests.append(TestCase(
        "2.4", "Cross-Table Property",
        "What is the confidence for 28-457-17LF?",
        "0.93",
        check_exact_value("0.93"),
    ))
    tests.append(TestCase(
        "2.5", "Cross-Table Property",
        "What are the comments for 19-2990-02LF?",
        "Customer approved substitute last month.",
        check_contains_any(["customer approved substitute"]),
    ))

    # ── 3. Broad Part Lookups ────────────────────────────────────
    tests.append(TestCase(
        "3.1", "Broad Lookup",
        "Tell me about 19-3082-01LF",
        "Status: In WhereUsed, Confidence: 0.97, NewPN: DM-287-38LF",
        check_contains_all(["in whereused with parent"]),
    ))
    tests.append(TestCase(
        "3.2", "Broad Lookup",
        "Tell me about 19-2166-01LF",
        "Status: May be eligible to be scrapped, Confidence: 0.88",
        check_contains_all(["may be eligible to be scrapped"]),
    ))
    tests.append(TestCase(
        "3.3", "Broad Lookup",
        "Tell me about 28-457-17LF",
        "Status: In WhereUsed, Confidence: 0.93, NewPN: DM-309-60LF",
        check_contains_all(["in whereused with parent"]),
    ))

    # ── 4. CRmaster-Only Parts ───────────────────────────────────
    tests.append(TestCase(
        "4.1", "CRmaster-Only",
        "Tell me about DM-478-14LF",
        "CRmaster only. Replacement_intent: N, Confidence: 0.90",
        check_contains_any(["0.90", "0.9", "no viable replacement", "obsolete", "dm-478-14lf"]),
    ))
    tests.append(TestCase(
        "4.2", "CRmaster-Only",
        "What is the confidence for DM-367-41LF?",
        "0.96",
        check_exact_value("0.96"),
    ))
    tests.append(TestCase(
        "4.3", "CRmaster-Only",
        "Does DM-605-91LF have a replacement?",
        "Yes — DM-605-95LF",
        check_contains_all(["dm-605-95lf"]),
    ))

    # ── 5. Nonexistent Parts ─────────────────────────────────────
    tests.append(TestCase(
        "5.1", "Nonexistent Part",
        "What is the status of FAKE-000-00LF?",
        "No data found",
        check_no_data(),
    ))
    tests.append(TestCase(
        "5.2", "Nonexistent Part",
        "Tell me about 99-9999-99LF",
        "No data found",
        check_no_data(),
    ))

    # ── 6. Aggregate Queries ─────────────────────────────────────
    tests.append(TestCase(
        "6.1", "Aggregate",
        "How many rows are in Obsolescence_Results?",
        "500",
        check_number(500),
    ))
    tests.append(TestCase(
        "6.2", "Aggregate",
        "How many rows are in CRmaster_ModelResults?",
        "24",
        check_number(24),
    ))
    tests.append(TestCase(
        "6.3", "Aggregate",
        'How many parts have status "In WhereUsed with parent"?',
        "83",
        check_number(83),
    ))
    tests.append(TestCase(
        "6.4", "Aggregate",
        "Break down Obsolescence_Results by Status",
        "In WhereUsed: 6, Component Request: 2, Need Further Review: 1, May be eligible: 1",
        check_status_breakdown({
            "In WhereUsed with parent": 83,
            "Component Request": 39,
            "Need Further Review": 25,
            "May be eligible to be scrapped": 51,
        }),
    ))

    # ── 7. Status Validation ─────────────────────────────────────
    tests.append(TestCase(
        "7.1", "Status Validation",
        'Show parts with status "Discontinued"',
        "Invalid Status value + allowed values",
        check_contains_any(["invalid", "not a valid", "not valid", "not recognized",
                            "not listed", "allowed values", "valid status",
                            "not an authoritative", "not one of",
                            "does not include", "not include",
                            "not among", "not found", "no parts",
                            "does not exist", "not exist"]),
    ))
    tests.append(TestCase(
        "7.2", "Status Validation",
        'How many parts have status "No stock"?',
        "64",
        check_number(64),
    ))
    tests.append(TestCase(
        "7.3", "Status Validation",
        'Show parts with status "Component Request - Please review Logid"',
        "39 rows including 19-2656-05LF and 19-1690-02LF",
        check_contains_any(["19-2656-05lf", "19-1690-02lf", "39", "component request"]),
    ))

    # ── 9. Schema / Metadata Queries ─────────────────────────────
    tests.append(TestCase(
        "9.1", "Schema/Metadata",
        "What tables are available?",
        "operations.Obsolescence_Results, operations.CRmaster_ModelResults",
        check_tables_listed(["Obsolescence_Results", "CRmaster_ModelResults"]),
    ))
    tests.append(TestCase(
        "9.2", "Schema/Metadata",
        "What columns does CRmaster_ModelResults have?",
        "pklogid, Comments, NewPNAssigned, Replacement_intent, ...",
        check_columns_listed([
            "pklogid", "Comments", "NewPNAssigned", "Replacement_intent",
            "Confidence", "PartNumber", "Old_Part", "New_Part",
        ]),
    ))

    # ── 10. Multi-Part Query ─────────────────────────────────────
    tests.append(TestCase(
        "10.1", "Multi-Part",
        "Tell me about 19-1690-02LF and 28-457-17LF",
        "Data for BOTH parts",
        check_contains_all(["19-1690-02lf", "28-457-17lf"]),
    ))

    # ── 11. Tricky / Ambiguous ───────────────────────────────────
    tests.append(TestCase(
        "11.2", "Tricky/Ambiguous",
        "Which parts have confidence above 0.90?",
        "Multiple parts with confidence > 0.90",
        check_confidence_list([
            "19-1690-02LF", "19-2990-02LF", "19-3082-01LF",
            "28-457-17LF", "DM-821-63LF", "DM-367-41LF", "DM-714-53LF",
        ]),
    ))

    # ── 12. Non-PartNumber Lookups ───────────────────────────────
    tests.append(TestCase(
        "12.1", "Non-PN Lookup",
        "Show me the row with pklogid 50112",
        "DM-605-91LF, Confidence: 0.89",
        check_contains_all(["dm-605-91lf"]),
    ))
    tests.append(TestCase(
        "12.2", "Non-PN Lookup",
        "Show me the row with pklogid 50106",
        "19-3082-01LF, Confidence: 0.97",
        check_contains_all(["19-3082-01lf"]),
    ))
    tests.append(TestCase(
        "12.3", "Non-PN Lookup",
        "What is the PartNumber for pklogid 50101?",
        "19-1690-02LF",
        check_contains_all(["19-1690-02lf"]),
    ))

    # ── 13. One-to-Many Relationship Queries ─────────────────────
    tests.append(TestCase(
        "13.1", "One-to-Many",
        "How many CRmaster entries does 19-1690-02LF have?",
        "3",
        check_number(3),
    ))
    tests.append(TestCase(
        "13.2", "One-to-Many",
        "Show all model results for 19-1690-02LF",
        "3 rows: 50101, 50201, 50202",
        check_contains_all(["50101", "50201", "50202"]),
    ))
    tests.append(TestCase(
        "13.3", "One-to-Many",
        "What is the highest confidence score for 19-1690-02LF?",
        "0.95",
        check_exact_value("0.95"),
    ))
    tests.append(TestCase(
        "13.4", "One-to-Many",
        "What is the latest model result for 19-3082-01LF?",
        "pklogid 50106, 2026-04-18, Confidence 0.97, DM-287-38LF",
        check_contains_all(["dm-287-38lf"]),
    ))
    tests.append(TestCase(
        "13.5", "One-to-Many",
        "Has the replacement recommendation changed for 19-3082-01LF?",
        "Yes — earlier DM-287-30LF, latest DM-287-38LF",
        check_contains_all(["dm-287-30lf", "dm-287-38lf"]),
    ))
    tests.append(TestCase(
        "13.6", "One-to-Many",
        "What is the average confidence for 28-457-17LF?",
        "0.82",
        check_exact_value("0.82"),
    ))
    tests.append(TestCase(
        "13.7", "One-to-Many",
        "How many model runs recommended a replacement for 19-1690-02LF?",
        "2",
        check_contains_any(["2", "two"]),
    ))
    tests.append(TestCase(
        "13.8", "One-to-Many",
        "Show all parts that have more than one CRmaster entry",
        "19-1690-02LF (3), 19-3082-01LF (2), 28-457-17LF (2)",
        check_contains_all(["19-1690-02lf", "19-3082-01lf", "28-457-17lf"]),
    ))

    return tests


# ─────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────

async def run_benchmark(section_filter: Optional[str] = None):
    logger.info("Initializing agent...")
    settings = Settings()
    loader = DataLoader(settings)
    kernel = AgentKernel(settings, loader)

    tests = build_tests()
    if section_filter:
        tests = [t for t in tests if t.id.startswith(section_filter + ".") or t.section.lower() == section_filter.lower()]
    results: list[TestResult] = []
    total_start = time.time()

    logger.info("Running %d test cases...\n", len(tests))

    for tc in tests:
        conv_id = f"bench-{tc.id}-{int(time.time())}"
        logger.info("[%s] %s", tc.id, tc.query)

        t0 = time.time()
        try:
            response = await kernel.ask(conv_id, tc.query)
            # Combine text + data_chunks for full evaluation
            full_response = response["text"]
            if response.get("data_chunks"):
                full_response += "\n" + "\n".join(response["data_chunks"])
        except Exception as e:
            full_response = f"[ERROR] {e}"
        elapsed = time.time() - t0

        # Run the checker
        result = tc.check(full_response, tc.expected)
        result.test_id = tc.id
        result.section = tc.section
        result.query = tc.query
        result.expected = tc.expected
        result.actual = full_response
        result.elapsed = elapsed
        results.append(result)

        status = "PASS" if result.passed else "FAIL"
        logger.info("  [%s] (%.1fs) %s", status, elapsed, result.notes or "")

    total_elapsed = time.time() - total_start

    # ── Summary ──────────────────────────────────────────────────
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    avg_time = sum(r.elapsed for r in results) / len(results) if results else 0

    print("\n" + "=" * 70)
    print(f"  TEST BANK RESULTS — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  {passed}/{len(results)} PASS | {failed} FAIL | Avg {avg_time:.1f}s | Total {total_elapsed:.0f}s")
    print("=" * 70)

    # Group by section
    sections: dict[str, list[TestResult]] = {}
    for r in results:
        sections.setdefault(r.section, []).append(r)

    for section, section_results in sections.items():
        sec_pass = sum(1 for r in section_results if r.passed)
        print(f"\n## {section} ({sec_pass}/{len(section_results)})")
        for r in section_results:
            status = "PASS" if r.passed else "FAIL"
            flag = "  " if r.passed else ">>"
            line = f"  {flag} [{r.test_id}] {status} ({r.elapsed:.1f}s) — {r.query[:60]}"
            if not r.passed:
                line += f"\n       Expected: {r.expected[:80]}"
                line += f"\n       Got: {r.actual[:120]}"
                if r.notes:
                    line += f"\n       Notes: {r.notes}"
            print(line)

    # ── Write markdown report ────────────────────────────────────
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report_path = os.path.join(OUTPUT_DIR, "test_bank_results.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Test Bank Benchmark Results\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"**Summary:** {passed}/{len(results)} PASS | {failed} FAIL | Avg {avg_time:.1f}s | Total {total_elapsed:.0f}s\n\n")

        f.write("| # | Section | Query | Expected | Verdict | Time | Notes |\n")
        f.write("|---|---------|-------|----------|---------|------|-------|\n")
        for r in results:
            status = "PASS" if r.passed else "**FAIL**"
            q = r.query[:50].replace("|", "\\|")
            e = r.expected[:40].replace("|", "\\|")
            n = r.notes[:50].replace("|", "\\|") if r.notes else ""
            f.write(f"| {r.test_id} | {r.section} | {q} | {e} | {status} | {r.elapsed:.1f}s | {n} |\n")

        # Failure details
        failures = [r for r in results if not r.passed]
        if failures:
            f.write(f"\n## Failure Details\n\n")
            for r in failures:
                f.write(f"### {r.test_id}: {r.query}\n\n")
                f.write(f"**Expected:** {r.expected}\n\n")
                f.write(f"**Actual response:**\n```\n{r.actual[:500]}\n```\n\n")
                if r.notes:
                    f.write(f"**Notes:** {r.notes}\n\n")

    # ── Write Excel report ───────────────────────────────────────
    try:
        import pandas as pd
        xlsx_path = os.path.join(OUTPUT_DIR, "test_bank_results.xlsx")
        rows_data = []
        for r in results:
            rows_data.append({
                "Test ID": r.test_id,
                "Section": r.section,
                "Query": r.query,
                "Expected": r.expected,
                "Actual": r.actual[:500],
                "Verdict": "PASS" if r.passed else "FAIL",
                "Time (s)": round(r.elapsed, 1),
                "Notes": r.notes or "",
            })
        df_out = pd.DataFrame(rows_data)
        df_out.to_excel(xlsx_path, index=False, sheet_name="Results")
        logger.info("Excel written to %s", xlsx_path)
    except Exception as e:
        logger.warning("Could not write Excel: %s", e)

    logger.info("\nReport written to %s", report_path)
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", "-s", help="Run only tests from this section (e.g. '13' or 'One-to-Many')")
    args = parser.parse_args()
    asyncio.run(run_benchmark(section_filter=args.section))
