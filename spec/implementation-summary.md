# 实现进度总结（代码已落地，零杂乱）

本文档总结当前已落地的代码能力、输出产物、与下一步开发路线。  
约束遵守：不修改 `data/` 与 `docs/`；所有生成物写入 `work/<run_id>/` 与 `outputs/<run_id>/`。

---

## 1) 已实现的能力

### 1.1 指标计算 + 人类可读审阅表（中文、可手算复核）

- 入口脚本：`src/run_metrics.py`
- 读取：`data/<中心>/{GT,doc agent,judge agent}/*.xlsx`（只读）
- 输出（每次执行一个 `run_id`）：
  - **主入口（你应打开的）**
    - `outputs/<run_id>/<中心>/<模型>/审阅表.xlsx`
      - 中文表头 + 分子/分母拆开 + 需要复核清单（带反馈列）
    - `outputs/<run_id>/summary/总览.xlsx`
      - `指标汇总_中心模型` / `解析异常` / `审阅表索引`
  - **可选：全量 raw（不建议人工看，供调试）**
    - `work/<run_id>/_raw/<中心>/<模型>/metrics_source_data.xlsx`（仅当不加 `--no-excel` 时生成）

当前已落地的 v1 算法指标（可复核，且每轮 source data 已给出）：
- D1/D2 检查召回率（分母=GT“有效检查数”）
- D1/D2 无效循环率 proxy（基于 judge 每轮 `匹配数量/总请求数量/评分_检查匹配度`，并保留 raw 值对照）
- D2 继承度口径已在文档锁定（重复率 + 非重复比例），但**语义去重/重复判断需要 LLM 输出**，尚未计算

### 1.2 状态审计 + judge 修正版副本（不改 data）

- 入口脚本：`src/run_status_audit.py`
- 行为：
  - 对每个 `*_Parsed.xlsx` 与对应 `*_Judge_Parsed.xlsx`，逐 sheet 比较第 2 列 `状态`
  - 以 Parsed 为真值，将 judge 的 `状态` 修正到副本中
  - 应用 `状态` 条件格式高亮（顺利通过/终止/未经过）
- 输出：
  - `work/<run_id>/status_audit/status_diff.csv`
  - `work/<run_id>/fixed_excels/<中心>/judge agent/*.xlsx`（修正版副本）

### 1.3 LLM 评测任务（生成任务）+ 小规模执行（可选）

LLM 输入严格来自 Excel 已抽取列值（GT/doc/judge），不读原始对话与原始JSON。

输出目录：`work/<run_id>/llm_tasks/`

- `llm.diagnosis_semantic_match.D1.jsonl`
  - 用于 D1 Top-k 诊断语义命中（k={1,3,5}）
  - prompt 模板：`prompts/llm_diagnosis_semantic_match.md`
- `llm.unmatched_check_reasonableness.jsonl`
  - 用于“未匹配检查项逐条合理性/冗余度标注”（供 Precision/合理性率等）
  - prompt 模板：`prompts/llm_unmatched_check_reasonableness.md`

可选执行（会调用 API）：
- 入口脚本：`src/run_llm_tasks.py`
- 输出：
  - `work/<run_id>/llm_results/<judge_model>__<channel>.jsonl`（缓存，避免重复计费）
  - `outputs/<run_id>/summary/llm_results_<judge_model>__<channel>.xlsx`（人工审阅）

---

## 2) 使用方式（你本地执行）

### 2.1 计算指标 + 导出 Excel

```bash
python src/run_metrics.py --tag <tag>
```

### 2.2 状态审计（生成 judge 修正版副本）

```bash
python src/run_status_audit.py --tag <tag>
```

### 2.3 LLM 小规模试跑（推荐先抽样覆盖多个中心×模型）

```bash
python src/run_llm_tasks.py --run-id <run_id> --task-filter llm.unmatched_check_reasonableness --sample-per-group 1 --max-tasks 30
python src/run_llm_tasks.py --run-id <run_id> --task-filter llm.diagnosis_semantic_match --sample-per-group 1 --max-tasks 30
```

仅导出已缓存结果（不调用 API）：

```bash
python src/run_llm_tasks.py --run-id <run_id> --export-only
```

可选参数（两者脚本都支持）：
- `--centers 佛山 新疆 武汉`
- `--models gpt-5-2025-08-07 ...`

---

## 3) 与《通俗总说明》的对应关系

- 口径与字段归属、检查匹配重建原则：`spec/metrics-overview.md`
- 当前代码输出结构（source data + field pack + LLM tasks）：已按 `spec/metrics-overview.md` 的“可复核/可在Excel自算”的目标落地

---

## 4) 已知限制 & 下一步开发（建议）

### 4.1 需要 LLM 结果后才能补齐的指标

- 检查 Precision/F1（需要逐条 `unmatched_checks` 的合理性标注）
- D2 继承度（需要 D2 请求 vs D1 已获检查 的语义重复判定）
- 错误级联（需要 LLM 输出“偏差/风险 → 可能影响下一步”的结构化结果）

### 4.2 成本控制建议（需要你决定是否加开关）

已实现开关：`python src/run_metrics.py --llm-task-scope {review_only,all}`（默认 `review_only`）。  
当前策略：仅对“需要复核/抽样覆盖”的 case 生成任务，以控制 LLM 成本与人工审阅量。
