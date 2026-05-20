from __future__ import annotations

import ast
import json
import math
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from matplotlib.ticker import PercentFormatter

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.build_doctor_review_report import (  # noqa: E402
    _build_flow_case_detail,
    _build_gate3_fail_map,
    _build_judge_scores,
    _build_special_case_map,
    _load_doctor_scores,
)


MODEL_ORDER = [
    "claude-opus-4-1-20250805-thinking",
    "deepseek-v3-1-think-250821",
    "gemini-2.5-pro",
    "gpt-5-2025-08-07",
    "grok-4",
]
CENTER_ORDER = ["佛山", "武汉", "新疆"]
CENTER_LABELS = {"佛山": "Foshan", "武汉": "Wuhan", "新疆": "Xinjiang"}

STAGE_KEYS = ["D1_Loop", "D1_Decision", "D2_Loop", "D2_Decision", "D3_Decision", "D4_Plan"]
STAGE_CN_ORDER = ["门诊A", "门诊B", "住院A", "住院B", "术后", "康复"]
STAGE_KEY_TO_CN = {
    "D1_Loop": "D1循环",
    "D1_Decision": "D1决策",
    "D2_Loop": "D2循环",
    "D2_Decision": "D2决策",
    "D3_Decision": "D3决策",
    "D4_Plan": "D4康复",
}
STAGE_KEY_TO_SHORT = {
    "D1_Loop": "门诊A",
    "D1_Decision": "门诊B",
    "D2_Loop": "住院A",
    "D2_Decision": "住院B",
    "D3_Decision": "术后",
    "D4_Plan": "康复",
}
STAGE_SHORT_TO_KEY = {v: k for k, v in STAGE_KEY_TO_SHORT.items()}


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _model_order(values: pd.Series | list[str]) -> list[str]:
    if isinstance(values, pd.Series):
        seen = list(dict.fromkeys(values.dropna().astype(str).tolist()))
    else:
        seen = list(dict.fromkeys([str(v) for v in values if str(v)]))
    ordered = [m for m in MODEL_ORDER if m in seen]
    ordered.extend([m for m in seen if m not in ordered])
    return ordered


def _center_order(values: pd.Series | list[str]) -> list[str]:
    if isinstance(values, pd.Series):
        seen = list(dict.fromkeys(values.dropna().astype(str).tolist()))
    else:
        seen = list(dict.fromkeys([str(v) for v in values if str(v)]))
    ordered = [c for c in CENTER_ORDER if c in seen]
    ordered.extend([c for c in seen if c not in ordered])
    return ordered


def _slugify(text: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", str(text).strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "item"


def _safe_sheet_name(name: str, used: set[str]) -> str:
    cleaned = re.sub(r"[\\/*?:\[\]]", "_", name)
    cleaned = cleaned[:31] if len(cleaned) > 31 else cleaned
    if cleaned not in used:
        used.add(cleaned)
        return cleaned
    i = 2
    while True:
        suffix = f"_{i}"
        base = cleaned[: 31 - len(suffix)]
        cand = f"{base}{suffix}"
        if cand not in used:
            used.add(cand)
            return cand
        i += 1


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _dense_rank_desc(values: pd.Series) -> pd.Series:
    return values.rank(method="dense", ascending=False).astype("Int64")


def _write_source_data(out_dir: Path, prefix: str, sheets: dict[str, pd.DataFrame], meta: dict[str, Any]) -> Path:
    source_dir = out_dir / "source_data"
    _ensure_dir(source_dir)
    out_path = source_dir / f"{prefix}_source.xlsx"

    def _extract_sources(meta_dict: dict[str, Any]) -> pd.DataFrame:
        rows: list[dict[str, str]] = []
        explicit = meta_dict.get("data_sources")
        if explicit:
            if isinstance(explicit, (list, tuple)):
                for item in explicit:
                    rows.append({"路径": str(item), "说明": "显式指定"})
            else:
                for item in str(explicit).split("\n"):
                    if item.strip():
                        rows.append({"路径": item.strip(), "说明": "显式指定"})
        for key in ["data_root", "doctor_root", "doctor_report", "summary_xlsx", "llm_xlsx", "llm_small_xlsx"]:
            if key in meta_dict and meta_dict[key]:
                rows.append({"路径": str(meta_dict[key]), "说明": f"meta:{key}"})
        if not rows:
            rows.append({"路径": "未提供（请补充数据源路径）", "说明": "placeholder"})
        return pd.DataFrame(rows)

    used: set[str] = set()
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        meta_df = pd.DataFrame({"Key": list(meta.keys()), "Value": [str(v) for v in meta.values()]})
        meta_df.to_excel(writer, sheet_name=_safe_sheet_name("作图说明", used), index=False)

        sources_df = _extract_sources(meta)
        sources_df.to_excel(writer, sheet_name=_safe_sheet_name("数据来源", used), index=False)

        # canonical sheets
        raw_df = None
        for key in ["raw", "raw_round_points", "raw_cat", "raw_points", "raw_detail"]:
            if key in sheets:
                raw_df = sheets.get(key)
                break
        calc_df = None
        for key in ["calc", "bin_summary", "stage_rank", "stage_agg", "all_stage_agg", "case_points", "stage_long"]:
            if key in sheets:
                calc_df = sheets.get(key)
                break
        summary_df = None
        for key in ["plot_data", "agg", "pivot", "summary", "combined"]:
            if key in sheets:
                summary_df = sheets.get(key)
                break

        if isinstance(raw_df, pd.DataFrame):
            raw_df.to_excel(writer, sheet_name=_safe_sheet_name("原始明细", used), index=False)
        else:
            pd.DataFrame({"说明": ["未提供原始明细（请补充原始数据来源）"]}).to_excel(
                writer, sheet_name=_safe_sheet_name("原始明细", used), index=False
            )
        if isinstance(calc_df, pd.DataFrame):
            calc_df.to_excel(writer, sheet_name=_safe_sheet_name("计算过程", used), index=False)
        else:
            pd.DataFrame({"说明": ["无额外计算过程（直接汇总/作图）"]}).to_excel(
                writer, sheet_name=_safe_sheet_name("计算过程", used), index=False
            )
        if isinstance(summary_df, pd.DataFrame):
            summary_df.to_excel(writer, sheet_name=_safe_sheet_name("汇总作图", used), index=False)

        # write remaining sheets for traceability
        for name, df in sheets.items():
            if df is None:
                continue
            if not isinstance(df, pd.DataFrame):
                try:
                    df = pd.DataFrame(df)
                except Exception:
                    continue
            if name in {"raw", "raw_round_points", "raw_cat", "raw_points", "raw_detail"}:
                continue
            if name in {"calc", "bin_summary", "stage_rank", "stage_agg", "all_stage_agg", "case_points", "stage_long"}:
                continue
            if name in {"plot_data", "agg", "pivot", "summary", "combined"}:
                continue
            df.to_excel(writer, sheet_name=_safe_sheet_name(name, used), index=False)
    return out_path


def _organize_figures(out_dir: Path) -> None:
    def _target_folder(file_name: str) -> Path | None:
        name = str(file_name)
        if name.startswith("algorithmic_"):
            return Path("algorithmic")
        if name.startswith("alignment_") or name.startswith("manual_"):
            return Path("alignment")
        if name.startswith("consistency_"):
            return Path("consistency")
        if name.startswith("calibration_"):
            return Path("calibration")
        if name.startswith("sankey_"):
            return Path("sankey")
        if name.startswith("d2_decision_review_breakdown") or name.startswith("d3_decision_review_breakdown"):
            return Path("algorithmic")
        if name.startswith("special_"):
            return Path("special")
        if name.startswith("llm_small_"):
            return Path("llm") / "small" / "summary"
        if name.startswith("llm_memory_"):
            return Path("llm") / "full" / "memory"
        if name.startswith("llm_consistency_"):
            return Path("llm") / "full" / "consistency"
        if name.startswith("llm_reasoning_") or name.startswith("llm_rationale_"):
            return Path("llm") / "full" / "reasoning"
        if name.startswith("llm_"):
            return Path("llm") / "full" / "general"
        return None

    fixed_dirs = [
        Path("algorithmic"),
        Path("alignment"),
        Path("consistency"),
        Path("calibration"),
        Path("sankey"),
        Path("special"),
        Path("llm") / "full" / "general",
        Path("llm") / "full" / "reasoning",
        Path("llm") / "full" / "memory",
        Path("llm") / "full" / "consistency",
        Path("llm") / "small" / "summary",
    ]
    for folder in fixed_dirs:
        _ensure_dir(out_dir / folder)

    # 1) ????????????
    for file in out_dir.glob("*.png"):
        target_rel = _target_folder(file.name)
        if target_rel is None:
            continue
        target = out_dir / target_rel / file.name
        _ensure_dir(target.parent)
        if target.exists():
            target.unlink()
        file.replace(target)

    # 2) ??? source_data ???????????? source_data
    global_source = out_dir / "source_data"
    if global_source.exists():
        for src_file in global_source.glob("*.xlsx"):
            target_rel = _target_folder(src_file.name)
            if target_rel is None:
                continue
            dest_dir = out_dir / target_rel / "source_data"
            _ensure_dir(dest_dir)
            dest_path = dest_dir / src_file.name
            if dest_path.exists():
                dest_path.unlink()
            shutil.move(str(src_file), str(dest_path))

        try:
            if not any(global_source.iterdir()):
                global_source.rmdir()
        except Exception:
            pass


def _save_image_grid(
    image_paths: list[Path],
    out_path: Path,
    title: str | None = None,
    labels: list[str] | None = None,
    ncols: int = 3,
) -> None:
    if not image_paths:
        return
    from PIL import Image, ImageDraw

    images: list[Image.Image] = []
    for path in image_paths:
        if not path.exists():
            continue
        try:
            images.append(Image.open(path).convert("RGB"))
        except Exception:
            continue
    if not images:
        return

    ncols = max(1, min(ncols, len(images)))
    nrows = math.ceil(len(images) / ncols)
    tile_w = max(img.width for img in images)
    tile_h = max(img.height for img in images)
    margin = 36
    header_h = 82 if title else 36
    canvas_w = margin * 2 + tile_w * ncols
    canvas_h = margin * 2 + header_h + tile_h * nrows
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    if title:
        draw.text((margin, 16), title, fill=(20, 20, 20))

    for idx, img in enumerate(images):
        r = idx // ncols
        c = idx % ncols
        x = margin + c * tile_w
        y = margin + header_h + r * tile_h
        if img.size != (tile_w, tile_h):
            img = img.resize((tile_w, tile_h))
        canvas.paste(img, (x, y))
        if labels and idx < len(labels):
            draw.text((x + 8, y + 6), labels[idx], fill=(30, 30, 30))

    canvas.save(out_path, dpi=(1200, 1200))


def _build_flow_case_table(data_root: Path, doctor_report: Path) -> pd.DataFrame:
    # Prefer rebuilding from data_root to keep per-case minimal classes up-to-date.
    raw = _build_flow_case_detail(data_root)
    if not raw.empty:
        df = raw.rename(columns={"中心": "Center", "模型名称": "Model", "病例ID": "CaseID"})
    else:
        df = pd.DataFrame()
        if doctor_report.exists():
            try:
                df = pd.read_excel(doctor_report, sheet_name="通过退出明细", engine="openpyxl")
            except Exception:
                df = pd.DataFrame()
        if df.empty:
            return pd.DataFrame(columns=["Center", "Model", "CaseID", *STAGE_KEYS])
        df = df.rename(columns={"中心": "Center", "模型名称": "Model", "病例ID": "CaseID"})

    for col in STAGE_KEYS:
        if col not in df.columns:
            df[col] = ""
    keep = ["Center", "Model", "CaseID", *STAGE_KEYS]
    df = df.loc[:, [c for c in keep if c in df.columns]].copy()
    df["Center"] = df["Center"].astype(str)
    df["Model"] = df["Model"].astype(str)
    df["CaseID"] = df["CaseID"].astype(str)
    return df.sort_values(["Center", "Model", "CaseID"], kind="mergesort").reset_index(drop=True)


def _compute_special_case_counts(data_root: Path, doctor_report: Path | None = None) -> pd.DataFrame:
    special_map = _build_special_case_map(data_root)
    flow_df = pd.DataFrame()
    if doctor_report is not None and doctor_report.exists():
        flow_df = _build_flow_case_table(data_root, doctor_report)
    rows: list[dict[str, Any]] = []
    for (center, model), ids in sorted(special_map.items()):
        total = 0
        if not flow_df.empty:
            total = int(flow_df[(flow_df["Center"] == center) & (flow_df["Model"] == model)]["CaseID"].nunique())
        rows.append(
            {
                "Center": center,
                "Model": model,
                "Special D1 Cases": int(len(ids)),
                "Total Cases": total,
                "Special Rate": float(len(ids) / total) if total else np.nan,
            }
        )
    return pd.DataFrame(rows)


def _sort_flow_labels(stage_key: str, labels: list[str]) -> list[str]:
    def _score(label: str) -> tuple[int, str]:
        text = str(label)
        if "通过_1轮" in text:
            return (10, text)
        if "通过_2轮" in text:
            return (11, text)
        if "通过_3轮" in text:
            return (12, text)
        if "一审通过" in text or "通过一审" in text:
            return (20, text)
        if "通过二审" in text:
            return (30, text)
        if text.endswith("_通过") or "通过" in text:
            return (40, text)
        if "未经过" in text:
            return (70, text)
        if "D1特殊" in text:
            return (80, text)
        if "退出" in text or "不通过" in text or "未完成" in text or "已退出" in text:
            return (90, text)
        return (60, text)

    return sorted(labels, key=_score)


def _base_color(stage_idx: int) -> tuple[float, float, float]:
    palette = [
        (64 / 255, 139 / 255, 191 / 255),
        (88 / 255, 176 / 255, 120 / 255),
        (243 / 255, 156 / 255, 18 / 255),
        (231 / 255, 76 / 255, 60 / 255),
        (155 / 255, 89 / 255, 182 / 255),
        (26 / 255, 188 / 255, 156 / 255),
    ]
    return palette[stage_idx % len(palette)]


def _rgba(rgb: tuple[float, float, float], alpha: float = 0.85) -> str:
    r, g, b = [int(max(0, min(255, round(v * 255)))) for v in rgb]
    return f"rgba({r},{g},{b},{alpha:.3f})"


def _tint(rgb: tuple[float, float, float], ratio: float) -> tuple[float, float, float]:
    ratio = max(0.0, min(1.0, ratio))
    return tuple(v * (1.0 - ratio) + ratio for v in rgb)


def _build_sankey_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    total_cases = max(1, int(df["CaseID"].nunique()))
    nodes: list[dict[str, Any]] = []
    node_index: dict[tuple[str, str], int] = {}

    stage_details: dict[str, pd.DataFrame] = {}

    for s_idx, stage in enumerate(STAGE_KEYS):
        labels = [str(v) for v in df[stage].fillna("").astype(str).tolist() if str(v).strip()]
        unique = _sort_flow_labels(stage, list(dict.fromkeys(labels)))
        counts = df[stage].value_counts(dropna=False).to_dict()
        denom = max(1, len(unique) - 1)
        for i, label in enumerate(unique):
            count = int(counts.get(label, 0))
            pretty = label.split("_", 1)[1] if "_" in label else label
            display = f"{STAGE_KEY_TO_CN.get(stage, stage)}:{pretty}<br>{count} ({count / total_cases:.1%})"
            x = 0.02 + s_idx * (0.96 / max(1, len(STAGE_KEYS) - 1))
            y = 0.08 + i * (0.84 / max(1, denom))
            base = _base_color(s_idx)
            color = _rgba(_tint(base, 0.18 + 0.64 * (i / max(1, len(unique)))), 0.92)
            node_idx = len(nodes)
            node_index[(stage, label)] = node_idx
            nodes.append(
                {
                    "NodeIndex": node_idx,
                    "Label": display,
                    "RawLabel": label,
                    "Stage": stage,
                    "Category": pretty,
                    "Color": color,
                    "X": x,
                    "Y": y,
                    "Count": count,
                    "PctTotal": count / total_cases,
                }
            )

        stage_df = (
            df[["CaseID", stage]]
            .rename(columns={stage: "当前阶段最小类"})
            .assign(阶段=STAGE_KEY_TO_CN.get(stage, stage))
            .sort_values(["当前阶段最小类", "CaseID"], kind="mergesort")
        )
        stage_details[f"阶段明细_{STAGE_KEY_TO_CN.get(stage, stage)}"] = stage_df

    links: list[dict[str, Any]] = []
    for i in range(len(STAGE_KEYS) - 1):
        s1 = STAGE_KEYS[i]
        s2 = STAGE_KEYS[i + 1]
        pair = (
            df[[s1, s2]]
            .fillna("")
            .astype(str)
            .groupby([s1, s2], dropna=False)
            .size()
            .reset_index(name="Count")
        )
        from_totals = pair.groupby(s1)["Count"].sum().to_dict()
        for _, row in pair.iterrows():
            src_label = str(row[s1])
            tgt_label = str(row[s2])
            if not src_label or not tgt_label:
                continue
            src = node_index.get((s1, src_label))
            tgt = node_index.get((s2, tgt_label))
            if src is None or tgt is None:
                continue
            count = int(row["Count"])
            from_count = int(from_totals.get(src_label, count))
            pct = count / max(1, from_count)
            src_color = nodes[src]["Color"]
            src_color = src_color.replace("0.92", "0.35")
            links.append(
                {
                    "Source": src,
                    "Target": tgt,
                    "Value": count,
                    "FromStage": s1,
                    "ToStage": s2,
                    "SourceLabel": src_label,
                    "TargetLabel": tgt_label,
                    "FromCount": from_count,
                    "FromPct": pct,
                    "Color": src_color,
                }
            )

    nodes_df = pd.DataFrame(nodes)
    links_df = pd.DataFrame(links)
    return nodes_df, links_df, stage_details


def _plot_sankey_flow(flow_cases: pd.DataFrame, out_dir: Path) -> None:
    if flow_cases.empty:
        return
    sankey_dir = out_dir / "sankey"
    _ensure_dir(sankey_dir)

    image_paths: list[Path] = []

    for (center, model), subset in flow_cases.groupby(["Center", "Model"]):
        subset = subset.copy().sort_values("CaseID", kind="mergesort")
        nodes_df, links_df, stage_details = _build_sankey_data(subset)
        if nodes_df.empty or links_df.empty:
            continue

        hover = [
            f"{r.SourceLabel} -> {r.TargetLabel}<br>n={int(r.Value)}<br>share from source={float(r.FromPct):.1%}<br>source total={int(r.FromCount)}"
            for r in links_df.itertuples(index=False)
        ]

        fig = go.Figure(
            data=[
                go.Sankey(
                    arrangement="snap",
                    node=dict(
                        pad=12,
                        thickness=20,
                        line=dict(color="rgba(55,55,55,0.35)", width=0.6),
                        label=nodes_df["Label"].tolist(),
                        color=nodes_df["Color"].tolist(),
                        x=nodes_df["X"].tolist(),
                        y=nodes_df["Y"].tolist(),
                    ),
                    link=dict(
                        source=links_df["Source"].astype(int).tolist(),
                        target=links_df["Target"].astype(int).tolist(),
                        value=links_df["Value"].astype(float).tolist(),
                        color=links_df["Color"].tolist(),
                        customdata=hover,
                        hovertemplate="%{customdata}<extra></extra>",
                    ),
                )
            ]
        )
        fig.update_layout(
            title=f"Sankey Flow - {CENTER_LABELS.get(center, center)} / {model}<br><sup>Node label shows n and overall share</sup>",
            font=dict(size=13),
            width=2360,
            height=1500,
            margin=dict(l=24, r=24, t=88, b=24),
            paper_bgcolor="white",
            plot_bgcolor="white",
        )

        png_name = f"sankey_flow_{center}_{model}.png"
        out_png = sankey_dir / png_name
        fig.write_image(out_png, scale=2.8)
        image_paths.append(out_png)

        transitions = links_df[["FromStage", "ToStage", "SourceLabel", "TargetLabel", "Value", "FromCount", "FromPct"]].copy()
        transitions = transitions.rename(columns={"Value": "Count"})

        flow_summary_rows: list[dict[str, Any]] = []
        if "D1_Loop" in subset.columns:
            for d1_label, group in subset.groupby("D1_Loop", dropna=False):
                total = len(group)
                for stage in STAGE_KEYS:
                    counts = group[stage].value_counts(dropna=False)
                    for stage_label, cnt in counts.items():
                        flow_summary_rows.append(
                            {
                                "D1_Loop_Class": str(d1_label),
                                "Stage": stage,
                                "Stage_Class": str(stage_label),
                                "Count": int(cnt),
                                "PctWithinD1Loop": float(cnt / total) if total else np.nan,
                            }
                        )
        flow_summary = pd.DataFrame(flow_summary_rows)

        sheets: dict[str, pd.DataFrame] = {
            "raw": subset,
            "calc": transitions,
            "plot_data": flow_summary,
            "flow_cases": subset,
            "nodes": nodes_df,
            "links": links_df,
            "transitions": transitions,
            "flow_summary_by_d1_loop": flow_summary,
        }
        sheets.update(stage_details)
        _write_source_data(
            out_dir,
            f"sankey_flow_{center}_{model}",
            sheets,
            {
                "figure": png_name,
                "description": "Case-level 6-stage sankey flow",
                "center": center,
                "model": model,
                "cases": int(subset["CaseID"].nunique()),
                "stages": " -> ".join(STAGE_KEYS),
                "doctor_report": str((out_dir.parent / "summary" / "\u533b\u751f\u8bc4\u6d4b\u6c47\u603b.xlsx").resolve()),
            },
        )

    if not image_paths:
        return

    # ???????????????
    from PIL import Image, ImageDraw

    centers = _center_order(flow_cases["Center"])
    models = _model_order(flow_cases["Model"])
    tile_w, tile_h = 980, 620
    margin = 46
    header_h = 92
    canvas_w = margin * 2 + tile_w * len(models)
    canvas_h = margin * 2 + header_h + tile_h * len(centers)
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 16), "Sankey Grid (Center x Model)", fill=(20, 20, 20))
    draw.text((margin, 46), "Each node shows n and percentage of total cases in this center-model block", fill=(70, 70, 70))

    for r, center in enumerate(centers):
        for c, model in enumerate(models):
            path = sankey_dir / f"sankey_flow_{center}_{model}.png"
            x = margin + c * tile_w
            y = margin + header_h + r * tile_h
            if path.exists():
                img = Image.open(path).convert("RGB").resize((tile_w - 12, tile_h - 42))
                canvas.paste(img, (x + 6, y + 30))
            draw.text((x + 8, y + 6), f"{CENTER_LABELS.get(center, center)} | {model}", fill=(30, 30, 30))

    canvas.save(sankey_dir / "sankey_flow_grid.png", dpi=(1200, 1200))


