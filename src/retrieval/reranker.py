"""Offline-first reranking for Phase 2C retrieval."""

from __future__ import annotations

import os
import time
from typing import Any

from src.knowledge.normalizer import normalize_text_key
from src.retrieval.contracts import (
    NormalizedQuery,
    QueryExpansion,
    RerankedCandidate,
    RerankScoreBreakdown,
    RerankTrace,
    RetrievedCandidate,
)

LOCAL_RULE_PROVIDERS = {"local", "local_rules", ""}
DRUG_INTENTS = {"drug_identity", "ingredient_question", "class_check"}


def rerank_candidates(
    normalized_query: NormalizedQuery,
    candidates: list[RetrievedCandidate],
    expansion: QueryExpansion | None = None,
    top_n: int = 8,
    provider: str = "local_rules",
) -> tuple[list[RetrievedCandidate], RerankTrace]:
    """Rerank candidates deterministically without external API calls."""

    started = time.perf_counter()
    warnings: list[str] = []
    requested_provider = (provider or "local_rules").strip().lower()
    actual_provider = _resolve_provider(requested_provider, warnings)
    safe_top_n = max(0, int(top_n or 0))

    if not candidates or safe_top_n == 0:
        trace = RerankTrace(
            provider=actual_provider,
            enabled=bool(candidates),
            input_count=len(candidates),
            output_count=0,
            top_n=safe_top_n,
            ranked_candidates=[],
            warnings=warnings,
            timings_ms={"total": round((time.perf_counter() - started) * 1000, 3)},
        )
        return [], trace

    scored = [
        _score_candidate(
            candidate=candidate,
            normalized_query=normalized_query,
            expansion=expansion,
        )
        for candidate in candidates
    ]
    scored.sort(
        key=lambda item: (
            item.score_breakdown.final_score,
            item.candidate.fused_score if item.candidate.fused_score is not None else item.candidate.score or 0.0,
        ),
        reverse=True,
    )

    ranked: list[RerankedCandidate] = []
    output: list[RetrievedCandidate] = []
    for index, item in enumerate(scored[:safe_top_n], start=1):
        debug = dict(item.candidate.debug)
        debug.update(
            {
                "rerank_provider": actual_provider,
                "rerank_score": item.score_breakdown.final_score,
                "rerank_rank": index,
                "rerank_reasons": item.score_breakdown.reasons,
            }
        )
        candidate = item.candidate.model_copy(
            update={
                "fused_score": item.score_breakdown.final_score,
                "rank": index,
                "debug": debug,
            }
        )
        reranked = RerankedCandidate(
            candidate=candidate,
            rerank_score=item.score_breakdown.final_score,
            rerank_rank=index,
            score_breakdown=item.score_breakdown,
        )
        ranked.append(reranked)
        output.append(candidate)

    trace = RerankTrace(
        provider=actual_provider,
        enabled=True,
        input_count=len(candidates),
        output_count=len(output),
        top_n=safe_top_n,
        ranked_candidates=ranked,
        warnings=warnings,
        timings_ms={"total": round((time.perf_counter() - started) * 1000, 3)},
    )
    return output, trace


def _resolve_provider(provider: str, warnings: list[str]) -> str:
    if provider in LOCAL_RULE_PROVIDERS:
        return "local_rules"
    if provider == "local_model":
        try:
            import sentence_transformers  # noqa: F401  # type: ignore[import]
        except Exception as exc:
            warnings.append(
                "RERANK_PROVIDER=local_model requested but sentence-transformers/model "
                f"is unavailable; falling back to local_rules: {exc}"
            )
            return "local_rules"
        warnings.append(
            "RERANK_PROVIDER=local_model interface is reserved; local_rules used to avoid model download."
        )
        return "local_rules"
    warnings.append(f"Unknown rerank provider {provider!r}; falling back to local_rules.")
    return "local_rules"


class _Scored:
    def __init__(self, candidate: RetrievedCandidate, breakdown: RerankScoreBreakdown) -> None:
        self.candidate = candidate
        self.score_breakdown = breakdown


