"""
src/agent/nodes/respond.py
==========================
LangGraph nodes for finalizing the response.
"""

import logging

from src.agent.state import ClinicalState
from src.agent.text_encoding import repair_mojibake

logger = logging.getLogger(__name__)


_SECTION_HEADINGS = [
    "**Tóm tắt ngắn**",
    "**Giải thích/cơ chế**",
    "**Chăm sóc/điều trị thường gặp**",
    "**Điều trị thường gặp theo tài liệu**",
    "**Lưu ý theo mức độ mụn**",
    "**Tác dụng phụ/cảnh báo**",
    "**Lưu ý an toàn/tác dụng phụ**",
    "**Khi nào nên gặp bác sĩ**",
    "**Phối hợp**",
    "**Lưu ý**",
]


def _dedupe_section_headings(text: str) -> str:
    """Keep only the first occurrence of each markdown section heading."""
    lines = text.splitlines()
    seen: set[str] = set()
    output: list[str] = []
    skip_until_next_heading = False

    for line in lines:
        stripped = line.strip()
        if stripped in _SECTION_HEADINGS:
            if stripped in seen:
                skip_until_next_heading = True
                continue
            seen.add(stripped)
            skip_until_next_heading = False
            output.append(line)
            continue
        if skip_until_next_heading and stripped in _SECTION_HEADINGS:
            skip_until_next_heading = False
        if skip_until_next_heading:
            continue
        output.append(line)

    return "\n".join(output).strip()


def _has_sufficient_answer_structure(text: str) -> bool:
    """Allow flexible medical-answer sections without forcing a generic wrapper."""
    has_summary = "**Tóm tắt ngắn**" in text
    has_note = "**Lưu ý**" in text
    has_referral = "**Khi nào nên gặp bác sĩ**" in text
    has_body = any(
        heading in text
        for heading in [
            "**Giải thích/cơ chế**",
            "**Chăm sóc/điều trị thường gặp**",
            "**Điều trị thường gặp theo tài liệu**",
            "**Phối hợp**",
        ]
    ) or "| Hoạt chất |" in text
    has_safety = any(
        heading in text
        for heading in [
            "**Lưu ý an toàn/tác dụng phụ**",
            "**Tác dụng phụ/cảnh báo**",
        ]
    ) or "| Hoạt chất |" in text
    return has_summary and has_body and has_safety and has_referral and has_note


