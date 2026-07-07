"""Taxonomy-backed query expansion for Phase 2A retrieval."""

from __future__ import annotations

from src.knowledge import DrugEntityNormalizer
from src.knowledge.normalizer import normalize_text_key
from src.retrieval.contracts import NormalizedQuery, QueryExpansion


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not value:
            continue
        item = str(value).strip()
        if not item:
            continue
        key = normalize_text_key(item)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def expand_normalized_query(
    normalized_query: NormalizedQuery,
    normalizer: DrugEntityNormalizer | None = None,
) -> QueryExpansion:
    """Expand normalized entities into canonical and alias search terms."""

    normalizer = normalizer or DrugEntityNormalizer()
    canonical_terms: list[str] = []
    alias_terms: list[str] = []
    reasons: list[str] = []

    for product in normalized_query.drug_product:
        canonical_terms.append(product)
        card = normalizer.get_entity_card("drug_product", product)
        if card:
            alias_terms.extend(card.aliases)
            reasons.append(f"drug_product:{product}")

    for ingredient in normalized_query.active_ingredient:
        canonical_terms.append(ingredient)
        card = normalizer.get_entity_card("active_ingredient", ingredient)
        if card:
            alias_terms.extend(card.aliases)
            reasons.append(f"active_ingredient:{ingredient}")

    for class_name in normalized_query.drug_class:
        canonical_terms.append(class_name)
        card = normalizer.get_entity_card("drug_class", class_name)
        if card:
            alias_terms.extend(card.aliases)
            reasons.append(f"drug_class:{class_name}")

    for condition in normalized_query.condition:
        canonical_terms.append(condition)
        card = normalizer.get_entity_card("condition", condition)
        if card:
            alias_terms.extend(card.aliases)
            reasons.append(f"condition:{condition}")

    for safety_context in normalized_query.safety_context:
        canonical_terms.append(safety_context)
        card = normalizer.get_entity_card("safety_context", safety_context)
        if card:
            alias_terms.extend(card.aliases)
            reasons.append(f"safety_context:{safety_context}")

    alias_terms.extend(normalized_query.aliases)
    expanded_terms = _dedupe([
        normalized_query.original_query,
        *canonical_terms,
        *alias_terms,
    ])

    return QueryExpansion(
        original_query=normalized_query.original_query,
        normalized_query=normalized_query,
        expanded_terms=expanded_terms,
        canonical_terms=_dedupe(canonical_terms),
        alias_terms=_dedupe(alias_terms),
        expansion_reason=_dedupe(reasons),
    )


__all__ = ["expand_normalized_query"]
