import argparse
import sys
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from tools.generate_figures import (
    _compute_calibration,
    _compute_calibration_points,
    _ensure_dir,
    _group_bar_plot_by_center,
    _load_summary_sheet,
    _plot_algorithmic,
    _plot_llm_metrics,
    _write_readme,
)
from tools.figure_stagewise import (
    STAGE_KEYS,
    _build_flow_case_table,
    _compute_special_case_counts,
    _organize_figures,
    _save_image_grid,
    _plot_alignment,
    _plot_calibration_reliability,
    _plot_confusion_matrices,
    _plot_llm_small_scale_metrics,
    _plot_llm_stage_metrics,
    _plot_manual_metrics,
    _plot_sankey_flow,
    _plot_stagewise_bars,
    _write_source_data,
)
from tools.build_doctor_review_report import _build_gate3_fail_map, _build_special_case_map


def _resolve_paths(args: argparse.Namespace) -> dict[str, Path]:
    project_root = Path(__file__).resolve().parents[2]
    run_id = args.run_id
    data_root = Path(args.data_root) if args.data_root else project_root / "data"
    summary_xlsx = (
        Path(args.summary_xlsx)
        if args.summary_xlsx
        else project_root / "outputs" / run_id / "summary" / "总览.xlsx"
    )
    llm_xlsx = (
        Path(args.llm_xlsx)
        if args.llm_xlsx
        else project_root / "outputs" / run_id / "summary" / "llm_results_gemini-2.5-pro__gala_api.xlsx"
    )
    llm_small_xlsx = (
        Path(args.llm_small_xlsx)
        if args.llm_small_xlsx
        else project_root
        / "outputs"
        / run_id
        / "summary"
        / "llm_results_gemini-3-pro-preview-thinking__gala_api_小规模汇总.xlsx"
    )
    doctor_report = (
        Path(args.doctor_report)
        if args.doctor_report
        else project_root / "outputs" / run_id / "summary" / "医生评测汇总.xlsx"
    )
    doctor_root = project_root.parent / "医生评测结果"
    out_dir = project_root / "outputs" / run_id / "figures"
    _ensure_dir(out_dir)
    return {
        "project_root": project_root,
        "run_id": run_id,
        "data_root": data_root,
        "summary_xlsx": summary_xlsx,
        "llm_xlsx": llm_xlsx,
        "llm_small_xlsx": llm_small_xlsx,
        "doctor_report": doctor_report,
        "doctor_root": doctor_root,
        "out_dir": out_dir,
    }


