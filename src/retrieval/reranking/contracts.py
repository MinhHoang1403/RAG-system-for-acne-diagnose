"""Provider-neutral reranking contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


PrimitiveMetadata = Mapping[str, Any]


class RerankerError(RuntimeError):
    """Base exception for reranker failures."""

    error_code = "reranker_error"


class RerankerUnavailable(RerankerError):
    """Raised when a requested reranker backend is not available locally."""

    error_code = "semantic_model_unavailable"


@dataclass(frozen=True)
class RerankCandidate:
    """Stable candidate shape consumed by reranker providers."""

    candidate_id: str
    text: str
    source_type: str
    original_rank: int
    retrieval_score: float | None
    dense_score: float | None
    sparse_score: float | None
    metadata: PrimitiveMetadata = field(default_factory=dict)


@dataclass(frozen=True)
class RerankScore:
    """Provider-neutral score returned by rerankers."""

    candidate_id: str
    final_score: float
    original_rank: int
    provider: str
    semantic_score: float | None = None
    rule_score: float | None = None
    retrieval_score: float | None = None
    diagnostics: PrimitiveMetadata = field(default_factory=dict)


def sort_scores(scores: list[RerankScore]) -> list[RerankScore]:
    """Sort scores deterministically: score desc, original rank asc, id asc."""

    return sorted(
        scores,
        key=lambda item: (
            -float(item.final_score),
            int(item.original_rank),
            item.candidate_id,
        ),
    )


__all__ = [
    "RerankCandidate",
    "RerankScore",
    "RerankerError",
    "RerankerUnavailable",
    "sort_scores",
]
