# Task: llm.loop_info_yield（Loop 信息增益/阳性产出判定）

## Inputs（仅来自Excel字段）

- `case_id`: `{{case_id}}`
- `stage`: `{{stage}}`（D1_Outpatient_Loop / D2_Admission_Loop）
- `round_index`: `{{round_index}}`（1/2/3...）
- `matched_check_items`: `{{matched_check_items}}`（若有：判官匹配的检查项目）
- `matched_check_content`: `{{matched_check_content}}`（判官匹配的检查结果内容文本）
- `ai_rationale`: `{{ai_rationale}}`（本轮AI理由）

## Instruction (System)

你需要判断该轮检查是否产生“有效信息增益（yield）”。

定义（v1）：
- `yield_flag=1`：该轮检查结果提供了关键阳性发现，或提供了足够强的阴性证据从而有效排除关键诊断、推动决策。
- `yield_flag=0`：结果基本无信息（重复、与当前问题无关、或不足以影响决策）。

输出需同时给出 `yield_type`：
- `positive`
- `negative_but_informative`
- `no_yield`

不要输出 case_id/stage（由程序附加）。

必须输出严格 JSON。

## Output JSON Schema

```json
{
  "round_index": 1,
  "yield_flag": 0,
  "yield_type": "positive|negative_but_informative|no_yield",
  "evidence": "<string>",
  "confidence": 0.0
}
```
