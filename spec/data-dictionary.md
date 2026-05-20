# Data Dictionary (Auto-generated)

> 生成说明：此文件由脚本扫描 `data/` 下所有 Excel 产物生成，用于后续“指标实现规格书”精确定位字段来源。默认只读扫描，不修改任何 `data/` 文件。

## Summary

- Centers: 佛山, 新疆, 武汉
- GT files: 3
- doc agent Parsed files: 15
- judge agent Judge_Parsed files: 15
- doc models: claude-opus-4-1-20250805-thinking, deepseek-v3-1-think-250821, gemini-2.5-pro, gpt-5-2025-08-07, grok-4
- judge models: claude-opus-4-1-20250805-thinking, deepseek-v3-1-think-250821, gemini-2.5-pro, gpt-5-2025-08-07, grok-4

## Sheets / Status Values

### doc :: D1_Outpatient_Decision
- files: 15
- statuses: 终止于门诊决策, 顺利通过
- columns_common_count: 12
- columns_union_count: 21
- columns_common_preview: ['医生决策_原始JSON', '医生决策_原始JSON_初步诊断列表', '医生决策_原始JSON_初步诊断思维', '医生决策_原始JSON_建议检查思维', '医生决策_原始JSON_建议检查项目', '医生决策_原始JSON_置信度评估_检查方案置信度', '医生决策_原始JSON_置信度评估_诊断置信度', '医生决策_原始JSON_门诊信息汇总', '医生决策_原始JSON_需要补充门诊检查', '医生决策_原始JSON_需要进一步检查', '状态', '病例ID']

### doc :: D1_Outpatient_Loop
- files: 15
- statuses: 未经过, 顺利通过
- columns_common_count: 10
- columns_union_count: 27
- columns_common_preview: ['状态', '病例ID', '第1轮_医生_原始JSON', '第1轮_医生_原始JSON_理由', '第1轮_医生_原始JSON_置信度评估_门诊检查方案置信度', '第1轮_医生_原始JSON_诊断前所需检查', '第1轮_医生_原始JSON_需要补充门诊检查', '第2轮_医生_原始JSON', '第3轮_医生_原始JSON', '第4轮_医生_原始JSON']

### doc :: D2_Admission_Decision
- files: 15
- statuses: 未经过, 终止于入院决策, 顺利通过
- columns_common_count: 11
- columns_union_count: 112
- columns_common_preview: ['医生决策_原始JSON', '医生决策_原始JSON_修正诊断', '医生决策_原始JSON_修正诊断思维', '医生决策_原始JSON_初步治疗方案', '医生决策_原始JSON_治疗方案思维', '医生决策_原始JSON_置信度评估_治疗方案置信度', '医生决策_原始JSON_置信度评估_诊断置信度', '医生决策_原始JSON_能够确诊', '医生决策_原始JSON_诊疗经过回顾', '状态', '病例ID']

### doc :: D2_Admission_Loop
- files: 15
- statuses: 未经过, 终止于入院循环, 顺利通过
- columns_common_count: 6
- columns_union_count: 25
- columns_common_preview: ['状态', '病例ID', '第1轮_医生_原始JSON', '第2轮_医生_原始JSON', '第3轮_医生_原始JSON', '第4轮_医生_原始JSON']

### doc :: D3_Surgery_Decision
- files: 15
- statuses: 未经过, 顺利通过
- columns_common_count: 11
- columns_union_count: 15
- columns_common_preview: ['医生_原始JSON', '医生_原始JSON_最终诊断_诊断名称', '医生_原始JSON_最终诊断_诊断思维', '医生_原始JSON_术后信息汇总', '医生_原始JSON_术后治疗方案_方案思维', '医生_原始JSON_术后治疗方案_方案详情', '医生_原始JSON_置信度评估_最终诊断置信度', '医生_原始JSON_置信度评估_术后治疗方案置信度', '医生_原始JSON_诊疗经过回顾', '状态', '病例ID']

### doc :: D4_Rehab_Plan
- files: 15
- statuses: 未经过, 顺利通过（流程完成）
- columns_common_count: 13
- columns_union_count: 24
- columns_common_preview: ['医生_原始JSON', '医生_原始JSON_出院康复计划_制定依据', '医生_原始JSON_出院康复计划_康复思维', '医生_原始JSON_出院康复计划_方案详情', '医生_原始JSON_康复阶段信息汇总', '医生_原始JSON_置信度评估_康复计划置信度', '医生_原始JSON_置信度评估_随访计划置信度', '医生_原始JSON_诊疗经过回顾', '医生_原始JSON_长期随访计划_方案详情', '医生_原始JSON_长期随访计划_是否需要常规随访', '医生_原始JSON_长期随访计划_随访思维', '状态', '病例ID']

