"""Build journal submission figure bundle from paper-facing v2_subplots assets.

Input:
- default: analysis_viz/figures/v2_subplots/ mapped to manuscript Figure 2-5
- optional legacy mode: analysis_viz/docs/final_paper_bundle_figure_map.csv

Output:
- work/paper_crosscheck/<run_id>/submission_bundle/
  - source data.xlsx
  - source_data_manifest.csv
  - FigXX/
    - source_data/FigXX_source_data.xlsx
    - plot_data/
    - scripts/
    - render/
    - manifest.json
  - Supplementary_Table_special_case.xlsx
  - special_case_reference_rewrite.csv

Notes:
- This script reorganizes existing assets for journal submission and does not
  recompute figures from scratch.
- Manuscript Figure 1 is intentionally excluded because the final workflow
  figure is maintained outside v2_subplots.
- SVG/PDF export is strict by default. Native vector sidecars must already
  exist next to the PNG; raster-embedded SVG wrappers are never generated.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_VIZ = ROOT / "analysis_viz"
DEFAULT_FIGURE_MAP = ANALYSIS_VIZ / "docs" / "final_paper_bundle_figure_map.csv"
DEFAULT_OUTPUT_BASE = ROOT / "work" / "paper_crosscheck"
V2_ROOT = ANALYSIS_VIZ / "figures" / "v2_subplots"

FIG_REGEX = re.compile(r"(?i)^(fig)(\d+)([a-z]?)")
SPECIAL_REGEX = re.compile(r"(?i)special")
EXCEL_MAX_ROWS = 1_048_000
DEFAULT_ROWS_PER_SUBPLOT_SHEET = 150_000
JOURNAL_SOURCE_WORKBOOK_NAME = "source data.xlsx"
JOURNAL_SOURCE_MANIFEST_NAME = "source_data_manifest.csv"
PROVENANCE_COLUMN_PATTERNS = (
    "source",
    "path",
    "__source",
    "source_file",
    "source_path",
    "source_paths",
    "source_sheet",
    "source_table",
    "source_column",
    "source_gt_path",
    "source_doc_path",
    "source_judge_path",
    "trace_path",
    "html_path",
    "来源文件",
    "来源路径",
    "原始路径",
    "本地路径",
)
LOCAL_PATH_VALUE_PATTERNS = (
    "analysis_viz/",
    "analysis_viz\\",
    "D:\\",
    "d:\\",
    ".xlsx:",
    ".jsonl",
    ".html",
)


@dataclass(frozen=True)
class FigureRow:
    section_id: str
    figure_file: str
    figure_relpath: str
    source_data_relpath: str
    source_type: str
    notes: str


@dataclass(frozen=True)
class SourceItem:
    path: Path
    sheets: tuple[str, ...] | None = None


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _default_run_id() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S_paper-crosscheck")


def _rel_to_root(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT)).replace("\\", "/")


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _safe_sheet_name(name: str, used: set[str]) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]", "_", name).strip()
    cleaned = cleaned[:31] if len(cleaned) > 31 else cleaned
    candidate = cleaned or "sheet"
    index = 1
    while candidate in used:
        suffix = f"_{index}"
        candidate = f"{cleaned[:31-len(suffix)]}{suffix}"
        index += 1
    used.add(candidate)
    return candidate


def _load_rows(path: Path) -> list[FigureRow]:
    if not path.exists():
        raise FileNotFoundError(f"figure map not found: {path}")
    rows: list[FigureRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for item in csv.DictReader(handle):
            rows.append(
                FigureRow(
                    section_id=(item.get("section_id") or "").strip(),
                    figure_file=(item.get("figure_file") or "").strip(),
                    figure_relpath=(item.get("figure_relpath") or "").strip(),
                    source_data_relpath=(item.get("source_data_relpath") or "").strip(),
                    source_type=(item.get("source_type") or "").strip(),
                    notes=(item.get("notes") or "").strip(),
                )
            )
    return rows


def _src(relpath: str, *sheets: str) -> str:
    suffix = f"::{','.join(sheets)}" if sheets else ""
    return f"{relpath}{suffix}"


def _load_v2_manuscript_rows() -> list[FigureRow]:
    """Return the canonical 5.12 manuscript figure map.

    The numbering follows the Word manuscript, not the internal G1-G4 folder
    names. Figure 1 is only packaged for panel c, whose plot source is the
    S1 human-vs-judge alignment bar chart used in the final manuscript.
    """

    fig1c_source = "analysis_viz/figures/v2_subplots/S1_manual_vs_llm/source_data/S1_manual_vs_llm_v6_source.xlsx"
    g1_source = "analysis_viz/figures/v2_subplots/G1_dataset/source_data/G1_dataset_overview_v2_source.xlsx"
    g2_source = "analysis_viz/figures/v2_subplots/G2_outcome/source_data/G2_outcome_metrics_v6_source.xlsx"
    g3_source = "analysis_viz/figures/v2_subplots/G3_continuity/source_data/G3_continuity_metrics_v4_source.xlsx"
    g4_source = "analysis_viz/figures/v2_subplots/G4_system/source_data/G4_system_metrics_v2_source.xlsx"

    rows = [
        # Manuscript Figure 1c -> S1_manual_vs_llm
        FigureRow("manuscript_fig01", "Fig1c_S1_manual_vs_llm_side_by_side_bar_v1.png", "analysis_viz/figures/v2_subplots/S1_manual_vs_llm/S1_manual_vs_llm_side_by_side_bar_v1.png", _src(fig1c_source, "明细_S1_结果", "明细_S1_逻辑", "计算_S1_结果4", "计算_S1_逻辑4", "汇总_S1_结果_模型_阶段_paper", "汇总_S1_逻辑_模型_阶段_paper"), "v2_subplots_xlsx", "Manuscript Figure 1c; human expert versus automated judge result and reasoning quality across D1-D4."),
        # Manuscript Figure 2 -> G1_dataset
        FigureRow("manuscript_fig02", "Fig2a_G1a_center_distribution_v2.png", "analysis_viz/figures/v2_subplots/G1_dataset/G1a_center_distribution_v2.png", _src(g1_source, "明细_中心", "汇总_中心", "汇总_中心_benign_malignant"), "v2_subplots_xlsx", "Manuscript Figure 2a; G1 dataset center and disease-structure panel."),
        FigureRow("manuscript_fig02", "Fig2b_G1b_palm_coein_stage_bar_v1.png", "analysis_viz/figures/v2_subplots/G1_dataset/G1b_palm_coein_stage_bar_v1.png", _src(g1_source, "明细_诊断_阶段_palm", "汇总_诊断_阶段_palm"), "v2_subplots_xlsx", "Manuscript Figure 2b; PALM-COEIN stage distribution."),
        FigureRow("manuscript_fig02", "Fig2c_G1c_text_density_v2.png", "analysis_viz/figures/v2_subplots/G1_dataset/G1c_text_density_v2.png", _src(g1_source, "明细_text_len", "汇总_text_len"), "v2_subplots_xlsx", "Manuscript Figure 2c; record text-density distribution."),
        FigureRow("manuscript_fig02", "Fig2d_G1d_icd_chapter_v2.png", "analysis_viz/figures/v2_subplots/G1_dataset/G1d_icd_chapter_v2.png", _src(g1_source, "明细_icd", "明细_icd_病例", "汇总_icd"), "v2_subplots_xlsx", "Manuscript Figure 2d; ICD code distribution."),
        FigureRow("manuscript_fig02", "Fig2e_G1e_longtail_palm_line_v1.png", "analysis_viz/figures/v2_subplots/G1_dataset/G1e_longtail_palm_line_v1.png", _src(g1_source, "明细_longtail", "汇总_longtail"), "v2_subplots_xlsx", "Manuscript Figure 2e; PALM-COEIN long-tail distribution."),
        FigureRow("manuscript_fig02", "Fig2f_G1f_check_profile_v2.png", "analysis_viz/figures/v2_subplots/G1_dataset/G1f_check_profile_v2.png", _src(g1_source, "明细_检查_type", "明细_检查_type_病例_level", "汇总_检查_type"), "v2_subplots_xlsx", "Manuscript Figure 2f; outpatient/admission examination spectrum."),
        FigureRow("manuscript_fig02", "Fig2g_G1g_plan_mix_stacked_bar_v1.png", "analysis_viz/figures/v2_subplots/G1_dataset/G1g_plan_mix_stacked_bar_v1.png", _src(g1_source, "明细_方案_type", "明细_方案_continuity", "汇总_方案_type"), "v2_subplots_xlsx", "Manuscript Figure 2g; treatment and follow-up plan mix."),
        # Manuscript Figure 3 -> G2_outcome
        FigureRow("manuscript_fig03", "Fig3a_G2A_diagnostic_quality_v2.png", "analysis_viz/figures/v2_subplots/G2_outcome/G2A_diagnostic_quality_v2.png", _src(g2_source, "明细_G2_诊断", "汇总_G2_诊断_模型"), "v2_subplots_xlsx", "Manuscript Figure 3a; staged diagnostic quality."),
        FigureRow("manuscript_fig03", "Fig3b_G2B_diag_robustness_final_palm_v2.png", "analysis_viz/figures/v2_subplots/G2_outcome/G2B_diag_robustness_final_palm_v2.png", _src(g2_source, "明细_G2_palm_final", "汇总_G2_palm_final"), "v2_subplots_xlsx", "Manuscript Figure 3b; PALM-COEIN-stratified final diagnosis."),
        FigureRow("manuscript_fig03", "Fig3c_G2C_check_efficiency_merged_v3.png", "analysis_viz/figures/v2_subplots/G2_outcome/G2C_check_efficiency_merged_v3.png", _src(g2_source, "明细_G2_检查2", "明细_G2_ineff2", "计算_G2_检查_病例", "计算_G2_检查_统计", "汇总_G2_检查_模型", "汇总_G2_ineff_模型"), "v2_subplots_xlsx", "Manuscript Figure 3c; examination quality and ineffective-loop rate."),
        FigureRow("manuscript_fig03", "Fig3d_G2D_plan_alignment_semantic_v1.png", "analysis_viz/figures/v2_subplots/G2_outcome/G2D_plan_alignment_semantic_v1.png", _src(g2_source, "明细_G2_方案", "汇总_G2_方案_模型"), "v2_subplots_xlsx", "Manuscript Figure 3d; treatment and follow-up plan quality."),
        # Manuscript Figure 4 -> G3_continuity
        FigureRow("manuscript_fig04", "Fig4a_G3A_memory_trend_v2.png", "analysis_viz/figures/v2_subplots/G3_continuity/G3A_memory_trend_v2.png", _src(g3_source, "明细_记忆_原始", "汇总_记忆_评分", "汇总_记忆_一致_component_阶段"), "v2_subplots_xlsx", "Manuscript Figure 4a; memory-retention trend."),
        FigureRow("manuscript_fig04", "Fig4b_G3B_consistency_trend_v2.png", "analysis_viz/figures/v2_subplots/G3_continuity/G3B_consistency_trend_v2.png", _src(g3_source, "明细_一致_事实_原始", "明细_一致_跨阶段_原始", "汇总_一致_评分", "汇总_记忆_一致_component_阶段"), "v2_subplots_xlsx", "Manuscript Figure 4b; same-stage and cross-stage consistency."),
        FigureRow("manuscript_fig04", "Fig4c_G3C_reasoning_trend_v2.png", "analysis_viz/figures/v2_subplots/G3_continuity/G3C_reasoning_trend_v2.png", _src(g3_source, "明细_推理_原始", "计算_推理_阶段", "汇总_推理_评分"), "v2_subplots_xlsx", "Manuscript Figure 4c; reasoning-chain quality."),
        FigureRow("manuscript_fig04", "Fig4d_G3D_memory_event_count_v2.png", "analysis_viz/figures/v2_subplots/G3_continuity/G3D_memory_event_count_v2.png", _src(g3_source, "汇总_记忆_事件_布尔", "汇总_记忆_事件_stack"), "v2_subplots_xlsx", "Manuscript Figure 4d; memory-related risk events."),
        FigureRow("manuscript_fig04", "Fig4e_G3E_consistency_event_count_v2.png", "analysis_viz/figures/v2_subplots/G3_continuity/G3E_consistency_event_count_v2.png", _src(g3_source, "汇总_一致_事件_布尔", "汇总_一致_事件_stack"), "v2_subplots_xlsx", "Manuscript Figure 4e; consistency-related risk events."),
        FigureRow("manuscript_fig04", "Fig4f_G3F_reasoning_event_count_v2.png", "analysis_viz/figures/v2_subplots/G3_continuity/G3F_reasoning_event_count_v2.png", _src(g3_source, "汇总_推理_事件_布尔", "汇总_推理_事件_stack"), "v2_subplots_xlsx", "Manuscript Figure 4f; reasoning-related risk events."),
        # Manuscript Figure 5 -> G4_system. The 5c panel uses the current
        # paper-facing ablation panel; special D1 is exported as a table below.
        FigureRow("manuscript_fig05", "Fig5a_G4A_sankey_arrow_rect_v1.png", "analysis_viz/figures/v2_subplots/G4_system/G4A_sankey_arrow_rect_v1.png", _src(g4_source, "明细_桑基_已用", "汇总_桑基_节点", "汇总_桑基_连线"), "v2_subplots_xlsx", "Manuscript Figure 5a; D1-D4 state transition and completion flow."),
        FigureRow("manuscript_fig05", "Fig5b_G4B_calibration_overall_weighted_v6.png", "analysis_viz/figures/v2_subplots/G4_system/G4B_calibration_overall_weighted_v6.png", _src(g4_source, "明细_校准_病例", "明细_校准_分箱", "汇总_b0_points", "汇总_b_阶段_模型_points"), "v2_subplots_xlsx", "Manuscript Figure 5b; staged confidence-accuracy calibration."),
        FigureRow("manuscript_fig05", "Fig5c_G4C_ablation_diag_dumbbell_v1.png", "analysis_viz/figures/v2_subplots/G4_system/G4C_ablation_diag_dumbbell_v1.png", _src("analysis_viz/figures/v2_subplots/_supplementary/ablation/source_data/ablation_source_all_in_one_v3_diag_only.xlsx", "图1_明细_总体哑铃", "图1_计算_总体哑铃", "图1_汇总_总体哑铃"), "v2_subplots_xlsx", "Manuscript Figure 5c; active-check ablation diagnostic impact."),
        # Supplementary table conversion for the special D1 shortcut.
        FigureRow("supplementary_special_table", "Supplementary_Table_special_d1_shortcut.xlsx", "", _src(g4_source, "明细_特殊_病例", "汇总_特殊_病例"), "v2_subplots_xlsx", "special D1 shortcut is converted from a figure into a supplementary table."),
    ]
    return rows


def _is_special(row: FigureRow) -> bool:
    haystack = " ".join(
        [row.section_id, row.figure_file, row.figure_relpath, row.source_data_relpath, row.notes]
    )
    return bool(SPECIAL_REGEX.search(haystack))


def _figure_group(row: FigureRow, include_nonfig: bool) -> str | None:
    match = FIG_REGEX.match(row.figure_file)
    if match:
        number = int(match.group(2))
        return f"Fig{number:02d}"
    if not include_nonfig:
        return None
    stem = Path(row.figure_file).stem
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower()
    slug = slug[:24] if slug else "misc"
    return f"FigMisc-{slug}"


def _subfigure_key(row: FigureRow) -> str:
    match = FIG_REGEX.match(row.figure_file)
    if match:
        number = int(match.group(2))
        letter = match.group(3).lower()
        return f"Fig{number}{letter}" if letter else f"Fig{number}"
    stem = Path(row.figure_file).stem
    return re.sub(r"[^A-Za-z0-9]+", "_", stem)[:30] or "subplot"


def _subfigure_sort_key(row: FigureRow) -> tuple[int, str, str]:
    match = FIG_REGEX.match(row.figure_file)
    if match:
        return int(match.group(2)), match.group(3).lower(), row.figure_file
    return 10_000, "", row.figure_file


def _journal_sheet_base(row: FigureRow) -> str:
    match = FIG_REGEX.match(row.figure_file)
    if match:
        number = int(match.group(2))
        letter = match.group(3).lower()
        return f"Fig. {number}{letter}" if letter else f"Fig. {number}"
    return _subfigure_key(row)


def _parse_source_part(part: str) -> tuple[str, tuple[str, ...] | None]:
    if "::" not in part:
        return part, None
    rel, sheet_text = part.split("::", 1)
    sheets = tuple(s.strip() for s in sheet_text.split(",") if s.strip())
    return rel, sheets or None


def _resolve_source_items(row: FigureRow) -> list[SourceItem]:
    out: list[SourceItem] = []
    parts = [part.strip() for part in row.source_data_relpath.split("|") if part.strip()]
    for part in parts:
        rel, sheets = _parse_source_part(part)
        path = ROOT / rel
        if path.exists() and path.is_file():
            out.append(SourceItem(path.resolve(), sheets))
    return out


def _source_item_paths(items: Iterable[SourceItem]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for item in items:
        if item.path in seen:
            continue
        seen.add(item.path)
        paths.append(item.path)
    return paths


def _pick_subplot_sources(row: FigureRow, all_sources: list[SourceItem]) -> list[SourceItem]:
    if not all_sources:
        return []
    if any(item.sheets for item in all_sources):
        return all_sources
    subkey = _subfigure_key(row).lower()
    preferred = [item for item in all_sources if item.path.stem.lower().startswith(f"{subkey}__")]
    if preferred:
        return preferred

    figure_match = re.match(r"(?i)fig(\d+)", subkey)
    if figure_match:
        master = f"fig{int(figure_match.group(1))}"
        master_sources = [item for item in all_sources if item.path.stem.lower().startswith(f"{master}__")]
        if master_sources:
            return master_sources

    return all_sources


def _read_single_source(path: Path, sheets: tuple[str, ...] | None = None) -> list[tuple[str, pd.DataFrame]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return [("csv", pd.read_csv(path))]
    if suffix in {".xlsx", ".xls"}:
        excel = pd.ExcelFile(path)
        selected = list(sheets) if sheets else excel.sheet_names
        existing = [sheet_name for sheet_name in selected if sheet_name in excel.sheet_names]
        return [(sheet_name, pd.read_excel(path, sheet_name=sheet_name)) for sheet_name in existing]
    return []


def _build_subplot_dataframe(
    source_paths: list[SourceItem],
    max_rows: int,
) -> tuple[pd.DataFrame, list[dict[str, object]], bool]:
    frames: list[pd.DataFrame] = []
    sources_meta: list[dict[str, object]] = []
    truncated = False
    remaining_budget = max_rows

    for source_item in source_paths:
        source_path = source_item.path
        for source_sheet, frame in _read_single_source(source_path, source_item.sheets):
            frame = frame.copy()
            frame.insert(0, "__source_file", _rel_to_root(source_path))
            frame.insert(1, "__source_sheet", source_sheet)
            frame.insert(2, "__source_row", range(1, len(frame) + 1))
            take = min(len(frame), remaining_budget)
            if take < len(frame):
                truncated = True
            if take > 0:
                frames.append(frame.head(take))
                remaining_budget -= take
            sources_meta.append(
                {
                    "source_file": _rel_to_root(source_path),
                    "source_sheet": source_sheet,
                    "rows_total": int(len(frame)),
                    "rows_written": int(take),
                }
            )
            if remaining_budget <= 0:
                truncated = True
                break
        if remaining_budget <= 0:
            break

    if not frames:
        empty = pd.DataFrame([{"status": "missing", "reason": "no resolved source rows"}])
        return empty, sources_meta, truncated
    return pd.concat(frames, ignore_index=True), sources_meta, truncated


def _is_submission_provenance_column(column: object) -> bool:
    text = str(column).strip().lower()
    return any(pattern.lower() in text for pattern in PROVENANCE_COLUMN_PATTERNS)


def _clean_journal_source_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Remove local engineering trace columns from the journal-facing workbook.

    The internal per-Fig workbooks and the root manifest keep provenance.  The
    top-level submission workbook should look like the reference NC source data:
    figure-panel data only, no local paths or helper columns.
    """

    drop_columns = [str(col) for col in frame.columns if _is_submission_provenance_column(col)]
    for column in frame.columns:
        column_name = str(column)
        if column_name in drop_columns:
            continue
        series = frame[column]
        if not pd.api.types.is_object_dtype(series):
            continue
        sample = series.dropna().astype(str).head(200)
        if any(any(pattern in value for pattern in LOCAL_PATH_VALUE_PATTERNS) for value in sample):
            drop_columns.append(column_name)
    cleaned = frame.drop(columns=drop_columns, errors="ignore").copy()
    cleaned = cleaned.dropna(axis=1, how="all")
    if cleaned.empty:
        cleaned = pd.DataFrame([{"status": "no journal-facing columns after provenance cleanup"}])
    return cleaned, drop_columns


