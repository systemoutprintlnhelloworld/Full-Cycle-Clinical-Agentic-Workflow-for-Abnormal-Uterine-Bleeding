"""Build plotting script inventory from figure registry and mapping tables."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FIG_REG = ROOT / "analysis_viz" / "docs" / "figure_registry.csv"
FIG_MAP = ROOT / "analysis_viz" / "docs" / "figure_metric_mapping.csv"
OUT_SUMMARY = ROOT / "analysis_viz" / "docs" / "plot_script_inventory.csv"
OUT_MISSING = ROOT / "analysis_viz" / "docs" / "plot_script_missing.csv"
OUT_MD = ROOT / "analysis_viz" / "docs" / "plot_script_inventory.md"


def main() -> None:
    rows: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []

    if FIG_REG.exists():
        with FIG_REG.open("r", encoding="utf-8-sig", newline="") as f:
            r = csv.DictReader(f)
            for rec in r:
                script_path = (rec.get("script_path") or "").strip()
                script_entry = (rec.get("script_entry") or "").strip()
                status = (rec.get("script_status") or "").strip()
                fig_rel = (rec.get("figure_relpath") or "").strip()
                fig_id = (rec.get("figure_id") or "").strip()
                if not script_path and not script_entry:
                    missing.append(
                        {
                            "source": "figure_registry",
                            "figure_id": fig_id,
                            "figure_relpath": fig_rel,
                            "reason": "no script path/entry",
                        }
                    )
                    continue
                rows.append(
                    {
                        "source": "figure_registry",
                        "figure_id": fig_id,
                        "figure_relpath": fig_rel,
                        "script_path": script_path,
                        "script_entry": script_entry,
                        "script_status": status,
                    }
                )
                if status and status.lower() not in {"found", "ok"}:
                    missing.append(
                        {
                            "source": "figure_registry",
                            "figure_id": fig_id,
                            "figure_relpath": fig_rel,
                            "reason": f"script_status={status}",
                        }
                    )

    if FIG_MAP.exists():
        with FIG_MAP.open("r", encoding="utf-8-sig", newline="") as f:
            r = csv.DictReader(f)
            for rec in r:
                rows.append(
                    {
                        "source": "figure_metric_mapping",
                        "figure_id": rec.get("figure_pattern", "").strip(),
                        "figure_relpath": rec.get("figure_dir", "").strip(),
                        "script_path": rec.get("script_primary", "").strip(),
                        "script_entry": rec.get("script_rebuild", "").strip(),
                        "script_status": "derived",
                    }
                )

    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    with OUT_SUMMARY.open("w", encoding="utf-8", newline="") as f:
        fields = ["source", "figure_id", "figure_relpath", "script_path", "script_entry", "script_status"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    with OUT_MISSING.open("w", encoding="utf-8", newline="") as f:
        fields = ["source", "figure_id", "figure_relpath", "reason"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in missing:
            w.writerow(r)

    # markdown summary
    script_counter = Counter([r["script_path"] for r in rows if r["script_path"]])
    lines: list[str] = []
    lines.append("# 绘图脚本索引（自动生成）")
    lines.append("")
    lines.append(f"- 总记录数：{len(rows)}")
    lines.append(f"- 缺失/异常记录数：{len(missing)}")
    lines.append("")
    lines.append("## 脚本使用频次")
    lines.append("")
    for sp, cnt in script_counter.most_common():
        lines.append(f"- `{sp}`: {cnt}")

    lines.append("")
    lines.append("## 输出文件")
    lines.append("")
    lines.append(f"- `analysis_viz/docs/{OUT_SUMMARY.name}`")
    lines.append(f"- `analysis_viz/docs/{OUT_MISSING.name}`")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("WROTE", OUT_SUMMARY)
    print("WROTE", OUT_MISSING)
    print("WROTE", OUT_MD)
    print("MISSING", len(missing))


if __name__ == "__main__":
    main()

