"""Candidate merge and light fusion for Phase 2A retrieval."""

from __future__ import annotations

import hashlib
from typing import Any

from src.retrieval.contracts import NormalizedQuery, RetrievedCandidate


ENTITY_PRIORITY_INTENTS = {"drug_identity", "ingredient_question", "class_check"}
DRUG_EVIDENCE_INTENTS = {"drug_identity", "ingredient_question", "class_check", "comparison"}


def merge_candidates(
    entity_candidates: list[RetrievedCandidate],
    chunk_candidates: list[RetrievedCandidate],
    normalized_query: NormalizedQuery,
    limit: int = 12,
) -> list[RetrievedCandidate]:
    """Merge entity and chunk candidates with dedupe and simple score fusion."""

    combined = [*entity_candidates, *chunk_candidates]
    deduped: dict[str, RetrievedCandidate] = {}
    for candidate in combined:
        key = _dedupe_key(candidate)
        scored = _with_merge_score(candidate, normalized_query)
        existing = deduped.get(key)
        if existing is None or (scored.fused_score or 0.0) > (existing.fused_score or 0.0):
            deduped[key] = scored

    all_ranked = sorted(
        deduped.values(),
        key=lambda candidate: candidate.fused_score or candidate.score or 0.0,
        reverse=True,
    )
    ranked = _preserve_chunk_evidence(all_ranked, normalized_query, limit)
    return [
        candidate.model_copy(update={"rank": index + 1})
        for index, candidate in enumerate(ranked)
    ]


def _preserve_chunk_evidence(
    ranked: list[RetrievedCandidate],
    normalized_query: NormalizedQuery,
    limit: int,
) -> list[RetrievedCandidate]:
    """Keep at least one chunk evidence candidate for drug-like queries."""

    selected = ranked[:limit]
    if (
        normalized_query.intent not in DRUG_EVIDENCE_INTENTS
        or any(candidate.source == "chunk" for candidate in selected)
    ):
        return selected
    first_chunk = next((candidate for candidate in ranked[limit:] if candidate.source == "chunk"), None)
    if first_chunk is None:
        return selected
    if len(selected) < limit:
        return [*selected, first_chunk]
    if not selected:
        return [first_chunk]
    return [*selected[:-1], first_chunk]


def _with_merge_score(
    candidate: RetrievedCandidate,
    normalized_query: NormalizedQuery,
) -> RetrievedCandidate:
    base = float(candidate.fused_score if candidate.fused_score is not None else candidate.score or 0.0)
    bonus = 0.0
    if candidate.source == "entity" and normalized_query.intent in ENTITY_PRIORITY_INTENTS:
        bonus += 0.20
    if candidate.source == "chunk":
        bonus += min(0.10, 0.02 * len(candidate.matched_metadata))
    debug = dict(candidate.debug)
    debug["merge_bonus"] = round(bonus, 6)
    return candidate.model_copy(
        update={
            "fused_score": round(base + bonus, 6),
            "debug": debug,
        }
    )


def _dedupe_key(candidate: RetrievedCandidate) -> str:
    payload = candidate.payload
    for field in ("chunk_id", "entity_id", "point_id"):
        value = payload.get(field)
        if value:
            return f"{candidate.collection}:{field}:{value}"
    if candidate.candidate_id:
        return f"{candidate.collection}:candidate:{candidate.candidate_id}"
    text = candidate.text.strip()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{candidate.collection}:text:{digest}"


def candidate_debug_summary(candidate: RetrievedCandidate) -> dict[str, Any]:
    """Compact debug view safe for API metadata/logs."""

    return {
        "rank": candidate.rank,
        "source": candidate.source,
        "collection": candidate.collection,
        "candidate_id": candidate.candidate_id,
        "score": candidate.score,
        "fused_score": candidate.fused_score,
        "matched_metadata": candidate.matched_metadata,
        "canonical_name": candidate.payload.get("canonical_name"),
        "chunk_id": candidate.payload.get("chunk_id"),
    }


__all__ = ["candidate_debug_summary", "merge_candidates"]