def _write_journal_source_sheet(
    writer: pd.ExcelWriter,
    *,
    sheet_name: str,
    row: FigureRow,
    source_items: list[SourceItem],
    max_rows_per_sheet: int,
) -> list[dict[str, object]]:
    worksheet = writer.book.create_sheet(title=sheet_name)
    writer.sheets[sheet_name] = worksheet
    worksheet.freeze_panes = "A3"

    manifest_rows: list[dict[str, object]] = []
    current_row = 0
    data_rows_written = 0
    block_index = 0
    remaining = max_rows_per_sheet

    if not source_items:
        missing = pd.DataFrame(
            [{"status": "missing", "reason": "no resolved source data for this manuscript panel"}]
        )
        worksheet.cell(row=1, column=1, value="missing source data")
        missing.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1)
        return [
            {
                "sheet_name": sheet_name,
                "subplot_key": _subfigure_key(row),
                "figure_file": row.figure_file,
                "figure_relpath": row.figure_relpath,
                "source_file": "",
                "source_sheet": "",
                "rows_total": 0,
                "rows_written": 1,
                "columns_written": len(missing.columns),
                "dropped_columns": "",
                "truncated": False,
                "note": "missing source data",
            }
        ]

    for source_item in source_items:
        for source_sheet, frame in _read_single_source(source_item.path, source_item.sheets):
            block_index += 1
            cleaned, dropped_columns = _clean_journal_source_frame(frame)
            rows_total = len(cleaned)
            take = min(rows_total, max(remaining, 0))
            truncated = take < rows_total
            block = cleaned.head(take) if take > 0 else pd.DataFrame(columns=cleaned.columns)

            title = source_sheet
            if block_index > 1 or len(source_items) > 1:
                title = f"{source_item.path.stem} :: {source_sheet}"
            worksheet.cell(row=current_row + 1, column=1, value=title)
            block.to_excel(writer, sheet_name=sheet_name, index=False, startrow=current_row + 1)

            manifest_rows.append(
                {
                    "sheet_name": sheet_name,
                    "subplot_key": _subfigure_key(row),
                    "figure_file": row.figure_file,
                    "figure_relpath": row.figure_relpath,
                    "source_file": _rel_to_root(source_item.path),
                    "source_sheet": source_sheet,
                    "rows_total": int(rows_total),
                    "rows_written": int(take),
                    "columns_written": int(len(block.columns)),
                    "dropped_columns": " | ".join(dropped_columns),
                    "truncated": bool(truncated),
                    "note": "journal-facing source-data block",
                }
            )

            data_rows_written += int(take)
            remaining -= int(take)
            current_row += int(take) + 3
            if remaining <= 0:
                break
        if remaining <= 0:
            break

    if data_rows_written == 0:
        worksheet.cell(row=1, column=1, value="empty source data")
        empty = pd.DataFrame([{"status": "empty", "reason": "resolved sources contain no rows"}])
        empty.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1)

    for column_cells in worksheet.columns:
        header = str(column_cells[0].value or "")
        width = min(max(len(header) + 2, 10), 36)
        worksheet.column_dimensions[column_cells[0].column_letter].width = width

    return manifest_rows


