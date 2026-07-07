from src.database.graph_store import (
    ENTITY_CONTEXT_CYPHER,
    KEYWORD_SEARCH_CYPHER,
    _normalize_entity_names,
    _normalize_keywords,
)


def test_graph_store_entity_lookup_supports_deterministic_and_legacy_schema():
    canonical_names, legacy_names = _normalize_entity_names(
        ["Dalacin T", " benzoyl_peroxide ", "Dalacin T"]
    )

    assert canonical_names == ["benzoyl_peroxide", "Dalacin T"]
    assert legacy_names == ["benzoyl_peroxide", "dalacin t"]
    assert "n.canonical_name IN $canonical_names" in ENTITY_CONTEXT_CYPHER
    assert "toLower(coalesce(n.canonical_name, n.name, ''))" in ENTITY_CONTEXT_CYPHER
    assert "coalesce(n.canonical_name, n.name) AS entity" in ENTITY_CONTEXT_CYPHER


def test_graph_store_keyword_search_uses_canonical_or_legacy_name():
    keywords = _normalize_keywords([" BP ", "acne", "  ", "da"])

    assert keywords == ["acne"]
    assert "canonical_name" in KEYWORD_SEARCH_CYPHER
    assert "n.name" in KEYWORD_SEARCH_CYPHER
    assert "CONTAINS kw" in KEYWORD_SEARCH_CYPHER
