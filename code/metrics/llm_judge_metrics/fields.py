from __future__ import annotations

from typing import Any

import pandas as pd

from .parsing import is_empty
from .types import LoadedData
from .status import safe_float


def _normalize_gt(gt: pd.DataFrame) -> pd.DataFrame:
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.copy()
    gt["CaseID"] = gt["CaseID"].astype(str)
    return gt


def _extract_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    keep = [c for c in cols if c in df.columns]
    return df[keep].copy()


def _left_join_case_id(df_left: pd.DataFrame, left_id: str, df_right: pd.DataFrame, right_id: str, cols_right: list[str]) -> pd.DataFrame:
    right = _extract_cols(df_right, [right_id] + cols_right).copy()
    right = right.rename(columns={right_id: left_id})
    return df_left.merge(right, on=left_id, how="left")


def build_d1_decision_fields(loaded: LoadedData) -> pd.DataFrame:
    gt = _normalize_gt(loaded.gt)
    doc = loaded.doc_sheets["D1_Outpatient_Decision"].copy()
    judge = loaded.judge_sheets["D1_Outpatient_Decision"].copy()

    cid_doc = doc.columns[0]
    cid_judge = judge.columns[0]

    doc_cols = [
        "状态",
        "医生决策_原始JSON_初步诊断列表",
        "医生决策_原始JSON_初步诊断思维",
        "医生决策_原始JSON_门诊信息汇总",
        "医生决策_原始JSON_置信度评估_诊断置信度",
        "医生决策_原始JSON_建议检查项目",
        "医生决策_原始JSON_建议检查思维",
    ]
    judge_cols = [
        "状态",
        "Gate1判官_原始JSON_是否继续评测",
        "Gate1判官_原始JSON_综合评分",
        "Gate1判官_原始JSON_诊断匹配_结论",
        "Gate1判官_原始JSON_诊断匹配_理由",
        "Gate1判官_原始JSON_诊断匹配_评分",
        "Gate1判官_原始JSON_检查匹配_匹配度",
        "Gate1判官_原始JSON_检查匹配_评分",
        "Gate1判官_原始JSON_检查匹配_匹配的检查项目",
        "Gate1判官_原始JSON_检查匹配_未匹配的检查项目",
    ]
    gt_cols = [
        "GT_Outpatient_Checks",
        "GT_Admission_Checks",
        "GT_Admission_Diagnosis",
    ]

    out = pd.DataFrame({"case_id": doc[cid_doc].astype(str)})
    out["center"] = loaded.fileset.center
    out["model"] = loaded.fileset.model

    doc_small = _extract_cols(doc, [cid_doc] + doc_cols).rename(columns={cid_doc: "case_id"})
    judge_small = _extract_cols(judge, [cid_judge] + judge_cols).rename(columns={cid_judge: "case_id"})
    gt_small = _extract_cols(gt, ["CaseID"] + gt_cols).rename(columns={"CaseID": "case_id"})

    out = out.merge(doc_small, on="case_id", how="left", suffixes=("", "__doc"))
    out = out.merge(judge_small, on="case_id", how="left", suffixes=("", "__judge"))
    out = out.merge(gt_small, on="case_id", how="left")

    # Rename duplicated status columns for clarity
    if "状态" in out.columns and "状态__judge" in out.columns:
        out = out.rename(columns={"状态": "doc_status", "状态__judge": "judge_status"})

    return out


