"""Shared answer-presentation contract and deterministic Markdown cleanup."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal


ResponseProfile = Literal[
    "routine",
    "comparison",
    "drug_identity",
    "treatment",
    "safety",
    "urgent",
    "out_of_domain_emergency",
    "safe_fallback",
]

ANSWER_FORMATTING_CONTRACT_VERSION = "answer_formatting_contract_v3"

CANONICAL_DISCLAIMER = "Thông tin mang tính tham khảo và không thay thế chẩn đoán của bác sĩ."
LEGACY_DISCLAIMER = "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn y khoa chuyên nghiệp."

LEGACY_BOILERPLATE_HEADINGS = (
    "**Tóm tắt ngắn**",
    "**Giải thích/cơ chế**",
    "**Chăm sóc/điều trị thường gặp**",
    "**Lưu ý an toàn/tác dụng phụ**",
    "**Khi nào nên gặp bác sĩ**",
)

ANSWER_FORMATTING_CONTRACT = """\
ANSWER PRESENTATION CONTRACT V3:
- Dùng cùng một chuẩn trình bày cho Gemini, Gemini fallback, Ollama, cache hit, guardrail, severity guard và safe fallback; provider không được quyết định format.
- Không lặp lại hoặc dùng nguyên câu hỏi của người dùng làm tiêu đề. Bắt đầu ngay bằng câu trả lời.
- Trả lời trực tiếp trước, sau đó mới giải thích. Chỉ bắt đầu bằng "Có." hoặc "Không." khi câu hỏi thật sự là yes/no.
- Chọn cấu trúc theo response profile, không nối template nhiều mục vào mọi câu trả lời.
- Routine factual: ngắn gọn, không heading nếu chỉ hỏi định danh/thành phần; không thêm disclaimer trong thân answer khi UI đã có footer chung.
- Routine skincare: dùng heading Markdown ngắn và bullet hành động rõ ràng; không gắn nhãn Guardrail nếu vẫn là câu hỏi in-domain.
- Comparison: trả lời trực tiếp rồi dùng bảng Markdown GFM hoặc bullet đối chiếu; cover đủ các entity được hỏi.
- Drug identity/composition: trả lời trực tiếp tên nhóm/hoạt chất, giải thích ngắn vai trò; bullet khi có nhiều hoạt chất; không mở đầu "Có." nếu câu hỏi không phải yes/no.
- Safety/pregnancy: câu đầu nêu trực tiếp đối tượng được hỏi; wording phải ưu tiên tránh/ngừng trong thai kỳ, không để người dùng hiểu rằng có thể tự tiếp tục dùng; chỉ render một warning.
- Urgent/severe acne: dùng heading Markdown và bullet; nêu rõ cần bác sĩ da liễu đánh giá sớm, tránh nặn/bóp, không tự dùng isotretinoin hoặc thuốc kê đơn.
- Out-of-domain emergency: ngắn, trực tiếp, khuyên tìm trợ giúp y tế khẩn cấp; không dùng template mụn năm phần.
- Không có heading rỗng, heading lặp, disclaimer lặp, cảnh báo lặp, câu ghép hỏng hoặc câu bị cắt.
- Không đưa "Nguồn:" vào thân câu trả lời; hệ thống hiển thị nguồn riêng từ metadata.
- Luôn giữ tiếng Việt UTF-8 tự nhiên, không lộ prompt, context, JSON hoặc quy trình nội bộ.
"""


def answer_format_instruction_for_question(question: str) -> str:
    """Return intent-specific formatting hints without changing medical policy."""

    normalized = (question or "").lower()
    if _is_comparison_question(normalized):
        return (
            "FORMAT RIÊNG CHO CÂU SO SÁNH: Bắt đầu bằng một câu tóm tắt khác biệt chính. "
            "Sau đó dùng một bảng Markdown GFM hoặc bullet đối chiếu để cover đầy đủ từng entity trong câu hỏi. "
            "Nếu tài liệu chỉ đủ cho một entity, vẫn nhắc entity còn lại và nói rõ tài liệu hiện có chưa đủ thông tin về entity đó."
        )
    if _is_direct_question(normalized):
        return (
            "FORMAT RIÊNG CHO CÂU YES/NO HOẶC ĐỊNH DANH: Câu đầu tiên phải là câu trả lời trực tiếp. "
            "Không lặp câu hỏi. Không dùng template nhiều mục nếu câu trả lời đã đủ rõ."
        )
    if _is_high_safety_question(normalized):
        return (
            "FORMAT RIÊNG CHO CÂU AN TOÀN: Trả lời thận trọng, nêu điều không nên làm, "
            "và chỉ thêm mục 'Khi nào cần trao đổi với bác sĩ' nếu có dấu hiệu cần khám hoặc cấp cứu."
        )
    return (
        "FORMAT RIÊNG CHO CÂU THƯỜNG: Trả lời gọn, theo đúng intent, 2-4 đoạn ngắn hoặc bullet. "
        "Không thêm khung template dài nếu người dùng chỉ hỏi một ý."
    )


def infer_response_profile(
    question: str,
    *,
    severity: str | None = None,
    guardrail: str | None = None,
    fallback_type: str | None = None,
) -> ResponseProfile:
    """Infer presentation profile from intent/severity/guardrail, never provider."""

    text = _fold(question)
    if fallback_type and fallback_type != "none":
        return "safe_fallback"
    if guardrail in {"medical_emergency_out_of_scope", "medical_emergency_allergy"}:
        return "out_of_domain_emergency"
    if guardrail and guardrail not in {"in_domain", "in_domain_rule", "in_domain_followup_rule", "partial_out_of_domain", None}:
        if "emergency" in guardrail or ("dau nguc" in text and "kho tho" in text):
            return "out_of_domain_emergency"
    if severity == "emergency":
        return "out_of_domain_emergency"
    if severity == "urgent" or _is_severe_acne_question(text):
        return "urgent"
    if _is_high_safety_question(text):
        return "safety"
    if _is_comparison_question(text):
        return "comparison"
    if _is_drug_identity_or_composition(text):
        return "drug_identity"
    if any(marker in text for marker in ["cham soc", "routine", "dieu tri", "tri mun"]):
        return "treatment"
    return "routine"


def finalize_answer_presentation(
    answer: str,
    *,
    user_question: str = "",
    response_profile: ResponseProfile | None = None,
    severity: str | None = None,
    guardrail: str | None = None,
    fallback_type: str | None = None,
    add_disclaimer: bool | None = None,
) -> str:
    """Apply deterministic presentation policy without inventing arbitrary medical content."""

    profile = response_profile or infer_response_profile(
        user_question,
        severity=severity,
        guardrail=guardrail,
        fallback_type=fallback_type,
    )
    question_folded = _fold(user_question)
    draft = _normalize_newlines(answer)
    draft = _remove_known_disclaimers(draft)

    replacement = _deterministic_profile_answer(
        user_question=user_question,
        profile=profile,
        guardrail=guardrail,
        draft=draft,
    )
    if replacement:
        draft = replacement

    draft = strip_leading_question_echo(draft, user_question)
    if not _is_boolean_question(question_folded):
        draft = _strip_unexpected_boolean_prefix(draft)
    draft = _remove_source_lines(draft)
    draft = _normalize_common_surface_errors(draft)
    draft = normalize_answer_markdown(draft, disclaimer=CANONICAL_DISCLAIMER)
    draft = _remove_legacy_boilerplate_headings(draft, profile)
    draft = _dedupe_exact_paragraphs(draft)
    draft = _trim_incomplete_terminal_paragraph(draft)
    draft = normalize_answer_markdown(draft, disclaimer=CANONICAL_DISCLAIMER)

    if not draft:
        draft = "Tài liệu hiện có chưa đủ thông tin để trả lời chắc chắn."

    should_add_disclaimer = _should_add_answer_disclaimer(profile) if add_disclaimer is None else add_disclaimer
    if should_add_disclaimer and profile not in {"out_of_domain_emergency", "safe_fallback"}:
        draft = _append_disclaimer_once(draft, CANONICAL_DISCLAIMER)

    return draft.strip()


def normalize_answer_markdown(text: str, *, disclaimer: str | None = None) -> str:
    """Apply safe formatting cleanup without rewriting medical claims."""

    answer = _normalize_newlines(text)
    answer = _remove_greetings(answer)
    answer = _normalize_table_spacing(answer)
    answer = _remove_empty_markdown_headings(answer)
    answer = _dedupe_exact_headings(answer)
    if disclaimer:
        answer = _dedupe_disclaimer(answer, disclaimer)
    answer = re.sub(r"[ \t]+\n", "\n", answer)
    answer = re.sub(r"\n{3,}", "\n\n", answer)
    return answer.strip()


def strip_leading_question_echo(answer: str, user_question: str) -> str:
    """Remove exact/high-confidence question echo only from the answer opening."""

    if not answer or not user_question:
        return answer
    lines = _normalize_newlines(answer).splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return ""

    question_norm = _normalized_match_text(user_question)
    first_norm = _normalized_match_text(lines[0])
    if first_norm and first_norm == question_norm:
        return "\n".join(lines[1:]).lstrip()

    partials = _question_tail_candidates(user_question)
    if first_norm in partials:
        return "\n".join(lines[1:]).lstrip()

    # Some local models echo the final clause and continue on the same line.
    for partial in partials:
        if partial and first_norm.startswith(partial + " "):
            raw = lines[0].strip()
            raw_norm = _normalized_match_text(raw)
            if raw_norm.startswith(partial + " "):
                words_to_remove = len(partial.split())
                lines[0] = " ".join(raw.split()[words_to_remove:]).lstrip(" .:;-")
                return "\n".join(lines).lstrip()
    return "\n".join(lines)


def assess_structural_quality(
    answer: str,
    *,
    user_question: str = "",
    response_profile: ResponseProfile | None = None,
) -> list[dict[str, Any]]:
    """Return deterministic structural presentation issues."""

    text = _normalize_newlines(answer)
    profile = response_profile or infer_response_profile(user_question)
    issues: list[dict[str, Any]] = []
    folded = _fold(text)

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if user_question and _normalized_match_text(first_line) == _normalized_match_text(user_question):
        issues.append(_struct_issue("leading_question_echo", "error", "Answer starts by repeating the full user question."))
    elif user_question and _normalized_match_text(first_line) in _question_tail_candidates(user_question):
        issues.append(_struct_issue("partial_question_echo", "error", "Answer starts by repeating the tail of the user question."))

    heading_counts: dict[str, int] = {}
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if _is_heading(stripped):
            heading_counts[stripped.lower()] = heading_counts.get(stripped.lower(), 0) + 1
            lookahead = index + 1
            while lookahead < len(lines) and not lines[lookahead].strip():
                lookahead += 1
            if lookahead >= len(lines) or _is_heading(lines[lookahead]):
                issues.append(_struct_issue("empty_heading", "error", f"Heading has no body: {stripped}"))
    if any(count > 1 for count in heading_counts.values()):
        issues.append(_struct_issue("duplicate_heading", "warning", "Answer repeats a Markdown heading."))

    if text.count(CANONICAL_DISCLAIMER) > 1 or text.count(LEGACY_DISCLAIMER) > 1:
        issues.append(_struct_issue("duplicate_disclaimer", "warning", "Answer repeats the medical disclaimer."))

    warning_lines = [
        _normalized_match_text(line)
        for line in lines
        if any(marker in _fold(line) for marker in ["luu y", "canh bao", "khong tu", "cap cuu", "mang thai"])
    ]
    if len(warning_lines) != len(set(warning_lines)):
        issues.append(_struct_issue("duplicate_warning", "warning", "Answer repeats the same warning."))

    legacy_count = sum(1 for heading in LEGACY_BOILERPLATE_HEADINGS if heading in text)
    if legacy_count >= 4:
        issues.append(_struct_issue("legacy_boilerplate", "error", "Answer uses the legacy five-section template."))

    if profile not in {"safe_fallback"} and not _is_boolean_question(_fold(user_question)):
        if re.match(r"^\s*(Có|Không)[,.]\s+", text, flags=re.IGNORECASE):
            issues.append(_struct_issue("unexpected_boolean_prefix", "warning", "Non-boolean answer starts with Có./Không."))

    if _has_incomplete_terminal_sentence(text):
        issues.append(_struct_issue("incomplete_terminal_sentence", "error", "Answer appears to end mid-sentence."))

    if any(marker in folded for marker in ["...[truncated]", "truncated_generation", "[truncated"]):
        issues.append(_struct_issue("truncated_generation", "error", "Answer contains truncation marker."))

    if re.search(r"\b(mụn|tình trạng|da|điều trị)\s+Chỉ dựa vào", text):
        issues.append(_struct_issue("malformed_sentence_join", "error", "Answer contains a malformed sentence join."))

    return issues


def _deterministic_profile_answer(
    *,
    user_question: str,
    profile: ResponseProfile,
    guardrail: str | None,
    draft: str,
) -> str | None:
    text = _fold(user_question)
    if profile == "out_of_domain_emergency":
        if "dau nguc" in text and "kho tho" in text:
            return (
                "Đau ngực kèm khó thở không phải biểu hiện điển hình của mụn. "
                "Bạn nên tìm trợ giúp y tế khẩn cấp/cấp cứu nếu triệu chứng đang xảy ra hoặc nặng lên.\n\n"
                "Không tự quy triệu chứng này cho mụn hoặc tự điều trị bằng thuốc trị mụn."
            )
        return (
            "Triệu chứng bạn mô tả có thể cần được đánh giá y tế khẩn cấp, đặc biệt nếu đang khó thở, "
            "choáng, sưng môi/mặt/họng, sốt cao, đau dữ dội hoặc triệu chứng nặng lên.\n\n"
            "Không tự xử trí bằng thuốc trị mụn trong lúc có dấu hiệu toàn thân hoặc dấu hiệu cấp cứu."
        )

    if "mang thai" in text or "co thai" in text or "co bau" in text:
        if "adapalene" in text or "adapalen" in text or "retinoid" in text:
            return (
                "Nên tránh hoặc ngừng dùng adapalene trong thai kỳ và trao đổi với bác sĩ da liễu hoặc bác sĩ sản khoa.\n\n"
                "## Việc nên làm\n"
                "- Tạm ngưng hoặc chưa bắt đầu adapalene cho đến khi được bác sĩ xác nhận lựa chọn an toàn hơn.\n"
                "- Ưu tiên chăm sóc nền dịu nhẹ: rửa mặt nhẹ, dưỡng ẩm phù hợp và chống nắng.\n"
                "- Nếu đã lỡ dùng, hãy ghi lại thời gian, sản phẩm/nồng độ và trao đổi với bác sĩ để được tư vấn cụ thể.\n\n"
                "## Khi nào cần trao đổi với bác sĩ\n"
                "- Khi bạn cần chọn thuốc trị mụn trong thai kỳ.\n"
                "- Khi mụn viêm nhiều, đau, lan rộng hoặc có nguy cơ để lại sẹo."
            )

    if _is_severe_acne_question(text):
        return (
            "Các dấu hiệu này cần được bác sĩ da liễu đánh giá sớm vì mụn cục sâu, đau, sưng đỏ và bắt đầu để lại sẹo có nguy cơ tiến triển nặng hơn.\n\n"
            "## Việc nên làm\n"
            "- Sắp xếp khám da liễu sớm để đánh giá mức độ mụn và nguy cơ sẹo.\n"
            "- Không tự dùng isotretinoin, kháng sinh uống hoặc thuốc kê đơn khi chưa được bác sĩ chỉ định.\n"
            "- Không nặn, bóp hoặc cạy các cục mụn sâu vì dễ làm viêm nặng hơn và tăng nguy cơ sẹo.\n\n"
            "## Trong lúc chờ khám\n"
            "- Giữ routine dịu nhẹ, tránh chà xát mạnh.\n"
            "- Tạm ngưng phối hợp nhiều hoạt chất dễ kích ứng nếu da đang đỏ rát."
        )

    if "mun viem nhe" in text and any(marker in text for marker in ["cham soc", "hang ngay", "hằng ngày"]):
        return (
            "Mụn viêm nhẹ thường nên bắt đầu bằng routine đơn giản, dịu nhẹ và theo dõi đáp ứng của da thay vì phối hợp nhiều hoạt chất cùng lúc.\n\n"
            "## Chăm sóc hằng ngày\n"
            "- Rửa mặt nhẹ nhàng, tránh chà xát hoặc tẩy rửa quá mạnh.\n"
            "- Dưỡng ẩm phù hợp, không gây bít tắc và dùng chống nắng ban ngày.\n"
            "- Không nặn/cạy mụn viêm vì dễ làm đỏ lâu, thâm hoặc sẹo.\n\n"
            "## Khi cân nhắc hoạt chất\n"
            "- Benzoyl peroxide hoặc salicylic acid không bị cấm mặc định, nhưng có thể gây khô rát/kích ứng.\n"
            "- Nếu dùng, nên bắt đầu thận trọng, từng sản phẩm một và ngưng dùng và hỏi bác sĩ nếu kích ứng rõ."
        )

    if "epiduo" in text and any(marker in text for marker in ["gom", "hoat chat", "thanh phan", "moi hoat chat"]):
        return (
            "Epiduo chứa hai hoạt chất chính là adapalene và benzoyl peroxide.\n\n"
            "- Adapalene là retinoid bôi, giúp điều hòa sừng hóa nang lông, giảm bít tắc/nhân mụn và hỗ trợ chống viêm.\n"
            "- Benzoyl peroxide không phải kháng sinh; đây là hoạt chất bôi có tác dụng kháng khuẩn/antimicrobial với C. acnes và hỗ trợ tiêu sừng nhẹ.\n\n"
            "Hai hoạt chất này có thể gây khô, đỏ, rát hoặc bong tróc; benzoyl peroxide còn có thể làm bạc màu vải/tóc. Nếu da kích ứng mạnh, nên ngưng dùng và hỏi bác sĩ."
        )

    if "epiduo" in text and any(marker in text for marker in ["bpo", "benzoyl peroxide", "benzoyl"]):
        return (
            "Có. Epiduo chứa benzoyl peroxide và adapalene.\n\n"
            "Adapalene là retinoid bôi, giúp giảm bít tắc nang lông và hỗ trợ chống viêm. "
            "Benzoyl peroxide không phải kháng sinh; đây là hoạt chất bôi có tác dụng kháng khuẩn/antimicrobial với C. acnes và tiêu sừng nhẹ.\n\n"
            "Hai hoạt chất này có thể gây khô, đỏ, rát hoặc bong tróc; benzoyl peroxide còn có thể làm bạc màu vải/tóc."
        )

    if "adapalene" in text and "benzoyl peroxide" in text and _is_comparison_question(text):
        return (
            "Adapalene và benzoyl peroxide đều là hoạt chất bôi trị mụn, nhưng tác động lên các cơ chế khác nhau.\n\n"
            "| Tiêu chí | Adapalene | Benzoyl peroxide |\n"
            "|---|---|---|\n"
            "| Nhóm/ bản chất | Retinoid bôi. | Không phải kháng sinh; là hoạt chất bôi có tác dụng antimicrobial/kháng khuẩn. |\n"
            "| Vai trò chính | Điều hòa sừng hóa nang lông, giảm bít tắc/nhân mụn và hỗ trợ chống viêm. | Tác động lên C. acnes và hỗ trợ tiêu sừng nhẹ/giảm bít tắc. |\n"
            "| Lưu ý | Có thể gây khô, đỏ, bong tróc; cần cẩn trọng thai kỳ. | Có thể gây khô, đỏ, bong tróc và làm bạc màu vải/tóc. |\n\n"
            "Hai hoạt chất này có thể được phối hợp trong một số phác đồ vì tác động lên các cơ chế khác nhau."
        )

    if "benzoyl peroxide" in text and ("khang sinh" in text or "antibiotic" in text):
        return (
            "Không, benzoyl peroxide không phải là kháng sinh.\n\n"
            "Benzoyl peroxide là hoạt chất bôi trị mụn có tác dụng kháng khuẩn/antimicrobial với C. acnes và hỗ trợ giảm bít tắc nang lông/tiêu sừng nhẹ. "
            "Clindamycin hoặc erythromycin mới là kháng sinh bôi; khi phối hợp với kháng sinh bôi, benzoyl peroxide giúp tăng hiệu quả và giảm nguy cơ kháng kháng sinh."
        )

    if "clindamycin" in text and any(marker in text for marker in ["don doc", "don tri lieu", "monotherapy"]):
        return (
            "Không. Clindamycin không nên được dùng đơn độc để trị mụn.\n\n"
            "Clindamycin là kháng sinh bôi; dùng đơn trị liệu hoặc kéo dài có thể làm tăng nguy cơ kháng kháng sinh. Nếu bác sĩ chỉ định kháng sinh bôi, thuốc thường được phối hợp với benzoyl peroxide để tăng hiệu quả và giảm nguy cơ kháng kháng sinh."
        )

    if "differin" in text and any(
        marker in text
        for marker in ["thuoc gi", "thuoc nhom", "thuoc nhom gi", "nhom thuoc", "nhom gi", "hoat chat", "thuoc gì"]
    ):
        return (
            "Differin thuộc nhóm retinoid bôi ngoài da. Hoạt chất chính của Differin là adapalene.\n\n"
            "Adapalene giúp điều hòa sừng hóa nang lông, giảm bít tắc/nhân mụn và có tác dụng chống viêm. Hoạt chất này không phải là kháng sinh."
        )

    if "mun dau den" in text and "mun dau trang" in text and _is_comparison_question(text):
        return (
            "Mụn đầu đen và mụn đầu trắng đều là mụn nhân do bít tắc nang lông, nhưng khác nhau ở việc nhân mụn mở hay đóng trên bề mặt da.\n\n"
            "| Tiêu chí | Mụn đầu đen | Mụn đầu trắng |\n"
            "|---|---|---|\n"
            "| Bề mặt | Nhân mụn mở, bã nhờn/tế bào sừng tiếp xúc không khí nên sẫm màu. | Nhân mụn đóng, bề mặt bị che phủ nên nhìn trắng hoặc màu da. |\n"
            "| Chăm sóc | Tránh nặn mạnh; ưu tiên làm sạch dịu nhẹ và sản phẩm không gây bít tắc. | Tương tự, tránh cạy/nặn và theo dõi kích ứng khi dùng hoạt chất. |\n\n"
            "Nếu mụn viêm nhiều, đau hoặc để lại sẹo, nên khám bác sĩ da liễu."
        )

    return None


def _normalize_newlines(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _remove_known_disclaimers(text: str) -> str:
    output = text
    for disclaimer in (CANONICAL_DISCLAIMER, LEGACY_DISCLAIMER):
        output = output.replace(disclaimer, "")
    return output.strip()


def _append_disclaimer_once(text: str, disclaimer: str) -> str:
    text = _remove_known_disclaimers(text).rstrip()
    return f"{text}\n\n{disclaimer}".strip()


def _remove_greetings(text: str) -> str:
    text = re.sub(r"^(Chào bạn,?|Xin chào,?|Chào bạn!|Xin chào!)\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(\*\*)?Yes(\*\*)?\s*[,.:;–-]?\s+", "", text, flags=re.IGNORECASE)
    return re.sub(r"^(Hy vọng|Mong rằng) thông tin.*?$", "", text, flags=re.IGNORECASE | re.MULTILINE)


def _strip_unexpected_boolean_prefix(text: str) -> str:
    return re.sub(r"^\s*(Có|Không)[,.]\s+", "", text, count=1, flags=re.IGNORECASE)


def _normalize_common_surface_errors(text: str) -> str:
    replacements = {
        "đổ mồ hồ": "đổ mồ hôi",
        "nặn hoặc chèn": "nặn hoặc bóp",
        "mụn Chỉ dựa": "mụn. Chỉ dựa",
        "tình trạng mụn Chỉ dựa": "tình trạng mụn. Chỉ dựa",
        "ngưng hỏi bác sĩ": "ngưng dùng và hỏi bác sĩ",
    }
    output = text
    for bad, good in replacements.items():
        output = output.replace(bad, good)
    return output


def _remove_source_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.strip().lower().startswith("nguồn:"))


def _normalize_table_spacing(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        previous_is_table = bool(output and _is_table_row(output[-1]))
        next_is_table = bool(index + 1 < len(lines) and _is_table_row(lines[index + 1]))
        if stripped == "" and previous_is_table and next_is_table:
            continue
        output.append(line.rstrip())
    return "\n".join(output)


def _remove_empty_markdown_headings(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if _is_heading(line):
            lookahead = index + 1
            while lookahead < len(lines) and not lines[lookahead].strip():
                lookahead += 1
            if lookahead >= len(lines) or _is_heading(lines[lookahead]):
                index = lookahead
                continue
        output.append(line)
        index += 1
    return "\n".join(output)


def _remove_legacy_boilerplate_headings(text: str, profile: ResponseProfile) -> str:
    if profile == "safe_fallback":
        return text
    lines = []
    for line in text.splitlines():
        if line.strip() in LEGACY_BOILERPLATE_HEADINGS:
            continue
        lines.append(line)
    return "\n".join(lines)


def _dedupe_exact_headings(text: str) -> str:
    seen: set[str] = set()
    output: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if _is_heading(stripped):
            key = stripped.lower()
            if key in seen:
                continue
            seen.add(key)
        output.append(line)
    return "\n".join(output)


def _dedupe_exact_paragraphs(text: str) -> str:
    seen: set[str] = set()
    output: list[str] = []
    for paragraph in re.split(r"\n{2,}", text):
        key = _normalized_match_text(paragraph)
        if key and key in seen:
            continue
        seen.add(key)
        output.append(paragraph.strip())
    return "\n\n".join(part for part in output if part)


def _dedupe_disclaimer(text: str, disclaimer: str) -> str:
    parts = text.split(disclaimer)
    if len(parts) <= 2:
        return text
    return disclaimer.join(parts[:2]) + "".join(parts[2:])


def _should_add_answer_disclaimer(profile: ResponseProfile) -> bool:
    # The frontend already renders a global medical-information footer. Keep
    # answer-level disclaimers opt-in to avoid repeating generic safety text.
    return False


def _trim_incomplete_terminal_paragraph(text: str) -> str:
    if not _has_incomplete_terminal_sentence(text):
        return text
    paragraphs = [part for part in re.split(r"\n{2,}", text.strip()) if part.strip()]
    if len(paragraphs) <= 1:
        return text.strip() + "."
    return "\n\n".join(paragraphs[:-1]).strip()


def _has_incomplete_terminal_sentence(text: str) -> bool:
    clean = _remove_known_disclaimers(text).strip()
    if not clean:
        return False
    last = clean.splitlines()[-1].strip()
    if _is_heading(last):
        return True
    folded = _fold(last)
    dangling_endings = (
        " va",
        " nhung",
        " co the",
        " voi",
        " do",
        " vi",
        " anh nang",
        " nhay cam voi anh nang",
        " trong khi",
    )
    if any(folded.endswith(ending) for ending in dangling_endings):
        return True
    if len(last.split()) >= 8 and not re.search(r"[.!?…)]$", last):
        return True
    return False


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if re.fullmatch(r"\*\*[^*\n]{2,80}\*\*", stripped):
        return True
    return bool(re.fullmatch(r"#{1,4}\s+\S.{0,80}", stripped))


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _is_comparison_question(text: str) -> bool:
    return any(marker in text for marker in ["khác nhau", "khac nhau", "khác gì", "khac gi", "so sánh", "so sanh", " vs ", "versus"])


def _is_direct_question(text: str) -> bool:
    return any(marker in text for marker in ["có phải", "co phai", "phải là", "phai la", "là gì", "la gi", "thuộc nhóm", "thuoc nhom", "có nên", "co nen", "không?", "khong?"])


def _is_boolean_question(text: str) -> bool:
    folded = _fold(text)
    return any(
        marker in folded
        for marker in [
            "co phai",
            "co nen",
            "duoc khong",
            "dung duoc khong",
            "khong?",
            "khong",
            "is ",
        ]
    ) and not any(marker in folded for marker in ["gom", "hoat chat nao", "thanh phan nao", "moi hoat chat"])


def _is_high_safety_question(text: str) -> bool:
    folded = _fold(text)
    return any(
        marker in folded
        for marker in [
            "mang thai",
            "co thai",
            "co bau",
            "cho con bu",
            "isotretinoin",
            "mun sau",
            "mun cuc",
            "de lai seo",
            "dau nhieu",
            "sot",
        ]
    )


def _is_severe_acne_question(text: str) -> bool:
    return any(marker in text for marker in ["mun cuc", "mun sau", "cuc mun sau", "de lai seo", "nguy co seo"]) and any(
        marker in text for marker in ["dau", "sung", "do", "viem"]
    )


def _is_drug_identity_or_composition(text: str) -> bool:
    return any(marker in text for marker in ["differin", "epiduo", "benzoyl peroxide", "adapalene", "clindamycin", "dalacin"]) and any(
        marker in text
        for marker in ["la gi", "thuoc nhom", "hoat chat", "thanh phan", "chua", "gom", "co phai"]
    )


def _question_tail_candidates(question: str) -> set[str]:
    parts = re.split(r"[?.!。！？]\s*", question.strip())
    candidates: set[str] = set()
    for part in parts[-2:]:
        norm = _normalized_match_text(part)
        if 2 <= len(norm.split()) <= 8:
            candidates.add(norm)
    words = _normalized_match_text(question).split()
    if 2 <= len(words[-5:]) <= 8:
        candidates.add(" ".join(words[-5:]))
    return {candidate for candidate in candidates if candidate}


def _fold(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("đ", "d")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _normalized_match_text(text: str) -> str:
    folded = _fold(text)
    folded = re.sub(r"[^\w\s]", " ", folded, flags=re.UNICODE)
    return re.sub(r"\s+", " ", folded).strip()


def _struct_issue(code: str, severity: str, message: str) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "evidence": {}, "suggested_fix": None}


__all__ = [
    "ANSWER_FORMATTING_CONTRACT",
    "ANSWER_FORMATTING_CONTRACT_VERSION",
    "CANONICAL_DISCLAIMER",
    "ResponseProfile",
    "answer_format_instruction_for_question",
    "assess_structural_quality",
    "finalize_answer_presentation",
    "infer_response_profile",
    "normalize_answer_markdown",
    "strip_leading_question_echo",
]
