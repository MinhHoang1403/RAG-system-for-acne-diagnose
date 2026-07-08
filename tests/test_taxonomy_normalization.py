from __future__ import annotations

from src.knowledge.taxonomy_models import (
    accentless_taxonomy_alias,
    normalize_taxonomy_alias,
    normalize_taxonomy_name,
)


def test_taxonomy_normalization_handles_spacing_hyphen_and_parentheses() -> None:
    assert normalize_taxonomy_name(" Benzoyl-Peroxide (BP) ") == "benzoyl peroxide bp"
    assert normalize_taxonomy_alias("benzoyl_peroxide") == "benzoyl peroxide"


def test_taxonomy_accentless_alias_view() -> None:
    assert accentless_taxonomy_alias("kháng sinh bôi tại chỗ") == "khang sinh boi tai cho"
