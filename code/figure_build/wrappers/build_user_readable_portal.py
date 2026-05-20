"""Build user-facing Chinese portal docs for analysis_viz."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_VIZ = ROOT / "analysis_viz"
PORTAL_DIR = ANALYSIS_VIZ / "给用户看"
FIGURE_MAP = ANALYSIS_VIZ / "docs" / "final_paper_bundle_figure_map.csv"
PORTAL_MAP_CSV = PORTAL_DIR / "02_图与数据对应清单.csv"


def _load_figure_rows() -> list[dict[str, str]]:
    if not FIGURE_MAP.exists():
        return []
    with FIGURE_MAP.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_map_csv(rows: list[dict[str, str]]) -> None:
    PORTAL_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "section_id",
        "figure_file",
        "figure_relpath",
        "source_data_relpath",
        "source_type",
        "source_status",
        "notes",
    ]
    with PORTAL_MAP_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_readme(rows: list[dict[str, str]]) -> None:
    missing_count = sum(1 for row in rows if row["source_status"] != "有")
    section_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"figures": 0, "missing": 0})
    for row in rows:
        sid = row["section_id"]
        section_stats[sid]["figures"] += 1
        if row["source_status"] != "有":
            section_stats[sid]["missing"] += 1

    lines: list[str] = []
    lines.append("# analysis_viz 用户阅读入口")
    lines.append("")
    lines.append("本目录只放“给你看”的高可读文档，不放工程脚本。")
    lines.append("")
    lines.append("## 先看这三个文件")
    lines.append("- `02_图与数据对应清单.csv`：每张图对应的数据源路径与缺失状态。")
    lines.append("- `03_目录释义_数据与图.md`：解释 raw/derived/figures 的区别。")
    lines.append("- `04_当前缺口与处理建议.md`：当前仍需补齐的项目。")
    lines.append("- `05_本轮整理总结.md`：本轮做了什么、还建议你抽查什么。")
    lines.append("")
    lines.append("## 当前覆盖统计")
    lines.append(f"- 图总数：{len(rows)}")
    lines.append(f"- 缺少明确source data的图数：{missing_count}")
    lines.append("")
    lines.append("## 按章节统计")
    for section_id in sorted(section_stats.keys()):
        stats = section_stats[section_id]
        lines.append(f"- {section_id}：图 {stats['figures']} 张，缺source {stats['missing']} 张")
    lines.append("")
    (PORTAL_DIR / "00_阅读入口.md").write_text("\n".join(lines), encoding="utf-8")


def _write_structure_doc() -> None:
    lines = [
        "# 目录释义：数据与图",
        "",
        "## `analysis_viz/data/raw`",
        "存放原始来源数据快照，保持与原评测结果同口径，不做加工。",
        "",
        "## `analysis_viz/data/derived`",
        "存放为绘图和论文汇总计算后的中间数据与指标表，属于可复现产物。",
        "",
        "## `analysis_viz/data/_backup_before_overwrite`",
        "为改写 Excel 样式或重建产物前的备份目录，默认不用于阅读。",
        "",
        "## `analysis_viz/figures/paper`",
        "论文主图原始拷贝（通常是 Fig1-Fig12 体系）。",
        "",
        "## `analysis_viz/figures/variants`",
        "同一指标的多风格/多版本图，便于比较展示风格与稳定性。",
        "",
        "## `analysis_viz/figures/final_paper_bundle`",
        "最终交付包：按结果章节分组并补充 variants 关键图组；每个多图目录附 `caption.md`。",
        "",
    ]
    (PORTAL_DIR / "03_目录释义_数据与图.md").write_text("\n".join(lines), encoding="utf-8")


def _write_gap_doc(rows: list[dict[str, str]]) -> None:
    missing_rows = [row for row in rows if row["source_status"] != "有"]
    lines = [
        "# 当前缺口与处理建议",
        "",
        "## 缺口定义",
        "当某张图没有可直接定位的 `source_data` 文件时，标记为“缺失”，需要后续补录或重算。",
        "",
        f"## 当前缺口数量：{len(missing_rows)}",
        "",
    ]
    if missing_rows:
        lines.append("## 缺口明细（前50条）")
        for row in missing_rows[:50]:
            lines.append(
                f"- {row['section_id']} / {row['figure_file']}：{row['notes'] or '无匹配source_data'}"
            )
        lines.append("")
    lines.extend(
        [
            "## 建议处理顺序",
            "1. 先补齐 final_paper_bundle 中用于论文正文的图（Fig1/2/3/4/5/7/8/9/11）。",
            "2. 再补 variants 中需展示的记忆/一致性/推理与算法图。",
            "3. 对确实无法回溯的图，保留缺口说明并标注“需重跑评测”。",
            "",
        ]
    )
    (PORTAL_DIR / "04_当前缺口与处理建议.md").write_text("\n".join(lines), encoding="utf-8")


def _write_todo_csv(rows: list[dict[str, str]]) -> None:
    todo_file = PORTAL_DIR / "任务进度跟踪.csv"
    with todo_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["任务", "状态", "说明", "关联文件"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "任务": "图与source data一一对应梳理",
                "状态": "进行中",
                "说明": f"当前共梳理 {len(rows)} 张图，缺口需继续补齐。",
                "关联文件": "analysis_viz/给用户看/02_图与数据对应清单.csv",
            }
        )
        writer.writerow(
            {
                "任务": "多图目录caption.md补齐",
                "状态": "进行中",
                "说明": "每图图注不少于40字，包含元素解释与解读目的。",
                "关联文件": "analysis_viz/figures/**/caption.md",
            }
        )


def main() -> None:
    figure_rows = _load_figure_rows()
    output_rows: list[dict[str, str]] = []
    for row in figure_rows:
        source_data = (row.get("source_data_relpath") or "").strip()
        output_rows.append(
            {
                "section_id": row.get("section_id", ""),
                "figure_file": row.get("figure_file", ""),
                "figure_relpath": row.get("figure_relpath", ""),
                "source_data_relpath": source_data,
                "source_type": row.get("source_type", ""),
                "source_status": "有" if source_data else "缺失",
                "notes": row.get("notes", ""),
            }
        )

    _write_map_csv(output_rows)
    _write_readme(output_rows)
    _write_structure_doc()
    _write_gap_doc(output_rows)
    _write_todo_csv(output_rows)

    print("WROTE", PORTAL_MAP_CSV)
    print("WROTE", PORTAL_DIR / "00_阅读入口.md")
    print("WROTE", PORTAL_DIR / "03_目录释义_数据与图.md")
    print("WROTE", PORTAL_DIR / "04_当前缺口与处理建议.md")
    print("WROTE", PORTAL_DIR / "任务进度跟踪.csv")


if __name__ == "__main__":
    main()
