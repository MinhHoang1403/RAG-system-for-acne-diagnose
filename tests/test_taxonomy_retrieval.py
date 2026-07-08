from __future__ import annotations

from src.knowledge.normalizer import DrugEntityNormalizer
from src.knowledge.taxonomy_models import DEFAULT_TAXONOMY_V2_PATH
from src.retrieval.query_normalization import normalize_query


def test_existing_product_aliases_still_normalize_with_v2() -> None:
    normalizer = DrugEntityNormalizer(DEFAULT_TAXONOMY_V2_PATH)
    normalized = normalize_query("Dalacin trị mụn thế nào?", normalizer=normalizer)

    assert "Dalacin T" in normalized.drug_product
    assert "clindamycin" in normalized.active_ingredient


def test_accentless_alias_matching_with_v2() -> None:
    normalizer = DrugEntityNormalizer(DEFAULT_TAXONOMY_V2_PATH)
    normalized = normalize_query("khang sinh boi co nen dung don doc khong?", normalizer=normalizer)

    assert "topical_antibiotic" in normalized.drug_class


def test_unknown_brand_not_mapped_blindly_with_v2() -> None:
    normalizer = DrugEntityNormalizer(DEFAULT_TAXONOMY_V2_PATH)
    normalized = normalize_query("MysteryBrand có thành phần gì?", normalizer=normalizer)

    assert normalized.drug_product == []
    assert normalized.active_ingredient == []
