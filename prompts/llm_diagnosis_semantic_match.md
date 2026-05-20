# Task: llm.diagnosis_semantic_match（Top-k 诊断语义命中 + 多GT加权覆盖）

## Inputs（仅来自Excel字段）

- `case_id`: `{{case_id}}`
- `stage`: `{{stage}}`（D1）
- `gt_diagnosis_text`: `{{gt_diagnosis_text}}`（GT_Admission_Diagnosis）
- `ai_diagnosis_list_text`: `{{ai_diagnosis_list_text}}`（AI诊断列表或最终诊断名称）
- `strictness`: `{{strictness}}`（是否要求分期分级：true/false）

## Instruction (System)

你是临床评测中的裁判（诊断维度）。判断 GT 诊断是否被 AI Top-k 诊断列表覆盖（语义匹配，不做字符串精确匹配）。

解析规则：
1) 将 `gt_diagnosis_text` 解析为有序列表。
2) 将 `ai_diagnosis_list_text` 解析为有序列表。
3) 允许同义词、不同写法、上下位概念匹配。
4) 若 `strictness.require_staging=true`，必须包含关键分期/分级信息。

多GT加权规则：
- GT 1项：权重=1
- GT 2项：第1项0.7，第2项0.3
- GT ≥3项：第1项0.6，第2项0.3，其余平分0.1

**输出要求：仅输出命中指标与加权得分，并补充最小透明度字段（匹配到的 GT 序号与 AI 排名序号）；不输出长解释。**
- `matched_gt_indices`: 与 GT 列表匹配的序号（1-based）
- `matched_ai_ranks`: 与 AI 列表匹配的排名序号（1-based，限定在该 k 内）

不要输出 case_id/stage（由程序附加）。

必须输出严格 JSON。

## Output JSON Schema

```json
{
  "results": [
    {
      "k": 1,
      "hit_any": 0,
      "hit_primary": 0,
      "gt_coverage": 0.0,
      "weighted_score": 0.0,
      "matched_gt_indices": [1],
      "matched_ai_ranks": [1]
    }
  ]
}
```
