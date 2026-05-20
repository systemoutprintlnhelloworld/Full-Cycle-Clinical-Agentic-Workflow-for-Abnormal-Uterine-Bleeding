from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml
from dotenv import load_dotenv
from openpyxl import load_workbook
from openpyxl.styles import PatternFill

from .discovery import discover_datasets
from .excel_export import ExcelSheetSpec, export_metrics_source_data_xlsx
from .fields import build_d3_decision_fields
from .ingest import load_dataset
from .status import detect_d1_decision_anomaly, detect_d1_skipped_to_d2


@dataclass(frozen=True)
class ChannelConfig:
    name: str
    base_url: str
    api_key: str
    timeout_s: int
    max_retries: int


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _inputs_hash(task: dict[str, Any]) -> str:
    payload = {
        "task": task.get("task"),
        "task_id": task.get("task_id"),
        "prompt_template": task.get("prompt_template"),
        "inputs": task.get("inputs"),
    }
    return _sha256_text(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def _resolve_env_vars(s: str) -> str:
    # Supports "${VAR}" only.
    if not isinstance(s, str):
        return str(s)
    if s.startswith("${") and s.endswith("}") and len(s) > 3:
        key = s[2:-1]
        v = os.getenv(key)
        if not v:
            raise RuntimeError(f"Missing env var {key!r} (required by channels.yaml)")
        return v
    return s


def load_channel_config(project_root: Path, channel_name: str) -> ChannelConfig:
    load_dotenv(project_root / ".env", override=False)
    cfg = yaml.safe_load((project_root / "channels.yaml").read_text(encoding="utf-8"))
    channels = (cfg or {}).get("channels") or {}
    if channel_name not in channels:
        raise KeyError(f"Channel {channel_name!r} not found in channels.yaml")
    c = channels[channel_name] or {}
    base_url = str(c.get("base_url", "")).strip().rstrip("/")
    api_key = _resolve_env_vars(str(c.get("api_key", "")).strip())
    timeout_s = int(c.get("timeout", 60))
    max_retries = int(c.get("max_retries", 2))
    if not base_url:
        raise RuntimeError(f"Channel {channel_name!r} missing base_url")
    if not api_key:
        raise RuntimeError(f"Channel {channel_name!r} missing api_key")
    return ChannelConfig(name=channel_name, base_url=base_url, api_key=api_key, timeout_s=timeout_s, max_retries=max_retries)


def _chat_completions(
    channel: ChannelConfig,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
) -> tuple[dict[str, Any], str]:
    url = f"{channel.base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {channel.api_key}", "Content-Type": "application/json"}

    resp = requests.post(url, headers=headers, json=payload, timeout=channel.timeout_s)
    resp.raise_for_status()
    data = resp.json()
    content = ""
    try:
        content = str(data["choices"][0]["message"]["content"])
    except Exception:
        content = ""
    return data, content


