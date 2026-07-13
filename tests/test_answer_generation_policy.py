"""
Tests for Phase 2 answer-generation policy without calling external LLMs.
"""

from __future__ import annotations

import pytest

from src.agent.graph import route_after_guard
from src.agent.nodes.respond import finalize_response_node
from src.agent.nodes.reason import _select_answer_contexts, filter_graph_facts_for_prompt
from src.agent.nodes.retrieve import rewrite_question_node
from src.agent.prompts.medical_answer import MEDICAL_RAG_SYSTEM_PROMPT


def test_medical_prompt_contains_required_medication_rules():
    prompt = MEDICAL_RAG_SYSTEM_PROMPT.lower()

    assert "benzoyl peroxide is not an antibiotic" in prompt
    assert "không khuyến cáo dùng kháng sinh bôi đơn trị liệu" in prompt
    assert "không kê liều cụ thể" in prompt
    assert "combined oral contraceptives" in prompt
    assert "spironolactone" in prompt
    assert "cần bác sĩ kê đơn/đánh giá" in prompt


def test_medical_prompt_contains_direct_answer_and_entity_preservation_rules():
    prompt = MEDICAL_RAG_SYSTEM_PROMPT.lower()

    assert "direct answer first" in prompt
    assert "primary entity preservation" in prompt
    assert "benzoyl peroxide không phải là kháng sinh" in prompt
    assert "không được viết \"có, ... không nên\"" in prompt
    assert "câu trả lời phải cover đầy đủ cả a và b" in prompt
    assert "ưu tiên bảng hoặc bullet đối chiếu" in prompt


def test_graph_fact_filter_removes_document_code_and_empty_fact():
    facts = [
        {
            "entity": "ng198",
            "relationship": "TREATS",
            "related_entity": "acne",
            "description": "guideline code",
            "evidence": "citation",
        },
        {
            "entity": "benzoyl peroxide",
            "relationship": "TREATS",
            "related_entity": "mụn trứng cá",
            "description": "",
            "evidence": "",
        },
        {
            "entity": "benzoyl peroxide",
            "relationship": "TREATS",
            "related_entity": "mụn trứng cá",
            "description": "Hoạt chất bôi trị mụn.",
            "evidence": "AAD recommendation",
        },
    ]

    filtered = filter_graph_facts_for_prompt(
        query="benzoyl peroxide trị mụn",
        contexts=[{"text": "benzoyl peroxide là hoạt chất bôi trị mụn.", "graph_nodes": ["benzoyl peroxide"]}],
        graph_facts=facts,
    )

    assert len(filtered) == 1
    assert filtered[0]["entity"] == "benzoyl peroxide"
    assert filtered[0]["evidence"] == "AAD recommendation"


def test_graph_fact_filter_removes_mechanism_treats_noise_without_context_support():
    facts = [
        {
            "entity": "C. acnes",
            "relationship": "TREATS",
            "related_entity": "mụn trứng cá",
            "description": "Noisy graph edge.",
            "evidence": "citation",
        }
    ]

    filtered = filter_graph_facts_for_prompt(
        query="cơ chế mụn",
        contexts=[{"text": "Mụn liên quan đến bít tắc nang lông và tăng tiết bã."}],
        graph_facts=facts,
    )

    assert filtered == []


def test_context_selection_prefers_clinical_chunk_over_abbreviation():
    contexts = [
        {
            "header": "Abbreviations",
            "text": "BP: benzoyl peroxide",
            "score": 0.99,
        },
        {
            "header": "Treatment recommendations",
            "text": "Benzoyl peroxide may be used as an acne treatment and can cause irritation.",
            "score": 0.75,
        },
    ]

    selected = _select_answer_contexts(contexts, limit=1)

    assert selected[0]["header"] == "Treatment recommendations"


