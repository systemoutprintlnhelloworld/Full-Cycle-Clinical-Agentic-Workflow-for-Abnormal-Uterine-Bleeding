from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


CENTER_CN = {
    "Foshan": "佛山",
    "Wuhan": "武汉",
    "Xinjiang": "新疆",
}

D1_SHEET = "D1_Outpatient_Decision"
D2_SHEET = "D2_Admission_Decision"
D3_SHEET = "D3_Surgery_Decision"

D1_DIAG_SCORE_COL = "Gate1判官_原始JSON_诊断匹配_评分"
D2_DIAG_SCORE_COL = "Gate2判官_原始JSON_修正诊断匹配_评分"
D3_DIAG_SCORE_COL = "判官_原始JSON_诊断匹配评估_评分"


def _read_stage_table(excel_path: Path, sheet_name: str, score_col: str) -> dict[str, dict]:
    frame = pd.read_excel(excel_path, sheet_name=sheet_name, dtype=object)
    if frame.empty:
        return {}

    case_col = "病例ID" if "病例ID" in frame.columns else frame.columns[0]
    status_col = "状态" if "状态" in frame.columns else (frame.columns[1] if len(frame.columns) > 1 else None)

    stage_map: dict[str, dict] = {}
    for _, row in frame.iterrows():
        case_id = str(row.get(case_col) or "").strip()
        if not case_id:
            continue
        status = str(row.get(status_col) or "").strip() if status_col else ""
        score = row.get(score_col)
        stage_map[case_id] = {
            "status": status,
            "score_not_null": bool(pd.notna(score)),
        }
    return stage_map


def _is_stage_ok(stage_entry: dict | None) -> bool:
    if not stage_entry:
        return False
    return stage_entry.get("status") == "顺利通过" and bool(stage_entry.get("score_not_null"))


def find_eligible_case_model_tracks(
    llm_metrics_root: Path,
    centers: list[str],
    models: list[str],
) -> tuple[list[dict], list[dict]]:
    eligible_tracks: list[dict] = []
    excluded_tracks: list[dict] = []

    for center_en in centers:
        center_cn = CENTER_CN.get(center_en)
        if not center_cn:
            logger.warning("未识别中心映射，跳过筛选 center=%s", center_en)
            continue

        for model in models:
            excel_path = (
                llm_metrics_root
                / "data"
                / center_cn
                / "judge agent"
                / f"Evaluation_Summary_{model}_CN_Judge_Parsed.xlsx"
            )
            if not excel_path.exists():
                logger.warning("筛选所需 baseline 文件缺失: %s", excel_path)
                continue

            d1_map = _read_stage_table(excel_path, D1_SHEET, D1_DIAG_SCORE_COL)
            d2_map = _read_stage_table(excel_path, D2_SHEET, D2_DIAG_SCORE_COL)
            d3_map = _read_stage_table(excel_path, D3_SHEET, D3_DIAG_SCORE_COL)
            all_case_ids = sorted(set(d1_map) | set(d2_map) | set(d3_map))

            for case_id in all_case_ids:
                d1_ok = _is_stage_ok(d1_map.get(case_id))
                d2_ok = _is_stage_ok(d2_map.get(case_id))
                d3_ok = _is_stage_ok(d3_map.get(case_id))

                record = {
                    "center": center_en,
                    "case_id": case_id,
                    "model": model,
                    "d1_status": (d1_map.get(case_id) or {}).get("status", ""),
                    "d2_status": (d2_map.get(case_id) or {}).get("status", ""),
                    "d3_status": (d3_map.get(case_id) or {}).get("status", ""),
                    "d1_score_non_null": (d1_map.get(case_id) or {}).get("score_not_null", False),
                    "d2_score_non_null": (d2_map.get(case_id) or {}).get("score_not_null", False),
                    "d3_score_non_null": (d3_map.get(case_id) or {}).get("score_not_null", False),
                    "baseline_source_file": str(excel_path),
                }

                if d1_ok and d2_ok and d3_ok:
                    record["eligibility"] = "eligible"
                    eligible_tracks.append(record)
                else:
                    record["eligibility"] = "excluded"
                    excluded_tracks.append(record)

    eligible_tracks.sort(key=lambda x: (x["center"], x["case_id"], x["model"]))
    excluded_tracks.sort(key=lambda x: (x["center"], x["case_id"], x["model"]))
    logger.info("模型-病例轨迹筛选完成：eligible=%s excluded=%s", len(eligible_tracks), len(excluded_tracks))
    return eligible_tracks, excluded_tracks


def group_tracks_by_case(tracks: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for row in tracks:
        key = (str(row["center"]), str(row["case_id"]))
        grouped.setdefault(key, []).append(str(row["model"]))

    rows: list[dict] = []
    for (center, case_id), models in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        models_sorted = sorted(models)
        rows.append(
            {
                "center": center,
                "case_id": case_id,
                "eligible_model_count": len(models_sorted),
                "eligible_models": ",".join(models_sorted),
            }
        )
    return rows
