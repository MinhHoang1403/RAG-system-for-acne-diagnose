"""Offline-first reranking for Phase 2C retrieval."""

from __future__ import annotations

import os
import time
from typing import Any

from src.knowledge.normalizer import normalize_text_key
from src.quality.safe_fallback import sanitize_fallback_reason
from src.retrieval.contracts import (
    NormalizedQuery,
    QueryExpansion,
    RerankedCandidate,
    RerankScoreBreakdown,
    RerankTrace,
    RetrievedCandidate,
)
from src.retrieval.reranking.contracts import RerankCandidate, RerankScore, RerankerUnavailable, sort_scores
from src.retrieval.reranking.normalization import normalize_score_map, sanitize_score
from src.retrieval.reranking.providers import (
    LocalSemanticReranker,
    PROVIDER_HYBRID,
    PROVIDER_LOCAL_RULES,
    PROVIDER_LOCAL_SEMANTIC,
    build_semantic_reranker_from_env,
    canonical_provider_name,
    hybrid_config_from_env,
    hybrid_fuse_scores,
)

LOCAL_RULE_PROVIDERS = {"local", "local_rules", ""}
DRUG_INTENTS = {"drug_identity", "ingredient_question", "class_check"}


def rerank_candidates(
    normalized_query: NormalizedQuery,
    candidates: list[RetrievedCandidate],
    expansion: QueryExpansion | None = None,
    top_n: int = 8,
    provider: str = "local_rules",
    semantic_reranker: LocalSemanticReranker | None = None,
    timeout_seconds: float | None = None,
) -> tuple[list[RetrievedCandidate], RerankTrace]:
    """Rerank candidates deterministically with local-only provider fallback."""

    started = time.perf_counter()
    warnings: list[str] = []
    requested_provider = (provider or "local_rules").strip().lower()
    actual_provider = _resolve_provider(requested_provider, warnings)
    safe_top_n = max(0, int(top_n or 0))
    fallback_used = False

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

    rerank_inputs = [
        _to_rerank_candidate(candidate, index + 1)
        for index, candidate in enumerate(candidates)
    ]

    try:
        scores, breakdowns, actual_provider, fallback_used = _score_with_provider(
            normalized_query=normalized_query,
            candidates=candidates,
            rerank_inputs=rerank_inputs,
            expansion=expansion,
            requested_provider=requested_provider,
            actual_provider=actual_provider,
            warnings=warnings,
            top_n=safe_top_n,
            semantic_reranker=semantic_reranker,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        warning = f"local_rules failed; using retrieval order fallback: {sanitize_fallback_reason(exc)}"
        warnings.append(warning)
        actual_provider = "retrieval_order"
        fallback_used = True
        scores = _retrieval_order_scores(rerank_inputs)
        breakdowns = {
            score.candidate_id: RerankScoreBreakdown(
                base_score=score.retrieval_score,
                retrieval_score=score.retrieval_score,
                final_score=score.final_score,
                reasons=[warning],
            )
            for score in scores
        }

    ranked: list[RerankedCandidate] = []
    output: list[RetrievedCandidate] = []
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    for index, score in enumerate(scores[:safe_top_n], start=1):
        source_candidate = candidate_by_id[score.candidate_id]
        breakdown = breakdowns[score.candidate_id]
        debug = dict(source_candidate.debug)
        debug.update(
            {
                "rerank_provider": actual_provider,
                "rerank_provider_requested": requested_provider,
                "rerank_fallback_used": fallback_used,
                "rerank_score": score.final_score,
                "rerank_rule_score": score.rule_score,
                "rerank_semantic_score": score.semantic_score,
                "rerank_retrieval_score": score.retrieval_score,
                "rerank_rank": index,
                "rerank_reasons": breakdown.reasons,
            }
        )
        candidate = source_candidate.model_copy(
            update={
                "fused_score": score.final_score,
                "rank": index,
                "debug": debug,
            }
        )
        reranked = RerankedCandidate(
            candidate=candidate,
            rerank_score=score.final_score,
            rerank_rank=index,
            score_breakdown=breakdown,
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
        timings_ms={
            "total": round((time.perf_counter() - started) * 1000, 3),
        },
        requested_provider=requested_provider,
        fallback_used=fallback_used,
        semantic_model_available=_semantic_model_available(semantic_reranker),
    )
    return output, trace


def _resolve_provider(provider: str, warnings: list[str]) -> str:
    canonical = canonical_provider_name(provider)
    if canonical in {PROVIDER_LOCAL_RULES, PROVIDER_LOCAL_SEMANTIC, PROVIDER_HYBRID}:
        return canonical
    warnings.append(f"Unknown rerank provider {provider!r}; falling back to local_rules.")
    return PROVIDER_LOCAL_RULES


def _score_with_provider(
    *,
    normalized_query: NormalizedQuery,
    candidates: list[RetrievedCandidate],
    rerank_inputs: list[RerankCandidate],
    expansion: QueryExpansion | None,
    requested_provider: str,
    actual_provider: str,
    warnings: list[str],
    top_n: int,
    semantic_reranker: LocalSemanticReranker | None,
    timeout_seconds: float | None,
) -> tuple[list[RerankScore], dict[str, RerankScoreBreakdown], str, bool]:
    rule_scored = _score_local_rules(candidates, normalized_query, expansion)
    rule_score_map = {
        item.candidate.candidate_id: item.score_breakdown.final_score
        for item in rule_scored
    }
    rule_normalized = normalize_score_map(rule_score_map)
    rule_breakdowns = {
        item.candidate.candidate_id: item.score_breakdown.model_copy(
            update={
                "rule_score": rule_normalized[item.candidate.candidate_id],
                "retrieval_score": sanitize_score(_retrieval_score(item.candidate)),
                "final_score": rule_normalized[item.candidate.candidate_id],
            }
        )
        for item in rule_scored
    }

    if actual_provider == PROVIDER_LOCAL_RULES:
        return (
            _local_rule_scores(rerank_inputs, rule_normalized),
            rule_breakdowns,
            PROVIDER_LOCAL_RULES,
            False,
        )

    reranker = semantic_reranker or build_semantic_reranker_from_env()
    try:
        semantic_ranked = reranker.rerank(
            normalized_query.original_query,
            rerank_inputs,
            top_n=len(rerank_inputs),
            timeout_seconds=timeout_seconds,
        )
        semantic_scores = {
            score.candidate_id: sanitize_score(score.semantic_score)
            for score in semantic_ranked
        }
        if actual_provider == PROVIDER_LOCAL_SEMANTIC:
            breakdowns = {
                score.candidate_id: RerankScoreBreakdown(
                    base_score=score.retrieval_score,
                    semantic_score=score.semantic_score,
                    retrieval_score=score.retrieval_score,
                    final_score=score.final_score,
                    reasons=[f"semantic_backend:{score.diagnostics.get('backend', 'local')}"],
                )
                for score in semantic_ranked
            }
            return semantic_ranked[:top_n], breakdowns, PROVIDER_LOCAL_SEMANTIC, False

        fused = hybrid_fuse_scores(
            rerank_inputs,
            semantic_scores,
            rule_normalized,
            config=hybrid_config_from_env(),
        )
        breakdowns = {
            score.candidate_id: RerankScoreBreakdown(
                base_score=score.retrieval_score,
                semantic_score=score.semantic_score,
                rule_score=score.rule_score,
                retrieval_score=score.retrieval_score,
                final_score=score.final_score,
                reasons=[
                    "hybrid_fusion",
                    *rule_breakdowns.get(score.candidate_id, RerankScoreBreakdown()).reasons[:5],
                ],
            )
            for score in fused
        }
        return fused[:top_n], breakdowns, PROVIDER_HYBRID, False
    except Exception as exc:
        allow_fallback = getattr(reranker.config, "allow_fallback", True)
        if not allow_fallback:
            raise
        warnings.append(
            f"{requested_provider} unavailable or failed; falling back to local_rules: "
            f"{type(exc).__name__}: {sanitize_fallback_reason(exc)}"
        )
        return (
            _local_rule_scores(rerank_inputs, rule_normalized),
            rule_breakdowns,
            PROVIDER_LOCAL_RULES,
            True,
        )


def _score_local_rules(
    candidates: list[RetrievedCandidate],
    normalized_query: NormalizedQuery,
    expansion: QueryExpansion | None,
) -> list["_Scored"]:
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
            -item.score_breakdown.final_score,
            item.candidate.rank if item.candidate.rank is not None else 999999,
            item.candidate.candidate_id,
        )
    )
    return scored


