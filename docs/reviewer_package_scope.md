# Reviewer Package Scope

## Included

- Source code supporting workflow replay, LLM-as-Judge scoring, source-data
  construction, figure bundle assembly, manuscript audit, and model-setting
  extraction.
- Prompt files and metric specifications needed to understand the evaluation
  logic.
- Paper-facing source-data and plot-data assets without protected render
  files.
- Synthetic toy data and an offline demo that can be run without credentials.
- Manifest and protection notes documenting what was copied and what was
  excluded.

## Excluded

- Patient-level raw clinical data.
- API keys, provider credentials, private endpoint tokens, and `.env` files.
- Hospital-internal deployment configuration.
- Historical output archives, logs, caches, and bulky raw model outputs.
- Protected `FigXX/render/` files.

## Reproduction tiers

| Tier | What reviewers can do | Requirements |
| --- | --- | --- |
| Offline package check | Inspect code, prompts, specs, manifests, source data, and run toy demo. | This repository only. |
| Source-data audit | Trace figure/source-data relationships and inspect bundled workbooks. | This repository only. |
| Controlled rerun | Rerun workflow and metrics on raw clinical inputs. | Controlled data access plus valid API credentials. |
| Full paper regeneration | Rebuild all trajectories, scores, source data, and figures. | Controlled data, credentials, and source-project runtime environment. |
