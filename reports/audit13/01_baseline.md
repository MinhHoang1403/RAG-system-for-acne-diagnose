# Audit 13 Baseline

Branch: `audit-13-end-to-end-answer-quality`

Baseline artifacts:

- `artifacts/audit13/baseline_eval.json`
- `artifacts/audit13/corpus_audit.json`
- `artifacts/audit13/neo4j_audit.json`

## Initial Findings

- Audit benchmark: 23/31 passed, 8 failed, 1 critical failure.
- Manifest: 4 documents, all runtime source files present, 638 Qdrant point IDs, no duplicate point IDs, no hash mismatches.
- Qdrant `acne_knowledge`: 638 points, 4 source files, no duplicate chunk IDs, no empty chunks, 5 duplicate text hashes, 13 very short chunks.
- Qdrant `acne_entities_v1`: 20 entity cards. Missing document/chunk metadata is expected for entity-card records and is not treated as a Phase 1 document chunk defect.
- Neo4j deterministic graph: PASS, 21 nodes, 15 relationships.

## First Failing Stages

| Symptom | First failing stage | Evidence |
|---|---|---|
| Product comparison missed entities | D. Query normalization | Comparison/product queries were classified as `general_acne_question`. |
| Context for product comparison lost the second product/ingredients | K. Context packing | Entity cards for all primary entities were not preserved when max context items were full. |
| Epiduo composition answer overrode comparison answer | P. Presentation formatting | Presentation finalizer selected a composition template before comparison semantics. |
| Typo/no-diacritic drug queries missed entities | D. Query normalization | `diferin`, `adapalen`, and `benzoyl peroxid` were not recognized as aliases. |
| Corrected pregnancy context was retained | D/G. Query normalization and intent | Negated pregnancy turns still carried pregnancy safety context. |
| Raw technical source labels reached UI metadata | Q. Source presentation | DOI-like PDF filename/title samples were exposed as display labels. |

## Safety

No ingestion, database reset, collection deletion, cache deletion, or runtime data mutation was performed.
