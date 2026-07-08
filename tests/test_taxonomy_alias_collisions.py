from __future__ import annotations

from src.knowledge.taxonomy_models import DrugClassEntity, SourceReference, load_taxonomy_catalog, validate_taxonomy_catalog


def test_allowed_alias_collisions_do_not_fail_validation() -> None:
    report = validate_taxonomy_catalog(load_taxonomy_catalog())

    assert report.passed is True
    assert any("Allowed alias collisions" in warning for warning in report.warnings)


def test_unresolved_alias_collision_fails() -> None:
    catalog = load_taxonomy_catalog()
    broken = catalog.model_copy(deep=True)
    broken.entities.append(
        DrugClassEntity(
            canonical_name="fake_conflict",
            entity_type="drug_class",
            display_name="fake conflict",
            aliases=["differin"],
            source_references=[
                SourceReference(
                    source_id="manual:test",
                    source_type="manual_review",
                    locator="tests",
                )
            ],
            review_status="verified",
            taxonomy_version=broken.taxonomy_version,
            entity_schema_version=broken.entity_schema_version,
        )
    )

    report = validate_taxonomy_catalog(broken)

    assert report.passed is False
    assert "alias_collision" in report.failures
