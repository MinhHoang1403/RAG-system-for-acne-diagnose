# Audit 15 Full System Review

## Executive Summary

Acne Advisor AI is a mature local-first RAG system for acne-related medical information. It combines a Phase 1 data foundation with a Phase 2 runtime that uses hybrid retrieval, taxonomy-derived entity cards, Neo4j graph enrichment, model generation, deterministic safety guards, answer-quality verification, source presentation, semantic cache versioning, and a React frontend.

Audit 15 found the architecture generally sound. The largest remaining technical risk is not an immediate runtime bug: changed-document cleanup during incremental ingestion remains conservative and can leave stale Qdrant/Neo4j records until a safe document-scoped cleanup path is implemented. The second important risk is entity coverage dependency on taxonomy completeness, demonstrated historically by the Tazorac/tazarotene issue and now mitigated by controlled entity rebuild workflow.

No production code was changed by this audit.

## Current System Status

| Area | Status | Notes |
|---|---|---|
| Git baseline | Healthy | Audit branch created from `b165e17` main |
| Phase 1 source layer | Healthy | 3 PDFs plus JSON dataset observed |
| Phase 1 chunk collection | Healthy | `acne_knowledge` 638 points, dense 3072 plus bm25 |
| Phase 1 entity collection | Healthy | `acne_entities_v1` 22 points after Tazorac rebuild |
| Neo4j entity graph | Healthy | 23 nodes, 18 relationships observed |
| Manifest | Healthy with extended statuses | 4 entries, `completed_with_graph_skipped` observed |
| Phase 2 retrieval | Healthy | Entity-aware hybrid retrieval pipeline |
| Phase 2 generation | Healthy with provider dependency | Gemini/Ollama paths and fallback layers |
| Safety/quality | Strong | Severity guard, fallback, verifier, finalizer |
| Frontend | Healthy | React/Vite with contract tests |
| CI | Healthy | Windows Python and frontend jobs |

## Architecture Summary

```text
sample_data + taxonomy
  -> scripts/ingest_knowledge.py
  -> Qdrant acne_knowledge + Neo4j + manifest/cache
  -> scripts/build_entity_index.py
  -> Qdrant acne_entities_v1
  -> scripts/build_entity_graph.py
  -> Neo4j deterministic entity graph

React UI
  -> FastAPI /chat
  -> LangGraph
  -> Redis cache
  -> Qdrant hybrid retrieval + entity retrieval
  -> Neo4j graph facts
  -> Gemini/Ollama generation
  -> quality/safety/fallback/finalizer
  -> PostgreSQL chat history
  -> React answer rendering
```

## Phase 1 Review

Phase 1 has the right primitives for maintainability:

- content-hash manifest
- content-addressed cache reuse
- Qdrant named dense and sparse vectors
- taxonomy-backed entity cards
- deterministic Neo4j entity graph
- controlled entity rebuild scripts

The key lesson from Audit 14 is now encoded in process: when a runtime answer misses an entity, do not assume chunk ingestion failed. Check the source layer, manifest, chunk Qdrant, entity Qdrant, Neo4j, and runtime detection in order.

## Phase 2 Review

Phase 2 is built around layered controls:

- normalization and query expansion preserve intent
- retrieval gathers both entity cards and evidence chunks
- context packing preserves primary entities
- prompt policy instructs direct and comparison answers
- verifier and finalizer correct common failures
- severity guard protects urgent/emergency cases
- cache is versioned by answer version and pipeline fingerprint

This is appropriate for the problem. It does mean that quality fixes may touch several layers. The existing tests are important because a prompt-only fix is usually insufficient.

## Feature Completeness

Implemented:

- chat API and frontend
- hybrid retrieval
- local/hybrid reranker
- answer quality verifier
- severity-aware answer guard
- deterministic safe fallback
- source presentation metadata
- chat history
- Redis semantic cache
- pipeline fingerprint
- reproducible environment checks
- release readiness checks
- controlled taxonomy/entity rebuild

Not implemented as production features:

- diagnosis or prescription automation
- web fallback retrieval
- external reranker production API
- LLM medical reviewer
- pgvector runtime retrieval

## Technology Summary

Core runtime:

- FastAPI
- LangGraph
- Qdrant
- Neo4j
- PostgreSQL
- Redis
- Google GenAI SDK
- Ollama
- React/Vite

Core versions/contracts:

- embedding model: `models/gemini-embedding-2`
- embedding dimension: 3072
- cache version: `v5`
- answer formatting contract: `answer_formatting_contract_v4`
- runtime resilience: `runtime_resilience_v1`
- severity guard: `severity_aware_answer_guard_v1`
- safe fallback: `safe_fallback_flow_v1`

## Validation Model

The project uses three layers of validation:

1. Unit and contract tests.
2. Offline eval scripts and readiness checks.
3. Manual/live smoke for external providers and local GPU reranker.

This is the right split. CI should not run ingestion or paid/live model calls. Developer release validation should still include live smoke when demonstrating the product.

Audit 15 validation after report generation:

- `pip check`: PASS
- `compileall`: PASS
- reproducible environment: PASS
- release readiness offline: PASS, 17/17
- Phase 2 aggregate eval: PASS, 11/11
- runtime resilience eval: PASS
- cache inspection: PASS, `CACHE_ANSWER_VERSION=v5`
- safe fallback eval: PASS, 13/13
- full pytest: PASS, 500 passed, coverage 76.77 percent
- frontend `npm ci`: PASS after stopping a stale local Vite dev server that locked a native Rolldown binding
- frontend tests: PASS, 23 passed
- frontend lint/build/audit: PASS

## Top Risks

| Priority | Risk | Action |
|---|---|---|
| P1 | Changed-document reingest can leave stale old Qdrant/Neo4j records | Implement safe document-scoped cleanup and tests |
| P1 | Taxonomy gaps can hide entities from retrieval even when chunks contain evidence | Add top-entity taxonomy coverage checks |
| P2 | Runtime cache can preserve old answers after policy changes | Keep bumping version/fingerprint intentionally and document cache-clear guidance |
| P2 | README count snapshots can drift | Refresh README after controlled data rebuilds |
| P2 | Local GPU reranker is environment-specific | Keep offline fallback tests and document local validation |
| P2 | Many scripts increase operator error risk | Add script command index by safe/read-only/mutating category |
| P3 | LLM nondeterminism can still slip through unseen query variants | Expand golden cases from every smoke failure |

## Do Not Touch Without Explicit Intent

- Do not reset or delete runtime stores casually.
- Do not run full ingestion for entity-only taxonomy fixes.
- Do not bypass cache version/fingerprint checks.
- Do not change embedding model or vector dimension without a full migration plan.
- Do not remove deterministic safety layers just because a model answer looks good once.
- Do not commit `.env` or runtime data.

## Final Conclusion

Audit 15 finds the system ready for report-only merge once validation passes. The architecture is layered and defensible. The main work left is operational hardening: safe changed-document cleanup, taxonomy coverage automation, and documentation refresh after data-layer rebuilds.
