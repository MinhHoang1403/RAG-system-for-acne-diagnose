# Audit 15 Feature Inventory

## User-Facing Features

| Feature | Backend files | Frontend files | Status | Notes |
|---|---|---|---|---|
| Chat answer generation | `src/api/app.py`, `src/agent/*` | `App.jsx`, `ChatInput.jsx`, `ChatMessage.jsx` | Implemented | RAG answer with safety and formatting layers |
| Model selection | `src/api/app.py`, `src/agent/llm/provider.py` | `ModelSelector.jsx`, `chatApi.js` | Implemented | Gemini and Ollama provider paths |
| Chat history | `src/database/repositories/chat_history.py`, `src/api/app.py` | `Sidebar.jsx`, `storage.js` | Implemented | PostgreSQL plus frontend state |
| Source display | `src/agent/source_presentation.py`, `src/api/app.py` | `presentationMetadata.js`, `ChatMessage.jsx` | Implemented | Friendly display labels while preserving raw IDs |
| Debug metadata | `src/api/app.py`, `src/observability/*` | `DebugPanel.jsx` | Implemented | Sanitized metadata; observability optional |
| Backend connectivity UX | `src/api/preflight.py`, `/health` | `connectivity.js` | Implemented | Tests cover startup connection behavior |

## Medical Answer Features

| Feature | Files | Status | Coverage |
|---|---|---|---|
| Direct yes/no answer first | `medical_answer.py`, `answer_formatting.py`, `reason.py` | Implemented | answer generation policy tests |
| Primary entity preservation | `query_normalization.py`, `context_packer.py`, `answer_formatting.py` | Implemented | query/context/answer tests |
| Comparison completeness | `context_packer.py`, `answer_formatting.py`, verifier | Implemented | answer quality and formatting tests |
| Pregnancy safety wording | `severity_guard.py`, `answer_verifier.py`, `answer_formatting.py` | Implemented | safety/format tests |
| Severe acne escalation | `severity_guard.py`, `safe_fallback.py`, `answer_formatting.py` | Implemented | severity and safe fallback evals |
| Emergency/self-harm routing | `severity_guard.py`, `safe_fallback.py` | Implemented | severity and fallback tests |
| Antibiotic/BP/retinoid rules | `answer_verifier.py`, `answer_formatting.py`, retrieval rules | Implemented | answer quality eval |
| Vietnamese mojibake detection/repair | `src/agent/text_encoding.py`, tests | Implemented | text encoding tests |

## Retrieval Features

| Feature | Files | Status |
|---|---|---|
| Query normalization with taxonomy aliases | `query_normalization.py`, `knowledge_normalizer.py`, taxonomy YAML | Implemented |
| Taxonomy-backed expansion | `query_expansion.py` | Implemented |
| Qdrant dense search | `vector_store.py`, `retriever.py` | Implemented |
| Qdrant sparse BM25 search | `vector_store.py`, `retriever.py` | Implemented |
| Dense/sparse fusion | `retriever.py` | Implemented |
| Metadata boosting | `database/retriever.py`, `retrieval/metadata_boost.py` | Implemented |
| Entity card retrieval | `entity_retriever.py`, `entity_index.py` | Implemented |
| Candidate merge | `candidate_merge.py` | Implemented |
| Hybrid semantic rerank | `reranker.py`, `reranking/providers.py` | Implemented |
| Context packing | `context_packer.py` | Implemented |
| Neo4j graph enrichment | `graph_store.py`, `neo4j_queries.py` | Implemented |

## Phase 1 Features

| Feature | Files | Status |
|---|---|---|
| PDF to Markdown ingestion | `scripts/ingest_knowledge.py` | Implemented |
| JSON dataset ingestion | `src/ingestion/json_loader.py`, ingest script | Implemented |
| Incremental manifest | `scripts/ingest_knowledge.py` | Implemented |
| Content-hash cache reuse | `scripts/ingest_knowledge.py` | Implemented |
| Dermatology metadata enrichment | `src/ingestion/domain_metadata.py` | Implemented |
| Qdrant hybrid upsert | ingest script, `vector_store.py` helpers | Implemented |
| Graph extraction/cache | ingest script | Implemented |
| Neo4j ingestion graph | ingest script | Implemented |
| Taxonomy entity cards | `entity_cards.py`, `build_entity_index.py` | Implemented |
| Deterministic entity graph | `graph_schema.py`, `graph_index.py`, `build_entity_graph.py` | Implemented |
| Controlled entity rebuild | `rebuild_phase1_entity_layer.py` | Implemented |

## Operational Features

| Feature | Files | Status |
|---|---|---|
| Preflight checks | `src/api/preflight.py`, `inspect_phase2_readiness.py`, `pre_ui_runtime_check.py` | Implemented |
| Reproducible env check | `check_reproducible_environment.py`, lock file | Implemented |
| Release readiness check | `check_release_readiness.py` | Implemented |
| Runtime resilience | `src/resilience/*`, provider/retrieval nodes | Implemented |
| Pipeline fingerprint | `src/observability/versioning.py` | Implemented |
| Sanitized trace export | `src/observability/trace_exporter.py` | Implemented |
| Redis cache inspection | `inspect_cache_versions.py` | Implemented |
| Frontend CI | `.github/workflows/python-ci.yml` | Implemented |

## Explicitly Not Implemented as Production Features

| Non-feature | Evidence |
|---|---|
| Clinical diagnosis | README and safety text state information-only scope |
| Prescription automation | Safety wording and verifier avoid dosing/prescribing behavior |
| Web fallback retrieval | README notes not implemented |
| LLM medical reviewer | README notes not implemented |
| Production external reranker API | Local semantic/hybrid reranker is implemented; external API reranker is not a production path |
| pgvector runtime retrieval | `PgVectorStore` is a placeholder; Qdrant is active |

## Feature Risk Summary

| Risk | Severity | Reason |
|---|---|---|
| LLM nondeterminism can still create answer drift | Medium | Mitigated by verifier and finalizer but not eliminated |
| Taxonomy gaps can suppress entity retrieval | Medium | Tazorac history shows source evidence alone is not enough |
| Changed-document stale cleanup remains conservative | Medium | Prevents unsafe deletes but can leave stale points/facts |
| README snapshot drift can confuse operators | Low | Runtime/evals are authoritative, docs can lag |