def _score_candidate(
    candidate: RetrievedCandidate,
    normalized_query: NormalizedQuery,
    expansion: QueryExpansion | None,
) -> _Scored:
    base_score = candidate.fused_score if candidate.fused_score is not None else candidate.score
    base_component = min(float(base_score or 0.0), 2.0)
    reasons: list[str] = []

    lexical_score = _lexical_score(candidate, normalized_query, expansion, reasons)
    entity_match_score = _entity_match_score(candidate, normalized_query, reasons)
    metadata_match_score = _metadata_match_score(candidate, normalized_query, reasons)
    intent_alignment_score = _intent_alignment_score(candidate, normalized_query, reasons)
    safety_alignment_score = _safety_alignment_score(candidate, normalized_query, reasons)
    source_priority_score = _source_priority_score(candidate, normalized_query, reasons)
    penalty = _penalty(candidate, normalized_query, reasons)

    final_score = round(
        base_component
        + lexical_score
        + entity_match_score
        + metadata_match_score
        + intent_alignment_score
        + safety_alignment_score
        + source_priority_score
        - penalty,
        6,
    )
    return _Scored(
        candidate,
        RerankScoreBreakdown(
            base_score=base_score,
            lexical_score=round(lexical_score, 6),
            entity_match_score=round(entity_match_score, 6),
            metadata_match_score=round(metadata_match_score, 6),
            intent_alignment_score=round(intent_alignment_score, 6),
            safety_alignment_score=round(safety_alignment_score, 6),
            source_priority_score=round(source_priority_score, 6),
            penalty=round(penalty, 6),
            final_score=final_score,
            reasons=reasons,
        ),
    )


def _lexical_score(
    candidate: RetrievedCandidate,
    normalized_query: NormalizedQuery,
    expansion: QueryExpansion | None,
    reasons: list[str],
) -> float:
    terms = [
        normalized_query.original_query,
        *normalized_query.drug_product,
        *normalized_query.active_ingredient,
        *normalized_query.drug_class,
        *normalized_query.condition,
        *normalized_query.safety_context,
    ]
    if expansion is not None:
        terms.extend(expansion.expanded_terms)
    candidate_text = _candidate_search_text(candidate)
    hits = _term_hits(terms, candidate_text)
    if hits:
        reasons.append(f"lexical_overlap:{','.join(hits[:5])}")
    return min(1.2, 0.18 * len(hits))


def _entity_match_score(
    candidate: RetrievedCandidate,
    normalized_query: NormalizedQuery,
    reasons: list[str],
) -> float:
    payload = candidate.payload
    score = 0.0
    checks = {
        "drug_product": normalized_query.drug_product,
        "active_ingredient": normalized_query.active_ingredient,
        "drug_class": normalized_query.drug_class,
        "condition": normalized_query.condition,
        "safety_context": normalized_query.safety_context,
    }
    payload_values = [
        payload.get("canonical_name"),
        *(_as_list(payload.get("aliases"))),
        *(_as_list(payload.get("active_ingredients"))),
        *(_as_list(payload.get("active_ingredient"))),
        *(_as_list(payload.get("drug_class"))),
        *(_as_list(payload.get("condition"))),
        *(_as_list(payload.get("safety_context"))),
        *(_as_list(payload.get("safety_contexts"))),
    ]
    payload_keys = {_key(value) for value in payload_values if value}
    for field, values in checks.items():
        hits = [value for value in values if _key(value) in payload_keys]
        if hits:
            score += 0.45 if field in {"drug_product", "active_ingredient"} else 0.30
            reasons.append(f"entity_match:{field}={','.join(hits)}")
    return min(score, 1.6)


