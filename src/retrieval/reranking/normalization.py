"""Deterministic score normalization helpers for reranking."""

from __future__ import annotations

import math
from collections.abc import Mapping


def sanitize_score(value: float | int | None, *, default: float = 0.0) -> float:
    """Return a finite float for a possibly missing or invalid score."""

    if value is None:
        return default
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(score):
        return default
    return score


def min_max_normalize(values: list[float | int | None]) -> list[float]:
    """Normalize finite scores to [0, 1] with safe equal-score handling."""

    sanitized = [sanitize_score(value) for value in values]
    if not sanitized:
        return []
    if len(sanitized) == 1:
        return [1.0]
    minimum = min(sanitized)
    maximum = max(sanitized)
    if math.isclose(maximum, minimum):
        return [1.0 for _ in sanitized]
    span = maximum - minimum
    return [round((score - minimum) / span, 6) for score in sanitized]


def normalize_score_map(scores: Mapping[str, float | int | None]) -> dict[str, float]:
    """Normalize a candidate-id score mapping to [0, 1]."""

    keys = list(scores.keys())
    normalized = min_max_normalize([scores[key] for key in keys])
    return dict(zip(keys, normalized, strict=True))


def clamp_unit(value: float | int | None) -> float:
    """Sanitize and clamp a score to [0, 1]."""

    score = sanitize_score(value)
    return round(min(1.0, max(0.0, score)), 6)


__all__ = ["clamp_unit", "min_max_normalize", "normalize_score_map", "sanitize_score"]
