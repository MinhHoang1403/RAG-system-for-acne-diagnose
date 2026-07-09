"""Deterministic ranking metrics for offline reranker evaluation."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


def reciprocal_rank_at_k(ranked_ids: Sequence[str], relevance: Mapping[str, int], k: int) -> float:
    for index, candidate_id in enumerate(_dedupe_ranked(ranked_ids)[: max(0, k)], start=1):
        if relevance.get(candidate_id, 0) > 0:
            return round(1.0 / index, 6)
    return 0.0


def recall_at_k(ranked_ids: Sequence[str], relevance: Mapping[str, int], k: int) -> float:
    relevant_ids = {candidate_id for candidate_id, label in relevance.items() if label > 0}
    if not relevant_ids:
        return 1.0
    found = {candidate_id for candidate_id in _dedupe_ranked(ranked_ids)[: max(0, k)] if candidate_id in relevant_ids}
    return round(len(found) / len(relevant_ids), 6)


def precision_at_k(ranked_ids: Sequence[str], relevance: Mapping[str, int], k: int) -> float:
    safe_k = max(0, k)
    if safe_k == 0:
        return 0.0
    hits = sum(1 for candidate_id in _dedupe_ranked(ranked_ids)[:safe_k] if relevance.get(candidate_id, 0) > 0)
    return round(hits / safe_k, 6)


def ndcg_at_k(ranked_ids: Sequence[str], relevance: Mapping[str, int], k: int) -> float:
    safe_k = max(0, k)
    if safe_k == 0:
        return 0.0
    dcg = _dcg([relevance.get(candidate_id, 0) for candidate_id in _dedupe_ranked(ranked_ids)[:safe_k]])
    ideal = _dcg(sorted((label for label in relevance.values() if label > 0), reverse=True)[:safe_k])
    if ideal == 0:
        return 1.0
    return round(dcg / ideal, 6)


def top1_accuracy(ranked_ids: Sequence[str], relevance: Mapping[str, int]) -> float:
    if not ranked_ids:
        return 1.0 if not any(label > 0 for label in relevance.values()) else 0.0
    deduped = _dedupe_ranked(ranked_ids)
    return 1.0 if deduped and relevance.get(deduped[0], 0) > 0 else 0.0


def ranking_metrics(ranked_ids: Sequence[str], relevance: Mapping[str, int], k: int = 5) -> dict[str, Any]:
    return {
        "mrr_at_k": reciprocal_rank_at_k(ranked_ids, relevance, k),
        "ndcg_at_k": ndcg_at_k(ranked_ids, relevance, k),
        "recall_at_k": recall_at_k(ranked_ids, relevance, k),
        "precision_at_k": precision_at_k(ranked_ids, relevance, k),
        "top1_accuracy": top1_accuracy(ranked_ids, relevance),
    }


def _dcg(labels: Sequence[int]) -> float:
    return sum((2**label - 1) / math.log2(index + 2) for index, label in enumerate(labels))


def _dedupe_ranked(ranked_ids: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for candidate_id in ranked_ids:
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        output.append(candidate_id)
    return output


__all__ = [
    "ndcg_at_k",
    "precision_at_k",
    "ranking_metrics",
    "recall_at_k",
    "reciprocal_rank_at_k",
    "top1_accuracy",
]
