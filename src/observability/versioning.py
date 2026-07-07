"""Deterministic Phase 2 pipeline version manifest and fingerprint."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Mapping


DEFAULT_ANSWER_CACHE_VERSION = "v5"
LEGACY_ANSWER_CACHE_VERSIONS = {"v1", "v2", "v3", "v4"}

_SECRET_KEY_MARKERS = (
    "api_key",
    "token",
    "password",
    "secret",
    "authorization",
    "bearer",
    "cookie",
)


def build_pipeline_version_manifest(settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a stable, secret-free Phase 2 pipeline version manifest."""

    settings = settings or {}

    def value(name: str, default: Any = "") -> Any:
        if name in settings:
            return settings[name]
        return os.getenv(name, default)

    answer_cache_version = _effective_answer_cache_version(value("CACHE_ANSWER_VERSION", None))

    manifest = {
        "phase": "phase2e",
        "retrieval_pipeline_version": value("RETRIEVAL_PIPELINE_VERSION", "retrieval_pipeline_v2"),
        "context_packer_version": value("CONTEXT_PACKER_VERSION", "context_packer_v2"),
        "reranker_version": value("RERANKER_VERSION", "local_reranker_v1"),
        "answer_verifier_version": value("ANSWER_VERIFIER_VERSION", "answer_verifier_v1"),
        "cache_schema_version": value("CACHE_SCHEMA_VERSION", "v3"),
        "answer_cache_version": answer_cache_version,
        "embedding_model": value("EMBEDDING_MODEL", "models/gemini-embedding-2"),
        "embedding_dimensions": _env_int(value("EMBEDDING_DIMENSIONS", "3072"), default=3072),
        "qdrant_collection_name": _runtime_chunk_collection_name(settings),
        "entity_collection_name": _runtime_entity_collection_name(settings),
        "kb_version": value("KB_VERSION", "acne_kb_v1"),
        "prompt_version": value("PROMPT_VERSION", "medical_prompt_v2"),
        "rerank_enabled": _env_bool(value("RERANK_ENABLED", "true"), default=True),
        "rerank_provider": value("RERANK_PROVIDER", "local_rules") or "local_rules",
        "rerank_top_n": _env_int(value("RERANK_TOP_N", "8"), default=8),
        "answer_verifier_enabled": _env_bool(value("ANSWER_VERIFIER_ENABLED", "true"), default=True),
        "answer_guard_mode": value("ANSWER_GUARD_MODE", "metadata_only") or "metadata_only",
    }
    return _strip_secret_keys(manifest)


def compute_pipeline_fingerprint(manifest: dict[str, Any]) -> str:
    """Compute a deterministic short SHA256 fingerprint for a manifest."""

    safe_manifest = _strip_secret_keys(manifest)
    payload = json.dumps(safe_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def current_pipeline_fingerprint() -> str:
    """Return the fingerprint for the current environment manifest."""

    return compute_pipeline_fingerprint(build_pipeline_version_manifest())


def get_answer_cache_version(settings: Mapping[str, Any] | None = None) -> str:
    """Return the effective Phase 2E cache answer version.

    Legacy values v1-v4 are promoted to v5 so stale `.env` files do not reuse
    pre-Phase-2E answer-cache namespaces. Newer explicit values are respected.
    """

    settings = settings or {}
    configured = settings.get("CACHE_ANSWER_VERSION")
    if configured is None:
        configured = os.getenv("CACHE_ANSWER_VERSION")
    return _effective_answer_cache_version(configured)


def pipeline_manifest_summary(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a compact manifest summary suitable for cache/debug metadata."""

    manifest = manifest or build_pipeline_version_manifest()
    summary_keys = [
        "phase",
        "retrieval_pipeline_version",
        "context_packer_version",
        "reranker_version",
        "answer_verifier_version",
        "cache_schema_version",
        "answer_cache_version",
        "embedding_model",
        "qdrant_collection_name",
        "entity_collection_name",
        "rerank_enabled",
        "rerank_provider",
        "rerank_top_n",
        "answer_verifier_enabled",
        "answer_guard_mode",
    ]
    return {key: manifest.get(key) for key in summary_keys if key in manifest}


def _env_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _effective_answer_cache_version(configured: Any) -> str:
    text = str(configured or "").strip()
    if not text:
        return DEFAULT_ANSWER_CACHE_VERSION
    if text.lower() in LEGACY_ANSWER_CACHE_VERSIONS:
        return DEFAULT_ANSWER_CACHE_VERSION
    return text


def _env_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _strip_secret_keys(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in data.items()
        if not any(marker in key.lower() for marker in _SECRET_KEY_MARKERS)
    }


def _runtime_chunk_collection_name(settings: Mapping[str, Any]) -> str:
    if "CHUNK_QDRANT_COLLECTION_NAME" in settings or "QDRANT_COLLECTION_NAME" in settings:
        configured = str(settings.get("CHUNK_QDRANT_COLLECTION_NAME") or "").strip()
        base = str(settings.get("QDRANT_COLLECTION_NAME") or os.getenv("QDRANT_COLLECTION_NAME", "acne_knowledge")).strip()
        if not configured or configured == "acne_chunks_v1":
            return base or "acne_knowledge"
        return configured
    try:
        from src.knowledge.entity_index import get_chunk_collection_name

        return get_chunk_collection_name()
    except Exception:
        configured = os.getenv("CHUNK_QDRANT_COLLECTION_NAME", "").strip()
        base = os.getenv("QDRANT_COLLECTION_NAME", "acne_knowledge").strip() or "acne_knowledge"
        if not configured or configured == "acne_chunks_v1":
            return base
        return configured


def _runtime_entity_collection_name(settings: Mapping[str, Any]) -> str:
    if "ENTITY_QDRANT_COLLECTION_NAME" in settings:
        return str(settings["ENTITY_QDRANT_COLLECTION_NAME"] or "acne_entities_v1")
    try:
        from src.knowledge.entity_index import get_entity_collection_name

        return get_entity_collection_name()
    except Exception:
        return os.getenv("ENTITY_QDRANT_COLLECTION_NAME", "acne_entities_v1")


__all__ = [
    "DEFAULT_ANSWER_CACHE_VERSION",
    "build_pipeline_version_manifest",
    "compute_pipeline_fingerprint",
    "current_pipeline_fingerprint",
    "get_answer_cache_version",
    "pipeline_manifest_summary",
]
