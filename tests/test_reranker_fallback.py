from src.retrieval.contracts import RetrievedCandidate
from src.retrieval.query_expansion import expand_normalized_query
from src.retrieval.query_normalization import normalize_query
from src.retrieval.reranker import rerank_candidates
from src.retrieval.reranking.providers import LocalSemanticReranker, SemanticRerankerConfig


class FailingBackend:
    name = "failing_backend"

    def score_pairs(self, query, documents, *, batch_size, timeout_seconds=None):
        del query, documents, batch_size, timeout_seconds
        raise RuntimeError("semantic_inference_error")


def _candidate(candidate_id: str, text: str) -> RetrievedCandidate:
    return RetrievedCandidate(
        candidate_id=candidate_id,
        source="chunk",
        collection="fixture",
        text=text,
        score=0.1,
        fused_score=0.1,
        payload={"chunk_id": candidate_id, "text": text, "active_ingredient": ["benzoyl_peroxide"]},
        rank=1,
    )


def test_semantic_failure_falls_back_to_local_rules():
    normalized = normalize_query("Benzoyl peroxide có phải kháng sinh không?")
    ranked, trace = rerank_candidates(
        normalized,
        [_candidate("bp", "Benzoyl peroxide is not an antibiotic.")],
        expand_normalized_query(normalized),
        provider="hybrid",
        semantic_reranker=LocalSemanticReranker(
            SemanticRerankerConfig(model_path="fixture", allow_fallback=True),
            backend=FailingBackend(),
        ),
    )

    assert ranked
    assert trace.provider == "local_rules"
    assert trace.fallback_used is True
    assert "falling back to local_rules" in " ".join(trace.warnings)


def test_unknown_provider_falls_back_to_local_rules():
    normalized = normalize_query("Adapalene là gì?")
    ranked, trace = rerank_candidates(normalized, [_candidate("adapalene", "Adapalene is a retinoid.")], provider="mystery")

    assert ranked
    assert trace.provider == "local_rules"
    assert trace.warnings
