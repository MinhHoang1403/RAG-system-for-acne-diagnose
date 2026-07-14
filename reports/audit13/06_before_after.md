# Before And After

## Benchmark

| Metric | Before | After |
|---|---:|---:|
| Total cases | 31 | 31 |
| Passed cases | 23 | 31 |
| Failed cases | 8 | 0 |
| Critical failures | 1 | 0 |

## Retrieval

| Metric | After live retrieval |
|---|---:|
| Recall@5 | 1.0 |
| Recall@10 | 1.0 |
| MRR | 0.975 |
| Required entity coverage | 1.0 |

Baseline live retrieval was not available before the patch because the initial live trace timed out. The reproducible baseline failure evidence is captured by the offline audit benchmark and trace notes in `01_baseline.md`.

## Code Changes

- Added read-only answer pipeline tracing.
- Added read-only Qdrant corpus auditing.
- Added Audit 13 answer-quality benchmark.
- Hardened query normalization.
- Preserved primary entity evidence in context packing.
- Improved comparison/source presentation handling.
- Added multi-retinoid class-check repair after live smoke exposed a wrong negative generation.
- Added regression tests for query normalization, context packing, and presentation.

## Live Smoke

- Gemini 3.5 fallback on: primary retry exhaustion observed, fallback to Gemini 3.1 Flash-Lite succeeded.
- Gemini 3.1 Flash-Lite fallback off: 11/11 required smoke queries produced non-empty final answers with no known critical retinoid contradiction.
- Ollama `qwen3:8b`: short identity query succeeded; longer requested-count query hit retry exhaustion.

## Re-ingestion

No re-ingestion plan was created. Audit 13 fixes do not require mutating Qdrant, Neo4j, Redis, PostgreSQL, or cache.