def build_d2_decision_fields(loaded: LoadedData) -> pd.DataFrame:
    gt = _normalize_gt(loaded.gt)
    doc = loaded.doc_sheets["D2_Admission_Decision"].copy()
    judge = loaded.judge_sheets["D2_Admission_Decision"].copy()

    cid_doc = doc.columns[0]
    cid_judge = judge.columns[0]

    doc_cols = [
        "状态",
        "医生决策_原始JSON_修正诊断",
        "医生决策_原始JSON_修正诊断思维",
        "医生决策_原始JSON_初步治疗方案",
        "医生决策_原始JSON_治疗方案思维",
        "医生决策_原始JSON_置信度评估_诊断置信度",
        "医生决策_原始JSON_置信度评估_治疗方案置信度",
        "医生决策_原始JSON_诊疗经过回顾",
    ]
    judge_cols = [
        "状态",
        "Gate2判官_原始JSON_是否继续评测",
        "Gate2判官_原始JSON_是否需要二审",
        "Gate2判官_原始JSON_综合评分",
        "Gate2判官_原始JSON_修正诊断匹配_结论",
        "Gate2判官_原始JSON_修正诊断匹配_理由",
        "Gate2判官_原始JSON_修正诊断匹配_评分",
        "Gate2判官_原始JSON_手术方案匹配_结论",
        "Gate2判官_原始JSON_手术方案匹配_理由",
        "Gate2判官_原始JSON_手术方案匹配_评分",
        "Gate2_二审原始JSON_is_reasonable",
        "Gate2_二审原始JSON_是否能继续评测",
        "Gate2_二审原始JSON_reasonableness_analysis",
    ]
    gt_cols = [
        "GT_Revised_Diagnosis",
        "GT_Admission_Checks",
        "GT_Surgery_Plan",
    ]

    out = pd.DataFrame({"case_id": doc[cid_doc].astype(str)})
    out["center"] = loaded.fileset.center
    out["model"] = loaded.fileset.model

    doc_small = _extract_cols(doc, [cid_doc] + doc_cols).rename(columns={cid_doc: "case_id"})
    judge_small = _extract_cols(judge, [cid_judge] + judge_cols).rename(columns={cid_judge: "case_id"})
    gt_small = _extract_cols(gt, ["CaseID"] + gt_cols).rename(columns={"CaseID": "case_id"})

    out = out.merge(doc_small, on="case_id", how="left", suffixes=("", "__doc"))
    out = out.merge(judge_small, on="case_id", how="left", suffixes=("", "__judge"))
    out = out.merge(gt_small, on="case_id", how="left")

    if "状态" in out.columns and "状态__judge" in out.columns:
        out = out.rename(columns={"状态": "doc_status", "状态__judge": "judge_status"})

    return out


def build_d3_decision_fields(loaded: LoadedData) -> pd.DataFrame:
    gt = _normalize_gt(loaded.gt)
    doc = loaded.doc_sheets["D3_Surgery_Decision"].copy()
    judge = loaded.judge_sheets["D3_Surgery_Decision"].copy()

    cid_doc = doc.columns[0]
    cid_judge = judge.columns[0]

    doc_cols = [
        "状态",
        "医生_原始JSON_最终诊断_诊断名称",
        "医生_原始JSON_最终诊断_诊断思维",
        "医生_原始JSON_术后治疗方案_方案详情",
        "医生_原始JSON_术后治疗方案_方案思维",
        "医生_原始JSON_术后信息汇总",
        "医生_原始JSON_诊疗经过回顾",
    ]
    judge_cols = [
        "状态",
        "判官_原始JSON_是否继续评测",
        "判官_原始JSON_综合评分",
        "判官_原始JSON_诊断匹配评估_结论",
        "判官_原始JSON_诊断匹配评估_理由",
        "判官_原始JSON_诊断匹配评估_评分",
        "判官_原始JSON_治疗方案匹配评估_结论",
        "判官_原始JSON_治疗方案匹配评估_理由",
        "判官_原始JSON_治疗方案匹配评估_评分",
    ]
    gt_cols = [
        "GT_Final_Diagnosis",
        "GT_PostOp_Plan",
        "GT_Pathology",
        "GT_Surgery_Findings",
    ]

    out = pd.DataFrame({"case_id": doc[cid_doc].astype(str)})
    out["center"] = loaded.fileset.center
    out["model"] = loaded.fileset.model

    doc_small = _extract_cols(doc, [cid_doc] + doc_cols).rename(columns={cid_doc: "case_id"})
    judge_small = _extract_cols(judge, [cid_judge] + judge_cols).rename(columns={cid_judge: "case_id"})
    gt_small = _extract_cols(gt, ["CaseID"] + gt_cols).rename(columns={"CaseID": "case_id"})

    out = out.merge(doc_small, on="case_id", how="left", suffixes=("", "__doc"))
    out = out.merge(judge_small, on="case_id", how="left", suffixes=("", "__judge"))
    out = out.merge(gt_small, on="case_id", how="left")

    if "状态" in out.columns and "状态__judge" in out.columns:
        out = out.rename(columns={"状态": "doc_status", "状态__judge": "judge_status"})

    return out


