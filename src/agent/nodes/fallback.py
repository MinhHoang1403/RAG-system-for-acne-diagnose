"""LangGraph nodes for deterministic safe fallback flow."""

from __future__ import annotations

from typing import Any

from src.agent.state import ClinicalState
from src.quality.safe_fallback import (
    build_safe_fallback_answer,
    decide_generation_fallback,
    decide_retrieval_fallback,
)


async def fallback_decision_node(state: ClinicalState) -> dict[str, Any]:
    """Decide whether retrieval evidence is usable before answer generation."""

    decision = decide_retrieval_fallback(dict(state))
    if not decision.fallback_applied:
        return {
            "fallback_applied": False,
            "fallback_type": "none",
            "fallback_reason": None,
            "fallback_answer": None,
            "fallback_cache_eligible": True,
        }
    return {
        "fallback_applied": True,
        "fallback_type": decision.fallback_type,
        "fallback_reason": decision.fallback_reason,
        "fallback_answer": build_safe_fallback_answer(
            decision.fallback_type,
            query=state.get("standalone_question") or state.get("user_question"),
            reason=decision.fallback_reason,
        ),
        "fallback_cache_eligible": decision.fallback_cache_eligible,
    }


async def generation_fallback_decision_node(state: ClinicalState) -> dict[str, Any]:
    """Validate generated draft answer before finalize_response_node."""

    decision = decide_generation_fallback(state.get("draft_answer"))
    if not decision.fallback_applied:
        return {
            "fallback_applied": False,
            "fallback_type": "none",
            "fallback_reason": None,
            "fallback_answer": None,
            "fallback_cache_eligible": True,
        }
    return {
        "fallback_applied": True,
        "fallback_type": decision.fallback_type,
        "fallback_reason": decision.fallback_reason,
        "fallback_answer": build_safe_fallback_answer(
            decision.fallback_type,
            query=state.get("standalone_question") or state.get("user_question"),
            reason=decision.fallback_reason,
        ),
        "fallback_cache_eligible": decision.fallback_cache_eligible,
    }


async def safe_fallback_node(state: ClinicalState) -> dict[str, Any]:
    """Convert a safe fallback decision into the draft answer used by finalize."""

    fallback_type = state.get("fallback_type") or "no_retrieval_evidence"
    fallback_reason = state.get("fallback_reason")
    fallback_answer = state.get("fallback_answer") or build_safe_fallback_answer(
        fallback_type,
        query=state.get("standalone_question") or state.get("user_question"),
        reason=fallback_reason,
    )
    return {
        "draft_answer": fallback_answer,
        "sources": [],
        "actual_provider": "system",
        "actual_model": None,
        "llm_fallback_used": False,
        "fallback_provider": None,
        "fallback_model": None,
        "fallback_applied": True,
        "fallback_type": fallback_type,
        "fallback_reason": fallback_reason,
        "fallback_answer": fallback_answer,
        "fallback_cache_eligible": False,
    }


__all__ = [
    "fallback_decision_node",
    "generation_fallback_decision_node",
    "safe_fallback_node",
]