def _local_rule_scores(
    rerank_inputs: list[RerankCandidate],
    normalized_rule_scores: dict[str, float],
) -> list[RerankScore]:
    scores = [
        RerankScore(
            candidate_id=candidate.candidate_id,
            final_score=normalized_rule_scores.get(candidate.candidate_id, 0.0),
            original_rank=candidate.original_rank,
            provider=PROVIDER_LOCAL_RULES,
            semantic_score=None,
            rule_score=normalized_rule_scores.get(candidate.candidate_id, 0.0),
            retrieval_score=sanitize_score(candidate.retrieval_score),
        )
        for candidate in rerank_inputs
    ]
    return sort_scores(scores)


def _retrieval_order_scores(rerank_inputs: list[RerankCandidate]) -> list[RerankScore]:
    if not rerank_inputs:
        return []
    max_rank = max(candidate.original_rank for candidate in rerank_inputs)
    return [
        RerankScore(
            candidate_id=candidate.candidate_id,
            final_score=round(1.0 - ((candidate.original_rank - 1) / max(max_rank, 1)), 6),
            original_rank=candidate.original_rank,
            provider="retrieval_order",
            retrieval_score=sanitize_score(candidate.retrieval_score),
        )
        for candidate in rerank_inputs
    ]


def _to_rerank_candidate(candidate: RetrievedCandidate, fallback_rank: int) -> RerankCandidate:
    payload = candidate.payload
    debug = candidate.debug
    return RerankCandidate(
        candidate_id=candidate.candidate_id,
        text=candidate.text or str(payload.get("text") or payload.get("content") or ""),
        source_type=candidate.source,
        original_rank=int(candidate.rank or fallback_rank),
        retrieval_score=_retrieval_score(candidate),
        dense_score=_score_from_payload_or_debug(payload, debug, "dense_score"),
        sparse_score=_score_from_payload_or_debug(payload, debug, "sparse_score"),
        metadata=payload,
    )


def _retrieval_score(candidate: RetrievedCandidate) -> float | None:
    return candidate.fused_score if candidate.fused_score is not None else candidate.score


def _score_from_payload_or_debug(
    payload: dict[str, Any],
    debug: dict[str, Any],
    field: str,
) -> float | None:
    value = payload.get(field)
    if value is None:
        value = debug.get(field)
    return sanitize_score(value) if value is not None else None


def _semantic_model_available(semantic_reranker: LocalSemanticReranker | None) -> bool:
    if semantic_reranker is not None:
        return bool(semantic_reranker.available)
    model_path = os.getenv("SEMANTIC_RERANK_MODEL_PATH", "").strip()
    return bool(model_path and os.path.exists(model_path))


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
