from __future__ import annotations

import pytest

from src.agent.answer_formatting import (
    ANSWER_FORMATTING_CONTRACT,
    ANSWER_FORMATTING_CONTRACT_VERSION,
    assess_structural_quality,
    answer_format_instruction_for_question,
    finalize_answer_presentation,
    normalize_answer_markdown,
    strip_leading_question_echo,
)
from src.agent.nodes import reason as reason_node
from src.agent.nodes.respond import finalize_response_node
from src.agent.prompts.medical_answer import build_medical_prompt
from src.quality.safe_fallback import build_safe_fallback_answer


def test_formatting_contract_avoids_mandatory_boilerplate_sections():
    prompt = build_medical_prompt(
        question="Differin thuộc nhóm thuốc gì?",
        symptoms=[],
        safety_flags=[],
        contexts=[{"text": "Differin contains adapalene, a topical retinoid.", "source_file": "doc.pdf"}],
        graph_facts=[],
    )

    assert ANSWER_FORMATTING_CONTRACT_VERSION == "answer_formatting_contract_v2"
    assert ANSWER_FORMATTING_CONTRACT in prompt
    assert "ANSWER PRESENTATION CONTRACT V2" in prompt
    assert "provider không được quyết định format" in prompt
    assert "3-5 đoạn ngắn gồm tóm tắt" not in prompt
    assert "Mục **Lưu ý** phải có câu" not in prompt


def test_comparison_prompt_requires_complete_entity_coverage_and_table_format():
    instruction = answer_format_instruction_for_question(
        "Mụn đầu đen và mụn đầu trắng khác nhau như thế nào?"
    )

    assert "CÂU SO SÁNH" in instruction
    assert "cover đầy đủ từng entity" in instruction
    assert "bảng Markdown GFM" in instruction


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Differin thuộc nhóm thuốc gì?", "CÂU YES/NO HOẶC ĐỊNH DANH"),
        ("Epiduo có BPO không?", "CÂU YES/NO HOẶC ĐỊNH DANH"),
        ("Tôi đang mang thai, có dùng adapalene được không?", "CÂU YES/NO HOẶC ĐỊNH DANH"),
        ("Tôi có nhiều cục mụn sâu, đau và bắt đầu để lại sẹo.", "CÂU AN TOÀN"),
    ],
)
def test_intent_specific_formatting_hints_cover_smoke_cases(question: str, expected: str):
    assert expected in answer_format_instruction_for_question(question)


def test_markdown_cleanup_removes_blank_lines_inside_tables_and_empty_headings():
    messy = (
        "| A | B |\n"
        "|---|---|\n"
        "\n"
        "| one | two |\n\n"
        "**Khi nào nên gặp bác sĩ**\n\n"
        "**Lưu ý**\n"
        "Thông tin mang tính tham khảo."
    )

    cleaned = normalize_answer_markdown(messy)

    assert "|---|---|\n| one | two |" in cleaned
    assert "**Khi nào nên gặp bác sĩ**" not in cleaned
    assert "**Lưu ý**" in cleaned


def test_markdown_cleanup_removes_leading_english_yes_marker():
    cleaned = normalize_answer_markdown("**Yes** Mụn đầu đen là một dạng mụn nhân mở.")

    assert cleaned == "Mụn đầu đen là một dạng mụn nhân mở."


@pytest.mark.asyncio
async def test_finalize_does_not_wrap_short_valid_answer_in_generic_template():
    result = await finalize_response_node(
        {
            "user_question": "Differin thuộc nhóm thuốc gì?",
            "draft_answer": "Differin chứa adapalene và thuộc nhóm retinoid bôi.",
            "conversation_history": [],
            "use_history_context": False,
            "is_in_domain": True,
        }
    )

    answer = result["final_answer"]
    assert answer.startswith("Differin thuộc nhóm retinoid bôi")
    assert "**Tóm tắt ngắn**" not in answer
    assert "Thông tin trả lời dựa trên phần tài liệu y khoa" not in answer
    assert answer.count("Thông tin mang tính tham khảo") == 1


