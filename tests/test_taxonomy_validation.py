from __future__ import annotations

from copy import deepcopy

import pytest

from src.knowledge.taxonomy_models import load_taxonomy_catalog, validate_taxonomy_catalog


def test_valid_taxonomy_passes() -> None:
    report = validate_taxonomy_catalog(load_taxonomy_catalog())

    assert report.passed is True
    assert report.verified_count == 21
    assert report.draft_count == 0


def test_missing_provenance_fails() -> None:
    catalog = load_taxonomy_catalog()
    broken = catalog.model_copy(deep=True)
    broken.entities[0].source_references.clear()

    report = validate_taxonomy_catalog(broken)

    assert report.passed is False
    assert "missing_provenance" in report.failures


def test_product_unknown_ingredient_fails() -> None:
    catalog = load_taxonomy_catalog()
    broken = catalog.model_copy(deep=True)
    product = next(entity for entity in broken.entities if entity.entity_type == "drug_product")
    product.active_ingredients.append("unknown_ingredient")

    report = validate_taxonomy_catalog(broken)

    assert report.passed is False
    assert "drug_product_relationship_integrity" in report.failures


def test_draft_entity_disallowed_in_production() -> None:
    catalog = load_taxonomy_catalog()
    broken = catalog.model_copy(deep=True)
    broken.entities[0].review_status = "draft"

    report = validate_taxonomy_catalog(broken)

    assert report.passed is False
    assert "production_entities_verified" in report.failures
