from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from tools.figure_stagewise import _write_source_data

def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _group_bar_plot(
    df: pd.DataFrame,
    title: str,
    ylabel: str,
    output_path: Path,
    ylim: tuple[float, float] | None = None,
) -> None:
    if df.empty:
        return
    ax = df.plot(kind="bar", figsize=(12, 6))
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Model")
    ax.legend(loc="best")
    if ylim:
        ax.set_ylim(*ylim)
    plt.xticks(rotation=35, ha="right")
    plt.tight_layout(rect=(0, 0.08, 1, 0.95))
    plt.savefig(output_path, dpi=200)
    plt.close()


MODEL_ORDER = [
    "claude-opus-4-1-20250805-thinking",
    "deepseek-v3-1-think-250821",
    "gemini-2.5-pro",
    "gpt-5-2025-08-07",
    "grok-4",
]
CENTER_ORDER = ["佛山", "武汉", "新疆"]
CENTER_LABELS = {"佛山": "Foshan", "武汉": "Wuhan", "新疆": "Xinjiang"}


def _model_order(models: pd.Series) -> list[str]:
    seen = list(dict.fromkeys(models.dropna().tolist()))
    ordered = [m for m in MODEL_ORDER if m in seen]
    return ordered + [m for m in seen if m not in ordered]


def _center_order(centers: pd.Series) -> list[str]:
    seen = list(dict.fromkeys(centers.dropna().tolist()))
    ordered = [c for c in CENTER_ORDER if c in seen]
    return ordered + [c for c in seen if c not in ordered]


def _group_bar_plot_by_center(
    df: pd.DataFrame,
    title: str,
    ylabel: str,
    output_path: Path,
    ylim: tuple[float, float] | None = None,
    center_order: list[str] | None = None,
    model_order: list[str] | None = None,
) -> None:
    if df.empty:
        return
    metric_cols = [c for c in df.columns if c not in {"Center", "Model"}]
    if not metric_cols:
        return
    centers = center_order or _center_order(df["Center"])
    models = model_order or _model_order(df["Model"])
    fig, axes = plt.subplots(1, len(centers), figsize=(7.5 * len(centers), 5.8), sharey=True)
    if len(centers) == 1:
        axes = [axes]
    for ax, center in zip(axes, centers):
        subset = df[df["Center"] == center].copy()
        if subset.empty:
            continue
        subset = subset.set_index("Model").reindex(models)
        bars = subset[metric_cols].plot(kind="bar", ax=ax)
        ax.set_title(CENTER_LABELS.get(center, center))
        ax.set_xlabel("Model")
        ax.set_ylabel(ylabel if ax is axes[0] else "")
        ax.tick_params(axis="x", rotation=35, labelsize=9)
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        if ylim:
            ax.set_ylim(*ylim)
        # annotate values (NA for missing)
        plot_vals = subset[metric_cols]
        for container_idx, container in enumerate(bars.containers):
            if container_idx >= len(metric_cols):
                continue
            col = metric_cols[container_idx]
            col_vals = plot_vals[col].tolist()
            for bar, val in zip(container, col_vals):
                x = bar.get_x() + bar.get_width() / 2
                if pd.isna(val):
                    ax.text(x, (ylim[0] if ylim else 0) + 0.01, "NA", ha="center", va="bottom", fontsize=7, color="#666666", rotation=90)
                else:
                    ax.text(x, float(val) + 0.01, f"{float(val):.2f}", ha="center", va="bottom", fontsize=7)
        if ax.get_legend() is not None:
            ax.get_legend().remove()
    handles, labels = axes[0].get_legend_handles_labels()
    if len(labels) > 1:
        fig.legend(
            handles,
            labels,
            loc="upper center",
            ncol=min(len(labels), 4),
            bbox_to_anchor=(0.5, 0.93),
        )
        top_pad = 0.82
    else:
        top_pad = 0.86
    fig.suptitle(title, y=0.98)
    fig.tight_layout(rect=(0, 0.16, 1, top_pad))
    plt.savefig(output_path, dpi=1200)
    plt.close()


def _plot_loop_inefficiency_by_center(
    df: pd.DataFrame,
    title: str,
    ylabel: str,
    output_path: Path,
    center_order: list[str],
    model_order: list[str],
    value_cols: tuple[str, str],
    count_cols: tuple[str, str],
) -> None:
    if df.empty:
        return
    centers = center_order or _center_order(df["Center"])
    models = model_order or _model_order(df["Model"])
    colors = [plt.get_cmap("tab10")(0), plt.get_cmap("tab10")(1)]
    fig, axes = plt.subplots(1, len(centers), figsize=(7.5 * len(centers), 5.8), sharey=True)
    if len(centers) == 1:
        axes = [axes]
    max_val = 0.0
    for ax, center in zip(axes, centers):
        subset = df[df["Center"] == center].copy()
        if subset.empty:
            continue
        subset = subset.set_index("Model").reindex(models)
        x = np.arange(len(models), dtype=float)
        width = 0.32
        for idx, (val_col, cnt_col) in enumerate(zip(value_cols, count_cols)):
            vals = pd.to_numeric(subset[val_col], errors="coerce")
            counts = pd.to_numeric(subset[cnt_col], errors="coerce").fillna(0)
            is_na = (counts <= 0) | vals.isna()
            heights = vals.fillna(0).to_numpy()
            heights = np.where(is_na.to_numpy(), 0.0, heights)
            max_val = max(max_val, float(np.nanmax(heights)) if heights.size else 0.0)
            bars = ax.bar(
                x + (idx - 0.5) * width,
                heights,
                width=width,
                color=colors[idx],
                edgecolor="white",
                linewidth=0.6,
                label=val_col.replace("均值", ""),
            )
            for b, h, na_flag in zip(bars, heights, is_na.tolist()):
                if na_flag:
                    b.set_facecolor((0.9, 0.9, 0.9, 1.0))
                    b.set_edgecolor((0.55, 0.55, 0.55, 1.0))
                    b.set_hatch("///")
                    ax.text(
                        b.get_x() + b.get_width() / 2,
                        0.01,
                        "NA",
                        ha="center",
                        va="bottom",
                        fontsize=7,
                        color="#666666",
                        rotation=90,
                    )
                else:
                    ax.text(
                        b.get_x() + b.get_width() / 2,
                        float(h) + 0.01,
                        f"{float(h):.2f}",
                        ha="center",
                        va="bottom",
                        fontsize=7,
                    )
        ax.set_title(CENTER_LABELS.get(center, center))
        ax.set_xlabel("Model")
        ax.set_ylabel(ylabel if ax is axes[0] else "")
        ax.tick_params(axis="x", rotation=35, labelsize=9)
        ax.grid(axis="y", linestyle="--", alpha=0.3)
    ylim_top = max(0.05, max_val * 1.2 + 0.02)
    for ax in axes:
        ax.set_ylim(0, min(1.0, ylim_top))
    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        fig.legend(
            handles,
            labels,
            loc="upper center",
            ncol=min(len(labels), 3),
            bbox_to_anchor=(0.5, 0.93),
        )
        top_pad = 0.82
    else:
        top_pad = 0.86
    fig.suptitle(title, y=0.98)
    fig.tight_layout(rect=(0, 0.16, 1, top_pad))
    plt.savefig(output_path, dpi=200)
    plt.close()


def _line_plot_by_center(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    ylabel: str,
    output_path: Path,
    x_order: list[str],
    ylim: tuple[float, float] | None = None,
    center_order: list[str] | None = None,
    model_order: list[str] | None = None,
    show_mean_line: bool = False,
) -> None:
    if df.empty:
        return
    centers = center_order or _center_order(df["Center"])
    models = model_order or _model_order(df["Model"])
    fig, axes = plt.subplots(1, len(centers), figsize=(7.5 * len(centers), 5.2), sharey=True)
    if len(centers) == 1:
        axes = [axes]
    for ax, center in zip(axes, centers):
        subset = df[df["Center"] == center]
        if subset.empty:
            continue
        pivot = (
            subset.pivot_table(index=x_col, columns="Model", values=y_col, aggfunc="mean")
            .reindex(x_order)
            .reindex(columns=models)
        )
        pivot.plot(ax=ax, marker="o")
        if show_mean_line:
            mean_line = pivot.mean(axis=1, skipna=True)
            ax.plot(mean_line.index.tolist(), mean_line.values, linestyle="--", color="black", label="Mean")
        ax.set_title(CENTER_LABELS.get(center, center))
        ax.set_xlabel(x_col)
        ax.set_ylabel(ylabel if ax is axes[0] else "")
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        if ylim:
            ax.set_ylim(*ylim)
        if ax.get_legend() is not None:
            ax.get_legend().remove()
    handles, labels = axes[0].get_legend_handles_labels()
    if labels:
        fig.legend(
            handles,
            labels,
            loc="upper center",
            ncol=min(len(labels), 4),
            bbox_to_anchor=(0.5, 0.93),
        )
    fig.suptitle(title, y=0.98)
    fig.tight_layout(rect=(0, 0.16, 1, 0.82))
    plt.savefig(output_path, dpi=200)
    plt.close()


