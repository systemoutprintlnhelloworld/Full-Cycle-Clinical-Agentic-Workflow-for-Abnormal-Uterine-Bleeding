from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
ALIGN_DIR = ROOT / "analysis_viz" / "data" / "derived" / "metrics" / "alignment"
OUT_MAIN = (
    ROOT
    / "analysis_viz"
    / "data"
    / "derived"
    / "figdata"
    / "v2_subplots"
    / "A0_consistency_tables"
    / "A0_consistency_raw_icc_pearson_ternary_source.xlsx"
)
OUT_SUPP = (
    ROOT
    / "analysis_viz"
    / "figures"
    / "v2_subplots"
    / "_supplementary"
    / "A0_consistency_tables"
    / "source_data"
    / "A0_consistency_raw_icc_pearson_ternary_source.xlsx"
)
OUT_NOTE = (
    ROOT
    / "analysis_viz"
    / "给用户看"
    / "A0_原始与三值化一致性计算说明_2026-04-14.md"
)


def _center_to_cn(center: Any) -> str:
    mapping = {
        "Foshan": "佛山",
        "Wuhan": "武汉",
        "Xinjiang": "新疆",
        "foshan": "佛山",
        "wuhan": "武汉",
        "xinjiang": "新疆",
    }
    s = str(center or "").strip()
    return mapping.get(s, s)


def _pearson_safe(x: pd.Series, y: pd.Series) -> tuple[float, str]:
    xs = pd.to_numeric(x, errors="coerce")
    ys = pd.to_numeric(y, errors="coerce")
    valid = xs.notna() & ys.notna()
    xs = xs[valid]
    ys = ys[valid]
    if len(xs) < 2:
        return float("nan"), "样本不足(<2)"
    if xs.nunique(dropna=True) < 2 and ys.nunique(dropna=True) < 2:
        return float("nan"), "两端无方差(常量)"
    if xs.nunique(dropna=True) < 2:
        return float("nan"), "左侧无方差(常量)"
    if ys.nunique(dropna=True) < 2:
        return float("nan"), "右侧无方差(常量)"
    return float(xs.corr(ys, method="pearson")), ""


def _spearman_safe(x: pd.Series, y: pd.Series) -> float:
    xs = pd.to_numeric(x, errors="coerce")
    ys = pd.to_numeric(y, errors="coerce")
    valid = xs.notna() & ys.notna()
    xs = xs[valid]
    ys = ys[valid]
    if len(xs) < 2:
        return float("nan")
    if xs.nunique(dropna=True) < 2 or ys.nunique(dropna=True) < 2:
        return float("nan")
    return float(xs.corr(ys, method="spearman"))


def _qwk_from_levels(x: pd.Series, y: pd.Series, *, step: float, max_score: float) -> float:
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


def _icc_a1(x: pd.Series, y: pd.Series) -> tuple[float, str]:
    xs = pd.to_numeric(x, errors="coerce")
    ys = pd.to_numeric(y, errors="coerce")
    valid = xs.notna() & ys.notna()
    xs = xs[valid]
    ys = ys[valid]
    n = len(xs)
    if n < 2:
        return float("nan"), "样本不足(<2)"

    mat = np.column_stack([xs.to_numpy(dtype=float), ys.to_numpy(dtype=float)])
    k = mat.shape[1]
    gm = float(mat.mean())
    row_means = mat.mean(axis=1)
    col_means = mat.mean(axis=0)

    ss_rows = float(k * np.sum((row_means - gm) ** 2))
    ss_cols = float(n * np.sum((col_means - gm) ** 2))
    ss_total = float(np.sum((mat - gm) ** 2))
    ss_err = float(ss_total - ss_rows - ss_cols)

    df_rows = n - 1
    df_cols = k - 1
    df_err = df_rows * df_cols
    if df_rows <= 0 or df_err <= 0:
        return float("nan"), "自由度不足"

    ms_rows = ss_rows / df_rows
    ms_cols = ss_cols / df_cols
    ms_err = ss_err / df_err
    den = ms_rows + (k - 1) * ms_err + k * (ms_cols - ms_err) / n

    if np.isclose(den, 0.0):
        if np.nanstd(xs) == 0 and np.nanstd(ys) == 0:
            return float("nan"), "两端无方差(常量)"
        if np.nanstd(xs) == 0:
            return float("nan"), "左侧无方差(常量)"
        if np.nanstd(ys) == 0:
            return float("nan"), "右侧无方差(常量)"
        return float("nan"), "分母为0"

    return float((ms_rows - ms_err) / den), ""


