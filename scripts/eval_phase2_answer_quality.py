#!/usr/bin/env python3
"""Offline Phase 2D answer quality eval."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.quality.answer_verifier import verify_answer_quality  # noqa: E402

DEFAULT_GOLDEN_PATH = PROJECT_ROOT / "tests" / "golden" / "phase2_answer_quality_cases.json"
VIETNAMESE_GOLDEN_PATH = PROJECT_ROOT / "tests" / "golden" / "vietnamese_answer_verifier_cases.json"


def load_cases(paths: list[Path] | None = None) -> list[dict[str, Any]]:
    paths = paths or [DEFAULT_GOLDEN_PATH, VIETNAMESE_GOLDEN_PATH]
    cases: list[dict[str, Any]] = []
    for path in paths:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        for case in loaded:
            case = dict(case)
            case.setdefault("category", path.stem)
            case["source_file"] = str(path.relative_to(PROJECT_ROOT))
            cases.append(case)
    return cases


def run_phase2_answer_quality_eval(path: Path | None = None) -> dict[str, Any]:
    cases = load_cases([path] if path else None)
    failures: list[str] = []
    reports: list[dict[str, Any]] = []
    critical_count = 0
    false_positive_count = 0
    false_negative_count = 0
    category_metrics: dict[str, dict[str, int]] = {}

    for case in cases:
        report = verify_answer_quality(query=str(case["query"]), answer=str(case["answer"]))
        issue_codes = [issue.code for issue in report.issues]
        critical_issues = [issue for issue in report.issues if issue.severity == "critical"]
        critical_count += len(critical_issues)
        case_failures: list[str] = []
        category = str(case.get("category") or "uncategorized")
        expected_passed = bool(case["expect_passed"])
        metrics = category_metrics.setdefault(category, {"total": 0, "passed": 0, "failed": 0})
        metrics["total"] += 1

        if report.passed is not expected_passed:
            case_failures.append(
                f"{case['id']}: category={category}, passed={report.passed}, expected={case['expect_passed']}"
            )
            if expected_passed and not report.passed:
                false_positive_count += 1
            elif not expected_passed and report.passed:
                false_negative_count += 1
        if case.get("expect_critical") and not critical_issues:
            case_failures.append(f"{case['id']}: category={category}, expected critical issue")
        for expected_code in case.get("expected_issue_codes", []):
            if expected_code not in issue_codes:
                case_failures.append(f"{case['id']}: category={category}, missing issue code {expected_code}")
        for absent_code in case.get("expected_absent_issue_codes", []):
            if absent_code in issue_codes:
                case_failures.append(f"{case['id']}: category={category}, unexpected issue code {absent_code}")
        for expected_fact in case.get("expected_detected_facts", []):
            if expected_fact not in report.detected_facts:
                case_failures.append(f"{case['id']}: category={category}, missing detected fact {expected_fact}")

        failures.extend(case_failures)
        metrics["passed" if not case_failures else "failed"] += 1
        reports.append(
            {
                "id": case["id"],
                "category": category,
                "passed": not case_failures,
                "report_passed": report.passed,
                "expected_passed": expected_passed,
                "intent": report.intent,
                "issue_codes": issue_codes,
                "critical_count": len(critical_issues),
                "missing_facts": report.missing_facts,
                "contradictions": report.contradictions,
                "failures": case_failures,
            }
        )

    passed = sum(1 for report in reports if report["passed"])
    failed = len(cases) - passed
    return {
        "passed": not failures,
        "readiness": "PASS" if not failures else "FAIL",
        "total_cases": len(cases),
        "passed_cases": passed,
        "failed_cases": failed,
        "failed": failed,
        "false_positive_count": false_positive_count,
        "false_negative_count": false_negative_count,
        "critical_detection_count": critical_count,
        "critical_issues_count": critical_count,
        "category_metrics": category_metrics,
        "failures": failures,
        "cases": reports,
    }


def main() -> int:
    summary = run_phase2_answer_quality_eval()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
