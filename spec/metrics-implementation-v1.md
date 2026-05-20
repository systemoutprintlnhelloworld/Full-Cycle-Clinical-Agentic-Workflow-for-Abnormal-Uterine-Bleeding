# 指标实现规格书 v1（Algorithmic + LLM as Judge）

本文件将 `docs/评测指标确认文档.md` 的指标体系落地为“可执行实现规格”：明确每个指标的输入字段（精确到 Excel 文件/Sheet/列）、计算公式或 LLM rubric、缺失处理、输出 schema、以及与其他指标/中间量的依赖关系。

> 快速阅读建议：如果你想先用“通俗 + 表格”把全貌看懂，请先看：`spec/metrics-overview.md`。
>
> ✅ 代码已开始落地（不改 `data/` / `docs/`）：  
> - 计算指标+导出可复核 Excel：`python src/run_metrics.py`（输出到 `outputs/<run_id>/metrics_source_data.xlsx`）  
> - 状态审计+生成修正版 judge 副本：`python src/run_status_audit.py`（输出到 `work/<run_id>/fixed_excels/` + `status_audit/status_diff.csv`）  
> - LLM 评测任务（不调用API，仅生成JSONL）：`work/<run_id>/llm_tasks/*.jsonl`

## 0. 总体约束（必须遵守）

1) **LLM 指标评测输入**尽量只来自现有 Excel 的已抽取列（doc/judge/GT）。默认不读取原始对话、原始JSON、外部文件。  
2) 默认不生成新 Excel。若确需导出 Excel（便于人工审阅），必须先沟通：生成哪些文件/包含哪些 sheet/字段/写入路径。  
3) `data/` 下原始 Excel 默认不改动。若需修正 `状态` 或颜色高亮：使用 **修正版副本策略**（见 `spec/project-structure.md`）。  
4) `D1 决策异常输出（修正诊断/治疗方案）`：已确认口径 = **D1计失败 + 同时按D2体系评分并纳入D2统计**（带 `is_anomaly_d1_to_d2=true`）。  

## 1. 数据源与文件定位

### 1.1 GT（真值）

- 文件：`data/<中心>/GT/standardized_*.xlsx`
- Sheet：`Sheet1`
- 主键：`CaseID`
- GT 常用字段（文本）：  
  - 病历事实：`BasicInfo`, `ChiefComplaint`, `PresentIllness`, `PastHistory`, `MenstrualHistory`, `FamilyHistory`, `PhysicalExam`, `GT_Patient_Wishes`
  - 检查与结果：`GT_Outpatient_Checks`, `GT_Admission_Checks`, `GT_Surgery_Findings`, `GT_Pathology`
  - 诊断：`GT_Admission_Diagnosis`, `GT_Revised_Diagnosis`, `GT_Final_Diagnosis`
  - 方案：`GT_Surgery_Plan`, `GT_PostOp_Plan`, `GT_Rehab_Plan`, `GT_Followup_Plan`

### 1.2 doc agent（评测 AI 医生输出）

- 文件：`data/<中心>/doc agent/Evaluation_Summary_<doc_model>_CN_Parsed.xlsx`
- Sheets（固定集合）：  
  - `D1_Outpatient_Loop`, `D1_Outpatient_Decision`, `D2_Admission_Loop`, `D2_Admission_Decision`, `D3_Surgery_Decision`, `D4_Rehab_Plan`
- 主键：`病例ID`
- 状态：每个 sheet 的第 2 列 `状态`
- 关键输入字段：以已抽取列为准（例如 `医生决策_原始JSON_初步诊断列表` 等）

### 1.3 judge agent（现有裁判输出）

- 文件：`data/<中心>/judge agent/Evaluation_Summary_<judge_model>_CN_Judge_Parsed.xlsx`
- Sheets 同 doc
- 主键：`病例ID`
- 状态：每个 sheet 第 2 列 `状态`
- 关键字段：以已抽取列为准（例如 `Gate1判官_原始JSON_诊断匹配_评分` 等）

