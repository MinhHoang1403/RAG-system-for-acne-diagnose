"""LangGraph node for deterministic answer quality verification."""

from __future__ import annotations

import logging
import os
from typing import Any

from src.agent.state import ClinicalState
from src.quality.answer_verifier import apply_answer_guard
from src.quality.safe_fallback import sanitize_fallback_reason
from src.quality.severity_guard import apply_severity_aware_answer_guard
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
        severity_guard = apply_severity_aware_answer_guard(query=query, answer=guard.answer)
        report_data = guard.report.model_dump(mode="json")
        severity_data = severity_guard.classification.model_dump(mode="json")
        report_data.setdefault("metadata", {})
        report_data["metadata"]["severity_guard"] = {
            **severity_data,
            "version": "severity_aware_answer_guard_v1",
            "modified": severity_guard.modified,
            "modification_reason": severity_guard.modification_reason,
            "cache_eligible": severity_guard.cache_eligible,
        }
        if severity_guard.modified:
            report_data.setdefault("issues", []).append(
                {
                    "code": severity_guard.modification_reason or "severity_guard_modified_answer",
                    "severity": "warning",
                    "message": "Severity-aware answer guard adjusted the response for medical safety.",
                    "evidence": severity_data,
                    "suggested_fix": None,
                }
            )
        logger.info(
            "Answer quality checked: passed=%s issues=%d modified=%s severity=%s severity_modified=%s",
            guard.report.passed,
            len(guard.report.issues),
            guard.modified,
            severity_guard.classification.severity,
            severity_guard.modified,
        )
        return {
            "final_answer": severity_guard.answer,
            "answer_quality_report": report_data,
            "answer_guard_modified": guard.modified or severity_guard.modified,
            "answer_guard_mode": guard_mode,
            "medical_severity": severity_guard.classification.severity,
            "severity_guard": severity_data,
            "severity_guard_modified": severity_guard.modified,
            "severity_guard_cache_eligible": severity_guard.cache_eligible,
        }
    except Exception as exc:
        safe_error = sanitize_fallback_reason(exc)
        logger.warning("Answer quality verifier failed safely: %s", safe_error)
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
                        "message": safe_error,
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
