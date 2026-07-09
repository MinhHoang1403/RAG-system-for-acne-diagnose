import math

from src.retrieval.reranking.normalization import (
    clamp_unit,
    min_max_normalize,
    normalize_score_map,
    sanitize_score,
)


def test_min_max_normalize_handles_empty_single_and_equal_scores():
    assert min_max_normalize([]) == []
    assert min_max_normalize([42]) == [1.0]
    assert min_max_normalize([3, 3, 3]) == [1.0, 1.0, 1.0]


def test_min_max_normalize_handles_nan_and_infinity():
    scores = min_max_normalize([math.nan, math.inf, -math.inf, 2])

    assert scores == [0.0, 0.0, 0.0, 1.0]
    assert all(math.isfinite(score) for score in scores)


def test_normalize_score_map_is_deterministic():
    normalized = normalize_score_map({"a": 10, "b": 20, "c": 10})

    assert normalized == {"a": 0.0, "b": 1.0, "c": 0.0}


def test_sanitize_and_clamp_unit():
    assert sanitize_score("bad") == 0.0
    assert clamp_unit(10) == 1.0
    assert clamp_unit(-1) == 0.0
