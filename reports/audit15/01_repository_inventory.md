# Audit 15 Repository Inventory

## Scope

- Repository: `C:\Study\SuperRAGSystem\acne-agent-system`
- Branch created for this audit: `audit-15-full-system-architecture-review`
- Base commit: `b165e173d62e8037252b828d6520e6f393e99eff`
- Base summary: merge of PR #9, answer quality, safety, and format fix
- Audit mode: read-only for production code and runtime stores
- Mutations performed by this audit: new files under `reports/audit15/` only

## Git Gate

Observed before report writing:

- Current branch: `audit-15-full-system-architecture-review`
- `main`, `origin/main`, and `HEAD` initially pointed to `b165e173d62e8037252b828d6520e6f393e99eff`
- Working tree was clean before report generation
- No merge, rebase, cherry-pick, or revert operation was in progress
- Existing stashes were left untouched

## Tracked File Inventory

Tracked repository size:

- `git ls-files`: 297 tracked files
- Audit scope reverse pass, `src scripts tests data .github`: 267 tracked files

Tracked top-level distribution:

| Area | Count | Notes |
|---|---:|---|
| `src` | 120 | Backend, frontend source, retrieval, knowledge, cache, quality, resilience |
| `tests` | 82 | Unit, contract, eval wrappers, safety, retrieval, frontend-adjacent checks |
| `scripts` | 62 | Ingestion, schema init, validation, evals, diagnostics |
| `reports` | 16 | Prior Audit 13 and Audit 14 evidence, plus debug report |
| `docs` | 6 | Sequence diagrams and Mermaid sources |
| `data` | 2 | Tracked taxonomy YAML only |
| `.github` | 1 | Windows CI workflow |

Tracked `src` module distribution:

| Module | Tracked file count | Role |
|---|---:|---|
| `frontend` | 30 | React/Vite UI, frontend tests, config |
| `agent` | 22 | LangGraph workflow, nodes, prompts, formatting, LLM provider |
| `retrieval` | 14 | Query normalization, expansion, merge, rerank, context packing |
| `database` | 10 | Qdrant, Neo4j, PostgreSQL, chat history repository |
| `knowledge` | 9 | Taxonomy, entity cards, Qdrant entity index, Neo4j graph index |
| `quality` | 7 | Answer verifier, severity guard, Vietnamese text helpers |
| `resilience` | 7 | Timeouts, retry, circuit breaker, budget |
| `ingestion` | 5 | Metadata enrichment, JSON loader, cleanup helpers |
| `observability` | 4 | Pipeline fingerprint and sanitized trace export |
| `cache` | 3 | Redis and semantic cache |
| `skills` | 3 | Skill registry utilities |
| `api` | 2 | FastAPI app and preflight checks |
| `integrations` | 2 | Google GenAI adapter |
| `web`, `web_legacy` | 2 | Inert legacy web shells |

## Local Runtime Inventory

The local workspace also contains untracked/generated runtime data:

- `data/postgres`
- `data/qdrant`
- `data/neo4j`
- `data/redis_data`
- `data/cache`
- `venv`
- `src/frontend/node_modules`
- `src/frontend/dist`

These were treated as runtime/dependency artifacts, not source inventory. The raw recursive filesystem inventory is dominated by dependency and database files and should not be used as source size evidence.

## Source Data Inventory

Observed source files:

| Path | Purpose |
|---|---|
| `sample_data/acne-vulgaris-management-pdf-66142088866501.pdf` | PDF source |
| `sample_data/PIIS0190962223033893.pdf` | PDF source |
| `sample_data/qd_4416_cut.pdf` | PDF source |
| `sample_data/web_raw_dataset.json` | Web/raw JSON source |
| `data/taxonomy/drug_aliases.yaml` | Tracked taxonomy aliases |
| `data/taxonomy/drug_taxonomy_v2.yaml` | Tracked canonical taxonomy with provenance |

## Local Runtime Snapshot

Read-only checks found Docker services running:

| Service | Container | Status |
|---|---|---|
| PostgreSQL | `acne_postgres` | Up, healthy |
| Redis | `acne_redis` | Up, healthy |
| Neo4j | `acne_neo4j` | Up, healthy |
| Qdrant | `acne_qdrant` | Up, API reachable |

Read-only data counts:

| Store | Object | Count or schema |
|---|---|---|
| Qdrant | `acne_knowledge` | 638 points, `dense` 3072 cosine, sparse `bm25` |
| Qdrant | `acne_entities_v1` | 22 points, `dense` 3072 cosine, sparse `bm25` |
| Neo4j | Nodes | 23 |
| Neo4j | Relationships | 18 |
| Manifest | `data/ingestion_manifest.json` | 4 document entries, status `completed_with_graph_skipped` |

No runtime data was modified.

## Configuration Files

Important tracked configuration:

- `.env.example`
- `docker-compose.yml`
- `pyproject.toml`
- `requirements.txt`
- `requirements.lock.txt`
- `.github/workflows/python-ci.yml`
- `src/frontend/package.json`
- `src/frontend/package-lock.json`

Local `.env` exists but was read only for non-secret structural checks. Secrets were not copied into reports.

## CI Inventory

`.github/workflows/python-ci.yml` defines:

- Windows Python job using Python 3.11.9
- Locked dependency install from `requirements.lock.txt`
- `pip check`
- reproducibility checker
- offline release readiness checker
- legacy Google SDK scan
- full `pytest -q`
- frontend Node 24.x job with `npm ci`, `npm run build`, and `npm run lint`

## Inventory Notes

- README still contains an older checkpoint snapshot in the Phase 1 table. Current local live counts are 638 chunk points, 22 entity points, and 23 Neo4j nodes with 18 relationships after Tazorac entity rebuild. This is a documentation drift, not a runtime defect.
- The reverse pass file list was based on tracked files to avoid counting runtime stores.
- The contradiction pass excluded dependency folders and mutable database directories.
