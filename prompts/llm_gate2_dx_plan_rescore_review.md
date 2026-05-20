# Task: llm.gate2_dx_plan_rescore_review（D2 Gate2 二审重评分）

## Inputs（仅来自Excel字段）

- `gt_revised_diagnosis`: `{{gt_revised_diagnosis}}`
- `gt_admission_diagnosis`: `{{gt_admission_diagnosis}}`
- `gt_final_diagnosis`: `{{gt_final_diagnosis}}`
- `gt_surgery_plan`: `{{gt_surgery_plan}}`
- `gt_patient_wishes`: `{{gt_patient_wishes}}`
- `ai_revised_diagnosis`: `{{ai_revised_diagnosis}}`
- `ai_treatment_plan`: `{{ai_treatment_plan}}`
- `ai_diagnosis_rationale`: `{{ai_diagnosis_rationale}}`
- `ai_plan_rationale`: `{{ai_plan_rationale}}`
- `full_context_facts`: `{{full_context_facts}}`

## Instruction (System)

你是妇科医疗质量控制专家。请对 D2 决策的“修正诊断匹配”进行**二审重评分**。

二审目标：
- 在更充分上下文（`full_context_facts`）基础上给出**明确分数**与**是否继续评测**判断。
- 只要方向正确或部分匹配即可继续评测；不要求分级/分型完全一致。

评分要求：
- 仅输出 `diag_score`（0-1 连续分数）。
- 治疗方案评分在一审已给出，二审不再评分。

不要输出 case_id/stage（由程序附加）。
必须输出严格 JSON。

## Output JSON Schema

```json
{
  "diag_score": 0.0,
  "should_continue": true,
  "reason": "1-3条简短原因"
}
```
