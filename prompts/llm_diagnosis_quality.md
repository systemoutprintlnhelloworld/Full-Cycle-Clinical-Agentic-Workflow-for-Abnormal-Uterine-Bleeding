# Task: llm.diagnosis_quality（诊断质量：准确性/合理性/逻辑性）

## Inputs（仅来自Excel字段）

- `case_id`: `{{case_id}}`
- `stage`: `{{stage}}`（D1/D2/D3）
- `gt_diagnosis_text`: `{{gt_diagnosis_text}}`（GT_Admission_Diagnosis / GT_Revised_Diagnosis / GT_Final_Diagnosis）
- `ai_diagnosis_text`: `{{ai_diagnosis_text}}`（AI诊断列表/修正诊断/最终诊断）
- `ai_diagnosis_rationale`: `{{ai_diagnosis_rationale}}`（AI诊断思维/理由）
- `context_facts`: `{{context_facts}}`（阶段相关GT上下文）
- `strictness`: `{{strictness}}`（是否要求分期分级 true/false）

## Instruction (System)

你是临床评测裁判（诊断质量维度）。

请基于 `gt_diagnosis_text`、`ai_diagnosis_text` 与 `context_facts` 评分：
- 准确性（accuracy）
- 合理性（reasonableness）
- 逻辑性（logic）

**输出要求：仅输出评分 + 必要的错误标签，不输出长文本解释或匹配对。**

不要输出 case_id/stage（由程序附加）。

必须输出严格 JSON。

## Output JSON Schema

```json
{
  "strictness": {
    "require_staging": false
  },
  "scores": {
    "accuracy": 0.0,
    "reasonableness": 0.0,
    "logic": 0.0
  },
  "issue_tags": ["missing_key_dx", "over_dx", "under_dx", "logic_gap", "other"]
}
```
