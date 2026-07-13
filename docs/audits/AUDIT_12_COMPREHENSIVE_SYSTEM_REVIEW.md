# Audit 12 Comprehensive System Review

## Scope

Audit performed on branch `audit-12-comprehensive-system-review` from base commit `a96a7a2`.

Rules observed:

- Inventory came from `git ls-files`.
- All 261 tracked files were read and recorded in a temporary ledger under `%TEMP%\acne-rag-audit-12`.
- No ingestion, database reset, collection deletion, Redis flush, tag creation, or merge was performed.
- `.env` was not modified or staged.
- Cache version remained `v5`; model defaults remained `gemini-3.5-flash`, `gemini-3.1-flash-lite`, and `qwen3:8b`.

## Baseline

- Branch: `audit-12-comprehensive-system-review`
- Base commit: `a96a7a2`
- Total tracked files: 261
- Working tree before branch creation: clean
- Local `main` matched `origin/main`
- Existing stashes were inspected and left untouched

## Architecture Map

Dependency direction is:

`FastAPI API -> LangGraph agent -> retrieval/provider/cache/database adapters -> external services`.

Main subsystems reviewed:

- API: `src/api/app.py`, `src/api/preflight.py`
- Agent graph and nodes: `src/agent/**`
- Provider and resilience: `src/agent/llm/**`, `src/integrations/**`, `src/resilience/**`
- Retrieval/reranking/context packing: `src/database/retriever.py`, `src/retrieval/**`
- Cache/observability: `src/cache/**`, `src/observability/**`
- Knowledge/ingestion/taxonomy: `src/knowledge/**`, `src/ingestion/**`, `scripts/ingest_knowledge.py`, `data/taxonomy/**`
- Frontend: `src/frontend/**`
- Scripts/CI/tests/docs: `scripts/**`, `tests/**`, `.github/**`, `docs/**`, README

No circular import requiring structural movement was found. The retained `src/web` and `src/web_legacy` files are intentionally inert legacy shells pointing to the maintained Vite frontend.

## Inventory

| Category | Count |
|---|---:|
| Total tracked files | 261 |
| Reviewed OK | 248 |
| Reviewed fixed | 13 |
| Reviewed deferred | 0 |
| Excluded generated | 0 |
| Pending | 0 |

## Issues And Fixes

| ID | Severity | File | Problem | Impact | Fix | Test | Status |
|---|---|---|---|---|---|---|---|
| A12-01 | P2 | `src/api/app.py` | Safe fallback `actual_model=None` was masked to request/default model in response and DB metadata | Misleading provider/model metadata for deterministic system fallback | Added `_chat_metadata_identity` and allowed `ChatMetadata.model=None` | `tests/test_safe_fallback_flow.py` | Fixed |
| A12-02 | P2 | `src/database/vector_store.py` | `search(..., filter=...)` ignored the filter argument | Future runtime/debug callers could query wider Qdrant scope than intended | Coerced dict/Qdrant filters and passed `query_filter` to `query_points` | `tests/test_storage_safety.py` | Fixed |
| A12-03 | P2 | `scripts/ingest_knowledge.py` | Incremental JSON source with `--limit-chunks` could log undefined `filename` | Edge-case crash during incremental JSON ingest planning | Added `display_name` for PDF/DOCX/JSON branches | Compile check | Fixed |
| A12-04 | P2 | `scripts/ingest_knowledge.py` | Manifest could be marked completed when Qdrant produced zero point IDs | Incremental runs could skip documents not actually indexed in Qdrant | Mark partial when Qdrant point IDs are missing and preserve partial reason | `tests/test_ingestion_cleanup.py` | Fixed |
| A12-05 | P2 | `scripts/diagnostics/debug_db.py` | Printed raw `DATABASE_URL` and performed writes by default | Secret exposure and accidental diagnostic DB writes | Masked URL and gated writes by `ALLOW_DIAGNOSTIC_WRITES=true` | `tests/test_diagnostic_script_safety.py` | Fixed |
| A12-06 | P2 | `scripts/diagnostics/persist_chat_manual.py` | Persisted manual chat row by default | Accidental write to local/runtime DB | Added explicit `ALLOW_DIAGNOSTIC_WRITES=true` opt-in | `tests/test_diagnostic_script_safety.py` | Fixed |
| A12-07 | P3 | `scripts/diagnostics/check_chat_db.py` | Hardcoded local DB URL and did not mask URL | Drift from env-driven runtime config | Loads `.env`, uses `DATABASE_URL`, masks output | `tests/test_diagnostic_script_safety.py` | Fixed |
| A12-08 | P2 | `src/frontend/src/utils/markdown.js` | Markdown links allowed arbitrary schemes | Generated answer could render `javascript:`/`data:` hrefs | Only `http/https` links render as anchors; unsafe links render as text | `src/frontend/src/utils/markdown.test.js` | Fixed |
| A12-09 | P3 | `src/frontend/index.html` | Favicon pointed to untracked `/vite.svg` | Broken/missing frontend icon | Changed to tracked `/favicon.svg` | Frontend build | Fixed |
| A12-10 | P3 | `src/agent/state.py` | Duplicate `fallback_reason` TypedDict field | Maintainer/type-contract confusion | Removed duplicate field, kept one canonical field | Full pytest | Fixed |
| A12-11 | P3 | `src/database/__init__.py`, `src/skills/__init__.py` | Package docstrings referenced legacy/unimplemented modules | Documentation drift | Updated docstrings to current structure | Full pytest | Fixed |
| A12-12 | P3 | README | Stale checkpoint tag/commit references | Operator could verify against old checkpoint | Updated to `checkpoint-audit11-pass` / `a96a7a2` | Docs audit | Fixed |
| A12-13 | P2 | `.env.example` | Missing reproducible/release readiness version contract variables | Release readiness failed env contract | Added `REPRODUCIBLE_ENVIRONMENT_VERSION` and `END_TO_END_RELEASE_READINESS_VERSION` | readiness tests | Fixed |

