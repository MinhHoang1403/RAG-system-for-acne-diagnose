# Retrieval And Reranker Audit

Artifacts:

- `artifacts/audit13/baseline_eval.json`
- `artifacts/audit13/after_eval_live.json`
- `artifacts/audit13/trace_comparison_retrieval_after.json`

## Before

- Audit benchmark: 23/31 passed.
- Critical failures: 1.
- Retrieval/context failures were visible for comparison and typo/no-diacritic cases because query normalization did not always expose the primary entities and the context packer did not guarantee entity-card coverage for every primary entity.

## After

Live retrieval eval:

- Cases: 31/31 passed
- Critical failures: 0
- Live retrieval cases evaluated: 20
- Recall@5: 1.0
- Recall@10: 1.0
- MRR: 0.975
- Entity coverage: 1.0

Comparison trace after fix:

- Detected intent: `comparison`
- Selected entities include Differin, Epiduo, adapalene, and benzoyl peroxide.
- Packed sources include entity and knowledge evidence instead of only a single product branch.

## Fixes

- Query normalization now recognizes comparison, product ingredient, shared class, typo/no-diacritic, and negated pregnancy patterns.
- Context packer treats comparison as drug intent and preserves entity-card evidence for every primary drug/product/ingredient in the normalized query.

## Regression Tests

- `tests/test_query_normalization.py`
- `tests/test_context_packer.py`
- `tests/fixtures/answer_quality_audit_v13.json`
- `scripts/eval_end_to_end_answer_quality_v13.py --live-retrieval`