def _metadata_match_score(
    candidate: RetrievedCandidate,
    normalized_query: NormalizedQuery,
    reasons: list[str],
) -> float:
    score = 0.0
    fields = {
        "active_ingredient": normalized_query.active_ingredient,
        "drug_class": normalized_query.drug_class,
        "condition": normalized_query.condition,
        "safety_context": normalized_query.safety_context,
        "query_intent_hint": normalized_query.query_intent_hint,
        "concern": _as_list(normalized_query.metadata.get("concern")),
        "content_type": _as_list(normalized_query.metadata.get("content_type")),
    }
    aliases = {"active_ingredient": ("active_ingredient", "active_ingredients", "ingredient")}
    for field, query_values in fields.items():
        if not query_values:
            continue
        payload_values: list[str] = []
        for payload_field in aliases.get(field, (field,)):
            payload_values.extend(_as_list(candidate.payload.get(payload_field)))
        payload_values.extend(_as_list(candidate.matched_metadata.get(field)))
        hits = _overlap(query_values, payload_values)
        if hits:
            score += 0.25
            reasons.append(f"metadata_match:{field}={','.join(hits)}")
    return min(score, 1.4)


def _intent_alignment_score(
    candidate: RetrievedCandidate,
    normalized_query: NormalizedQuery,
    reasons: list[str],
) -> float:
    payload = candidate.payload
    intent = normalized_query.intent
    score = 0.0
    if intent in DRUG_INTENTS:
        if candidate.source == "entity" and payload.get("entity_type") in {
            "drug_product",
            "active_ingredient",
            "drug_class",
        }:
            score += 0.9
            reasons.append("intent_alignment:drug_entity")
        if candidate.source == "chunk" and _has_related_metadata(candidate, normalized_query):
            score += 0.55
            reasons.append("intent_alignment:drug_chunk_evidence")
    elif intent == "side_effect":
        if payload.get("side_effects") or "side_effect" in _as_list(payload.get("query_intent_hint")):
            score += 0.9
            reasons.append("intent_alignment:side_effect")
    elif intent == "safety":
        if payload.get("contraindications") or payload.get("safety_contexts") or payload.get("safety_context"):
            score += 0.9
            reasons.append("intent_alignment:safety")
    elif intent == "acne_type":
        if candidate.source == "chunk" and (
            payload.get("concern") or payload.get("content_type") or payload.get("condition")
        ):
            score += 1.0
            reasons.append("intent_alignment:acne_chunk")
        elif candidate.source == "entity" and payload.get("entity_type") == "condition":
            score += 0.25
            reasons.append("intent_alignment:condition_entity")
    else:
        if candidate.source == "chunk":
            score += 0.45
            reasons.append("intent_alignment:general_chunk")
    return score


def _safety_alignment_score(
    candidate: RetrievedCandidate,
    normalized_query: NormalizedQuery,
    reasons: list[str],
) -> float:
    if normalized_query.intent not in {"safety", "side_effect"}:
        return 0.0
    terms = set(_key(value) for value in normalized_query.safety_context)
    terms.update(_key(value) for value in _as_list(normalized_query.metadata.get("safety_context")))
    payload_terms = set(
        _key(value)
        for value in [
            *(_as_list(candidate.payload.get("safety_context"))),
            *(_as_list(candidate.payload.get("safety_contexts"))),
            *(_as_list(candidate.payload.get("contraindications"))),
            *(_as_list(candidate.payload.get("side_effects"))),
        ]
    )
    if terms and terms & payload_terms:
        reasons.append("safety_alignment:context_overlap")
        return 0.45
    if candidate.payload.get("contraindications") or candidate.payload.get("side_effects"):
        reasons.append("safety_alignment:payload_safety_fields")
        return 0.25
    return 0.0


def _source_priority_score(
    candidate: RetrievedCandidate,
    normalized_query: NormalizedQuery,
    reasons: list[str],
) -> float:
    if normalized_query.intent in DRUG_INTENTS and candidate.source == "entity":
        reasons.append("source_priority:entity_for_drug_intent")
        return 0.35
    if normalized_query.intent == "acne_type" and candidate.source == "chunk":
        reasons.append("source_priority:chunk_for_acne_type")
        return 0.45
    if normalized_query.intent == "general_acne_question" and candidate.source == "chunk":
        reasons.append("source_priority:chunk_for_general")
        return 0.25
    return 0.0


