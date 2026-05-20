from __future__ import annotations

from pathlib import Path

import pandas as pd

from .types import DataFileSet, LoadedData


SHEETS = [
    "D1_Outpatient_Loop",
    "D1_Outpatient_Decision",
    "D2_Admission_Loop",
    "D2_Admission_Decision",
    "D3_Surgery_Decision",
    "D4_Rehab_Plan",
]


def _resolve_sheet_name(xl: pd.ExcelFile, sheet: str) -> str:
    normal = f"{sheet}_正常"
    if normal in xl.sheet_names:
        return normal
    return sheet


def _read_excel_sheet_from_xl(xl: pd.ExcelFile, sheet: str) -> pd.DataFrame:
    resolved = _resolve_sheet_name(xl, sheet)
    return xl.parse(resolved)


def load_dataset(fileset: DataFileSet) -> LoadedData:
    gt = pd.read_excel(fileset.gt_path, sheet_name="Sheet1", engine="openpyxl")

    doc_sheets: dict[str, pd.DataFrame] = {}
    judge_sheets: dict[str, pd.DataFrame] = {}

    doc_xl = pd.ExcelFile(fileset.doc_path)
    judge_xl = pd.ExcelFile(fileset.judge_path)
    for sheet in SHEETS:
        doc_sheets[sheet] = _read_excel_sheet_from_xl(doc_xl, sheet)
        judge_sheets[sheet] = _read_excel_sheet_from_xl(judge_xl, sheet)

    return LoadedData(fileset=fileset, gt=gt, doc_sheets=doc_sheets, judge_sheets=judge_sheets)
