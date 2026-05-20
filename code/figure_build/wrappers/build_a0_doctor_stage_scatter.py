from __future__ import annotations

import argparse
import hashlib
import shutil
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]

MANUAL_METRIC_DIR = ROOT / "analysis_viz" / "data" / "derived" / "metrics" / "manual"

FIG_BASE_DIR = ROOT / "analysis_viz" / "figures" / "v2_subplots" / "_supplementary" / "A0_consistency_tables" / "doctor_scatter"

SOURCE_MAIN_DIR = ROOT / "analysis_viz" / "data" / "derived" / "figdata" / "v2_subplots" / "A0_consistency_tables"
SOURCE_SUPP_DIR = ROOT / "analysis_viz" / "figures" / "v2_subplots" / "_supplementary" / "A0_consistency_tables" / "source_data"

METRIC_TO_FILE = {
    "result": MANUAL_METRIC_DIR / "manual_result_quality_source.xlsx",
    "reasoning": MANUAL_METRIC_DIR / "manual_reasoning_quality_source.xlsx",
}

METRIC_TO_CN = {
    "result": "结果评分",
    "reasoning": "推理评分",
}

STAGE_ORDER = ["D1_Loop", "D1_Decision", "D2_Loop", "D2_Decision", "D3_Decision", "D4_Plan"]
STAGE_TO_CN = {
    "D1_Loop": "门诊检查",
    "D1_Decision": "门诊决策",
    "D2_Loop": "住院检查",
    "D2_Decision": "住院决策",
    "D3_Decision": "术后决策",
    "D4_Plan": "随访计划",
}

MODEL_ORDER = ["deepseek-v3", "gpt-5", "gemini-2.5p", "grok-4", "claude-4.1"]
MODEL_COLOR = {
    "deepseek-v3": "#2ca02c",
    "gpt-5": "#9467bd",
    "gemini-2.5p": "#d62728",
    "grok-4": "#ff7f0e",
    "claude-4.1": "#17becf",
}

STAGE_SCOPE = {
    "D1_Loop": "check",
    "D2_Loop": "check",
    "D1_Decision": "decision",
    "D2_Decision": "decision",
    "D3_Decision": "decision",
    "D4_Plan": "decision",
}

SCOPE_TO_STAGES = {
    "check": ["D1_Loop", "D2_Loop"],
    "decision": ["D1_Decision", "D2_Decision", "D3_Decision", "D4_Plan"],
}

SCOPE_TO_CN = {"check": "检查环节", "decision": "诊断环节"}


def _setup_matplotlib_fonts() -> None:
    # 优先使用常见中文字体，避免中文标题渲染为方块或告警
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "WenQuanYi Zen Hei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def _ordered_models(models: Iterable[str]) -> list[str]:
    found = [str(m) for m in models if str(m)]
    found_set = set(found)
    ordered = [m for m in MODEL_ORDER if m in found_set]
    extra = sorted(found_set - set(ordered))
    return ordered + extra


def _model_offsets(models: list[str], step: float = 0.08) -> dict[str, tuple[float, float]]:
    # 最多 5 个主模型，使用固定偏移避免同格点完全重叠
    base = [(-step, -step), (step, -step), (-step, step), (step, step), (0.0, 0.0)]
    out: dict[str, tuple[float, float]] = {}
    for i, m in enumerate(models):
        if i < len(base):
            out[m] = base[i]
        else:
            # 兜底：额外模型沿圆周放置
            r = step * 1.2
            theta = (i - len(base)) * (2.0 * np.pi / max(1, len(models)))
            out[m] = (float(r * np.cos(theta)), float(r * np.sin(theta)))
    return out


def _stable_rng(key: str) -> np.random.Generator:
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    seed = int(digest[:8], 16)
    return np.random.default_rng(seed)


def _jitter(count: int, scale: float, key: str) -> np.ndarray:
    if count <= 0:
        return np.array([], dtype=float)
    rng = _stable_rng(key)
    return rng.normal(0.0, scale, count)


def _archive_legacy_stage_scatter(fig_dir: Path) -> list[Path]:
    # 将旧版“按单环节输出”的散点图移入 archieve，避免与新图混淆
    legacy_patterns = [
        "A0_doctor_score_scatter_*.png",
        "A0_doctor_score_diff_scatter_*.png",
    ]
    moved: list[Path] = []
    if not fig_dir.exists():
        return moved
    archive_dir = fig_dir / "archieve"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for pat in legacy_patterns:
        for src in sorted(fig_dir.glob(pat)):
            dst = archive_dir / f"{stamp}_{src.name}"
            idx = 1
            while dst.exists():
                dst = archive_dir / f"{stamp}_{idx}_{src.name}"
                idx += 1
            shutil.move(str(src), str(dst))
            moved.append(dst)
    return moved


