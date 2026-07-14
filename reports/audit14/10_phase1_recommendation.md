# Phase 1 Recommendation

PHASE 1 DATA FOUNDATION AUDIT: PASS

PHASE 1 ACTION REQUIRED: D. ENTITY INDEX REBUILD

## Answer

Phase 1 is stable enough at the source, manifest, and chunk collection layers. The current corpus is not empty or stale: `acne_knowledge` has the Tazorac/tazarotene evidence needed for the investigated question.

The missing layer is the entity foundation:

- `data/taxonomy/drug_aliases.yaml` does not include Tazorac or tazarotene.
- `data/taxonomy/drug_taxonomy_v2.yaml` does not include Tazorac or tazarotene.
- `acne_entities_v1` has no Tazorac entity card and no tazarotene entity card.
- Neo4j has no Tazorac/tazarotene node or product-ingredient relation.
- Runtime normalization therefore detects only Differin/Epiduo and drops Tazorac before context packing.

Do not delete runtime data. Do not run full ingestion.

## Required Next Action

Highest-priority action:
Add Tazorac/tazarotene to taxonomy with source-backed provenance, then rebuild only entity artifacts:

1. Update taxonomy/alias definitions for:
   - `DrugProduct: Tazorac -> ActiveIngredient: tazarotene`
   - `ActiveIngredient: tazarotene -> DrugClass: topical_retinoid`
2. Dry-run entity index and entity graph.
3. If approved, rebuild `acne_entities_v1`.
4. If approved, upsert Neo4j entity graph.
5. Re-run retrieval trace for:
   `Tazorac, Differin và Epiduo khác nhau về hoạt chất như thế nào?`

## Why Not Full Reingestion

The full reingestion guard is false:

- no manifest hash mismatch;
- no duplicate document IDs;
- no duplicate manifest point IDs;
- `acne_knowledge` point count is 638 and includes the missing facts;
- Tazorac/tazarotene failure starts after chunk ingestion.

## Prioritized Plan

| Priority | Problem | Affected stores | Recommended fix | Reingestion required | Risk | Validation |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | Tazorac/tazarotene absent from taxonomy/entity graph | taxonomy, `acne_entities_v1`, Neo4j | Source-backed taxonomy addition, then entity index/graph rebuild | Entity-only rebuild yes; full chunk ingestion no | Medium | Entity coverage, Neo4j relation, retrieval trace |
| P1 | Runtime query expansion drops Tazorac | runtime normalizer via taxonomy | Same taxonomy addition; verify alias resolution | No chunk ingestion | Medium | Trace detected entities include Tazorac/tazarotene |
| P2 | Qdrant/Neo4j entity IDs use different schemes | entity collection, Neo4j | Document or align identity strategy in a later hardening step | No | Low/medium | Cross-store ID consistency test |
| P3 | Reranker timed out in trace | runtime retrieval | Tune timeout separately; not Phase 1 data blocker | No | Low | Reranker eval |
| P4 | Reports are large because they include evidence samples | audit tooling | Keep only excerpts, not raw dumps | No | Low | Manual review |

## Conclusion

Tazorac is not missing from source or `acne_knowledge`; it is missing from taxonomy-derived entity stores. The correct primary action is D, not C/E/F.
