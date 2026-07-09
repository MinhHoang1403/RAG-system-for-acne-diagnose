from src.retrieval.reranking.metrics import (
    ndcg_at_k,
    precision_at_k,
    ranking_metrics,
    recall_at_k,
    reciprocal_rank_at_k,
    top1_accuracy,
)


def test_ranking_metrics_handle_relevance_labels():
    ranked = ["a", "b", "c"]
    relevance = {"a": 0, "b": 3, "c": 1}

    assert reciprocal_rank_at_k(ranked, relevance, 3) == 0.5
    assert recall_at_k(ranked, relevance, 2) == 0.5
    assert precision_at_k(ranked, relevance, 2) == 0.5
    assert 0.0 < ndcg_at_k(ranked, relevance, 3) <= 1.0
    assert top1_accuracy(ranked, relevance) == 0.0


def test_ranking_metrics_handle_zero_relevant_case():
    metrics = ranking_metrics(["a"], {"a": 0}, k=5)

    assert metrics["recall_at_k"] == 1.0
    assert metrics["ndcg_at_k"] == 1.0
    assert metrics["top1_accuracy"] == 0.0