def _dynamic_limits(values: np.ndarray, pad: float = 0.05) -> tuple[float, float] | None:
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    min_val = float(values.min())
    max_val = float(values.max())
    lower = max(0.0, min_val - pad)
    upper = min(1.0, max_val + pad)
    if upper - lower < 0.05:
        upper = min(1.0, lower + 0.05)
    return (lower, upper)

def _load_summary_sheet(summary_xlsx: Path) -> pd.DataFrame:
    xl = pd.ExcelFile(summary_xlsx)
    df = xl.parse(0)
    for c in df.columns[2:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _iter_center_model_files(data_root: Path, subdir: str, suffix: str) -> list[tuple[str, str, Path]]:
    rows: list[tuple[str, str, Path]] = []
    for center_dir in sorted(data_root.iterdir()):
        if not center_dir.is_dir():
            continue
        center = center_dir.name
        agent_dir = center_dir / subdir
        if not agent_dir.exists():
            continue
        for path in sorted(agent_dir.glob(f"Evaluation_Summary_*_{suffix}.xlsx")):
            name = path.stem.replace("Evaluation_Summary_", "").replace(f"_{suffix}", "")
            rows.append((center, name, path))
    return rows


def _normalize_confidence(values: pd.Series) -> pd.Series:
    vals = pd.to_numeric(values, errors="coerce")
    if vals.dropna().empty:
        return vals
    max_val = vals.max(skipna=True)
    if max_val > 1.0:
        vals = vals / 100.0
    return vals.clip(lower=0, upper=1)


def _normalize_score(values: pd.Series) -> pd.Series:
    vals = pd.to_numeric(values, errors="coerce")
    if vals.dropna().empty:
        return vals
    max_val = vals.max(skipna=True)
    if max_val > 1.0:
        vals = vals / 100.0
    return vals.clip(lower=0, upper=1)


def _label_match(series: pd.Series, allow_partial: bool) -> pd.Series:
    text = series.fillna("").astype(str).str.replace(r"\s+", "", regex=True)
    has_match = text.str.contains("匹配", regex=False)
    if not allow_partial:
        has_match = has_match & ~text.str.contains("部分匹配", regex=False)
    has_match = has_match & ~text.str.contains("不匹配", regex=False)
    has_match = has_match & ~text.str.contains("完全不同", regex=False)
    has_match = has_match & ~text.str.contains("完全不相同", regex=False)
    return has_match


def _compute_ece(conf: pd.Series, labels: pd.Series, bins: int = 10) -> float | None:
    conf = conf.dropna()
    labels = labels.loc[conf.index]
    if conf.empty:
        return None
    bins_edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    n = len(conf)
    for i in range(bins):
        lo, hi = bins_edges[i], bins_edges[i + 1]
        mask = (conf >= lo) & (conf < hi if i < bins - 1 else conf <= hi)
        if not mask.any():
            continue
        bin_conf = conf[mask].mean()
        bin_acc = labels[mask].mean()
        ece += (mask.sum() / n) * abs(bin_conf - bin_acc)
    return float(ece)


def _plot_algorithmic(summary_df: pd.DataFrame, out_dir: Path, data_root: Path, summary_xlsx: Path | None = None) -> pd.DataFrame:
    center_col = summary_df.columns[0]
    model_col = summary_df.columns[1]
    summary_by_model = summary_df.groupby(model_col).mean(numeric_only=True)
    data_sources = [str(p) for _, _, p in _iter_center_model_files(data_root, "judge agent", "CN_Judge_Parsed")]
    data_sources += [str(p) for _, _, p in _iter_center_model_files(data_root, "doc agent", "CN_Parsed")]
    if summary_xlsx:
        data_sources.append(str(summary_xlsx))
    meta_base = {
        "data_root": str(data_root),
        "summary_xlsx": str(summary_xlsx) if summary_xlsx else "",
        "data_sources": data_sources,
    }

    col_map = {
        "D1检查匹配率(病例均值)": "D1 Check Match Rate (case mean)",
        "D2检查匹配率(病例均值)": "D2 Check Match Rate (case mean)",
        "D1无效循环率(0匹配)均值": "D1 Loop Inefficiency (0-match)",
        "D2无效循环率(0匹配)均值": "D2 Loop Inefficiency (0-match)",
        "Gate1 流程通过率(基于流程状态)": "Gate1 Flow Pass Rate",
        "Gate2 流程通过率(基于流程状态)": "Gate2 Flow Pass Rate",
        "Gate1 Judge通过率(继续评测)": "Gate1 Judge Pass Rate",
        "Gate2 Judge初审通过率(继续评测)": "Gate2 Judge Pass Rate",
        "Gate1 Judge总分均值": "D1 Judge Overall Score",
        "Gate2 Judge总分均值": "D2 Judge Overall Score",
        "D3总分均值": "D3 Judge Overall Score",
        "D4总分均值": "D4 Judge Overall Score",
        "Gate1 Judge诊断评分均值": "D1 Diagnosis Score",
        "Gate1 Judge检查匹配评分均值": "D1 Check Match Score",
        "Gate1 Judge检查匹配度均值": "D1 Check Match Degree",
        "Gate2 Judge修正诊断评分均值": "D2 Revised Dx Score",
        "Gate2 Judge手术方案评分均值": "D2 Surgery Plan Score",
        "D3最终诊断评分均值": "D3 Diagnosis Score",
        "D3术后方案评分均值": "D3 Post-op Plan Score",
        "D4康复计划评分均值": "D4 Rehab Score",
        "D4随访计划评分均值": "D4 Follow-up Score",
    }

    keep_cols = [c for c in col_map if c in summary_df.columns]
    center_df = summary_df[[center_col, model_col] + keep_cols].rename(
        columns={center_col: "Center", model_col: "Model", **col_map}
    )
    center_order = _center_order(center_df["Center"])
    model_order = _model_order(center_df["Model"])

    # Check match rates
    df_check = center_df[["Center", "Model", "D1 Check Match Rate (case mean)", "D2 Check Match Rate (case mean)"]]
    _group_bar_plot_by_center(
        df_check,
        title="Check Match Rate by Model (by Center)",
        ylabel="Rate",
        output_path=out_dir / "algorithmic_check_match_rate_by_model.png",
        ylim=(0, 1),
        center_order=center_order,
        model_order=model_order,
    )
    _write_source_data(
        out_dir,
        "algorithmic_check_match_rate_by_model",
        {"raw": df_check, "plot_data": df_check},
        {
            **meta_base,
            "figure": "algorithmic_check_match_rate_by_model.png",
            "description": "Check match rate by model (D1/D2)",
        },
    )

    # Loop inefficiency (NA vs 0 by sample count)
    loop_counts = {
        "D1 Loop Count": "D1无效循环率样本数",
        "D2 Loop Count": "D2无效循环率样本数",
    }
    count_cols = [c for c in loop_counts.values() if c in summary_df.columns]
    df_loop = center_df[["Center", "Model", "D1 Loop Inefficiency (0-match)", "D2 Loop Inefficiency (0-match)"]].copy()
    if count_cols:
        for cn in count_cols:
            df_loop[loop_counts.get("D1 Loop Count") if "D1" in cn else loop_counts.get("D2 Loop Count")] = summary_df[cn]
        df_loop = df_loop.rename(
            columns={
                loop_counts.get("D1 Loop Count"): "D1 Loop Samples",
                loop_counts.get("D2 Loop Count"): "D2 Loop Samples",
            }
        )
        if "D1 Loop Samples" in df_loop.columns and "D2 Loop Samples" in df_loop.columns:
            _plot_loop_inefficiency_by_center(
                df_loop,
                title="Loop Inefficiency by Model (by Center)",
                ylabel="Rate",
                output_path=out_dir / "algorithmic_loop_inefficiency_by_model.png",
                center_order=center_order,
                model_order=model_order,
                value_cols=("D1 Loop Inefficiency (0-match)", "D2 Loop Inefficiency (0-match)"),
                count_cols=("D1 Loop Samples", "D2 Loop Samples"),
            )
        else:
            _group_bar_plot_by_center(
                df_loop,
                title="Loop Inefficiency by Model (by Center)",
                ylabel="Rate",
                output_path=out_dir / "algorithmic_loop_inefficiency_by_model.png",
                ylim=(0, 1),
                center_order=center_order,
                model_order=model_order,
            )
    else:
        _group_bar_plot_by_center(
            df_loop,
            title="Loop Inefficiency by Model (by Center)",
            ylabel="Rate",
            output_path=out_dir / "algorithmic_loop_inefficiency_by_model.png",
            ylim=(0, 1),
            center_order=center_order,
            model_order=model_order,
        )
    _write_source_data(
        out_dir,
        "algorithmic_loop_inefficiency_by_model",
        {"raw": df_loop, "plot_data": df_loop},
        {
            **meta_base,
            "figure": "algorithmic_loop_inefficiency_by_model.png",
            "description": "Loop inefficiency by model (D1/D2)",
        },
    )

    # Stage pass rate from doctor report (D1/D2/D3)
    doctor_report = out_dir.parent / "summary" / "医生评测汇总.xlsx"
    pass_df = _compute_stage_pass_rates_from_doctor_report(doctor_report)
    if not pass_df.empty:
        plot_df = pass_df[
            ["Center", "Model", "D1 Pass Rate", "D2 First Pass Rate", "D2 Second Pass Rate", "D3 Pass Rate"]
        ].copy()
        _group_bar_plot_by_center(
            plot_df,
            title="Stage Pass Rate by Model (D1/D2/D3)",
            ylabel="Rate",
            output_path=out_dir / "algorithmic_stage_pass_rate_by_model.png",
            ylim=(0, 1.0),
            center_order=center_order,
            model_order=model_order,
        )
        _write_source_data(
            out_dir,
            "algorithmic_stage_pass_rate_by_model",
            {"raw": pass_df, "plot_data": plot_df},
            {
                **meta_base,
                "figure": "algorithmic_stage_pass_rate_by_model.png",
                "description": "Stage pass rate by model (D1/D2/D3) from doctor report",
                "doctor_report": str(doctor_report),
            },
        )

    # Overall judge scores by stage (D1/D2/D3/D4)
    df_scores = center_df[
        ["Center", "Model", "D1 Judge Overall Score", "D2 Judge Overall Score", "D3 Judge Overall Score", "D4 Judge Overall Score"]
    ]
    _group_bar_plot_by_center(
        df_scores,
        title="Overall Judge Scores by Stage (by Center)",
        ylabel="Score (0-1)",
        output_path=out_dir / "algorithmic_judge_scores_by_stage.png",
        ylim=(0, 1),
        center_order=center_order,
        model_order=model_order,
    )
    _write_source_data(
        out_dir,
        "algorithmic_judge_scores_by_stage",
        {"raw": df_scores, "plot_data": df_scores},
        {
            **meta_base,
            "figure": "algorithmic_judge_scores_by_stage.png",
            "description": "Overall judge scores by stage",
        },
    )

    # Judge score pathways (Diagnosis / Check / Plan)
    pathway_rows: list[dict[str, Any]] = []
    # diagnosis
    for stage, col in [
        ("D1_Decision", "D1 Diagnosis Score"),
        ("D2_Decision", "D2 Revised Dx Score"),
        ("D3_Decision", "D3 Diagnosis Score"),
    ]:
        if col in center_df.columns:
            tmp = center_df[["Center", "Model", col]].rename(columns={col: "Value"}).copy()
            tmp["Stage"] = stage
            tmp["Pathway"] = "Diagnosis"
            pathway_rows.append(tmp)

    # check: D1 Loop + D1 Decision (D2 check) + D2 Loop
    loop_check = _compute_loop_check_match_degree(data_root)
    if not loop_check.empty:
        d1_loop = loop_check[loop_check["Stage"] == "D1_Loop"].rename(columns={"Value": "Value"}).copy()
        d1_loop["Pathway"] = "Check"
        d1_loop["Stage"] = "D1_Loop"
        pathway_rows.append(d1_loop[["Center", "Model", "Stage", "Value", "Pathway"]])
        d2_loop = loop_check[loop_check["Stage"] == "D2_Loop"].rename(columns={"Value": "Value"}).copy()
        d2_loop["Pathway"] = "Check"
        d2_loop["Stage"] = "D2_Loop"
        pathway_rows.append(d2_loop[["Center", "Model", "Stage", "Value", "Pathway"]])

    if "D1 Check Match Score" in center_df.columns:
        tmp = center_df[["Center", "Model", "D1 Check Match Score"]].rename(columns={"D1 Check Match Score": "Value"}).copy()
        tmp["Stage"] = "D1_Decision_D2Check"
        tmp["Pathway"] = "Check"
        pathway_rows.append(tmp)

    # plan
    plan_cols = ["D2 Surgery Plan Score", "D3 Post-op Plan Score"]
    if all(c in center_df.columns for c in plan_cols):
        for stage, col in [
            ("D2_Decision", "D2 Surgery Plan Score"),
            ("D3_Decision", "D3 Post-op Plan Score"),
        ]:
            tmp = center_df[["Center", "Model", col]].rename(columns={col: "Value"}).copy()
            tmp["Stage"] = stage
            tmp["Pathway"] = "Plan"
            pathway_rows.append(tmp)
    if "D4 Rehab Score" in center_df.columns or "D4 Follow-up Score" in center_df.columns:
        d4 = center_df[["Center", "Model"]].copy()
        vals = []
        if "D4 Rehab Score" in center_df.columns:
            vals.append(center_df["D4 Rehab Score"])
        if "D4 Follow-up Score" in center_df.columns:
            vals.append(center_df["D4 Follow-up Score"])
        if vals:
            d4["Value"] = pd.concat(vals, axis=1).mean(axis=1, skipna=True)
            d4["Stage"] = "D4_Plan"
            d4["Pathway"] = "Plan"
            pathway_rows.append(d4)

    if pathway_rows:
        path_df = pd.concat(pathway_rows, ignore_index=True)
        _plot_judge_score_pathways(
            path_df,
            out_dir / "algorithmic_judge_score_pathways.png",
            center_order,
            model_order,
            data_root,
            summary_xlsx,
        )

    # Build English summary table
    summary_en = summary_by_model[list(col_map.keys())].rename(columns=col_map)
    summary_en.insert(0, "Model", summary_en.index)
    return summary_en.reset_index(drop=True)


def _compute_d3_judge_pass_rate(data_root: Path) -> pd.DataFrame:
    rows = []
    for center, model, path in _iter_center_model_files(data_root, "judge agent", "CN_Judge_Parsed"):
        try:
            df = pd.read_excel(path, sheet_name="D3_Surgery_Decision", engine="openpyxl")
        except Exception:
            continue
        if "判官_原始JSON_诊断匹配评估_结论" not in df.columns:
            continue
        conclusion = df["判官_原始JSON_诊断匹配评估_结论"].astype(str)
        status = df.get("状态")
        if status is not None:
            mask = status.astype(str).str.strip().ne("未经过")
        else:
            mask = conclusion.notna()
        subset = conclusion[mask].astype(str).str.strip()
        subset = subset[subset.ne("") & subset.str.lower().ne("nan")]
        if subset.empty:
            continue
        passed = _label_match(subset, allow_partial=False)
        rate = passed.mean()
        rows.append({"Center": center, "Model": model, "D3 Judge Diagnosis Pass Rate": rate})
    if not rows:
        return pd.DataFrame(columns=["Center", "Model", "D3 Judge Diagnosis Pass Rate"])
    df_rates = pd.DataFrame(rows)
    return df_rates.groupby(["Center", "Model"], as_index=False)["D3 Judge Diagnosis Pass Rate"].mean()


def _compute_gate_judge_pass_rates(data_root: Path) -> pd.DataFrame:
    rows = []
    mapping = [
        ("Gate1 Judge Pass Rate", "D1_Outpatient_Decision", "Gate1判官_原始JSON_是否继续评测"),
        ("Gate2 Judge Pass Rate", "D2_Admission_Decision", "Gate2判官_原始JSON_是否继续评测"),
    ]
    for center, model, path in _iter_center_model_files(data_root, "judge agent", "CN_Judge_Parsed"):
        for label, sheet, col in mapping:
            try:
                df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
            except Exception:
                continue
            if col not in df.columns:
                continue
            status = df.get("状态")
            if status is not None:
                mask = status.astype(str).str.strip().ne("未经过")
            else:
                mask = df[col].notna()
            subset = df[col][mask]
            if subset.empty:
                continue
            rate = pd.to_numeric(subset, errors="coerce").astype(float).mean()
            rows.append({"Center": center, "Model": model, "Metric": label, "Rate": rate})
    if not rows:
        return pd.DataFrame(columns=["Center", "Model", "Gate1 Judge Pass Rate", "Gate2 Judge Pass Rate"])
    df = pd.DataFrame(rows)
    pivot = df.pivot_table(index=["Center", "Model"], columns="Metric", values="Rate", aggfunc="mean").reset_index()
    for col in ["Gate1 Judge Pass Rate", "Gate2 Judge Pass Rate"]:
        if col not in pivot.columns:
            pivot[col] = np.nan
    return pivot[["Center", "Model", "Gate1 Judge Pass Rate", "Gate2 Judge Pass Rate"]]


def _compute_stage_pass_rates_from_doctor_report(doctor_report: Path) -> pd.DataFrame:
    if not doctor_report.exists():
        return pd.DataFrame()
    try:
        df = pd.read_excel(doctor_report, sheet_name="通过退出明细", engine="openpyxl")
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    center_col = "中心" if "中心" in df.columns else "Center"
    model_col = "模型名称" if "模型名称" in df.columns else "Model"
    case_col = "病例ID" if "病例ID" in df.columns else "CaseID"

    required = {"D1_Decision", "D2_Decision", "D3_Decision"}
    if not required.issubset(set(df.columns)):
        return pd.DataFrame()

    df = df[[center_col, model_col, case_col, "D1_Decision", "D2_Decision", "D3_Decision"]].copy()
    df[center_col] = df[center_col].astype(str)
    df[model_col] = df[model_col].astype(str)
    df[case_col] = df[case_col].astype(str)

    def _has(text: str, key: str) -> bool:
        return key in text

    rows: list[dict[str, Any]] = []
    for (center, model), sub in df.groupby([center_col, model_col]):
        total = int(sub[case_col].nunique())
        if total <= 0:
            continue

        d1_dec = sub["D1_Decision"].fillna("").astype(str)
        d2_dec = sub["D2_Decision"].fillna("").astype(str)
        d3_dec = sub["D3_Decision"].fillna("").astype(str)

        d1_pass = d1_dec.apply(lambda s: _has(s, "D1决策_通过") and not _has(s, "D1决策_特殊"))
        d2_first = d2_dec.apply(lambda s: _has(s, "一审通过"))
        d2_second = d2_dec.apply(lambda s: _has(s, "需要二审_通过二审"))
        d3_pass = d3_dec.apply(lambda s: _has(s, "通过一审") or _has(s, "需要二审_通过二审"))

        rows.append(
            {
                "Center": center,
                "Model": model,
                "Total Cases": total,
                "D1 Pass Count": int(d1_pass.sum()),
                "D1 Pass Rate": float(d1_pass.sum() / total),
                "D2 First Pass Count": int(d2_first.sum()),
                "D2 First Pass Rate": float(d2_first.sum() / total),
                "D2 Second Pass Count": int(d2_second.sum()),
                "D2 Second Pass Rate": float(d2_second.sum() / total),
                "D3 Pass Count": int(d3_pass.sum()),
                "D3 Pass Rate": float(d3_pass.sum() / total),
            }
        )

    return pd.DataFrame(rows)


def _compute_loop_scores(data_root: Path) -> pd.DataFrame:
    rows = []
    for center, model, path in _iter_center_model_files(data_root, "judge agent", "CN_Judge_Parsed"):
        for stage, sheet in [("D1", "D1_Outpatient_Loop"), ("D2", "D2_Admission_Loop")]:
            try:
                df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
            except Exception:
                continue
            score_cols = [c for c in df.columns if "评分_综合评分" in str(c)]
            if not score_cols:
                continue
            scores = pd.to_numeric(df[score_cols].stack(), errors="coerce").dropna()
            if scores.empty:
                continue
            rows.append({"Center": center, "Model": model, "Stage": stage, "Loop Score": scores.mean()})
    if not rows:
        return pd.DataFrame(columns=["Center", "Model", "D1 Loop Score", "D2 Loop Score"])
    df = pd.DataFrame(rows)
    pivot = df.pivot_table(index=["Center", "Model"], columns="Stage", values="Loop Score", aggfunc="mean").reset_index()
    pivot = pivot.rename(columns={"D1": "D1 Loop Score", "D2": "D2 Loop Score"})
    return pivot


def _compute_loop_check_match_degree(data_root: Path) -> pd.DataFrame:
    rows = []
    for center, model, path in _iter_center_model_files(data_root, "judge agent", "CN_Judge_Parsed"):
        for stage, sheet in [("D1_Loop", "D1_Outpatient_Loop"), ("D2_Loop", "D2_Admission_Loop")]:
            try:
                df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
            except Exception:
                continue
            if df.empty:
                continue
            score_cols = [c for c in df.columns if "判官_原始JSON_评分_检查匹配度" in str(c)]
            if not score_cols:
                continue
            vals = df[score_cols].apply(pd.to_numeric, errors="coerce")
            case_mean = vals.mean(axis=1, skipna=True)
            case_mean = case_mean.dropna()
            if case_mean.empty:
                continue
            rows.append(
                {
                    "Center": center,
                    "Model": model,
                    "Stage": stage,
                    "Value": float(case_mean.mean()),
                    "Samples": int(case_mean.shape[0]),
                }
            )
    if not rows:
        return pd.DataFrame(columns=["Center", "Model", "Stage", "Value", "Samples"])
    df = pd.DataFrame(rows)
    return df.groupby(["Center", "Model", "Stage"], as_index=False).agg(Value=("Value", "mean"), Samples=("Samples", "sum"))


def _plot_judge_score_pathways(
    path_df: pd.DataFrame,
    out_path: Path,
    center_order: list[str],
    model_order: list[str],
    data_root: Path | None = None,
    summary_xlsx: Path | None = None,
) -> None:
    if path_df.empty:
        return
    pathways = ["Diagnosis", "Check", "Plan"]
    stage_labels = {
        "Diagnosis": ["D1_Decision", "D2_Decision", "D3_Decision"],
        "Check": ["D1_Loop", "D1_Decision_D2Check", "D2_Loop"],
        "Plan": ["D2_Decision", "D3_Decision", "D4_Plan"],
    }
    stage_names = {
        "D1_Decision": "D1决策",
        "D2_Decision": "D2决策",
        "D3_Decision": "D3决策",
        "D4_Plan": "D4方案",
        "D1_Loop": "D1Loop",
        "D2_Loop": "D2Loop",
        "D1_Decision_D2Check": "D1决策(D2检查)",
    }

    for center in center_order:
        cdf = path_df[path_df["Center"] == center].copy()
        if cdf.empty:
            continue
        fig, axes = plt.subplots(1, 3, figsize=(16.2, 4.6), sharey=True)
        cmap = plt.get_cmap("tab10")
        for ax, pathway in zip(axes, pathways):
            sdf = cdf[cdf["Pathway"] == pathway].copy()
            if sdf.empty:
                ax.axis("off")
                continue
            x_labels = stage_labels[pathway]
            x = np.arange(len(x_labels), dtype=float)
            for idx, model in enumerate(model_order):
                mdf = sdf[sdf["Model"] == model].copy()
                if mdf.empty:
                    continue
                mdf = mdf.set_index("Stage").reindex(x_labels)
                vals = pd.to_numeric(mdf["Value"], errors="coerce").to_numpy()
                ax.plot(
                    x,
                    vals,
                    marker="o",
                    linewidth=1.8,
                    color=cmap(idx % 10),
                    label=model,
                )
                for xv, yv in zip(x, vals):
                    if np.isfinite(yv):
                        ax.text(xv, float(yv) + 0.02, f"{float(yv):.2f}", ha="center", va="bottom", fontsize=7)
            ax.set_xticks(x)
            ax.set_xticklabels([stage_names.get(s, s) for s in x_labels])
            ax.set_ylim(0, 1)
            ax.grid(axis="y", linestyle=":", alpha=0.25)
            ax.set_title({"Diagnosis": "诊断质量", "Check": "检查质量", "Plan": "方案质量"}[pathway])

        handles, labels = axes[0].get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="upper center", ncol=min(5, len(labels)), bbox_to_anchor=(0.5, 1.05), fontsize=8)
        fig.suptitle(f"Judge Score Pathways - {CENTER_LABELS.get(center, center)}", y=1.08)
        fig.tight_layout(rect=(0, 0, 1, 0.86))
        out_png = out_path.parent / f"{out_path.stem}_{center}.png"
        fig.savefig(out_png, dpi=600)
        plt.close(fig)

        _write_source_data(
            out_path.parent,
            out_png.stem,
            {"raw": cdf, "plot_data": cdf},
            {
                "figure": out_png.name,
                "description": "Judge score pathways (Diagnosis/Check/Plan)",
                "center": center,
                "stage_order": ",".join(sum([stage_labels[p] for p in pathways], [])),
                "data_root": str(data_root) if data_root else "",
                "summary_xlsx": str(summary_xlsx) if summary_xlsx else "",
            },
        )

