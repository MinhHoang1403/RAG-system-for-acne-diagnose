"""
src/agent/nodes/reason.py
=========================
LangGraph nodes for safety checks and reasoning (generating answers).
"""

import logging
import re
from typing import Any

from src.agent.state import ClinicalState

logger = logging.getLogger(__name__)


async def safety_check_node(state: ClinicalState) -> dict:
    """Check the query and contexts for safety issues (e.g., severe conditions)."""
    question = state.get("normalized_question", "")
    symptoms = state.get("symptoms", [])
    
    flags = []
    
    # Simple rule-based safety check for Phase 2
    severe_keywords = ["chảy máu", "nhiễm trùng", "mủ nhiều", "sốt", "đau nhức dữ dội"]
    for kw in severe_keywords:
        if kw in question:
            flags.append(f"Cảnh báo: Có dấu hiệu nghiêm trọng ({kw}).")

    emergency_keywords = ["đau ngực", "khó thở", "tức ngực", "ngất", "choáng", "sốc phản vệ"]
    for kw in emergency_keywords:
        if kw in question:
            flags.append(
                f"Cảnh báo khẩn cấp: {kw} không phải triệu chứng điển hình của mụn; "
                "nên đi cấp cứu hoặc liên hệ cơ sở y tế ngay nếu triệu chứng đang xảy ra."
            )

    # ── Retinoid + Pregnancy safety flags ─────────────────────────────
    question_lower = question.lower()
    retinoid_keywords = [
        "isotretinoin", "tretinoin", "retinoid",
        "adapalene", "adapalen",
        "tazarotene", "tazaroten",
    ]
    pregnancy_keywords = [
        "mang thai", "có thai", "có bầu",
        "chuẩn bị mang thai", "kế hoạch mang thai",
        "pregnancy", "pregnant",
    ]
    has_retinoid = any(kw in question_lower for kw in retinoid_keywords)
    has_pregnancy = any(kw in question_lower for kw in pregnancy_keywords)

    if has_retinoid and has_pregnancy:
        # Find which retinoid was mentioned for a specific warning
        matched_retinoid = next(
            (kw for kw in retinoid_keywords if kw in question_lower),
            "retinoid",
        )
        flags.append(
            f"Cảnh báo nghiêm trọng: {matched_retinoid.capitalize()} cần tránh "
            f"hoặc chỉ dùng dưới sự giám sát chặt chẽ của bác sĩ chuyên khoa "
            f"trong thai kỳ hoặc khi có kế hoạch mang thai."
        )

    logger.debug(f"Safety flags: {flags}")
    return {"safety_flags": flags}


import os
from src.agent.llm.provider import generate_llm_response


def _is_reference_context(ctx: dict[str, Any]) -> bool:
    header = str(ctx.get("header") or ctx.get("parent_header_path") or "").lower()
    role = str(ctx.get("context_role") or "").lower()
    content_type = ctx.get("content_type", [])
    if isinstance(content_type, str):
        content_type = [content_type]
    content_type_text = " ".join(str(item).lower() for item in content_type)
    markers = ("references", "reference", "bibliography", "tài liệu tham khảo", "tham khảo")
    return role == "reference" or any(marker in header or marker in content_type_text for marker in markers)


_LOW_VALUE_SECTION_MARKERS = (
    "abbreviations",
    "abbreviation",
    "references",
    "reference",
    "bibliography",
    "funding",
    "acknowledgements",
    "acknowledgments",
    "table of contents",
    "contents",
    "author",
    "correspondence",
    "tài liệu tham khảo",
    "mục lục",
)

_CLINICAL_SECTION_MARKERS = (
    "recommendation",
    "management",
    "treatment",
    "therapy",
    "safety",
    "adverse",
    "side effect",
    "contraindication",
    "pregnancy",
    "maintenance",
    "skin care",
    "referral",
    "cơ chế",
    "điều trị",
    "tác dụng phụ",
    "chống chỉ định",
    "chăm sóc",
    "khuyến cáo",
    "chuyển tuyến",
)

_DOCUMENT_CODE_RE = re.compile(r"^(?:ng\s*198|ng198|nice\s*ng\s*198|aad\s*2024|\d{2,})$", re.IGNORECASE)


def _context_header_text(ctx: dict[str, Any]) -> str:
    return str(
        ctx.get("header")
        or ctx.get("parent_header_path")
        or ctx.get("section")
        or ""
    ).lower()


