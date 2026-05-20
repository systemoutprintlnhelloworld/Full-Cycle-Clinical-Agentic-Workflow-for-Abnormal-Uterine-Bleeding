# 指标依赖关系（DAG）与中间量定义

> 快速阅读建议：如果你想先用“通俗 + 表格”把全貌看懂，请先看：`spec/metrics-overview.md`。

本文件用于明确：哪些算法指标依赖哪些 LLM 中间量/现有 judge 输出；以及执行顺序（LLM优先）。

## 0. 基础实体与索引键

- `center`：佛山 / 新疆 / 武汉
- `doc_model`：来自 `data/*/doc agent/Evaluation_Summary_*_Parsed.xlsx`
- `judge_model`：来自 `data/*/judge agent/Evaluation_Summary_*_Judge_Parsed.xlsx`（与doc_model一致）
- `case_id`：来自 `病例ID`（doc/judge）与 `CaseID`（GT）
- `stage`：`D1_Outpatient_Loop` / `D1_Outpatient_Decision` / `D2_Admission_Loop` / `D2_Admission_Decision` / `D3_Surgery_Decision` / `D4_Rehab_Plan`

> 说明：后续所有表与 JSONL 产物必须至少包含以上键，才能进行跨表关联与聚合。

## 1. 状态主数据（flow_status）

### 1.1 输入来源

- 以 `doc agent *Parsed.xlsx` 的各 sheet 第2列 `状态` 为主
- 若 `judge agent *Judge_Parsed.xlsx` 的 `状态` 与 Parsed 不一致：后续在修正版副本中修正 judge 的状态（以Parsed为准）

### 1.2 输出

- `flow_status`：精确到“终止于哪个环节的子环节/轮次”
- `is_evaluated(stage)`：该 stage 是否被评测（与“失败”严格区分）
- `is_completed`：是否完成全流程至 D4
- `is_failed_at(stage)`：阶段性失败标记（由本文件第4节定义的“阶段失败条件”给出）

### 1.3 特殊：D1 决策异常输出（Anomaly@D1Decision->D2Scored）

当 `D1_Outpatient_Decision` 出现“修正诊断/治疗方案”而“初步诊断列表/建议检查项目”为空：

- 标记 `is_anomaly_d1_to_d2 = true`
- 计数规则（已确认口径）：
  - D1：计入失败（用于Gate通过率/错误级联等）
  - D2：照常评分与统计（但必须带异常标记，防止误读）

## 2. 现有 judge 可直接复用的信号（无需新 LLM）

> 这些信号来自 `_Judge_Parsed.xlsx` 已抽取列，可直接用于部分指标或作为 LLM 中间量的弱监督/校验。

- `gate1.continue`：Gate1 是否继续评测（D1 decision）
- `gate1.diagnosis_match.{conclusion, score}`
- `gate1.check_match.{degree, score}`
- `loop.d1.round_i.check_match_score` / `loop.d1.round_i.reasonableness_score` / `loop.d1.round_i.overall_score`
- `gate2.continue`
- `gate2.revised_dx_match.score`
- `gate2.plan_match.score`
- `gate2.secondary.is_reasonable`（二审捞回）
- `d3.dx_match.score` / `d3.plan_match.score`
- `d4.rehab.score` / `d4.followup.score` / `d4.overall.score`

## 3. LLM 中间量（必须先产出，供多个算法指标复用）

所有 LLM 中间量默认输出为 JSONL：

- 路径：`work/<run_id>/llm_cache/<task_name>.jsonl`
- 每行至少包含：`center, doc_model, judge_model, case_id, stage, task_name, input_fingerprint, output_json`

### 3.1 `llm.check_canonical_map`（检查项语义归一）

目的：把 AI/GT 中的检查项映射到统一 canonical，避免 exact match。

- 输入（Excel字段）：GT 检查文本（`GT_Outpatient_Checks`/`GT_Admission_Checks`）、AI 请求检查列表（doc loop 与 decision 中的检查项字段）
- 输出（JSON schema）：`{canonical_items: [...], mapping: [{raw, canonical, confidence, note}] }`

消费者：

- `alg.check.recall`
- `alg.check.inheritance`
- `alg.check.precision`（用于判定“是否与GT同义项重复/覆盖”）

> 说明：你已强调“不能做字符串匹配”。如果现有 judge 已给出匹配/未匹配列表，则可直接复用；`llm.check_canonical_map` 主要用于：GT 文本抽取、跨模型字段差异导致 judge 列缺失时的兜底。

