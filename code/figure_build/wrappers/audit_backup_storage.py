"""Audit backup storage usage under analysis_viz/data/_backup_before_overwrite.

Outputs:
- analysis_viz/docs/backup_storage_audit.csv
- analysis_viz/docs/backup_storage_audit.md
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BACKUP_DIR = ROOT / "analysis_viz" / "data" / "_backup_before_overwrite"
OUT_CSV = ROOT / "analysis_viz" / "docs" / "backup_storage_audit.csv"
OUT_MD = ROOT / "analysis_viz" / "docs" / "backup_storage_audit.md"


def _stem_group(file_name: str) -> str:
    marker = "__backup_"
    if marker in file_name:
        return file_name.split(marker, 1)[0]
    return file_name


def main() -> None:
    rows: list[dict[str, object]] = []
    all_files = sorted([path for path in BACKUP_DIR.glob("*.xlsx") if path.is_file()]) if BACKUP_DIR.exists() else []

    summary: dict[str, dict[str, object]] = {}
    for file_path in all_files:
        stem = _stem_group(file_path.name)
        item = summary.setdefault(
            stem,
            {
                "stem": stem,
                "file_count": 0,
                "total_size_bytes": 0,
                "latest_mtime": None,
                "oldest_mtime": None,
            },
        )
        size_bytes = file_path.stat().st_size
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        item["file_count"] = int(item["file_count"]) + 1
        item["total_size_bytes"] = int(item["total_size_bytes"]) + int(size_bytes)
        item["latest_mtime"] = mtime if item["latest_mtime"] is None else max(item["latest_mtime"], mtime)
        item["oldest_mtime"] = mtime if item["oldest_mtime"] is None else min(item["oldest_mtime"], mtime)

    for key in sorted(summary.keys()):
        item = summary[key]
        rows.append(
            {
                "stem": item["stem"],
                "file_count": int(item["file_count"]),
                "total_size_bytes": int(item["total_size_bytes"]),
                "total_size_mb": round(int(item["total_size_bytes"]) / (1024 * 1024), 3),
                "latest_mtime": item["latest_mtime"].isoformat(timespec="seconds") if item["latest_mtime"] else "",
                "oldest_mtime": item["oldest_mtime"].isoformat(timespec="seconds") if item["oldest_mtime"] else "",
            }
        )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as file_handle:
        fieldnames = ["stem", "file_count", "total_size_bytes", "total_size_mb", "latest_mtime", "oldest_mtime"]
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    total_bytes = sum(row["total_size_bytes"] for row in rows)
    total_mb = total_bytes / (1024 * 1024)
    total_files = len(all_files)
    top_by_count = sorted(rows, key=lambda row: int(row["file_count"]), reverse=True)[:10]
    top_by_size = sorted(rows, key=lambda row: int(row["total_size_bytes"]), reverse=True)[:10]

    markdown_lines = [
        "# 备份目录巡检报告",
        "",
        f"- 目录：`{BACKUP_DIR}`",
        f"- 文件数：{total_files}",
        f"- 总体积：{total_mb:.2f} MB",
        f"- 分组数：{len(rows)}",
        "",
        "## 按备份数量 Top10",
        "",
    ]
    if top_by_count:
        for row in top_by_count:
            markdown_lines.append(
                f"- `{row['stem']}`: {row['file_count']} files, {row['total_size_mb']} MB"
            )
    else:
        markdown_lines.append("- 无")

    markdown_lines += ["", "## 按体积 Top10", ""]
    if top_by_size:
        for row in top_by_size:
            markdown_lines.append(
                f"- `{row['stem']}`: {row['total_size_mb']} MB, {row['file_count']} files"
            )
    else:
        markdown_lines.append("- 无")

    markdown_lines += ["", "## 详表", "", f"- `analysis_viz/docs/{OUT_CSV.name}`", ""]
    OUT_MD.write_text("\n".join(markdown_lines), encoding="utf-8")

    print("WROTE", OUT_CSV)
    print("WROTE", OUT_MD)
    print("FILES", total_files)
    print("SIZE_MB", f"{total_mb:.2f}")


if __name__ == "__main__":
    main()

