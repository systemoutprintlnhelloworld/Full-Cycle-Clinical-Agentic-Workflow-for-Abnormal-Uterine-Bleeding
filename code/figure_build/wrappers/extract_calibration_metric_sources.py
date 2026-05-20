"""Extract audit-friendly calibration metric source tables.

This wrapper rebuilds calibration metrics from plot source workbooks and enforces
project-level sample rules:
1) D1 anomaly cases do NOT participate in any calculations.
2) Gate3-fail cases do NOT contribute to D4 calculations.

Outputs (analysis_viz/data/derived/metrics/calibration):
- calibration_ece_stagewise_source.xlsx
- calibration_reliability_stagewise_source.xlsx
- calibration_bubble_check_stagewise_source.xlsx
- calibration_bubble_diagnosis_stagewise_source.xlsx
- calibration_bubble_plan_stagewise_source.xlsx
- calibration_line_check_stagewise_source.xlsx
- calibration_line_diagnosis_stagewise_source.xlsx
- calibration_line_plan_stagewise_source.xlsx
- calibration_line_overall_stagewise_source.xlsx
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]

RAW_DIR = ROOT / "analysis_viz" / "data" / "raw"
OUT_DIR = ROOT / "analysis_viz" / "data" / "derived" / "metrics" / "calibration"

RAW_METRICS_SOURCE = RAW_DIR / "metrics_source_data.xlsx"
RAW_DOCTOR_SUMMARY = RAW_DIR / "医生评测汇总.xlsx"

CAL_SOURCE_DIR = (
    ROOT
    / "analysis_viz"
    / "figures"
    / "variants"
    / "outputs_latest__calibration"
    / "source_data"
)

RAW_ECE_WORKBOOK = CAL_SOURCE_DIR / "calibration_ece_stagewise_source.xlsx"


MODEL_SHORT = {
    "deepseek-v3-1-think-250821": "deepseek-v3",
    "gpt-5-2025-08-07": "gpt-5",
    "gemini-2.5-pro": "gemini-2.5p",
    "grok-4": "grok-4",
    "claude-opus-4-1-20250805-thinking": "claude-4.1",
}

STAGE_RENAME = {
    "D1_Loop": "门诊检查",
    "D1_Decision": "门诊决策",
    "D2_Loop": "入院检查",
    "D2_Decision": "入院决策",
    "D3_Decision": "术后康复",
    "D4_Plan": "随访计划",
    "D4_Rehab_Plan": "随访计划",
}

D4_STAGE_SET = {"D4_Plan", "D4_Rehab_Plan"}


@dataclass(frozen=True)
class MetricSpec:
    metric_id: str
    metric_name: str
    output_file: str
    source_pattern: str
    source_category: str
    description: str


def _load_d1_anomaly_set() -> set[tuple[str, str, str]]:
    df = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="d1_decision_anomalies")
    return set(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))


def _load_gate3_fail_set() -> set[tuple[str, str, str]]:
    df = pd.read_excel(RAW_DOCTOR_SUMMARY, sheet_name="人工评分_D4Gate3不通过")
    df = df.rename(columns={"中心": "center", "模型名称": "model", "病例ID": "case_id"})
    return set(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))


def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame], meta_rows: list[dict[str, object]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = pd.DataFrame(meta_rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
        meta.to_excel(writer, sheet_name="meta", index=False)


def _read_sheet_by_index(path: Path, idx: int) -> pd.DataFrame:
    xl = pd.ExcelFile(path)
    if idx >= len(xl.sheet_names):
        raise ValueError(f"sheet index {idx} out of range for {path}")
    return pd.read_excel(path, sheet_name=xl.sheet_names[idx])


def _normalize_round_detail(df: pd.DataFrame, *, source_file: Path, source_category: str | None = None) -> pd.DataFrame:
    out = df.rename(
        columns={
            "Center": "center",
            "Model": "model",
            "CaseID": "case_id",
            "Stage": "stage",
            "Category": "category",
            "DetailType": "detail_type",
            "Round": "round",
            "Confidence": "confidence",
            "Accuracy": "accuracy",
            "DocSheet": "doc_sheet",
            "JudgeSheet": "judge_sheet",
            "ConfidenceSource": "confidence_source",
            "AccuracySource": "accuracy_source",
        }
    ).copy()

    for col in ["center", "model", "case_id", "stage"]:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].astype(str)

    if "category" not in out.columns:
        out["category"] = source_category or ""
    out["category"] = out["category"].astype(str).str.lower()

    if source_category:
        out = out[out["category"] == source_category.lower()].copy()

    if "detail_type" not in out.columns:
        out["detail_type"] = ""
    if "round" not in out.columns:
        out["round"] = pd.NA

    out["confidence"] = pd.to_numeric(out.get("confidence"), errors="coerce")
    out["accuracy"] = pd.to_numeric(out.get("accuracy"), errors="coerce")
    out["source_file"] = str(source_file)
    return out


def _add_common_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["model_short"] = out["model"].map(MODEL_SHORT).fillna(out["model"].astype(str))
    out["stage_cn"] = out["stage"].map(STAGE_RENAME).fillna(out["stage"].astype(str))
    return out


def _attach_rule_flags(
    detail_all: pd.DataFrame,
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    out = detail_all.copy()
    keys = list(zip(out["center"].astype(str), out["model"].astype(str), out["case_id"].astype(str)))
    out["is_d1_anomaly"] = [k in d1_set for k in keys]
    out["is_gate3_fail"] = [k in gate3_set for k in keys]

    excluded_d1 = out[out["is_d1_anomaly"]].copy()
    used = out[~out["is_d1_anomaly"]].copy()
    excluded_gate3_d4 = used[(used["stage"].astype(str).isin(D4_STAGE_SET)) & (used["is_gate3_fail"])].copy()
    detail_used = used.drop(excluded_gate3_d4.index)
    return out, excluded_d1, excluded_gate3_d4, detail_used


def _summary_from_detail_used(detail_used: pd.DataFrame) -> pd.DataFrame:
    if detail_used.empty:
        return pd.DataFrame(
            columns=[
                "center",
                "model",
                "model_short",
                "stage",
                "stage_cn",
                "category",
                "samples",
                "accuracy_mean",
                "confidence_mean",
                "ece_proxy_abs_error_mean",
                "overconfidence_rate",
            ]
        )
    out = detail_used.copy()
    out["abs_error"] = (out["confidence"] - out["accuracy"]).abs()
    out["is_overconfidence"] = out["confidence"] > out["accuracy"]
    summary = (
        out.groupby(["center", "model", "model_short", "stage", "stage_cn", "category"], as_index=False)
        .agg(
            samples=("case_id", "nunique"),
            accuracy_mean=("accuracy", "mean"),
            confidence_mean=("confidence", "mean"),
            ece_proxy_abs_error_mean=("abs_error", "mean"),
            overconfidence_rate=("is_overconfidence", "mean"),
        )
        .sort_values(["center", "category", "stage", "model_short"], kind="mergesort")
    )
    return summary


def _bin_summary_from_detail_used(detail_used: pd.DataFrame) -> pd.DataFrame:
    if detail_used.empty:
        return pd.DataFrame(
            columns=[
                "center",
                "model",
                "model_short",
                "stage",
                "stage_cn",
                "category",
                "bin",
                "conf",
                "acc",
                "n",
                "n_cases",
            ]
        )
    out = detail_used.copy()
    out["bin"] = pd.cut(out["confidence"], bins=np.linspace(0, 1, 11), include_lowest=True)
    bsum = (
        out.groupby(["center", "model", "model_short", "stage", "stage_cn", "category", "bin"], observed=True)
        .agg(
            conf=("confidence", "mean"),
            acc=("accuracy", "mean"),
            n=("case_id", "count"),
            n_cases=("case_id", "nunique"),
        )
        .reset_index()
        .sort_values(["center", "category", "stage", "model_short", "bin"], kind="mergesort")
    )
    bsum["bin"] = bsum["bin"].astype(str)
    return bsum


def _extract_case_bin_metric(
    spec: MetricSpec,
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
) -> Path:
    src_files = sorted(CAL_SOURCE_DIR.glob(spec.source_pattern))
    if not src_files:
        raise FileNotFoundError(f"No source_data matched pattern: {spec.source_pattern}")

    round_parts: list[pd.DataFrame] = []
    process_parts: list[pd.DataFrame] = []
    for path in src_files:
        detail_raw = _read_sheet_by_index(path, 2)
        detail_round = _normalize_round_detail(detail_raw, source_file=path, source_category=spec.source_category)
        if detail_round.empty:
            continue
        round_parts.append(detail_round)

        try:
            proc = _read_sheet_by_index(path, 3)
            proc = proc.copy()
            proc["source_file"] = str(path)
            process_parts.append(proc)
        except Exception:
            pass

    if not round_parts:
        raise RuntimeError(f"No detail rows for {spec.metric_id}")

    detail_round_all = pd.concat(round_parts, ignore_index=True)

    # case-level points (same grain used by calibration bubble/line plotting)
    detail_all = (
        detail_round_all.groupby(["center", "model", "case_id", "stage", "category"], as_index=False)
        .agg(
            confidence=("confidence", "mean"),
            accuracy=("accuracy", "mean"),
            n_rounds=("round", "count"),
        )
    )
    detail_all = _add_common_cols(detail_all)

    detail_all, excluded_d1, excluded_gate3_d4, detail_used = _attach_rule_flags(detail_all, d1_set, gate3_set)

    summary_used = _summary_from_detail_used(detail_used)
    bin_summary_used = _bin_summary_from_detail_used(detail_used)
    raw_process_concat = pd.concat(process_parts, ignore_index=True) if process_parts else pd.DataFrame()

    out_path = OUT_DIR / spec.output_file
    _write_xlsx(
        out_path,
        {
            "detail_round_all": detail_round_all,
            "detail_all": detail_all,
            "detail_used": detail_used,
            "summary_used": summary_used,
            "bin_summary_used": bin_summary_used,
            "excluded_d1_anomaly": excluded_d1,
            "excluded_gate3_d4": excluded_gate3_d4,
            "raw_process_concat": raw_process_concat,
        },
        [
            {"key": "metric_id", "value": spec.metric_id},
            {"key": "metric_name", "value": spec.metric_name},
            {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
            {"key": "raw_source_pattern", "value": spec.source_pattern},
            {"key": "raw_source_files", "value": "|".join(str(p) for p in src_files)},
            {"key": "category", "value": spec.source_category},
            {"key": "description", "value": spec.description},
            {"key": "rule_d1", "value": "D1 anomaly cases excluded from calculations"},
            {"key": "rule_gate3_d4", "value": "Gate3 fail cases excluded from D4"},
            {"key": "detail_rows", "value": int(len(detail_all))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "excluded_gate3_d4_rows", "value": int(len(excluded_gate3_d4))},
            {"key": "used_rows", "value": int(len(detail_used))},
        ],
    )
    return out_path


def _extract_ece(
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
) -> Path:
    if not RAW_ECE_WORKBOOK.exists():
        raise FileNotFoundError(str(RAW_ECE_WORKBOOK))

    detail = _read_sheet_by_index(RAW_ECE_WORKBOOK, 2)
    summary = _read_sheet_by_index(RAW_ECE_WORKBOOK, 4)

    detail = _normalize_round_detail(detail, source_file=RAW_ECE_WORKBOOK, source_category="overall")

    # case-level points
    detail_all = (
        detail.groupby(["center", "model", "case_id", "stage", "category"], as_index=False)
        .agg(
            confidence=("confidence", "mean"),
            accuracy=("accuracy", "mean"),
            n_rounds=("round", "count"),
        )
    )
    detail_all = _add_common_cols(detail_all)

    detail_all, excluded_d1, excluded_gate3_d4, detail_used = _attach_rule_flags(detail_all, d1_set, gate3_set)
    summary_used = _summary_from_detail_used(detail_used)
    bin_summary_used = _bin_summary_from_detail_used(detail_used)

    out_path = OUT_DIR / "calibration_ece_stagewise_source.xlsx"
    _write_xlsx(
        out_path,
        {
            "detail_all": detail_all,
            "detail_used": detail_used,
            "summary_used": summary_used,
            "bin_summary_used": bin_summary_used,
            "excluded_d1_anomaly": excluded_d1,
            "excluded_gate3_d4": excluded_gate3_d4,
            "raw_summary_plot": summary,
        },
        [
            {"key": "metric_id", "value": "calibration_ece_stagewise"},
            {"key": "metric_name", "value": "Calibration ECE stagewise（可审计）"},
            {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
            {"key": "raw_file", "value": str(RAW_ECE_WORKBOOK)},
            {"key": "raw_detail_sheet", "value": "sheet_index_2"},
            {"key": "raw_summary_sheet", "value": "sheet_index_4"},
            {"key": "description", "value": "Calibration: ECE stagewise (audit-friendly, category=overall)"},
            {"key": "rule_d1", "value": "D1 anomaly cases excluded from calculations"},
            {"key": "rule_gate3_d4", "value": "Gate3 fail cases excluded from D4"},
            {"key": "detail_rows", "value": int(len(detail_all))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "excluded_gate3_d4_rows", "value": int(len(excluded_gate3_d4))},
            {"key": "used_rows", "value": int(len(detail_used))},
        ],
    )
    return out_path


def main() -> None:
    d1_set = _load_d1_anomaly_set()
    gate3_set = _load_gate3_fail_set()

    out_paths: list[Path] = []
    out_paths.append(_extract_ece(d1_set, gate3_set))

    specs = [
        MetricSpec(
            metric_id="calibration_reliability_stagewise",
            metric_name="Calibration reliability stagewise（overall）",
            output_file="calibration_reliability_stagewise_source.xlsx",
            source_pattern="calibration_reliability_stagewise_*_source.xlsx",
            source_category="overall",
            description="Overall 6-stage calibration bubbles / reliability",
        ),
        MetricSpec(
            metric_id="calibration_bubble_check_stagewise",
            metric_name="Calibration bubble check stagewise",
            output_file="calibration_bubble_check_stagewise_source.xlsx",
            source_pattern="calibration_bubble_check_stagewise_*_source.xlsx",
            source_category="check",
            description="Calibration bubble by stage (check category)",
        ),
        MetricSpec(
            metric_id="calibration_bubble_diagnosis_stagewise",
            metric_name="Calibration bubble diagnosis stagewise",
            output_file="calibration_bubble_diagnosis_stagewise_source.xlsx",
            source_pattern="calibration_bubble_diagnosis_stagewise_*_source.xlsx",
            source_category="diagnosis",
            description="Calibration bubble by stage (diagnosis category)",
        ),
        MetricSpec(
            metric_id="calibration_bubble_plan_stagewise",
            metric_name="Calibration bubble plan stagewise",
            output_file="calibration_bubble_plan_stagewise_source.xlsx",
            source_pattern="calibration_bubble_plan_stagewise_*_source.xlsx",
            source_category="plan",
            description="Calibration bubble by stage (plan category)",
        ),
        MetricSpec(
            metric_id="calibration_line_overall_stagewise",
            metric_name="Calibration line overall stagewise",
            output_file="calibration_line_overall_stagewise_source.xlsx",
            source_pattern="calibration_reliability_stagewise_*_source.xlsx",
            source_category="overall",
            description="Calibration line by stage (overall category)",
        ),
        MetricSpec(
            metric_id="calibration_line_check_stagewise",
            metric_name="Calibration line check stagewise",
            output_file="calibration_line_check_stagewise_source.xlsx",
            source_pattern="calibration_bubble_check_stagewise_*_source.xlsx",
            source_category="check",
            description="Calibration line by stage (check category)",
        ),
        MetricSpec(
            metric_id="calibration_line_diagnosis_stagewise",
            metric_name="Calibration line diagnosis stagewise",
            output_file="calibration_line_diagnosis_stagewise_source.xlsx",
            source_pattern="calibration_bubble_diagnosis_stagewise_*_source.xlsx",
            source_category="diagnosis",
            description="Calibration line by stage (diagnosis category)",
        ),
        MetricSpec(
            metric_id="calibration_line_plan_stagewise",
            metric_name="Calibration line plan stagewise",
            output_file="calibration_line_plan_stagewise_source.xlsx",
            source_pattern="calibration_bubble_plan_stagewise_*_source.xlsx",
            source_category="plan",
            description="Calibration line by stage (plan category)",
        ),
    ]

    for spec in specs:
        out_paths.append(_extract_case_bin_metric(spec, d1_set, gate3_set))

    for p in out_paths:
        print("WROTE", p)


if __name__ == "__main__":
    main()