Severity totals:

- P0: 0
- P1: 0
- P2: 8
- P3: 5

## Cleanup

| File/module | Action | Evidence | Replacement | Tests |
|---|---|---|---|---|
| `src/agent/state.py` | Removed duplicate field | Same `fallback_reason` declared twice | Single TypedDict field | Full pytest |
| `src/database/__init__.py` | Updated stale docs | Listed modules not present in repo | Current database layer summary | Full pytest |
| `src/skills/__init__.py` | Updated stale docs | Listed untracked skill packages | Current registry scaffold summary | Full pytest |
| `README.md` | Updated stale checkpoint refs | Old tag/commit differed from current stable checkpoint | `checkpoint-audit11-pass`, `a96a7a2` | Release readiness/docs audit |

Files deleted: none.

Files merged: none.

Dependencies removed: none.

Config variables removed: none.

Files retained despite appearing unused:

- `src/web/index.html` and `src/web_legacy/index.html`: retained because they are intentional retired shell entrypoints.
- `PgVectorStore` placeholder: retained as an interface-compatible future backend; not active runtime.
- Diagnostic scripts: retained but hardened because they remain useful manual tools.

## Cross-System Findings

- API metadata now preserves `actual_provider="system"` and `actual_model=None` for deterministic safe fallback.
- Cache answer version remains `v5`; cache fingerprint changed automatically through manifest version/env contract, not by hardcoding.
- Qdrant runtime now honors dense search filters and continues to support unauthenticated local Docker plus authenticated Qdrant via `QDRANT_API_KEY`.
- Ingestion manifest logic is stricter about Qdrant indexing completeness without running ingestion or deleting data.
- Frontend Markdown renderer is safer for generated links while preserving tables, lists, inline code, and external links.
- No broad refactor or public API break was introduced.

## Failure-Path Matrix

| Failure | Expected behavior | Actual path reviewed | Cache behavior | Coverage |
|---|---|---|---|---|
| PostgreSQL unavailable | `/chat` still returns non-fatal response when persistence fails; health reports DB issue | `_persist_chat_to_db` warnings are non-fatal | No cache write dependency | API/release tests |
| Redis unavailable | cache lookup/store fail open without crashing | `redis_cache`, `semantic_cache` sanitize errors | Cache skipped | storage/cache tests |
| Qdrant unavailable | retrieval error becomes recoverable or health failure | retriever/search paths and preflight reviewed | no cache for errors | safe fallback/release tests |
| Neo4j unavailable | graph context degrades while vector context can remain | graph store error handling reviewed | no cache on errors | retrieval/safe fallback tests |
| Ollama unavailable | provider fallback chain reports unavailable or uses Gemini fallback if configured | provider layer reviewed | no cache on provider errors | runtime resilience tests |
| Gemini 429/503/timeout | retry/fallback by transient class; 503/504 structured at API boundary | provider resilience and release checks | no cache on fallback/errors | fallback/resilience/release tests |
| Invalid API key/model | non-retryable/permanent error, not masked as transient | Google adapter/provider tests | no cache | provider tests |
| Reranker timeout | falls back to local rules if allowed | reranker timeout/fallback path reviewed | retrieval continues | reranker tests |
| Empty retrieval | deterministic safe fallback, not cacheable | safe fallback node reviewed | cache skipped | safe fallback eval/tests |
| Quality guard failure | sanitized quality error report, no secret leakage | quality node reviewed | guarded result rules apply | severity/quality tests |
| Cache corruption/stale | invalid metadata causes miss | cache lookup validation reviewed | no stale hit | cache/severity tests |
| Frontend network failure | structured user-facing error | frontend API client reviewed | n/a | frontend tests |

