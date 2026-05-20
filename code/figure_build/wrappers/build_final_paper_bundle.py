"""Build final paper bundle with variants and source mapping.

Input:
- analysis_viz/figures/results_sections/*
- analysis_viz/figures/variants/*

Output:
- analysis_viz/figures/final_paper_bundle/<section>/{figures,figdata}
- analysis_viz/docs/final_paper_bundle_manifest.csv
- analysis_viz/docs/final_paper_bundle_figure_map.csv
"""

from __future__ import annotations

import csv
import hashlib
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_VIZ = ROOT / "analysis_viz"
SECTIONS_ROOT = ANALYSIS_VIZ / "figures" / "results_sections"
OUT_ROOT = ANALYSIS_VIZ / "figures" / "final_paper_bundle"
OUT_MANIFEST = ANALYSIS_VIZ / "docs" / "final_paper_bundle_manifest.csv"
OUT_FIGURE_MAP = ANALYSIS_VIZ / "docs" / "final_paper_bundle_figure_map.csv"
FIGURE_METRIC_MAPPING = ANALYSIS_VIZ / "docs" / "figure_metric_mapping.csv"
ARCHIVE_FIGDATA_SOURCE_DIR = ANALYSIS_VIZ / "data" / "derived" / "figdata" / "archive_2026-02-06" / "source_data"
ALIGNMENT_RESULT_CASELEVEL = ANALYSIS_VIZ / "data" / "derived" / "metrics" / "alignment" / "alignment_result_vs_judge_case_level_source.xlsx"
ALIGNMENT_REASONING_CASELEVEL = ANALYSIS_VIZ / "data" / "derived" / "metrics" / "alignment" / "alignment_reasoning_vs_llm_case_level_source.xlsx"
LLM_MEMORY_SOURCE = ANALYSIS_VIZ / "data" / "derived" / "metrics" / "llm_memory_source.xlsx"
LLM_CONSISTENCY_SOURCE = ANALYSIS_VIZ / "data" / "derived" / "metrics" / "llm_consistency_source.xlsx"
SPECIAL_D1_SOURCE = ANALYSIS_VIZ / "data" / "derived" / "figdata" / "paper" / "FigS__special_d1_case_rates.csv"

