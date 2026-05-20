"""Run sample rule audit for key derived artifacts.

This audit is intentionally pragmatic:
- It checks that D1 anomaly cases are excluded where required.
- It checks that Gate3-fail cases do not contribute to D4 metrics.

Outputs:
- analysis_viz/docs/sample_rule_audit.csv (overwrite each run)
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "analysis_viz" / "docs"
AUDIT_CSV = DOCS / "sample_rule_audit.csv"

RAW_METRICS_SOURCE = ROOT / "analysis_viz" / "data" / "raw" / "metrics_source_data.xlsx"
RAW_DOCTOR_SUMMARY = ROOT / "analysis_viz" / "data" / "raw" / "医生评测汇总.xlsx"

PAPER_FIGDATA_DIR = ROOT / "analysis_viz" / "data" / "derived" / "figdata" / "paper"


def _load_d1_anomaly_set() -> set[tuple[str, str, str]]:
    df = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="d1_decision_anomalies")
    return set(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))


def _load_gate3_fail_set() -> set[tuple[str, str, str]]:
    df = pd.read_excel(RAW_DOCTOR_SUMMARY, sheet_name="人工评分_D4Gate3不通过")
    df = df.rename(columns={"中心": "center", "模型名称": "model", "病例ID": "case_id"})
    return set(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))


def _add_row(
    rows: list[dict[str, str]],
    *,
    artifact_type: str,
    artifact_relpath: str,
    check_name: str,
    passed: bool,
    details: str,
) -> None:
    rows.append(
        {
            "artifact_type": artifact_type,
            "artifact_relpath": artifact_relpath,
            "check_name": check_name,
            "pass": str(passed),
            "details": details,
        }
    )


def _check_d1_absent(df: pd.DataFrame, d1_set: set[tuple[str, str, str]], cols: tuple[str, str, str]) -> tuple[bool, str]:
    c_center, c_model, c_case = cols
    if not all(c in df.columns for c in cols):
        return False, f"missing columns: {cols}"
    keys = set(zip(df[c_center].astype(str), df[c_model].astype(str), df[c_case].astype(str)))
    hit = keys & d1_set
    if hit:
        sample = sorted(list(hit))[:5]
        return False, f"found {len(hit)} d1 anomaly keys, sample={sample}"
    return True, ""


def _check_gate3_d4_absent(df: pd.DataFrame, gate3_set: set[tuple[str, str, str]], cols: tuple[str, str, str], stage_col: str) -> tuple[bool, str]:
    c_center, c_model, c_case = cols
    if not all(c in df.columns for c in cols + (stage_col,)):
        return False, f"missing columns: {cols + (stage_col,)}"
    sub = df[df[stage_col].astype(str).isin(["D4", "D4_Rehab_Plan", "D4_Plan", "随访计划"])].copy()
    if sub.empty:
        return True, "no D4 rows"
    keys = set(zip(sub[c_center].astype(str), sub[c_model].astype(str), sub[c_case].astype(str)))
    hit = keys & gate3_set
    if hit:
        sample = sorted(list(hit))[:5]
        return False, f"found {len(hit)} gate3-fail keys in D4 rows, sample={sample}"
    return True, ""


def _check_blank_d4_for_excluded_keys(
    df_used: pd.DataFrame,
    df_excluded: pd.DataFrame,
    *,
    d4_col: str,
    cols: tuple[str, str, str] = ("center", "model", "case_id"),
) -> tuple[bool, str]:
    c_center, c_model, c_case = cols
    required = {c_center, c_model, c_case, d4_col}
    if not required.issubset(set(df_used.columns)):
        return False, f"used missing columns: {sorted(list(required - set(df_used.columns)))}"
    if not {c_center, c_model, c_case}.issubset(set(df_excluded.columns)):
        return False, "excluded missing key columns"

    excluded_keys = set(
        zip(
            df_excluded[c_center].astype(str),
            df_excluded[c_model].astype(str),
            df_excluded[c_case].astype(str),
        )
    )
    if not excluded_keys:
        return True, "no excluded keys"

    used = df_used[[c_center, c_model, c_case, d4_col]].copy()
    used[d4_col] = used[d4_col].fillna("").astype(str)
    used_idx = used.set_index([c_center, c_model, c_case])[d4_col]

    violations: list[tuple[str, str, str]] = []
    missing: list[tuple[str, str, str]] = []
    for key in excluded_keys:
        if key not in used_idx.index:
            missing.append(key)
            continue
        v = used_idx.loc[key]
        if str(v).strip() != "":
            violations.append(key)

    if missing:
        sample = sorted(missing)[:5]
        return False, f"missing {len(missing)} excluded keys in used sheet, sample={sample}"
    if violations:
        sample = sorted(violations)[:5]
        return False, f"found {len(violations)} non-blank D4 values for excluded keys, sample={sample}"
    return True, ""


def main() -> None:
    d1_set = _load_d1_anomaly_set()
    gate3_set = _load_gate3_fail_set()

    rows: list[dict[str, str]] = []

    # Paper Fig3 derived sources
    fig3_check = PAPER_FIGDATA_DIR / "Fig3__check_match_rate_source.xlsx"
    if fig3_check.exists():
        df_used = pd.read_excel(fig3_check, sheet_name="detail_used")
        ok, msg = _check_d1_absent(df_used, d1_set, ("center", "model", "case_id"))
        _add_row(
            rows,
            artifact_type="figdata",
            artifact_relpath="analysis_viz/data/derived/figdata/paper/Fig3__check_match_rate_source.xlsx#detail_used",
            check_name="exclude_d1",
            passed=ok,
            details=msg,
        )
    else:
        _add_row(
            rows,
            artifact_type="figdata",
            artifact_relpath="analysis_viz/data/derived/figdata/paper/Fig3__check_match_rate_source.xlsx",
            check_name="exists",
            passed=False,
            details="missing file",
        )

    fig3_loop = PAPER_FIGDATA_DIR / "Fig3__loop_inefficiency_source.xlsx"
    if fig3_loop.exists():
        df_used = pd.read_excel(fig3_loop, sheet_name="detail_used")
        ok, msg = _check_d1_absent(df_used, d1_set, ("center", "model", "case_id"))
        _add_row(
            rows,
            artifact_type="figdata",
            artifact_relpath="analysis_viz/data/derived/figdata/paper/Fig3__loop_inefficiency_source.xlsx#detail_used",
            check_name="exclude_d1",
            passed=ok,
            details=msg,
        )
    else:
        _add_row(
            rows,
            artifact_type="figdata",
            artifact_relpath="analysis_viz/data/derived/figdata/paper/Fig3__loop_inefficiency_source.xlsx",
            check_name="exists",
            passed=False,
            details="missing file",
        )

    # Derived sankey source
    for label, sankey in [
        (
            "outputs_latest",
            ROOT
            / "analysis_viz"
            / "data"
            / "derived"
            / "figdata"
            / "outputs_latest"
            / "sankey"
            / "Fig7__sankey_flow_source.xlsx",
        ),
        (
            "paper",
            ROOT
            / "analysis_viz"
            / "data"
            / "derived"
            / "figdata"
            / "paper"
            / "Fig7__sankey_flow_source.xlsx",
        ),
    ]:
        rel = f"analysis_viz/data/derived/figdata/{label}/sankey/Fig7__sankey_flow_source.xlsx"
        if label == "paper":
            rel = "analysis_viz/data/derived/figdata/paper/Fig7__sankey_flow_source.xlsx"
        if not sankey.exists():
            _add_row(
                rows,
                artifact_type="figdata",
                artifact_relpath=rel,
                check_name="exists",
                passed=False,
                details="missing file",
            )
            continue

        df_used = pd.read_excel(sankey, sheet_name="detail_used")
        ok, msg = _check_d1_absent(df_used, d1_set, ("center", "model", "case_id"))
        _add_row(
            rows,
            artifact_type="figdata",
            artifact_relpath=f"{rel}#detail_used",
            check_name="exclude_d1",
            passed=ok,
            details=msg,
        )

        # Gate3 fail -> D4 blanked audit (sankey uses explicit excluded sheet).
        df_ex = pd.read_excel(sankey, sheet_name="excluded_d3_fail_d4_blank")
        ok2, msg2 = _check_blank_d4_for_excluded_keys(df_used, df_ex, d4_col="随访计划")
        _add_row(
            rows,
            artifact_type="figdata",
            artifact_relpath=f"{rel}#detail_used",
            check_name="exclude_gate3_d4",
            passed=ok2,
            details=msg2,
        )

    # LLM derived sources
    metric_checks: list[tuple[str, str, tuple[str, ...]]] = [
        (
            "analysis_viz/data/derived/metrics/llm_reasoning_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/llm_consistency_source.xlsx",
            "stage",
            ("fact_detail_used", "cross_detail_used"),
        ),
        (
            "analysis_viz/data/derived/metrics/llm_memory_source.xlsx",
            "stage",
            ("detail_used",),
        ),
    ]
    for rel, stage_col, sheets in metric_checks:
        path = ROOT / rel
        if not path.exists():
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=rel,
                check_name="exists",
                passed=False,
                details="missing file",
            )
            continue

        for sheet in sheets:
            df_used = pd.read_excel(path, sheet_name=sheet)
            ok, msg = _check_d1_absent(df_used, d1_set, ("center", "model", "case_id"))
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=f"{rel}#{sheet}",
                check_name="exclude_d1",
                passed=ok,
                details=msg,
            )

            ok2, msg2 = _check_gate3_d4_absent(
                df_used,
                gate3_set,
                ("center", "model", "case_id"),
                stage_col,
            )
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=f"{rel}#{sheet}",
                check_name="exclude_gate3_d4",
                passed=ok2,
                details=msg2,
            )

    # Algorithmic derived sources
    algo_checks: list[tuple[str, str, tuple[str, ...]]] = [
        (
            "analysis_viz/data/derived/metrics/algorithmic/algorithmic_check_match_rate_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/algorithmic/algorithmic_loop_inefficiency_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/algorithmic/algorithmic_stage_pass_rate_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/algorithmic/algorithmic_judge_scores_by_stage_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/algorithmic/algorithmic_judge_score_pathways_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/algorithmic/algorithmic_judge_scores_stagewise_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/algorithmic/algorithmic_loop_inefficiency_stagewise_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/algorithmic/algorithmic_stage_no_exit_rate_source.xlsx",
            "stage",
            ("detail_used",),
        ),
    ]
    for rel, stage_col, sheets in algo_checks:
        path = ROOT / rel
        if not path.exists():
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=rel,
                check_name="exists",
                passed=False,
                details="missing file",
            )
            continue

        for sheet in sheets:
            df_used = pd.read_excel(path, sheet_name=sheet)
            ok, msg = _check_d1_absent(df_used, d1_set, ("center", "model", "case_id"))
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=f"{rel}#{sheet}",
                check_name="exclude_d1",
                passed=ok,
                details=msg,
            )

            if stage_col not in df_used.columns:
                _add_row(
                    rows,
                    artifact_type="metric",
                    artifact_relpath=f"{rel}#{sheet}",
                    check_name="exclude_gate3_d4",
                    passed=True,
                    details="n/a (no stage column)",
                )
            else:
                ok2, msg2 = _check_gate3_d4_absent(
                    df_used,
                    gate3_set,
                    ("center", "model", "case_id"),
                    stage_col,
                )
                _add_row(
                    rows,
                    artifact_type="metric",
                    artifact_relpath=f"{rel}#{sheet}",
                    check_name="exclude_gate3_d4",
                    passed=ok2,
                    details=msg2,
                )

    # Calibration derived sources
    calib_checks: list[tuple[str, str, tuple[str, ...]]] = [
        (
            "analysis_viz/data/derived/metrics/calibration/calibration_ece_stagewise_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/calibration/calibration_reliability_stagewise_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/calibration/calibration_bubble_check_stagewise_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/calibration/calibration_bubble_diagnosis_stagewise_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/calibration/calibration_bubble_plan_stagewise_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/calibration/calibration_line_overall_stagewise_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/calibration/calibration_line_check_stagewise_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/calibration/calibration_line_diagnosis_stagewise_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/calibration/calibration_line_plan_stagewise_source.xlsx",
            "stage",
            ("detail_used",),
        ),
    ]
    for rel, stage_col, sheets in calib_checks:
        path = ROOT / rel
        if not path.exists():
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=rel,
                check_name="exists",
                passed=False,
                details="missing file",
            )
            continue

        for sheet in sheets:
            df_used = pd.read_excel(path, sheet_name=sheet)
            ok, msg = _check_d1_absent(df_used, d1_set, ("center", "model", "case_id"))
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=f"{rel}#{sheet}",
                check_name="exclude_d1",
                passed=ok,
                details=msg,
            )

            ok2, msg2 = _check_gate3_d4_absent(
                df_used,
                gate3_set,
                ("center", "model", "case_id"),
                stage_col,
            )
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=f"{rel}#{sheet}",
                check_name="exclude_gate3_d4",
                passed=ok2,
                details=msg2,
            )

    # Manual derived sources
    manual_checks: list[tuple[str, str, tuple[str, ...]]] = [
        (
            "analysis_viz/data/derived/metrics/manual/manual_result_quality_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/manual/manual_reasoning_quality_source.xlsx",
            "stage",
            ("detail_used",),
        ),
    ]
    for rel, stage_col, sheets in manual_checks:
        path = ROOT / rel
        if not path.exists():
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=rel,
                check_name="exists",
                passed=False,
                details="missing file",
            )
            continue

        for sheet in sheets:
            df_used = pd.read_excel(path, sheet_name=sheet)
            ok, msg = _check_d1_absent(df_used, d1_set, ("center", "model", "case_id"))
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=f"{rel}#{sheet}",
                check_name="exclude_d1",
                passed=ok,
                details=msg,
            )

            ok2, msg2 = _check_gate3_d4_absent(
                df_used,
                gate3_set,
                ("center", "model", "case_id"),
                stage_col,
            )
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=f"{rel}#{sheet}",
                check_name="exclude_gate3_d4",
                    passed=ok2,
                    details=msg2,
                )

    # Alignment derived sources (case-level audit-friendly rebuild)
    alignment_checks: list[tuple[str, str, tuple[str, ...]]] = [
        (
            "analysis_viz/data/derived/metrics/alignment/alignment_result_vs_judge_case_level_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/alignment/alignment_reasoning_vs_llm_case_level_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/alignment/alignment_doctor_consensus_result_source.xlsx",
            "stage",
            ("detail_used",),
        ),
        (
            "analysis_viz/data/derived/metrics/alignment/alignment_doctor_consensus_reasoning_source.xlsx",
            "stage",
            ("detail_used",),
        ),
    ]
    for rel, stage_col, sheets in alignment_checks:
        path = ROOT / rel
        if not path.exists():
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=rel,
                check_name="exists",
                passed=False,
                details="missing file",
            )
            continue

        for sheet in sheets:
            df_used = pd.read_excel(path, sheet_name=sheet)
            ok, msg = _check_d1_absent(df_used, d1_set, ("center", "model", "case_id"))
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=f"{rel}#{sheet}",
                check_name="exclude_d1",
                passed=ok,
                details=msg,
            )

            ok2, msg2 = _check_gate3_d4_absent(
                df_used,
                gate3_set,
                ("center", "model", "case_id"),
                stage_col,
            )
            _add_row(
                rows,
                artifact_type="metric",
                artifact_relpath=f"{rel}#{sheet}",
                check_name="exclude_gate3_d4",
                passed=ok2,
                details=msg2,
            )

    DOCS.mkdir(parents=True, exist_ok=True)
    with AUDIT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["artifact_type", "artifact_relpath", "check_name", "pass", "details"],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


if __name__ == "__main__":
    main()
