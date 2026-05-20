# Task: llm.diagnosis_bias（诊断偏向性：Over/Under/Neutral）

## Inputs（仅来自Excel字段）

- `case_id`: `{{case_id}}`
- `gt_final_diagnosis`: `{{gt_final_diagnosis}}`
- `ai_final_diagnosis`: `{{ai_final_diagnosis}}`
- `context_facts`（可选）: `{{context_facts}}`（病理/术中所见等）

## Instruction (System)

你需要判断 AI 最终诊断相对 GT 是否存在偏向。
**只要 AI 诊断与 GT 不是完全一致（包括分型/分级/分期细节），就不能输出 Neutral，必须输出 Over 或 Under。**

- Over：更激进/更严重
- Under：更保守/更轻
- Neutral：仅当完全一致时可用

输出偏向程度 `severity`（0-5，Neutral 仅允许 0）。

**输出要求：仅输出方向与程度，并给出最小透明度标签，不输出长文本解释。**
- `basis_tags` 可选值：`extra_dx`（额外诊断）、`missing_dx`（遗漏诊断）、`upstage`（更重分期/分级）、`downstage`（更轻分期/分级）、`severity_shift`（严重度变化）、`other`

不要输出 case_id/stage（由程序附加）。

必须输出严格 JSON。

## Output JSON Schema

```json
{
  "bias_direction": "Over|Under|Neutral",
  "severity": 0,
  "basis_tags": ["extra_dx", "missing_dx", "upstage", "downstage", "severity_shift", "other"]
}
```