def _context_text(ctx: dict[str, Any]) -> str:
    return str(ctx.get("text") or ctx.get("content") or ctx.get("page_content") or "")


def _is_low_value_context(ctx: dict[str, Any]) -> bool:
    header = _context_header_text(ctx)
    text = _context_text(ctx).strip()
    if any(marker in header for marker in _LOW_VALUE_SECTION_MARKERS):
        return True
    if len(text) < 80 and re.search(r"\b[A-Z]{2,8}\s*[:=]\s*[A-Za-z][A-Za-z\s-]{2,40}$", text):
        return True
    return False


def _is_bp_antibiotic_identity_query(query: str) -> bool:
    query_lower = query.lower()
    has_bp = bool(re.search(r"\bbenzoyl\s+peroxide\b|\bbp\b", query_lower))
    asks_antibiotic_identity = any(
        marker in query_lower
        for marker in [
            "có phải kháng sinh không",
            "phải kháng sinh không",
            "là kháng sinh không",
            "is benzoyl peroxide an antibiotic",
            "is bp an antibiotic",
        ]
    )
    return has_bp and asks_antibiotic_identity


def _context_quality_score(ctx: dict[str, Any], query: str = "") -> float:
    score = float(ctx.get("score") or ctx.get("boosted_score") or 0.0)
    header = _context_header_text(ctx)
    text = _context_text(ctx)
    text_lower = text.lower()
    query_lower = query.lower()

    if _is_low_value_context(ctx):
        score -= 0.35
    if _is_reference_context(ctx):
        score -= 0.25
    if any(marker in header or marker in text_lower[:500] for marker in _CLINICAL_SECTION_MARKERS):
        score += 0.20
    if len(text.strip()) >= 250:
        score += 0.05
    if _is_bp_antibiotic_identity_query(query_lower):
        has_bp = "benzoyl peroxide" in text_lower or re.search(r"\bbp\b", text_lower)
        has_direct_antibiotic_contrast = any(
            marker in text_lower
            for marker in [
                "does not contain antibiotics",
                "not an antibiotic",
                "không phải kháng sinh",
                "benzoyl peroxide",
                "kháng sinh bôi tại chỗ",
                "dùng dạng phối hợp với bp",
            ]
        )
        mentions_oral_antibiotics = any(
            marker in text_lower
            for marker in ["oral antibiotic", "kháng sinh uống", "kháng sinh đường uống", "doxycycline", "lymecycline", "minocycline"]
        )
        if has_bp and has_direct_antibiotic_contrast:
            score += 0.45
        if mentions_oral_antibiotics and not has_bp:
            score -= 0.45
    return score


def _select_answer_contexts(contexts: list[dict[str, Any]], limit: int = 5, query: str = "") -> list[dict[str, Any]]:
    """Select prompt contexts, preferring clinical chunks over abbreviations/references."""
    if not contexts:
        return []
    ranked = sorted(
        (dict(ctx) for ctx in contexts),
        key=lambda ctx: _context_quality_score(ctx, query=query),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    low_value_fallback: list[dict[str, Any]] = []
    for ctx in ranked:
        if _is_low_value_context(ctx) or _is_reference_context(ctx):
            ctx["context_role"] = "supporting"
            low_value_fallback.append(ctx)
            continue
        ctx["context_role"] = "main"
        selected.append(ctx)
        if len(selected) >= limit:
            return selected
    selected.extend(low_value_fallback[: max(0, limit - len(selected))])
    return selected[:limit]


def _tokenize_terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-ZÀ-ỹ0-9][a-zA-ZÀ-ỹ0-9_.-]{2,}", text.lower())
        if token not in {"the", "and", "for", "with", "trong", "của", "với", "này"}
    }


