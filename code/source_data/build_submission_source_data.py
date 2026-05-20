from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


MAIN_SECTION_RE = re.compile(r"^0[1-5]_")
FIG_ID_RE = re.compile(r"(Fig\d+)", re.IGNORECASE)


def now_local() -> datetime:
    return datetime.now().astimezone()


def make_run_id() -> str:
    return now_local().strftime("%Y-%m-%d_%H-%M-%S_submission-source-data")


def resolve_paths(project_root: Path) -> dict[str, Path]:
    map_csv = next((project_root / "analysis_viz").glob("**/02_*对应清单.csv"))
    manifest_csv = project_root / "analysis_viz" / "docs" / "final_paper_bundle_manifest.csv"
    if not map_csv.exists():
        raise FileNotFoundError("Cannot find figure-source mapping csv.")
    if not manifest_csv.exists():
        raise FileNotFoundError(f"Cannot find manifest csv: {manifest_csv}")
    return {"map_csv": map_csv, "manifest_csv": manifest_csv}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build submission-ready source data package for main-paper figures.")
    return parser.parse_args()


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def figure_id_from_name(figure_file: str) -> str:
    m = FIG_ID_RE.search(figure_file or "")
    return m.group(1).capitalize() if m else "FigUnknown"


def collect_main_rows(project_root: Path, map_csv: Path, manifest_csv: Path) -> pd.DataFrame:
    fig_map = pd.read_csv(map_csv, dtype=str).fillna("")
    bundle_manifest = pd.read_csv(manifest_csv)
    main_sections = {
        str(row["section_id"])
        for _, row in bundle_manifest.iterrows()
        if to_bool(row.get("included")) and MAIN_SECTION_RE.match(str(row.get("section_id", "")))
    }
    rows = fig_map[fig_map["section_id"].isin(main_sections)].copy()
    if rows.empty:
        raise RuntimeError("No main-paper figure rows found from mapping table.")
    rows["figure_id"] = rows["figure_file"].map(figure_id_from_name)
    rows["source_data_relpath"] = rows["source_data_relpath"].astype(str)
    rows["source_relpath_items"] = rows["source_data_relpath"].map(
        lambda s: [part.strip() for part in s.split("|") if part.strip()]
    )
    rows = rows.explode("source_relpath_items")
    rows = rows.rename(columns={"source_relpath_items": "source_relpath"})
    rows = rows[rows["source_relpath"].astype(str) != ""].copy()
    rows["source_abs_path"] = rows["source_relpath"].map(lambda s: str((project_root / s).resolve()))
    rows["source_exists"] = rows["source_relpath"].map(lambda s: (project_root / s).exists())
    rows["source_ext"] = rows["source_relpath"].map(lambda s: Path(s).suffix.lower())
    rows = rows.drop_duplicates(
        subset=["figure_id", "figure_file", "figure_relpath", "source_relpath"]
    ).reset_index(drop=True)
    return rows


def read_source_file(project_root: Path, source_relpath: str) -> list[tuple[str, pd.DataFrame]]:
    source_path = project_root / source_relpath
    ext = source_path.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(source_path)
        return [("csv", df)]
    if ext in {".xlsx", ".xls"}:
        sheets = pd.read_excel(source_path, sheet_name=None)
        return [(sheet_name, sheet_df) for sheet_name, sheet_df in sheets.items()]
    return []


