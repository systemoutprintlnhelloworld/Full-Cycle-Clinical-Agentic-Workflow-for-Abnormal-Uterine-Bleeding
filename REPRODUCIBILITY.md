# Reproducibility notes

This repository is intended to make the paper-facing computational workflow traceable without carrying bulky historical outputs or protected render files.

## Canonical sources

- Manuscript source: `D:/研究生/项目/课题7-临床评测/论文/论文大纲 (5.12）.docx`
- Paper audit and source-data scripts: original project `LLM as judge评分系统 & 量化指标系统`
- Model invocation and workflow details: external snapshot under `external/auto_eval_system_snapshot/`
- Current paper source-data bundle snapshot: `paper_assets/submission_bundle_no_render/`

## Recommended review order

1. Read `MANIFEST.csv` to confirm the copied file set.
2. Inspect `code/source_data/` and `code/figure_build/wrappers/` for source-data and figure bundle generation logic.
3. Inspect `code/model_settings/` and `external/auto_eval_system_snapshot/` for model names, parameters, and workflow settings.
4. Inspect `prompts/` and `spec/` for metric definitions, judge prompts, and stage-flow definitions.
5. Inspect `paper_assets/submission_bundle_no_render/` for the current paper-facing source-data package without render assets.

## Important exclusions

The repository intentionally excludes raw private data, model output logs, historical archive outputs, caches, and `FigXX/render/` files.

This means the repository is a submission-facing code and provenance package, not a complete raw-data archive. Claims that require private raw inputs should still be verified against the protected working project or the controlled raw-data storage.

