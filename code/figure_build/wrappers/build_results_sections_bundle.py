"""Build results-section bundle from paper figures and figdata.

Output:
- analysis_viz/figures/results_sections/<section>/{figures,figdata}
- analysis_viz/docs/results_section_manifest.csv
"""

from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PAPER_FIG = ROOT / "论文" / "figures"
PAPER_FIGDATA = ROOT / "论文" / "figdata"

OUT_ROOT = ROOT / "analysis_viz" / "figures" / "results_sections"
MANIFEST = ROOT / "analysis_viz" / "docs" / "results_section_manifest.csv"

SECTIONS: list[tuple[str, tuple[str, ...], str]] = [
    ("01_dataset_split", ("Fig1",), "数据集划分与复杂度"),
    ("02_overall_summary", ("Fig2", "Fig4", "Fig11"), "整体情况汇总（人工/LLM/人机对齐）"),
    ("03_outcome_metrics", ("Fig3", "Fig8"), "结果性指标（诊断/检查/Judge score）"),
    ("04_continuity_metrics", ("Fig9",), "持续性指标（一致性/记忆）"),
    ("05_system_framework_metrics", ("Fig5", "Fig7"), "系统框架指标（校准/流程）"),
    ("06_placeholders", ("Fig10", "Fig12"), "占位图（待补数据）"),
    ("07_optional_small_scale", ("Fig6",), "可选小规模图（当前非论文主展示）"),
]

FIG_TOKEN_RE = re.compile(r"^(Fig\d+)(?:[A-Za-z]?)(?:_|\.|$)")


def _extract_figure_token(name: str) -> str:
    match = FIG_TOKEN_RE.match(name)
    if not match:
        return ""
    return match.group(1)


def _match_prefix(name: str, prefixes: tuple[str, ...]) -> bool:
    token = _extract_figure_token(name)
    if not token:
        return False
    return token in set(prefixes)


def _copy(src: Path, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return False
    shutil.copy2(src, dst)
    return True


def main() -> None:
    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []

    fig_files = sorted([p for p in PAPER_FIG.glob("*.png")])
    data_files = sorted([p for p in PAPER_FIGDATA.glob("*") if p.is_file()])

    for sec_id, prefixes, sec_desc in SECTIONS:
        sec_dir = OUT_ROOT / sec_id
        fig_dir = sec_dir / "figures"
        dat_dir = sec_dir / "figdata"
        fig_dir.mkdir(parents=True, exist_ok=True)
        dat_dir.mkdir(parents=True, exist_ok=True)

        sec_figs = [p for p in fig_files if _match_prefix(p.name, prefixes)]
        sec_data = [p for p in data_files if _match_prefix(p.name, prefixes)]

        # special add: Fig7 derived audit source
        if sec_id == "05_system_framework_metrics":
            fig7_derived = ROOT / "analysis_viz" / "data" / "derived" / "figdata" / "paper" / "Fig7__sankey_flow_source.xlsx"
            if fig7_derived.exists():
                sec_data.append(fig7_derived)

        copied_fig = 0
        copied_data = 0

        for p in sec_figs:
            if _copy(p, fig_dir / p.name):
                copied_fig += 1

        for p in sec_data:
            if _copy(p, dat_dir / p.name):
                copied_data += 1

        rows.append(
            {
                "section_id": sec_id,
                "section_desc": sec_desc,
                "figure_prefixes": "|".join(prefixes),
                "figure_count": str(len(sec_figs)),
                "figdata_count": str(len(sec_data)),
                "copied_figure_count": str(copied_fig),
                "copied_figdata_count": str(copied_data),
                "output_dir": str(sec_dir.relative_to(ROOT)).replace("\\", "/"),
                "notes": "Fig6 marked optional; llm/small/summary excluded from main paper display",
            }
        )

    with MANIFEST.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "section_id",
            "section_desc",
            "figure_prefixes",
            "figure_count",
            "figdata_count",
            "copied_figure_count",
            "copied_figdata_count",
            "output_dir",
            "notes",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print("WROTE", MANIFEST)
    for r in rows:
        print(f"{r['section_id']}: figures={r['figure_count']}, figdata={r['figdata_count']}")


if __name__ == "__main__":
    main()