def _extract_dual_tables(xlsx_path: Path, sheet_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None, engine="openpyxl")
    header_rows = [i for i, v in enumerate(raw.iloc[:, 0].astype(str)) if str(v).strip() == "中心"]
    if not header_rows:
        return pd.DataFrame(), pd.DataFrame()

    tables: list[pd.DataFrame] = []
    for idx, h in enumerate(header_rows):
        start = h + 1
        end = header_rows[idx + 1] - 1 if idx + 1 < len(header_rows) else len(raw)
        header = raw.iloc[h].tolist()
        data = raw.iloc[start:end].copy()
        data.columns = header
        data = data.dropna(how="all")
        data = data.loc[:, [c for c in data.columns if str(c).strip() and not str(c).startswith("Unnamed")]]
        if not data.empty:
            tables.append(data.reset_index(drop=True))

    if len(tables) == 1:
        return tables[0], pd.DataFrame()
    return tables[0], tables[1]


def _melt_alignment(df: pd.DataFrame, value_token: str, source_label: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Center", "Model", "Stage", "Value", "Source"])
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        center = str(row.get("中心", "")).strip()
        model = str(row.get("模型名称", "")).strip()
        if not center or not model:
            continue
        for stage in STAGE_CN_ORDER:
            col = f"{stage}_{value_token}"
            if col not in df.columns:
                continue
            val = _to_numeric(pd.Series([row.get(col)])).iloc[0]
            rows.append(
                {
                    "Center": center,
                    "Model": model,
                    "Stage": STAGE_SHORT_TO_KEY.get(stage, stage),
                    "Value": val,
                    "Source": source_label,
                }
            )
    return pd.DataFrame(rows)


def _plot_alignment_stagewise(
    long_df: pd.DataFrame,
    out_path: Path,
    title: str,
    meta_name: str,
    out_dir: Path,
    meta_extra: dict[str, Any] | None = None,
    style: str = "default",
    sources: list[tuple[str, str, str, float, float]] | None = None,
) -> None:
    if long_df.empty:
        return
    centers = _center_order(long_df["Center"])
    models = _model_order(long_df["Model"])
    stage_order = STAGE_KEYS
    stage_names = [STAGE_KEY_TO_SHORT[s] for s in stage_order]

    if style == "alt":
        palette = {m: plt.get_cmap("Set2")(i % 8) for i, m in enumerate(models)}
    else:
        palette = {m: plt.get_cmap("tab10")(i % 10) for i, m in enumerate(models)}

    source_specs = sources or [
        ("人工", "o", "-", 0.9, -0.03),
        ("Judge", "s", "--", 0.9, 0.03),
        ("LLM", "^", "--", 0.9, 0.03),
    ]

    image_paths: list[Path] = []
    labels: list[str] = []
    image_paths: list[Path] = []
    labels: list[str] = []
    for center in centers:
        center_df = long_df[long_df["Center"] == center].copy()
        if center_df.empty:
            continue

        # 阶段-来源内按模型排名（值越大排名越高）
        rank_df = center_df.copy()
        rank_df["Rank"] = (
            rank_df.groupby(["Stage", "Source"])["Value"].rank(method="dense", ascending=False).astype("Int64")
        )

        fig, axes = plt.subplots(1, len(models), figsize=(4.2 * len(models), 6.2), sharey=True)
        if len(models) == 1:
            axes = [axes]

        for ax, model in zip(axes, models):
            sub = rank_df[rank_df["Model"] == model]
            if sub.empty:
                ax.axis("off")
                continue

            base = palette[model]
            for s_idx, (source, marker, ls, alpha, offset) in enumerate(source_specs):
                ssub = sub[sub["Source"] == source].set_index("Stage").reindex(stage_order)
                if ssub["Value"].notna().sum() == 0:
                    continue
                if s_idx == 0:
                    color = base
                else:
                    color = tuple(max(0, min(1, c * 0.6)) for c in base[:3]) + (1.0,)
                x = np.arange(len(stage_order), dtype=float) + offset
                y = ssub["Value"].astype(float).to_numpy()
                ax.plot(x, y, marker=marker, linestyle=ls, linewidth=1.6, markersize=4.5, color=color, alpha=alpha, label=source)

                for i, (val, rk) in enumerate(zip(ssub["Value"].tolist(), ssub["Rank"].tolist())):
                    if pd.isna(val):
                        continue
                    txt = f"{val:.2f}\n#{int(rk)}" if not pd.isna(rk) else f"{val:.2f}"
                    ax.text(i + offset, float(val) + 0.03, txt, fontsize=7, ha="center", va="bottom", color=color)

            ax.set_title(model, fontsize=9)
            ax.set_xticks(np.arange(len(stage_order)))
            ax.set_xticklabels(stage_names, rotation=25)
            ax.grid(axis="y", linestyle="--", alpha=0.25)

        vals = rank_df["Value"].dropna().to_numpy()
        if vals.size:
            ymin = max(0.0, float(vals.min() - 0.35))
            ymax = float(vals.max() + 0.55)
            for ax in axes:
                ax.set_ylim(ymin, ymax)
        axes[0].set_ylabel("Score (0-5)")

        handles, labels = axes[0].get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="upper center", ncol=min(4, len(labels)), bbox_to_anchor=(0.5, 1.2))
        fig.suptitle(f"{title} - {CENTER_LABELS.get(center, center)}", y=1.24)
        fig.tight_layout(rect=(0, 0, 1, 0.72))

        center_path = out_path.parent / f"{out_path.stem}_{center}{out_path.suffix}"
        fig.savefig(center_path, dpi=320)
        plt.close(fig)
        image_paths.append(center_path)
        labels.append(CENTER_LABELS.get(center, center))

        meta = {
            "figure": center_path.name,
            "description": meta_name,
            "center": center,
            "stage_order": ",".join(stage_order),
        }
        if meta_extra:
            meta.update(meta_extra)
        _write_source_data(out_dir, f"{center_path.stem}", {"stage_long": center_df, "stage_rank": rank_df}, meta)

    if len(image_paths) > 1:
        grid_path = out_path.parent / f"{out_path.stem}_grid.png"
        _save_image_grid(image_paths, grid_path, title=title, labels=labels, ncols=len(image_paths))


def _plot_alignment_bars_stagewise(
    long_df: pd.DataFrame,
    out_path: Path,
    title: str,
    meta_name: str,
    out_dir: Path,
    meta_extra: dict[str, Any] | None = None,
    sources: tuple[str, str] = ("人工", "Judge"),
) -> None:
    if long_df.empty:
        return
    centers = _center_order(long_df["Center"])
    models = _model_order(long_df["Model"])
    stage_order = STAGE_KEYS
    stage_names = [STAGE_KEY_TO_SHORT[s] for s in stage_order]

    color_list = ["#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F", "#EDC949", "#B07AA1", "#FF9DA7"]
    palette = {m: color_list[i % len(color_list)] for i, m in enumerate(models)}

    image_paths: list[Path] = []
    labels: list[str] = []
    for center in centers:
        cdf = long_df[long_df["Center"] == center].copy()
        if cdf.empty:
            continue

        fig, axes = plt.subplots(2, 3, figsize=(15.8, 8.6))
        axes_flat = axes.flatten()

        for idx, stage in enumerate(stage_order):
            ax = axes_flat[idx]
            sdf = cdf[cdf["Stage"] == stage].copy()
            if sdf.empty:
                ax.text(0.5, 0.5, "NA", ha="center", va="center")
                ax.set_axis_off()
                continue

            pivot = sdf.pivot_table(index="Model", columns="Source", values="Value", aggfunc="mean").reindex(models)
            x = np.arange(len(models), dtype=float)
            width = 0.34

            ranks = {}
            for src in sources:
                if src in pivot.columns:
                    ranks[src] = pivot[src].rank(method="dense", ascending=False)

            for s_idx, src in enumerate(sources):
                if src not in pivot.columns:
                    continue
                vals = pivot[src].to_numpy(dtype=float)
                color = [palette[m] for m in models]
                if s_idx == 1:
                    # darker for the second source
                    darker = []
                    for m in models:
                        base_rgb = mcolors.to_rgb(palette[m])
                        darker.append(tuple(max(0, min(1, c * 0.6)) for c in base_rgb) + (1.0,))
                    color = darker
                bars = ax.bar(
                    x + (s_idx - 0.5) * width,
                    vals,
                    width=width,
                    color=color,
                    edgecolor="white",
                    linewidth=0.6,
                    label=src if idx == 0 else None,
                )
                for i, (b, v) in enumerate(zip(bars, vals)):
                    if np.isfinite(v):
                        rk = ranks.get(src)
                        rk_val = rk.iloc[i] if rk is not None else np.nan
                        txt = f"{v:.2f}" if pd.isna(rk_val) else f"{v:.2f}\n#{int(rk_val)}"
                        ax.text(
                            b.get_x() + b.get_width() / 2,
                            float(v) + 0.05,
                            txt,
                            ha="center",
                            va="bottom",
                            fontsize=7,
                        )

            ax.set_title(stage_names[idx])
            ax.set_xticks(x)
            ax.set_xticklabels(models, rotation=25, ha="right", fontsize=8)
            ax.set_ylim(0, 5)
            ax.grid(axis="y", linestyle=":", alpha=0.25)

        for j in range(len(stage_order), len(axes_flat)):
            axes_flat[j].axis("off")

        handles, labels = axes_flat[0].get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.02), fontsize=8)
        fig.suptitle(f"{title} - {CENTER_LABELS.get(center, center)}", y=1.06)
        fig.tight_layout(rect=(0, 0, 1, 0.9))

        center_path = out_path.parent / f"{out_path.stem}_{center}{out_path.suffix}"
        fig.savefig(center_path, dpi=420)
        plt.close(fig)
        image_paths.append(center_path)
        labels.append(CENTER_LABELS.get(center, center))

        meta = {
            "figure": center_path.name,
            "description": meta_name,
            "center": center,
            "stage_order": ",".join(stage_order),
            "sources": ",".join(sources),
        }
        if meta_extra:
            meta.update(meta_extra)
        _write_source_data(out_dir, f"{center_path.stem}", {"stage_long": cdf}, meta)

    if len(image_paths) > 1:
        grid_path = out_path.parent / f"{out_path.stem}_grid.png"
        _save_image_grid(image_paths, grid_path, title=title, labels=labels, ncols=len(image_paths))


def _plot_alignment(doctor_report: Path, out_dir: Path) -> None:
    if not doctor_report.exists():
        return
    align_dir = out_dir / "alignment"
    _ensure_dir(align_dir)

    result_manual, result_other = _extract_dual_tables(doctor_report, "人机对齐_结果质量")
    reason_manual, reason_other = _extract_dual_tables(doctor_report, "人机对齐_推理合理性")

    result_long = pd.concat(
        [
            _melt_alignment(result_manual, "结果质量评分_均值", "人工"),
            _melt_alignment(result_other, "Judge_综合评分_均值_x5", "Judge"),
        ],
        ignore_index=True,
    )
    reason_long = pd.concat(
        [
            _melt_alignment(reason_manual, "推理合理性_均值", "人工"),
            _melt_alignment(reason_other, "LLM推理质量_均值_x5", "LLM"),
        ],
        ignore_index=True,
    )

    if not result_long.empty:
        _plot_alignment_stagewise(
            result_long,
            align_dir / "alignment_result_quality_stagewise.png",
            "Manual vs Judge (Result Quality)",
            "人工结果质量 vs Judge综合评分（x5）",
            out_dir,
            meta_extra={"doctor_report": str(doctor_report)},
        )
        _plot_alignment_stagewise(
            result_long,
            align_dir / "alignment_result_quality_stagewise_alt.png",
            "Manual vs Judge (Result Quality)",
            "人工结果质量 vs Judge综合评分（x5）",
            out_dir,
            meta_extra={"doctor_report": str(doctor_report)},
            style="alt",
        )
        _plot_alignment_bars_stagewise(
            result_long,
            align_dir / "alignment_result_quality_stagewise_bars.png",
            "Manual vs Judge (Result Quality)",
            "人工结果质量 vs Judge综合评分（x5）",
            out_dir,
            meta_extra={"doctor_report": str(doctor_report)},
            sources=("人工", "Judge"),
        )
    if not reason_long.empty:
        _plot_alignment_stagewise(
            reason_long,
            align_dir / "alignment_reasoning_quality_stagewise.png",
            "Manual Reasoning vs LLM Reasoning",
            "人工推理合理性 vs LLM推理质量（x5）",
            out_dir,
            meta_extra={"doctor_report": str(doctor_report)},
        )
        _plot_alignment_stagewise(
            reason_long,
            align_dir / "alignment_reasoning_quality_stagewise_alt.png",
            "Manual Reasoning vs LLM Reasoning",
            "人工推理合理性 vs LLM推理质量（x5）",
            out_dir,
            meta_extra={"doctor_report": str(doctor_report)},
            style="alt",
        )
        _plot_alignment_bars_stagewise(
            reason_long,
            align_dir / "alignment_reasoning_quality_stagewise_bars.png",
            "Manual Reasoning vs LLM Reasoning",
            "人工推理合理性 vs LLM推理质量（x5）",
            out_dir,
            meta_extra={"doctor_report": str(doctor_report)},
            sources=("人工", "LLM"),
        )