def _load_detail(metric: str) -> pd.DataFrame:
    path = METRIC_TO_FILE[metric]
    if not path.exists():
        raise FileNotFoundError(f"源文件不存在: {path}")
    df = pd.read_excel(path, sheet_name="detail_used")
    required = {"doctor", "center", "model", "model_short", "case_id", "stage", "stage_cn", "score_0_5"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"detail_used 缺少必要列: {missing}")
    df = df.copy()
    df["score_0_5"] = pd.to_numeric(df["score_0_5"], errors="coerce")
    df = df[df["score_0_5"].notna()].copy()
    df["stage"] = df["stage"].astype(str)
    df["stage_cn"] = df["stage"].map(STAGE_TO_CN).fillna(df["stage_cn"].astype(str))
    return df


def _build_pair_detail(detail: pd.DataFrame) -> pd.DataFrame:
    keys = ["center", "model", "model_short", "case_id", "stage", "stage_cn"]
    rows: list[dict[str, object]] = []
    for key_vals, sub in detail.groupby(keys, dropna=False):
        d = (
            sub[["doctor", "score_0_5"]]
            .dropna(subset=["doctor", "score_0_5"])
            .groupby("doctor", as_index=False)["score_0_5"]
            .mean()
            .sort_values("doctor", kind="mergesort")
        )
        doctors = d["doctor"].astype(str).tolist()
        if len(doctors) < 2:
            continue
        score_map = {str(r["doctor"]): float(r["score_0_5"]) for _, r in d.iterrows()}
        for doctor_a, doctor_b in combinations(doctors, 2):
            score_a = score_map[doctor_a]
            score_b = score_map[doctor_b]
            rows.append(
                {
                    "center": key_vals[0],
                    "model": key_vals[1],
                    "model_short": key_vals[2],
                    "case_id": key_vals[3],
                    "stage": key_vals[4],
                    "stage_cn": key_vals[5],
                    "doctor_a": doctor_a,
                    "doctor_b": doctor_b,
                    "score_a": score_a,
                    "score_b": score_b,
                    "score_mean": float((score_a + score_b) / 2.0),
                    "score_diff": float(score_a - score_b),
                    "score_abs_diff": float(abs(score_a - score_b)),
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError("未生成医生配对数据，无法绘图")
    return out


def _build_plot_detail(pair_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    score_a = pair_df[["center", "model", "model_short", "case_id", "stage", "stage_cn", "score_a"]].copy()
    score_a["doctor_side"] = "Doctor 1"
    score_a = score_a.rename(columns={"score_a": "score"})

    score_b = pair_df[["center", "model", "model_short", "case_id", "stage", "stage_cn", "score_b"]].copy()
    score_b["doctor_side"] = "Doctor 2"
    score_b = score_b.rename(columns={"score_b": "score"})

    score_detail = pd.concat([score_a, score_b], ignore_index=True)
    score_detail["stage_scope"] = score_detail["stage"].map(STAGE_SCOPE).fillna("other")
    score_detail["stage_scope_cn"] = score_detail["stage_scope"].map(SCOPE_TO_CN).fillna(score_detail["stage_scope"])
    score_detail["score"] = pd.to_numeric(score_detail["score"], errors="coerce")
    score_detail = score_detail[score_detail["score"].notna()].copy()

    diff_detail = pair_df[
        ["center", "model", "model_short", "case_id", "stage", "stage_cn", "score_diff", "score_abs_diff", "score_mean"]
    ].copy()
    diff_detail["stage_scope"] = diff_detail["stage"].map(STAGE_SCOPE).fillna("other")
    diff_detail["stage_scope_cn"] = diff_detail["stage_scope"].map(SCOPE_TO_CN).fillna(diff_detail["stage_scope"])
    diff_detail["score_diff"] = pd.to_numeric(diff_detail["score_diff"], errors="coerce")
    diff_detail["score_abs_diff"] = pd.to_numeric(diff_detail["score_abs_diff"], errors="coerce")
    diff_detail["score_mean"] = pd.to_numeric(diff_detail["score_mean"], errors="coerce")
    diff_detail = diff_detail[diff_detail["score_abs_diff"].notna()].copy()
    return score_detail, diff_detail


def _plot_score_distribution_by_scope(
    score_detail: pd.DataFrame, out_dir: Path, metric_cn: str, scope: str
) -> tuple[dict[str, object] | None, pd.DataFrame]:
    stages = [s for s in SCOPE_TO_STAGES.get(scope, []) if s in set(score_detail["stage"].astype(str))]
    if not stages:
        return None, pd.DataFrame()

    sub = score_detail[score_detail["stage"].isin(stages)].copy()
    nrows = len(stages)
    fig, axes = plt.subplots(nrows, 1, figsize=(7.6, 2.0 * nrows + 0.8), sharex=True)
    if nrows == 1:
        axes = [axes]

    out_rows: list[pd.DataFrame] = []
    legend_handles = None
    legend_labels = None

    for idx, stage in enumerate(stages):
        ax = axes[idx]
        stage_sub = sub[sub["stage"] == stage].copy()
        stage_cn = str(stage_sub["stage_cn"].iloc[0]) if not stage_sub.empty else STAGE_TO_CN.get(stage, stage)
        models = _ordered_models(stage_sub["model_short"].astype(str).tolist())
        offsets = _model_offsets(models, step=0.065)
        doctor_base = {"Doctor 1": 0.0, "Doctor 2": 1.0}

        stage_rows: list[pd.DataFrame] = []
        for model in models:
            for doctor_side in ["Doctor 1", "Doctor 2"]:
                msub = stage_sub[
                    (stage_sub["model_short"].astype(str) == model) & (stage_sub["doctor_side"].astype(str) == doctor_side)
                ].copy()
                if msub.empty:
                    continue
                base_x = doctor_base[doctor_side]
                dx, _ = offsets.get(model, (0.0, 0.0))
                jit = _jitter(len(msub), 0.016, f"{scope}|{stage}|{doctor_side}|{model}|score")
                x = base_x + dx + jit
                y = pd.to_numeric(msub["score"], errors="coerce").to_numpy(dtype=float)
                ax.scatter(
                    x,
                    y,
                    s=16,
                    alpha=0.72,
                    color=MODEL_COLOR.get(model, "#666666"),
                    edgecolors="none",
                    label=model if doctor_side == "Doctor 1" else None,
                )
                tmp = msub.copy()
                tmp["plot_x"] = x
                tmp["plot_y"] = y
                stage_rows.append(tmp)

        if stage_rows:
            out_rows.append(pd.concat(stage_rows, ignore_index=True))

        ax.set_ylim(0.7, 5.3)
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_xlim(-0.45, 1.45)
        ax.set_xticks([])
        ax.grid(axis="y", alpha=0.25, linestyle=":")
        ax.axvline(0.5, color="#aaaaaa", linewidth=0.8, alpha=0.55)
        ax.text(-0.10, 0.5, stage_cn, transform=ax.transAxes, ha="right", va="center", fontsize=10, fontweight="bold")
        ax.text(1.01, 0.88, f"N={len(stage_sub)}", transform=ax.transAxes, ha="left", va="center", fontsize=9, color="#333333")

        if idx == 0:
            ax.text(0.0, 5.18, "Doctor 1", ha="center", va="bottom", fontsize=11, color="#222222")
            ax.text(1.0, 5.18, "Doctor 2", ha="center", va="bottom", fontsize=11, color="#222222")
            legend_handles, legend_labels = ax.get_legend_handles_labels()

    if legend_handles:
        fig.legend(
            legend_handles,
            legend_labels,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.01),
            frameon=False,
            fontsize=9,
            ncol=max(1, len(legend_labels)),
        )
    fig.suptitle(f"{SCOPE_TO_CN.get(scope, scope)} 医生评分分布（分医生，{metric_cn}）", y=0.995, fontsize=14)
    fig.tight_layout(rect=[0.06, 0.08, 0.98, 0.96])

    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / f"A0_doctor_score_distribution_{scope}.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)

    detail = pd.concat(out_rows, ignore_index=True) if out_rows else pd.DataFrame()
    fig_row = {
        "图类型": "医生评分分布点图_分医生",
        "阶段编码": "|".join(stages),
        "阶段中文": "|".join(STAGE_TO_CN.get(s, s) for s in stages),
        "文件名": out_png.name,
        "样本数": int(len(sub)),
    }
    return fig_row, detail


def _plot_score_distribution_merged_by_scope(
    score_detail: pd.DataFrame, out_dir: Path, metric_cn: str, scope: str
) -> tuple[dict[str, object] | None, pd.DataFrame]:
    stages = [s for s in SCOPE_TO_STAGES.get(scope, []) if s in set(score_detail["stage"].astype(str))]
    if not stages:
        return None, pd.DataFrame()

    sub = score_detail[score_detail["stage"].isin(stages)].copy()
    nrows = len(stages)
    fig, axes = plt.subplots(nrows, 1, figsize=(7.0, 2.0 * nrows + 0.8), sharex=True)
    if nrows == 1:
        axes = [axes]

    out_rows: list[pd.DataFrame] = []
    legend_handles = None
    legend_labels = None

    for idx, stage in enumerate(stages):
        ax = axes[idx]
        stage_sub = sub[sub["stage"] == stage].copy()
        stage_cn = str(stage_sub["stage_cn"].iloc[0]) if not stage_sub.empty else STAGE_TO_CN.get(stage, stage)
        models = _ordered_models(stage_sub["model_short"].astype(str).tolist())
        offsets = _model_offsets(models, step=0.07)

        stage_rows: list[pd.DataFrame] = []
        for model in models:
            msub = stage_sub[stage_sub["model_short"].astype(str) == model].copy()
            if msub.empty:
                continue
            dx, _ = offsets.get(model, (0.0, 0.0))
            jit = _jitter(len(msub), 0.016, f"{scope}|{stage}|{model}|score_merged")
            x = dx + jit
            y = pd.to_numeric(msub["score"], errors="coerce").to_numpy(dtype=float)
            ax.scatter(
                x,
                y,
                s=16,
                alpha=0.72,
                color=MODEL_COLOR.get(model, "#666666"),
                edgecolors="none",
                label=model,
            )
            tmp = msub.copy()
            tmp["plot_x"] = x
            tmp["plot_y"] = y
            stage_rows.append(tmp)
        if stage_rows:
            out_rows.append(pd.concat(stage_rows, ignore_index=True))

        ax.set_ylim(0.7, 5.3)
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_xlim(-0.45, 0.45)
        ax.set_xticks([])
        ax.grid(axis="y", alpha=0.25, linestyle=":")
        ax.text(-0.10, 0.5, stage_cn, transform=ax.transAxes, ha="right", va="center", fontsize=10, fontweight="bold")
        ax.text(1.01, 0.88, f"N={len(stage_sub)}", transform=ax.transAxes, ha="left", va="center", fontsize=9, color="#333333")
        if idx == 0:
            legend_handles, legend_labels = ax.get_legend_handles_labels()

    if legend_handles:
        fig.legend(
            legend_handles,
            legend_labels,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.01),
            frameon=False,
            fontsize=9,
            ncol=max(1, len(legend_labels)),
        )
    fig.suptitle(f"{SCOPE_TO_CN.get(scope, scope)} 医生评分分布（合并医生，{metric_cn}）", y=0.995, fontsize=14)
    fig.tight_layout(rect=[0.06, 0.08, 0.98, 0.96])

    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / f"A0_doctor_score_distribution_merged_{scope}.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)

    detail = pd.concat(out_rows, ignore_index=True) if out_rows else pd.DataFrame()
    fig_row = {
        "图类型": "医生评分分布点图_合并医生",
        "阶段编码": "|".join(stages),
        "阶段中文": "|".join(STAGE_TO_CN.get(s, s) for s in stages),
        "文件名": out_png.name,
        "样本数": int(len(sub)),
    }
    return fig_row, detail


def _plot_diff_distribution_by_scope(
    diff_detail: pd.DataFrame, out_dir: Path, metric_cn: str, scope: str
) -> tuple[dict[str, object] | None, pd.DataFrame]:
    stages = [s for s in SCOPE_TO_STAGES.get(scope, []) if s in set(diff_detail["stage"].astype(str))]
    if not stages:
        return None, pd.DataFrame()

    sub = diff_detail[diff_detail["stage"].isin(stages)].copy()
    nrows = len(stages)
    fig, axes = plt.subplots(nrows, 1, figsize=(7.0, 2.0 * nrows + 0.8), sharex=True)
    if nrows == 1:
        axes = [axes]

    out_rows: list[pd.DataFrame] = []
    legend_handles = None
    legend_labels = None

    for idx, stage in enumerate(stages):
        ax = axes[idx]
        stage_sub = sub[sub["stage"] == stage].copy()
        stage_cn = str(stage_sub["stage_cn"].iloc[0]) if not stage_sub.empty else STAGE_TO_CN.get(stage, stage)
        models = _ordered_models(stage_sub["model_short"].astype(str).tolist())
        offsets = _model_offsets(models, step=0.07)

        stage_rows: list[pd.DataFrame] = []
        for model in models:
            msub = stage_sub[stage_sub["model_short"].astype(str) == model].copy()
            if msub.empty:
                continue
            dx, _ = offsets.get(model, (0.0, 0.0))
            jit = _jitter(len(msub), 0.016, f"{scope}|{stage}|{model}|diff")
            x = dx + jit
            y = pd.to_numeric(msub["score_abs_diff"], errors="coerce").to_numpy(dtype=float)
            ax.scatter(
                x,
                y,
                s=16,
                alpha=0.72,
                color=MODEL_COLOR.get(model, "#666666"),
                edgecolors="none",
                label=model,
            )
            tmp = msub.copy()
            tmp["plot_x"] = x
            tmp["plot_y"] = y
            stage_rows.append(tmp)
        if stage_rows:
            out_rows.append(pd.concat(stage_rows, ignore_index=True))

        mean_abs_diff = float(pd.to_numeric(stage_sub["score_abs_diff"], errors="coerce").mean())
        ax.axhline(0.0, linestyle="--", linewidth=1.0, color="#666666")
        ax.axhline(mean_abs_diff, linestyle="-.", linewidth=1.0, color="#b91c1c")
        ax.set_ylim(-0.2, 4.4)
        ax.set_yticks([0, 1, 2, 3, 4])
        ax.set_xlim(-0.45, 0.45)
        ax.set_xticks([])
        ax.grid(axis="y", alpha=0.25, linestyle=":")
        ax.text(-0.10, 0.5, stage_cn, transform=ax.transAxes, ha="right", va="center", fontsize=10, fontweight="bold")
        ax.text(
            1.01,
            0.88,
            f"N={len(stage_sub)} mean(|diff|)={mean_abs_diff:.3f}",
            transform=ax.transAxes,
            ha="left",
            va="center",
            fontsize=9,
            color="#333333",
        )
        if idx == 0:
            legend_handles, legend_labels = ax.get_legend_handles_labels()

    if legend_handles:
        fig.legend(
            legend_handles,
            legend_labels,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.01),
            frameon=False,
            fontsize=9,
            ncol=max(1, len(legend_labels)),
        )
    fig.suptitle(f"{SCOPE_TO_CN.get(scope, scope)} 医生绝对分差分布（{metric_cn}）", y=0.995, fontsize=14)
    fig.tight_layout(rect=[0.06, 0.08, 0.98, 0.96])

    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / f"A0_doctor_diff_distribution_{scope}.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)

    detail = pd.concat(out_rows, ignore_index=True) if out_rows else pd.DataFrame()
    fig_row = {
        "图类型": "医生绝对分差分布点图",
        "阶段编码": "|".join(stages),
        "阶段中文": "|".join(STAGE_TO_CN.get(s, s) for s in stages),
        "文件名": out_png.name,
        "样本数": int(len(sub)),
    }
    return fig_row, detail