def _is_bad_entity_name(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text or len(text) < 3:
        return True
    if _DOCUMENT_CODE_RE.match(text):
        return True
    if text.isdigit():
        return True
    return False


def _is_mechanism_or_bacteria(value: str) -> bool:
    text = value.lower()
    markers = (
        "c. acnes",
        "cutibacterium",
        "propionibacterium",
        "vi khuẩn",
        "bacteria",
        "sebum",
        "bã nhờn",
        "comedogenesis",
        "keratin",
        "inflammation",
        "viêm",
        "pathogenesis",
    )
    return any(marker in text for marker in markers)


def filter_graph_facts_for_prompt(
    query: str,
    contexts: list[dict[str, Any]],
    graph_facts: list[dict[str, Any]],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Filter noisy Neo4j facts before they are allowed into the LLM prompt."""
    if not graph_facts:
        return []

    context_text = " ".join(_context_text(ctx) for ctx in contexts).lower()
    graph_node_terms: set[str] = set()
    for ctx in contexts:
        nodes = ctx.get("graph_nodes", [])
        if isinstance(nodes, list):
            graph_node_terms.update(str(node).lower() for node in nodes if node)

    query_terms = _tokenize_terms(query)
    ranked: list[tuple[float, dict[str, Any]]] = []
    seen: set[tuple[str, str, str]] = set()

    for fact in graph_facts:
        entity = str(fact.get("entity") or "").strip()
        related = str(fact.get("related_entity") or "").strip()
        rel = str(fact.get("relationship") or "").strip().upper()
        description = str(fact.get("description") or "").strip()
        related_description = str(fact.get("related_description") or "").strip()
        evidence = str(fact.get("evidence") or "").strip()

        if _is_bad_entity_name(entity) or (related and _is_bad_entity_name(related)):
            continue
        if not evidence and not description and not related_description:
            continue
        if rel == "TREATS" and (_is_mechanism_or_bacteria(entity) or _is_mechanism_or_bacteria(related)):
            if entity.lower() not in context_text and related.lower() not in context_text:
                continue

        key = (entity.lower(), rel, related.lower())
        if key in seen:
            continue
        seen.add(key)

        fact_terms = _tokenize_terms(f"{entity} {related} {description} {related_description} {evidence}")
        overlap = len(fact_terms & query_terms)
        node_overlap = int(entity.lower() in graph_node_terms or related.lower() in graph_node_terms)
        evidence_bonus = 0.5 if evidence else 0.0
        ranked.append((overlap + node_overlap + evidence_bonus, fact))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [fact for _, fact in ranked[:limit]]

async def generate_answer_node(state: ClinicalState) -> dict:
    """Generate the answer based on vector contexts and graph facts using LLM."""
    question = state.get("user_question", "")
    contexts = state.get("vector_contexts", [])
    graph_facts = state.get("graph_facts", [])
    safety_flags = state.get("safety_flags", [])
    symptoms = state.get("symptoms", [])
    conversation_history = state.get("conversation_history", [])
    prompt_history = conversation_history if state.get("use_history_context") else []
    ignored_out_of_domain_part = state.get("ignored_out_of_domain_part", False)
    
    if state.get("is_in_domain") is False:
        logger.debug("Domain guardrail triggered. Skipping LLM generation.")
        return {}
        
    try:
        from src.agent.prompts.medical_answer import build_medical_prompt

        answer_contexts = _select_answer_contexts(contexts, limit=5, query=question)
        prompt_graph_facts = filter_graph_facts_for_prompt(
            query=question,
            contexts=answer_contexts,
            graph_facts=graph_facts,
            limit=10,
        )
        
        prompt = build_medical_prompt(
            question=question,
            symptoms=symptoms,
            safety_flags=safety_flags,
            contexts=answer_contexts,
            graph_facts=prompt_graph_facts,
            conversation_history=prompt_history,
            ignored_out_of_domain_part=ignored_out_of_domain_part
        )
        
        llm_provider = state.get("llm_provider", "gemini")
        llm_model = state.get("llm_model")
        allow_model_fallback = state.get("allow_model_fallback", True)
        
        logger.info(f"Generating answer with LLM: provider={llm_provider}, model={llm_model}")
        
        response_data = await generate_llm_response(
            prompt=prompt,
            provider=llm_provider,
            model=llm_model,
            temperature=0.2,
            allow_fallback=allow_model_fallback
        )
        
        draft = response_data["text"]
        logger.info("LLM generation successful.")
        
        return {
            "draft_answer": draft,
            "sources": list(dict.fromkeys(
                ctx.get("source_file", "")
                for ctx in answer_contexts
                if ctx.get("source_file")
            ))[:2] or state.get("sources", [])[:2],
            "actual_provider": response_data["provider"],
            "actual_model": response_data["model"],
            "llm_fallback_used": response_data["fallback_used"],
            "fallback_provider": response_data["fallback_provider"],
            "fallback_model": response_data["fallback_model"]
        }
        
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        # Set llm_fallback metadata
        state["llm_fallback"] = True
        state["fallback_reason"] = "quota_or_generation_error"
        state["llm_fallback_used"] = True
        
        # Fallback to rule-based safe answer instead of raw context
        query_lower = question.lower()
        standalone = (state.get("standalone_question") or "").lower()
        
        # Build combined text from history for entity detection
        history_text = ""
        for msg in prompt_history:
            history_text += " " + msg.get("content", "").lower()
        combined_context = query_lower + " " + standalone + " " + history_text
        
        # Detect side-effects questions about benzoyl peroxide
        side_effect_keywords = ["tác dụng phụ", "kích ứng", "tác hại", "phản ứng phụ", "ảnh hưởng", "nguy hiểm"]
        has_side_effect_question = any(kw in query_lower or kw in standalone for kw in side_effect_keywords)
        has_bp_entity = "benzoyl peroxide" in combined_context or "bp " in combined_context
        
        if any(kw in query_lower for kw in ["đau ngực", "khó thở", "tức ngực"]):
            draft = (
                "**Tóm tắt ngắn**\n"
                "Đau ngực hoặc khó thở không phải biểu hiện điển hình của mụn. Nếu triệu chứng đang xảy ra, bạn nên đi cấp cứu hoặc liên hệ cơ sở y tế ngay.\n\n"
                "**Giải thích/cơ chế**\n"
                "Mụn thường gây tổn thương tại da như nhân mụn, sẩn viêm, mụn mủ hoặc đau tại vùng da bị viêm, không giải thích được triệu chứng hô hấp hoặc đau ngực.\n\n"
                "**Chăm sóc/điều trị thường gặp**\n"
                "Tạm thời không tự quy triệu chứng toàn thân này cho mụn hoặc thuốc trị mụn. Hãy ưu tiên đánh giá y tế trực tiếp trước.\n\n"
                "**Lưu ý an toàn/tác dụng phụ**\n"
                "Nếu đau ngực, khó thở, choáng, ngất, tím tái, nổi mề đay lan rộng hoặc sưng môi/mặt, cần xử trí khẩn cấp.\n\n"
                "**Khi nào nên gặp bác sĩ**\n"
                "Nên đi cấp cứu ngay nếu đau ngực hoặc khó thở còn tiếp diễn, nặng lên, hoặc xuất hiện sau khi dùng thuốc/sản phẩm mới.\n\n"
                "**Lưu ý**\n"
                "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn y khoa chuyên nghiệp."
            )
        elif "mụn đầu đen" in query_lower:
            draft = (
                "**Tóm tắt ngắn**\n"
                "Mụn đầu đen thường liên quan đến bít tắc lỗ chân lông và oxy hóa chất bã trong nhân mụn.\n\n"
                "**Giải thích/cơ chế**\n"
                "Đây thường là dạng mụn không viêm, nên mục tiêu chính là làm sạch dịu nhẹ, giảm bít tắc và hạn chế kích thích da.\n\n"
                "**Chăm sóc/điều trị thường gặp**\n"
                "Có thể duy trì sữa rửa mặt dịu nhẹ, dưỡng ẩm phù hợp và chống nắng. Một số hoạt chất như salicylic acid hoặc retinoid bôi có thể được cân nhắc, nhưng nên bắt đầu thận trọng nếu da nhạy cảm.\n\n"
                "**Lưu ý an toàn/tác dụng phụ**\n"
                "Không nên nặn mạnh vì dễ gây viêm, thâm hoặc sẹo. Nếu dùng hoạt chất, theo dõi khô rát, bong tróc hoặc kích ứng.\n\n"
                "**Khi nào nên gặp bác sĩ**\n"
                "Nên gặp bác sĩ da liễu nếu mụn lan rộng, viêm đau, để lại thâm/sẹo hoặc không cải thiện sau chăm sóc cơ bản.\n\n"
                "**Lưu ý**\n"
                "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn y khoa chuyên nghiệp."
            )
        elif has_side_effect_question and has_bp_entity:
            draft = (
                "**Tóm tắt ngắn**\n"
                "Benzoyl peroxide có thể hỗ trợ mụn nhờ tác dụng kháng khuẩn và giảm bít tắc, nhưng dễ gây kích ứng ở một số người.\n\n"
                "**Giải thích/cơ chế**\n"
                "Hoạt chất này tác động lên vi khuẩn liên quan đến mụn và quá trình hình thành nhân mụn.\n\n"
                "**Chăm sóc/điều trị thường gặp**\n"
                "Khi dùng sản phẩm chứa benzoyl peroxide, nên theo dõi đáp ứng da và tránh phối hợp quá nhiều hoạt chất kích ứng cùng lúc nếu chưa có hướng dẫn.\n\n"
                "**Lưu ý an toàn/tác dụng phụ**\n"
                "Tác dụng phụ thường gặp gồm khô, đỏ, châm chích, nóng rát, bong tróc hoặc ngứa. Hoạt chất này cũng có thể làm bạc màu vải, khăn, áo gối hoặc tóc.\n\n"
                "**Khi nào nên gặp bác sĩ**\n"
                "Ngừng dùng và đi khám nếu kích ứng nặng, đau rát dữ dội, sưng môi/mặt, khó thở hoặc nổi mề đay lan rộng.\n\n"
                "**Lưu ý**\n"
                "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn y khoa chuyên nghiệp."
            )
        elif "benzoyl peroxide" in query_lower or "benzoyl peroxide" in standalone:
            draft = (
                "**Tóm tắt ngắn**\n"
                "Benzoyl peroxide là hoạt chất thường được nhắc đến trong chăm sóc và điều trị mụn, đặc biệt mụn viêm.\n\n"
                "**Giải thích/cơ chế**\n"
                "Nó có tác dụng kháng khuẩn và hỗ trợ giảm bít tắc nang lông, từ đó có thể giảm tổn thương mụn ở một số trường hợp.\n\n"
                "**Chăm sóc/điều trị thường gặp**\n"
                "Có thể gặp benzoyl peroxide trong sản phẩm bôi trị mụn, đôi khi được phối hợp với hoạt chất khác theo hướng dẫn chuyên môn.\n\n"
                "**Lưu ý an toàn/tác dụng phụ**\n"
                "Hoạt chất này có thể gây khô, đỏ, châm chích, bong tróc hoặc kích ứng, và có thể làm bạc màu vải.\n\n"
                "**Khi nào nên gặp bác sĩ**\n"
                "Nên gặp bác sĩ nếu mụn viêm nhiều, đau, để lại sẹo, không cải thiện hoặc da kích ứng nặng khi dùng sản phẩm.\n\n"
                "**Lưu ý**\n"
                "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn y khoa chuyên nghiệp."
            )
        else:
            draft = (
                "**Tóm tắt ngắn**\n"
                "Mụn nên được chăm sóc theo hướng giảm bít tắc, giảm viêm và hạn chế kích ứng da.\n\n"
                "**Giải thích/cơ chế**\n"
                "Mụn có thể liên quan đến tăng tiết bã, bít tắc nang lông, vi khuẩn liên quan đến mụn và phản ứng viêm.\n\n"
                "**Chăm sóc/điều trị thường gặp**\n"
                "Có thể bắt đầu bằng làm sạch dịu nhẹ, dưỡng ẩm phù hợp, chống nắng và tránh nặn mụn. Thuốc/hoạt chất trị mụn nên chọn theo tình trạng da và mức độ mụn.\n\n"
                "**Lưu ý an toàn/tác dụng phụ**\n"
                "Không nên tự phối hợp nhiều hoạt chất mạnh hoặc dùng thuốc kê đơn khi chưa có hướng dẫn. Theo dõi khô rát, đỏ, bong tróc hoặc kích ứng.\n\n"
                "**Khi nào nên gặp bác sĩ**\n"
                "Nên gặp bác sĩ da liễu nếu mụn đau, viêm nhiều, kéo dài, để lại sẹo/thâm hoặc ảnh hưởng nhiều đến sinh hoạt.\n\n"
                "**Lưu ý**\n"
                "Thông tin này chỉ mang tính tham khảo và không thay thế tư vấn y khoa chuyên nghiệp."
            )
            
        if safety_flags:
            draft = "**LƯU Ý AN TOÀN QUAN TRỌNG:**\n" + "\n".join([f"- {flag}" for flag in safety_flags]) + "\n\n" + draft
    
    logger.debug("Generated draft answer via rule-based fallback.")
    return {
        "draft_answer": draft,
        "actual_provider": state.get("llm_provider"),
        "actual_model": state.get("llm_model"),
        "llm_fallback_used": True,
        "fallback_provider": "rule_based",
        "fallback_model": "rule_based"
    }
