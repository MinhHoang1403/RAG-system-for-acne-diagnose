# Cross-Store Consistency

## Tazorac Case

| Layer | Result | Evidence |
| --- | --- | --- |
| Source corpus | Present | `sample_data/web_raw_dataset.json` includes `Tazarotene (Brand names: ... Tazorac)` and `tazarotene (Tazorac)`. |
| Manifest | Consistent | 4 entries, 638 Qdrant point IDs, no missing source, no hash mismatch, no duplicate point IDs. |
| Qdrant `acne_knowledge` | Present | `Tazorac`: 4 matching points; `tazarotene`: 16 matching points. |
| Qdrant `acne_entities_v1` | Missing | No DrugProduct card for Tazorac and no ActiveIngredient card for tazarotene. |
| Neo4j | Missing | No Tazorac node, no tazarotene node, no `Tazorac -HAS_ACTIVE_INGREDIENT-> tazarotene`. |
| Runtime detection | Missing | Trace detects only `Differin`, `Epiduo`, `adapalene`, and `benzoyl_peroxide`. |

First failing stage: `qdrant_entity`.

## Additional Consistency Finding

The 20 shared Qdrant/Neo4j entities use different `entity_id` schemes:

- Qdrant entity payloads use readable IDs such as `drug_product:differin`.
- Neo4j graph nodes use hashed stable IDs such as `drug_product:510bbe62ab4f838d111b8fad`.

This is not the first cause of the Tazorac failure because Tazorac/tazarotene are absent from both entity stores, but it should be tracked as a cross-store identity consistency issue.
