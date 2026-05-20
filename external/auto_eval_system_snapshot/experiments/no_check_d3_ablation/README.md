# No-Check D3 Ablation

本目录是独立的消融实验项目，只新增文件，不修改原有自动测评系统代码。

## 实验目标

- 删除门诊/入院检查循环
- 删除 D1/D2/D3 gate 对流程推进的控制
- 固定流程为 `D1 -> D2 -> D3`
- 在 Doctor 输入上下文中移除门诊/入院检查结果文本（不向 Doctor 注入检查细节）
- D1 仅输出 `初步诊断`，Judge 在 D1 仅做诊断匹配评估（方案评估=`不适用`）
- D2 之后默认提供手术相关信息，不再依赖“治疗方案匹配后再给信息”的动态机制
- Judge 只负责打分，不负责阻断流程
- 仅运行 baseline 中 D1/D2/D3 均 `顺利通过` 且 D3 诊断评分非空的“模型-病例轨迹”
- 当前小规模联调目标：15 个病例组，45 线程
- 所有涉及 `gemini-2.5-pro` 的调用（Doctor/Judge）强制走运行时路由：主 `duckcoding`，fallback `星辰`（不改原 channels.yaml）

## 输出

默认输出到仓库根目录下的 `output_ablation_no_check_d3/<run_label>/`：

- `eligible_cases.csv`
- `eligible_tracks.csv`
- `excluded_tracks.csv`
- `summary.csv`
- `summary.xlsx`
- `checkpoint.json`
- `task_failures.jsonl`
- `failed_tasks_for_resume.csv`（仅失败时生成，含可续跑上下文路径与最后 prompt 摘要）
- `outputs/<center>/<model>/per_case_json/*.json`
- `outputs/<center>/<model>/raw_traces/*.jsonl`
- `outputs/<center>/<model>/html_traces/*.html`
- `outputs/<center>/<model>/html_traces/*_trace.html`

## 运行方式

```powershell
python experiments/no_check_d3_ablation/run_ablation.py --threads 45 --limit-cases 15 --task-retries 3
```

### Gemini 渠道（运行时）

```powershell
$env:DUCKCODING_BASE_URL='https://api.duckcoding.ai/v1'
$env:DUCKCODING_API_KEY='<duckcoding_key>'
$env:XINGCHEN_BASE_URL='https://ai.centos.hk/v1'
$env:XINGCHEN_API_KEY='<your_key>'
python experiments/no_check_d3_ablation/run_ablation.py --threads 45 --limit-cases 15 --run-label smoke15_20260411_45t_duck_xing --task-retries 3
```

说明：
- 若本轮任务中包含 `gemini-2.5-pro`，至少需要配置 `XINGCHEN_API_KEY`（星辰渠道必需）。
- 当 `DUCKCODING_API_KEY` 存在时：`gemini` 路由为 `duckcoding -> xingchen`。
- 当 `DUCKCODING_API_KEY` 缺失时：自动降级为仅 `xingchen`（不再报错退出）。
- `DUCKCODING_BASE_URL` 与 `XINGCHEN_BASE_URL` 支持不带 `/v1` 的写法，运行时会自动补齐为 OpenAI 兼容地址。
- 运行器会在控制台实时输出进度条，并每 5 秒心跳刷新一次速度和 ETA。

## 消融可视化（不新增 API 调用）

```powershell
python experiments/no_check_d3_ablation/plot_ablation_effects.py --run-label smoke15_20260410_03
```

输出目录：
- `output_ablation_no_check_d3/<run_label>/figures_ablation_effect/`
- `output_ablation_no_check_d3/<run_label>/source_data_ablation_effect/`

Source data 默认包含：
- `ablation_vs_normal_pairs.csv`
- `ablation_vs_normal_metric_means.csv`
- `ablation_vs_normal_metric_deltas_by_model.csv`
- `ablation_vs_normal_metric_coverage.csv`

说明：
- 正常流程基线会自动在 `output/<center*>/<model>/single_excels/` 中匹配同病例文件（含 `-v2` 目录），优先使用版本目录与较新文件。

## HTML Trace 样式

- 消融项目已改为复用主系统 `auto_eval_system/utils/html_logger.py` 的 Project Echo 样式。
- 每个病例会生成两份同内容页面：
  - `<model>_<center>_<case_id>_trace.html`
  - `<model>_<center>_<case_id>.html`（兼容旧命名）

## 当前默认假设

- 评测中心默认使用 `Foshan`、`Wuhan`、`Xinjiang`
- 评测模型默认使用主系统的 5 个模型
- Judge 默认使用 `gemini-2.5-pro`
- D1/D2/D3 的“距离 GT 最终诊断”评分，复用原 D3 诊断评分标准
