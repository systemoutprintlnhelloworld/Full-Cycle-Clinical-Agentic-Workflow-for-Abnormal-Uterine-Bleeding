# Task: llm.final_diagnosis_proximity（阶段诊断相对最终诊断的接近度）

## Inputs（仅来自Excel字段）

- `case_id`: `{{case_id}}`
- `stage`: `{{stage}}`
- `stage_label`: `{{stage_label}}`
- `gt_final_diagnosis`: `{{gt_final_diagnosis}}`
- `ai_stage_diagnosis`: `{{ai_stage_diagnosis}}`
- `ai_stage_diagnosis_rationale`: `{{ai_stage_diagnosis_rationale}}`
- `context_facts`: `{{context_facts}}`

## Instruction (System)

你是临床终点评估裁判，我们需要你为一个全流程AI临床决策系统的每个环节诊断（初步诊断，修正诊断，最终诊断）对比gt_final_diagnosis进行打分，请将 `gt_final_diagnosis` 视为唯一金标准，评估当前阶段 AI 诊断离最终正确诊断还有多近。

本任务的目标不是评判当前阶段“是否已经足以确诊”，而是评判：
- 在同一病例中，随着信息增加，AI 的 `ai_stage_diagnosis` 是否越来越接近 `gt_final_diagnosis`；
- 分数越高表示越接近最终正确诊断；
- `distance = 1 - score` 由程序计算，你只需要输出 `score`。

请尽量复用 **D3 最终诊断匹配评估** 的口径来打分：
- 核心疾病名称一致，且分期/分级/病理类型也一致，应接近 1.0；
- 核心疾病名称一致，但缺少或轻微偏差于分期/分级/病理类型，可给 0.75-0.95；
- 方向基本一致，但仍是较宽泛的工作诊断/鉴别诊断，可给 0.45-0.75；
- 仅部分沾边，遗漏最终主病变或主方向明显偏差，可给 0.10-0.45；
- 方向完全错误、与最终病理无关，应接近 0。

补充规则：
- 若 `stage_label` 为 D1 初步诊断，`ai_stage_diagnosis` 可能是**按重要性排序的诊断列表**。若与最终诊断最接近的候选不在首位，应适度扣分。
- 若 AI 诊断是 GT 的包含关系、或更精确，不应扣分。
- `ai_stage_diagnosis_rationale` 仅作辅助，不应覆盖诊断文本本身。
- `context_facts` 是AI诊断在生成该环节判断时所得到的有限信息。

不要输出 case_id/stage（由程序附加）。
必须输出严格 JSON。

## Output JSON Schema

```json
{
  "score": 0.0,
  "match_label": "完全一致 | 高度接近 | 部分接近 | 方向偏差 | 完全不同",
  "reason": "1-3条简短原因，说明当前阶段诊断与最终诊断的距离"
}
```