def _write_journal_source_data_workbook(
    rows: list[FigureRow],
    out_root: Path,
    max_rows_per_subplot: int,
) -> tuple[Path, Path, list[dict[str, object]]]:
    workbook_path = out_root / JOURNAL_SOURCE_WORKBOOK_NAME
    manifest_path = out_root / JOURNAL_SOURCE_MANIFEST_NAME
    manifest_rows: list[dict[str, object]] = []
    used_sheet_names: set[str] = set()

    panel_rows = [
        row
        for row in rows
        if not _is_special(row) and _figure_group(row, include_nonfig=False) is not None
    ]

    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        for row in sorted(panel_rows, key=_subfigure_sort_key):
            sheet_name = _safe_sheet_name(_journal_sheet_base(row), used_sheet_names)
            source_items = _pick_subplot_sources(row, _resolve_source_items(row))
            manifest_rows.extend(
                _write_journal_source_sheet(
                    writer,
                    sheet_name=sheet_name,
                    row=row,
                    source_items=source_items,
                    max_rows_per_sheet=max_rows_per_subplot,
                )
            )

        # pandas/openpyxl creates a default sheet only when no sheets exist; keep
        # the workbook valid even if the map is unexpectedly empty.
        if not panel_rows:
            pd.DataFrame([{"status": "empty", "reason": "no manuscript figure panel rows"}]).to_excel(
                writer, sheet_name="empty", index=False
            )

    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "sheet_name",
            "subplot_key",
            "figure_file",
            "figure_relpath",
            "source_file",
            "source_sheet",
            "rows_total",
            "rows_written",
            "columns_written",
            "dropped_columns",
            "truncated",
            "note",
        ]
        csv_writer = csv.DictWriter(handle, fieldnames=fieldnames)
        csv_writer.writeheader()
        csv_writer.writerows(manifest_rows)

    return workbook_path, manifest_path, manifest_rows


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_plot_data(
    source_paths: Iterable[Path],
    target_dir: Path,
    subplot_key: str,
    copied_hashes: dict[str, Path],
) -> list[Path]:
    copied: list[Path] = []
    for source_path in source_paths:
        if not source_path.exists():
            continue
        digest = _sha256(source_path)
        if digest in copied_hashes:
            copied.append(copied_hashes[digest])
            continue
        target_name = f"{subplot_key}__{source_path.name}"
        target_path = target_dir / target_name
        _copy_file(source_path, target_path)
        copied_hashes[digest] = target_path
        copied.append(target_path)
    return copied


