"""LangGraph node for deterministic medical severity classification."""

from __future__ import annotations

from typing import Any

from src.agent.state import ClinicalState
from src.quality.severity_guard import classify_medical_severity


async def severity_classification_node(state: ClinicalState) -> dict[str, Any]:
    """Classify query severity before cache lookup or answer generation."""

    query = state.get("standalone_question") or state.get("user_question", "")
    classification = classify_medical_severity(query)
    return {
        "medical_severity": classification.severity,
        "severity_guard": classification.model_dump(mode="json"),
    }


__all__ = ["severity_classification_node"]
