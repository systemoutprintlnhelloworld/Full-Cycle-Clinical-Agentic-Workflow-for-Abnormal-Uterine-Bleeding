# 2026-05-20 denominator and source-data audit summary

## Scope

本次只读核查以下问题，不修改 5.12 主稿、Excel source data 或任何 `submission_bundle/Fig0X/render/` 文件：

- Table 1 中 D3/D4 专家评分样本量与 Fig. 5 workflow-valid denominator 的差异。
- D1/D2 检查环节样本量是否也存在不同口径。
- 主稿、补表与投稿 `source data.xlsx` 是否仍残留旧的 `1437/1325` 作为汇总分母。
- 校准结果中 `0.801` 与 `0.803` 的来源差异。
- D1 出现“跨阶段一致性均分”的语义解释。

## Primary inputs checked

- `D:\研究生\项目\课题7-临床评测\论文\论文大纲 (5.12）.docx`
- `analysis_viz/data/derived/metrics/manual/manual_result_quality_source.xlsx`
- `analysis_viz/data/derived/metrics/manual/manual_reasoning_quality_source.xlsx`
- `analysis_viz/figures/v2_subplots/G4_system/source_data/G4_system_metrics_v2_source.xlsx`
- `analysis_viz/figures/v2_subplots/G3_continuity/source_data/G3_continuity_metrics_v4_source.xlsx`
- `work/paper_crosscheck/2026-05-14_v2-subplots_submission_fix/submission_bundle/source data.xlsx`
- `work/paper_crosscheck/2026-05-14_v2-subplots_submission_fix/submission_bundle/Fig04/source_data/Fig04_source_data.xlsx`
- `work/paper_crosscheck/2026-05-14_v2-subplots_submission_fix/submission_bundle/Fig05/source_data/Fig05_source_data.xlsx`

## Finding 1: Table 1 D3/D4 uses raw downstream stage rows, not workflow-valid rows

5.12 主稿 Table 1 当前值：

| Stage | Result n | Result agreement | Result mean | Reasoning n | Reasoning agreement | Reasoning mean |
|---|---:|---:|---:|---:|---:|---:|
| D3 术后决策 | 1437 | 74.1% | 4.36 | 1437 | 80.9% | 4.44 |
| D4 随访计划 | 1325 | 83.2% | 4.57 | 1325 | 85.8% | 4.59 |

Fig. 5a / workflow-valid denominator 显示：

| Stage | Raw pass | Excluded by D2 forced stop | Workflow-valid |
|---|---:|---:|---:|
| D3 | 1437 | 8 | 1429 |
| D4 | 1325 | 5 | 1320 |

结论：`1437/1325` 不是算错，而是人工评分表读取了原始 D3/D4 下游行；`1429/1320` 是应用 D2 二审 `should_continue=false` 后的 workflow-valid 口径。若 Table 1 要和 Fig. 5a、当前 source data 主口径一致，应改用 `1429/1320`。

## Finding 2: D3/D4 extra case-model pairs

D3 多出的 8 条：

| Stage | Center | Case | Model | Reason |
|---|---|---|---|---|
| D3 | 佛山 | foshan_22 | gpt-5 | Gate2 `should_continue=false` |
| D3 | 佛山 | foshan_22 | grok-4 | Gate2 `should_continue=false` |
| D3 | 佛山 | foshan_72 | deepseek-v3 | Gate2 `should_continue=false` |
| D3 | 佛山 | foshan_77 | deepseek-v3 | Gate2 `should_continue=false` |
| D3 | 新疆 | Xinjiang_075 | grok-4 | Gate2 `should_continue=false` |
| D3 | 新疆 | Xinjiang_080 | grok-4 | Gate2 `should_continue=false` |
| D3 | 新疆 | Xinjiang_085 | claude-4.1 | Gate2 `should_continue=false` |
| D3 | 新疆 | Xinjiang_092 | gpt-5 | Gate2 `should_continue=false` |

D4 多出的 5 条：

| Stage | Center | Case | Model | Reason |
|---|---|---|---|---|
| D4 | 佛山 | foshan_72 | deepseek-v3 | Gate2 `should_continue=false` |
| D4 | 佛山 | foshan_77 | deepseek-v3 | Gate2 `should_continue=false` |
| D4 | 新疆 | Xinjiang_080 | grok-4 | Gate2 `should_continue=false` |
| D4 | 新疆 | Xinjiang_085 | claude-4.1 | Gate2 `should_continue=false` |
| D4 | 新疆 | Xinjiang_092 | gpt-5 | Gate2 `should_continue=false` |

这些记录的 raw D3/D4 行确实存在，且 D3/D4 status 可显示为通过；但 workflow 规则已经在 D2 二审处判定不应继续，因此与 Fig. 5a 的完成流程定义冲突。

## Finding 3: Recalculated Table 1 rows under workflow-valid denominator

按当前 Table 1 的三档映射规则重新计算：低 `[0,2)`，中 `[2,4)`，高 `[4,5]`；完全一致率为两位专家标签一致比例。

| Stage | Dimension | n | Agreement | Mean |
|---|---|---:|---:|---:|
| D3 术后决策 | Result quality | 1429 | 74.0% | 4.37 |
| D3 术后决策 | Reasoning quality | 1429 | 80.9% | 4.44 |
| D4 随访计划 | Result quality | 1320 | 83.1% | 4.57 |
| D4 随访计划 | Reasoning quality | 1320 | 85.8% | 4.59 |

建议 Table 1 最小修改：

