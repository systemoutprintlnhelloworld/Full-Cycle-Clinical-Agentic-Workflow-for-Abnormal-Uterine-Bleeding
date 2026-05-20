"""Sync center raw data (GT/doc agent/judge agent) into analysis_viz raw layer.

- Source: data/<center>/{GT, doc agent, judge agent}
- Target: analysis_viz/data/raw/center_data/<center>/{GT, doc agent, judge agent}
- Exclude any folder named bkup* or backup*
"""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "data"
DST_ROOT = ROOT / "analysis_viz" / "data" / "raw" / "center_data"

CENTERS = ["佛山", "新疆", "武汉"]
SUBDIRS = ["GT", "doc agent", "judge agent"]


def _is_excluded_dir(p: Path) -> bool:
    name = p.name.lower()
    return name.startswith("bkup") or name.startswith("backup")


def _copy_tree_filtered(src: Path, dst: Path) -> tuple[int, int]:
    file_count = 0
    copied_count = 0
    if not src.exists():
        return file_count, copied_count

    for path in src.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(src)

        skip = False
        for part in rel.parts[:-1]:
            name = part.lower()
            if name.startswith("bkup") or name.startswith("backup"):
                skip = True
                break
        if skip:
            continue

        file_count += 1
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size == path.stat().st_size:
            # quick skip, assumes unchanged when size equal
            continue
        shutil.copy2(path, target)
        copied_count += 1

    return file_count, copied_count


def main() -> None:
    DST_ROOT.mkdir(parents=True, exist_ok=True)
    total_files = 0
    total_copied = 0

    for center in CENTERS:
        for sub in SUBDIRS:
            src = SRC_ROOT / center / sub
            dst = DST_ROOT / center / sub
            n_all, n_cp = _copy_tree_filtered(src, dst)
            total_files += n_all
            total_copied += n_cp
            print(f"SYNC {center}/{sub}: files={n_all}, copied={n_cp}")

    print(f"DONE total_files={total_files}, total_copied={total_copied}")


if __name__ == "__main__":
    main()

