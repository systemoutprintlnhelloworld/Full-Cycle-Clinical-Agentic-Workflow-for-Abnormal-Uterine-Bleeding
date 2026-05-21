# Code and Software Submission Checklist

This file is a repository-level working checklist for the journal code and
software submission form. It is not the journal PDF itself. Use it to fill
the official Code and Software Submission Checklist before submission or
peer-review file upload.

## Software identity

| Item | Current entry |
| --- | --- |
| Software name | Full-Cycle Clinical Agentic Workflow for Abnormal Uterine Bleeding |
| Repository | Private GitHub reviewer repository |
| Version/tag for submission | `v1.0-nm-submission` recommended before final upload |
| Primary language | Python |
| Operating system tested | Windows development environment; Linux/macOS expected for non-COM scripts |
| License | Restricted review license pending institutional approval |
| DOI/archive | To be minted after final code freeze if required |

## What the software does

This code package supports a full-cycle gynecological clinical decision
workflow replay and evaluation pipeline for abnormal uterine bleeding. It
contains code for workflow construction, environment-agent replay,
doctor-agent model invocation, LLM-as-Judge scoring, trajectory logging,
blind-review support, metric aggregation, source-data construction, figure
bundle assembly, and manuscript/source-data audit.

## Materials included in this repository

| Required material | Location | Status |
| --- | --- | --- |
| Source code | `code/`, `external/auto_eval_system_snapshot/` | Included |
| Version information | `README.md`, `docs/model_versions.md` | Included |
| README | `README.md` | Included |
| Installation instructions | `docs/installation.md` | Included |
| Demo instructions | `docs/demo.md`, `run_demo.sh`, `run_demo.ps1` | Included |
| Example data | `demo_data/` | Synthetic toy data included |
| Runtime notes | `docs/demo.md`, `docs/installation.md` | Included |
| Repository manifest | `MANIFEST.csv` | Included for copied source snapshot |
| License | `LICENSE` | Restricted review license pending final approval |
| Data dictionary | `docs/data_dictionary.md`, `spec/data-dictionary.md` | Included |
| Prompt inventory | `docs/prompt_inventory.md`, `prompts/` | Included |
| Model settings | `docs/model_versions.md`, `paper_assets/submission_bundle_no_render/model_inference_settings_summary.md` | Included |

## Materials intentionally excluded

- Patient-level raw clinical records.
- Hospital-internal credentials or deployment configuration.
- API keys, tokens, private keys, and provider account metadata.
- Bulky historical output folders, raw model logs, and protected render
  files.
- Source-project `FigXX/render/` outputs, which were explicitly protected
  during repository organization.

## Reviewer access notes

The offline demo does not call external LLM APIs and does not require
patient data. Full reproduction of model trajectories requires controlled
data access and valid OpenAI-compatible provider credentials. Any claim that
depends on controlled raw data should be checked against the controlled data
storage or the paper-facing source-data workbooks in `paper_assets/`.

## Pre-submission items still requiring author confirmation

- Final public license choice.
- Whether the reviewer repository should be archived with Zenodo or another
  DOI service before acceptance.
- Exact private reviewer URL and access policy to enter into the journal
  submission system.
- Whether API-provider-specific terms allow reviewer-side reruns, or whether
  cached outputs/source data should be used for review instead.
