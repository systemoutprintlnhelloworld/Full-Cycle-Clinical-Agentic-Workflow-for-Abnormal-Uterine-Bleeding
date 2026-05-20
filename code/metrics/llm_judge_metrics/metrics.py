from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .parsing import GTCheckItem, is_gt_check_effective, parse_gt_checks, parse_list_cell
from .status import STAGE_ORDER, detect_d1_decision_anomaly, infer_flow_status_row
from .types import LoadedData


@dataclass(frozen=True)
class MetricTables:
    case_index: pd.DataFrame
    check_rounds: pd.DataFrame
    gt_checks: pd.DataFrame
    metrics_by_case: pd.DataFrame
    metrics_by_center_model: pd.DataFrame


def _case_ids_from_doc(doc_sheets: dict[str, pd.DataFrame]) -> list[str]:
    # Prefer union across sheets (some files may have missing/shifted rows in a single sheet).
    case_ids: set[str] = set()
    for df in doc_sheets.values():
        if df is None or df.empty:
            continue
        cid_col = df.columns[0]
        for x in df[cid_col].dropna().astype(str).tolist():
            cid = str(x).strip()
            if cid:
                case_ids.add(cid)
    return sorted(case_ids)


def build_case_index(loaded: LoadedData) -> pd.DataFrame:
    center = loaded.fileset.center
    model = loaded.fileset.model

    anomalies = detect_d1_decision_anomaly(
        loaded.doc_sheets["D1_Outpatient_Decision"],
        loaded.doc_sheets.get("D2_Admission_Decision"),
    )

    case_ids = _case_ids_from_doc(loaded.doc_sheets)

    rows: list[dict[str, Any]] = []
    for case_id in case_ids:
        inferred = infer_flow_status_row(loaded.doc_sheets, case_id)
        row: dict[str, Any] = {
            "center": center,
            "model": model,
            "case_id": case_id,
            "is_anomaly_d1_to_d2": case_id in anomalies,
        }
        # Keep inferred row keys (case_id overwritten by anchor row above).
        row.update(inferred)
        row["case_id"] = case_id
        rows.append(row)

    return pd.DataFrame(rows)


def build_gt_checks_table(loaded: LoadedData) -> pd.DataFrame:
    gt = loaded.gt.copy()
    # Normalize ID column name
    if "CaseID" not in gt.columns:
        # best effort: first column
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})

    rows: list[dict[str, Any]] = []
    for _, r in gt.iterrows():
        case_id = str(r.get("CaseID", "")).strip()
        out_checks = parse_gt_checks(r.get("GT_Outpatient_Checks"))
        adm_checks = parse_gt_checks(r.get("GT_Admission_Checks"))
        out_eff = [c for c in out_checks if is_gt_check_effective(c)]
        adm_eff = [c for c in adm_checks if is_gt_check_effective(c)]
        rows.append(
            {
                "center": loaded.fileset.center,
                "case_id": case_id,
                "gt_outpatient_effective_count": len(out_eff),
                "gt_admission_effective_count": len(adm_eff),
                "gt_outpatient_checks_raw": str(r.get("GT_Outpatient_Checks", "") if r.get("GT_Outpatient_Checks") is not None else ""),
                "gt_admission_checks_raw": str(r.get("GT_Admission_Checks", "") if r.get("GT_Admission_Checks") is not None else ""),
            }
        )
    return pd.DataFrame(rows)


