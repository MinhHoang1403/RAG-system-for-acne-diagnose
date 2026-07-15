# Live Smoke Regressions - Root Cause and Fix

## Scope

Audit and fix two live `/chat` answer-quality regressions found after Answer Quality Generalization V2:

- Emergency query: `Sau khi bôi thuốc trị mụn, mắt tôi sưng và tôi bắt đầu khó thở.`
- Exact-count sign query: `Liệt kê đúng 4 dấu hiệu routine trị mụn đang gây kích ứng quá mức.`

No ingestion, database reset, Qdrant/Neo4j cleanup, entity rebuild, or cache flush was performed.

## Why unit/eval passed but live smoke failed

Previous tests covered severe isotretinoin neurologic emergency and formatter-level exact sign list behavior, but did not cover the live wording combination that users typed:

- `mắt tôi sưng` and `môi tôi sưng` use the order `region ... sưng`; the old classifier only matched fixed phrases such as `sưng mặt`, `sưng môi`, `sưng họng`.
- Because the emergency classifier returned `routine`, the severity guard did not replace the LLM answer with an emergency template.
- The fallback presentation template for generic out-of-domain emergency still contained weak wording: `có thể cần được đánh giá y tế khẩn cấp`.
- Exact-count signs were deterministic in the formatter, but the verifier only checked item count when it found at least one markdown list item. A paragraph answer or cache/generation answer with no list could avoid the exact-count issue.
- Cache version remained `v5`; without a contract fingerprint bump, old live answers could still be eligible under the same answer-formatting contract namespace.

## Stage investigation

| Stage | Finding |
|---|---|
| Backend not restarted | Possible operational contributor, but not the root cause. Local reproduction in-process showed the emergency query classified as `routine` before the patch. |
| Cache/fingerprint | Cache could preserve prior bad live answers. `CACHE_ANSWER_VERSION` remains `v5`, but the answer formatting contract was bumped to `answer_formatting_contract_v6`, so the pipeline fingerprint changes without flushing Redis. |
| Guardrail bypass | Not the primary cause. The in-domain path relies on severity classification; the classifier missed anaphylaxis-like wording. |
| Severity template too weak | Confirmed. Generic emergency formatting used `có thể cần...`; patched to immediate emergency action wording. |
| Parser not used | Exact-count parser was used for `dấu hiệu/triệu chứng`, but did not recognize `biểu hiện` as an exact-count unit; patched. |
| Verifier no repair | Confirmed. The verifier missed exact-count failures when no markdown items existed. It now flags item-count mismatch when the count is not exactly preserved. |
| LLM overwrite | Possible live contributor. Final presentation now repairs exact-count signs after cleanup, so generated/cache drift is overridden for that constrained intent. |
| API/frontend/cache | No frontend issue found. `/chat` finalization goes through `finalize_response_node` and `answer_quality_node`; both now share the stronger contract. |

## Fix summary

- Added a reusable emergency wording contract in `src/agent/emergency_contract.py`.
- Strengthened anaphylaxis-like detection for `khó thở` plus swelling/rash around eyes, lips, face, throat, or throat tightness.
- Updated severity guard emergency template selection to use the specific anaphylaxis-like emergency answer.
- Replaced weak generic out-of-domain emergency fallback wording with direct emergency action.
- Added exact-count sign repair in final answer presentation.
- Updated requested-structure parsing to recognize `biểu hiện` for exact item counts.
- Tightened answer verifier exact item-count checking.
- Bumped answer formatting contract to `answer_formatting_contract_v6`; `CACHE_ANSWER_VERSION` remains `v5`.

## Expected live behavior

For anaphylaxis-like topical medication reactions, the first answer sentence must direct immediate emergency action, for example:

`Bạn cần gọi cấp cứu hoặc đến cơ sở cấp cứu ngay...`

For exact-count signs/symptoms requests, the answer must contain exactly the requested number of observable signs/symptoms and must not replace them with causes, habits, or a second long management list.