def _compute_special_case_counts(data_root: Path) -> pd.DataFrame:
    rows = []
    for center, model, path in _iter_center_model_files(data_root, "doc agent", "CN_Parsed"):
        try:
            df = pd.read_excel(path, sheet_name="D1_Outpatient_Decision", engine="openpyxl")
        except Exception:
            continue
        if df.empty:
            continue
        if "状态" in df.columns:
            special = df["状态"].astype(str).str.contains("特殊", regex=False)
        else:
            col_revise = "医生决策_原始JSON_修正诊断"
            col_plan = "医生决策_原始JSON_初步治疗方案"
            col_dx = "医生决策_原始JSON_初步诊断列表"
            col_check = "医生决策_原始JSON_建议检查项目"
            for col in [col_revise, col_plan, col_dx, col_check]:
                if col not in df.columns:
                    df[col] = ""
            has_revise_or_plan = df[col_revise].fillna("").astype(str).str.strip().ne("") | df[col_plan].fillna("").astype(str).str.strip().ne("")
            no_dx = df[col_dx].fillna("").astype(str).str.strip().eq("")
            no_check = df[col_check].fillna("").astype(str).str.strip().eq("")
            special = has_revise_or_plan & no_dx & no_check
        rows.append(
            {
                "Center": center,
                "Model": model,
                "Special D1 Cases": int(special.sum()),
                "Total D1 Cases": int(len(df)),
                "Special Rate": float(special.sum() / len(df)) if len(df) else 0.0,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["Center", "Model", "Special D1 Cases", "Total D1 Cases", "Special Rate"])
    return pd.DataFrame(rows)


def _iter_calibration_datasets(data_root: Path):
    for center_dir in sorted(data_root.iterdir()):
        if not center_dir.is_dir():
            continue
        doc_dir = center_dir / "doc agent"
        judge_dir = center_dir / "judge agent"
        if not doc_dir.exists() or not judge_dir.exists():
            continue
        for doc_path in sorted(doc_dir.glob("Evaluation_Summary_*_CN_Parsed.xlsx")):
            model = doc_path.stem.replace("Evaluation_Summary_", "").replace("_CN_Parsed", "")
            judge_path = judge_dir / f"Evaluation_Summary_{model}_CN_Judge_Parsed.xlsx"
            if not judge_path.exists():
                continue
            yield center_dir.name, model, doc_path, judge_path


def _to_unit(values: pd.Series) -> pd.Series:
    vals = pd.to_numeric(values, errors="coerce")
    if vals.dropna().empty:
        return vals
    max_val = float(vals.max(skipna=True))
    if max_val > 1.0:
        if max_val <= 5.0:
            vals = vals / 5.0
        else:
            vals = vals / 100.0
    return vals.clip(lower=0, upper=1)


def _valid_stage_rows(df: pd.DataFrame) -> pd.DataFrame:
    status_col = "状态"
    skipped = "未经过"
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if status_col in out.columns:
        status = out[status_col].astype(str).str.strip()
        out = out[status.ne(skipped) & status.ne("")]
    return out


def _merge_conf_acc(doc_df: pd.DataFrame, judge_df: pd.DataFrame, doc_cols: list[str], judge_cols: list[str]) -> pd.DataFrame:
    case_col = "病例ID"
    if doc_df.empty or judge_df.empty:
        return pd.DataFrame(columns=["CaseID", "Confidence", "Accuracy"])
    if case_col not in doc_df.columns or case_col not in judge_df.columns:
        return pd.DataFrame(columns=["CaseID", "Confidence", "Accuracy"])

    dcols = [c for c in doc_cols if c in doc_df.columns]
    jcols = [c for c in judge_cols if c in judge_df.columns]
    if not dcols or not jcols:
        return pd.DataFrame(columns=["CaseID", "Confidence", "Accuracy"])

    doc_vals = doc_df[[case_col, *dcols]].copy()
    doc_vals["Confidence"] = pd.concat([_to_unit(doc_vals[c]) for c in dcols], axis=1).mean(axis=1, skipna=True)
    doc_vals = doc_vals[[case_col, "Confidence"]]

    judge_vals = judge_df[[case_col, *jcols]].copy()
    judge_vals["Accuracy"] = pd.concat([_to_unit(judge_vals[c]) for c in jcols], axis=1).mean(axis=1, skipna=True)
    judge_vals = judge_vals[[case_col, "Accuracy"]]

    merged = doc_vals.merge(judge_vals, on=case_col, how="inner")
    merged = merged.rename(columns={case_col: "CaseID"})
    merged = merged.dropna(subset=["Confidence", "Accuracy"])
    return merged


def _compute_calibration_points(data_root: Path) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []

    d1_loop_conf = "第{r}轮_医生_原始JSON_置信度评估_门诊检查方案置信度"
    d2_loop_conf = "第{r}轮_医生_原始JSON_置信度评估_检查方案置信度"
    loop_check_score = "第{r}轮_判官_原始JSON_评分_检查匹配度"
    loop_overall_score = "第{r}轮_判官_原始JSON_评分_综合评分"

    c_d1_dx = "医生决策_原始JSON_置信度评估_诊断置信度"
    c_d1_check = "医生决策_原始JSON_置信度评估_检查方案置信度"
    c_d1_plan = "医生决策_原始JSON_置信度评估_治疗方案置信度"
    c_gate1_dx = "Gate1判官_原始JSON_诊断匹配_评分"
    c_gate1_check = "Gate1判官_原始JSON_检查匹配_评分"
    c_gate1_overall = "Gate1判官_原始JSON_综合评分"

    c_d2_dx = "医生决策_原始JSON_置信度评估_诊断置信度"
    c_d2_plan = "医生决策_原始JSON_置信度评估_治疗方案置信度"
    c_gate2_dx = "Gate2判官_原始JSON_修正诊断匹配_评分"
    c_gate2_plan = "Gate2判官_原始JSON_手术方案匹配_评分"
    c_gate2_overall = "Gate2判官_原始JSON_综合评分"

    c_d3_dx = "医生_原始JSON_置信度评估_最终诊断置信度"
    c_d3_plan = "医生_原始JSON_置信度评估_术后治疗方案置信度"
    c_gate3_dx = "判官_原始JSON_诊断匹配评估_评分"
    c_gate3_plan = "判官_原始JSON_治疗方案匹配评估_评分"
    c_gate3_overall = "判官_原始JSON_综合评分"

    c_d4_rehab_conf = "医生_原始JSON_置信度评估_康复计划置信度"
    c_d4_follow_conf = "医生_原始JSON_置信度评估_随访计划置信度"
    c_d4_rehab_score = "判官_原始JSON_康复计划评估_评分"
    c_d4_follow_score = "判官_原始JSON_随访计划评估_评分"
    c_d4_overall = "判官_原始JSON_综合评分"

    def _append(
        center: str,
        model: str,
        stage: str,
        category: str,
        detail_type: str,
        doc_sheet: str,
        judge_sheet: str,
        merged: pd.DataFrame,
        conf_src: str,
        acc_src: str,
        round_id: int | None = None,
    ) -> None:
        if merged.empty:
            return
        out = merged.copy()
        out["Center"] = center
        out["Model"] = model
        out["Stage"] = stage
        out["Category"] = category
        out["DetailType"] = detail_type
        out["DocSheet"] = doc_sheet
        out["JudgeSheet"] = judge_sheet
        out["ConfidenceSource"] = conf_src
        out["AccuracySource"] = acc_src
        out["Round"] = round_id
        rows.append(
            out[
                [
                    "Center",
                    "Model",
                    "CaseID",
                    "Stage",
                    "Category",
                    "DetailType",
                    "Round",
                    "Confidence",
                    "Accuracy",
                    "DocSheet",
                    "JudgeSheet",
                    "ConfidenceSource",
                    "AccuracySource",
                ]
            ]
        )

    for center, model, doc_path, judge_path in _iter_calibration_datasets(data_root):
        try:
            doc_xl = pd.ExcelFile(doc_path)
            judge_xl = pd.ExcelFile(judge_path)
        except Exception:
            continue

        def _sheet(xl: pd.ExcelFile, name: str) -> pd.DataFrame:
            if name not in xl.sheet_names:
                return pd.DataFrame()
            try:
                return _valid_stage_rows(xl.parse(name))
            except Exception:
                return pd.DataFrame()

        d1_loop_doc = _sheet(doc_xl, "D1_Outpatient_Loop")
        d1_loop_judge = _sheet(judge_xl, "D1_Outpatient_Loop")
        d2_loop_doc = _sheet(doc_xl, "D2_Admission_Loop")
        d2_loop_judge = _sheet(judge_xl, "D2_Admission_Loop")
        d1_dec_doc = _sheet(doc_xl, "D1_Outpatient_Decision")
        d1_dec_judge = _sheet(judge_xl, "D1_Outpatient_Decision")
        d2_dec_doc = _sheet(doc_xl, "D2_Admission_Decision")
        d2_dec_judge = _sheet(judge_xl, "D2_Admission_Decision")
        d3_dec_doc = _sheet(doc_xl, "D3_Surgery_Decision")
        d3_dec_judge = _sheet(judge_xl, "D3_Surgery_Decision")
        d4_doc = _sheet(doc_xl, "D4_Rehab_Plan")
        d4_judge = _sheet(judge_xl, "D4_Rehab_Plan")

        for r in range(1, 5):
            _append(
                center,
                model,
                "D1_Loop",
                "check",
                "round",
                "D1_Outpatient_Loop",
                "D1_Outpatient_Loop",
                _merge_conf_acc(d1_loop_doc, d1_loop_judge, [d1_loop_conf.format(r=r)], [loop_check_score.format(r=r)]),
                f"D1 loop conf round {r}",
                f"D1 loop check score round {r}",
                round_id=r,
            )
            _append(
                center,
                model,
                "D1_Loop",
                "overall",
                "round",
                "D1_Outpatient_Loop",
                "D1_Outpatient_Loop",
                _merge_conf_acc(d1_loop_doc, d1_loop_judge, [d1_loop_conf.format(r=r)], [loop_overall_score.format(r=r)]),
                f"D1 loop conf round {r}",
                f"D1 loop overall score round {r}",
                round_id=r,
            )
            _append(
                center,
                model,
                "D2_Loop",
                "check",
                "round",
                "D2_Admission_Loop",
                "D2_Admission_Loop",
                _merge_conf_acc(d2_loop_doc, d2_loop_judge, [d2_loop_conf.format(r=r)], [loop_check_score.format(r=r)]),
                f"D2 loop conf round {r}",
                f"D2 loop check score round {r}",
                round_id=r,
            )
            _append(
                center,
                model,
                "D2_Loop",
                "overall",
                "round",
                "D2_Admission_Loop",
                "D2_Admission_Loop",
                _merge_conf_acc(d2_loop_doc, d2_loop_judge, [d2_loop_conf.format(r=r)], [loop_overall_score.format(r=r)]),
                f"D2 loop conf round {r}",
                f"D2 loop overall score round {r}",
                round_id=r,
            )

        _append(
            center,
            model,
            "D1_Decision",
            "diagnosis",
            "case",
            "D1_Outpatient_Decision",
            "D1_Outpatient_Decision",
            _merge_conf_acc(d1_dec_doc, d1_dec_judge, [c_d1_dx], [c_gate1_dx]),
            "D1 diagnosis confidence",
            "Gate1 diagnosis score",
        )
        _append(
            center,
            model,
            "D1_Decision",
            "check",
            "case",
            "D1_Outpatient_Decision",
            "D1_Outpatient_Decision",
            _merge_conf_acc(d1_dec_doc, d1_dec_judge, [c_d1_check], [c_gate1_check]),
            "D1 check confidence",
            "Gate1 check score",
        )
        _append(
            center,
            model,
            "D1_Decision",
            "overall",
            "case",
            "D1_Outpatient_Decision",
            "D1_Outpatient_Decision",
            _merge_conf_acc(d1_dec_doc, d1_dec_judge, [c_d1_dx, c_d1_check, c_d1_plan], [c_gate1_overall]),
            "D1 confidence mean",
            "Gate1 overall score",
        )

        _append(
            center,
            model,
            "D2_Decision",
            "diagnosis",
            "case",
            "D2_Admission_Decision",
            "D2_Admission_Decision",
            _merge_conf_acc(d2_dec_doc, d2_dec_judge, [c_d2_dx], [c_gate2_dx]),
            "D2 diagnosis confidence",
            "Gate2 revised diagnosis score",
        )
        _append(
            center,
            model,
            "D2_Decision",
            "plan",
            "case",
            "D2_Admission_Decision",
            "D2_Admission_Decision",
            _merge_conf_acc(d2_dec_doc, d2_dec_judge, [c_d2_plan], [c_gate2_plan]),
            "D2 plan confidence",
            "Gate2 surgery-plan score",
        )
        _append(
            center,
            model,
            "D2_Decision",
            "overall",
            "case",
            "D2_Admission_Decision",
            "D2_Admission_Decision",
            _merge_conf_acc(d2_dec_doc, d2_dec_judge, [c_d2_dx, c_d2_plan], [c_gate2_overall]),
            "D2 confidence mean",
            "Gate2 overall score",
        )

        _append(
            center,
            model,
            "D3_Decision",
            "diagnosis",
            "case",
            "D3_Surgery_Decision",
            "D3_Surgery_Decision",
            _merge_conf_acc(d3_dec_doc, d3_dec_judge, [c_d3_dx], [c_gate3_dx]),
            "D3 diagnosis confidence",
            "D3 diagnosis score",
        )
        _append(
            center,
            model,
            "D3_Decision",
            "plan",
            "case",
            "D3_Surgery_Decision",
            "D3_Surgery_Decision",
            _merge_conf_acc(d3_dec_doc, d3_dec_judge, [c_d3_plan], [c_gate3_plan]),
            "D3 postop-plan confidence",
            "D3 postop-plan score",
        )
        _append(
            center,
            model,
            "D3_Decision",
            "overall",
            "case",
            "D3_Surgery_Decision",
            "D3_Surgery_Decision",
            _merge_conf_acc(d3_dec_doc, d3_dec_judge, [c_d3_dx, c_d3_plan], [c_gate3_overall]),
            "D3 confidence mean",
            "D3 overall score",
        )

        _append(
            center,
            model,
            "D4_Plan",
            "plan",
            "case",
            "D4_Rehab_Plan",
            "D4_Rehab_Plan",
            _merge_conf_acc(d4_doc, d4_judge, [c_d4_rehab_conf, c_d4_follow_conf], [c_d4_rehab_score, c_d4_follow_score]),
            "D4 plan confidence mean",
            "D4 rehab/follow score mean",
        )
        _append(
            center,
            model,
            "D4_Plan",
            "overall",
            "case",
            "D4_Rehab_Plan",
            "D4_Rehab_Plan",
            _merge_conf_acc(d4_doc, d4_judge, [c_d4_rehab_conf, c_d4_follow_conf], [c_d4_overall]),
            "D4 plan confidence mean",
            "D4 overall score",
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "Center",
                "Model",
                "CaseID",
                "Stage",
                "Category",
                "DetailType",
                "Round",
                "Confidence",
                "Accuracy",
                "DocSheet",
                "JudgeSheet",
                "ConfidenceSource",
                "AccuracySource",
            ]
        )
    return pd.concat(rows, ignore_index=True)


