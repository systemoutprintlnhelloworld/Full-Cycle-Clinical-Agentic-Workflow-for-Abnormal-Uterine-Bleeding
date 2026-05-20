from __future__ import annotations

import logging
from pathlib import Path

from auto_eval_system.modules.data_loader import DataLoader

logger = logging.getLogger(__name__)


def resolve_center_data_path(repo_root: Path, center_name: str) -> Path:
    center_key = center_name.strip()
    standardized_path = repo_root / "data" / f"standardized_{center_key.lower()}.xlsx"
    if standardized_path.exists():
        return standardized_path

    fuzzy_candidates = sorted((repo_root / "data").glob(f"standardized_{center_key.lower()}*.xlsx"))
    if fuzzy_candidates:
        return fuzzy_candidates[0]

    raw_path = repo_root / "data" / "raw" / center_key
    if raw_path.exists():
        return raw_path

    plain_path = repo_root / "data" / center_key
    if plain_path.exists():
        return plain_path

    raise FileNotFoundError(f"未找到中心 {center_name} 的数据路径。")


def load_patients_by_center(repo_root: Path, center_name: str) -> dict[str, dict]:
    data_path = resolve_center_data_path(repo_root, center_name)
    loader = DataLoader(str(data_path))
    patients = loader.load_patients()
    patient_map: dict[str, dict] = {}
    for patient in patients:
        case_id = patient.get("case_id")
        if case_id is None:
            continue
        patient_map[str(case_id)] = patient
    logger.info("中心 %s 加载到 %s 个病例。", center_name, len(patient_map))
    return patient_map
