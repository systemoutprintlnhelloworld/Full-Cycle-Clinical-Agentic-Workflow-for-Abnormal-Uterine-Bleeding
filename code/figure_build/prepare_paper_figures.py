from __future__ import annotations

import math
import shutil
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
FIGDATA = ROOT / "论文" / "figdata"
PAPER_FIG = ROOT / "论文" / "figures"
PAPER_FIG.mkdir(parents=True, exist_ok=True)

warnings.filterwarnings("ignore", message="Glyph .* missing from font")
warnings.filterwarnings("ignore", message="This figure includes Axes that are not compatible with tight_layout")

PALETTE = ["#4C72B0", "#55A868", "#C44E52", "#8172B2", "#DD8452", "#64B5CD"]

FIGDATA_PREFIX_BY_NAME = {
    "dataset_center_counts.csv": "Fig1a",
    "dataset_diagnosis_category_by_stage.csv": "Fig1b",
    "dataset_diagnosis_category_counts.csv": "Fig1b",
    "dataset_case_text_length.csv": "Fig1c",
    "dataset_text_length_histogram.csv": "Fig1c",
    "dataset_text_length_summary.csv": "Fig1c",
    "dataset_stage_coverage.csv": "Fig1d",
    "dataset_stage_info_density.csv": "Fig1d",
    "dataset_check_type_counts.csv": "Fig1f",
    "dataset_check_count_summary.csv": "Fig1f",
    "dataset_plan_type_counts.csv": "Fig1g",
    "dataset_plan_count_summary.csv": "Fig1g",
    "dataset_benign_malignant_counts.csv": "Fig1h",
    "dataset_rare_common_counts.csv": "Fig1h",
    "dataset_diagnosis_longtail.csv": "Fig1h",
    "dataset_icd10_chapter_coverage.csv": "Fig1k",
    "dataset_icd10_chapter_counts.csv": "Fig1k",
    "dataset_icd10_mapping.csv": "Fig1k",
    "dataset_final_diagnosis_terms.csv": "Fig1l",
    "dataset_wuhan_differential_diagnosis_counts.csv": "Fig1l",
    "consistency_stage_avg.csv": "Fig9",
    "memory_stage_avg.csv": "Fig9",
    "d2_decision_review_breakdown.csv": "Fig8a",
    "d3_decision_review_breakdown.csv": "Fig8b",
    "algorithmic_metrics_overall.csv": "Fig12",
}


def _figdata_path(name: str) -> Path:
    prefix = FIGDATA_PREFIX_BY_NAME.get(name)
    preferred = FIGDATA / (f"{prefix}__{name}" if prefix else name)
    if preferred.exists():
        return preferred
    old = FIGDATA / name
    if old.exists():
        return old
    matches = sorted(FIGDATA.glob(f"*__{name}"))
    if matches:
        return matches[0]
    return preferred


def configure_fonts() -> None:
    # Load Chinese fonts explicitly from Windows font files to avoid乱码.
    candidates = [
        ("C:/Windows/Fonts/msyh.ttc", "Microsoft YaHei"),
        ("C:/Windows/Fonts/msyhbd.ttc", "Microsoft YaHei"),
        ("C:/Windows/Fonts/simhei.ttf", "SimHei"),
        ("C:/Windows/Fonts/simsun.ttc", "SimSun"),
    ]
    available: list[str] = []
    for font_path, font_name in candidates:
        if Path(font_path).exists():
            try:
                font_manager.fontManager.addfont(font_path)
            except Exception:
                pass
            if font_name not in available:
                available.append(font_name)
    if not available:
        available = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = available + ["DejaVu Sans", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False


def apply_style() -> None:
    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except Exception:
        try:
            plt.style.use("seaborn-whitegrid")
        except Exception:
            pass
    plt.rcParams.update(
        {
            "axes.spines.top": False,
            "axes.spines.right": False,
            "grid.alpha": 0.3,
            "grid.linestyle": "--",
            "axes.prop_cycle": plt.cycler(color=PALETTE),
        }
    )
    configure_fonts()


apply_style()


def _save_fig(path: Path) -> None:
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()


def cleanup_deprecated_figures() -> None:
    # 保留所有历史图像，避免误删用户已有成果。
    return


def plot_center_counts() -> None:
    path = _figdata_path("dataset_center_counts.csv")
    if not path.exists():
        return
    df = pd.read_csv(path)
    if df.empty:
        return

    name_map = {"Foshan": "佛山", "Wuhan": "武汉", "Xinjiang": "新疆"}
    labels = [name_map.get(str(x), str(x)) for x in df["Center"].tolist()]
    values = [int(v) for v in df["Cases"].tolist()]
    total = sum(values)

    colors = ["#4C72B0", "#55A868", "#C44E52", "#8172B2"]
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.6), gridspec_kw={"width_ratios": [1.15, 1.0]})

    wedges, _, autotexts = axes[0].pie(
        values,
        labels=labels,
        autopct=lambda p: f"{p:.1f}%",
        startangle=90,
        pctdistance=0.78,
        colors=colors[: len(values)],
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1.1},
        textprops={"fontsize": 10},
    )
    for t in autotexts:
        t.set_fontsize(9)
        t.set_color("#1F1F1F")
    axes[0].text(0, 0, f"N={total}", ha="center", va="center", fontsize=12, fontweight="bold")
    axes[0].set_title("Case share by center")

    y = np.arange(len(labels))
    bars = axes[1].barh(y, values, color=colors[: len(values)], edgecolor="white", linewidth=0.9)
    axes[1].set_yticks(y)
    axes[1].set_yticklabels(labels)
    axes[1].invert_yaxis()
    axes[1].set_xlabel("Cases")
    axes[1].set_title("Absolute case counts")
    axes[1].grid(axis="x", alpha=0.25)
    for bar, val in zip(bars, values):
        axes[1].text(
            bar.get_width() + max(total * 0.008, 0.5),
            bar.get_y() + bar.get_height() / 2,
            f"{val}",
            va="center",
            fontsize=9,
        )

    _save_fig(PAPER_FIG / "Fig1a_dataset_center_counts.png")

def plot_diagnosis_category_counts() -> None:
    by_stage_path = _figdata_path("dataset_diagnosis_category_by_stage.csv")
    if by_stage_path.exists():
        df = pd.read_csv(by_stage_path)
        stage_order = ["Admission", "Revised", "Final"]
        stage_title = {
            "Admission": "D1 admission diagnosis",
            "Revised": "D2 revised diagnosis",
            "Final": "D3 final diagnosis",
        }
        stage_colors = {
            "Admission": "#4C72B0",
            "Revised": "#55A868",
            "Final": "#C44E52",
        }

        fig, axes = plt.subplots(1, 3, figsize=(14.6, 5.2), sharex=False)
        for ax, stage in zip(axes, stage_order):
            sub = df[df["Stage"] == stage].copy()
            if sub.empty:
                ax.text(0.5, 0.5, "Missing data", ha="center", va="center")
                ax.axis("off")
                continue
            sub = sub.sort_values("Cases", ascending=True)
            ax.barh(
                sub["DiagnosisCategory"],
                sub["Cases"],
                color=stage_colors.get(stage, PALETTE[1]),
                edgecolor="white",
                linewidth=0.8,
            )
            ax.set_title(stage_title.get(stage, stage), fontsize=11)
            ax.set_xlabel("Cases")
            ax.grid(axis="x", alpha=0.25)
            ax.tick_params(axis="y", labelsize=8)

        fig.suptitle("Diagnosis Category Distribution by Stage", y=1.03, fontsize=13)
        _save_fig(PAPER_FIG / "Fig1b_diagnosis_category_counts.png")
        return

    path = _figdata_path("dataset_diagnosis_category_counts.csv")
    if not path.exists():
        return
    df = pd.read_csv(path).sort_values("Cases", ascending=True)
    plt.figure(figsize=(6.8, 4.8))
    plt.barh(df["DiagnosisCategory"], df["Cases"], color=PALETTE[1])
    plt.xlabel("Cases")
    plt.title("Diagnosis Category Distribution")
    _save_fig(PAPER_FIG / "Fig1b_diagnosis_category_counts.png")


