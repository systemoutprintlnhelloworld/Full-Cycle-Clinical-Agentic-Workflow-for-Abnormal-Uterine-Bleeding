from __future__ import annotations

import argparse
import json
import logging
from math import ceil
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AUTO_EVAL_ROOT = ROOT.parent / "自动测评系统"
DEFAULT_SUPP_ROOT = ROOT / "analysis_viz" / "figures" / "v2_subplots" / "_supplementary" / "ablation"

MODEL_ORDER = [
    "claude-opus-4-1-20250805-thinking",
    "deepseek-v3-1-think-250821",
    "gemini-2.5-pro",
    "gpt-5-2025-08-07",
    "grok-4",
]

MODEL_SHORT = {
    "claude-opus-4-1-20250805-thinking": "claude-4.1",
    "deepseek-v3-1-think-250821": "deepseek-v3",
    "gemini-2.5-pro": "gemini-2.5p",
    "gpt-5-2025-08-07": "gpt-5",
    "grok-4": "grok-4",
}

CENTER_CN = {
    "Foshan": "佛山",
    "Wuhan": "武汉",
    "Xinjiang": "新疆",
}

METRIC_SPECS = [
    {
        "metric_key": "d1_diag",
        "stage": "D1",
        "metric_type": "诊断",
        "metric_label": "D1 诊断",
        "baseline_sheet": "D1_Outpatient_Decision",
        "baseline_col": "Gate1判官_原始JSON_诊断匹配_评分",
        "ablation_section": "诊断匹配评估",
    },
    {
        "metric_key": "d1_plan",
        "stage": "D1",
        "metric_type": "方案",
        "metric_label": "D1 方案",
        "baseline_sheet": "D1_Outpatient_Decision",
        "baseline_col": "Gate1判官_原始JSON_检查匹配_评分",
        "ablation_section": "治疗方案匹配评估",
    },
    {
        "metric_key": "d2_diag",
        "stage": "D2",
        "metric_type": "诊断",
        "metric_label": "D2 诊断",
        "baseline_sheet": "D2_Admission_Decision",
        "baseline_col": "Gate2判官_原始JSON_修正诊断匹配_评分",
        "ablation_section": "诊断匹配评估",
    },
    {
        "metric_key": "d2_plan",
        "stage": "D2",
        "metric_type": "方案",
        "metric_label": "D2 术前方案",
        "baseline_sheet": "D2_Admission_Decision",
        "baseline_col": "Gate2判官_原始JSON_手术方案匹配_评分",
        "ablation_section": "治疗方案匹配评估",
    },
    {
        "metric_key": "d3_diag",
        "stage": "D3",
        "metric_type": "诊断",
        "metric_label": "D3 诊断",
        "baseline_sheet": "D3_Surgery_Decision",
        "baseline_col": "判官_原始JSON_诊断匹配评估_评分",
        "ablation_section": "诊断匹配评估",
    },
    {
        "metric_key": "d3_plan",
        "stage": "D3",
        "metric_type": "方案",
        "metric_label": "D3 术后方案",
        "baseline_sheet": "D3_Surgery_Decision",
        "baseline_col": "判官_原始JSON_治疗方案匹配评估_评分",
        "ablation_section": "治疗方案匹配评估",
    },
]

METRIC_ORDER = [item["metric_key"] for item in METRIC_SPECS]
METRIC_LABEL_MAP = {item["metric_key"]: item["metric_label"] for item in METRIC_SPECS}

PANEL_METRIC_ORDER = ["d3_plan", "d3_diag", "d2_plan", "d2_diag", "d1_plan", "d1_diag"]