@pytest.mark.asyncio
async def test_finalize_blackhead_whitehead_comparison_uses_table():
    result = await finalize_response_node(
        {
            "user_question": "Mụn đầu đen và mụn đầu trắng khác nhau như thế nào?",
            "draft_answer": "Mụn đầu đen là nhân mụn mở. Mụn đầu trắng là nhân mụn đóng.",
            "conversation_history": [],
            "use_history_context": False,
            "is_in_domain": True,
        }
    )

    answer = result["final_answer"]
    assert answer.startswith("Mụn đầu đen và mụn đầu trắng")
    assert "| Tiêu chí | Mụn đầu đen | Mụn đầu trắng |" in answer
    assert "**Tóm tắt ngắn**" not in answer


@pytest.mark.asyncio
async def test_finalize_differin_identity_removes_yes_prefix_and_stays_concise():
    result = await finalize_response_node(
        {
            "user_question": "Differin thuộc nhóm thuốc gì?",
            "draft_answer": "Có, Differin thuộc nhóm topical_retinoid.",
            "conversation_history": [],
            "use_history_context": False,
            "is_in_domain": True,
        }
    )

    answer = result["final_answer"]
    assert answer.startswith("Differin thuộc nhóm retinoid bôi")
    assert "Có, Differin" not in answer
    assert "adapalene" in answer
    assert "**Tóm tắt ngắn**" not in answer


@pytest.mark.asyncio
async def test_finalize_epiduo_composition_covers_both_ingredients():
    result = await finalize_response_node(
        {
            "user_question": "Epiduo có BPO không?",
            "draft_answer": "Có. Epiduo có benzoyl peroxide.",
            "conversation_history": [],
            "use_history_context": False,
            "is_in_domain": True,
        }
    )

    answer = result["final_answer"]
    assert answer.startswith("Có. Epiduo chứa")
    assert "adapalene" in answer
    assert "benzoyl peroxide" in answer
    assert "không phải kháng sinh" in answer


@pytest.mark.asyncio
async def test_finalize_pregnancy_safety_preserves_warning():
    result = await finalize_response_node(
        {
            "user_question": "Đang mang thai có dùng adapalene được không?",
            "draft_answer": "Có thể dùng adapalene nếu muốn.",
            "conversation_history": [],
            "use_history_context": False,
            "is_in_domain": True,
        }
    )

    answer = result["final_answer"]
    assert answer.startswith("Không nên dùng adapalene")
    assert "bác sĩ da liễu hoặc sản khoa" in answer
    assert answer.count("Thông tin mang tính tham khảo") == 1


@pytest.mark.asyncio
async def test_finalize_severe_acne_keeps_escalation():
    result = await finalize_response_node(
        {
            "user_question": "Tôi có nhiều cục mụn sâu, đau và đang để lại sẹo.",
            "draft_answer": (
                "Mụn cục sâu, đau và để lại sẹo là dấu hiệu cần được bác sĩ da liễu đánh giá sớm.\n\n"
                "Không tự nặn hoặc tự dùng isotretinoin/kháng sinh uống khi chưa được kê đơn."
            ),
            "conversation_history": [],
            "use_history_context": False,
            "is_in_domain": True,
        }
    )

    answer = result["final_answer"]
    assert "bác sĩ da liễu" in answer
    assert "sẹo" in answer
    assert "Không nặn" in answer
    assert "Thông tin trả lời dựa trên phần tài liệu y khoa" not in answer


def test_safe_fallback_format_is_short_and_not_cache_boilerplate():
    answer = build_safe_fallback_answer("insufficient_context")

    assert "Tài liệu hiện có chưa đủ bằng chứng" in answer
    assert answer.count("**Tóm tắt ngắn**") == 1
    assert "Thông tin trả lời dựa trên phần tài liệu y khoa" not in answer
    assert len(answer.split()) < 90


def test_strip_leading_question_echo_exact_and_partial():
    question = "Tôi có nhiều cục mụn sâu, đau, sưng đỏ và bắt đầu để lại sẹo. Tôi nên làm gì?"

    exact = strip_leading_question_echo(question + "\n\nBạn nên khám da liễu sớm.", question)
    partial = strip_leading_question_echo("Tôi nên làm gì?\nBạn nên khám da liễu sớm.", question)

    assert exact.startswith("Bạn nên khám")
    assert partial.startswith("Bạn nên khám")