def plot_text_length_histogram() -> None:
    df = pd.read_csv(_figdata_path("dataset_text_length_histogram.csv"))
    starts = df["BinStart"].tolist()
    ends = df["BinEnd"].tolist()
    counts = df["Count"].tolist()
    widths = [e - s for s, e in zip(starts, ends)]
    plt.figure(figsize=(6.6, 4.2))
    plt.bar(starts, counts, width=widths, align="edge", color=PALETTE[2], edgecolor="white")
    plt.xlabel("Text length (non-space characters)")
    plt.ylabel("Cases")
    plt.title("Text Length Histogram")
    length_path = _figdata_path("dataset_case_text_length.csv")
    if length_path.exists():
        length_df = pd.read_csv(length_path)
        lengths = pd.to_numeric(length_df.get("TextLen"), errors="coerce").dropna()
        if not lengths.empty:
            p50 = float(np.percentile(lengths, 50))
            p90 = float(np.percentile(lengths, 90))
            p95 = float(np.percentile(lengths, 95))
            xmax = max(p95 * 1.05, 1)
            if p50 > 0 and p95 > p50 * 2.4:
                xmax = max(p90 * 1.1, 1)
            plt.xlim(0, xmax)
            plt.axvline(p95, color="#444444", linestyle="--", linewidth=1)
            plt.text(p95, max(counts) * 0.92, "P95", ha="left", va="center", fontsize=8, color="#444444")
    _save_fig(PAPER_FIG / "Fig1c_text_length_histogram.png")


def plot_stage_coverage() -> None:
    density_path = _figdata_path("dataset_stage_info_density.csv")
    coverage_path = _figdata_path("dataset_stage_coverage.csv")
    if not density_path.exists() and not coverage_path.exists():
        return

    density_df = pd.read_csv(density_path) if density_path.exists() else pd.DataFrame()
    coverage_df = pd.read_csv(coverage_path) if coverage_path.exists() else pd.DataFrame()

    if density_df.empty:
        return

    def _fmt_field(name: str) -> str:
        s = str(name)
        s = s.replace("GT_", "")
        s = s.replace("_", " ")
        s = s.replace("BasicInfo", "Basic info")
        s = s.replace("ChiefComplaint", "Chief complaint")
        s = s.replace("PresentIllness", "Present illness")
        s = s.replace("PastHistory", "Past history")
        s = s.replace("MenstrualHistory", "Menstrual history")
        s = s.replace("FamilyHistory", "Family history")
        s = s.replace("PhysicalExam", "Physical exam")
        return s

    density_df = density_df.copy()
    density_df["MedianChars"] = pd.to_numeric(density_df["MedianChars"], errors="coerce")
    density_df["P25Chars"] = pd.to_numeric(density_df["P25Chars"], errors="coerce")
    density_df["P75Chars"] = pd.to_numeric(density_df["P75Chars"], errors="coerce")
    density_df = density_df.dropna(subset=["MedianChars"]) 

    if not coverage_df.empty and "Field" in coverage_df.columns:
        coverage_df = coverage_df[["Field", "Percent"]].copy()
        coverage_df["Percent"] = pd.to_numeric(coverage_df["Percent"], errors="coerce")
        density_df = density_df.merge(coverage_df, on="Field", how="left")
    else:
        density_df["Percent"] = np.nan

    density_df = density_df.sort_values("MedianChars", ascending=True)

    labels = [_fmt_field(x) for x in density_df["Field"]]
    med = density_df["MedianChars"].fillna(0)
    p25 = density_df["P25Chars"].fillna(0)
    p75 = density_df["P75Chars"].fillna(0)
    xerr = np.vstack([np.maximum(med - p25, 0), np.maximum(p75 - med, 0)])

    n_fields = max(1, len(labels))
    fig_h = min(16.0, max(6.8, 0.32 * n_fields))

    fig, ax = plt.subplots(figsize=(10.6, fig_h))
    bars = ax.barh(labels, med, color="#6F63C2", xerr=xerr, ecolor="#4A4A4A", capsize=2)
    ax.set_xlabel("Median non-space characters (IQR)")
    ax.set_title("Information density across all non-ID GT fields")
    ax.grid(axis="x", alpha=0.25)
    ax.tick_params(axis="y", labelsize=8)

    if "Percent" in density_df.columns:
        for bar, pct in zip(bars, density_df["Percent"].fillna(np.nan)):
            if pd.notna(pct):
                ax.text(
                    bar.get_width() + max(float(med.max()) * 0.01, 1.2),
                    bar.get_y() + bar.get_height() / 2,
                    f"{pct * 100:.0f}% present",
                    va="center",
                    fontsize=7,
                    color="#555555",
                )

    _save_fig(PAPER_FIG / "Fig1d_stage_coverage.png")

def plot_diagnosis_category_by_stage() -> None:
    path = _figdata_path("dataset_diagnosis_category_by_stage.csv")
    if not path.exists():
        return
    df = pd.read_csv(path)
    pivot = df.pivot_table(index="Stage", columns="DiagnosisCategory", values="Cases", aggfunc="sum").fillna(0)
    stage_order = [c for c in ["Admission", "Revised", "Final"] if c in pivot.index]
    pivot = pivot.loc[stage_order]
    stage_name = {"Admission": "D1 admission", "Revised": "D2 revised", "Final": "D3 final"}
    pivot.index = [stage_name.get(x, x) for x in pivot.index]
    pivot.plot(kind="bar", stacked=True, figsize=(8.0, 4.8), colormap="tab20")
    plt.ylabel("Cases")
    plt.title("Diagnosis Category Shift Across Stages")
    plt.legend(loc="upper right", fontsize=7, ncol=2, frameon=False)
    _save_fig(PAPER_FIG / "Fig1e_diagnosis_category_by_stage.png")