def _ternary_map(v: pd.Series) -> pd.Series:
    x = pd.to_numeric(v, errors="coerce")
    out = pd.Series(np.nan, index=x.index, dtype=float)
    # 连续分值按阈值区间离散化，避免 1.x / 3.x 被误丢弃
    out[(x >= 0) & (x < 2)] = 0.0
    out[(x >= 2) & (x < 4)] = 1.0
    out[(x >= 4) & (x <= 5)] = 2.0
    return out


def _calc_metrics(x: pd.Series, y: pd.Series, mode: str) -> dict[str, Any]:
    if mode == "raw_0_5":
        xx = pd.to_numeric(x, errors="coerce")
        yy = pd.to_numeric(y, errors="coerce")
        qwk = _qwk_from_levels(xx, yy, step=0.5, max_score=5.0)
    else:
        xx = _ternary_map(x)
        yy = _ternary_map(y)
        qwk = _qwk_from_levels(xx, yy, step=1.0, max_score=2.0)

    valid = xx.notna() & yy.notna()
    xx = xx[valid]
    yy = yy[valid]
    n = int(len(xx))
    if n == 0:
        return {
            "n_pairs": 0,
            "mae": np.nan,
            "rmse": np.nan,
            "exact_rate": np.nan,
            "within1_rate": np.nan,
            "pearson_r": np.nan,
            "pearson_missing_reason": "样本不足(<2)",
            "spearman_rho": np.nan,
            "icc_a1": np.nan,
            "icc_missing_reason": "样本不足(<2)",
            "qwk": np.nan,
        }

    diff = (xx - yy).abs()
    pear, pear_reason = _pearson_safe(xx, yy)
    icc, icc_reason = _icc_a1(xx, yy)
    return {
        "n_pairs": n,
        "mae": float(diff.mean()),
        "rmse": float(np.sqrt(((xx - yy) ** 2).mean())),
        "exact_rate": float((diff == 0).mean()),
        "within1_rate": float((diff <= 1).mean()),
        "pearson_r": pear,
        "pearson_missing_reason": pear_reason,
        "spearman_rho": _spearman_safe(xx, yy),
        "icc_a1": icc,
        "icc_missing_reason": icc_reason,
        "qwk": qwk,
    }


