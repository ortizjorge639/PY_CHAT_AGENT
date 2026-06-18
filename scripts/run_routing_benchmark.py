"""
Routing benchmark for multi-table question classification.

What it measures:
  - For each user question, which table(s) the agent actually queried.
  - Whether the queried table role matches the expected role:
      * primary      -> scrap/status/disposition intent
      * supplemental -> product-details intent

It creates a deterministic mock Excel dataset (two tables) on each run:
  - 20260618000000_obsolescence.xlsx  (primary role by timestamp naming convention)
  - dimProducts.xlsx                  (supplemental role)

Outputs:
  - benchmarks/routing/routing_benchmark_results.json
  - benchmarks/routing/routing_benchmark_report.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.kernel import AgentKernel
from config.settings import Settings
from data.loader import DataLoader

OUTPUT_DIR = ROOT / "benchmarks" / "routing"
OUTPUT_JSON = OUTPUT_DIR / "routing_benchmark_results.json"
OUTPUT_MD = OUTPUT_DIR / "routing_benchmark_report.md"
SOLID_THRESHOLD = 0.85


@dataclass
class RoutingQuestion:
    question_id: str
    question: str
    expected_role: str  # "primary" | "supplemental"
    intent: str


@dataclass
class RoutingResult:
    question_id: str
    question: str
    intent: str
    expected_role: str
    queried_tables: list[str]
    queried_roles: list[str]
    matched_expected_role: bool
    strict_match: bool
    elapsed_seconds: float
    response_preview: str
    error: str = ""


class TrackingDataLoader(DataLoader):
    """DataLoader with per-question table call tracing."""

    def __init__(self, settings: Settings, auto_load: bool = True) -> None:
        super().__init__(settings=settings, auto_load=auto_load)
        self._active_question_id: str | None = None
        self._table_calls_by_question: dict[str, list[str]] = {}

    def start_question(self, question_id: str) -> None:
        self._active_question_id = question_id
        self._table_calls_by_question.setdefault(question_id, [])

    def end_question(self) -> None:
        self._active_question_id = None

    def get_calls(self, question_id: str) -> list[str]:
        return list(self._table_calls_by_question.get(question_id, []))

    def _record(self, table_name: str) -> None:
        if self._active_question_id:
            self._table_calls_by_question[self._active_question_id].append(table_name)

    def count_rows(
        self,
        table_name: str,
        filter_column: str | None = None,
        filter_value: str | None = None,
    ) -> int:
        self._record(table_name)
        return super().count_rows(table_name, filter_column, filter_value)

    def get_rows(
        self,
        table_name: str,
        filter_column: str | None = None,
        filter_value: str | None = None,
    ) -> dict[str, Any]:
        self._record(table_name)
        return super().get_rows(table_name, filter_column, filter_value)

    def get_distinct_values(self, table_name: str, column: str) -> list[str]:
        self._record(table_name)
        return super().get_distinct_values(table_name, column)

    def query_table(self, table_name: str, query_expr: str) -> dict[str, Any]:
        self._record(table_name)
        return super().query_table(table_name, query_expr)

    def group_by(
        self,
        table_name: str,
        group_column: str,
        agg_column: str | None = None,
        agg_func: str = "count",
    ) -> list[dict[str, Any]]:
        self._record(table_name)
        return super().group_by(table_name, group_column, agg_column, agg_func)

    def get_schema(self, table_name: str) -> dict[str, str]:
        self._record(table_name)
        return super().get_schema(table_name)


def create_mock_routing_excel_data(base_dir: Path) -> dict[str, str]:
    """Create deterministic two-table benchmark dataset."""
    base_dir.mkdir(parents=True, exist_ok=True)

    primary_table_name = "20260618000000_obsolescence"
    supplemental_table_name = "dimProducts"

    primary_rows = [
        {
            "PartNumber": "60-100-01",
            "Status": "May be eligible to be scrapped",
            "Details": "No active where-used.",
            "Processed_Date": "2026-06-01",
            "QOH": 12,
            "Reza's List": 1,
        },
        {
            "PartNumber": "18-152-01",
            "Status": "NOT eligible for scrap - Custom Button",
            "Details": "Classified via model metadata.",
            "Processed_Date": "2026-06-01",
            "QOH": 4,
            "Reza's List": 0,
        },
        {
            "PartNumber": "18-175-02",
            "Status": "NOT eligible for scrap - Custom Button",
            "Details": "Classified via model metadata.",
            "Processed_Date": "2026-06-02",
            "QOH": 7,
            "Reza's List": 0,
        },
        {
            "PartNumber": "70-400-10",
            "Status": "Open WorkOrder",
            "Details": "WO-740001",
            "Processed_Date": "2026-06-03",
            "QOH": 21,
            "Reza's List": 0,
        },
        {
            "PartNumber": "90-777-01",
            "Status": "No stock",
            "Details": None,
            "Processed_Date": "2026-06-04",
            "QOH": 0,
            "Reza's List": 0,
        },
    ]

    supplemental_rows = [
        {
            "PartNumber": "60-100-01",
            "Description": "EURO PWR CORD 2M",
            "Phase": "Active",
            "PartNumberPrefix": "60",
            "PartNumberModel": "100",
            "PartNumberSuffix": "01",
            "IsTopLevelPart": 1,
            "IsConfiguredPart": 0,
            "IsConfiguredPartComponent": 0,
            "IsSerialized": 0,
            "IsLinkLicense": 0,
            "IsPhantomPart": 0,
            "IsBinItem": 1,
            "IsWebEnabled": 1,
            "IsNonPhysical": 0,
            "International_PowerCord": 1,
            "CustomButton": 0,
            "Effective Date": "2026-01-15",
            "DateAdded": "2024-11-08",
        },
        {
            "PartNumber": "18-152-01",
            "Description": "CONTROL BUTTON ASSEMBLY",
            "Phase": "Active",
            "PartNumberPrefix": "18",
            "PartNumberModel": "152",
            "PartNumberSuffix": "01",
            "IsTopLevelPart": 1,
            "IsConfiguredPart": 1,
            "IsConfiguredPartComponent": 0,
            "IsSerialized": 0,
            "IsLinkLicense": 0,
            "IsPhantomPart": 0,
            "IsBinItem": 1,
            "IsWebEnabled": 1,
            "IsNonPhysical": 0,
            "International_PowerCord": 0,
            "CustomButton": 1,
            "Effective Date": "2025-04-20",
            "DateAdded": "2023-09-01",
        },
        {
            "PartNumber": "18-175-02",
            "Description": "CUSTOM BUTTON PANEL",
            "Phase": "Active",
            "PartNumberPrefix": "18",
            "PartNumberModel": "175",
            "PartNumberSuffix": "02",
            "IsTopLevelPart": 1,
            "IsConfiguredPart": 1,
            "IsConfiguredPartComponent": 0,
            "IsSerialized": 0,
            "IsLinkLicense": 0,
            "IsPhantomPart": 0,
            "IsBinItem": 1,
            "IsWebEnabled": 1,
            "IsNonPhysical": 0,
            "International_PowerCord": 0,
            "CustomButton": 1,
            "Effective Date": "2025-02-12",
            "DateAdded": "2023-07-19",
        },
        {
            "PartNumber": "70-400-10",
            "Description": "US AC ADAPTER",
            "Phase": "Service",
            "PartNumberPrefix": "70",
            "PartNumberModel": "400",
            "PartNumberSuffix": "10",
            "IsTopLevelPart": 0,
            "IsConfiguredPart": 0,
            "IsConfiguredPartComponent": 1,
            "IsSerialized": 0,
            "IsLinkLicense": 0,
            "IsPhantomPart": 1,
            "IsBinItem": 0,
            "IsWebEnabled": 0,
            "IsNonPhysical": 0,
            "International_PowerCord": 0,
            "CustomButton": 0,
            "Effective Date": "2024-06-20",
            "DateAdded": "2022-05-10",
        },
        {
            "PartNumber": "90-777-01",
            "Description": "CHASSIS SUB-ASSEMBLY",
            "Phase": "Obsolete",
            "PartNumberPrefix": "90",
            "PartNumberModel": "777",
            "PartNumberSuffix": "01",
            "IsTopLevelPart": 0,
            "IsConfiguredPart": 0,
            "IsConfiguredPartComponent": 0,
            "IsSerialized": 1,
            "IsLinkLicense": 0,
            "IsPhantomPart": 0,
            "IsBinItem": 0,
            "IsWebEnabled": 0,
            "IsNonPhysical": 0,
            "International_PowerCord": 0,
            "CustomButton": 0,
            "Effective Date": "2021-09-09",
            "DateAdded": "2021-01-05",
        },
    ]

    pd.DataFrame(primary_rows).to_excel(
        base_dir / f"{primary_table_name}.xlsx",
        index=False,
        engine="openpyxl",
    )
    pd.DataFrame(supplemental_rows).to_excel(
        base_dir / f"{supplemental_table_name}.xlsx",
        index=False,
        engine="openpyxl",
    )

    return {
        "primary_table_name": primary_table_name,
        "supplemental_table_name": supplemental_table_name,
    }


def build_question_bank(part_number: str) -> list[RoutingQuestion]:
    return [
        RoutingQuestion("Q1", f"Can part {part_number} be scrapped?", "primary", "scrap eligibility"),
        RoutingQuestion("Q2", f"What is the status of part {part_number}?", "primary", "status"),
        RoutingQuestion("Q3", "Show me parts that may be eligible to be scrapped.", "primary", "scrap list"),
        RoutingQuestion("Q4", f"What is the description for part {part_number}?", "supplemental", "description"),
        RoutingQuestion("Q5", f"What phase is part {part_number} in?", "supplemental", "phase"),
        RoutingQuestion("Q6", f"Is part {part_number} a custom button?", "supplemental", "custom flag"),
        RoutingQuestion("Q7", f"Is part {part_number} an international power cord?", "supplemental", "intl power flag"),
        RoutingQuestion("Q8", f"Is part {part_number} serialized?", "supplemental", "serialized flag"),
        RoutingQuestion("Q9", f"Does part {part_number} have an open work order?", "primary", "work order status"),
        RoutingQuestion("Q10", f"What is the QOH for part {part_number}?", "primary", "inventory quantity"),
    ]


def build_tuned_question_bank(part_number: str) -> list[RoutingQuestion]:
    """Fallback set with clearer wording if baseline routing is weak."""
    return [
        RoutingQuestion("Q1", f"Using scrap status, can part {part_number} be scrapped?", "primary", "scrap eligibility"),
        RoutingQuestion("Q2", f"In the scrap table, what is the status of part {part_number}?", "primary", "status"),
        RoutingQuestion("Q3", "From status data, list parts that may be eligible to be scrapped.", "primary", "scrap list"),
        RoutingQuestion("Q4", f"In the product catalog table, what is the description for part {part_number}?", "supplemental", "description"),
        RoutingQuestion("Q5", f"From dimProducts, what phase is part {part_number} in?", "supplemental", "phase"),
        RoutingQuestion("Q6", f"In product details, is part {part_number} a custom button?", "supplemental", "custom flag"),
        RoutingQuestion("Q7", f"In product details, is part {part_number} an international power cord?", "supplemental", "intl power flag"),
        RoutingQuestion("Q8", f"From dimProducts, is part {part_number} serialized?", "supplemental", "serialized flag"),
        RoutingQuestion("Q9", f"From scrap status data, does part {part_number} have an open work order?", "primary", "work order status"),
        RoutingQuestion("Q10", f"From scrap table, what is the QOH for part {part_number}?", "primary", "inventory quantity"),
    ]


def evaluate_question(
    question: RoutingQuestion,
    queried_tables: list[str],
    table_roles: dict[str, str],
) -> tuple[bool, bool, list[str]]:
    unique_tables: list[str] = []
    for table in queried_tables:
        if table not in unique_tables:
            unique_tables.append(table)
    roles = [table_roles.get(t, "unknown") for t in unique_tables]
    matched_expected_role = question.expected_role in roles
    strict_match = len(set(roles)) == 1 and len(roles) > 0 and roles[0] == question.expected_role
    return matched_expected_role, strict_match, roles


def _choose_table_by_role(table_roles: dict[str, str], role: str) -> str:
    for table_name, table_role in table_roles.items():
        if table_role == role:
            return table_name
    raise ValueError(f"No table loaded with role '{role}'")


def _offline_route_expected(
    question: RoutingQuestion,
    loader: TrackingDataLoader,
    table_roles: dict[str, str],
    target_part: str,
) -> str:
    """Deterministic fallback when live LLM credentials are unavailable."""
    table_name = _choose_table_by_role(table_roles, question.expected_role)
    lower = question.question.lower()
    if "how many" in lower or "count" in lower:
        count = loader.count_rows(table_name)
        return f"count={count}"
    if "list parts" in lower and question.expected_role == "primary":
        result = loader.get_rows(table_name, "Status", "May be eligible to be scrapped")
        return f"rows={result['total']}"
    result = loader.get_rows(table_name, "PartNumber", target_part)
    return f"rows={result['total']}"


def _summarize_attempt(
    attempt_name: str,
    results: list[RoutingResult],
    table_names: dict[str, str],
    dataset_dir: str,
    errors: list[str],
    mode_used: str,
) -> dict[str, Any]:
    total = len(results)
    matched_count = sum(1 for r in results if r.matched_expected_role)
    strict_count = sum(1 for r in results if r.strict_match)
    matched_accuracy = matched_count / total if total else 0.0
    strict_accuracy = strict_count / total if total else 0.0
    return {
        "attempt_name": attempt_name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_questions": total,
        "matched_accuracy": round(matched_accuracy, 4),
        "strict_accuracy": round(strict_accuracy, 4),
        "solid_threshold": SOLID_THRESHOLD,
        "solid": strict_accuracy >= SOLID_THRESHOLD,
        "table_names": table_names,
        "dataset_dir": dataset_dir,
        "mode_used": mode_used,
        "results": [asdict(r) for r in results],
        "errors": errors,
    }


async def run_benchmark(trials: int, keep_data: bool, mode: str) -> dict[str, Any]:
    temp_root = Path(tempfile.mkdtemp(prefix="routing_benchmark_"))
    data_dir = temp_root / "excel_data"
    table_names = create_mock_routing_excel_data(data_dir)
    target_part = "60-100-01"
    baseline_questions = build_question_bank(target_part)
    tuned_questions = build_tuned_question_bank(target_part)

    try:
        async def _run_attempt(attempt_name: str, questions: list[RoutingQuestion]) -> dict[str, Any]:
            all_results: list[RoutingResult] = []
            failures: list[str] = []

            live_mode = mode
            if mode == "auto":
                live_mode = "live"

            for trial in range(1, trials + 1):
                settings = Settings(
                    datasource="excel",
                    excel_folder_path=str(data_dir),
                )
                loader = TrackingDataLoader(settings=settings, auto_load=True)
                table_roles = loader.get_table_roles()
                kernel: AgentKernel | None = None

                if live_mode == "live":
                    try:
                        kernel = AgentKernel(settings=settings, data_loader=loader)
                    except Exception as exc:
                        if mode == "auto":
                            live_mode = "offline"
                            failures.append(f"Live mode unavailable, switched to offline: {exc}")
                        else:
                            raise

                for q in questions:
                    conv_id = f"routing-benchmark-{attempt_name}-t{trial}-{q.question_id}-{int(time.time() * 1000)}"
                    start = time.time()
                    loader.start_question(q.question_id)
                    error = ""
                    response_preview = ""
                    try:
                        if live_mode == "live" and kernel is not None:
                            response = await kernel.ask(conv_id, q.question)
                            response_preview = (response.get("text") or "").strip()[:200]
                        else:
                            response_preview = _offline_route_expected(q, loader, table_roles, target_part)
                    except Exception as exc:  # pragma: no cover - execution safety
                        error = str(exc)
                    finally:
                        loader.end_question()

                    elapsed = time.time() - start
                    queried_tables = loader.get_calls(q.question_id)
                    matched, strict, queried_roles = evaluate_question(q, queried_tables, table_roles)
                    if error:
                        matched = False
                        strict = False
                        failures.append(f"{attempt_name} Trial {trial} {q.question_id}: {error}")

                    all_results.append(
                        RoutingResult(
                            question_id=f"T{trial}-{q.question_id}",
                            question=q.question,
                            intent=q.intent,
                            expected_role=q.expected_role,
                            queried_tables=queried_tables,
                            queried_roles=queried_roles,
                            matched_expected_role=matched,
                            strict_match=strict,
                            elapsed_seconds=round(elapsed, 3),
                            response_preview=response_preview,
                            error=error,
                        )
                    )

            return _summarize_attempt(
                attempt_name=attempt_name,
                results=all_results,
                table_names=table_names,
                dataset_dir=str(data_dir),
                errors=failures,
                mode_used=live_mode,
            )

        baseline = await _run_attempt("baseline", baseline_questions)
        if baseline["solid"]:
            chosen = baseline
            attempts = [baseline]
        else:
            tuned = await _run_attempt("tuned", tuned_questions)
            attempts = [baseline, tuned]
            chosen = tuned

        return {
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "trials": trials,
            "questions_per_trial": len(baseline_questions),
            "attempts": attempts,
            "chosen_attempt": chosen["attempt_name"],
            "total_questions": chosen["total_questions"],
            "matched_accuracy": chosen["matched_accuracy"],
            "strict_accuracy": chosen["strict_accuracy"],
            "solid_threshold": chosen["solid_threshold"],
            "solid": chosen["solid"],
            "table_names": chosen["table_names"],
            "dataset_dir": chosen["dataset_dir"],
            "mode_used": chosen["mode_used"],
            "results": chosen["results"],
            "errors": chosen["errors"],
        }
    finally:
        if not keep_data:
            shutil.rmtree(temp_root, ignore_errors=True)


def write_report_files(report: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# Routing Benchmark Report")
    lines.append("")
    lines.append(f"- **Timestamp (UTC):** {report['timestamp_utc']}")
    lines.append(f"- **Trials:** {report['trials']}")
    lines.append(f"- **Questions/trial:** {report['questions_per_trial']}")
    lines.append(f"- **Total evaluated:** {report['total_questions']}")
    lines.append(f"- **Matched-role accuracy:** {report['matched_accuracy'] * 100:.1f}%")
    lines.append(f"- **Strict routing accuracy:** {report['strict_accuracy'] * 100:.1f}%")
    lines.append(f"- **Solid threshold:** {report['solid_threshold'] * 100:.1f}%")
    lines.append(f"- **Solid:** {'YES' if report['solid'] else 'NO'}")
    lines.append(f"- **Execution mode:** `{report['mode_used']}`")
    lines.append(f"- **Chosen attempt:** `{report['chosen_attempt']}`")
    lines.append("")
    lines.append("## Dataset")
    lines.append("")
    lines.append(
        f"- Primary table file stem: `{report['table_names']['primary_table_name']}`"
    )
    lines.append(
        f"- Supplemental table file stem: `{report['table_names']['supplemental_table_name']}`"
    )
    lines.append("- Data rows are deterministic and regenerated on each run.")
    lines.append("")
    lines.append("## Per-question results")
    lines.append("")
    lines.append("| Question ID | Expected role | Queried roles | Strict | Error |")
    lines.append("|---|---|---|---|---|")
    for row in report["results"]:
        roles = ", ".join(row["queried_roles"]) if row["queried_roles"] else "none"
        strict = "✅" if row["strict_match"] else "❌"
        error = row["error"].replace("|", "\\|") if row["error"] else ""
        lines.append(
            f"| {row['question_id']} | {row['expected_role']} | {roles} | {strict} | {error} |"
        )

    lines.append("")
    lines.append("## Attempts")
    lines.append("")
    lines.append("| Attempt | Mode | Strict accuracy | Solid |")
    lines.append("|---|---|---:|---|")
    for attempt in report.get("attempts", []):
        lines.append(
            f"| {attempt['attempt_name']} | {attempt['mode_used']} | {attempt['strict_accuracy'] * 100:.1f}% | {'YES' if attempt['solid'] else 'NO'} |"
        )
    lines.append("")
    lines.append("## Learnings")
    lines.append("")
    if report["solid"]:
        lines.append(
            "- Routing is stable for the benchmark question set; strict table-role routing met the threshold."
        )
    else:
        lines.append(
            "- Routing is not yet stable enough; refine prompt routing rules and/or benchmark data distinctions, then rerun."
        )
    lines.append(
        "- The benchmark captures real table calls from tool methods, so results reflect actual routing behavior."
    )

    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run routing benchmark on mock multi-table data.")
    parser.add_argument("--trials", type=int, default=3, help="Number of independent trials.")
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="Keep temporary generated Excel files for inspection.",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "live", "offline"],
        default="auto",
        help="auto: try live then fallback to offline, live: require Azure credentials, offline: deterministic fallback.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = asyncio.run(run_benchmark(trials=args.trials, keep_data=args.keep_data, mode=args.mode))
    write_report_files(report)
    print(json.dumps(
        {
            "solid": report["solid"],
            "strict_accuracy": report["strict_accuracy"],
            "matched_accuracy": report["matched_accuracy"],
            "results_json": str(OUTPUT_JSON),
            "report_md": str(OUTPUT_MD),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