def _plot_diff_hist_by_scope(
    diff_detail: pd.DataFrame, out_dir: Path, metric_cn: str, scope: str
) -> tuple[dict[str, object] | None, pd.DataFrame]:
    stages = [s for s in SCOPE_TO_STAGES.get(scope, []) if s in set(diff_detail["stage"].astype(str))]
    if not stages:
        return None, pd.DataFrame()

    sub = diff_detail[diff_detail["stage"].isin(stages)].copy()
    nrows = len(stages)
    fig, axes = plt.subplots(nrows, 1, figsize=(6.8, 1.9 * nrows + 0.8), sharex=True)
    if nrows == 1:
        axes = [axes]

    hist_rows: list[dict[str, object]] = []
    bins = list(range(0, 5))
    for idx, stage in enumerate(stages):
        ax = axes[idx]
        stage_sub = sub[sub["stage"] == stage].copy()
        stage_cn = str(stage_sub["stage_cn"].iloc[0]) if not stage_sub.empty else STAGE_TO_CN.get(stage, stage)
        vals = pd.to_numeric(stage_sub["score_abs_diff"], errors="coerce").round().clip(0, 4).dropna().astype(int)
        counts = vals.value_counts().reindex(bins, fill_value=0).sort_index()
        ax.bar(counts.index.to_list(), counts.values.tolist(), color="#8fa3ad", edgecolor="white", linewidth=0.8)
        ax.axvline(0.0, linestyle="--", linewidth=1.0, color="#666666")
        ax.grid(axis="y", alpha=0.25, linestyle=":")
        ymax = max(1, int(counts.max()))
        ax.set_ylim(0, ymax * 1.22)
        ax.set_xlim(-0.6, 4.6)
        ax.text(-0.10, 0.5, stage_cn, transform=ax.transAxes, ha="right", va="center", fontsize=10, fontweight="bold")
        for x, c in counts.items():
            ax.text(float(x), float(c) + max(0.02 * ymax, 0.2), f"{int(c)}", ha="center", va="bottom", fontsize=8, color="#333333")
            hist_rows.append(
                {
                    "stage_scope": scope,
                    "stage_scope_cn": SCOPE_TO_CN.get(scope, scope),
                    "stage": stage,
                    "stage_cn": stage_cn,
                    "score_abs_diff_bin": int(x),
                    "count": int(c),
                }
            )
        if idx != nrows - 1:
            ax.tick_params(axis="x", labelbottom=False)

    axes[-1].set_xlabel("Absolute Score Difference |Doctor 1 - Doctor 2| (bins: 0,1,2,3,4)")
    axes[-1].set_xticks(bins)
    axes[-1].set_xticklabels([str(b) for b in bins])
    fig.suptitle(f"{SCOPE_TO_CN.get(scope, scope)} 绝对分差频率柱状图（{metric_cn}）", y=0.995, fontsize=14)
    fig.tight_layout(rect=[0.06, 0.02, 0.98, 0.97])

    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / f"A0_doctor_diff_hist_{scope}.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)

    hist_df = pd.DataFrame(hist_rows)
    fig_row = {
        "图类型": "医生绝对分差频率柱状图",
        "阶段编码": "|".join(stages),
        "阶段中文": "|".join(STAGE_TO_CN.get(s, s) for s in stages),
        "文件名": out_png.name,
        "样本数": int(len(sub)),
    }
    return fig_row, hist_df