> 重要：后续所有跨表关联统一使用 `case_id`（`CaseID`/`病例ID`）做 join key；并携带 `center/doc_model/judge_model`。

## 2. 状态与分桶（所有聚合都必须用）

### 2.1 基准规则

- 以 `doc agent *Parsed.xlsx` 的 `状态` 为主（真值），对每个 case×model 构建：  
  - `flow_status`：未评测 / 终止于某环节 / 失败 / 完成  
  - `is_evaluated(stage)`：是否进入该 stage（与“失败”严格区分）
- 若 `judge agent` 的 `状态` 与 Parsed 不一致：在修正版副本中修正 judge 的状态（不改原文件）。

### 2.2 D1 决策异常输出（必须识别）

判定规则（v1）：`D1_Outpatient_Decision` 中存在“修正诊断/治疗方案”但“初步诊断列表/建议检查项目”均为空。

计分规则（已确认）：

- D1：计入失败（用于Gate通过率/错误级联/失败原因分析）
- D2：按 D2 指标体系照常评分与统计（但必须带 `is_anomaly_d1_to_d2=true`）

## 3. 算法指标（Algorithmic Metrics）

> 注意：以下“算法指标”允许依赖 LLM 中间量（语义归一/标注），因此多数为 **LLM辅助算法指标**，禁止 pure exact match。

### 3.1 检查阶段指标（门诊 & 入院）

#### 3.1.1 `alg.check.recall`（检查召回率 / Recall）

- 定义：`匹配的有效GT检查数 / GT总有效检查数`
- 输入（Excel）：  
  - GT：  
    - D1 门诊检查：`GT_Outpatient_Checks`  
    - D2 入院检查：`GT_Admission_Checks`（若 D1 loop 未经过，则使用 `GT_Outpatient_Checks ∪ GT_Admission_Checks`，以对齐“门诊+入院检查”共同匹配的现实情况）  
  - AI 请求检查（按阶段归属）：  
    - D1 门诊检查（只来自门诊 loop）：`D1_Outpatient_Loop` 中 `第i轮_医生_原始JSON_诊断前所需检查`（跨轮去重）  
    - D2 入院检查（包含 D1 决策中的入院检查建议）：  
      - `D1_Outpatient_Decision` 中 `医生决策_原始JSON_建议检查项目`（这是入院检查/术前检查建议，归入 D2）  
      - `D2_Admission_Loop` 中每轮 “需要补充检查”字段（若该模型缺少抽取列，则允许用每轮 `第i轮_医生_原始JSON` 兜底解析）  
- 语义匹配来源（禁止字符串精确匹配）：优先复用已有 judge 输出的“匹配/未匹配/AI额外检查”语义结果；不足部分再用 LLM 补评产出同结构结果。
- 计算步骤（高层）：  
  - 从 GT 检查文本中抽取 GT_check_set（排除“无”）  
  - 从 AI 请求字段抽取 AI_check_set（跨轮去重）  
  - 通过 judge/LLM 的语义匹配结果得到 `matched_gt_count` 与 `gt_total`  
  - recall = matched_gt_count / len(GT_check_set)
- 缺失处理：  
  - 若 GT_check_set 为空：recall 记为 NA（并计入缺失率，不参与均值）  
  - 若 AI_check_set 为空且该阶段已评测：recall=0

#### 3.1.2 `alg.check.precision`（检查精确率 / Precision）

- 定义：`(匹配有效检查数 + 合理未匹配数) / AI总请求检查数`
- 输入（Excel）：  
  - AI 请求检查集合（同 recall）  
  - GT 检查集合（同 recall）
- 语义判定来源：  
  - 匹配数/总请求数：优先使用 judge loop 的 `匹配数量/总请求数量` 或 judge 的匹配结果列表推导  
  - 合理未匹配数：对 AI 的“额外检查”（如 judge loop 的 `AI建议但实际未执行的检查`）逐条做合理性标注（LLM as Judge），得到 item-level `is_clinically_meaningful` 再汇总计数
- 输出：precision ∈ [0,1]

#### 3.1.3 `alg.check.f1`（检查 F1 分数）

