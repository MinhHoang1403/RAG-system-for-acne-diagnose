from scripts.eval_phase2_retrieval import DEFAULT_GOLDEN_PATH, load_cases, run_phase2_retrieval_eval


def test_phase2_retrieval_golden_set_has_required_cases():
    cases = load_cases(DEFAULT_GOLDEN_PATH)
    ids = {case["id"] for case in cases}

    assert len(cases) == 8
    assert {
        "dalacin_t_identity",
        "epiduo_contains_bpo",
        "differin_class",
        "benzoyl_peroxide_not_antibiotic",
        "clindamycin_not_retinoid",
        "adapalene_not_antibiotic",
        "blackheads_acne_type",
        "inflammatory_acne_treatment",
    } == ids


def test_phase2_retrieval_eval_passes_offline():
    summary = run_phase2_retrieval_eval(DEFAULT_GOLDEN_PATH)

    assert summary["readiness"] == "PASS"
    assert summary["total_cases"] == 8
    assert summary["failed"] == 0
    assert summary["failures"] == []
