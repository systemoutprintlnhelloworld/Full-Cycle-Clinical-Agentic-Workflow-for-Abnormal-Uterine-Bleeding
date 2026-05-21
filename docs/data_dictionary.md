# Data Dictionary

This repository contains two data classes: synthetic demo data and
paper-facing source-data assets.

## Synthetic demo data

Location: `demo_data/`

| Field | Meaning |
| --- | --- |
| `case_id` | Synthetic case identifier. Not a real patient ID. |
| `center` | Synthetic center label used for workflow grouping. |
| `patient_summary` | Short synthetic clinical summary. |
| `stages` | Ordered D1-D4 stage objects. |
| `stage_id` | Stage label, for example `D1` or `D2`. |
| `visible_information` | Information available to the doctor agent at that stage. |
| `doctor_action` | Synthetic doctor-agent decision or request. |
| `environment_feedback` | Synthetic environment-agent feedback. |
| `judge_score` | Synthetic reviewer-safe score used by the offline demo. |
| `notes` | Demo-only comments. |

## Paper-facing source-data assets

Location: `paper_assets/submission_bundle_no_render/`

This folder contains current source-data workbooks, plot-data tables,
launcher scripts, figure manifests, and model-setting summaries. Rendered
PNG/SVG/PDF files are intentionally excluded.

| Asset | Meaning |
| --- | --- |
| `source data.xlsx` | Journal-facing source data workbook. |
| `source_data_manifest.csv` | Mapping from manuscript figure panels to source files and sheets. |
| `FigXX/source_data/` | Per-figure source-data workbook folder. |
| `FigXX/plot_data/` | Plotting input tables used by figure launcher scripts. |
| `FigXX/scripts/` | Per-panel launcher scripts copied without protected render outputs. |
| `bundle_manifest.json` | Machine-readable figure/source-data package manifest. |
| `model_inference_settings_summary.md` | Traceable model invocation and parameter summary. |

## Controlled raw data

Private raw clinical records are not included. They are required only for
full raw-data reruns and should remain under controlled institutional access.