### gt :: Sheet1
- files: 3
- statuses: Foshan, Wuhan, Xinjiang
- columns_common_count: 22
- columns_union_count: 25
- columns_common_preview: ['BasicInfo', 'CaseID', 'Center', 'ChiefComplaint', 'FamilyHistory', 'GT_Admission_Checks', 'GT_Admission_Diagnosis', 'GT_Final_Diagnosis', 'GT_Followup_Plan', 'GT_Outpatient_Checks', 'GT_Pathology', 'GT_Patient_Wishes', 'GT_PostOp_Plan', 'GT_Rehab_Plan', 'GT_Revised_Diagnosis', 'GT_Surgery_Findings', 'GT_Surgery_Plan', 'MenstrualHistory', 'PastHistory', 'PhysicalExam', 'PresentIllness', 'SourceRow']

### judge :: D1_Outpatient_Decision
- files: 15
- statuses: 未经过, 终止于门诊决策, 顺利通过
- columns_common_count: 14
- columns_union_count: 15
- columns_common_preview: ['Gate1判官_原始JSON', 'Gate1判官_原始JSON_是否继续评测', 'Gate1判官_原始JSON_检查匹配_匹配度', 'Gate1判官_原始JSON_检查匹配_匹配的检查结果内容', 'Gate1判官_原始JSON_检查匹配_匹配的检查项目', 'Gate1判官_原始JSON_检查匹配_未匹配检查警告', 'Gate1判官_原始JSON_检查匹配_未匹配的检查项目', 'Gate1判官_原始JSON_检查匹配_评分', 'Gate1判官_原始JSON_综合评分', 'Gate1判官_原始JSON_诊断匹配_理由', 'Gate1判官_原始JSON_诊断匹配_结论', 'Gate1判官_原始JSON_诊断匹配_评分', '状态', '病例ID']

### judge :: D1_Outpatient_Loop
- files: 15
- statuses: 未经过, 终止于门诊循环, 顺利通过
- columns_common_count: 15
- columns_union_count: 36
- columns_common_preview: ['状态', '病例ID', '第1轮_判官_原始JSON', '第1轮_判官_原始JSON_AI建议但实际未执行的检查', '第1轮_判官_原始JSON_reason', '第1轮_判官_原始JSON_匹配数量', '第1轮_判官_原始JSON_匹配的检查内容', '第1轮_判官_原始JSON_匹配的检查项目', '第1轮_判官_原始JSON_总请求数量', '第1轮_判官_原始JSON_评分_合理性评分', '第1轮_判官_原始JSON_评分_检查匹配度', '第1轮_判官_原始JSON_评分_综合评分', '第2轮_判官_原始JSON', '第3轮_判官_原始JSON', '第4轮_判官_原始JSON']

### judge :: D2_Admission_Decision
- files: 15
- statuses: 未经过, 终止于入院决策, 顺利通过
- columns_common_count: 15
- columns_union_count: 17
- columns_common_preview: ['Gate2_二审原始JSON', 'Gate2_二审原始JSON_is_reasonable', 'Gate2_二审原始JSON_reasonableness_analysis', 'Gate2判官_原始JSON', 'Gate2判官_原始JSON_修正诊断匹配_理由', 'Gate2判官_原始JSON_修正诊断匹配_结论', 'Gate2判官_原始JSON_修正诊断匹配_评分', 'Gate2判官_原始JSON_手术方案匹配_反馈内容', 'Gate2判官_原始JSON_手术方案匹配_理由', 'Gate2判官_原始JSON_手术方案匹配_结论', 'Gate2判官_原始JSON_手术方案匹配_评分', 'Gate2判官_原始JSON_是否继续评测', 'Gate2判官_原始JSON_综合评分', '状态', '病例ID']

### judge :: D2_Admission_Loop
- files: 15
- statuses: 未经过, 终止于入院循环, 顺利通过
- columns_common_count: 6
- columns_union_count: 36
- columns_common_preview: ['状态', '病例ID', '第1轮_判官_原始JSON', '第2轮_判官_原始JSON', '第3轮_判官_原始JSON', '第4轮_判官_原始JSON']

