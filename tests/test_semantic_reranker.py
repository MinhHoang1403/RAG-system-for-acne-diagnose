from pathlib import Path

from src.retrieval.reranking.contracts import RerankCandidate, RerankerUnavailable
from src.retrieval.reranking.providers import (
    LocalSemanticReranker,
    SemanticRerankerConfig,
    clear_semantic_reranker_cache_for_tests,
    get_cached_semantic_reranker_from_env,
)


class FakeBackend:
    name = "fake_semantic"

    def __init__(self):
        self.last_documents = []
        self.last_batch_size = None

    def score_pairs(self, query, documents, *, batch_size, timeout_seconds=None):
        del query, timeout_seconds
        self.last_documents = list(documents)
        self.last_batch_size = batch_size
        return [3.0 if ("not an antibiotic" in document or "Benzoyl" in document) else 1.0 for document in documents]


def _candidate(candidate_id: str, text: str, rank: int) -> RerankCandidate:
    return RerankCandidate(candidate_id, text, "chunk", rank, 0.1, None, None, {})


def test_local_semantic_reranker_uses_fake_backend_without_model_download():
    reranker = LocalSemanticReranker(
        SemanticRerankerConfig(model_path="fixture", max_candidates=8),
        backend=FakeBackend(),
    )

    scores = reranker.rerank(
        "Benzoyl peroxide có phải kháng sinh không?",
        [
            _candidate("oral", "Oral antibiotics need supervision.", 1),
            _candidate("bp", "Benzoyl peroxide is not an antibiotic.", 2),
        ],
        top_n=2,
    )

    assert [score.candidate_id for score in scores] == ["bp", "oral"]
    assert scores[0].semantic_score == 1.0
    assert scores[0].diagnostics["backend"] == "fake_semantic"


def test_missing_local_model_path_is_unavailable(tmp_path: Path):
    missing = tmp_path / "missing-model"
    reranker = LocalSemanticReranker(SemanticRerankerConfig(model_path=str(missing)))

    try:
        reranker.rerank("query", [_candidate("a", "text", 1)], top_n=1)
    except RerankerUnavailable as exc:
        assert "not provisioned" in str(exc) or "does not exist" in str(exc)
    else:
        raise AssertionError("missing model should not be treated as available")


def test_candidate_cap_truncation_and_duplicate_ids_are_deterministic():
    backend = FakeBackend()
    reranker = LocalSemanticReranker(
        SemanticRerankerConfig(
            model_path="fixture",
            batch_size=2,
            max_candidates=2,
            max_query_chars=10,
            max_document_chars=12,
        ),
        backend=backend,
    )

    scores = reranker.rerank(
        "Benzoyl peroxide có phải kháng sinh không?",
        [
            _candidate("dup", "Benzoyl peroxide is not an antibiotic.", 2),
            _candidate("dup", "This duplicate should not be scored.", 3),
            _candidate("other", "Oral antibiotics.", 1),
            _candidate("late", "Late relevant not an antibiotic.", 4),
        ],
        top_n=8,
    )

    assert len(scores) == 2
    assert [score.candidate_id for score in scores] == ["dup", "other"]
    assert backend.last_batch_size == 2
    assert all(len(document) <= 12 for document in backend.last_documents)


def test_cross_encoder_backend_source_enforces_local_files_only():
    source = Path("src/retrieval/reranking/providers.py").read_text(encoding="utf-8")

    assert "local_files_only=True" in source
    assert "TRANSFORMERS_OFFLINE" in source


def test_cached_semantic_reranker_reuses_instance_for_same_model_and_device(monkeypatch, tmp_path):
    clear_semantic_reranker_cache_for_tests()
    model_path = tmp_path / "local-reranker"
    model_path.mkdir()
    monkeypatch.setenv("SEMANTIC_RERANK_MODEL_PATH", str(model_path))
    monkeypatch.setenv("SEMANTIC_RERANK_DEVICE", "cuda")
    monkeypatch.setenv("SEMANTIC_RERANK_BATCH_SIZE", "4")

    first = get_cached_semantic_reranker_from_env()
    second = get_cached_semantic_reranker_from_env()

    assert first is second

    monkeypatch.setenv("SEMANTIC_RERANK_DEVICE", "cpu")
    third = get_cached_semantic_reranker_from_env()

    assert third is not first
    clear_semantic_reranker_cache_for_tests()
