from __future__ import annotations

import pytest

from src.agent.nodes import cache as cache_node
from src.observability.versioning import (
    build_pipeline_version_manifest,
    compute_pipeline_fingerprint,
    get_answer_cache_version,
)


def test_pipeline_fingerprint_is_deterministic_and_changes():
    manifest = build_pipeline_version_manifest(
        {
            "CACHE_ANSWER_VERSION": "v5",
            "RERANKER_VERSION": "local_reranker_v1",
        }
    )
    fingerprint_a = compute_pipeline_fingerprint(manifest)
    fingerprint_b = compute_pipeline_fingerprint(dict(reversed(list(manifest.items()))))

    changed = dict(manifest)
    changed["reranker_version"] = "local_reranker_v2"

    assert fingerprint_a == fingerprint_b
    assert fingerprint_a != compute_pipeline_fingerprint(changed)
    assert len(fingerprint_a) == 24


def test_answer_verifier_version_is_in_manifest_and_changes_fingerprint():
    old_manifest = build_pipeline_version_manifest(
        {
            "CACHE_ANSWER_VERSION": "v5",
            "ANSWER_VERIFIER_VERSION": "answer_verifier_v1",
        }
    )
    new_manifest = build_pipeline_version_manifest(
        {
            "CACHE_ANSWER_VERSION": "v5",
            "ANSWER_VERIFIER_VERSION": "answer_verifier_v2",
        }
    )

    assert new_manifest["answer_verifier_version"] == "answer_verifier_v2"
    assert compute_pipeline_fingerprint(old_manifest) != compute_pipeline_fingerprint(new_manifest)


def test_pipeline_manifest_does_not_include_secret_keys():
    manifest = build_pipeline_version_manifest(
        {
            "CACHE_ANSWER_VERSION": "v5",
            "QDRANT_API_KEY": "secret",
            "GOOGLE_API_KEY": "secret",
        }
    )
    serialized = str(manifest).lower()

    assert "api_key" not in serialized
    assert "secret" not in serialized


def test_legacy_answer_cache_version_is_promoted_to_phase2e_default():
    assert get_answer_cache_version({"CACHE_ANSWER_VERSION": "v4"}) == "v5"
    assert get_answer_cache_version({"CACHE_ANSWER_VERSION": "v6"}) == "v6"


@pytest.mark.asyncio
async def test_cache_store_metadata_has_pipeline_fingerprint(monkeypatch):
    captured: dict = {}

    async def fake_set_answer_cache(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cache_node, "set_answer_cache", fake_set_answer_cache)
    monkeypatch.setenv("CACHE_MIN_ANSWER_CHARS", "10")
    monkeypatch.setenv("CACHE_REQUIRED_ENTITY_CHECK", "false")
    monkeypatch.setenv("CACHE_ANSWER_VERSION", "v5")

    result = await cache_node.cache_store_node(
        {
            "cache_hit": False,
            "bypass_cache": False,
            "conversation_history": [],
            "cache_reason": "miss",
            "is_in_domain": True,
            "use_history_context": False,
            "errors": [],
            "llm_fallback": False,
            "llm_fallback_used": False,
            "guardrail": "in_domain",
            "fallback_provider": None,
            "user_question": "Mụn đầu đen là gì?",
            "standalone_question": None,
            "final_answer": "Mụn đầu đen là dạng nhân mụn mở liên quan bít tắc nang lông.",
            "sources": ["source.pdf"],
            "actual_provider": "gemini",
            "actual_model": "gemini-2.5-flash",
            "answer_quality_report": {"passed": True, "issues": []},
            "pipeline_manifest": {"phase": "phase2e", "cache_schema_version": "v3"},
            "pipeline_fingerprint": "abc123fingerprint",
        }
    )

    assert result == {}
    assert captured["pipeline_fingerprint"] == "abc123fingerprint"
    assert captured["metadata"]["pipeline_fingerprint"] == "abc123fingerprint"
    assert captured["metadata"]["answer_cache_version"] == "v5"
