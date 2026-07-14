# Entity Graph Audit

Source artifact: `artifacts/audit13/neo4j_audit.json`

## Neo4j Snapshot

- Validator result: PASS
- Nodes: 21
- Relationships: 15
- Labels:
  - `ActiveIngredient`: 7
  - `Condition`: 1
  - `DrugClass`: 6
  - `DrugProduct`: 3
  - `SafetyContext`: 4
- Relationships:
  - `BELONGS_TO_CLASS`: 11
  - `HAS_ACTIVE_INGREDIENT`: 4

## Schema Checks

- Required labels and relationship types present.
- Required node and relationship properties present.
- No legacy graph properties detected.
- No duplicate canonical names.
- No orphan drug products.
- Active ingredients have class relationships.
- Relationship directions valid.
- Required constraints and indexes present.
- Runtime Neo4j queries produced no critical notifications.

## Root Cause Conclusion

Neo4j was not the first failing stage for the reproduced answer-quality failures. The graph contained the deterministic product/class relationships needed by runtime; the failures came later in query understanding, context packing, and presentation.
