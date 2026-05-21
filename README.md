# Full-Cycle Clinical Agentic Workflow for Abnormal Uterine Bleeding

This repository is a curated reviewer code package for a full-cycle clinical agentic workflow study in abnormal uterine bleeding (AUB).

It was created by copying selected source code, prompts, specifications, and small paper-facing assets from the working project. The original working folders were not moved or modified. In particular, files under `work/paper_crosscheck/2026-05-14_v2-subplots_submission_fix/submission_bundle/FigXX/render/` in the source project were treated as protected and were not copied here.

## What This Software Does

The software supports full-cycle gynecological clinical decision workflow replay and evaluation. It includes workflow construction, environment-agent replay, doctor-agent model invocation, LLM-as-Judge scoring, trajectory logging, WebUI/blind-review support code snapshots, metric aggregation, source-data construction, figure bundle assembly, and manuscript/source-data audit utilities.

The repository is intended for confidential peer-review inspection and controlled reproducibility assessment. It does not include raw patient-level clinical records or API credentials.

## Reviewer Quick Start

1. Read `CODE_AND_SOFTWARE_SUBMISSION_CHECKLIST.md` for the journal checklist working copy.
2. Read `docs/reviewer_package_scope.md` for what is included and excluded.
3. Install dependencies with `requirements.txt` or `environment.yml`; see `docs/installation.md`.
4. Run the reviewer-safe offline demo:

```bash
bash run_demo.sh
```

On Windows PowerShell:

```powershell
.\run_demo.ps1
```

The demo uses only synthetic data in `demo_data/`, makes no API calls, and writes `outputs/demo_summary.json`.

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
- `demo_data/`: synthetic reviewer-safe toy cases.
- `scripts/run_offline_demo.py`: offline demo runner.
- `docs/`: installation, demo, data dictionary, model settings, prompt inventory, repository organization, and protection notes.

## Code and Software Submission Materials

- Checklist working copy: `CODE_AND_SOFTWARE_SUBMISSION_CHECKLIST.md`
- License: `LICENSE`
- Installation: `docs/installation.md`
- Demo: `docs/demo.md`
- Data dictionary: `docs/data_dictionary.md`
- Prompt inventory: `docs/prompt_inventory.md`
- Model versions and inference settings: `docs/model_versions.md`
- Reproducibility notes: `REPRODUCIBILITY.md`

## Provenance

Repository-level provenance is tracked by git history and by the paper-bundle manifests under `paper_assets/submission_bundle_no_render/`.

Use `source_data_manifest.csv`, `bundle_manifest.json`, and per-figure `manifest.json` files as the first audit trail for figure/source-data assets.

Repository-level reviewer package files added after the original copy step are tracked by git history.

## Protected render rule

Do not add or regenerate `FigXX/render/` files in this repository unless explicitly required later.

The protected render files in the source project were hashed before and after this organization step. See `docs/PROTECTED_RENDER_POLICY.md` and `paper_assets/audit_reports/2026-05-20_submission_code_repo_organize/`.

## Data, Credentials, and License Boundary

This package intentionally excludes patient-level raw clinical records, model output logs that may contain sensitive content, API keys, provider credentials, hospital-internal deployment files, caches, and bulky historical outputs.

The current `LICENSE` is a restricted confidential-review license pending final institutional approval. Before public release, replace it with the license approved by the author team and institution.
