import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SPECIAL_SHEETS = ["D2_Admission_Loop_特殊D1", "D2_Admission_Decision_特殊D1"]


def _iter_backup_dirs(agent_dir: Path) -> list[Path]:
    return sorted([p for p in agent_dir.iterdir() if p.is_dir() and p.name.startswith("bkup_")])


def _find_latest_backup_file(agent_dir: Path, stem_prefix: str) -> Path | None:
    candidates: list[Path] = []
    for bkup in _iter_backup_dirs(agent_dir):
        for path in bkup.glob(f"{stem_prefix}_*.xlsx"):
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _load_special_ids(path: Path) -> set[str]:
    try:
        xl = pd.ExcelFile(path)
    except Exception:
        return set()
    special_ids: set[str] = set()
    for sheet in SPECIAL_SHEETS:
        if sheet not in xl.sheet_names:
            continue
        df = xl.parse(sheet)
        if df.empty:
            continue
        cid_col = df.columns[0]
        ids = df[cid_col].dropna().astype(str).str.strip().tolist()
        special_ids.update({cid for cid in ids if cid})
    return special_ids


def _restore_special_sheets(current_path: Path, backup_path: Path, special_ids: set[str]) -> bool:
    if not special_ids:
        return False
    try:
        current_xl = pd.ExcelFile(current_path)
    except Exception:
        return False
    try:
        backup_xl = pd.ExcelFile(backup_path)
    except Exception:
        return False

    restored_any = False
    with pd.ExcelWriter(current_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        for sheet in SPECIAL_SHEETS:
            if sheet in backup_xl.sheet_names:
                df = backup_xl.parse(sheet)
                df.to_excel(writer, sheet_name=sheet, index=False)
                restored_any = True
        # D1 loop special sheet rebuild from current D1 loop
        if "D1_Outpatient_Loop" in current_xl.sheet_names:
            df_d1 = current_xl.parse("D1_Outpatient_Loop")
            if not df_d1.empty:
                cid_col = df_d1.columns[0]
                mask = df_d1[cid_col].astype(str).str.strip().isin(special_ids)
                df_special = df_d1.loc[mask].copy()
                df_special.to_excel(writer, sheet_name="D1_Outpatient_Loop_特殊D1", index=False)
                restored_any = True
    return restored_any


def _iter_current_excels(agent_dir: Path, pattern: str) -> Iterable[Path]:
    yield from agent_dir.glob(pattern)


def main() -> None:
    data_root = PROJECT_ROOT / "data"
    updated = 0
    for center_dir in data_root.iterdir():
        if not center_dir.is_dir():
            continue
        for agent, pattern in [("doc agent", "Evaluation_Summary_*_CN_Parsed.xlsx"), ("judge agent", "Evaluation_Summary_*_CN_Judge_Parsed.xlsx")]:
            agent_dir = center_dir / agent
            if not agent_dir.exists():
                continue
            for current_path in _iter_current_excels(agent_dir, pattern):
                backup_path = _find_latest_backup_file(agent_dir, current_path.stem)
                if not backup_path:
                    continue
                special_ids = _load_special_ids(backup_path)
                if not special_ids:
                    continue
                if _restore_special_sheets(current_path, backup_path, special_ids):
                    updated += 1
    print(f"restored_special_sheets={updated}")


if __name__ == "__main__":
    main()
