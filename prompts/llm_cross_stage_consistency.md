# Task: llm.cross_stage_consistency

## Inputs (from parsed Excel fields only)

- `case_id`: `{{case_id}}`
- `stage`: `{{stage}}` (D1-D4 Decision)
- `multi_stage_summaries`: `{{multi_stage_summaries}}`
- `gt_facts`: `{{gt_facts}}`

## Instruction (System)

Detect cross-stage inconsistency and contradiction across D1-D4 outputs.

Rules to reduce false positives:
1) Mark `stage_conflict` only for clear conflict on the same event/check/date/result.
2) Granularity differences (coarse vs specific) are not conflict by themselves.
3) Minor numeric drift without decision impact should not be scored as 0.
4) New information that is clinically explainable by GT should prefer `fact_shift` instead of hard conflict.

Requirements:
- Must output findings for all 4 stages: D1, D2, D3, D4.
- For each stage: output `score` and `issue_tags`.
- If no issue: `issue_tags` can be `[]` or `["none"]`.
- Do not output case_id/stage.
- Output strict JSON only.

## Output JSON Schema

```json
{
  "stage_findings": [
    {
      "stage": "D1",
      "score": 0.0,
      "issue_tags": ["stage_conflict", "fact_shift", "other"]
    },
    {
      "stage": "D2",
      "score": 0.0,
      "issue_tags": ["stage_conflict", "fact_shift", "other"]
    },
    {
      "stage": "D3",
      "score": 0.0,
      "issue_tags": ["stage_conflict", "fact_shift", "other"]
    },
    {
      "stage": "D4",
      "score": 0.0,
      "issue_tags": ["stage_conflict", "fact_shift", "other"]
    }
  ]
}
```