- D3 样本数从 `1437` 改为 `1429`；结果均分建议从 `4.36` 改为 `4.37`；结果完全一致率从 `74.1%` 改为 `74.0%`。
- D4 样本数从 `1325` 改为 `1320`；结果完全一致率从 `83.2%` 改为 `83.1%`。
- D3/D4 推理均分和推理一致率四舍五入后基本保持现有显示值。

## Finding 4: Checking-loop denominators have a separate口径 issue

Table 1 当前检查环节：

| Stage | Table 1 n | Manual expert detail source | Calibration detail source |
|---|---:|---:|---:|
| D1 门诊检查 | 977 | 977 | 976 |
| D2 住院检查 | 357 | 357 | 339 |

差异来源：

- D1 多出的 1 条是 `foshan_44 / gemini-2.5p`，人工评分表中 `D1_Loop` status 为 `未经过`，但仍有两位专家评分；G4 check/calibration 中 `d1_check_count=0`。
- D2 多出的 18 条是入院检查循环终止类记录，人工评分表中 status 为 `终止于入院循环（第3/4轮后）` 或类似状态；G4 calibration detail 未纳入这些记录。

如果 Table 1 表示“专家实际评分覆盖”，当前 `977/357` 可以保留，但 caption 必须说明包含被专家评分的 loop termination / non-passed loop records。若 Table 1 要与校准和 workflow-valid source data 对齐，则可改为：

| Stage | Dimension | n | Agreement | Mean |
|---|---|---:|---:|---:|
| D1 门诊检查 | Result quality | 976 | 85.5% | 4.45 |
| D1 门诊检查 | Reasoning quality | 976 | 89.2% | 4.49 |
| D2 住院检查 | Result quality | 339 | 77.9% | 4.46 |
| D2 住院检查 | Reasoning quality | 339 | 83.8% | 4.51 |

建议：投稿主文 Table 1 优先统一为 workflow/calibration-valid 口径；若保留专家评分覆盖口径，则必须在表注里写清楚它与 Fig. 5b/Supplementary calibration 表的分母不同。

## Finding 5: Current manuscript/source-data denominator consistency

5.12 主稿全文检索：

- 正文段落已使用 `1320`、`1429` 等当前 workflow-valid 口径。
- Table 1 仍残留 `D3=1437` 和 `D4=1325`。
- 后续诊断接近度、校准表、记忆/一致性/推理异常表基本已使用 `1429/1320`。

投稿顶层 `source data.xlsx` 检索结果：

- 未发现 `1437/1325` 作为图级汇总分母展示。
- 命中的 `1429/1320` 与当前 Fig. 4 / Fig. 5 主口径一致。
- 在 per-figure source workbook 中出现的 `1437/1325` 多数是 `__source_row` 或底层明细行号/原始 source rows，不应直接判定为汇总分母错误。

Subagent B 进一步确认：

- `source data.xlsx` 的 21 个 sheet 与 `source_data_manifest.csv` 完全对应。
- 62 个 source block 均 `truncated=False`。
- Fig04/G3 与 Fig05/G4 当前主展示口径一致：D3 `1429`，D4 `1320`。
- `Fig05/plot_data/Fig5a__G4_system_metrics_v2_source.xlsx` 中旧的 `汇总_b3_diag_*` / `汇总_b5_plan_*` sheets 仍含 `1437/1325`，但这些 sheets 不是当前 Fig. 5b 作图使用的数据。投稿时建议不要将完整 G4 源 workbook 作为 plot_data 原样暴露，或在 meta/README 标注这些旧 sheets 为 `not used in current manuscript figure`。

## Finding 6: Calibration `0.801` should be updated to `0.803` if using current Fig. 5b source

当前源表：

- `analysis_viz/figures/v2_subplots/G4_system/source_data/G4_system_metrics_v2_source.xlsx`
- Sheet: `汇总_b0_points`
- Row: `B0 weighted overall`
- `x_conf = 0.886800`
- `y_acc = 0.802648`

因此按三位小数应写：

- 平均置信度 `0.887`
- 平均正确率 `0.803`

5.12 主稿正文仍写“平均正确率为 `0.801`”。这应视为旧值残留或非当前 source data 口径。若正文引用 Fig. 5b 和 Supplementary Tables 6–7，建议改为 `0.803`，并明确为“按阶段样本量加权的 overall point”。

同段还有一个文字问题：`校校准分析显示` 应改为 `校准分析显示`。

## Finding 7: D1 cross-stage consistency is generated by task design but table label is misleading

代码与 prompt 显示，`llm.cross_stage_consistency` 任务输入是同一病例的 D1-D4 summary，并要求输出 D1、D2、D3、D4 四个 stage findings。因此 D1 的 `cross_score_0_1` 不是“D1 与前序阶段比较”，而是“以 D1 为轨迹起点，回看其是否与后续 D2-D4 输出产生冲突”。

当前 Supplementary Table 15 把 D1 列为普通“跨阶段一致性均分”容易让读者误解。建议后续二选一：

- 将 D1 的跨阶段一致性显示为 `NA`，并保留 raw source data。
- 或把列名/脚注改为“D1 为 trajectory-anchor consistency，非前序阶段比较”。

本轮未修改该表，按用户要求先继续排查分母问题。

## Recommended next edits, not yet applied

1. 修改 5.12 主稿 Table 1 的 D3/D4 行到 workflow-valid 口径。
2. 决定 D1/D2 checking-loop Table 1 是否也切换到 calibration-valid 口径。
3. 将正文校准段 `0.801` 改为 `0.803`，同时删除 `校校准` typo。
4. 为 Table 1 caption 增加分母说明，避免专家评分覆盖、workflow completion、calibration detail 三种口径混用。
5. 后续如需要，再处理 D1 cross-stage consistency 的显示或脚注。
