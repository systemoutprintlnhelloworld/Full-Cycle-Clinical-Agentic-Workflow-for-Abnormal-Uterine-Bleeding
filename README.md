# Paper submission code repository

This repository is a curated, code-first snapshot for the paper submission package of 课题7临床评测.

It was created by copying selected source code, prompts, specifications, and small paper-facing assets from the working project. The original working folders were not moved or modified. In particular, files under `work/paper_crosscheck/2026-05-14_v2-subplots_submission_fix/submission_bundle/FigXX/render/` in the source project were treated as protected and were not copied here.

## Layout

- `code/paper_crosscheck/`: manuscript audit and cross-check entry points.
- `code/source_data/`: source-data packaging scripts.
- `code/figure_build/`: figure bundle and paper-figure orchestration scripts.
- `code/metrics/`: metric calculation and LLM-judge metric package.
- `code/model_settings/`: model inference setting extraction scripts.
- `code/tools/`: selected utility scripts used by the paper pipeline.
- `external/auto_eval_system_snapshot/`: code-only snapshot of the external auto-evaluation system, excluding outputs, data, logs, `.env`, and git metadata.
- `prompts/`: LLM judge and metric prompts.
- `spec/`: metric, flow, data-dictionary, and implementation specifications.
- `paper_assets/submission_bundle_no_render/`: current paper-facing source data, plot data, launchers, manifests, and model-setting assets, explicitly excluding `render/`.
- `paper_assets/audit_reports/`: recent audit summaries and organization manifests.
- `docs/`: repository organization and protection notes.

## Manifest

`MANIFEST.csv` records every copied file with source path, destination path, size, and SHA256 hash.

Use it as the first audit trail when checking whether the repository contains the expected code and assets.

## Protected render rule

Do not add or regenerate `FigXX/render/` files in this repository unless explicitly required later.

The protected render files in the source project were hashed before and after this organization step. See `docs/PROTECTED_RENDER_POLICY.md` and `paper_assets/audit_reports/2026-05-20_submission_code_repo_organize/`.

