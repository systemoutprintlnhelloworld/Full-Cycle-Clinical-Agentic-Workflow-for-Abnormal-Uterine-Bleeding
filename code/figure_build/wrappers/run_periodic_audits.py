"""Run periodic audits and write a compact run report.

Outputs:
- analysis_viz/docs/periodic_audit_run.md
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUT_MD = ROOT / "analysis_viz" / "docs" / "periodic_audit_run.md"

SCRIPTS = [
    "analysis_viz/scripts/wrappers/build_metrics_registry.py",
    "analysis_viz/scripts/wrappers/run_sample_rule_audit.py",
    "analysis_viz/scripts/wrappers/audit_metric_observability_schema.py",
    "analysis_viz/scripts/wrappers/build_alignment_source_inventory.py",
    "analysis_viz/scripts/wrappers/audit_figdata_granularity.py",
    "analysis_viz/scripts/wrappers/build_plot_script_inventory.py",
    "analysis_viz/scripts/wrappers/audit_backup_storage.py",
    "analysis_viz/scripts/wrappers/audit_outputs_cleanup.py",
]


def _run_script(script_relpath: str) -> tuple[bool, str]:
    process = subprocess.run(
        [sys.executable, script_relpath],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode == 0:
        return True, process.stdout.strip()
    return False, (process.stdout + "\n" + process.stderr).strip()


def main() -> None:
    results: list[tuple[str, bool, str]] = []
    started_at = datetime.now().isoformat(timespec="seconds")

    for script_relpath in SCRIPTS:
        ok, log_text = _run_script(script_relpath)
        results.append((script_relpath, ok, log_text))
        print(("OK   " if ok else "FAIL "), script_relpath)

    ended_at = datetime.now().isoformat(timespec="seconds")

    lines = [
        "# 周期审计运行记录",
        "",
        f"- 开始时间：{started_at}",
        f"- 结束时间：{ended_at}",
        f"- 总任务数：{len(results)}",
        f"- 成功数：{sum(1 for _, ok, _ in results if ok)}",
        f"- 失败数：{sum(1 for _, ok, _ in results if not ok)}",
        "",
        "## 逐项结果",
        "",
    ]
    for script_relpath, ok, log_text in results:
        lines.append(f"- {'✅' if ok else '❌'} `{script_relpath}`")
        if log_text:
            short = log_text.splitlines()[:8]
            lines.append("  - 输出摘要：")
            for line in short:
                lines.append(f"    - {line}")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", OUT_MD)

    if any(not ok for _, ok, _ in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

