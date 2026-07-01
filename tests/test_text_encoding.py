"""
Tests for UTF-8 mojibake repair and prompt encoding.
"""

from __future__ import annotations

from src.agent.prompts.medical_answer import MEDICAL_RAG_SYSTEM_PROMPT
from src.agent.text_encoding import repair_mojibake


def test_repair_mojibake_vietnamese_examples():
    examples = {
        "TÃ³m táº¯t ngáº¯n": "Tóm tắt ngắn",
        "Äiá»u trá»": "Điều trị",
        "khÃ´ng kÃª ÄÆ¡n": "không kê đơn",
        "bÃ¡c sÄ© da liá»…u": "bác sĩ da liễu",
    }

    for broken, expected in examples.items():
        assert repair_mojibake(broken) == expected


def test_medical_prompt_has_no_common_mojibake_markers():
    markers = ("TÃ", "táº", "áº", "á»", "khÃ", "bÃ¡c", "LÆ")

    for marker in markers:
        assert marker not in MEDICAL_RAG_SYSTEM_PROMPT
