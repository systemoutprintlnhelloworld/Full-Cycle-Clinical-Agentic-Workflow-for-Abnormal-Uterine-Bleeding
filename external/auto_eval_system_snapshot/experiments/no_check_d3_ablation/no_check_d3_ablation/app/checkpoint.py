from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path


class AblationCheckpoint:
    def __init__(self, checkpoint_path: Path):
        self.checkpoint_path = checkpoint_path
        self.lock = threading.Lock()
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _load(self) -> dict:
        if not self.checkpoint_path.exists():
            return {"completed_rows": {}, "failed_tasks": {}, "updated_at": None}
        with self.checkpoint_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _save(self) -> None:
        self.state["updated_at"] = datetime.now().isoformat()
        with self.checkpoint_path.open("w", encoding="utf-8") as handle:
            json.dump(self.state, handle, ensure_ascii=False, indent=2)

    def is_completed(self, task_key: str) -> bool:
        with self.lock:
            row = self.state["completed_rows"].get(task_key)
            if not row:
                return False
            status = str(row.get("status", "")).strip().lower()
            return status != "error"

    def mark_completed(self, task_key: str, row: dict) -> None:
        with self.lock:
            self.state["completed_rows"][task_key] = row
            self.state["failed_tasks"].pop(task_key, None)
            self._save()

    def mark_failed(self, task_key: str, payload: dict) -> None:
        with self.lock:
            self.state["failed_tasks"][task_key] = payload
            self._save()

    def all_completed_rows(self) -> list[dict]:
        with self.lock:
            return list(self.state["completed_rows"].values())

    def all_failed_rows(self) -> list[dict]:
        with self.lock:
            return list(self.state["failed_tasks"].values())