def build_d4_rehab_fields(loaded: LoadedData) -> pd.DataFrame:
    gt = _normalize_gt(loaded.gt)
    doc = loaded.doc_sheets["D4_Rehab_Plan"].copy()
    judge = loaded.judge_sheets["D4_Rehab_Plan"].copy()

    cid_doc = doc.columns[0]
    cid_judge = judge.columns[0]

    doc_cols = [
        "状态",
        "医生_原始JSON_出院康复计划_方案详情",
        "医生_原始JSON_长期随访计划_方案详情",
        "医生_原始JSON_长期随访计划_是否需要常规随访",
        "医生_原始JSON_康复阶段信息汇总",
        "医生_原始JSON_诊疗经过回顾",
    ]
    judge_cols = [
        "状态",
        "判官_原始JSON_综合评分",
        "判官_原始JSON_康复计划评估_评分",
        "判官_原始JSON_康复计划评估_理由",
        "判官_原始JSON_随访计划评估_评分",
        "判官_原始JSON_随访计划评估_理由",
    ]
    gt_cols = [
        "GT_Rehab_Plan",
        "GT_Followup_Plan",
        "GT_Final_Diagnosis",
    ]

    out = pd.DataFrame({"case_id": doc[cid_doc].astype(str)})
    out["center"] = loaded.fileset.center
    out["model"] = loaded.fileset.model

    doc_small = _extract_cols(doc, [cid_doc] + doc_cols).rename(columns={cid_doc: "case_id"})
    judge_small = _extract_cols(judge, [cid_judge] + judge_cols).rename(columns={cid_judge: "case_id"})
    gt_small = _extract_cols(gt, ["CaseID"] + gt_cols).rename(columns={"CaseID": "case_id"})

    out = out.merge(doc_small, on="case_id", how="left", suffixes=("", "__doc"))
    out = out.merge(judge_small, on="case_id", how="left", suffixes=("", "__judge"))
    out = out.merge(gt_small, on="case_id", how="left")

    if "状态" in out.columns and "状态__judge" in out.columns:
        out = out.rename(columns={"状态": "doc_status", "状态__judge": "judge_status"})

    return out


