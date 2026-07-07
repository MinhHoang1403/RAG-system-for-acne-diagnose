"""LangGraph node for deterministic answer quality verification."""

from __future__ import annotations

import logging
import os
from typing import Any

from src.agent.state import ClinicalState
from src.quality.answer_verifier import apply_answer_guard
from src.retrieval.contracts import PackedContext, RetrievalTrace
from src.retrieval.query_normalization import normalize_query

logger = logging.getLogger(__name__)


async def answer_quality_node(state: ClinicalState) -> dict[str, Any]:
    """Verify the finalized answer without calling external services."""

    enabled = os.getenv("ANSWER_VERIFIER_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    if not enabled:
        return {
            "answer_quality_report": None,
            "answer_guard_modified": False,
        }

    query = state.get("standalone_question") or state.get("user_question", "")
    answer = state.get("final_answer", "")
    if not query or not answer:
        return {}

    try:
        normalized_query = normalize_query(query)
        packed_context = _parse_model(PackedContext, state.get("packed_context"))
        retrieval_trace = _parse_model(RetrievalTrace, state.get("retrieval_trace"))
        guard_mode = os.getenv("ANSWER_GUARD_MODE", "metadata_only")
        strict_enabled = os.getenv("ANSWER_VERIFIER_STRICT", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if strict_enabled and guard_mode.strip().lower() == "metadata_only":
            guard_mode = "strict_safe"

        guard = apply_answer_guard(
            query=query,
            answer=answer,
            normalized_query=normalized_query,
            packed_context=packed_context,
            retrieval_trace=retrieval_trace,
            mode=guard_mode,
        )
        logger.info(
            "Answer quality checked: passed=%s issues=%d modified=%s",
            guard.report.passed,
            len(guard.report.issues),
            guard.modified,
        )
        return {
            "final_answer": guard.answer,
            "answer_quality_report": guard.report.model_dump(mode="json"),
            "answer_guard_modified": guard.modified,
            "answer_guard_mode": guard_mode,
        }
    except Exception as exc:
        logger.warning("Answer quality verifier failed safely: %s", exc)
        return {
            "answer_quality_report": {
                "passed": False,
                "original_query": query,
                "intent": None,
                "checked_answer": answer,
                "issues": [
                    {
                        "code": "answer_verifier_runtime_error",
                        "severity": "warning",
                        "message": str(exc),
                        "evidence": {},
                        "suggested_fix": None,
                    }
                ],
                "required_facts": [],
                "detected_facts": [],
                "missing_facts": [],
                "contradictions": [],
                "safety_warnings": [],
                "metadata": {},
            },
            "answer_guard_modified": False,
        }


def _parse_model(model_cls: Any, value: Any) -> Any | None:
    if value is None:
        return None
    if isinstance(value, model_cls):
        return value
    if isinstance(value, dict):
        return model_cls.model_validate(value)
    return None


__all__ = ["answer_quality_node"]