def _plot_consistency_trend(
    long_df: pd.DataFrame,
    out_dir: Path,
    prefix: str,
    title: str,
    ylabel: str,
    meta_extra: dict[str, Any] | None = None,
    sources: list[tuple[str, str, str, float, float]] | None = None,
    invert_y: bool = False,
    raw_sources: dict[str, pd.DataFrame] | None = None,
) -> None:
    if long_df.empty:
        return
    cons_dir = out_dir / "consistency"
    _ensure_dir(cons_dir)
    centers = _center_order(long_df["Center"])
    models = _model_order(long_df["Model"])
    stage_order = STAGE_KEYS
    stage_names = [STAGE_KEY_TO_SHORT[s] for s in stage_order]

    palette = {m: plt.get_cmap("tab10")(i % 10) for i, m in enumerate(models)}
    source_specs = sources or [
        ("人工", "o", "-", 0.9, -0.03),
        ("LLM", "s", "--", 0.9, 0.03),
    ]

    image_paths: list[Path] = []
    labels: list[str] = []

    for center in centers:
        center_df = long_df[long_df["Center"] == center].copy()
        if center_df.empty:
            continue

        fig, axes = plt.subplots(1, len(models), figsize=(4.2 * len(models), 6.2), sharey=True)
        if len(models) == 1:
            axes = [axes]

        for ax, model in zip(axes, models):
            sub = center_df[center_df["Model"] == model]
            if sub.empty:
                ax.axis("off")
                continue
            base = palette[model]
            for s_idx, (source, marker, ls, alpha, offset) in enumerate(source_specs):
                ssub = sub[sub["Source"] == source].set_index("Stage").reindex(stage_order)
                if ssub["Value"].notna().sum() == 0:
                    continue
                color = base if s_idx == 0 else tuple(max(0, min(1, c * 0.6)) for c in base[:3]) + (1.0,)
                x = np.arange(len(stage_order), dtype=float) + offset
                y = ssub["Value"].astype(float).to_numpy()
                ax.plot(x, y, marker=marker, linestyle=ls, linewidth=1.7, markersize=4.6, color=color, alpha=alpha, label=source)
                for i, val in enumerate(y):
                    if not np.isfinite(val):
                        continue
                    ax.text(i + offset, float(val) + 0.05, f"{float(val):.2f}", fontsize=7, ha="center", va="bottom", color=color)

            ax.set_title(model, fontsize=9)
            ax.set_xticks(np.arange(len(stage_order)))
            ax.set_xticklabels(stage_names, rotation=25)
            ax.grid(axis="y", linestyle="--", alpha=0.25)

        vals = center_df["Value"].dropna().to_numpy()
        if vals.size:
            ymin = float(vals.min() - 0.4)
            ymax = float(vals.max() + 0.6)
            for ax in axes:
                ax.set_ylim(ymin, ymax)
        axes[0].set_ylabel(ylabel)
        if invert_y:
            for ax in axes:
                ax.invert_yaxis()

        handles, labels = axes[0].get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="upper center", ncol=min(4, len(labels)), bbox_to_anchor=(0.5, 1.18))
        fig.suptitle(f"{title} - {CENTER_LABELS.get(center, center)}", y=1.22)
        fig.tight_layout(rect=(0, 0, 1, 0.74))

        out_path = cons_dir / f"{prefix}_{center}.png"
        fig.savefig(out_path, dpi=420)
        plt.close(fig)

        image_paths.append(out_path)
        labels.append(CENTER_LABELS.get(center, center))

        sheets = {"raw": center_df}
        if raw_sources:
            for name, df in raw_sources.items():
                if df is None or df.empty:
                    continue
                if "Center" in df.columns:
                    sheets[name] = df[df["Center"] == center].copy()
                else:
                    sheets[name] = df.copy()

        meta = {
            "figure": out_path.name,
            "description": title,
            "center": center,
            "stage_order": ",".join(stage_order),
            "sources": ",".join([s[0] for s in source_specs]),
        }
        if meta_extra:
            meta.update(meta_extra)
        _write_source_data(out_dir, out_path.stem, sheets, meta)

    if len(image_paths) > 1:
        grid_path = cons_dir / f"{prefix}_grid.png"
        _save_image_grid(image_paths, grid_path, title=title, labels=labels, ncols=len(image_paths))
        grid_sheets = {"raw": long_df}
        if raw_sources:
            grid_sheets.update(raw_sources)
        _write_source_data(
            out_dir,
            f"{prefix}_grid",
            grid_sheets,
            {
                "figure": grid_path.name,
                "description": f"{title} (grid)",
                "stage_order": ",".join(stage_order),
                **(meta_extra or {}),
            },
        )


def _build_rank_case_data(doctor_root: Path, data_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = _load_doctor_scores(doctor_root)
    if raw.empty:
        return pd.DataFrame(), pd.DataFrame()

    gate3_fail = _build_gate3_fail_map(data_root)
    special_map = _build_special_case_map(data_root)
    special_triplets = {
        (center, model, cid)
        for (center, model), ids in special_map.items()
        for cid in ids
    }

    stage_map = {
        "门诊A": "D1_Loop",
        "门诊B": "D1_Decision",
        "住院A": "D2_Loop",
        "住院B": "D2_Decision",
        "术后": "D3_Decision",
        "康复": "D4_Plan",
    }

    rows_manual: list[dict[str, Any]] = []
    for _, r in raw.iterrows():
        center = str(r.get("中心", "")).strip()
        model = str(r.get("模型名称", "")).strip()
        case_id = str(r.get("病例ID", "")).strip()
        doctor = str(r.get("医生", "")).strip()
        if not center or not model or not case_id or not doctor:
            continue
        for stage_cn, stage_key in stage_map.items():
            col = f"{stage_cn}_结果质量评分"
            if col not in raw.columns:
                continue
            score = _to_numeric(pd.Series([r.get(col)])).iloc[0]
            if pd.isna(score):
                continue
            triplet = (center, model, case_id)
            if stage_key in {"D2_Loop", "D2_Decision"} and triplet in special_triplets:
                continue
            if stage_key == "D4_Plan" and triplet in gate3_fail:
                continue
            rows_manual.append(
                {
                    "Center": center,
                    "Model": model,
                    "CaseID": case_id,
                    "Doctor": doctor,
                    "Stage": stage_key,
                    "Score": float(score),
                }
            )

    manual_df = pd.DataFrame(rows_manual)

    judge = _build_judge_scores(data_root, gate3_fail=gate3_fail)
    rows_llm: list[dict[str, Any]] = []
    if not judge.empty:
        for _, r in judge.iterrows():
            center = str(r.get("中心", "")).strip()
            model = str(r.get("模型名称", "")).strip()
            case_id = str(r.get("病例ID", "")).strip()
            if not center or not model or not case_id:
                continue
            triplet = (center, model, case_id)
            for stage_cn, stage_key in stage_map.items():
                col = f"{stage_cn}_Judge_综合评分_x5"
                if col not in judge.columns:
                    continue
                score = _to_numeric(pd.Series([r.get(col)])).iloc[0]
                if pd.isna(score):
                    continue
                if stage_key in {"D2_Loop", "D2_Decision"} and triplet in special_triplets:
                    continue
                if stage_key == "D4_Plan" and triplet in gate3_fail:
                    continue
                rows_llm.append(
                    {
                        "Center": center,
                        "Model": model,
                        "CaseID": case_id,
                        "Stage": stage_key,
                        "Score": float(score),
                    }
                )
    llm_df = pd.DataFrame(rows_llm)
    return manual_df, llm_df


def _add_rank(df: pd.DataFrame, group_cols: list[str], score_col: str = "Score") -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["Rank"] = (
        out.groupby(group_cols)[score_col]
        .rank(method="dense", ascending=False)
        .astype("Int64")
    )
    return out


def _plot_rank_bubble(agg: pd.DataFrame, title: str, out_path: Path, use_counts: bool = True) -> None:
    fig, ax = plt.subplots(figsize=(5.2, 4.9))
    if agg.empty:
        ax.text(0.5, 0.5, "NA", ha="center", va="center", fontsize=14)
        ax.set_axis_off()
    else:
        ax.plot([1, 5], [1, 5], linestyle="--", color="gray", linewidth=1)
        if use_counts and "Count" in agg.columns:
            sizes = np.full(len(agg), 180.0, dtype=float)
            sc = ax.scatter(
                agg["RankA"],
                agg["RankB"],
                s=sizes,
                c=agg["Count"],
                cmap="YlGnBu",
                edgecolor="black",
                alpha=0.9,
            )
            for _, r in agg.iterrows():
                ax.text(float(r["RankA"]), float(r["RankB"]), str(int(r["Count"])), ha="center", va="center", fontsize=8)
            fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04, label="Count")
        else:
            ax.scatter(
                agg["RankA"],
                agg["RankB"],
                s=36.0,
                color="#4C72B0",
                alpha=0.25,
                edgecolor="none",
            )
        ax.set_xlim(0.5, 5.5)
        ax.set_ylim(0.5, 5.5)
        ax.set_xticks([1, 2, 3, 4, 5])
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.grid(linestyle=":", alpha=0.3)
        ax.set_aspect("equal", adjustable="box")
    ax.set_title(title)
    ax.set_xlabel("X Rank")
    ax.set_ylabel("Y Rank")
    fig.tight_layout()
    fig.savefig(out_path, dpi=320)
    plt.close(fig)


