"""Build one-source-workbook-per-figure with detail/summary sheets."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_VIZ = ROOT / "analysis_viz"
FIGURE_MAP = ANALYSIS_VIZ / "docs" / "final_paper_bundle_figure_map.csv"

MAX_DETAIL_SHEETS = 12
MAX_ROWS_PER_SHEET = 50000


def _safe_sheet_name(name: str, used: set[str]) -> str:
    base = name[:31] if len(name) > 31 else name
    candidate = base
    index = 1
    while candidate in used:
        suffix = f"_{index}"
        trim = 31 - len(suffix)
        candidate = f"{base[:trim]}{suffix}"
        index += 1
    used.add(candidate)
    return candidate


def _read_csv_rows() -> list[dict[str, str]]:
    if not FIGURE_MAP.exists():
        return []
    with FIGURE_MAP.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _resolve_paths(source_data_relpath: str) -> list[Path]:
    relpaths = [part.strip() for part in source_data_relpath.split("|") if part.strip()]
    paths: list[Path] = []
    for relpath in relpaths:
        path = ROOT / relpath
        if path.exists() and path.is_file():
            paths.append(path)
    return paths


def _read_frames(source_file: Path) -> list[tuple[str, pd.DataFrame]]:
    suffix = source_file.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(source_file)
        return [("csv", frame)]
    if suffix in {".xlsx", ".xls"}:
        out: list[tuple[str, pd.DataFrame]] = []
        excel = pd.ExcelFile(source_file)
        for sheet_name in excel.sheet_names:
            frame = pd.read_excel(source_file, sheet_name=sheet_name)
            out.append((sheet_name, frame))
        return out
    return []


def main() -> None:
    rows = _read_csv_rows()
    built_count = 0
    for row in rows:
        figure_relpath = row.get("figure_relpath", "")
        section_id = row.get("section_id", "")
        figure_file = row.get("figure_file", "")
        source_paths = _resolve_paths(row.get("source_data_relpath", ""))

        section_dir = ANALYSIS_VIZ / "figures" / "final_paper_bundle" / section_id
        out_dir = section_dir / "figdata_per_figure"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{Path(figure_file).stem}_source_data.xlsx"

        summary_rows: list[dict[str, object]] = []
        used_sheet_names: set[str] = set()
        detail_written = 0

        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            meta = pd.DataFrame(
                [
                    {
                        "figure_file": figure_file,
                        "figure_relpath": figure_relpath,
                        "section_id": section_id,
                        "source_count": len(source_paths),
                        "rule_note": "该工作簿包含明细(detail_*)与汇总(summary)；若无源文件则写入missing说明。",
                    }
                ]
            )
            meta.to_excel(writer, sheet_name="meta", index=False)

            if not source_paths:
                missing = pd.DataFrame(
                    [
                        {
                            "status": "missing",
                            "reason": "未在final_paper_bundle_figure_map.csv中匹配到source_data_relpath",
                        }
                    ]
                )
                missing.to_excel(writer, sheet_name="missing", index=False)
            else:
                for source_file in source_paths:
                    frames = _read_frames(source_file)
                    for source_sheet, frame in frames:
                        if detail_written >= MAX_DETAIL_SHEETS:
                            summary_rows.append(
                                {
                                    "source_file": str(source_file.relative_to(ROOT)).replace("\\", "/"),
                                    "source_sheet": source_sheet,
                                    "rows": len(frame),
                                    "cols": len(frame.columns),
                                    "detail_sheet": "",
                                    "note": "truncated_by_MAX_DETAIL_SHEETS",
                                }
                            )
                            continue

                        working = frame.head(MAX_ROWS_PER_SHEET).copy()
                        source_file_col = "source_file" if "source_file" not in working.columns else "__source_file"
                        source_sheet_col = "source_sheet" if "source_sheet" not in working.columns else "__source_sheet"
                        working.insert(0, source_file_col, str(source_file.relative_to(ROOT)).replace("\\", "/"))
                        working.insert(1, source_sheet_col, source_sheet)

                        sheet_name = _safe_sheet_name(f"detail_{detail_written + 1}", used_sheet_names)
                        working.to_excel(writer, sheet_name=sheet_name, index=False)
                        detail_written += 1
                        summary_rows.append(
                            {
                                "source_file": str(source_file.relative_to(ROOT)).replace("\\", "/"),
                                "source_sheet": source_sheet,
                                "rows": len(frame),
                                "cols": len(frame.columns),
                                "detail_sheet": sheet_name,
                                "note": "full" if len(frame) <= MAX_ROWS_PER_SHEET else f"truncated_to_{MAX_ROWS_PER_SHEET}",
                            }
                        )

            summary = pd.DataFrame(summary_rows)
            if summary.empty:
                summary = pd.DataFrame([{"note": "no source rows"}])
            summary.to_excel(writer, sheet_name="summary", index=False)

        built_count += 1
        print("WROTE", out_path)

    print("DONE", f"workbooks={built_count}")


if __name__ == "__main__":
    main()