def _compute_calibration(data_root: Path) -> pd.DataFrame:
    points = _compute_calibration_points(data_root)
    if points.empty:
        return pd.DataFrame(columns=["Center", "Model", "Stage", "Accuracy", "ECE", "OverconfidenceRate", "Samples"])

    case_points = (
        points.groupby(["Center", "Model", "CaseID", "Stage", "Category"], as_index=False)
        .agg(Confidence=("Confidence", "mean"), Accuracy=("Accuracy", "mean"))
    )
    overall = case_points[case_points["Category"] == "overall"].copy()
    if overall.empty:
        return pd.DataFrame(columns=["Center", "Model", "Stage", "Accuracy", "ECE", "OverconfidenceRate", "Samples"])

    rows = []
    for (center, model, stage), g in overall.groupby(["Center", "Model", "Stage"]):
        conf = pd.to_numeric(g["Confidence"], errors="coerce")
        acc = pd.to_numeric(g["Accuracy"], errors="coerce")
        valid = conf.notna() & acc.notna()
        if int(valid.sum()) == 0:
            continue
        conf_v = conf[valid]
        acc_v = acc[valid]
        ece = _compute_ece(conf_v, acc_v, bins=10)
        high_conf = conf_v >= 0.8
        if int(high_conf.sum()) > 0:
            overconf_rate = float((acc_v[high_conf] < 0.5).mean())
        else:
            overconf_rate = np.nan
        rows.append(
            {
                "Center": center,
                "Model": model,
                "Stage": stage,
                "Accuracy": float(acc_v.mean()),
                "ECE": ece,
                "OverconfidenceRate": overconf_rate,
                "Samples": int(valid.sum()),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["Center", "Model", "Stage", "Accuracy", "ECE", "OverconfidenceRate", "Samples"])
    return pd.DataFrame(rows)


def _plot_llm_metrics(llm_xlsx: Path, out_dir: Path) -> pd.DataFrame:
    if not llm_xlsx.exists():
        return pd.DataFrame()

    xl = pd.ExcelFile(llm_xlsx)
    model_col = "被评测模型"
    center_col = "中心"
    summaries: list[pd.DataFrame] = []

    def _process_sheet(
        sheet_name: str,
        cols: list[str],
        name_map: dict[str, str],
        fig_name: str,
        title: str,
        ylabel: str,
        ylim: tuple[float, float] = (0, 1),
    ) -> None:
        if sheet_name not in xl.sheet_names:
            return
        try:
            df = xl.parse(sheet_name)
        except Exception:
            return
        if df.empty or center_col not in df.columns or model_col not in df.columns:
            return

        available = [c for c in cols if c in df.columns]
        if not available:
            return
        for c in available:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        agg = (
            df[[center_col, model_col] + available]
            .groupby([center_col, model_col])[available]
            .mean(numeric_only=True)
            .reset_index()
            .rename(columns={center_col: "Center", model_col: "Model", **{k: v for k, v in name_map.items() if k in available}})
        )
        if len(agg.columns) > 2:
            _group_bar_plot_by_center(
                agg,
                title=title,
                ylabel=ylabel,
                output_path=out_dir / fig_name,
                ylim=ylim,
            )

        means = df.groupby(model_col)[available].mean(numeric_only=True).rename(
            columns={k: v for k, v in name_map.items() if k in available}
        )
        count_col = available[0]
        counts = df.groupby(model_col)[count_col].count().rename(f"n_{sheet_name}")
        merged = means.copy()
        merged[f"n_{sheet_name}"] = counts
        summaries.append(merged)

    _process_sheet(
        "诊断TopK语义命中",
        ["k=1命中(任一GT)(0/1)", "k=3命中(任一GT)(0/1)", "k=5命中(任一GT)(0/1)"],
        {
            "k=1命中(任一GT)(0/1)": "Top1 Hit Rate",
            "k=3命中(任一GT)(0/1)": "Top3 Hit Rate",
            "k=5命中(任一GT)(0/1)": "Top5 Hit Rate",
        },
        "llm_topk_hit_rates_by_model.png",
        "LLM Diagnosis TopK Hit Rates (by Center)",
        "Hit Rate",
    )
    _process_sheet(
        "诊断质量",
        ["准确性(0-1)", "合理性(0-1)", "逻辑性(0-1)"],
        {
            "准确性(0-1)": "Diagnosis Accuracy",
            "合理性(0-1)": "Diagnosis Reasonableness",
            "逻辑性(0-1)": "Diagnosis Logic",
        },
        "llm_diagnosis_quality_by_model.png",
        "LLM Diagnosis Quality (by Center)",
        "Score (0-1)",
    )
    _process_sheet(
        "事实一致性与信息丢失",
        ["一致性得分(0-1)", "信息丢失率(0-1)"],
        {
            "一致性得分(0-1)": "Fact Consistency",
            "信息丢失率(0-1)": "Missing Rate",
        },
        "llm_fact_consistency_by_model.png",
        "LLM Fact Consistency and Missing Rate (by Center)",
        "Score (0-1)",
    )
    _process_sheet(
        "方案质量",
        ["准确性(0-1)", "安全性(0-1)", "完备性(0-1)", "合理性(0-1)"],
        {
            "准确性(0-1)": "Plan Accuracy",
            "安全性(0-1)": "Plan Safety",
            "完备性(0-1)": "Plan Completeness",
            "合理性(0-1)": "Plan Reasonableness",
        },
        "llm_plan_quality_by_model.png",
        "LLM Treatment Plan Quality (by Center)",
        "Score (0-1)",
    )
    _process_sheet(
        "推理证据链质量",
        ["得分(0-1)"],
        {"得分(0-1)": "Rationale Score"},
        "llm_rationale_quality_by_model.png",
        "LLM Rationale Quality (by Center)",
        "Score (0-1)",
    )
    _process_sheet(
        "康复-随访计划质量",
        ["康复_完整性(0-1)", "康复_合理性(0-1)", "随访_覆盖性(0-1)", "随访_合理性(0-1)"],
        {
            "康复_完整性(0-1)": "Rehab Completeness",
            "康复_合理性(0-1)": "Rehab Reasonableness",
            "随访_覆盖性(0-1)": "Follow-up Coverage",
            "随访_合理性(0-1)": "Follow-up Reasonableness",
        },
        "llm_rehab_followup_quality_by_model.png",
        "LLM Rehab & Follow-up Quality (by Center)",
        "Score (0-1)",
    )

    if not summaries:
        return pd.DataFrame()
    summary_df = pd.concat(summaries, axis=1)
    summary_df.insert(0, "Model", summary_df.index)
    return summary_df.reset_index(drop=True)


def _plot_calibration_scatter(points_df: pd.DataFrame, out_dir: Path) -> None:
    if points_df.empty:
        return
    stages = ["D1", "D2", "D3", "D4"]
    centers = _center_order(points_df["Center"])
    models = _model_order(points_df["Model"])
    color_map = {m: plt.get_cmap("tab10")(i % 10) for i, m in enumerate(models)}
    for stage in stages:
        stage_df = points_df[points_df["Stage"] == stage]
        if stage_df.empty:
            continue
        xlim = (0.0, 1.0)
        ylim = (0.0, 1.0)
        fig, axes = plt.subplots(1, len(centers), figsize=(7.5 * len(centers), 5.6), sharex=False, sharey=False)
        if len(centers) == 1:
            axes = [axes]
        for ax, center in zip(axes, centers):
            subset = stage_df[stage_df["Center"] == center].copy()
            if subset.empty:
                continue
            for model in models:
                model_df = subset[subset["Model"] == model]
                if model_df.empty:
                    continue
                jitter = (
                    (pd.util.hash_pandas_object(model_df["CaseID"], index=False).astype("uint64") % 1000) / 1000.0
                    - 0.5
                ) * 0.04
                x_vals = (model_df["Accuracy"] + jitter).clip(*xlim)
                ax.scatter(
                    x_vals,
                    model_df["Confidence"],
                    s=18,
                    alpha=0.35,
                    color=color_map.get(model),
                    edgecolor="none",
                )
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
            diag_min = max(xlim[0], ylim[0])
            diag_max = min(xlim[1], ylim[1])
            ax.plot([diag_min, diag_max], [diag_min, diag_max], linestyle="--", color="black", linewidth=1)
            ax.set_title(CENTER_LABELS.get(center, center))
            ax.set_xlabel("Accuracy")
            ax.set_ylabel("Confidence")
            ax.grid(axis="both", linestyle="--", alpha=0.3)
        handles = [
            plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=color_map[m], markeredgecolor="white", markersize=7, label=m)
            for m in models
        ]
        fig.legend(handles, models, loc="upper center", ncol=min(len(models), 4), bbox_to_anchor=(0.5, 0.93))
        fig.suptitle(f"Calibration Scatter (Accuracy vs Confidence) - {stage}", y=0.98)
        fig.tight_layout(rect=(0, 0.16, 1, 0.82))
        plt.savefig(out_dir / f"calibration_scatter_{stage.lower()}.png", dpi=200)
        plt.close()