def _build_suite(
    df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    stage_group_map: dict[str, str],
    stage_order: list[str],
    stage_label_map: dict[str, str],
    comparator: str,
    dimension: str,
    mode: str,
) -> pd.DataFrame:
    use = df.copy()
    use["stage_key"] = use["stage"].map(stage_group_map)
    use[x_col] = pd.to_numeric(use[x_col], errors="coerce")
    use[y_col] = pd.to_numeric(use[y_col], errors="coerce")
    use = use[use["stage_key"].isin(stage_order)].copy()
    use = use[use[x_col].notna() & use[y_col].notna()].copy()

    rows: list[dict[str, Any]] = []
    for stage_key in stage_order:
        sub = use[use["stage_key"] == stage_key].copy()
        metrics = _calc_metrics(sub[x_col], sub[y_col], mode)
        rows.append(
            {
                "stage_scope": "decision" if "CHECK" not in stage_key else "check",
                "stage_key": stage_key,
                "stage_cn": stage_label_map.get(stage_key, stage_key),
                "comparator": comparator,
                "dimension": dimension,
                "scale_mode": mode,
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def _to_zh(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["stage_scope"] = out["stage_scope"].map({"decision": "决策环节", "check": "检查环节"}).fillna(out["stage_scope"])
    out["comparator"] = out["comparator"].map(
        {"human_vs_judge": "人机(医生 vs Judge)", "doctor_vs_doctor": "人人(医生A vs 医生B)"}
    ).fillna(out["comparator"])
    out["dimension"] = out["dimension"].map({"result": "结果评分", "reasoning": "推理评分"}).fillna(out["dimension"])
    out["scale_mode"] = out["scale_mode"].map(
        {"raw_0_5": "原始0-5", "ternary_0_1_2": "三值化(0-1/2-3/4-5)"}
    ).fillna(out["scale_mode"])
    out = out.rename(
        columns={
            "stage_scope": "阶段范围",
            "stage_key": "阶段编码",
            "stage_cn": "阶段名称",
            "comparator": "对比类型",
            "dimension": "评分维度",
            "scale_mode": "量纲口径",
            "n_pairs": "配对数",
            "mae": "MAE",
            "rmse": "RMSE",
            "exact_rate": "完全一致率(0-1)",
            "within1_rate": "±1分一致率(0-1)",
            "pearson_r": "Pearson相关",
            "pearson_missing_reason": "Pearson缺失原因",
            "spearman_rho": "Spearman相关",
            "icc_a1": "ICC(A,1)",
            "icc_missing_reason": "ICC缺失原因",
            "qwk": "加权Kappa(QW)",
        }
    )
    return out


def _build_ternary_detail(
    df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    stage_group_map: dict[str, str],
    stage_order: list[str],
    stage_label_map: dict[str, str],
    comparator: str,
    dimension: str,
) -> pd.DataFrame:
    use = df.copy()
    use["stage_key"] = use["stage"].map(stage_group_map)
    use = use[use["stage_key"].isin(stage_order)].copy()
    use[x_col] = pd.to_numeric(use[x_col], errors="coerce")
    use[y_col] = pd.to_numeric(use[y_col], errors="coerce")
    use = use[use[x_col].notna() & use[y_col].notna()].copy()
    if use.empty:
        return pd.DataFrame()

    use["left_raw"] = pd.to_numeric(use[x_col], errors="coerce")
    use["right_raw"] = pd.to_numeric(use[y_col], errors="coerce")
    use["left_tri"] = _ternary_map(use[x_col])
    use["right_tri"] = _ternary_map(use[y_col])
    use["tri_diff"] = (use["left_tri"] - use["right_tri"]).abs()
    use["stage_cn"] = use["stage_key"].map(stage_label_map).fillna(use["stage_key"])
    use["stage_scope"] = np.where(use["stage_key"].astype(str).str.contains("CHECK"), "检查环节", "决策环节")
    use["comparator"] = comparator
    use["dimension"] = dimension

    keep = [c for c in ["center", "model", "model_short", "case_id", "doctor", "doctor_a", "doctor_b"] if c in use.columns]
    out = use[keep + ["stage_scope", "stage_key", "stage_cn", "comparator", "dimension", "left_raw", "right_raw", "left_tri", "right_tri", "tri_diff"]].copy()

    if "center" in out.columns:
        out["center"] = out["center"].map(_center_to_cn)
    out["comparator"] = out["comparator"].map(
        {"human_vs_judge": "人机(医生 vs Judge)", "doctor_vs_doctor": "人人(医生A vs 医生B)"}
    ).fillna(out["comparator"])
    out["dimension"] = out["dimension"].map({"result": "结果评分", "reasoning": "推理评分"}).fillna(out["dimension"])

    out = out.rename(
        columns={
            "center": "中心",
            "model": "模型",
            "model_short": "模型简称",
            "case_id": "病例ID",
            "doctor": "医生",
            "doctor_a": "医生A",
            "doctor_b": "医生B",
            "stage_scope": "阶段范围",
            "stage_key": "阶段编码",
            "stage_cn": "阶段名称",
            "comparator": "对比类型",
            "dimension": "评分维度",
            "left_raw": "左侧评分(0-5)",
            "right_raw": "右侧评分(0-5)",
            "left_tri": "左侧三值标签",
            "right_tri": "右侧三值标签",
            "tri_diff": "三值标签差值",
        }
    )
    return out


def main() -> None:
    result_detail = pd.read_excel(ALIGN_DIR / "alignment_result_vs_judge_case_level_source.xlsx", sheet_name="detail_used")
    reason_detail = pd.read_excel(ALIGN_DIR / "alignment_reasoning_vs_llm_case_level_source.xlsx", sheet_name="detail_used")
    cons_result_pair = pd.read_excel(ALIGN_DIR / "alignment_doctor_consensus_result_source.xlsx", sheet_name="pair_detail_used")
    cons_reason_pair = pd.read_excel(ALIGN_DIR / "alignment_doctor_consensus_reasoning_source.xlsx", sheet_name="pair_detail_used")

    decision_stage_map = {"D1_Decision": "D1", "D2_Decision": "D2", "D3_Decision": "D3", "D4_Plan": "D4"}
    decision_stage_order = ["D1", "D2", "D3", "D4"]
    decision_stage_label_map = {"D1": "D1 门诊决策", "D2": "D2 住院决策", "D3": "D3 术后决策", "D4": "D4 随访计划"}
    check_stage_map = {"D1_Loop": "D1_CHECK", "D2_Loop": "D2_CHECK"}
    check_stage_order = ["D1_CHECK", "D2_CHECK"]
    check_stage_label_map = {"D1_CHECK": "门诊检查", "D2_CHECK": "住院检查"}

    blocks: list[pd.DataFrame] = []
    for mode in ["raw_0_5", "ternary_0_1_2"]:
        blocks.extend(
            [
                _build_suite(
                    result_detail,
                    x_col="human_score_0_5",
                    y_col="judge_score_0_5",
                    stage_group_map=decision_stage_map,
                    stage_order=decision_stage_order,
                    stage_label_map=decision_stage_label_map,
                    comparator="human_vs_judge",
                    dimension="result",
                    mode=mode,
                ),
                _build_suite(
                    reason_detail,
                    x_col="human_score_0_5",
                    y_col="llm_reasoning_score_0_5",
                    stage_group_map=decision_stage_map,
                    stage_order=decision_stage_order,
                    stage_label_map=decision_stage_label_map,
                    comparator="human_vs_judge",
                    dimension="reasoning",
                    mode=mode,
                ),
                _build_suite(
                    cons_result_pair,
                    x_col="doctor_score_0_5_a",
                    y_col="doctor_score_0_5_b",
                    stage_group_map=decision_stage_map,
                    stage_order=decision_stage_order,
                    stage_label_map=decision_stage_label_map,
                    comparator="doctor_vs_doctor",
                    dimension="result",
                    mode=mode,
                ),
                _build_suite(
                    cons_reason_pair,
                    x_col="doctor_score_0_5_a",
                    y_col="doctor_score_0_5_b",
                    stage_group_map=decision_stage_map,
                    stage_order=decision_stage_order,
                    stage_label_map=decision_stage_label_map,
                    comparator="doctor_vs_doctor",
                    dimension="reasoning",
                    mode=mode,
                ),
                _build_suite(
                    result_detail,
                    x_col="human_score_0_5",
                    y_col="judge_score_0_5",
                    stage_group_map=check_stage_map,
                    stage_order=check_stage_order,
                    stage_label_map=check_stage_label_map,
                    comparator="human_vs_judge",
                    dimension="result",
                    mode=mode,
                ),
                _build_suite(
                    reason_detail,
                    x_col="human_score_0_5",
                    y_col="llm_reasoning_score_0_5",
                    stage_group_map=check_stage_map,
                    stage_order=check_stage_order,
                    stage_label_map=check_stage_label_map,
                    comparator="human_vs_judge",
                    dimension="reasoning",
                    mode=mode,
                ),
                _build_suite(
                    cons_result_pair,
                    x_col="doctor_score_0_5_a",
                    y_col="doctor_score_0_5_b",
                    stage_group_map=check_stage_map,
                    stage_order=check_stage_order,
                    stage_label_map=check_stage_label_map,
                    comparator="doctor_vs_doctor",
                    dimension="result",
                    mode=mode,
                ),
                _build_suite(
                    cons_reason_pair,
                    x_col="doctor_score_0_5_a",
                    y_col="doctor_score_0_5_b",
                    stage_group_map=check_stage_map,
                    stage_order=check_stage_order,
                    stage_label_map=check_stage_label_map,
                    comparator="doctor_vs_doctor",
                    dimension="reasoning",
                    mode=mode,
                ),
            ]
        )
    all_metrics = pd.concat(blocks, ignore_index=True)

    raw_view = all_metrics[all_metrics["scale_mode"] == "raw_0_5"].copy()
    ternary_view = all_metrics[all_metrics["scale_mode"] == "ternary_0_1_2"].copy()

    key_cols = ["stage_scope", "stage_key", "stage_cn", "comparator", "dimension"]
    cmp_left = raw_view[key_cols + ["n_pairs", "pearson_r", "icc_a1", "spearman_rho", "qwk", "pearson_missing_reason", "icc_missing_reason"]].copy()
    cmp_right = ternary_view[key_cols + ["n_pairs", "pearson_r", "icc_a1", "spearman_rho", "qwk", "pearson_missing_reason", "icc_missing_reason"]].copy()
    compare = cmp_left.merge(cmp_right, on=key_cols, how="outer", suffixes=("_raw0_5", "_ternary"))
    compare["pearson_delta_ternary_minus_raw"] = pd.to_numeric(compare["pearson_r_ternary"], errors="coerce") - pd.to_numeric(compare["pearson_r_raw0_5"], errors="coerce")
    compare["icc_delta_ternary_minus_raw"] = pd.to_numeric(compare["icc_a1_ternary"], errors="coerce") - pd.to_numeric(compare["icc_a1_raw0_5"], errors="coerce")

    raw_zh = _to_zh(raw_view)
    ternary_zh = _to_zh(ternary_view)

    compare_zh = compare.rename(
        columns={
            "stage_scope": "阶段范围",
            "stage_key": "阶段编码",
            "stage_cn": "阶段名称",
            "comparator": "对比类型",
            "dimension": "评分维度",
            "n_pairs_raw0_5": "配对数_原始0-5",
            "pearson_r_raw0_5": "Pearson_原始0-5",
            "icc_a1_raw0_5": "ICC_原始0-5",
            "spearman_rho_raw0_5": "Spearman_原始0-5",
            "qwk_raw0_5": "QWK_原始0-5",
            "pearson_missing_reason_raw0_5": "Pearson缺失原因_原始0-5",
            "icc_missing_reason_raw0_5": "ICC缺失原因_原始0-5",
            "n_pairs_ternary": "配对数_三值化",
            "pearson_r_ternary": "Pearson_三值化",
            "icc_a1_ternary": "ICC_三值化",
            "spearman_rho_ternary": "Spearman_三值化",
            "qwk_ternary": "QWK_三值化",
            "pearson_missing_reason_ternary": "Pearson缺失原因_三值化",
            "icc_missing_reason_ternary": "ICC缺失原因_三值化",
            "pearson_delta_ternary_minus_raw": "Pearson变化(三值-原始)",
            "icc_delta_ternary_minus_raw": "ICC变化(三值-原始)",
        }
    )
    compare_zh["阶段范围"] = compare_zh["阶段范围"].map({"decision": "决策环节", "check": "检查环节"}).fillna(compare_zh["阶段范围"])
    compare_zh["对比类型"] = compare_zh["对比类型"].map(
        {"human_vs_judge": "人机(医生 vs Judge)", "doctor_vs_doctor": "人人(医生A vs 医生B)"}
    ).fillna(compare_zh["对比类型"])
    compare_zh["评分维度"] = compare_zh["评分维度"].map({"result": "结果评分", "reasoning": "推理评分"}).fillna(compare_zh["评分维度"])

    ternary_detail = pd.concat(
        [
            _build_ternary_detail(
                result_detail,
                x_col="human_score_0_5",
                y_col="judge_score_0_5",
                stage_group_map=decision_stage_map,
                stage_order=decision_stage_order,
                stage_label_map=decision_stage_label_map,
                comparator="human_vs_judge",
                dimension="result",
            ),
            _build_ternary_detail(
                reason_detail,
                x_col="human_score_0_5",
                y_col="llm_reasoning_score_0_5",
                stage_group_map=decision_stage_map,
                stage_order=decision_stage_order,
                stage_label_map=decision_stage_label_map,
                comparator="human_vs_judge",
                dimension="reasoning",
            ),
            _build_ternary_detail(
                cons_result_pair,
                x_col="doctor_score_0_5_a",
                y_col="doctor_score_0_5_b",
                stage_group_map=decision_stage_map,
                stage_order=decision_stage_order,
                stage_label_map=decision_stage_label_map,
                comparator="doctor_vs_doctor",
                dimension="result",
            ),
            _build_ternary_detail(
                cons_reason_pair,
                x_col="doctor_score_0_5_a",
                y_col="doctor_score_0_5_b",
                stage_group_map=decision_stage_map,
                stage_order=decision_stage_order,
                stage_label_map=decision_stage_label_map,
                comparator="doctor_vs_doctor",
                dimension="reasoning",
            ),
            _build_ternary_detail(
                result_detail,
                x_col="human_score_0_5",
                y_col="judge_score_0_5",
                stage_group_map=check_stage_map,
                stage_order=check_stage_order,
                stage_label_map=check_stage_label_map,
                comparator="human_vs_judge",
                dimension="result",
            ),
            _build_ternary_detail(
                reason_detail,
                x_col="human_score_0_5",
                y_col="llm_reasoning_score_0_5",
                stage_group_map=check_stage_map,
                stage_order=check_stage_order,
                stage_label_map=check_stage_label_map,
                comparator="human_vs_judge",
                dimension="reasoning",
            ),
            _build_ternary_detail(
                cons_result_pair,
                x_col="doctor_score_0_5_a",
                y_col="doctor_score_0_5_b",
                stage_group_map=check_stage_map,
                stage_order=check_stage_order,
                stage_label_map=check_stage_label_map,
                comparator="doctor_vs_doctor",
                dimension="result",
            ),
            _build_ternary_detail(
                cons_reason_pair,
                x_col="doctor_score_0_5_a",
                y_col="doctor_score_0_5_b",
                stage_group_map=check_stage_map,
                stage_order=check_stage_order,
                stage_label_map=check_stage_label_map,
                comparator="doctor_vs_doctor",
                dimension="reasoning",
            ),
        ],
        ignore_index=True,
    )

    meta = pd.DataFrame(
        [
            {"键": "generated_at", "值": datetime.now().isoformat(timespec="seconds")},
            {"键": "raw_scale", "值": "原始评分0-5"},
            {"键": "ternary_rule", "值": "[0,2)=>低; [2,4)=>中; [4,5]=>高"},
            {"键": "icc_type", "值": "ICC(A,1), two-way random absolute agreement"},
            {"键": "notes", "值": "Pearson/ICC 缺失会在原因列中解释"},
            {"键": "source_result", "值": str((ALIGN_DIR / "alignment_result_vs_judge_case_level_source.xlsx").as_posix())},
            {"键": "source_reason", "值": str((ALIGN_DIR / "alignment_reasoning_vs_llm_case_level_source.xlsx").as_posix())},
            {"键": "source_doc_result", "值": str((ALIGN_DIR / "alignment_doctor_consensus_result_source.xlsx").as_posix())},
            {"键": "source_doc_reason", "值": str((ALIGN_DIR / "alignment_doctor_consensus_reasoning_source.xlsx").as_posix())},
        ]
    )

    OUT_MAIN.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT_MAIN, engine="openpyxl") as writer:
        raw_zh.to_excel(writer, sheet_name="原始0_5_指标汇总", index=False)
        ternary_zh.to_excel(writer, sheet_name="三值化_指标汇总", index=False)
        compare_zh.to_excel(writer, sheet_name="原始_vs_三值化_对比", index=False)
        ternary_detail.to_excel(writer, sheet_name="三值化_样本明细", index=False)
        meta.to_excel(writer, sheet_name="元信息", index=False)

    OUT_SUPP.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUPP.write_bytes(OUT_MAIN.read_bytes())

    OUT_NOTE.parent.mkdir(parents=True, exist_ok=True)
    OUT_NOTE.write_text(
        "# A0 一致性补算（原始0-5 vs 三值化）\n\n"
        "已补算：原始0-5与三值化([0,2)/[2,4)/[4,5])下的 Pearson 与 ICC(A,1)，并提供缺失原因。\n\n"
        "输出：\n"
        "- analysis_viz/data/derived/figdata/v2_subplots/A0_consistency_tables/A0_consistency_raw_icc_pearson_ternary_source.xlsx\n"
        "- analysis_viz/figures/v2_subplots/_supplementary/A0_consistency_tables/source_data/A0_consistency_raw_icc_pearson_ternary_source.xlsx\n",
        encoding="utf-8",
    )

    print(OUT_MAIN)
    print(OUT_SUPP)
    print(OUT_NOTE)


if __name__ == "__main__":
    main()
