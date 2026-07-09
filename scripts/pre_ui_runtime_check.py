#!/usr/bin/env python3
"""Pre-UI runtime readiness check without live chat or paid API calls."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass

from src.observability.trace_exporter import sanitize_for_observability  # noqa: E402
from src.observability.versioning import (  # noqa: E402
    build_pipeline_version_manifest,
    compute_pipeline_fingerprint,
    get_answer_cache_version,
)

SECRET_MARKERS = (
    "api_key",
    "token",
    "secret",
    "password",
    "authorization",
    "bearer",
    "cookie",
    "key",
)
URL_CONFIG_KEYS = {"DATABASE_URL", "REDIS_URL"}
RERANK_PROVIDERS_WITHOUT_MODEL = {"local_rules"}
RERANK_PROVIDERS_WITH_MODEL = {"hybrid", "local_semantic", "local_cross_encoder", "semantic", "local_model"}


def check(name: str, passed: bool, details: dict[str, Any] | None = None, severity: str = "error") -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "severity": severity,
        "details": sanitize_for_observability(details or {}),
    }


async def run_pre_ui_runtime_check() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []

    manifest = build_pipeline_version_manifest()
    fingerprint = compute_pipeline_fingerprint(manifest)
    env_summary = _env_summary()
    reranker_status = _reranker_runtime_status(manifest)

    checks.append(check("pipeline_fingerprint", bool(fingerprint), {"fingerprint": fingerprint}))
    checks.append(check("cache_version", get_answer_cache_version() == "v5", {"answer_cache_version": get_answer_cache_version()}))
    checks.append(
        check(
            "neo4j_schema_version",
            manifest.get("neo4j_schema_version") == "neo4j_schema_v1",
            {"neo4j_schema_version": manifest.get("neo4j_schema_version")},
        )
    )
    checks.append(
        check(
            "taxonomy_version",
            bool(manifest.get("taxonomy_version")),
            {"taxonomy_version": manifest.get("taxonomy_version")},
        )
    )
    checks.append(
        check(
            "env_runtime_core",
            env_summary.get("QDRANT_COLLECTION_NAME") == "acne_knowledge"
            and env_summary.get("CHUNK_QDRANT_COLLECTION_NAME") == "acne_knowledge"
            and env_summary.get("ENTITY_QDRANT_COLLECTION_NAME") == "acne_entities_v1"
            and env_summary.get("NEO4J_URI") == "bolt://127.0.0.1:7687"
            and _is_supported_rerank_provider(os.getenv("RERANK_PROVIDER", "local_rules"))
            and env_summary.get("AGENT_TOTAL_TIMEOUT_SECONDS") == "120"
            and env_summary.get("CIRCUIT_BREAKER_ENABLED") == "true"
            and env_summary.get("OBSERVABILITY_ENABLED") == "false"
            and env_summary.get("PHASE2_DEBUG_METADATA") == "false",
            env_summary,
        )
    )
    checks.append(
        check(
            "reranker_hardening",
            manifest.get("reranker_version") == "reranker_pipeline_v2"
            and reranker_status["passed"],
            {
                "reranker_version": manifest.get("reranker_version"),
                "runtime_rerank_provider": manifest.get("rerank_provider"),
                "semantic_model_identifier": manifest.get("semantic_rerank_model_identifier"),
                "fallback_allowed": manifest.get("semantic_rerank_allow_fallback"),
                **reranker_status["details"],
            },
        )
    )

    try:
        from src.api.app import app

        schema = app.openapi()
        paths = schema.get("paths", {})
        checks.append(
            check(
                "api_import_and_openapi",
                "/health" in paths and "/chat" in paths,
                {"path_count": len(paths), "has_health": "/health" in paths, "has_chat": "/chat" in paths},
            )
        )
    except Exception as exc:
        checks.append(check("api_import_and_openapi", False, {"error": str(exc)}))
        errors.append(f"API import/OpenAPI failed: {exc}")
        return _finalize(checks, warnings, errors)

    try:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
        health = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        health_status = health.get("status")
        checks.append(
            check(
                "api_health",
                response.status_code == 200 and health_status == "ok",
                {
                    "status_code": response.status_code,
                    "status": health_status,
                    "postgres": health.get("postgres"),
                    "qdrant": health.get("qdrant"),
                    "neo4j": health.get("neo4j"),
                    "redis": health.get("redis"),
                    "ollama": health.get("ollama"),
                },
            )
        )
        if health_status != "ok":
            warnings.append("API /health is not ok; UI can open but chat readiness may be degraded.")
    except Exception as exc:
        checks.append(check("api_health", False, {"error": str(exc)}))
        errors.append(f"API health failed: {exc}")

    frontend_check = _check_frontend_config()
    checks.append(frontend_check)
    if not frontend_check["passed"]:
        warnings.append("Frontend API config check failed.")

    report = _finalize(checks, warnings, errors)
    report["runtime"] = {
        "pipeline_fingerprint": fingerprint,
        "answer_cache_version": get_answer_cache_version(),
        "pipeline_manifest": sanitize_for_observability(manifest),
    }
    return report


def _env_summary() -> dict[str, str]:
    names = [
        "QDRANT_COLLECTION_NAME",
        "CHUNK_QDRANT_COLLECTION_NAME",
        "ENTITY_QDRANT_COLLECTION_NAME",
        "QDRANT_URL",
        "NEO4J_URI",
        "REDIS_URL",
        "DATABASE_URL",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSIONS",
        "GOOGLE_MODEL",
        "OLLAMA_MODEL",
        "RERANK_ENABLED",
        "RERANK_PROVIDER",
        "RERANK_TOP_N",
        "SEMANTIC_RERANK_MODEL_PATH",
        "SEMANTIC_RERANK_DEVICE",
        "SEMANTIC_RERANK_BATCH_SIZE",
        "SEMANTIC_RERANK_MAX_CANDIDATES",
        "SEMANTIC_RERANK_ALLOW_FALLBACK",
        "SEMANTIC_RERANK_WEIGHT",
        "RULE_RERANK_WEIGHT",
        "RETRIEVAL_RERANK_WEIGHT",
        "ANSWER_VERIFIER_ENABLED",
        "ANSWER_GUARD_MODE",
        "ANSWER_VERIFIER_STRICT",
        "TAXONOMY_VERSION",
        "RUNTIME_RESILIENCE_VERSION",
        "AGENT_TOTAL_TIMEOUT_SECONDS",
        "RETRIEVAL_TIMEOUT_SECONDS",
        "NEO4J_TIMEOUT_SECONDS",
        "RERANK_TIMEOUT_SECONDS",
        "GEMINI_TIMEOUT_SECONDS",
        "OLLAMA_TIMEOUT_SECONDS",
        "LLM_MAX_RETRIES",
        "LLM_RETRY_BASE_DELAY_SECONDS",
        "LLM_RETRY_MAX_DELAY_SECONDS",
        "CIRCUIT_BREAKER_ENABLED",
        "CIRCUIT_BREAKER_FAILURE_THRESHOLD",
        "CIRCUIT_BREAKER_RECOVERY_SECONDS",
        "CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS",
        "CACHE_ANSWER_VERSION",
        "OBSERVABILITY_ENABLED",
        "OBSERVABILITY_TRACE_DIR",
        "OBSERVABILITY_MAX_TEXT_CHARS",
        "PHASE2_DEBUG_METADATA",
    ]
    summary: dict[str, str] = {}
    for name in names:
        value = os.getenv(name, "")
        if name in URL_CONFIG_KEYS:
            summary[name] = "<CONFIGURED>" if value else "<MISSING>"
        elif name == "SEMANTIC_RERANK_MODEL_PATH":
            summary[name] = _summarize_model_path(value)
        elif any(marker in name.lower() for marker in SECRET_MARKERS):
            summary[name] = "<REDACTED>" if value else "<EMPTY>"
        else:
            summary[name] = value or "<MISSING>"
    return summary


def _is_supported_rerank_provider(provider: str) -> bool:
    normalized = (provider or "local_rules").strip().lower()
    return normalized in RERANK_PROVIDERS_WITHOUT_MODEL | RERANK_PROVIDERS_WITH_MODEL


def _reranker_runtime_status(manifest: dict[str, Any]) -> dict[str, Any]:
    provider = str(manifest.get("rerank_provider") or "local_rules").strip().lower()
    model_path = os.getenv("SEMANTIC_RERANK_MODEL_PATH", "").strip()
    model_exists = bool(model_path and Path(model_path).exists())
    model_identifier = str(manifest.get("semantic_rerank_model_identifier") or "").strip()
    fallback_allowed = bool(manifest.get("semantic_rerank_allow_fallback", True))
    details = {
        "provider_supported": _is_supported_rerank_provider(provider),
        "semantic_model_configured": bool(model_path),
        "semantic_model_path_exists": model_exists,
    }

    if provider in RERANK_PROVIDERS_WITHOUT_MODEL:
        return {"passed": True, "details": details}
    if provider in RERANK_PROVIDERS_WITH_MODEL:
        return {
            "passed": bool(model_identifier and model_exists and fallback_allowed),
            "details": details,
        }
    return {"passed": False, "details": details}


def _summarize_model_path(value: str) -> str:
    if not value:
        return "<MISSING>"
    path = Path(value)
    identifier = path.name or "<CONFIGURED>"
    return f"<CONFIGURED:{identifier};exists={str(path.exists()).lower()}>"


def _check_frontend_config() -> dict[str, Any]:
    api_client = PROJECT_ROOT / "src" / "frontend" / "src" / "api" / "chatApi.js"
    package_json = PROJECT_ROOT / "src" / "frontend" / "package.json"
    if not api_client.exists():
        return check("frontend_api_config", False, {"error": "src/frontend API client not found"}, severity="warning")
    source = api_client.read_text(encoding="utf-8")
    details = {
        "api_client": str(api_client.relative_to(PROJECT_ROOT)),
        "package_json_exists": package_json.exists(),
        "uses_vite_api_url": "import.meta.env.VITE_API_URL" in source,
        "fallback_local_api": "http://127.0.0.1:8000" in source or "http://localhost:8000" in source,
        "chat_endpoint": "/chat" in source,
        "health_endpoint": "/health" in source,
    }
    return check(
        "frontend_api_config",
        all(
            [
                details["package_json_exists"],
                details["uses_vite_api_url"],
                details["fallback_local_api"],
                details["chat_endpoint"],
                details["health_endpoint"],
            ]
        ),
        details,
        severity="warning",
    )


def _finalize(checks: list[dict[str, Any]], warnings: list[str], errors: list[str]) -> dict[str, Any]:
    failed_errors = [item for item in checks if not item["passed"] and item["severity"] == "error"]
    return {
        "passed": not failed_errors and not errors,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }


def main() -> int:
    report = asyncio.run(run_pre_ui_runtime_check())
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
