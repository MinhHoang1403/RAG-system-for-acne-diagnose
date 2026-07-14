"""Read-only end-to-end answer pipeline trace for Audit 13.

The script runs the LangGraph pipeline and writes a compact JSON trace that is
safe to keep in artifacts: source IDs, scores, metadata, short excerpts and
final answers are included; secrets and full documents are not.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except Exception:
    pass

from src.agent.graph import clinical_graph  # noqa: E402
from src.agent.source_presentation import build_source_metadata  # noqa: E402
from src.database.retriever import HybridRetriever  # noqa: E402
from src.observability.versioning import (  # noqa: E402
    build_pipeline_version_manifest,
    compute_pipeline_fingerprint,
)
from src.resilience.budget import DeadlineBudget  # noqa: E402
from src.resilience.contracts import runtime_resilience_settings_from_env  # noqa: E402


MAX_EXCERPT_CHARS = 360


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _excerpt(text: Any, limit: int = MAX_EXCERPT_CHARS) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 15)].rstrip() + " ...[truncated]"


def _compact_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    keep = [
        "point_id",
        "chunk_id",
        "entity_id",
        "document_id",
        "source_file",
        "source_path",
        "source_type",
        "canonical_name",
        "entity_type",
        "drug_product",
        "active_ingredient",
        "drug_class",
        "condition",
        "safety_context",
        "content_type",
        "concern",
        "header",
        "parent_header_path",
        "chunk_index",
        "ingestion_run_id",
        "kb_version",
    ]
    compact = {key: payload.get(key) for key in keep if payload.get(key) not in (None, "", [])}
    if payload.get("text"):
        compact["text_excerpt"] = _excerpt(payload.get("text"))
        compact["text_hash"] = _sha(str(payload.get("text")))
    return compact


def _compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = candidate.get("payload") if isinstance(candidate.get("payload"), dict) else {}
    text = candidate.get("text") or payload.get("text") or ""
    debug = candidate.get("debug") if isinstance(candidate.get("debug"), dict) else {}
    return {
        "candidate_id": candidate.get("candidate_id"),
        "source": candidate.get("source"),
        "collection": candidate.get("collection"),
        "rank": candidate.get("rank"),
        "score": candidate.get("score"),
        "fused_score": candidate.get("fused_score"),
        "matched_metadata": candidate.get("matched_metadata") or {},
        "debug": {
            key: debug.get(key)
            for key in [
                "dense_score",
                "sparse_score",
                "rrf_score",
                "metadata_boost",
                "base_score",
                "merge_bonus",
                "rerank_score",
                "rerank_reasons",
                "rerank_rank",
            ]
            if debug.get(key) is not None
        },
        "payload": _compact_payload(payload),
        "text_excerpt": _excerpt(text),
        "text_hash": _sha(str(text)),
    }


def _compact_rerank_trace(trace: dict[str, Any] | None) -> dict[str, Any] | None:
    if not trace:
        return None
    ranked = []
    for item in trace.get("ranked_candidates", []) or []:
        candidate = item.get("candidate", {}) if isinstance(item, dict) else {}
        ranked.append(
            {
                "rerank_rank": item.get("rerank_rank"),
                "rerank_score": item.get("rerank_score"),
                "score_breakdown": item.get("score_breakdown") or {},
                "candidate": _compact_candidate(candidate),
            }
        )
    return {
        "provider": trace.get("provider"),
        "requested_provider": trace.get("requested_provider"),
        "enabled": trace.get("enabled"),
        "fallback_used": trace.get("fallback_used"),
        "semantic_model_available": trace.get("semantic_model_available"),
        "input_count": trace.get("input_count"),
        "output_count": trace.get("output_count"),
        "top_n": trace.get("top_n"),
        "ranked_candidates": ranked,
        "warnings": trace.get("warnings") or [],
        "timings_ms": trace.get("timings_ms") or {},
    }


def _compact_packed_context(packed: dict[str, Any] | None) -> dict[str, Any] | None:
    if not packed:
        return None
    items = []
    for item in packed.get("items", []) or []:
        items.append(
            {
                "item_id": item.get("item_id"),
                "source": item.get("source"),
                "role": item.get("role"),
                "rank": item.get("rank"),
                "score": item.get("score"),
                "fused_score": item.get("fused_score"),
                "matched_metadata": item.get("matched_metadata") or {},
                "reason": item.get("reason"),
                "payload": _compact_payload(item.get("payload") or {}),
                "text_excerpt": _excerpt(item.get("text")),
                "text_hash": _sha(str(item.get("text") or "")),
            }
        )
    return {
        "original_query": packed.get("original_query"),
        "intent": packed.get("intent"),
        "entity_items_count": packed.get("entity_items_count"),
        "chunk_items_count": packed.get("chunk_items_count"),
        "items": items,
        "context_text_hash": _sha(str(packed.get("context_text") or "")),
        "context_text_chars": len(str(packed.get("context_text") or "")),
        "warnings": packed.get("warnings") or [],
        "debug": packed.get("debug") or {},
    }


def _compact_retrieval_trace(trace: dict[str, Any] | None) -> dict[str, Any] | None:
    if not trace:
        return None
    normalized = trace.get("normalized_query") or {}
    return {
        "original_query": trace.get("original_query"),
        "normalized_query": normalized,
        "expansion": trace.get("expansion") or {},
        "entity_candidates": [_compact_candidate(c) for c in trace.get("entity_candidates", []) or []],
        "chunk_candidates": [_compact_candidate(c) for c in trace.get("chunk_candidates", []) or []],
        "merged_candidates": [_compact_candidate(c) for c in trace.get("merged_candidates", []) or []],
        "selected_context": [_compact_candidate(c) for c in trace.get("selected_context", []) or []],
        "rerank_trace": _compact_rerank_trace(trace.get("rerank_trace")),
        "packed_context": _compact_packed_context(trace.get("packed_context")),
        "warnings": trace.get("warnings") or [],
        "timings_ms": trace.get("timings_ms") or {},
    }


def _failure_stage(final_state: dict[str, Any]) -> str | None:
    if final_state.get("is_in_domain") is False:
        return "guardrail"
    if final_state.get("cache_hit"):
        return None
    if final_state.get("retrieval_status") not in {None, "success"}:
        return "retrieval"
    if final_state.get("fallback_applied"):
        return "safe_fallback"
    if not final_state.get("draft_answer") and not final_state.get("final_answer"):
        return "generation"
    quality = final_state.get("answer_quality_report")
    if isinstance(quality, dict) and quality.get("passed") is False:
        return "quality_verifier"
    return None


def _initial_state(
    *,
    query: str,
    provider: str,
    model: str | None,
    history: list[dict[str, str]],
    allow_fallback: bool,
    bypass_cache: bool,
) -> dict[str, Any]:
    manifest = build_pipeline_version_manifest()
    settings = runtime_resilience_settings_from_env()
    return {
        "user_question": query,
        "user_id": None,
        "session_id": "audit13-trace",
        "conversation_history": history,
        "standalone_question": None,
        "use_history_context": False,
        "normalized_question": "",
        "patient_profile": {},
        "symptoms": [],
        "vector_contexts": [],
        "graph_facts": [],
        "sources": [],
        "retrieval_status": "not_started",
        "retrieval_error": None,
        "retrieval_trace": None,
        "packed_context": None,
        "pipeline_manifest": manifest,
        "pipeline_fingerprint": compute_pipeline_fingerprint(manifest),
        "observability_exported": None,
        "runtime_budget": DeadlineBudget.from_timeout(settings.agent_total_timeout_seconds),
        "runtime_resilience_settings": settings.model_dump(mode="json"),
        "runtime_resilience": {
            "runtime_resilience_version": manifest.get("runtime_resilience_version"),
            "agent_total_timeout_seconds": settings.agent_total_timeout_seconds,
            "deadline_started": True,
        },
        "safety_flags": [],
        "draft_answer": "",
        "final_answer": "",
        "answer_quality_report": None,
        "answer_guard_modified": None,
        "answer_guard_mode": None,
        "medical_severity": None,
        "severity_guard": None,
        "severity_guard_modified": None,
        "severity_guard_cache_eligible": None,
        "fallback_applied": False,
        "fallback_type": "none",
        "fallback_reason": None,
        "fallback_answer": None,
        "fallback_cache_eligible": True,
        "errors": [],
        "cache_enabled": None,
        "cache_checked": None,
        "cache_hit": None,
        "cache_key": None,
        "cache_similarity": None,
        "cache_reason": None,
        "cached_answer": None,
        "cached_sources": None,
        "cache_metadata": None,
        "llm_provider": provider,
        "llm_model": model,
        "allow_model_fallback": allow_fallback,
        "requested_provider": None,
        "requested_model": None,
        "actual_provider": None,
        "actual_model": None,
        "llm_fallback_used": False,
        "fallback_provider": None,
        "fallback_model": None,
        "fallback_chain": None,
        "bypass_cache": bypass_cache,
    }


async def run_trace(args: argparse.Namespace) -> dict[str, Any]:
    history = json.loads(args.history_json) if args.history_json else []
    if args.retrieval_only:
        retriever = HybridRetriever()
        try:
            result = await retriever.retrieve(args.query, top_k=5)
        finally:
            await retriever.close()
        retrieval_trace = _compact_retrieval_trace(result.metadata.get("retrieval_trace"))
        packed_context = _compact_packed_context(result.metadata.get("packed_context"))
        return {
            "query_id": args.query_id or _sha(args.query),
            "original_query": args.query,
            "conversation_context": history,
            "normalized_query": (
                (result.metadata.get("retrieval_trace") or {})
                .get("normalized_query", {})
                .get("normalized_text")
            ),
            "rewritten_query": args.query,
            "detected_intent": (
                (result.metadata.get("retrieval_trace") or {})
                .get("normalized_query", {})
                .get("intent")
            ),
            "detected_severity": None,
            "detected_entities": (
                (result.metadata.get("retrieval_trace") or {})
                .get("normalized_query", {})
            ),
            "requested_provider": None,
            "requested_model": None,
            "actual_provider": None,
            "actual_model": None,
            "fallback_used": None,
            "cache_hit": None,
            "cache_fingerprint": None,
            "retrieval_mode": "hybrid_qdrant_neo4j",
            "retrieval_status": "success" if result.vector_contexts else "no_evidence",
            "retrieval_error": None,
            "retrieval_trace": retrieval_trace,
            "packed_context": packed_context,
            "packed_context_token_count": len(str((result.metadata.get("packed_context") or {}).get("context_text", "")).split()),
            "prompt_profile": {
                "answer_formatting_contract_version": build_pipeline_version_manifest().get("answer_formatting_contract_version"),
                "prompt_family": "medical_answer",
            },
            "raw_model_answer": "",
            "quality_verifier_result": None,
            "severity_guard_result": None,
            "presentation_profile": None,
            "final_answer": "",
            "source_metadata": build_source_metadata(result.sources, result.vector_contexts),
            "response_origin": "retrieval_only",
            "guardrail_applied": False,
            "failure_stage": None,
            "pipeline_manifest": build_pipeline_version_manifest(),
            "pipeline_fingerprint": compute_pipeline_fingerprint(build_pipeline_version_manifest()),
            "errors": [],
        }
    state = _initial_state(
        query=args.query,
        provider=args.provider,
        model=args.model,
        history=history,
        allow_fallback=not args.no_model_fallback,
        bypass_cache=args.bypass_cache,
    )
    try:
        final_state = await clinical_graph.ainvoke(state)
    except Exception as exc:
        provider = args.provider
        return {
            "query_id": args.query_id or _sha(args.query),
            "original_query": args.query,
            "conversation_context": history,
            "requested_provider": provider,
            "requested_model": args.model,
            "actual_provider": None,
            "actual_model": None,
            "fallback_used": None,
            "cache_hit": None,
            "cache_fingerprint": state.get("pipeline_fingerprint"),
            "retrieval_mode": "hybrid_qdrant_neo4j",
            "prompt_profile": {
                "answer_formatting_contract_version": (
                    (state.get("pipeline_manifest") or {}).get("answer_formatting_contract_version")
                ),
                "prompt_family": "medical_answer",
            },
            "raw_model_answer": "",
            "final_answer": "",
            "source_metadata": [],
            "response_origin": "error",
            "guardrail_applied": False,
            "failure_stage": "pipeline_exception",
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:500],
            "pipeline_manifest": state.get("pipeline_manifest"),
            "pipeline_fingerprint": state.get("pipeline_fingerprint"),
            "provider": provider,
        }
    retrieval_trace = _compact_retrieval_trace(final_state.get("retrieval_trace"))
    packed_context = _compact_packed_context(final_state.get("packed_context"))
    source_metadata = build_source_metadata(
        final_state.get("sources", []),
        final_state.get("vector_contexts", []),
    )

    return {
        "query_id": args.query_id or _sha(args.query),
        "original_query": args.query,
        "conversation_context": history,
        "normalized_query": final_state.get("normalized_question"),
        "rewritten_query": final_state.get("standalone_question"),
        "detected_intent": (
            (final_state.get("retrieval_trace") or {})
            .get("normalized_query", {})
            .get("intent")
        ),
        "detected_severity": final_state.get("medical_severity"),
        "detected_entities": (
            (final_state.get("retrieval_trace") or {})
            .get("normalized_query", {})
        ),
        "requested_provider": final_state.get("requested_provider"),
        "requested_model": final_state.get("requested_model"),
        "actual_provider": final_state.get("actual_provider"),
        "actual_model": final_state.get("actual_model"),
        "fallback_used": final_state.get("llm_fallback_used"),
        "fallback_provider": final_state.get("fallback_provider"),
        "fallback_model": final_state.get("fallback_model"),
        "cache_hit": final_state.get("cache_hit"),
        "cache_reason": final_state.get("cache_reason"),
        "cache_metadata": final_state.get("cache_metadata") or {},
        "cache_fingerprint": final_state.get("pipeline_fingerprint"),
        "retrieval_mode": "hybrid_qdrant_neo4j",
        "retrieval_status": final_state.get("retrieval_status"),
        "retrieval_error": final_state.get("retrieval_error"),
        "retrieval_trace": retrieval_trace,
        "packed_context": packed_context,
        "packed_context_token_count": len(str((final_state.get("packed_context") or {}).get("context_text", "")).split()),
        "prompt_profile": {
            "answer_formatting_contract_version": (
                (final_state.get("pipeline_manifest") or {}).get("answer_formatting_contract_version")
            ),
            "prompt_family": "medical_answer",
        },
        "raw_model_answer": final_state.get("draft_answer") or "",
        "quality_verifier_result": final_state.get("answer_quality_report"),
        "severity_guard_result": final_state.get("severity_guard"),
        "presentation_profile": final_state.get("response_profile"),
        "final_answer": final_state.get("final_answer") or "",
        "source_metadata": source_metadata,
        "response_origin": (
            "cache" if final_state.get("cache_hit")
            else "guardrail" if final_state.get("is_in_domain") is False
            else "safe_fallback" if final_state.get("fallback_applied")
            else "llm"
        ),
        "guardrail_applied": final_state.get("is_in_domain") is False,
        "failure_stage": _failure_stage(final_state),
        "pipeline_manifest": final_state.get("pipeline_manifest"),
        "pipeline_fingerprint": final_state.get("pipeline_fingerprint"),
        "errors": final_state.get("errors") or [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a read-only Audit 13 answer pipeline trace.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--query-id", default="")
    parser.add_argument("--provider", default="gemini")
    parser.add_argument("--model", default=None)
    parser.add_argument("--history-json", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--bypass-cache", action="store_true", default=True)
    parser.add_argument("--use-cache", dest="bypass_cache", action="store_false")
    parser.add_argument("--no-model-fallback", action="store_true")
    parser.add_argument("--retrieval-only", action="store_true")
    args = parser.parse_args()

    trace = asyncio.run(run_trace(args))
    text = json.dumps(trace, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
