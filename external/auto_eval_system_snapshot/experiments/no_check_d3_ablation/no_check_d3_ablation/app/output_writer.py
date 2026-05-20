from __future__ import annotations

import csv
import html
import json
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook


def sanitize_filename(value: str) -> str:
    return value.replace("/", "_").replace("\\", "_").replace(":", "-")


def build_case_file_stem(center: str, model: str, case_id: str) -> str:
    return sanitize_filename(f"{model}_{center}_{case_id}")


class CaseTraceWriter:
    def __init__(self, output_dir: Path, center: str, model: str, case_id: str):
        self.output_dir = output_dir
        self.center = center
        self.model = model
        self.case_id = case_id
        self.events: list[dict] = []

        self.raw_trace_dir = self.output_dir / "raw_traces"
        self.per_case_dir = self.output_dir / "per_case_json"
        self.html_dir = self.output_dir / "html_traces"
        for path in (self.raw_trace_dir, self.per_case_dir, self.html_dir):
            path.mkdir(parents=True, exist_ok=True)

        file_stem = build_case_file_stem(center, model, case_id)
        self.raw_trace_path = self.raw_trace_dir / f"{file_stem}.jsonl"
        self.per_case_path = self.per_case_dir / f"{file_stem}.json"
        self.html_path = self.html_dir / f"{file_stem}.html"
        self.echo_html_path = self.html_dir / f"{file_stem}_trace.html"

    def log_event(self, stage: str, kind: str, payload: dict | None = None) -> None:
        event = {
            "timestamp": datetime.now().isoformat(),
            "case_id": self.case_id,
            "center": self.center,
            "model": self.model,
            "stage": stage,
            "kind": kind,
            "payload": payload or {},
        }
        self.events.append(event)
        with self.raw_trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def save_case_result(self, result: dict) -> None:
        payload = {"case_result": result, "events": self.events}
        with self.per_case_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        self._write_html(payload)

    def _write_html(self, payload: dict) -> None:
        if self._write_echo_html(payload):
            return

        blocks = []
        for event in self.events:
            pretty = html.escape(json.dumps(event["payload"], ensure_ascii=False, indent=2))
            blocks.append(
                "<details open>"
                f"<summary>{html.escape(event['stage'])} / {html.escape(event['kind'])}</summary>"
                f"<pre>{pretty}</pre>"
                "</details>"
            )
        summary = html.escape(json.dumps(payload["case_result"], ensure_ascii=False, indent=2))
        html_doc = (
            "<html><head><meta charset='utf-8'><title>No-Check Ablation Trace</title>"
            "<style>body{font-family:Consolas,monospace;background:#faf8f2;color:#111;padding:24px;}"
            "details{border:1px solid #ddd;background:#fff;margin:12px 0;padding:12px;}"
            "summary{font-weight:700;cursor:pointer;}pre{white-space:pre-wrap;word-break:break-word;}"
            "</style></head><body>"
            f"<h1>{html.escape(self.model)} | {html.escape(self.center)} | {html.escape(self.case_id)}</h1>"
            "<h2>Case Result</h2>"
            f"<pre>{summary}</pre>"
            "<h2>Events</h2>"
            f"{''.join(blocks)}"
            "</body></html>"
        )
        self.html_path.write_text(html_doc, encoding="utf-8")

    def _write_echo_html(self, payload: dict) -> bool:
        try:
            from auto_eval_system.utils.html_logger import HtmlTraceLogger
        except Exception:
            return False

        def map_stage_name(stage: str, kind: str) -> str:
            stage_prefix = str(stage or "system")
            kind_map = {
                "doctor_prompt": "Doc_Prompt",
                "doctor_output": "Doc_Output",
                "doctor_retry": "Doc_Retry",
                "judge_output": "Judge_Output",
                "error": "Error",
            }
            suffix = kind_map.get(kind, kind)
            return f"{stage_prefix}_{suffix}"

        try:
            trace_logger = HtmlTraceLogger(
                trace_dir=str(self.html_dir),
                case_id=self.case_id,
                model_name=self.model,
                center_name=self.center,
            )
            for event in self.events:
                stage = map_stage_name(event.get("stage", "system"), event.get("kind", "event"))
                event_payload = event.get("payload") or {}
                stamped_payload = {"timestamp": event.get("timestamp"), **event_payload}
                kind = event.get("kind")
                if kind == "doctor_prompt":
                    trace_logger.log(stage, stamped_payload, None, model=self.model, center=self.center)
                elif kind in {"doctor_output", "judge_output"}:
                    trace_logger.log(
                        stage,
                        None,
                        event_payload.get("output", stamped_payload),
                        model=self.model,
                        center=self.center,
                    )
                elif kind in {"doctor_retry", "error"}:
                    trace_logger.log(
                        stage,
                        None,
                        stamped_payload,
                        error=event_payload.get("error") or event_payload.get("message") or "runtime_error",
                        model=self.model,
                        center=self.center,
                    )
                else:
                    trace_logger.log(stage, None, stamped_payload, model=self.model, center=self.center)

            trace_logger.log(
                "Case_Summary",
                None,
                payload.get("case_result", {}),
                model=self.model,
                center=self.center,
            )
            trace_logger.save_trace()
            if self.echo_html_path.exists():
                try:
                    self.html_path.write_text(self.echo_html_path.read_text(encoding="utf-8"), encoding="utf-8")
                except Exception:
                    pass
            return self.echo_html_path.exists()
        except Exception:
            return False


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_excel(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "summary"
    fieldnames = sorted({key for row in rows for key in row.keys()})
    worksheet.append(fieldnames)
    for row in rows:
        worksheet.append([row.get(field) for field in fieldnames])
    workbook.save(path)


def load_partial_stage_payload(output_dir: Path, center: str, model: str, case_id: str) -> dict[str, dict]:
    file_stem = build_case_file_stem(center, model, case_id)
    per_case_path = output_dir / "per_case_json" / f"{file_stem}.json"
    if not per_case_path.exists():
        return {}

    with per_case_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    stages: dict[str, dict] = {}
    for event in payload.get("events", []):
        stage = event.get("stage")
        kind = event.get("kind")
        if stage not in {"D1", "D2", "D3"}:
            continue
        stages.setdefault(stage, {})
        event_payload = event.get("payload", {})
        if kind == "doctor_output":
            stages[stage]["doctor"] = event_payload.get("output")
        elif kind == "judge_output":
            stages[stage]["judge"] = event_payload.get("output")
    return stages
