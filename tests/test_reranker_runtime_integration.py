from src.observability.versioning import build_pipeline_version_manifest, get_answer_cache_version
from src.retrieval.reranker import rerank_provider_from_env, rerank_top_n_from_env
from src.retrieval.reranking.providers import canonical_provider_name, semantic_config_from_env


def test_runtime_default_remains_local_rules(monkeypatch):
    monkeypatch.delenv("RERANK_PROVIDER", raising=False)
    monkeypatch.delenv("SEMANTIC_RERANK_MODEL_PATH", raising=False)

    assert rerank_provider_from_env() == "local_rules"
    assert canonical_provider_name(rerank_provider_from_env()) == "local_rules"
    assert semantic_config_from_env().model_path == ""


def test_reranker_config_is_in_pipeline_fingerprint_manifest(monkeypatch):
    monkeypatch.setenv("RERANK_PROVIDER", "local_rules")
    monkeypatch.setenv("RERANK_TOP_N", "8")
    monkeypatch.setenv("SEMANTIC_RERANK_MODEL_PATH", "")

    manifest = build_pipeline_version_manifest()

    assert manifest["reranker_version"] == "reranker_pipeline_v2"
    assert manifest["rerank_provider"] == "local_rules"
    assert manifest["rerank_top_n"] == 8
    assert manifest["semantic_rerank_model_identifier"] == ""
    assert get_answer_cache_version() == "v5"


def test_top_n_env_fallback(monkeypatch):
    monkeypatch.setenv("RERANK_TOP_N", "not-an-int")

    assert rerank_top_n_from_env(default=8) == 8
