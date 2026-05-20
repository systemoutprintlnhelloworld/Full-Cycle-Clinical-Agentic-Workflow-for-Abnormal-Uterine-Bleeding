"""Audit outputs cleanup status and write markdown report."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs"
REPORT = ROOT / "analysis_viz" / "docs" / "outputs_cleanup_audit.md"


def _count_images(path: Path) -> int:
    exts = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".bmp", ".tif", ".tiff"}
    n = 0
    for p in path.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            n += 1
    return n


def main() -> None:
    dirs = sorted([p for p in OUT.iterdir() if p.is_dir()])
    archive_dirs = []
    if (OUT / "archive").exists():
        archive_dirs = sorted([p for p in (OUT / "archive").iterdir() if p.is_dir()])

    lines: list[str] = []
    lines.append("# outputs 清理审计报告")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- 扫描目录：`{OUT}`")
    lines.append("")
    lines.append("## 顶层目录")
    lines.append("")
    for p in dirs:
        lines.append(f"- `{p.name}`")

    lines.append("")
    lines.append("## 结论")
    lines.append("")

    top_ok = set(p.name for p in dirs) <= {"archive", "latest"}
    if top_ok:
        lines.append("- ✅ `outputs/` 顶层仅包含 `latest` 与 `archive`。")
    else:
        extra = sorted(set(p.name for p in dirs) - {"archive", "latest"})
        lines.append(f"- ❌ 顶层仍有额外目录：{extra}")

    if archive_dirs:
        lines.append("")
        lines.append("## archive 子目录")
        lines.append("")
        for p in archive_dirs:
            lines.append(f"- `{p.name}` (images={_count_images(p)})")

        keep_ok = [p.name for p in archive_dirs] == ["2026-02-06_05-24-36_latest"]
        if keep_ok:
            lines.append("")
            lines.append("- ✅ archive 仅保留 `2026-02-06_05-24-36_latest`。")
        else:
            lines.append("")
            lines.append("- ⚠️ archive 存在非预期目录（请复核）。")
    else:
        lines.append("- ⚠️ 未检测到 archive 子目录。")

    lines.append("")
    lines.append("## 历史清理记录")
    lines.append("")
    manifest = ROOT / "analysis_viz" / "docs" / "cleanup_manifest.csv"
    if manifest.exists():
        lines.append(f"- 见：`{manifest.relative_to(ROOT).as_posix()}`")
    else:
        lines.append("- 未找到 cleanup_manifest.csv")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("WROTE", REPORT)


if __name__ == "__main__":
    main()