def plot_check_type_distribution() -> None:
    path = _figdata_path("dataset_check_type_counts.csv")
    if not path.exists():
        return
    df = pd.read_csv(path)
    if df.empty:
        return

    stage_order = ["Outpatient", "Admission"]
    stage_label = {"Outpatient": "门诊", "Admission": "住院"}
    pivot = df.pivot_table(index="Stage", columns="Category", values="Cases", aggfunc="sum").fillna(0)
    pivot = pivot.loc[[s for s in stage_order if s in pivot.index]]
    if pivot.empty:
        return

    preferred_order = ["实验室检验", "影像", "病理", "内镜", "其他"]
    categories = [c for c in preferred_order if c in pivot.columns] + [
        c for c in pivot.columns if c not in preferred_order
    ]
    base_colors = {
        "实验室检验": "#4C72B0",
        "影像": "#55A868",
        "病理": "#C44E52",
        "内镜": "#8172B2",
        "其他": "#BDBDBD",
    }
    color_map = {cat: base_colors.get(cat, PALETTE[idx % len(PALETTE)]) for idx, cat in enumerate(categories)}

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.8), gridspec_kw={"width_ratios": [1.35, 1.0], "wspace": 0.2})

    left = np.zeros(pivot.shape[0])
    y = np.arange(pivot.shape[0])
    for cat in categories:
        vals = pivot[cat].to_numpy()
        axes[0].barh(y, vals, left=left, color=color_map[cat], edgecolor="white", linewidth=0.8, label=cat)
        left += vals
    axes[0].set_yticks(y)
    axes[0].set_yticklabels([stage_label.get(s, s) for s in pivot.index])
    axes[0].set_xlabel("检查条目数")
    axes[0].set_title("检查类型绝对规模")
    axes[0].grid(axis="x", alpha=0.25)

    non_other_cols = [c for c in categories if str(c) != "其他"]
    if non_other_cols:
        comp = pivot[non_other_cols].copy()
        denom = comp.sum(axis=1).replace(0, np.nan)
        share = comp.div(denom, axis=0).fillna(0)
        left2 = np.zeros(share.shape[0])
        for cat in non_other_cols:
            vals = share[cat].to_numpy() * 100
            axes[1].barh(y, vals, left=left2, color=color_map[cat], edgecolor="white", linewidth=0.8)
            for i, v in enumerate(vals):
                if v >= 6:
                    axes[1].text(left2[i] + v / 2, i, f"{v:.0f}%", ha="center", va="center", fontsize=7, color="#1F1F1F")
            left2 += vals
        axes[1].set_yticks(y)
        axes[1].set_yticklabels([stage_label.get(s, s) for s in pivot.index])
        axes[1].set_xlim(0, 100)
        axes[1].set_xlabel("非“其他”检查构成 (%)")
        axes[1].set_title("关键信息型检查构成")
        axes[1].grid(axis="x", alpha=0.25)
    else:
        axes[1].text(0.5, 0.5, "缺少非“其他”检查数据", ha="center", va="center")
        axes[1].axis("off")

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=min(4, len(labels)), frameon=False, fontsize=8)
    fig.subplots_adjust(bottom=0.2)
    _save_fig(PAPER_FIG / "Fig1f_check_type_distribution.png")

def plot_plan_type_distribution() -> None:
    path = _figdata_path("dataset_plan_type_counts.csv")
    if not path.exists():
        return
    df = pd.read_csv(path)
    if df.empty:
        return

    stage_order = ["Surgery_Plan", "PostOp_Plan", "Followup_Plan", "Rehab_Plan"]
    stage_label = {
        "Surgery_Plan": "术前/术中方案",
        "PostOp_Plan": "术后方案",
        "Followup_Plan": "随访方案",
        "Rehab_Plan": "康复方案",
    }

    pivot = df.pivot_table(index="Stage", columns="Category", values="Cases", aggfunc="sum").fillna(0)
    pivot = pivot.loc[[s for s in stage_order if s in pivot.index]]
    if pivot.empty:
        return

    category_order = ["手术", "化疗", "放疗", "内分泌/激素", "保守/药物", "康复/护理", "随访/复查", "其他"]
    counts = pivot.T.reindex([c for c in category_order if c in pivot.columns])
    fig, axes = plt.subplots(1, 2, figsize=(12.0, 5.4), gridspec_kw={"width_ratios": [1.55, 0.85], "wspace": 0.35})

    heat = axes[0].imshow(counts.to_numpy(), cmap="YlOrRd", aspect="auto")
    axes[0].set_xticks(np.arange(counts.shape[1]))
    axes[0].set_xticklabels([stage_label.get(s, s) for s in counts.columns], rotation=12, ha="right")
    axes[0].set_yticks(np.arange(counts.shape[0]))
    axes[0].set_yticklabels(counts.index)
    axes[0].set_title("治疗/随访方案类型热度图（计数）")

    for i in range(counts.shape[0]):
        for j in range(counts.shape[1]):
            val = int(counts.iloc[i, j])
            if val > 0:
                axes[0].text(j, i, str(val), ha="center", va="center", fontsize=8, color="#1F1F1F")

    cb = fig.colorbar(heat, ax=axes[0], fraction=0.046, pad=0.03)
    cb.set_label("Cases", fontsize=9)

    totals = counts.sum(axis=1).sort_values(ascending=True)
    bars = axes[1].barh(totals.index, totals.values, color="#4C72B0", edgecolor="white", linewidth=0.8)
    axes[1].set_xlabel("总条目数")
    axes[1].set_title("各方案类型总体规模")
    axes[1].grid(axis="x", alpha=0.25)
    for bar, val in zip(bars, totals.values):
        axes[1].text(
            bar.get_width() + max(float(totals.max()) * 0.01, 0.6),
            bar.get_y() + bar.get_height() / 2,
            str(int(val)),
            va="center",
            fontsize=8,
        )

    _save_fig(PAPER_FIG / "Fig1g_plan_type_distribution.png")


def _plot_manual_stage_summary(path: Path, title: str, out_name: str, color: str) -> None:
    if not path.exists():
        return
    df = pd.read_csv(path)
    if df.empty or "Stage" not in df.columns:
        return
    df["Mean"] = pd.to_numeric(df["Mean"], errors="coerce")
    df["Min"] = pd.to_numeric(df["Min"], errors="coerce")
    df["Max"] = pd.to_numeric(df["Max"], errors="coerce")
    df = df.dropna(subset=["Mean"])
    if df.empty:
        return

    stage_order = ["门诊A", "门诊B", "住院A", "住院B", "术后", "康复"]
    df["Stage"] = pd.Categorical(df["Stage"], categories=stage_order, ordered=True)
    df = df.sort_values("Stage")
    x = np.arange(df.shape[0])
    y = df["Mean"].to_numpy()
    yerr = np.vstack(
        [
            np.maximum(y - df["Min"].to_numpy(), 0),
            np.maximum(df["Max"].to_numpy() - y, 0),
        ]
    )

    plt.figure(figsize=(7.2, 4.6))
    plt.bar(x, y, color=color, edgecolor="white", linewidth=0.8)
    plt.errorbar(x, y, yerr=yerr, fmt="none", ecolor="#4A4A4A", elinewidth=1.0, capsize=3)
    plt.xticks(x, df["Stage"].tolist())
    plt.ylim(0, 5.1)
    plt.ylabel("Score (0-5)")
    plt.title(title)
    plt.grid(axis="y", alpha=0.25)
    _save_fig(PAPER_FIG / out_name)


def plot_manual_quality_summaries() -> None:
    _plot_manual_stage_summary(
        _figdata_path("manual_result_quality_stage_summary.csv"),
        "Manual result quality by stage",
        "Fig2d_manual_result_quality_by_stage.png",
        "#4C72B0",
    )
    _plot_manual_stage_summary(
        _figdata_path("manual_reasoning_quality_stage_summary.csv"),
        "Manual reasoning quality by stage",
        "Fig4d_manual_reasoning_quality_by_stage.png",
        "#55A868",
    )