def test_context_selection_prefers_bp_not_antibiotic_chunk_over_oral_antibiotics():
    contexts = [
        {
            "header": "Oral antibiotics",
            "text": "Oral antibiotics such as doxycycline may be used for acne in selected cases.",
            "score": 0.95,
        },
        {
            "header": "Benzoyl peroxide (BP)",
            "text": "Benzoyl peroxide (BP) does not contain antibiotics and may reduce antibiotic resistance.",
            "score": 0.70,
        },
    ]

    selected = _select_answer_contexts(
        contexts,
        limit=1,
        query="Benzoyl peroxide có phải kháng sinh không?",
    )

    assert selected[0]["header"] == "Benzoyl peroxide (BP)"


@pytest.mark.asyncio
async def test_finalize_bp_antibiotic_question_direct_answer_first():
    result = await finalize_response_node(
        {
            "user_question": "Benzoyl peroxide có phải kháng sinh không?",
            "draft_answer": "Không nên tự uống kháng sinh để trị mụn.",
            "conversation_history": [],
            "use_history_context": False,
            "is_in_domain": True,
        }
    )

    answer = result["final_answer"]
    assert answer.lower().startswith("không, benzoyl peroxide không phải là kháng sinh.")
    assert "benzoyl peroxide không phải là kháng sinh" in answer.lower()
    assert "Không nên tự uống kháng sinh" not in answer.splitlines()[0]


@pytest.mark.asyncio
async def test_finalize_clindamycin_monotherapy_polarity_is_no():
    result = await finalize_response_node(
        {
            "user_question": "Có nên dùng clindamycin đơn độc để trị mụn không?",
            "draft_answer": "Có, clindamycin không nên được dùng đơn độc để trị mụn theo tài liệu hiện có.",
            "conversation_history": [],
            "use_history_context": False,
            "is_in_domain": True,
        }
    )

    answer = result["final_answer"]
    assert answer.startswith("Không. Clindamycin không nên")
    assert "Có, clindamycin không nên" not in answer
    assert "**Tóm tắt ngắn**" not in answer


@pytest.mark.asyncio
async def test_finalize_adapalene_bp_comparison_covers_both_entities():
    result = await finalize_response_node(
        {
            "user_question": "Adapalene và benzoyl peroxide khác nhau thế nào?",
            "draft_answer": "Adapalene là retinoid bôi.",
            "conversation_history": [],
            "use_history_context": False,
            "is_in_domain": True,
        }
    )

    answer = result["final_answer"].lower()
    assert "adapalene" in answer
    assert "benzoyl peroxide" in answer
    assert "| tiêu chí | adapalene | benzoyl peroxide |" in answer
    assert "retinoid bôi" in answer
    assert "không phải kháng sinh" in answer
    assert "có thể được phối hợp" in answer
    assert "bạc màu" in answer
    assert "**khi nào nên gặp bác sĩ**" not in answer


@pytest.mark.asyncio
async def test_finalize_dedupes_duplicate_section_headers():
    result = await finalize_response_node(
        {
            "user_question": "Mụn viêm khi nào nên gặp bác sĩ?",
            "draft_answer": (
                "**Tóm tắt ngắn**\nNên gặp bác sĩ nếu mụn nặng.\n\n"
                "**Khi nào nên gặp bác sĩ**\nNếu mụn đau nhiều.\n\n"
                "**Khi nào nên gặp bác sĩ**\nNếu mụn kéo dài.\n\n"
                "**Lưu ý**\n"
            ),
            "conversation_history": [],
            "use_history_context": False,
            "is_in_domain": True,
        }
    )

    assert result["final_answer"].count("**Khi nào nên gặp bác sĩ**") == 0
    assert result["final_answer"].count("Nếu mụn đau nhiều.") == 1


@pytest.mark.asyncio
async def test_rewrite_preserves_explicit_primary_entity_with_history():
    result = await rewrite_question_node(
        {
            "user_question": "Benzoyl peroxide có phải kháng sinh không?",
            "normalized_question": "benzoyl peroxide có phải kháng sinh không?",
            "conversation_history": [{"role": "user", "content": "Tôi bị mụn viêm."}],
        }
    )

    assert result["standalone_question"] == "benzoyl peroxide có phải kháng sinh không?"
    assert result["use_history_context"] is False


def test_out_of_domain_guard_routes_to_finalize_without_retrieval():
    assert route_after_guard({"is_in_domain": False}) == "finalize"
