# Flow Status 定义（用于分桶聚合与错误分析）

本文件定义 `flow_status` 与 `stage_status` 的统一口径，用于：\n
1) 区分“失败”与“未评测”；\n
2) 精确定位终止环节（到子环节/轮次）；\n
3) 统一修正 `*_Judge_Parsed.xlsx` 的状态到与 `*_Parsed.xlsx` 一致（副本策略）。\n

## 1. 数据中出现的原始状态值（观察）

来自 `doc agent *Parsed.xlsx`（不同 sheet）：\n
- `未经过`\n
- `顺利通过`\n
- `终止于门诊决策`\n
- `终止于入院循环`\n
- `终止于入院决策`\n
- `顺利通过（流程完成）`\n

来自 `judge agent *Judge_Parsed.xlsx`：\n
- 除上述外，还可能出现：`终止于门诊循环` 等（与 Parsed 不一致时以 Parsed 为准）。\n

## 2. 统一层级

### 2.1 `stage_status`（每个 sheet 一条）

对每个 `case_id × stage(sheet)`，定义：\n
- `NOT_EVALUATED`：未进入该sheet/未产生输出（通常对应 `未经过`）\n
- `PASSED`：该sheet完成且进入下一环节（通常对应 `顺利通过` / `顺利通过（流程完成）`）\n
- `TERMINATED_HERE`：流程终止于该sheet（例如 `终止于门诊决策`）\n

### 2.2 `flow_status`（case×model 一条）

对每个 `case_id × doc_model` 汇总定义：\n
- `COMPLETED@D4`：D4 为 `PASSED`（流程完成）\n
- `TERMINATED@D3`：D3 为 `TERMINATED_HERE` 或后续未进入\n
- `TERMINATED@D2_DECISION`\n
- `TERMINATED@D2_LOOP`\n
- `TERMINATED@D1_DECISION`\n
- `TERMINATED@D1_LOOP`\n
- `NOT_STARTED`：所有stage均未评测（一般不会出现）\n
- `ANOMALY@D1_DECISION_TO_D2_SCORED`：D1决策异常输出（见第4节）\n

> 注意：`TERMINATED` 不等于 `FAILED`。失败需要结合 judge 结果或规则（例如 Gate continue=False 且二审不捞回）。\n

## 3. Loop 子环节精细化（轮次）

现有 `状态` 不包含“终止于第几轮”。为了支持错误分析，定义 `loop_rounds_executed`：\n

- D1：在 `D1_Outpatient_Loop` sheet 中，统计 `第1轮_医生_原始JSON`、`第2轮_医生_原始JSON`... 哪些非空，得到执行轮次上界。\n
- D2：在 `D2_Admission_Loop` sheet 同理。\n

并定义：\n
- `TERMINATED@D1_LOOP_R<n>`：若流程终止于D1 loop，并记录最后一轮为 n。\n
- `TERMINATED@D2_LOOP_R<n>`：同理。\n

## 4. D1 决策异常输出（已确认口径）

判定（v1）：\n
- `D1_Outpatient_Decision` 中出现“修正诊断/治疗方案”字段非空；同时“初步诊断列表/建议检查项目”为空。\n

计分口径（你已确认）：\n
- 在 D1 统计中：计为失败案例（用于Gate通过率/错误级联/失败分析）；\n
- 在 D2 统计中：照常按 D2 指标体系评分，并纳入 D2 各项指标统计；\n
- 需要标记：`is_anomaly_d1_to_d2=true`，并将 `flow_status` 置为 `ANOMALY@D1_DECISION_TO_D2_SCORED`。\n

## 5. Excel 颜色高亮建议（修正版副本中应用）

建议按 `flow_status` 或 `stage_status` 做条件格式：\n
- `PASSED/COMPLETED`：绿色\n
- `TERMINATED`：橙色\n
- `FAILED`：红色\n
- `NOT_EVALUATED`：灰色\n
- `ANOMALY`：紫色\n

并在 `work/<run_id>/status_audit/rules.md` 中记录具体颜色值与条件范围。\n