def _plot_confusion_matrices(doctor_root: Path, data_root: Path, out_dir: Path, run_id: str) -> None:
    # 兼容旧入口：这里改为排名一致性气泡散点
    manual_df, llm_df = _build_rank_case_data(doctor_root, data_root)
    if manual_df.empty or llm_df.empty:
        return

    cons_dir = out_dir / "consistency"
    _ensure_dir(cons_dir)

    # New: alignment-style trend charts (mean scores / mean ranks)
    manual_case = (
        manual_df.groupby(["Center", "Model", "Stage", "CaseID"], as_index=False)["Score"].mean(numeric_only=True)
    )
    manual_stage = (
        manual_case.groupby(["Center", "Model", "Stage"], as_index=False)["Score"].mean(numeric_only=True)
    ).rename(columns={"Score": "Value"})
    manual_stage["Source"] = "人工"
    llm_stage = (
        llm_df.groupby(["Center", "Model", "Stage"], as_index=False)["Score"].mean(numeric_only=True)
    ).rename(columns={"Score": "Value"})
    llm_stage["Source"] = "LLM"
    score_long = pd.concat([manual_stage, llm_stage], ignore_index=True)
    _plot_consistency_trend(
        score_long,
        out_dir,
        "consistency_score_alignment_style",
        "Consistency Trend (Manual vs LLM Score)",
        "Score (0-5)",
        meta_extra={"doctor_root": str(doctor_root), "data_root": str(data_root)},
        raw_sources={
            "manual_raw": manual_df,
            "llm_raw": llm_df,
            "manual_case_mean": manual_case,
            "manual_stage_mean": manual_stage,
            "llm_stage_mean": llm_stage,
        },
    )

    manual_rank = _add_rank(manual_df, ["Center", "Doctor", "Stage", "CaseID"])
    llm_rank = _add_rank(llm_df, ["Center", "Stage", "CaseID"])
    manual_rank_case = (
        manual_rank.groupby(["Center", "Model", "Stage", "CaseID"], as_index=False)["Rank"].mean(numeric_only=True)
    )
    manual_rank_stage = (
        manual_rank_case.groupby(["Center", "Model", "Stage"], as_index=False)["Rank"].mean(numeric_only=True)
    ).rename(columns={"Rank": "Value"})
    manual_rank_stage["Source"] = "人工"
    llm_rank_stage = (
        llm_rank.groupby(["Center", "Model", "Stage"], as_index=False)["Rank"].mean(numeric_only=True)
    ).rename(columns={"Rank": "Value"})
    llm_rank_stage["Source"] = "LLM"
    rank_long = pd.concat([manual_rank_stage, llm_rank_stage], ignore_index=True)
    _plot_consistency_trend(
        rank_long,
        out_dir,
        "consistency_rank_alignment_style",
        "Consistency Trend (Manual vs LLM Rank)",
        "Average Rank (1=best)",
        meta_extra={"doctor_root": str(doctor_root), "data_root": str(data_root)},
        invert_y=True,
        raw_sources={
            "manual_rank_raw": manual_rank,
            "llm_rank_raw": llm_rank,
            "manual_rank_case": manual_rank_case,
            "manual_rank_stage": manual_rank_stage,
            "llm_rank_stage": llm_rank_stage,
        },
    )

    # Keep one scatter-style backup (LLM vs first doctor per center)
    def _plot_score_scatter_all(merged: pd.DataFrame, x_col: str, y_col: str, title: str, out_path: Path) -> None:
        fig, ax = plt.subplots(figsize=(7.6, 7.6))
        if merged.empty:
            ax.text(0.5, 0.5, "NA", ha="center", va="center")
            ax.set_axis_off()
        else:
            ax.plot([0, 5], [0, 5], linestyle="--", color="gray", linewidth=1)
            x_vals = merged[x_col].astype(float).to_numpy()
            y_vals = merged[y_col].astype(float).to_numpy()
            ax.scatter(x_vals, y_vals, s=26.0, color="#2A6FBB", alpha=0.18, edgecolor="none")
            ax.set_xlim(-0.1, 5.1)
            ax.set_ylim(-0.1, 5.1)
            ax.set_xticks([0, 1, 2, 3, 4, 5])
            ax.set_yticks([0, 1, 2, 3, 4, 5])
            ax.set_aspect("equal", adjustable="box")
            ax.grid(linestyle=":", alpha=0.25)
        ax.set_xlabel("LLM")
        ax.set_ylabel("Doctor")
        ax.set_title(title)
        fig.tight_layout()
        fig.savefig(out_path, dpi=320)
        plt.close(fig)

    for center in _center_order(manual_rank["Center"]):
        c_manual = manual_rank[manual_rank["Center"] == center]
        c_llm = llm_rank[llm_rank["Center"] == center]
        doctors = sorted(c_manual["Doctor"].dropna().unique().tolist())
        if not doctors:
            continue
        doc = doctors[0]
        doc_rank = c_manual[c_manual["Doctor"] == doc][
            ["Center", "Stage", "CaseID", "Model", "Rank"]
        ].rename(columns={"Rank": "RankDoctor"})
        llm_rank_sub = c_llm[["Center", "Stage", "CaseID", "Model", "Rank"]].rename(columns={"Rank": "RankLLM"})
        merged_rank = llm_rank_sub.merge(doc_rank, on=["Center", "Stage", "CaseID", "Model"], how="inner")
        if not merged_rank.empty:
            agg = (
                merged_rank.groupby(["RankLLM", "RankDoctor"], as_index=False)
                .size()
                .rename(columns={"size": "Count"})
                .rename(columns={"RankLLM": "RankA", "RankDoctor": "RankB"})
            )
            _plot_rank_bubble(
                agg,
                f"Rank Bubble (LLM vs {doc}) - {CENTER_LABELS.get(center, center)}",
                cons_dir / f"consistency_rank_bubble_{center}_llm_vs_{_slugify(doc)}.png",
            )

        doc_score = manual_df[(manual_df["Center"] == center) & (manual_df["Doctor"] == doc)][
            ["Center", "Stage", "CaseID", "Model", "Score"]
        ].rename(columns={"Score": "ScoreDoctor"})
        llm_score = llm_df[llm_df["Center"] == center][
            ["Center", "Stage", "CaseID", "Model", "Score"]
        ].rename(columns={"Score": "ScoreLLM"})
        merged_score = llm_score.merge(doc_score, on=["Center", "Stage", "CaseID", "Model"], how="inner")
        _plot_score_scatter_all(
            merged_score,
            "ScoreLLM",
            "ScoreDoctor",
            f"Score Scatter (LLM vs {doc}) - {CENTER_LABELS.get(center, center)}",
            cons_dir / f"consistency_score_scatter_{center}_llm_vs_{_slugify(doc)}.png",
        )
        _write_source_data(
            out_dir,
            f"consistency_score_scatter_{center}_llm_vs_{_slugify(doc)}",
            {"raw": merged_score},
            {
                "figure": f"consistency_score_scatter_{center}_llm_vs_{_slugify(doc)}.png",
                "description": "Backup scatter (LLM vs first doctor)",
                "center": center,
                "doctor": doc,
                "doctor_root": str(doctor_root),
                "data_root": str(data_root),
            },
        )

    return

    manual_rank = _add_rank(manual_df, ["Center", "Doctor", "Stage", "CaseID"])
    llm_rank = _add_rank(llm_df, ["Center", "Stage", "CaseID"])

    def _jitter_values(values: pd.Series, ids: pd.Series | None, scale: float, salt: str) -> np.ndarray:
        vals = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float, copy=True)
        if ids is None or ids.empty:
            return vals
        base = ids.astype(str) + str(salt)
        hashed = pd.util.hash_pandas_object(base, index=False).astype("uint64").to_numpy()
        jitter = ((hashed % 1000) / 1000.0 - 0.5) * (2.0 * scale)
        mask = np.isfinite(vals)
        vals[mask] = np.clip(vals[mask] + jitter[mask], 0.0, 5.0)
        return vals

    def _plot_score_grid(merged: pd.DataFrame, x_col: str, y_col: str, title: str, out_path: Path) -> None:
        fig, axes = plt.subplots(2, 3, figsize=(14.5, 9.2))
        axes_flat = axes.flatten()
        for idx, stage in enumerate(STAGE_KEYS):
            ax = axes_flat[idx]
            sub = merged[merged["Stage"] == stage].copy()
            if sub.empty:
                ax.text(0.5, 0.5, "NA", ha="center", va="center")
                ax.set_axis_off()
                continue
            ax.plot([0, 5], [0, 5], linestyle="--", color="gray", linewidth=1)
            x_vals = sub[x_col].astype(float).to_numpy()
            y_vals = sub[y_col].astype(float).to_numpy()
            ax.scatter(
                x_vals,
                y_vals,
                s=28.0,
                color="#2A6FBB",
                alpha=0.18,
                edgecolor="none",
            )
            ax.set_title(STAGE_KEY_TO_SHORT.get(stage, stage))
            ax.set_xlim(-0.1, 5.1)
            ax.set_ylim(-0.1, 5.1)
            ax.set_xticks([0, 1, 2, 3, 4, 5])
            ax.set_yticks([0, 1, 2, 3, 4, 5])
            ax.set_aspect("equal", adjustable="box")
            ax.grid(linestyle=":", alpha=0.25)
        for j in range(len(STAGE_KEYS), len(axes_flat)):
            axes_flat[j].axis("off")
        fig.suptitle(title, y=0.99)
        fig.tight_layout(rect=(0, 0, 1, 0.97))
        fig.savefig(out_path, dpi=320)
        plt.close(fig)

    def _plot_score_scatter_all(merged: pd.DataFrame, x_col: str, y_col: str, title: str, out_path: Path) -> None:
        fig, ax = plt.subplots(figsize=(8.6, 8.6))
        if merged.empty:
            ax.text(0.5, 0.5, "NA", ha="center", va="center")
            ax.set_axis_off()
        else:
            ax.plot([0, 5], [0, 5], linestyle="--", color="gray", linewidth=1)
            x_vals = merged[x_col].astype(float).to_numpy()
            y_vals = merged[y_col].astype(float).to_numpy()
            ax.scatter(
                x_vals,
                y_vals,
                s=28.0,
                c="#2A6FBB",
                alpha=0.18,
                edgecolor="none",
            )
            ax.set_xlim(-0.1, 5.1)
            ax.set_ylim(-0.1, 5.1)
            ax.set_xticks([0, 1, 2, 3, 4, 5])
            ax.set_yticks([0, 1, 2, 3, 4, 5])
            ax.set_aspect("equal", adjustable="box")
            ax.grid(linestyle=":", alpha=0.25)
        ax.set_xlabel("X Score")
        ax.set_ylabel("Y Score")
        ax.set_title(title)
        fig.tight_layout()
        fig.savefig(out_path, dpi=420)
        plt.close(fig)

    for center in _center_order(manual_rank["Center"]):
        c_manual = manual_rank[manual_rank["Center"] == center]
        c_llm = llm_rank[llm_rank["Center"] == center]
        doctors = sorted(c_manual["Doctor"].dropna().unique().tolist())
        if not doctors:
            continue

        pairs: list[tuple[str, str, str, pd.DataFrame]] = []
        for doc in doctors[:2]:
            doc_df = c_manual[c_manual["Doctor"] == doc][["Center", "Stage", "CaseID", "Model", "Rank"]].rename(columns={"Rank": "RankDoctor"})
            llm_sub = c_llm[["Center", "Stage", "CaseID", "Model", "Rank"]].rename(columns={"Rank": "RankLLM"})
            merged = llm_sub.merge(doc_df, on=["Center", "Stage", "CaseID", "Model"], how="inner")
            pairs.append((f"LLM_vs_{doc}", "RankLLM", "RankDoctor", merged))

        if len(doctors) >= 2:
            d1 = c_manual[c_manual["Doctor"] == doctors[0]][["Center", "Stage", "CaseID", "Model", "Rank"]].rename(columns={"Rank": "RankA"})
            d2 = c_manual[c_manual["Doctor"] == doctors[1]][["Center", "Stage", "CaseID", "Model", "Rank"]].rename(columns={"Rank": "RankB"})
            merged = d1.merge(d2, on=["Center", "Stage", "CaseID", "Model"], how="inner")
            pairs.append((f"{doctors[0]}_vs_{doctors[1]}", "RankA", "RankB", merged))

        score_pairs: list[tuple[str, str, str, pd.DataFrame]] = []
        for doc in doctors[:2]:
            doc_score = manual_df[(manual_df["Center"] == center) & (manual_df["Doctor"] == doc)][
                ["Center", "Stage", "CaseID", "Model", "Score"]
            ].rename(columns={"Score": "ScoreDoctor"})
            llm_score = llm_df[llm_df["Center"] == center][
                ["Center", "Stage", "CaseID", "Model", "Score"]
            ].rename(columns={"Score": "ScoreLLM"})
            merged_score = llm_score.merge(doc_score, on=["Center", "Stage", "CaseID", "Model"], how="inner")
            score_pairs.append((f"LLM_vs_{doc}", "ScoreLLM", "ScoreDoctor", merged_score))

        if len(doctors) >= 2:
            d1_score = manual_df[(manual_df["Center"] == center) & (manual_df["Doctor"] == doctors[0])][
                ["Center", "Stage", "CaseID", "Model", "Score"]
            ].rename(columns={"Score": "ScoreA"})
            d2_score = manual_df[(manual_df["Center"] == center) & (manual_df["Doctor"] == doctors[1])][
                ["Center", "Stage", "CaseID", "Model", "Score"]
            ].rename(columns={"Score": "ScoreB"})
            merged_score = d1_score.merge(d2_score, on=["Center", "Stage", "CaseID", "Model"], how="inner")
            score_pairs.append((f"{doctors[0]}_vs_{doctors[1]}", "ScoreA", "ScoreB", merged_score))

        for pair_name, x_col, y_col, merged in pairs:
            if merged.empty:
                continue

            fig, axes = plt.subplots(2, 3, figsize=(14.5, 9.2))
            axes_flat = axes.flatten()

            stage_rows: list[pd.DataFrame] = []
            for idx, stage in enumerate(STAGE_KEYS):
                ax = axes_flat[idx]
                sub = merged[merged["Stage"] == stage].copy()
                if sub.empty:
                    ax.text(0.5, 0.5, "NA", ha="center", va="center")
                    ax.set_axis_off()
                    continue
                ax.plot([1, 5], [1, 5], linestyle="--", color="gray", linewidth=1)
                ax.scatter(
                    sub[x_col].astype(float),
                    sub[y_col].astype(float),
                    s=32.0,
                    color="#4C72B0",
                    alpha=0.25,
                    edgecolor="none",
                )
                ax.set_title(STAGE_KEY_TO_SHORT.get(stage, stage))
                ax.set_xlim(0.5, 5.5)
                ax.set_ylim(0.5, 5.5)
                ax.set_xticks([1, 2, 3, 4, 5])
                ax.set_yticks([1, 2, 3, 4, 5])
                ax.set_aspect("equal", adjustable="box")
                ax.grid(linestyle=":", alpha=0.25)
                stage_rows.append(sub)

            for j in range(len(STAGE_KEYS), len(axes_flat)):
                axes_flat[j].axis("off")

            x_name = pair_name.split("_vs_")[0]
            y_name = pair_name.split("_vs_")[1]
            fig.suptitle(f"Ranking Consistency Bubble - {CENTER_LABELS.get(center, center)} ({x_name} vs {y_name})", y=0.99)
            fig.tight_layout(rect=(0, 0, 1, 0.97))
            out_png = cons_dir / f"consistency_rank_bubble_{center}_{_slugify(pair_name)}.png"
            fig.savefig(out_png, dpi=320)
            plt.close(fig)

            all_stage = pd.concat(stage_rows, ignore_index=True) if stage_rows else pd.DataFrame()
            agg_all = (
                all_stage[[x_col, y_col]].rename(columns={x_col: "RankA", y_col: "RankB"})
                if not all_stage.empty
                else pd.DataFrame(columns=["RankA", "RankB"])
            )
            all_path = cons_dir / f"consistency_rank_bubble_{center}_{_slugify(pair_name)}_allstages.png"
            _plot_rank_bubble(
                agg_all,
                f"All Stages - {CENTER_LABELS.get(center, center)} ({x_name} vs {y_name})",
                all_path,
                use_counts=False,
            )

            stage_agg = (
                all_stage[["Stage", x_col, y_col]].rename(columns={x_col: "RankA", y_col: "RankB"})
                if not all_stage.empty
                else pd.DataFrame(columns=["Stage", "RankA", "RankB"])
            )
            fig2, ax2 = plt.subplots(figsize=(8.6, 8.6))
            if stage_agg.empty:
                ax2.text(0.5, 0.5, "NA", ha="center", va="center")
                ax2.set_axis_off()
            else:
                ax2.plot([1, 5], [1, 5], linestyle="--", color="gray", linewidth=1)
                ax2.scatter(
                    stage_agg["RankA"].astype(float).to_numpy(),
                    stage_agg["RankB"].astype(float).to_numpy(),
                    s=28.0,
                    c="#2A6FBB",
                    alpha=0.18,
                    edgecolor="none",
                )
                ax2.set_xlim(0.5, 5.5)
                ax2.set_ylim(0.5, 5.5)
                ax2.set_xticks([1, 2, 3, 4, 5])
                ax2.set_yticks([1, 2, 3, 4, 5])
                ax2.set_aspect("equal", adjustable="box")
                ax2.grid(linestyle=":", alpha=0.25)
                ax2.set_xlabel(x_name)
                ax2.set_ylabel(y_name)
                ax2.set_title(f"Rank Scatter (density) - {CENTER_LABELS.get(center, center)} ({x_name} vs {y_name})")
            fig2.tight_layout()
            scatter_path = cons_dir / f"consistency_rank_scatter_{center}_{_slugify(pair_name)}_allstages.png"
            fig2.savefig(scatter_path, dpi=420)
            plt.close(fig2)

            for score_name, sx, sy, merged_score in score_pairs:
                if merged_score.empty:
                    continue
                grid_path = cons_dir / f"consistency_score_grid_{center}_{_slugify(score_name)}.png"
                _plot_score_grid(
                    merged_score,
                    sx,
                    sy,
                    f"Score Consistency (by stage) - {CENTER_LABELS.get(center, center)} ({score_name})",
                    grid_path,
                )
                all_path = cons_dir / f"consistency_score_scatter_{center}_{_slugify(score_name)}_allstages.png"
                _plot_score_scatter_all(
                    merged_score,
                    sx,
                    sy,
                    f"Score Consistency (all stages) - {CENTER_LABELS.get(center, center)} ({score_name})",
                    all_path,
                )
                _write_source_data(
                    out_dir,
                    all_path.stem,
                    {"merged_score": merged_score},
                    {
                        "figure": all_path.name,
                        "alternate_figure": grid_path.name,
                        "description": "Score consistency scatter (one sample per point)",
                        "center": center,
                        "pair": score_name,
                        "run_id": run_id,
                        "doctor_root": str(doctor_root),
                        "data_root": str(data_root),
                    },
                )

            _write_source_data(
                out_dir,
                f"consistency_rank_bubble_{center}_{_slugify(pair_name)}",
                {
                    "merged_detail": merged,
                    "all_stage_agg": agg_all,
                    "stage_agg": stage_agg,
                },
                {
                    "figure": out_png.name,
                    "alternate_figure": scatter_path.name,
                    "description": "Rank consistency bubbles by case and stage",
                    "center": center,
                    "pair": pair_name,
                    "run_id": run_id,
                    "doctor_root": str(doctor_root),
                    "data_root": str(data_root),
                },
            )

        # alignment-style consistency (score + rank) using dual-line panels
        score_align = []
        if not manual_df.empty:
            manual_mean = (
                manual_df[manual_df["Center"] == center]
                .groupby(["Center", "Model", "Stage"], as_index=False)["Score"]
                .mean()
                .assign(Source="人工")
                .rename(columns={"Score": "Value"})
            )
            score_align.append(manual_mean)
        if not llm_df.empty:
            llm_mean = (
                llm_df[llm_df["Center"] == center]
                .groupby(["Center", "Model", "Stage"], as_index=False)["Score"]
                .mean()
                .assign(Source="LLM")
                .rename(columns={"Score": "Value"})
            )
            score_align.append(llm_mean)
        if score_align:
            score_long = pd.concat(score_align, ignore_index=True)
            _plot_alignment_stagewise(
                score_long,
                cons_dir / "consistency_score_alignment_style.png",
                "Consistency (Score) - LLM vs Doctor",
                "一致性-打分（LLM均值 vs 医生均值）",
                out_dir,
                meta_extra={"doctor_root": str(doctor_root), "data_root": str(data_root)},
            )

        rank_align = []
        if not manual_rank.empty:
            manual_rank_mean = (
                manual_rank[manual_rank["Center"] == center]
                .groupby(["Center", "Model", "Stage"], as_index=False)["Rank"]
                .mean()
                .assign(Source="人工")
                .rename(columns={"Rank": "Value"})
            )
            rank_align.append(manual_rank_mean)
        if not llm_rank.empty:
            llm_rank_mean = (
                llm_rank[llm_rank["Center"] == center]
                .groupby(["Center", "Model", "Stage"], as_index=False)["Rank"]
                .mean()
                .assign(Source="LLM")
                .rename(columns={"Rank": "Value"})
            )
            rank_align.append(llm_rank_mean)
        if rank_align:
            rank_long = pd.concat(rank_align, ignore_index=True)
            _plot_alignment_stagewise(
                rank_long,
                cons_dir / "consistency_rank_alignment_style.png",
                "Consistency (Rank) - LLM vs Doctor",
                "一致性-排名（LLM均值 vs 医生均值）",
                out_dir,
                meta_extra={"doctor_root": str(doctor_root), "data_root": str(data_root)},
            )


def _plot_stagewise_bars(
    df_long: pd.DataFrame,
    stage_keys: list[str],
    out_dir: Path,
    output_prefix: str,
    title_prefix: str,
    ylabel: str,
    value_col: str = "Value",
    ylim: tuple[float, float] | None = None,
) -> None:
    if df_long.empty:
        return

    for center in _center_order(df_long["Center"]):
        sub = df_long[df_long["Center"] == center].copy()
        if sub.empty:
            continue

        models = _model_order(sub["Model"])
        existing_stage = [s for s in stage_keys if s in set(sub["Stage"].astype(str).tolist())]
        if not existing_stage:
            existing_stage = list(dict.fromkeys(sub["Stage"].astype(str).tolist()))

        pivot = (
            sub.pivot_table(index="Model", columns="Stage", values=value_col, aggfunc="mean")
            .reindex(index=models)
            .reindex(columns=existing_stage)
        )

        fig, ax = plt.subplots(figsize=(9.8, 9.8))
        width = 0.11 if len(existing_stage) >= 6 else 0.16
        x = np.arange(len(models), dtype=float)
        model_palette = {m: plt.get_cmap("tab10")(i % 10) for i, m in enumerate(models)}

        for i, stage in enumerate(existing_stage):
            vals = pivot[stage].astype(float).to_numpy() if stage in pivot.columns else np.full(len(models), np.nan)
            pos = x + (i - (len(existing_stage) - 1) / 2) * width
            ratio = i / max(1, len(existing_stage) - 1)
            colors = [_tint(model_palette[m][:3], 0.58 - 0.46 * ratio) for m in models]

            # ???
            draw_vals = np.where(np.isnan(vals), 0.0, vals)
            bars = ax.bar(
                pos,
                draw_vals,
                width=width,
                color=colors,
                edgecolor="white",
                linewidth=0.5,
                label=STAGE_KEY_TO_SHORT.get(stage, stage),
            )

            # NA ????????????? 0
            for b, v in zip(bars, vals):
                cx = b.get_x() + b.get_width() / 2
                if np.isnan(v):
                    b.set_facecolor((0.92, 0.92, 0.92, 1.0))
                    b.set_edgecolor((0.55, 0.55, 0.55, 1.0))
                    b.set_hatch("///")
                    ax.text(cx, 0.01 if not ylim else ylim[0] + 0.01, "NA", ha="center", va="bottom", fontsize=7, color="#666666", rotation=90)
                else:
                    ax.text(cx, float(v) + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=7)

        ax.set_xticks(x)
        ax.set_xticklabels(models, rotation=24, ha="right")
        ax.set_ylabel(ylabel)
        ax.set_title(f"{title_prefix} - {CENTER_LABELS.get(center, center)}")
        ax.grid(axis="y", linestyle="--", alpha=0.24)
        if ylim:
            ax.set_ylim(*ylim)
        ax.legend(loc="upper right", fontsize=8, ncol=2)
        fig.tight_layout()

        path = out_dir / "calibration" / f"{output_prefix}_{center}.png"
        _ensure_dir(path.parent)
        fig.savefig(path, dpi=360)
        plt.close(fig)

        _write_source_data(
            out_dir,
            f"{output_prefix}_{center}",
            {"plot_data": pivot.reset_index(), "raw": sub},
            {
                "figure": path.name,
                "description": title_prefix,
                "center": center,
                "value_col": value_col,
                "stage_order": ",".join(existing_stage),
            },
        )


