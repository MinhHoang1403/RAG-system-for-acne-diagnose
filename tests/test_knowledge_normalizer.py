from __future__ import annotations

from src.knowledge import DrugEntityNormalizer


def _entity_names(result: dict) -> set[str]:
    return {entity["canonical_name"] for entity in result["normalized_entities"]}


def _entity_types(result: dict) -> set[tuple[str, str]]:
    return {
        (entity["entity_type"], entity["canonical_name"])
        for entity in result["normalized_entities"]
    }


def test_dalacin_t_maps_to_clindamycin() -> None:
    normalizer = DrugEntityNormalizer()

    result = normalizer.expand_query("Dalacin T là gì?")

    assert ("drug_product", "Dalacin T") in _entity_types(result)
    assert "clindamycin" in result["active_ingredients"]
    assert "topical_antibiotic" in result["drug_class"]


def test_epiduo_maps_to_adapalene_and_bpo() -> None:
    normalizer = DrugEntityNormalizer()

    result = normalizer.expand_query("Epiduo có BPO không?")

    assert ("drug_product", "Epiduo") in _entity_types(result)
    assert "adapalene" in result["active_ingredients"]
    assert "benzoyl_peroxide" in result["active_ingredients"]


def test_differin_maps_to_topical_retinoid() -> None:
    normalizer = DrugEntityNormalizer()

    result = normalizer.expand_query("Differin thuộc nhóm gì?")

    assert ("drug_product", "Differin") in _entity_types(result)
    assert "adapalene" in result["active_ingredients"]
    assert "topical_retinoid" in result["drug_class"]


def test_benzoyl_peroxide_not_antibiotic() -> None:
    normalizer = DrugEntityNormalizer()

    result = normalizer.expand_query("Benzoyl peroxide có phải kháng sinh không?")

    assert "benzoyl_peroxide" in result["active_ingredients"]
    assert "topical_antibiotic" not in result["drug_class"]
    assert "oral_antibiotic" not in result["drug_class"]


def test_bp_token_boundary() -> None:
    normalizer = DrugEntityNormalizer()

    bp_result = normalizer.expand_query("BP trị mụn thế nào?")
    false_positive_result = normalizer.expand_query("abpsomething")

    assert "benzoyl_peroxide" in bp_result["active_ingredients"]
    assert "benzoyl_peroxide" not in false_positive_result["active_ingredients"]
    assert "benzoyl_peroxide" not in _entity_names(false_positive_result)


def test_normalize_mention_exact_product_aliases() -> None:
    normalizer = DrugEntityNormalizer()

    assert [card.canonical_name for card in normalizer.normalize_mention("Dalacin-T")] == [
        "Dalacin T"
    ]
    assert [card.canonical_name for card in normalizer.normalize_mention("Epiduo gel")] == [
        "Epiduo"
    ]