def _save_png_800dpi(source_png: Path, target_png: Path) -> tuple[str, str]:
    target_png.parent.mkdir(parents=True, exist_ok=True)
    if Image is None:
        _copy_file(source_png, target_png)
        return "copied_original", "Pillow unavailable; copied original PNG without dpi rewrite."
    try:
        with Image.open(source_png) as image:
            image.save(target_png, dpi=(800, 800))
        return "rewritten_800dpi", ""
    except Exception as exc:  # pragma: no cover
        _copy_file(source_png, target_png)
        return "copied_original", f"failed to rewrite png dpi: {exc}"


def _copy_native_vector_sidecar(
    figure_png: Path,
    render_dir: Path,
    render_name: str,
    suffix: str,
    strict_vector: bool,
) -> tuple[str, str, str]:
    source = figure_png.with_suffix(suffix)
    target = render_dir / f"{render_name}{suffix}"
    if source.exists():
        _copy_file(source, target)
        return _rel_to_root(target), "native_vector", ""

    note = (
        f"Missing native vector sidecar: {source}. "
        "Re-run analysis_viz/scripts/wrappers/build_v2_subplots_bundle.py after vector export support; "
        "do not create raster-embedded SVG."
    )
    if strict_vector:
        raise FileNotFoundError(note)
    return "", "missing_native_vector", note


