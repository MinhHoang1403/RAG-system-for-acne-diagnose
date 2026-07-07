from scripts.eval_phase2_context_packing import run_phase2_context_packing_eval


def test_phase2_context_packing_eval_passes_offline():
    summary = run_phase2_context_packing_eval()

    assert summary["readiness"] == "PASS"
    assert summary["total_cases"] == 6
    assert summary["failed"] == 0
    assert summary["failures"] == []
