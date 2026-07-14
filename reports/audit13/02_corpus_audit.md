# Corpus Audit

Source artifact: `artifacts/audit13/corpus_audit.json`

## Manifest

- Manifest path: `data/ingestion_manifest.json`
- Document count: 4
- Status: `completed_with_graph_skipped` for 4 documents
- Source types: 3 `source_document`, 1 `web_json`
- Total Qdrant point IDs: 638
- Duplicate point IDs: 0
- Duplicate document IDs: 0
- Missing source files: 0
- Content hash mismatches: 0
- Completed entries with empty point IDs: 0

## Qdrant Knowledge Collection

- Collection: `acne_knowledge`
- Points: 638
- Unique source paths: 4
- Duplicate chunk IDs: 0
- Empty chunks: 0
- Oversized chunks: 0
- Duplicate text hash groups: 5
- Very short chunks: 13
- Source types: 276 `web_json`, 362 `source_document`
- Text length chars: min 29, p50 958, p90 1970, p95 1985, max 2000

The short/duplicate chunks are tracked as non-critical corpus quality findings. They did not cause the reproduced answer failures, because live retrieval after the code fix reaches 100% required entity coverage.

## Entity Collection

- Collection: `acne_entities_v1`
- Points: 20
- Empty entity texts: 0
- Duplicate entity text hashes: 0
- Document/chunk metadata absent: 20 entity records

The missing document/chunk fields are expected for entity-centric cards, not Phase 1 document chunks.

## Re-ingestion

No data defect was found that requires controlled re-ingestion for Audit 13.
