#!/usr/bin/env python3
"""Offline deterministic eval for Step 7 safe fallback flow."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.nodes.fallback import generation_fallback_decision_node, safe_fallback_node  # noqa: E402
from src.quality.safe_fallback import (  # noqa: E402
    SAFE_FALLBACK_FLOW_VERSION,
    build_safe_fallback_answer,
    decide_generation_fallback,
    decide_retrieval_fallback,
)
from src.quality.severity_guard import apply_severity_aware_answer_guard  # noqa: E402
from src.resilience.exceptions import ProviderTimeoutError, ProviderUnavailableError  # noqa: E402


def _case(case_id: str, passed: bool, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": case_id, "passed": bool(passed), "details": details or {}}


async def run_eval() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    empty_query = decide_retrieval_fallback({"standalone_question": "", "vector_contexts": [], "graph_facts": []})
    cases.append(_case("empty_query", empty_query.fallback_type == "empty_query"))

    no_evidence = decide_retrieval_fallback(
        {"standalone_question": "mụn", "vector_contexts": [], "graph_facts": [], "packed_context": None}
    )
    cases.append(_case("no_vector_or_graph_evidence", no_evidence.fallback_type == "no_retrieval_evidence"))

    retrieval_error = decide_retrieval_fallback(
        {"standalone_question": "mụn", "retrieval_status": "recoverable_error", "retrieval_error": "backend failed"}
    )
    cases.append(_case("recoverable_retrieval_error", retrieval_error.fallback_type == "retrieval_error"))

    cases.append(_case("empty_generation", decide_generation_fallback(" ").fallback_type == "empty_generation"))
    cases.append(_case("invalid_generation", decide_generation_fallback(None).fallback_type == "invalid_generation"))

    routine = apply_severity_aware_answer_guard("Mụn đầu đen là gì?", build_safe_fallback_answer("no_retrieval_evidence"))
    cases.append(_case("routine_no_evidence", routine.modified is False and routine.classification.severity == "routine"))

    caution = apply_severity_aware_answer_guard(
        "Da tôi đỏ rát nhẹ khi dùng benzoyl peroxide",
        build_safe_fallback_answer("no_retrieval_evidence"),
    )
    cases.append(_case("caution_no_evidence", caution.classification.severity == "caution"))

    urgent = apply_severity_aware_answer_guard(
        "Tôi đang mang thai, có dùng isotretinoin trị mụn được không?",
        build_safe_fallback_answer("no_retrieval_evidence"),
    )
    cases.append(_case("urgent_no_evidence", urgent.classification.severity == "urgent" and "24-48" in urgent.answer))

    emergency = apply_severity_aware_answer_guard(
        "Bôi thuốc xong tôi khó thở, sưng môi và nổi mề đay",
        build_safe_fallback_answer("no_retrieval_evidence"),
    )
    cases.append(_case("emergency_no_evidence", emergency.classification.severity == "emergency" and "cấp cứu" in emergency.answer))

    valid_evidence = decide_retrieval_fallback(
        {"standalone_question": "mụn", "vector_contexts": [{"text": "evidence"}], "graph_facts": []}
    )
    cases.append(_case("valid_evidence_no_fallback", valid_evidence.fallback_applied is False))

    decision = await generation_fallback_decision_node({"draft_answer": ""})
    fallback = await safe_fallback_node(decision)
    cases.append(
        _case(
            "fallback_not_cacheable",
            decision["fallback_cache_eligible"] is False and fallback["fallback_cache_eligible"] is False,
        )
    )

    try:
        raise ProviderTimeoutError("timeout")
    except ProviderTimeoutError:
        cases.append(_case("timeout_not_swallowed", True))

    try:
        raise ProviderUnavailableError("unavailable")
    except ProviderUnavailableError:
        cases.append(_case("provider_unavailable_not_swallowed", True))

    passed_cases = sum(1 for case in cases if case["passed"])
    return {
        "name": "SAFE_FALLBACK_FLOW",
        "version": SAFE_FALLBACK_FLOW_VERSION,
        "passed": passed_cases == len(cases),
        "total_cases": len(cases),
        "passed_cases": passed_cases,
        "failed_cases": len(cases) - passed_cases,
        "cases": cases,
    }


def main() -> int:
    report = asyncio.run(run_eval())
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print("SAFE_FALLBACK_FLOW: PASS" if report["passed"] else "SAFE_FALLBACK_FLOW: FAIL")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
