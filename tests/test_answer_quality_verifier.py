from __future__ import annotations

from src.quality.answer_verifier import apply_answer_guard, verify_answer_quality


def _codes(query: str, answer: str) -> tuple[bool, list[str]]:
    report = verify_answer_quality(query=query, answer=answer)
    return report.passed, [issue.code for issue in report.issues]


def test_bp_not_antibiotic_good_and_bad_answers():
    good_passed, good_codes = _codes(
        "Benzoyl peroxide có phải kháng sinh không?",
        "Không, benzoyl peroxide không phải kháng sinh. Đây là hoạt chất bôi có tác dụng kháng khuẩn.",
    )
    bad_passed, bad_codes = _codes(
        "Benzoyl peroxide có phải kháng sinh không?",
        "Benzoyl peroxide là kháng sinh dùng để trị mụn.",
    )

    assert good_passed is True
    assert "bp_antibiotic_contradiction" not in good_codes
    assert bad_passed is False
    assert "bp_antibiotic_contradiction" in bad_codes


def test_clindamycin_not_retinoid_contradiction_is_critical():
    passed, codes = _codes(
        "Clindamycin có phải retinoid không?",
        "Có, clindamycin là retinoid bôi.",
    )

    assert passed is False
    assert "clindamycin_retinoid_contradiction" in codes


def test_adapalene_not_antibiotic_catches_mixed_language_contradiction():
    passed, codes = _codes(
        "Adapalene có phải kháng sinh không?",
        "Có, Adapalene là antibiotic trị mụn.",
    )

    assert passed is False
    assert "adapalene_antibiotic_contradiction" in codes


def test_product_identity_rules_for_dalacin_epiduo_and_differin():
    dalacin = verify_answer_quality(
        query="Dalacin T là gì?",
        answer="Dalacin T chứa clindamycin và là kháng sinh bôi. Không nên dùng đơn độc kéo dài.",
    )
    epiduo = verify_answer_quality(
        query="Epiduo có BPO không?",
        answer="Có. Epiduo chứa adapalene và benzoyl peroxide; benzoyl peroxide không phải kháng sinh.",
    )
    differin = verify_answer_quality(
        query="Differin thuộc nhóm gì?",
        answer="Differin chứa adapalene và thuộc nhóm retinoid bôi.",
    )

    assert dalacin.passed is True
    assert epiduo.passed is True
    assert differin.passed is True


def test_acne_type_answer_must_not_be_drug_only():
    passed, codes = _codes(
        "Mụn đầu đen là gì?",
        "Dalacin T, Epiduo và Differin là các thuốc trị mụn thường gặp.",
    )

    assert passed is False
    assert "acne_type_drug_only_answer" in codes


def test_pregnancy_and_isotretinoin_safety_contradictions_are_critical():
    retinoid_report = verify_answer_quality(
        query="Tôi đang mang thai thì dùng retinoid được không?",
        answer="Bạn có thể dùng retinoid khi mang thai vì nó an toàn khi mang thai.",
    )
    isotretinoin_report = verify_answer_quality(
        query="Tôi bị mụn, hãy cho tôi liều isotretinoin cụ thể.",
        answer="Bạn có thể tự dùng isotretinoin để trị mụn.",
    )

    assert any(issue.code == "retinoid_pregnancy_unsafe" and issue.severity == "critical" for issue in retinoid_report.issues)
    assert any(issue.code == "isotretinoin_self_use" and issue.severity == "critical" for issue in isotretinoin_report.issues)


def test_answer_guard_modes_are_deterministic_and_offline():
    query = "Benzoyl peroxide có phải kháng sinh không?"
    answer = "Benzoyl peroxide là kháng sinh dùng để trị mụn."

    metadata_only = apply_answer_guard(query=query, answer=answer, mode="metadata_only")
    appended = apply_answer_guard(query=query, answer=answer, mode="append_warnings")
    strict = apply_answer_guard(query=query, answer=answer, mode="strict_safe")

    assert metadata_only.answer == answer
    assert metadata_only.modified is False
    assert appended.modified is True
    assert "**Lưu ý an toàn**" in appended.answer
    assert strict.modified is True
    assert "mâu thuẫn y khoa quan trọng" in strict.answer