def _build_stage_summary(pair_df: pd.DataFrame) -> pd.DataFrame:
    stage_summary = (
        pair_df.groupby(["stage", "stage_cn", "model_short"], as_index=False)
        .agg(
            样本数=("score_diff", "size"),
            医生A均分=("score_a", "mean"),
            医生B均分=("score_b", "mean"),
            平均分差_A减B=("score_diff", "mean"),
            平均绝对分差=("score_abs_diff", "mean"),
            分差标准差=("score_diff", "std"),
        )
        .sort_values(["stage", "model_short"], kind="mergesort")
    )
    stage_summary["stage"] = pd.Categorical(stage_summary["stage"], categories=STAGE_ORDER, ordered=True)
    stage_summary = stage_summary.sort_values(["stage", "model_short"], kind="mergesort").reset_index(drop=True)
    return stage_summary


def _write_source_workbook(
    *,
    metric: str,
    detail_df: pd.DataFrame,
    pair_df: pd.DataFrame,
    stage_summary: pd.DataFrame,
    fig_index: pd.DataFrame,
    score_plot_detail_split: pd.DataFrame,
    score_plot_detail_merged: pd.DataFrame,
    diff_plot_detail: pd.DataFrame,
    diff_hist_stat: pd.DataFrame,
) -> tuple[Path, Path]:
    stem = f"A0_doctor_stage_scatter_source_{metric}_v1.xlsx"
    out_main = SOURCE_MAIN_DIR / stem
    out_supp = SOURCE_SUPP_DIR / stem
    out_main.parent.mkdir(parents=True, exist_ok=True)
    out_supp.parent.mkdir(parents=True, exist_ok=True)

    detail_zh = detail_df.rename(
        columns={
            "doctor": "医生",
            "center": "中心",
            "model": "模型",
            "model_short": "模型简称",
            "case_id": "病例ID",
            "stage": "阶段编码",
            "stage_cn": "阶段中文",
            "status": "流程状态",
            "score_0_5": "评分(0-5)",
            "source_file": "来源文件",
            "is_d1_anomaly": "是否D1异常样本",
            "is_gate3_fail": "是否Gate3失败样本",
        }
    )
    pair_zh = pair_df.rename(
        columns={
            "center": "中心",
            "model": "模型",
            "model_short": "模型简称",
            "case_id": "病例ID",
            "stage": "阶段编码",
            "stage_cn": "阶段中文",
            "doctor_a": "医生A",
            "doctor_b": "医生B",
            "score_a": "医生A评分(0-5)",
            "score_b": "医生B评分(0-5)",
            "score_mean": "两医生平均分",
            "score_diff": "分差(A-B)",
            "score_abs_diff": "绝对分差",
        }
    )
    score_plot_split_zh = score_plot_detail_split.rename(
        columns={
            "center": "中心",
            "model": "模型",
            "stage": "阶段编码",
            "stage_cn": "阶段中文",
            "stage_scope": "阶段大类编码",
            "stage_scope_cn": "阶段大类",
            "model_short": "模型简称",
            "case_id": "病例ID",
            "doctor_side": "医生侧",
            "score": "评分(1-5)",
            "plot_x": "绘图X(仅抖动)",
            "plot_y": "绘图Y",
        }
    )
    score_plot_merged_zh = score_plot_detail_merged.rename(
        columns={
            "center": "中心",
            "model": "模型",
            "stage": "阶段编码",
            "stage_cn": "阶段中文",
            "stage_scope": "阶段大类编码",
            "stage_scope_cn": "阶段大类",
            "model_short": "模型简称",
            "case_id": "病例ID",
            "doctor_side": "医生侧",
            "score": "评分(1-5)",
            "plot_x": "绘图X(仅抖动)",
            "plot_y": "绘图Y",
        }
    )
    diff_plot_detail_zh = diff_plot_detail.rename(
        columns={
            "center": "中心",
            "model": "模型",
            "stage": "阶段编码",
            "stage_cn": "阶段中文",
            "stage_scope": "阶段大类编码",
            "stage_scope_cn": "阶段大类",
            "model_short": "模型简称",
            "case_id": "病例ID",
            "score_mean": "两医生平均分",
            "score_diff": "分差(A-B)",
            "score_abs_diff": "绝对分差(|A-B|)",
            "plot_x": "绘图X(仅抖动)",
            "plot_y": "绘图Y",
        }
    )
    diff_hist_stat_zh = diff_hist_stat.rename(
        columns={
            "stage_scope": "阶段大类编码",
            "stage_scope_cn": "阶段大类",
            "stage": "阶段编码",
            "stage_cn": "阶段中文",
            "score_abs_diff_bin": "绝对分差分箱",
            "count": "频数",
        }
    )

    meta = pd.DataFrame(
        [
            {"键": "generated_at", "值": datetime.now().isoformat(timespec="seconds")},
            {"键": "metric", "值": metric},
            {"键": "metric_cn", "值": METRIC_TO_CN.get(metric, metric)},
            {"键": "input_file", "值": str(METRIC_TO_FILE[metric].as_posix())},
            {"键": "input_sheet", "值": "detail_used"},
            {"键": "pair_rule", "值": "同中心+同模型+同病例+同阶段，医生两两配对"},
            {"键": "diff_definition", "值": "分差 = 医生A评分 - 医生B评分"},
            {"键": "plot_1", "值": "医生评分分布点图(分医生): 仅Y轴(1-5), X仅用于防重叠抖动, 同框展示Doctor 1/Doctor 2"},
            {"键": "plot_2", "值": "医生评分分布点图(合并医生): 仅Y轴(1-5), X仅用于防重叠抖动"},
            {"键": "plot_3", "值": "医生绝对分差分布点图: 仅Y轴(0~4), X仅用于防重叠抖动"},
            {"键": "plot_4", "值": "医生绝对分差频率柱状图: 按绝对分差分箱(0~4)统计频数"},
        ]
    )

    with pd.ExcelWriter(out_main, engine="openpyxl") as writer:
        detail_zh.to_excel(writer, sheet_name="原始明细_医生评分", index=False)
        pair_zh.to_excel(writer, sheet_name="配对明细_医生分差", index=False)
        score_plot_split_zh.to_excel(writer, sheet_name="绘图明细_评分分布_分医生", index=False)
        score_plot_merged_zh.to_excel(writer, sheet_name="绘图明细_评分分布_合并医生", index=False)
        diff_plot_detail_zh.to_excel(writer, sheet_name="绘图明细_绝对分差分布", index=False)
        diff_hist_stat_zh.to_excel(writer, sheet_name="频率统计_绝对分差柱状图", index=False)
        stage_summary.to_excel(writer, sheet_name="分环节统计", index=False)
        fig_index.to_excel(writer, sheet_name="图文件清单", index=False)
        meta.to_excel(writer, sheet_name="元信息", index=False)

    out_supp.write_bytes(out_main.read_bytes())
    return out_main, out_supp


