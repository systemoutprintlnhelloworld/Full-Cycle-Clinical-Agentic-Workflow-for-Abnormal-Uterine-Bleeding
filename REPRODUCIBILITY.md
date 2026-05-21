# Reproducibility notes

This repository is intended to make the paper-facing computational workflow traceable without carrying bulky historical outputs or protected render files.

## Reproduction levels

| Level | Purpose | Requirements |
| --- | --- | --- |
| Offline demo | Verify package structure on synthetic data. | This repository only. |
| Source-data audit | Inspect figure/source-data workbooks and manifests. | This repository only. |
| Controlled rerun | Rerun workflow/metrics on protected clinical inputs. | Controlled data plus API credentials. |
| Full paper regeneration | Rebuild trajectories, scores, source data, and figures. | Source-project runtime, controlled data, and credentials. |

## Canonical sources

- Manuscript source: `D:/研究生/项目/课题7-临床评测/论文/论文大纲 (5.12）.docx`
- Paper audit and source-data scripts: original project `LLM as judge评分系统 & 量化指标系统`
- Model invocation and workflow details: external snapshot under `external/auto_eval_system_snapshot/`
- Current paper source-data bundle snapshot: `paper_assets/submission_bundle_no_render/`

## Recommended review order

1. Read the git history and `paper_assets/submission_bundle_no_render/*manifest*` files to confirm the copied file set and figure/source-data mapping.
2. Read `CODE_AND_SOFTWARE_SUBMISSION_CHECKLIST.md`, `docs/installation.md`, and `docs/demo.md`.
3. Run `bash run_demo.sh` or `.\run_demo.ps1` to confirm the offline synthetic demo.
4. Inspect `code/source_data/` and `code/figure_build/wrappers/` for source-data and figure bundle generation logic.
5. Inspect `code/model_settings/` and `external/auto_eval_system_snapshot/` for model names, parameters, and workflow settings.
6. Inspect `prompts/` and `spec/` for metric definitions, judge prompts, and stage-flow definitions.
7. Inspect `paper_assets/submission_bundle_no_render/` for the current paper-facing source-data package without render assets.

## Important exclusions

The repository intentionally excludes raw private data, model output logs, historical archive outputs, caches, and `FigXX/render/` files.

This means the repository is a submission-facing code and provenance package, not a complete raw-data archive. Claims that require private raw inputs should still be verified against the protected working project or the controlled raw-data storage.

## Demo runtime

The offline demo uses `demo_data/toy_case_*.json`, does not call LLM APIs, and should complete in less than one minute on a standard laptop.

## Credential boundary

Use `.env.example` only as a template. Do not commit `.env`, API keys, provider tokens, or hospital-internal credentials.
