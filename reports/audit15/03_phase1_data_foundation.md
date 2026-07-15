# Audit 15 Phase 1 Data Foundation

## Summary

Phase 1 is a source-to-knowledge-base pipeline that ingests PDF and JSON source material into:

- Qdrant chunk collection `acne_knowledge`
- Qdrant entity collection `acne_entities_v1`
- Neo4j deterministic entity graph
- `data/ingestion_manifest.json`
- Markdown and graph caches under `data/cache`

This audit did not run ingestion, rebuild entity indexes, upsert graph data, or mutate stores.

## Source Layer

Observed source corpus:

- 3 PDFs in `sample_data`
- `sample_data/web_raw_dataset.json`
- tracked taxonomy files in `data/taxonomy`

The JSON dataset is a first-class source through `src/ingestion/json_loader.py`. PDF ingestion is handled by `scripts/ingest_knowledge.py` with LlamaParse for Markdown conversion.

## Manifest Layer

Implemented in `scripts/ingest_knowledge.py`:

- `compute_file_hash`
- `load_ingestion_manifest`
- `save_ingestion_manifest`
- `get_incremental_file_plan`
- `update_manifest_after_success`
- `update_manifest_after_failure`

Local manifest snapshot:

- 4 document entries
- status observed: `completed_with_graph_skipped`
- total Qdrant point IDs observed from prior audit/run evidence: 638

Interpretation:

- Incremental ingestion is designed to skip unchanged content by content hash.
- Non-full states are represented explicitly, including graph-skipped/partial/warning statuses.
- The manifest protects future incremental runs from reprocessing unchanged sources.

Risk:

- Status vocabulary has grown beyond the initial `completed`, `completed_with_warnings`, `partial`, `failed` set. Tooling and docs must consistently understand extended statuses such as `completed_with_graph_skipped`.

## Chunking and Metadata

Key code:

- `scripts/ingest_knowledge.py` for parsing, Markdown cache, chunking, embedding, Qdrant payloads
- `src/ingestion/domain_metadata.py` for dermatology metadata enrichment
- `src/knowledge/versioning.py` for expected embedding and KB metadata

Important behavior:

- Chunk IDs are stable and source-path aware.
- Qdrant payloads include version metadata, source metadata, chunk IDs, and entity/dermatology metadata.
- Dense vector dimension is fixed at 3072 for `models/gemini-embedding-2`.
- Sparse vector uses hashed BM25 style vector under named sparse vector `bm25`.

## Qdrant Chunk Collection

Read-only local snapshot:

| Collection | Points | Dense vector | Sparse vector |
|---|---:|---|---|
| `acne_knowledge` | 638 | `dense`, 3072, cosine | `bm25` |

Strengths:

- Hybrid collection schema is explicit.
- Runtime and ingestion share sparse vector helpers.
- `QDRANT_API_KEY` support exists for secured Qdrant while preserving local Docker behavior.

Risks:

- Changed-document cleanup is intentionally conservative. The contradiction pass found the stale cleanup TODO in `scripts/ingest_knowledge.py`: old Qdrant points/Neo4j facts can remain stale for changed documents until document-scoped cleanup is fully proven safe.

## Taxonomy and Entity Layer

Key code:

- `data/taxonomy/drug_aliases.yaml`
- `data/taxonomy/drug_taxonomy_v2.yaml`
- `src/knowledge/taxonomy_models.py`
- `src/knowledge/entity_cards.py`
- `src/knowledge/entity_index.py`
- `scripts/build_entity_index.py`
- `scripts/rebuild_phase1_entity_layer.py`

Observed state:

- Taxonomy includes Tazorac/tazarotene with source-backed provenance.
- Qdrant entity collection has 22 points.
- Entity collection schema matches dense 3072 and sparse BM25.

Design:

- Entity cards are deterministic from taxonomy.
- Entity point IDs are stable.
- Rebuild tooling supports dry-run and controlled apply.

Risk:

- Entity coverage depends on taxonomy completeness. Audit 14 showed Tazorac was present in chunk evidence but absent from taxonomy-derived entity stores until the controlled entity rebuild.

## Neo4j Entity Graph

Key code:

- `src/knowledge/graph_schema.py`
- `src/knowledge/graph_index.py`
- `scripts/build_entity_graph.py`
- `scripts/validate_neo4j_schema.py`

Read-only local snapshot:

- Nodes: 23
- Relationships: 18

Important hardening:

- `sanitize_neo4j_properties` converts nested maps/lists/objects to JSON string properties such as `metadata_json`.
- Schema constraints and indexes are generated from code, not hand-applied ad hoc.

Risk:

- The runtime must continue to tolerate both deterministic and older entity ID schemes until all graph/query consumers are fully aligned.

## Cache Layer

Ingestion cache behavior:

- Markdown cache is keyed by content hash and can reuse unchanged source conversion.
- Graph cache is reused only when the chunk hash matches and `extraction_error` is false.
- Empty graph payloads are valid if extraction did not fail.

Risk:

- Cache directory is runtime data and should not be treated as tracked source.

## Current Phase 1 Assessment

| Layer | Status | Evidence |
|---|---|---|
| Source corpus | Healthy | 3 PDFs plus JSON dataset present |
| Manifest | Healthy with extended status vocabulary | 4 document entries, graph-skipped completion status |
| Chunk Qdrant | Healthy | 638 points, correct dense and sparse vectors |
| Entity Qdrant | Healthy after Tazorac rebuild | 22 points, correct schema |
| Neo4j graph | Healthy after Tazorac rebuild | 23 nodes, 18 relationships |
| Cleanup for changed docs | Known limitation | TODO and warning remain by design |

## Phase 1 Recommendation

Do not run full ingestion for routine taxonomy/entity fixes. Continue to use:

1. Taxonomy update with provenance.
2. Entity index dry-run.
3. Controlled entity index rebuild.
4. Entity graph dry-run.
5. Controlled Neo4j graph upsert.
6. Read-only validation.

Only run full ingestion when the source/chunk layer actually changes or manifest/hash validation indicates a true corpus rebuild need.
