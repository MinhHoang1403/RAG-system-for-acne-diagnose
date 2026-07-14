"""Entity-aware context packing for Phase 2B retrieval."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from src.retrieval.contracts import (
    ContextItem,
    ContextPackTrace,
    NormalizedQuery,
    PackedContext,
    RetrievedCandidate,
)

DRUG_INTENTS = {"drug_identity", "ingredient_question", "class_check", "comparison"}


def pack_context(
    normalized_query: NormalizedQuery,
    merged_candidates: list[RetrievedCandidate],
    max_items: int = 8,
    max_chars: int = 6000,
) -> PackedContext:
    """Pack merged retrieval candidates into prompt-ready context text."""

    warnings: list[str] = []
    selected: list[ContextItem] = []
    dropped: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_text: set[str] = set()

    ordered = _order_candidates_for_intent(normalized_query, merged_candidates)

    for candidate in ordered:
        if len(selected) >= max_items:
            dropped.append(_drop_record(candidate, "max_items"))
            continue
        key = _dedupe_key(candidate)
        if key in seen:
            dropped.append(_drop_record(candidate, "duplicate"))
            continue
        item = _candidate_to_item(candidate, normalized_query)
        if not item.text.strip():
            dropped.append(_drop_record(candidate, "empty_text"))
            continue
        text_key = _near_duplicate_text_key(item.text)
        if text_key and text_key in seen_text:
            dropped.append(_drop_record(candidate, "near_duplicate_text"))
            continue
        selected.append(item)
        seen.add(key)
        if text_key:
            seen_text.add(text_key)

    selected = _ensure_intent_requirements(normalized_query, selected, ordered, seen, max_items, dropped)

    if not selected:
        warnings.append("No retrieval candidates selected for packed context.")
    if normalized_query.intent in DRUG_INTENTS:
        has_entity = any(item.source == "entity" for item in selected)
        has_chunk = any(item.source == "chunk" for item in selected)
        if has_entity and not has_chunk:
            warnings.append("Drug intent packed context has entity card but no chunk evidence.")
    if normalized_query.intent == "acne_type" and not any(item.source == "chunk" for item in selected):
        warnings.append("Acne type packed context has no chunk evidence.")

    context_text = _build_context_text(selected, max_chars=max_chars, warnings=warnings)
    trace = ContextPackTrace(
        intent=normalized_query.intent,
        selected_entity_ids=[
            item.payload.get("entity_id") or item.payload.get("point_id") or item.item_id
            for item in selected
            if item.source == "entity"
        ],
        selected_chunk_ids=[
            item.payload.get("chunk_id") or item.payload.get("point_id") or item.item_id
            for item in selected
            if item.source == "chunk"
        ],
        selection_reasons=[item.reason for item in selected],
        dropped_candidates=dropped[:20],
        warnings=warnings,
    )
    return PackedContext(
        original_query=normalized_query.original_query,
        intent=normalized_query.intent,
        items=selected,
        context_text=context_text,
        entity_items_count=sum(1 for item in selected if item.source == "entity"),
        chunk_items_count=sum(1 for item in selected if item.source == "chunk"),
        warnings=warnings,
        debug={"pack_trace": trace.model_dump(mode="json")},
    )


def _order_candidates_for_intent(
    normalized_query: NormalizedQuery,
    candidates: list[RetrievedCandidate],
) -> list[RetrievedCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: (
            _intent_priority(normalized_query, candidate),
            candidate.fused_score if candidate.fused_score is not None else candidate.score or 0.0,
        ),
        reverse=True,
    )


def _intent_priority(normalized_query: NormalizedQuery, candidate: RetrievedCandidate) -> float:
    payload = candidate.payload
    score = 0.0
    if normalized_query.intent in DRUG_INTENTS:
        if candidate.source == "entity" and payload.get("entity_type") in {
            "drug_product",
            "active_ingredient",
            "drug_class",
        }:
            score += 4.0
        if candidate.source == "chunk" and _has_any_match(
            candidate,
            ("drug_product", "active_ingredient", "drug_class", "query_intent_hint"),
        ):
            score += 3.0
    elif normalized_query.intent == "side_effect":
        if candidate.source == "entity" and payload.get("side_effects"):
            score += 4.0
        if candidate.source == "chunk" and _has_any_match(
            candidate,
            ("query_intent_hint", "safety_context", "active_ingredient", "drug_class"),
        ):
            score += 3.5
    elif normalized_query.intent == "safety":
        if candidate.source == "entity" and (payload.get("contraindications") or payload.get("safety_contexts")):
            score += 4.0
        if candidate.source == "chunk" and _has_any_match(
            candidate,
            ("safety_context", "query_intent_hint", "drug_class", "active_ingredient"),
        ):
            score += 3.5
    elif normalized_query.intent == "acne_type":
        if candidate.source == "chunk" and _has_any_match(
            candidate,
            ("concern", "content_type", "condition", "domain_topic"),
        ):
            score += 5.0
        if candidate.source == "entity" and payload.get("entity_type") == "condition":
            score += 2.0
        if candidate.source == "entity" and payload.get("entity_type") in {"drug_product", "active_ingredient"}:
            score -= 3.0
    else:
        if candidate.source == "chunk":
            score += 3.0
        if candidate.source == "entity" and _query_has_entity(normalized_query):
            score += 2.0
    return score


def _ensure_intent_requirements(
    normalized_query: NormalizedQuery,
    selected: list[ContextItem],
    ordered: list[RetrievedCandidate],
    seen: set[str],
    max_items: int,
    dropped: list[dict[str, Any]],
) -> list[ContextItem]:
    if normalized_query.intent in DRUG_INTENTS:
        selected = _ensure_primary_entity_coverage(
            normalized_query,
            selected,
            ordered,
            seen,
            max_items,
            dropped,
        )
        selected = _ensure_source(
            selected,
            ordered,
            seen,
            source="entity",
            max_items=max_items,
            dropped=dropped,
            normalized_query=normalized_query,
        )
        selected = _ensure_source(
            selected,
            ordered,
            seen,
            source="chunk",
            max_items=max_items,
            dropped=dropped,
            normalized_query=normalized_query,
        )
    elif normalized_query.intent == "acne_type":
        selected = _ensure_source(
            selected,
            ordered,
            seen,
            source="chunk",
            max_items=max_items,
            dropped=dropped,
            normalized_query=normalized_query,
        )
        selected = [
            item for item in selected
            if item.source == "chunk" or item.payload.get("entity_type") == "condition"
        ]
    return selected[:max_items]


def _ensure_primary_entity_coverage(
    normalized_query: NormalizedQuery,
    selected: list[ContextItem],
    ordered: list[RetrievedCandidate],
    seen: set[str],
    max_items: int,
    dropped: list[dict[str, Any]],
) -> list[ContextItem]:
    """Keep entity-card evidence for every primary entity named in a drug query."""

    targets = _primary_entity_targets(normalized_query)
    if not targets:
        return selected

    for target in targets:
        if _selected_has_entity_target(selected, target):
            continue
        for candidate in ordered:
            if candidate.source != "entity" or not _candidate_matches_entity_target(candidate, target):
                continue
            key = _dedupe_key(candidate)
            if key in seen:
                continue
            item = _candidate_to_item(candidate, normalized_query)
            if not item.text.strip():
                dropped.append(_drop_record(candidate, "empty_text"))
                continue
            if len(selected) >= max_items:
                replace_index = _replacement_index_for_primary_entity(selected)
                replaced = selected[replace_index]
                dropped.append(
                    {
                        "candidate_id": replaced.item_id,
                        "source": replaced.source,
                        "reason": f"replaced_to_include_primary_entity:{target}",
                    }
                )
                selected = [*selected[:replace_index], *selected[replace_index + 1:]]
            selected.append(item)
            seen.add(key)
            break
    return selected


def _primary_entity_targets(normalized_query: NormalizedQuery) -> list[str]:
    values = [*normalized_query.drug_product, *normalized_query.active_ingredient]
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(key)
    return output


def _selected_has_entity_target(selected: list[ContextItem], target: str) -> bool:
    return any(
        item.source == "entity" and _payload_matches_entity_target(item.payload, target)
        for item in selected
    )


def _candidate_matches_entity_target(candidate: RetrievedCandidate, target: str) -> bool:
    return _payload_matches_entity_target(candidate.payload, target)


def _payload_matches_entity_target(payload: dict[str, Any], target: str) -> bool:
    values = [
        payload.get("canonical_name"),
        payload.get("entity_id"),
        *_as_list(payload.get("aliases")),
    ]
    return any(_key(value) == target or _key(value).split(":")[-1] == target for value in values)


def _replacement_index_for_primary_entity(selected: list[ContextItem]) -> int:
    for index in range(len(selected) - 1, -1, -1):
        if selected[index].source != "entity":
            return index
    return len(selected) - 1


def _ensure_source(
    selected: list[ContextItem],
    ordered: list[RetrievedCandidate],
    seen: set[str],
    *,
    source: str,
    max_items: int,
    dropped: list[dict[str, Any]],
    normalized_query: NormalizedQuery,
) -> list[ContextItem]:
    if any(item.source == source for item in selected):
        return selected
    for candidate in ordered:
        if candidate.source != source:
            continue
        key = _dedupe_key(candidate)
        if key in seen:
            continue
        item = _candidate_to_item(candidate, normalized_query)
        if not item.text.strip():
            dropped.append(_drop_record(candidate, "empty_text"))
            continue
        if len(selected) >= max_items:
            replaced = selected[-1]
            dropped.append(
                {
                    "candidate_id": replaced.item_id,
                    "source": replaced.source,
                    "reason": f"replaced_to_include_{source}",
                }
            )
            selected = selected[:-1]
        selected.append(item)
        seen.add(key)
        return selected
    return selected


def _candidate_to_item(candidate: RetrievedCandidate, normalized_query: NormalizedQuery) -> ContextItem:
    role = _role_for_candidate(candidate, normalized_query)
    return ContextItem(
        item_id=candidate.candidate_id,
        source=candidate.source,
        role=role,
        text=_safe_text(candidate.text),
        payload=dict(candidate.payload),
        score=candidate.score,
        fused_score=candidate.fused_score,
        rank=candidate.rank,
        matched_metadata=dict(candidate.matched_metadata),
        reason=_selection_reason(candidate, normalized_query, role),
    )


def _role_for_candidate(candidate: RetrievedCandidate, normalized_query: NormalizedQuery) -> str:
    if normalized_query.intent == "side_effect":
        return "side_effect_context" if candidate.source == "chunk" else "primary_entity"
    if normalized_query.intent == "safety":
        return "safety_context"
    if normalized_query.intent == "acne_type":
        return "acne_type_context" if candidate.source == "chunk" else "supporting_evidence"
    if candidate.source == "entity":
        return "primary_entity"
    return "supporting_evidence"


def _selection_reason(candidate: RetrievedCandidate, normalized_query: NormalizedQuery, role: str) -> str:
    matches = ", ".join(sorted(candidate.matched_metadata)) or "score"
    return f"{role}: selected for {normalized_query.intent} via {matches}"


def _build_context_text(items: list[ContextItem], max_chars: int, warnings: list[str]) -> str:
    blocks: list[str] = []
    entity_index = 0
    chunk_index = 0
    for item in items:
        if item.source == "entity":
            entity_index += 1
            blocks.append(_entity_block(item, entity_index))
        else:
            chunk_index += 1
            blocks.append(_chunk_block(item, chunk_index))
    text = "\n\n".join(blocks)
    if len(text) > max_chars:
        warnings.append(f"Packed context truncated to {max_chars} characters.")
        return text[: max(max_chars - 20, 0)].rstrip() + "\n...[truncated]"
    return text


def _entity_block(item: ContextItem, index: int) -> str:
    payload = item.payload
    lines = [
        f"[ENTITY CARD #{index}]",
        f"Name: {payload.get('canonical_name', '')}",
        f"Type: {payload.get('entity_type', '')}",
    ]
    _append_list_line(lines, "Active ingredients", payload.get("active_ingredients"))
    _append_list_line(lines, "Drug class", payload.get("drug_class"))
    _append_list_line(lines, "Safety contexts", payload.get("safety_contexts"))
    _append_list_line(lines, "Contraindications", payload.get("contraindications"))
    _append_list_line(lines, "Side effects", payload.get("side_effects"))
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    if metadata.get("not_antibiotic") is True:
        lines.append("Metadata: not_antibiotic=true")
    lines.append(f"Reason: {item.reason}")
    lines.append(f"Text: {_shorten(item.text, 1200)}")
    return "\n".join(line for line in lines if line.strip())


def _chunk_block(item: ContextItem, index: int) -> str:
    payload = item.payload
    lines = [
        f"[EVIDENCE CHUNK #{index}]",
        f"Source file: {payload.get('source_file', '')}",
        f"Header: {payload.get('header') or payload.get('parent_header_path') or ''}",
        f"Matched metadata: {_format_metadata(item.matched_metadata)}",
        f"Reason: {item.reason}",
        f"Text: {_shorten(item.text, 1500)}",
    ]
    return "\n".join(line for line in lines if line.strip())


def packed_context_to_legacy_contexts(packed_context: PackedContext) -> list[dict[str, Any]]:
    """Bridge PackedContext items into the existing prompt context list format."""

    contexts: list[dict[str, Any]] = []
    for item in packed_context.items:
        payload = dict(item.payload)
        payload["text"] = item.text
        payload["score"] = item.fused_score if item.fused_score is not None else item.score
        payload["retrieval_source"] = item.source
        payload["context_role"] = item.role
        payload["matched_metadata"] = item.matched_metadata
        payload["context_pack_reason"] = item.reason
        if item.source == "entity":
            payload.setdefault("source_file", f"entity:{item.payload.get('entity_type', 'entity')}")
            payload.setdefault("header", item.payload.get("entity_type", "entity"))
        contexts.append(payload)
    return contexts


def _has_any_match(candidate: RetrievedCandidate, fields: tuple[str, ...]) -> bool:
    if any(field in candidate.matched_metadata for field in fields):
        return True
    for field in fields:
        if candidate.payload.get(field):
            return True
    return False


def _query_has_entity(normalized_query: NormalizedQuery) -> bool:
    return any([
        normalized_query.drug_product,
        normalized_query.active_ingredient,
        normalized_query.drug_class,
    ])


def _dedupe_key(candidate: RetrievedCandidate) -> str:
    payload = candidate.payload
    for field in ("entity_id", "chunk_id", "point_id"):
        value = payload.get(field)
        if value:
            return f"{candidate.source}:{value}"
    text = candidate.text.strip()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{candidate.source}:text:{digest}"


def _near_duplicate_text_key(text: str) -> str:
    normalized = re.sub(r"\W+", " ", _safe_text(text).lower()).strip()
    if len(normalized) < 80:
        return ""
    prefix = normalized[:320]
    return hashlib.sha256(prefix.encode("utf-8")).hexdigest()[:16]


def _drop_record(candidate: RetrievedCandidate, reason: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "source": candidate.source,
        "rank": candidate.rank,
        "reason": reason,
    }


def _append_list_line(lines: list[str], label: str, value: Any) -> None:
    values = _as_list(value)
    if values:
        lines.append(f"{label}: {', '.join(values)}")


def _format_metadata(metadata: dict[str, Any]) -> str:
    if not metadata:
        return "(none)"
    parts: list[str] = []
    for key in sorted(metadata):
        values = _as_list(metadata[key])
        parts.append(f"{key}={','.join(values)}")
    return "; ".join(parts)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)] if value else []


def _safe_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _shorten(text: str, max_len: int) -> str:
    text = _safe_text(text)
    if len(text) <= max_len:
        return text
    return text[: max(max_len - 15, 0)].rstrip() + " ...[truncated]"


__all__ = ["pack_context", "packed_context_to_legacy_contexts"]
