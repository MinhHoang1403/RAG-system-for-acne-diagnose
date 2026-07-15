# Audit 15 Module Map

## Backend Entry Points

| Module | Key files | Primary entry points | External dependencies | Side effects |
|---|---|---|---|---|
| API | `src/api/app.py`, `src/api/preflight.py` | `/health`, `/retrieve`, `/models`, `/chat`, chat session routes | FastAPI, Postgres, Redis, Qdrant, Neo4j, LLM provider | Persists chat messages, can delete app-owned chat/session/cache data only through explicit endpoints |
| Agent graph | `src/agent/graph.py`, `src/agent/state.py` | `build_clinical_graph`, `run_clinical_agent` | LangGraph nodes | Routes request through guard, cache, retrieval, generation, quality, fallback, observability |
| LLM provider | `src/agent/llm/provider.py`, `src/agent/llm/ollama_client.py`, `src/integrations/google_genai.py` | `generate_llm_response`, `generate_ollama_response`, Google GenAI wrapper | Google GenAI SDK, Ollama HTTP | External model calls when runtime is not mocked/offline |
| Cache | `src/cache/semantic_cache.py`, `src/cache/redis_cache.py`, `src/agent/nodes/cache.py` | `get_exact_cache`, `set_answer_cache`, cache lookup/store nodes | Redis | Reads/writes answer cache keys |
| Retrieval | `src/database/retriever.py`, `src/database/vector_store.py`, `src/retrieval/*` | `HybridRetriever.retrieve`, `embed_query`, `rerank_candidates`, `pack_context` | Qdrant, Gemini embedding, Neo4j | Read-heavy; embedding call required for live retrieval |
| Knowledge graph runtime | `src/database/graph_store.py`, `src/database/neo4j_queries.py` | `Neo4jGraphStore` methods | Neo4j | Runtime read queries for graph facts |
| Chat history | `src/database/connection.py`, `src/database/repositories/chat_history.py`, `src/database/models/base.py` | DB session, chat/session CRUD | SQLAlchemy async, PostgreSQL | Persists and mutates chat history |
| Quality/safety | `src/quality/*`, `src/agent/nodes/quality.py`, `src/agent/nodes/severity.py`, `src/agent/nodes/respond.py` | `verify_answer_quality`, `apply_severity_aware_answer_guard`, finalizer | Pydantic, regex/rules | Mutates final answer text in memory only |
| Observability | `src/observability/versioning.py`, `src/observability/trace_exporter.py` | `build_pipeline_version_manifest`, `current_pipeline_fingerprint`, trace export | Filesystem only if enabled | Optional JSONL trace write after sanitization |

## Phase 1 Data Foundation

| Module | Key files | Entry points | Stores touched | Safety posture |
|---|---|---|---|---|
| Main ingestion | `scripts/ingest_knowledge.py` | CLI `cli`, `ingest_pipeline`, `ingest_pipeline_incremental` | Qdrant `acne_knowledge`, Neo4j, cache, manifest | Has incremental manifest and avoids global reset |
| Source loaders | `src/ingestion/json_loader.py`, PDF path in ingest script | `load_web_json_documents`, LlamaParse integration | Markdown cache and chunks | JSON loader is deterministic; PDF parsing needs external key |
| Metadata enrichment | `src/ingestion/domain_metadata.py` | `enrich_domain_metadata` | Qdrant payload metadata | Rule/taxonomy based |
| Cleanup planning | `src/ingestion/cleanup.py` | cleanup plan and guarded cleanup helpers | Qdrant only when explicitly invoked by pipeline | Collection safety checks and point-id filtering |
| Taxonomy | `src/knowledge/taxonomy_models.py`, `data/taxonomy/*.yaml` | load/validate taxonomy catalog | Source for entity cards and query normalization | Tracked, provenance-bearing |
| Entity Qdrant index | `src/knowledge/entity_cards.py`, `src/knowledge/entity_index.py`, `scripts/build_entity_index.py` | dry-run and upsert entity cards | Qdrant `acne_entities_v1` | Dry-run path exists; schema validation enforced |
| Entity Neo4j graph | `src/knowledge/graph_schema.py`, `src/knowledge/graph_index.py`, `scripts/build_entity_graph.py` | schema apply, graph upsert, validate | Neo4j | Neo4j property sanitizer prevents nested map writes |
| Controlled rebuild | `scripts/rebuild_phase1_entity_layer.py` | plan, backup, apply, rollback, verify | Entity Qdrant and Neo4j | Designed for entity-only rebuild, not full ingestion |

