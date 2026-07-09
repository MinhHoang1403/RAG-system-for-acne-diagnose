from src.retrieval.contracts import RetrievedCandidate
from src.retrieval.query_expansion import expand_normalized_query
from src.retrieval.query_normalization import normalize_query
from src.retrieval.reranker import rerank_candidates
from src.retrieval.reranking.contracts import RerankCandidate, RerankScore, sort_scores


def _candidate(candidate_id: str, text: str, score: float = 0.1) -> RetrievedCandidate:
    return RetrievedCandidate(
        candidate_id=candidate_id,
        source="chunk",
        collection="fixture",
        text=text,
        score=score,
        fused_score=score,
        payload={"chunk_id": candidate_id, "text": text, "source_file": "fixture.json"},
        rank=1,
    )


def test_contracts_have_stable_tie_breaking():
    scores = [
        RerankScore("b", 0.5, 2, "fixture"),
        RerankScore("a", 0.5, 1, "fixture"),
        RerankScore("c", 0.6, 3, "fixture"),
    ]

    assert [score.candidate_id for score in sort_scores(scores)] == ["c", "a", "b"]


def test_rerank_candidate_contract_preserves_metadata():
    candidate = RerankCandidate(
        candidate_id="chunk-1",
        text="Benzoyl peroxide is not an antibiotic.",
        source_type="chunk",
        original_rank=1,
        retrieval_score=0.42,
        dense_score=0.8,
        sparse_score=0.3,
        metadata={"chunk_id": "chunk-1", "source_file": "fixture.json"},
    )

    assert candidate.metadata["chunk_id"] == "chunk-1"
    assert candidate.dense_score == 0.8


def test_rerank_does_not_mutate_input_candidate():
    normalized = normalize_query("Benzoyl peroxide có phải kháng sinh không?")
    candidate = _candidate("bp", "Benzoyl peroxide is not an antibiotic.", 0.2)
    before = candidate.model_dump()

    ranked, trace = rerank_candidates(normalized, [candidate], expand_normalized_query(normalized))

    assert candidate.model_dump() == before
    assert ranked[0].candidate_id == "bp"
    assert trace.provider == "local_rules"
