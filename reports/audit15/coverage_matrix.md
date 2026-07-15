# Audit 15 Coverage Matrix

## Required Coverage

| Required area | Files inspected or referenced | Covered | Notes |
|---|---|---|---|
| Repository inventory | `git ls-files`, top-level directories, `docker compose ps` | Yes | Source inventory separated from runtime/dependency artifacts |
| Module map | `src/*`, `scripts/*`, frontend source | Yes | See `02_module_map.md` |
| Phase 1 data foundation | `scripts/ingest_knowledge.py`, `src/ingestion/*`, `src/knowledge/*`, taxonomy YAML | Yes | See `03_phase1_data_foundation.md` |
| Phase 2 runtime pipeline | `src/api/*`, `src/agent/*`, `src/retrieval/*`, `src/database/*`, `src/cache/*`, `src/quality/*` | Yes | See `04_phase2_runtime_pipeline.md` |
| Feature inventory | backend, frontend, scripts, tests | Yes | See `05_feature_inventory.md` |
| Technology stack | `.env.example`, `docker-compose.yml`, `requirements*`, `pyproject.toml`, frontend package, CI | Yes | See `06_technology_stack.md` |
| End-to-end flows | ingestion, entity rebuild, API, chat, fallback, frontend, release | Yes | See `07_end_to_end_flows.md` |
| Tests/evaluations | `tests/*`, `scripts/eval*`, `scripts/check*`, CI | Yes | See `08_tests_and_evaluations.md` |
| Architecture assessment | all inspected areas plus contradiction pass | Yes | See `09_architecture_assessment.md` |
| Full system review | synthesis across all reports | Yes | See `10_full_system_review.md` |

## Source Areas

| Area | Covered | Evidence |
|---|---|---|
| `src/api` | Yes | API routes, models, preflight |
| `src/agent` | Yes | LangGraph, nodes, prompts, formatting, LLM provider |
| `src/cache` | Yes | Redis and semantic cache |
| `src/database` | Yes | Qdrant, Neo4j, PostgreSQL, retriever |
| `src/frontend` | Yes | React app, components, API client, utils, tests |
| `src/ingestion` | Yes | JSON loader, metadata, cleanup |
| `src/integrations` | Yes | Google GenAI adapter |
| `src/knowledge` | Yes | Taxonomy, entity cards, Qdrant entity index, graph index |
| `src/observability` | Yes | Fingerprint and trace exporter |
| `src/quality` | Yes | Severity guard, answer verifier |
| `src/resilience` | Yes | Timeout/retry/circuit breaker settings |
| `src/retrieval` | Yes | Normalization, expansion, rerank, context packing |
| `src/skills` | Yes | Registry presence noted |
| `src/web`, `src/web_legacy` | Yes | Inert legacy web shells noted |

## Script Areas

| Area | Covered | Evidence |
|---|---|---|
| Ingestion | Yes | `ingest_knowledge.py` |
| Schema init | Yes | `init_schema.py`, `init_chat_schema.py` mentioned in operational flow |
| Entity build | Yes | `build_entity_index.py`, `build_entity_graph.py`, rebuild script |
| Validation | Yes | `validate_*`, `check_*`, `inspect_*` scripts |
| Evals | Yes | Phase 1, Phase 2, safety, fallback, reranker evals |
| Diagnostics | Yes | Read-only diagnostics inventory noted |

## Data and Runtime Stores

| Store | Covered | Mutation? | Evidence |
|---|---|---:|---|
| Qdrant `acne_knowledge` | Yes | No | Read-only collection config/count |
| Qdrant `acne_entities_v1` | Yes | No | Read-only collection config/count |
| Neo4j | Yes | No | Read-only count query |
| PostgreSQL | Partially | No | Docker health plus code/test review; no data query needed |
| Redis | Partially | No | Docker health plus cache code/test review; no key mutation |
| Manifest | Yes | No | Read-only structural/status check |
| Cache directory | Yes | No | Treated as runtime data |

## Configuration and CI

| File | Covered | Notes |
|---|---|---|
| `.env.example` | Yes | Version/model/reranker/cache variables reviewed |
| `.env` | Limited | Existence and Neo4j auth used for read-only count; secrets not printed |
| `docker-compose.yml` | Yes | Runtime store images and loopback ports |
| `requirements.txt` | Yes | Dependency classes |
| `requirements.lock.txt` | Yes | CI install source and reproducibility |
| `pyproject.toml` | Yes | Python version, pytest/coverage, tooling |
| `.github/workflows/python-ci.yml` | Yes | CI gate |
| `src/frontend/package.json` | Yes | Frontend stack and scripts |

## Prior Reports

| Report set | Covered | Reason |
|---|---|---|
| `reports/audit13/*` | Yes | Answer quality root cause and before/after |
| `reports/audit14/*` | Yes | Phase 1/Tazorac data foundation evidence |

## Reverse Pass

Command class:

- `git ls-files src scripts tests data .github | Sort-Object`

Result:

- 267 tracked files in the core audit scope.
- The tracked reverse pass avoids false positives from runtime stores and dependencies.

## Contradiction Pass

Command class:

- `rg -n "TODO|FIXME|deprecated|legacy|fallback|cache|fingerprint|guardrail|pregnan|Tazorac|tazarotene|ingestion|manifest|rebuild|Qdrant|Neo4j|Redis|PostgreSQL|Ollama|Gemini|Markdown|self-harm|fulminans|isotretinoin" .`

Exclusions:

- `venv`
- runtime database directories
- frontend `node_modules`
- frontend `dist`
- logs
- `.git`

Result:

- 3334 hits, mostly expected references.
- One real open implementation TODO: changed-document stale Qdrant/Neo4j cleanup in ingestion.
- No P0/P1 contradiction found.

## Coverage Gaps

| Gap | Reason | Severity |
|---|---|---|
| No full ingestion run | Explicitly prohibited and unnecessary for report audit | None |
| No entity rebuild/upsert | Explicitly prohibited | None |
| No paid/live chat call during static audit | Avoids external cost and nondeterminism | Low |
| No PostgreSQL row inspection | Not needed for architecture audit; code/tests cover chat history | Low |
| No Redis key inspection/mutation | Avoids cache disturbance; cache code/tests reviewed | Low |

## Coverage Conclusion

All required Audit 15 areas were covered. The audit was intentionally read-only for production code and runtime data.
