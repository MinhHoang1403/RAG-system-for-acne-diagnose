# Audit 15 Tests and Evaluations

## Test Inventory

Tracked Python tests include 78 Python test files plus golden fixtures. Coverage areas:

- API health and preflight
- answer generation policy
- answer formatting contract
- answer quality verifier
- cache versioning
- candidate merge
- context packing
- ingestion chunking/file discovery/cleanup
- JSON loader
- taxonomy models, aliases, migration, retrieval, validation
- entity cards, entity graph schema, entity retriever
- Neo4j query/schema validators
- Qdrant/retrieval trace behavior
- reranker contracts, score normalization, timeout, fallback, runtime integration
- semantic reranker
- runtime resilience
- safe fallback flow
- severity guard
- text encoding
- observability sanitizer and trace exporter
- phase eval wrappers
- release readiness and reproducible environment

Frontend tests:

- `src/frontend/src/api/chatApi.test.js`
- `src/frontend/src/api/connectivity.test.js`
- `src/frontend/src/config/api.test.js`
- `src/frontend/src/utils/markdown.test.js`
- `src/frontend/src/utils/presentationMetadata.test.js`

## Eval and Inspection Scripts

| Script | Purpose |
|---|---|
| `scripts/eval_phase1_data_foundation_v14.py` | Read-only Phase 1 data foundation audit |
| `scripts/eval_phase1_readiness.py` | Phase 1 readiness |
| `scripts/validate_phase1_complete.py` | Qdrant/manifest/Neo4j/taxonomy validation |
| `scripts/eval_phase2_retrieval.py` | Retrieval quality |
| `scripts/eval_phase2_context_packing.py` | Context packing |
| `scripts/eval_phase2_reranking.py` | Reranking |
| `scripts/eval_phase2_answer_quality.py` | Answer quality golden cases |
| `scripts/eval_phase2_all.py` | Aggregate Phase 2 eval |
| `scripts/eval_runtime_resilience.py` | Timeout/retry/circuit breaker |
| `scripts/eval_safe_fallback_flow.py` | Deterministic fallback |
| `scripts/eval_severity_aware_guard.py` | Severity-aware answer guard |
| `scripts/eval_semantic_reranker.py` | Offline/local semantic reranker checks |
| `scripts/inspect_cache_versions.py` | Cache version and legacy entry inspection |
| `scripts/inspect_phase2_readiness.py` | Phase 2 readiness inspection |
| `scripts/pre_ui_runtime_check.py` | Backend/frontend pre-UI runtime checks |
| `scripts/check_reproducible_environment.py` | Locked dependency and environment reproducibility |
| `scripts/check_release_readiness.py` | Offline release gate |

## CI Coverage

`.github/workflows/python-ci.yml` covers:

- Python 3.11.9 on Windows
- locked dependency install
- `pip check`
- reproducibility checker
- offline release readiness checker
- legacy Google SDK scan
- full `pytest -q`
- frontend `npm ci`
- frontend build
- frontend lint

CI does not run:

- live Gemini calls
- local GPU semantic reranker inference
- live ingestion
- database reset/rebuild commands

This is appropriate for PR safety. Live/local validations remain developer-operated.

## Prior Verified Results

Before Audit 15, the latest post-merge validation on `main` had passed:

- `pip check`
- `compileall`
- full pytest with coverage above 70 percent
- Audit 14 temp eval
- Audit 13 answer quality benchmark
- Phase 2 answer quality eval
- safe fallback eval
- Phase 2 aggregate eval
- runtime resilience eval
- cache version inspection
- reproducible environment check
- release readiness offline
- frontend tests, lint, build, audit
- deterministic smoke

Audit 15 reran validation after report generation because only reports were added.

## Audit 15 Validation Results

| Command | Result | Notes |
|---|---|---|
| `.\venv\Scripts\python.exe -m pip check` | PASS | No broken requirements |
| `.\venv\Scripts\python.exe -m compileall src scripts tests` | PASS | Compile succeeded |
| `.\venv\Scripts\python.exe scripts\check_reproducible_environment.py` | PASS | `REPRODUCIBLE_ENVIRONMENT: PASS` |
| `.\venv\Scripts\python.exe scripts\check_release_readiness.py --mode offline` | PASS | 17/17 checks |
| `.\venv\Scripts\python.exe scripts\eval_phase2_all.py` | PASS | 11/11 checks |
| `.\venv\Scripts\python.exe scripts\eval_runtime_resilience.py` | PASS | Retry exhaustion and circuit open checks passed |
| `.\venv\Scripts\python.exe scripts\inspect_cache_versions.py` | PASS | `CACHE_ANSWER_VERSION=v5`, no legacy entries |
| `.\venv\Scripts\python.exe scripts\eval_safe_fallback_flow.py` | PASS | 13/13 cases |
| `.\venv\Scripts\python.exe -m pytest -q` | PASS | 500 passed, total coverage 76.77 percent |
| `npm.cmd ci` | PASS after stopping stale frontend dev server | Initial attempt hit Windows `EPERM` on a locked Rolldown native binding |
| `npm.cmd test` | PASS | 23 frontend tests passed |
| `npm.cmd run lint` | PASS | ESLint completed |
| `npm.cmd run build` | PASS | Vite production build completed |
| `npm.cmd audit` | PASS | 0 vulnerabilities |

## Test Strengths

- Tests cover both isolated units and higher-level eval workflows.
- Golden cases exist for retrieval, answer quality, reranker, Vietnamese verifier, and ingestion.
- Safety and formatting regressions have dedicated tests.
- Reranker fallback and timeout behavior are covered.
- CI blocks legacy Google SDK regressions.

## Test Gaps

| Gap | Severity | Reason |
|---|---|---|
| No live paid-provider test in CI | Low/Medium | Correct for cost/safety, but provider outages remain runtime concerns |
| No GPU semantic reranker in CI | Low/Medium | Hardware-dependent |
| No full ingestion in CI | Medium | Correct for cost/data safety; requires manual Phase 1 validation |
| README/runtime snapshot drift not a CI failure | Low | Docs can lag counts after controlled rebuilds |
| Changed-document cleanup TODO not covered as completed behavior | Medium | Intentional limitation should become a future test once implemented |

## Recommended Validation Set

Minimum after report-only changes:

1. `.\venv\Scripts\python.exe -m pip check`
2. `.\venv\Scripts\python.exe -m compileall src scripts tests`
3. `.\venv\Scripts\python.exe -m pytest -q`
4. `.\venv\Scripts\python.exe scripts\check_reproducible_environment.py`
5. `.\venv\Scripts\python.exe scripts\check_release_readiness.py --mode offline`
6. `git diff --check`

Preferred additional checks:

1. `.\venv\Scripts\python.exe scripts\eval_phase2_all.py`
2. `.\venv\Scripts\python.exe scripts\eval_runtime_resilience.py`
3. `.\venv\Scripts\python.exe scripts\inspect_cache_versions.py`
4. Frontend `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run build`, `npm.cmd audit`