### 3.2 `llm.unmatched_check_reasonableness`（未匹配检查项合理性/冗余度）

目的：为 Precision / 检查合理性率 / 冗余度提供 item-level 标签。

- 输入：未匹配检查项列表（来自 AI 请求列表 - GT canonical 集合）、病例关键信息（GT现病史/查体/已做检查结果）、AI理由（doc 的 `理由/思维`）
- 输出：`[{check_item, is_clinically_meaningful(0/1), is_redundant(0/1), expected_impact, rationale}]`

消费者：

- `alg.check.precision`
- `alg.check.reasonableness_rate`
- `llm.check.necessity` / `llm.check.redundancy`（LLM指标）

### 3.3 `llm.loop_info_yield`（Loop 信息增益/阳性产出）

目的：为“无效循环率”提供 loop-level 标注，避免硬编码“阳性/阴性”规则。

- 输入：每轮匹配到的检查结果内容（GT结果文本/判官匹配内容）、AI本轮理由
- 输出：`{round: i, yield_flag(0/1), yield_type: [positive|negative_but_informative|no_yield], evidence}`（可扩展）

消费者：

- `alg.loop.inefficiency`

### 3.4 `llm.diagnosis_semantic_match`（Top-k 诊断语义命中）

目的：实现 Top-k 覆盖率、诊断方向合理性等（避免 exact match）。

- 输入：GT 诊断（`GT_Admission_Diagnosis` / `GT_Revised_Diagnosis` / `GT_Final_Diagnosis`）、AI 诊断列表（doc 的 `初步诊断列表`/`修正诊断`/`最终诊断`）
- 输出：`{k: 1|3|5, hit(0/1), matched_pairs: [...], strictness: {...}}`

消费者：

- `alg.dx.topk_coverage`
- `llm.dx.reasonableness` / `llm.dx.logic`（LLM指标的输入辅助）

### 3.5 `llm.effective_result_flag`（检查结果是否“已获且有效”）

目的：为“信息继承度/重复开单”提供“哪些检查已获且有效”的集合。

- 输入：D1阶段已做检查及其结果文本（GT与/或判官匹配内容）、病例上下文
- 输出：`{effective_checks: [...], per_item: [{check, effective(0/1), reason}] }`

消费者：

- `alg.check.inheritance`

## 4. 算法指标依赖映射（消费者列表）

> 下表为“指标 -> 依赖”的摘要版；详细的 Excel 字段来源与公式在 `spec/metrics-implementation-v1.md` 中展开。

### 4.1 门诊/入院检查阶段

- `alg.check.recall` 依赖：`llm.check_canonical_map` + GT检查集合
- `alg.check.precision` 依赖：`llm.check_canonical_map` + `llm.unmatched_check_reasonableness` + AI请求集合
- `alg.check.f1` 依赖：Recall + Precision
- `alg.loop.inefficiency` 依赖：`llm.loop_info_yield`
- `alg.loop.efficiency` 依赖：doc loop 中“实际执行到第几轮” + `flow_status`
- `alg.check.reasonableness_rate` 依赖：`llm.unmatched_check_reasonableness` + 匹配数

### 4.2 决策/诊断/方案阶段

- `alg.gate.pass_rate` 依赖：`flow_status` + `gate*.continue`
- `alg.gate.status_distribution` 依赖：`gate2.secondary.is_reasonable` + `gate*.continue` + `flow_status`
- `alg.dx.topk_coverage` 依赖：`llm.diagnosis_semantic_match`
- `alg.calibration.ece` 依赖：doc 置信度字段 + accuracy label（优先使用现有 judge match 分数/结论二值化）

### 4.3 信息处理

- `alg.check.inheritance` 依赖：`llm.effective_result_flag` + `llm.check_canonical_map` + D2请求检查集合

### 4.4 整体

- `alg.error_cascade` 依赖：阶段失败定义 + `flow_status`
  - 阶段失败定义建议（v1，可配置）：\n
    - D1失败：`gate1.continue == false` 或 `gate1.diagnosis_match.score < t1` 或 `is_anomaly_d1_to_d2==true`\n
    - D2失败：`gate2.continue == false` 且 `gate2.secondary.is_reasonable != true`\n
    - D3失败：`判官_是否继续评测 == false` 或 `d3.dx_match.score < t3`\n
    - D4失败：通常无Gate失败，仅统计缺失/未评测\n
