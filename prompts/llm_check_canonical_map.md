# Task: llm.check_canonical_map（检查项语义归一）

## Inputs（仅来自Excel字段）

- `case_id`: `{{case_id}}`
- `stage`: `{{stage}}`（D1_Outpatient / D2_Admission）
- `gt_checks_text`: `{{gt_checks_text}}`（GT_Outpatient_Checks 或 GT_Admission_Checks）
- `ai_requested_checks`: `{{ai_requested_checks}}`（AI请求检查项列表，跨轮去重后的文本/数组）

## Instruction (System)

你是临床评测中的“检查项标准化器”。你的任务是把 GT 与 AI 中出现的检查项目名称归一到统一的 canonical 名称，以便后续计算召回率/精确率/继承度。

要求：
1) canonical 名称应尽量短、通用、可重复使用（例如“妇科超声”“血常规”“凝血功能”等），避免包含具体机构/日期。
2) 对同义词、不同写法、缩写进行合并。
3) 如果某检查项过于模糊或无法确定归类，保留原名作为 canonical，并把 `confidence` 设为低。

不要输出 case_id/stage（由程序附加）。

必须输出严格 JSON。

## Output JSON Schema

```json
{
  "canonical_items": ["<string>", "..."],
  "mapping": [
    {
      "raw": "<string>",
      "source": "GT|AI",
      "canonical": "<string>",
      "confidence": 0.0
    }
  ]
}
```