def plot_case_difficulty_profile() -> None:
    benign_path = _figdata_path("dataset_benign_malignant_counts.csv")
    longtail_path = _figdata_path("dataset_diagnosis_longtail.csv")
    if not benign_path.exists() or not longtail_path.exists():
        return
    benign = pd.read_csv(benign_path)
    longtail = pd.read_csv(longtail_path)
    if benign.empty or longtail.empty:
        return

    class_label = {
        "良性/非肿瘤": "Benign / non-neoplastic",
        "恶性/肿瘤": "Malignant / neoplastic",
        "缺失": "Missing",
    }

    longtail_plot = longtail.sort_values("Cases", ascending=False).copy()
    x = np.arange(longtail_plot.shape[0])
    cum_pct = longtail_plot["Cases"].cumsum() / longtail_plot["Cases"].sum() * 100
    bucket_order = ["Common(>=5)", "Uncommon(2-4)", "Rare(1)"]
    bucket_counts = longtail_plot["ClassBucket"].value_counts().reindex(bucket_order).fillna(0).astype(int)

    themes = [
        {
            "name": "main",
            "out": PAPER_FIG / "Fig1h_case_difficulty_profile.png",
            "mode": "bar_pareto",
            "left_colors": {"良性/非肿瘤": "#4C72B0", "恶性/肿瘤": "#C44E52", "缺失": "#9E9E9E"},
            "tail_colors": {"Common(>=5)": "#4C72B0", "Uncommon(2-4)": "#DD8452", "Rare(1)": "#55A868"},
        },
        {
            "name": "styleA",
            "out": PAPER_FIG / "Fig1h_case_difficulty_profile_styleA.png",
            "mode": "donut_lorenz",
            "left_colors": {"良性/非肿瘤": "#3F5D7D", "恶性/肿瘤": "#B24C63", "缺失": "#9E9E9E"},
            "tail_colors": {"Common(>=5)": "#3F5D7D", "Uncommon(2-4)": "#C38D5A", "Rare(1)": "#5D9C86"},
        },
        {
            "name": "styleB",
            "out": PAPER_FIG / "Fig1h_case_difficulty_profile_styleB.png",
            "mode": "rank_scatter",
            "left_colors": {"良性/非肿瘤": "#2B6CB0", "恶性/肿瘤": "#D1495B", "缺失": "#9E9E9E"},
            "tail_colors": {"Common(>=5)": "#2B6CB0", "Uncommon(2-4)": "#D17A22", "Rare(1)": "#2F855A"},
        },
    ]

    for theme in themes:
        fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.8), gridspec_kw={"width_ratios": [1.1, 2.0]})

        benign_plot = benign.sort_values("Cases", ascending=True).copy()
        labels = [class_label.get(str(x), str(x)) for x in benign_plot["Class"]]
        values = benign_plot["Cases"].to_numpy()
        total = float(values.sum()) if values.size else 0.0

        if theme["mode"] == "donut_lorenz":
            colors = [theme["left_colors"].get(str(x), "#999999") for x in benign_plot["Class"]]
            _, _, autotexts = axes[0].pie(
                values,
                labels=labels,
                colors=colors,
                startangle=90,
                autopct=lambda p: f"{p:.1f}%" if p > 0 else "",
                pctdistance=0.8,
                wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1.0},
                textprops={"fontsize": 8},
            )
            for t in autotexts:
                t.set_fontsize(8)
            axes[0].text(0, 0, f"N={int(total)}", ha="center", va="center", fontsize=11, fontweight="bold")
            axes[0].set_title("Benign/Malignant mix")
        else:
            colors = [theme["left_colors"].get(str(x), "#999999") for x in benign_plot["Class"]]
            bars = axes[0].barh(labels, values, color=colors, edgecolor="white", linewidth=0.9)
            for bar, val in zip(bars, values):
                pct_v = (float(val) / total * 100) if total else 0
                axes[0].text(
                    val + max(total * 0.01, 0.3),
                    bar.get_y() + bar.get_height() / 2,
                    f"{int(val)} ({pct_v:.1f}%)",
                    va="center",
                    fontsize=8,
                )
            axes[0].set_title("Case difficulty: benign vs malignant")
            axes[0].set_xlabel("Cases")
            axes[0].grid(axis="x", alpha=0.25)

        tail_colors = longtail_plot["ClassBucket"].map(theme["tail_colors"]).fillna("#999999")
        if theme["mode"] == "bar_pareto":
            axes[1].bar(x, longtail_plot["Cases"], color=tail_colors, width=0.88, edgecolor="white", linewidth=0.6)
            axes[1].set_ylabel("Cases")
            axes[1].set_title("Diagnosis long-tail profile")
            axes[1].set_xlabel("Diagnosis rank (descending frequency)")
            axes[1].grid(axis="y", alpha=0.25)
            ax2 = axes[1].twinx()
            ax2.plot(x, cum_pct, color="#2F2F2F", linewidth=1.6, alpha=0.85)
            ax2.set_ylim(0, 102)
            ax2.set_ylabel("Cumulative coverage (%)", fontsize=8)
            ax2.tick_params(axis="y", labelsize=8)
            ax2.axhline(80, color="#666666", linestyle="--", linewidth=0.9, alpha=0.7)
        elif theme["mode"] == "donut_lorenz":
            axes[1].bar(
                x,
                longtail_plot["Cases"],
                color=tail_colors,
                width=0.82,
                edgecolor="white",
                linewidth=0.5,
                alpha=0.95,
            )
            axes[1].set_ylabel("Cases")
            axes[1].set_xlabel("Diagnosis rank")
            axes[1].set_title("Long-tail by rarity class + cumulative curve")
            axes[1].grid(axis="y", alpha=0.2)

            ax2 = axes[1].twinx()
            ax2.plot(x, cum_pct, color="#2F855A", linewidth=1.7)
            ax2.set_ylim(0, 102)
            ax2.set_ylabel("Cumulative coverage (%)", fontsize=8)
            ax2.tick_params(axis="y", labelsize=8)
            ax2.axhline(80, color="#666666", linestyle="--", linewidth=0.9, alpha=0.7)
        else:
            axes[1].scatter(
                np.arange(1, len(longtail_plot) + 1),
                longtail_plot["Cases"],
                s=26,
                c=tail_colors,
                alpha=0.75,
                edgecolors="white",
                linewidths=0.4,
            )
            axes[1].plot(np.arange(1, len(longtail_plot) + 1), longtail_plot["Cases"], color="#444444", linewidth=0.8, alpha=0.5)
            axes[1].set_yscale("log")
            axes[1].set_xlabel("Diagnosis rank")
            axes[1].set_ylabel("Cases (log scale)")
            axes[1].set_title("Long-tail rank-frequency (log)")
            axes[1].grid(axis="both", alpha=0.2)

        if longtail_plot.shape[0] > 0:
            tick_num = 5 if longtail_plot.shape[0] >= 5 else longtail_plot.shape[0]
            tick_positions = np.linspace(0, longtail_plot.shape[0] - 1, num=tick_num, dtype=int)
            tick_positions = np.unique(tick_positions)
            axes[1].set_xticks(tick_positions if theme["mode"] == "bar_pareto" else tick_positions + 1)
            axes[1].set_xticklabels([str(i + 1) for i in tick_positions], fontsize=8)

        # Highlight rarity segments to avoid "all green" perception.
        if bucket_counts.sum() > 0 and theme["mode"] in {"bar_pareto", "donut_lorenz"}:
            start = 0
            for bucket in bucket_order:
                count = int(bucket_counts.get(bucket, 0))
                if count <= 0:
                    continue
                end = start + count
                axes[1].axvspan(
                    start - 0.5,
                    end - 0.5,
                    color=theme["tail_colors"].get(bucket, "#CCCCCC"),
                    alpha=0.08,
                    linewidth=0,
                )
                start = end


        legend_handles = [
            plt.Rectangle((0, 0), 1, 1, color=theme["tail_colors"]["Common(>=5)"]),
            plt.Rectangle((0, 0), 1, 1, color=theme["tail_colors"]["Uncommon(2-4)"]),
            plt.Rectangle((0, 0), 1, 1, color=theme["tail_colors"]["Rare(1)"]),
        ]
        axes[1].legend(
            legend_handles,
            ["Common (n>=5)", "Uncommon (n=2-4)", "Rare (n=1)"],
            loc="upper right",
            fontsize=7,
            frameon=False,
        )

        _save_fig(theme["out"])

