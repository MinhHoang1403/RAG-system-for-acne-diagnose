from __future__ import annotations

from copy import deepcopy

from scripts.validate_neo4j_schema import offline_snapshot, validate_snapshot


def test_valid_offline_snapshot_passes() -> None:
    report = validate_snapshot(offline_snapshot())

    assert report["passed"] is True
    assert report["failures"] == []


def test_missing_required_property_fails() -> None:
    snapshot = offline_snapshot()
    snapshot["properties_by_label"]["DrugProduct"].remove("metadata_json")

    report = validate_snapshot(snapshot)

    assert report["passed"] is False
    assert "required_node_properties_present" in report["failures"]


def test_duplicate_canonical_name_fails() -> None:
    snapshot = offline_snapshot()
    snapshot["duplicate_canonical_names"] = [
        {"label": "DrugProduct", "canonical_name": "Epiduo", "count": 2}
    ]

    report = validate_snapshot(snapshot)

    assert report["passed"] is False
    assert "no_duplicate_canonical_names" in report["failures"]


def test_invalid_relationship_direction_fails() -> None:
    snapshot = offline_snapshot()
    snapshot["relationship_directions"] = [
        {
            "relationship_type": "HAS_ACTIVE_INGREDIENT",
            "source_labels": ["ActiveIngredient"],
            "target_labels": ["DrugProduct"],
            "count": 1,
        }
    ]

    report = validate_snapshot(snapshot)

    assert report["passed"] is False
    assert "relationship_directions_valid" in report["failures"]


def test_legacy_property_fails_without_dumping_secret() -> None:
    snapshot = deepcopy(offline_snapshot())
    snapshot["property_keys"]["name"] = 1

    report = validate_snapshot(snapshot)
    serialized = str(report).lower()

    assert report["passed"] is False
    assert "no_legacy_properties" in report["failures"]
    assert "password" not in serialized

