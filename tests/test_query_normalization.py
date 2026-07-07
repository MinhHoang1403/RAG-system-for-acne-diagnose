from src.retrieval.query_normalization import normalize_query


def test_drug_queries_normalize_taxonomy_entities():
    dalacin = normalize_query("Dalacin T là gì?")
    assert dalacin.intent == "drug_identity"
    assert "Dalacin T" in dalacin.drug_product
    assert "clindamycin" in dalacin.active_ingredient
    assert "topical_antibiotic" in dalacin.drug_class

    epiduo = normalize_query("Epiduo có BPO không?")
    assert epiduo.intent == "ingredient_question"
    assert "Epiduo" in epiduo.drug_product
    assert {"adapalene", "benzoyl_peroxide"}.issubset(epiduo.active_ingredient)

    differin = normalize_query("Differin thuộc nhóm gì?")
    assert differin.intent == "class_check"
    assert "adapalene" in differin.active_ingredient
    assert "topical_retinoid" in differin.drug_class


def test_class_contrast_queries_do_not_assign_negative_class():
    bp = normalize_query("Benzoyl peroxide có phải kháng sinh không?")
    assert bp.intent == "class_check"
    assert "benzoyl_peroxide" in bp.active_ingredient
    assert "benzoyl_peroxide" in bp.drug_class
    assert "topical_antibiotic" not in bp.drug_class

    adapalene = normalize_query("Adapalene có phải kháng sinh không?")
    assert adapalene.intent == "class_check"
    assert "adapalene" in adapalene.active_ingredient
    assert "topical_retinoid" in adapalene.drug_class
    assert "topical_antibiotic" not in adapalene.drug_class


def test_acne_type_query_is_not_classified_as_drug_query():
    blackheads = normalize_query("Mụn đầu đen là gì?")
    assert blackheads.intent == "acne_type"
    assert "acne_vulgaris" in blackheads.condition
    assert "blackheads" in blackheads.metadata["concern"]
    assert blackheads.drug_product == []

    inflammatory = normalize_query("Mụn viêm nên xử lý thế nào?")
    assert inflammatory.intent == "acne_type"
    assert "inflammatory_acne" in inflammatory.metadata["concern"]
    assert inflammatory.drug_product == []
