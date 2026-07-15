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


def test_antibiotic_multi_intent_requires_all_sub_questions():
    query = (
        "Vì sao không nên dùng clindamycin bôi hoặc kháng sinh uống đơn độc để điều trị mụn kéo dài? "
        "Benzoyl peroxide có vai trò gì khi phối hợp với kháng sinh?"
    )
    bad = verify_answer_quality(
        query=query,
        answer="Không, benzoyl peroxide không phải kháng sinh. Đây là hoạt chất bôi trị mụn.",
    )
    good = verify_answer_quality(
        query=query,
        answer=(
            "Không nên dùng clindamycin bôi hoặc kháng sinh uống đơn độc/kéo dài. "
            "Clindamycin bôi là kháng sinh bôi, đơn trị liệu kéo dài làm tăng nguy cơ kháng kháng sinh. "
            "Kháng sinh uống cần bác sĩ kê đơn và theo dõi. Benzoyl peroxide không phải kháng sinh; "
            "khi phối hợp giúp tăng hiệu quả và giảm nguy cơ kháng kháng sinh."
        ),
    )

    assert "antibiotic_multi_intent_incomplete" in [issue.code for issue in bad.issues]
    assert good.passed is True


def test_multi_entity_pregnancy_verifier_fails_when_named_med_is_missing():
    query = "Tôi đang có thai và hiện dùng adapalene, tazarotene và doxycycline để trị mụn. Tôi nên làm gì?"
    missing_one = verify_answer_quality(
        query=query,
        answer=(
            "Trong thai kỳ, nên ngừng adapalene và doxycycline, không tự dùng tiếp, "
            "và hỏi bác sĩ sản khoa hoặc bác sĩ da liễu."
        ),
    )
    complete = verify_answer_quality(
        query=query,
        answer=(
            "Trong thai kỳ, không tự tiếp tục dùng các thuốc trị mụn đã nêu. "
            "Adapalene là retinoid bôi cần tránh/ngừng; tazarotene là retinoid bôi cần tránh; "
            "doxycycline là kháng sinh uống cần bác sĩ sản khoa/da liễu đánh giá. Không tự tăng liều hay dùng tiếp."
        ),
    )

    missing_codes = [issue.code for issue in missing_one.issues]
    assert "missing_safety_entity" in missing_codes
    assert any(issue.evidence.get("missing_entity") == "tazarotene" for issue in missing_one.issues)
    assert complete.passed is True


def test_self_harm_answer_requires_crisis_actions_before_acne_advice():
    query = (
        "Mụn của tôi không quá nặng nhưng khiến tôi né tránh mọi người, mất ngủ và gần đây "
        "tôi đã nghĩ đến việc tự làm hại bản thân. Tôi nên làm gì?"
    )
    bad = verify_answer_quality(
        query=query,
        answer="Bạn nên chăm sóc da dịu nhẹ và gặp bác sĩ da liễu nếu mụn ảnh hưởng tâm lý.",
    )
    good = verify_answer_quality(
        query=query,
        answer=(
            "An toàn của bạn là ưu tiên trước điều trị mụn. Nếu có nguy cơ hành động ngay, hãy gọi cấp cứu "
            "hoặc đến cơ sở y tế khẩn cấp. Hãy nhờ một người đáng tin cậy ở bên và không ở một mình. "
            "Sau khi đã an toàn, bạn có thể gặp bác sĩ da liễu để xử lý mụn."
        ),
    )

    assert {"self_harm_emergency_action_missing", "self_harm_trusted_person_missing"} <= {
        issue.code for issue in bad.issues
    }
    assert good.passed is True


def test_acne_fulminans_verifier_requires_suspected_and_urgent_wording():
    query = (
        "Một nam thiếu niên đột ngột xuất hiện nhiều cục và nang viêm lớn, trợt loét, "
        "đóng vảy xuất huyết, kèm sốt và đau khớp."
    )
    bad = verify_answer_quality(query=query, answer="Đây là mụn nặng, nên khám bác sĩ khi sắp xếp được.")
    good = verify_answer_quality(
        query=query,
        answer=(
            "Mô tả này có thể nghi acne fulminans, nhưng không thể chẩn đoán chắc chắn qua chat. "
            "Bạn nên được đánh giá khẩn trong ngày, tốt nhất trong vòng 24 giờ."
        ),
    )

    assert "acne_fulminans_not_mentioned" in [issue.code for issue in bad.issues]
    assert "acne_fulminans_urgency_missing" in [issue.code for issue in bad.issues]
    assert good.passed is True


def test_requested_table_columns_are_verified_generically():
    query = (
        "Hãy lập bảng so sánh các lựa chọn điều trị đầu tay trong 12 tuần cho mụn nhẹ-trung bình "
        "và mụn trung bình-nặng, gồm thuốc, đường dùng, ưu điểm và lưu ý an toàn."
    )
    bad = verify_answer_quality(
        query=query,
        answer=(
            "| Thuốc | Đường dùng | Lưu ý an toàn |\n"
            "|---|---|---|\n"
            "| Benzoyl peroxide | Bôi | Có thể kích ứng. |"
        ),
    )
    good = verify_answer_quality(
        query=query,
        answer=(
            "| Thuốc | Đường dùng | Ưu điểm | Lưu ý an toàn |\n"
            "|---|---|---|---|\n"
            "| Benzoyl peroxide | Bôi | Không phải kháng sinh, hỗ trợ giảm mụn viêm. | Có thể kích ứng. |"
        ),
    )

    assert "requested_table_column_missing" in [issue.code for issue in bad.issues]
    assert good.passed is True


def test_oral_isotretinoin_does_not_accept_irrelevant_topical_warning():
    query = (
        "Khi nào isotretinoin đường uống được cân nhắc trong điều trị mụn? "
        "Trước và trong điều trị cần đánh giá những vấn đề nào?"
    )
    bad = verify_answer_quality(
        query=query,
        answer=(
            "Isotretinoin đường uống cần bác sĩ da liễu theo dõi. "
            "Nếu da đỏ rát, khô bong hoặc châm chích tăng, hãy giảm tần suất bôi hoặc tạm ngưng hoạt chất dễ kích ứng."
        ),
    )
    good = verify_answer_quality(
        query=query,
        answer=(
            "Isotretinoin đường uống được cân nhắc cho mụn nặng hoặc nguy cơ sẹo khi bác sĩ da liễu chỉ định. "
            "Cần đánh giá thai kỳ, sức khỏe tâm thần, chức năng gan và lipid máu theo tài liệu."
        ),
    )

    assert "irrelevant_topical_warning" in [issue.code for issue in bad.issues]
    assert good.passed is True