def _render_assets(
    figure_png: Path,
    render_dir: Path,
    render_name: str,
    strict_vector: bool,
) -> dict[str, str]:
    render_dir.mkdir(parents=True, exist_ok=True)
    out_png = render_dir / f"{render_name}.png"

    png_mode, png_note = _save_png_800dpi(figure_png, out_png)
    svg_path, svg_mode, svg_note = _copy_native_vector_sidecar(
        figure_png=figure_png,
        render_dir=render_dir,
        render_name=render_name,
        suffix=".svg",
        strict_vector=strict_vector,
    )
    pdf_path, pdf_mode, pdf_note = _copy_native_vector_sidecar(
        figure_png=figure_png,
        render_dir=render_dir,
        render_name=render_name,
        suffix=".pdf",
        strict_vector=strict_vector,
    )

    return {
        "png": _rel_to_root(out_png),
        "svg": svg_path,
        "pdf": pdf_path,
        "png_mode": png_mode,
        "png_note": png_note,
        "svg_mode": svg_mode,
        "svg_note": svg_note,
        "pdf_mode": pdf_mode,
        "pdf_note": pdf_note,
    }


def _write_launcher_script(
    scripts_dir: Path,
    subplot_key: str,
    figure_png_rel: str,
) -> Path:
    scripts_dir.mkdir(parents=True, exist_ok=True)
    script_path = scripts_dir / f"render_{subplot_key}.py"
    content = f'''"""Launcher for {subplot_key} render export.

This is a lightweight launcher for submission packaging:
- load existing PNG from v2_subplots/final paper-facing assets
- export 800 DPI PNG
- copy native SVG/PDF sidecars generated by the original plotting script

Raster-embedded SVG fallback is intentionally forbidden because it cannot be
edited reliably in Adobe Illustrator.
"""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image
except Exception:
    Image = None


def locate_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "analysis_viz").exists():
            return parent
    return current.parents[-1]


ROOT = locate_repo_root()
SRC_PNG = ROOT / "{figure_png_rel}"


def copy_required_sidecar(suffix: str, render_dir: Path) -> Path:
    native_path = SRC_PNG.with_suffix(suffix)
    if not native_path.exists():
        raise FileNotFoundError(
            f"Missing native vector sidecar: {{native_path}}. "
            "Do not create raster-embedded SVG; re-run build_v2_subplots_bundle.py."
        )
    out_path = render_dir / f"{subplot_key}{{suffix}}"
    out_path.write_bytes(native_path.read_bytes())
    return out_path


def main() -> None:
    render_dir = Path(__file__).resolve().parents[1] / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    out_png = render_dir / "{subplot_key}.png"

    if Image is not None:
        try:
            with Image.open(SRC_PNG) as img:
                img.save(out_png, dpi=(800, 800))
        except Exception:
            out_png.write_bytes(SRC_PNG.read_bytes())
    else:
        out_png.write_bytes(SRC_PNG.read_bytes())

    out_svg = copy_required_sidecar(".svg", render_dir)
    out_pdf = copy_required_sidecar(".pdf", render_dir)

    print("DONE", out_png, out_svg, out_pdf)


if __name__ == "__main__":
    main()
'''
    script_path.write_text(content, encoding="utf-8")
    return script_path


