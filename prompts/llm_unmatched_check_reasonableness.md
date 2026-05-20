# Task: llm.unmatched_check_reasonableness（未匹配检查项合理性/冗余度标注｜全局视角）

## Inputs（仅来自Excel字段）

- `case_id`: `{{case_id}}`
- `stage`: `{{stage}}`（D1_Outpatient / D2_Admission）
- `gt_facts`: `{{gt_facts}}`
- `gt_checks_text`: `{{gt_checks_text}}`
- `ai_requested_checks_all`: `{{ai_requested_checks_all}}`
- `judge_matched_checks_all`: `{{judge_matched_checks_all}}`
- `judge_unmatched_checks_all`: `{{judge_unmatched_checks_all}}`
- `unmatched_checks_to_judge`: `{{unmatched_checks_to_judge}}`
- `prior_matched_checks`: `{{prior_matched_checks}}`
- `ai_rationale`: `{{ai_rationale}}`

## Instruction (System)

你需要对 `unmatched_checks_to_judge` 中每个“未匹配检查项”逐条标注：
- 是否有临床意义（is_clinically_meaningful）
- 是否冗余（is_redundant）

要求：
1) `items` 数量必须与 `unmatched_checks_to_judge` 完全一致。
2) `check_item` 必须与输入原文完全一致（不得改写/合并/拆分）。
3) 允许两者同时为 0（信息不足）。

**输出要求：仅输出标记与计数，不输出长文本解释。**

不要输出 case_id/stage（由程序附加）。

必须输出严格 JSON。

## Output JSON Schema

```json
{
  "items": [
    {
      "check_item": "<string>",
      "is_clinically_meaningful": 0,
      "is_redundant": 0
    }
  ],
  "meaningful_count": 0,
  "redundant_count": 0
}
```
