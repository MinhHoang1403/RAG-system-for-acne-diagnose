from __future__ import annotations

from scripts.plan_entity_index_update import build_entity_index_update_plan
from src.knowledge.entity_index import build_entity_point_payload, entity_identity_key, entity_point_id
from src.knowledge.taxonomy_models import load_taxonomy_catalog


def test_entity_index_planner_is_dry_run_and_finds_new_class_card() -> None:
    plan = build_entity_index_update_plan()

    assert plan["mutation_executed"] is False
    assert "drug_class:azelaic_acid" in plan["new"]
    assert plan["delete_candidates"] == []
    assert plan["conflicts"] == []


def test_payload_version_change_produces_updated_not_conflict() -> None:
    plan = build_entity_index_update_plan()

    assert plan["updated"]
    assert plan["conflicts"] == []
    assert plan["existing_point_ids_reused"] == 20


def test_existing_point_id_is_reused_from_snapshot() -> None:
    card = next(card for card in load_taxonomy_catalog().to_entity_cards() if card.canonical_name == "Epiduo")
    existing_payload = build_entity_point_payload(
        card.model_copy(update={"taxonomy_version": "drug_taxonomy_v1", "entity_schema_version": "entity_schema_v1"}),
        point_id="existing-epiduo-point",
    )
    plan = build_entity_index_update_plan(existing_points=[{"point_id": "existing-epiduo-point", "payload": existing_payload}])

    epiduo = next(item for item in plan["reused_point_ids"] if item["identity"] == entity_identity_key(card))
    assert epiduo["point_id"] == "existing-epiduo-point"
    assert entity_identity_key(card) in plan["updated"]


def test_new_entity_receives_deterministic_stable_id() -> None:
    cards = load_taxonomy_catalog().to_entity_cards()
    card = next(card for card in cards if card.entity_type == "drug_class" and card.canonical_name == "azelaic_acid")
    existing_points = []
    for existing_card in cards:
        if entity_identity_key(existing_card) == entity_identity_key(card):
            continue
        payload = build_entity_point_payload(existing_card)
        existing_points.append({"point_id": payload["point_id"], "payload": payload})
    plan = build_entity_index_update_plan(existing_points=existing_points)
    preview = next(payload for payload in plan["preview_payloads"] if payload["canonical_name"] == "azelaic_acid")

    assert "drug_class:azelaic_acid" in plan["new"]
    assert preview["point_id"] == entity_point_id(card)


def test_duplicate_canonical_matches_produce_conflict() -> None:
    payload = {
        "entity_type": "drug_product",
        "canonical_name": "Differin",
        "metadata": {"taxonomy_key": "differin"},
    }

    plan = build_entity_index_update_plan(
        existing_points=[
            {"point_id": "point-1", "payload": payload},
            {"point_id": "point-2", "payload": payload},
        ]
    )

    assert plan["apply_blocked"] is True
    assert any(conflict["reason"].startswith("multiple existing points") for conflict in plan["conflicts"])


def test_point_id_occupied_by_another_entity_produces_conflict() -> None:
    plan = build_entity_index_update_plan(
        existing_points=[
            {
                "point_id": "same-point",
                "payload": {
                    "entity_type": "drug_product",
                    "canonical_name": "Differin",
                    "metadata": {"taxonomy_key": "differin"},
                },
            },
            {
                "point_id": "same-point",
                "payload": {
                    "entity_type": "drug_product",
                    "canonical_name": "Epiduo",
                    "metadata": {"taxonomy_key": "epiduo"},
                },
            },
        ]
    )

    assert plan["apply_blocked"] is True
    assert any(conflict["reason"] == "point ID is occupied by multiple canonical identities" for conflict in plan["conflicts"])


def test_dry_run_performs_no_upsert_or_delete() -> None:
    plan = build_entity_index_update_plan()

    assert plan["mutation_executed"] is False
    assert plan["delete_candidates"] == []
