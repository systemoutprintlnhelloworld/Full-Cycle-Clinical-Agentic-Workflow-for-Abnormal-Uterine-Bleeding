from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd

from .ingest import SHEETS
from .parsing import is_empty
from .quality import canonicalize_sheet_columns
from .sorting import case_id_sort_key
from .status import detect_d1_decision_anomaly, _row_has_output_for_stage
from .types import DataFileSet


DOC_REQUIRED_ALL: dict[str, list[str]] = {
    "D1_Outpatient_Decision": [
        "医生决策_原始JSON_初步诊断列表",
    ],
    "D2_Admission_Decision": [
        "医生决策_原始JSON_修正诊断",
        "医生决策_原始JSON_初步治疗方案",
    ],
    "D3_Surgery_Decision": [
        "医生_原始JSON_最终诊断_诊断名称",
        "医生_原始JSON_术后治疗方案_方案详情",
    ],
}

DOC_REQUIRED_ANY: dict[str, list[str]] = {
    "D4_Rehab_Plan": [
        "医生_原始JSON_出院康复计划_方案详情",
        "医生_原始JSON_长期随访计划_方案详情",
    ],
}

JUDGE_REQUIRED_ALL: dict[str, list[str]] = {
    "D1_Outpatient_Decision": [
        "Gate1判官_原始JSON_是否继续评测",
        "Gate1判官_原始JSON_综合评分",
        "Gate1判官_原始JSON_诊断匹配_评分",
        "Gate1判官_原始JSON_检查匹配_评分",
    ],
    "D2_Admission_Decision": [
        "Gate2判官_原始JSON_是否继续评测",
        "Gate2判官_原始JSON_综合评分",
        "Gate2判官_原始JSON_修正诊断匹配_评分",
        "Gate2判官_原始JSON_手术方案匹配_评分",
        "Gate2_二审原始JSON_is_reasonable",
    ],
    "D3_Surgery_Decision": [
        "判官_原始JSON_是否继续评测",
        "判官_原始JSON_综合评分",
        "判官_原始JSON_诊断匹配评估_评分",
        "判官_原始JSON_治疗方案匹配评估_评分",
    ],
    "D4_Rehab_Plan": [
        "判官_原始JSON_综合评分",
        "判官_原始JSON_康复计划评估_评分",
        "判官_原始JSON_随访计划评估_评分",
    ],
}


def _read_sheet_header(path, sheet: str) -> list[str]:
    try:
        df = pd.read_excel(path, sheet_name=sheet, nrows=0, engine="openpyxl")
    except Exception:
        return []
    df2, _ = canonicalize_sheet_columns(df)
    return [str(c) for c in df2.columns]


def collect_column_stats(datasets: list[DataFileSet]) -> tuple[dict, dict, dict]:
    """
    Collect column frequencies and per-dataset column sets (doc/judge).
    Returns (stats, dataset_cols, totals).
    """
    stats: dict[str, dict[str, dict[str, int]]] = {"doc": {}, "judge": {}}
    totals: dict[str, dict[str, int]] = {"doc": {}, "judge": {}}
    dataset_cols: dict[tuple[str, str, str, str], set[str]] = {}

    for ds in datasets:
        for kind, path in [("doc", ds.doc_path), ("judge", ds.judge_path)]:
            for sheet in SHEETS:
                cols = _read_sheet_header(path, sheet)
                dataset_cols[(ds.center, ds.model, kind, sheet)] = set(cols)
                if not cols:
                    continue
                totals[kind][sheet] = totals[kind].get(sheet, 0) + 1
                for c in cols:
                    stats.setdefault(kind, {}).setdefault(sheet, {})
                    stats[kind][sheet][c] = stats[kind][sheet].get(c, 0) + 1

    return stats, dataset_cols, totals


