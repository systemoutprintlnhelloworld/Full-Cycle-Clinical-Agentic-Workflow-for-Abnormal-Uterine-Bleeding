# Offline Demo

The offline demo is intentionally small and does not call LLM APIs. It shows
how a case record is represented, how stage-level outputs are summarized, and
how reviewer-safe synthetic data can be processed without patient records.

## Run on Unix-like shells

```bash
bash run_demo.sh
```

## Run on Windows PowerShell

```powershell
.\run_demo.ps1
```

## Expected output

The demo reads `demo_data/toy_case_001.json` and
`demo_data/toy_case_002.json`, prints a stage summary to the console, and
writes `outputs/demo_summary.json`.

Expected runtime is less than one minute on a standard laptop because no API
calls are made.

## What this demo does not do

- It does not reproduce the full 304-case, five-model paper run.
- It does not access private clinical records.
- It does not call model providers or consume API credits.
- It does not regenerate protected render files.

For paper-level provenance, inspect `paper_assets/submission_bundle_no_render/`
and its `*manifest*` files.
