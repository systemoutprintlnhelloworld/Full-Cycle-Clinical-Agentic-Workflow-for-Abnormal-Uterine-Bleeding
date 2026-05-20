# Project Structure & “零杂乱”规范

本项目当前包含 `data/`（评测过程产物）与 `docs/`（指标文档）。后续所有实现与生成物必须遵守本规范，避免污染目录、避免覆盖原始数据、保证可复现。

## 1. 根目录结构（建议）

- `data/`：原始数据与评测产物（默认只读；如需修正状态/高亮，使用副本策略，见第4节）
- `docs/`：指标文档与论文材料（只读）
- `plan/`：计划与迭代记录（本会话产物已写入）
- `spec/`：规格书（指标实现、依赖DAG、数据字典、状态定义等）
- `prompts/`：LLM评测提示词模板（所有LLM指标/中间量输出契约）
- `configs/`：配置文件（字段映射、阈值、run参数、模型参数等）
- `src/`：实现代码（数据读取、状态审计、LLM runner、指标计算）
- `work/`：中间产物与可回滚修正（缓存、审计、修正版Excel副本）
- `outputs/`：最终产物（指标结果表、报告数据、图表数据；默认不导出Excel，除非先沟通）

## 2. Run ID 与产物落盘约定

所有“可复现”的执行必须绑定一个 `run_id`，用于隔离中间产物与结果：

- `run_id = YYYY-MM-DD_HH-mm-ss_<tag>`
- `work/<run_id>/...`：缓存、审计、修正版副本、临时中间量
- `outputs/<run_id>/...`：最终指标表、可视化输入数据、报告素材

推荐约定：

- `work/<run_id>/status_audit/`：状态差异清单、规则说明、证据抽样
- `work/<run_id>/fixed_excels/`：修正版Excel副本（按原路径层级镜像）
- `work/<run_id>/llm_cache/`：LLM中间量 JSONL（按任务类型分文件）
- `outputs/<run_id>/metrics/`：指标结果（CSV/Parquet/JSONL）
- `outputs/<run_id>/reports/`：后续报告输入（先留空）

## 3. 不生成/少生成 Excel 的原则

你的偏好是：LLM指标评测时尽量只从现有Excel中提取字段值作为输入，不额外生成Excel。

默认输出格式：

- 中间量：`work/<run_id>/llm_cache/*.jsonl`
- 指标表：`outputs/<run_id>/metrics/*.csv`（必要时可加 Parquet）

只有在你明确同意后才导出Excel（例如为了方便人工审阅），并且必须说明：

1) 生成哪些Excel；2) 写到哪里；3) 每个sheet的字段与来源；4) 是否覆盖已有文件（默认禁止覆盖）。

## 4. 对 `data/` Excel 的“状态/高亮”修正策略（副本）

允许修正内容（仅限这两类）：

1) `状态` 字段更正（以 `Parsed.xlsx` 为准）；
2) 条件格式/颜色高亮统一（按 `flow_status` 着色，辅助错误分析）。

修正策略（默认）：

- 不原地修改 `data/` 下任何Excel；
- 生成修正版副本到：`work/<run_id>/fixed_excels/`；
- 同时写入审计记录到：`work/<run_id>/status_audit/`；
  - `status_diff.csv`：逐行记录修正前后
  - `rules.md`：修正规则（可复现/可解释）
  - `samples.md`：抽样证据（可选）

## 5. LLM评测输入来源约束（强制）

LLM指标/中间量评测的输入必须来自：

- `GT standardized_*.xlsx` 的文本字段（例如 `GT_Outpatient_Checks`、`GT_Revised_Diagnosis` 等）
- `doc agent *Parsed.xlsx` 的已抽取字段（诊断列表、方案文本、思维/理由、置信度等）
- `judge agent *Judge_Parsed.xlsx` 的已抽取字段（匹配结论/分数/二审reasonableness等）

默认禁止读取：

- 原始对话日志、未入表的context文件、外部数据库（除非你另行指定）

## 6. 需要纳入版本控制的文件

推荐必须纳入：

- `plan/`、`spec/`、`prompts/`、`configs/`、`src/`

推荐不纳入：

- `work/`、`outputs/`（执行产物，体积大；如需留存，采用压缩归档或只留关键CSV）

