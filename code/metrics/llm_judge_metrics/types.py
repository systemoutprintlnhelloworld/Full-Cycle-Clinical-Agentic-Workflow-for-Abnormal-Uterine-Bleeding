from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd


@dataclasses.dataclass(frozen=True)
class DataFileSet:
    center: str
    model: str
    gt_path: Path
    doc_path: Path
    judge_path: Path


@dataclasses.dataclass(frozen=True)
class LoadedData:
    fileset: DataFileSet
    gt: pd.DataFrame
    doc_sheets: dict[str, pd.DataFrame]
    judge_sheets: dict[str, pd.DataFrame]

