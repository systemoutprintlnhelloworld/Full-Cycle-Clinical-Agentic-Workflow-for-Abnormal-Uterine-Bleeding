# 指标数据来源映射表 (v2)

本文档详细说明了 `output/metrics/` 目录下各阶段指标 Excel 文件的数据来源。

## 1. 门诊阶段
### 1.1 门诊循环 (Metric_D1_Loop.xlsx)
记录 Doctor Agent 在门诊阶段与模拟患者的交互轮数。
- **Loop_Count**: 统计 `D1_Outpatient_Loop` Sheet 中，非空的 `第X轮_医生_原始JSON` 列的最大索引值 (e.g. 第3轮有数据 -> 3)。

### 1.2 门诊决策 (Metric_D1_Decision.xlsx)
记录 D1 阶段的最终通过状态及判官打分。
- **Passed**: 基于 `D1_Outpatient_Decision` 的 `状态` 列，包含 "通过" 为 1，否则 0。
- **评分**: 来自 `D1_Outpatient_Decision` (Judge_Parsed) 的所有 `...评分` 列。

## 2. 入院阶段
### 2.1 入院循环 (Metric_D2_Loop.xlsx)
记录入院后的查房交互轮数。
- **Loop_Count**: 同 D1 Loop，统计 `D2_Admission_Loop` Sheet 中的非空轮数列数。

### 2.2 入院决策 (Metric_D2_Decision.xlsx)
记录 D2 阶段的诊断决策状态及评分。
- **Passed**: 基于 `D2_Admission_Decision` 的 `状态` 列。

## 3. 手术阶段
### 3.1 手术决策 (Metric_D3_Decision.xlsx)
记录 D3 阶段的手术方案决策。
- **Passed**: 基于 `D3_Surgery_Decision` 的 `状态` 列。

## 4. 康复阶段
### 4.1 康复计划 (Metric_D4_Rehab.xlsx)
记录 D4 阶段的康复建议及评分。
- **评分**: 同样提取 Judge 打分列。

## 数据文件存放位置
- **源文件**: `D:\研究生\项目\课题7-临床评测\自动测评系统\测评结果\{Center}\{Model}\`
- **输出文件**: `D:\研究生\项目\课题7-临床评测\自动测评系统\output\metrics\`
