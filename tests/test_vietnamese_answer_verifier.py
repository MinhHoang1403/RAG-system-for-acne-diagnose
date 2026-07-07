from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.quality.answer_verifier import verify_answer_quality
from src.quality.proposition_detector import extract_domain_propositions, proposition_exists
from src.quality.vietnamese_text import build_matching_views, strip_vietnamese_diacritics

GOLDEN_PATH = Path(__file__).parent / "golden" / "vietnamese_answer_verifier_cases.json"


def _load_cases() -> list[dict]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _load_cases(), ids=lambda case: case["id"])
def test_vietnamese_answer_verifier_golden_cases(case: dict):
    report = verify_answer_quality(query=case["query"], answer=case["answer"])
    issue_codes = [issue.code for issue in report.issues]
    critical_count = sum(1 for issue in report.issues if issue.severity == "critical")

    assert report.passed is bool(case["expect_passed"])
    if case.get("expect_critical"):
        assert critical_count > 0
    for expected_code in case.get("expected_issue_codes", []):
        assert expected_code in issue_codes
    for absent_code in case.get("expected_absent_issue_codes", []):
        assert absent_code not in issue_codes
    for expected_fact in case.get("expected_detected_facts", []):
        assert expected_fact in report.detected_facts


def test_normalization_builds_accent_preserving_and_accentless_views():
    accent, accentless = build_matching_views("**BPO** — không phải là `kháng sinh`.\u200b")

    assert accent == "bpo - không phải là kháng sinh."
    assert accentless == "bpo - khong phai la khang sinh."
    assert strip_vietnamese_diacritics("điều trị Đỏ") == "dieu tri Do"


def test_negative_matcher_is_not_overridden_by_positive_phrase():
    props = extract_domain_propositions(
        "Benzoyl peroxide không phải là kháng sinh.",
        query_context="Benzoyl peroxide có phải kháng sinh không?",
    )

    assert proposition_exists(props, subject="benzoyl_peroxide", relation="is_not_a", object_="antibiotic")
    assert not proposition_exists(props, subject="benzoyl_peroxide", relation="is_a", object_="antibiotic")


def test_not_only_is_treated_as_positive_membership():
    props = extract_domain_propositions(
        "BPO không chỉ là kháng sinh mà còn là thuốc trị mụn.",
        query_context="Benzoyl peroxide có phải kháng sinh không?",
    )

    assert proposition_exists(props, subject="benzoyl_peroxide", relation="is_a", object_="antibiotic")


def test_subjectless_answer_uses_clear_query_context_only():
    bp_props = extract_domain_propositions(
        "Không phải kháng sinh.",
        query_context="Benzoyl peroxide có phải kháng sinh không?",
    )
    ambiguous_props = extract_domain_propositions(
        "Không phải kháng sinh.",
        query_context="BPO và clindamycin khác nhau thế nào?",
    )

    assert proposition_exists(bp_props, subject="benzoyl_peroxide", relation="is_not_a", object_="antibiotic")
    assert not proposition_exists(ambiguous_props, subject="benzoyl_peroxide", relation="is_not_a", object_="antibiotic")


def test_multi_entity_relations_stay_attached_to_their_subjects():
    props = extract_domain_propositions(
        "BPO không phải kháng sinh, còn clindamycin là kháng sinh bôi.",
        query_context="Benzoyl peroxide có phải kháng sinh không?",
    )

    assert proposition_exists(props, subject="benzoyl_peroxide", relation="is_not_a", object_="antibiotic")
    assert proposition_exists(props, subject="clindamycin", relation="is_a", object_="topical_antibiotic")
    assert not proposition_exists(props, subject="benzoyl_peroxide", relation="is_a", object_="antibiotic")
    assert not proposition_exists(props, subject="clindamycin", relation="is_not_a", object_="antibiotic")


def test_double_negation_and_quoted_claim_do_not_create_false_assertions():
    double_negation = extract_domain_propositions(
        "Không thể khẳng định adapalene không phải kháng sinh.",
        query_context="Adapalene có phải kháng sinh không?",
    )
    quoted = extract_domain_propositions(
        "Một số người nói \"BPO là kháng sinh\", nhưng điều đó không đúng.",
        query_context="Benzoyl peroxide có phải kháng sinh không?",
    )

    assert not proposition_exists(double_negation, subject="adapalene", relation="is_not_a", object_="antibiotic")
    assert not proposition_exists(quoted, subject="benzoyl_peroxide", relation="is_a", object_="antibiotic")