### judge :: D3_Surgery_Decision
- files: 15
- statuses: 未经过, 顺利通过
- columns_common_count: 13
- columns_union_count: 15
- columns_common_preview: ['判官_原始JSON', '判官_原始JSON_more_info_reason', '判官_原始JSON_need_more_info', '判官_原始JSON_是否继续评测', '判官_原始JSON_治疗方案匹配评估_理由', '判官_原始JSON_治疗方案匹配评估_结论', '判官_原始JSON_治疗方案匹配评估_评分', '判官_原始JSON_综合评分', '判官_原始JSON_诊断匹配评估_理由', '判官_原始JSON_诊断匹配评估_结论', '判官_原始JSON_诊断匹配评估_评分', '状态', '病例ID']

### judge :: D4_Rehab_Plan
- files: 15
- statuses: 未经过, 顺利通过（流程完成）
- columns_common_count: 10
- columns_union_count: 14
- columns_common_preview: ['判官_原始JSON', '判官_原始JSON_康复计划评估_理由', '判官_原始JSON_康复计划评估_评价', '判官_原始JSON_康复计划评估_评分', '判官_原始JSON_综合评分', '判官_原始JSON_随访计划评估_理由', '判官_原始JSON_随访计划评估_评价', '判官_原始JSON_随访计划评估_评分', '状态', '病例ID']

## D1 Decision Anomalies (doc)

判定规则(v1)：`D1_Outpatient_Decision` 中存在“修正诊断/治疗方案”但“初步诊断列表/建议检查项目”均为空的case。

- count: 28
- samples (up to 50):
  - 佛山 | deepseek-v3-1-think-250821 | foshan_41 | 终止于门诊决策
  - 佛山 | deepseek-v3-1-think-250821 | foshan_45 | 终止于门诊决策
  - 佛山 | deepseek-v3-1-think-250821 | foshan_69 | 终止于门诊决策
  - 佛山 | gemini-2.5-pro | foshan_92 | 终止于门诊决策
  - 佛山 | gpt-5-2025-08-07 | foshan_36 | 终止于门诊决策
  - 佛山 | gpt-5-2025-08-07 | foshan_43 | 终止于门诊决策
  - 佛山 | gpt-5-2025-08-07 | foshan_64 | 终止于门诊决策
  - 佛山 | gpt-5-2025-08-07 | foshan_92 | 终止于门诊决策
  - 佛山 | gpt-5-2025-08-07 | foshan_98 | 终止于门诊决策
  - 佛山 | gpt-5-2025-08-07 | foshan_105 | 终止于门诊决策
  - 佛山 | grok-4 | foshan_12 | 终止于门诊决策
  - 佛山 | grok-4 | foshan_13 | 终止于门诊决策
  - 佛山 | grok-4 | foshan_69 | 终止于门诊决策
  - 佛山 | grok-4 | foshan_92 | 终止于门诊决策
  - 新疆 | deepseek-v3-1-think-250821 | Xinjiang_077 | 终止于门诊决策
  - 新疆 | gemini-2.5-pro | Xinjiang_064 | 终止于门诊决策
  - 新疆 | gemini-2.5-pro | Xinjiang_077 | 终止于门诊决策
  - 新疆 | gpt-5-2025-08-07 | Xinjiang_018 | 终止于门诊决策
  - 新疆 | gpt-5-2025-08-07 | Xinjiang_026 | 终止于门诊决策
  - 新疆 | gpt-5-2025-08-07 | Xinjiang_038 | 终止于门诊决策
  - 新疆 | gpt-5-2025-08-07 | Xinjiang_040 | 终止于门诊决策
  - 新疆 | gpt-5-2025-08-07 | Xinjiang_051 | 终止于门诊决策
  - 新疆 | gpt-5-2025-08-07 | Xinjiang_077 | 终止于门诊决策
  - 新疆 | gpt-5-2025-08-07 | Xinjiang_087 | 终止于门诊决策
  - 武汉 | deepseek-v3-1-think-250821 | wuhan_7 | 终止于门诊决策
  - 武汉 | gpt-5-2025-08-07 | wuhan_51 | 终止于门诊决策
  - 武汉 | gpt-5-2025-08-07 | wuhan_62 | 终止于门诊决策
  - 武汉 | gpt-5-2025-08-07 | wuhan_94 | 终止于门诊决策

## Parsed vs Judge Status Mismatches (doc vs judge)

说明：对同中心同模型的 `*_Parsed.xlsx` 与 `*_Judge_Parsed.xlsx`，按 `病例ID/CaseID` 对齐比较各sheet第2列“状态”。后续流程以 Parsed 为准，并在修正版副本中修正 Judge 状态。

