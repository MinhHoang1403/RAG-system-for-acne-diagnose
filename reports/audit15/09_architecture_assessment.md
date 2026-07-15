# Audit 15 Architecture Assessment

## Overall Assessment

The system is architecturally coherent for a local-first medical-information RAG assistant. It has a clear separation between:

- source ingestion and runtime retrieval
- chunk evidence and taxonomy-derived entity evidence
- generation and deterministic quality/safety repair
- raw source IDs and user-facing source display
- cache versioning and pipeline fingerprinting

The architecture is not a lightweight demo anymore. It is a multi-store, multi-stage system with operational complexity. The strongest design choice is that the system no longer trusts a single model output: retrieval, prompt policy, quality verifier, severity guard, safe fallback, and final presentation all participate in answer correctness.

## Strengths

| Strength | Evidence | Impact |
|---|---|---|
| Clear Phase 1/Phase 2 separation | ingestion scripts vs runtime `src` modules | Reduces accidental data rebuilds during runtime fixes |
| Hybrid retrieval | Qdrant dense/sparse, entity cards, Neo4j facts | Better recall and entity grounding |
| Taxonomy-backed entity layer | taxonomy YAML, entity cards, graph schema | Deterministic entity coverage and explainable fixes |
| Incremental manifest | ingestion manifest functions | Avoids reprocessing unchanged sources |
| Versioned cache/fingerprint | `observability/versioning.py`, cache tests | Prevents many stale-cache regressions |
| Safety layers | domain guard, severity guard, safe fallback, answer verifier | Important for medical-information scope |
| Local-first runtime stores | Docker Compose loopback bindings | Developer reproducibility and reduced external dependency |
| CI hardening | Windows CI, lock file, frontend build/lint | Catches broad regressions |

## Weaknesses

| Weakness | Severity | Evidence | Suggested action |
|---|---|---|---|
| Changed-document stale cleanup remains incomplete | Medium | TODO in `scripts/ingest_knowledge.py` and warning behavior | Implement document-scoped Qdrant/Neo4j cleanup after safe tests |
| Runtime depends on taxonomy completeness | Medium | Audit 14 Tazorac case | Add taxonomy coverage checks for common acne drugs before runtime eval |
| README snapshot drift | Low | README still lists older counts while live stores show newer counts | Refresh docs after entity rebuild checkpoints |
| Broad codebase with many scripts | Medium | 62 tracked scripts | Add a script index or command taxonomy to reduce operator error |
| GPU reranker environment is machine-specific | Low/Medium | Local model path in env example | Keep offline fallback contract tests and document local GPU validation |
| Full ingestion remains manual/costful | Medium | Uses external parsing/embedding/model services | Maintain dry-run and sample/eval gates |

## Risk Register

| ID | Risk | Severity | Current mitigation | Future hardening |
|---|---|---|---|---|
| A15-R1 | Stale old records after changed-document reingest | Medium | Warnings and no unsafe deletion | Safe document-ID cleanup with tests |
| A15-R2 | Taxonomy gap suppresses entity evidence | Medium | Audit 14 process, taxonomy tests, rebuild workflow | Coverage matrix for top acne entities |
| A15-R3 | Stale Redis answer after policy change | Medium | Cache version/fingerprint | Add release checklist item for cache version intent |
| A15-R4 | Provider outage or slow model call | Medium | Timeout/retry/circuit breaker/fallback | Provider status observability and live smoke notes |
| A15-R5 | LLM answer contradiction | Medium | Verifier, deterministic repairs, formatting | Expand golden cases from real smoke failures |
| A15-R6 | README/documentation drift | Low | Evals and reports are authoritative | Add docs validation for key counts if desired |
| A15-R7 | Runtime data counted as source | Low | Audit distinguishes tracked source vs runtime dirs | Keep reports and scripts using `git ls-files` for source inventory |
| A15-R8 | Legacy compatibility paths confuse readers | Low | Tests cover legacy promotion/removal | Add code comments where compatibility remains intentional |

## Contradiction Pass Findings

Command category:

- `TODO|FIXME`
- `deprecated|legacy`
- `fallback|cache|fingerprint|guardrail`
- medical/safety keywords
- store/pipeline keywords

Classification:

| Finding | Classification |
|---|---|
| `scripts/ingest_knowledge.py` TODO about stale Qdrant/Neo4j cleanup | Real known limitation, Medium |
| `legacy` in context bridge/cache version tests | Intentional compatibility behavior |
| `legacy` in Google SDK checks | Intentional negative check |
| `legacy` web shells | Retired inert entrypoints, Low |
| `fallback` references | Core resilience feature, not defect |
| `cache`/`fingerprint` references | Core versioning feature, not defect |
| Tazorac/tazarotene references | Expected after Audit 14 fix |
| pregnancy/self-harm/fulminans/isotretinoin references | Expected safety coverage |

No P0/P1 production-code defect was found in the static contradiction pass.

## Data Architecture Assessment

Phase 1 data design is solid:

- Source hashes drive incremental decisions.
- Runtime stores are separated by purpose.
- Entity layer can be rebuilt without full ingestion.
- Neo4j properties are sanitized.

The main architectural debt is cleanup semantics for changed source documents. The conservative current behavior favors safety over aggressive deletion. That is acceptable until a tested document-scoped cleanup path exists.

## Runtime Architecture Assessment

Phase 2 runtime design is strong:

- Retrieval is entity-aware and intent-aware.
- Context packing explicitly protects primary entity coverage.
- Generation is treated as one component, not the sole source of truth.
- Safety/quality layers are deterministic and testable.
- Frontend display is separated from raw source metadata.

The main runtime risk is operational dependency on external/local model availability. The project already has graceful fallback layers, but live smoke remains necessary before demos.

## Recommended Next Actions

| Priority | Action | Reason |
|---|---|---|
| P1 | Implement safe changed-document cleanup by `document_id` for Qdrant and Neo4j | Closes the remaining Phase 1 incremental debt |
| P1 | Add taxonomy coverage checklist for common acne entities | Prevents another Tazorac-like miss |
| P2 | Refresh README checkpoint counts after PR #8/#9 state | Avoid operator confusion |
| P2 | Create command index for scripts | Reduces risk from many similar diagnostics/evals |
| P2 | Add docs note for `completed_with_graph_skipped` manifest status | Keeps manifest semantics explicit |
| P3 | Add optional local GPU reranker validation recipe to docs | Helps reproduce machine-specific semantic reranker path |

## Merge Readiness Assessment

Audit 15 itself is report-only. If validation passes, it is safe to merge as documentation/report output. No production behavior changes were made.
