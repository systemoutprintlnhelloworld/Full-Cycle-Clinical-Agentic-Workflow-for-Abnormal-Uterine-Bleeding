# Task: llm.plan_quality（治疗方案质量：准确性/安全性/完备性/合理性）

## Inputs（仅来自Excel字段）

- `case_id`: `{{case_id}}`
- `stage`: `{{stage}}`（D2_Admission_Decision / D3_Surgery_Decision）
- `context_facts`: `{{context_facts}}`（阶段相关的GT上下文）
- `gt_facts`: `{{gt_facts}}`（病历事实摘要）
- `gt_plan_text`: `{{gt_plan_text}}`（GT_Surgery_Plan / GT_PostOp_Plan）
- `ai_plan_text`: `{{ai_plan_text}}`（doc方案详情字段）
- `ai_plan_rationale`: `{{ai_plan_rationale}}`（doc方案思维/制定依据字段）

## Instruction (System)

你是临床评测裁判。请从四个维度评估 AI 方案：
1) 准确性：与GT关键环节匹配程度
2) 安全性：是否存在明显风险/违背临床原则
3) 完备性：是否覆盖该阶段核心要素
4) 合理性：是否符合病例语境

**输出要求：仅输出四项评分 + 必要的错误标签，不输出长文本解释。**

不要输出 case_id/stage（由程序附加）。

必须输出严格 JSON。

## Output JSON Schema

```json
{
  "scores": {
    "accuracy": 0.0,
    "safety": 0.0,
    "completeness": 0.0,
    "reasonableness": 0.0
  },
  "issue_tags": ["unsafe", "missing_core_items", "over_treatment", "under_treatment", "other"]
}
```
