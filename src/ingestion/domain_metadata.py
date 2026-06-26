"""
domain_metadata.py
==================
Phase 1.5 – Rule-based dermatology metadata extractor.

Provides :func:`extract_dermatology_metadata` which scans a chunk's text
(and optional header path) for domain-specific keywords and returns a
structured metadata dict suitable for enriching ``SemanticChunk.metadata``.

No LLM calls – pure keyword / regex matching.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from src.ingestion.dermatology_taxonomy import (
    BODY_AREA_KEYWORDS,
    CONCERN_KEYWORDS,
    CONTENT_TYPE_KEYWORDS,
    DOMAIN_TOPIC_KEYWORDS,
    INGREDIENT_KEYWORDS,
    SAFETY_CONTEXT_KEYWORDS,
    SKIN_TYPE_KEYWORDS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Data structure
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DermatologyChunkMetadata:
    """Structured metadata for a single dermatology content chunk."""

    domain_topic: list[str] = field(default_factory=list)
    content_type: list[str] = field(default_factory=list)
    concern: list[str] = field(default_factory=list)
    ingredient: list[str] = field(default_factory=list)
    skin_type: list[str] = field(default_factory=list)
    body_area: list[str] = field(default_factory=list)
    safety_context: list[str] = field(default_factory=list)
    evidence_type: str | None = None
    confidence: float = 0.0
    extraction_method: str = "rule_based"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _match_keywords(
    text_lower: str,
    keyword_dict: dict[str, list[str]],
) -> list[str]:
    """Return deduplicated, stable-ordered list of canonical values matched."""
    matched: list[str] = []
    for canonical, keywords in keyword_dict.items():
        for kw in keywords:
            if kw in text_lower:
                if canonical not in matched:
                    matched.append(canonical)
                break  # one keyword is enough per canonical value
    return matched


def _detect_evidence_type(text_lower: str) -> str | None:
    """Heuristic detection of evidence type from text keywords."""
    evidence_patterns: list[tuple[str, list[str]]] = [
        ("clinical_study", [
            "clinical trial", "thử nghiệm lâm sàng",
            "randomized", "rct", "double-blind", "placebo",
            "nghiên cứu lâm sàng",
        ]),
        ("systematic_review", [
            "systematic review", "meta-analysis", "meta analysis",
            "tổng quan hệ thống",
        ]),
        ("guideline", [
            "guideline", "hướng dẫn điều trị", "phác đồ",
            "consensus", "recommendation",
        ]),
        ("expert_opinion", [
            "expert opinion", "ý kiến chuyên gia",
            "according to dermatologist", "bác sĩ khuyên",
        ]),
        ("in_vitro", [
            "in vitro", "in-vitro", "cell culture", "nuôi cấy tế bào",
        ]),
    ]

    for evidence_type, patterns in evidence_patterns:
        for pattern in patterns:
            if pattern in text_lower:
                return evidence_type
    return None


def _compute_confidence(meta: DermatologyChunkMetadata) -> float:
    """
    Compute a confidence score based on how many metadata fields were populated.

    Strategy:
    - 0.0 if nothing matched at all.
    - 0.3 base if at least one field matched.
    - +0.1 for each additional populated field (up to 7 fields).
    - Capped at 1.0.
    """
    populated_fields = 0
    for field_name in (
        "domain_topic",
        "content_type",
        "concern",
        "ingredient",
        "skin_type",
        "body_area",
        "safety_context",
    ):
        values = getattr(meta, field_name)
        if values:
            populated_fields += 1

    if populated_fields == 0:
        return 0.0

    # Base 0.3 + 0.1 per populated field
    confidence = 0.3 + (populated_fields * 0.1)
    return min(confidence, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def extract_dermatology_metadata(
    text: str,
    header_path: str | list[str] = "",
) -> dict[str, Any]:
    """
    Extract dermatology-specific metadata from *text* using rule-based
    keyword matching.

    Parameters
    ----------
    text : str
        The chunk text to analyse.
    header_path : str | list[str]
        Optional Markdown header path (e.g. ``"Acne Treatment > Retinoids"``
        or ``["Acne Treatment", "Retinoids"]``). Will be concatenated and
        matched alongside *text*.

    Returns
    -------
    dict[str, Any]
        A flat dictionary matching the ``DermatologyChunkMetadata`` fields.
        All list values are deduplicated, stable-ordered, lowercase snake_case.
    """
    # Normalise header_path to a string
    if isinstance(header_path, list):
        header_str = " ".join(header_path)
    else:
        header_str = header_path or ""

    # Combine text and header for matching (lowercased)
    combined = f"{header_str} {text}".lower()

    meta = DermatologyChunkMetadata(
        domain_topic=_match_keywords(combined, DOMAIN_TOPIC_KEYWORDS),
        content_type=_match_keywords(combined, CONTENT_TYPE_KEYWORDS),
        concern=_match_keywords(combined, CONCERN_KEYWORDS),
        ingredient=_match_keywords(combined, INGREDIENT_KEYWORDS),
        skin_type=_match_keywords(combined, SKIN_TYPE_KEYWORDS),
        body_area=_match_keywords(combined, BODY_AREA_KEYWORDS),
        safety_context=_match_keywords(combined, SAFETY_CONTEXT_KEYWORDS),
        evidence_type=_detect_evidence_type(combined),
        extraction_method="rule_based",
    )

    meta.confidence = _compute_confidence(meta)

    return meta.to_dict()
