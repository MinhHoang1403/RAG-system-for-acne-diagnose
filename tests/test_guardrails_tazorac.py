from __future__ import annotations

import asyncio

from src.agent.nodes.guardrails import domain_guard_node


def test_tazorac_questions_are_rule_based_in_domain() -> None:
    questions = [
        "Tazorac chứa hoạt chất gì?",
        "Tazarotene thuộc nhóm thuốc nào?",
        "tazorac co hoat chat gi",
    ]

    for question in questions:
        result = asyncio.run(domain_guard_node({"user_question": question}))

        assert result["is_in_domain"] is True
        assert result["guardrail"] == "in_domain_rule"
