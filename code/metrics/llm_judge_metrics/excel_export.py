from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


@dataclass(frozen=True)
class ExcelSheetSpec:
    name: str
    df: pd.DataFrame


_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")  # dark blue
_HEADER_FONT = Font(color="FFFFFF", bold=True)

_FILL_GREEN = PatternFill("solid", fgColor="C6EFCE")
_FILL_ORANGE = PatternFill("solid", fgColor="FFEB9C")
_FILL_GREY = PatternFill("solid", fgColor="E7E6E6")
_FILL_RED = PatternFill("solid", fgColor="FFC7CE")

_INVALID_SHEET_CHARS = set("[]:*?/\\")


def _sanitize_sheet_name(name: str, used: set[str]) -> str:
    cleaned = "".join("-" if ch in _INVALID_SHEET_CHARS else ch for ch in (name or ""))
    cleaned = cleaned.strip() or "Sheet"
    cleaned = cleaned[:31]
    base = cleaned
    idx = 1
    while cleaned in used:
        suffix = f"_{idx}"
        cleaned = (base[: 31 - len(suffix)] + suffix) if len(base) + len(suffix) > 31 else base + suffix
        idx += 1
    used.add(cleaned)
    return cleaned


def export_metrics_source_data_xlsx(path: Path, sheets: list[ExcelSheetSpec]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        used_names: set[str] = set()
        for spec in sheets:
            df = spec.df.copy()
            if not df.empty:
                for col in df.columns:
                    if df[col].dtype == object:
                        df[col] = df[col].apply(
                            lambda v: ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v
                        )
            # Excel-friendly: avoid very large cells; keep as string
            sheet_name = _sanitize_sheet_name(spec.name, used_names)
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    wb = load_workbook(path)
    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        # Style header
        for cell in ws[1]:
            cell.fill = _HEADER_FILL
            cell.font = _HEADER_FONT

        # Reasonable column widths
        max_col = ws.max_column
        max_row = min(ws.max_row, 2000)
        for col_idx in range(1, max_col + 1):
            letter = get_column_letter(col_idx)
            values = []
            for row_idx in range(1, max_row + 1):
                v = ws.cell(row=row_idx, column=col_idx).value
                if v is None:
                    continue
                values.append(str(v))
            width = min(60, max([len(ws.cell(row=1, column=col_idx).value or "")] + [len(v) for v in values[:200]]))
            ws.column_dimensions[letter].width = max(8, width + 2)

        # Numeric readability for summary sheet
        if ws.title == "指标汇总_中心模型":
            for col_idx in range(1, max_col + 1):
                header = ws.cell(row=1, column=col_idx).value
                if not header:
                    continue
                h = str(header)
                # Skip count-like columns
                if any(k in h for k in ["样本数", "病例数", "通过数"]):
                    continue
                if any(k in h for k in ["率", "均值", "命中", "覆盖"]):
                    col_letter = get_column_letter(col_idx)
                    rng = f"{col_letter}2:{col_letter}{ws.max_row}"
                    ws.conditional_formatting.add(
                        rng,
                        ColorScaleRule(
                            start_type="min",
                            start_color="F8696B",
                            mid_type="percentile",
                            mid_value=50,
                            mid_color="FFEB84",
                            end_type="max",
                            end_color="63BE7B",
                        ),
                    )
                    for row_idx in range(2, ws.max_row + 1):
                        cell = ws.cell(row=row_idx, column=col_idx)
                        if isinstance(cell.value, (int, float)):
                            cell.number_format = "0.000"

        # Conditional formatting for common status strings
        # Apply to all columns that contain "status" or "状态" in header.
        status_cols = []
        for col_idx in range(1, max_col + 1):
            header = ws.cell(row=1, column=col_idx).value
            if not header:
                continue
            h = str(header)
            if "status" in h.lower() or "状态" in h:
                status_cols.append(col_idx)

        for col_idx in status_cols:
            col_letter = get_column_letter(col_idx)
            rng = f"{col_letter}2:{col_letter}{ws.max_row}"

            ws.conditional_formatting.add(
                rng,
                FormulaRule(formula=[f'ISNUMBER(SEARCH("顺利通过",{col_letter}2))'], fill=_FILL_GREEN),
            )
            ws.conditional_formatting.add(
                rng,
                FormulaRule(formula=[f'ISNUMBER(SEARCH("终止",{col_letter}2))'], fill=_FILL_ORANGE),
            )
            ws.conditional_formatting.add(
                rng,
                FormulaRule(formula=[f'ISNUMBER(SEARCH("未经过",{col_letter}2))'], fill=_FILL_GREY),
            )
            ws.conditional_formatting.add(
                rng,
                FormulaRule(formula=[f'ISNUMBER(SEARCH("Anomaly",{col_letter}2))'], fill=_FILL_RED),
            )

    wb.save(path)