def _build_figure_bundle(
    fig_id: str,
    rows: list[FigureRow],
    out_root: Path,
    max_rows_per_subplot: int,
    strict_vector: bool,
) -> dict[str, object]:
    fig_dir = out_root / fig_id
    if fig_dir.exists():
        shutil.rmtree(fig_dir)
    source_data_dir = fig_dir / "source_data"
    plot_data_dir = fig_dir / "plot_data"
    scripts_dir = fig_dir / "scripts"
    render_dir = fig_dir / "render"
    source_data_dir.mkdir(parents=True, exist_ok=True)
    plot_data_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)
    render_dir.mkdir(parents=True, exist_ok=True)

    workbook_path = source_data_dir / f"{fig_id}_source_data.xlsx"
    meta_rows: list[dict[str, object]] = []
    subfigure_manifest: list[dict[str, object]] = []
    copied_hashes: dict[str, Path] = {}
    used_sheet_names: set[str] = set()

    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        for row in rows:
            subplot_key = _subfigure_key(row)
            sheet_name = _safe_sheet_name(subplot_key, used_sheet_names)
            figure_png = (ROOT / row.figure_relpath).resolve()

            all_sources = _resolve_source_items(row)
            subplot_sources = _pick_subplot_sources(row, all_sources)
            frame, sources_meta, truncated = _build_subplot_dataframe(subplot_sources, max_rows_per_subplot)
            if len(frame) > EXCEL_MAX_ROWS:
                frame = frame.head(EXCEL_MAX_ROWS)
                truncated = True
            frame.to_excel(writer, sheet_name=sheet_name, index=False)

            copied_plot_data = _copy_plot_data(_source_item_paths(subplot_sources), plot_data_dir, subplot_key, copied_hashes)
            render_meta = _render_assets(
                figure_png=figure_png,
                render_dir=render_dir,
                render_name=Path(row.figure_file).stem,
                strict_vector=strict_vector,
            )
            launcher = _write_launcher_script(scripts_dir, subplot_key, row.figure_relpath.replace("\\", "/"))

            source_list = [_rel_to_root(path) for path in _source_item_paths(subplot_sources)]
            subplot_record = {
                "subplot_key": subplot_key,
                "sheet_name": sheet_name,
                "section_id": row.section_id,
                "figure_file": row.figure_file,
                "figure_relpath": row.figure_relpath,
                "source_paths": source_list,
                "source_count": len(source_list),
                "sources_detail": sources_meta,
                "rows_written": int(len(frame)),
                "truncated": bool(truncated),
                "plot_data_files": [_rel_to_root(path) for path in copied_plot_data],
                "launcher_script": _rel_to_root(launcher),
                "render_png": render_meta["png"],
                "render_svg": render_meta["svg"],
                "render_pdf": render_meta["pdf"],
                "svg_mode": render_meta["svg_mode"],
                "svg_note": render_meta["svg_note"],
                "pdf_mode": render_meta["pdf_mode"],
                "pdf_note": render_meta["pdf_note"],
                "png_mode": render_meta["png_mode"],
                "png_note": render_meta["png_note"],
            }
            subfigure_manifest.append(subplot_record)
            meta_rows.append(
                {
                    "subplot_key": subplot_key,
                    "sheet_name": sheet_name,
                    "section_id": row.section_id,
                    "figure_file": row.figure_file,
                    "figure_relpath": row.figure_relpath,
                    "source_count": len(source_list),
                    "source_paths": " | ".join(source_list),
                    "rows_written": int(len(frame)),
                    "truncated": bool(truncated),
                    "plot_data_files": " | ".join(_rel_to_root(path) for path in copied_plot_data),
                    "launcher_script": _rel_to_root(launcher),
                    "render_png": render_meta["png"],
                    "render_svg": render_meta["svg"],
                    "render_pdf": render_meta["pdf"],
                    "svg_mode": render_meta["svg_mode"],
                    "svg_note": render_meta["svg_note"],
                    "pdf_mode": render_meta["pdf_mode"],
                    "pdf_note": render_meta["pdf_note"],
                    "generated_at": _now_iso(),
                }
            )

        meta_df = pd.DataFrame(meta_rows) if meta_rows else pd.DataFrame([{"status": "empty"}])
        meta_df.to_excel(writer, sheet_name="meta", index=False)

    manifest = {
        "fig_id": fig_id,
        "generated_at": _now_iso(),
        "workbook": _rel_to_root(workbook_path),
        "subfigure_count": len(subfigure_manifest),
        "subfigures": subfigure_manifest,
    }
    manifest_path = fig_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _write_special_case_outputs(
    special_rows: list[FigureRow],
    out_root: Path,
    max_rows_per_subplot: int,
) -> tuple[Path | None, Path | None]:
    if not special_rows:
        return None, None

    workbook_path = out_root / "Supplementary_Table_special_case.xlsx"
    rewrite_csv = out_root / "special_case_reference_rewrite.csv"
    used_sheet_names: set[str] = set()
    rewrite_rows: list[dict[str, str]] = []

    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        for index, row in enumerate(special_rows, start=1):
            subplot_key = _subfigure_key(row)
            all_sources = _resolve_source_items(row)
            picked_sources = _pick_subplot_sources(row, all_sources)
            truncated_any = False
            for source_item in picked_sources:
                for source_sheet, frame in _read_single_source(source_item.path, source_item.sheets):
                    sheet_base = source_sheet
                    if "明细" in source_sheet:
                        sheet_base = "special_detail"
                    elif "汇总" in source_sheet:
                        sheet_base = "special_summary"
                    sheet_name = _safe_sheet_name(sheet_base, used_sheet_names)
                    frame = frame.copy()
                    if len(frame) > EXCEL_MAX_ROWS:
                        frame = frame.head(EXCEL_MAX_ROWS)
                        truncated_any = True
                    frame.to_excel(writer, sheet_name=sheet_name, index=False)

            rewrite_rows.append(
                {
                    "old_reference": f"Supplementary Fig. ({row.figure_file})",
                    "new_reference": "Supplementary Table 23",
                    "section_id": row.section_id,
                    "figure_file": row.figure_file,
                    "figure_relpath": row.figure_relpath,
                    "source_paths": " | ".join(_rel_to_root(path) for path in _source_item_paths(picked_sources)),
                    "note": "auto-generated rewrite hint from special-case figure to supplementary table",
                    "truncated": str(bool(truncated_any)),
                }
            )

        meta = pd.DataFrame(
            [
                {
                    "generated_at": _now_iso(),
                    "row_count": len(special_rows),
                    "rule": "special-case rows are converted from figure references to supplementary tables",
                }
            ]
        )
        meta.to_excel(writer, sheet_name="meta", index=False)

    with rewrite_csv.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "old_reference",
            "new_reference",
            "section_id",
            "figure_file",
            "figure_relpath",
            "source_paths",
            "note",
            "truncated",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rewrite_rows)

    return workbook_path, rewrite_csv


