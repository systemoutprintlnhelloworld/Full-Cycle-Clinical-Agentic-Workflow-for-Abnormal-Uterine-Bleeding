"""Extract analysis-friendly LLM metric source tables.

Goal
----
The raw xlsx files under `analysis_viz/data/raw/` contain long prompt/context fields
that are not needed for plotting. This script extracts *minimal* detail+summary
tables to `analysis_viz/data/derived/metrics/`.

Mandatory sample rules
----------------------
1) D1 anomaly cases are excluded from *all* calculations.
   Source: `analysis_viz/data/raw/metrics_source_data.xlsx` / `d1_decision_anomalies`.
2) If D3 Gate3 fails, then D4 does not participate in any calculations.
   Source: `analysis_viz/data/raw/医生评测汇总.xlsx` / `人工评分_D4Gate3不通过`.

Outputs
-------
- analysis_viz/data/derived/metrics/llm_reasoning_source.xlsx
- analysis_viz/data/derived/metrics/llm_consistency_source.xlsx
- analysis_viz/data/derived/metrics/llm_memory_source.xlsx

Each workbook includes:
- detail_all / detail_used
- summary_used
- excluded_* (audit)
- meta
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "analysis_viz" / "data" / "raw"
OUT_DIR = ROOT / "analysis_viz" / "data" / "derived" / "metrics"

RAW_METRICS_SOURCE = RAW_DIR / "metrics_source_data.xlsx"
RAW_DOCTOR_SUMMARY = RAW_DIR / "医生评测汇总.xlsx"

RAW_LLM_REASONING = RAW_DIR / "llm_reasoning_gemini-2.5-pro__gala_api.xlsx"
RAW_LLM_CONSISTENCY = RAW_DIR / "llm_consistency_gemini-2.5-pro__gala_api.xlsx"
RAW_LLM_MEMORY = RAW_DIR / "llm_memory_gemini-2.5-pro__gala_api.xlsx"


MODEL_SHORT = {
    "deepseek-v3-1-think-250821": "deepseek-v3",
    "gpt-5-2025-08-07": "gpt-5",
    "gemini-2.5-pro": "gemini-2.5p",
    "grok-4": "grok-4",
    "claude-opus-4-1-20250805-thinking": "claude-4.1",
}

STAGE6_RENAME = {
    "D1_Outpatient_Loop": "门诊检查",
    "D1_Outpatient_Decision": "门诊决策",
    "D2_Admission_Loop": "入院检查",
    "D2_Admission_Decision": "入院决策",
    "D3_Surgery_Decision": "术后康复",
    "D4_Rehab_Plan": "随访计划",
}

STAGE4_RENAME = {
    "D1": "门诊决策",
    "D2": "入院决策",
    "D3": "术后康复",
    "D4": "随访计划",
}


def _load_d1_anomaly_set() -> set[tuple[str, str, str]]:
    df = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="d1_decision_anomalies")
    return set(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))


def _load_gate3_fail_set() -> set[tuple[str, str, str]]:
    df = pd.read_excel(RAW_DOCTOR_SUMMARY, sheet_name="人工评分_D4Gate3不通过")
    df = df.rename(columns={"中心": "center", "模型名称": "model", "病例ID": "case_id"})
    return set(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))


def _add_common_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["model_short"] = df["model"].map(MODEL_SHORT).fillna(df["model"].astype(str))
    return df


def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame], meta_rows: list[dict[str, object]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = pd.DataFrame(meta_rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
        meta.to_excel(writer, sheet_name="meta", index=False)


def _extract_reasoning(d1_set: set[tuple[str, str, str]], gate3_set: set[tuple[str, str, str]]) -> None:
    detail = pd.read_excel(
        RAW_LLM_REASONING,
        sheet_name="推理质量-明细",
        usecols=["中心", "被评测模型", "病例ID", "阶段", "推理质量得分(0-1)", "错误标签(JSON)", "错误"],
    )
    detail = detail.rename(
        columns={
            "中心": "center",
            "被评测模型": "model",
            "病例ID": "case_id",
            "阶段": "stage",
            "推理质量得分(0-1)": "reasoning_score_0_1",
            "错误标签(JSON)": "error_tags_json",
            "错误": "error",
        }
    )
    detail = _add_common_cols(detail)
    detail["stage_cn"] = detail["stage"].map(STAGE6_RENAME).fillna(detail["stage"].astype(str))
    keys = list(zip(detail["center"].astype(str), detail["model"].astype(str), detail["case_id"].astype(str)))
    detail["is_d1_anomaly"] = [k in d1_set for k in keys]
    detail["is_gate3_fail"] = [k in gate3_set for k in keys]

    excluded_d1 = detail[detail["is_d1_anomaly"]].copy()
    used = detail[~detail["is_d1_anomaly"]].copy()
    excluded_gate3_d4 = used[(used["stage"] == "D4_Rehab_Plan") & (used["is_gate3_fail"])].copy()
    used = used.drop(excluded_gate3_d4.index)

    summary = (
        used.groupby(["center", "model", "model_short", "stage", "stage_cn"], as_index=False)
        .agg(
            reasoning_score_0_1_mean=("reasoning_score_0_1", "mean"),
            n_cases=("case_id", "nunique"),
        )
        .sort_values(["center", "model_short", "stage"], kind="mergesort")
    )

    _write_xlsx(
        OUT_DIR / "llm_reasoning_source.xlsx",
        {
            "detail_all": detail,
            "detail_used": used,
            "summary_used": summary,
            "excluded_d1_anomaly": excluded_d1,
            "excluded_gate3_d4": excluded_gate3_d4,
        },
        [
            {"key": "raw_file", "value": str(RAW_LLM_REASONING)},
            {"key": "d1_anomaly_source", "value": "metrics_source_data.xlsx/d1_decision_anomalies"},
            {"key": "gate3_fail_source", "value": "医生评测汇总.xlsx/人工评分_D4Gate3不通过"},
            {"key": "detail_rows", "value": int(len(detail))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "excluded_gate3_d4_rows", "value": int(len(excluded_gate3_d4))},
            {"key": "used_rows", "value": int(len(used))},
        ],
    )


def _extract_consistency(d1_set: set[tuple[str, str, str]], gate3_set: set[tuple[str, str, str]]) -> None:
    def _load(sheet: str) -> pd.DataFrame:
        wanted = {
            "中心",
            "被评测模型",
            "病例ID",
            "阶段",
            "一致性得分(0-1)",
            # Note: cross-stage sheet may not contain conflict/hallucination counts.
            "冲突条数",
            "幻觉条数",
        }
        df = pd.read_excel(
            RAW_LLM_CONSISTENCY,
            sheet_name=sheet,
            usecols=lambda c: c in wanted,
        )
        df = df.rename(
            columns={
                "中心": "center",
                "被评测模型": "model",
                "病例ID": "case_id",
                "阶段": "stage",
                "一致性得分(0-1)": "consistency_score_0_1",
                "冲突条数": "conflict_count",
                "幻觉条数": "hallucination_count",
            }
        )
        # Ensure columns exist for downstream summary.
        if "conflict_count" not in df.columns:
            df["conflict_count"] = pd.NA
        if "hallucination_count" not in df.columns:
            df["hallucination_count"] = pd.NA
        df = _add_common_cols(df)
        df["stage_cn"] = df["stage"].map(STAGE4_RENAME).fillna(df["stage"].astype(str))
        keys = list(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))
        df["is_d1_anomaly"] = [k in d1_set for k in keys]
        df["is_gate3_fail"] = [k in gate3_set for k in keys]
        return df

    fact = _load("一致性-事实-明细")
    cross = _load("一致性-跨阶段-明细")

    excluded_d1 = pd.concat([fact[fact["is_d1_anomaly"]], cross[cross["is_d1_anomaly"]]], ignore_index=True)

    def _apply(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        used = df[~df["is_d1_anomaly"]].copy()
        excluded_gate3_d4 = used[(used["stage"] == "D4") & (used["is_gate3_fail"])].copy()
        used = used.drop(excluded_gate3_d4.index)
        return used, excluded_gate3_d4

    fact_used, fact_ex_gate3 = _apply(fact)
    cross_used, cross_ex_gate3 = _apply(cross)
    excluded_gate3 = pd.concat([fact_ex_gate3, cross_ex_gate3], ignore_index=True)

    def _summary(df_used: pd.DataFrame, prefix: str) -> pd.DataFrame:
        out = (
            df_used.groupby(["center", "model", "model_short", "stage", "stage_cn"], as_index=False)
            .agg(
                consistency_score_0_1_mean=("consistency_score_0_1", "mean"),
                conflict_count_mean=("conflict_count", "mean"),
                hallucination_count_mean=("hallucination_count", "mean"),
                n_cases=("case_id", "nunique"),
            )
            .sort_values(["center", "model_short", "stage"], kind="mergesort")
        )
        out.insert(0, "metric", prefix)
        return out

    summary = pd.concat(
        [_summary(fact_used, "fact"), _summary(cross_used, "cross")], ignore_index=True
    )

    _write_xlsx(
        OUT_DIR / "llm_consistency_source.xlsx",
        {
            "fact_detail_all": fact,
            "fact_detail_used": fact_used,
            "cross_detail_all": cross,
            "cross_detail_used": cross_used,
            "summary_used": summary,
            "excluded_d1_anomaly": excluded_d1,
            "excluded_gate3_d4": excluded_gate3,
        },
        [
            {"key": "raw_file", "value": str(RAW_LLM_CONSISTENCY)},
            {"key": "d1_anomaly_source", "value": "metrics_source_data.xlsx/d1_decision_anomalies"},
            {"key": "gate3_fail_source", "value": "医生评测汇总.xlsx/人工评分_D4Gate3不通过"},
            {"key": "fact_rows", "value": int(len(fact))},
            {"key": "cross_rows", "value": int(len(cross))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "excluded_gate3_d4_rows", "value": int(len(excluded_gate3))},
            {"key": "fact_used_rows", "value": int(len(fact_used))},
            {"key": "cross_used_rows", "value": int(len(cross_used))},
        ],
    )


def _extract_memory(d1_set: set[tuple[str, str, str]], gate3_set: set[tuple[str, str, str]]) -> None:
    detail = pd.read_excel(
        RAW_LLM_MEMORY,
        sheet_name="记忆保持-明细",
        usecols=[
            "中心",
            "被评测模型",
            "病例ID",
            "阶段",
            "历史信息继承度(0-1)",
            "历史信息利用率(0-1)",
            "关键信息丢失率(0-1)",
        ],
    )
    detail = detail.rename(
        columns={
            "中心": "center",
            "被评测模型": "model",
            "病例ID": "case_id",
            "阶段": "stage",
            "历史信息继承度(0-1)": "inheritance_0_1",
            "历史信息利用率(0-1)": "utilization_0_1",
            "关键信息丢失率(0-1)": "key_info_loss_rate_0_1",
        }
    )
    detail = _add_common_cols(detail)
    detail["stage_cn"] = detail["stage"].map(STAGE6_RENAME).fillna(detail["stage"].astype(str))
    keys = list(zip(detail["center"].astype(str), detail["model"].astype(str), detail["case_id"].astype(str)))
    detail["is_d1_anomaly"] = [k in d1_set for k in keys]
    detail["is_gate3_fail"] = [k in gate3_set for k in keys]

    excluded_d1 = detail[detail["is_d1_anomaly"]].copy()
    used = detail[~detail["is_d1_anomaly"]].copy()
    excluded_gate3_d4 = used[(used["stage"] == "D4_Rehab_Plan") & (used["is_gate3_fail"])].copy()
    used = used.drop(excluded_gate3_d4.index)

    summary = (
        used.groupby(["center", "model", "model_short", "stage", "stage_cn"], as_index=False)
        .agg(
            inheritance_0_1_mean=("inheritance_0_1", "mean"),
            utilization_0_1_mean=("utilization_0_1", "mean"),
            key_info_loss_rate_0_1_mean=("key_info_loss_rate_0_1", "mean"),
            n_cases=("case_id", "nunique"),
        )
        .sort_values(["center", "model_short", "stage"], kind="mergesort")
    )

    _write_xlsx(
        OUT_DIR / "llm_memory_source.xlsx",
        {
            "detail_all": detail,
            "detail_used": used,
            "summary_used": summary,
            "excluded_d1_anomaly": excluded_d1,
            "excluded_gate3_d4": excluded_gate3_d4,
        },
        [
            {"key": "raw_file", "value": str(RAW_LLM_MEMORY)},
            {"key": "d1_anomaly_source", "value": "metrics_source_data.xlsx/d1_decision_anomalies"},
            {"key": "gate3_fail_source", "value": "医生评测汇总.xlsx/人工评分_D4Gate3不通过"},
            {"key": "detail_rows", "value": int(len(detail))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "excluded_gate3_d4_rows", "value": int(len(excluded_gate3_d4))},
            {"key": "used_rows", "value": int(len(used))},
        ],
    )


def main() -> None:
    d1_set = _load_d1_anomaly_set()
    gate3_set = _load_gate3_fail_set()

    _extract_reasoning(d1_set, gate3_set)
    _extract_consistency(d1_set, gate3_set)
    _extract_memory(d1_set, gate3_set)


if __name__ == "__main__":
    main()
