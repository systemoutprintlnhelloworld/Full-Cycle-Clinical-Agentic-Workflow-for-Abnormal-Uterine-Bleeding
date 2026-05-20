# 指标评测施行方案（LLM 优先）

本文件给出可执行的端到端施行方案，遵守：LLM 指标输入尽量只来自现有 Excel 抽取列；默认不生成新 Excel；状态修正使用副本策略。

## 0. 运行前准备

1) 选择 `run_id`：`YYYY-MM-DD_HH-mm-ss_<tag>`  
2) 确认本次范围：center 列表、doc_model/judge_model 列表、是否全量 case 还是抽样  
3) 产物目录：\n
   - `work/<run_id>/`（缓存/审计/修正版副本）\n
   - `outputs/<run_id>/`（指标结果）\n

## 1. 数据索引与字典（只读）

1) 运行 `src/tools/generate_data_dictionary.py` 生成：`spec/data-dictionary.md`（已生成）。\n
2) 读取 `data/` 中所有 `standardized_*.xlsx`、`*_Parsed.xlsx`、`*_Judge_Parsed.xlsx`，建立索引表：\n
   - `case_id, center, doc_model, judge_model`\n
   - 每个 stage 的状态与关键字段缺失率\n

## 2. 状态审计与精细化（副本策略）

目标：建立 `flow_status` 并修正 judge 状态到与 Parsed 一致，同时增强“终止子环节”精度与颜色高亮。\n

1) 以 doc Parsed 的 `状态` 为真值，构建 `stage_status` 与 `flow_status`（见 `spec/flow-status-definition.md`）。\n
2) 检测 Parsed vs Judge 状态不一致（已在 `spec/data-dictionary.md` 中给出汇总）。\n
3) 生成修正版副本到：`work/<run_id>/fixed_excels/`：\n
   - 修正 `_Judge_Parsed.xlsx` 的 `状态` 列（对齐 Parsed）\n
   - （可选）修正 Parsed 中明显不自洽的状态，并记录规则与证据\n
4) 产出审计：\n
   - `work/<run_id>/status_audit/status_diff.csv`\n
   - `work/<run_id>/status_audit/rules.md`\n
5) 颜色高亮（可选）：在修正版副本中应用条件格式（不影响原始 data）。\n

## 3. 构建 LLM 评测任务（只用 Excel 字段拼装输入）

### 3.1 必做：算法指标所需 LLM 中间量

按 `spec/metric-dependencies.md` 先产出中间量（JSONL）：\n
- `llm.check_canonical_map`\n
- `llm.unmatched_check_reasonableness`\n
- `llm.loop_info_yield`\n
- `llm.diagnosis_semantic_match`\n
- `llm.effective_result_flag`\n

### 3.2 必做：LLM 指标缺口与补评

优先补齐：\n
- 事实一致性/信息丢失（`prompts/llm_fact_consistency_and_missing.md`）\n
- 推理证据链（`prompts/llm_rationale_quality.md`）\n
- 方案安全/完备（`prompts/llm_plan_quality.md`）\n
- 诊断偏向性（`prompts/llm_diagnosis_bias.md`）\n

### 3.3 D1 异常输出（已确认口径）

1) 检测异常 case（见 `spec/data-dictionary.md` 的 D1 anomalies）。\n
2) 将其作为 D2 评分输入生成补评任务：\n
   - D1：计失败\n
   - D2：照常评分并纳入统计（带异常标记）\n

### 3.4 缓存与幂等

每条 LLM 调用必须写入 JSONL，并携带 `input_fingerprint`（由输入字段拼接后哈希得到）。若 fingerprint 已存在则跳过，保证可复现与节省成本。\n

## 4. 计算算法指标（在 LLM 中间量完成后执行）

按 `spec/metrics-implementation-v1.md`：\n
1) 计算检查类指标：Recall/Precision/F1/合理性率/循环效率/无效循环率\n
2) 计算诊断类指标：Top-k coverage、Gate pass/分布、错误级联\n
3) 计算 ECE：按 stage/整体输出\n
4) 计算继承度：D1有效检查集合 vs D2请求集合\n

输出建议（默认不导出Excel）：\n
- `outputs/<run_id>/metrics/case_level.csv`\n
- `outputs/<run_id>/metrics/aggregate_by_center_model.csv`\n
- `outputs/<run_id>/metrics/missingness_report.csv`\n

## 5.（后置）可视化与报告

在 `docs/数据分析可视化计划.md` 的基础上，按上一步输出的 aggregate 表即可开始作图（该部分不在当前优先级）。\n

