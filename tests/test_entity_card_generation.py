from __future__ import annotations

from src.knowledge.entity_index import build_entity_point_payload, entity_identity_key, entity_point_id
from src.knowledge.taxonomy_models import load_taxonomy_catalog


def test_v2_entity_cards_include_verified_only() -> None:
    catalog = load_taxonomy_catalog()
    cards = catalog.to_entity_cards(verified_only=True)

    assert len(cards) == 21
    assert all(card.metadata["review_status"] == "verified" for card in cards)
    assert any(card.entity_type == "drug_class" and card.canonical_name == "azelaic_acid" for card in cards)


def test_v2_entity_card_payload_keeps_runtime_contract() -> None:
    card = next(card for card in load_taxonomy_catalog().to_entity_cards() if card.canonical_name == "Epiduo")
    payload = build_entity_point_payload(card)

    for field in ("canonical_name", "entity_type", "aliases", "metadata", "taxonomy_version", "entity_id", "point_id"):
        assert field in payload
    assert payload["taxonomy_version"] == "drug_taxonomy_v2"
    assert payload["metadata"]["source_references"]
    assert entity_point_id(card) == payload["point_id"]


def test_taxonomy_and_schema_version_do_not_change_canonical_identity() -> None:
    card = next(card for card in load_taxonomy_catalog().to_entity_cards() if card.canonical_name == "Epiduo")
    changed = card.model_copy(
        update={
            "taxonomy_version": "drug_taxonomy_v99",
            "entity_schema_version": "entity_schema_v99",
        }
    )

    assert entity_identity_key(card) == entity_identity_key(changed)
    assert entity_point_id(card) == entity_point_id(changed)
