from src.retrieval.query_expansion import expand_normalized_query
from src.retrieval.query_normalization import normalize_query


def test_expansion_contains_canonical_aliases_and_related_terms():
    normalized = normalize_query("Dalacin T là gì?")
    expansion = expand_normalized_query(normalized)

    assert "Dalacin T" in expansion.expanded_terms
    assert "dalacin" in expansion.expanded_terms
    assert "clindamycin" in expansion.expanded_terms
    assert "topical_antibiotic" in expansion.expanded_terms
    assert "drug_product:Dalacin T" in expansion.expansion_reason


def test_expansion_for_epiduo_contains_both_active_ingredients():
    normalized = normalize_query("Epiduo có BPO không?")
    expansion = expand_normalized_query(normalized)

    assert "Epiduo" in expansion.canonical_terms
    assert "adapalene" in expansion.canonical_terms
    assert "benzoyl_peroxide" in expansion.canonical_terms
    assert "bpo" in expansion.alias_terms
