from __future__ import annotations

from scripts import inspect_phase2_readiness


def test_display_rerank_provider_recognizes_hybrid_with_model(monkeypatch, tmp_path):
    monkeypatch.setenv("RERANK_PROVIDER", "hybrid")
    monkeypatch.setenv("SEMANTIC_RERANK_MODEL_PATH", str(tmp_path))

    display = inspect_phase2_readiness._display_rerank_provider()

    assert display == "hybrid (semantic model available)"


def test_display_rerank_provider_recognizes_hybrid_without_model(monkeypatch, tmp_path):
    monkeypatch.setenv("RERANK_PROVIDER", "hybrid")
    monkeypatch.setenv("SEMANTIC_RERANK_MODEL_PATH", str(tmp_path / "missing"))

    display = inspect_phase2_readiness._display_rerank_provider()

    assert display == "hybrid (semantic model missing; falls back to local_rules)"
