# Generation And Presentation Audit

Artifacts:

- `artifacts/audit13/baseline_eval.json`
- `artifacts/audit13/after_eval.json`
- `artifacts/audit13/trace_comparison_product_after.json`

## Findings

| Symptom | First failing stage | Downstream effect | Fix |
|---|---|---|---|
| Product comparison answer omitted a queried entity | K/P | Model/finalizer had incomplete or collapsed comparison context | Preserve all primary entity cards; ensure comparison formatting is detected before product composition formatting. |
| Retinoid shared-class question answered with wrong negative polarity | M/P | Live Flash-Lite generation said the named retinoids were not in the same group despite retrieved class evidence | Add deterministic class-check repair for multi-retinoid shared-class questions; keep route/indication distinction. |
| Raw technical source label appeared | Q | UI/debug metadata could show DOI-like filename or section title | Add safe source display mapping and prefer entity-friendly labels where appropriate. |
| Corrected pregnancy context retained warning | D/G | Later turns could keep stale safety intent | Strip negated pregnancy context before intent inference. |
| Typo/no-diacritic entity lookup failed | D | Retrieval missed product/ingredient cards | Add taxonomy aliases for common typo/no-diacritic forms. |

## Presentation Contract

- Comparison questions are recognized by accented and unaccented Vietnamese markers.
- Product comparison presentation keeps all primary entities present.
- Multi-retinoid class-check presentation preserves the shared retinoid class while distinguishing topical vs oral route and clinical context.
- Source display metadata hides raw technical filenames in user-facing labels while preserving raw IDs in backend trace/debug metadata.
- `CACHE_ANSWER_VERSION` remains `v5`.

## Provider Observation

Provider smoke observations:

- Gemini 3.5 primary returned retry exhaustion during live smoke, then model fallback to Gemini 3.1 Flash-Lite succeeded.
- Gemini 3.1 Flash-Lite direct smoke for all 11 required live queries passed.
- Ollama `qwen3:8b` succeeded on a short identity query and timed out on a longer requested-count query; this is tracked as a local provider/runtime limitation, not a retrieval or presentation regression.
