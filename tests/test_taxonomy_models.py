from __future__ import annotations

from src.knowledge.taxonomy_models import (
    DEFAULT_TAXONOMY_V2_PATH,
    TaxonomyCatalog,
    load_taxonomy_catalog,
)


def test_taxonomy_v2_loads_with_schema_metadata() -> None:
    catalog = load_taxonomy_catalog(DEFAULT_TAXONOMY_V2_PATH)

    assert catalog.taxonomy_version == "drug_taxonomy_v2"
    assert catalog.entity_schema_version == "entity_schema_v2"
    assert catalog.taxonomy_schema_version == "taxonomy_schema_v2"
    assert catalog.entity_counts()["drug_product"] == 3


def test_taxonomy_json_schema_exports() -> None:
    schema = TaxonomyCatalog.model_json_schema()

    assert schema["title"] == "TaxonomyCatalog"
    assert "entities" in schema["properties"]
