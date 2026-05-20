"""Extract audit-friendly manual (doctor) metric source tables.

Raw doctor scoring files live under:
- analysis_viz/data/raw/doctor_eval_results/<doctor>/<center>*.xlsx

The existing aggregated table `analysis_viz/data/raw/医生评测汇总.xlsx` is useful,
but for observability we also keep case-level manual scoring detail.

Mandatory sample rules
----------------------
1) D1 anomaly cases do NOT participate in any calculations.
2) Gate3-fail cases do NOT contribute to D4 calculations.

Outputs
-------
- analysis_viz/data/derived/metrics/manual/manual_result_quality_source.xlsx
- analysis_viz/data/derived/metrics/manual/manual_reasoning_quality_source.xlsx
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]

RAW_DIR = ROOT / "analysis_viz" / "data" / "raw"
RAW_DOCTOR_DIR = RAW_DIR / "doctor_eval_results"

OUT_DIR = ROOT / "analysis_viz" / "data" / "derived" / "metrics" / "manual"

RAW_METRICS_SOURCE = RAW_DIR / "metrics_source_data.xlsx"
RAW_DOCTOR_SUMMARY = RAW_DIR / "医生评测汇总.xlsx"


MODEL_SHORT = {
    "deepseek-v3-1-think-250821": "deepseek-v3",
    "gpt-5-2025-08-07": "gpt-5",
    "gemini-2.5-pro": "gemini-2.5p",
    "grok-4": "grok-4",
    "claude-opus-4-1-20250805-thinking": "claude-4.1",
}


STAGE_PREFIX_TO_CODE = {
    "门诊A": "D1_Loop",
    "门诊B": "D1_Decision",
    "住院A": "D2_Loop",
    "住院B": "D2_Decision",
    "术后": "D3_Decision",
    "康复": "D4_Plan",
}


STAGE6_RENAME = {
    "D1_Loop": "门诊检查",
    "D1_Decision": "门诊决策",
    "D2_Loop": "入院检查",
    "D2_Decision": "入院决策",
    "D3_Decision": "术后康复",
    "D4_Plan": "随访计划",
}


def _load_d1_anomaly_set() -> set[tuple[str, str, str]]:
    df = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="d1_decision_anomalies")
    return set(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))


def _load_gate3_fail_set() -> set[tuple[str, str, str]]:
    df = pd.read_excel(RAW_DOCTOR_SUMMARY, sheet_name="人工评分_D4Gate3不通过")
    df = df.rename(columns={"中心": "center", "模型名称": "model", "病例ID": "case_id"})
    return set(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))


def _iter_doctor_workbooks() -> list[tuple[str, str, Path]]:
    if not RAW_DOCTOR_DIR.exists():
        return []
    out: list[tuple[str, str, Path]] = []
    for doctor_dir in sorted(p for p in RAW_DOCTOR_DIR.iterdir() if p.is_dir()):
        doctor = doctor_dir.name
        for xlsx in sorted(doctor_dir.glob("*.xlsx")):
            center = xlsx.stem.split("-", 1)[0]
            out.append((doctor, center, xlsx))
    return out


def _load_scoring_coverage(doctor: str, center: str, path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="评分覆盖率")
    df = df.rename(columns={"病例ID": "case_id", "模型名称": "model", "中心": "center"})
    if "center" not in df.columns:
        df["center"] = center
    df["doctor"] = doctor
    df["source_file"] = str(path)
    return df


def _normalize_long(df_cov: pd.DataFrame) -> pd.DataFrame:
    base_cols = ["doctor", "center", "model", "case_id", "source_file"]
    for col in base_cols:
        if col not in df_cov.columns:
            df_cov[col] = ""

    rows: list[dict[str, object]] = []
    for prefix, stage in STAGE_PREFIX_TO_CODE.items():
        status_col = f"{prefix}_状态"
        reasoning_col = f"{prefix}_推理合理性"
        result_col = f"{prefix}_结果质量评分"
        if status_col not in df_cov.columns:
            continue
        if reasoning_col not in df_cov.columns:
            df_cov[reasoning_col] = pd.NA
        if result_col not in df_cov.columns:
            df_cov[result_col] = pd.NA

        sub = df_cov[base_cols + [status_col, reasoning_col, result_col]].copy()
        sub = sub.rename(
            columns={
                status_col: "status",
                reasoning_col: "reasoning_score_0_5",
                result_col: "result_score_0_5",
            }
        )
        sub["stage"] = stage
        rows.extend(sub.to_dict(orient="records"))

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["model_short"] = out["model"].map(MODEL_SHORT).fillna(out["model"].astype(str))
    out["stage_cn"] = out["stage"].map(STAGE6_RENAME).fillna(out["stage"].astype(str))
    out["reasoning_score_0_5"] = pd.to_numeric(out["reasoning_score_0_5"], errors="coerce")
    out["result_score_0_5"] = pd.to_numeric(out["result_score_0_5"], errors="coerce")
    return out


def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame], meta_rows: list[dict[str, object]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = pd.DataFrame(meta_rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
        meta.to_excel(writer, sheet_name="meta", index=False)


def _build_metric_workbook(
    *,
    metric_id: str,
    metric_name: str,
    score_col: str,
    df_long: pd.DataFrame,
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
    out_path: Path,
) -> None:
    if df_long.empty:
        raise RuntimeError("No manual scoring rows loaded")

    detail_all = df_long[[
        "doctor",
        "center",
        "model",
        "model_short",
        "case_id",
        "stage",
        "stage_cn",
        "status",
        score_col,
        "source_file",
    ]].copy()
    detail_all = detail_all.rename(columns={score_col: "score_0_5"})

    keys = list(zip(detail_all["center"].astype(str), detail_all["model"].astype(str), detail_all["case_id"].astype(str)))
    detail_all["is_d1_anomaly"] = [k in d1_set for k in keys]
    detail_all["is_gate3_fail"] = [k in gate3_set for k in keys]

    # used: numeric score, not D1 anomaly, and for Gate3-fail exclude D4 only
    detail_all["score_0_5"] = pd.to_numeric(detail_all["score_0_5"], errors="coerce")
    excluded_d1 = detail_all[detail_all["is_d1_anomaly"]].copy()
    used = detail_all[~detail_all["is_d1_anomaly"]].copy()
    excluded_gate3_d4 = used[(used["stage"] == "D4_Plan") & (used["is_gate3_fail"])].copy()
    used = used.drop(excluded_gate3_d4.index)

    detail_used = used.dropna(subset=["score_0_5"]).copy()
    summary_used = (
        detail_used.groupby(["center", "model", "model_short", "stage", "stage_cn"], as_index=False)
        .agg(
            score_0_5_mean=("score_0_5", "mean"),
            n_cases=("case_id", "nunique"),
            n_doctors=("doctor", "nunique"),
        )
        .sort_values(["center", "stage", "model_short"], kind="mergesort")
    )

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
            {"key": "metric_id", "value": metric_id},
            {"key": "metric_name", "value": metric_name},
            {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
            {"key": "raw_source", "value": str(RAW_DOCTOR_DIR)},
            {"key": "raw_dir", "value": str(RAW_DOCTOR_DIR)},
            {"key": "raw_sheet", "value": "评分覆盖率"},
            {"key": "rule_d1", "value": "D1 anomaly cases excluded from calculations"},
            {"key": "rule_gate3_d4", "value": "Gate3 fail cases excluded from D4"},
            {"key": "detail_rows", "value": int(len(detail_all))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "excluded_gate3_d4_rows", "value": int(len(excluded_gate3_d4))},
            {"key": "used_rows", "value": int(len(detail_used))},
        ],
    )


def main() -> None:
    d1_set = _load_d1_anomaly_set()
    gate3_set = _load_gate3_fail_set()

    cov_parts: list[pd.DataFrame] = []
    for doctor, center, path in _iter_doctor_workbooks():
        try:
            cov_parts.append(_load_scoring_coverage(doctor, center, path))
        except Exception:
            continue
    if not cov_parts:
        raise RuntimeError(f"No doctor workbooks loaded from {RAW_DOCTOR_DIR}")

    cov = pd.concat(cov_parts, ignore_index=True)
    df_long = _normalize_long(cov)
    if df_long.empty:
        raise RuntimeError("No long-form manual rows")

    _build_metric_workbook(
        metric_id="manual_result_quality",
        metric_name="人工结果质量（0-5）",
        score_col="result_score_0_5",
        df_long=df_long,
        d1_set=d1_set,
        gate3_set=gate3_set,
        out_path=OUT_DIR / "manual_result_quality_source.xlsx",
    )
    print("WROTE", OUT_DIR / "manual_result_quality_source.xlsx")

    _build_metric_workbook(
        metric_id="manual_reasoning_quality",
        metric_name="人工推理合理性（0-5）",
        score_col="reasoning_score_0_5",
        df_long=df_long,
        d1_set=d1_set,
        gate3_set=gate3_set,
        out_path=OUT_DIR / "manual_reasoning_quality_source.xlsx",
    )
    print("WROTE", OUT_DIR / "manual_reasoning_quality_source.xlsx")


if __name__ == "__main__":
    main()

