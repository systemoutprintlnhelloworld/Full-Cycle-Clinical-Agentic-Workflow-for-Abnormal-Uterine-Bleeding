from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

sns.set_style("whitegrid")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

METRIC_SPECS = [
    ("d1_diag", "D1 诊断"),
    ("d1_plan", "D1 方案"),
    ("d2_diag", "D2 诊断"),
    ("d2_plan", "D2 术前方案"),
    ("d3_diag", "D3 诊断"),
    ("d3_plan", "D3 术后方案"),
]


def normalize_case_id(case_id: str) -> str:
    return str(case_id).strip().lower().replace("-", "_")


def extract_case_id_from_excel_name(file_name: str, model: str) -> str | None:
    prefix = f"{model}_None_"
    suffix = ".xlsx"
    if not file_name.startswith(prefix) or not file_name.endswith(suffix):
        return None
    return file_name[len(prefix) : -len(suffix)]


def find_normal_excel_path(repo_root: Path, center: str, model: str, case_id: str) -> Path:
    output_root = repo_root / "output"
    default_path = output_root / center / model / "single_excels" / f"{model}_None_{case_id}.xlsx"
    if not output_root.exists():
        return default_path

    center_key = center.strip().lower()
    case_key = normalize_case_id(case_id)
    matches: dict[str, tuple[int, float, Path]] = {}

    for center_dir in output_root.iterdir():
        if not center_dir.is_dir():
            continue
        name = center_dir.name.lower()
        if not (
            name == center_key
            or name.startswith(f"{center_key}-")
            or name.startswith(f"{center_key}_")
        ):
            continue

        single_excels_dir = center_dir / model / "single_excels"
        if not single_excels_dir.exists():
            continue

        for excel_path in single_excels_dir.glob(f"{model}_None_*.xlsx"):
            parsed_case = extract_case_id_from_excel_name(excel_path.name, model)
            if parsed_case is None:
                continue
            if normalize_case_id(parsed_case) != case_key:
                continue

            priority = 0
            if re.search(r"(^|[-_])v\d+($|[-_])", name):
                priority += 2
            if name == center_key:
                priority += 1
            if parsed_case == case_id:
                priority += 1
            try:
                mtime = excel_path.stat().st_mtime
            except OSError:
                mtime = 0.0
            matches[str(excel_path)] = (priority, mtime, excel_path)

    if matches:
        return sorted(matches.values(), key=lambda item: (item[0], item[1]), reverse=True)[0][2]
    return default_path


def safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        number = float(value)
        if pd.isna(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def read_single_cell_score(excel_path: Path, sheet_name: str, column_name: str) -> float | None:
    if not excel_path.exists():
        return None
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
    except Exception:
        return None
    if df.empty or column_name not in df.columns:
        return None
    return safe_float(df.iloc[0][column_name])


def read_single_row(excel_path: Path, sheet_name: str) -> dict:
    if not excel_path.exists():
        return {}
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
    except Exception:
        return {}
    if df.empty:
        return {}
    return df.iloc[0].to_dict()


def parse_json_obj(value) -> dict:
    if not isinstance(value, str) or not value.strip():
        return {}
    text = value.strip()
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def score_from_nested_json(payload: dict, section_keys: list[str]) -> float | None:
    for key in section_keys:
        section = payload.get(key)
        if isinstance(section, dict):
            score = safe_float(section.get("评分"))
            if score is not None:
                return score
    return None


def load_normal_scores(repo_root: Path, center: str, model: str, case_id: str) -> dict:
    excel_path = find_normal_excel_path(repo_root, center, model, case_id)
    d1_row = read_single_row(excel_path, "门诊决策")
    d2_row = read_single_row(excel_path, "入院决策")
    d3_row = read_single_row(excel_path, "手术决策")

    d1_gate_json = parse_json_obj(d1_row.get("Gate原始JSON"))
    d2_gate_json = parse_json_obj(d2_row.get("Gate原始JSON"))
    d3_gate_json = parse_json_obj(d3_row.get("Gate原始JSON"))

    d1_diag = safe_float(d1_row.get("Gate诊断分"))
    if d1_diag is None:
        d1_diag = score_from_nested_json(d1_gate_json, ["诊断匹配"])

    d1_plan = safe_float(d1_row.get("Gate检查分"))
    if d1_plan is None:
        d1_plan = score_from_nested_json(d1_gate_json, ["检查匹配"])

    d2_diag = safe_float(d2_row.get("Gate诊断分"))
    if d2_diag is None:
        d2_diag = score_from_nested_json(d2_gate_json, ["修正诊断匹配", "诊断匹配评估", "诊断匹配"])

    d2_plan = safe_float(d2_row.get("Gate手术分"))
    if d2_plan is None:
        d2_plan = score_from_nested_json(d2_gate_json, ["手术方案匹配", "手术匹配", "治疗方案匹配评估", "治疗方案匹配"])

    d3_diag = safe_float(d3_row.get("诊断得分"))
    if d3_diag is None:
        d3_diag = score_from_nested_json(d3_gate_json, ["诊断匹配评估", "诊断匹配"])

    d3_plan = safe_float(d3_row.get("方案得分"))
    if d3_plan is None:
        d3_plan = score_from_nested_json(d3_gate_json, ["治疗方案匹配评估", "治疗方案匹配", "手术方案匹配", "方案匹配"])

    return {
        "d1_diag": d1_diag,
        "d1_plan": d1_plan,
        "d2_diag": d2_diag,
        "d2_plan": d2_plan,
        "d3_diag": d3_diag,
        "d3_plan": d3_plan,
        "normal_excel_path": str(excel_path),
    }


def load_ablation_scores(run_root: Path, center: str, model: str, case_id: str) -> dict:
    per_case_path = run_root / "outputs" / center / model / "per_case_json" / f"{model}_{center}_{case_id}.json"
    if not per_case_path.exists():
        return {
            "d1_diag": None,
            "d1_plan": None,
            "d2_diag": None,
            "d2_plan": None,
            "d3_diag": None,
            "d3_plan": None,
            "ablation_status": "missing",
            "ablation_json_path": str(per_case_path),
        }

    with per_case_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    case_result = payload.get("case_result", {})
    stages = case_result.get("stages", {}) or {}

    def stage_score(stage_name: str, section_name: str) -> float | None:
        judge = (stages.get(stage_name) or {}).get("judge") or {}
        section = judge.get(section_name) or {}
        return safe_float(section.get("评分"))

    return {
        "d1_diag": stage_score("D1", "诊断匹配评估"),
        "d1_plan": stage_score("D1", "治疗方案匹配评估"),
        "d2_diag": stage_score("D2", "诊断匹配评估"),
        "d2_plan": stage_score("D2", "治疗方案匹配评估"),
        "d3_diag": stage_score("D3", "诊断匹配评估"),
        "d3_plan": stage_score("D3", "治疗方案匹配评估"),
        "ablation_status": case_result.get("status", "unknown"),
        "ablation_json_path": str(per_case_path),
    }


def build_pair_dataframe(repo_root: Path, run_root: Path, models: list[str]) -> pd.DataFrame:
    selected_cases = pd.read_csv(run_root / "selected_cases.csv", encoding="utf-8-sig")
    rows = []
    for _, case in selected_cases.iterrows():
        center = str(case["center"])
        case_id = str(case["case_id"])
        for model in models:
            normal = load_normal_scores(repo_root, center, model, case_id)
            ablation = load_ablation_scores(run_root, center, model, case_id)
            row = {
                "center": center,
                "case_id": case_id,
                "model": model,
                "ablation_status": ablation.get("ablation_status"),
                "normal_excel_path": normal.get("normal_excel_path"),
                "ablation_json_path": ablation.get("ablation_json_path"),
            }
            for metric_key, _ in METRIC_SPECS:
                row[f"normal_{metric_key}"] = normal.get(metric_key)
                row[f"ablation_{metric_key}"] = ablation.get(metric_key)
                n_val = row[f"normal_{metric_key}"]
                a_val = row[f"ablation_{metric_key}"]
                row[f"delta_{metric_key}"] = None if n_val is None or a_val is None else a_val - n_val
            rows.append(row)
    return pd.DataFrame(rows)


def build_mean_long(pair_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for metric_key, metric_label in METRIC_SPECS:
        n_col = f"normal_{metric_key}"
        a_col = f"ablation_{metric_key}"
        for condition, col in (("正常流程", n_col), ("消融流程", a_col)):
            series = pd.to_numeric(pair_df[col], errors="coerce")
            rows.append(
                {
                    "metric_key": metric_key,
                    "metric_label": metric_label,
                    "condition": condition,
                    "mean_score": series.mean(),
                    "count": int(series.notna().sum()),
                }
            )
    return pd.DataFrame(rows)


def build_mean_delta_by_model(pair_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for model, group in pair_df.groupby("model"):
        for metric_key, metric_label in METRIC_SPECS:
            delta_col = f"delta_{metric_key}"
            series = pd.to_numeric(group[delta_col], errors="coerce")
            rows.append(
                {
                    "model": model,
                    "metric_key": metric_key,
                    "metric_label": metric_label,
                    "mean_delta": series.mean(),
                    "count": int(series.notna().sum()),
                }
            )
    return pd.DataFrame(rows)


def build_metric_coverage(pair_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for metric_key, metric_label in METRIC_SPECS:
        n_col = f"normal_{metric_key}"
        a_col = f"ablation_{metric_key}"
        normal_series = pd.to_numeric(pair_df[n_col], errors="coerce")
        ablation_series = pd.to_numeric(pair_df[a_col], errors="coerce")
        paired_series = normal_series.notna() & ablation_series.notna()
        rows.append(
            {
                "metric_key": metric_key,
                "metric_label": metric_label,
                "total_rows": int(len(pair_df)),
                "normal_non_null": int(normal_series.notna().sum()),
                "ablation_non_null": int(ablation_series.notna().sum()),
                "paired_non_null": int(paired_series.sum()),
            }
        )
    return pd.DataFrame(rows)


def plot_dumbbell_overall(mean_long_df: pd.DataFrame, output_path: Path) -> None:
    pivot = mean_long_df.pivot(index="metric_label", columns="condition", values="mean_score").reset_index()
    pivot = pivot.set_index("metric_label").loc[[label for _, label in METRIC_SPECS]].reset_index()

    fig, ax = plt.subplots(figsize=(10, 5.5))
    y_positions = range(len(pivot))
    for idx, row in pivot.iterrows():
        n_val = row.get("正常流程")
        a_val = row.get("消融流程")
        if pd.isna(n_val) or pd.isna(a_val):
            continue
        ax.plot([n_val, a_val], [idx, idx], color="#9ca3af", linewidth=2, zorder=1)
        ax.scatter(n_val, idx, color="#2563eb", s=58, zorder=2)
        ax.scatter(a_val, idx, color="#dc2626", s=58, zorder=2)
        ax.text(a_val + 0.01, idx, f"{(a_val - n_val):+.2f}", va="center", fontsize=9, color="#374151")

    ax.set_yticks(list(y_positions))
    ax.set_yticklabels(pivot["metric_label"])
    ax.set_xlim(0, 1)
    ax.set_xlabel("平均评分")
    ax.set_title("消融前后评分对比（总体哑铃图）")
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.scatter([], [], color="#2563eb", label="正常流程")
    ax.scatter([], [], color="#dc2626", label="消融流程")
    ax.legend(loc="lower right")
    plt.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def plot_dumbbell_by_model(pair_df: pd.DataFrame, output_path: Path) -> None:
    models = sorted(pair_df["model"].dropna().unique().tolist())
    ncols = 3
    nrows = (len(models) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(14, 3.8 * nrows), sharex=True)
    axes = axes.flatten()

    for ax in axes[len(models) :]:
        ax.axis("off")

    for i, model in enumerate(models):
        ax = axes[i]
        sub = pair_df[pair_df["model"] == model]
        data = []
        for metric_key, metric_label in METRIC_SPECS:
            n_series = pd.to_numeric(sub[f"normal_{metric_key}"], errors="coerce")
            a_series = pd.to_numeric(sub[f"ablation_{metric_key}"], errors="coerce")
            data.append(
                {
                    "metric_label": metric_label,
                    "normal_mean": n_series.mean(),
                    "ablation_mean": a_series.mean(),
                }
            )
        metric_df = pd.DataFrame(data).set_index("metric_label").loc[[label for _, label in METRIC_SPECS]].reset_index()
        for y, row in metric_df.iterrows():
            n_val = row["normal_mean"]
            a_val = row["ablation_mean"]
            if pd.isna(n_val) or pd.isna(a_val):
                continue
            ax.plot([n_val, a_val], [y, y], color="#9ca3af", linewidth=1.8)
            ax.scatter(n_val, y, color="#2563eb", s=38)
            ax.scatter(a_val, y, color="#dc2626", s=38)
        ax.set_yticks(range(len(metric_df)))
        ax.set_yticklabels(metric_df["metric_label"], fontsize=9)
        ax.set_xlim(0, 1)
        ax.set_title(model, fontsize=10)
        ax.grid(axis="x", linestyle="--", alpha=0.3)

    fig.suptitle("消融前后评分对比（分模型哑铃图）", fontsize=14, y=0.995)
    handles = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#2563eb", markersize=8, label="正常流程"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#dc2626", markersize=8, label="消融流程"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.005))
    plt.tight_layout(rect=[0, 0.03, 1, 0.98])
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def plot_delta_bar_overall(mean_delta_df: pd.DataFrame, output_path: Path) -> None:
    overall = mean_delta_df.groupby(["metric_key", "metric_label"], as_index=False)["mean_delta"].mean()
    overall = overall.set_index("metric_label").loc[[label for _, label in METRIC_SPECS]].reset_index()

    fig, ax = plt.subplots(figsize=(10, 5.2))
    colors = ["#16a34a" if val >= 0 else "#dc2626" for val in overall["mean_delta"].fillna(0)]
    ax.bar(overall["metric_label"], overall["mean_delta"], color=colors, alpha=0.9)
    ax.axhline(0, color="#6b7280", linewidth=1)
    for i, val in enumerate(overall["mean_delta"]):
        if pd.isna(val):
            continue
        va = "bottom" if val >= 0 else "top"
        offset = 0.01 if val >= 0 else -0.01
        ax.text(i, val + offset, f"{val:+.2f}", ha="center", va=va, fontsize=9)
    ax.set_ylabel("平均分变化（消融 - 正常）")
    ax.set_title("消融带来的评分增减（总体柱状图）")
    ax.tick_params(axis="x", rotation=15)
    plt.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def plot_delta_bar_by_model(mean_delta_df: pd.DataFrame, output_path: Path) -> None:
    plot_df = mean_delta_df.copy()
    plot_df["metric_label"] = pd.Categorical(plot_df["metric_label"], [label for _, label in METRIC_SPECS], ordered=True)
    plot_df = plot_df.sort_values(["metric_label", "model"])

    fig, ax = plt.subplots(figsize=(13.5, 6.2))
    sns.barplot(
        data=plot_df,
        x="metric_label",
        y="mean_delta",
        hue="model",
        ax=ax,
        palette="tab10",
    )
    ax.axhline(0, color="#6b7280", linewidth=1)
    ax.set_ylabel("平均分变化（消融 - 正常）")
    ax.set_xlabel("")
    ax.set_title("消融带来的评分增减（分模型柱状图）")
    ax.tick_params(axis="x", rotation=15)
    ax.legend(title="模型", loc="upper right")
    plt.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot ablation effect using existing judge scores only.")
    parser.add_argument("--repo-root", type=str, default=None, help="自动测评系统仓库根目录")
    parser.add_argument("--run-label", type=str, default="smoke15_20260410_03", help="消融实验 run_label")
    parser.add_argument(
        "--models",
        nargs="+",
        default=[
            "gemini-2.5-pro",
            "gpt-5-2025-08-07",
            "claude-opus-4-1-20250805-thinking",
            "deepseek-v3-1-think-250821",
            "grok-4",
        ],
        help="参与对比的模型",
    )
    args = parser.parse_args()

    if args.repo_root:
        repo_root = Path(args.repo_root).resolve()
    else:
        repo_root = Path(__file__).resolve().parents[2]
    run_root = repo_root / "output_ablation_no_check_d3" / args.run_label

    output_dir = run_root / "figures_ablation_effect"
    source_dir = run_root / "source_data_ablation_effect"
    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)

    pair_df = build_pair_dataframe(repo_root, run_root, args.models)
    mean_long_df = build_mean_long(pair_df)
    mean_delta_df = build_mean_delta_by_model(pair_df)
    coverage_df = build_metric_coverage(pair_df)

    pair_df.to_csv(source_dir / "ablation_vs_normal_pairs.csv", index=False, encoding="utf-8-sig")
    mean_long_df.to_csv(source_dir / "ablation_vs_normal_metric_means.csv", index=False, encoding="utf-8-sig")
    mean_delta_df.to_csv(source_dir / "ablation_vs_normal_metric_deltas_by_model.csv", index=False, encoding="utf-8-sig")
    coverage_df.to_csv(source_dir / "ablation_vs_normal_metric_coverage.csv", index=False, encoding="utf-8-sig")

    plot_dumbbell_overall(mean_long_df, output_dir / "ablation_dumbbell_overall.png")
    plot_dumbbell_by_model(pair_df, output_dir / "ablation_dumbbell_by_model.png")
    plot_delta_bar_overall(mean_delta_df, output_dir / "ablation_delta_bar_overall.png")
    plot_delta_bar_by_model(mean_delta_df, output_dir / "ablation_delta_bar_by_model.png")

    logger.info("Source data saved to: %s", source_dir)
    logger.info("Figures saved to: %s", output_dir)


if __name__ == "__main__":
    main()
