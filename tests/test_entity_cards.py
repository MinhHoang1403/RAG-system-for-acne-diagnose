from __future__ import annotations

from scripts.build_entity_index import build_dry_run_summary
from src.knowledge.entity_cards import build_entity_cards_from_taxonomy, entity_card_to_text
from src.knowledge.entity_index import build_entity_point_payload


def _find_card(entity_type: str, canonical_name: str):
    for card in build_entity_cards_from_taxonomy():
        if card.entity_type == entity_type and card.canonical_name == canonical_name:
            return card
    raise AssertionError(f"Missing card {entity_type}:{canonical_name}")


def test_build_entity_cards_contains_required_products() -> None:
    product_names = {
        card.canonical_name
        for card in build_entity_cards_from_taxonomy()
        if card.entity_type == "drug_product"
    }

    assert {"Differin", "Epiduo", "Dalacin T"}.issubset(product_names)


def test_dalacin_card_payload() -> None:
    card = _find_card("drug_product", "Dalacin T")

    assert card.canonical_name == "Dalacin T"
    assert "clindamycin" in card.active_ingredients
    assert "topical_antibiotic" in card.drug_class


def test_epiduo_card_payload() -> None:
    card = _find_card("drug_product", "Epiduo")

    assert "adapalene" in card.active_ingredients
    assert "benzoyl_peroxide" in card.active_ingredients


def test_differin_card_payload() -> None:
    card = _find_card("drug_product", "Differin")

    assert "adapalene" in card.active_ingredients
    assert "topical_retinoid" in card.drug_class


def test_benzoyl_peroxide_entity_not_antibiotic() -> None:
    card = _find_card("active_ingredient", "benzoyl_peroxide")
    text = entity_card_to_text(card).lower()

    assert "topical_antibiotic" not in card.drug_class
    assert "oral_antibiotic" not in card.drug_class
    assert card.metadata["not_antibiotic"] is True
    assert "not an antibiotic" in text


def test_entity_stable_id_deterministic() -> None:
    card = _find_card("drug_product", "Epiduo")

    assert card.stable_id("acne_kb_v1") == card.stable_id("acne_kb_v1")
    assert card.stable_id("acne_kb_v1") != card.stable_id("acne_kb_v2")


def test_entity_payload_has_required_fields() -> None:
    card = _find_card("drug_product", "Epiduo")

    payload = build_entity_point_payload(card, kb_version="acne_kb_v1")

    for field_name in [
        "entity_type",
        "canonical_name",
        "aliases",
        "active_ingredients",
        "drug_class",
        "taxonomy_version",
        "entity_schema_version",
        "kb_version",
        "entity_id",
        "text",
        "embedding_provider",
        "embedding_model",
        "embedding_dimensions",
    ]:
        assert field_name in payload
    assert payload["embedding_dimensions"] == 3072


def test_dry_run_summary_does_not_require_qdrant() -> None:
    cards = build_entity_cards_from_taxonomy()

    summary = build_dry_run_summary(cards)

    assert summary["collection"] == "acne_entities_v1"
    assert summary["card_count"] >= 3
    preview_names = {payload["canonical_name"] for payload in summary["preview_payloads"]}
    assert {"Dalacin T", "Epiduo", "Differin", "benzoyl_peroxide"}.issubset(preview_names)