MODEL_COLORS = {
    "claude-4.1": "#1f77b4",
    "deepseek-v3": "#ff7f0e",
    "gemini-2.5p": "#2ca02c",
    "gpt-5": "#d62728",
    "grok-4": "#9467bd",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

sns.set_style("whitegrid")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["ps.fonttype"] = 42
mpl.rcParams["svg.fonttype"] = "none"
mpl.rcParams["pdf.fonttype"] = 42
mpl.rcParams["ps.fonttype"] = 42


def save_figure_bundle(fig: plt.Figure, output_path: Path, dpi: int = 240) -> None:
    """Save PNG plus Illustrator-friendly SVG/PDF sidecars."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi)
    if output_path.suffix.lower() != ".png":
        return
    for fmt in ("svg", "pdf"):
        fig.savefig(output_path.with_suffix(f".{fmt}"), format=fmt)


def normalize_case_id(value: object) -> str:
    text = str(value or "").strip()
    return text.lower().replace("-", "_")


def safe_float(value: object) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
    except Exception:
        if value is None:
            return None
    try:
        out = float(value)
        if pd.isna(out):
            return None
        return out
    except Exception:
        return None


def load_selected_tracks(auto_eval_root: Path, run_label: str, models: list[str]) -> pd.DataFrame:
    run_root = auto_eval_root / "output_ablation_no_check_d3" / run_label
    summary_path = run_root / "summary.csv"
    selected_tracks_path = run_root / "selected_tracks.csv"
    selected_cases_path = run_root / "selected_cases.csv"

    if summary_path.exists():
        summary = pd.read_csv(summary_path, encoding="utf-8-sig", dtype=object)
        required = {"center", "case_id", "model"}
        if not required.issubset(set(summary.columns)):
            raise ValueError(f"summary.csv 缺少列: {required - set(summary.columns)}")
        if "status" in summary.columns:
            summary = summary[summary["status"].astype(str).str.lower() == "success"].copy()
        tracks = summary[list(required)].copy()
    elif selected_tracks_path.exists():
        tracks = pd.read_csv(selected_tracks_path, encoding="utf-8-sig", dtype=object)
        required = {"center", "case_id", "model"}
        if not required.issubset(set(tracks.columns)):
            raise ValueError(f"selected_tracks.csv 缺少列: {required - set(tracks.columns)}")
        tracks = tracks[list(required)].copy()
    else:
        if not selected_cases_path.exists():
            raise FileNotFoundError(f"selected_tracks.csv / selected_cases.csv 均不存在: {run_root}")
        cases = pd.read_csv(selected_cases_path, encoding="utf-8-sig", dtype=object)
        if "center" not in cases.columns or "case_id" not in cases.columns:
            raise ValueError(f"selected_cases.csv 缺少 center/case_id: {selected_cases_path}")
        rows: list[dict] = []
        for _, row in cases.iterrows():
            for model in models:
                rows.append(
                    {
                        "center": str(row["center"]),
                        "case_id": str(row["case_id"]),
                        "model": model,
                    }
                )
        tracks = pd.DataFrame(rows)

    tracks["center"] = tracks["center"].astype(str)
    tracks["case_id"] = tracks["case_id"].astype(str)
    tracks["model"] = tracks["model"].astype(str)
    tracks = tracks.drop_duplicates(subset=["center", "case_id", "model"]).reset_index(drop=True)
    tracks["case_id_norm"] = tracks["case_id"].map(normalize_case_id)
    tracks["model_short"] = tracks["model"].map(MODEL_SHORT).fillna(tracks["model"])
    tracks["run_label"] = run_label
    tracks["run_mtime"] = run_root.stat().st_mtime if run_root.exists() else 0.0
    return tracks


def load_selected_tracks_by_center(
    auto_eval_root: Path,
    center_run_labels: dict[str, str],
    models: list[str],
) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    for center, run_label in center_run_labels.items():
        df = load_selected_tracks(auto_eval_root, run_label, models)
        if "center" in df.columns:
            df = df[df["center"].astype(str) == str(center)].copy()
        if df.empty:
            logger.warning("中心 %s 在 run_label=%s 下无 selected_tracks。", center, run_label)
            continue
        df["run_label"] = run_label
        chunks.append(df)
    if not chunks:
        raise RuntimeError("未从任何 run_label 读取到 selected_tracks。")
    out = pd.concat(chunks, ignore_index=True)
    out = out.drop_duplicates(subset=["center", "case_id_norm", "model"], keep="first").reset_index(drop=True)
    return out


def discover_run_labels(
    auto_eval_root: Path,
    exclude_runs: list[str] | None = None,
) -> list[str]:
    run_base = auto_eval_root / "output_ablation_no_check_d3"
    if not run_base.exists():
        return []

    exclude = set(exclude_runs or [])
    exclude |= {"remaining_cases_for_fulltest", "channel_test_quick"}
    labels: list[str] = []
    for path in run_base.iterdir():
        if not path.is_dir():
            continue
        name = path.name
        if name.startswith("_"):
            continue
        if name in exclude:
            continue
        if (path / "summary.csv").exists() or (path / "selected_tracks.csv").exists() or (path / "selected_cases.csv").exists():
            labels.append(name)

    labels = sorted(labels, key=lambda n: (run_base / n).stat().st_mtime)
    return labels


def load_selected_tracks_multi(
    auto_eval_root: Path,
    run_labels: list[str],
    models: list[str],
) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    for idx, run_label in enumerate(run_labels):
        df = load_selected_tracks(auto_eval_root, run_label, models)
        if df.empty:
            logger.warning("run_label=%s 下无可用轨迹（summary success 或 selected_tracks）。", run_label)
            continue
        df["run_index"] = idx
        chunks.append(df)
    if not chunks:
        raise RuntimeError("run_labels 读取后为空，请检查 run_label 是否存在且有可用轨迹。")

    out = pd.concat(chunks, ignore_index=True)
    out = out.sort_values(["run_mtime", "run_index"], ascending=[False, False]).reset_index(drop=True)
    out = out.drop_duplicates(subset=["center", "case_id_norm", "model"], keep="first").reset_index(drop=True)
    return out


def load_baseline_scores(llm_root: Path, tracks_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    center_models = tracks_df[["center", "model"]].drop_duplicates().reset_index(drop=True)

    for _, cm in center_models.iterrows():
        center_en = str(cm["center"])
        model = str(cm["model"])
        center_cn = CENTER_CN.get(center_en)
        if not center_cn:
            logger.warning("未识别中心映射，跳过 baseline center=%s", center_en)
            continue

        excel_path = (
            llm_root / "data" / center_cn / "judge agent" / f"Evaluation_Summary_{model}_CN_Judge_Parsed.xlsx"
        )
        if not excel_path.exists():
            logger.warning("baseline 文件不存在: %s", excel_path)
            continue

        cache: dict[str, pd.DataFrame] = {}
        for spec in METRIC_SPECS:
            sheet_name = spec["baseline_sheet"]
            if sheet_name not in cache:
                frame = pd.read_excel(excel_path, sheet_name=sheet_name, dtype=object)
                cache[sheet_name] = frame
            else:
                frame = cache[sheet_name]

            if frame.empty:
                continue

            case_col = "病例ID" if "病例ID" in frame.columns else frame.columns[0]
            status_col = "状态" if "状态" in frame.columns else (frame.columns[1] if len(frame.columns) > 1 else None)

            if spec["baseline_col"] not in frame.columns:
                logger.warning("baseline 缺少评分列: %s | %s | %s", excel_path, sheet_name, spec["baseline_col"])
                continue

            for _, row in frame.iterrows():
                case_id = str(row.get(case_col) or "").strip()
                if not case_id:
                    continue
                rows.append(
                    {
                        "center": center_en,
                        "case_id": case_id,
                        "case_id_norm": normalize_case_id(case_id),
                        "model": model,
                        "stage": spec["stage"],
                        "metric_type": spec["metric_type"],
                        "metric_key": spec["metric_key"],
                        "metric_label": spec["metric_label"],
                        "baseline_score": safe_float(row.get(spec["baseline_col"])),
                        "baseline_status": row.get(status_col) if status_col else None,
                        "baseline_sheet": sheet_name,
                        "baseline_col": spec["baseline_col"],
                        "baseline_source_file": str(excel_path),
                    }
                )

    baseline_df = pd.DataFrame(rows)
    if baseline_df.empty:
        return baseline_df
    baseline_df = baseline_df.drop_duplicates(
        subset=["center", "case_id_norm", "model", "metric_key"],
        keep="first",
    ).reset_index(drop=True)
    return baseline_df


def load_ablation_scores(auto_eval_root: Path, tracks_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []

    for _, track in tracks_df.iterrows():
        run_label = str(track.get("run_label") or "").strip()
        if not run_label:
            continue
        run_root = auto_eval_root / "output_ablation_no_check_d3" / run_label
        center = str(track["center"])
        case_id = str(track["case_id"])
        model = str(track["model"])
        case_id_norm = normalize_case_id(case_id)

        per_case_path = (
            run_root / "outputs" / center / model / "per_case_json" / f"{model}_{center}_{case_id}.json"
        )
        status = "missing"
        stages: dict = {}
        if per_case_path.exists():
            payload = json.loads(per_case_path.read_text(encoding="utf-8"))
            case_result = payload.get("case_result", {}) or {}
            status = str(case_result.get("status", "unknown"))
            stages = case_result.get("stages", {}) or {}

        for spec in METRIC_SPECS:
            stage_payload = stages.get(spec["stage"], {}) or {}
            judge_payload = stage_payload.get("judge", {}) or {}
            section = judge_payload.get(spec["ablation_section"], {}) or {}
            score = safe_float(section.get("评分"))
            rows.append(
                {
                    "center": center,
                    "case_id": case_id,
                    "case_id_norm": case_id_norm,
                    "model": model,
                    "stage": spec["stage"],
                    "metric_type": spec["metric_type"],
                    "metric_key": spec["metric_key"],
                    "metric_label": spec["metric_label"],
                    "ablation_score": score,
                    "ablation_status": status,
                    "ablation_run_label": run_label,
                    "ablation_source_file": str(per_case_path),
                }
            )
    return pd.DataFrame(rows)


def build_pair_detail(tracks_df: pd.DataFrame, baseline_df: pd.DataFrame, ablation_df: pd.DataFrame) -> pd.DataFrame:
    grid_rows: list[dict] = []
    for _, row in tracks_df.iterrows():
        for spec in METRIC_SPECS:
            grid_rows.append(
                {
                    "center": str(row["center"]),
                    "case_id": str(row["case_id"]),
                    "case_id_norm": str(row["case_id_norm"]),
                    "model": str(row["model"]),
                    "model_short": str(row["model_short"]),
                    "run_label": str(row.get("run_label") or ""),
                    "stage": spec["stage"],
                    "metric_type": spec["metric_type"],
                    "metric_key": spec["metric_key"],
                    "metric_label": spec["metric_label"],
                }
            )

    pair_df = pd.DataFrame(grid_rows)
    pair_df = pair_df.merge(
        baseline_df[
            [
                "center",
                "case_id_norm",
                "model",
                "metric_key",
                "baseline_score",
                "baseline_status",
                "baseline_sheet",
                "baseline_col",
                "baseline_source_file",
            ]
        ],
        on=["center", "case_id_norm", "model", "metric_key"],
        how="left",
    )
    pair_df = pair_df.merge(
        ablation_df[
            [
                "center",
                "case_id_norm",
                "model",
                "metric_key",
                "ablation_score",
                "ablation_status",
                "ablation_run_label",
                "ablation_source_file",
            ]
        ],
        on=["center", "case_id_norm", "model", "metric_key"],
        how="left",
    )
    pair_df["delta_score"] = pair_df["ablation_score"] - pair_df["baseline_score"]
    pair_df["paired_flag"] = pair_df["baseline_score"].notna() & pair_df["ablation_score"].notna()
    pair_df["pair_key"] = pair_df["center"] + "::" + pair_df["case_id"] + "::" + pair_df["model"]
    pair_df["metric_order"] = pair_df["metric_key"].map({key: idx for idx, key in enumerate(METRIC_ORDER)})
    pair_df["model_order"] = pair_df["model"].map({m: i for i, m in enumerate(MODEL_ORDER)}).fillna(999)
    pair_df = pair_df.sort_values(
        ["center", "case_id", "model_order", "metric_order"],
        ascending=[True, True, True, True],
    ).reset_index(drop=True)
    return pair_df


def get_plot_metric_keys(pair_df: pd.DataFrame) -> list[str]:
    metric_paired = (
        pair_df.groupby(["metric_key"], as_index=False)
        .agg(paired_n=("paired_flag", lambda s: int(s.sum())))
        .set_index("metric_key")["paired_n"]
        .to_dict()
    )
    keys = [k for k in METRIC_ORDER if metric_paired.get(k, 0) > 0]
    if not keys:
        raise RuntimeError("未找到可绘图的配对指标（paired_n=0）。")
    return keys


def resolve_metric_scope_keys(
    available_keys: list[str],
    metric_scope: str,
) -> list[str]:
    if metric_scope == "diag":
        preferred = ["d1_diag", "d2_diag", "d3_diag"]
    else:
        preferred = METRIC_ORDER
    keys = [k for k in preferred if k in available_keys]
    if not keys:
        raise RuntimeError(f"metric_scope={metric_scope} 下无可用配对指标。")
    return keys


def build_dumbbell_tables(pair_df: pd.DataFrame, metric_keys: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    detail_df = pair_df[pair_df["paired_flag"] & pair_df["metric_key"].isin(metric_keys)].copy()
    calc_df = (
        detail_df.groupby(["metric_key", "metric_label"], as_index=False)
        .agg(
            paired_n=("delta_score", "size"),
            baseline_mean=("baseline_score", "mean"),
            ablation_mean=("ablation_score", "mean"),
            delta_mean=("delta_score", "mean"),
            delta_std=("delta_score", "std"),
            delta_median=("delta_score", "median"),
        )
        .reset_index(drop=True)
    )
    calc_df["metric_order"] = calc_df["metric_key"].map({key: idx for idx, key in enumerate(METRIC_ORDER)})
    calc_df = calc_df.sort_values("metric_order").reset_index(drop=True)

    summary_df = calc_df[
        ["metric_key", "metric_label", "paired_n", "baseline_mean", "ablation_mean", "delta_mean", "delta_std", "delta_median"]
    ].copy()
    summary_df["计算口径"] = "同中心+同病例+同模型+同指标配对后，先算差值(消融-正常)，再聚合"
    return detail_df, calc_df, summary_df


def build_bar_tables(pair_df: pd.DataFrame, metric_keys: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    detail_df = pair_df[pair_df["paired_flag"] & pair_df["metric_key"].isin(metric_keys)].copy()
    calc_df = (
        detail_df.groupby(["model", "model_short", "metric_key", "metric_label"], as_index=False)
        .agg(
            paired_n=("delta_score", "size"),
            delta_mean=("delta_score", "mean"),
            delta_std=("delta_score", "std"),
            delta_median=("delta_score", "median"),
            baseline_mean=("baseline_score", "mean"),
            ablation_mean=("ablation_score", "mean"),
        )
        .reset_index(drop=True)
    )
    calc_df["metric_order"] = calc_df["metric_key"].map({key: idx for idx, key in enumerate(METRIC_ORDER)})
    calc_df["model_order"] = calc_df["model"].map({name: idx for idx, name in enumerate(MODEL_ORDER)}).fillna(999)
    calc_df = calc_df.sort_values(["metric_order", "model_order"]).reset_index(drop=True)

    summary_df = calc_df.pivot_table(
        index=["metric_key", "metric_label"],
        columns="model_short",
        values="delta_mean",
        aggfunc="first",
    ).reset_index()
    summary_df["metric_order"] = summary_df["metric_key"].map({key: idx for idx, key in enumerate(METRIC_ORDER)})
    summary_df = summary_df.sort_values("metric_order").reset_index(drop=True)
    summary_df["计算口径"] = "同中心+同病例+同模型+同指标配对后，按模型与指标聚合差值(消融-正常)"
    return detail_df, calc_df, summary_df


def build_panel_tables(pair_df: pd.DataFrame, metric_keys: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    detail_df = pair_df[pair_df["paired_flag"] & pair_df["metric_key"].isin(metric_keys)].copy()
    calc_df = (
        detail_df.groupby(["model", "model_short", "metric_key", "metric_label"], as_index=False)
        .agg(
            paired_n=("delta_score", "size"),
            baseline_mean=("baseline_score", "mean"),
            ablation_mean=("ablation_score", "mean"),
            delta_mean=("delta_score", "mean"),
            delta_std=("delta_score", "std"),
            delta_median=("delta_score", "median"),
        )
        .reset_index(drop=True)
    )
    calc_df["metric_order"] = calc_df["metric_key"].map(
        {key: idx for idx, key in enumerate(PANEL_METRIC_ORDER)}
    )
    calc_df["model_order"] = calc_df["model"].map({name: idx for idx, name in enumerate(MODEL_ORDER)}).fillna(999)
    calc_df = calc_df.sort_values(["model_order", "metric_order"]).reset_index(drop=True)

    summary_df = calc_df[
        [
            "model",
            "model_short",
            "metric_key",
            "metric_label",
            "paired_n",
            "baseline_mean",
            "ablation_mean",
            "delta_mean",
            "delta_std",
            "delta_median",
        ]
    ].copy()
    summary_df["计算口径"] = "同模型内，按指标比较正常流程均值 vs 消融流程均值（仅配对样本）"
    return detail_df, calc_df, summary_df


def build_center_panel_tables(pair_df: pd.DataFrame, metric_keys: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    detail_df = pair_df[pair_df["paired_flag"] & pair_df["metric_key"].isin(metric_keys)].copy()
    calc_df = (
        detail_df.groupby(["center", "metric_key", "metric_label"], as_index=False)
        .agg(
            paired_n=("delta_score", "size"),
            baseline_mean=("baseline_score", "mean"),
            ablation_mean=("ablation_score", "mean"),
            delta_mean=("delta_score", "mean"),
            delta_std=("delta_score", "std"),
            delta_median=("delta_score", "median"),
        )
        .reset_index(drop=True)
    )
    calc_df["metric_order"] = calc_df["metric_key"].map(
        {key: idx for idx, key in enumerate(PANEL_METRIC_ORDER)}
    )
    calc_df["center_order"] = calc_df["center"].map({name: idx for idx, name in enumerate(CENTER_CN.keys())}).fillna(999)
    calc_df = calc_df.sort_values(["center_order", "metric_order"]).reset_index(drop=True)
    summary_df = calc_df.copy()
    summary_df["计算口径"] = "同中心内，按指标比较正常流程均值 vs 消融流程均值（仅配对样本）"
    return detail_df, calc_df, summary_df


def plot_dumbbell(calc_df: pd.DataFrame, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11.2, 5.8))
    rows = calc_df.copy()
    y_values = list(range(len(rows)))
    for idx, row in rows.iterrows():
        n_val = float(row["baseline_mean"])
        a_val = float(row["ablation_mean"])
        ax.plot([n_val, a_val], [idx, idx], color="#9ca3af", linewidth=2.2, zorder=1)
        ax.scatter(n_val, idx, color="#2563eb", s=72, zorder=2, label="正常流程" if idx == 0 else None)
        ax.scatter(a_val, idx, color="#dc2626", s=72, zorder=2, label="消融流程" if idx == 0 else None)
        ax.text(
            max(n_val, a_val) + 0.01,
            idx,
            f"Δ={row['delta_mean']:+.3f} (n={int(row['paired_n'])})",
            va="center",
            fontsize=9.4,
            color="#334155",
        )

    ax.set_yticks(y_values)
    ax.set_yticklabels(rows["metric_label"])
    ax.set_xlim(0, 1)
    ax.set_xlabel("平均评分（仅配对样本）")
    ax.set_title("消融前后评分对比（总体哑铃图）")
    ax.grid(axis="x", linestyle="--", alpha=0.35)
    # 将图例固定到右上角外侧空白区，避免遮挡哑铃线与标注文本
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=True, borderaxespad=0.0)
    plt.tight_layout(rect=[0.0, 0.0, 0.84, 1.0])
    save_figure_bundle(fig, output_path, dpi=240)
    plt.close(fig)


def plot_delta_bar(calc_df: pd.DataFrame, metric_keys: list[str], output_path: Path) -> None:
    plot_df = calc_df.copy()
    plot_df["metric_label"] = pd.Categorical(
        plot_df["metric_key"],
        categories=metric_keys,
        ordered=True,
    )
    plot_df["metric_label"] = plot_df["metric_label"].map(METRIC_LABEL_MAP)
    model_short_order = [MODEL_SHORT[name] for name in MODEL_ORDER if MODEL_SHORT[name] in set(plot_df["model_short"])]
    plot_df["model_short"] = pd.Categorical(plot_df["model_short"], categories=model_short_order, ordered=True)

    fig, ax = plt.subplots(figsize=(15.5, 6.8))
    sns.barplot(
        data=plot_df,
        x="metric_label",
        y="delta_mean",
        hue="model_short",
        hue_order=model_short_order,
        palette=MODEL_COLORS,
        ax=ax,
    )
    ax.axhline(0, color="#475569", linewidth=1.2)
    ax.set_xlabel("")
    ax.set_ylabel("平均分变化（消融 - 正常）")
    ax.set_title("消融带来的评分增减（分模型柱状图）")
    ax.tick_params(axis="x", rotation=12)
    ax.legend(title="模型", loc="upper right")
    plt.tight_layout()
    save_figure_bundle(fig, output_path, dpi=240)
    plt.close(fig)


def plot_model_panel_dumbbell(calc_df: pd.DataFrame, metric_keys: list[str], output_path: Path) -> None:
    present_models = [m for m in MODEL_ORDER if m in set(calc_df["model"])]
    if not present_models:
        raise RuntimeError("分模型哑铃图无可用模型。")

    n_models = len(present_models)
    ncols = 3
    nrows = ceil(n_models / ncols)
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(7.1 * ncols, 4.7 * nrows), squeeze=False)

    panel_metric_keys = [k for k in PANEL_METRIC_ORDER if k in metric_keys]
    panel_metric_labels = [METRIC_LABEL_MAP[k] for k in panel_metric_keys]
    y_values = list(range(len(panel_metric_keys)))

    for idx, model in enumerate(present_models):
        r = idx // ncols
        c = idx % ncols
        ax = axes[r][c]
        model_df = calc_df[calc_df["model"] == model].copy()
        model_df["metric_order"] = model_df["metric_key"].map({k: i for i, k in enumerate(panel_metric_keys)})
        model_df = model_df.sort_values("metric_order").reset_index(drop=True)

        value_map = {row["metric_key"]: row for _, row in model_df.iterrows()}
        for y_idx, metric_key in enumerate(panel_metric_keys):
            row_data = value_map.get(metric_key)
            if row_data is None:
                continue
            n_val = float(row_data["baseline_mean"])
            a_val = float(row_data["ablation_mean"])
            ax.plot([n_val, a_val], [y_idx, y_idx], color="#94a3b8", linewidth=2.0, zorder=1)
            ax.scatter(n_val, y_idx, color="#2563eb", s=48, zorder=2)
            ax.scatter(a_val, y_idx, color="#dc2626", s=48, zorder=2)

        ax.set_yticks(y_values)
        ax.set_yticklabels(panel_metric_labels)
        ax.set_xlim(0, 1)
        ax.set_title(model, fontsize=13)
        ax.grid(axis="x", linestyle="--", alpha=0.32)

    for idx in range(n_models, nrows * ncols):
        r = idx // ncols
        c = idx % ncols
        axes[r][c].axis("off")

    handles = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#2563eb", markersize=8, label="正常流程"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#dc2626", markersize=8, label="消融流程"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 0.02))
    fig.suptitle("消融前后评分对比（分模型哑铃图）", fontsize=18, y=0.99)
    plt.tight_layout(rect=[0.0, 0.06, 1.0, 0.97])
    save_figure_bundle(fig, output_path, dpi=240)
    plt.close(fig)


def plot_center_panel_dumbbell(calc_df: pd.DataFrame, metric_keys: list[str], output_path: Path) -> None:
    present_centers = [c for c in CENTER_CN.keys() if c in set(calc_df["center"])]
    if not present_centers:
        raise RuntimeError("分中心哑铃图无可用中心。")

    n_centers = len(present_centers)
    ncols = 3
    nrows = ceil(n_centers / ncols)
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(7.1 * ncols, 4.7 * nrows), squeeze=False)

    panel_metric_keys = [k for k in PANEL_METRIC_ORDER if k in metric_keys]
    panel_metric_labels = [METRIC_LABEL_MAP[k] for k in panel_metric_keys]
    y_values = list(range(len(panel_metric_keys)))

    for idx, center in enumerate(present_centers):
        r = idx // ncols
        c = idx % ncols
        ax = axes[r][c]
        center_df = calc_df[calc_df["center"] == center].copy()
        center_df["metric_order"] = center_df["metric_key"].map({k: i for i, k in enumerate(panel_metric_keys)})
        center_df = center_df.sort_values("metric_order").reset_index(drop=True)

        value_map = {row["metric_key"]: row for _, row in center_df.iterrows()}
        for y_idx, metric_key in enumerate(panel_metric_keys):
            row_data = value_map.get(metric_key)
            if row_data is None:
                continue
            n_val = float(row_data["baseline_mean"])
            a_val = float(row_data["ablation_mean"])
            ax.plot([n_val, a_val], [y_idx, y_idx], color="#94a3b8", linewidth=2.0, zorder=1)
            ax.scatter(n_val, y_idx, color="#2563eb", s=48, zorder=2)
            ax.scatter(a_val, y_idx, color="#dc2626", s=48, zorder=2)

        ax.set_yticks(y_values)
        ax.set_yticklabels(panel_metric_labels)
        ax.set_xlim(0, 1)
        ax.set_title(CENTER_CN.get(center, center), fontsize=13)
        ax.grid(axis="x", linestyle="--", alpha=0.32)

    for idx in range(n_centers, nrows * ncols):
        r = idx // ncols
        c = idx % ncols
        axes[r][c].axis("off")

    handles = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#2563eb", markersize=8, label="正常流程"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#dc2626", markersize=8, label="消融流程"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 0.02))
    fig.suptitle("消融前后评分对比（分中心哑铃图）", fontsize=18, y=0.99)
    plt.tight_layout(rect=[0.0, 0.06, 1.0, 0.97])
    save_figure_bundle(fig, output_path, dpi=240)
    plt.close(fig)


def build_center_heatmap_tables(
    pair_df: pd.DataFrame,
    metric_keys: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    detail_df = pair_df[pair_df["paired_flag"] & pair_df["metric_key"].isin(metric_keys)].copy()
    calc_df = (
        detail_df.groupby(["center", "metric_key", "metric_label"], as_index=False)
        .agg(
            paired_n=("delta_score", "size"),
            baseline_mean=("baseline_score", "mean"),
            ablation_mean=("ablation_score", "mean"),
            delta_mean=("delta_score", "mean"),
            delta_std=("delta_score", "std"),
            delta_median=("delta_score", "median"),
        )
        .reset_index(drop=True)
    )
    calc_df["center_order"] = calc_df["center"].map({name: i for i, name in enumerate(CENTER_CN.keys())}).fillna(999)
    calc_df["metric_order"] = calc_df["metric_key"].map({key: idx for idx, key in enumerate(METRIC_ORDER)}).fillna(999)
    calc_df = calc_df.sort_values(["center_order", "metric_order"]).reset_index(drop=True)

    summary_df = (
        calc_df.pivot_table(index=["center"], columns="metric_label", values="delta_mean", aggfunc="first")
        .reset_index()
    )
    summary_df["计算口径"] = "同中心内按病例-模型-指标配对后，聚合差值(消融-正常)"
    return detail_df, calc_df, summary_df


def plot_center_heatmap(calc_df: pd.DataFrame, metric_keys: list[str], output_path: Path) -> None:
    pivot_df = (
        calc_df.pivot_table(index="center", columns="metric_key", values="delta_mean", aggfunc="first")
        .reindex(index=[c for c in CENTER_CN.keys() if c in set(calc_df["center"])], columns=metric_keys)
    )
    if pivot_df.empty:
        raise RuntimeError("中心热力图无可用数据。")
    pivot_df = pivot_df.rename(index=CENTER_CN, columns=METRIC_LABEL_MAP)

    fig, ax = plt.subplots(figsize=(12.2, 4.8))
    sns.heatmap(
        pivot_df,
        annot=True,
        fmt=".3f",
        cmap="RdBu_r",
        center=0.0,
        cbar_kws={"label": "平均分变化（消融 - 正常）"},
        linewidths=0.6,
        linecolor="#e2e8f0",
        ax=ax,
    )
    ax.set_xlabel("指标")
    ax.set_ylabel("中心")
    ax.set_title("分中心的消融影响热力图（同病例同模型配对）")
    plt.tight_layout()
    save_figure_bundle(fig, output_path, dpi=240)
    plt.close(fig)


def to_cn_detail(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "center",
        "case_id",
        "model",
        "model_short",
        "run_label",
        "stage",
        "metric_type",
        "metric_label",
        "baseline_score",
        "ablation_score",
        "delta_score",
        "paired_flag",
        "baseline_status",
        "ablation_status",
        "ablation_run_label",
        "baseline_source_file",
        "ablation_source_file",
    ]
    out = df[cols].copy()
    out = out.rename(
        columns={
            "center": "中心",
            "case_id": "病例ID",
            "model": "模型",
            "model_short": "模型简称",
            "run_label": "轨迹来源run_label",
            "stage": "阶段",
            "metric_type": "指标类型",
            "metric_label": "指标",
            "baseline_score": "正常流程得分",
            "ablation_score": "消融流程得分",
            "delta_score": "差值_消融减正常",
            "paired_flag": "是否配对样本",
            "baseline_status": "正常流程状态",
            "ablation_status": "消融流程状态",
            "ablation_run_label": "消融结果run_label",
            "baseline_source_file": "正常流程来源文件",
            "ablation_source_file": "消融流程来源文件",
        }
    )
    out["是否配对样本"] = out["是否配对样本"].map(lambda x: "是" if bool(x) else "否")
    return out


def to_cn_calc_dumbbell(df: pd.DataFrame) -> pd.DataFrame:
    out = df[
        ["metric_label", "paired_n", "baseline_mean", "ablation_mean", "delta_mean", "delta_median", "delta_std"]
    ].copy()
    out = out.rename(
        columns={
            "metric_label": "指标",
            "paired_n": "配对样本数",
            "baseline_mean": "正常流程均值",
            "ablation_mean": "消融流程均值",
            "delta_mean": "差值均值_消融减正常",
            "delta_median": "差值中位数_消融减正常",
            "delta_std": "差值标准差_消融减正常",
        }
    )
    return out


def to_cn_calc_bar(df: pd.DataFrame) -> pd.DataFrame:
    out = df[
        ["model", "model_short", "metric_label", "paired_n", "baseline_mean", "ablation_mean", "delta_mean", "delta_std", "delta_median"]
    ].copy()
    out = out.rename(
        columns={
            "model": "模型",
            "model_short": "模型简称",
            "metric_label": "指标",
            "paired_n": "配对样本数",
            "baseline_mean": "正常流程均值",
            "ablation_mean": "消融流程均值",
            "delta_mean": "差值均值_消融减正常",
            "delta_std": "差值标准差_消融减正常",
            "delta_median": "差值中位数_消融减正常",
        }
    )
    return out


def to_cn_calc_center(df: pd.DataFrame) -> pd.DataFrame:
    out = df[
        ["center", "metric_label", "paired_n", "baseline_mean", "ablation_mean", "delta_mean", "delta_std", "delta_median"]
    ].copy()
    out["center"] = out["center"].map(CENTER_CN).fillna(out["center"])
    out = out.rename(
        columns={
            "center": "中心",
            "metric_label": "指标",
            "paired_n": "配对样本数",
            "baseline_mean": "正常流程均值",
            "ablation_mean": "消融流程均值",
            "delta_mean": "差值均值_消融减正常",
            "delta_std": "差值标准差_消融减正常",
            "delta_median": "差值中位数_消融减正常",
        }
    )
    return out


def to_cn_summary(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rename_map = {
        "metric_key": "指标键",
        "metric_label": "指标",
        "paired_n": "配对样本数",
        "baseline_mean": "正常流程均值",
        "ablation_mean": "消融流程均值",
        "delta_mean": "差值均值_消融减正常",
        "delta_std": "差值标准差_消融减正常",
        "delta_median": "差值中位数_消融减正常",
        "计算口径": "计算口径",
    }
    out = out.rename(columns={k: v for k, v in rename_map.items() if k in out.columns})
    return out


def write_source_workbook(
    out_path: Path,
    detail_df: pd.DataFrame,
    calc_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    detail_sheet: str,
    calc_sheet: str,
    summary_sheet: str,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        detail_df.to_excel(writer, sheet_name=detail_sheet, index=False)
        calc_df.to_excel(writer, sheet_name=calc_sheet, index=False)
        summary_df.to_excel(writer, sheet_name=summary_sheet, index=False)


def write_multi_sheet_workbook(out_path: Path, sheets: list[tuple[str, pd.DataFrame]]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for sheet_name, df in sheets:
            safe_sheet = str(sheet_name)[:31]
            df.to_excel(writer, sheet_name=safe_sheet, index=False)


def parse_center_run_labels(center_run_label_args: list[str] | None) -> dict[str, str]:
    if not center_run_label_args:
        return {}
    mapping: dict[str, str] = {}
    for item in center_run_label_args:
        text = str(item or "").strip()
        if "=" not in text:
            raise ValueError(f"--center-run-label 参数格式错误，应为 center=run_label: {item}")
        center, run_label = text.split("=", 1)
        center = center.strip()
        run_label = run_label.strip()
        if not center or not run_label:
            raise ValueError(f"--center-run-label 参数缺少 center 或 run_label: {item}")
        mapping[center] = run_label
    return mapping


def clean_source_data_dir(src_dir: Path, keep_name: str | None = None) -> None:
    if not src_dir.exists():
        return
    for path in src_dir.iterdir():
        if path.is_dir():
            continue
        if keep_name and path.name == keep_name:
            continue
        try:
            path.unlink()
        except Exception as exc:
            logger.warning("清理旧 source data 文件失败: %s | %s", path, exc)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build supplementary ablation figures/source data from baseline judge-agent + no-check ablation outputs."
    )
    parser.add_argument("--run-label", default="smoke15_20260411_45t_v4_xingchen_fixd1", help="消融实验 run_label（单run模式）")
    parser.add_argument("--run-labels", nargs="+", default=[], help="多个 run_label 合并模式（同轨迹保留较新的 run）")
    parser.add_argument("--all-runs", action="store_true", help="自动扫描并合并 output_ablation_no_check_d3 下全部可用 run")
    parser.add_argument(
        "--center-run-label",
        action="append",
        default=[],
        help="按中心指定run_label，格式 center=run_label，可重复传入。如 Foshan=xxx",
    )
    parser.add_argument("--exclude-runs", nargs="+", default=[], help="与 --all-runs 搭配，排除指定 run_label")
    parser.add_argument("--auto-eval-root", type=str, default=str(DEFAULT_AUTO_EVAL_ROOT), help="自动测评系统项目根目录")
    parser.add_argument("--supp-root", type=str, default=str(DEFAULT_SUPP_ROOT), help="补充材料输出目录")
    parser.add_argument("--models", nargs="+", default=MODEL_ORDER, help="模型列表")
    parser.add_argument(
        "--metric-scope",
        choices=["all", "diag"],
        default="all",
        help="绘图指标范围：all=诊断+方案，diag=仅D1/D2/D3诊断",
    )
    parser.add_argument("--source-excel-name", type=str, default="ablation_source_all_in_one_v1.xlsx", help="单一source data工作簿文件名")
    parser.add_argument("--clean-source-dir", action="store_true", help="输出前清理 source_data 目录中的旧文件")
    parser.add_argument("--dumbbell-only", action="store_true", help="仅输出总体/分模型/分中心三张哑铃图")
    args = parser.parse_args()

    auto_eval_root = Path(args.auto_eval_root).resolve()
    supp_root = Path(args.supp_root).resolve()
    fig_dir = supp_root / "figures"
    src_dir = supp_root / "source_data"
    fig_dir.mkdir(parents=True, exist_ok=True)
    src_dir.mkdir(parents=True, exist_ok=True)

    center_run_map = parse_center_run_labels(args.center_run_label)
    run_mode = "single"
    run_labels_used: list[str] = []
    if center_run_map:
        run_mode = "center"
        tracks_df = load_selected_tracks_by_center(auto_eval_root, center_run_map, args.models)
        run_labels_used = sorted(set(center_run_map.values()))
    elif args.run_labels:
        run_mode = "multi"
        run_labels_used = [str(x).strip() for x in args.run_labels if str(x).strip()]
        tracks_df = load_selected_tracks_multi(auto_eval_root, run_labels_used, args.models)
    elif args.all_runs:
        run_mode = "all"
        run_labels_used = discover_run_labels(auto_eval_root, exclude_runs=args.exclude_runs)
        if not run_labels_used:
            raise RuntimeError("未发现可用 run_label，请检查 output_ablation_no_check_d3 目录。")
        tracks_df = load_selected_tracks_multi(auto_eval_root, run_labels_used, args.models)
    else:
        tracks_df = load_selected_tracks(auto_eval_root, args.run_label, args.models)
        centers_auto = sorted(set(tracks_df["center"].astype(str).tolist()))
        center_run_map = {center: args.run_label for center in centers_auto}
        run_labels_used = [args.run_label]

    centers = sorted(tracks_df["center"].astype(str).unique().tolist())
    logger.info("selected_tracks: n=%s, centers=%s, run_mode=%s", len(tracks_df), centers, run_mode)
    logger.info("run_labels_used: %s", run_labels_used)
    if center_run_map:
        logger.info("center->run_label: %s", center_run_map)

    baseline_df = load_baseline_scores(ROOT, tracks_df)
    if baseline_df.empty:
        raise RuntimeError("未读取到 baseline judge-agent 分数，请检查 data/*/judge agent 目录与文件名。")
    ablation_df = load_ablation_scores(auto_eval_root, tracks_df)
    pair_df = build_pair_detail(tracks_df, baseline_df, ablation_df)
    available_metric_keys = get_plot_metric_keys(pair_df)
    plot_metric_keys = resolve_metric_scope_keys(available_metric_keys, args.metric_scope)
    logger.info("用于绘图的指标范围=%s: %s", args.metric_scope, [METRIC_LABEL_MAP[k] for k in plot_metric_keys])

    detail_dumbbell, calc_dumbbell, summary_dumbbell = build_dumbbell_tables(pair_df, plot_metric_keys)
    detail_bar, calc_bar, summary_bar = build_bar_tables(pair_df, plot_metric_keys)
    detail_panel, calc_panel, summary_panel = build_panel_tables(pair_df, plot_metric_keys)
    detail_center, calc_center, summary_center = build_center_heatmap_tables(pair_df, plot_metric_keys)
    detail_center_panel, calc_center_panel, summary_center_panel = build_center_panel_tables(pair_df, plot_metric_keys)

    if args.clean_source_dir:
        clean_source_data_dir(src_dir)

    if args.dumbbell_only:
        dumbbell_fig = fig_dir / "ablation_dumbbell_overall_v2.png"
        model_dumbbell_fig = fig_dir / "ablation_dumbbell_by_model_v2.png"
        center_dumbbell_fig = fig_dir / "ablation_dumbbell_by_center_v2.png"
        plot_dumbbell(calc_dumbbell, dumbbell_fig)
        plot_model_panel_dumbbell(calc_panel, plot_metric_keys, model_dumbbell_fig)
        plot_center_panel_dumbbell(calc_center_panel, plot_metric_keys, center_dumbbell_fig)
    else:
        dumbbell_fig = fig_dir / "ablation_score_delta_dumbbell_v1.png"
        bar_fig = fig_dir / "ablation_score_delta_bar_by_model_v1.png"
        panel_fig = fig_dir / "ablation_score_compare_by_model_panel_v1.png"
        center_heatmap_fig = fig_dir / "ablation_score_delta_center_heatmap_v1.png"
        plot_dumbbell(calc_dumbbell, dumbbell_fig)
        plot_delta_bar(calc_bar, plot_metric_keys, bar_fig)
        plot_model_panel_dumbbell(calc_panel, plot_metric_keys, panel_fig)
        plot_center_heatmap(calc_center, plot_metric_keys, center_heatmap_fig)

    coverage = (
        pair_df.groupby(["metric_key", "metric_label"], as_index=False)
        .agg(
            total_rows=("pair_key", "size"),
            baseline_non_null=("baseline_score", lambda s: int(s.notna().sum())),
            ablation_non_null=("ablation_score", lambda s: int(s.notna().sum())),
            paired_non_null=("paired_flag", lambda s: int(s.sum())),
        )
        .reset_index(drop=True)
    )
    coverage["metric_order"] = coverage["metric_key"].map({key: idx for idx, key in enumerate(METRIC_ORDER)})
    coverage = coverage.sort_values("metric_order").reset_index(drop=True)
    coverage_cn = coverage.rename(
        columns={
            "metric_key": "指标键",
            "metric_label": "指标",
            "total_rows": "总记录数",
            "baseline_non_null": "正常流程非空数",
            "ablation_non_null": "消融流程非空数",
            "paired_non_null": "配对非空数",
        }
    )
    coverage_cn = coverage_cn.copy()
    if center_run_map:
        coverage_cn["run_label映射"] = json.dumps(center_run_map, ensure_ascii=False)
    else:
        coverage_cn["run_label映射"] = "；".join(sorted(set(tracks_df["run_label"].astype(str))))

    run_info = (
        tracks_df.groupby(["run_label", "center"], as_index=False)
        .agg(
            去重后保留轨迹数=("case_id_norm", "size"),
            病例组数=("case_id_norm", "nunique"),
            模型数=("model", "nunique"),
        )
        .reset_index(drop=True)
    )
    run_info["center"] = run_info["center"].map(CENTER_CN).fillna(run_info["center"])
    run_info = run_info.rename(columns={"run_label": "run_label", "center": "中心"})
    run_info["说明"] = "同中心同病例同模型同指标配对后比较（消融-正常）"

    source_book_path = src_dir / args.source_excel_name
    if args.dumbbell_only:
        write_multi_sheet_workbook(
            source_book_path,
            [
                ("运行信息", run_info),
                ("图1_明细_总体哑铃", to_cn_detail(detail_dumbbell)),
                ("图1_计算_总体哑铃", to_cn_calc_dumbbell(calc_dumbbell)),
                ("图1_汇总_总体哑铃", to_cn_summary(summary_dumbbell)),
                ("图2_明细_分模型哑铃", to_cn_detail(detail_panel)),
                ("图2_计算_分模型哑铃", to_cn_calc_bar(calc_panel)),
                ("图2_汇总_分模型哑铃", to_cn_summary(summary_panel)),
                ("图3_明细_分中心哑铃", to_cn_detail(detail_center_panel)),
                ("图3_计算_分中心哑铃", to_cn_calc_center(calc_center_panel)),
                ("图3_汇总_分中心哑铃", to_cn_summary(summary_center_panel)),
                ("覆盖率汇总", coverage_cn),
            ],
        )
        logger.info(
            "ablation supplementary figures written (dumbbell only): %s | %s | %s",
            dumbbell_fig,
            model_dumbbell_fig,
            center_dumbbell_fig,
        )
    else:
        write_multi_sheet_workbook(
            source_book_path,
            [
                ("运行信息", run_info),
                ("图A_明细", to_cn_detail(detail_dumbbell)),
                ("图A_计算", to_cn_calc_dumbbell(calc_dumbbell)),
                ("图A_汇总", to_cn_summary(summary_dumbbell)),
                ("图B_明细", to_cn_detail(detail_bar)),
                ("图B_计算", to_cn_calc_bar(calc_bar)),
                ("图B_汇总", to_cn_summary(summary_bar)),
                ("图C_明细", to_cn_detail(detail_panel)),
                ("图C_计算", to_cn_calc_bar(calc_panel)),
                ("图C_汇总", to_cn_summary(summary_panel)),
                ("图D_明细", to_cn_detail(detail_center)),
                ("图D_计算", to_cn_calc_center(calc_center)),
                ("图D_汇总", to_cn_summary(summary_center)),
                ("覆盖率汇总", coverage_cn),
            ],
        )
        logger.info(
            "ablation supplementary figures written: %s | %s | %s | %s",
            dumbbell_fig,
            bar_fig,
            panel_fig,
            center_heatmap_fig,
        )
    logger.info("ablation supplementary source data written: %s", source_book_path)


if __name__ == "__main__":
    main()
