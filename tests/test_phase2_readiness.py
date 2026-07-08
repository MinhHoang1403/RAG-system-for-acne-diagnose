from src.database.graph_store import (
    ENTITY_CONTEXT_CYPHER,
    KEYWORD_SEARCH_CYPHER,
    _normalize_entity_names,
    _normalize_keywords,
)


def test_graph_store_entity_lookup_supports_deterministic_and_legacy_schema():
    canonical_names, lookup_names = _normalize_entity_names(
        ["Dalacin T", " benzoyl_peroxide ", "Dalacin T"]
    )

    assert canonical_names == ["benzoyl_peroxide", "Dalacin T"]
    assert lookup_names == ["benzoyl_peroxide", "dalacin t"]
    assert "n.canonical_name IN $canonical_names" in ENTITY_CONTEXT_CYPHER
    assert "n.aliases" in ENTITY_CONTEXT_CYPHER
    assert ".name" not in ENTITY_CONTEXT_CYPHER
    assert "n.canonical_name AS entity" in ENTITY_CONTEXT_CYPHER


def test_graph_store_keyword_search_uses_canonical_name_or_aliases():
    keywords = _normalize_keywords([" BP ", "acne", "  ", "da"])

    assert keywords == ["acne"]
    assert "canonical_name" in KEYWORD_SEARCH_CYPHER
    assert "n.aliases" in KEYWORD_SEARCH_CYPHER
    assert ".name" not in KEYWORD_SEARCH_CYPHER
    assert "CONTAINS kw" in KEYWORD_SEARCH_CYPHER