def build_judge_scores_by_case(loaded: LoadedData) -> pd.DataFrame:
    """
    Extract a compact, numeric-friendly judge score table per case.
    This avoids merging the full text-heavy *decision_fields into metrics_by_case.
    """

    def get_row(df: pd.DataFrame, case_id: str) -> pd.Series | None:
        if df.empty:
            return None
        cid_col = df.columns[0]
        sel = df.loc[df[cid_col].astype(str) == case_id]
        if sel.empty:
            return None
        return sel.iloc[0]

    d1 = loaded.judge_sheets["D1_Outpatient_Decision"]
    d2 = loaded.judge_sheets["D2_Admission_Decision"]
    d3 = loaded.judge_sheets["D3_Surgery_Decision"]
    d4 = loaded.judge_sheets["D4_Rehab_Plan"]

    case_ids = [str(x) for x in d1[d1.columns[0]].dropna().astype(str).unique()]
    rows: list[dict[str, Any]] = []
    for case_id in case_ids:
        r1 = get_row(d1, case_id)
        r2 = get_row(d2, case_id)
        r3 = get_row(d3, case_id)
        r4 = get_row(d4, case_id)

        row: dict[str, Any] = {"center": loaded.fileset.center, "model": loaded.fileset.model, "case_id": case_id}

        def get_text(r: pd.Series | None, col: str) -> str:
            if r is None or col not in r.index:
                return ""
            v = r.get(col)
            return "" if is_empty(v) else str(v).strip()

        def get_boollike(r: pd.Series | None, col: str) -> bool | None:
            if r is None or col not in r.index:
                return None
            v = r.get(col)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            if isinstance(v, bool):
                return bool(v)
            s = str(v).strip().lower()
            if s in {"1", "true", "yes", "y", "是", "通过"}:
                return True
            if s in {"0", "false", "no", "n", "否", "不通过"}:
                return False
            return None

        def get_num(r: pd.Series | None, col: str) -> float | None:
            if r is None or col not in r.index:
                return None
            return safe_float(r.get(col))

        # Gate1 / D1 decision
        row["gate1_continue"] = get_boollike(r1, "Gate1判官_原始JSON_是否继续评测")
        row["gate1_overall_score"] = get_num(r1, "Gate1判官_原始JSON_综合评分")
        row["gate1_dx_conclusion"] = get_text(r1, "Gate1判官_原始JSON_诊断匹配_结论")
        row["gate1_dx_score"] = get_num(r1, "Gate1判官_原始JSON_诊断匹配_评分")
        row["gate1_check_match_degree"] = get_num(r1, "Gate1判官_原始JSON_检查匹配_匹配度")
        row["gate1_check_score"] = get_num(r1, "Gate1判官_原始JSON_检查匹配_评分")

        # Gate2 / D2 decision
        def get_boollike_any(r: pd.Series | None, cols: list[str]) -> bool | None:
            for col in cols:
                v = get_boollike(r, col)
                if v is not None:
                    return v
            return None

        row["gate2_continue"] = get_boollike_any(
            r2,
            [
                "Gate2_二审原始JSON_是否能继续评测",
                "Gate2_二审原始JSON_is_reasonable",
                "Gate2判官_原始JSON_是否继续评测",
            ],
        )
        row["gate2_overall_score"] = get_num(r2, "Gate2判官_原始JSON_综合评分")
        row["gate2_revised_dx_conclusion"] = get_text(r2, "Gate2判官_原始JSON_修正诊断匹配_结论")
        row["gate2_revised_dx_score"] = get_num(r2, "Gate2判官_原始JSON_修正诊断匹配_评分")
        row["gate2_surgery_conclusion"] = get_text(r2, "Gate2判官_原始JSON_手术方案匹配_结论")
        row["gate2_surgery_score"] = get_num(r2, "Gate2判官_原始JSON_手术方案匹配_评分")
        row["gate2_secondary_is_reasonable"] = get_boollike_any(
            r2,
            [
                "Gate2_二审原始JSON_is_reasonable",
                "Gate2_二审原始JSON_是否能继续评测",
            ],
        )

        # D3 decision
        row["d3_continue"] = get_boollike(r3, "判官_原始JSON_是否继续评测")
        row["d3_overall_score"] = get_num(r3, "判官_原始JSON_综合评分")
        row["d3_dx_conclusion"] = get_text(r3, "判官_原始JSON_诊断匹配评估_结论")
        row["d3_dx_score"] = get_num(r3, "判官_原始JSON_诊断匹配评估_评分")
        row["d3_plan_conclusion"] = get_text(r3, "判官_原始JSON_治疗方案匹配评估_结论")
        row["d3_plan_score"] = get_num(r3, "判官_原始JSON_治疗方案匹配评估_评分")

        # D4 plan
        row["d4_overall_score"] = get_num(r4, "判官_原始JSON_综合评分")
        row["d4_rehab_score"] = get_num(r4, "判官_原始JSON_康复计划评估_评分")
        row["d4_followup_score"] = get_num(r4, "判官_原始JSON_随访计划评估_评分")

        rows.append(row)

    return pd.DataFrame(rows)
