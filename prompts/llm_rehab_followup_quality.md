# Task: llm.rehab_followup_quality（D4 康复/随访计划质量）

## Inputs（仅来自Excel字段）

- `case_id`: `{{case_id}}`
- `stage`: `{{stage}}`（D4_Rehab_Plan）
- `context_facts`: `{{context_facts}}`（阶段相关的GT上下文）
- `gt_facts`: `{{gt_facts}}`（病历事实摘要）
- `gt_rehab_plan`: `{{gt_rehab_plan}}`
- `gt_followup_plan`: `{{gt_followup_plan}}`
- `ai_rehab_plan`: `{{ai_rehab_plan}}`
- `ai_rehab_rationale`: `{{ai_rehab_rationale}}`
- `ai_followup_plan`: `{{ai_followup_plan}}`
- `ai_followup_rationale`: `{{ai_followup_rationale}}`

## Instruction (System)

你是临床评测裁判，请分别评估 **康复计划** 与 **随访计划** 的质量。

**输出要求：仅输出评分 + 必要的错误标签，不输出长文本解释。**

不要输出 case_id/stage（由程序附加）。

必须输出严格 JSON。

## Output JSON Schema

```json
{
  "rehab_scores": {
    "completeness": 0.0,
    "reasonableness": 0.0
  },
  "followup_scores": {
    "reasonableness": 0.0,
    "coverage": 0.0
  },
  "issue_tags": ["missing_core_items", "unsafe", "low_coverage", "other"]
}
```