def _plot_calibration_reliability(points_df: pd.DataFrame, out_dir: Path, data_root: Path | None = None) -> None:
    if points_df.empty:
        return
    cal_dir = out_dir / "calibration"
    _ensure_dir(cal_dir)

    required_cols = {"Center", "Model", "CaseID", "Stage", "Category", "Confidence", "Accuracy"}
    if not required_cols.issubset(set(points_df.columns)):
        return

    case_points = (
        points_df.groupby(["Center", "Model", "CaseID", "Stage", "Category"], as_index=False)
        .agg(Confidence=("Confidence", "mean"), Accuracy=("Accuracy", "mean"))
    )

    category_cfg = {
        "diagnosis": {
            "title": "Diagnosis calibration bubbles",
            "stages": ["D1_Decision", "D2_Decision", "D3_Decision"],
            "filename": "calibration_bubble_diagnosis_stagewise_{center}.png",
        },
        "check": {
            "title": "Check calibration bubbles",
            "stages": ["D1_Loop", "D1_Decision", "D2_Loop"],
            "filename": "calibration_bubble_check_stagewise_{center}.png",
        },
        "plan": {
            "title": "Plan calibration bubbles",
            "stages": ["D2_Decision", "D3_Decision", "D4_Plan"],
            "filename": "calibration_bubble_plan_stagewise_{center}.png",
        },
        "overall": {
            "title": "Overall 6-stage calibration bubbles",
            "stages": STAGE_KEYS,
            "filename": "calibration_reliability_stagewise_{center}.png",
        },
    }

    for center in _center_order(case_points["Center"]):
        cdf = case_points[case_points["Center"] == center].copy()
        if cdf.empty:
            continue
        models = _model_order(cdf["Model"])

        for category, cfg in category_cfg.items():
            cat_df = cdf[cdf["Category"] == category].copy()
            if cat_df.empty:
                continue

            stages = [s for s in cfg["stages"] if s in set(cat_df["Stage"].astype(str).tolist())]
            if not stages:
                continue

            ncols = 3
            nrows = math.ceil(len(stages) / ncols)
            fig, axes = plt.subplots(nrows, ncols, figsize=(5.2 * ncols, 5.2 * nrows))
            axes_arr = np.array(axes).reshape(nrows, ncols)
            axes_flat = axes_arr.flatten()
            cmap = plt.get_cmap("tab10")
            all_bins: list[pd.DataFrame] = []

            for idx, stage in enumerate(stages):
                ax = axes_flat[idx]
                sdf = cat_df[cat_df["Stage"] == stage].copy()
                if sdf.empty:
                    ax.text(0.5, 0.5, "NA", ha="center", va="center")
                    ax.set_axis_off()
                    continue

                for m_idx, model in enumerate(models):
                    mdf = sdf[sdf["Model"] == model].copy()
                    if mdf.empty:
                        continue
                    mdf = mdf.dropna(subset=["Confidence", "Accuracy"])
                    if mdf.empty:
                        continue
                    mdf["bin"] = pd.cut(mdf["Confidence"], bins=np.linspace(0, 1, 11), include_lowest=True)
                    agg = (
                        mdf.groupby("bin", observed=False)
                        .agg(conf=("Confidence", "mean"), acc=("Accuracy", "mean"), n=("CaseID", "count"))
                        .reset_index()
                    )
                    agg["Model"] = model
                    agg["Stage"] = stage
                    agg["Category"] = category
                    all_bins.append(agg)

                    plot_df = agg.dropna(subset=["conf", "acc"]).copy()
                    if plot_df.empty:
                        continue
                    plot_df = plot_df.sort_values("conf")
                    color = cmap(m_idx % 10)
                    ax.scatter(
                        plot_df["conf"],
                        plot_df["acc"],
                        s=plot_df["n"].astype(float) * 42 + 36,
                        c=[color],
                        alpha=0.48,
                        edgecolor="black",
                        linewidths=0.5,
                        label=model,
                    )
                    if len(plot_df) >= 2:
                        ax.plot(
                            plot_df["conf"],
                            plot_df["acc"],
                            color=color,
                            linewidth=1.2,
                            alpha=0.75,
                        )
                    for _, rr in plot_df.iterrows():
                        if int(rr["n"]) >= 8:
                            ax.text(float(rr["conf"]), float(rr["acc"]), f"{int(rr['n'])}", ha="center", va="center", fontsize=7)

                ax.plot([0, 1], [0, 1], linestyle="--", color="black", linewidth=1.0)
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.set_aspect("equal", adjustable="box")
                ax.set_xlabel("Confidence")
                ax.set_ylabel("Accuracy")
                ax.set_title(STAGE_KEY_TO_SHORT.get(stage, stage))
                ax.grid(linestyle=":", alpha=0.28)

            for j in range(len(stages), len(axes_flat)):
                axes_flat[j].axis("off")

            handles, labels = axes_flat[0].get_legend_handles_labels()
            if handles:
                fig.legend(handles, labels, loc="upper center", ncol=min(5, len(labels)), bbox_to_anchor=(0.5, 0.99), fontsize=8)
            fig.suptitle(f"{cfg['title']} - {CENTER_LABELS.get(center, center)}", y=0.995)
            fig.tight_layout(rect=(0, 0, 1, 0.95))

            out_name = cfg["filename"].format(center=center)
            out_png = cal_dir / out_name
            fig.savefig(out_png, dpi=420)
            plt.close(fig)

            bins_df = pd.concat(all_bins, ignore_index=True) if all_bins else pd.DataFrame()
            line_png = None
            if not bins_df.empty:
                line_fig, line_axes = plt.subplots(nrows, ncols, figsize=(5.2 * ncols, 5.2 * nrows))
                line_axes_arr = np.array(line_axes).reshape(nrows, ncols)
                line_axes_flat = line_axes_arr.flatten()
                for idx, stage in enumerate(stages):
                    ax = line_axes_flat[idx]
                    stage_bins = bins_df[bins_df["Stage"] == stage].copy()
                    if stage_bins.empty:
                        ax.text(0.5, 0.5, "NA", ha="center", va="center")
                        ax.set_axis_off()
                        continue
                    for m_idx, model in enumerate(models):
                        mdf = stage_bins[stage_bins["Model"] == model].dropna(subset=["conf", "acc"]).copy()
                        if mdf.empty:
                            continue
                        mdf = mdf.sort_values("conf")
                        color = cmap(m_idx % 10)
                        ax.plot(
                            mdf["conf"],
                            mdf["acc"],
                            marker="o",
                            markersize=4.2,
                            linewidth=1.4,
                            color=color,
                            alpha=0.85,
                            label=model,
                        )
                    ax.plot([0, 1], [0, 1], linestyle="--", color="black", linewidth=1.0)
                    ax.set_xlim(0, 1)
                    ax.set_ylim(0, 1)
                    ax.set_aspect("equal", adjustable="box")
                    ax.set_xlabel("Confidence")
                    ax.set_ylabel("Accuracy")
                    ax.set_title(STAGE_KEY_TO_SHORT.get(stage, stage))
                    ax.grid(linestyle=":", alpha=0.28)

                for j in range(len(stages), len(line_axes_flat)):
                    line_axes_flat[j].axis("off")

                handles, labels = line_axes_flat[0].get_legend_handles_labels()
                if handles:
                    line_fig.legend(handles, labels, loc="upper center", ncol=min(5, len(labels)), bbox_to_anchor=(0.5, 0.99), fontsize=8)
                line_fig.suptitle(f"{cfg['title']} (line) - {CENTER_LABELS.get(center, center)}", y=0.995)
                line_fig.tight_layout(rect=(0, 0, 1, 0.95))
                line_png = cal_dir / f"calibration_line_{category}_stagewise_{center}.png"
                line_fig.savefig(line_png, dpi=420)
                plt.close(line_fig)
            raw_cat = points_df[(points_df["Center"] == center) & (points_df["Category"] == category)].copy()
            case_cat = cat_df.copy()
            _write_source_data(
                out_dir,
                out_png.stem,
                {
                    "raw_round_points": raw_cat,
                    "case_points": case_cat,
                    "bin_summary": bins_df,
                },
                {
                    "figure": out_png.name,
                    "line_figure": line_png.name if line_png else "",
                    "description": f"{cfg['title']} (bubble size = sample count)",
                    "center": center,
                    "category": category,
                    "stage_order": ",".join(stages),
                    "data_root": str(data_root) if data_root else "",
                },
            )

            # ??????????????????
            if category == "overall":
                alias = cal_dir / f"calibration_bubble_overall_stagewise_{center}.png"
                if alias.exists():
                    alias.unlink()
                shutil.copy2(out_png, alias)


def _plot_manual_metrics(doctor_report: Path, out_dir: Path) -> None:
    if not doctor_report.exists():
        return
    out_alignment = out_dir / "alignment"
    _ensure_dir(out_alignment)

    mapping = [
        ("人工评分_结果质量_汇总", "结果质量评分_均值", "manual_result_quality_by_stage.png", "Manual Result Quality by Stage"),
        ("人工评分_推理合理性_汇总", "推理合理性_均值", "manual_reasoning_quality_by_stage.png", "Manual Reasoning Quality by Stage"),
    ]

    for sheet, token, fig_name, title in mapping:
        try:
            df = pd.read_excel(doctor_report, sheet_name=sheet, engine="openpyxl")
        except Exception:
            continue
        if df.empty:
            continue
        rows: list[dict[str, Any]] = []
        for _, r in df.iterrows():
            center = str(r.get("中心", "")).strip()
            model = str(r.get("模型名称", "")).strip()
            if not center or not model:
                continue
            for stage in STAGE_CN_ORDER:
                col = f"{stage}_{token}"
                if col not in df.columns:
                    continue
                val = _to_numeric(pd.Series([r.get(col)])).iloc[0]
                rows.append({"Center": center, "Model": model, "Stage": STAGE_SHORT_TO_KEY.get(stage, stage), "Value": val})

        long_df = pd.DataFrame(rows)
        if long_df.empty:
            continue

        for center in _center_order(long_df["Center"]):
            sub = long_df[long_df["Center"] == center]
            if sub.empty:
                continue
            models = _model_order(sub["Model"])
            pivot = (
                sub.pivot_table(index="Model", columns="Stage", values="Value", aggfunc="mean")
                .reindex(index=models)
                .reindex(columns=STAGE_KEYS)
            )
            fig, ax = plt.subplots(figsize=(11.4, 5.2))
            pivot.plot(kind="bar", ax=ax, colormap="Blues")
            ax.set_title(f"{title} - {CENTER_LABELS.get(center, center)}")
            ax.set_ylabel("Score (0-5)")
            ax.set_xlabel("Model")
            ax.set_ylim(0, 5)
            ax.grid(axis="y", linestyle="--", alpha=0.25)
            ax.legend(title="Stage", ncol=3, fontsize=8)
            plt.xticks(rotation=25, ha="right")
            fig.tight_layout()
            out_png = out_alignment / fig_name.replace(".png", f"_{center}.png")
            fig.savefig(out_png, dpi=320)
            plt.close(fig)

            _write_source_data(
                out_dir,
                out_png.stem,
                {"plot_data": pivot.reset_index(), "raw": sub},
                {
                    "figure": out_png.name,
                    "description": title,
                    "center": center,
                    "doctor_report": str(doctor_report),
                },
            )


def _normalize_llm_stage(value: Any) -> str:
    s = str(value or "").strip()
    mapping = {
        "D1_Outpatient_Loop": "D1_Loop",
        "D1_Outpatient_Decision": "D1_Decision",
        "D2_Admission_Loop": "D2_Loop",
        "D2_Admission_Decision": "D2_Decision",
        "D3_Surgery_Decision": "D3_Decision",
        "D4_Rehab_Plan": "D4_Plan",
        "D1": "D1_Decision",
        "D2": "D2_Decision",
        "D3": "D3_Decision",
        "D4": "D4_Plan",
    }
    return mapping.get(s, s)