EXCLUDED_SECTION_PREFIXES = {"06_", "07_"}
VARIANT_SECTION_SPECS: list[tuple[str, Path, str]] = [
    ("06_variants_algorithmic_latest", ANALYSIS_VIZ / "figures" / "variants" / "outputs_latest__algorithmic", "latest algorithmic variants"),
    ("07_variants_alignment_latest", ANALYSIS_VIZ / "figures" / "variants" / "outputs_latest__alignment", "latest alignment variants"),
    ("08_variants_calibration_latest", ANALYSIS_VIZ / "figures" / "variants" / "outputs_latest__calibration", "latest calibration variants"),
    ("09_variants_sankey_latest", ANALYSIS_VIZ / "figures" / "variants" / "outputs_latest__sankey", "latest sankey variants"),
    ("10_variants_llm_memory", ANALYSIS_VIZ / "figures" / "variants" / "outputs_latest__llm_full" / "memory", "llm memory variants"),
    ("11_variants_llm_consistency", ANALYSIS_VIZ / "figures" / "variants" / "outputs_latest__llm_full" / "consistency", "llm consistency variants"),
    ("12_variants_llm_reasoning", ANALYSIS_VIZ / "figures" / "variants" / "outputs_latest__llm_full" / "reasoning", "llm reasoning variants"),
    ("13_variants_special_cases", ANALYSIS_VIZ / "figures" / "variants" / "outputs_latest__special", "special case variants"),
    ("14_variants_archive_algorithmic", ANALYSIS_VIZ / "figures" / "variants" / "archive_2026-02-06__algorithmic", "archive algorithmic variants"),
    ("15_variants_archive_alignment", ANALYSIS_VIZ / "figures" / "variants" / "archive_2026-02-06__alignment", "archive alignment variants"),
]
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg"}
DATA_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def _load_mapping_rules() -> list[tuple[re.Pattern[str], str]]:
    if not FIGURE_METRIC_MAPPING.exists():
        return []

    rules: list[tuple[re.Pattern[str], str]] = []
    with FIGURE_METRIC_MAPPING.open("r", encoding="utf-8", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        for row in reader:
            pattern = (row.get("figure_pattern") or "").strip()
            derived = (row.get("derived_metric_workbook") or "").strip()
            if not pattern or not derived:
                continue
            escaped = re.escape(pattern)
            escaped = escaped.replace("<center>", r".+?")
            escaped = escaped.replace("<model>", r".+?")
            escaped = escaped.replace(r"\*", r".*")
            regex = re.compile(rf"^{escaped}$")
            rules.append((regex, derived))
    return rules


def _infer_derived_source(figure_name: str, rules: list[tuple[re.Pattern[str], str]]) -> Path | None:
    for regex, relpath in rules:
        if not regex.match(figure_name):
            continue
        candidate = ROOT / relpath
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _infer_fallback_source(figure_name: str) -> Path | None:
    lowered = figure_name.lower()
    if lowered.startswith("alignment_result_quality_") and ALIGNMENT_RESULT_CASELEVEL.exists():
        return ALIGNMENT_RESULT_CASELEVEL
    if lowered.startswith("alignment_reasoning_quality_") and ALIGNMENT_REASONING_CASELEVEL.exists():
        return ALIGNMENT_REASONING_CASELEVEL
    if lowered.startswith("llm_memory_") and LLM_MEMORY_SOURCE.exists():
        return LLM_MEMORY_SOURCE
    if lowered.startswith("llm_consistency_") and LLM_CONSISTENCY_SOURCE.exists():
        return LLM_CONSISTENCY_SOURCE
    if "special_d1_case" in lowered and SPECIAL_D1_SOURCE.exists():
        return SPECIAL_D1_SOURCE
    return None


def _is_excluded(section_name: str) -> bool:
    return any(section_name.startswith(prefix) for prefix in EXCLUDED_SECTION_PREFIXES)


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _copy_file(source: Path, target: Path) -> tuple[int, int]:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return 1, source.stat().st_size


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _copy_tree(
    source_dir: Path,
    target_dir: Path,
    known_image_hashes: set[str],
) -> tuple[int, int, list[Path], list[Path]]:
    copied_files = 0
    copied_bytes = 0
    copied_images: list[Path] = []
    copied_data: list[Path] = []
    if not source_dir.exists():
        return copied_files, copied_bytes, copied_images, copied_data

    for source_path in sorted(source_dir.rglob("*")):
        if not source_path.is_file():
            continue
        relative_path = source_path.relative_to(source_dir)
        target_path = target_dir / relative_path
        if source_path.suffix.lower() in IMAGE_EXTENSIONS:
            image_hash = _sha256(source_path)
            if image_hash in known_image_hashes:
                continue
            known_image_hashes.add(image_hash)
        added_files, added_bytes = _copy_file(source_path, target_path)
        copied_files += added_files
        copied_bytes += added_bytes

        suffix = target_path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            copied_images.append(target_path)
        if suffix in DATA_EXTENSIONS:
            copied_data.append(target_path)

    return copied_files, copied_bytes, copied_images, copied_data


def _copy_variant_section(
    section_id: str,
    source_dir: Path,
    notes: str,
    rows: list[dict[str, str]],
    figure_rows: list[dict[str, str]],
    known_image_hashes: set[str],
    mapping_rules: list[tuple[re.Pattern[str], str]],
) -> None:
    target_dir = OUT_ROOT / section_id
    target_fig_dir = target_dir / "figures"
    target_data_dir = target_dir / "figdata"
    target_fig_dir.mkdir(parents=True, exist_ok=True)
    target_data_dir.mkdir(parents=True, exist_ok=True)

    copied_files = 0
    copied_bytes = 0
    copied_fig_count = 0
    copied_data_count = 0

    if not source_dir.exists():
        rows.append(
            {
                "section_id": section_id,
                "included": "False",
                "source_dir": _rel(source_dir),
                "target_dir": _rel(target_dir),
                "copied_files": "0",
                "copied_bytes": "0",
                "notes": f"{notes}; source missing",
            }
        )
        return

    source_data_dir = source_dir / "source_data"
    archive_mode = "archive_2026-02-06__" in source_dir.name
    copied_source_by_stem: dict[str, list[Path]] = {}

    if source_data_dir.exists():
        for source_data_file in sorted(source_data_dir.glob("*")):
            if not source_data_file.is_file() or source_data_file.suffix.lower() not in DATA_EXTENSIONS:
                continue
            target = target_data_dir / source_data_file.name
            added_files, added_bytes = _copy_file(source_data_file, target)
            copied_files += added_files
            copied_bytes += added_bytes
            copied_data_count += 1
            stem = source_data_file.stem.replace("_source", "")
            copied_source_by_stem.setdefault(stem, []).append(target)

    for source_path in sorted(source_dir.rglob("*")):
        if not source_path.is_file():
            continue
        if "source_data" in source_path.parts:
            continue
        if source_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        image_hash = _sha256(source_path)
        if image_hash in known_image_hashes:
            continue
        known_image_hashes.add(image_hash)

        rel_from_group = source_path.relative_to(source_dir)
        target_img = target_fig_dir / rel_from_group
        added_files, added_bytes = _copy_file(source_path, target_img)
        copied_files += added_files
        copied_bytes += added_bytes
        copied_fig_count += 1

        source_paths: list[Path] = []
        if source_path.stem in copied_source_by_stem:
            source_paths.extend(copied_source_by_stem[source_path.stem])

        if archive_mode and ARCHIVE_FIGDATA_SOURCE_DIR.exists():
            archive_source = ARCHIVE_FIGDATA_SOURCE_DIR / f"{source_path.stem}_source.xlsx"
            if archive_source.exists():
                target_archive = target_data_dir / archive_source.name
                if not target_archive.exists():
                    added_files, added_bytes = _copy_file(archive_source, target_archive)
                    copied_files += added_files
                    copied_bytes += added_bytes
                    copied_data_count += 1
                source_paths.append(target_archive)

        if not source_paths:
            inferred = _infer_derived_source(source_path.name, mapping_rules)
            if inferred is not None:
                inferred_name = f"{source_path.stem}__derived_metric_source{inferred.suffix.lower()}"
                target_inferred = target_data_dir / inferred_name
                if not target_inferred.exists():
                    added_files, added_bytes = _copy_file(inferred, target_inferred)
                    copied_files += added_files
                    copied_bytes += added_bytes
                    copied_data_count += 1
                source_paths.append(target_inferred)

        if not source_paths:
            fallback_source = _infer_fallback_source(source_path.name)
            if fallback_source is not None:
                fallback_name = f"{source_path.stem}__fallback_source{fallback_source.suffix.lower()}"
                target_fallback = target_data_dir / fallback_name
                if not target_fallback.exists():
                    added_files, added_bytes = _copy_file(fallback_source, target_fallback)
                    copied_files += added_files
                    copied_bytes += added_bytes
                    copied_data_count += 1
                source_paths.append(target_fallback)

        figure_rows.append(
            {
                "section_id": section_id,
                "figure_file": target_img.name,
                "figure_relpath": _rel(target_img),
                "source_data_relpath": "|".join(_rel(path) for path in sorted(set(source_paths))),
                "source_type": "variant",
                "notes": "" if source_paths else "no matched source_data",
            }
        )

    rows.append(
        {
            "section_id": section_id,
            "included": "True",
            "source_dir": _rel(source_dir),
            "target_dir": _rel(target_dir),
            "copied_files": str(copied_files),
            "copied_bytes": str(copied_bytes),
            "notes": f"{notes}; figures={copied_fig_count}; figdata={copied_data_count}",
        }
    )


def main() -> None:
    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    OUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    figure_rows: list[dict[str, str]] = []
    known_image_hashes: set[str] = set()
    mapping_rules = _load_mapping_rules()

    section_dirs = [path for path in sorted(SECTIONS_ROOT.glob("*")) if path.is_dir()]

    for section_dir in section_dirs:
        section_name = section_dir.name
        if _is_excluded(section_name):
            rows.append(
                {
                    "section_id": section_name,
                    "included": "False",
                    "source_dir": _rel(section_dir),
                    "target_dir": "",
                    "copied_files": "0",
                    "copied_bytes": "0",
                    "notes": "excluded placeholders/optional",
                }
            )
            continue

        target_dir = OUT_ROOT / section_name
        copied_files, copied_bytes, copied_images, copied_data = _copy_tree(
            section_dir,
            target_dir,
            known_image_hashes,
        )
        section_data_relpaths = [_rel(path) for path in copied_data]
        for image_path in copied_images:
            figure_rows.append(
                {
                    "section_id": section_name,
                    "figure_file": image_path.name,
                    "figure_relpath": _rel(image_path),
                    "source_data_relpath": "|".join(section_data_relpaths),
                    "source_type": "paper_section",
                    "notes": "section-level figdata copied by Fig-prefix",
                }
            )

        rows.append(
            {
                "section_id": section_name,
                "included": "True",
                "source_dir": _rel(section_dir),
                "target_dir": _rel(target_dir),
                "copied_files": str(copied_files),
                "copied_bytes": str(copied_bytes),
                "notes": "",
            }
        )

    for section_id, source_dir, notes in VARIANT_SECTION_SPECS:
        _copy_variant_section(
            section_id,
            source_dir,
            notes,
            rows,
            figure_rows,
            known_image_hashes,
            mapping_rules,
        )

    with OUT_MANIFEST.open("w", encoding="utf-8", newline="") as file_handle:
        fieldnames = [
            "section_id",
            "included",
            "source_dir",
            "target_dir",
            "copied_files",
            "copied_bytes",
            "notes",
        ]
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with OUT_FIGURE_MAP.open("w", encoding="utf-8", newline="") as file_handle:
        fieldnames = [
            "section_id",
            "figure_file",
            "figure_relpath",
            "source_data_relpath",
            "source_type",
            "notes",
        ]
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in figure_rows:
            writer.writerow(row)

    print("WROTE", OUT_MANIFEST)
    print("WROTE", OUT_FIGURE_MAP)
    for row in rows:
        print(
            f"{row['section_id']}: included={row['included']}, "
            f"copied_files={row['copied_files']}, notes={row['notes']}"
        )


if __name__ == "__main__":
    main()
