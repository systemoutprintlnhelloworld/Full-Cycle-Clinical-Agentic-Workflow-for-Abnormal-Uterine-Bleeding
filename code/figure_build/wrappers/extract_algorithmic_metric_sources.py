"""Extract audit-friendly algorithmic (machine) metric source tables.

This script rebuilds the algorithmic metrics (A1-A8 family) from canonical
tables and outputs "detail + summary + exclusions" workbooks.

Canonical raw sources
---------------------
- analysis_viz/data/raw/metrics_source_data.xlsx
- analysis_viz/data/raw/医生评测汇总.xlsx

Mandatory sample rules
----------------------
1) D1 anomaly cases do NOT participate in any calculations.
2) Gate3-fail cases do NOT contribute to D4 calculations.

Outputs
-------
- analysis_viz/data/derived/metrics/algorithmic/*.xlsx
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "analysis_viz" / "data" / "raw"
OUT_DIR = ROOT / "analysis_viz" / "data" / "derived" / "metrics" / "algorithmic"

RAW_METRICS_SOURCE = RAW_DIR / "metrics_source_data.xlsx"
RAW_DOCTOR_SUMMARY = RAW_DIR / "医生评测汇总.xlsx"


MODEL_SHORT = {
    "deepseek-v3-1-think-250821": "deepseek-v3",
    "gpt-5-2025-08-07": "gpt-5",
    "gemini-2.5-pro": "gemini-2.5p",
    "grok-4": "grok-4",
    "claude-opus-4-1-20250805-thinking": "claude-4.1",
}

STAGE6_RENAME = {
    "D1_Loop": "门诊检查",
    "D1_Decision": "门诊决策",
    "D2_Loop": "入院检查",
    "D2_Decision": "入院决策",
    "D3_Decision": "术后康复",
    "D4_Plan": "随访计划",
    "D1_Decision_D2Check": "门诊决策",
}


def _load_d1_anomaly_set() -> set[tuple[str, str, str]]:
    df = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="d1_decision_anomalies")
    return set(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))


def _load_gate3_fail_set() -> set[tuple[str, str, str]]:
    df = pd.read_excel(RAW_DOCTOR_SUMMARY, sheet_name="人工评分_D4Gate3不通过")
    df = df.rename(columns={"中心": "center", "模型名称": "model", "病例ID": "case_id"})
    return set(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))


def _add_common_cols(df: pd.DataFrame, *, stage_col: str | None = "stage") -> pd.DataFrame:
    df = df.copy()
    df["model_short"] = df["model"].map(MODEL_SHORT).fillna(df["model"].astype(str))
    if stage_col and stage_col in df.columns:
        df["stage_cn"] = df[stage_col].map(STAGE6_RENAME).fillna(df[stage_col].astype(str))
    return df


def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame], meta_rows: list[dict[str, object]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = pd.DataFrame(meta_rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
        meta.to_excel(writer, sheet_name="meta", index=False)


def _extract_check_match_rate(d1_set: set[tuple[str, str, str]]) -> Path:
    usecols = [
        "center",
        "model",
        "case_id",
        "D1_Outpatient_Loop__judge_match_score_mean",
        "D2_Admission_Loop__judge_match_score_mean",
    ]
    df_case = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="metrics_by_case", usecols=usecols)

    rows: list[dict[str, object]] = []
    for rec in df_case.to_dict(orient="records"):
        base = {
            "center": str(rec.get("center")),
            "model": str(rec.get("model")),
            "case_id": str(rec.get("case_id")),
        }
        d1 = rec.get("D1_Outpatient_Loop__judge_match_score_mean")
        if pd.notna(d1):
            rows.append({**base, "stage": "D1_Loop", "check_match_rate": float(d1)})
        d2 = rec.get("D2_Admission_Loop__judge_match_score_mean")
        if pd.notna(d2):
            rows.append({**base, "stage": "D2_Loop", "check_match_rate": float(d2)})

    detail_all = pd.DataFrame(rows)
    if detail_all.empty:
        raise RuntimeError("No rows extracted for algorithmic check match rate")

    detail_all = _add_common_cols(detail_all)
    keys = list(
        zip(
            detail_all["center"].astype(str),
            detail_all["model"].astype(str),
            detail_all["case_id"].astype(str),
        )
    )
    detail_all["is_d1_anomaly"] = [k in d1_set for k in keys]
    detail_all["is_gate3_fail"] = False

    excluded_d1 = detail_all[detail_all["is_d1_anomaly"]].copy()
    detail_used = detail_all[~detail_all["is_d1_anomaly"]].copy()

    summary_used = (
        detail_used.groupby(["center", "model", "model_short", "stage", "stage_cn"], as_index=False)
        .agg(
            check_match_rate_mean=("check_match_rate", "mean"),
            n_cases=("case_id", "nunique"),
        )
        .sort_values(["center", "stage", "model_short"], kind="mergesort")
    )

    out_path = OUT_DIR / "algorithmic_check_match_rate_source.xlsx"
    _write_xlsx(
        out_path,
        {
            "detail_all": detail_all,
            "detail_used": detail_used,
            "summary_used": summary_used,
            "excluded_d1_anomaly": excluded_d1,
        },
        [
            {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
            {"key": "raw_file", "value": str(RAW_METRICS_SOURCE)},
            {"key": "raw_sheet", "value": "metrics_by_case"},
            {"key": "description", "value": "Algorithmic A1: D1/D2 检查匹配率（病例均值）"},
            {"key": "d1_anomaly_source", "value": "metrics_source_data.xlsx/d1_decision_anomalies"},
            {"key": "detail_rows", "value": int(len(detail_all))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "used_rows", "value": int(len(detail_used))},
        ],
    )
    return out_path


def _extract_loop_inefficiency(d1_set: set[tuple[str, str, str]]) -> Path:
    usecols = [
        "center",
        "model",
        "case_id",
        "d1_inefficiency_by_zero",
        "d2_inefficiency_by_zero",
    ]
    df_case = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="metrics_by_case", usecols=usecols)

    rows: list[dict[str, object]] = []
    for rec in df_case.to_dict(orient="records"):
        base = {
            "center": str(rec.get("center")),
            "model": str(rec.get("model")),
            "case_id": str(rec.get("case_id")),
        }
        d1 = rec.get("d1_inefficiency_by_zero")
        if pd.notna(d1):
            rows.append({**base, "stage": "D1_Loop", "loop_inefficiency_0_match": float(d1)})
        d2 = rec.get("d2_inefficiency_by_zero")
        if pd.notna(d2):
            rows.append({**base, "stage": "D2_Loop", "loop_inefficiency_0_match": float(d2)})

    detail_all = pd.DataFrame(rows)
    if detail_all.empty:
        raise RuntimeError("No rows extracted for algorithmic loop inefficiency")

    detail_all = _add_common_cols(detail_all)
    keys = list(
        zip(
            detail_all["center"].astype(str),
            detail_all["model"].astype(str),
            detail_all["case_id"].astype(str),
        )
    )
    detail_all["is_d1_anomaly"] = [k in d1_set for k in keys]
    detail_all["is_gate3_fail"] = False

    excluded_d1 = detail_all[detail_all["is_d1_anomaly"]].copy()
    detail_used = detail_all[~detail_all["is_d1_anomaly"]].copy()

    summary_used = (
        detail_used.groupby(["center", "model", "model_short", "stage", "stage_cn"], as_index=False)
        .agg(
            loop_inefficiency_0_match_mean=("loop_inefficiency_0_match", "mean"),
            n_cases=("case_id", "nunique"),
        )
        .sort_values(["center", "stage", "model_short"], kind="mergesort")
    )

    out_path = OUT_DIR / "algorithmic_loop_inefficiency_source.xlsx"
    _write_xlsx(
        out_path,
        {
            "detail_all": detail_all,
            "detail_used": detail_used,
            "summary_used": summary_used,
            "excluded_d1_anomaly": excluded_d1,
        },
        [
            {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
            {"key": "raw_file", "value": str(RAW_METRICS_SOURCE)},
            {"key": "raw_sheet", "value": "metrics_by_case"},
            {"key": "description", "value": "Algorithmic A2: D1/D2 无效循环率（0-match）"},
            {"key": "d1_anomaly_source", "value": "metrics_source_data.xlsx/d1_decision_anomalies"},
            {"key": "detail_rows", "value": int(len(detail_all))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "used_rows", "value": int(len(detail_used))},
        ],
    )
    return out_path


def _extract_stage_pass_rate(d1_set: set[tuple[str, str, str]]) -> Path:
    df = pd.read_excel(RAW_DOCTOR_SUMMARY, sheet_name="通过退出明细")
    df = df.rename(columns={"中心": "center", "模型名称": "model", "病例ID": "case_id"})
    required = {"center", "model", "case_id", "D1_Decision", "D2_Decision", "D3_Decision"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"doctor summary missing columns: {sorted(list(missing))}")

    detail_all = df[["center", "model", "case_id", "D1_Decision", "D2_Decision", "D3_Decision"]].copy()
    detail_all = _add_common_cols(detail_all, stage_col=None)
    keys = list(
        zip(
            detail_all["center"].astype(str),
            detail_all["model"].astype(str),
            detail_all["case_id"].astype(str),
        )
    )
    detail_all["is_d1_anomaly"] = [k in d1_set for k in keys]
    detail_all["is_gate3_fail"] = False

    excluded_d1 = detail_all[detail_all["is_d1_anomaly"]].copy()
    detail_used = detail_all[~detail_all["is_d1_anomaly"]].copy()

    def _has(text: str, key: str) -> bool:
        return key in str(text or "")

    rows: list[dict[str, object]] = []
    for (center, model), sub in detail_used.groupby(["center", "model"], dropna=False):
        total = int(sub["case_id"].astype(str).nunique())
        if total <= 0:
            continue
        d1_dec = sub["D1_Decision"].fillna("").astype(str)
        d2_dec = sub["D2_Decision"].fillna("").astype(str)
        d3_dec = sub["D3_Decision"].fillna("").astype(str)

        d1_pass = d1_dec.apply(lambda s: _has(s, "D1决策_通过") and (not _has(s, "D1决策_特殊")))
        d2_first = d2_dec.apply(lambda s: _has(s, "一审通过"))
        d2_second = d2_dec.apply(lambda s: _has(s, "需要二审_通过二审"))
        d3_pass = d3_dec.apply(lambda s: _has(s, "通过一审") or _has(s, "需要二审_通过二审"))

        rows.append(
            {
                "center": center,
                "model": model,
                "model_short": MODEL_SHORT.get(str(model), str(model)),
                "n_cases": total,
                "d1_pass_count": int(d1_pass.sum()),
                "d1_pass_rate": float(d1_pass.sum() / total),
                "d2_first_pass_count": int(d2_first.sum()),
                "d2_first_pass_rate": float(d2_first.sum() / total),
                "d2_second_pass_count": int(d2_second.sum()),
                "d2_second_pass_rate": float(d2_second.sum() / total),
                "d3_pass_count": int(d3_pass.sum()),
                "d3_pass_rate": float(d3_pass.sum() / total),
            }
        )

    summary_used = pd.DataFrame(rows).sort_values(["center", "model_short"], kind="mergesort")

    out_path = OUT_DIR / "algorithmic_stage_pass_rate_source.xlsx"
    _write_xlsx(
        out_path,
        {
            "detail_all": detail_all,
            "detail_used": detail_used,
            "summary_used": summary_used,
            "excluded_d1_anomaly": excluded_d1,
        },
        [
            {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
            {"key": "raw_file", "value": str(RAW_DOCTOR_SUMMARY)},
            {"key": "raw_sheet", "value": "通过退出明细"},
            {"key": "description", "value": "Algorithmic A3: D1/D2/D3 阶段通过率（基于通过退出明细）"},
            {"key": "d1_anomaly_source", "value": "metrics_source_data.xlsx/d1_decision_anomalies"},
            {"key": "detail_rows", "value": int(len(detail_all))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "used_rows", "value": int(len(detail_used))},
        ],
    )
    return out_path


def _extract_judge_scores_by_stage(
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
) -> Path:
    usecols = [
        "center",
        "model",
        "case_id",
        "gate1_overall_score",
        "gate2_overall_score",
        "d3_overall_score",
        "d4_overall_score",
    ]
    df = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="judge_scores_by_case", usecols=usecols)

    rows: list[dict[str, object]] = []
    for rec in df.to_dict(orient="records"):
        base = {
            "center": str(rec.get("center")),
            "model": str(rec.get("model")),
            "case_id": str(rec.get("case_id")),
        }
        for stage, col in [
            ("D1_Decision", "gate1_overall_score"),
            ("D2_Decision", "gate2_overall_score"),
            ("D3_Decision", "d3_overall_score"),
            ("D4_Plan", "d4_overall_score"),
        ]:
            v = rec.get(col)
            if pd.isna(v):
                continue
            rows.append({**base, "stage": stage, "judge_overall_score": float(v)})

    detail_all = pd.DataFrame(rows)
    if detail_all.empty:
        raise RuntimeError("No rows extracted for judge scores by stage")

    detail_all = _add_common_cols(detail_all)
    keys = list(
        zip(
            detail_all["center"].astype(str),
            detail_all["model"].astype(str),
            detail_all["case_id"].astype(str),
        )
    )
    detail_all["is_d1_anomaly"] = [k in d1_set for k in keys]
    detail_all["is_gate3_fail"] = [k in gate3_set for k in keys]

    excluded_d1 = detail_all[detail_all["is_d1_anomaly"]].copy()
    used = detail_all[~detail_all["is_d1_anomaly"]].copy()
    excluded_gate3_d4 = used[(used["stage"] == "D4_Plan") & (used["is_gate3_fail"])].copy()
    detail_used = used.drop(excluded_gate3_d4.index)

    summary_used = (
        detail_used.groupby(["center", "model", "model_short", "stage", "stage_cn"], as_index=False)
        .agg(
            judge_overall_score_mean=("judge_overall_score", "mean"),
            n_cases=("case_id", "nunique"),
        )
        .sort_values(["center", "stage", "model_short"], kind="mergesort")
    )

    out_path = OUT_DIR / "algorithmic_judge_scores_by_stage_source.xlsx"
    _write_xlsx(
        out_path,
        {
            "detail_all": detail_all,
            "detail_used": detail_used,
            "summary_used": summary_used,
            "excluded_d1_anomaly": excluded_d1,
            "excluded_gate3_d4": excluded_gate3_d4,
        },
        [
            {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
            {"key": "raw_file", "value": str(RAW_METRICS_SOURCE)},
            {"key": "raw_sheet", "value": "judge_scores_by_case"},
            {"key": "description", "value": "Algorithmic A4: Judge 综合评分（按阶段）"},
            {"key": "d1_anomaly_source", "value": "metrics_source_data.xlsx/d1_decision_anomalies"},
            {"key": "gate3_fail_source", "value": "医生评测汇总.xlsx/人工评分_D4Gate3不通过"},
            {"key": "detail_rows", "value": int(len(detail_all))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "excluded_gate3_d4_rows", "value": int(len(excluded_gate3_d4))},
            {"key": "used_rows", "value": int(len(detail_used))},
        ],
    )
    return out_path


def _extract_judge_score_pathways(
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
) -> Path:
    df_judge = pd.read_excel(
        RAW_METRICS_SOURCE,
        sheet_name="judge_scores_by_case",
        usecols=[
            "center",
            "model",
            "case_id",
            "gate1_dx_score",
            "gate2_revised_dx_score",
            "d3_dx_score",
            "gate1_check_score",
            "gate2_surgery_score",
            "d3_plan_score",
            "d4_rehab_score",
            "d4_followup_score",
        ],
    )
    df_loop = pd.read_excel(
        RAW_METRICS_SOURCE,
        sheet_name="metrics_by_case",
        usecols=[
            "center",
            "model",
            "case_id",
            "D1_Outpatient_Loop__judge_match_score_mean",
            "D2_Admission_Loop__judge_match_score_mean",
        ],
    )

    key_cols = ["center", "model", "case_id"]
    df = df_judge.merge(df_loop, on=key_cols, how="left", validate="one_to_one")

    rows: list[dict[str, object]] = []
    for rec in df.to_dict(orient="records"):
        base = {
            "center": str(rec.get("center")),
            "model": str(rec.get("model")),
            "case_id": str(rec.get("case_id")),
        }

        # Diagnosis pathway
        for stage, col in [
            ("D1_Decision", "gate1_dx_score"),
            ("D2_Decision", "gate2_revised_dx_score"),
            ("D3_Decision", "d3_dx_score"),
        ]:
            v = rec.get(col)
            if pd.notna(v):
                rows.append({**base, "pathway": "Diagnosis", "stage": stage, "value": float(v)})

        # Check pathway
        loop_d1 = rec.get("D1_Outpatient_Loop__judge_match_score_mean")
        if pd.notna(loop_d1):
            rows.append({**base, "pathway": "Check", "stage": "D1_Loop", "value": float(loop_d1)})
        check_score = rec.get("gate1_check_score")
        if pd.notna(check_score):
            rows.append({**base, "pathway": "Check", "stage": "D1_Decision_D2Check", "value": float(check_score)})
        loop_d2 = rec.get("D2_Admission_Loop__judge_match_score_mean")
        if pd.notna(loop_d2):
            rows.append({**base, "pathway": "Check", "stage": "D2_Loop", "value": float(loop_d2)})

        # Plan pathway
        for stage, col in [
            ("D2_Decision", "gate2_surgery_score"),
            ("D3_Decision", "d3_plan_score"),
        ]:
            v = rec.get(col)
            if pd.notna(v):
                rows.append({**base, "pathway": "Plan", "stage": stage, "value": float(v)})

        vals: list[float] = []
        for col in ["d4_rehab_score", "d4_followup_score"]:
            v = rec.get(col)
            if pd.notna(v):
                vals.append(float(v))
        if vals:
            rows.append({**base, "pathway": "Plan", "stage": "D4_Plan", "value": float(sum(vals) / len(vals))})

    detail_all = pd.DataFrame(rows)
    if detail_all.empty:
        raise RuntimeError("No rows extracted for judge score pathways")

    detail_all = _add_common_cols(detail_all)
    keys = list(
        zip(
            detail_all["center"].astype(str),
            detail_all["model"].astype(str),
            detail_all["case_id"].astype(str),
        )
    )
    detail_all["is_d1_anomaly"] = [k in d1_set for k in keys]
    detail_all["is_gate3_fail"] = [k in gate3_set for k in keys]

    excluded_d1 = detail_all[detail_all["is_d1_anomaly"]].copy()
    used = detail_all[~detail_all["is_d1_anomaly"]].copy()
    excluded_gate3_d4 = used[(used["stage"] == "D4_Plan") & (used["is_gate3_fail"])].copy()
    detail_used = used.drop(excluded_gate3_d4.index)

    summary_used = (
        detail_used.groupby(
            ["center", "model", "model_short", "pathway", "stage", "stage_cn"],
            as_index=False,
        )
        .agg(
            value_mean=("value", "mean"),
            n_cases=("case_id", "nunique"),
        )
        .sort_values(["center", "pathway", "stage", "model_short"], kind="mergesort")
    )

    out_path = OUT_DIR / "algorithmic_judge_score_pathways_source.xlsx"
    _write_xlsx(
        out_path,
        {
            "detail_all": detail_all,
            "detail_used": detail_used,
            "summary_used": summary_used,
            "excluded_d1_anomaly": excluded_d1,
            "excluded_gate3_d4": excluded_gate3_d4,
        },
        [
            {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
            {"key": "raw_file", "value": str(RAW_METRICS_SOURCE)},
            {"key": "raw_sheets", "value": "judge_scores_by_case + metrics_by_case"},
            {"key": "description", "value": "Algorithmic A5: Judge score pathways（Diagnosis/Check/Plan）"},
            {"key": "d1_anomaly_source", "value": "metrics_source_data.xlsx/d1_decision_anomalies"},
            {"key": "gate3_fail_source", "value": "医生评测汇总.xlsx/人工评分_D4Gate3不通过"},
            {"key": "detail_rows", "value": int(len(detail_all))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "excluded_gate3_d4_rows", "value": int(len(excluded_gate3_d4))},
            {"key": "used_rows", "value": int(len(detail_used))},
        ],
    )
    return out_path


def _extract_judge_scores_stagewise(
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
) -> Path:
    rounds = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="check_rounds")
    judge = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="judge_scores_by_case")
    if rounds.empty or judge.empty:
        raise RuntimeError("metrics_source_data missing check_rounds or judge_scores_by_case")

    loop = rounds.copy()
    loop["judge_composite_score_raw"] = pd.to_numeric(loop.get("judge_composite_score_raw"), errors="coerce")
    loop_case = (
        loop.groupby(["center", "model", "case_id", "stage"], as_index=False)
        .agg(judge_overall_score=("judge_composite_score_raw", "mean"))
    )
    stage_map = {
        "D1_Outpatient_Loop": "D1_Loop",
        "D2_Admission_Loop": "D2_Loop",
    }
    loop_case["stage"] = loop_case["stage"].map(stage_map)
    loop_case = loop_case[loop_case["stage"].notna()].copy()

    dec_map = {
        "D1_Decision": "gate1_overall_score",
        "D2_Decision": "gate2_overall_score",
        "D3_Decision": "d3_overall_score",
        "D4_Plan": "d4_overall_score",
    }
    dec_rows: list[pd.DataFrame] = []
    for stage, col in dec_map.items():
        if col not in judge.columns:
            continue
        sub = judge[["center", "model", "case_id", col]].copy()
        sub[col] = pd.to_numeric(sub[col], errors="coerce")
        sub = sub.rename(columns={col: "judge_overall_score"})
        sub["stage"] = stage
        dec_rows.append(sub[["center", "model", "case_id", "stage", "judge_overall_score"]])
    decision = pd.concat(dec_rows, ignore_index=True) if dec_rows else pd.DataFrame()

    detail_all = pd.concat(
        [
            loop_case[["center", "model", "case_id", "stage", "judge_overall_score"]],
            decision,
        ],
        ignore_index=True,
    )
    detail_all = detail_all.dropna(subset=["judge_overall_score"]).copy()
    if detail_all.empty:
        raise RuntimeError("No rows extracted for algorithmic judge scores stagewise")

    detail_all = _add_common_cols(detail_all)
    keys = list(
        zip(
            detail_all["center"].astype(str),
            detail_all["model"].astype(str),
            detail_all["case_id"].astype(str),
        )
    )
    detail_all["is_d1_anomaly"] = [k in d1_set for k in keys]
    detail_all["is_gate3_fail"] = [k in gate3_set for k in keys]

    excluded_d1 = detail_all[detail_all["is_d1_anomaly"]].copy()
    used = detail_all[~detail_all["is_d1_anomaly"]].copy()
    excluded_gate3_d4 = used[(used["stage"] == "D4_Plan") & (used["is_gate3_fail"])].copy()
    detail_used = used.drop(excluded_gate3_d4.index)

    summary_used = (
        detail_used.groupby(["center", "model", "model_short", "stage", "stage_cn"], as_index=False)
        .agg(
            judge_overall_score_mean=("judge_overall_score", "mean"),
            n_cases=("case_id", "nunique"),
        )
        .sort_values(["center", "stage", "model_short"], kind="mergesort")
    )

    out_path = OUT_DIR / "algorithmic_judge_scores_stagewise_source.xlsx"
    _write_xlsx(
        out_path,
        {
            "detail_all": detail_all,
            "detail_used": detail_used,
            "summary_used": summary_used,
            "excluded_d1_anomaly": excluded_d1,
            "excluded_gate3_d4": excluded_gate3_d4,
        },
        [
            {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
            {"key": "raw_file", "value": str(RAW_METRICS_SOURCE)},
            {"key": "raw_sheets", "value": "check_rounds + judge_scores_by_case"},
            {"key": "description", "value": "Algorithmic A6: 6阶段 Judge Overall Score（Loop + Decision）"},
            {"key": "d1_anomaly_source", "value": "metrics_source_data.xlsx/d1_decision_anomalies"},
            {"key": "gate3_fail_source", "value": "医生评测汇总.xlsx/人工评分_D4Gate3不通过"},
            {"key": "detail_rows", "value": int(len(detail_all))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "excluded_gate3_d4_rows", "value": int(len(excluded_gate3_d4))},
            {"key": "used_rows", "value": int(len(detail_used))},
        ],
    )
    return out_path


def _extract_loop_inefficiency_stagewise(d1_set: set[tuple[str, str, str]]) -> Path:
    rounds = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="check_rounds")
    if rounds.empty:
        raise RuntimeError("metrics_source_data missing check_rounds")

    loop = rounds.copy()
    loop["inefficient_round_by_zero"] = pd.to_numeric(loop.get("inefficient_round_by_zero"), errors="coerce")
    loop_case = (
        loop.groupby(["center", "model", "case_id", "stage"], as_index=False)
        .agg(loop_inefficiency_0_match=("inefficient_round_by_zero", "mean"))
    )
    stage_map = {
        "D1_Outpatient_Loop": "D1_Loop",
        "D2_Admission_Loop": "D2_Loop",
    }
    loop_case["stage"] = loop_case["stage"].map(stage_map)
    detail_all = loop_case[loop_case["stage"].notna()].copy()
    detail_all = detail_all.dropna(subset=["loop_inefficiency_0_match"]).copy()
    if detail_all.empty:
        raise RuntimeError("No rows extracted for algorithmic loop inefficiency stagewise")

    detail_all = _add_common_cols(detail_all)
    keys = list(
        zip(
            detail_all["center"].astype(str),
            detail_all["model"].astype(str),
            detail_all["case_id"].astype(str),
        )
    )
    detail_all["is_d1_anomaly"] = [k in d1_set for k in keys]
    detail_all["is_gate3_fail"] = False

    excluded_d1 = detail_all[detail_all["is_d1_anomaly"]].copy()
    detail_used = detail_all[~detail_all["is_d1_anomaly"]].copy()

    summary_used = (
        detail_used.groupby(["center", "model", "model_short", "stage", "stage_cn"], as_index=False)
        .agg(
            loop_inefficiency_0_match_mean=("loop_inefficiency_0_match", "mean"),
            n_cases=("case_id", "nunique"),
        )
        .sort_values(["center", "stage", "model_short"], kind="mergesort")
    )

    out_path = OUT_DIR / "algorithmic_loop_inefficiency_stagewise_source.xlsx"
    _write_xlsx(
        out_path,
        {
            "detail_all": detail_all,
            "detail_used": detail_used,
            "summary_used": summary_used,
            "excluded_d1_anomaly": excluded_d1,
        },
        [
            {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
            {"key": "raw_file", "value": str(RAW_METRICS_SOURCE)},
            {"key": "raw_sheet", "value": "check_rounds"},
            {"key": "description", "value": "Algorithmic A7: Loop无效率（0-match）按阶段"},
            {"key": "d1_anomaly_source", "value": "metrics_source_data.xlsx/d1_decision_anomalies"},
            {"key": "detail_rows", "value": int(len(detail_all))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "used_rows", "value": int(len(detail_used))},
        ],
    )
    return out_path


def _extract_stage_no_exit_rate(
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
) -> Path:
    df = pd.read_excel(RAW_DOCTOR_SUMMARY, sheet_name="通过退出明细")
    df = df.rename(columns={"中心": "center", "模型名称": "model", "病例ID": "case_id"})
    stage_cols = ["D1_Loop", "D1_Decision", "D2_Loop", "D2_Decision", "D3_Decision", "D4_Plan"]
    for col in stage_cols:
        if col not in df.columns:
            df[col] = ""

    base = df[["center", "model", "case_id"] + stage_cols].copy()
    base = _add_common_cols(base, stage_col=None)
    keys = list(
        zip(
            base["center"].astype(str),
            base["model"].astype(str),
            base["case_id"].astype(str),
        )
    )
    base["is_d1_anomaly"] = [k in d1_set for k in keys]
    base["is_gate3_fail"] = [k in gate3_set for k in keys]

    excluded_d1 = base[base["is_d1_anomaly"]].copy()
    used_wide = base[~base["is_d1_anomaly"]].copy()

    exit_tokens = ["退出", "不通过", "失败", "终止", "特殊"]
    long_rows: list[dict[str, object]] = []
    for rec in used_wide.to_dict(orient="records"):
        center = rec.get("center")
        model = rec.get("model")
        case_id = rec.get("case_id")
        model_short = rec.get("model_short")
        is_gate3 = bool(rec.get("is_gate3_fail"))
        for stage in stage_cols:
            status = str(rec.get(stage) or "")
            reached = (status.strip() != "") and ("未经过" not in status)
            no_exit = reached
            for token in exit_tokens:
                if token in status:
                    no_exit = False
                    break
            long_rows.append(
                {
                    "center": center,
                    "model": model,
                    "model_short": model_short,
                    "case_id": case_id,
                    "stage": stage,
                    "stage_cn": STAGE6_RENAME.get(stage, stage),
                    "status_text": status,
                    "reached": bool(reached),
                    "no_exit": bool(no_exit),
                    "is_d1_anomaly": False,
                    "is_gate3_fail": is_gate3,
                }
            )

    detail_all = pd.DataFrame(long_rows)
    if detail_all.empty:
        raise RuntimeError("No rows extracted for stage no-exit rate")

    excluded_gate3_d4 = detail_all[(detail_all["stage"] == "D4_Plan") & (detail_all["is_gate3_fail"])].copy()
    detail_used = detail_all.drop(excluded_gate3_d4.index)

    summary_used = (
        detail_used.groupby(["center", "model", "model_short", "stage", "stage_cn"], as_index=False)
        .agg(
            n_cases=("case_id", "nunique"),
            n_reached=("reached", "sum"),
            n_no_exit=("no_exit", "sum"),
        )
        .sort_values(["center", "stage", "model_short"], kind="mergesort")
    )
    summary_used["no_exit_rate"] = summary_used.apply(
        lambda r: (float(r["n_no_exit"]) / float(r["n_cases"])) if float(r["n_cases"]) > 0 else pd.NA,
        axis=1,
    )

    out_path = OUT_DIR / "algorithmic_stage_no_exit_rate_source.xlsx"
    _write_xlsx(
        out_path,
        {
            "detail_all": detail_all,
            "detail_used": detail_used,
            "summary_used": summary_used,
            "excluded_d1_anomaly": excluded_d1,
            "excluded_gate3_d4": excluded_gate3_d4,
        },
        [
            {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
            {"key": "raw_file", "value": str(RAW_DOCTOR_SUMMARY)},
            {"key": "raw_sheet", "value": "通过退出明细"},
            {"key": "description", "value": "Algorithmic A8: 六阶段未发生退出比例（按病例/阶段）"},
            {"key": "d1_anomaly_source", "value": "metrics_source_data.xlsx/d1_decision_anomalies"},
            {"key": "gate3_fail_source", "value": "医生评测汇总.xlsx/人工评分_D4Gate3不通过"},
            {"key": "detail_used_rows", "value": int(len(detail_used))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "excluded_gate3_d4_rows", "value": int(len(excluded_gate3_d4))},
        ],
    )
    return out_path


def main() -> None:
    d1_set = _load_d1_anomaly_set()
    gate3_set = _load_gate3_fail_set()

    outputs = [
        _extract_check_match_rate(d1_set),
        _extract_loop_inefficiency(d1_set),
        _extract_stage_pass_rate(d1_set),
        _extract_judge_scores_by_stage(d1_set, gate3_set),
        _extract_judge_score_pathways(d1_set, gate3_set),
        _extract_judge_scores_stagewise(d1_set, gate3_set),
        _extract_loop_inefficiency_stagewise(d1_set),
        _extract_stage_no_exit_rate(d1_set, gate3_set),
    ]
    for out in outputs:
        print("WROTE", out)


if __name__ == "__main__":
    main()
