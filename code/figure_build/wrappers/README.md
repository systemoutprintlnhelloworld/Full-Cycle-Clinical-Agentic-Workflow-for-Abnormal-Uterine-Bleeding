本目录存放对仓库现有脚本的“薄封装入口”（wrapper）。

原则：
- 不修改原有逻辑，只负责把输入/输出路径与参数固定下来，方便复现。
- 对应原始实现一般位于：`scripts/` 或 `src/tools/`。

当前 wrappers：

## A. 索引与审计
- `build_registries.py`：生成图索引 `analysis_viz/docs/figure_registry.csv`
- `build_metrics_registry.py`：生成机器指标索引 `analysis_viz/docs/metrics_registry.csv`
- `run_sample_rule_audit.py`：样本规则审计（D1 anomaly / Gate3->D4）
- `audit_metric_observability_schema.py`：机器指标工作簿结构可观测性审计
- `audit_outputs_cleanup.py`：`outputs` 清理状态审计
- `build_plot_script_inventory.py`：绘图脚本清单与缺失统计
- `build_alignment_source_inventory.py`：alignment source_data 可观测分层盘点
- `audit_figdata_granularity.py`：全量 figdata 粒度审计（病例级/汇总级）
- `audit_backup_storage.py`：备份目录体积与分组巡检
- `run_periodic_audits.py`：周期审计一键执行与运行记录

## B. 数据抽取与重建
- `extract_sankey_figdata.py`：Sankey 明细+汇总（含规则排除）
- `extract_llm_metric_sources.py`：LLM 三类指标可审计 source
- `extract_paper_algorithmic_sources.py`：Paper Fig3 指标可审计重建
- `extract_algorithmic_metric_sources.py`：algorithmic A1-A8 可审计重建
- `extract_calibration_metric_sources.py`：calibration ece/reliability/bubble/line 可审计重建
- `extract_manual_metric_sources.py`：manual result/reasoning 可审计重建
- `extract_alignment_metric_sources.py`：alignment 对齐与双医生一致性病例级可审计重建

## C. 资产同步与分层
- `sync_center_raw_data.py`：同步三中心 `GT/doc agent/judge agent`（排除 bkup）
- `sync_latest_summary_raw.py`：同步 `outputs/latest/summary` 到 raw 快照
- `sync_variants_figure_assets.py`：同步保留的 variants 图资产（含 llm/full，排除 llm/small/summary）
- `build_results_sections_bundle.py`：按 Results 章节分层打包 figures/figdata（修复 Fig1/Fig10 前缀误匹配）
- `build_final_paper_bundle.py`：终稿打包（含 variants 关键图组）并生成逐图 source map
- `build_per_figure_source_workbooks.py`：为 final 包每张图生成一对一 source workbook（含 detail+summary）

## D. 可读性增强
- `style_excel.py`：关键 derived xlsx 样式增强（覆盖前备份，按文件保留最近 20 份）
- `generate_figure_captions.py`：为多图目录生成 `caption.md`（逐图学术图注）
- `build_user_readable_portal.py`：生成“给用户看”中文入口与图-数据对应清单