def compute_common_columns(
    stats: dict[str, dict[str, dict[str, int]]],
    totals: dict[str, dict[str, int]],
    min_ratio: float = 0.6,
    min_count: int = 2,
) -> dict[str, dict[str, set[str]]]:
    common: dict[str, dict[str, set[str]]] = {"doc": {}, "judge": {}}
    for kind, sheet_stats in stats.items():
        for sheet, col_counts in sheet_stats.items():
            total = max(1, totals.get(kind, {}).get(sheet, 0))
            threshold = max(min_count, int(math.ceil(total * min_ratio)))
            cols = {c for c, n in col_counts.items() if n >= threshold}
            common.setdefault(kind, {})[sheet] = cols
    return common


def scan_column_anomalies(
    dataset_cols: dict[tuple[str, str, str, str], set[str]],
    common_cols: dict[str, dict[str, set[str]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def _is_expected_extra(kind: str, sheet: str, col: str) -> bool:
        # Loops can reach round 3/4; treat those columns as normal.
        if sheet in {"D1_Outpatient_Loop", "D2_Admission_Loop"}:
            if col.startswith("第3轮_医生_原始JSON_") or col.startswith("第4轮_医生_原始JSON_"):
                return True
            if col.startswith("第3轮_判官_原始JSON_") or col.startswith("第4轮_判官_原始JSON_"):
                return True
        # Decision nested fields are auto-merged; treat as expected.
        if sheet in {"D1_Outpatient_Decision", "D2_Admission_Decision"} and kind == "doc":
            if col.startswith("医生决策_原始JSON_初步治疗方案_"):
                return True
            if col.startswith("医生决策_原始JSON_术后信息汇总"):
                return True
            if col.startswith("医生决策_原始JSON_初步治疗方案_术后信息汇总"):
                return True
        if sheet == "D3_Surgery_Decision" and kind == "doc":
            if col == "医生_原始JSON_方案思维":
                return True
        return False
    for (center, model, kind, sheet), cols in dataset_cols.items():
        common = common_cols.get(kind, {}).get(sheet, set())
        if not common:
            continue
        missing = sorted(common - cols)
        extra = sorted(cols - common)
        # User-confirmed: missing common columns are expected (do not list as anomalies).
        # for c in missing:
        #     rows.append(
        #         {
        #             "center": center,
        #             "model": model,
        #             "kind": kind,
        #             "sheet": sheet,
        #             "case_id": "",
        #             "round_idx": "",
        #             "anomaly_type": "missing_common_column",
        #             "column": c,
        #             "details": json.dumps({"note": "该中心/模型缺失通用列"}, ensure_ascii=False),
        #         }
        #     )
        for c in extra:
            if _is_expected_extra(kind, sheet, c):
                continue
            rows.append(
                {
                    "center": center,
                    "model": model,
                    "kind": kind,
                    "sheet": sheet,
                    "case_id": "",
                    "round_idx": "",
                    "anomaly_type": "extra_rare_column",
                    "column": c,
                    "details": json.dumps({"note": "该列在其他文件中不常见"}, ensure_ascii=False),
                }
            )
    return rows


def _get_row(df: pd.DataFrame, case_id: str) -> pd.Series | None:
    if df.empty:
        return None
    cid_col = df.columns[0]
    sel = df.loc[df[cid_col].astype(str) == case_id]
    if sel.empty:
        return None
    return sel.iloc[0]


def _case_ids_from_doc(doc_sheets: dict[str, pd.DataFrame]) -> list[str]:
    case_ids: set[str] = set()
    for df in doc_sheets.values():
        if df is None or df.empty:
            continue
        cid_col = df.columns[0]
        for x in df[cid_col].dropna().astype(str).tolist():
            cid = str(x).strip()
            if cid:
                case_ids.add(cid)
    return sorted(case_ids, key=case_id_sort_key)


def scan_missing_value_anomalies(
    *,
    fileset: DataFileSet,
    doc_sheets: dict[str, pd.DataFrame],
    judge_sheets: dict[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    case_ids = _case_ids_from_doc(doc_sheets)
    d1_anomalies = detect_d1_decision_anomaly(
        doc_sheets.get("D1_Outpatient_Decision", pd.DataFrame()),
        doc_sheets.get("D2_Admission_Decision", pd.DataFrame()),
    )

    # Doc missing required fields
    for stage, req_cols in DOC_REQUIRED_ALL.items():
        df = doc_sheets.get(stage)
        if df is None or df.empty:
            continue
        for case_id in case_ids:
            if stage == "D1_Outpatient_Decision" and case_id in d1_anomalies:
                continue
            row = _get_row(df, case_id)
            if row is None:
                continue
            if not _row_has_output_for_stage(stage, df, row):
                continue
            for c in req_cols:
                if c not in df.columns:
                    continue
                if is_empty(row.get(c)):
                    rows.append(
                        {
                            "center": fileset.center,
                            "model": fileset.model,
                            "kind": "doc",
                            "sheet": stage,
                            "case_id": case_id,
                            "round_idx": "",
                            "anomaly_type": "doc_missing_required_field",
                            "column": c,
                            "details": json.dumps({"note": "阶段有输出但关键字段为空"}, ensure_ascii=False),
                        }
                    )

    for stage, req_cols in DOC_REQUIRED_ANY.items():
        df = doc_sheets.get(stage)
        if df is None or df.empty:
            continue
        for case_id in case_ids:
            row = _get_row(df, case_id)
            if row is None:
                continue
            if not _row_has_output_for_stage(stage, df, row):
                continue
            cols = [c for c in req_cols if c in df.columns]
            if not cols:
                continue
            if all(is_empty(row.get(c)) for c in cols):
                rows.append(
                    {
                        "center": fileset.center,
                        "model": fileset.model,
                        "kind": "doc",
                        "sheet": stage,
                        "case_id": case_id,
                        "round_idx": "",
                        "anomaly_type": "doc_missing_required_any",
                        "column": "|".join(cols),
                        "details": json.dumps({"note": "需至少填写一项"}, ensure_ascii=False),
                    }
                )

    # Judge missing required fields (only when doc stage has output)
    for stage, req_cols in JUDGE_REQUIRED_ALL.items():
        doc_df = doc_sheets.get(stage)
        judge_df = judge_sheets.get(stage)
        if doc_df is None or judge_df is None or doc_df.empty or judge_df.empty:
            continue
        for case_id in case_ids:
            if stage == "D1_Outpatient_Decision" and case_id in d1_anomalies:
                continue
            doc_row = _get_row(doc_df, case_id)
            if doc_row is None or not _row_has_output_for_stage(stage, doc_df, doc_row):
                continue
            judge_row = _get_row(judge_df, case_id)
            if judge_row is None:
                rows.append(
                    {
                        "center": fileset.center,
                        "model": fileset.model,
                        "kind": "judge",
                        "sheet": stage,
                        "case_id": case_id,
                        "round_idx": "",
                        "anomaly_type": "judge_missing_all_fields",
                        "column": "|".join([c for c in req_cols if c in judge_df.columns]),
                        "details": json.dumps({"note": "阶段有输出但裁判行缺失"}, ensure_ascii=False),
                    }
                )
                continue
            cols = [c for c in req_cols if c in judge_df.columns]
            if not cols:
                continue
            if all(is_empty(judge_row.get(c)) for c in cols):
                rows.append(
                    {
                        "center": fileset.center,
                        "model": fileset.model,
                        "kind": "judge",
                        "sheet": stage,
                        "case_id": case_id,
                        "round_idx": "",
                        "anomaly_type": "judge_missing_all_fields",
                        "column": "|".join(cols),
                        "details": json.dumps({"note": "裁判关键字段全部为空"}, ensure_ascii=False),
                    }
                )
            else:
                for c in cols:
                    if is_empty(judge_row.get(c)):
                        rows.append(
                            {
                                "center": fileset.center,
                                "model": fileset.model,
                                "kind": "judge",
                                "sheet": stage,
                                "case_id": case_id,
                                "round_idx": "",
                                "anomaly_type": "judge_missing_required_field",
                                "column": c,
                                "details": json.dumps({"note": "裁判字段缺失"}, ensure_ascii=False),
                            }
                        )

    return rows
