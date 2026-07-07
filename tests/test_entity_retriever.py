from src.knowledge.entity_cards import build_entity_cards_from_taxonomy
from src.knowledge.entity_index import build_entity_point_payload
from src.retrieval.entity_retriever import retrieve_entity_candidates_from_payloads
from src.retrieval.query_expansion import expand_normalized_query
from src.retrieval.query_normalization import normalize_query


def _payloads():
    return [
        build_entity_point_payload(card, kb_version="acne_kb_v1")
        for card in build_entity_cards_from_taxonomy()
    ]


def test_entity_retriever_exact_match_preserves_payload_fields():
    normalized = normalize_query("Dalacin T là gì?")
    expansion = expand_normalized_query(normalized)
    candidates = retrieve_entity_candidates_from_payloads(normalized, expansion, _payloads())

    assert candidates
    dalacin = next(c for c in candidates if c.payload["canonical_name"] == "Dalacin T")
    assert dalacin.source == "entity"
    assert dalacin.payload["entity_type"] == "drug_product"
    assert "clindamycin" in dalacin.payload["active_ingredients"]
    assert "topical_antibiotic" in dalacin.payload["drug_class"]
    assert dalacin.payload["kb_version"] == "acne_kb_v1"
    assert dalacin.matched_metadata["canonical_name"] == ["Dalacin T"]


def test_entity_retriever_handles_missing_optional_fields():
    normalized = normalize_query("Clindamycin có phải retinoid không?")
    expansion = expand_normalized_query(normalized)
    payload = {
        "entity_type": "active_ingredient",
        "canonical_name": "clindamycin",
        "aliases": ["clindamycin"],
        "drug_class": ["topical_antibiotic"],
        "entity_id": "active_ingredient:test",
    }
    candidates = retrieve_entity_candidates_from_payloads(normalized, expansion, [payload])

    assert len(candidates) == 1
    assert candidates[0].payload["side_effects"] == []
    assert candidates[0].payload["contraindications"] == []


def test_benzoyl_peroxide_entity_exposes_not_antibiotic_metadata():
    normalized = normalize_query("Benzoyl peroxide có phải kháng sinh không?")
    expansion = expand_normalized_query(normalized)
    candidates = retrieve_entity_candidates_from_payloads(normalized, expansion, _payloads())
    bp = next(c for c in candidates if c.payload["canonical_name"] == "benzoyl_peroxide")

    assert bp.payload["metadata"]["not_antibiotic"] is True
    assert "topical_antibiotic" not in bp.payload["drug_class"]