def _simple_wordcloud(
    ax: plt.Axes,
    df: pd.DataFrame,
    word_col: str,
    value_col: str,
    title: str,
    max_words: int = 60,
) -> None:
    if df.empty or word_col not in df.columns or value_col not in df.columns:
        ax.text(0.5, 0.5, "Missing data", ha="center", va="center")
        ax.axis("off")
        return
    data = df[[word_col, value_col]].dropna()
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna(subset=[value_col])
    if data.empty:
        ax.text(0.5, 0.5, "Missing data", ha="center", va="center")
        ax.axis("off")
        return
    data = data.sort_values(value_col, ascending=False).head(max_words).reset_index(drop=True)
    weights = data[value_col].to_numpy()
    min_w, max_w = float(weights.min()), float(weights.max())
    if min_w == max_w:
        sizes = np.full_like(weights, 14, dtype=float)
    else:
        sizes = 10 + (weights - min_w) / (max_w - min_w) * 18
    cols = 8
    rows = int(math.ceil(len(data) / cols))
    rng = np.random.default_rng(42)
    for idx, (word, size) in enumerate(zip(data[word_col], sizes)):
        col = idx % cols
        row = idx // cols
        x = col + 0.5 + rng.uniform(-0.15, 0.15)
        y = rows - row - 0.5 + rng.uniform(-0.2, 0.2)
        ax.text(
            x,
            y,
            str(word),
            fontsize=float(size),
            ha="center",
            va="center",
            color=PALETTE[idx % len(PALETTE)],
        )
    ax.set_xlim(0, cols)
    ax.set_ylim(0, rows)
    ax.axis("off")
    ax.set_title(title)