def _penalty(candidate: RetrievedCandidate, normalized_query: NormalizedQuery, reasons: list[str]) -> float:
    penalty = 0.0
    if not candidate.text.strip() and not candidate.payload:
        penalty += 0.5
        reasons.append("penalty:empty_candidate")
    if len(candidate.payload) <= 2:
        penalty += 0.15
        reasons.append("penalty:thin_payload")
    if normalized_query.intent == "acne_type":
        if (
            candidate.source == "entity"
            and candidate.payload.get("entity_type") in {"drug_product", "active_ingredient", "drug_class"}
            and not _query_has_drug_entity(normalized_query)
        ):
            penalty += 1.2
            reasons.append("penalty:drug_entity_for_acne_type")
    if normalized_query.intent in DRUG_INTENTS and candidate.source == "entity":
        if not _has_related_metadata(candidate, normalized_query):
            penalty += 0.35
            reasons.append("penalty:unrelated_entity")
    return penalty


def _candidate_search_text(candidate: RetrievedCandidate) -> str:
    payload = candidate.payload
    parts = [
        candidate.text,
        str(payload.get("canonical_name") or ""),
        " ".join(_as_list(payload.get("aliases"))),
        " ".join(_as_list(payload.get("active_ingredients"))),
        " ".join(_as_list(payload.get("drug_class"))),
        " ".join(_as_list(payload.get("concern"))),
        " ".join(_as_list(payload.get("content_type"))),
        " ".join(_as_list(payload.get("condition"))),
    ]
    return " ".join(parts).casefold()


def _term_hits(terms: list[str], text: str) -> list[str]:
    hits: list[str] = []
    normalized_text = normalize_text_key(text).replace(" ", "_")
    raw_text = text.casefold()
    for term in terms:
        term_text = str(term or "").strip()
        if not term_text:
            continue
        term_key = normalize_text_key(term_text).replace(" ", "_")
        if (term_key and term_key in normalized_text) or term_text.casefold() in raw_text:
            if term_text not in hits:
                hits.append(term_text)
    return hits


def _has_related_metadata(candidate: RetrievedCandidate, normalized_query: NormalizedQuery) -> bool:
    for field, values in {
        "drug_product": normalized_query.drug_product,
        "active_ingredient": normalized_query.active_ingredient,
        "drug_class": normalized_query.drug_class,
        "condition": normalized_query.condition,
        "safety_context": normalized_query.safety_context,
    }.items():
        if not values:
            continue
        payload_values = []
        if field == "active_ingredient":
            payload_values.extend(_as_list(candidate.payload.get("active_ingredient")))
            payload_values.extend(_as_list(candidate.payload.get("active_ingredients")))
        elif field == "safety_context":
            payload_values.extend(_as_list(candidate.payload.get("safety_context")))
            payload_values.extend(_as_list(candidate.payload.get("safety_contexts")))
        else:
            payload_values.extend(_as_list(candidate.payload.get(field)))
        payload_values.extend(_as_list(candidate.payload.get("canonical_name")))
        payload_values.extend(_as_list(candidate.payload.get("aliases")))
        if _overlap(values, payload_values):
            return True
    return False


def _query_has_drug_entity(normalized_query: NormalizedQuery) -> bool:
    return bool(normalized_query.drug_product or normalized_query.active_ingredient or normalized_query.drug_class)


def _overlap(left: list[str], right: list[str]) -> list[str]:
    right_keys = {_key(value) for value in right if value}
    hits = [value for value in left if _key(value) in right_keys]
    return list(dict.fromkeys(hits))


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)] if value else []


def _key(value: Any) -> str:
    return normalize_text_key(str(value or "")).replace(" ", "_")


def rerank_enabled_from_env() -> bool:
    return os.getenv("RERANK_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def rerank_top_n_from_env(default: int = 8) -> int:
    try:
        return int(os.getenv("RERANK_TOP_N", str(default)))
    except ValueError:
        return default


def rerank_provider_from_env() -> str:
    return os.getenv("RERANK_PROVIDER", "local_rules").strip() or "local_rules"


__all__ = [
    "rerank_candidates",
    "rerank_enabled_from_env",
    "rerank_provider_from_env",
    "rerank_top_n_from_env",
]