- 定义：`2 * (P * R) / (P + R)`（P/R 同上）
- 缺失：若 P 或 R 为 NA，则 F1=NA

#### 3.1.4 `alg.loop.inefficiency`（无效循环率 / Inefficiency）

- 定义：`yield_flag=0 的 loop 数 / 总 loop 数`
- 输入（Excel）：  
  - 每轮检查结果内容：优先使用 `_Judge_Parsed.xlsx` 中 `第i轮_判官_原始JSON_匹配的检查内容`（因为它已对齐“本轮匹配到的GT检查结果内容”）  
  - AI 理由：`doc` 中 `第i轮_医生_原始JSON_理由`
- 依赖：`llm.loop_info_yield`（判定本轮是否产生“有效阳性/关键信息增益”）
- 说明：该指标**不等价于阳性率**；可把“阴性但对排除诊断有关键价值”计为 yield=1（由 rubric 决定）。

#### 3.1.5 `alg.loop.efficiency`（循环效率）

- 定义：完成决策所需的平均 loop 数（越低越好）
- 输入（Excel）：  
  - doc loop 中每轮字段是否为空（或 `需要补充门诊检查/需要补充检查` 的布尔字段）  
  - `flow_status`（区分未评测 vs 失败/终止）
- 计算：对已进入该 loop 阶段的 case，统计实际执行轮次 `n_rounds`，取平均。

#### 3.1.6 `alg.check.reasonableness_rate`（检查合理性率）

- 定义：`(匹配数 + Judge/LLM 判定有意义的未匹配数) / 总请求数`
- 输入：  
  - 匹配数：优先使用已有 judge 的匹配结果（匹配列表或匹配数量字段）；不足部分用 LLM 补评得到匹配列表/数量  
  - 总请求数：AI_check_set 大小（按阶段归属抽取并去重）  
  - 有意义的未匹配数：对 AI 额外检查逐条做合理性标注（LLM as Judge），汇总 `is_clinically_meaningful=1` 的数量

### 3.2 决策与诊断指标

#### 3.2.1 `alg.gate.pass_rate`（Gate 通过率）

- 定义：`通过Gate的病例数 / 总参与病例数`
- 输入（Excel）：  
  - `flow_status`（以 Parsed 为准）  
  - judge：`Gate1/2/判官_原始JSON_是否继续评测`（当该 stage 被评测时）
- 口径（v1）：  
  - 通过：`是否继续评测 == True` 且 stage 已评测  
  - 失败：`是否继续评测 == False` 且（二审不存在或 is_reasonable!=True）  
  - 未评测：`flow_status` 显示未进入该 stage
- D1 异常：计入 D1 失败。

#### 3.2.2 `alg.gate.status_distribution`（Gate 状态分布）

- 输出桶：`Passed` / `Secondary_Override` / `Failed` / `Not_Evaluated`
- 输入：  
  - Gate1：`Gate1判官_原始JSON_是否继续评测`（若存在二审机制则同理扩展）  
  - Gate2：`Gate2判官_原始JSON_是否继续评测` + `Gate2_二审原始JSON_is_reasonable`
- 判定：  
  - Passed：continue=True  
  - Secondary_Override：continue=False 且 is_reasonable=True  
  - Failed：continue=False 且 is_reasonable!=True  
  - Not_Evaluated：未进入该stage

#### 3.2.3 `alg.dx.topk_coverage`（Top-k 诊断覆盖率）

- 定义：GT 诊断是否出现在 AI 输出的前 k 个候选诊断中（k=1/3/5）
- 输入（Excel）：  
  - D1：AI `医生决策_原始JSON_初步诊断列表`；GT `GT_Admission_Diagnosis`（或以确认文档口径调整）  
  - D2：AI `医生决策_原始JSON_修正诊断`；GT `GT_Revised_Diagnosis`  
  - D3：AI `医生_原始JSON_最终诊断_诊断名称`；GT `GT_Final_Diagnosis`
- 依赖：`llm.diagnosis_semantic_match`

#### 3.2.4 `alg.error_cascade`（错误级联传导率）