def _plot_llm_stage_metric(
    long_df: pd.DataFrame,
    value_col: str,
    stage_order: list[str],
    out_dir: Path,
    prefix: str,
    title: str,
    ylim: tuple[float, float] = (0, 1),
    meta_extra: dict[str, Any] | None = None,
) -> None:
    if long_df.empty:
        return
    if prefix.startswith("llm_reasoning"):
        llm_dir = out_dir / "llm" / "full" / "reasoning"
    elif prefix.startswith("llm_consistency"):
        llm_dir = out_dir / "llm" / "full" / "consistency"
    elif prefix.startswith("llm_memory"):
        llm_dir = out_dir / "llm" / "full" / "memory"
    else:
        llm_dir = out_dir / "llm" / "full" / "general"
    _ensure_dir(llm_dir)

    centers = _center_order(long_df["Center"])
    models = _model_order(long_df["Model"])
    model_palette = {m: plt.get_cmap("tab10")(i % 10) for i, m in enumerate(models)}

    def _draw_one(ax, cdf: pd.DataFrame, center: str) -> pd.DataFrame:
        pivot = (
            cdf.pivot_table(index="Model", columns="Stage", values=value_col, aggfunc="mean")
            .reindex(index=models)
            .reindex(columns=stage_order)
        )
        x = np.arange(len(models), dtype=float)
        width = 0.12 if len(stage_order) >= 6 else 0.18
        for i, stage in enumerate(stage_order):
            vals = pivot[stage].astype(float).to_numpy() if stage in pivot.columns else np.full(len(models), np.nan)
            pos = x + (i - (len(stage_order) - 1) / 2) * width
            ratio = i / max(1, len(stage_order) - 1)
            colors = [_tint(model_palette[m][:3], 0.62 - 0.5 * ratio) for m in models]
            bars = ax.bar(pos, np.where(np.isnan(vals), 0.0, vals), width=width, color=colors, edgecolor="white", linewidth=0.4, label=STAGE_KEY_TO_SHORT.get(stage, stage))
            for b, v in zip(bars, vals):
                cx = b.get_x() + b.get_width() / 2
                if np.isnan(v):
                    b.set_facecolor((0.92, 0.92, 0.92, 1.0))
                    b.set_edgecolor((0.55, 0.55, 0.55, 1.0))
                    b.set_hatch("///")
                    ax.text(cx, ylim[0] + 0.01, "NA", ha="center", va="bottom", fontsize=6.5, color="#666666", rotation=90)
                else:
                    ax.text(cx, float(v) + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=6.8)

        ax.set_xticks(x)
        ax.set_xticklabels(models, rotation=24, ha="right")
        ax.set_title(CENTER_LABELS.get(center, center))
        ax.set_ylim(*ylim)
        ax.grid(axis="y", linestyle=":", alpha=0.25)
        return pivot

    # ????
    for center in centers:
        cdf = long_df[long_df["Center"] == center].copy()
        if cdf.empty:
            continue
        fig, ax = plt.subplots(figsize=(9.6, 9.6))
        pivot = _draw_one(ax, cdf, center)
        ax.set_ylabel("Score (0-1)")
        ax.set_title(f"{title} - {CENTER_LABELS.get(center, center)}")
        ax.legend(loc="upper right", fontsize=8, ncol=2)
        fig.tight_layout()
        out_png = llm_dir / f"{prefix}_{center}.png"
        fig.savefig(out_png, dpi=420)
        plt.close(fig)
        _write_source_data(
            out_dir,
            f"{prefix}_{center}",
            {"raw": cdf, "plot_data": pivot.reset_index()},
            {
                "figure": out_png.name,
                "description": title,
                "center": center,
                "stage_order": ",".join(stage_order),
                **(meta_extra or {}),
            },
        )

    # ??????? 2x2?
    fig, axes = plt.subplots(2, 2, figsize=(12, 12))
    axes_flat = axes.flatten()
    for idx, center in enumerate(centers):
        ax = axes_flat[idx]
        cdf = long_df[long_df["Center"] == center].copy()
        if cdf.empty:
            ax.axis("off")
            continue
        _draw_one(ax, cdf, center)
        ax.set_ylabel("Score (0-1)")
    for j in range(len(centers), len(axes_flat)):
        axes_flat[j].axis("off")
    handles, labels = axes_flat[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper center", ncol=min(6, len(labels)), bbox_to_anchor=(0.5, 0.99), fontsize=8)
    fig.suptitle(title, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    combined = llm_dir / f"{prefix}_combined.png"
    fig.savefig(combined, dpi=1200)
    plt.close(fig)

    _write_source_data(
        out_dir,
        f"{prefix}_combined",
        {"raw": long_df},
        {
            "figure": combined.name,
            "description": f"{title} (multi-center combined)",
            "stage_order": ",".join(stage_order),
            **(meta_extra or {}),
        },
    )


def _plot_llm_consistency_linebar(
    cons: pd.DataFrame,
    out_dir: Path,
    stage_order: list[str],
    title: str,
    out_prefix: str = "llm_consistency_cross_stagewise_linebar",
    description: str = "Consistency (line) + sample count (bar)",
    meta_extra: dict[str, Any] | None = None,
) -> None:
    if cons.empty:
        return
    llm_dir = out_dir / "llm" / "full" / "consistency"
    _ensure_dir(llm_dir)
    centers = _center_order(cons["Center"])
    image_paths: list[Path] = []
    labels: list[str] = []
    for center in centers:
        cdf = cons[cons["Center"] == center].copy()
        if cdf.empty:
            continue
        rows: list[dict[str, Any]] = []
        for stage in stage_order:
            sdf = cdf[cdf["Stage"] == stage].copy()
            if sdf.empty:
                rows.append({"Stage": stage, "Mean": np.nan, "Samples": 0, "ConflictCount": 0, "FactShiftCount": 0, "OtherCount": 0})
                continue
            if "Samples" in sdf.columns:
                w = pd.to_numeric(sdf["Samples"], errors="coerce").fillna(0)
                v = pd.to_numeric(sdf["Value"], errors="coerce")
                denom = float(w.sum())
                mean = float((v * w).sum() / denom) if denom > 0 else float(v.mean())
                samples = int(denom)
            else:
                mean = float(pd.to_numeric(sdf["Value"], errors="coerce").mean())
                samples = int(len(sdf))
            conflict = int(pd.to_numeric(sdf["ConflictCount"], errors="coerce").fillna(0).sum()) if "ConflictCount" in sdf.columns else 0
            fact_shift = int(pd.to_numeric(sdf["FactShiftCount"], errors="coerce").fillna(0).sum()) if "FactShiftCount" in sdf.columns else 0
            other = int(pd.to_numeric(sdf["OtherCount"], errors="coerce").fillna(0).sum()) if "OtherCount" in sdf.columns else 0
            rows.append(
                {
                    "Stage": stage,
                    "Mean": mean,
                    "Samples": samples,
                    "ConflictCount": conflict,
                    "FactShiftCount": fact_shift,
                    "OtherCount": other,
                }
            )
        agg = pd.DataFrame(rows)

        fig, ax1 = plt.subplots(figsize=(7.6, 7.6))
        x = np.arange(len(stage_order), dtype=float)
        ax1.plot(x, agg["Mean"].to_numpy(), marker="o", linewidth=2.2, color="#3B6FB6", label="Consistency score")
        for xi, yi in zip(x, agg["Mean"].to_numpy()):
            if np.isfinite(yi):
                ax1.text(xi, float(yi) + 0.03, f"{float(yi):.2f}", ha="center", va="bottom", fontsize=8, color="#2F5FA3")
        ax1.set_ylabel("Score (0-1)")
        ax1.set_ylim(0, 1)
        ax1.set_xticks(x)
        ax1.set_xticklabels([STAGE_KEY_TO_SHORT[s] for s in stage_order])
        ax1.grid(axis="y", linestyle="--", alpha=0.25)

        ax2 = ax1.twinx()
        if {"ConflictCount", "FactShiftCount"}.issubset(set(agg.columns)):
            ax2.bar(x - 0.18, agg["ConflictCount"].to_numpy(), width=0.28, color="#F4B6A4", alpha=0.85, label="Conflict count")
            ax2.bar(x + 0.18, agg["FactShiftCount"].to_numpy(), width=0.28, color="#F08A8B", alpha=0.85, label="Fact-shift count")
            ax2.set_ylabel("Issue count (per stage)")
        else:
            ax2.bar(x, agg["Samples"].to_numpy(), width=0.45, color="#D9CDBF", alpha=0.7, label="Samples")
            ax2.set_ylabel("Samples")

        ax1.set_title(f"{title} - {CENTER_LABELS.get(center, center)}")
        handles1, labels1 = ax1.get_legend_handles_labels()
        handles2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(handles1 + handles2, labels1 + labels2, loc="upper right", fontsize=8)
        fig.tight_layout()
        out_png = llm_dir / f"{out_prefix}_{center}.png"
        fig.savefig(out_png, dpi=420)
        plt.close(fig)
        image_paths.append(out_png)
        labels.append(CENTER_LABELS.get(center, center))

        _write_source_data(
            out_dir,
            out_png.stem,
            {"raw": cdf, "agg": agg},
            {
                "figure": out_png.name,
                "description": description,
                "center": center,
                "stage_order": ",".join(stage_order),
                **(meta_extra or {}),
            },
        )

    if len(image_paths) > 1:
        _save_image_grid(
            image_paths,
            llm_dir / f"{out_prefix}_grid.png",
            title=title,
            labels=labels,
            ncols=len(image_paths),
        )


def _parse_issue_tags(raw: Any) -> list[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    text = str(raw).strip()
    if not text:
        return []
    tags: Any = []
    try:
        tags = json.loads(text)
    except Exception:
        try:
            tags = ast.literal_eval(text)
        except Exception:
            tags = [part.strip().strip("'").strip('"') for part in text.strip("[]").split(",") if part.strip()]
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list):
        return []
    return [str(tag).strip() for tag in tags if str(tag).strip()]


def _aggregate_issue_tag_counts(
    detail_df: pd.DataFrame,
    center_col: str,
    model_col: str,
    stage_col: str,
    stage_order: list[str],
    tag_map: dict[str, str],
    tag_col: str = "错误标签(JSON)",
) -> pd.DataFrame:
    if detail_df.empty or tag_col not in detail_df.columns:
        return pd.DataFrame()
    base = detail_df[[center_col, model_col, stage_col, tag_col]].copy()
    base[stage_col] = base[stage_col].map(_normalize_llm_stage)
    base = base[base[stage_col].isin(stage_order)].copy()
    if base.empty:
        return pd.DataFrame()
    base["_tags"] = base[tag_col].apply(_parse_issue_tags)
    for tag_key, out_col in tag_map.items():
        base[out_col] = base["_tags"].apply(lambda tags: int(sum(1 for tag in tags if tag == tag_key)))
    base["Samples"] = 1
    agg_cols = list(tag_map.values()) + ["Samples"]
    return (
        base.groupby([center_col, model_col, stage_col], as_index=False)[agg_cols]
        .sum()
        .rename(columns={center_col: "Center", model_col: "Model", stage_col: "Stage"})
    )


def _plot_llm_issue_tag_distribution(
    counts_df: pd.DataFrame,
    out_dir: Path,
    stage_order: list[str],
    title: str,
    out_prefix: str,
    subdir: Path,
    tag_styles: list[tuple[str, str, str]],
    meta_extra: dict[str, Any] | None = None,
) -> None:
    if counts_df.empty:
        return
    llm_dir = out_dir / subdir
    _ensure_dir(llm_dir)
    tag_cols = [col for col, _, _ in tag_styles]
    centers = _center_order(counts_df["Center"])
    image_paths: list[Path] = []
    labels: list[str] = []
    grid_rows: list[pd.DataFrame] = []

    for center in centers:
        cdf = counts_df[counts_df["Center"] == center].copy()
        if cdf.empty:
            continue
        rows: list[dict[str, Any]] = []
        for stage in stage_order:
            sdf = cdf[cdf["Stage"] == stage]
            row: dict[str, Any] = {
                "Stage": stage,
                "Samples": int(pd.to_numeric(sdf.get("Samples", 0), errors="coerce").fillna(0).sum()),
            }
            issue_total = 0
            for col in tag_cols:
                value = int(pd.to_numeric(sdf.get(col, 0), errors="coerce").fillna(0).sum())
                row[col] = value
                issue_total += value
            row["IssueTotal"] = issue_total
            rows.append(row)
        agg = pd.DataFrame(rows)
        share = agg[["Stage", "Samples", "IssueTotal"]].copy()
        denom = agg["IssueTotal"].replace(0, np.nan)
        for col in tag_cols:
            share[col] = (agg[col] / denom).fillna(0.0)
        grid_rows.append(pd.concat([pd.DataFrame({"Center": [center] * len(agg)}), agg], axis=1))

        fig, ax = plt.subplots(figsize=(7.8, 5.6))
        x = np.arange(len(stage_order), dtype=float)
        bottom = np.zeros(len(stage_order), dtype=float)
        for col, label, color in tag_styles:
            values = share[col].to_numpy(dtype=float)
            ax.bar(x, values, bottom=bottom, width=0.62, color=color, edgecolor="white", linewidth=0.8, label=label)
            bottom += values

        for idx, (_, row) in enumerate(agg.iterrows()):
            label = f"tag={int(row['IssueTotal'])}\nn={int(row['Samples'])}"
            y = min(1.02, bottom[idx] + 0.03)
            ax.text(x[idx], y, label, ha="center", va="bottom", fontsize=7, color="#3A3A3A")

        ax.set_ylim(0, 1.12)
        ax.set_ylabel("Issue-tag share")
        ax.set_xticks(x)
        ax.set_xticklabels([STAGE_KEY_TO_SHORT[s] for s in stage_order])
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.grid(axis="y", linestyle="--", alpha=0.25)
        ax.set_title(f"{title} - {CENTER_LABELS.get(center, center)}")
        ax.legend(loc="upper right", fontsize=8)
        fig.tight_layout()

        out_png = llm_dir / f"{out_prefix}_{center}.png"
        fig.savefig(out_png, dpi=420)
        plt.close(fig)
        image_paths.append(out_png)
        labels.append(CENTER_LABELS.get(center, center))

        _write_source_data(
            out_dir,
            out_png.stem,
            {"raw": cdf, "agg": agg, "summary": share},
            {
                "figure": out_png.name,
                "description": f"{title} (stacked issue-tag share by stage)",
                "center": center,
                "stage_order": ",".join(stage_order),
                **(meta_extra or {}),
            },
        )

    if len(image_paths) > 1:
        grid_path = llm_dir / f"{out_prefix}_grid.png"
        _save_image_grid(
            image_paths,
            grid_path,
            title=title,
            labels=labels,
            ncols=len(image_paths),
        )
        _write_source_data(
            out_dir,
            grid_path.stem,
            {"raw": counts_df, "agg": pd.concat(grid_rows, ignore_index=True) if grid_rows else counts_df},
            {
                "figure": grid_path.name,
                "description": f"{title} (multi-center combined)",
                "stage_order": ",".join(stage_order),
                **(meta_extra or {}),
            },
        )


def _plot_llm_consistency_band(
    cons: pd.DataFrame,
    out_dir: Path,
    stage_order: list[str],
    title: str,
    meta_extra: dict[str, Any] | None = None,
) -> None:
    if cons.empty:
        return
    llm_dir = out_dir / "llm" / "full" / "consistency"
    _ensure_dir(llm_dir)
    centers = _center_order(cons["Center"])
    for center in centers:
        cdf = cons[cons["Center"] == center].copy()
        if cdf.empty:
            continue
        rows: list[dict[str, Any]] = []
        for stage in stage_order:
            sdf = cdf[cdf["Stage"] == stage].copy()
            vals = pd.to_numeric(sdf["Value"], errors="coerce")
            rows.append(
                {
                    "Stage": stage,
                    "Mean": float(vals.mean()) if not vals.empty else np.nan,
                    "Std": float(vals.std()) if len(vals) > 1 else 0.0,
                }
            )
        agg = pd.DataFrame(rows)
        x = np.arange(len(stage_order), dtype=float)
        mean = agg["Mean"].to_numpy()
        std = agg["Std"].to_numpy()

        fig, ax = plt.subplots(figsize=(7.4, 5.2))
        ax.plot(x, mean, marker="o", linewidth=2.2, color="#2C7BB6", label="Mean")
        ax.fill_between(x, mean - std, mean + std, color="#2C7BB6", alpha=0.2, label="±1 std")
        ax.set_ylabel("Score (0-1)")
        ax.set_ylim(0, 1)
        ax.set_xticks(x)
        ax.set_xticklabels([STAGE_KEY_TO_SHORT[s] for s in stage_order])
        ax.grid(axis="y", linestyle="--", alpha=0.25)
        ax.set_title(f"{title} - {CENTER_LABELS.get(center, center)}")
        ax.legend(loc="upper right", fontsize=8)
        fig.tight_layout()
        out_png = llm_dir / f"llm_consistency_cross_stagewise_band_{center}.png"
        fig.savefig(out_png, dpi=420)
        plt.close(fig)

        _write_source_data(
            out_dir,
            out_png.stem,
            {"raw": cdf, "agg": agg},
            {
                "figure": out_png.name,
                "description": "Consistency mean ± std (band)",
                "center": center,
                "stage_order": ",".join(stage_order),
                **(meta_extra or {}),
            },
        )


def _plot_llm_metric_model_lines(
    df: pd.DataFrame,
    out_dir: Path,
    stage_order: list[str],
    title: str,
    out_prefix: str,
    subdir: Path,
    value_col: str = "Value",
    ylim: tuple[float, float] = (0, 1),
    meta_extra: dict[str, Any] | None = None,
) -> None:
    if df.empty:
        return
    llm_dir = out_dir / subdir
    _ensure_dir(llm_dir)
    centers = _center_order(df["Center"])
    models = _model_order(df["Model"])
    model_palette = {m: plt.get_cmap("tab10")(i % 10) for i, m in enumerate(models)}
    for center in centers:
        cdf = df[df["Center"] == center].copy()
        if cdf.empty:
            continue
        pivot = (
            cdf.pivot_table(index="Model", columns="Stage", values=value_col, aggfunc="mean")
            .reindex(index=models)
            .reindex(columns=stage_order)
        )
        x = np.arange(len(stage_order), dtype=float)
        fig, ax = plt.subplots(figsize=(7.8, 5.8))
        for model in models:
            if model not in pivot.index:
                continue
            vals = pd.to_numeric(pivot.loc[model], errors="coerce").to_numpy()
            ax.plot(
                x,
                vals,
                marker="o",
                linewidth=1.9,
                color=model_palette[model],
                alpha=0.9,
                label=model,
            )
        ax.set_xticks(x)
        ax.set_xticklabels([STAGE_KEY_TO_SHORT[s] for s in stage_order])
        ax.set_ylim(*ylim)
        ax.set_ylabel("Score (0-1)")
        ax.grid(axis="y", linestyle="--", alpha=0.25)
        ax.set_title(f"{title} - {CENTER_LABELS.get(center, center)}")
        ax.legend(loc="upper right", ncol=2, fontsize=7)
        fig.tight_layout()
        out_png = llm_dir / f"{out_prefix}_{center}.png"
        fig.savefig(out_png, dpi=420)
        plt.close(fig)

        _write_source_data(
            out_dir,
            out_png.stem,
            {"raw": cdf, "plot_data": pivot.reset_index()},
            {
                "figure": out_png.name,
                "description": f"{title} (model lines)",
                "center": center,
                "stage_order": ",".join(stage_order),
                **(meta_extra or {}),
            },
        )


def _plot_llm_metric_heatmap(
    df: pd.DataFrame,
    out_dir: Path,
    stage_order: list[str],
    title: str,
    out_prefix: str,
    subdir: Path,
    value_col: str = "Value",
    ylim: tuple[float, float] = (0, 1),
    meta_extra: dict[str, Any] | None = None,
) -> None:
    if df.empty:
        return
    llm_dir = out_dir / subdir
    _ensure_dir(llm_dir)
    centers = _center_order(df["Center"])
    models = _model_order(df["Model"])
    for center in centers:
        cdf = df[df["Center"] == center].copy()
        if cdf.empty:
            continue
        pivot = (
            cdf.pivot_table(index="Model", columns="Stage", values=value_col, aggfunc="mean")
            .reindex(index=models)
            .reindex(columns=stage_order)
        )
        data = pivot.apply(pd.to_numeric, errors="coerce").to_numpy()
        masked = np.ma.masked_invalid(data)
        cmap = plt.get_cmap("YlGnBu").copy()
        cmap.set_bad(color="#E0E0E0")

        fig, ax = plt.subplots(figsize=(7.8, 5.6))
        im = ax.imshow(masked, vmin=ylim[0], vmax=ylim[1], cmap=cmap, aspect="auto")
        ax.set_xticks(np.arange(len(stage_order)))
        ax.set_xticklabels([STAGE_KEY_TO_SHORT[s] for s in stage_order])
        ax.set_yticks(np.arange(len(models)))
        ax.set_yticklabels(models)
        ax.set_title(f"{title} - {CENTER_LABELS.get(center, center)}")
        for i, model in enumerate(models):
            for j, stage in enumerate(stage_order):
                val = data[i, j] if i < data.shape[0] and j < data.shape[1] else np.nan
                if np.isnan(val):
                    ax.text(j, i, "NA", ha="center", va="center", fontsize=7, color="#666666")
                else:
                    ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7, color="black")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        fig.tight_layout()
        out_png = llm_dir / f"{out_prefix}_{center}.png"
        fig.savefig(out_png, dpi=420)
        plt.close(fig)

        _write_source_data(
            out_dir,
            out_png.stem,
            {"raw": cdf, "plot_data": pivot.reset_index()},
            {
                "figure": out_png.name,
                "description": f"{title} (heatmap)",
                "center": center,
                "stage_order": ",".join(stage_order),
                **(meta_extra or {}),
            },
        )


def _plot_llm_metric_model_band(
    df: pd.DataFrame,
    out_dir: Path,
    stage_order: list[str],
    title: str,
    out_prefix: str,
    subdir: Path,
    value_col: str = "Value",
    ylim: tuple[float, float] = (0, 1),
    meta_extra: dict[str, Any] | None = None,
) -> None:
    if df.empty:
        return
    llm_dir = out_dir / subdir
    _ensure_dir(llm_dir)
    centers = _center_order(df["Center"])
    models = _model_order(df["Model"])
    model_palette = {m: plt.get_cmap("tab10")(i % 10) for i, m in enumerate(models)}
    for center in centers:
        cdf = df[df["Center"] == center].copy()
        if cdf.empty:
            continue
        rows = []
        for stage in stage_order:
            sdf = cdf[cdf["Stage"] == stage].copy()
            for model in models:
                mdf = sdf[sdf["Model"] == model]
                vals = pd.to_numeric(mdf[value_col], errors="coerce")
                rows.append(
                    {
                        "Stage": stage,
                        "Model": model,
                        "Mean": float(vals.mean()) if not vals.empty else np.nan,
                        "Std": float(vals.std()) if len(vals) > 1 else 0.0,
                    }
                )
        agg = pd.DataFrame(rows)
        x = np.arange(len(stage_order), dtype=float)
        fig, ax = plt.subplots(figsize=(7.8, 5.8))
        for model in models:
            mdf = agg[agg["Model"] == model].copy().set_index("Stage").reindex(stage_order)
            mean = mdf["Mean"].to_numpy()
            std = mdf["Std"].to_numpy()
            color = model_palette[model]
            ax.plot(x, mean, marker="o", linewidth=1.8, color=color, label=model)
            ax.fill_between(x, mean - std, mean + std, color=color, alpha=0.15)
        ax.set_xticks(x)
        ax.set_xticklabels([STAGE_KEY_TO_SHORT[s] for s in stage_order])
        ax.set_ylim(*ylim)
        ax.set_ylabel("Score (0-1)")
        ax.grid(axis="y", linestyle="--", alpha=0.25)
        ax.set_title(f"{title} - {CENTER_LABELS.get(center, center)}")
        ax.legend(loc="upper right", ncol=2, fontsize=7)
        fig.tight_layout()
        out_png = llm_dir / f"{out_prefix}_{center}.png"
        fig.savefig(out_png, dpi=420)
        plt.close(fig)

        _write_source_data(
            out_dir,
            out_png.stem,
            {"raw": cdf, "agg": agg},
            {
                "figure": out_png.name,
                "description": f"{title} (model band)",
                "center": center,
                "stage_order": ",".join(stage_order),
                **(meta_extra or {}),
            },
        )


def _plot_llm_memory_line(
    mem: pd.DataFrame,
    out_dir: Path,
    stage_order: list[str],
    title: str,
    col_inherit: str,
    col_use: str,
    meta_extra: dict[str, Any] | None = None,
) -> None:
    if mem.empty:
        return
    llm_dir = out_dir / "llm" / "full" / "memory"
    _ensure_dir(llm_dir)
    centers = _center_order(mem["Center"])
    for center in centers:
        cdf = mem[mem["Center"] == center].copy()
        if cdf.empty:
            continue
        rows: list[dict[str, Any]] = []
        for stage in stage_order:
            sdf = cdf[cdf["Stage"] == stage].copy()
            v1 = pd.to_numeric(sdf[col_inherit], errors="coerce")
            v2 = pd.to_numeric(sdf[col_use], errors="coerce")
            rows.append(
                {
                    "Stage": stage,
                    "Inheritance": float(v1.mean()) if not v1.empty else np.nan,
                    "Utilization": float(v2.mean()) if not v2.empty else np.nan,
                }
            )
        agg = pd.DataFrame(rows)
        agg["Overall"] = agg[["Inheritance", "Utilization"]].mean(axis=1, skipna=True)

        x = np.arange(len(stage_order), dtype=float)
        fig, ax = plt.subplots(figsize=(7.4, 5.2))
        ax.plot(x, agg["Inheritance"].to_numpy(), marker="o", linewidth=2.0, color="#4C9F70", label="Inheritance")
        ax.plot(x, agg["Utilization"].to_numpy(), marker="s", linewidth=2.0, color="#7A6FB5", label="Utilization")
        ax.plot(x, agg["Overall"].to_numpy(), marker="D", linewidth=2.0, linestyle="--", color="#2C7BB6", label="Overall")
        ax.set_ylabel("Score (0-1)")
        ax.set_ylim(0, 1)
        ax.set_xticks(x)
        ax.set_xticklabels([STAGE_KEY_TO_SHORT[s] for s in stage_order])
        ax.grid(axis="y", linestyle="--", alpha=0.25)
        ax.set_title(f"{title} - {CENTER_LABELS.get(center, center)}")
        ax.legend(loc="lower left", fontsize=8)
        fig.tight_layout()
        out_png = llm_dir / f"llm_memory_stagewise_line_{center}.png"
        fig.savefig(out_png, dpi=420)
        plt.close(fig)

        _write_source_data(
            out_dir,
            out_png.stem,
            {"raw": cdf, "agg": agg},
            {
                "figure": out_png.name,
                "description": "Memory retention lines (inheritance/utilization/overall)",
                "center": center,
                "stage_order": ",".join(stage_order),
                **(meta_extra or {}),
            },
        )


def _plot_llm_memory_band(
    mem: pd.DataFrame,
    out_dir: Path,
    stage_order: list[str],
    title: str,
    col_inherit: str,
    col_use: str,
    meta_extra: dict[str, Any] | None = None,
) -> None:
    if mem.empty:
        return
    llm_dir = out_dir / "llm" / "full" / "memory"
    _ensure_dir(llm_dir)
    centers = _center_order(mem["Center"])
    for center in centers:
        cdf = mem[mem["Center"] == center].copy()
        if cdf.empty:
            continue
        rows: list[dict[str, Any]] = []
        for stage in stage_order:
            sdf = cdf[cdf["Stage"] == stage].copy()
            v1 = pd.to_numeric(sdf[col_inherit], errors="coerce")
            v2 = pd.to_numeric(sdf[col_use], errors="coerce")
            overall = pd.concat([v1, v2], ignore_index=True)
            rows.append(
                {
                    "Stage": stage,
                    "Inheritance_mean": float(v1.mean()) if not v1.empty else np.nan,
                    "Inheritance_std": float(v1.std()) if len(v1) > 1 else 0.0,
                    "Utilization_mean": float(v2.mean()) if not v2.empty else np.nan,
                    "Utilization_std": float(v2.std()) if len(v2) > 1 else 0.0,
                    "Overall_mean": float(overall.mean()) if not overall.empty else np.nan,
                    "Overall_std": float(overall.std()) if len(overall) > 1 else 0.0,
                }
            )
        agg = pd.DataFrame(rows)
        x = np.arange(len(stage_order), dtype=float)

        fig, ax = plt.subplots(figsize=(7.4, 5.2))
        for label, mean_col, std_col, color in [
            ("Inheritance", "Inheritance_mean", "Inheritance_std", "#4C9F70"),
            ("Utilization", "Utilization_mean", "Utilization_std", "#7A6FB5"),
            ("Overall", "Overall_mean", "Overall_std", "#2C7BB6"),
        ]:
            mean = agg[mean_col].to_numpy()
            std = agg[std_col].to_numpy()
            ax.plot(x, mean, marker="o", linewidth=2.0, color=color, label=label)
            ax.fill_between(x, mean - std, mean + std, color=color, alpha=0.18)
        ax.set_ylabel("Score (0-1)")
        ax.set_ylim(0, 1)
        ax.set_xticks(x)
        ax.set_xticklabels([STAGE_KEY_TO_SHORT[s] for s in stage_order])
        ax.grid(axis="y", linestyle="--", alpha=0.25)
        ax.set_title(f"{title} - {CENTER_LABELS.get(center, center)}")
        ax.legend(loc="lower left", fontsize=8)
        fig.tight_layout()
        out_png = llm_dir / f"llm_memory_stagewise_band_{center}.png"
        fig.savefig(out_png, dpi=420)
        plt.close(fig)

        _write_source_data(
            out_dir,
            out_png.stem,
            {"raw": cdf, "agg": agg},
            {
                "figure": out_png.name,
                "description": "Memory retention mean ± std (band)",
                "center": center,
                "stage_order": ",".join(stage_order),
                **(meta_extra or {}),
            },
        )


def _plot_llm_memory_linebar(
    mem: pd.DataFrame,
    out_dir: Path,
    stage_order: list[str],
    title: str,
    col_inherit: str,
    col_use: str,
    meta_extra: dict[str, Any] | None = None,
) -> None:
    if mem.empty:
        return
    llm_dir = out_dir / "llm" / "full" / "memory"
    _ensure_dir(llm_dir)
    centers = _center_order(mem["Center"])
    image_paths: list[Path] = []
    labels: list[str] = []
    for center in centers:
        cdf = mem[mem["Center"] == center].copy()
        if cdf.empty:
            continue
        rows: list[dict[str, Any]] = []
        for stage in stage_order:
            sdf = cdf[cdf["Stage"] == stage].copy()
            v1 = pd.to_numeric(sdf[col_inherit], errors="coerce")
            v2 = pd.to_numeric(sdf[col_use], errors="coerce")
            rows.append(
                {
                    "Stage": stage,
                    "Inheritance": float(v1.mean()) if not v1.empty else np.nan,
                    "Utilization": float(v2.mean()) if not v2.empty else np.nan,
                }
            )
        agg = pd.DataFrame(rows)
        agg["Overall"] = agg[["Inheritance", "Utilization"]].mean(axis=1, skipna=True)

        x = np.arange(len(stage_order), dtype=float)
        width = 0.28
        fig, ax = plt.subplots(figsize=(7.6, 7.6))
        ax.bar(x - width / 2, agg["Inheritance"].to_numpy(), width=width, color="#7AA6D9", label="Inheritance")
        ax.bar(x + width / 2, agg["Utilization"].to_numpy(), width=width, color="#A7C7E7", label="Utilization")
        ax.plot(x, agg["Overall"].to_numpy(), marker="o", linewidth=2.2, color="#2C7BB6", label="Overall")
        ax.set_ylabel("Score (0-1)")
        ax.set_ylim(0, 1)
        ax.set_xticks(x)
        ax.set_xticklabels([STAGE_KEY_TO_SHORT[s] for s in stage_order])
        ax.grid(axis="y", linestyle="--", alpha=0.25)
        ax.set_title(f"{title} - {CENTER_LABELS.get(center, center)}")
        ax.legend(loc="upper right", fontsize=8, ncol=2)
        fig.tight_layout()
        out_png = llm_dir / f"llm_memory_stagewise_linebar_{center}.png"
        fig.savefig(out_png, dpi=420)
        plt.close(fig)
        image_paths.append(out_png)
        labels.append(CENTER_LABELS.get(center, center))

        _write_source_data(
            out_dir,
            out_png.stem,
            {"raw": cdf, "agg": agg},
            {
                "figure": out_png.name,
                "description": "Memory retention (line + bars)",
                "center": center,
                "stage_order": ",".join(stage_order),
                **(meta_extra or {}),
            },
        )

    if len(image_paths) > 1:
        _save_image_grid(
            image_paths,
            llm_dir / "llm_memory_stagewise_linebar_grid.png",
            title=title,
            labels=labels,
            ncols=len(image_paths),
        )

def _plot_llm_stage_metrics(llm_xlsx: Path, out_dir: Path) -> None:
    if not llm_xlsx.exists():
        return
    try:
        xl = pd.ExcelFile(llm_xlsx)
    except Exception:
        return

    base_dir = llm_xlsx.parent
    cons_xlsx = base_dir / "llm_consistency_gemini-2.5-pro__gala_api.xlsx"
    mem_xlsx = base_dir / "llm_memory_gemini-2.5-pro__gala_api.xlsx"
    try:
        cons_xl = pd.ExcelFile(cons_xlsx) if cons_xlsx.exists() else xl
    except Exception:
        cons_xl = xl
    try:
        mem_xl = pd.ExcelFile(mem_xlsx) if mem_xlsx.exists() else xl
    except Exception:
        mem_xl = xl

    center_col = "中心"
    model_col = "被评测模型"
    stage_col = "阶段"

    sheet_reason = "推理质量-汇总"
    reason_value = "推理质量得分(0-1)"

    sheet_cons = "一致性-跨阶段-汇总"
    cons_value = "一致性得分(0-1)"
    sheet_cons_fact = "一致性-事实-汇总"

    sheet_mem = "记忆保持-汇总"
    mem_col_1 = "历史信息继承度(0-1)"
    mem_col_2 = "历史信息利用率(0-1)"

    def _read(sheet_name: str, xl_obj: pd.ExcelFile) -> pd.DataFrame:
        if sheet_name not in xl_obj.sheet_names:
            return pd.DataFrame()
        try:
            return xl_obj.parse(sheet_name)
        except Exception:
            return pd.DataFrame()

    reason_df = _read(sheet_reason, xl)
    if not reason_df.empty and {center_col, model_col, stage_col, reason_value}.issubset(reason_df.columns):
        reason = reason_df.rename(columns={center_col: "Center", model_col: "Model", stage_col: "Stage", reason_value: "Value"}).copy()
        reason["Stage"] = reason["Stage"].map(_normalize_llm_stage)
        reason = reason[reason["Stage"].isin(STAGE_KEYS)]
        _plot_llm_stage_metric(
            reason,
            value_col="Value",
            stage_order=STAGE_KEYS,
            out_dir=out_dir,
            prefix="llm_reasoning_quality_stagewise",
            title="LLM Reasoning Quality (6 stages)",
            ylim=(0, 1),
            meta_extra={"llm_xlsx": str(llm_xlsx)},
        )
        _plot_llm_metric_model_band(
            reason,
            out_dir,
            STAGE_KEYS,
            "LLM Reasoning Quality (model band)",
            "llm_reasoning_quality_stagewise_modelband",
            Path("llm") / "full" / "reasoning",
            meta_extra={"llm_xlsx": str(llm_xlsx)},
        )

    cons_df = _read(sheet_cons, cons_xl)
    if not cons_df.empty and {center_col, model_col, stage_col, cons_value}.issubset(cons_df.columns):
        cons = cons_df.rename(columns={center_col: "Center", model_col: "Model", stage_col: "Stage", cons_value: "Value"}).copy()
        if "样本数" in cons_df.columns:
            cons["Samples"] = pd.to_numeric(cons_df["样本数"], errors="coerce")
        cons["Stage"] = cons["Stage"].map(_normalize_llm_stage)
        cons_order = ["D1_Decision", "D2_Decision", "D3_Decision", "D4_Plan"]
        cons = cons[cons["Stage"].isin(cons_order)]
        cons_detail = _read("一致性-跨阶段-明细", cons_xl)
        cons_issue_counts = _aggregate_issue_tag_counts(
            cons_detail,
            center_col,
            model_col,
            stage_col,
            cons_order,
            {
                "stage_conflict": "ConflictCount",
                "fact_shift": "FactShiftCount",
                "other": "OtherCount",
            },
        )
        if not cons_issue_counts.empty:
            cons = cons.merge(cons_issue_counts, on=["Center", "Model", "Stage"], how="left")
        _plot_llm_stage_metric(
            cons,
            value_col="Value",
            stage_order=cons_order,
            out_dir=out_dir,
            prefix="llm_consistency_cross_stagewise",
            title="LLM Cross-stage Consistency (decision stages)",
            ylim=(0, 1),
            meta_extra={"llm_xlsx": str(cons_xlsx if cons_xlsx.exists() else llm_xlsx)},
        )
        _plot_llm_consistency_linebar(
            cons,
            out_dir,
            cons_order,
            "LLM Consistency (line+bars)",
            out_prefix="llm_consistency_cross_stagewise_linebar",
            description="Cross-stage consistency (line) + issue count (bar)",
            meta_extra={"llm_xlsx": str(cons_xlsx if cons_xlsx.exists() else llm_xlsx)},
        )
        _plot_llm_issue_tag_distribution(
            cons_issue_counts,
            out_dir,
            cons_order,
            "LLM Consistency Issue-tag Distribution",
            "llm_consistency_cross_stagewise_tag_distribution",
            Path("llm") / "full" / "consistency",
            [
                ("ConflictCount", "Stage conflict", "#F4B6A4"),
                ("FactShiftCount", "Fact shift", "#F08A8B"),
                ("OtherCount", "Other", "#CFCFCF"),
            ],
            meta_extra={"llm_xlsx": str(cons_xlsx if cons_xlsx.exists() else llm_xlsx)},
        )
        _plot_llm_consistency_band(cons, out_dir, cons_order, "LLM Consistency (mean ± std)", meta_extra={"llm_xlsx": str(llm_xlsx)})
        _plot_llm_metric_model_lines(
            cons,
            out_dir,
            cons_order,
            "LLM Consistency (model lines)",
            "llm_consistency_cross_stagewise_lines",
            Path("llm") / "full" / "consistency",
            meta_extra={"llm_xlsx": str(cons_xlsx if cons_xlsx.exists() else llm_xlsx)},
        )
        _plot_llm_metric_heatmap(
            cons,
            out_dir,
            cons_order,
            "LLM Consistency (heatmap)",
            "llm_consistency_cross_stagewise_heatmap",
            Path("llm") / "full" / "consistency",
            meta_extra={"llm_xlsx": str(cons_xlsx if cons_xlsx.exists() else llm_xlsx)},
        )
        _plot_llm_metric_model_band(
            cons,
            out_dir,
            cons_order,
            "LLM Consistency (model band)",
            "llm_consistency_cross_stagewise_modelband",
            Path("llm") / "full" / "consistency",
            meta_extra={"llm_xlsx": str(cons_xlsx if cons_xlsx.exists() else llm_xlsx)},
        )

    # fact consistency
    cons_fact_df = _read(sheet_cons_fact, cons_xl)
    if not cons_fact_df.empty and {center_col, model_col, stage_col, cons_value}.issubset(cons_fact_df.columns):
        cons_fact = cons_fact_df.rename(
            columns={center_col: "Center", model_col: "Model", stage_col: "Stage", cons_value: "Value"}
        ).copy()
        if "样本数" in cons_fact_df.columns:
            cons_fact["Samples"] = pd.to_numeric(cons_fact_df["样本数"], errors="coerce")
        cons_fact["Stage"] = cons_fact["Stage"].map(_normalize_llm_stage)
        cons_order = ["D1_Decision", "D2_Decision", "D3_Decision", "D4_Plan"]
        cons_fact = cons_fact[cons_fact["Stage"].isin(cons_order)]
        cons_fact_detail = _read("一致性-事实-明细", cons_xl)
        fact_issue_counts = _aggregate_issue_tag_counts(
            cons_fact_detail,
            center_col,
            model_col,
            stage_col,
            cons_order,
            {
                "contradiction": "ContradictionCount",
                "hallucination": "HallucinationCount",
                "missing": "MissingCount",
                "unsupported_detail": "UnsupportedDetailCount",
            },
        )
        if not fact_issue_counts.empty:
            cons_fact = cons_fact.merge(fact_issue_counts, on=["Center", "Model", "Stage"], how="left")
        _plot_llm_stage_metric(
            cons_fact,
            value_col="Value",
            stage_order=cons_order,
            out_dir=out_dir,
            prefix="llm_consistency_fact_stagewise",
            title="LLM Fact Consistency (decision stages)",
            ylim=(0, 1),
            meta_extra={"llm_xlsx": str(cons_xlsx if cons_xlsx.exists() else llm_xlsx)},
        )
        _plot_llm_consistency_linebar(
            cons_fact,
            out_dir,
            cons_order,
            "LLM Fact Consistency (line+bars)",
            out_prefix="llm_consistency_fact_stagewise_linebar",
            description="Fact consistency (line) + sample count (bar)",
            meta_extra={"llm_xlsx": str(cons_xlsx if cons_xlsx.exists() else llm_xlsx)},
        )
        _plot_llm_issue_tag_distribution(
            fact_issue_counts,
            out_dir,
            cons_order,
            "LLM Fact-consistency Issue-tag Distribution",
            "llm_consistency_fact_stagewise_tag_distribution",
            Path("llm") / "full" / "consistency",
            [
                ("ContradictionCount", "Contradiction", "#D96C75"),
                ("HallucinationCount", "Hallucination", "#F3A683"),
                ("MissingCount", "Missing", "#7FB3D5"),
                ("UnsupportedDetailCount", "Unsupported detail", "#B39DDB"),
            ],
            meta_extra={"llm_xlsx": str(cons_xlsx if cons_xlsx.exists() else llm_xlsx)},
        )

    mem_df = _read(sheet_mem, mem_xl)
    if not mem_df.empty and {center_col, model_col, stage_col}.issubset(mem_df.columns):
        mem = mem_df.rename(columns={center_col: "Center", model_col: "Model", stage_col: "Stage"}).copy()
        for col in [mem_col_1, mem_col_2]:
            if col in mem.columns:
                mem[col] = pd.to_numeric(mem[col], errors="coerce")
        use_cols = [c for c in [mem_col_1, mem_col_2] if c in mem.columns]
        if use_cols:
            mem["Value"] = mem[use_cols].mean(axis=1, skipna=True)
            mem["Stage"] = mem["Stage"].map(_normalize_llm_stage)
            mem_order = ["D2_Decision", "D3_Decision", "D4_Plan"]
            mem = mem[mem["Stage"].isin(mem_order)]
            mem_detail = _read("记忆保持-明细", mem_xl)
            mem_issue_counts = _aggregate_issue_tag_counts(
                mem_detail,
                center_col,
                model_col,
                stage_col,
                mem_order,
                {
                    "missing_prior_info": "MissingPriorInfoCount",
                    "unused_key_info": "UnusedKeyInfoCount",
                    "other": "OtherCount",
                },
            )
            _plot_llm_stage_metric(
                mem,
                value_col="Value",
                stage_order=mem_order,
                out_dir=out_dir,
                prefix="llm_memory_stagewise",
                title="LLM Memory Retention (D2-D4 decisions)",
                ylim=(0, 1),
                meta_extra={"llm_xlsx": str(mem_xlsx if mem_xlsx.exists() else llm_xlsx)},
            )
            _plot_llm_memory_line(
                mem,
                out_dir,
                mem_order,
                "LLM Memory Retention (lines)",
                mem_col_1,
                mem_col_2,
                meta_extra={"llm_xlsx": str(mem_xlsx if mem_xlsx.exists() else llm_xlsx)},
            )
            _plot_llm_memory_linebar(
                mem,
                out_dir,
                mem_order,
                "LLM Memory Retention (line+bars)",
                mem_col_1,
                mem_col_2,
                meta_extra={"llm_xlsx": str(mem_xlsx if mem_xlsx.exists() else llm_xlsx)},
            )
            _plot_llm_memory_band(
                mem,
                out_dir,
                mem_order,
                "LLM Memory Retention (mean ± std)",
                mem_col_1,
                mem_col_2,
                meta_extra={"llm_xlsx": str(mem_xlsx if mem_xlsx.exists() else llm_xlsx)},
            )
            _plot_llm_metric_model_lines(
                mem,
                out_dir,
                mem_order,
                "LLM Memory Retention (model lines)",
                "llm_memory_stagewise_lines",
                Path("llm") / "full" / "memory",
                meta_extra={"llm_xlsx": str(mem_xlsx if mem_xlsx.exists() else llm_xlsx)},
            )
            _plot_llm_metric_heatmap(
                mem,
                out_dir,
                mem_order,
                "LLM Memory Retention (heatmap)",
                "llm_memory_stagewise_heatmap",
                Path("llm") / "full" / "memory",
                meta_extra={"llm_xlsx": str(mem_xlsx if mem_xlsx.exists() else llm_xlsx)},
            )
            _plot_llm_metric_model_band(
                mem,
                out_dir,
                mem_order,
                "LLM Memory Retention (model band)",
                "llm_memory_stagewise_modelband",
                Path("llm") / "full" / "memory",
                meta_extra={"llm_xlsx": str(mem_xlsx if mem_xlsx.exists() else llm_xlsx)},
            )
            _plot_llm_issue_tag_distribution(
                mem_issue_counts,
                out_dir,
                mem_order,
                "LLM Memory Issue-tag Distribution",
                "llm_memory_stagewise_tag_distribution",
                Path("llm") / "full" / "memory",
                [
                    ("MissingPriorInfoCount", "Missing prior info", "#E5989B"),
                    ("UnusedKeyInfoCount", "Unused key info", "#84A59D"),
                    ("OtherCount", "Other", "#CFCFCF"),
                ],
                meta_extra={"llm_xlsx": str(mem_xlsx if mem_xlsx.exists() else llm_xlsx)},
            )


def _plot_llm_small_scale_metrics(llm_small_xlsx: Path, out_dir: Path) -> None:
    if not llm_small_xlsx.exists():
        return
    try:
        xl = pd.ExcelFile(llm_small_xlsx)
    except Exception:
        return

    small_dir = out_dir / "llm" / "small" / "summary"
    _ensure_dir(small_dir)

    center_col_raw = "中心"
    model_col_raw = "被评测模型"
    stage_col_raw = "阶段"
    sample_col_raw = "小规模_样本数"

    def _draw_combined(df_plot: pd.DataFrame, value_cols: list[str], title: str, out_png: Path, ylim: tuple[float, float] | None = None) -> None:
        centers = _center_order(df_plot["Center"])
        models = _model_order(df_plot["Model"])
        fig, axes = plt.subplots(2, 2, figsize=(12, 12))
        axes_flat = axes.flatten()

        for idx, center in enumerate(centers):
            ax = axes_flat[idx]
            sub = df_plot[df_plot["Center"] == center].copy()
            if sub.empty:
                ax.axis("off")
                continue
            sub = sub.set_index("Model").reindex(models)
            x = np.arange(len(models), dtype=float)
            width = 0.8 / max(1, len(value_cols))
            color_list = ["#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F", "#EDC949", "#B07AA1", "#FF9DA7"]
            for i, col in enumerate(value_cols):
                vals = pd.to_numeric(sub[col], errors="coerce").to_numpy()
                bars = ax.bar(
                    x + (i - (len(value_cols) - 1) / 2) * width,
                    vals,
                    width=width,
                    color=color_list[i % len(color_list)],
                    label=col,
                )
                for b, v in zip(bars, vals):
                    if np.isnan(v):
                        continue
                    ax.text(b.get_x() + b.get_width() / 2, float(v) + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=6.5)
            ax.set_xticks(x)
            ax.set_xticklabels(models, rotation=24, ha="right")
            ax.set_title(CENTER_LABELS.get(center, center))
            ax.grid(axis="y", linestyle=":", alpha=0.25)
            if ylim is not None:
                ax.set_ylim(*ylim)

        for j in range(len(centers), len(axes_flat)):
            axes_flat[j].axis("off")
        handles, labels = axes_flat[0].get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="upper center", ncol=min(4, len(labels)), bbox_to_anchor=(0.5, 0.99), fontsize=8)
        fig.suptitle(title, y=0.995)
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(out_png, dpi=1200)
        plt.close(fig)

        _write_source_data(
            out_dir,
            out_png.stem,
            {"raw": df_plot, "plot_data": df_plot},
            {
                "figure": out_png.name,
                "description": title,
                "llm_small_xlsx": str(llm_small_xlsx),
            },
        )

    def _draw_topk_lines(df_plot: pd.DataFrame, out_png: Path, title: str) -> None:
        centers = _center_order(df_plot["Center"])
        models = _model_order(df_plot["Model"])
        fig, axes = plt.subplots(2, 2, figsize=(12, 12), sharey=True)
        axes_flat = axes.flatten()
        palette = {"k1": "#4E79A7", "k3": "#F28E2B", "k5": "#E15759"}
        for idx, center in enumerate(centers):
            ax = axes_flat[idx]
            sub = df_plot[df_plot["Center"] == center].copy()
            if sub.empty:
                ax.axis("off")
                continue
            sub = sub.set_index("Model").reindex(models)
            x = np.arange(len(models), dtype=float)
            if "k1" in sub.columns:
                ax.plot(x, sub["k1"].to_numpy(dtype=float), marker="o", color=palette["k1"], label="Top-1")
            if "k3" in sub.columns:
                ax.plot(x, sub["k3"].to_numpy(dtype=float), marker="s", color=palette["k3"], label="Top-3")
            if "k5" in sub.columns:
                ax.plot(x, sub["k5"].to_numpy(dtype=float), marker="D", color=palette["k5"], label="Top-5")
            for col, color in palette.items():
                if col in sub.columns:
                    for xi, yi in zip(x, sub[col].to_numpy(dtype=float)):
                        if np.isfinite(yi):
                            ax.text(xi, float(yi) + 0.01, f"{float(yi):.2f}", ha="center", va="bottom", fontsize=7, color=color)
            ax.set_xticks(x)
            ax.set_xticklabels(models, rotation=25, ha="right")
            ax.set_title(CENTER_LABELS.get(center, center))
            ax.grid(axis="y", linestyle=":", alpha=0.25)
            ax.set_ylim(0, 1)
        for j in range(len(centers), len(axes_flat)):
            axes_flat[j].axis("off")
        handles, labels = axes_flat[0].get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 0.99), fontsize=8)
        fig.suptitle(title, y=0.995)
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(out_png, dpi=1200)
        plt.close(fig)

        _write_source_data(
            out_dir,
            out_png.stem,
            {"raw": df_plot, "plot_data": df_plot},
            {
                "figure": out_png.name,
                "description": title,
                "llm_small_xlsx": str(llm_small_xlsx),
            },
        )

    def _draw_horizontal_bars(df_plot: pd.DataFrame, value_cols: list[str], title: str, out_png: Path) -> None:
        centers = _center_order(df_plot["Center"])
        models = _model_order(df_plot["Model"])
        fig, axes = plt.subplots(2, 2, figsize=(12, 12), sharex=True)
        axes_flat = axes.flatten()
        color_list = ["#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F", "#EDC949", "#B07AA1", "#FF9DA7"]
        for idx, center in enumerate(centers):
            ax = axes_flat[idx]
            sub = df_plot[df_plot["Center"] == center].copy()
            if sub.empty:
                ax.axis("off")
                continue
            sub = sub.set_index("Model").reindex(models)
            y = np.arange(len(models), dtype=float)
            height = 0.8 / max(1, len(value_cols))
            for i, col in enumerate(value_cols):
                vals = pd.to_numeric(sub[col], errors="coerce").to_numpy()
                ax.barh(
                    y + (i - (len(value_cols) - 1) / 2) * height,
                    vals,
                    height=height,
                    color=color_list[i % len(color_list)],
                    label=col,
                )
                for yi, v in zip(y, vals):
                    if np.isfinite(v):
                        ax.text(float(v) + 0.01, yi + (i - (len(value_cols) - 1) / 2) * height, f"{float(v):.2f}", va="center", fontsize=7)
            ax.set_yticks(y)
            ax.set_yticklabels(models)
            ax.set_xlim(0, 1)
            ax.grid(axis="x", linestyle=":", alpha=0.25)
            ax.set_title(CENTER_LABELS.get(center, center))
        for j in range(len(centers), len(axes_flat)):
            axes_flat[j].axis("off")
        handles, labels = axes_flat[0].get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="upper center", ncol=min(4, len(labels)), bbox_to_anchor=(0.5, 0.99), fontsize=8)
        fig.suptitle(title, y=0.995)
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(out_png, dpi=1200)
        plt.close(fig)

        _write_source_data(
            out_dir,
            out_png.stem,
            {"raw": df_plot, "plot_data": df_plot},
            {
                "figure": out_png.name,
                "description": title,
                "llm_small_xlsx": str(llm_small_xlsx),
            },
        )

    compat_rows: list[pd.DataFrame] = []

    for sheet in xl.sheet_names:
        if str(sheet).startswith("0_"):
            continue
        try:
            df = xl.parse(sheet)
        except Exception:
            continue
        if df.empty:
            continue

        center_col = center_col_raw if center_col_raw in df.columns else None
        model_col = model_col_raw if model_col_raw in df.columns else None
        if not center_col or not model_col:
            continue

        metric_cols = [
            c
            for c in df.columns
            if isinstance(c, str)
            and c.startswith("小规模_")
            and c.endswith("_均值")
            and ("样本" not in c)
            and ("sample" not in c.lower())
        ]
        if not metric_cols:
            metric_cols = [
                c
                for c in df.columns
                if c not in {center_col, model_col, stage_col_raw, "样本数", sample_col_raw}
                and ("样本" not in str(c))
                and ("sample" not in str(c).lower())
            ]

        if not metric_cols:
            continue

        for col in metric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        agg = (
            df[[center_col, model_col] + metric_cols]
            .groupby([center_col, model_col])[metric_cols]
            .mean(numeric_only=True)
            .reset_index()
            .rename(columns={center_col: "Center", model_col: "Model"})
        )
        if agg.empty:
            continue

        # Style selection
        if "TopK" in str(sheet) or any("k=" in str(c) for c in metric_cols):
            topk_cols = {}
            for col in metric_cols:
                if "k=1" in str(col):
                    topk_cols[col] = "k1"
                if "k=3" in str(col):
                    topk_cols[col] = "k3"
                if "k=5" in str(col):
                    topk_cols[col] = "k5"
            topk_df = agg.rename(columns=topk_cols)
            keep = ["Center", "Model"] + list(topk_cols.values())
            topk_df = topk_df[keep]
            out_png = small_dir / "llm_small_topk_lines_combined.png"
            _draw_topk_lines(topk_df, out_png, "LLM Small-scale TopK (line)")
            out_png_bar = small_dir / "llm_small_topk_bars_combined.png"
            _draw_combined(topk_df, ["k1", "k3", "k5"], "LLM Small-scale TopK (bar)", out_png_bar, ylim=(0, 1))
        else:
            out_png = small_dir / f"llm_small_{_slugify(sheet)}_bars_combined.png"
            _draw_horizontal_bars(agg, metric_cols, f"LLM Small-scale Metrics - {sheet}", out_png)

        for col in metric_cols:
            if "k=1" in str(col):
                key = "llm_small_TopK_k_1_GT_0_1"
            elif "k=3" in str(col):
                key = "llm_small_TopK_k_3_GT_0_1"
            elif "k=5" in str(col):
                key = "llm_small_TopK_k_5_GT_0_1"
            elif "(0-1)" in str(col) or "(0/1)" in str(col):
                key = "llm_small_metric_0_1"
            elif "(0-5)" in str(col):
                key = "llm_small_metric_0_5"
            else:
                key = "llm_small_metric_metric"
            part = agg[["Center", "Model", col]].rename(columns={col: "Value"}).copy()
            part["MetricGroup"] = key
            part["MetricName"] = col
            compat_rows.append(part)

    if not compat_rows:
        return

    compat = pd.concat(compat_rows, ignore_index=True)
    grouped = compat.groupby(["Center", "Model", "MetricGroup"], as_index=False)["Value"].mean(numeric_only=True)

    for metric_group in sorted(grouped["MetricGroup"].dropna().unique().tolist()):
        gdf = grouped[grouped["MetricGroup"] == metric_group].copy()
        if gdf.empty:
            continue
        plot_df = gdf.rename(columns={"Value": metric_group})
        out_png = small_dir / f"{metric_group}_combined.png"
        ylim = (0, 5) if "0_5" in metric_group else (0, 1)
        _draw_horizontal_bars(plot_df.rename(columns={metric_group: "Value"}), ["Value"], f"{metric_group} (small-scale combined)", out_png)
        _write_source_data(
            out_dir,
            f"{metric_group}_combined",
            {
                "detail": compat[compat["MetricGroup"] == metric_group],
                "agg": gdf,
                "pivot": gdf.pivot_table(index="Model", columns="Center", values="Value", aggfunc="mean").reset_index(),
            },
            {
                "figure": out_png.name,
                "description": "Small-scale compatibility aggregate (combined)",
                "metric_group": metric_group,
                "llm_small_xlsx": str(llm_small_xlsx),
            },
        )
