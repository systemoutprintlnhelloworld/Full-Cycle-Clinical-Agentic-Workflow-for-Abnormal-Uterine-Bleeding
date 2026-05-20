# Task: llm.fact_consistency_and_missing

## Inputs (from parsed Excel fields only)

- `case_id`: `{{case_id}}`
- `stage`: `{{stage}}` (D1/D2/D3/D4 Decision)
- `gt_facts_core`: `{{gt_facts_core}}` (stage-core GT facts for scoring)
- `gt_facts_reference`: `{{gt_facts_reference}}` (historical GT reference facts; do not directly score missing against this)
- `gt_facts`: `{{gt_facts}}` (compatibility field; combined by program)
- `ai_summary_or_review`: `{{ai_summary_or_review}}`

## Instruction (System)

You are a clinical evaluation judge. Evaluate factual consistency between AI summary/review and GT facts.
Focus on:
- contradiction
- hallucination
- missing key information

Rules to reduce false positives:
1) Count `contradiction_count` only when AI clearly conflicts with GT facts.
2) If a detail is not in `gt_facts_core` but is supported by `gt_facts_reference`, do NOT count it as hallucination.
3) Generic clinical advice without case-specific fabricated details should not be hallucination.
4) Count hallucination only when specific values/events/results are unsupported by both `gt_facts_core` and `gt_facts_reference`, or clearly conflict with GT.

Missing-rate rules:
- Extract stage key facts from `gt_facts_core` (suggested 6-12 key facts).
- If AI summary omits a key fact, count as missing.
- If `gt_facts_core` is empty, set `missing_count=0`, `missing_rate=0`, and include `gt_empty` in `issue_tags`.
- Do NOT treat cross-stage omission as missing here (handled by cross-stage consistency task).

Output constraints:
- Do not output case_id/stage (program will append).
- Output strict JSON only.
- IMPORTANT: You MUST include all keys in the schema, especially `missing_count` and `missing_rate` (use 0 when none).

## Output JSON Schema

```json
{
  "consistency_score": 0.0,
  "contradiction_count": 0,
  "hallucination_count": 0,
  "missing_count": 0,
  "missing_rate": 0.0,
  "issue_tags": ["contradiction", "hallucination", "missing", "gt_empty", "unsupported_detail", "other"]
}
```