- 定义：`P(Dn+1 失败 | Dn 失败)`（条件概率）
- 输入：  
  - `flow_status` + 阶段失败判定（见 `spec/metric-dependencies.md` 第4节建议）
- 输出：按阶段对（D1→D2、D2→D3、D3→D4）分别计算

#### 3.2.5 `alg.calibration.ece`（置信度校准 / ECE）

- 定义：Expected Calibration Error（bin=10）
- 输入（Excel）：  
  - 置信度字段（doc）：  
    - D1 loop：`第i轮_医生_原始JSON_置信度评估_门诊检查方案置信度`（或同义字段）  
    - D1 decision：`医生决策_原始JSON_置信度评估_诊断置信度` / `检查方案置信度`  
    - D2 decision：`医生决策_原始JSON_置信度评估_诊断置信度` / `治疗方案置信度`  
    - D3：`医生_原始JSON_置信度评估_最终诊断置信度` / `术后治疗方案置信度`  
    - D4：`医生_原始JSON_置信度评估_康复计划置信度` / `随访计划置信度`
  - accuracy label：优先使用现有 judge 的 match score 二值化（score>=阈值 记 1），缺失则用结论字段二值化。
- 输出：stage-level ECE + overall ECE

### 3.3 信息处理指标

#### 3.3.1 `alg.check.inheritance`（信息继承度 / 重复开单）

- 定义：`D2请求的检查中，与D1重复且已获结果(有效)的比例`（比例越低越好）
- 输入（Excel）：  
  - D1 已做检查与结果：GT `GT_Outpatient_Checks` + 判官 `D1_Outpatient_Loop` 匹配内容  
  - D2 请求检查集合：doc `D2_Admission_Loop` 请求字段
- 依赖：  
  - `llm.effective_result_flag`（判定哪些D1检查“已获且有效”）  
  - 检查语义匹配（D1有效检查 vs D2请求检查）：优先复用已有 judge 的匹配结果；不足部分用 LLM 做同义归一/语义对齐（不做字符串精确匹配）

## 4. LLM as Judge 指标（Semantic Metrics）

> 统一要求：每个 LLM 指标必须输出结构化 JSON（见 `spec/metric-dependencies.md` 的 JSONL 规范），并包含可解释证据（引用到输入字段片段）。

### 4.1 门诊/入院补充检查阶段（Loop）

#### 4.1.1 `llm.check.necessity`（检查必要性）

- 输入（Excel）：AI 请求检查集合 + GT 已做检查与结果 + 病例关键信息 + AI 理由
- 输出：`score∈[0,1]` + `reasons[]` + `missing_critical_checks[]` + `unnecessary_checks[]`
- 备注：可与 `llm.unmatched_check_reasonableness` 共用一次评测，避免重复调用

#### 4.1.2 `llm.check.redundancy`（检查冗余度）

- 输入同上
- 输出：`score∈[0,1]` + `redundant_checks[]`（逐项说明）

#### 4.1.3 `llm.check.cost_effectiveness`（成本效益比 / 成本-收益权衡）

- 输入同上（若未来提供检查成本表，可加入成本字段）
- 输出：`score∈[0,1]` + `cost_risk_notes[]`

#### 4.1.4 `llm.rationale.quality`（推理证据链质量 / Rationale Quality）

- 目标：评估“观察-推断-诊断/决策”链条是否合理，是否存在叙事干扰/过度整合
- 输入（Excel）：AI 理由/思维字段（loop 与 decision）
- 输出：`score∈[0,1]` + `chain: [{observation, inference, conclusion}]` + `error_tags[]`

### 4.2 D1 门诊决策（Stage 1）

#### 4.2.1 `llm.memory.fact_consistency`（事实一致性/幻觉检测）

- 输入（Excel）：GT 病历事实字段 + AI `门诊信息汇总`（或同义汇总字段）
- 输出：`score∈[0,1]` + `contradictions[]` + `hallucinations[]`

#### 4.2.2 `llm.memory.info_missing`（重要信息丢失率）

- 输入同上
- 输出：`missing_items[]` + `missing_rate∈[0,1]` + `score∈[0,1]`

