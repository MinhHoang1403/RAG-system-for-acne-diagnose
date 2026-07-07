from __future__ import annotations

from scripts.eval_phase2_answer_quality import run_phase2_answer_quality_eval


def test_phase2_answer_quality_eval_passes_golden_cases():
    summary = run_phase2_answer_quality_eval()

    assert summary["readiness"] == "PASS"
    assert summary["failed"] == 0
    assert summary["total_cases"] >= 8
    assert summary["critical_issues_count"] >= 4