## Phase 2 Runtime

| Stage | File/function | Responsibility | Important tests/evals |
|---|---|---|---|
| API validation | `src/api/app.py` Pydantic models | Validate request/response schema | `tests/test_api_health.py`, `tests/test_pre_ui_runtime_check.py` |
| History load | `_load_recent_history_from_db` | Load recent chat context safely | chat repository tests |
| Normalization | `normalize_question_node`, `normalize_query` | Detect entities, intent, typo/no-diacritic aliases | query normalization tests |
| Rewrite | `rewrite_question_node` | Follow-up rewrite based on history | answer generation policy tests |
| Guardrails | `domain_guard_node`, `severity_classification_node` | Domain/safety routing and severity classification | severity/guardrail tests |
| Cache lookup | `cache_lookup_node` | Exact cache lookup by normalized question, model, versions, fingerprint | cache versioning tests |
| Retrieval | `retrieve_context_node`, `HybridRetriever.retrieve` | Dense/sparse search, entity cards, graph enrichment, rerank, context pack | phase2 retrieval/context/reranking evals |
| Fallback decision | `fallback_decision_node` | Safe fallback before generation if evidence missing or recoverable error | safe fallback tests/eval |
| Generation | `generate_answer_node`, `build_medical_prompt`, provider | Prompt and LLM call | answer policy, provider adapter tests |
| Generation fallback | `generation_fallback_decision_node`, `safe_fallback_node` | Deterministic fallback when generation invalid/empty | safe fallback eval |
| Quality guard | `answer_quality_node` | Rule-based verifier and repairs | answer quality verifier/eval |
| Presentation | `finalize_response_node`, `answer_formatting.py`, `source_presentation.py` | Markdown normalization, source display, warnings | answer formatting and frontend metadata tests |
| Cache store | `cache_store_node` | Store only eligible, versioned, quality-gated answers | cache tests |
| Observability | `observability_export_node` | Optional sanitized trace | trace exporter tests |

## Frontend

| Area | Files | Responsibility |
|---|---|---|
| App shell | `src/frontend/src/App.jsx`, `main.jsx`, `styles.css` | Chat layout, startup, state orchestration |
| API client | `src/frontend/src/api/chatApi.js`, `connectivity.js`, `config/api.js` | Backend URL resolution, health/connectivity, chat/session calls |
| Chat UI | `ChatInput.jsx`, `ChatWindow.jsx`, `ChatMessage.jsx` | Message rendering and input workflow |
| Controls | `Sidebar.jsx`, `ModelSelector.jsx`, `DebugPanel.jsx`, `EmptyState.jsx` | Session navigation, model choice, metadata display |
| Utilities | `markdown.js`, `presentationMetadata.js`, `storage.js` | Markdown rendering policy, source/badge metadata, local storage |
| Frontend tests | `*.test.js` in frontend `src` | API contract, connectivity, markdown, presentation metadata |

## Diagnostics and Evals

| Category | Scripts |
|---|---|
| Release/reproducibility | `check_reproducible_environment.py`, `check_release_readiness.py`, `inspect_cache_versions.py` |
| Phase 1 | `validate_phase1_complete.py`, `eval_phase1_readiness.py`, `eval_phase1_data_foundation_v14.py`, `inspect_ingestion_manifest.py` |
| Phase 2 | `eval_phase2_retrieval.py`, `eval_phase2_context_packing.py`, `eval_phase2_reranking.py`, `eval_phase2_answer_quality.py`, `eval_phase2_all.py` |
| Safety/fallback | `eval_severity_aware_guard.py`, `eval_safe_fallback_flow.py`, `eval_runtime_resilience.py` |
| Reranker | `eval_semantic_reranker.py` |
| Debug/trace | `audit_answer_pipeline.py`, `audit_qdrant_corpus.py`, `generate_phase2_debug_report.py` |

## Observed Cross-Cutting Concerns

- Versioning and fingerprinting are centralized in `src/observability/versioning.py`.
- `CACHE_ANSWER_VERSION` is currently `v5` in `.env.example` and CI.
- Runtime uses Google GenAI SDK through a local adapter, with legacy SDK scans in CI.
- The architecture intentionally keeps deterministic rule layers after LLM generation to protect answer quality and safety.
- `PgVectorStore` remains a placeholder while Qdrant is the active vector store.
