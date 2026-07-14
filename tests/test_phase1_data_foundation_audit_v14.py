from __future__ import annotations

import json

from scripts.eval_phase1_data_foundation_v14 import (
    StoreCoverage,
    build_entity_coverage_matrix,
    classify_fact_presence,
    cross_store_entity_id_consistency,
    full_reingestion_guard,
    infer_phase1_action,
    manifest_integrity,
    normalize_for_search,
    relation_exists,
    text_contains_any,
)


def test_tazorac_alias_resolution_fixture() -> None:
    text = "Tazorac is a brand name for tazarotene topical retinoid."

    assert text_contains_any(text, ["Tazorac"])
    assert text_contains_any(text, ["tazarotene"])
    assert normalize_for_search("Tazarotene") == "tazarotene"


def test_tazorac_tazarotene_relation_fixture() -> None:
    neo4j = {
        "product_ingredient_relationships": [
            {"product": "Tazorac", "relation": "HAS_ACTIVE_INGREDIENT", "ingredient": "tazarotene"}
        ],
        "ingredient_class_relationships": [
            {"ingredient": "tazarotene", "relation": "BELONGS_TO_CLASS", "class": "topical_retinoid"}
        ],
    }

    assert relation_exists(neo4j, ("Tazorac", "HAS_ACTIVE_INGREDIENT", "tazarotene"))
    assert relation_exists(neo4j, ("tazarotene", "BELONGS_TO_CLASS", "topical_retinoid"))


def test_differin_and_epiduo_active_ingredient_relations_fixture() -> None:
    neo4j = {
        "product_ingredient_relationships": [
            {"product": "Differin", "relation": "HAS_ACTIVE_INGREDIENT", "ingredient": "adapalene"},
            {"product": "Epiduo", "relation": "HAS_ACTIVE_INGREDIENT", "ingredient": "adapalene"},
            {"product": "Epiduo", "relation": "HAS_ACTIVE_INGREDIENT", "ingredient": "benzoyl_peroxide"},
        ],
        "ingredient_class_relationships": [],
    }

    assert relation_exists(neo4j, ("Differin", "HAS_ACTIVE_INGREDIENT", "adapalene"))
    assert relation_exists(neo4j, ("Epiduo", "HAS_ACTIVE_INGREDIENT", "adapalene"))
    assert relation_exists(neo4j, ("Epiduo", "HAS_ACTIVE_INGREDIENT", "benzoyl_peroxide"))


def test_shared_retinoid_class_fixture() -> None:
    neo4j = {
        "product_ingredient_relationships": [],
        "ingredient_class_relationships": [
            {"ingredient": "adapalene", "relation": "BELONGS_TO_CLASS", "class": "topical_retinoid"},
            {"ingredient": "tazarotene", "relation": "BELONGS_TO_CLASS", "class": "topical_retinoid"},
            {"ingredient": "tretinoin", "relation": "BELONGS_TO_CLASS", "class": "topical_retinoid"},
        ],
    }

    assert relation_exists(neo4j, ("adapalene", "BELONGS_TO_CLASS", "topical_retinoid"))
    assert relation_exists(neo4j, ("tazarotene", "BELONGS_TO_CLASS", "topical_retinoid"))
    assert relation_exists(neo4j, ("tretinoin", "BELONGS_TO_CLASS", "topical_retinoid"))


def test_manifest_integrity_detects_hash_and_point_ids(tmp_path) -> None:
    source = tmp_path / "source.json"
    source.write_text('{"ok": true}\n', encoding="utf-8")
    manifest = tmp_path / "ingestion_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": {
                    str(source): {
                        "status": "completed",
                        "document_id": "doc-1",
                        "source_type": "web_json",
                        "content_hash": "wrong-hash",
                        "qdrant_indexed": True,
                        "qdrant_point_ids": ["point-1"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = manifest_integrity(manifest)

    assert result["document_count"] == 1
    assert result["total_qdrant_point_ids"] == 1
    assert result["hash_mismatches"] == [str(source)]


def test_cross_store_entity_id_consistency_detects_mismatch() -> None:
    qdrant_points = [
        (
            "point-1",
            {
                "entity_type": "drug_product",
                "canonical_name": "Differin",
                "entity_id": "drug_product:one",
            },
        )
    ]
    neo4j = {
        "critical_nodes": [
            {
                "entity_type": "drug_product",
                "canonical_name": "Differin",
                "entity_id": "drug_product:two",
            }
        ]
    }

    result = cross_store_entity_id_consistency(qdrant_points, neo4j)

    assert result["shared_entities"] == 1
    assert result["mismatches"][0]["canonical_name"] == "differin"


def test_missing_entity_detection_in_coverage_matrix() -> None:
    report = {
        "source_coverage": {"entity_evidence": {"Tazorac": [{"path": "sample_data/web_raw_dataset.json"}]}},
        "qdrant": {
            "knowledge": {"entity_matches": {"Tazorac": {"samples": [{}]}}},
            "entities": {"entity_matches": {}},
        },
        "taxonomy": {"coverage": {"Tazorac": {"alias_present": False, "resolved_canonical_names": []}}},
        "neo4j": {"product_ingredient_relationships": [], "ingredient_class_relationships": []},
    }

    matrix = build_entity_coverage_matrix(report)

    assert matrix["Tazorac"]["source_present"] is True
    assert matrix["Tazorac"]["knowledge_present"] is True
    assert matrix["Tazorac"]["entity_card_present"] is False
    assert matrix["Tazorac"]["alias_present"] is False


def test_targeted_reingestion_decision_when_knowledge_missing_but_source_present() -> None:
    action = infer_phase1_action(
        StoreCoverage(
            source_present=True,
            knowledge_present=False,
            entity_present=False,
            graph_present=False,
            runtime_detected=False,
        )
    )

    assert action == "C"


def test_entity_index_rebuild_decision_when_knowledge_exists_but_entity_graph_missing() -> None:
    action = infer_phase1_action(
        StoreCoverage(
            source_present=True,
            knowledge_present=True,
            entity_present=False,
            graph_present=False,
            runtime_detected=False,
        )
    )

    assert action == "D"


def test_full_reingestion_decision_guard_requires_systemic_integrity_error() -> None:
    clean_report = {
        "manifest_integrity": {
            "hash_mismatches": [],
            "duplicate_document_ids": [],
            "duplicate_point_ids": [],
        },
        "qdrant": {"knowledge": {"duplicate_chunk_ids": [], "missing_required_metadata": {}}},
    }
    dirty_report = {
        "manifest_integrity": {
            "hash_mismatches": ["sample_data/source.pdf"],
            "duplicate_document_ids": [],
            "duplicate_point_ids": [],
        },
        "qdrant": {"knowledge": {"duplicate_chunk_ids": [], "missing_required_metadata": {}}},
    }

    assert full_reingestion_guard(clean_report) is False
    assert full_reingestion_guard(dirty_report) is True


def test_fact_presence_classification() -> None:
    assert classify_fact_presence(0) == "fact absent"
    assert classify_fact_presence(1) == "fact present and correct"
    assert classify_fact_presence(1, ambiguous=True) == "fact present but ambiguous"
    assert classify_fact_presence(1, conflicting=True) == "fact present but conflicting"