def _write_readme(out_dir: Path) -> None:
    readme = out_dir / "README.md"
    content = """# 图表说明（论文风格图注）

## 目录结构与用途
- `algorithmic/`：系统性与流程性指标（通过率、效率、judge综合得分）
- `sankey/`：病例级六阶段流向桑基图（含节点n与比例）
- `alignment/`：人工评分与 Judge/LLM 的阶段对齐图（多风格备选）
- `consistency/`：一致性指标（散点/气泡 + alignment风格双线）
- `calibration/`：置信度-准确率校准（气泡+连线/ECE/分箱曲线）
- `llm/full/*`：LLM全量指标（推理/记忆/一致性，多风格）
- `llm/small/summary/`：LLM小规模指标（TopK/质量类）
- `special/`：D1特殊病例统计
- `source_data/`：各图可复现源数据（已归档到各子目录下）

## 阶段映射（图例缩写）
`D1_Loop`（门诊Loop）、`D1_Decision`（门诊决策）  
`D2_Loop`（入院Loop）、`D2_Decision`（入院决策）  
`D3_Decision`（术后决策）、`D4_Plan`（康复/随访方案）

---
## A. 系统性与流程指标（Algorithmic）
图A1 `algorithmic/algorithmic_check_match_rate_by_model.png`：D1/D2检查匹配率（case mean）。柱上数值为均值；NA表示该中心-模型未评测。

图A2 `algorithmic/algorithmic_loop_inefficiency_by_model.png`：无效循环率（0-match）对比。若样本数为0则标记为NA，非0不表示失败。

图A3 `algorithmic/algorithmic_stage_pass_rate_by_model.png`：基于“通过退出明细”的阶段通过率（D1、D2一审、D2二审、D3）。D1特殊计入未通过。

图A4 `algorithmic/algorithmic_judge_scores_by_stage.png`：Judge综合评分在六阶段的对比（0-1）。

图A5 `algorithmic/algorithmic_judge_score_pathways_<center>.png`：临床路径曲线图（诊断/检查/方案三条线）。  
诊断路径：D1→D2→D3；检查路径：D1 Loop → D1决策(D2检查) → D2 Loop；方案路径：D2→D3→D4。  
纵轴为judge评分（0-1），用于论文Results中“诊断/检查/方案质量”章节。

图A6 `algorithmic/algorithmic_judge_scores_stagewise_<center>.png`：六阶段Judge分数（按中心）。  
图A6-grid `algorithmic/algorithmic_judge_scores_stagewise_grid.png`：三中心拼图。

图A7 `algorithmic/algorithmic_loop_inefficiency_stagewise_<center>.png`：Loop无效率（D1/D2）。  
图A7-grid `algorithmic/algorithmic_loop_inefficiency_stagewise_grid.png`：三中心拼图。

图A8 `algorithmic/algorithmic_stage_no_exit_rate_<center>.png`：六阶段“未发生退出”比例（基于通过退出明细）。  
图A8-grid `algorithmic/algorithmic_stage_no_exit_rate_grid.png`：三中心拼图。

---
## B. 人机对齐与一致性
图B1 `alignment/alignment_result_quality_stagewise_<center>.png`：人工“结果质量” vs Judge综合评分（×5）分阶段对齐。  
图B1-alt `alignment/alignment_result_quality_stagewise_alt_<center>.png`：同数据不同配色备选。
图B1-bars `alignment/alignment_result_quality_stagewise_bars_<center>.png`：结果质量柱状对比（每阶段/模型）。
图B1-grid `alignment/alignment_result_quality_stagewise_grid.png`：结果质量三中心拼图。  
图B1-bars-grid `alignment/alignment_result_quality_stagewise_bars_grid.png`：结果质量柱状三中心拼图。

图B2 `alignment/alignment_reasoning_quality_stagewise_<center>.png`：人工“推理合理性” vs LLM推理质量（×5）分阶段对齐。  
图B2-alt `alignment/alignment_reasoning_quality_stagewise_alt_<center>.png`：同数据不同配色备选。
图B2-bars `alignment/alignment_reasoning_quality_stagewise_bars_<center>.png`：推理质量柱状对比（每阶段/模型）。
图B2-grid `alignment/alignment_reasoning_quality_stagewise_grid.png`：推理质量三中心拼图。  
图B2-bars-grid `alignment/alignment_reasoning_quality_stagewise_bars_grid.png`：推理质量柱状三中心拼图。

图B3 `consistency/consistency_score_alignment_style_<center>.png`：一致性（打分）alignment风格，展示医生均值 vs LLM均值（双线）。  
图B4 `consistency/consistency_rank_alignment_style_<center>.png`：一致性（排名）alignment风格，展示医生均值Rank vs LLM均值Rank。
图B3-grid `consistency/consistency_score_alignment_style_grid.png`：三中心总览拼图。  
图B4-grid `consistency/consistency_rank_alignment_style_grid.png`：三中心总览拼图。

图B5 `consistency/consistency_rank_bubble_<center>_llm_vs_<doctor>.png`：排名一致性气泡图（备选风格）。  
图B6 `consistency/consistency_score_scatter_<center>_llm_vs_<doctor>.png`：打分一致性散点（备选风格）。

---
## C. 校准（置信度-准确率）
图C1 `calibration/calibration_ece_stagewise_<center>.png`：ECE分阶段柱状（分箱=10）。  
图C2 `calibration/calibration_bubble_diagnosis_stagewise_<center>.png`：诊断校准气泡图（气泡大小=样本数，叠加连线表示趋势）。  
图C3 `calibration/calibration_bubble_check_stagewise_<center>.png`：检查校准（D1 Loop + D1决策 + D2 Loop）。  
图C4 `calibration/calibration_bubble_plan_stagewise_<center>.png`：方案校准（D2/D3/D4）。  
图C5 `calibration/calibration_reliability_stagewise_<center>.png`：总体六阶段校准气泡（叠加趋势线）。  
图C6 `calibration/calibration_line_<category>_stagewise_<center>.png`：独立连线版（按置信度分箱后连线）。

---
## D. LLM 全量指标（Full）
图D1 `llm/full/reasoning/llm_reasoning_quality_stagewise_<center>.png`：推理质量六阶段柱状对比。  
图D1b `llm/full/reasoning/llm_reasoning_quality_stagewise_modelband_<center>.png`：推理质量“模型趋势线+误差带”风格（备选）。

图D2 `llm/full/consistency/llm_consistency_cross_stagewise_<center>.png`：跨阶段一致性（D1-D4决策）。  
图D2b `llm/full/consistency/llm_consistency_cross_stagewise_linebar_<center>.png`：一致性折线+样本/冲突柱。  
图D2b-grid `llm/full/consistency/llm_consistency_cross_stagewise_linebar_grid.png`：一致性折线+柱三中心拼图。  
图D2c `llm/full/consistency/llm_consistency_cross_stagewise_band_<center>.png`：一致性均值±标准差。  
图D2d `llm/full/consistency/llm_consistency_cross_stagewise_lines_<center>.png`：模型趋势线。  
图D2e `llm/full/consistency/llm_consistency_cross_stagewise_heatmap_<center>.png`：模型×阶段热力图。  
图D2f `llm/full/consistency/llm_consistency_cross_stagewise_modelband_<center>.png`：模型趋势线+误差带（备选）。
图D2g `llm/full/consistency/llm_consistency_cross_stagewise_tag_distribution_<center>.png`：跨阶段一致性错误标签占比堆叠柱（`stage_conflict` / `fact_shift` / `other`），柱顶标注 `tag数/样本数`。

图D2h `llm/full/consistency/llm_consistency_fact_stagewise_<center>.png`：事实一致性（D1-D4决策）。  
图D2i `llm/full/consistency/llm_consistency_fact_stagewise_linebar_<center>.png`：事实一致性折线+样本柱。  
图D2j `llm/full/consistency/llm_consistency_fact_stagewise_tag_distribution_<center>.png`：事实一致性错误标签占比堆叠柱（`contradiction` / `hallucination` / `missing` / `unsupported_detail`）。

图D3 `llm/full/memory/llm_memory_stagewise_<center>.png`：记忆保持（D2-D4决策）。  
图D3b `llm/full/memory/llm_memory_stagewise_line_<center>.png`：继承/利用/整体三线。  
图D3b2 `llm/full/memory/llm_memory_stagewise_linebar_<center>.png`：总体折线 + 继承/利用柱（风格备选）。  
图D3b2-grid `llm/full/memory/llm_memory_stagewise_linebar_grid.png`：记忆保持折线+柱三中心拼图。  
图D3c `llm/full/memory/llm_memory_stagewise_band_<center>.png`：均值±标准差。  
图D3d `llm/full/memory/llm_memory_stagewise_lines_<center>.png`：模型趋势线。  
图D3e `llm/full/memory/llm_memory_stagewise_heatmap_<center>.png`：模型×阶段热力图。  
图D3f `llm/full/memory/llm_memory_stagewise_modelband_<center>.png`：模型趋势线+误差带（备选）。
图D3g `llm/full/memory/llm_memory_stagewise_tag_distribution_<center>.png`：记忆保持错误标签占比堆叠柱（`missing_prior_info` / `unused_key_info` / `other`）。

---
## E. LLM 小规模指标（Small）
图E1 `llm/small/summary/llm_small_topk_lines_combined.png`：Top-1/3/5 命中率多中心折线（论文优先）。  
图E2 `llm/small/summary/llm_small_*_bars_combined.png`：其它小规模指标统一水平条形对比（无样本数列）。

---
## Source Data（可复现）
每张图在同级 `source_data/<figure_stem>_source.xlsx` 中包含：  
1) 作图说明（含指标定义/缩写解释）  
2) 数据来源（具体Excel路径/Sheet/列说明）  
3) 原始明细（仅来自允许数据源）  
4) 计算过程（必要中间表）  
5) 汇总作图表（作图用结果表）
"""
    readme.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate English-only figures from latest metrics outputs.")
    parser.add_argument("--run-id", default="latest")
    parser.add_argument("--data-root", default=None, help="Override data root (default: <project_root>/data)")
    parser.add_argument(
        "--summary-xlsx",
        default=None,
        help="Override summary workbook path (default: outputs/<run_id>/summary/总览.xlsx)",
    )
    parser.add_argument(
        "--llm-xlsx",
        default=None,
        help="Override LLM results workbook path (default: outputs/<run_id>/summary/llm_results_gemini-2.5-pro__gala_api.xlsx)",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    run_id = args.run_id
    data_root = Path(args.data_root) if args.data_root else project_root / "data"
    summary_xlsx = Path(args.summary_xlsx) if args.summary_xlsx else project_root / "outputs" / run_id / "summary" / "总览.xlsx"
    llm_xlsx = (
        Path(args.llm_xlsx)
        if args.llm_xlsx
        else project_root / "outputs" / run_id / "summary" / "llm_results_gemini-2.5-pro__gala_api.xlsx"
    )

    out_dir = project_root / "outputs" / run_id / "figures"
    _ensure_dir(out_dir)

    summary_df = _load_summary_sheet(summary_xlsx)
    algo_summary = _plot_algorithmic(summary_df, out_dir, data_root)
    llm_summary = _plot_llm_metrics(llm_xlsx, out_dir)

    # Loop scores
    loop_scores = _compute_loop_scores(data_root)
    if not loop_scores.empty:
        _group_bar_plot_by_center(
            loop_scores,
            title="Judge Loop Score by Model (by Center)",
            ylabel="Score (0-1)",
            output_path=out_dir / "algorithmic_loop_scores_by_model.png",
            ylim=(0, 1),
        )

    # Special cases
    special_df = _compute_special_case_counts(data_root)
    if not special_df.empty:
        special_df.to_csv(project_root / "outputs" / run_id / "summary" / "special_d1_case_counts_en.csv", index=False)
        _group_bar_plot_by_center(
            special_df[["Center", "Model", "Special D1 Cases"]],
            title="D1 Special Case Count by Model (by Center)",
            ylabel="Count",
            output_path=out_dir / "special_d1_case_counts_by_model.png",
        )

    # Calibration
    calib_df = _compute_calibration(data_root)
    if not calib_df.empty:
        calib_df.to_csv(project_root / "outputs" / run_id / "summary" / "calibration_summary_en.csv", index=False)
        pivot = calib_df.pivot_table(index=["Center", "Model"], columns="Stage", values="ECE", aggfunc="mean").reset_index()
        pivot = pivot.rename(columns={"D1": "D1 ECE", "D2": "D2 ECE", "D3": "D3 ECE"})
        ece_values = pivot[["D1 ECE", "D2 ECE", "D3 ECE"]].to_numpy()
        ylim = _dynamic_limits(ece_values)
        _group_bar_plot_by_center(
            pivot[["Center", "Model", "D1 ECE", "D2 ECE", "D3 ECE"]],
            title="Calibration Error (ECE) by Model (by Center)",
            ylabel="ECE",
            output_path=out_dir / "calibration_ece_by_model.png",
            ylim=ylim,
        )
        _line_plot_by_center(
            calib_df.rename(columns={"Stage": "Stage", "ECE": "ECE"}),
            x_col="Stage",
            y_col="ECE",
            title="Calibration Error (ECE) across Stages",
            ylabel="ECE",
            output_path=out_dir / "calibration_ece_by_stage_by_center.png",
            x_order=["D1", "D2", "D3"],
            ylim=ylim,
            show_mean_line=True,
        )
        calib_points = _compute_calibration_points(data_root)
        if not calib_points.empty:
            _plot_calibration_scatter(calib_points, out_dir)

    algo_summary.to_csv(project_root / "outputs" / run_id / "summary" / "algorithmic_metrics_summary_en.csv", index=False)
    llm_summary.to_csv(project_root / "outputs" / run_id / "summary" / "llm_metrics_summary_en.csv", index=False)
    _write_readme(out_dir)


if __name__ == "__main__":
    main()