def _extract_first_json_object(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """
    Best-effort extraction of the first JSON object from text (handles code fences).
    Returns (obj, error).
    """
    if not text:
        return None, "empty_response"
    s = text.strip()
    # Fast path
    if s.startswith("{") and s.endswith("}"):
        try:
            return json.loads(s), None
        except Exception as e:
            return None, f"json_load_failed:{e}"

    # Strip common code fences
    if s.startswith("```"):
        parts = s.split("```")
        # try each fenced block
        for p in parts:
            p2 = p.strip()
            if p2.startswith("{") and p2.endswith("}"):
                try:
                    return json.loads(p2), None
                except Exception:
                    continue

    # Bracket matching
    start = s.find("{")
    if start < 0:
        return None, "no_json_object_found"
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = s[start : i + 1]
                try:
                    return json.loads(candidate), None
                except Exception as e:
                    return None, f"json_load_failed:{e}"
    return None, "unterminated_json_object"


def _normalize_issue_tags(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        s = str(x).strip().lower()
        if s:
            out.append(s)
    return out


def _validate_response_json(task_name: str, parsed: dict[str, Any]) -> str | None:
    if task_name == "llm.fact_consistency_and_missing":
        if "consistency_score" not in parsed:
            return "invalid_response:missing_consistency_score"
        if "missing_count" not in parsed or "missing_rate" not in parsed:
            return "invalid_response:missing_missing_metrics"
        return None

    if task_name == "llm.memory_retention":
        if "retention_rate" not in parsed or "utilization_rate" not in parsed:
            return "invalid_response:missing_memory_scores"
        return None

    if task_name == "llm.cross_stage_consistency":
        findings = parsed.get("stage_findings")
        if not isinstance(findings, list):
            return "invalid_response:missing_stage_findings"
        want = {"D1", "D2", "D3", "D4"}
        got = {str((it or {}).get("stage", "")).strip().upper() for it in findings if isinstance(it, dict)}
        if not want.issubset(got):
            return "invalid_response:stage_findings_incomplete"
        return None

    return None


def _load_tasks_jsonl(path: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            tasks.append(json.loads(ln))
    return tasks


def _load_done_index(results_jsonl: Path) -> set[tuple[str, str]]:
    done: set[tuple[str, str]] = set()
    if not results_jsonl.exists():
        return done
    with results_jsonl.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except Exception:
                continue
            task_id = str(r.get("task_id", "")).strip()
            inputs_hash = str(r.get("inputs_hash", "")).strip()
            # Only consider SUCCESS as done. Failed rows should be retried in the next run.
            err = r.get("error")
            ok = (err is None) or (str(err).strip() == "")
            if task_id and inputs_hash and ok:
                done.add((task_id, inputs_hash))
    return done


def _write_clean_results_jsonl(results_jsonl: Path) -> Path:
    """
    Create a sanitized JSONL file by dropping unreadable/invalid lines.
    This avoids downstream decode errors after concurrent writes.
    """
    clean_path = results_jsonl.with_name(f"{results_jsonl.stem}.clean.jsonl")
    if not results_jsonl.exists():
        return clean_path
    with results_jsonl.open("rb") as src, clean_path.open("w", encoding="utf-8") as dst:
        for bline in src:
            try:
                line = bline.decode("utf-8").strip()
            except UnicodeDecodeError:
                line = bline.decode("utf-8", "ignore").strip()
            if not line:
                continue
            try:
                json.loads(line)
            except Exception:
                continue
            dst.write(line + "\n")
    return clean_path


def _load_all_results(results_jsonl: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not results_jsonl.exists():
        return rows
    with results_jsonl.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    return rows


def run_llm_tasks(
    project_root: Path,
    run_id: str,
    channel_name: str,
    judge_model: str,
    task_files: list[str] | None,
    task_filter: list[str] | None,
    max_tasks: int,
    sample_cases_per_center: int,
    require_all_models: bool,
    case_sampling_strategy: str,
    sample_per_group: int,
    max_workers: int,
    temperature: float,
    progress_interval_s: int = 0,
    stop_when_plateau: int = 0,
) -> Path:
    """
    Execute LLM judge tasks for a given metrics `run_id`:
    - Reads tasks from `work/<run_id>/llm_tasks/*.jsonl`
    - Writes JSONL results to `work/<run_id>/llm_results/<judge_model>__<channel>.jsonl`
    - Exports a human-review Excel to `outputs/<run_id>/summary/llm_results_<judge_model>.xlsx`
    Returns the Excel path.
    """
    work_dir = (project_root / "work" / run_id).resolve()
    outputs_dir = (project_root / "outputs" / run_id / "summary").resolve()
    outputs_dir.mkdir(parents=True, exist_ok=True)

    tasks_dir = work_dir / "llm_tasks"
    if not tasks_dir.exists():
        raise FileNotFoundError(f"Tasks dir not found: {tasks_dir}")

    paths = []
    if task_files:
        for f in task_files:
            paths.append((tasks_dir / f).resolve())
    else:
        paths = sorted(tasks_dir.glob("*.jsonl"))

    all_tasks: list[dict[str, Any]] = []
    for p in paths:
        if p.exists():
            all_tasks.extend(_load_tasks_jsonl(p))

    if task_filter:
        allowed = set(task_filter)
        all_tasks = [t for t in all_tasks if str(t.get("task", "")).strip() in allowed]

    # Default cost control: keep only tasks with non-empty prompt.
    tasks_full = [t for t in all_tasks if str(t.get("prompt", "")).strip()]

    def _stable_case_order(case_ids: list[str]) -> list[str]:
        if case_sampling_strategy == "first":
            return sorted(case_ids)
        # stable_hash: deterministic pseudo-random order
        return sorted(case_ids, key=lambda cid: hashlib.sha256(cid.encode("utf-8")).hexdigest())

    # Optional: pick common case_ids per center so that the same cases can be compared across models.
    if sample_cases_per_center and sample_cases_per_center > 0:
        # Determine models per center in the current task set.
        center_models: dict[str, set[str]] = {}
        coverage: dict[tuple[str, str], set[str]] = {}
        for t in tasks_full:
            center = str(t.get("center", "")).strip()
            model = str(t.get("model", "")).strip()
            case_id = str(t.get("case_id", "")).strip()
            if not center or not model or not case_id:
                continue
            center_models.setdefault(center, set()).add(model)
            coverage.setdefault((center, case_id), set()).add(model)

        selected_by_center: dict[str, set[str]] = {}
        for center, models in center_models.items():
            models_set = set(models)
            candidates = [cid for (c, cid), _ in coverage.items() if c == center]
            if require_all_models:
                candidates = [cid for cid in candidates if models_set.issubset(coverage.get((center, cid), set()))]
                # If strict intersection is empty, fall back to max-overlap sampling to avoid zero samples.
                if not candidates:
                    candidates = [cid for (c, cid), _ in coverage.items() if c == center]

            def _case_sort_key(cid: str) -> tuple[int, str]:
                cov = len(coverage.get((center, cid), set()))
                if case_sampling_strategy == "first":
                    return (-cov, cid)
                return (-cov, hashlib.sha256(cid.encode("utf-8")).hexdigest())

            ordered = sorted(set(candidates), key=_case_sort_key)
            selected_by_center[center] = set(ordered[:sample_cases_per_center])

        tasks_full = [
            t
            for t in tasks_full
            if str(t.get("center", "")).strip() in selected_by_center
            and str(t.get("case_id", "")).strip() in selected_by_center[str(t.get("center", "")).strip()]
        ]

    channel = load_channel_config(project_root, channel_name=channel_name)

    results_dir = work_dir / "llm_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    results_jsonl = results_dir / f"{judge_model}__{channel_name}.jsonl"
    done = _load_done_index(results_jsonl)

    # Keep only pending tasks so repeated runs can keep making progress.
    all_tasks = []
    for t in tasks_full:
        task_id = str(t.get("task_id", "")).strip()
        if not task_id:
            continue
        ih = _inputs_hash(t)
        if (task_id, ih) in done:
            continue
        all_tasks.append(t)

    # Deterministic execution order (avoid being stuck on one center because of file order).
    def _stable_task_key(t: dict[str, Any]) -> str:
        s = "|".join(
            [
                str(t.get("center", "")).strip(),
                str(t.get("case_id", "")).strip(),
                str(t.get("model", "")).strip(),
                str(t.get("stage", "")).strip(),
                str(t.get("task", "")).strip(),
                str(t.get("task_id", "")).strip(),
            ]
        )
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    all_tasks = sorted(all_tasks, key=_stable_task_key)

    # Optional: sample across (center, doc_model, task) to cover multiple groups.
    if sample_per_group and sample_per_group > 0:
        sampled: list[dict[str, Any]] = []
        counts: dict[tuple[str, str, str, str], int] = {}
        for t in all_tasks:
            key = (
                str(t.get("center", "")).strip(),
                str(t.get("model", "")).strip(),
                str(t.get("stage", "")).strip(),
                str(t.get("task", "")).strip(),
            )
            if counts.get(key, 0) >= sample_per_group:
                continue
            sampled.append(t)
            counts[key] = counts.get(key, 0) + 1
        all_tasks = sampled

    # Cap
    if max_tasks > 0:
        all_tasks = all_tasks[:max_tasks]

    written_rows: list[dict[str, Any]] = []
    write_lock = threading.Lock()
    total_tasks = len(all_tasks)
    start_ts = time.time()
    prog_done = 0
    prog_ok = 0
    prog_fail = 0

    def _print_progress() -> None:
        if total_tasks <= 0:
            return
        elapsed = time.time() - start_ts
        avg = (elapsed / prog_done) if prog_done else 0.0
        eta = avg * (total_tasks - prog_done) if prog_done else 0.0
        msg = f"\r进度 {prog_done}/{total_tasks} | 成功 {prog_ok} | 失败 {prog_fail} | 用时 {elapsed:.1f}s | 预计剩余 {eta:.1f}s"
        print(msg, end="", flush=True)

    def _snapshot_remaining() -> int:
        done_now = _load_done_index(results_jsonl)
        remaining = 0
        for t in tasks_full:
            task_id = str(t.get("task_id", "")).strip()
            if not task_id:
                continue
            ih = _inputs_hash(t)
            if (task_id, ih) in done_now:
                continue
            remaining += 1
        return remaining

    last_snapshot_ts = time.time()
    plateau_count = 0
    last_remaining = None

    def _retry_delay_s(error: str, attempt_idx: int) -> float:
        # Exponential backoff by error type; return <=0 to skip further retries.
        err = (error or "").lower()
        if "httperror:403" in err:
            return 0.0
        if "httperror:429" in err:
            base = 10.0
        elif "readtimeout" in err or "read timed out" in err:
            base = 8.0
        elif "sslerror" in err:
            base = 6.0
        else:
            base = 3.0
        return base * (2**attempt_idx)

    def _run_one(task: dict[str, Any]) -> dict[str, Any]:
        task_id = str(task.get("task_id", "")).strip()
        ih = _inputs_hash(task)
        prompt = str(task.get("prompt", ""))
        messages = [{"role": "user", "content": prompt}]

        started = time.time()
        raw: dict[str, Any] | None = None
        content = ""
        error: str | None = None
        parsed: dict[str, Any] | None = None
        error_history: list[str] = []

        # Robust retry with backoff; do NOT mark as done unless success.
        max_retries = max(0, int(channel.max_retries))
        for attempt_idx in range(0, 1 + max_retries):
            raw = None
            content = ""
            error = None
            parsed = None
            try:
                raw, content = _chat_completions(channel=channel, model=judge_model, messages=messages, temperature=temperature)
                parsed, err = _extract_first_json_object(content)
                if err:
                    error = err
                elif isinstance(parsed, dict):
                    v_err = _validate_response_json(str(task.get("task", "")).strip(), parsed)
                    if v_err:
                        error = v_err
                else:
                    error = "invalid_response:not_json_object"
            except Exception as e:
                error = f"request_failed:{type(e).__name__}:{e}"

            if error is None:
                break

            error_history.append(error)
            if attempt_idx < max_retries:
                delay_s = _retry_delay_s(error, attempt_idx)
                if delay_s <= 0:
                    break
                time.sleep(delay_s)
                continue
            break

        elapsed = time.time() - started

        return {
            "task": task.get("task"),
            "task_id": task_id,
            "center": task.get("center"),
            "doc_model": task.get("model"),
            "case_id": task.get("case_id"),
            "stage": task.get("stage"),
            "prompt_template": task.get("prompt_template"),
            "inputs": task.get("inputs"),
            "inputs_hash": ih,
            "prompt": prompt,
            "judge_model": judge_model,
            "channel": channel_name,
            "base_url": channel.base_url,
            "temperature": temperature,
            # attempts_made = failures + (1 if success else 0)
            "attempts": len(error_history) + (1 if error is None else 0),
            "error_history": error_history,
            "elapsed_s": round(elapsed, 3),
            "response_text": content,
            "response_json": parsed,
            "error": error,
            "raw_api_response": raw,
        }

    with results_jsonl.open("a", encoding="utf-8") as out:
        if max_workers is None or max_workers <= 1:
            for task in all_tasks:
                task_id = str(task.get("task_id", "")).strip()
                if not task_id:
                    continue
                rec = _run_one(task)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written_rows.append(rec)
                if rec.get("error") in (None, ""):
                    done.add((str(rec.get("task_id", "")).strip(), str(rec.get("inputs_hash", "")).strip()))
                    prog_ok += 1
                else:
                    prog_fail += 1
                prog_done += 1
                _print_progress()
                if progress_interval_s and (time.time() - last_snapshot_ts) >= progress_interval_s:
                    remaining = _snapshot_remaining()
                    print(f"\n[快照] 剩余任务 {remaining} | 成功 {prog_ok} | 失败 {prog_fail}")
                    if last_remaining is not None and remaining >= last_remaining:
                        plateau_count += 1
                    else:
                        plateau_count = 0
                    last_remaining = remaining
                    last_snapshot_ts = time.time()
                    if stop_when_plateau and plateau_count >= stop_when_plateau:
                        print("\n[停止] 剩余未下降，触发 stop_when_plateau")
                        return export_llm_results_xlsx(
                            project_root=project_root,
                            run_id=run_id,
                            channel_name=channel_name,
                            judge_model=judge_model,
                        )
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = [ex.submit(_run_one, task) for task in all_tasks if str(task.get("task_id", "")).strip()]
                for fut in as_completed(futures):
                    rec = fut.result()
                    with write_lock:
                        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        written_rows.append(rec)
                        if rec.get("error") in (None, ""):
                            done.add((str(rec.get("task_id", "")).strip(), str(rec.get("inputs_hash", "")).strip()))
                            prog_ok += 1
                        else:
                            prog_fail += 1
                        prog_done += 1
                        _print_progress()
                        if progress_interval_s and (time.time() - last_snapshot_ts) >= progress_interval_s:
                            remaining = _snapshot_remaining()
                            print(f"\n[快照] 剩余任务 {remaining} | 成功 {prog_ok} | 失败 {prog_fail}")
                            if last_remaining is not None and remaining >= last_remaining:
                                plateau_count += 1
                            else:
                                plateau_count = 0
                            last_remaining = remaining
                            last_snapshot_ts = time.time()
                            if stop_when_plateau and plateau_count >= stop_when_plateau:
                                print("\n[停止] 剩余未下降，触发 stop_when_plateau")
                                return export_llm_results_xlsx(
                                    project_root=project_root,
                                    run_id=run_id,
                                    channel_name=channel_name,
                                    judge_model=judge_model,
                                )
    if total_tasks > 0:
        print("")

    # Clean JSONL to avoid decode issues from concurrent writes.
    _write_clean_results_jsonl(results_jsonl)

    # Export a single review workbook filtered by the CURRENT task spec (work/<run_id>/llm_tasks),
    # independent of which subset we ran in this invocation.
    return export_llm_results_xlsx(
        project_root=project_root,
        run_id=run_id,
        channel_name=channel_name,
        judge_model=judge_model,
    )


def _parse_model_from_stem(stem: str, suffix: str) -> str:
    name = stem.replace("Evaluation_Summary_", "")
    if suffix in name:
        name = name.replace(suffix, "")
    return name


def _load_special_case_map(project_root: Path) -> dict[tuple[str, str], set[str]]:
    data_root = project_root / "data"
    special_map: dict[tuple[str, str], set[str]] = {}
    for center_dir in data_root.iterdir():
        if not center_dir.is_dir():
            continue
        center = center_dir.name
        doc_dir = center_dir / "doc agent"
        if not doc_dir.exists():
            continue
        for path in doc_dir.glob("Evaluation_Summary_*_CN_Parsed.xlsx"):
            model = _parse_model_from_stem(path.stem, "_CN_Parsed")
            special_cases: set[str] = set()
            special_sheet_present = False
            try:
                xl = pd.ExcelFile(path)
                for sheet in ["D2_Admission_Decision_特殊D1", "D1_Outpatient_Loop_特殊D1"]:
                    if sheet not in xl.sheet_names:
                        continue
                    special_sheet_present = True
                    df_special = xl.parse(sheet)
                    if df_special.empty:
                        continue
                    cid_col = df_special.columns[0]
                    ids = df_special[cid_col].dropna().astype(str).str.strip().tolist()
                    special_cases.update({cid for cid in ids if cid})
            except Exception:
                special_cases = set()
            if not special_sheet_present and not special_cases:
                try:
                    d1_loop = pd.read_excel(path, sheet_name="D1_Outpatient_Loop")
                    d1_dec = pd.read_excel(path, sheet_name="D1_Outpatient_Decision")
                    d2_loop = pd.read_excel(path, sheet_name="D2_Admission_Loop")
                    d2_dec = pd.read_excel(path, sheet_name="D2_Admission_Decision")
                except Exception:
                    continue
                doc_sheets = {
                    "D1_Outpatient_Loop": d1_loop,
                    "D1_Outpatient_Decision": d1_dec,
                    "D2_Admission_Loop": d2_loop,
                    "D2_Admission_Decision": d2_dec,
                }
                special_cases = detect_d1_skipped_to_d2(doc_sheets)
            special_map[(center, model)] = {str(cid).strip() for cid in special_cases if str(cid).strip()}
    return special_map


def _load_gate3_fail_keys(project_root: Path) -> set[tuple[str, str, str]]:
    data_root = project_root / "data"
    fail_keys: set[tuple[str, str, str]] = set()
    for center_dir in data_root.iterdir():
        if not center_dir.is_dir():
            continue
        center = center_dir.name
        judge_dir = center_dir / "judge agent"
        if not judge_dir.exists():
            continue
        for path in judge_dir.glob("Evaluation_Summary_*_CN_Judge_Parsed.xlsx"):
            model = _parse_model_from_stem(path.stem, "_CN_Judge_Parsed")
            try:
                d3 = pd.read_excel(path, sheet_name="D3_Surgery_Decision")
            except Exception:
                continue
            if d3.empty or "Gate3_不通过标记" not in d3.columns:
                continue
            cid_col = d3.columns[0]
            gate3 = pd.to_numeric(d3["Gate3_不通过标记"], errors="coerce")
            for cid in d3.loc[gate3 == 1, cid_col].astype(str).str.strip().tolist():
                if cid and cid.lower() != "nan":
                    fail_keys.add((center, model, cid))
    return fail_keys


def _flatten_special_keys(special_map: dict[tuple[str, str], set[str]]) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for (center, model), ids in special_map.items():
        for cid in ids:
            if cid:
                keys.add((str(center).strip(), str(model).strip(), str(cid).strip()))
    return keys


def _split_llm_detail_by_special_and_gate3(
    df: pd.DataFrame,
    special_keys: set[tuple[str, str, str]],
    gate3_keys: set[tuple[str, str, str]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return df, pd.DataFrame(), pd.DataFrame()
    required = {"中心", "被评测模型", "病例ID", "阶段"}
    if not required.issubset(set(df.columns)):
        return df, pd.DataFrame(), pd.DataFrame()
    keys = list(
        zip(
            df["中心"].astype(str).str.strip(),
            df["被评测模型"].astype(str).str.strip(),
            df["病例ID"].astype(str).str.strip(),
        )
    )
    is_special = pd.Series([k in special_keys for k in keys], index=df.index)
    is_gate3 = pd.Series([k in gate3_keys for k in keys], index=df.index)
    is_d2 = df["阶段"].astype(str).eq("D2_Admission_Decision")
    is_d4 = df["阶段"].astype(str).eq("D4_Rehab_Plan")
    special_mask = is_special & is_d2
    gate3_mask = is_gate3 & is_d4
    special_df = df.loc[special_mask].copy()
    gate3_df = df.loc[gate3_mask].copy()
    normal_df = df.loc[~(special_mask | gate3_mask)].copy()
    return normal_df, special_df, gate3_df


def export_llm_results_xlsx(
    project_root: Path,
    run_id: str,
    channel_name: str,
    judge_model: str,
) -> Path:
    """
    Export existing cached LLM results JSONL to an Excel review file (no API calls).

    - Reads: `work/<run_id>/llm_results/<judge_model>__<channel_name>.jsonl`
    - Writes: `outputs/<run_id>/summary/llm_results_<judge_model>__<channel_name>.xlsx`
    """
    work_dir = (project_root / "work" / run_id).resolve()
    outputs_dir = (project_root / "outputs" / run_id / "summary").resolve()
    outputs_dir.mkdir(parents=True, exist_ok=True)

    results_jsonl = (work_dir / "llm_results" / f"{judge_model}__{channel_name}.jsonl").resolve()
    if not results_jsonl.exists():
        raise FileNotFoundError(f"LLM results not found: {results_jsonl}")
    clean_jsonl = results_jsonl.with_name(f"{results_jsonl.stem}.clean.jsonl")
    if clean_jsonl.exists():
        results_jsonl = clean_jsonl

    export_rows = _load_all_results(results_jsonl)
    if not export_rows:
        raise RuntimeError(f"No LLM results to export: {results_jsonl}")

    # Filter to current task spec when possible (avoid exporting stale tasks that are no longer generated).
    tasks_dir = work_dir / "llm_tasks"
    current_keys: set[tuple[str, str]] = set()
    if tasks_dir.exists():
        for p in sorted(tasks_dir.glob("*.jsonl")):
            try:
                for t in _load_tasks_jsonl(p):
                    task_id = str(t.get("task_id", "")).strip()
                    if not task_id:
                        continue
                    current_keys.add((task_id, _inputs_hash(t)))
            except Exception:
                continue
    if current_keys:
        filtered = [
            r
            for r in export_rows
            if (str(r.get("task_id", "")).strip(), str(r.get("inputs_hash", "")).strip()) in current_keys
        ]
        if not filtered:
            raise RuntimeError("No LLM results matched current llm_tasks spec; run tasks or export without filtering by regenerating tasks.")
        # Preserve rationale quality rows if they exist but were filtered out by inputs_hash drift.
        if not any(str(r.get("task")) == "llm.rationale_quality" for r in filtered):
            fallback = [r for r in export_rows if str(r.get("task")) == "llm.rationale_quality"]
            filtered.extend(fallback)
        export_rows = filtered

    special_keys = _flatten_special_keys(_load_special_case_map(project_root))
    gate3_keys: set[tuple[str, str, str]] = _load_gate3_fail_keys(project_root)

    input_keys = [
        "gt_diagnosis_text",
        "ai_diagnosis_list_text",
        "ai_diagnosis_text",
        "ai_diagnosis_rationale",
        "strictness",
        "gt_facts",
        "gt_checks_text",
        "multi_stage_summaries",
        "prior_stage_summary",
        "current_stage_review",
        "ai_rationale_text",
        "ai_summary_or_review",
        "gt_plan_text",
        "ai_plan_text",
        "ai_plan_rationale",
        "gt_final_diagnosis",
        "ai_final_diagnosis",
        "stage_label",
        "ai_stage_diagnosis",
        "ai_stage_diagnosis_rationale",
        "gt_rehab_plan",
        "gt_followup_plan",
        "ai_rehab_plan",
        "ai_rehab_rationale",
        "ai_followup_plan",
        "ai_followup_rationale",
        "context_facts",
        # legacy keys (v1)
        "ai_requested_checks",
        "unmatched_checks",
        # current keys (v2)
        "ai_requested_checks_all",
        "judge_matched_checks_all",
        "judge_unmatched_checks_all",
        "unmatched_checks_to_judge",
        "prior_matched_checks",
        "ai_rationale",
        "prompt_sha256",
    ]
    task_rows: list[dict[str, Any]] = []
    for r in export_rows:
        inputs = r.get("inputs") if isinstance(r.get("inputs"), dict) else {}
        row = {
            "task": r.get("task"),
            "task_id": r.get("task_id"),
            "center": r.get("center"),
            "doc_model": r.get("doc_model"),
            "case_id": r.get("case_id"),
            "stage": r.get("stage"),
            "judge_model": r.get("judge_model"),
            "channel": r.get("channel"),
            "elapsed_s": r.get("elapsed_s"),
            "error": r.get("error"),
            "prompt_template": r.get("prompt_template"),
            "prompt": r.get("prompt"),
            "response_text": r.get("response_text"),
            "response_json": json.dumps(r.get("response_json") or {}, ensure_ascii=False),
            "inputs_json": json.dumps(inputs or {}, ensure_ascii=False),
        }
        for k in input_keys:
            row[f"input__{k}"] = inputs.get(k)
        task_rows.append(row)
    df_tasks = pd.DataFrame(task_rows)
    if not df_tasks.empty:
        df_tasks = df_tasks.rename(
            columns={
                "task": "任务类型",
                "task_id": "任务ID",
                "center": "中心",
                "doc_model": "被评测模型",
                "case_id": "病例ID",
                "stage": "阶段",
                "judge_model": "裁判模型",
                "channel": "渠道",
                "elapsed_s": "耗时(秒)",
                "error": "错误",
                "prompt_template": "提示词模板",
                "prompt": "提示词(完整)",
                "response_text": "模型原始回答",
                "response_json": "解析JSON(提取)",
                "inputs_json": "输入(原始JSON)",
                "input__gt_diagnosis_text": "输入_GT诊断文本",
                "input__ai_diagnosis_list_text": "输入_AI诊断列表",
                "input__ai_diagnosis_text": "输入_AI诊断文本",
                "input__ai_diagnosis_rationale": "输入_AI诊断思维",
                "input__strictness": "输入_严格度",
                "input__gt_facts": "输入_GT病历事实",
                "input__gt_checks_text": "输入_GT检查原文",
                "input__ai_requested_checks": "输入_AI请求检查列表(旧)",
                "input__unmatched_checks": "输入_未匹配检查列表(旧)",
                "input__ai_requested_checks_all": "输入_AI提出检查(全量)",
                "input__judge_matched_checks_all": "输入_裁判判定匹配检查(全量)",
                "input__judge_unmatched_checks_all": "输入_裁判判定未匹配检查(全量)",
                "input__unmatched_checks_to_judge": "输入_需判定合理性的未匹配检查",
                "input__prior_matched_checks": "输入_前序已匹配检查",
                "input__ai_rationale": "输入_AI理由/思维",
                "input__ai_rationale_text": "输入_AI理由/思维(聚合)",
                "input__ai_summary_or_review": "输入_AI汇总/回顾",
                "input__gt_plan_text": "输入_GT方案文本",
                "input__ai_plan_text": "输入_AI方案文本",
                "input__ai_plan_rationale": "输入_AI方案思维/依据",
                "input__gt_final_diagnosis": "输入_GT最终诊断",
                "input__ai_final_diagnosis": "输入_AI最终诊断",
                "input__stage_label": "输入_阶段标签",
                "input__ai_stage_diagnosis": "输入_AI阶段诊断",
                "input__ai_stage_diagnosis_rationale": "输入_AI阶段诊断思维",
                "input__gt_rehab_plan": "输入_GT康复计划",
                "input__gt_followup_plan": "输入_GT随访计划",
                "input__ai_rehab_plan": "输入_AI康复计划",
                "input__ai_rehab_rationale": "输入_AI康复思维/依据",
                "input__ai_followup_plan": "输入_AI随访计划",
                "input__ai_followup_rationale": "输入_AI随访思维/依据",
                "input__context_facts": "输入_上下文事实(可选)",
                "input__prompt_sha256": "输入_提示词版本(hash)",
            }
        )
        # Keep the task sheet compact: drop per-field input columns (raw JSON is retained).
        drop_cols = [c for c in df_tasks.columns if str(c).startswith("输入_")]
        if drop_cols:
            df_tasks = df_tasks.drop(columns=drop_cols)

    def _merge_inputs(inputs: dict[str, Any], pairs: list[tuple[str, str]]) -> str:
        parts: list[str] = []
        for label, key in pairs:
            v = inputs.get(key)
            if v is None:
                continue
            s = str(v).strip()
            if not s:
                continue
            parts.append(f"{label}:\n{s}")
        return "\n\n".join(parts)

    def _sort_df(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        sort_cols = [c for c in ["中心", "被评测模型", "病例ID", "阶段"] if c in df.columns]
        if sort_cols:
            return df.sort_values(sort_cols, na_position="last")
        return df

    def _dedup_df(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        return df.drop_duplicates().copy()

    def _empty_like(df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(columns=list(df.columns))

    def _build_summary_df(df: pd.DataFrame, group_cols: list[str], mean_cols: list[str]) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        work = df.copy()
        numeric_cols: list[str] = []
        for c in mean_cols:
            if c in work.columns:
                work[c] = pd.to_numeric(work[c], errors="coerce")
                numeric_cols.append(c)
        if not numeric_cols:
            cols = group_cols + ["样本数"]
            return pd.DataFrame(columns=cols)
        summary = work.groupby(group_cols, as_index=False)[numeric_cols].mean()
        summary["样本数"] = work.groupby(group_cols).size().values
        return summary

    def _collect_special_d1_triplets() -> set[tuple[str, str, str]]:
        data_root = (project_root / "data").resolve()
        special: set[tuple[str, str, str]] = set()
        try:
            discovery = discover_datasets(data_root)
            for ds in discovery.datasets:
                loaded = load_dataset(ds)
                d1 = loaded.doc_sheets.get("D1_Outpatient_Decision")
                d2 = loaded.doc_sheets.get("D2_Admission_Decision")
                if d1 is None:
                    continue
                anomalies = detect_d1_decision_anomaly(d1, d2)
                for case_id in anomalies:
                    special.add((ds.center, ds.model, str(case_id)))
        except Exception:
            return set()
        return special

    def _load_existing_d3_proximity_rows(
        selected_case_keys: set[tuple[str, str, str]],
    ) -> list[dict[str, Any]]:
        if not selected_case_keys:
            return []
        wanted_pairs = {(center, model) for center, model, _ in selected_case_keys}
        rows: list[dict[str, Any]] = []
        try:
            discovery = discover_datasets((project_root / "data").resolve())
        except Exception:
            return rows
        for ds in discovery.datasets:
            pair = (str(ds.center).strip(), str(ds.model).strip())
            if pair not in wanted_pairs:
                continue
            try:
                loaded = load_dataset(ds)
                d3_df = build_d3_decision_fields(loaded)
            except Exception:
                continue
            if d3_df.empty:
                continue
            for _, r in d3_df.iterrows():
                key = (
                    str(r.get("center", "")).strip(),
                    str(r.get("model", "")).strip(),
                    str(r.get("case_id", "")).strip(),
                )
                if key not in selected_case_keys:
                    continue
                score = pd.to_numeric(r.get("判官_原始JSON_诊断匹配评估_评分"), errors="coerce")
                if pd.isna(score):
                    continue
                rows.append(
                    {
                        "任务ID": f"{key[0]}|{key[1]}|{key[2]}|D3_Surgery_Decision|existing_gate3_judge",
                        "中心": key[0],
                        "被评测模型": key[1],
                        "病例ID": key[2],
                        "阶段": "D3_Surgery_Decision",
                        "裁判模型": "existing_gate3_judge",
                        "提示词模板": "existing_gate3_judge_score",
                        "提示词版本(hash)": "",
                        "提示词(完整)": "",
                        "输入(汇总)": "",
                        "接近度得分(0-1)": float(score),
                        "距离(0-1)": round(max(0.0, min(1.0, 1.0 - float(score))), 4),
                        "结论": r.get("判官_原始JSON_诊断匹配评估_结论") or "",
                        "理由": r.get("判官_原始JSON_诊断匹配评估_理由") or "",
                        "来源": "existing_gate3_judge",
                        "错误": "",
                    }
                )
        return rows

    # Task-specific flattening
    dx_rows: list[dict[str, Any]] = []
    dx_quality_rows: list[dict[str, Any]] = []
    check_rows: list[dict[str, Any]] = []
    rationale_rows: list[dict[str, Any]] = []
    final_dx_proximity_rows: list[dict[str, Any]] = []
    gate_rescore_map: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    fact_rows: list[dict[str, Any]] = []
    memory_rows: list[dict[str, Any]] = []
    consistency_rows: list[dict[str, Any]] = []
    plan_rows: list[dict[str, Any]] = []
    bias_rows: list[dict[str, Any]] = []
    rehab_rows: list[dict[str, Any]] = []
    for r in export_rows:
        task_name = str(r.get("task", "")).strip()
        parsed = r.get("response_json") if isinstance(r.get("response_json"), dict) else None
        if not parsed:
            continue
        inputs = r.get("inputs") if isinstance(r.get("inputs"), dict) else {}

        if task_name == "llm.diagnosis_semantic_match":
            by_k: dict[int, dict[str, Any]] = {}
            for item in parsed.get("results") or []:
                try:
                    k = int(item.get("k"))
                except Exception:
                    continue
                by_k[k] = item
            input_summary = _merge_inputs(
                inputs,
                [
                    ("GT诊断文本", "gt_diagnosis_text"),
                    ("AI诊断列表", "ai_diagnosis_list_text"),
                    ("严格度", "strictness"),
                ],
            )
            dx_rows.append(
                {
                    "任务ID": r.get("task_id"),
                    "中心": r.get("center"),
                    "被评测模型": r.get("doc_model"),
                    "病例ID": r.get("case_id"),
                    "阶段": r.get("stage"),
                    "裁判模型": r.get("judge_model"),
                    "提示词模板": r.get("prompt_template"),
                    "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                    "提示词(完整)": r.get("prompt"),
                    "输入(汇总)": input_summary,
                    "k=1命中(任一GT)(0/1)": (by_k.get(1) or {}).get("hit_any", (by_k.get(1) or {}).get("hit")),
                    "k=3命中(任一GT)(0/1)": (by_k.get(3) or {}).get("hit_any", (by_k.get(3) or {}).get("hit")),
                    "k=5命中(任一GT)(0/1)": (by_k.get(5) or {}).get("hit_any", (by_k.get(5) or {}).get("hit")),
                    "k=1命中(第1GT)(0/1)": (by_k.get(1) or {}).get("hit_primary"),
                    "k=3命中(第1GT)(0/1)": (by_k.get(3) or {}).get("hit_primary"),
                    "k=5命中(第1GT)(0/1)": (by_k.get(5) or {}).get("hit_primary"),
                    "k=1覆盖率(0-1)": (by_k.get(1) or {}).get("gt_coverage"),
                    "k=3覆盖率(0-1)": (by_k.get(3) or {}).get("gt_coverage"),
                    "k=5覆盖率(0-1)": (by_k.get(5) or {}).get("gt_coverage"),
                    "k=1加权覆盖得分(0-1)": (by_k.get(1) or {}).get("weighted_score"),
                    "k=3加权覆盖得分(0-1)": (by_k.get(3) or {}).get("weighted_score"),
                    "k=5加权覆盖得分(0-1)": (by_k.get(5) or {}).get("weighted_score"),
                    "k=1匹配GT序号(JSON)": json.dumps((by_k.get(1) or {}).get("matched_gt_indices") or [], ensure_ascii=False),
                    "k=3匹配GT序号(JSON)": json.dumps((by_k.get(3) or {}).get("matched_gt_indices") or [], ensure_ascii=False),
                    "k=5匹配GT序号(JSON)": json.dumps((by_k.get(5) or {}).get("matched_gt_indices") or [], ensure_ascii=False),
                    "k=1匹配AI排名(JSON)": json.dumps((by_k.get(1) or {}).get("matched_ai_ranks") or [], ensure_ascii=False),
                    "k=3匹配AI排名(JSON)": json.dumps((by_k.get(3) or {}).get("matched_ai_ranks") or [], ensure_ascii=False),
                    "k=5匹配AI排名(JSON)": json.dumps((by_k.get(5) or {}).get("matched_ai_ranks") or [], ensure_ascii=False),
                    "错误": r.get("error"),
                }
            )
        elif task_name == "llm.diagnosis_quality":
            scores = parsed.get("scores") or {}
            input_summary = _merge_inputs(
                inputs,
                [
                    ("GT诊断文本", "gt_diagnosis_text"),
                    ("AI诊断文本", "ai_diagnosis_text"),
                    ("AI诊断思维", "ai_diagnosis_rationale"),
                    ("上下文事实", "context_facts"),
                    ("严格度", "strictness"),
                ],
            )
            dx_quality_rows.append(
                {
                    "任务ID": r.get("task_id"),
                    "中心": r.get("center"),
                    "被评测模型": r.get("doc_model"),
                    "病例ID": r.get("case_id"),
                    "阶段": r.get("stage"),
                    "裁判模型": r.get("judge_model"),
                    "提示词模板": r.get("prompt_template"),
                    "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                    "提示词(完整)": r.get("prompt"),
                    "输入(汇总)": input_summary,
                    "准确性(0-1)": (scores or {}).get("accuracy"),
                    "合理性(0-1)": (scores or {}).get("reasonableness"),
                    "逻辑性(0-1)": (scores or {}).get("logic"),
                    "错误标签(JSON)": json.dumps(parsed.get("issue_tags") or [], ensure_ascii=False),
                    "错误": r.get("error"),
                }
            )
        elif task_name == "llm.final_diagnosis_proximity":
            input_summary = _merge_inputs(
                inputs,
                [
                    ("阶段标签", "stage_label"),
                    ("GT最终诊断", "gt_final_diagnosis"),
                    ("AI阶段诊断", "ai_stage_diagnosis"),
                    ("AI诊断思维", "ai_stage_diagnosis_rationale"),
                    ("上下文事实", "context_facts"),
                ],
            )
            score = pd.to_numeric(parsed.get("score"), errors="coerce")
            distance = None if pd.isna(score) else round(max(0.0, min(1.0, 1.0 - float(score))), 4)
            match_label = parsed.get("match_label")
            if isinstance(match_label, (list, dict)):
                match_label = json.dumps(match_label, ensure_ascii=False)
            reason = parsed.get("reason")
            if isinstance(reason, list):
                reason = "；".join(str(x).strip() for x in reason if str(x).strip())
            elif isinstance(reason, dict):
                reason = json.dumps(reason, ensure_ascii=False)
            final_dx_proximity_rows.append(
                {
                    "任务ID": r.get("task_id"),
                    "中心": r.get("center"),
                    "被评测模型": r.get("doc_model"),
                    "病例ID": r.get("case_id"),
                    "阶段": r.get("stage"),
                    "裁判模型": r.get("judge_model"),
                    "提示词模板": r.get("prompt_template"),
                    "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                    "提示词(完整)": r.get("prompt"),
                    "输入(汇总)": input_summary,
                    "接近度得分(0-1)": None if pd.isna(score) else float(score),
                    "距离(0-1)": distance,
                    "结论": match_label or "",
                    "理由": reason or "",
                    "来源": "llm_rescore_against_gt_final",
                    "错误": r.get("error"),
                }
            )
        elif task_name == "llm.unmatched_check_reasonableness":
            ai_all = inputs.get("ai_requested_checks_all") or inputs.get("ai_requested_checks") or ""
            matched_all = inputs.get("judge_matched_checks_all") or ""
            unmatched_all = inputs.get("judge_unmatched_checks_all") or inputs.get("unmatched_checks") or ""
            to_judge = inputs.get("unmatched_checks_to_judge") or ""
            prior_matched = inputs.get("prior_matched_checks") or ""
            gt_checks_text = inputs.get("gt_checks_text") or ""
            gt_facts = inputs.get("gt_facts") or ""
            ai_rationale = inputs.get("ai_rationale") or ""
            input_summary = _merge_inputs(
                inputs,
                [
                    ("需判定未匹配检查", "unmatched_checks_to_judge"),
                    ("AI提出检查(全量)", "ai_requested_checks_all"),
                    ("裁判匹配检查(全量)", "judge_matched_checks_all"),
                    ("裁判未匹配检查(全量)", "judge_unmatched_checks_all"),
                    ("前序已匹配检查", "prior_matched_checks"),
                    ("GT已执行检查原文", "gt_checks_text"),
                    ("GT病历事实", "gt_facts"),
                    ("AI理由/思维", "ai_rationale"),
                ],
            )
            for item in parsed.get("items") or []:
                check_rows.append(
                    {
                        "任务ID": r.get("task_id"),
                        "中心": r.get("center"),
                        "被评测模型": r.get("doc_model"),
                        "病例ID": r.get("case_id"),
                        "阶段": r.get("stage"),
                        "裁判模型": r.get("judge_model"),
                        "提示词模板": r.get("prompt_template"),
                        "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                        "提示词(完整)": r.get("prompt"),
                        "输入(汇总)": input_summary,
                        "未匹配检查项": item.get("check_item"),
                        "是否仍有临床意义(0/1)": item.get("is_clinically_meaningful"),
                        "是否冗余(0/1)": item.get("is_redundant"),
                        "输出_JSON原文": json.dumps(item or {}, ensure_ascii=False),
                        "错误": r.get("error"),
                    }
                )
        elif task_name == "llm.rationale_quality":
            input_summary = _merge_inputs(
                inputs,
                [
                    ("AI输出", "ai_output_text"),
                    ("AI理由/思维", "ai_rationale_text"),
                    ("GT病历事实", "gt_facts"),
                ],
            )
            rationale_rows.append(
                {
                    "任务ID": r.get("task_id"),
                    "中心": r.get("center"),
                    "被评测模型": r.get("doc_model"),
                    "病例ID": r.get("case_id"),
                    "阶段": r.get("stage"),
                    "裁判模型": r.get("judge_model"),
                    "提示词模板": r.get("prompt_template"),
                    "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                    "提示词(完整)": r.get("prompt"),
                    "输入(汇总)": input_summary,
                    "推理质量得分(0-1)": parsed.get("score"),
                    "错误标签(JSON)": json.dumps(parsed.get("issue_tags") or [], ensure_ascii=False),
                    "错误": r.get("error"),
                }
            )
        elif task_name == "llm.gate1_dx_rescore":
            input_summary = _merge_inputs(
                inputs,
                [
                    ("AI初步诊断", "ai_preliminary_diagnosis"),
                    ("AI诊断思维", "ai_diagnosis_rationale"),
                    ("GT入院诊断", "gt_admission_diagnosis"),
                    ("GT主诊断", "gt_primary_diagnosis"),
                    ("GT鉴别诊断", "gt_differential_diagnoses"),
                    ("上下文事实", "context_facts"),
                ],
            )
            key = (
                str(r.get("center") or ""),
                str(r.get("doc_model") or ""),
                str(r.get("case_id") or ""),
                str(r.get("stage") or ""),
            )
            row = gate_rescore_map.get(key)
            if row is None:
                row = {
                    "任务ID": r.get("task_id"),
                    "中心": r.get("center"),
                    "被评测模型": r.get("doc_model"),
                    "病例ID": r.get("case_id"),
                    "阶段": r.get("stage"),
                    "裁判模型": r.get("judge_model"),
                    "提示词模板": r.get("prompt_template"),
                    "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                    "提示词(完整)": r.get("prompt"),
                    "输入(汇总)": input_summary,
                    "诊断结论": "",
                    "诊断理由": "",
                    "诊断得分(0-1)": "",
                    "方案结论": "",
                    "方案理由": "",
                    "方案得分(0-1)": "",
                    "综合得分(0-1)": "",
                    "是否继续评测": "",
                    "二审诊断得分(0-1)": "",
                    "二审方案得分(0-1)": "",
                    "二审综合得分(0-1)": "",
                    "二审是否继续评测": "",
                    "二审理由": "",
                    "输出_JSON原文": "",
                    "二审_JSON原文": "",
                    "错误": r.get("error"),
                }
            row["诊断结论"] = parsed.get("match_label") or ""
            row["诊断得分(0-1)"] = parsed.get("score")
            row["综合得分(0-1)"] = parsed.get("score")
            row["诊断理由"] = parsed.get("reason") or ""
            row["输出_JSON原文"] = json.dumps(parsed or {}, ensure_ascii=False)
            gate_rescore_map[key] = row
        elif task_name == "llm.gate2_dx_plan_rescore":
            input_summary = _merge_inputs(
                inputs,
                [
                    ("AI修正诊断", "ai_revised_diagnosis"),
                    ("AI治疗方案", "ai_treatment_plan"),
                    ("AI诊断思维", "ai_diagnosis_rationale"),
                    ("AI方案思维", "ai_plan_rationale"),
                    ("GT修正诊断", "gt_revised_diagnosis"),
                    ("GT入院诊断", "gt_admission_diagnosis"),
                    ("GT最终诊断", "gt_final_diagnosis"),
                    ("GT手术方案", "gt_surgery_plan"),
                    ("上下文事实", "context_facts"),
                ],
            )
            key = (
                str(r.get("center") or ""),
                str(r.get("doc_model") or ""),
                str(r.get("case_id") or ""),
                str(r.get("stage") or ""),
            )
            row = gate_rescore_map.get(key)
            if row is None:
                row = {
                    "任务ID": r.get("task_id"),
                    "中心": r.get("center"),
                    "被评测模型": r.get("doc_model"),
                    "病例ID": r.get("case_id"),
                    "阶段": r.get("stage"),
                    "裁判模型": r.get("judge_model"),
                    "提示词模板": r.get("prompt_template"),
                    "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                    "提示词(完整)": r.get("prompt"),
                    "输入(汇总)": input_summary,
                    "诊断结论": "",
                    "诊断理由": "",
                    "诊断得分(0-1)": "",
                    "方案结论": "",
                    "方案理由": "",
                    "方案得分(0-1)": "",
                    "综合得分(0-1)": "",
                    "是否继续评测": "",
                    "二审诊断得分(0-1)": "",
                    "二审方案得分(0-1)": "",
                    "二审综合得分(0-1)": "",
                    "二审是否继续评测": "",
                    "二审理由": "",
                    "输出_JSON原文": "",
                    "二审_JSON原文": "",
                    "错误": r.get("error"),
                }
            diag_block = parsed.get("修正诊断匹配") or {}
            plan_block = parsed.get("手术方案匹配") or {}
            row["诊断结论"] = diag_block.get("结论") or ""
            row["诊断理由"] = diag_block.get("理由") or ""
            diag_score = diag_block.get("评分")
            if diag_score is None:
                diag_score = diag_block.get("score")
            row["诊断得分(0-1)"] = diag_score
            row["方案结论"] = plan_block.get("结论") or ""
            row["方案理由"] = plan_block.get("理由") or ""
            plan_score = plan_block.get("评分")
            if plan_score is None:
                plan_score = plan_block.get("score")
            row["方案得分(0-1)"] = plan_score
            row["是否继续评测"] = parsed.get("是否继续评测")
            row["输出_JSON原文"] = json.dumps(parsed or {}, ensure_ascii=False)
            gate_rescore_map[key] = row
        elif task_name == "llm.gate2_dx_plan_rescore_review":
            input_summary = _merge_inputs(
                inputs,
                [
                    ("AI修正诊断", "ai_revised_diagnosis"),
                    ("AI治疗方案", "ai_treatment_plan"),
                    ("AI诊断思维", "ai_diagnosis_rationale"),
                    ("AI方案思维", "ai_plan_rationale"),
                    ("GT修正诊断", "gt_revised_diagnosis"),
                    ("GT入院诊断", "gt_admission_diagnosis"),
                    ("GT最终诊断", "gt_final_diagnosis"),
                    ("GT手术方案", "gt_surgery_plan"),
                    ("完整上下文", "full_context_facts"),
                ],
            )
            key = (
                str(r.get("center") or ""),
                str(r.get("doc_model") or ""),
                str(r.get("case_id") or ""),
                str(r.get("stage") or ""),
            )
            row = gate_rescore_map.get(key)
            if row is None:
                row = {
                    "任务ID": r.get("task_id"),
                    "中心": r.get("center"),
                    "被评测模型": r.get("doc_model"),
                    "病例ID": r.get("case_id"),
                    "阶段": r.get("stage"),
                    "裁判模型": r.get("judge_model"),
                    "提示词模板": r.get("prompt_template"),
                    "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                    "提示词(完整)": r.get("prompt"),
                    "输入(汇总)": input_summary,
                    "诊断结论": "",
                    "诊断理由": "",
                    "诊断得分(0-1)": "",
                    "方案结论": "",
                    "方案理由": "",
                    "方案得分(0-1)": "",
                    "综合得分(0-1)": "",
                    "是否继续评测": "",
                    "二审诊断得分(0-1)": "",
                    "二审方案得分(0-1)": "",
                    "二审综合得分(0-1)": "",
                    "二审是否继续评测": "",
                    "二审理由": "",
                    "输出_JSON原文": "",
                    "二审_JSON原文": "",
                    "错误": r.get("error"),
                }
            def _as_float(val: Any) -> float | None:
                try:
                    if val is None or val == "":
                        return None
                    return float(val)
                except Exception:
                    return None

            diag_score = _as_float(parsed.get("diag_score"))
            row["二审诊断得分(0-1)"] = diag_score
            row["二审方案得分(0-1)"] = ""
            row["二审是否继续评测"] = parsed.get("should_continue")
            row["二审理由"] = parsed.get("reason") or ""
            row["二审_JSON原文"] = json.dumps(parsed or {}, ensure_ascii=False)
            # If main scores are empty, backfill with review scores
            plan_score_main = _as_float(row.get("方案得分(0-1)"))
            if row.get("诊断得分(0-1)") in ("", None) and diag_score is not None:
                row["诊断得分(0-1)"] = diag_score
            if diag_score is not None and plan_score_main is not None:
                overall = round(0.6 * diag_score + 0.4 * plan_score_main, 4)
                # 二审诊断分一旦存在，综合得分以二审诊断为准
                row["综合得分(0-1)"] = overall
                row["二审综合得分(0-1)"] = overall
            gate_rescore_map[key] = row
        elif task_name == "llm.fact_consistency_and_missing":
            input_summary = _merge_inputs(
                inputs,
                [
                    ("AI汇总/回顾", "ai_summary_or_review"),
                    ("GT病历事实", "gt_facts"),
                ],
            )
            fact_rows.append(
                {
                    "任务ID": r.get("task_id"),
                    "中心": r.get("center"),
                    "被评测模型": r.get("doc_model"),
                    "病例ID": r.get("case_id"),
                    "阶段": r.get("stage"),
                    "一致性指标": "事实一致性/扭曲",
                    "裁判模型": r.get("judge_model"),
                    "提示词模板": r.get("prompt_template"),
                    "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                    "提示词(完整)": r.get("prompt"),
                    "输入(汇总)": input_summary,
                    "一致性得分(0-1)": parsed.get("consistency_score"),
                    "冲突条数": parsed.get("contradiction_count"),
                    "幻觉条数": parsed.get("hallucination_count"),
                    "关键信息丢失条数": parsed.get("missing_count", 0),
                    "关键信息丢失率(0-1)": parsed.get("missing_rate", 0.0),
                    "冲突原因(JSON)": json.dumps(parsed.get("contradiction_reasons") or [], ensure_ascii=False),
                    "幻觉原因(JSON)": json.dumps(parsed.get("hallucination_reasons") or [], ensure_ascii=False),
                    "丢失原因(JSON)": json.dumps(parsed.get("missing_reasons") or [], ensure_ascii=False),
                    "错误标签(JSON)": json.dumps(parsed.get("issue_tags") or [], ensure_ascii=False),
                    "原因(简短)": json.dumps(parsed.get("issue_reasons") or [], ensure_ascii=False),
                    "错误": r.get("error"),
                }
            )
        elif task_name == "llm.memory_retention":
            input_summary = _merge_inputs(
                inputs,
                [
                    ("前序阶段信息汇总/回顾", "prior_stage_summary"),
                    ("当前阶段诊疗回顾/思维", "current_stage_review"),
                    ("GT病历事实", "gt_facts"),
                ],
            )
            memory_rows.append(
                {
                    "任务ID": r.get("task_id"),
                    "中心": r.get("center"),
                    "被评测模型": r.get("doc_model"),
                    "病例ID": r.get("case_id"),
                    "阶段": r.get("stage"),
                    "裁判模型": r.get("judge_model"),
                    "提示词模板": r.get("prompt_template"),
                    "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                    "提示词(完整)": r.get("prompt"),
                    "输入(汇总)": input_summary,
                    "历史信息继承度(0-1)": parsed.get("retention_rate"),
                    "历史信息利用率(0-1)": parsed.get("utilization_rate"),
                    "错误标签(JSON)": json.dumps(parsed.get("issue_tags") or [], ensure_ascii=False),
                    "原因(简短)": json.dumps(parsed.get("issue_reasons") or [], ensure_ascii=False),
                    "错误": r.get("error"),
                }
            )
        elif task_name == "llm.cross_stage_consistency":
            input_summary = _merge_inputs(
                inputs,
                [
                    ("多阶段信息汇总", "multi_stage_summaries"),
                    ("GT病历事实", "gt_facts"),
                ],
            )
            for item in parsed.get("stage_findings") or []:
                consistency_rows.append(
                    {
                        "任务ID": r.get("task_id"),
                        "中心": r.get("center"),
                        "被评测模型": r.get("doc_model"),
                        "病例ID": r.get("case_id"),
                        "阶段": item.get("stage"),
                        "一致性指标": "跨阶段矛盾检测",
                        "裁判模型": r.get("judge_model"),
                        "提示词模板": r.get("prompt_template"),
                        "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                        "提示词(完整)": r.get("prompt"),
                        "输入(汇总)": input_summary,
                        "一致性得分(0-1)": item.get("score"),
                        "错误标签(JSON)": json.dumps(item.get("issue_tags") or [], ensure_ascii=False),
                        "原因(简短)": item.get("reason"),
                        "错误": r.get("error"),
                    }
                )
        elif task_name == "llm.plan_quality":
            scores = parsed.get("scores") or {}
            input_summary = _merge_inputs(
                inputs,
                [
                    ("GT方案文本", "gt_plan_text"),
                    ("AI方案文本", "ai_plan_text"),
                    ("AI方案思维/依据", "ai_plan_rationale"),
                    ("上下文事实", "context_facts"),
                ],
            )
            plan_rows.append(
                {
                    "任务ID": r.get("task_id"),
                    "中心": r.get("center"),
                    "被评测模型": r.get("doc_model"),
                    "病例ID": r.get("case_id"),
                    "阶段": r.get("stage"),
                    "裁判模型": r.get("judge_model"),
                    "提示词模板": r.get("prompt_template"),
                    "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                    "提示词(完整)": r.get("prompt"),
                    "输入(汇总)": input_summary,
                    "准确性(0-1)": (scores or {}).get("accuracy"),
                    "安全性(0-1)": (scores or {}).get("safety"),
                    "完备性(0-1)": (scores or {}).get("completeness"),
                    "合理性(0-1)": (scores or {}).get("reasonableness"),
                    "错误标签(JSON)": json.dumps(parsed.get("issue_tags") or [], ensure_ascii=False),
                    "错误": r.get("error"),
                }
            )
        elif task_name == "llm.rehab_followup_quality":
            rehab_scores = parsed.get("rehab_scores") or {}
            followup_scores = parsed.get("followup_scores") or {}
            input_summary = _merge_inputs(
                inputs,
                [
                    ("GT康复计划", "gt_rehab_plan"),
                    ("AI康复计划", "ai_rehab_plan"),
                    ("AI康复思维/依据", "ai_rehab_rationale"),
                    ("GT随访计划", "gt_followup_plan"),
                    ("AI随访计划", "ai_followup_plan"),
                    ("AI随访思维/依据", "ai_followup_rationale"),
                    ("上下文事实", "context_facts"),
                ],
            )
            rehab_rows.append(
                {
                    "任务ID": r.get("task_id"),
                    "中心": r.get("center"),
                    "被评测模型": r.get("doc_model"),
                    "病例ID": r.get("case_id"),
                    "阶段": r.get("stage"),
                    "裁判模型": r.get("judge_model"),
                    "提示词模板": r.get("prompt_template"),
                    "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                    "提示词(完整)": r.get("prompt"),
                    "输入(汇总)": input_summary,
                    "康复_完整性(0-1)": (rehab_scores or {}).get("completeness"),
                    "康复_合理性(0-1)": (rehab_scores or {}).get("reasonableness"),
                    "随访_合理性(0-1)": (followup_scores or {}).get("reasonableness"),
                    "随访_覆盖性(0-1)": (followup_scores or {}).get("coverage"),
                    "错误标签(JSON)": json.dumps(parsed.get("issue_tags") or [], ensure_ascii=False),
                    "错误": r.get("error"),
                }
            )
        elif task_name == "llm.diagnosis_bias":
            bias_dir = parsed.get("bias_direction")
            severity = parsed.get("severity")
            corrected_dir = bias_dir
            corrected_sev = severity
            ai_text = str(inputs.get("ai_final_diagnosis") or "").strip()
            gt_text = str(inputs.get("gt_final_diagnosis") or "").strip()
            if bias_dir == "Neutral" and ai_text and gt_text and ai_text != gt_text:
                corrected_dir = "Under"
                try:
                    corrected_sev = max(1, int(severity)) if severity is not None else 1
                except Exception:
                    corrected_sev = 1
            input_summary = _merge_inputs(
                inputs,
                [
                    ("GT最终诊断", "gt_final_diagnosis"),
                    ("AI最终诊断", "ai_final_diagnosis"),
                    ("上下文事实", "context_facts"),
                ],
            )
            bias_rows.append(
                {
                    "任务ID": r.get("task_id"),
                    "中心": r.get("center"),
                    "被评测模型": r.get("doc_model"),
                    "病例ID": r.get("case_id"),
                    "阶段": r.get("stage"),
                    "裁判模型": r.get("judge_model"),
                    "提示词模板": r.get("prompt_template"),
                    "提示词版本(hash)": (inputs or {}).get("prompt_sha256"),
                    "提示词(完整)": r.get("prompt"),
                    "输入(汇总)": input_summary,
                    "偏向方向": parsed.get("bias_direction"),
                    "偏向程度(0-5)": parsed.get("severity"),
                    "偏向方向(纠偏)": corrected_dir,
                    "偏向程度(纠偏)": corrected_sev,
                    "偏向依据标签(JSON)": json.dumps(parsed.get("basis_tags") or [], ensure_ascii=False),
                    "错误": r.get("error"),
                }
            )

    sheets = []
    if rationale_rows:
        rat_detail = _dedup_df(_sort_df(pd.DataFrame(rationale_rows)))
        rat_detail, rat_special, rat_gate3 = _split_llm_detail_by_special_and_gate3(
            rat_detail, special_keys, gate3_keys
        )
        rat_summary = _sort_df(
            _build_summary_df(rat_detail, ["中心", "被评测模型", "阶段"], ["推理质量得分(0-1)"])
        )

        sheets.append(ExcelSheetSpec("推理质量-明细", rat_detail))
        sheets.append(ExcelSheetSpec("推理质量-汇总", rat_summary))
        if special_keys and not rat_detail.empty:
            rat_special_out = rat_special if not rat_special.empty else _empty_like(rat_detail)
            rat_special_summary = _sort_df(
                _build_summary_df(rat_special_out, ["中心", "被评测模型", "阶段"], ["推理质量得分(0-1)"])
            )
            sheets.append(ExcelSheetSpec("推理质量-D2特殊-明细", _sort_df(rat_special_out)))
            sheets.append(ExcelSheetSpec("推理质量-D2特殊-汇总", rat_special_summary))
        elif not rat_special.empty:
            rat_special_summary = _sort_df(
                _build_summary_df(rat_special, ["中心", "被评测模型", "阶段"], ["推理质量得分(0-1)"])
            )
            sheets.append(ExcelSheetSpec("推理质量-D2特殊-明细", _sort_df(rat_special)))
            sheets.append(ExcelSheetSpec("推理质量-D2特殊-汇总", rat_special_summary))
        if gate3_keys and not rat_detail.empty:
            rat_gate3_out = rat_gate3 if not rat_gate3.empty else _empty_like(rat_detail)
            rat_gate3_summary = _sort_df(
                _build_summary_df(rat_gate3_out, ["中心", "被评测模型", "阶段"], ["推理质量得分(0-1)"])
            )
            sheets.append(ExcelSheetSpec("推理质量-D4Gate3不通过-明细", _sort_df(rat_gate3_out)))
            sheets.append(ExcelSheetSpec("推理质量-D4Gate3不通过-汇总", rat_gate3_summary))
        elif not rat_gate3.empty:
            rat_gate3_summary = _sort_df(
                _build_summary_df(rat_gate3, ["中心", "被评测模型", "阶段"], ["推理质量得分(0-1)"])
            )
            sheets.append(ExcelSheetSpec("推理质量-D4Gate3不通过-明细", _sort_df(rat_gate3)))
            sheets.append(ExcelSheetSpec("推理质量-D4Gate3不通过-汇总", rat_gate3_summary))
    if final_dx_proximity_rows:
        selected_case_keys = {
            (
                str(r.get("中心", "")).strip(),
                str(r.get("被评测模型", "")).strip(),
                str(r.get("病例ID", "")).strip(),
            )
            for r in final_dx_proximity_rows
            if str(r.get("中心", "")).strip() and str(r.get("被评测模型", "")).strip() and str(r.get("病例ID", "")).strip()
        }
        final_dx_proximity_rows.extend(_load_existing_d3_proximity_rows(selected_case_keys))
        final_dx_detail = _dedup_df(_sort_df(pd.DataFrame(final_dx_proximity_rows)))
        if not final_dx_detail.empty:
            for col in ["接近度得分(0-1)", "距离(0-1)"]:
                if col in final_dx_detail.columns:
                    final_dx_detail[col] = pd.to_numeric(final_dx_detail[col], errors="coerce")
            final_dx_summary = _sort_df(
                _build_summary_df(
                    final_dx_detail,
                    ["中心", "被评测模型", "阶段"],
                    ["接近度得分(0-1)", "距离(0-1)"],
                )
            )
            sheets.append(ExcelSheetSpec("最终诊断接近度-明细", final_dx_detail))
            sheets.append(ExcelSheetSpec("最终诊断接近度-汇总", final_dx_summary))
    if gate_rescore_map:
        gate_detail = _dedup_df(_sort_df(pd.DataFrame(gate_rescore_map.values())))
        if not gate_detail.empty and {"诊断得分(0-1)", "方案得分(0-1)", "综合得分(0-1)"}.issubset(gate_detail.columns):
            gate_detail["诊断得分(0-1)"] = pd.to_numeric(gate_detail["诊断得分(0-1)"], errors="coerce")
            gate_detail["方案得分(0-1)"] = pd.to_numeric(gate_detail["方案得分(0-1)"], errors="coerce")
            gate_detail["综合得分(0-1)"] = pd.to_numeric(gate_detail["综合得分(0-1)"], errors="coerce")
            if "阶段" in gate_detail.columns:
                d1_mask = gate_detail["阶段"].astype(str).str.startswith("D1")
            else:
                d1_mask = pd.Series(False, index=gate_detail.index)
            # D1: overall = diag if plan missing
            mask_overall = gate_detail["综合得分(0-1)"].isna()
            gate_detail.loc[mask_overall & d1_mask, "综合得分(0-1)"] = gate_detail.loc[
                mask_overall & d1_mask, "诊断得分(0-1)"
            ]
            # D2: overall = 0.6*diag + 0.4*plan when both available
            d2_mask = ~d1_mask
            d2_ready = mask_overall & d2_mask & gate_detail["诊断得分(0-1)"].notna() & gate_detail[
                "方案得分(0-1)"
            ].notna()
            gate_detail.loc[d2_ready, "综合得分(0-1)"] = (
                0.6 * gate_detail.loc[d2_ready, "诊断得分(0-1)"]
                + 0.4 * gate_detail.loc[d2_ready, "方案得分(0-1)"]
            ).round(4)
        gate_summary = _sort_df(
            _build_summary_df(
                gate_detail,
                ["中心", "被评测模型", "阶段"],
                ["诊断得分(0-1)", "方案得分(0-1)", "综合得分(0-1)"],
            )
        )
        sheets.append(ExcelSheetSpec("Gate重评分-明细", gate_detail))
        sheets.append(ExcelSheetSpec("Gate重评分-汇总", gate_summary))
    fact_detail = None
    fact_missing_source = None
    if fact_rows:
        fact_detail = _dedup_df(_sort_df(pd.DataFrame(fact_rows)))
        fact_detail, fact_special, fact_gate3 = _split_llm_detail_by_special_and_gate3(
            fact_detail, special_keys, gate3_keys
        )
        # Keep a copy for memory missing-rate aggregation before dropping columns in consistency sheets.
        if not fact_detail.empty:
            key_cols = ["中心", "被评测模型", "病例ID"]
            fact_missing_source = (
                fact_detail[key_cols + ["关键信息丢失率(0-1)"]]
                .copy()
                .groupby(key_cols, as_index=False)["关键信息丢失率(0-1)"]
                .mean()
            )
        # Remove missing-rate fields from consistency outputs (they belong to memory table).
        drop_missing_cols = ["关键信息丢失条数", "关键信息丢失率(0-1)", "丢失原因(JSON)"]
        fact_detail = fact_detail.drop(columns=[c for c in drop_missing_cols if c in fact_detail.columns])
        fact_summary = _sort_df(
            _build_summary_df(
                fact_detail,
                ["中心", "被评测模型", "阶段"],
                ["一致性得分(0-1)", "冲突条数", "幻觉条数"],
            )
        )
        sheets.append(ExcelSheetSpec("一致性-事实-明细", fact_detail))
        sheets.append(ExcelSheetSpec("一致性-事实-汇总", fact_summary))
        if special_keys and not fact_detail.empty:
            fact_special_out = fact_special if not fact_special.empty else _empty_like(fact_detail)
            fact_special_summary = _sort_df(
                _build_summary_df(
                    fact_special_out,
                    ["中心", "被评测模型", "阶段"],
                    ["一致性得分(0-1)", "冲突条数", "幻觉条数"],
                )
            )
            sheets.append(ExcelSheetSpec("一致性-事实-D2特殊-明细", _sort_df(fact_special_out)))
            sheets.append(ExcelSheetSpec("一致性-事实-D2特殊-汇总", fact_special_summary))
        elif not fact_special.empty:
            fact_special_summary = _sort_df(
                _build_summary_df(
                    fact_special,
                    ["中心", "被评测模型", "阶段"],
                    ["一致性得分(0-1)", "冲突条数", "幻觉条数"],
                )
            )
            sheets.append(ExcelSheetSpec("一致性-事实-D2特殊-明细", _sort_df(fact_special)))
            sheets.append(ExcelSheetSpec("一致性-事实-D2特殊-汇总", fact_special_summary))
        if gate3_keys and not fact_detail.empty:
            fact_gate3_out = fact_gate3 if not fact_gate3.empty else _empty_like(fact_detail)
            fact_gate3_summary = _sort_df(
                _build_summary_df(
                    fact_gate3_out,
                    ["中心", "被评测模型", "阶段"],
                    ["一致性得分(0-1)", "冲突条数", "幻觉条数"],
                )
            )
            sheets.append(ExcelSheetSpec("一致性-事实-D4Gate3不通过-明细", _sort_df(fact_gate3_out)))
            sheets.append(ExcelSheetSpec("一致性-事实-D4Gate3不通过-汇总", fact_gate3_summary))
        elif not fact_gate3.empty:
            fact_gate3_summary = _sort_df(
                _build_summary_df(
                    fact_gate3,
                    ["中心", "被评测模型", "阶段"],
                    ["一致性得分(0-1)", "冲突条数", "幻觉条数"],
                )
            )
            sheets.append(ExcelSheetSpec("一致性-事实-D4Gate3不通过-明细", _sort_df(fact_gate3)))
            sheets.append(ExcelSheetSpec("一致性-事实-D4Gate3不通过-汇总", fact_gate3_summary))
    if consistency_rows:
        cross_detail = _dedup_df(_sort_df(pd.DataFrame(consistency_rows)))
        cross_detail, cross_special, cross_gate3 = _split_llm_detail_by_special_and_gate3(
            cross_detail, special_keys, gate3_keys
        )
        cross_summary = _sort_df(
            _build_summary_df(
                cross_detail,
                ["中心", "被评测模型", "阶段"],
                ["一致性得分(0-1)", "冲突条数", "幻觉条数"],
            )
        )
        sheets.append(ExcelSheetSpec("一致性-跨阶段-明细", cross_detail))
        sheets.append(ExcelSheetSpec("一致性-跨阶段-汇总", cross_summary))
        if special_keys and not cross_detail.empty:
            cross_special_out = cross_special if not cross_special.empty else _empty_like(cross_detail)
            cross_special_summary = _sort_df(
                _build_summary_df(
                    cross_special_out,
                    ["中心", "被评测模型", "阶段"],
                    ["一致性得分(0-1)", "冲突条数", "幻觉条数"],
                )
            )
            sheets.append(ExcelSheetSpec("一致性-跨阶段-D2特殊-明细", _sort_df(cross_special_out)))
            sheets.append(ExcelSheetSpec("一致性-跨阶段-D2特殊-汇总", cross_special_summary))
        elif not cross_special.empty:
            cross_special_summary = _sort_df(
                _build_summary_df(
                    cross_special,
                    ["中心", "被评测模型", "阶段"],
                    ["一致性得分(0-1)", "冲突条数", "幻觉条数"],
                )
            )
            sheets.append(ExcelSheetSpec("一致性-跨阶段-D2特殊-明细", _sort_df(cross_special)))
            sheets.append(ExcelSheetSpec("一致性-跨阶段-D2特殊-汇总", cross_special_summary))
        if gate3_keys and not cross_detail.empty:
            cross_gate3_out = cross_gate3 if not cross_gate3.empty else _empty_like(cross_detail)
            cross_gate3_summary = _sort_df(
                _build_summary_df(
                    cross_gate3_out,
                    ["中心", "被评测模型", "阶段"],
                    ["一致性得分(0-1)", "冲突条数", "幻觉条数"],
                )
            )
            sheets.append(ExcelSheetSpec("一致性-跨阶段-D4Gate3不通过-明细", _sort_df(cross_gate3_out)))
            sheets.append(ExcelSheetSpec("一致性-跨阶段-D4Gate3不通过-汇总", cross_gate3_summary))
        elif not cross_gate3.empty:
            cross_gate3_summary = _sort_df(
                _build_summary_df(
                    cross_gate3,
                    ["中心", "被评测模型", "阶段"],
                    ["一致性得分(0-1)", "冲突条数", "幻觉条数"],
                )
            )
            sheets.append(ExcelSheetSpec("一致性-跨阶段-D4Gate3不通过-明细", _sort_df(cross_gate3)))
            sheets.append(ExcelSheetSpec("一致性-跨阶段-D4Gate3不通过-汇总", cross_gate3_summary))
    if memory_rows:
        mem_detail = _dedup_df(_sort_df(pd.DataFrame(memory_rows)))
        mem_detail, mem_special, mem_gate3 = _split_llm_detail_by_special_and_gate3(
            mem_detail, special_keys, gate3_keys
        )
        # Attach missing_rate from fact consistency by center/model/case (stage-agnostic).
        if fact_missing_source is not None and not fact_missing_source.empty:
            key_cols = ["中心", "被评测模型", "病例ID"]
            mem_detail = mem_detail.merge(fact_missing_source, on=key_cols, how="left")
        mem_summary = _sort_df(
            _build_summary_df(
                mem_detail,
                ["中心", "被评测模型", "阶段"],
                ["历史信息继承度(0-1)", "历史信息利用率(0-1)", "关键信息丢失率(0-1)"],
            )
        )
        sheets.append(ExcelSheetSpec("记忆保持-明细", mem_detail))
        sheets.append(ExcelSheetSpec("记忆保持-汇总", mem_summary))
        if special_keys and not mem_detail.empty:
            mem_special_out = mem_special if not mem_special.empty else _empty_like(mem_detail)
            mem_special_summary = _sort_df(
                _build_summary_df(
                    mem_special_out,
                    ["中心", "被评测模型", "阶段"],
                    ["历史信息继承度(0-1)", "历史信息利用率(0-1)"],
                )
            )
            sheets.append(ExcelSheetSpec("记忆保持-D2特殊-明细", _sort_df(mem_special_out)))
            sheets.append(ExcelSheetSpec("记忆保持-D2特殊-汇总", mem_special_summary))
        elif not mem_special.empty:
            mem_special_summary = _sort_df(
                _build_summary_df(
                    mem_special,
                    ["中心", "被评测模型", "阶段"],
                    ["历史信息继承度(0-1)", "历史信息利用率(0-1)"],
                )
            )
            sheets.append(ExcelSheetSpec("记忆保持-D2特殊-明细", _sort_df(mem_special)))
            sheets.append(ExcelSheetSpec("记忆保持-D2特殊-汇总", mem_special_summary))
        if gate3_keys and not mem_detail.empty:
            mem_gate3_out = mem_gate3 if not mem_gate3.empty else _empty_like(mem_detail)
            mem_gate3_summary = _sort_df(
                _build_summary_df(
                    mem_gate3_out,
                    ["中心", "被评测模型", "阶段"],
                    ["历史信息继承度(0-1)", "历史信息利用率(0-1)"],
                )
            )
            sheets.append(ExcelSheetSpec("记忆保持-D4Gate3不通过-明细", _sort_df(mem_gate3_out)))
            sheets.append(ExcelSheetSpec("记忆保持-D4Gate3不通过-汇总", mem_gate3_summary))
        elif not mem_gate3.empty:
            mem_gate3_summary = _sort_df(
                _build_summary_df(
                    mem_gate3,
                    ["中心", "被评测模型", "阶段"],
                    ["历史信息继承度(0-1)", "历史信息利用率(0-1)"],
                )
            )
            sheets.append(ExcelSheetSpec("记忆保持-D4Gate3不通过-明细", _sort_df(mem_gate3)))
            sheets.append(ExcelSheetSpec("记忆保持-D4Gate3不通过-汇总", mem_gate3_summary))
    # Build memory-only and consistency-only workbooks (exclude rationale/gate rescore/other tasks).
    memory_sheets: list[ExcelSheetSpec] = []
    consistency_sheets: list[ExcelSheetSpec] = []
    for s in sheets:
        if s.name.startswith("记忆保持"):
            memory_sheets.append(s)
        if s.name.startswith("一致性-事实") or s.name.startswith("一致性-跨阶段"):
            consistency_sheets.append(s)

    def _drop_empty_special_sheets(sheets_in: list[ExcelSheetSpec]) -> list[ExcelSheetSpec]:
        out: list[ExcelSheetSpec] = []
        for s in sheets_in:
            if "D2特殊" in s.name or "D4Gate3不通过" in s.name:
                df = s.df
                if df is None or df.empty:
                    continue
            out.append(s)
        return out

    memory_sheets = _drop_empty_special_sheets(memory_sheets)
    consistency_sheets = _drop_empty_special_sheets(consistency_sheets)

    def _apply_model_colors(path: Path) -> None:
        try:
            wb = load_workbook(path)
            palette = [
                "FFF2CC",  # light yellow
                "E2F0D9",  # light green
                "DDEBF7",  # light blue
                "FCE4D6",  # light orange
                "E4DFEC",  # light purple
                "F8CBAD",  # light coral
                "D9E1F2",  # light periwinkle
                "F4B084",  # light brown
            ]
            model_names: set[str] = set()
            model_col_map: dict[str, int] = {}
            for ws in wb.worksheets:
                headers = {ws.cell(row=1, column=c).value: c for c in range(1, ws.max_column + 1)}
                model_col = headers.get("被评测模型")
                if model_col is None:
                    continue
                model_col_map[ws.title] = model_col
                for row_idx in range(2, ws.max_row + 1):
                    v = ws.cell(row=row_idx, column=model_col).value
                    if v is not None and str(v).strip():
                        model_names.add(str(v).strip())
            model_colors = {
                name: PatternFill("solid", fgColor=palette[idx % len(palette)])
                for idx, name in enumerate(sorted(model_names))
            }
            for ws in wb.worksheets:
                model_col = model_col_map.get(ws.title)
                if model_col is None:
                    continue
                for row_idx in range(2, ws.max_row + 1):
                    model = ws.cell(row=row_idx, column=model_col).value
                    if model is None:
                        continue
                    model_key = str(model).strip()
                    fill = model_colors.get(model_key)
                    if not fill:
                        continue
                    for col_idx in range(1, ws.max_column + 1):
                        ws.cell(row=row_idx, column=col_idx).fill = fill
            wb.save(path)
        except Exception:
            pass

    latest_summary = (project_root / "outputs" / "latest" / "summary").resolve()
    latest_summary.mkdir(parents=True, exist_ok=True)
    if not sheets:
        raise RuntimeError("No exportable LLM result sheets were generated.")

    out_results = outputs_dir / f"llm_results_{judge_model}__{channel_name}.xlsx"
    export_metrics_source_data_xlsx(out_results, sheets=sheets)
    _apply_model_colors(out_results)
    shutil.copy2(out_results, latest_summary / out_results.name)

    out_memory = outputs_dir / f"llm_memory_{judge_model}__{channel_name}.xlsx"
    out_consistency = outputs_dir / f"llm_consistency_{judge_model}__{channel_name}.xlsx"
    if memory_sheets:
        export_metrics_source_data_xlsx(out_memory, sheets=memory_sheets)
        _apply_model_colors(out_memory)
        shutil.copy2(out_memory, latest_summary / out_memory.name)
    if consistency_sheets:
        export_metrics_source_data_xlsx(out_consistency, sheets=consistency_sheets)
        _apply_model_colors(out_consistency)
        shutil.copy2(out_consistency, latest_summary / out_consistency.name)

    return out_results
