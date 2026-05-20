"""Extract audit-friendly algorithmic (machine) figdata for paper figures.

Background
----------
Paper Fig3* uses algorithmic loop metrics that originally lived in historical
`outputs/archive/*/figures/*` source_data workbooks.

To improve observability and to enforce mandatory sample rules, we re-extract a
minimal, analysis-friendly data source from the *canonical* machine metrics table:

- analysis_viz/data/raw/metrics_source_data.xlsx

Mandatory sample rules
----------------------
1) D1 anomaly cases do NOT participate in any calculations.
   Source: metrics_source_data.xlsx / d1_decision_anomalies.
2) Gate3-fail => D4 exclusion rule is NOT relevant for Fig3 (only D1/D2 loop).

Outputs
-------
- analysis_viz/data/derived/figdata/paper/Fig3__check_match_rate_source.xlsx
  - detail_all / detail_used / summary_used / excluded_d1_anomaly / meta
- analysis_viz/data/derived/figdata/paper/Fig3__loop_inefficiency_source.xlsx
  - detail_all / detail_used / summary_used / excluded_d1_anomaly / meta

Both workbooks include:
- stage_cn (统一六环节命名中的“门诊检查/入院检查”)
- model_short (deepseek-v3 / gpt-5 / gemini-2.5p / grok-4 / claude-4.1)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]

RAW_METRICS_SOURCE = ROOT / "analysis_viz" / "data" / "raw" / "metrics_source_data.xlsx"

OUT_DIR = ROOT / "analysis_viz" / "data" / "derived" / "figdata" / "paper"


MODEL_SHORT = {
    "deepseek-v3-1-think-250821": "deepseek-v3",
    "gpt-5-2025-08-07": "gpt-5",
    "gemini-2.5-pro": "gemini-2.5p",
    "grok-4": "grok-4",
    "claude-opus-4-1-20250805-thinking": "claude-4.1",
}


STAGE_LOOP_RENAME = {
    "D1_Loop": "门诊检查",
    "D2_Loop": "入院检查",
}


def _load_d1_anomaly_set() -> set[tuple[str, str, str]]:
    df = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="d1_decision_anomalies")
    return set(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))


def _add_common_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["model_short"] = df["model"].map(MODEL_SHORT).fillna(df["model"].astype(str))
    df["stage_cn"] = df["stage"].map(STAGE_LOOP_RENAME).fillna(df["stage"].astype(str))
    return df


def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame], meta_rows: list[dict[str, object]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = pd.DataFrame(meta_rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
        meta.to_excel(writer, sheet_name="meta", index=False)


def _extract_check_match(d1_set: set[tuple[str, str, str]]) -> Path:
    usecols = [
        "center",
        "model",
        "case_id",
        "D1_Outpatient_Loop__judge_match_score_mean",
        "D1_Outpatient_Loop__judge_reasonable_score_mean",
        "D2_Admission_Loop__judge_match_score_mean",
        "D2_Admission_Loop__judge_reasonable_score_mean",
    ]
    df_case = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="metrics_by_case", usecols=usecols)

    rows: list[dict[str, object]] = []
    for rec in df_case.to_dict(orient="records"):
        base = {
            "center": rec.get("center"),
            "model": rec.get("model"),
            "case_id": rec.get("case_id"),
        }
        d1_match = rec.get("D1_Outpatient_Loop__judge_match_score_mean")
        d1_reasonable = rec.get("D1_Outpatient_Loop__judge_reasonable_score_mean")
        if pd.notna(d1_match) or pd.notna(d1_reasonable):
            rows.append(
                {
                    **base,
                    "stage": "D1_Loop",
                    "check_match_degree": d1_match,
                    "check_reasonable": d1_reasonable,
                }
            )

        d2_match = rec.get("D2_Admission_Loop__judge_match_score_mean")
        d2_reasonable = rec.get("D2_Admission_Loop__judge_reasonable_score_mean")
        if pd.notna(d2_match) or pd.notna(d2_reasonable):
            rows.append(
                {
                    **base,
                    "stage": "D2_Loop",
                    "check_match_degree": d2_match,
                    "check_reasonable": d2_reasonable,
                }
            )

    detail_all = pd.DataFrame(rows)
    if detail_all.empty:
        raise RuntimeError("No rows extracted for check match degree")

    detail_all = _add_common_cols(detail_all)
    keys = list(zip(detail_all["center"].astype(str), detail_all["model"].astype(str), detail_all["case_id"].astype(str)))
    detail_all["is_d1_anomaly"] = [k in d1_set for k in keys]

    excluded = detail_all[detail_all["is_d1_anomaly"]].copy()
    detail_used = detail_all[~detail_all["is_d1_anomaly"]].copy()

    summary_used = (
        detail_used.groupby(["center", "model", "model_short", "stage", "stage_cn"], dropna=False)
        .agg(
            check_match_degree_mean=("check_match_degree", "mean"),
            check_reasonable_mean=("check_reasonable", "mean"),
            n_cases=("case_id", "nunique"),
        )
        .reset_index()
        .sort_values(["center", "stage", "model_short"], kind="stable")
    )

    out_path = OUT_DIR / "Fig3__check_match_rate_source.xlsx"
    meta_rows = [
        {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
        {"key": "raw_source", "value": str(RAW_METRICS_SOURCE)},
        {"key": "raw_sheet", "value": "metrics_by_case"},
        {
            "key": "description",
            "value": "Fig3 检查匹配度/合理性：从 metrics_source_data.xlsx 提取病例级指标，并汇总用于绘图。",
        },
        {"key": "rule_d1", "value": "D1 anomaly cases excluded from calculations"},
        {"key": "detail_all_rows", "value": int(len(detail_all))},
        {"key": "excluded_d1_rows", "value": int(len(excluded))},
        {"key": "detail_used_rows", "value": int(len(detail_used))},
    ]

    _write_xlsx(
        out_path,
        {
            "detail_all": detail_all,
            "detail_used": detail_used,
            "summary_used": summary_used,
            "excluded_d1_anomaly": excluded,
        },
        meta_rows,
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
            "center": rec.get("center"),
            "model": rec.get("model"),
            "case_id": rec.get("case_id"),
        }
        d1_val = rec.get("d1_inefficiency_by_zero")
        if pd.notna(d1_val):
            rows.append({**base, "stage": "D1_Loop", "loop_inefficiency_0_match": d1_val})
        d2_val = rec.get("d2_inefficiency_by_zero")
        if pd.notna(d2_val):
            rows.append({**base, "stage": "D2_Loop", "loop_inefficiency_0_match": d2_val})

    detail_all = pd.DataFrame(rows)
    if detail_all.empty:
        raise RuntimeError("No rows extracted for loop inefficiency")
    detail_all = _add_common_cols(detail_all)
    keys = list(zip(detail_all["center"].astype(str), detail_all["model"].astype(str), detail_all["case_id"].astype(str)))
    detail_all["is_d1_anomaly"] = [k in d1_set for k in keys]

    excluded = detail_all[detail_all["is_d1_anomaly"]].copy()
    detail_used = detail_all[~detail_all["is_d1_anomaly"]].copy()

    summary_used = (
        detail_used.groupby(["center", "model", "model_short", "stage", "stage_cn"], dropna=False)
        .agg(
            loop_inefficiency_0_match_mean=("loop_inefficiency_0_match", "mean"),
            n_cases=("case_id", "nunique"),
        )
        .reset_index()
        .sort_values(["center", "stage", "model_short"], kind="stable")
    )

    out_path = OUT_DIR / "Fig3__loop_inefficiency_source.xlsx"
    meta_rows = [
        {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
        {"key": "raw_source", "value": str(RAW_METRICS_SOURCE)},
        {"key": "raw_sheet", "value": "metrics_by_case"},
        {
            "key": "description",
            "value": "Fig3 无效循环率(0匹配)：从 metrics_source_data.xlsx 提取病例级指标，并汇总用于绘图。",
        },
        {"key": "rule_d1", "value": "D1 anomaly cases excluded from calculations"},
        {"key": "detail_all_rows", "value": int(len(detail_all))},
        {"key": "excluded_d1_rows", "value": int(len(excluded))},
        {"key": "detail_used_rows", "value": int(len(detail_used))},
    ]

    _write_xlsx(
        out_path,
        {
            "detail_all": detail_all,
            "detail_used": detail_used,
            "summary_used": summary_used,
            "excluded_d1_anomaly": excluded,
        },
        meta_rows,
    )
    return out_path


def main() -> None:
    d1_set = _load_d1_anomaly_set()
    out_check = _extract_check_match(d1_set)
    out_loop = _extract_loop_inefficiency(d1_set)
    print("WROTE", out_check)
    print("WROTE", out_loop)


if __name__ == "__main__":
    main()

