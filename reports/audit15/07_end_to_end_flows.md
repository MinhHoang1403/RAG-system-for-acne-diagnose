# Audit 15 End-to-End Flows

## Flow 1: Full Phase 1 Ingestion

Input:

- PDFs and JSON under `sample_data`

Path:

1. `scripts/ingest_knowledge.py` discovers source files.
2. PDF sources are parsed to Markdown and cached.
3. JSON sources are loaded through `src/ingestion/json_loader.py`.
4. Semantic chunks are built and enriched with dermatology metadata.
5. Optional graph extraction runs and caches valid chunk graph payloads.
6. Neo4j upsert runs unless skipped.
7. Gemini embeddings are generated.
8. Qdrant points are upserted with `dense` and `bm25`.
9. Manifest is updated per source.

Expected output:

- Updated Qdrant chunk collection.
- Updated Neo4j graph when graph stages are enabled.
- Updated manifest.

Audit note:

- Not executed in Audit 15.

## Flow 2: Incremental Ingestion

Input:

- Source files plus `data/ingestion_manifest.json`

Path:

1. Compute SHA256 content hash.
2. Compare each source with manifest.
3. Skip unchanged completed-like sources.
4. Reingest new, changed, failed, or partial sources.
5. Update manifest after success/failure.

Expected output:

- Only changed/new files are processed.

Known limitation:

- Changed-document stale cleanup for old Qdrant/Neo4j records remains conservative and explicitly warned.

## Flow 3: Controlled Entity Index Rebuild

Input:

- `data/taxonomy/*.yaml`

Path:

1. Validate taxonomy.
2. Build deterministic entity cards.
3. Dry-run entity points.
4. Upsert to `acne_entities_v1` only when explicitly requested.
5. Validate collection schema and point coverage.

Expected output:

- Updated entity collection without full chunk ingestion.

## Flow 4: Controlled Entity Graph Upsert

Input:

- Taxonomy-derived graph records.

Path:

1. `scripts/build_entity_graph.py --dry-run`.
2. Optional schema apply.
3. `src/knowledge/graph_index.py` sanitizes properties.
4. Nodes and relationships are merged into Neo4j.
5. Validation counts and required relationships are checked.

Expected output:

- Deterministic Neo4j entity graph.

## Flow 5: `/health`

Input:

- GET request.

Path:

1. `src/api/app.py` health endpoint.
2. Runs configured preflight checks through `src/api/preflight.py`.
3. Reports service status without mutating stores.

Expected output:

- Health payload with component statuses.

## Flow 6: `/retrieve`

Input:

- Query string and `top_k`.

Path:

1. API validates query.
2. `HybridRetriever.retrieve` normalizes and expands query.
3. Qdrant dense/sparse retrieval runs.
4. Entity retrieval, merge, rerank, context packing, and graph enrichment run.
5. API returns contexts/facts.

Expected output:

- Retrieval results and graph facts without LLM answer generation.

## Flow 7: `/chat` Cache Hit

Input:

- POST `/chat` with non-bypassed cache and cacheable question.

Path:

1. API loads history.
2. LangGraph normalizes and guard-checks.
3. `cache_lookup_node` builds versioned cache key.
4. Redis returns cached answer.
5. Response finalizes and chat history persists.

Expected output:

- Cached answer, metadata provider `cache`, no LLM call.

## Flow 8: `/chat` RAG Miss

Input:

- POST `/chat` with cache miss.

Path:

1. Normalize, rewrite, guard, severity.
2. Retrieve contexts and graph facts.
3. Build medical prompt.
4. Call provider through resilience wrapper.
5. Verify answer quality.
6. Finalize Markdown/presentation.
7. Store cache if eligible.
8. Persist chat messages.

Expected output:

- RAG answer with sources, metadata, and stored session history.

## Flow 9: Safe Fallback Before Generation

Input:

- Empty question, out-of-scope question, missing evidence, or recoverable retrieval failure.

Path:

1. Fallback decision evaluates state.
2. `safe_fallback_node` builds deterministic safe answer.
3. Severity guard still applies.
4. Answer is finalized.
5. Cache store is skipped.

Expected output:

- Safe deterministic answer with fallback metadata.

## Flow 10: Provider Fallback

Input:

- Primary provider/model fails with transient or retryable error.

Path:

1. Resilience layer applies timeout/retry.
2. Circuit breaker tracks repeated failure.
3. Provider fallback model is attempted when configured.
4. Metadata records actual and fallback provider/model.

Expected output:

- Answer from fallback provider/model or safe fallback if generation fails.

## Flow 11: Severity-Aware Guard

Input:

- User question containing routine, caution, urgent, emergency, self-harm, or severe symptom markers.

Path:

1. `classify_medical_severity`.
2. Severity metadata added to state.
3. Answer guard prepends/appends required medical safety wording.
4. Finalizer removes duplication.

Expected output:

- Safety-appropriate response without duplicated warnings.

## Flow 12: Answer Formatting

Input:

- Draft answer, profile, sources, metadata.

Path:

1. Infer response profile.
2. Apply deterministic profile answer when applicable.
3. Normalize Markdown.
4. Remove stale boilerplate and duplicate headings.
5. Add one disclaimer where policy requires it.
6. Build source display metadata.

Expected output:

- Consistent Markdown answer and friendly source display.

## Flow 13: Frontend Startup

Input:

- User opens React app.

Path:

1. Frontend resolves API base URL.
2. Connectivity helper checks backend.
3. App shows available state and model controls.
4. Chat UI becomes usable when backend is reachable.

Expected output:

- Stable startup even while backend is still warming up.

## Flow 14: Frontend Chat

Input:

- User sends a message.

Path:

1. `ChatInput` emits message.
2. `chatApi.js` sends POST `/chat`.
3. `ChatWindow` appends pending and final messages.
4. `ChatMessage` renders Markdown and metadata.
5. Session data is synchronized.

Expected output:

- Displayed answer with badges and sources that match backend metadata.

## Flow 15: Release Validation

Input:

- Developer runs offline validation scripts and test suites.

Path:

1. `pip check`.
2. `compileall`.
3. `pytest`.
4. phase eval scripts.
5. cache/reproducibility/release readiness checks.
6. frontend test/lint/build/audit.

Expected output:

- PASS before merge.

## Flow-Level Risks

| Flow | Risk | Severity |
|---|---|---|
| Incremental ingestion | changed-document cleanup can leave stale old records | Medium |
| RAG miss | external provider outage can slow or fail generation | Medium |
| Semantic reranker | local GPU model missing falls back to rules | Low/Medium |
| Cache hit | stale cache if version/fingerprint not bumped after policy changes | Medium |
| Documentation | README count snapshot can drift after controlled rebuilds | Low |