def build_submission_bundle(
    run_id: str,
    figure_map_path: Path,
    source_mode: str,
    output_base: Path,
    include_nonfig: bool,
    max_rows_per_subplot: int,
    strict_vector: bool,
) -> Path:
    rows = _load_v2_manuscript_rows() if source_mode == "v2-subplots" else _load_rows(figure_map_path)
    out_root = (output_base / run_id / "submission_bundle").resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[FigureRow]] = {}
    special_rows: list[FigureRow] = []
    skipped_nonfig = 0
    for row in rows:
        if _is_special(row):
            special_rows.append(row)
        fig_group = _figure_group(row, include_nonfig=include_nonfig)
        if fig_group is None:
            skipped_nonfig += 1
            continue
        grouped.setdefault(fig_group, []).append(row)

    bundle_manifest = {
        "generated_at": _now_iso(),
        "run_id": run_id,
        "source_mode": source_mode,
        "input_figure_map": _rel_to_root(figure_map_path.resolve()) if source_mode != "v2-subplots" else "built-in manuscript Figure 2-5 mapping from analysis_viz/figures/v2_subplots",
        "include_nonfig": include_nonfig,
        "max_rows_per_subplot": max_rows_per_subplot,
        "strict_vector": strict_vector,
        "total_rows": len(rows),
        "skipped_nonfig_rows": skipped_nonfig,
        "figure_groups": {},
    }

    for fig_id in sorted(grouped):
        bundle_manifest["figure_groups"][fig_id] = _build_figure_bundle(
            fig_id=fig_id,
            rows=grouped[fig_id],
            out_root=out_root,
            max_rows_per_subplot=max_rows_per_subplot,
            strict_vector=strict_vector,
        )

    special_workbook, special_rewrite_csv = _write_special_case_outputs(
        special_rows=special_rows,
        out_root=out_root,
        max_rows_per_subplot=max_rows_per_subplot,
    )
    journal_source_workbook, journal_source_manifest, journal_source_rows = _write_journal_source_data_workbook(
        rows=rows,
        out_root=out_root,
        max_rows_per_subplot=max_rows_per_subplot,
    )
    bundle_manifest["special_case"] = {
        "rows": len(special_rows),
        "workbook": _rel_to_root(special_workbook) if special_workbook else "",
        "rewrite_csv": _rel_to_root(special_rewrite_csv) if special_rewrite_csv else "",
    }
    bundle_manifest["journal_source_data"] = {
        "workbook": _rel_to_root(journal_source_workbook),
        "manifest_csv": _rel_to_root(journal_source_manifest),
        "sheet_count": len({str(item["sheet_name"]) for item in journal_source_rows}),
        "block_count": len(journal_source_rows),
        "style_reference": "NC-style single top-level source data workbook; one sheet per quantitative manuscript panel; provenance kept in CSV/internal workbooks.",
    }

    manifest_path = out_root / "bundle_manifest.json"
    manifest_path.write_text(json.dumps(bundle_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build submission-ready per-figure bundles from paper-facing assets.")
    parser.add_argument("--run-id", default="", help="Optional fixed run id under work/paper_crosscheck.")
    parser.add_argument("--source-mode", choices=["v2-subplots", "legacy-final-map"], default="v2-subplots", help="Default uses manuscript Figure 2-5 mapped to v2_subplots. legacy-final-map uses --figure-map.")
    parser.add_argument("--figure-map", default=str(DEFAULT_FIGURE_MAP), help="Path to final_paper_bundle_figure_map.csv for legacy-final-map mode.")
    parser.add_argument("--output-base", default=str(DEFAULT_OUTPUT_BASE), help="Base output directory. Final output is <output-base>/<run-id>/submission_bundle.")
    parser.add_argument("--include-nonfig", action="store_true", help="Also package rows whose figure names do not start with Fig<number>.")
    parser.add_argument("--max-rows-per-subplot", type=int, default=DEFAULT_ROWS_PER_SUBPLOT_SHEET, help="Row budget written into each subplot sheet.")
    parser.add_argument("--allow-missing-vector", action="store_true", help="Do not fail when native SVG/PDF sidecars are missing; record missing_native_vector instead. Raster SVG fallback is still forbidden.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = args.run_id.strip() or _default_run_id()
    output_root = build_submission_bundle(
        run_id=run_id,
        figure_map_path=Path(args.figure_map),
        source_mode=str(args.source_mode),
        output_base=Path(args.output_base),
        include_nonfig=bool(args.include_nonfig),
        max_rows_per_subplot=int(args.max_rows_per_subplot),
        strict_vector=not bool(args.allow_missing_vector),
    )
    print(str(output_root))


if __name__ == "__main__":
    main()
