# Task: llm.memory_retention

## Inputs (from parsed Excel fields only)

- `case_id`: `{{case_id}}`
- `stage`: `{{stage}}` (D2/D3/D4 Decision)
- `prior_stage_summary`: `{{prior_stage_summary}}`
- `current_stage_review`: `{{current_stage_review}}`
- `gt_facts`: `{{gt_facts}}` (for identifying what is key; not direct contradiction scoring)

## Instruction (System)

Evaluate whether key prior information is retained and used in the current stage reasoning.

Definitions:
- Key info: only items that materially affect diagnosis/staging/treatment decisions.
- `retention_rate`: key prior info explicitly retained (same meaning or equivalent expression).
- `utilization_rate`: retained key info actually used in reasoning/decision (causal/justification use), not mere listing.

Tag policy:
- `missing_prior_info`: key prior item not carried forward and not legitimately replaced by stronger new evidence.
- `unused_key_info`: key prior item is mentioned but not used in decision logic.
- `other`: only if needed.

Constraints:
- Evaluate primarily from `prior_stage_summary` and `current_stage_review`.
- Use `gt_facts` only to identify what is key.
- Do not output case_id/stage.
- Output strict JSON only.

## Output JSON Schema

```json
{
  "retention_rate": 0.0,
  "utilization_rate": 0.0,
  "issue_tags": ["missing_prior_info", "unused_key_info", "other"]
}
```