def test_finalizer_removes_empty_heading_duplicate_disclaimer_and_legacy_template():
    answer = finalize_answer_presentation(
        (
            "**Tóm tắt ngắn**\nNên chăm sóc da dịu nhẹ.\n\n"
            "**Giải thích/cơ chế**\nMụn viêm liên quan phản ứng viêm.\n\n"
            "**Chăm sóc/điều trị thường gặp**\nRửa mặt nhẹ.\n\n"
            "**Lưu ý an toàn/tác dụng phụ**\nTheo dõi kích ứng.\n\n"
            "**Khi nào nên gặp bác sĩ**\n\n"
            "Thông tin mang tính tham khảo và không thay thế chẩn đoán của bác sĩ.\n\n"
            "Thông tin mang tính tham khảo và không thay thế chẩn đoán của bác sĩ."
        ),
        user_question="Mụn viêm nhẹ nên chăm sóc da hằng ngày như thế nào?",
        response_profile="treatment",
    )

    assert "**Tóm tắt ngắn**" not in answer
    assert "**Khi nào nên gặp bác sĩ**" not in answer
    assert answer.count("Thông tin mang tính tham khảo") == 1


def test_structural_quality_detects_incomplete_and_truncated_output():
    issues = assess_structural_quality(
        "Mụn viêm có thể làm da nhạy cảm với ánh nắng",
        user_question="Mụn viêm nhẹ nên chăm sóc da hằng ngày như thế nào?",
    )
    codes = {issue["code"] for issue in issues}

    assert "incomplete_terminal_sentence" in codes

    truncated = assess_structural_quality("Câu trả lời\n...[truncated_generation]", user_question="Mụn là gì?")
    assert "truncated_generation" in {issue["code"] for issue in truncated}


def test_non_boolean_composition_does_not_start_with_yes_prefix():
    answer = finalize_answer_presentation(
        "Có. Epiduo chứa adapalene và benzoyl peroxide.",
        user_question="Epiduo gồm những hoạt chất nào và mỗi hoạt chất có tác dụng gì?",
    )

    assert answer.startswith("Epiduo chứa hai hoạt chất")
    assert not answer.startswith("Có.")


def test_boolean_question_keeps_valid_yes_prefix():
    answer = finalize_answer_presentation(
        "Có. Epiduo chứa benzoyl peroxide.",
        user_question="Epiduo có BPO không?",
    )

    assert answer.startswith("Có.")


@pytest.mark.parametrize("provider", ["gemini", "ollama"])
@pytest.mark.asyncio
async def test_provider_generation_uses_same_formatting_contract(monkeypatch, provider: str):
    captured: dict[str, str] = {}

    async def fake_generate_llm_response(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return {
            "text": "Mụn đầu đen là nhân mụn mở; mụn đầu trắng là nhân mụn đóng.",
            "provider": provider,
            "model": "mock-model",
            "fallback_used": False,
            "fallback_provider": None,
            "fallback_model": None,
            "resilience": {"provider": provider},
        }

    monkeypatch.setattr(reason_node, "generate_llm_response", fake_generate_llm_response)

    await reason_node.generate_answer_node(
        {
            "user_question": "Mụn đầu đen và mụn đầu trắng khác nhau như thế nào?",
            "vector_contexts": [
                {
                    "text": "Blackheads are open comedones; whiteheads are closed comedones.",
                    "source_file": "doc.pdf",
                    "score": 0.9,
                }
            ],
            "graph_facts": [],
            "safety_flags": [],
            "symptoms": [],
            "conversation_history": [],
            "use_history_context": False,
            "ignored_out_of_domain_part": False,
            "is_in_domain": True,
            "llm_provider": provider,
            "llm_model": "mock-model",
            "allow_model_fallback": False,
        }
    )

    assert ANSWER_FORMATTING_CONTRACT in captured["prompt"]
    assert "bảng Markdown GFM" in captured["prompt"]