#### 4.2.3 `llm.dx.reasonableness_logic`（诊断合理性/逻辑性）

- 输入（Excel）：GT 诊断 + AI 初步诊断列表 + AI 诊断思维/理由 + 病历事实
- 输出：`reasonableness_score∈[0,1]` + `logic_score∈[0,1]` + `key_errors[]`

#### 4.2.4 `llm.dx.topk_accuracy`（Top-1 / Recall@3 诊断准确）

- 输入同 `alg.dx.topk_coverage`，但可输出更丰富的匹配对与解释
- 输出：`top1_hit`, `top3_hit`, `matched_pairs[]`

### 4.3 D2 入院决策（Stage 2）

#### 4.3.1 `llm.dx.accuracy_revised`（修正诊断准确性）

- 默认复用：judge `Gate2判官_原始JSON_修正诊断匹配_评分`（缺失则回退到结论二值）
- 若需补评：输入 GT `GT_Revised_Diagnosis` + AI `修正诊断`

#### 4.3.2 `llm.plan.accuracy_safety_completeness`（治疗方案：准确性/安全性/完备性/合理性）

- 输入（Excel）：GT `GT_Surgery_Plan`/`GT_PostOp_Plan`（按阶段），AI `初步治疗方案` + `治疗方案思维` + 病历事实/病理
- 输出：\n
  - `accuracy_score∈[0,1]`（与GT关键环节匹配/偏差合理）\n
  - `safety_score∈[0,1]`（是否存在明显风险/违反指南/不恰当侵入性）\n
  - `completeness_score∈[0,1]`（术前准备/流程/术后管理关键项覆盖）\n
  - `reasonableness_score∈[0,1]`\n
  - `missing_core_items[]` / `unsafe_items[]`

#### 4.3.3 `llm.memory.stage2_retention`（历史信息继承度/事实一致性/信息丢失）

- 输入：GT 病历事实 + AI `诊疗经过回顾`（或同义字段）
- 输出：与 D1 类似（consistency + missing）

### 4.4 D3 术后决策（Stage 3）

#### 4.4.1 `llm.dx.accuracy_final`（最终诊断准确性）

- 默认复用：judge `判官_原始JSON_诊断匹配评估_评分`
- 若需补评：输入 GT `GT_Final_Diagnosis` + AI 最终诊断（含分期分级如有）

#### 4.4.2 `llm.dx.bias`（诊断偏向性：Over/Under/Neutral）

- 输入：GT 最终诊断（含关键分期/分级） + AI 最终诊断
- 输出：`bias_direction`（Over/Under/Neutral）+ `severity(0-5)` + `evidence`

#### 4.4.3 `llm.plan.postop_quality`（术后方案规范性/完备性/合理性）

- 默认复用：judge `判官_原始JSON_治疗方案匹配评估_评分` 作为“匹配/准确性”信号之一
- 仍需补充：安全性/完备性细则（同 D2 方案 rubric）

### 4.5 D4 康复/随访（Stage 4）

#### 4.5.1 `llm.rehab.completeness_logic`

- 默认复用：judge `判官_原始JSON_康复计划评估_评分`
- 若补评：输入 GT `GT_Rehab_Plan` + AI `出院康复计划_方案详情` + 病历事实

#### 4.5.2 `llm.followup.rationality_logic`

- 默认复用：judge `判官_原始JSON_随访计划评估_评分`
- 若补评：输入 GT `GT_Followup_Plan` + AI `长期随访计划_方案详情` + 最终诊断

## 5. 建议/改进（不阻塞执行，后续可迭代）

1) **成本表**：若你愿意提供检查项目成本/侵入性等级表（CSV），可把 `llm.check.cost_effectiveness` 部分改为半算法半规则（可解释性更强）。  
2) **决策高效性**：可作为派生指标：`loop_efficiency` + `gate_pass` + `cost_effectiveness` 的加权（待你确认权重）。  
3) **指南遵从度**：当前为待定指标；若未来引入RAG+指南库，建议单独作为 judge 任务，不与现有指标耦合。  