def build_source_workbook(project_root: Path, rows: pd.DataFrame, workbook_path: Path) -> dict[str, int]:
    row_counts: dict[str, int] = {}
    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        readme_rows = [
            {"field": "package_type", "value": "Main-paper Source Data"},
            {"field": "created_at", "value": now_local().isoformat(timespec="seconds")},
            {"field": "scope", "value": "Sections 01-05 from final_paper_bundle_manifest.csv"},
            {"field": "traceability", "value": "Each row carries panel/source file/source sheet columns."},
            {"field": "policy_hint", "value": "Submission-oriented organization for Nature/medical journals."},
        ]
        pd.DataFrame(readme_rows).to_excel(writer, sheet_name="README", index=False)
        row_counts["README"] = len(readme_rows)

        for figure_id, fig_group in rows.groupby("figure_id", sort=True):
            bucket: list[pd.DataFrame] = []
            for _, row in fig_group.iterrows():
                src_relpath = str(row["source_relpath"])
                if not (project_root / src_relpath).exists():
                    continue
                sheet_dfs = read_source_file(project_root, src_relpath)
                for src_sheet_name, src_df in sheet_dfs:
                    traced = src_df.copy()
                    traced.insert(0, "__source_sheet", src_sheet_name)
                    traced.insert(0, "__source_file", src_relpath)
                    traced.insert(0, "__panel_file", str(row["figure_file"]))
                    traced.insert(0, "__figure_relpath", str(row["figure_relpath"]))
                    bucket.append(traced)
            if not bucket:
                continue
            merged = pd.concat(bucket, ignore_index=True, sort=False)
            sheet_name = figure_id[:31]
            merged.to_excel(writer, sheet_name=sheet_name, index=False)
            row_counts[sheet_name] = len(merged)
    return row_counts


def write_readme(
    run_dir: Path,
    map_csv: Path,
    manifest_csv: Path,
    manifest_rows: pd.DataFrame,
    workbook_row_counts: dict[str, int],
) -> None:
    lines = [
        "# Submission Source Data Package",
        "",
        f"- Created at: {now_local().isoformat(timespec='seconds')}",
        f"- Scope: main-paper sections (`01-05`) only",
        f"- Figure-source map: `{map_csv}`",
        f"- Bundle manifest: `{manifest_csv}`",
        "",
        "## Files",
        "- `Source Data.xlsx`: main submission workbook with traceability columns.",
        "- `source_data_manifest.csv`: figure-to-source expanded mapping and existence checks.",
        "",
        "## Validation",
        f"- Manifest rows: {len(manifest_rows)}",
        f"- Distinct figure IDs: {manifest_rows['figure_id'].nunique()}",
        f"- Workbook sheets: {len(workbook_row_counts)}",
    ]
    for sheet_name, row_count in sorted(workbook_row_counts.items()):
        lines.append(f"- Sheet `{sheet_name}` rows: {row_count}")
    (run_dir / "README_submission_source_data.md").write_text("\n".join(lines), encoding="utf-8")


def validate_outputs(manifest_rows: pd.DataFrame, workbook_row_counts: dict[str, int]) -> None:
    if manifest_rows.empty:
        raise RuntimeError("Manifest is empty.")
    fig_counts = manifest_rows.groupby("figure_id").size().to_dict()
    missing_sheet_figs = [fig for fig in fig_counts if fig[:31] not in workbook_row_counts]
    if missing_sheet_figs:
        raise RuntimeError(f"Workbook missing figure sheets: {missing_sheet_figs}")
    non_readme_sheets = {k: v for k, v in workbook_row_counts.items() if k != "README"}
    empty_sheets = [k for k, v in non_readme_sheets.items() if v <= 0]
    if empty_sheets:
        raise RuntimeError(f"Empty figure sheets found: {empty_sheets}")
    if not bool(manifest_rows["source_exists"].all()):
        missing = manifest_rows.loc[~manifest_rows["source_exists"], "source_relpath"].tolist()
        raise RuntimeError(f"Missing source files in manifest: {missing[:5]}")


def main() -> None:
    parse_args()
    project_root = Path(__file__).resolve().parents[1]
    paths = resolve_paths(project_root)
    run_id = make_run_id()
    run_dir = project_root / "work" / "submission_source_data" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows = collect_main_rows(project_root, paths["map_csv"], paths["manifest_csv"])
    manifest_csv = run_dir / "source_data_manifest.csv"
    manifest_rows.to_csv(manifest_csv, index=False, encoding="utf-8-sig")

    workbook_path = run_dir / "Source Data.xlsx"
    workbook_row_counts = build_source_workbook(project_root, manifest_rows, workbook_path)
    validate_outputs(manifest_rows, workbook_row_counts)
    write_readme(run_dir, paths["map_csv"], paths["manifest_csv"], manifest_rows, workbook_row_counts)
    print(str(run_dir))


if __name__ == "__main__":
    main()
