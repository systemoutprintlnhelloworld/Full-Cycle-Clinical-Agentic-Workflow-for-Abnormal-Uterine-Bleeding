"""Sync retained figure assets into analysis_viz/figures/variants.

Retention policy:
- Keep archive: outputs/archive/2026-02-06_05-24-36_latest/figures/{algorithmic,alignment}
- Keep latest: outputs/latest/figures/{algorithmic,alignment,calibration,sankey,special}
- Keep latest llm full: outputs/latest/figures/llm/full
- Exclude latest llm small summary: outputs/latest/figures/llm/small/summary
"""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VAR_ROOT = ROOT / "analysis_viz" / "figures" / "variants"


def _copy_tree(src: Path, dst: Path) -> tuple[int, int]:
    if not src.exists():
        return 0, 0
    dst.mkdir(parents=True, exist_ok=True)
    total = 0
    copied = 0
    for p in src.rglob("*"):
        if p.is_dir():
            continue
        total += 1
        rel = p.relative_to(src)
        t = dst / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        if t.exists() and t.stat().st_size == p.stat().st_size:
            continue
        shutil.copy2(p, t)
        copied += 1
    return total, copied


def main() -> None:
    jobs = [
        (
            ROOT / "outputs" / "archive" / "2026-02-06_05-24-36_latest" / "figures" / "algorithmic",
            VAR_ROOT / "archive_2026-02-06__algorithmic",
        ),
        (
            ROOT / "outputs" / "archive" / "2026-02-06_05-24-36_latest" / "figures" / "alignment",
            VAR_ROOT / "archive_2026-02-06__alignment",
        ),
        (
            ROOT / "outputs" / "latest" / "figures" / "algorithmic",
            VAR_ROOT / "outputs_latest__algorithmic",
        ),
        (
            ROOT / "outputs" / "latest" / "figures" / "alignment",
            VAR_ROOT / "outputs_latest__alignment",
        ),
        (
            ROOT / "outputs" / "latest" / "figures" / "calibration",
            VAR_ROOT / "outputs_latest__calibration",
        ),
        (
            ROOT / "outputs" / "latest" / "figures" / "sankey",
            VAR_ROOT / "outputs_latest__sankey",
        ),
        (
            ROOT / "outputs" / "latest" / "figures" / "special",
            VAR_ROOT / "outputs_latest__special",
        ),
        (
            ROOT / "outputs" / "latest" / "figures" / "llm" / "full",
            VAR_ROOT / "outputs_latest__llm_full",
        ),
    ]

    for src, dst in jobs:
        total, copied = _copy_tree(src, dst)
        print(f"SYNC {src} -> {dst}: total={total}, copied={copied}")

    print("NOTE excluded: outputs/latest/figures/llm/small/summary")


if __name__ == "__main__":
    main()

