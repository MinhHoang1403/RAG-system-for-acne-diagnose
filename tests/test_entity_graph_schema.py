from __future__ import annotations

from scripts.build_entity_graph import build_dry_run_summary
from src.knowledge.entity_cards import build_entity_cards_from_taxonomy
from src.knowledge.graph_schema import (
    build_entity_graph_records,
    get_entity_graph_constraints,
)


def _records() -> dict[str, list[dict]]:
    return build_entity_graph_records(build_entity_cards_from_taxonomy())


def _node_set(records: dict[str, list[dict]]) -> set[tuple[str, str]]:
    return {
        (node["label"], node["canonical_name"])
        for node in records["nodes"]
    }


def _relationship_set(records: dict[str, list[dict]]) -> set[tuple[str, str, str, str, str]]:
    return {
        (
            rel["source_label"],
            rel["source_name"],
            rel["relationship"],
            rel["target_label"],
            rel["target_name"],
        )
        for rel in records["relationships"]
    }


def test_build_graph_records_required_nodes() -> None:
    nodes = _node_set(_records())

    assert ("DrugProduct", "Dalacin T") in nodes
    assert ("DrugProduct", "Epiduo") in nodes
    assert ("DrugProduct", "Differin") in nodes
    assert ("ActiveIngredient", "clindamycin") in nodes
    assert ("ActiveIngredient", "adapalene") in nodes
    assert ("ActiveIngredient", "benzoyl_peroxide") in nodes
    assert ("DrugClass", "topical_antibiotic") in nodes
    assert ("DrugClass", "topical_retinoid") in nodes


def test_dalacin_relationships() -> None:
    relationships = _relationship_set(_records())

    assert (
        "DrugProduct",
        "Dalacin T",
        "HAS_ACTIVE_INGREDIENT",
        "ActiveIngredient",
        "clindamycin",
    ) in relationships
    assert (
        "ActiveIngredient",
        "clindamycin",
        "BELONGS_TO_CLASS",
        "DrugClass",
        "topical_antibiotic",
    ) in relationships


def test_epiduo_relationships() -> None:
    relationships = _relationship_set(_records())

    assert (
        "DrugProduct",
        "Epiduo",
        "HAS_ACTIVE_INGREDIENT",
        "ActiveIngredient",
        "adapalene",
    ) in relationships
    assert (
        "DrugProduct",
        "Epiduo",
        "HAS_ACTIVE_INGREDIENT",
        "ActiveIngredient",
        "benzoyl_peroxide",
    ) in relationships
    assert (
        "ActiveIngredient",
        "adapalene",
        "BELONGS_TO_CLASS",
        "DrugClass",
        "topical_retinoid",
    ) in relationships
    assert (
        "ActiveIngredient",
        "benzoyl_peroxide",
        "BELONGS_TO_CLASS",
        "DrugClass",
        "topical_antibiotic",
    ) not in relationships
    assert (
        "ActiveIngredient",
        "benzoyl_peroxide",
        "BELONGS_TO_CLASS",
        "DrugClass",
        "oral_antibiotic",
    ) not in relationships


def test_differin_relationships() -> None:
    relationships = _relationship_set(_records())

    assert (
        "DrugProduct",
        "Differin",
        "HAS_ACTIVE_INGREDIENT",
        "ActiveIngredient",
        "adapalene",
    ) in relationships
    assert (
        "ActiveIngredient",
        "adapalene",
        "BELONGS_TO_CLASS",
        "DrugClass",
        "topical_retinoid",
    ) in relationships


def test_constraints_have_unique_canonical_name() -> None:
    constraints = get_entity_graph_constraints()
    labels = [
        "DrugProduct",
        "ActiveIngredient",
        "DrugClass",
        "Condition",
        "SafetyContext",
        "SideEffect",
    ]

    for label in labels:
        matching = [constraint for constraint in constraints if f"(n:{label})" in constraint]
        assert matching
        assert "REQUIRE n.canonical_name IS UNIQUE" in matching[0]


def test_dry_run_build_entity_graph_no_neo4j_required() -> None:
    summary = build_dry_run_summary()

    assert summary["card_count"] == 20
    assert summary["node_count"] >= 20
    assert summary["relationship_count"] >= 1
    assert summary["nodes_by_label"]["DrugProduct"] == 3
    assert "HAS_ACTIVE_INGREDIENT" in summary["relationships_by_type"]
    preview_names = {node["canonical_name"] for node in summary["preview"]["nodes"]}
    assert {"Dalacin T", "Epiduo", "Differin", "benzoyl_peroxide"}.issubset(preview_names)
