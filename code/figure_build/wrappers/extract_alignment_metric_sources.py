"""Extract audit-friendly alignment metric source tables.

目标
----
补齐 alignment 的病例级可审计数据层，输出：
1) 人工结果质量 vs Judge(×5)
2) 人工推理合理性 vs LLM推理质量(×5)
3) 双医生一致性（结果质量 / 推理合理性）

强制样本规则
------------
1) D1 anomaly 不参与任何计算；
2) Gate3-fail 样本不参与 D4 计算。

输出目录
--------
analysis_viz/data/derived/metrics/alignment/
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]

RAW_DIR = ROOT / "analysis_viz" / "data" / "raw"
RAW_DOCTOR_DIR = RAW_DIR / "doctor_eval_results"
RAW_METRICS_SOURCE = RAW_DIR / "metrics_source_data.xlsx"
RAW_DOCTOR_SUMMARY = RAW_DIR / "医生评测汇总.xlsx"
RAW_LLM_REASONING = RAW_DIR / "llm_reasoning_gemini-2.5-pro__gala_api.xlsx"

OUT_DIR = ROOT / "analysis_viz" / "data" / "derived" / "metrics" / "alignment"


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


STAGE_RENAME = {
    "D1_Loop": "门诊检查",
    "D1_Decision": "门诊决策",
    "D2_Loop": "入院检查",
    "D2_Decision": "入院决策",
    "D3_Decision": "术后康复",
    "D4_Plan": "随访计划",
    "D4_Rehab_Plan": "随访计划",
}


JUDGE_STAGE_COLS = {
    "D1_Outpatient_Loop__judge_composite_score_mean": "D1_Loop",
    "gate1_overall_score": "D1_Decision",
    "D2_Admission_Loop__judge_composite_score_mean": "D2_Loop",
    "gate2_overall_score": "D2_Decision",
    "d3_overall_score": "D3_Decision",
    "d4_overall_score": "D4_Plan",
}


LLM_STAGE_MAP = {
    "D1_Outpatient_Loop": "D1_Loop",
    "D1_Outpatient_Decision": "D1_Decision",
    "D2_Admission_Loop": "D2_Loop",
    "D2_Admission_Decision": "D2_Decision",
    "D3_Surgery_Decision": "D3_Decision",
    "D4_Rehab_Plan": "D4_Plan",
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
        if doctor_dir.name.lower().startswith("bkup"):
            continue
        for xlsx in sorted(doctor_dir.glob("*.xlsx")):
            center = xlsx.stem.split("-", 1)[0]
            out.append((doctor_dir.name, center, xlsx))
    return out


def _load_scoring_coverage(doctor: str, center: str, path: Path) -> pd.DataFrame:
    try:
        df = pd.read_excel(path, sheet_name="评分覆盖率")
    except Exception:
        df = pd.read_excel(path, sheet_name="评分覆盖率_D2正常")
    df = df.rename(columns={"病例ID": "case_id", "模型名称": "model", "中心": "center"})
    if "center" not in df.columns:
        df["center"] = center
    df["doctor"] = doctor
    df["source_file"] = str(path)
    return df


def _normalize_manual_long(df_cov: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    base_cols = ["doctor", "center", "model", "case_id", "source_file"]
    for col in base_cols:
        if col not in df_cov.columns:
            df_cov[col] = ""

    for prefix, stage in STAGE_PREFIX_TO_CODE.items():
        status_col = f"{prefix}_状态"
        result_col = f"{prefix}_结果质量评分"
        reasoning_col = f"{prefix}_推理合理性"
        if status_col not in df_cov.columns:
            continue
        sub = df_cov[base_cols].copy()
        sub["status"] = df_cov[status_col]
        sub["result_score_0_5"] = pd.to_numeric(df_cov.get(result_col), errors="coerce")
        sub["reasoning_score_0_5"] = pd.to_numeric(df_cov.get(reasoning_col), errors="coerce")
        sub["stage"] = stage
        rows.extend(sub.to_dict(orient="records"))

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["center"] = out["center"].astype(str).str.strip()
    out["model"] = out["model"].astype(str).str.strip()
    out["case_id"] = out["case_id"].astype(str).str.strip()
    out["model_short"] = out["model"].map(MODEL_SHORT).fillna(out["model"])
    out["stage_cn"] = out["stage"].map(STAGE_RENAME).fillna(out["stage"])
    return out


def _load_judge_case_scores_x5() -> pd.DataFrame:
    df = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="metrics_by_case")
    df = df.rename(columns={"center": "center", "model": "model", "case_id": "case_id"})
    out_rows: list[pd.DataFrame] = []

    for col, stage in JUDGE_STAGE_COLS.items():
        if col not in df.columns:
            continue
        sub = df[["center", "model", "case_id", col]].copy()
        sub["judge_score_0_5"] = pd.to_numeric(sub[col], errors="coerce") * 5.0
        sub["stage"] = stage
        sub["judge_source_col"] = col
        sub["judge_source_sheet"] = "metrics_by_case"
        out_rows.append(sub[["center", "model", "case_id", "stage", "judge_score_0_5", "judge_source_sheet", "judge_source_col"]])

    if not out_rows:
        return pd.DataFrame()

    out = pd.concat(out_rows, ignore_index=True)
    out["center"] = out["center"].astype(str).str.strip()
    out["model"] = out["model"].astype(str).str.strip()
    out["case_id"] = out["case_id"].astype(str).str.strip()
    out["model_short"] = out["model"].map(MODEL_SHORT).fillna(out["model"])
    out["stage_cn"] = out["stage"].map(STAGE_RENAME).fillna(out["stage"])
    return out


def _load_llm_reason_case_scores_x5() -> pd.DataFrame:
    if not RAW_LLM_REASONING.exists():
        return pd.DataFrame()
    df = pd.read_excel(
        RAW_LLM_REASONING,
        sheet_name="推理质量-明细",
        usecols=["中心", "被评测模型", "病例ID", "阶段", "推理质量得分(0-1)"],
    )
    if df.empty:
        return pd.DataFrame()

    out = df.rename(
        columns={
            "中心": "center",
            "被评测模型": "model",
            "病例ID": "case_id",
            "阶段": "stage_raw",
            "推理质量得分(0-1)": "llm_reason_score_0_1",
        }
    ).copy()
    out["stage"] = out["stage_raw"].map(LLM_STAGE_MAP)
    out = out[out["stage"].notna()].copy()
    out["llm_reasoning_score_0_5"] = pd.to_numeric(out["llm_reason_score_0_1"], errors="coerce") * 5.0
    out["llm_source_sheet"] = "推理质量-明细"
    out["llm_source_col"] = "推理质量得分(0-1)"
    out["center"] = out["center"].astype(str).str.strip()
    out["model"] = out["model"].astype(str).str.strip()
    out["case_id"] = out["case_id"].astype(str).str.strip()
    out["model_short"] = out["model"].map(MODEL_SHORT).fillna(out["model"])
    out["stage_cn"] = out["stage"].map(STAGE_RENAME).fillna(out["stage"])
    return out[
        [
            "center",
            "model",
            "case_id",
            "stage",
            "model_short",
            "stage_cn",
            "llm_reasoning_score_0_5",
            "llm_source_sheet",
            "llm_source_col",
        ]
    ]


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
    excluded_gate3_d4 = used[(used["stage"] == "D4_Plan") & (used["is_gate3_fail"])].copy()
    detail_used = used.drop(excluded_gate3_d4.index)
    return out, excluded_d1, excluded_gate3_d4, detail_used


def _spearman_rho(x: pd.Series, y: pd.Series) -> float:
    xs = pd.to_numeric(x, errors="coerce")
    ys = pd.to_numeric(y, errors="coerce")
    valid = xs.notna() & ys.notna()
    xs = xs[valid]
    ys = ys[valid]
    if len(xs) < 2 or xs.nunique(dropna=True) < 2 or ys.nunique(dropna=True) < 2:
        return float("nan")
    return float(xs.corr(ys, method="spearman"))


def _quadratic_weighted_kappa(x: pd.Series, y: pd.Series, *, step: float = 0.5, max_score: float = 5.0) -> float:
    xs = pd.to_numeric(x, errors="coerce")
    ys = pd.to_numeric(y, errors="coerce")
    valid = xs.notna() & ys.notna()
    xs = xs[valid].clip(0.0, max_score)
    ys = ys[valid].clip(0.0, max_score)
    if len(xs) < 2:
        return float("nan")

    n_levels = int(round(max_score / step)) + 1
    xi = np.rint(xs.to_numpy(dtype=float) / step).astype(int)
    yi = np.rint(ys.to_numpy(dtype=float) / step).astype(int)
    xi = np.clip(xi, 0, n_levels - 1)
    yi = np.clip(yi, 0, n_levels - 1)

    observed = np.zeros((n_levels, n_levels), dtype=float)
    for a, b in zip(xi, yi):
        observed[a, b] += 1.0
    total = float(observed.sum())
    if total <= 0:
        return float("nan")

    hist_x = observed.sum(axis=1)
    hist_y = observed.sum(axis=0)
    expected = np.outer(hist_x, hist_y) / total
    denom_scale = max(1, n_levels - 1)
    weights = np.fromfunction(lambda i, j: ((i - j) / denom_scale) ** 2, (n_levels, n_levels), dtype=float)
    observed = observed / total
    expected = expected / total
    expected_weighted = float((weights * expected).sum())
    if expected_weighted <= 0:
        return float("nan")
    observed_weighted = float((weights * observed).sum())
    return float(1.0 - observed_weighted / expected_weighted)


def _calc_alignment_summary(detail_used: pd.DataFrame, target_col: str) -> pd.DataFrame:
    if detail_used.empty:
        return pd.DataFrame(
            columns=[
                "center",
                "model",
                "model_short",
                "stage",
                "stage_cn",
                "n_pairs",
                "n_cases",
                "n_doctors",
                "human_mean",
                "target_mean",
                "delta_mean",
                "mae",
                "rmse",
                "pearson_r",
                "spearman_rho",
                "quadratic_weighted_kappa",
            ]
        )

    grouped = []
    for keys, sub in detail_used.groupby(["center", "model", "model_short", "stage", "stage_cn"], dropna=False):
        x = pd.to_numeric(sub["human_score_0_5"], errors="coerce")
        y = pd.to_numeric(sub[target_col], errors="coerce")
        valid = x.notna() & y.notna()
        x = x[valid]
        y = y[valid]
        if x.empty:
            continue
        delta = y - x
        row = {
            "center": keys[0],
            "model": keys[1],
            "model_short": keys[2],
            "stage": keys[3],
            "stage_cn": keys[4],
            "n_pairs": int(len(x)),
            "n_cases": int(sub.loc[valid, "case_id"].nunique()),
            "n_doctors": int(sub.loc[valid, "doctor"].nunique()),
            "human_mean": float(x.mean()),
            "target_mean": float(y.mean()),
            "delta_mean": float(delta.mean()),
            "mae": float((x - y).abs().mean()),
            "rmse": float(np.sqrt(((x - y) ** 2).mean())),
            "pearson_r": (
                float(x.corr(y))
                if len(x) >= 2 and x.nunique(dropna=True) >= 2 and y.nunique(dropna=True) >= 2
                else np.nan
            ),
            "spearman_rho": _spearman_rho(x, y),
            "quadratic_weighted_kappa": _quadratic_weighted_kappa(x, y),
        }
        grouped.append(row)

    out = pd.DataFrame(grouped)
    if out.empty:
        return out
    return out.sort_values(["center", "stage", "model_short"], kind="mergesort")


def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame], meta_rows: list[dict[str, object]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = pd.DataFrame(meta_rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
        meta.to_excel(writer, sheet_name="meta", index=False)


def _build_alignment_metric(
    *,
    metric_id: str,
    metric_name: str,
    manual_long: pd.DataFrame,
    manual_score_col: str,
    target_df: pd.DataFrame,
    target_col: str,
    source_sheet_col: str,
    source_col_col: str,
    out_file: str,
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
) -> None:
    detail = manual_long[
        [
            "doctor",
            "center",
            "model",
            "model_short",
            "case_id",
            "stage",
            "stage_cn",
            "status",
            manual_score_col,
            "source_file",
        ]
    ].copy()
    detail = detail.rename(columns={manual_score_col: "human_score_0_5", "source_file": "manual_source_file"})
    detail["human_score_0_5"] = pd.to_numeric(detail["human_score_0_5"], errors="coerce")

    merged = detail.merge(
        target_df[
            [
                "center",
                "model",
                "case_id",
                "stage",
                target_col,
                source_sheet_col,
                source_col_col,
            ]
        ],
        on=["center", "model", "case_id", "stage"],
        how="left",
    )

    detail_all, excluded_d1, excluded_gate3_d4, detail_rule_used = _attach_rule_flags(merged, d1_set, gate3_set)
    detail_used = detail_rule_used.dropna(subset=["human_score_0_5", target_col]).copy()
    summary_used = _calc_alignment_summary(detail_used, target_col)

    _write_xlsx(
        OUT_DIR / out_file,
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
            {"key": "raw_manual_source", "value": str(RAW_DOCTOR_DIR)},
            {"key": "raw_manual_sheet", "value": "评分覆盖率"},
            {"key": "rule_d1", "value": "D1 anomaly cases excluded from calculations"},
            {"key": "rule_gate3_d4", "value": "Gate3 fail cases excluded from D4"},
            {"key": "detail_rows", "value": int(len(detail_all))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "excluded_gate3_d4_rows", "value": int(len(excluded_gate3_d4))},
            {"key": "used_rows", "value": int(len(detail_used))},
        ],
    )


def _build_doctor_consensus_metric(
    *,
    metric_id: str,
    metric_name: str,
    manual_long: pd.DataFrame,
    manual_score_col: str,
    out_file: str,
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
) -> None:
    detail = manual_long[
        [
            "doctor",
            "center",
            "model",
            "model_short",
            "case_id",
            "stage",
            "stage_cn",
            "status",
            manual_score_col,
            "source_file",
        ]
    ].copy()
    detail = detail.rename(columns={manual_score_col: "doctor_score_0_5", "source_file": "manual_source_file"})
    detail["doctor_score_0_5"] = pd.to_numeric(detail["doctor_score_0_5"], errors="coerce")

    detail_all, excluded_d1, excluded_gate3_d4, detail_rule_used = _attach_rule_flags(detail, d1_set, gate3_set)
    detail_used = detail_rule_used.dropna(subset=["doctor_score_0_5"]).copy()

    key_cols = ["center", "model", "model_short", "case_id", "stage", "stage_cn"]
    pair = detail_used.merge(
        detail_used,
        on=key_cols,
        suffixes=("_a", "_b"),
        how="inner",
    )
    pair = pair[pair["doctor_a"] < pair["doctor_b"]].copy()
    pair["abs_diff"] = (pair["doctor_score_0_5_a"] - pair["doctor_score_0_5_b"]).abs()
    pair["is_exact_match"] = pair["abs_diff"] == 0
    pair["is_within_1pt"] = pair["abs_diff"] <= 1

    summary_rows: list[dict[str, object]] = []
    group_cols = ["center", "model", "model_short", "stage", "stage_cn"]
    for keys, g in pair.groupby(group_cols, dropna=False):
        summary_rows.append(
            {
                "center": keys[0],
                "model": keys[1],
                "model_short": keys[2],
                "stage": keys[3],
                "stage_cn": keys[4],
                "n_pairs": int(g["case_id"].count()),
                "n_cases": int(g["case_id"].nunique()),
                "abs_diff_mean": float(pd.to_numeric(g["abs_diff"], errors="coerce").mean()),
                "exact_match_rate": float(pd.to_numeric(g["is_exact_match"], errors="coerce").mean()),
                "within_1pt_rate": float(pd.to_numeric(g["is_within_1pt"], errors="coerce").mean()),
                "spearman_rho": _spearman_rho(g["doctor_score_0_5_a"], g["doctor_score_0_5_b"]),
                "quadratic_weighted_kappa": _quadratic_weighted_kappa(
                    g["doctor_score_0_5_a"], g["doctor_score_0_5_b"]
                ),
            }
        )
    summary_used = pd.DataFrame(summary_rows)
    if not summary_used.empty:
        summary_used = summary_used.sort_values(["center", "stage", "model_short"], kind="mergesort").reset_index(drop=True)

    _write_xlsx(
        OUT_DIR / out_file,
        {
            "detail_all": detail_all,
            "detail_used": detail_used,
            "pair_detail_used": pair,
            "summary_used": summary_used,
            "excluded_d1_anomaly": excluded_d1,
            "excluded_gate3_d4": excluded_gate3_d4,
        },
        [
            {"key": "metric_id", "value": metric_id},
            {"key": "metric_name", "value": metric_name},
            {"key": "generated_at", "value": datetime.now().isoformat(timespec="seconds")},
            {"key": "raw_manual_source", "value": str(RAW_DOCTOR_DIR)},
            {"key": "raw_manual_sheet", "value": "评分覆盖率"},
            {"key": "rule_d1", "value": "D1 anomaly cases excluded from calculations"},
            {"key": "rule_gate3_d4", "value": "Gate3 fail cases excluded from D4"},
            {"key": "detail_rows", "value": int(len(detail_all))},
            {"key": "excluded_d1_rows", "value": int(len(excluded_d1))},
            {"key": "excluded_gate3_d4_rows", "value": int(len(excluded_gate3_d4))},
            {"key": "used_rows", "value": int(len(detail_used))},
            {"key": "pair_rows", "value": int(len(pair))},
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

    manual_long = _normalize_manual_long(pd.concat(cov_parts, ignore_index=True))
    if manual_long.empty:
        raise RuntimeError("No manual long-form rows loaded")

    judge_df = _load_judge_case_scores_x5()
    if judge_df.empty:
        raise RuntimeError("No judge case-level scores found in metrics_source_data.xlsx/metrics_by_case")

    llm_reason_df = _load_llm_reason_case_scores_x5()
    if llm_reason_df.empty:
        raise RuntimeError("No llm reasoning case-level scores found in llm_reasoning file")

    _build_alignment_metric(
        metric_id="alignment_result_vs_judge_case_level",
        metric_name="Alignment: 人工结果质量 vs Judge(×5) 病例级",
        manual_long=manual_long,
        manual_score_col="result_score_0_5",
        target_df=judge_df,
        target_col="judge_score_0_5",
        source_sheet_col="judge_source_sheet",
        source_col_col="judge_source_col",
        out_file="alignment_result_vs_judge_case_level_source.xlsx",
        d1_set=d1_set,
        gate3_set=gate3_set,
    )
    print("WROTE", OUT_DIR / "alignment_result_vs_judge_case_level_source.xlsx")

    _build_alignment_metric(
        metric_id="alignment_reasoning_vs_llm_case_level",
        metric_name="Alignment: 人工推理合理性 vs LLM推理质量(×5) 病例级",
        manual_long=manual_long,
        manual_score_col="reasoning_score_0_5",
        target_df=llm_reason_df,
        target_col="llm_reasoning_score_0_5",
        source_sheet_col="llm_source_sheet",
        source_col_col="llm_source_col",
        out_file="alignment_reasoning_vs_llm_case_level_source.xlsx",
        d1_set=d1_set,
        gate3_set=gate3_set,
    )
    print("WROTE", OUT_DIR / "alignment_reasoning_vs_llm_case_level_source.xlsx")

    _build_doctor_consensus_metric(
        metric_id="alignment_doctor_consensus_result",
        metric_name="Alignment: 双医生结果质量一致性（病例级）",
        manual_long=manual_long,
        manual_score_col="result_score_0_5",
        out_file="alignment_doctor_consensus_result_source.xlsx",
        d1_set=d1_set,
        gate3_set=gate3_set,
    )
    print("WROTE", OUT_DIR / "alignment_doctor_consensus_result_source.xlsx")

    _build_doctor_consensus_metric(
        metric_id="alignment_doctor_consensus_reasoning",
        metric_name="Alignment: 双医生推理合理性一致性（病例级）",
        manual_long=manual_long,
        manual_score_col="reasoning_score_0_5",
        out_file="alignment_doctor_consensus_reasoning_source.xlsx",
        d1_set=d1_set,
        gate3_set=gate3_set,
    )
    print("WROTE", OUT_DIR / "alignment_doctor_consensus_reasoning_source.xlsx")


if __name__ == "__main__":
    main()
