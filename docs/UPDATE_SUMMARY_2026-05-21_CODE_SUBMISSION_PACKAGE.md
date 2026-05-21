# Code Submission Package Update Summary

## Objective

Update the private reviewer repository so it better matches journal code and
software submission expectations. The repository now provides a clear
reviewer entry point, installation instructions, synthetic demo data, an
offline demo, model/prompt documentation, a working code-submission checklist,
and an explicit license boundary.

## Added

- `CODE_AND_SOFTWARE_SUBMISSION_CHECKLIST.md`: working copy for filling the
  official journal checklist.
- `LICENSE`: restricted confidential-review license pending institutional
  approval.
- `requirements.txt` and `environment.yml`: baseline Python environment files.
- `.env.example`: safe credential template; real `.env` remains ignored.
- `demo_data/`: two synthetic toy AUB cases with no patient-level data.
- `scripts/run_offline_demo.py`, `run_demo.sh`, `run_demo.ps1`: offline demo
  that makes no API calls.
- `docs/installation.md`: pip/conda setup and credential boundary.
- `docs/demo.md`: demo instructions and runtime expectation.
- `docs/data_dictionary.md`: synthetic demo and source-data field overview.
- `docs/prompt_inventory.md`: prompt source map.
- `docs/model_versions.md`: tested model IDs and inference-setting entry
  points.
- `docs/reviewer_package_scope.md`: what is included/excluded and reproduction
  tiers.

## Updated

- `README.md`: promoted from organization note to reviewer package entry
  point, with quick start and code-submission material map.
- `REPRODUCIBILITY.md`: added reproduction tiers, demo order, and credential
  boundary.
- `.gitignore`: keeps `.env` ignored while allowing `.env.example`.

## Validation

- Ran `.\run_demo.ps1`.
- Demo completed successfully and wrote `outputs/demo_summary.json`.
- Verified tracked files still contain no `FigXX/render/` paths.
- Verified `.env.example` is not ignored.

## Submission interpretation

`GuidelinesCodePublication.pdf` should not be submitted as a filled form. It
is a guidance document. The actionable repository-side materials are the
checklist working copy, README, installation/demo docs, source code, example
data, model/prompt documentation, license boundary, and reviewer-safe code
package.

## Remaining author decisions

- Confirm final public license before acceptance or public archive.
- Decide whether to mint a DOI for the code snapshot.
- Decide whether reviewers should receive only this private GitHub repository
  or an additional ZIP/archive.
- Confirm whether any controlled cached outputs can be shared under the
  target journal's reviewer-confidential channel.
