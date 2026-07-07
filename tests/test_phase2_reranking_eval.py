from scripts.eval_phase2_reranking import run_phase2_reranking_eval


def test_phase2_reranking_eval_passes_offline():
    summary = run_phase2_reranking_eval()

    assert summary["readiness"] == "PASS"
    assert summary["total_cases"] == 8
    assert summary["failed"] == 0
    assert summary["failures"] == []
    assert summary["metrics"]["relevant_candidate_at_5"]["passed"] == 8