def _run_one_metric(metric: str) -> dict[str, object]:
    detail = _load_detail(metric)
    pair = _build_pair_detail(detail)
    metric_cn = METRIC_TO_CN.get(metric, metric)
    score_plot_detail, diff_plot_detail = _build_plot_detail(pair)

    fig_dir = FIG_BASE_DIR / metric
    archived_files = _archive_legacy_stage_scatter(fig_dir)
    fig_rows: list[dict[str, object]] = []
    score_plot_rows_split: list[pd.DataFrame] = []
    score_plot_rows_merged: list[pd.DataFrame] = []
    diff_plot_rows: list[pd.DataFrame] = []
    diff_hist_rows: list[pd.DataFrame] = []

    for scope in ["check", "decision"]:
        score_fig_split, score_detail_scope_split = _plot_score_distribution_by_scope(score_plot_detail, fig_dir, metric_cn, scope)
        if score_fig_split is not None:
            fig_rows.append(score_fig_split)
        if not score_detail_scope_split.empty:
            score_plot_rows_split.append(score_detail_scope_split)

        score_fig_merged, score_detail_scope_merged = _plot_score_distribution_merged_by_scope(
            score_plot_detail, fig_dir, metric_cn, scope
        )
        if score_fig_merged is not None:
            fig_rows.append(score_fig_merged)
        if not score_detail_scope_merged.empty:
            score_plot_rows_merged.append(score_detail_scope_merged)

        diff_fig, diff_detail_scope = _plot_diff_distribution_by_scope(diff_plot_detail, fig_dir, metric_cn, scope)
        if diff_fig is not None:
            fig_rows.append(diff_fig)
        if not diff_detail_scope.empty:
            diff_plot_rows.append(diff_detail_scope)

        hist_fig, hist_stat_scope = _plot_diff_hist_by_scope(diff_plot_detail, fig_dir, metric_cn, scope)
        if hist_fig is not None:
            fig_rows.append(hist_fig)
        if not hist_stat_scope.empty:
            diff_hist_rows.append(hist_stat_scope)

    fig_index = pd.DataFrame(fig_rows)
    score_plot_used_split = pd.concat(score_plot_rows_split, ignore_index=True) if score_plot_rows_split else pd.DataFrame()
    score_plot_used_merged = (
        pd.concat(score_plot_rows_merged, ignore_index=True) if score_plot_rows_merged else pd.DataFrame()
    )
    diff_plot_used = pd.concat(diff_plot_rows, ignore_index=True) if diff_plot_rows else pd.DataFrame()
    diff_hist_stat = pd.concat(diff_hist_rows, ignore_index=True) if diff_hist_rows else pd.DataFrame()

    stage_summary = _build_stage_summary(pair)
    out_main, out_supp = _write_source_workbook(
        metric=metric,
        detail_df=detail,
        pair_df=pair,
        stage_summary=stage_summary,
        fig_index=fig_index,
        score_plot_detail_split=score_plot_used_split,
        score_plot_detail_merged=score_plot_used_merged,
        diff_plot_detail=diff_plot_used,
        diff_hist_stat=diff_hist_stat,
    )
    return {
        "metric": metric,
        "figure_dir": fig_dir,
        "source_main": out_main,
        "source_supp": out_supp,
        "n_detail": int(len(detail)),
        "n_pairs": int(len(pair)),
        "n_figures": int(len(fig_index)),
        "n_archived_legacy": int(len(archived_files)),
        "archive_dir": fig_dir / "archieve",
    }


def main() -> None:
    _setup_matplotlib_fonts()
    parser = argparse.ArgumentParser(description="Build stage-wise doctor score scatter and doctor-pair difference scatter.")
    parser.add_argument(
        "--metric",
        choices=["result", "reasoning", "both"],
        default="result",
        help="result=结果评分, reasoning=推理评分, both=两者都输出",
    )
    args = parser.parse_args()

    metrics = ["result", "reasoning"] if args.metric == "both" else [args.metric]
    for metric in metrics:
        out = _run_one_metric(metric)
        print(f"[{metric}] FIG_DIR={out['figure_dir']}")
        print(f"[{metric}] SOURCE_MAIN={out['source_main']}")
        print(f"[{metric}] SOURCE_SUPP={out['source_supp']}")
        print(f"[{metric}] ARCHIVE_DIR={out['archive_dir']} ARCHIVED_LEGACY={out['n_archived_legacy']}")
        print(
            f"[{metric}] DETAIL_ROWS={out['n_detail']} PAIR_ROWS={out['n_pairs']} FIG_COUNT={out['n_figures']}"
        )


if __name__ == "__main__":
    main()
