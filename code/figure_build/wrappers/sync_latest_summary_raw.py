"""Sync outputs/latest/summary files into analysis_viz raw snapshot."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "outputs" / "latest" / "summary"
DST = ROOT / "analysis_viz" / "data" / "raw" / "latest_summary_snapshot"


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing: {SRC}")
    DST.mkdir(parents=True, exist_ok=True)

    copied = 0
    total = 0
    for p in sorted(SRC.iterdir()):
        if not p.is_file():
            continue
        if p.name.startswith("~$"):
            continue
        total += 1
        t = DST / p.name
        if t.exists() and t.stat().st_size == p.stat().st_size:
            continue
        shutil.copy2(p, t)
        copied += 1
    print(f"SYNC summary snapshot: total={total}, copied={copied}")


if __name__ == "__main__":
    main()

