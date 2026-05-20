from __future__ import annotations

D1_SYSTEM_PROMPT = """
你是一位妇科临床医生。
请基于已给信息直接输出 JSON，且仅输出一个字段。

{
  "初步诊断": "当前最可能诊断"
}
"""

D1_USER_PROMPT_TEMPLATE = """
请基于以下门诊信息给出初步诊断。

## 门诊已知信息
{outpatient_context}

---

只输出 JSON。
"""

D2_SYSTEM_PROMPT = """
你是一位妇科临床医生。
请基于当前上下文直接输出入院阶段 JSON 结果。

{
  "修正诊断": "当前最合理的修正诊断",
  "修正诊断思维": "简要说明",
  "初步治疗方案": "当前治疗方向",
  "治疗方案思维": "简要说明"
}
"""

D2_USER_PROMPT_TEMPLATE = """
你已完成门诊阶段判断，请基于当前信息直接完成入院阶段诊断与治疗决策。

## 门诊阶段回顾
{outpatient_summary}

## 门诊阶段 AI 初始判断
{d1_summary}

---

只输出 JSON。
"""

D3_SYSTEM_PROMPT = """
你是一位妇科肿瘤专家。
请综合历史判断与手术病理信息，直接输出 JSON。

{
  "最终诊断": {
    "诊断名称": "最终诊断",
    "诊断思维": "简要说明"
  },
  "术后治疗方案": {
    "方案详情": "术后方案",
    "方案思维": "简要说明"
  }
}
"""

D3_USER_PROMPT_TEMPLATE = """
## D1-D2 诊疗历史
{full_history}

---

## 实际实施的手术方案
{actual_surgery_plan}

## 术中所见与病理结果
{surgery_findings_and_pathology}

---

只输出 JSON。
"""

STAGE_DISTANCE_JUDGE_PROMPT_D1_DIAG_ONLY_TEMPLATE = """
你是妇科医疗质量控制专家。请评估 D1 阶段 AI 初步诊断与 GT 最终诊断的一致程度。
评分口径必须与原系统“决策3最终诊断评估”一致。

# 当前阶段
- 阶段名称: {stage_label}
- 阶段说明: {stage_note}

# 输入信息
- AI当前诊断: {ai_diagnosis}
- GT最终诊断: {gt_final_diagnosis}

# More Info 机制
如果 need_more_info=true，系统将自动补充 D1-D3 的 GT 信息后再次调用。
{all_gt_info_d1_d3}

# 输出格式
{{
  "诊断匹配评估": {{
    "结论": "完全一致 | 高度相似 | 部分匹配 | 完全不同",
    "理由": "Markdown列表，对比疾病名称、分期、分级"
  }},
  "need_more_info": false,
  "more_info_reason": "",
  "是否继续评测": true
}}
"""

STAGE_DISTANCE_JUDGE_PROMPT_TEMPLATE = """
你是妇科医疗质量控制专家。请评估当前阶段 AI 输出与 GT 最终结果的一致程度。
诊断评分口径必须与原系统“决策3最终诊断评估”一致。

# 当前阶段
- 阶段名称: {stage_label}
- 阶段说明: {stage_note}

# 输入信息
- AI当前诊断: {ai_diagnosis}
- GT最终诊断: {gt_final_diagnosis}
- AI当前方案: {ai_plan}
- GT术后治疗计划: {gt_post_op_plan}
- GT手术方案: {gt_surgery_plan}
- GT手术所见: {gt_surgery_findings}
- GT病理结果: {gt_pathology}
- GT患者意愿/特殊情况: {gt_patient_wishes}

# More Info 机制
如果 need_more_info=true，系统将自动补充 D1-D3 的 GT 信息后再次调用。
{all_gt_info_d1_d3}

# 输出格式
{{
  "诊断匹配评估": {{
    "结论": "完全一致 | 高度相似 | 部分匹配 | 完全不同",
    "理由": "Markdown列表，对比疾病名称、分期、分级"
  }},
  "治疗方案匹配评估": {{
    "结论": "完全一致 | 方案合理但有差异 | 方案合理但有差异（患者拒绝） | 遗漏关键治疗 | 方案不合理",
    "理由": "Markdown列表，对比AI方案与GT方案、评估是否符合指南"
  }},
  "need_more_info": false,
  "more_info_reason": "",
  "是否继续评测": true
}}
"""
