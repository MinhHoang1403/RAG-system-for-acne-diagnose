# Audit 15 Phase 2 Runtime Pipeline

## Runtime Overview

Phase 2 is a FastAPI plus LangGraph RAG runtime. It combines:

- Redis semantic answer cache
- PostgreSQL chat history
- Qdrant hybrid retrieval
- Qdrant entity-card retrieval
- Neo4j graph enrichment
- local/hybrid reranking
- Gemini or Ollama answer generation
- deterministic safety and quality guards
- React frontend

## API Flow

Entrypoint: `src/api/app.py`

Important routes:

- `GET /health`
- `GET /retrieve`
- `GET /models`
- `POST /chat`
- `GET /chat/sessions`
- `GET /chat/sessions/{session_id}/messages`
- `PATCH /chat/sessions/{session_id}/rename`
- `PATCH /chat/sessions/{session_id}/hide`
- `POST /chat/sessions/sync`
- `DELETE /chat/sessions`

`POST /chat` is the primary end-to-end route. It validates the request, loads recent chat history, calls the clinical agent, builds metadata, persists chat messages, and returns a structured answer.

## LangGraph Flow

Code: `src/agent/graph.py`

High-level flow:

1. `normalize_question_node`
2. `rewrite_question_node`
3. `domain_guard_node`
4. `severity_classification_node`
5. `cache_lookup_node`
6. `extract_symptoms_node`
7. `retrieve_context_node`
8. `fallback_decision_node`
9. `safe_fallback_node` if required
10. `generate_answer_node`
11. `generation_fallback_decision_node`
12. `answer_quality_node`
13. `finalize_response_node`
14. `cache_store_node`
15. `observability_export_node`

Routing decisions are in:

- `route_after_guard`
- `route_after_cache`
- `route_after_fallback_decision`
- `route_after_generation_fallback_decision`

## Retrieval Flow

Key files:

- `src/database/retriever.py`
- `src/database/vector_store.py`
- `src/database/graph_store.py`
- `src/retrieval/query_normalization.py`
- `src/retrieval/query_expansion.py`
- `src/retrieval/entity_retriever.py`
- `src/retrieval/candidate_merge.py`
- `src/retrieval/reranker.py`
- `src/retrieval/reranking/providers.py`
- `src/retrieval/context_packer.py`

Steps:

1. Normalize query and detect primary entities, intent, safety context.
2. Expand query from taxonomy.
3. Embed query with Gemini embedding.
4. Search Qdrant dense vector.
5. Search Qdrant sparse BM25 vector.
6. Fuse dense/sparse results.
7. Apply query-adaptive dermatology metadata boost.
8. Retrieve taxonomy-backed entity cards.
9. Merge chunk and entity candidates.
10. Rerank through configured provider.
11. Pack context with intent and primary-entity coverage.
12. Fetch graph facts from Neo4j.

## Reranking

Current intended runtime configuration from `.env.example`:

- `RERANK_PROVIDER=hybrid`
- `SEMANTIC_RERANK_DEVICE=cuda`
- `SEMANTIC_RERANK_BATCH_SIZE=4`
- `SEMANTIC_RERANK_MAX_CANDIDATES=16`
- fallback enabled

Design:

- Semantic reranker uses a local CrossEncoder only if the local model path is provisioned.
- Hybrid fusion combines semantic score, local rule score, and original retrieval order.
- If semantic reranker is unavailable and fallback is allowed, runtime uses deterministic local rules.

Risk:

- Local GPU model availability is machine-specific. CI therefore validates contracts and offline behavior, not GPU inference.

## Generation

Key files:

- `src/agent/nodes/reason.py`
- `src/agent/prompts/medical_answer.py`
- `src/agent/llm/provider.py`
- `src/integrations/google_genai.py`
- `src/agent/llm/ollama_client.py`

Important behavior:

- Direct yes/no and comparison instructions are in prompt and formatting layers.
- Gemini is accessed only through the `google-genai` adapter.
- Ollama is supported as a local provider.
- Runtime resilience wraps provider calls with timeout, retry, and circuit breaker.
- Model fallback can use configured Gemini fallback models when the primary provider/model fails.

Risk:

- LLM output remains nondeterministic. The system compensates with answer-quality verification, deterministic repairs, and formatting finalization.

## Safety and Quality

Key files:

- `src/quality/severity_guard.py`
- `src/quality/answer_verifier.py`
- `src/agent/answer_formatting.py`
- `src/agent/nodes/quality.py`
- `src/agent/nodes/respond.py`
- `src/agent/nodes/fallback.py`

Layers:

1. Domain guard.
2. Severity classification: routine, caution, urgent, emergency.
3. Safe fallback before or after generation.
4. Answer Quality Verifier.
5. Final answer presentation normalization.
6. Source display metadata separation from raw source IDs.

This layered design is appropriate for a medical-information RAG assistant because final model text is not trusted blindly.

## Cache and Fingerprint

Key files:

- `src/cache/semantic_cache.py`
- `src/agent/nodes/cache.py`
- `src/observability/versioning.py`

Important behavior:

- Cache key includes answer cache version and pipeline fingerprint.
- `CACHE_ANSWER_VERSION=v5`.
- `ANSWER_FORMATTING_CONTRACT_VERSION=answer_formatting_contract_v4`.
- Pipeline fingerprint is computed from version manifest, not hardcoded.
- Safe fallback answers are not cache-eligible.

Risk:

- Runtime cache can hold old answers after policy changes unless version/fingerprint changes or cache is manually cleared.

## Frontend Flow

Key files:

- `src/frontend/src/api/chatApi.js`
- `src/frontend/src/api/connectivity.js`
- `src/frontend/src/config/api.js`
- `src/frontend/src/App.jsx`
- `src/frontend/src/components/*`
- `src/frontend/src/utils/markdown.js`
- `src/frontend/src/utils/presentationMetadata.js`

Flow:

1. Resolve API base URL.
2. Check backend connectivity.
3. Send chat request with session/model/cache options.
4. Render answer Markdown.
5. Display friendly source metadata and badges.
6. Persist local UI state.

Risk:

- The frontend can only reflect metadata supplied by backend. Backend metadata contract tests are therefore important.

## Phase 2 Assessment

| Area | Status | Notes |
|---|---|---|
| API contract | Healthy | Routes and Pydantic models are explicit |
| Retrieval | Healthy | Entity-aware hybrid retrieval plus context packing |
| Reranking | Healthy with environment dependency | GPU semantic path is local-machine dependent |
| Generation | Healthy with provider dependency | Gemini/Ollama availability remains external |
| Safety | Strong deterministic guard coverage | Still not a substitute for clinical review |
| Cache | Versioned and fingerprinted | Manual cache care needed after major behavior changes |
| Frontend | Contract-tested | CI builds/lints frontend |
