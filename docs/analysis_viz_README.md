# analysis_viz - 数据分析与可视化子项目

本目录用于集中管理：
- raw 源数据（评测已终止后不可再生的关键 Excel/人工评分）
- 绘图/指标所需的 derived data source（明细+汇总）
- figures（论文最终图 + 多风格 variants）
- scripts（绘图/报表生成脚本入口与复现说明）
- docs（索引、审计、可观测性说明）

## 给用户看的入口（中文）
- 阅读入口：`给用户看/00_阅读入口.md`
- 图-数据对应清单：`给用户看/02_图与数据对应清单.csv`
- 目录释义：`给用户看/03_目录释义_数据与图.md`
- 当前缺口：`给用户看/04_当前缺口与处理建议.md`

## 关键索引
- 图索引：`docs/figure_registry.csv`
- 指标索引：`docs/metrics_registry.csv`
- 清理清单：`docs/cleanup_manifest.csv`
- 样本规则审计：`docs/sample_rule_audit.csv`
- 终稿逐图映射：`docs/final_paper_bundle_figure_map.csv`

## 约定
- 六环节统一：门诊检查 / 门诊决策 / 入院检查 / 入院决策 / 术后康复 / 随访计划
- 模型缩写统一：deepseek-v3, gpt-5, gemini-2.5p, grok-4, claude-4.1
- 样本剔除：D1 特殊案例永不参与计算；D3 Gate3 不通过则 D4 不参与计算

## 常用重建脚本
- `python analysis_viz/scripts/wrappers/build_results_sections_bundle.py`
- `python analysis_viz/scripts/wrappers/build_final_paper_bundle.py`
- `python analysis_viz/scripts/wrappers/build_per_figure_source_workbooks.py`
- `python analysis_viz/scripts/wrappers/generate_figure_captions.py`
- `python analysis_viz/scripts/wrappers/build_user_readable_portal.py`