## Concurrency Audit

- In-memory circuit breaker is model-scoped; tests cover provider/model isolation and half-open behavior.
- Cache writes are skipped for fallback, severity-modified, history, errors, provider fallback, and uncited answers.
- Async clients are closed where retriever owns them; diagnostic scripts do not create background services.
- No new global mutable singleton was added.
- The Qdrant filter change is per-call local state.
- Existing semantic reranker cache remains keyed by model/device; tests cover reuse and device change.

Remaining structural risk: model-scoped circuit state is in-memory per process, so multi-worker deployments will not share breaker state. This is acceptable for current `API_WORKERS=1`; distributed breaker storage would be a future production scaling task.

## Validation

| Command | Result |
|---|---|
| `.\venv\Scripts\python.exe -m pip check` | PASS |
| `.\venv\Scripts\python.exe -m compileall -q src scripts tests` | PASS |
| `.\venv\Scripts\python.exe -m py_compile src\api\app.py src\database\vector_store.py scripts\ingest_knowledge.py scripts\diagnostics\debug_db.py scripts\diagnostics\check_chat_db.py scripts\diagnostics\persist_chat_manual.py` | PASS |
| Targeted pytest for safe fallback, Qdrant filter, ingestion manifest, diagnostic script safety | PASS, 5 passed |
| `.\venv\Scripts\python.exe -m pytest -q` | PASS, 440 passed, coverage 75.25% |
| `.\venv\Scripts\python.exe scripts\eval_phase2_answer_quality.py` | PASS, 55/55 |
| `.\venv\Scripts\python.exe scripts\eval_safe_fallback_flow.py` | PASS, 13/13 |
| `.\venv\Scripts\python.exe scripts\eval_runtime_resilience.py` | PASS |
| `.\venv\Scripts\python.exe scripts\eval_phase2_all.py` | PASS, 11/11 |
| `.\venv\Scripts\python.exe scripts\inspect_cache_versions.py` | PASS |
| `.\venv\Scripts\python.exe scripts\check_reproducible_environment.py` | PASS |
| `.\venv\Scripts\python.exe scripts\check_release_readiness.py --mode offline` | PASS, 17/17 |
| `.\venv\Scripts\python.exe scripts\pre_ui_runtime_check.py` | PASS |
| `npm ci` in `src/frontend` | PASS |
| `npm test` in `src/frontend` | PASS, 9/9 |
| `npm run lint` in `src/frontend` | PASS |
| `npm run build` in `src/frontend` | PASS |
| `npm audit` in `src/frontend` | PASS, 0 vulnerabilities |
| `git diff --check` | PASS |

Static analysis note:

- `ruff` and `mypy` are referenced by project tooling expectations, but the current venv does not have those modules installed. They were attempted and reported `No module named ruff` / `No module named mypy`. No dependencies were added solely for audit.

## Cache And Fingerprint

- Cache version: `v5`
- Previous reference fingerprint from readiness checker: `c8507401e35043380fd119e7`
- Current fingerprint: `0230ac7e05f9049b6303a262`
- Legacy entries detected: `0`
- Warnings: `[]`

No cache schema change was made. The fingerprint is still computed from the pipeline manifest.

## Deleted Files

None.

## Deferred Items

| Item | Reason | Risk | Required next action |
|---|---|---|---|
| Shared circuit breaker state across multiple API workers | Current runtime target is `API_WORKERS=1`; adding distributed breaker state is out of scope | Multi-worker deployments could allow more than one half-open probe | Revisit only when scaling API workers above 1 |
| Ruff/mypy execution in local venv | Modules are not installed in current environment; audit policy said not to add dependencies just for audit | CI/local style drift may be missed if tools are expected elsewhere | Install configured dev tooling in a separate environment or add an explicit dev extra |

## Final Ledger

| Status | Count |
|---|---:|
| REVIEWED_OK | 248 |
| REVIEWED_FIXED | 13 |
| REVIEWED_DEFERRED | 0 |
| EXCLUDED_GENERATED | 0 |
| PENDING | 0 |

## Conclusion

AUDIT 12 COMPREHENSIVE SYSTEM REVIEW: PASS
