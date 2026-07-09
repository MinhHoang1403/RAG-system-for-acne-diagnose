from src.retrieval.reranking.contracts import RerankCandidate
from src.retrieval.reranking.providers import HybridFusionConfig, hybrid_fuse_scores


def _candidate(candidate_id: str, rank: int, retrieval_score: float) -> RerankCandidate:
    return RerankCandidate(candidate_id, "text", "chunk", rank, retrieval_score, None, None, {})


def test_hybrid_fusion_normalizes_sources_and_uses_weights():
    candidates = [_candidate("a", 1, 0.9), _candidate("b", 2, 0.1)]
    scores = hybrid_fuse_scores(
        candidates,
        {"a": 0.0, "b": 1.0},
        {"a": 10.0, "b": 1.0},
        config=HybridFusionConfig(semantic_weight=0.7, rule_weight=0.2, retrieval_weight=0.1),
    )

    assert scores[0].candidate_id == "b"
    assert scores[0].semantic_score == 1.0
    assert scores[0].provider == "hybrid"
    assert 0.0 <= scores[0].final_score <= 1.0


def test_hybrid_weight_validation_falls_back_to_defaults():
    config = HybridFusionConfig(0, 0, 0).normalized()

    assert config.semantic_weight == 0.70
    assert config.rule_weight == 0.20
    assert config.retrieval_weight == 0.10
