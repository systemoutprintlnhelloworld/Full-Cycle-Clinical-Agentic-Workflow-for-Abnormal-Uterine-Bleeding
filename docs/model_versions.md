# Model Versions and Inference Settings

The detailed model invocation table is maintained in:

`paper_assets/submission_bundle_no_render/model_inference_settings_summary.md`

## Tested doctor-model backbones

- `gemini-2.5-pro`
- `gpt-5-2025-08-07`
- `claude-opus-4-1-20250805-thinking`
- `deepseek-v3-1-think-250821`
- `grok-4`

## Other workflow models

| Module | Model | Notes |
| --- | --- | --- |
| Patient description generation | `gemini-2.5-pro` | Verified from code snapshot. |
| Patient description verification | `gpt-4o` | Verified from code snapshot. |
| Workflow judge agent | `gemini-2.5-pro` | Low-temperature JSON output in workflow code. |
| Post-hoc LLM metric judge | `gemini-2.5-pro` by default | Overrideable by CLI in metric runner. |

## Parameters

Only locally traceable parameters should be reported. The current extracted
summary records temperature, response format, retry behavior, provider route,
and items not explicitly specified in request code. Parameters such as
`top_p` and `max_tokens` should remain "provider default" unless verified in
request payloads or provider logs.

## Sensitive fields

API keys and provider account details are excluded and must not be submitted.
Endpoint base URLs and route names are listed only to document the local
execution path.