def compute_metrics(
    case_index: pd.DataFrame,
    check_rounds: pd.DataFrame,
    gt_checks: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Metrics by case (D1/D2 check match rate + loop inefficiency proxies)
    # Keep GT check stats for context only (not used as denominator in v2 metrics).
    gt_counts = gt_checks[
        [
            "center",
            "case_id",
            "gt_outpatient_effective_count",
            "gt_admission_effective_count",
        ]
    ].copy()

    # Aggregate check rounds
    rounds = check_rounds.copy()
    rounds["matched_count_final"] = pd.to_numeric(rounds["matched_count_final"], errors="coerce")
    rounds["ai_total_requested_count"] = pd.to_numeric(rounds["ai_total_requested_count"], errors="coerce")
    rounds["judge_match_score_raw"] = pd.to_numeric(rounds.get("judge_match_score_raw"), errors="coerce")
    rounds["judge_reasonable_score_raw"] = pd.to_numeric(rounds.get("judge_reasonable_score_raw"), errors="coerce")
    rounds["judge_composite_score_raw"] = pd.to_numeric(rounds.get("judge_composite_score_raw"), errors="coerce")

    def to_list(v: Any) -> list[str]:
        try:
            return parse_list_cell(v)
        except Exception:
            return []

    def union_len(series: pd.Series) -> int:
        s: set[str] = set()
        for v in series.tolist():
            if not v:
                continue
            for x in v:
                xs = str(x).strip()
                if xs:
                    s.add(xs)
        return len(s)

    def agg_stage(stage_name: str) -> pd.DataFrame:
        sub = rounds.loc[rounds["stage"] == stage_name].copy()
        if sub.empty:
            return pd.DataFrame(columns=["center", "model", "case_id"])

        sub["ai_total_requested_count"] = pd.to_numeric(sub["ai_total_requested_count"], errors="coerce")
        sub["matched_count_final"] = pd.to_numeric(sub["matched_count_final"], errors="coerce")

        # A round is considered "executed" if the AI requested >0 checks.
        sub["_executed_round"] = sub["ai_total_requested_count"].fillna(0) > 0
        # A round is considered "judge-scored" for match metrics if we have a numeric matched_count_final.
        # (Judge may be missing for some executed rounds; those must be treated as NOT_EVALUATED, not failure.)
        sub["_judge_scored_round"] = sub["_executed_round"] & sub["matched_count_final"].notna()

        # Unique-count view (for LLM合理性回填与手工核对)：以判官的匹配/未执行列表为准，不做字符串exact-match。
        sub["_matched_items"] = (
            sub["judge_matched_items_raw"].map(to_list) if "judge_matched_items_raw" in sub.columns else [[] for _ in range(len(sub))]
        )
        sub["_unexecuted_items"] = (
            sub["judge_unexecuted_items_raw"].map(to_list)
            if "judge_unexecuted_items_raw" in sub.columns
            else [[] for _ in range(len(sub))]
        )
        sub["_requested_items"] = sub["_matched_items"] + sub["_unexecuted_items"]

        def _agg_case(g: pd.DataFrame) -> pd.Series:
            executed_rounds = int(g["_executed_round"].sum())
            judge_scored_rounds = int(g["_judge_scored_round"].sum())
            requested_total = float(g.loc[g["_executed_round"], "ai_total_requested_count"].fillna(0).sum())

            # If any executed round is missing judge scoring, treat the whole stage as NOT_EVALUATED for match/ineff metrics.
            stage_complete = executed_rounds > 0 and judge_scored_rounds == executed_rounds

            matched_total = pd.NA
            ineff_zero = pd.NA
            requested_unique = pd.NA
            matched_unique = pd.NA
            unmatched_unique = pd.NA
            if executed_rounds == 0:
                # Not executed: keep totals at 0, metrics will be masked downstream.
                matched_total = 0.0
                ineff_zero = 0.0
                requested_unique = 0.0
                matched_unique = 0.0
                unmatched_unique = 0.0
            elif stage_complete:
                matched_total = float(g.loc[g["_judge_scored_round"], "matched_count_final"].sum())
                ineff_zero = float(int((g.loc[g["_judge_scored_round"], "matched_count_final"] == 0).sum()))
                # Unique-count view: only meaningful when judge lists exist for all executed rounds.
                requested_unique = float(union_len(g.loc[g["_executed_round"], "_requested_items"]))
                matched_unique = float(union_len(g.loc[g["_executed_round"], "_matched_items"]))
                unmatched_unique = float(union_len(g.loc[g["_executed_round"], "_unexecuted_items"]))

            return pd.Series(
                {
                    "executed_rounds": executed_rounds,
                    "judge_scored_rounds": judge_scored_rounds,
                    "requested_total": requested_total,
                    "matched_total": matched_total,
                    "requested_unique_count": requested_unique,
                    "matched_unique_count": matched_unique,
                    "unmatched_unique_count": unmatched_unique,
                    "inefficient_rounds_by_zero": ineff_zero,
                    # Keep score-based inefficiency as a separate proxy (still requires judge scores).
                    "inefficient_rounds_by_score": float(int(pd.Series(g.loc[g["_executed_round"], "inefficient_round_by_score"]).fillna(False).sum()))
                    if stage_complete
                    else pd.NA,
                    "judge_match_score_mean": float(g.loc[g["_executed_round"], "judge_match_score_raw"].mean())
                    if stage_complete
                    else pd.NA,
                    "judge_reasonable_score_mean": float(g.loc[g["_executed_round"], "judge_reasonable_score_raw"].mean())
                    if stage_complete
                    else pd.NA,
                    "judge_composite_score_mean": float(g.loc[g["_executed_round"], "judge_composite_score_raw"].mean())
                    if stage_complete
                    else pd.NA,
                }
            )

        g = sub.groupby(["center", "model", "case_id"], as_index=False).apply(_agg_case)
        # pandas groupby.apply returns a multi-indexed frame; normalize.
        if isinstance(g.index, pd.MultiIndex):
            g = g.reset_index(level=[0, 1, 2], drop=True).reset_index()
        else:
            g = g.reset_index(drop=True)
        g = g.rename(
            columns={
                "executed_rounds": f"{stage_name}__executed_rounds",
                "judge_scored_rounds": f"{stage_name}__judge_scored_rounds",
                "requested_total": f"{stage_name}__requested_total",
                "matched_total": f"{stage_name}__matched_total",
                "requested_unique_count": f"{stage_name}__requested_unique_count",
                "matched_unique_count": f"{stage_name}__matched_unique_count",
                "unmatched_unique_count": f"{stage_name}__unmatched_unique_count",
                "inefficient_rounds_by_zero": f"{stage_name}__ineff_rounds_by_zero",
                "inefficient_rounds_by_score": f"{stage_name}__ineff_rounds_by_score",
                "judge_match_score_mean": f"{stage_name}__judge_match_score_mean",
                "judge_reasonable_score_mean": f"{stage_name}__judge_reasonable_score_mean",
                "judge_composite_score_mean": f"{stage_name}__judge_composite_score_mean",
            }
        )
        return g

    d1_loop = agg_stage("D1_Outpatient_Loop")
    d2_from_d1 = agg_stage("D2_SuggestedFromD1Decision")
    d2_loop = agg_stage("D2_Admission_Loop")

    # D2 stage totals = D1 suggestion pseudo-round + D2 admission loop
    d2_stage = pd.merge(d2_from_d1, d2_loop, on=["center", "model", "case_id"], how="outer")
    for col in ["D2_SuggestedFromD1Decision__requested_total", "D2_SuggestedFromD1Decision__matched_total", "D2_Admission_Loop__requested_total", "D2_Admission_Loop__matched_total"]:
        if col not in d2_stage.columns:
            d2_stage[col] = 0
    d2_stage["D2_Check__requested_total"] = d2_stage["D2_SuggestedFromD1Decision__requested_total"].fillna(0) + d2_stage[
        "D2_Admission_Loop__requested_total"
    ].fillna(0)
    d2_stage["D2_Check__matched_total"] = d2_stage["D2_SuggestedFromD1Decision__matched_total"].fillna(0) + d2_stage[
        "D2_Admission_Loop__matched_total"
    ].fillna(0)

    # Unique-count totals across D2 suggestion + D2 loop (for LLM合理性回填与手工核对)
    d2_unique = rounds.loc[rounds["stage"].isin(["D2_SuggestedFromD1Decision", "D2_Admission_Loop"])].copy()
    if d2_unique.empty:
        d2_unique = pd.DataFrame(columns=["center", "model", "case_id"])
    else:
        d2_unique["_matched_items"] = (
            d2_unique["judge_matched_items_raw"].map(to_list)
            if "judge_matched_items_raw" in d2_unique.columns
            else [[] for _ in range(len(d2_unique))]
        )
        d2_unique["_unexecuted_items"] = (
            d2_unique["judge_unexecuted_items_raw"].map(to_list)
            if "judge_unexecuted_items_raw" in d2_unique.columns
            else [[] for _ in range(len(d2_unique))]
        )
        d2_unique["_requested_items"] = d2_unique["_matched_items"] + d2_unique["_unexecuted_items"]
        d2_unique = d2_unique.groupby(["center", "model", "case_id"], as_index=False).agg(
            requested_unique_count=("_requested_items", union_len),
            matched_unique_count=("_matched_items", union_len),
            unmatched_unique_count=("_unexecuted_items", union_len),
        )
        d2_unique = d2_unique.rename(
            columns={
                "requested_unique_count": "D2_Check__requested_unique_count",
                "matched_unique_count": "D2_Check__matched_unique_count",
                "unmatched_unique_count": "D2_Check__unmatched_unique_count",
            }
        )

    # Merge into case metrics
    base = case_index.merge(gt_counts, on=["center", "case_id"], how="left")
    base = base.merge(d1_loop, on=["center", "model", "case_id"], how="left")
    base = base.merge(d2_stage, on=["center", "model", "case_id"], how="left")
    base = base.merge(d2_unique, on=["center", "model", "case_id"], how="left")

    def ensure_numeric_fill0(col: str, default: float = 0.0) -> None:
        if col not in base.columns:
            base[col] = default
        base[col] = pd.to_numeric(base[col], errors="coerce").fillna(default)

    def ensure_numeric_keepna(col: str) -> None:
        if col not in base.columns:
            base[col] = pd.NA
        base[col] = pd.to_numeric(base[col], errors="coerce")

    # Ensure required numeric columns exist (some stages may be fully missing for a model/center).
    ensure_numeric_fill0("gt_outpatient_effective_count", default=0.0)
    ensure_numeric_fill0("gt_admission_effective_count", default=0.0)

    ensure_numeric_fill0("D1_Outpatient_Loop__requested_total", default=0.0)
    ensure_numeric_keepna("D1_Outpatient_Loop__matched_total")
    ensure_numeric_keepna("D1_Outpatient_Loop__requested_unique_count")
    ensure_numeric_keepna("D1_Outpatient_Loop__matched_unique_count")
    ensure_numeric_keepna("D1_Outpatient_Loop__unmatched_unique_count")
    ensure_numeric_fill0("D1_Outpatient_Loop__executed_rounds", default=0.0)
    ensure_numeric_keepna("D1_Outpatient_Loop__ineff_rounds_by_zero")
    ensure_numeric_fill0("D1_Outpatient_Loop__judge_scored_rounds", default=0.0)

    ensure_numeric_fill0("D2_Check__requested_total", default=0.0)
    ensure_numeric_keepna("D2_Check__matched_total")
    ensure_numeric_keepna("D2_Check__requested_unique_count")
    ensure_numeric_keepna("D2_Check__matched_unique_count")
    ensure_numeric_keepna("D2_Check__unmatched_unique_count")
    ensure_numeric_fill0("D2_Admission_Loop__executed_rounds", default=0.0)
    ensure_numeric_keepna("D2_Admission_Loop__ineff_rounds_by_zero")
    ensure_numeric_fill0("D2_Admission_Loop__judge_scored_rounds", default=0.0)

    def safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
        den2 = den.where(den != 0)
        return num / den2

    # Check match rate (strict): matched / AI requested
    base["d1_check_match_rate"] = safe_div(base["D1_Outpatient_Loop__matched_total"], base["D1_Outpatient_Loop__requested_total"])
    base["d1_check_match_rate"] = base["d1_check_match_rate"].clip(lower=0, upper=1)
    base["d2_check_match_rate"] = safe_div(base["D2_Check__matched_total"], base["D2_Check__requested_total"])
    base["d2_check_match_rate"] = base["d2_check_match_rate"].clip(lower=0, upper=1)

    # Weighted (sum of matched / sum of requested), excluding NOT_EVALUATED cases.
    base["d1_check_match_rate_weight_num"] = base["D1_Outpatient_Loop__matched_total"].where(base["d1_check_match_rate"].notna())
    base["d1_check_match_rate_weight_den"] = base["D1_Outpatient_Loop__requested_total"].where(base["d1_check_match_rate"].notna())
    base["d2_check_match_rate_weight_num"] = base["D2_Check__matched_total"].where(base["d2_check_match_rate"].notna())
    base["d2_check_match_rate_weight_den"] = base["D2_Check__requested_total"].where(base["d2_check_match_rate"].notna())

    # Unique-count view (judge list union): matched_unique / requested_unique
    base["d1_check_match_rate_unique"] = safe_div(
        base["D1_Outpatient_Loop__matched_unique_count"], base["D1_Outpatient_Loop__requested_unique_count"]
    ).clip(lower=0, upper=1)
    base["d2_check_match_rate_unique"] = safe_div(base["D2_Check__matched_unique_count"], base["D2_Check__requested_unique_count"]).clip(
        lower=0, upper=1
    )

    # Do not treat Not_Evaluated as failure: mask metrics when stage wasn't executed.
    if "is_evaluated_inferred__D1_Outpatient_Loop" in base.columns:
        d1_eval = base["is_evaluated_inferred__D1_Outpatient_Loop"].astype(bool)
    else:
        d1_eval = base["D1_Outpatient_Loop__executed_rounds"] > 0
    base.loc[~d1_eval, "d1_check_match_rate"] = pd.NA
    base.loc[~d1_eval, "d1_check_match_rate_unique"] = pd.NA

    d2_eval = base["D2_Check__requested_total"] > 0
    base.loc[~d2_eval, "d2_check_match_rate"] = pd.NA
    d2_eval_unique = base["D2_Check__requested_unique_count"] > 0
    base.loc[~d2_eval_unique, "d2_check_match_rate_unique"] = pd.NA

    # Inefficiency (proxy)
    base["d1_inefficiency_by_zero"] = safe_div(base["D1_Outpatient_Loop__ineff_rounds_by_zero"], base["D1_Outpatient_Loop__executed_rounds"])
    base["d2_inefficiency_by_zero"] = safe_div(base["D2_Admission_Loop__ineff_rounds_by_zero"], base["D2_Admission_Loop__executed_rounds"])

    # Missing-judge flags (stage executed but not scorable)
    base["d1_check_match_not_scored"] = (base["D1_Outpatient_Loop__requested_total"] > 0) & (base["D1_Outpatient_Loop__matched_total"].isna())
    base["d2_check_match_not_scored"] = (base["D2_Check__requested_total"] > 0) & (base["D2_Check__matched_total"].isna())

    # Aggregate per center/model
    g = base.groupby(["center", "model"], as_index=False)
    by_center_model = g.agg(
        cases=("case_id", "count"),
        d1_check_match_rate_mean=("d1_check_match_rate", "mean"),
        d1_check_match_rate_n=("d1_check_match_rate", "count"),
        d1_check_match_rate_requested_n=("D1_Outpatient_Loop__requested_total", lambda s: int((pd.to_numeric(s, errors="coerce").fillna(0) > 0).sum())),
        d1_check_match_rate_not_scored_n=("d1_check_match_not_scored", "sum"),
        d2_check_match_rate_mean=("d2_check_match_rate", "mean"),
        d2_check_match_rate_n=("d2_check_match_rate", "count"),
        d2_check_match_rate_requested_n=("D2_Check__requested_total", lambda s: int((pd.to_numeric(s, errors="coerce").fillna(0) > 0).sum())),
        d2_check_match_rate_not_scored_n=("d2_check_match_not_scored", "sum"),
        d1_check_match_rate_weight_num=("d1_check_match_rate_weight_num", "sum"),
        d1_check_match_rate_weight_den=("d1_check_match_rate_weight_den", "sum"),
        d2_check_match_rate_weight_num=("d2_check_match_rate_weight_num", "sum"),
        d2_check_match_rate_weight_den=("d2_check_match_rate_weight_den", "sum"),
        d1_inefficiency_by_zero_mean=("d1_inefficiency_by_zero", "mean"),
        d1_inefficiency_by_zero_n=("d1_inefficiency_by_zero", "count"),
        d2_inefficiency_by_zero_mean=("d2_inefficiency_by_zero", "mean"),
        d2_inefficiency_by_zero_n=("d2_inefficiency_by_zero", "count"),
    )

    def _safe_weighted(num: pd.Series, den: pd.Series) -> pd.Series:
        den2 = den.where(den != 0)
        return (num / den2).astype("Float64")

    by_center_model["d1_check_match_rate_weighted"] = _safe_weighted(
        by_center_model["d1_check_match_rate_weight_num"], by_center_model["d1_check_match_rate_weight_den"]
    )
    by_center_model["d2_check_match_rate_weighted"] = _safe_weighted(
        by_center_model["d2_check_match_rate_weight_num"], by_center_model["d2_check_match_rate_weight_den"]
    )
    by_center_model = by_center_model.drop(
        columns=[
            "d1_check_match_rate_weight_num",
            "d1_check_match_rate_weight_den",
            "d2_check_match_rate_weight_num",
            "d2_check_match_rate_weight_den",
        ]
    )

    # --- Flow-based gate pass rates (separate from judge "continue" fields)
    stage_to_idx = {s: i for i, s in enumerate(STAGE_ORDER)}

    def _idx(s: Any) -> int:
        return stage_to_idx.get(str(s).strip(), -1)

    end_idx = base["flow_end_stage"].map(_idx) if "flow_end_stage" in base.columns else pd.Series([-1] * len(base))
    d1_dec_idx = stage_to_idx.get("D1_Outpatient_Decision", 1)
    d2_dec_idx = stage_to_idx.get("D2_Admission_Decision", 3)

    gate1_reached = base["has_output__D1_Outpatient_Decision"].astype(bool) if "has_output__D1_Outpatient_Decision" in base.columns else end_idx >= d1_dec_idx
    gate1_pass = gate1_reached & (end_idx > d1_dec_idx)
    gate2_reached = base["has_output__D2_Admission_Decision"].astype(bool) if "has_output__D2_Admission_Decision" in base.columns else end_idx >= d2_dec_idx
    gate2_pass = gate2_reached & (end_idx > d2_dec_idx)

    base["gate1_flow_reached"] = gate1_reached
    base["gate1_flow_pass"] = gate1_pass
    base["gate2_flow_reached"] = gate2_reached
    base["gate2_flow_pass"] = gate2_pass

    flow_agg = base.groupby(["center", "model"], as_index=False).agg(
        gate1_flow_reached_n=("gate1_flow_reached", "sum"),
        gate1_flow_pass_n=("gate1_flow_pass", "sum"),
        gate2_flow_reached_n=("gate2_flow_reached", "sum"),
        gate2_flow_pass_n=("gate2_flow_pass", "sum"),
    )
    by_center_model = by_center_model.merge(flow_agg, on=["center", "model"], how="left")

    def _safe_rate(num: pd.Series, den: pd.Series) -> pd.Series:
        den2 = den.where(den != 0)
        return (num / den2).astype("Float64")

    by_center_model["gate1_flow_pass_rate"] = _safe_rate(by_center_model["gate1_flow_pass_n"], by_center_model["gate1_flow_reached_n"])
    by_center_model["gate2_flow_pass_rate"] = _safe_rate(by_center_model["gate2_flow_pass_n"], by_center_model["gate2_flow_reached_n"])

    return base, by_center_model


def build_metric_tables(loaded: LoadedData, check_rounds: pd.DataFrame) -> MetricTables:
    case_index = build_case_index(loaded)
    gt_checks = build_gt_checks_table(loaded)
    metrics_by_case, metrics_by_center_model = compute_metrics(case_index, check_rounds, gt_checks)
    return MetricTables(
        case_index=case_index,
        check_rounds=check_rounds,
        gt_checks=gt_checks,
        metrics_by_case=metrics_by_case,
        metrics_by_center_model=metrics_by_center_model,
    )