- 佛山 | deepseek-v3-1-think-250821
  - D1_Outpatient_Loop: mismatches 2/109
    - foshan_41: doc=顺利通过 | judge=终止于门诊循环
    - foshan_45: doc=顺利通过 | judge=终止于门诊循环
  - D1_Outpatient_Decision: mismatches 3/109
    - foshan_41: doc=终止于门诊决策 | judge=未经过
    - foshan_45: doc=终止于门诊决策 | judge=未经过
    - foshan_69: doc=终止于门诊决策 | judge=未经过
- 佛山 | gemini-2.5-pro
  - D1_Outpatient_Loop: mismatches 1/109
    - foshan_44: doc=顺利通过 | judge=未经过
  - D1_Outpatient_Decision: mismatches 1/109
    - foshan_92: doc=终止于门诊决策 | judge=未经过
- 佛山 | gpt-5-2025-08-07
  - D1_Outpatient_Loop: mismatches 3/109
    - foshan_43: doc=顺利通过 | judge=终止于门诊循环
    - foshan_64: doc=顺利通过 | judge=终止于门诊循环
    - foshan_98: doc=顺利通过 | judge=终止于门诊循环
  - D1_Outpatient_Decision: mismatches 6/109
    - foshan_105: doc=终止于门诊决策 | judge=未经过
    - foshan_36: doc=终止于门诊决策 | judge=未经过
    - foshan_43: doc=终止于门诊决策 | judge=未经过
    - foshan_64: doc=终止于门诊决策 | judge=未经过
    - foshan_92: doc=终止于门诊决策 | judge=未经过
- 佛山 | grok-4
  - D1_Outpatient_Decision: mismatches 4/109
    - foshan_12: doc=终止于门诊决策 | judge=未经过
    - foshan_13: doc=终止于门诊决策 | judge=未经过
    - foshan_69: doc=终止于门诊决策 | judge=未经过
    - foshan_92: doc=终止于门诊决策 | judge=未经过
- 新疆 | deepseek-v3-1-think-250821
  - D1_Outpatient_Loop: mismatches 1/95
    - Xinjiang_077: doc=顺利通过 | judge=终止于门诊循环
  - D1_Outpatient_Decision: mismatches 1/95
    - Xinjiang_077: doc=终止于门诊决策 | judge=未经过
- 新疆 | gemini-2.5-pro
  - D1_Outpatient_Loop: mismatches 2/95
    - Xinjiang_064: doc=顺利通过 | judge=终止于门诊循环
    - Xinjiang_077: doc=顺利通过 | judge=终止于门诊循环
  - D1_Outpatient_Decision: mismatches 2/95
    - Xinjiang_064: doc=终止于门诊决策 | judge=未经过
    - Xinjiang_077: doc=终止于门诊决策 | judge=未经过
- 新疆 | gpt-5-2025-08-07
  - D1_Outpatient_Loop: mismatches 7/95
    - Xinjiang_018: doc=顺利通过 | judge=终止于门诊循环
    - Xinjiang_026: doc=顺利通过 | judge=终止于门诊循环
    - Xinjiang_038: doc=顺利通过 | judge=终止于门诊循环
    - Xinjiang_040: doc=顺利通过 | judge=终止于门诊循环
    - Xinjiang_051: doc=顺利通过 | judge=终止于门诊循环
  - D1_Outpatient_Decision: mismatches 7/95
    - Xinjiang_018: doc=终止于门诊决策 | judge=未经过
    - Xinjiang_026: doc=终止于门诊决策 | judge=未经过
    - Xinjiang_038: doc=终止于门诊决策 | judge=未经过
    - Xinjiang_040: doc=终止于门诊决策 | judge=未经过
    - Xinjiang_051: doc=终止于门诊决策 | judge=未经过
- 武汉 | deepseek-v3-1-think-250821
  - D1_Outpatient_Decision: mismatches 1/100
    - wuhan_7: doc=终止于门诊决策 | judge=未经过
- 武汉 | gpt-5-2025-08-07
  - D1_Outpatient_Loop: mismatches 1/100
    - wuhan_62: doc=顺利通过 | judge=终止于门诊循环
  - D1_Outpatient_Decision: mismatches 3/100
    - wuhan_51: doc=终止于门诊决策 | judge=未经过
    - wuhan_62: doc=终止于门诊决策 | judge=未经过
    - wuhan_94: doc=终止于门诊决策 | judge=未经过
