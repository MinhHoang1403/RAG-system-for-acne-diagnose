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


def load_cases(path: Path = DEFAULT_GOLDEN_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_phase2_answer_quality_eval(path: Path = DEFAULT_GOLDEN_PATH) -> dict[str, Any]:
    cases = load_cases(path)
    failures: list[str] = []
    reports: list[dict[str, Any]] = []
    critical_count = 0

    for case in cases:
        report = verify_answer_quality(query=str(case["query"]), answer=str(case["answer"]))
        issue_codes = [issue.code for issue in report.issues]
        critical_issues = [issue for issue in report.issues if issue.severity == "critical"]
        critical_count += len(critical_issues)
        case_failures: list[str] = []

        if report.passed is not bool(case["expect_passed"]):
            case_failures.append(
                f"{case['id']}: passed={report.passed}, expected={case['expect_passed']}"
            )
        if case.get("expect_critical") and not critical_issues:
            case_failures.append(f"{case['id']}: expected critical issue")
        for expected_code in case.get("expected_issue_codes", []):
            if expected_code not in issue_codes:
                case_failures.append(f"{case['id']}: missing issue code {expected_code}")

        failures.extend(case_failures)
        reports.append(
            {
                "id": case["id"],
                "passed": not case_failures,
                "report_passed": report.passed,
                "intent": report.intent,
                "issue_codes": issue_codes,
                "critical_count": len(critical_issues),
                "missing_facts": report.missing_facts,
                "contradictions": report.contradictions,
                "failures": case_failures,
            }
        )

    passed = sum(1 for report in reports if report["passed"])
    return {
        "readiness": "PASS" if not failures else "FAIL",
        "total_cases": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "critical_issues_count": critical_count,
        "failures": failures,
        "cases": reports,
    }


def main() -> int:
    summary = run_phase2_answer_quality_eval()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["readiness"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
