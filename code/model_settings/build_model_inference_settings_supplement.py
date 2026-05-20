from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_BASE = PROJECT_ROOT / "work" / "paper_crosscheck"
EXTERNAL_SYSTEM_ROOT = Path(r"D:\研究生\项目\课题7-临床评测\自动测评系统")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def find_line(path: Path, needle: str) -> str:
    try:
        for index, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            if needle in line:
                return f"{rel(path)}:{index}"
    except FileNotFoundError:
        return f"{rel(path)}:missing"
    return f"{rel(path)}:not_found({needle})"


def load_yaml_without_secrets(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for channel in (data.get("channels") or {}).values():
        if isinstance(channel, dict) and "api_key" in channel:
            channel["api_key"] = "<redacted>"
    return data


def collect_channel_rows(config_path: Path, scope: str) -> list[dict[str, Any]]:
    data = load_yaml_without_secrets(config_path)
    channels = data.get("channels") or {}
    model_channels = data.get("model_channels") or {}
    rows: list[dict[str, Any]] = []
    for model, route in model_channels.items():
        route = route or {}
        primary = route.get("primary", "")
        fallback = route.get("fallback", []) or []
        candidate_channels = [primary] + list(fallback)
        for channel_name in candidate_channels:
            channel = channels.get(channel_name) or {}
            rows.append(
                {
                    "scope": scope,
                    "model_id": model,
                    "channel_name": channel_name,
                    "effective_model_name": (route.get("channel_map") or {}).get(channel_name, model),
                    "base_url": channel.get("base_url", ""),
                    "timeout_s": channel.get("timeout", ""),
                    "max_retries": channel.get("max_retries", ""),
                    "api_key": "<redacted>",
                    "evidence": rel(config_path),
                }
            )
    return rows


def build_settings_rows() -> list[dict[str, Any]]:
    ext = EXTERNAL_SYSTEM_ROOT
    main_py = ext / "main.py"
    workflow_py = ext / "auto_eval_system" / "modules" / "workflow.py"
    doctor_py = ext / "auto_eval_system" / "modules" / "doctor_agent.py"
    patient_py = ext / "auto_eval_system" / "modules" / "patient_description_agent.py"
    judge_py = ext / "auto_eval_system" / "modules" / "judge_agent.py"
    channel_py = ext / "auto_eval_system" / "utils" / "channel_manager.py"
    run_llm_tasks_py = PROJECT_ROOT / "src" / "run_llm_tasks.py"
    llm_runner_py = PROJECT_ROOT / "src" / "llm_judge_metrics" / "llm_runner.py"

    doctor_models = [
        "gemini-2.5-pro",
        "gpt-5-2025-08-07",
        "claude-opus-4-1-20250805-thinking",
        "deepseek-v3-1-think-250821",
        "grok-4",
    ]

    rows = [
        {
            "system_module": "Automated clinical evaluation system",
            "agent_task": "Doctor agent / tested model trajectories",
            "backbone_model": "; ".join(doctor_models),
            "model_role": "Tested doctor-model backbones selected by CLI",
            "provider_route": "Configured by model_channels in external channels.yaml",
            "api_style": "OpenAI-compatible chat.completions.create via channel fallback",
            "temperature": 0.5,
            "top_p": "Not specified (provider default)",
            "max_tokens": "Not specified (provider default)",
            "response_format": '{"type": "json_object"}',
            "timeout_retry": "Channel timeout/max_retries from channels.yaml; global fallback max_attempts=3 and retry_delay=2 s",
            "run_id_or_label": "No fixed run_label in main workflow; outputs organized by output/<center>/<model>",
            "status": "verified_from_code",
            "evidence": "; ".join(
                [
                    find_line(main_py, "AVAILABLE_MODELS"),
                    find_line(main_py, "model_aliases"),
                    find_line(workflow_py, "DoctorAgent(model_name=model_name)"),
                    find_line(doctor_py, "temperature=0.5"),
                    find_line(doctor_py, 'response_format={"type": "json_object"}'),
                    find_line(channel_py, "call_with_fallback"),
                ]
            ),
        },
        {
            "system_module": "Automated clinical evaluation system",
            "agent_task": "Patient description generation",
            "backbone_model": "gemini-2.5-pro",
            "model_role": "Generates patient-facing descriptions from structured clinical data",
            "provider_route": "call_with_fallback route for gemini-2.5-pro",
            "api_style": "OpenAI-compatible chat.completions.create via channel fallback",
            "temperature": 0.7,
            "top_p": "Not specified (provider default)",
            "max_tokens": "Not specified (provider default)",
            "response_format": "Not specified",
            "timeout_retry": "Channel timeout/max_retries from channels.yaml",
            "run_id_or_label": "Part of automated evaluation workflow",
            "status": "verified_from_code",
            "evidence": "; ".join(
                [
                    find_line(patient_py, 'model_name: str = "gemini-2.5-pro"'),
                    find_line(patient_py, "temperature=0.7"),
                ]
            ),
        },
        {
            "system_module": "Automated clinical evaluation system",
            "agent_task": "Patient description verification",
            "backbone_model": "gpt-4o",
            "model_role": "Verifies and corrects generated patient descriptions",
            "provider_route": "call_with_fallback route for gpt-4o",
            "api_style": "OpenAI-compatible chat.completions.create via channel fallback",
            "temperature": 0.1,
            "top_p": "Not specified (provider default)",
            "max_tokens": "Not specified (provider default)",
            "response_format": "Not specified",
            "timeout_retry": "Channel timeout/max_retries from channels.yaml",
            "run_id_or_label": "Part of patient-description generation step",
            "status": "verified_from_code",
            "evidence": "; ".join(
                [
                    find_line(patient_py, 'verify_model_name = "gpt-4o"'),
                    find_line(patient_py, "temperature=0.1"),
                ]
            ),
        },
        {
            "system_module": "Automated clinical evaluation system",
            "agent_task": "Workflow judge agent",
            "backbone_model": "gemini-2.5-pro",
            "model_role": "Automated evaluator for stage outputs and gate decisions",
            "provider_route": "call_with_fallback route for gemini-2.5-pro",
            "api_style": "OpenAI-compatible chat.completions.create via channel fallback",
            "temperature": 0.1,
            "top_p": "Not specified (provider default)",
            "max_tokens": "Not specified (provider default)",
            "response_format": '{"type": "json_object"}',
            "timeout_retry": "Judge wrapper max_retries=3; each call also uses channel fallback",
            "run_id_or_label": "Part of automated evaluation workflow",
            "status": "verified_from_code",
            "evidence": "; ".join(
                [
                    find_line(workflow_py, 'JudgeAgent(model_name="gemini-2.5-pro")'),
                    find_line(judge_py, "max_retries = 3"),
                    find_line(judge_py, "temperature=0.1"),
                    find_line(judge_py, 'response_format={"type": "json_object"}'),
                ]
            ),
        },
        {
            "system_module": "LLM-as-judge metrics system",
            "agent_task": "Post-hoc LLM metric judge tasks",
            "backbone_model": "gemini-2.5-pro by default; overrideable by --judge-model",
            "model_role": "Post-hoc evaluator for metric-specific prompts",
            "provider_route": "Default channel gala_api from project channels.yaml",
            "api_style": "HTTP POST to <base_url>/chat/completions",
            "temperature": 0.0,
            "top_p": "Not specified (provider default)",
            "max_tokens": "Not specified (provider default)",
            "response_format": "Not specified; JSON is parsed from model text output",
            "timeout_retry": "timeout from channels.yaml; attempts=1+max_retries; exponential backoff by error type",
            "run_id_or_label": "--run-id required by src/run_llm_tasks.py",
            "status": "verified_from_code",
            "evidence": "; ".join(
                [
                    find_line(run_llm_tasks_py, '--channel", default="gala_api"'),
                    find_line(run_llm_tasks_py, '--judge-model", default="gemini-2.5-pro"'),
                    find_line(run_llm_tasks_py, '--temperature", type=float, default=0.0'),
                    find_line(llm_runner_py, 'url = f"{channel.base_url}/chat/completions"'),
                    find_line(llm_runner_py, '"temperature": temperature'),
                    find_line(llm_runner_py, "def _retry_delay_s"),
                    find_line(llm_runner_py, "for attempt_idx in range(0, 1 + max_retries)"),
                ]
            ),
        },
    ]
    return rows


def build_unverified_rows() -> list[dict[str, str]]:
    return [
        {
            "item": "top_p",
            "status": "not_found_in_actual_request_code",
            "handling": "Report as Not specified (provider default); do not invent a value.",
        },
        {
            "item": "max_tokens / max_completion_tokens",
            "status": "not_found_in_actual_request_code",
            "handling": "Report as Not specified (provider default); do not invent a value.",
        },
        {
            "item": "official provider behind gateway",
            "status": "not_verifiable_from_local_code",
            "handling": "Report only gateway/channel route and base_url; avoid claiming official endpoint.",
        },
        {
            "item": "API version/date",
            "status": "not_recorded_in_payload_or_config",
            "handling": "Mark unavailable unless logs or provider dashboard records are supplied.",
        },
        {
            "item": "API key",
            "status": "sensitive_secret",
            "handling": "Never include in manuscript, supplement, workbook, or reports.",
        },
    ]


def write_markdown(out_path: Path, settings: pd.DataFrame, unverified: pd.DataFrame, channel_rows: pd.DataFrame) -> None:
    lines = [
        "# Model Invocation and Inference Settings Supplement",
        "",
        f"- Generated at: {now_iso()}",
        f"- Canonical manuscript: `D:/研究生/项目/课题7-临床评测/论文/论文大纲 (5.12）.docx`",
        "- Evidence principle: only values traceable to local code/configuration are reported.",
        "- Sensitive fields: API keys are intentionally redacted and must not be submitted.",
        "",
        "## Supplement-ready Table",
        "",
        settings.to_markdown(index=False),
        "",
        "## Items Not Explicitly Specified in Code",
        "",
        unverified.to_markdown(index=False),
        "",
        "## Provider Route Summary",
        "",
        channel_rows.to_markdown(index=False),
        "",
        "## Suggested Supplement Wording",
        "",
        (
            "All model calls were made through OpenAI-compatible chat-completion endpoints configured by channel "
            "routing files. Doctor-model trajectories used the five tested backbones listed in the table. The "
            "automated workflow judge used Gemini 2.5 Pro with low-temperature JSON output, whereas post-hoc "
            "LLM metric judging used Gemini 2.5 Pro by default at temperature 0.0. Parameters not explicitly "
            "set in the request payload, including top_p and max_tokens, should be reported as provider defaults."
        ),
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def build_outputs(run_id: str, output_base: Path) -> Path:
    out_dir = (output_base / run_id / "submission_bundle").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    settings_df = pd.DataFrame(build_settings_rows())
    unverified_df = pd.DataFrame(build_unverified_rows())
    channel_df = pd.DataFrame(
        collect_channel_rows(EXTERNAL_SYSTEM_ROOT / "auto_eval_system" / "config" / "channels.yaml", "automated_evaluation_system")
        + collect_channel_rows(PROJECT_ROOT / "channels.yaml", "llm_judge_metrics_system")
    )

    xlsx_path = out_dir / "model_inference_settings.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        settings_df.to_excel(writer, sheet_name="settings", index=False)
        channel_df.to_excel(writer, sheet_name="provider_routes", index=False)
        unverified_df.to_excel(writer, sheet_name="unverified_items", index=False)
        pd.DataFrame(
            [
                {"field": "generated_at", "value": now_iso()},
                {"field": "api_key_policy", "value": "redacted; not included"},
                {"field": "source_policy", "value": "local code/config only; no inferred hyperparameters"},
            ]
        ).to_excel(writer, sheet_name="meta", index=False)

    md_path = out_dir / "model_inference_settings_summary.md"
    write_markdown(md_path, settings_df, unverified_df, channel_df)
    return out_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build supplement-ready model invocation settings tables.")
    parser.add_argument("--run-id", required=True, help="paper_crosscheck run id containing submission_bundle")
    parser.add_argument("--output-base", default=str(DEFAULT_OUTPUT_BASE), help="Base output directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = build_outputs(args.run_id, Path(args.output_base))
    print(str(out_dir))


if __name__ == "__main__":
    main()
