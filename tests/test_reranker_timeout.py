from src.retrieval.contracts import RetrievedCandidate
from src.retrieval.query_normalization import normalize_query
from src.retrieval.reranker import rerank_candidates
from src.retrieval.reranking.providers import LocalSemanticReranker, SemanticRerankerConfig


class TimeoutBackend:
    name = "timeout_backend"

    def score_pairs(self, query, documents, *, batch_size, timeout_seconds=None):
        del query, documents, batch_size, timeout_seconds
        raise TimeoutError("semantic_inference_timeout")


def test_semantic_timeout_falls_back_without_hanging():
    normalized = normalize_query("Retinoid có dùng khi mang thai không?")
    candidate = RetrievedCandidate(
        candidate_id="retinoid_pregnancy",
        source="chunk",
        collection="fixture",
        text="Topical retinoids require caution during pregnancy.",
        score=0.2,
        fused_score=0.2,
        payload={"chunk_id": "retinoid_pregnancy", "drug_class": ["topical_retinoid"]},
        rank=1,
    )

    ranked, trace = rerank_candidates(
        normalized,
        [candidate],
        provider="local_semantic",
        semantic_reranker=LocalSemanticReranker(
            SemanticRerankerConfig(model_path="fixture", allow_fallback=True),
            backend=TimeoutBackend(),
        ),
        timeout_seconds=0.001,
    )

    assert ranked[0].candidate_id == "retinoid_pregnancy"
    assert trace.provider == "local_rules"
    assert trace.fallback_used is True
