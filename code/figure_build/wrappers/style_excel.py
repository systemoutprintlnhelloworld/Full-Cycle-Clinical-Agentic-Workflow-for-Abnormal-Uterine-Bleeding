"""Apply readability styling to selected xlsx files.

User requirement: allow overwriting the original Excel files.
Safety: this script always backs up the original to
`analysis_viz/data/_backup_before_overwrite/` before overwriting.

Styling rules (lightweight, consistent):
- Freeze top row
- Enable auto filter
- Auto-size columns (approx)
- Conditional formatting: max numeric in each numeric column -> bold red

This is intentionally conservative to avoid breaking formulas.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Font


ROOT = Path(__file__).resolve().parents[3]
BACKUP_DIR = ROOT / "analysis_viz" / "data" / "_backup_before_overwrite"
MAX_BACKUPS_PER_FILE = 20


def _prune_old_backups(stem: str) -> None:
    pattern = f"{stem}__backup_*.xlsx"
    backups = sorted(BACKUP_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[MAX_BACKUPS_PER_FILE:]:
        try:
            old.unlink()
        except Exception:
            continue


def _backup(path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest = BACKUP_DIR / f"{path.stem}__backup_{ts}{path.suffix}"
    dest.write_bytes(path.read_bytes())
    _prune_old_backups(path.stem)
    return dest


def _autosize(ws: openpyxl.worksheet.worksheet.Worksheet) -> None:
    max_width: dict[int, int] = {}
    for row in ws.iter_rows(values_only=True):
        for idx, value in enumerate(row, start=1):
            if value is None:
                continue
            s = str(value)
            max_width[idx] = max(max_width.get(idx, 0), min(60, len(s) + 2))
    for idx, width in max_width.items():
        col = openpyxl.utils.get_column_letter(idx)
        ws.column_dimensions[col].width = max(10, float(width))


def _style_sheet(ws: openpyxl.worksheet.worksheet.Worksheet) -> None:
    if ws.max_row < 1 or ws.max_column < 1:
        return

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # Conditional formatting: highlight max in numeric columns.
    red_bold = Font(color="FF0000", bold=True)
    for col_idx in range(1, ws.max_column + 1):
        col_letter = openpyxl.utils.get_column_letter(col_idx)
        rng = f"{col_letter}2:{col_letter}{ws.max_row}"
        # Apply only if there is at least one numeric cell.
        has_numeric = False
        for cell in ws[rng]:
            for c in cell:
                if isinstance(c.value, (int, float)):
                    has_numeric = True
                    break
            if has_numeric:
                break
        if not has_numeric:
            continue
        ws.conditional_formatting.add(
            rng,
            CellIsRule(operator="equal", formula=[f"MAX({rng})"], font=red_bold),
        )

    _autosize(ws)


def style_workbook(path: Path) -> tuple[Path, Path]:
    backup = _backup(path)
    wb = openpyxl.load_workbook(path)
    for name in wb.sheetnames:
        _style_sheet(wb[name])
    wb.save(path)
    wb.close()
    return path, backup


def main() -> None:
    targets = [
        ROOT / "analysis_viz" / "data" / "derived" / "metrics" / "llm_reasoning_source.xlsx",
        ROOT / "analysis_viz" / "data" / "derived" / "metrics" / "llm_consistency_source.xlsx",
        ROOT / "analysis_viz" / "data" / "derived" / "metrics" / "llm_memory_source.xlsx",
        ROOT / "analysis_viz" / "data" / "derived" / "figdata" / "paper" / "Fig3__check_match_rate_source.xlsx",
        ROOT / "analysis_viz" / "data" / "derived" / "figdata" / "paper" / "Fig3__loop_inefficiency_source.xlsx",
        ROOT / "analysis_viz" / "data" / "derived" / "figdata" / "paper" / "Fig7__sankey_flow_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "figdata"
        / "outputs_latest"
        / "sankey"
        / "Fig7__sankey_flow_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "algorithmic"
        / "algorithmic_check_match_rate_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "algorithmic"
        / "algorithmic_loop_inefficiency_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "algorithmic"
        / "algorithmic_stage_pass_rate_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "algorithmic"
        / "algorithmic_judge_scores_by_stage_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "algorithmic"
        / "algorithmic_judge_score_pathways_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "algorithmic"
        / "algorithmic_judge_scores_stagewise_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "algorithmic"
        / "algorithmic_loop_inefficiency_stagewise_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "algorithmic"
        / "algorithmic_stage_no_exit_rate_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "calibration"
        / "calibration_ece_stagewise_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "calibration"
        / "calibration_reliability_stagewise_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "calibration"
        / "calibration_bubble_check_stagewise_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "calibration"
        / "calibration_bubble_diagnosis_stagewise_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "calibration"
        / "calibration_bubble_plan_stagewise_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "calibration"
        / "calibration_line_overall_stagewise_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "calibration"
        / "calibration_line_check_stagewise_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "calibration"
        / "calibration_line_diagnosis_stagewise_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "calibration"
        / "calibration_line_plan_stagewise_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "manual"
        / "manual_result_quality_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "manual"
        / "manual_reasoning_quality_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "alignment"
        / "alignment_result_vs_judge_case_level_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "alignment"
        / "alignment_reasoning_vs_llm_case_level_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "alignment"
        / "alignment_doctor_consensus_result_source.xlsx",
        ROOT
        / "analysis_viz"
        / "data"
        / "derived"
        / "metrics"
        / "alignment"
        / "alignment_doctor_consensus_reasoning_source.xlsx",
    ]
    for path in targets:
        if not path.exists():
            print("MISSING", path)
            continue
        out, backup = style_workbook(path)
        print("STYLED", out)
        print("BACKUP", backup)


if __name__ == "__main__":
    main()