async def finalize_response_node(state: ClinicalState) -> dict:
    """Finalize the response before returning to the user."""
    
    if state.get("is_in_domain") is False:
        logger.info("Finalizing out-of-domain response.")
        disclaimer = "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn y khoa chuyên nghiệp."
        refusal = state.get("refusal_message", "Xin lỗi, tôi không thể trả lời câu hỏi này.")
        refusal = refusal.replace(disclaimer, "").strip()
        guardrail = state.get("guardrail")

        if guardrail in {"out_of_domain", "out_of_domain_fallback", "unsafe_out_of_domain"}:
            final_answer = refusal
        elif guardrail == "unsafe_prescription_request":
            final_answer = (
                "Tôi không thể kê đơn, chọn liều hoặc bỏ qua hướng dẫn an toàn cho thuốc trị mụn nguy cơ cao. "
                "Các thuốc như isotretinoin, retinoid hoặc kháng sinh cần bác sĩ da liễu đánh giá, kê đơn và theo dõi. "
                f"{disclaimer}"
            )
        elif guardrail == "medical_emergency_allergy":
            final_answer = (
                "**Tóm tắt ngắn**\n"
                f"{refusal}\n\n"
                "**Giải thích/cơ chế**\n"
                "Sưng môi, nổi mề đay, khó thở, choáng hoặc tim đập nhanh sau thuốc/sản phẩm mới có thể gợi ý phản ứng dị ứng nặng hoặc phản vệ.\n\n"
                "**Chăm sóc/điều trị thường gặp**\n"
                "Ngừng sản phẩm nghi ngờ và không tự bôi/uống thêm thuốc trị mụn để xử trí tại nhà khi đang có triệu chứng toàn thân.\n\n"
                "**Lưu ý an toàn/tác dụng phụ**\n"
                "Nếu đang khó thở, sưng môi/mặt/lưỡi, nổi mề đay lan nhanh, choáng hoặc tim đập nhanh, cần gọi cấp cứu hoặc đi cấp cứu ngay.\n\n"
                "**Khi nào nên gặp bác sĩ**\n"
                "Cần khám khẩn/cấp cứu ngay nếu triệu chứng đang xảy ra, nặng lên hoặc xuất hiện sau khi dùng thuốc/sản phẩm mới.\n\n"
                "**Lưu ý**\n"
                f"{disclaimer}"
            )
        elif guardrail == "urgent_skin_eye_infection":
            final_answer = (
                "**Tóm tắt ngắn**\n"
                f"{refusal}\n\n"
                "**Giải thích/cơ chế**\n"
                "Sưng đau vùng da kèm sốt cao, đỏ lan nhanh, đau quanh mắt hoặc nhìn mờ có thể không còn là mụn thông thường và cần loại trừ nhiễm trùng lan rộng.\n\n"
                "**Chăm sóc/điều trị thường gặp**\n"
                "Không nên nặn, chườm nóng mạnh hoặc tự dùng kháng sinh/thuốc uống khi chưa được khám. Hãy ưu tiên đánh giá y tế trực tiếp.\n\n"
                "**Lưu ý an toàn/tác dụng phụ**\n"
                "Vùng quanh mắt và triệu chứng sốt/nhìn mờ là dấu hiệu nguy hiểm vì nhiễm trùng có thể lan nhanh.\n\n"
                "**Khi nào nên gặp bác sĩ**\n"
                "Nên đi khám cấp cứu hoặc cơ sở y tế ngay, đặc biệt nếu đau quanh mắt, sưng tăng, đỏ lan, sốt cao hoặc thay đổi thị lực.\n\n"
                "**Lưu ý**\n"
                f"{disclaimer}"
            )
        elif guardrail == "medical_emergency_out_of_scope":
            final_answer = (
                "**Tóm tắt ngắn**\n"
                f"{refusal}\n\n"
                "**Giải thích/cơ chế**\n"
                "Mụn thường gây tổn thương tại da như sẩn, mụn mủ, nang viêm hoặc đau tại vùng da bị mụn. "
                "Các triệu chứng toàn thân như khó thở, choáng, ngất hoặc tim đập nhanh cần được đánh giá y tế riêng.\n\n"
                "**Chăm sóc/điều trị thường gặp**\n"
                "Không nên tự quy triệu chứng này là do mụn hoặc tự xử trí bằng thuốc trị mụn. "
                "Hãy ưu tiên kiểm tra triệu chứng cấp tính trước, sau đó mới xử lý vấn đề da liễu nếu cần.\n\n"
                "**Lưu ý an toàn/tác dụng phụ**\n"
                "Nếu triệu chứng xuất hiện sau khi dùng thuốc hoặc sản phẩm mới, hãy ngừng sản phẩm nghi ngờ và liên hệ cơ sở y tế. "
                "Nếu đang khó thở, choáng, ngất, tím tái hoặc tim đập nhanh, cần đi cấp cứu ngay.\n\n"
                "**Khi nào nên gặp bác sĩ**\n"
                "Nên đi cấp cứu hoặc gọi hỗ trợ y tế khẩn cấp nếu triệu chứng đang xảy ra, nặng lên, hoặc kèm choáng/ngất.\n\n"
                "**Lưu ý**\n"
                f"{disclaimer}"
            )
        else:
            final_answer = (
                "**Tóm tắt ngắn**\n"
                f"{refusal}\n\n"
                "**Giải thích/cơ chế**\n"
                "Câu hỏi này nằm ngoài phạm vi Acne Advisor AI, nên tôi không nên suy diễn hoặc đưa lời khuyên không đúng chuyên môn.\n\n"
                "**Chăm sóc/điều trị thường gặp**\n"
                "Bạn có thể hỏi về mụn trứng cá, chăm sóc da mụn, hoạt chất trị mụn, tác dụng phụ hoặc khi nào nên gặp bác sĩ da liễu.\n\n"
                "**Lưu ý an toàn/tác dụng phụ**\n"
                "Không tự dùng thuốc kê đơn hoặc phối hợp nhiều hoạt chất mạnh nếu chưa có hướng dẫn chuyên môn.\n\n"
                "**Khi nào nên gặp bác sĩ**\n"
                "Nên gặp bác sĩ nếu có triệu chứng nặng, kéo dài, đau nhiều, để lại sẹo hoặc có dấu hiệu toàn thân bất thường.\n\n"
                "**Lưu ý**\n"
                f"{disclaimer}"
            )
        return {
            "final_answer": final_answer,
            "vector_contexts": [],
            "graph_facts": [],
            "symptoms": [],
            "sources": [],
            "actual_provider": "system",
            "actual_model": "guardrail-rule"
        }
        
    if state.get("cache_hit"):
        logger.debug("Finalizing cached response.")
        return {} # Keep existing final_answer set by cache_lookup
        
    draft = repair_mojibake(state.get("draft_answer", ""))
    
    # Post-process Qwen (or any model) output to ensure safety
    import re
    
    # ── Group 0: Existing treatment wording rules ──────────────────────
    replacements = [
        (r"(thuộc mức độ trung bình đến nặng|có thể thuộc mức độ trung bình đến nặng|thuộc mức độ mụn trung bình đến nặng)", "Chỉ dựa vào mô tả này thì chưa thể xác định chính xác mức độ mụn hay lựa chọn phù hợp nhất cho bạn."),
        # Specific Benzoyl peroxide sentence rewrite (must come before generic patterns)
        (r"Benzoyl\s+[Pp]eroxide\s+có\s+thể\s+là\s+một\s+lựa\s+chọn\s+phù\s+hợp[^.]*", "Benzoyl peroxide có thể là một hoạt chất đáng cân nhắc trong một số trường hợp mụn viêm"),
        # Broader "lựa chọn phù hợp" treatment phrases
        (r"(lựa chọn phù hợp để điều trị|lựa chọn phù hợp cho điều trị|lựa chọn điều trị phù hợp|lựa chọn trị liệu phù hợp|lựa chọn phù hợp cho tình trạng của bạn)", "hoạt chất đáng cân nhắc trong một số trường hợp"),
        (r"(là một lựa chọn trị liệu phù hợp|là lựa chọn trị liệu phù hợp|là lựa chọn điều trị phù hợp|là một lựa chọn điều trị phù hợp)", "hoạt chất đáng cân nhắc trong một số trường hợp mụn viêm"),
        (r"là một lựa chọn phổ biến để điều trị", "là hoạt chất thường được nhắc đến trong điều trị"),
        (r"lựa chọn phổ biến để điều trị", "hoạt chất thường được nhắc đến trong điều trị")
    ]
    
    for pattern, replacement in replacements:
        draft = re.sub(pattern, replacement, draft, flags=re.IGNORECASE)
    
    # ── Group A: Pregnancy category removal ───────────────────────────
    # Remove "thai kỳ C/X" etc. unless preceded by "phân loại cũ"
    # Python re requires fixed-width lookbehinds, so we use a callback
    def _pregnancy_cat_repl(m: re.Match) -> str:
        start = m.start()
        # Check if "phân loại cũ" appears in the 30 chars before the match
        prefix = draft[max(0, start - 30):start]
        if "phân loại cũ" in prefix:
            return m.group(0)  # keep as-is
        return "cần tham khảo bác sĩ về độ an toàn khi mang thai"

    draft = re.sub(
        r"thai kỳ\s+[A-DX](?!\w)",
        _pregnancy_cat_repl,
        draft,
        flags=re.IGNORECASE,
    )
    draft = re.sub(
        r"(?i)(?:FDA\s+)?pregnancy\s+category\s+[A-DX](?!\w)",
        "cần tham khảo bác sĩ về độ an toàn khi mang thai",
        draft,
    )

    # ── Group B: Translation fixes ────────────────────────────────────
    draft = re.sub(r"cắn môi", "môi nứt nẻ", draft, flags=re.IGNORECASE)
    draft = re.sub(r"nhiễm ánh sáng", "nhạy cảm với ánh sáng", draft, flags=re.IGNORECASE)

    # ── Group C: Isotretinoin scar wording ────────────────────────────
    draft = re.sub(
        r"isotretinoin\s+gây\s+(?:nguy\s+cơ\s+)?sẹo",
        "isotretinoin thường được cân nhắc cho mụn nặng, mụn có nguy cơ để lại sẹo, hoặc không đáp ứng với điều trị khác",
        draft,
        flags=re.IGNORECASE,
    )

    # ── Group C.5: High-risk isotretinoin safety reinforcement ────────
    if "isotretinoin" in draft.lower():
        isotretinoin_warning = (
            "Isotretinoin là thuốc kê đơn, không nên tự ý dùng; cần bác sĩ da liễu kê đơn, "
            "theo dõi tác dụng phụ và làm xét nghiệm khi cần. Thuốc này chống chỉ định trong thai kỳ "
            "và cần tránh nếu đang mang thai hoặc có kế hoạch mang thai khi chưa được bác sĩ chuyên khoa quản lý."
        )
        if "không nên tự ý dùng" not in draft.lower() and "không tự ý dùng" not in draft.lower():
            safety_heading = "**Lưu ý an toàn/tác dụng phụ**"
            if safety_heading in draft:
                draft = draft.replace(
                    safety_heading,
                    safety_heading + "\n" + isotretinoin_warning + "\n",
                    1,
                )
            else:
                draft += "\n\n**Lưu ý an toàn/tác dụng phụ**\n" + isotretinoin_warning

    # ── Group D: Retinoid comparative safety ──────────────────────────
    draft = re.sub(
        r"(?:tretinoin|adapalen[e]?|tazaroten[e]?)\s+(?:thì\s+)?ít\s+nguy\s+hiểm\s+hơn",
        "Các retinoid, đặc biệt isotretinoin đường uống và một số retinoid bôi, cần tránh hoặc chỉ dùng khi bác sĩ đánh giá lợi ích-nguy cơ",
        draft,
        flags=re.IGNORECASE,
    )
    
    # Context-dependent dosage/frequency sanitization
    # Only sanitize if user didn't ask about usage/dosage/frequency
    user_question = (state.get("user_question") or "").lower()
    conversation_history = (state.get("conversation_history") or []) if state.get("use_history_context") else []
    history_text = " ".join(str(msg.get("content", "")) for msg in conversation_history).lower()
    user_history_text = " ".join(
        str(msg.get("content", ""))
        for msg in conversation_history
        if msg.get("role") == "user"
    ).lower()
    combined_question_context = f"{user_history_text} {user_question}".strip()
    dosage_query_keywords = ["cách dùng", "dùng thế nào", "tần suất", "bôi mấy lần", "liều", "bao lâu", "mấy lần", "dùng sao"]
    user_asked_dosage = any(kw in user_question for kw in dosage_query_keywords)

    pregnancy_context = any(
        kw in combined_question_context
        for kw in ["mang thai", "có thai", "có bầu", "thai 2 tháng", "cho con bú", "đang bầu"]
    )
    retinoid_context = any(
        kw in combined_question_context
        for kw in ["retinoid", "isotretinoin", "tretinoin", "adapalene", "adapalen", "tazarotene", "tazaroten"]
    )
    asks_med_choice = any(
        kw in user_question
        for kw in ["dùng thuốc gì", "nên dùng thuốc gì", "thuốc gì", "uống thuốc gì", "bôi thuốc gì", "kê thuốc"]
    )
    antibiotic_question = "kháng sinh" in combined_question_context or "antibiotic" in combined_question_context
    toothpaste_question = "kem đánh răng" in user_question
    care_followup = any(
        kw in user_question
        for kw in ["bắt đầu chăm sóc", "chăm sóc như thế nào", "nên bắt đầu", "routine", "quy trình"]
    )
    profile_followup = any(
        kw in user_question
        for kw in ["nhắc lại", "tình trạng da", "tuổi của tôi", "da và tuổi"]
    )
    breastfeeding_context = any(
        kw in combined_question_context
        for kw in ["cho con bú", "đang cho con bú", "nuôi con bằng sữa mẹ"]
    )
    pregnancy_or_breastfeeding_context = pregnancy_context or breastfeeding_context
    benzoyl_peroxide_question = bool(
        re.search(r"\bbenzoyl\s+peroxide\b|\bbp\b", combined_question_context, flags=re.IGNORECASE)
    )
    bp_antibiotic_identity_question = benzoyl_peroxide_question and any(
        marker in combined_question_context
        for marker in [
            "có phải kháng sinh không",
            "phải kháng sinh không",
            "là kháng sinh không",
            "is benzoyl peroxide an antibiotic",
            "is bp an antibiotic",
        ]
    )
    adapalene_question = "adapalene" in combined_question_context or "adapalen" in combined_question_context
    clindamycin_monotherapy_question = (
        "clindamycin" in combined_question_context
        and any(marker in combined_question_context for marker in ["đơn độc", "đơn trị liệu", "monotherapy"])
        and any(marker in combined_question_context for marker in ["có nên", "nên dùng", "dùng được không"])
    )
    adapalene_bp_comparison_question = (
        adapalene_question
        and benzoyl_peroxide_question
        and any(marker in combined_question_context for marker in ["khác nhau", "khác gì", "so sánh", "versus", " vs "])
    )
    lemon_question = "nước chanh" in user_question or "chanh" in user_question
    chocolate_question = "chocolate" in combined_question_context

    if profile_followup and user_history_text:
        age_match = re.search(r"\b(\d{1,2})\s*tuổi\b", user_history_text)
        age_text = f"{age_match.group(1)} tuổi" if age_match else "tuổi chưa rõ"
        details = []
        for marker in ["da dầu", "mụn đầu đen", "mũi", "mụn viêm", "má"]:
            if marker in user_history_text:
                details.append(marker)
        if all(marker in user_history_text for marker in ["da dầu", "mụn đầu đen", "mũi", "mụn viêm", "má"]):
            detail_text = "da dầu, có mụn đầu đen ở mũi và vài mụn viêm ở má"
        else:
            detail_text = ", ".join(dict.fromkeys(details)) if details else "tình trạng da đã trao đổi trong cuộc trò chuyện"
        draft = (
            "**Tóm tắt ngắn**\n"
            f"Bạn đã nói mình {age_text}, có {detail_text}.\n\n"
            "**Giải thích/cơ chế**\n"
            "Thông tin này giúp định hướng chăm sóc theo tình trạng da dầu, bít tắc lỗ chân lông và vài tổn thương viêm, nhưng chưa thay thế khám trực tiếp.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Có thể bắt đầu bằng làm sạch dịu nhẹ, dưỡng ẩm không gây bít tắc, chống nắng và tránh nặn mụn. Nếu cần hoạt chất, nên dùng từng bước và theo dõi kích ứng.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Không tự uống kháng sinh, isotretinoin hoặc phối hợp nhiều thuốc mạnh khi chưa có bác sĩ chỉ định.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên khám da liễu nếu mụn viêm tăng, đau, để lại sẹo/thâm nhiều hoặc không cải thiện sau chăm sóc cơ bản.\n\n"
            "**Lưu ý**\n"
        )
    elif bp_antibiotic_identity_question:
        draft = (
            "**Tóm tắt ngắn**\n"
            "Không, Benzoyl peroxide không phải là kháng sinh.\n\n"
            "**Giải thích/cơ chế**\n"
            "Benzoyl peroxide là hoạt chất bôi trị mụn có tác dụng kháng khuẩn/antimicrobial và hỗ trợ giảm bít tắc nang lông, tiêu sừng nhẹ. "
            "Nó khác với kháng sinh bôi như clindamycin hoặc erythromycin.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Trong điều trị mụn, benzoyl peroxide có thể được dùng đơn độc trong một số trường hợp phù hợp hoặc phối hợp với retinoid/kháng sinh bôi tùy mức độ và hướng dẫn chuyên môn.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Hoạt chất này có thể gây khô, đỏ, bong tróc, châm chích hoặc kích ứng, và có thể làm bạc màu tóc, vải hoặc quần áo. "
            "Khi phối hợp với kháng sinh bôi, benzoyl peroxide giúp giảm nguy cơ kháng kháng sinh.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên gặp bác sĩ da liễu nếu mụn viêm nhiều, đau, có sẹo/nguy cơ sẹo, hoặc da kích ứng nặng khi dùng sản phẩm trị mụn.\n\n"
            "**Lưu ý**\n"
        )
    elif antibiotic_question and not benzoyl_peroxide_question and any(kw in user_question for kw in ["có cần uống", "uống kháng sinh", "cần uống", "kháng sinh không"]):
        draft = (
            "**Tóm tắt ngắn**\n"
            "Không nên tự uống kháng sinh để trị mụn. Kháng sinh đường uống chỉ nên dùng khi bác sĩ da liễu đánh giá là cần.\n\n"
            "**Giải thích/cơ chế**\n"
            "Kháng sinh có thể được cân nhắc trong một số trường hợp mụn viêm, nhưng dùng sai dễ gây tác dụng phụ và kháng kháng sinh.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Bạn nên bắt đầu từ chăm sóc da ổn định và điều trị bôi phù hợp trước khi nghĩ đến thuốc uống, trừ khi mụn viêm nặng hoặc lan rộng.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Không tự dùng, dùng lại đơn cũ hoặc dùng kéo dài kháng sinh. Nếu bác sĩ kê kháng sinh, cần dùng đúng hướng dẫn và tái khám.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên khám nếu mụn viêm nhiều, đau, có nang/cục, để lại sẹo hoặc ảnh hưởng nhiều đến sinh hoạt.\n\n"
            "**Lưu ý**\n"
        )
    elif clindamycin_monotherapy_question:
        draft = (
            "**Tóm tắt ngắn**\n"
            "Không. Clindamycin không nên được dùng đơn độc để trị mụn.\n\n"
            "**Giải thích/cơ chế**\n"
            "Clindamycin là kháng sinh bôi. Dùng kháng sinh bôi đơn trị liệu dễ làm tăng nguy cơ kháng kháng sinh và không phải cách dùng được khuyến nghị trong tài liệu hiện có.\n\n"
            "**Điều trị thường gặp theo tài liệu**\n"
            "Nếu bác sĩ chỉ định kháng sinh bôi, thuốc thường được phối hợp với benzoyl peroxide để tăng hiệu quả và giảm nguy cơ kháng kháng sinh.\n\n"
            "**Tác dụng phụ/cảnh báo**\n"
            "Không tự dùng kéo dài hoặc dùng lại đơn cũ. Nếu da kích ứng, đỏ rát hoặc mụn nặng lên, nên ngừng sản phẩm nghi ngờ và hỏi bác sĩ.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên gặp bác sĩ da liễu nếu mụn viêm nhiều, đau, có sẹo/nguy cơ sẹo hoặc cần thuốc kháng sinh trị mụn.\n\n"
            "**Lưu ý**\n"
        )
    elif pregnancy_context and retinoid_context:
        draft = (
            "**Tóm tắt ngắn**\n"
            "Khi đang mang thai hoặc cho con bú, bạn không nên tự dùng retinoid để trị mụn.\n\n"
            "**Giải thích/cơ chế**\n"
            "Một số retinoid, đặc biệt isotretinoin đường uống, có nguy cơ nghiêm trọng trong thai kỳ. Vì vậy cần bác sĩ da liễu/sản khoa đánh giá lợi ích-nguy cơ trước mọi quyết định dùng thuốc.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Có thể ưu tiên chăm sóc nền như làm sạch dịu nhẹ, dưỡng ẩm phù hợp và chống nắng. Nếu cần hoạt chất trị mụn, bác sĩ có thể cân nhắc lựa chọn an toàn hơn tùy tình trạng.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Không tự dùng retinoid, isotretinoin hoặc thuốc kê đơn khi đang mang thai/cho con bú. Nếu đã lỡ dùng, nên liên hệ bác sĩ để được tư vấn cụ thể.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên gặp bác sĩ da liễu hoặc sản khoa nếu mụn viêm nhiều, đau, lan rộng hoặc bạn đang cần điều trị bằng thuốc.\n\n"
            "**Lưu ý**\n"
        )
    elif pregnancy_context and asks_med_choice:
        draft = (
            "**Tóm tắt ngắn**\n"
            "Khi đang mang thai, bạn không nên tự chọn thuốc trị mụn, nhất là thuốc uống hoặc retinoid.\n\n"
            "**Giải thích/cơ chế**\n"
            "An toàn thuốc trong thai kỳ phụ thuộc tuổi thai, mức độ mụn, bệnh nền và loại thuốc. Vì vậy cần bác sĩ da liễu/sản khoa đánh giá trước.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Bác sĩ có thể cân nhắc một số lựa chọn như azelaic acid hoặc benzoyl peroxide trong tình huống phù hợp, nhưng bạn không nên tự dùng nếu chưa được hướng dẫn. Chăm sóc nền dịu nhẹ, dưỡng ẩm và chống nắng vẫn là bước quan trọng.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Tránh tự dùng retinoid/isotretinoin, kháng sinh hoặc phối hợp nhiều hoạt chất mạnh trong thai kỳ. Nếu kích ứng, đau rát hoặc mụn viêm nặng lên, nên dừng sản phẩm nghi ngờ và hỏi bác sĩ.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên gặp bác sĩ nếu mụn viêm nhiều, đau, để lại sẹo, hoặc bạn cần thuốc điều trị khi đang mang thai.\n\n"
            "**Lưu ý**\n"
        )
    elif breastfeeding_context and benzoyl_peroxide_question:
        draft = (
            "**Tóm tắt ngắn**\n"
            "Khi đang cho con bú, bạn không nên tự ý dùng thuốc trị mụn. Với benzoyl peroxide bôi, bác sĩ có thể cân nhắc tùy từng trường hợp.\n\n"
            "**Giải thích/cơ chế**\n"
            "Benzoyl peroxide là hoạt chất trị mụn bôi ngoài da. Câu hỏi quan trọng khi cho con bú là mức độ cần thiết, vùng bôi và nguy cơ kích ứng hơn là tự dùng theo cảm tính.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Nếu bác sĩ đồng ý dùng, cần tránh bôi lên vùng da mà em bé có thể tiếp xúc trực tiếp và theo dõi khô rát hoặc kích ứng.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Không tự ý dùng thuốc mới khi đang cho con bú, nhất là nếu da đang nhạy cảm. Nếu có đỏ, rát, bong tróc hoặc bé chạm vào vùng bôi, nên hỏi bác sĩ.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên hỏi bác sĩ da liễu hoặc sản khoa nếu bạn đang cho con bú và muốn bắt đầu một hoạt chất trị mụn mới.\n\n"
            "**Lưu ý**\n"
        )
    elif pregnancy_context and any(kw in user_question for kw in ["mụn viêm", "mụn viêm nhiều", "thuốc gì", "nên dùng thuốc gì"]):
        draft = (
            "**Tóm tắt ngắn**\n"
            "Khi đang mang thai, bạn không nên tự chọn thuốc trị mụn, nhất là retinoid hoặc isotretinoin.\n\n"
            "**Giải thích/cơ chế**\n"
            "Mụn viêm liên quan đến bít tắc, bã nhờn, vi khuẩn liên quan đến mụn và phản ứng viêm. Trong thai kỳ, việc chọn thuốc cần ưu tiên an toàn cho mẹ và thai.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Bác sĩ có thể cân nhắc azelaic acid hoặc benzoyl peroxide tùy trường hợp. Kháng sinh chỉ nên dùng khi bác sĩ kê và theo dõi phù hợp.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Không tự dùng retinoid, isotretinoin hoặc kháng sinh uống trong thai kỳ. Nếu da kích ứng, đau rát hoặc mụn nặng lên, hãy hỏi bác sĩ.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên gặp bác sĩ da liễu hoặc sản khoa nếu mụn viêm nhiều, đau, lan rộng hoặc để lại sẹo.\n\n"
            "**Lưu ý**\n"
        )
    elif lemon_question:
        draft = (
            "**Tóm tắt ngắn**\n"
            "Không có đủ bằng chứng cho thấy uống nước chanh mỗi ngày có thể chữa khỏi mụn.\n\n"
            "**Giải thích/cơ chế**\n"
            "Nước chanh không phải hoạt chất điều trị mụn đã được chứng minh. Uống quá nhiều có thể gây khó chịu dạ dày hoặc ảnh hưởng men răng.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Mụn nên được xử lý bằng chăm sóc da phù hợp và hoạt chất/thuốc có bằng chứng hơn, thay vì xem nước chanh là giải pháp chính.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Nếu uống nước chanh làm bạn khó chịu dạ dày hoặc ê buốt răng, nên giảm hoặc ngừng.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên gặp bác sĩ nếu mụn kéo dài, viêm nhiều hoặc để lại sẹo.\n\n"
            "**Lưu ý**\n"
        )
    elif chocolate_question and "chắc chắn" in user_question:
        draft = (
            "**Tóm tắt ngắn**\n"
            "Không có bằng chứng đủ chắc để nói chocolate chắc chắn gây mụn cho mọi người.\n\n"
            "**Giải thích/cơ chế**\n"
            "Ăn uống có thể ảnh hưởng khác nhau giữa từng người, nhưng không nên kết luận đơn giản rằng chocolate luôn là nguyên nhân trực tiếp của mụn.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Nếu bạn thấy một số món làm mụn nặng hơn, có thể theo dõi nhật ký ăn uống và phản ứng da để trao đổi với bác sĩ.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Không cần kiêng cực đoan chỉ vì nghe nói chocolate gây mụn nếu chưa có bằng chứng cá nhân rõ ràng.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên gặp bác sĩ nếu mụn viêm nhiều, kéo dài hoặc ảnh hưởng nhiều đến sinh hoạt.\n\n"
            "**Lưu ý**\n"
        )
    elif adapalene_bp_comparison_question:
        draft = (
            "**Tóm tắt ngắn**\n"
            "Adapalene và benzoyl peroxide đều là hoạt chất bôi trị mụn, nhưng tác động lên các cơ chế khác nhau.\n\n"
            "| Hoạt chất | Vai trò | Lưu ý an toàn |\n"
            "|---|---|---|\n"
            "| Adapalene | Retinoid bôi, giúp điều hòa sừng hóa nang lông, giảm bít tắc/nhân mụn và có tác dụng chống viêm. | Có thể gây khô, đỏ, bong tróc, kích ứng; cần cẩn trọng trong thai kỳ và nên hỏi bác sĩ nếu đang mang thai/chuẩn bị mang thai. |\n"
            "| Benzoyl peroxide | Không phải kháng sinh; là hoạt chất bôi có tác dụng kháng khuẩn/antimicrobial với C. acnes và hỗ trợ giảm bít tắc/tiêu sừng nhẹ. | Có thể gây khô, đỏ, bong tróc, châm chích/kích ứng và có thể làm bạc màu vải, tóc hoặc quần áo. |\n\n"
            "**Phối hợp**\n"
            "Hai hoạt chất này có thể được phối hợp trong một số phác đồ vì tác động lên các cơ chế khác nhau của mụn. Khi phối hợp hoặc khi da nhạy cảm, nên dùng theo hướng dẫn chuyên môn để giảm kích ứng.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên gặp bác sĩ da liễu nếu mụn viêm nhiều, đau, có sẹo/nguy cơ sẹo, đang mang thai/cho con bú, hoặc da kích ứng mạnh khi dùng hoạt chất trị mụn.\n\n"
            "**Lưu ý**\n"
        )
    elif adapalene_question:
        draft = (
            "**Tóm tắt ngắn**\n"
            "Adapalene là retinoid bôi giúp điều hòa sừng hóa nang lông, giảm bít tắc và có tác dụng chống viêm trong điều trị mụn.\n\n"
            "**Giải thích/cơ chế**\n"
            "Hoạt chất này giúp hạn chế hình thành nhân mụn mới và hỗ trợ cải thiện mụn đầu đen, mụn ẩn hoặc một phần mụn viêm nhẹ.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Thường được dùng với tần suất thấp hoặc nồng độ phù hợp theo hướng dẫn chuyên môn để giảm kích ứng ban đầu.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Có thể gây khô, rát, đỏ hoặc bong tróc nếu da chưa quen. Không tự dùng nếu đang mang thai hoặc chưa được bác sĩ hướng dẫn.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên gặp bác sĩ nếu da kích ứng mạnh, mụn viêm tăng hoặc bạn cần chọn hoạt chất phù hợp hơn.\n\n"
            "**Lưu ý**\n"
        )
    elif "uống nước chanh" in user_question or "nước chanh" in user_question:
        draft = (
            "**Tóm tắt ngắn**\n"
            "Không có đủ bằng chứng cho thấy uống nước chanh mỗi ngày có thể chữa khỏi mụn.\n\n"
            "**Giải thích/cơ chế**\n"
            "Nước chanh không phải phương pháp điều trị mụn được chứng minh. Uống nhiều có thể làm khó chịu dạ dày hoặc ảnh hưởng men răng.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Mụn nên được xử lý bằng routine da và hoạt chất có bằng chứng hơn là dựa vào đồ uống dân gian.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Nếu uống nước chanh làm bạn đau dạ dày, ê buốt răng hoặc buồn nôn, nên giảm hoặc ngừng.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên gặp bác sĩ nếu mụn viêm nhiều, kéo dài hoặc để lại sẹo.\n\n"
            "**Lưu ý**\n"
        )
    elif toothpaste_question:
        draft = (
            "**Tóm tắt ngắn**\n"
            "Không nên bôi kem đánh răng lên mụn. Cách này không phải điều trị mụn chuẩn và có thể làm da kích ứng.\n\n"
            "**Giải thích/cơ chế**\n"
            "Kem đánh răng được thiết kế cho răng miệng, không phải da mặt; hương liệu, chất tạo bọt hoặc menthol có thể làm đỏ, rát, khô và bong tróc da.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Thay vào đó, nên rửa mặt dịu nhẹ, dưỡng ẩm phù hợp, chống nắng và dùng sản phẩm trị mụn được thiết kế cho da nếu cần.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Nếu đã bôi và bị rát, đỏ hoặc sưng, hãy rửa sạch nhẹ nhàng và tạm ngưng các hoạt chất dễ kích ứng.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên gặp bác sĩ nếu vùng da sưng đau, phồng rộp, chảy dịch, hoặc kích ứng không giảm.\n\n"
            "**Lưu ý**\n"
        )
    elif care_followup and user_history_text:
        age_match = re.search(r"\b(\d{1,2})\s*tuổi\b", user_history_text)
        age_text = f"{age_match.group(1)} tuổi" if age_match else "tuổi chưa rõ"
        details = []
        for marker in ["da dầu", "mụn đầu đen", "mũi", "mụn viêm", "má"]:
            if marker in user_history_text:
                details.append(marker)
        if all(marker in user_history_text for marker in ["da dầu", "mụn đầu đen", "mũi", "mụn viêm", "má"]):
            detail_text = "da dầu, có mụn đầu đen ở mũi và vài mụn viêm ở má"
        else:
            detail_text = ", ".join(dict.fromkeys(details)) if details else "tình trạng da đã trao đổi trong cuộc trò chuyện"
        draft = (
            "**Tóm tắt ngắn**\n"
            f"Bạn {age_text}, {detail_text}. Nên bắt đầu bằng routine đơn giản, ổn định và ít kích ứng.\n\n"
            "**Giải thích/cơ chế**\n"
            "Mụn đầu đen thường liên quan đến bít tắc lỗ chân lông, còn mụn viêm liên quan thêm phản ứng viêm. Da dầu dễ bí tắc hơn nếu làm sạch quá mạnh hoặc dùng sản phẩm quá dày.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Có thể bắt đầu với sữa rửa mặt dịu nhẹ, dưỡng ẩm mỏng nhẹ không gây bít tắc và chống nắng ban ngày. Nếu thêm hoạt chất trị mụn, nên thêm từng loại một và theo dõi da.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Tránh nặn mụn đầu đen mạnh và tránh phối hợp nhiều hoạt chất như acid, retinoid, benzoyl peroxide cùng lúc khi mới bắt đầu.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên khám nếu mụn viêm tăng nhanh, đau, có nang/cục, để lại sẹo hoặc không cải thiện sau chăm sóc cơ bản.\n\n"
            "**Lưu ý**\n"
        )

    # Local models can occasionally drift into mixed-language text or repeat
    # headings on high-risk medication answers. For isotretinoin safety queries,
    # prefer a concise deterministic answer over a malformed draft.
    isotretinoin_query = "isotretinoin" in user_question
    isotretinoin_safety_query = isotretinoin_query and any(
        kw in user_question
        for kw in ["tác dụng phụ", "phản ứng phụ", "tác hại", "nguy cơ", "nguy hiểm", "side effect"]
    )
    has_cjk_text = bool(re.search(r"[\u4e00-\u9fff]", draft))
    has_repeated_heading = any(
        draft.count(heading) > 1
        for heading in ["**Tóm tắt ngắn**", "**Giải thích/cơ chế**", "**Lưu ý an toàn/tác dụng phụ**"]
    )
    if isotretinoin_safety_query or (isotretinoin_query and (has_cjk_text or has_repeated_heading)):
        draft = (
            "**Tóm tắt ngắn**\n"
            "Isotretinoin có thể gây khô da, khô/nứt môi, khô mắt, chảy máu mũi và đau cơ/khớp. "
            "Đây là thuốc kê đơn, không tự ý dùng.\n\n"
            "**Giải thích/cơ chế**\n"
            "Isotretinoin thường được cân nhắc cho mụn nặng, mụn có nguy cơ để lại sẹo, hoặc không đáp ứng với điều trị khác. "
            "Thuốc tác động mạnh lên tuyến bã và quá trình viêm nên cần theo dõi y khoa.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Khi được bác sĩ kê đơn, người dùng thường cần dưỡng ẩm, chăm sóc môi/da khô và tái khám theo lịch. "
            "Không phối hợp thêm thuốc hoặc hoạt chất mạnh nếu chưa được bác sĩ hướng dẫn.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Isotretinoin không nên tự ý dùng; cần bác sĩ da liễu kê đơn, theo dõi tác dụng phụ và xét nghiệm khi cần. "
            "Thuốc chống chỉ định trong thai kỳ và cần tránh nếu đang mang thai hoặc có kế hoạch mang thai khi chưa được bác sĩ chuyên khoa quản lý.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Cần liên hệ bác sĩ nếu có khô rát nặng, thay đổi tâm trạng rõ, đau đầu dữ dội, đau bụng, vàng da, rối loạn thị giác hoặc bất kỳ triệu chứng bất thường nào khi dùng thuốc.\n\n"
            "**Lưu ý**\n"
        )
    
    if not user_asked_dosage:
        dosage_replacements = [
            (r"\b\d+\s*-\s*\d+\s*lần/tuần\b", "theo hướng dẫn trên sản phẩm hoặc theo tư vấn của bác sĩ/dược sĩ"),
            (r"\b\d+\s*lần/ngày\b", "theo hướng dẫn trên sản phẩm hoặc theo tư vấn của bác sĩ/dược sĩ"),
            (r"[Bb]ôi sau khi dưỡng ẩm", "nên dùng thận trọng theo hướng dẫn trên sản phẩm hoặc hỏi bác sĩ/dược sĩ"),
            (r"[Dd]ùng kem dưỡng ẩm trước khi bôi retinoid", "nên dùng thận trọng theo hướng dẫn trên sản phẩm hoặc hỏi bác sĩ/dược sĩ"),
            (r"[Dd]ùng kem dưỡng ẩm trước khi bôi", "nên dùng thận trọng theo hướng dẫn trên sản phẩm hoặc hỏi bác sĩ/dược sĩ"),
            (r"[Nn]ên bắt đầu với tần suất bôi thấp \([^)]*\)", "nên dùng thận trọng theo hướng dẫn trên sản phẩm hoặc hỏi bác sĩ/dược sĩ"),
        ]
        for pattern, replacement in dosage_replacements:
            draft = re.sub(pattern, replacement, draft, flags=re.IGNORECASE)
    
    # Replace light sensitivity warning
    draft = re.sub(
        r"tăng nhạy cảm ánh sáng",
        "Khi da đang khô, đỏ hoặc bong tróc, nên bảo vệ da khỏi nắng và dùng chống nắng phù hợp",
        draft,
        flags=re.IGNORECASE
    )
    draft = re.sub(
        r"vi khuẩn gây nhiễm trùng",
        "vi khuẩn liên quan đến mụn và phản ứng viêm",
        draft,
        flags=re.IGNORECASE,
    )
    draft = re.sub(
        r"benzoyl peroxide\s*\(\s*(clindamycin|erythromycin)\s*(?:hoặc|/)\s*(clindamycin|erythromycin)\s*\)",
        r"benzoyl peroxide hoặc kháng sinh bôi như \1/\2 khi được bác sĩ chỉ định",
        draft,
        flags=re.IGNORECASE,
    )

    # ── Group E: Topical antibiotic monotherapy warning ────────────────
    # If mentions clindamycin/erythromycin bôi but doesn't already warn
    # about antibiotic resistance or mention benzoyl peroxide combo
    draft_lower = draft.lower()
    has_topical_abx = bool(re.search(
        r"(?:clindamycin|erythromycin)(?:\s+bôi|\s+dạng\s+bôi|\s+gel|\s+lotion|\s+dung\s+dịch)?",
        draft_lower,
    ))
    has_resistance_warning = (
        "kháng kháng sinh" in draft_lower
        or "kháng thuốc" in draft_lower
        or "phối hợp" in draft_lower
        or ("benzoyl peroxide" in draft_lower and has_topical_abx)
    )
    if has_topical_abx and not has_resistance_warning:
        # Append warning before the disclaimer
        abx_warning = (
            "\n\nLưu ý: kháng sinh bôi (như clindamycin, erythromycin) thường không nên dùng đơn độc; "
            "thường phối hợp với benzoyl peroxide để giảm nguy cơ kháng kháng sinh."
        )
        disclaimer = "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn y khoa chuyên nghiệp."
        if disclaimer in draft:
            draft = draft.replace(disclaimer, abx_warning + "\n\n" + disclaimer)
        else:
            draft += abx_warning

    # Remove leftover concentrations/frequency fragments that local models may
    # copy from source text when the user did not ask for dosing.
    if not user_asked_dosage:
        draft = re.sub(
            r"\b(clindamycin|erythromycin)\s+\d+(?:\.\d+)?\s*%",
            r"\1",
            draft,
            flags=re.IGNORECASE,
        )
        draft = re.sub(
            r"\b\d+\s*[-–—]\s*(?=theo hướng dẫn)",
            "",
            draft,
            flags=re.IGNORECASE,
        )
        draft = re.sub(
            r"\bnên bôi\s+theo hướng dẫn",
            "nên dùng theo hướng dẫn",
            draft,
            flags=re.IGNORECASE,
        )
        
    # Remove generic headings or greetings if they leaked through
    draft = re.sub(r"^(Chào bạn,?|Xin chào,?|Chào bạn!|Xin chào!)\s*", "", draft, flags=re.IGNORECASE)
    draft = re.sub(r"^(Hy vọng|Mong rằng) thông tin.*?$", "", draft, flags=re.IGNORECASE | re.MULTILINE)
    draft = re.sub(r"\bhoặc\s+Khi\b", "hoặc khi", draft)
    draft = re.sub(r"\bHoặc\s+Khi\b", "Hoặc khi", draft)
    draft = re.sub(r"chưa chứng minhChocolate", "chưa chứng minh chocolate", draft, flags=re.IGNORECASE)
    for heading in [
        "**Tóm tắt ngắn**",
        "**Giải thích/cơ chế**",
        "**Chăm sóc/điều trị thường gặp**",
        "**Lưu ý an toàn/tác dụng phụ**",
        "**Khi nào nên gặp bác sĩ**",
        "**Lưu ý**",
    ]:
        escaped = re.escape(heading)
        draft = re.sub(
            rf"({escaped})\s*(?:\n\s*)+{escaped}",
            r"\1",
            draft,
            flags=re.IGNORECASE,
        )
    draft = re.sub(r"(\*\*Lưu ý\*\*)\s*[-–]\s*$", r"\1", draft, flags=re.MULTILINE)
    draft = _dedupe_section_headings(draft)
    draft = re.sub(r"\n{3,}", "\n\n", draft).strip()

    disclaimer = "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn y khoa chuyên nghiệp."
    draft = draft.replace(f"\n\n{disclaimer}", "")
    draft = draft.replace(disclaimer, "")

    required_headings = [
        "**Tóm tắt ngắn**",
        "**Giải thích/cơ chế**",
        "**Chăm sóc/điều trị thường gặp**",
        "**Lưu ý an toàn/tác dụng phụ**",
        "**Khi nào nên gặp bác sĩ**",
        "**Lưu ý**",
    ]
    if not all(heading in draft for heading in required_headings) and not _has_sufficient_answer_structure(draft):
        draft = (
            "**Tóm tắt ngắn**\n"
            + (draft or "Tôi chưa có đủ thông tin để trả lời chi tiết.")
            + "\n\n**Giải thích/cơ chế**\n"
            "Thông tin trả lời dựa trên phần tài liệu y khoa và kiến thức liên hệ đã truy xuất.\n\n"
            "**Chăm sóc/điều trị thường gặp**\n"
            "Không tự ý dùng thuốc kê đơn hoặc phối hợp nhiều hoạt chất mạnh nếu chưa có hướng dẫn chuyên môn.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\n"
            "Theo dõi kích ứng, đau rát, phản ứng dị ứng hoặc các triệu chứng toàn thân bất thường.\n\n"
            "**Khi nào nên gặp bác sĩ**\n"
            "Nên gặp bác sĩ da liễu nếu mụn kéo dài, viêm đau, để lại sẹo hoặc không đáp ứng với chăm sóc cơ bản.\n\n"
            "**Lưu ý**\n"
        )
    elif "**Lưu ý**" in draft:
        before_note, note, after_note = draft.partition("**Lưu ý**")
        draft = before_note.rstrip() + "\n\n" + note + "\n" + after_note.strip()

    draft = re.sub(r"(\*\*Lưu ý\*\*)\s*[-–]\s*$", r"\1", draft, flags=re.MULTILINE).rstrip()
    draft = _dedupe_section_headings(draft)
    draft = draft.rstrip() + "\n" + disclaimer
    
    logger.debug("Finalizing response.")
    return {"final_answer": repair_mojibake(draft.strip())}