def plot_diagnosis_term_clouds() -> None:
    final_path = _figdata_path("dataset_final_diagnosis_terms.csv")
    diff_path = _figdata_path("dataset_wuhan_differential_diagnosis_counts.csv")
    if not final_path.exists() and not diff_path.exists():
        return

    def _prepare(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
        if df.empty:
            return df
        frame = df.copy()
        frame = frame.rename(columns={"Diagnosis": "Term"})
        frame["Cases"] = pd.to_numeric(frame["Cases"], errors="coerce")
        frame = frame.dropna(subset=["Term", "Cases"])
        frame = frame.sort_values("Cases", ascending=False).head(top_n).reset_index(drop=True)
        frame["Term"] = frame["Term"].astype(str).map(lambda x: x if len(x) <= 22 else x[:22] + "...")
        frame["CumPct"] = frame["Cases"].cumsum() / frame["Cases"].sum() * 100
        return frame

    def _plot(ax: plt.Axes, data: pd.DataFrame, title: str, bar_color: str) -> None:
        if data.empty:
            ax.text(0.5, 0.5, "Missing data", ha="center", va="center")
            ax.axis("off")
            return
        y = np.arange(data.shape[0])
        ax.barh(y, data["Cases"], color=bar_color, edgecolor="white", linewidth=0.8)
        ax.set_yticks(y)
        ax.set_yticklabels(data["Term"], fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel("Cases")
        ax.set_title(title)
        ax.grid(axis="x", alpha=0.25)

        ax2 = ax.twiny()
        ax2.plot(data["CumPct"], y, color="#C44E52", marker="o", linewidth=1.4, markersize=3)
        ax2.set_xlim(0, 100)
        ax2.set_xlabel("Cumulative coverage (%)", fontsize=8)
        ax2.tick_params(axis="x", labelsize=8)
        ax2.grid(False)

    fig_rt, axes_rt = plt.subplots(1, 2, figsize=(13.6, 6.0), gridspec_kw={"wspace": 0.36})
    if final_path.exists():
        final_df = pd.read_csv(final_path)
        _plot(axes_rt[0], _prepare(final_df, top_n=20), "Final diagnosis richness (Top 20 + Pareto)", "#4C72B0")
    else:
        axes_rt[0].text(0.5, 0.5, "Missing final diagnosis terms", ha="center", va="center")
        axes_rt[0].axis("off")

    if diff_path.exists():
        diff_df = pd.read_csv(diff_path)
        _plot(axes_rt[1], _prepare(diff_df, top_n=20), "Wuhan differential richness (Top 20 + Pareto)", "#55A868")
    else:
        axes_rt[1].text(0.5, 0.5, "Missing differential terms", ha="center", va="center")
        axes_rt[1].axis("off")

    _save_fig(PAPER_FIG / "Fig1l_diagnosis_term_richness.png")

def plot_consistency_and_memory() -> None:
    cons_path = _figdata_path("consistency_stage_avg.csv")
    mem_path = _figdata_path("memory_stage_avg.csv")
    if not cons_path.exists() and not mem_path.exists():
        return

    fig, axes = plt.subplots(1, 2, figsize=(9.8, 4.0), gridspec_kw={"wspace": 0.28})

    if cons_path.exists():
        cons = pd.read_csv(cons_path)
        if not cons.empty and "Stage" in cons.columns and "Mean" in cons.columns:
            order = ["D1", "D2", "D3", "D4"]
            cons["Stage"] = pd.Categorical(cons["Stage"], categories=order, ordered=True)
            cons = cons.sort_values("Stage")
            axes[0].plot(cons["Stage"], cons["Mean"], marker="o", color="#4C72B0", linewidth=1.8, label="Consistency score")
            axes[0].set_ylim(0, 1)
            axes[0].set_title("Consistency by stage")
            axes[0].set_ylabel("Score (0-1)")
            axes[0].grid(axis="y", alpha=0.25)

            if "ConflictMean" in cons.columns or "HallucinationMean" in cons.columns:
                ax0b = axes[0].twinx()
                width = 0.34
                x = np.arange(cons.shape[0])
                if "ConflictMean" in cons.columns:
                    ax0b.bar(x - width / 2, cons["ConflictMean"].fillna(0), width=width, color="#C44E52", alpha=0.35, label="Conflict count")
                if "HallucinationMean" in cons.columns:
                    ax0b.bar(x + width / 2, cons["HallucinationMean"].fillna(0), width=width, color="#DD8452", alpha=0.35, label="Hallucination count")
                ax0b.set_ylabel("Issue count (per case)", fontsize=8)
                ax0b.tick_params(axis="y", labelsize=8)
                h1, l1 = axes[0].get_legend_handles_labels()
                h2, l2 = ax0b.get_legend_handles_labels()
                axes[0].legend(h1 + h2, l1 + l2, fontsize=7, frameon=False, loc="upper right")
            else:
                axes[0].legend(fontsize=7, frameon=False, loc="upper right")
        else:
            axes[0].text(0.5, 0.5, "Missing consistency data", ha="center", va="center")
            axes[0].axis("off")
    else:
        axes[0].text(0.5, 0.5, "Missing consistency data", ha="center", va="center")
        axes[0].axis("off")

    if mem_path.exists():
        mem = pd.read_csv(mem_path)
        if not mem.empty and "Stage" in mem.columns:
            stage_map = {
                "D2_Admission_Decision": "D2",
                "D3_Surgery_Decision": "D3",
                "D4_Rehab_Plan": "D4",
            }
            mem["Stage"] = mem["Stage"].map(stage_map).fillna(mem["Stage"])
            order = ["D1", "D2", "D3", "D4"]
            mem["Stage"] = pd.Categorical(mem["Stage"], categories=order, ordered=True)
            mem = mem.sort_values("Stage")

            if "InheritanceMean" in mem.columns:
                axes[1].plot(mem["Stage"], mem["InheritanceMean"], marker="o", color="#55A868", linewidth=1.8, label="Inheritance")
            if "UtilizationMean" in mem.columns:
                axes[1].plot(mem["Stage"], mem["UtilizationMean"], marker="s", color="#8172B2", linewidth=1.8, label="Utilization")
            if "Mean" in mem.columns:
                axes[1].plot(mem["Stage"], mem["Mean"], marker="D", color="#4C72B0", linewidth=1.2, linestyle="--", label="Overall memory")

            axes[1].set_ylim(0, 1)
            axes[1].set_title("Memory retention by stage")
            axes[1].set_ylabel("Score (0-1)")
            axes[1].grid(axis="y", alpha=0.25)
            axes[1].legend(fontsize=7, frameon=False, loc="lower left")
        else:
            axes[1].text(0.5, 0.5, "Missing memory data", ha="center", va="center")
            axes[1].axis("off")
    else:
        axes[1].text(0.5, 0.5, "Missing memory data", ha="center", va="center")
        axes[1].axis("off")

    plt.tight_layout()
    plt.savefig(PAPER_FIG / "Fig9_consistency_memory.png", dpi=300)
    plt.close()

def _load_alignment_tables(path: Path, sheet_name: str, judge_label: str) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    if not path.exists():
        return None
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    judge_rows = raw.index[raw[0].astype(str).str.contains(judge_label, na=False)]
    if judge_rows.empty:
        return None
    judge_idx = int(judge_rows[0])
    human_header = raw.loc[1].tolist()
    human = raw.loc[2:judge_idx - 1].copy()
    human.columns = human_header
    human = human[human["中心"].notna()]
    judge_header = raw.loc[judge_idx + 1].tolist()
    judge = raw.loc[judge_idx + 2:].copy()
    judge.columns = judge_header
    judge = judge[judge["中心"].notna()]
    return human, judge


def _melt_alignment(df: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
    id_cols = ["中心", "模型名称"]
    keep = [c for c in id_cols if c in df.columns]
    data = df[keep + value_cols].melt(id_vars=keep, var_name="Metric", value_name="Score")
    data["Score"] = pd.to_numeric(data["Score"], errors="coerce")
    data = data.dropna(subset=["Score"])
    data["Stage"] = data["Metric"].astype(str).str.split("_").str[0]
    return data


def plot_human_vs_judge_alignment() -> None:
    result_sheet = "人机对齐_结果质量"
    result_label = "Judge结果质量"
    reason_sheet = "人机对齐_推理合理性"
    reason_label = "LLM推理质量"

    latest_report = ROOT / "outputs" / "latest" / "summary" / "医生评测汇总.xlsx"
    candidates: list[Path] = []
    if latest_report.exists():
        candidates.append(latest_report)
    candidates.extend(
        sorted(
            (ROOT / "outputs" / "archive").glob("*_latest/summary/医生评测汇总.xlsx"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    )

    selected_path = None
    for cand in candidates:
        try:
            xls = pd.ExcelFile(cand)
        except Exception:
            continue
        if result_sheet in xls.sheet_names:
            selected_path = cand
            break
    if selected_path is None:
        return

    tables = _load_alignment_tables(selected_path, result_sheet, result_label)
    if not tables:
        return
    human, judge = tables

    human_cols = [
        c
        for c in human.columns
        if str(c).endswith("均值") and str(c) not in ["病例数"]
    ]
    judge_cols = [c for c in judge.columns if "_x5" in str(c)]
    human_long = _melt_alignment(human, human_cols)
    judge_long = _melt_alignment(judge, judge_cols)
    merged = human_long.merge(
        judge_long,
        on=["中心", "模型名称", "Stage"],
        suffixes=("_Human", "_Judge"),
    )
    if merged.empty:
        return

    def _to_bubble(frame: pd.DataFrame, x_col: str, y_col: str) -> pd.DataFrame:
        data = frame.copy()
        data["X"] = data[x_col].round(1)
        data["Y"] = data[y_col].round(1)
        bubble = (
            data.groupby(["Stage", "X", "Y"], as_index=False)
            .size()
            .rename(columns={"size": "RepeatCount"})
        )
        return bubble

    bubble_result = _to_bubble(merged, "Score_Human", "Score_Judge")
    corr_result = merged["Score_Human"].corr(merged["Score_Judge"])

    reason_bubble = None
    corr_reason = None
    reason_source = None
    for cand in candidates:
        try:
            xls = pd.ExcelFile(cand)
        except Exception:
            continue
        if reason_sheet not in xls.sheet_names:
            continue
        reason_tables = _load_alignment_tables(cand, reason_sheet, reason_label)
        if not reason_tables:
            continue
        human_r, llm_r = reason_tables
        h_cols = [
            c
            for c in human_r.columns
            if str(c).endswith("均值") and str(c) not in ["病例数"]
        ]
        l_cols = [c for c in llm_r.columns if "_x5" in str(c)]
        h_long = _melt_alignment(human_r, h_cols)
        l_long = _melt_alignment(llm_r, l_cols)
        merged_r = h_long.merge(
            l_long,
            on=["中心", "模型名称", "Stage"],
            suffixes=("_Human", "_LLM"),
        )
        if merged_r.empty:
            continue
        reason_bubble = _to_bubble(merged_r, "Score_Human", "Score_LLM")
        corr_reason = merged_r["Score_Human"].corr(merged_r["Score_LLM"])
        reason_source = cand
        break

    # Export Fig11 source data to figdata, so each plot has traceable tables.
    result_pairs = merged.copy().rename(
        columns={
            "Score_Human": "HumanScore",
            "Score_Judge": "JudgeScore",
        }
    )
    result_pairs["SourceWorkbook"] = selected_path.name
    result_pairs.to_csv(
        FIGDATA / "Fig11__human_judge_alignment_points.csv",
        index=False,
        encoding="utf-8-sig",
    )

    result_bubble = bubble_result.copy()
    result_bubble["SourceWorkbook"] = selected_path.name
    result_bubble.to_csv(
        FIGDATA / "Fig11__human_judge_alignment_bubble.csv",
        index=False,
        encoding="utf-8-sig",
    )

    corr_rows = [
        {
            "Panel": "ResultQuality",
            "Correlation": float(corr_result) if corr_result is not None and pd.notna(corr_result) else np.nan,
            "SourceWorkbook": selected_path.name,
        }
    ]

    if reason_bubble is not None and not reason_bubble.empty and "merged_r" in locals() and merged_r is not None:
        reason_source_name = reason_source.name if reason_source is not None else selected_path.name
        reason_pairs = merged_r.copy().rename(
            columns={
                "Score_Human": "HumanScore",
                "Score_LLM": "LLMScore",
            }
        )
        reason_pairs["SourceWorkbook"] = reason_source_name
        reason_pairs.to_csv(
            FIGDATA / "Fig11__human_llm_reasoning_points.csv",
            index=False,
            encoding="utf-8-sig",
        )

        reason_bubble_export = reason_bubble.copy()
        reason_bubble_export["SourceWorkbook"] = reason_source_name
        reason_bubble_export.to_csv(
            FIGDATA / "Fig11__human_llm_reasoning_bubble.csv",
            index=False,
            encoding="utf-8-sig",
        )

        corr_rows.append(
            {
                "Panel": "ReasoningQuality",
                "Correlation": float(corr_reason) if corr_reason is not None and pd.notna(corr_reason) else np.nan,
                "SourceWorkbook": reason_source_name,
            }
        )

    pd.DataFrame(corr_rows).to_csv(
        FIGDATA / "Fig11__human_llm_alignment_correlation.csv",
        index=False,
        encoding="utf-8-sig",
    )

    style_configs = [
        {
            "out": PAPER_FIG / "Fig11_human_vs_judge_alignment.png",
            "size_base": 32,
            "size_step": 80,
            "alpha": 0.72,
            "diag_color": "#666666",
            "stage_colors": {
                "门诊A": "#4C72B0",
                "门诊B": "#55A868",
                "住院A": "#C44E52",
                "住院B": "#8172B2",
                "术后": "#DD8452",
                "康复": "#64B5CD",
            },
        },
        {
            "out": PAPER_FIG / "Fig11A_human_vs_judge_alignment_styleA.png",
            "size_base": 34,
            "size_step": 78,
            "alpha": 0.76,
            "diag_color": "#5F5F5F",
            "stage_colors": {
                "门诊A": "#3F5D7D",
                "门诊B": "#5D9C86",
                "住院A": "#B24C63",
                "住院B": "#7A6AAE",
                "术后": "#C38D5A",
                "康复": "#5FA6C5",
            },
        },
        {
            "out": PAPER_FIG / "Fig11B_human_vs_judge_alignment_styleB.png",
            "size_base": 30,
            "size_step": 85,
            "alpha": 0.74,
            "diag_color": "#4F4F4F",
            "stage_colors": {
                "门诊A": "#2B6CB0",
                "门诊B": "#2F855A",
                "住院A": "#D1495B",
                "住院B": "#6A4C93",
                "术后": "#D17A22",
                "康复": "#1B9AAA",
            },
        },
    ]

    def _draw_panel(
        ax: plt.Axes,
        bubble_df: pd.DataFrame,
        corr_val: float | None,
        title: str,
        y_label: str,
        style: dict,
    ) -> None:
        if bubble_df is None or bubble_df.empty:
            ax.text(0.5, 0.5, "Missing alignment data", ha="center", va="center")
            ax.axis("off")
            return

        bubble_plot = bubble_df.copy()
        repeat_adj = bubble_plot["RepeatCount"].clip(lower=1)
        bubble_plot["MarkerSize"] = style["size_base"] + (repeat_adj ** 2.1) * style["size_step"]

        for stage, group in bubble_plot.groupby("Stage"):
            ax.scatter(
                group["X"],
                group["Y"],
                label=stage,
                alpha=style["alpha"],
                s=group["MarkerSize"],
                color=style["stage_colors"].get(stage, "#999999"),
                edgecolors="white",
                linewidths=0.5,
            )

        ax.plot([0, 5], [0, 5], color=style["diag_color"], linestyle="--", linewidth=1.1)
        corr_text = f"{corr_val:.2f}" if corr_val is not None and pd.notna(corr_val) else "NA"
        ax.set_title(f"{title}, r={corr_text}")
        ax.set_xlabel("Human score (0-5)")
        ax.set_ylabel(y_label)
        ax.set_xlim(-0.1, 5.1)
        ax.set_ylim(-0.1, 5.1)

        repeat_levels = [1, 2, 3, 4]
        max_repeat = int(bubble_plot["RepeatCount"].max()) if not bubble_plot.empty else 1
        repeat_levels = [x for x in repeat_levels if x <= max_repeat]
        if max_repeat > 4:
            repeat_levels.append(max_repeat)

        size_handles = [
            ax.scatter([], [], s=style["size_base"] + (rep ** 1.8) * style["size_step"], color="#9A9A9A", alpha=0.35, edgecolors="white", linewidths=0.5)
            for rep in repeat_levels
        ]
        size_legend = ax.legend(
            size_handles,
            [f"repeat={rep}" for rep in repeat_levels],
            title="Bubble size",
            fontsize=7,
            title_fontsize=8,
            frameon=False,
            loc="upper left",
            bbox_to_anchor=(0.0, 0.98),
            labelspacing=0.3,
            borderaxespad=0.3,
        )
        ax.add_artist(size_legend)

        ax.legend(fontsize=7, frameon=False, loc="lower right", bbox_to_anchor=(0.98, 0.02), ncol=2)

    for style in style_configs:
        fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.7))
        _draw_panel(
            axes[0],
            bubble_result,
            corr_result,
            "Human vs Judge (Results)",
            "Judge score (x5)",
            style,
        )

        if reason_bubble is not None and not reason_bubble.empty:
            _draw_panel(
                axes[1],
                reason_bubble,
                corr_reason,
                "Human vs LLM (Reasoning)",
                "LLM score (x5)",
                style,
            )
        else:
            axes[1].text(0.5, 0.5, "Missing reasoning alignment data", ha="center", va="center")
            axes[1].axis("off")

        _save_fig(style["out"])


def plot_doctor_consensus_placeholder() -> None:
    plt.figure(figsize=(5.2, 4.2))
    plt.text(
        0.5,
        0.5,
        "Pending: per-case dual-doctor ratings",
        ha="center",
        va="center",
        fontsize=11,
    )
    plt.axis("off")
    _save_fig(PAPER_FIG / "Fig10_doctor_consensus_placeholder.png")


def plot_decision_efficiency_and_cascade() -> None:
    metrics_path = _figdata_path("algorithmic_metrics_overall.csv")
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.0))
    if metrics_path.exists():
        df = pd.read_csv(metrics_path)
        target = df[df["Metric"].isin(["D1无效循环率(0匹配)", "D2无效循环率(0匹配)"])]
        if not target.empty:
            labels = target["Metric"].map({"D1无效循环率(0匹配)": "D1", "D2无效循环率(0匹配)": "D2"})
            axes[0].bar(labels, target["Mean"] * 100, color="#4C72B0")
            axes[0].set_ylabel("Inefficiency rate (%)")
            axes[0].set_title("Decision Efficiency (proxy)")
        else:
            axes[0].text(0.5, 0.5, "Missing inefficiency metrics", ha="center", va="center")
            axes[0].axis("off")
    else:
        axes[0].text(0.5, 0.5, "Missing metrics file", ha="center", va="center")
        axes[0].axis("off")

    axes[1].text(0.5, 0.5, "Pending: error cascade labels", ha="center", va="center")
    axes[1].axis("off")
    plt.tight_layout()
    plt.savefig(PAPER_FIG / "Fig12_decision_efficiency_cascade_placeholder.png", dpi=300)
    plt.close()


def plot_icd10_chapter_coverage() -> None:
    path = _figdata_path("dataset_icd10_chapter_coverage.csv")
    if not path.exists():
        return
    df = pd.read_csv(path)
    if df.empty:
        return
    df = df.sort_values("ICD10Chapter")

    label_map = {
        "C": "Malignant neoplasms",
        "D": "In situ / benign neoplasms",
        "N": "Genitourinary diseases",
        "O": "Pregnancy & childbirth",
        "Z": "Other factors",
    }

    covered = pd.to_numeric(df["CoveredCategories"], errors="coerce").fillna(0).astype(float)
    catalog = pd.to_numeric(df["CatalogCategories"], errors="coerce").fillna(0).astype(float)
    missing = (catalog - covered).clip(lower=0)
    chapter = df["ICD10Chapter"].astype(str).tolist()

    base_colors = ["#4C72B0", "#55A868", "#8172B2", "#DD8452", "#64B5CD", "#C44E52"]
    chapter_colors = [base_colors[i % len(base_colors)] for i in range(len(chapter))]

    fig, ax = plt.subplots(1, 1, figsize=(9.4, 5.2))

    outer_sizes = catalog.to_numpy()
    outer_labels = chapter
    ax.pie(
        outer_sizes,
        radius=1.0,
        labels=outer_labels,
        labeldistance=1.06,
        colors=chapter_colors,
        startangle=90,
        wedgeprops={"width": 0.28, "edgecolor": "white", "linewidth": 1.0},
        textprops={"fontsize": 9},
    )

    inner_sizes = []
    inner_colors = []
    for idx in range(len(chapter)):
        inner_sizes.extend([covered.iloc[idx], missing.iloc[idx]])
        inner_colors.extend([chapter_colors[idx], "#E6E6E6"])
    ax.pie(
        inner_sizes,
        radius=0.72,
        labels=None,
        colors=inner_colors,
        startangle=90,
        wedgeprops={"width": 0.28, "edgecolor": "white", "linewidth": 0.9},
    )

    cov_total = covered.sum()
    cat_total = catalog.sum()
    cov_pct = (cov_total / cat_total * 100) if cat_total else 0
    ax.text(
        0,
        0,
        f"ICD-10\ncoverage\n{int(cov_total)}/{int(cat_total)}\n({cov_pct:.1f}%)",
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
    )
    ax.set_title("Gyne ICD-10 chapter coverage (nested donut)")

    legend_rows = []
    for idx, chap in enumerate(chapter):
        name = label_map.get(chap, "ICD-10 chapter")
        cov = covered.iloc[idx]
        cat = catalog.iloc[idx]
        cov_rate = (cov / cat * 100) if cat else 0
        legend_rows.append(f"{chap} {name}  {int(cov)}/{int(cat)} ({cov_rate:.1f}%)")

    ax.legend(
        handles=[
            plt.Rectangle((0, 0), 1, 1, color=chapter_colors[i], ec="white")
            for i in range(len(chapter))
        ],
        labels=legend_rows,
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        frameon=False,
        fontsize=8,
        title="Chapter coverage",
        title_fontsize=9,
    )

    _save_fig(PAPER_FIG / "Fig1k_icd10_chapter_coverage.png")

def plot_decision_review_breakdown() -> None:
    d2_path = _figdata_path("d2_decision_review_breakdown.csv")
    d3_path = _figdata_path("d3_decision_review_breakdown.csv")
    if d2_path.exists():
        df = pd.read_csv(d2_path).sort_values("Cases", ascending=True)
        plt.figure(figsize=(7.2, 4.6))
        plt.barh(df["Category"], df["Cases"], color="#4C72B0")
        plt.xlabel("Cases")
        plt.title("D2 Decision Review Breakdown")
        _save_fig(PAPER_FIG / "Fig8a_d2_decision_review_breakdown.png")
    if d3_path.exists():
        df = pd.read_csv(d3_path).sort_values("Cases", ascending=True)
        plt.figure(figsize=(7.2, 4.6))
        plt.barh(df["Category"], df["Cases"], color="#55A868")
        plt.xlabel("Cases")
        plt.title("D3 Decision Review Breakdown")
        _save_fig(PAPER_FIG / "Fig8b_d3_decision_review_breakdown.png")



def copy_figures() -> None:
    mapping = {
        "outputs/latest/figures/alignment/alignment_result_quality_stagewise_佛山.png": "Fig2a_alignment_result_quality_佛山.png",
        "outputs/latest/figures/alignment/alignment_result_quality_stagewise_武汉.png": "Fig2b_alignment_result_quality_武汉.png",
        "outputs/latest/figures/alignment/alignment_result_quality_stagewise_新疆.png": "Fig2c_alignment_result_quality_新疆.png",
        "outputs/latest/figures/algorithmic/algorithmic_check_match_rate_stagewise_佛山.png": "Fig3a_check_match_rate_佛山.png",
        "outputs/latest/figures/algorithmic/algorithmic_check_match_rate_stagewise_武汉.png": "Fig3b_check_match_rate_武汉.png",
        "outputs/latest/figures/algorithmic/algorithmic_check_match_rate_stagewise_新疆.png": "Fig3c_check_match_rate_新疆.png",
        "outputs/latest/figures/algorithmic/algorithmic_loop_inefficiency_stagewise_佛山.png": "Fig3d_loop_inefficiency_佛山.png",
        "outputs/latest/figures/algorithmic/algorithmic_loop_inefficiency_stagewise_武汉.png": "Fig3e_loop_inefficiency_武汉.png",
        "outputs/latest/figures/algorithmic/algorithmic_loop_inefficiency_stagewise_新疆.png": "Fig3f_loop_inefficiency_新疆.png",
        "outputs/latest/figures/alignment/alignment_reasoning_quality_stagewise_佛山.png": "Fig4a_alignment_reasoning_quality_佛山.png",
        "outputs/latest/figures/alignment/alignment_reasoning_quality_stagewise_武汉.png": "Fig4b_alignment_reasoning_quality_武汉.png",
        "outputs/latest/figures/alignment/alignment_reasoning_quality_stagewise_新疆.png": "Fig4c_alignment_reasoning_quality_新疆.png",
        "outputs/latest/figures/calibration/calibration_ece_stagewise_佛山.png": "Fig5a_calibration_ece_佛山.png",
        "outputs/latest/figures/calibration/calibration_ece_stagewise_武汉.png": "Fig5b_calibration_ece_武汉.png",
        "outputs/latest/figures/calibration/calibration_ece_stagewise_新疆.png": "Fig5c_calibration_ece_新疆.png",
        "outputs/latest/figures/calibration/calibration_reliability_stagewise_佛山.png": "Fig5d_calibration_reliability_佛山.png",
        "outputs/latest/figures/calibration/calibration_reliability_stagewise_武汉.png": "Fig5e_calibration_reliability_武汉.png",
        "outputs/latest/figures/calibration/calibration_reliability_stagewise_新疆.png": "Fig5f_calibration_reliability_新疆.png",
        "outputs/latest/figures/llm/small/summary/llm_small_topk_lines_combined.png": "Fig6a_llm_small_topk_hit_rates.png",
        "outputs/latest/figures/llm/small/summary/llm_small_诊断质量_小规模汇总.png": "Fig6b_llm_small_diagnosis_quality.png",
        "outputs/latest/figures/llm/small/summary/llm_small_metric_metric_combined.png": "Fig6c_llm_small_fact_consistency.png",
        "outputs/latest/figures/llm/small/summary/llm_small_metric_0_1_combined.png": "Fig6d_llm_small_rationale_quality.png",
        "outputs/latest/figures/llm/small/summary/llm_small_方案质量_小规模汇总.png": "Fig6e_llm_small_plan_quality.png",
        "outputs/latest/figures/llm/small/summary/llm_small_诊断偏向性_小规模汇总.png": "Fig6f_llm_small_diagnosis_bias.png",
        "outputs/latest/figures/llm/small/summary/llm_small_康复-随访计划质量_小规模汇总.png": "Fig6g_llm_small_rehab_followup_quality.png",
        "outputs/latest/figures/llm/small/summary/llm_small_未匹配检查合理性_小规模汇总.png": "Fig6h_llm_small_unmatched_check_reasonableness.png",
        "outputs/latest/figures/sankey/sankey_flow_grid.png": "Fig7_sankey_flow_grid.png",
        "outputs/latest/figures/sankey/sankey_flow_佛山_gemini-2.5-pro.png": "Fig7a_sankey_佛山_gemini-2.5-pro.png",
        "outputs/latest/figures/sankey/sankey_flow_武汉_gemini-2.5-pro.png": "Fig7b_sankey_武汉_gemini-2.5-pro.png",
        "outputs/latest/figures/sankey/sankey_flow_新疆_gemini-2.5-pro.png": "Fig7c_sankey_新疆_gemini-2.5-pro.png",
    }
    for src, dest in mapping.items():
        src_path = ROOT / src
        if not src_path.exists():
            continue
        shutil.copy2(src_path, PAPER_FIG / dest)


def main() -> None:
    cleanup_deprecated_figures()
    plot_center_counts()
    plot_diagnosis_category_counts()
    plot_text_length_histogram()
    plot_stage_coverage()
    plot_check_type_distribution()
    plot_plan_type_distribution()
    plot_case_difficulty_profile()
    plot_consistency_and_memory()
    plot_human_vs_judge_alignment()
    plot_manual_quality_summaries()
    plot_doctor_consensus_placeholder()
    plot_decision_efficiency_and_cascade()
    plot_icd10_chapter_coverage()
    plot_decision_review_breakdown()
    copy_figures()


if __name__ == "__main__":
    main()
