from __future__ import annotations

import copy
import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..adapters.agent_adapter import (
    enable_duckcoding_for_gemini,
    enable_xingchen_for_gemini,
    force_yunwu_routing,
    set_model_routing,
)
from ..adapters.loader_adapter import load_patients_by_center
from .case_selection import find_eligible_case_model_tracks, group_tracks_by_case
from .checkpoint import AblationCheckpoint
from .output_writer import build_case_file_stem, load_partial_stage_payload, write_csv, write_excel
from .workflow_no_checks import NoCheckAblationWorkflow

logger = logging.getLogger(__name__)


class NoCheckAblationRunner:
    def __init__(
        self,
        repo_root: Path,
        run_root: Path,
        centers: list[str],
        models: list[str],
        judge_model: str,
        max_workers: int = 30,
        task_retries: int = 3,
    ):
        self.repo_root = repo_root
        self.run_root = run_root
        self.centers = centers
        self.models = models
        self.judge_model = judge_model
        self.max_workers = max_workers
        self.task_retries = task_retries
        self.original_output_root = self.repo_root / "output"
        default_metrics_root = self._resolve_default_metrics_root()
        env_metrics_root = os.getenv("ABLATION_LLM_METRICS_ROOT", "").strip()
        self.llm_metrics_root = Path(
            env_metrics_root or str(default_metrics_root)
        ).resolve()
        self.checkpoint = AblationCheckpoint(self.run_root / "checkpoint.json")
        self.failure_log_path = self.run_root / "task_failures.jsonl"
        self.failure_lock = threading.Lock()

    def run(
        self,
        limit_cases: int,
        skip_cases: int = 0,
        include_case_keys: set[tuple[str, str]] | None = None,
        min_eligible_model_count: int = 0,
    ) -> list[dict]:
        all_models_in_run = sorted(set(self.models + [self.judge_model]))
        force_yunwu_routing(all_models_in_run)
        if "gemini-2.5-pro" in all_models_in_run:
            duck_ok = enable_duckcoding_for_gemini()
            xing_ok = enable_xingchen_for_gemini()
            if not xing_ok:
                raise RuntimeError(
                    "检测到 gemini-2.5-pro 参与评测，但未成功启用星辰渠道。"
                    "请设置 XINGCHEN_API_KEY（可选 XINGCHEN_BASE_URL）后重试。"
                )
            route_env = os.getenv("ABLATION_GEMINI_ROUTE_ORDER", "").strip()
            if route_env:
                requested = [item.strip() for item in route_env.split(",") if item.strip()]
                available = []
                channel_manager = __import__(
                    "auto_eval_system.utils.channel_manager",
                    fromlist=["get_channel_manager"],
                ).get_channel_manager()
                for item in requested:
                    if item in channel_manager.channels:
                        if item == "duckcoding_api" and not duck_ok:
                            continue
                        if item == "xingchen_api" and not xing_ok:
                            continue
                        available.append(item)
                if "xingchen_api" not in available and xing_ok:
                    available.append("xingchen_api")
                if available:
                    set_model_routing("gemini-2.5-pro", available)
                    logger.info("Gemini 路由已按环境变量设置：%s", " -> ".join(available))
                else:
                    set_model_routing("gemini-2.5-pro", ["xingchen_api"])
                    logger.warning("Gemini 路由环境变量未命中可用渠道，降级为仅星辰。")
            elif duck_ok:
                set_model_routing("gemini-2.5-pro", ["duckcoding_api", "xingchen_api"])
                logger.info("Gemini 路由已设置：primary=duckcoding_api, fallback=[xingchen_api]")
            else:
                set_model_routing("gemini-2.5-pro", ["xingchen_api"])
                logger.warning("Gemini 路由已降级为仅星辰：primary=xingchen_api（duckcoding 不可用）")
        patient_maps = {center: load_patients_by_center(self.repo_root, center) for center in self.centers}
        eligible_tracks, excluded_tracks = find_eligible_case_model_tracks(
            self.llm_metrics_root,
            self.centers,
            self.models,
        )
        write_csv(self.run_root / "eligible_tracks.csv", eligible_tracks)
        if excluded_tracks:
            write_csv(self.run_root / "excluded_tracks.csv", excluded_tracks)

        eligible_cases = group_tracks_by_case(eligible_tracks)
        if min_eligible_model_count > 0:
            eligible_cases = [
                row
                for row in eligible_cases
                if int(row.get("eligible_model_count", 0)) >= min_eligible_model_count
            ]
        if include_case_keys:
            include_norm = {(str(c), str(case_id)) for c, case_id in include_case_keys}
            eligible_cases = [
                row
                for row in eligible_cases
                if (str(row.get("center", "")), str(row.get("case_id", ""))) in include_norm
            ]
        write_csv(self.run_root / "eligible_cases.csv", eligible_cases)
        effective_cases = eligible_cases[skip_cases:] if skip_cases > 0 else eligible_cases
        selected_cases = effective_cases[:limit_cases] if limit_cases > 0 else effective_cases
        write_csv(self.run_root / "selected_cases.csv", selected_cases)
        selected_case_keys = {(str(row["center"]), str(row["case_id"])) for row in selected_cases}
        selected_tracks = [
            row for row in eligible_tracks if (str(row["center"]), str(row["case_id"])) in selected_case_keys
        ]
        write_csv(self.run_root / "selected_tracks.csv", selected_tracks)
        logger.info(
            "本次选择 %s 个病例组、%s 条模型-病例轨迹进行测试（skip_cases=%s, limit_cases=%s）。",
            len(selected_cases),
            len(selected_tracks),
            skip_cases,
            limit_cases,
        )

        tasks = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for track in selected_tracks:
                center = str(track["center"])
                case_id = str(track["case_id"])
                model = str(track["model"])
                if case_id not in patient_maps.get(center, {}):
                    logger.warning("病例缺失于数据加载结果，跳过 center=%s case_id=%s", center, case_id)
                    continue
                tasks.append(
                    executor.submit(
                        self._run_task,
                        center,
                        case_id,
                        model,
                        patient_maps[center][case_id],
                    )
                )

            total_tasks = len(tasks)
            completed_tasks = 0
            start_ts = time.time()
            progress_lock = threading.Lock()
            stop_progress = threading.Event()

            def progress_heartbeat() -> None:
                while not stop_progress.wait(5):
                    with progress_lock:
                        snapshot = completed_tasks
                    self._render_progress(snapshot, total_tasks, start_ts)

            self._render_progress(completed_tasks, total_tasks, start_ts)
            progress_thread = threading.Thread(
                target=progress_heartbeat,
                name="ablation-progress-heartbeat",
                daemon=True,
            )
            progress_thread.start()
            try:
                for future in as_completed(tasks):
                    future.result()
                    with progress_lock:
                        completed_tasks += 1
                        snapshot = completed_tasks
                    self._render_progress(snapshot, total_tasks, start_ts)
                    if snapshot % 5 == 0 or snapshot == total_tasks:
                        elapsed = max(1e-9, time.time() - start_ts)
                        speed = snapshot / elapsed
                        logger.info(
                            "进度摘要：%s/%s (%.1f%%)，速度 %.2f 轨迹/秒",
                            snapshot,
                            total_tasks,
                            snapshot * 100.0 / total_tasks if total_tasks else 100.0,
                            speed,
                        )
            finally:
                stop_progress.set()
                progress_thread.join(timeout=1.5)
                with progress_lock:
                    snapshot = completed_tasks
                self._render_progress(snapshot, total_tasks, start_ts, force_newline=True)

        rows = sorted(
            self.checkpoint.all_completed_rows(),
            key=lambda item: (item["center"], item["case_id"], item["model"]),
        )
        if rows:
            write_csv(self.run_root / "summary.csv", rows)
            write_excel(self.run_root / "summary.xlsx", rows)
        failed_rows = self.checkpoint.all_failed_rows()
        if failed_rows:
            write_csv(self.run_root / "failed_tasks_for_resume.csv", failed_rows)
        return rows

    def _run_task(self, center: str, case_id: str, model: str, patient: dict) -> None:
        task_key = f"{center}::{case_id}::{model}"
        if self.checkpoint.is_completed(task_key):
            logger.info("跳过已完成任务 %s", task_key)
            return

        output_dir = self.run_root / "outputs" / center / model
        last_error = None
        for attempt in range(1, self.task_retries + 1):
            try:
                resume_state = load_partial_stage_payload(output_dir, center, model, case_id)
                workflow = NoCheckAblationWorkflow(
                    model_name=model,
                    judge_model=self.judge_model,
                    center_name=center,
                    output_dir=output_dir,
                )
                result = workflow.run_single_case(copy.deepcopy(patient), resume_state=resume_state)
                row = result["summary"]
                row["task_attempts"] = attempt
                self.checkpoint.mark_completed(task_key, row)
                logger.info("完成任务 %s attempt=%s", task_key, attempt)
                return
            except Exception as exc:
                last_error = exc
                failure_context = self._collect_failure_context(output_dir, center, model, case_id)
                self._log_failure(
                    {
                        "center": center,
                        "case_id": case_id,
                        "model": model,
                        "attempt": attempt,
                        "error": str(exc),
                        "timestamp": time.time(),
                        **failure_context,
                    }
                )
                if attempt < self.task_retries:
                    time.sleep(attempt)

        final_failure_context = self._collect_failure_context(output_dir, center, model, case_id)
        error_row = {
            "center": center,
            "case_id": case_id,
            "model": model,
            "judge_model": self.judge_model,
            "status": "error",
            "error": str(last_error),
            "task_attempts": self.task_retries,
            **final_failure_context,
        }
        self.checkpoint.mark_completed(task_key, error_row)
        self.checkpoint.mark_failed(task_key, error_row)

    def _log_failure(self, payload: dict) -> None:
        self.failure_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.failure_lock:
            with self.failure_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _collect_failure_context(self, output_dir: Path, center: str, model: str, case_id: str) -> dict:
        file_stem = build_case_file_stem(center, model, case_id)
        per_case_path = output_dir / "per_case_json" / f"{file_stem}.json"
        raw_trace_path = output_dir / "raw_traces" / f"{file_stem}.jsonl"
        html_trace_path = output_dir / "html_traces" / f"{file_stem}.html"
        echo_trace_path = output_dir / "html_traces" / f"{file_stem}_trace.html"
        resume_state = load_partial_stage_payload(output_dir, center, model, case_id)
        completed_stages = sorted(resume_state.keys())
        next_stage = self._infer_next_stage(completed_stages)

        last_prompt_excerpt = ""
        if per_case_path.exists():
            try:
                payload = json.loads(per_case_path.read_text(encoding="utf-8"))
                events = payload.get("events", []) or []
                for event in reversed(events):
                    if event.get("kind") == "doctor_prompt":
                        prompt_payload = event.get("payload") or {}
                        last_prompt_excerpt = str(prompt_payload.get("user_prompt") or "").strip()[:1200]
                        break
            except Exception:
                last_prompt_excerpt = ""

        return {
            "resume_completed_stages": "|".join(completed_stages),
            "resume_next_stage_hint": next_stage,
            "per_case_json_path": str(per_case_path),
            "raw_trace_path": str(raw_trace_path),
            "html_trace_path": str(html_trace_path),
            "echo_trace_path": str(echo_trace_path),
            "last_prompt_excerpt": last_prompt_excerpt,
        }

    @staticmethod
    def _infer_next_stage(completed_stages: list[str]) -> str:
        stage_order = ["D1", "D2", "D3"]
        for stage in stage_order:
            if stage not in completed_stages:
                return stage
        return "completed_or_unknown"

    def _resolve_default_metrics_root(self) -> Path:
        direct = self.repo_root.parent / "LLM as judge评分系统 & 量化指标系统"
        if direct.exists():
            return direct
        candidates = sorted(self.repo_root.parent.glob("LLM as judge*"))
        if candidates:
            return candidates[0]
        logger.warning("未自动定位到 LLM 指标仓库，默认使用父目录。建议设置 ABLATION_LLM_METRICS_ROOT。")
        return self.repo_root.parent

    @staticmethod
    def _render_progress(completed: int, total: int, start_ts: float, force_newline: bool = False) -> None:
        if total <= 0:
            print("[进度] 0/0 |------------------------------|   0.0%", end="\n", flush=True)
            return
        width = 30
        ratio = completed / total
        filled = int(width * ratio)
        bar = "█" * filled + "-" * (width - filled)
        elapsed = max(1e-9, time.time() - start_ts)
        speed = completed / elapsed if completed > 0 else 0.0
        remaining = max(0, total - completed)
        eta = remaining / speed if speed > 1e-9 else 0.0
        line = (
            f"[进度] {completed}/{total} |{bar}| {ratio * 100:5.1f}% "
            f"| {speed:5.2f} 轨迹/s | ETA {eta/60:5.1f} min"
        )
        stdout_is_tty = sys.stdout.isatty()
        if force_newline or not stdout_is_tty:
            print(line, end="\n", flush=True)
            return
        end_char = "\n" if completed >= total else ""
        print(f"\r{line}", end=end_char, flush=True)
