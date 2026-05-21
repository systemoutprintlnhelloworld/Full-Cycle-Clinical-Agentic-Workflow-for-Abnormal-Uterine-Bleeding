# Prompt Inventory

Prompt materials are included to make the doctor-agent, environment-agent,
and LLM-as-Judge logic auditable.

## Main prompt locations

| Location | Contents |
| --- | --- |
| `prompts/` | Post-hoc LLM metric prompts and canonical mapping notes. |
| `external/auto_eval_system_snapshot/docs/prompts_v2.md` | Workflow prompt descriptions from the auto-evaluation system snapshot. |
| `external/auto_eval_system_snapshot/auto_eval_system/prompts_v2.py` | Executable prompt definitions used by the workflow snapshot, if present. |
| `external/auto_eval_system_snapshot/experiments/no_check_d3_ablation/` | No-examination ablation workflow and prompt logic. |

## Prompt groups

| Group | Purpose |
| --- | --- |
| Doctor agent prompts | Generate stage-specific examination requests, diagnoses, plans, and follow-up decisions. |
| Environment agent logic | Reveal chronological case information and provide examination feedback. |
| Gate/judge prompts | Evaluate whether stage decisions remain aligned enough to continue. |
| Post-hoc LLM metric prompts | Score diagnosis proximity, plan quality, factual consistency, memory retention, reasoning quality, and related metrics. |
| Ablation prompts | Run D1-D3 workflow without active-examination feedback for sensitivity analysis. |

## Audit principle

Do not paraphrase prompts as evidence when exact prompts are needed. Use the
files above as the source of truth and cite the file path plus prompt name.