def _compute_algorithmic_stagewise_from_source(summary_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_xlsx = summary_dir / "metrics_source_data.xlsx"
    if not source_xlsx.exists():
        return pd.DataFrame(), pd.DataFrame()

    try:
        rounds = pd.read_excel(source_xlsx, sheet_name="check_rounds")
        judge = pd.read_excel(source_xlsx, sheet_name="judge_scores_by_case")
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

    if rounds.empty or judge.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Loop stage overall score: per-case mean across rounds, then center-model mean
    loop = rounds.copy()
    loop["judge_composite_score_raw"] = pd.to_numeric(loop.get("judge_composite_score_raw"), errors="coerce")
    loop["inefficient_round_by_zero"] = pd.to_numeric(loop.get("inefficient_round_by_zero"), errors="coerce")
    loop_case = (
        loop.groupby(["center", "model", "case_id", "stage"], as_index=False)
        .agg(loop_overall=("judge_composite_score_raw", "mean"), loop_ineff=("inefficient_round_by_zero", "mean"))
    )
    stage_map = {
        "D1_Outpatient_Loop": "D1_Loop",
        "D2_Admission_Loop": "D2_Loop",
    }
    loop_case["Stage"] = loop_case["stage"].map(stage_map)
    loop_case = loop_case[loop_case["Stage"].notna()]

    loop_score = (
        loop_case.groupby(["center", "model", "Stage"], as_index=False)["loop_overall"]
        .mean(numeric_only=True)
        .rename(columns={"center": "Center", "model": "Model", "loop_overall": "Value"})
    )
    loop_ineff = (
        loop_case.groupby(["center", "model", "Stage"], as_index=False)["loop_ineff"]
        .mean(numeric_only=True)
        .rename(columns={"center": "Center", "model": "Model", "loop_ineff": "Value"})
    )

    # Decision stage overall score
    dec_rows = []
    col_map = {
        "D1_Decision": "gate1_overall_score",
        "D2_Decision": "gate2_overall_score",
        "D3_Decision": "d3_overall_score",
        "D4_Plan": "d4_overall_score",
    }
    for stage, col in col_map.items():
        if col not in judge.columns:
            continue
        sub = judge[["center", "model", col]].copy()
        sub[col] = pd.to_numeric(sub[col], errors="coerce")
        agg = sub.groupby(["center", "model"], as_index=False)[col].mean(numeric_only=True)
        agg["Stage"] = stage
        agg = agg.rename(columns={"center": "Center", "model": "Model", col: "Value"})
        dec_rows.append(agg[["Center", "Model", "Stage", "Value"]])

    decision_score = pd.concat(dec_rows, ignore_index=True) if dec_rows else pd.DataFrame(columns=["Center", "Model", "Stage", "Value"])

    judge_scores = pd.concat([loop_score, decision_score], ignore_index=True)

    # Loop ineff chart shows D1/D2 only; fill other stages as NA in plotting stage
    return judge_scores, loop_ineff


def _compute_stage_no_exit_rates(doctor_report: Path) -> pd.DataFrame:
    if not doctor_report.exists():
        return pd.DataFrame(columns=["Center", "Model", "Stage", "Value"])
    try:
        df = pd.read_excel(doctor_report, sheet_name="通过退出明细", engine="openpyxl")
    except Exception:
        return pd.DataFrame(columns=["Center", "Model", "Stage", "Value"])
    if df.empty:
        return pd.DataFrame(columns=["Center", "Model", "Stage", "Value"])

    center_col = "中心" if "中心" in df.columns else "Center"
    model_col = "模型名称" if "模型名称" in df.columns else "Model"
    case_col = "病例ID" if "病例ID" in df.columns else "CaseID"
    stage_cols = ["D1_Loop", "D1_Decision", "D2_Loop", "D2_Decision", "D3_Decision", "D4_Plan"]
    for col in stage_cols:
        if col not in df.columns:
            df[col] = ""

    # drop D1 special cases entirely
    special_map = _build_special_case_map(Path(doctor_report).parents[2] / "data")
    special_triplets = {
        (center, model, cid)
        for (center, model), ids in special_map.items()
        for cid in ids
    }
    if case_col in df.columns:
        triplets = list(
            zip(
                df[center_col].astype(str),
                df[model_col].astype(str),
                df[case_col].astype(str),
            )
        )
        mask_special = [t in special_triplets for t in triplets]
        df = df.loc[~pd.Series(mask_special, index=df.index)]

    # gate3 fail cases: exclude D4 stage (treat as not reached)
    gate3_triplets = _build_gate3_fail_map(Path(doctor_report).parents[2] / "data")

    exit_tokens = ["退出", "不通过", "失败", "终止", "特殊"]
    rows: list[dict[str, Any]] = []
    for (center, model), sub in df.groupby([center_col, model_col]):
        sub = sub.copy()
        total_cases = int(sub[case_col].nunique()) if case_col in sub.columns else len(sub)
        if case_col in sub.columns:
            trip = list(zip(sub[center_col].astype(str), sub[model_col].astype(str), sub[case_col].astype(str)))
            gate3_mask = pd.Series([t in gate3_triplets for t in trip], index=sub.index)
        else:
            gate3_mask = pd.Series([False] * len(sub), index=sub.index)
        for stage in stage_cols:
            vals = sub[stage].fillna("").astype(str)
            reached = vals.str.strip().ne("") & ~vals.str.contains("未经过", regex=False)
            if stage == "D4_Plan":
                reached = reached & ~gate3_mask
            if not reached.any():
                rows.append({"Center": center, "Model": model, "Stage": stage, "Value": np.nan if total_cases == 0 else 0.0})
                continue
            no_exit = reached.copy()
            for token in exit_tokens:
                no_exit = no_exit & ~vals.str.contains(token, regex=False)
            rate = float(no_exit.sum() / total_cases) if total_cases > 0 else np.nan
            rows.append({"Center": center, "Model": model, "Stage": stage, "Value": rate})

    return pd.DataFrame(rows)


def _plot_algorithmic_stagewise_chart(
    long_df: pd.DataFrame,
    out_path_prefix: Path,
    title_prefix: str,
    ylabel: str,
    stage_order: list[str],
    ylim: tuple[float, float] | None = (0, 1),
) -> None:
    if long_df.empty:
        return

    centers = [c for c in ["佛山", "武汉", "新疆"] if c in set(long_df["Center"].astype(str).tolist())]
    models_order = [
        "claude-opus-4-1-20250805-thinking",
        "deepseek-v3-1-think-250821",
        "gemini-2.5-pro",
        "gpt-5-2025-08-07",
        "grok-4",
    ]

    image_paths: list[Path] = []
    labels: list[str] = []
    for center in centers:
        sub = long_df[long_df["Center"] == center].copy()
        if sub.empty:
            continue
        pivot = (
            sub.pivot_table(index="Model", columns="Stage", values="Value", aggfunc="mean")
            .reindex(index=models_order)
            .reindex(columns=stage_order)
        )

        fig, ax = plt.subplots(figsize=(9.6, 9.6))
        x = np.arange(len(models_order), dtype=float)
        width = 0.11 if len(stage_order) >= 6 else 0.18
        cmap = plt.get_cmap("tab10")

        max_val = 0.0
        for i, stage in enumerate(stage_order):
            vals = pivot[stage].astype(float).to_numpy() if stage in pivot.columns else np.full(len(models_order), np.nan)
            bars = ax.bar(
                x + (i - (len(stage_order) - 1) / 2) * width,
                np.where(np.isnan(vals), 0.0, vals),
                width=width,
                color=[cmap(j % 10) for j in range(len(models_order))],
                alpha=0.35 + 0.55 * (i / max(1, len(stage_order) - 1)),
                label=stage,
                edgecolor="white",
                linewidth=0.5,
            )
            for b, v in zip(bars, vals):
                cx = b.get_x() + b.get_width() / 2
                if np.isnan(v):
                    b.set_facecolor((0.92, 0.92, 0.92, 1.0))
                    b.set_edgecolor((0.55, 0.55, 0.55, 1.0))
                    b.set_hatch("///")
                    ax.text(cx, 0.01, "NA", ha="center", va="bottom", fontsize=6.6, color="#666666", rotation=90)
                else:
                    ax.text(cx, float(v) + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=6.8)
                    if np.isfinite(v):
                        max_val = max(max_val, float(v))

        ax.set_xticks(x)
        ax.set_xticklabels(models_order, rotation=24, ha="right")
        ax.set_title(f"{title_prefix} - {center}")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", linestyle=":", alpha=0.25)
        if ylim is None:
            top = max(0.05, max_val * 1.2 + 0.02)
            ax.set_ylim(0, min(1.0, top))
        else:
            ax.set_ylim(*ylim)
        ax.legend(loc="upper right", fontsize=7.5, ncol=2)
        fig.tight_layout()
        out_path = out_path_prefix.parent / f"{out_path_prefix.name}_{center}.png"
        fig.savefig(out_path, dpi=420)
        plt.close(fig)
        image_paths.append(out_path)
        labels.append(center)

        _write_source_data(
            out_path_prefix.parent,
            out_path.stem,
            {"raw": sub, "pivot": pivot.reset_index()},
            {
                "figure": out_path.name,
                "description": title_prefix,
                "center": center,
                "stage_order": ",".join(stage_order),
            },
        )

    if len(image_paths) > 1:
        _save_image_grid(
            image_paths,
            out_path_prefix.parent / f"{out_path_prefix.name}_grid.png",
            title=title_prefix,
            labels=labels,
            ncols=len(image_paths),
        )
        _write_source_data(
            out_path_prefix.parent,
            f"{out_path_prefix.name}_grid",
            {"raw": long_df},
            {
                "figure": f"{out_path_prefix.name}_grid.png",
                "description": f"{title_prefix} (grid)",
                "stage_order": ",".join(stage_order),
            },
        )


def _generate_algorithmic_stagewise_figures(paths: dict[str, Path]) -> None:
    summary_dir = paths["project_root"] / "outputs" / paths["run_id"] / "summary"
    out_alg = paths["out_dir"] / "algorithmic"
    _ensure_dir(out_alg)
    stage_order = ["D1_Loop", "D1_Decision", "D2_Loop", "D2_Decision", "D3_Decision", "D4_Plan"]
    loop_stage_order = ["D1_Loop", "D2_Loop"]

    judge_scores, loop_ineff = _compute_algorithmic_stagewise_from_source(summary_dir)
    if not judge_scores.empty:
        _plot_algorithmic_stagewise_chart(
            judge_scores,
            out_alg / "algorithmic_judge_scores_stagewise",
            "Judge Overall Score (6 stages)",
            "Score (0-1)",
            stage_order,
            ylim=(0, 1),
        )
    if not loop_ineff.empty:
        _plot_algorithmic_stagewise_chart(
            loop_ineff,
            out_alg / "algorithmic_loop_inefficiency_stagewise",
            "Loop Inefficiency (0-match)",
            "Rate",
            loop_stage_order,
            ylim=None,
        )

    # Stage non-exit rate (from doctor report)
    no_exit = _compute_stage_no_exit_rates(paths["doctor_report"])
    if not no_exit.empty:
        _plot_algorithmic_stagewise_chart(
            no_exit,
            out_alg / "algorithmic_stage_no_exit_rate",
            "Stage Non-exit Rate (6 stages)",
            "Rate",
            stage_order,
            ylim=(0, 1),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate figures in small chunks to avoid long runtimes.")
    parser.add_argument("--run-id", default="latest")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--summary-xlsx", default=None)
    parser.add_argument("--llm-xlsx", default=None)
    parser.add_argument("--llm-small-xlsx", default=None)
    parser.add_argument("--doctor-report", default=None)
    parser.add_argument(
        "--part",
        required=True,
        choices=[
            "algorithmic",
            "llm",
            "llm_small",
            "manual_alignment",
            "sankey",
            "special",
            "calibration",
            "readme",
        ],
    )
    parser.add_argument("--center", default=None, help="Optional center filter (for sankey only)")
    parser.add_argument("--model", default=None, help="Optional model filter (for sankey only)")
    args = parser.parse_args()
    paths = _resolve_paths(args)

    if args.part == "algorithmic":
        summary_df = _load_summary_sheet(paths["summary_xlsx"])
        algo_summary = _plot_algorithmic(
            summary_df,
            paths["out_dir"],
            paths["data_root"],
            paths["summary_xlsx"],
        )
        algo_summary.to_csv(
            paths["project_root"] / "outputs" / paths["run_id"] / "summary" / "algorithmic_metrics_summary_en.csv",
            index=False,
        )
        _generate_algorithmic_stagewise_figures(paths)
        return

    if args.part == "llm":
        llm_summary = _plot_llm_metrics(paths["llm_xlsx"], paths["out_dir"])
        _plot_llm_stage_metrics(paths["llm_xlsx"], paths["out_dir"])
        if not llm_summary.empty:
            llm_summary.to_csv(
                paths["project_root"] / "outputs" / paths["run_id"] / "summary" / "llm_metrics_summary_en.csv",
                index=False,
            )
        return

    if args.part == "llm_small":
        _plot_llm_small_scale_metrics(paths["llm_small_xlsx"], paths["out_dir"])
        return

    if args.part == "manual_alignment":
        _plot_manual_metrics(paths["doctor_report"], paths["out_dir"])
        _plot_alignment(paths["doctor_report"], paths["out_dir"])
        _plot_confusion_matrices(paths["doctor_root"], paths["data_root"], paths["out_dir"], paths["run_id"])
        return

    if args.part == "sankey":
        flow_cases = _build_flow_case_table(paths["data_root"], paths["doctor_report"])
        if flow_cases.empty:
            return
        if args.center:
            flow_cases = flow_cases[flow_cases["Center"] == args.center]
        if args.model:
            flow_cases = flow_cases[flow_cases["Model"] == args.model]
        if flow_cases.empty:
            return
        _plot_sankey_flow(flow_cases, paths["out_dir"])
        return

    if args.part == "special":
        special_df = _compute_special_case_counts(paths["data_root"], paths["doctor_report"])
        if not special_df.empty:
            special_df.to_csv(
                paths["project_root"] / "outputs" / paths["run_id"] / "summary" / "special_d1_case_counts_en.csv",
                index=False,
            )
            _group_bar_plot_by_center(
                special_df[["Center", "Model", "Special D1 Cases"]],
                title="D1 Special Case Count by Model (by Center)",
                ylabel="Count",
                output_path=paths["out_dir"] / "special_d1_case_counts_by_model.png",
            )
        return

    if args.part == "calibration":
        calib_df = _compute_calibration(paths["data_root"])
        calib_points = pd.DataFrame()
        if not calib_df.empty:
            calib_df.to_csv(
                paths["project_root"] / "outputs" / paths["run_id"] / "summary" / "calibration_summary_en.csv",
                index=False,
            )
            calib_long = calib_df.rename(columns={"ECE": "Value"})
            _plot_stagewise_bars(
                calib_long,
                STAGE_KEYS,
                paths["out_dir"],
                output_prefix="calibration_ece_stagewise",
                title_prefix="Calibration Error (ECE)",
                ylabel="ECE",
                value_col="Value",
                ylim=(0, 1),
            )
            calib_points = _compute_calibration_points(paths["data_root"])
            _write_source_data(
                paths["out_dir"],
                "calibration_ece_stagewise",
                {"summary": calib_df, "raw_points": calib_points},
                {"description": "ECE 按阶段与中心聚合"},
            )
        if not calib_points.empty:
            _plot_calibration_reliability(calib_points, paths["out_dir"], paths["data_root"])
        return

    if args.part == "readme":
        _write_readme(paths["out_dir"])
        _organize_figures(paths["out_dir"])
        return


if __name__ == "__main__":
    main()
