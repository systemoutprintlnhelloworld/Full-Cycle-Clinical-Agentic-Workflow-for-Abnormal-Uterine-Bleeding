from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .types import DataFileSet


_DOC_RE = re.compile(r"^Evaluation_Summary_(.+?)_CN_Parsed\.xlsx$", re.IGNORECASE)
_JUDGE_RE = re.compile(r"^Evaluation_Summary_(.+?)_CN_Judge_Parsed\.xlsx$", re.IGNORECASE)


@dataclass(frozen=True)
class DiscoveryResult:
    datasets: list[DataFileSet]
    warnings: list[str]


def _infer_model_from_name(path: Path, is_judge: bool) -> str | None:
    m = (_JUDGE_RE if is_judge else _DOC_RE).match(path.name)
    return m.group(1) if m else None


def discover_datasets(data_root: Path, centers: list[str] | None = None, models: list[str] | None = None) -> DiscoveryResult:
    warnings: list[str] = []
    datasets: list[DataFileSet] = []

    if not data_root.exists():
        return DiscoveryResult(datasets=[], warnings=[f"data_root not found: {data_root}"])

    def _is_valid_center_dir(path: Path) -> bool:
        name = path.name.lower()
        return not (
            name.startswith("backup")
            or name.startswith("bkup")
            or name.startswith("archive")
            or name.startswith("tmp")
        )

    center_dirs = [p for p in data_root.iterdir() if p.is_dir() and _is_valid_center_dir(p)]
    if centers:
        center_set = set(centers)
        center_dirs = [p for p in center_dirs if p.name in center_set]

    for center_dir in sorted(center_dirs, key=lambda p: p.name):
        gt_dir = center_dir / "GT"
        doc_dir = center_dir / "doc agent"
        judge_dir = center_dir / "judge agent"

        gt_files = sorted(gt_dir.glob("standardized_*.xlsx")) if gt_dir.exists() else []
        if not gt_files:
            warnings.append(f"[{center_dir.name}] missing GT standardized_*.xlsx under {gt_dir}")
            continue
        if len(gt_files) > 1:
            warnings.append(f"[{center_dir.name}] multiple GT files found; using first: {gt_files[0].name}")
        gt_path = gt_files[0]

        doc_files = sorted(doc_dir.glob("Evaluation_Summary_*_CN_Parsed.xlsx")) if doc_dir.exists() else []
        judge_files = sorted(judge_dir.glob("Evaluation_Summary_*_CN_Judge_Parsed.xlsx")) if judge_dir.exists() else []

        doc_by_model: dict[str, Path] = {}
        for p in doc_files:
            model_name = _infer_model_from_name(p, is_judge=False)
            if not model_name:
                warnings.append(f"[{center_dir.name}] cannot infer model from doc filename: {p.name}")
                continue
            doc_by_model[model_name] = p

        judge_by_model: dict[str, Path] = {}
        for p in judge_files:
            model_name = _infer_model_from_name(p, is_judge=True)
            if not model_name:
                warnings.append(f"[{center_dir.name}] cannot infer model from judge filename: {p.name}")
                continue
            judge_by_model[model_name] = p

        model_names = sorted(set(doc_by_model) | set(judge_by_model))
        if models:
            model_set = set(models)
            model_names = [m for m in model_names if m in model_set]

        for model_name in model_names:
            doc_path = doc_by_model.get(model_name)
            judge_path = judge_by_model.get(model_name)
            if not doc_path:
                warnings.append(f"[{center_dir.name} | {model_name}] missing doc Parsed.xlsx")
                continue
            if not judge_path:
                warnings.append(f"[{center_dir.name} | {model_name}] missing judge Judge_Parsed.xlsx")
                continue
            datasets.append(
                DataFileSet(center=center_dir.name, model=model_name, gt_path=gt_path, doc_path=doc_path, judge_path=judge_path)
            )

    return DiscoveryResult(datasets=datasets, warnings=warnings)
