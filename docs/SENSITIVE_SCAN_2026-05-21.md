# Sensitive Information Scan Summary

## Scope

Repository: `paper_submission_code_repo_2026-05-20`

Scan date: 2026-05-21

Scope was limited to git-tracked files. Ignored local files such as `.env`
and generated `outputs/` were not included.

## Checks performed

- Tracked file names matching `.env`, key, pem, token, credentials, secrets,
  and private-key naming patterns.
- Tracked paths containing `render/`.
- Text scan for high-risk literal secret patterns:
  - OpenAI-style `sk-...` keys.
  - GitHub `gh*_...` tokens.
  - Google `AIza...` keys.
  - Slack `xox...` tokens.
  - PEM private-key blocks.
  - Literal long `Bearer ...` tokens.

## Findings and fixes

Initial scan found high-risk literal OpenAI-style key patterns in the
auto-evaluation snapshot:

- `external/auto_eval_system_snapshot/auto_eval_system/config/channels.yaml`
- `external/auto_eval_system_snapshot/auto_eval_system/config/settings.py`
- `external/auto_eval_system_snapshot/docs/channel_config.md`

These were replaced with environment-variable placeholders or redacted
documentation placeholders. The code snapshot now uses environment variables
for the affected settings.

## Final scan result

- High-risk literal secret patterns: `0`.
- Tracked `render/` files: `0`.
- Tracked sensitive-name files: only `.env.example`, which is an intentional
  empty template and contains no real credential values.

## Residual notes

The repository still contains code and documentation that mention field names
such as `api_key`, `token`, and provider route names. These are expected for
configuration code and documentation. They were not counted as leaked secrets
unless a literal key/token value was present.

Before public release, repeat the scan after any additional file copy from the
working project.
