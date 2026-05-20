"""构建 v2 组图与子图（G1/G2/G3/G4/S1），并输出一图一源数据工作簿。

核心约束（按用户要求）：
1) 检查相关计算将 D1 决策检查并入 D2Loop。
2) D1 anomaly 不参与计算。
3) Gate3 fail 的 D4 不参与计算。
4) 每个图生成 source data（至少含明细+汇总+meta）。
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
from datetime import datetime
from difflib import SequenceMatcher
from html import unescape as html_unescape
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
import openpyxl
import pandas as pd
from matplotlib import font_manager
from matplotlib.colors import to_hex, to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch
from matplotlib.ticker import MultipleLocator
from matplotlib.transforms import Bbox
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill

try:
    import plotly.graph_objects as go
except Exception:  # pragma: no cover
    go = None

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None

try:
    from docx import Document
except Exception:  # pragma: no cover
    Document = None


ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_VIZ = ROOT / "analysis_viz"
PLOTLY_TMP_DIR = ANALYSIS_VIZ / "tmp_kaleido"

RAW_DIR = ANALYSIS_VIZ / "data" / "raw"
DERIVED_METRICS_DIR = ANALYSIS_VIZ / "data" / "derived" / "metrics"
PAPER_FIGDATA_DIR = ANALYSIS_VIZ / "data" / "derived" / "figdata" / "paper"
CENTER_DATA_DIR = RAW_DIR / "center_data"
DOCTOR_EVAL_RESULTS_DIR = RAW_DIR / "doctor_eval_results"
LIVING_REVISION_DIR = ROOT / "论文" / "revision" / "living"

OUT_FIG_DIR = ANALYSIS_VIZ / "figures" / "v2_subplots"
OUT_DATA_DIR = ANALYSIS_VIZ / "data" / "derived" / "figdata" / "v2_subplots"
OUT_SUPPLE_DIR = OUT_FIG_DIR / "_supplementary"
G1_DERIVED_DIR = OUT_DATA_DIR / "G1_dataset"
G1_LLM_TAXONOMY_CSV = G1_DERIVED_DIR / "G1_llm_case_taxonomy_v1.csv"
G1_LLM_PALM_LONG_CSV = G1_DERIVED_DIR / "G1_llm_palm_stage_detail_v1.csv"
G1_LLM_PLAN_LONG_CSV = G1_DERIVED_DIR / "G1_llm_plan_stage_detail_v1.csv"

RAW_METRICS_SOURCE = RAW_DIR / "metrics_source_data.xlsx"
RAW_DOCTOR_SUMMARY = RAW_DIR / "医生评测汇总.xlsx"

MODEL_SHORT = {
    "deepseek-v3-1-think-250821": "deepseek-v3",
    "gpt-5-2025-08-07": "gpt-5",
    "gemini-2.5-pro": "gemini-2.5p",
    "grok-4": "grok-4",
    "claude-opus-4-1-20250805-thinking": "claude-4.1",
}
MODEL_ORDER = ["deepseek-v3", "gpt-5", "gemini-2.5p", "grok-4", "claude-4.1"]
MODEL_MARKER = {
    "deepseek-v3": "s",
    "gpt-5": "^",
    "gemini-2.5p": "o",
    "grok-4": "D",
    "claude-4.1": "*",
}
MODEL_COLOR = {
    "deepseek-v3": "#2ca02c",
    "gpt-5": "#9467bd",
    "gemini-2.5p": "#d62728",
    "grok-4": "#ff7f0e",
    "claude-4.1": "#17becf",
}

_STYLE_READY = False

STAGE6_CN = {
    "D1_Loop": "门诊检查",
    "D1_Decision": "门诊决策",
    "D2_Loop": "住院检查",
    "D2_Decision": "住院决策",
    "D3_Decision": "术后决策",
    "D4_Plan": "随访与康复计划",
}
STAGE6_ORDER = ["D1_Loop", "D1_Decision", "D2_Loop", "D2_Decision", "D3_Decision", "D4_Plan"]
STAGE4_ORDER = ["D1", "D2", "D3", "D4"]
STAGE4_CN = {"D1": "D1 门诊", "D2": "D2 住院", "D3": "D3 术后", "D4": "D4 随访"}
CENTER_ORDER_CN = ["佛山", "武汉", "新疆"]
CAPTION_FILE_BY_GROUP = {
    "G1_dataset": "图注_Figure_G1_数据集概览.md",
    "G2_outcome": "图注_Figure_G2_结局表现.md",
    "G3_continuity": "图注_Figure_G3_连续性表现.md",
    "G4_system": "图注_Figure_G4_系统评估.md",
    "S1_manual_vs_llm": "图注_Figure_S1_医生与Judge对比.md",
    "A0_consistency_tables": "图注_Figure_A0_一致性与案例研究.md",
}
DOCTOR_PREFIX_TO_STAGE6 = {
    "门诊A": "D1_Loop",
    "门诊B": "D1_Decision",
    "住院A": "D2_Loop",
    "住院B": "D2_Decision",
    "术后": "D3_Decision",
    "康复": "D4_Plan",
}
STAGE6_TO_STAGE4 = {
    "D1_Loop": "D1",
    "D1_Decision": "D1",
    "D2_Loop": "D2",
    "D2_Decision": "D2",
    "D3_Decision": "D3",
    "D4_Plan": "D4",
}

PALM_COEIN_ORDER = [
    "P-息肉",
    "A-腺肌症",
    "L-肌瘤",
    "M-恶性/增生",
    "C-凝血相关",
    "O-排卵障碍",
    "E-子宫内膜原因",
    "I-医源性",
    "N-非肿瘤",
    "数据缺失",
    "不适用",
]
PALM_COEIN_COLOR = {
    "P-息肉": "#4C78A8",
    "A-腺肌症": "#72B7B2",
    "L-肌瘤": "#59A14F",
    "M-恶性/增生": "#C44E52",
    "C-凝血相关": "#B279A2",
    "O-排卵障碍": "#F28E2B",
    "E-子宫内膜原因": "#E15759",
    "I-医源性": "#9D7660",
    "N-非肿瘤": "#A0A0A0",
    "数据缺失": "#AEB6C2",
    "不适用": "#7A7A7A",
}

PALM_CLASS_TO_LABEL = {
    1: "P-息肉",
    2: "A-腺肌症",
    3: "L-肌瘤",
    4: "M-恶性/增生",
    5: "C-凝血相关",
    6: "O-排卵障碍",
    7: "E-子宫内膜原因",
    8: "I-医源性",
    9: "N-非肿瘤",
}

PLAN_CLASS_TO_LABEL = {
    1: "手术处置",
    2: "药物/内分泌治疗",
    3: "检查/监测",
    4: "康复/护理",
    5: "随访管理",
    6: "无/未提及",
    7: "其他",
}
PLAN_STAGE_ORDER = ["Surgery", "PostOp", "Rehab", "Followup"]
PLAN_STAGE_LABEL = {"Surgery": "手术方案", "PostOp": "术后方案", "Rehab": "康复方案", "Followup": "随访方案"}
PLAN_LABEL_ORDER = ["手术处置", "药物/内分泌治疗", "检查/监测", "康复/护理", "随访管理", "其他", "无/未提及"]
PLAN_LABEL_COLOR = {
    "手术处置": "#4C78A8",
    "药物/内分泌治疗": "#F28E2B",
    "检查/监测": "#59A14F",
    "康复/护理": "#76B7B2",
    "随访管理": "#9C755F",
    "其他": "#8C8C8C",
    "无/未提及": "#A6A6A6",
}

PREG_RELATED_PAT = re.compile(
    r"(妊娠|流产|异位妊娠|宫外孕|先兆流产|稽留流产|胚胎|胎停|葡萄胎|妊娠物|产后)",
    re.IGNORECASE,
)
D2_NONE_PAT = re.compile(r"^\s*(修正诊断[:：])?\s*无\s*$", re.IGNORECASE)


def _configure_fonts() -> None:
    candidates = [
        ("C:/Windows/Fonts/msyh.ttc", "Microsoft YaHei"),
        ("C:/Windows/Fonts/msyhbd.ttc", "Microsoft YaHei"),
        ("C:/Windows/Fonts/msyhui.ttf", "Microsoft YaHei UI"),
        ("C:/Windows/Fonts/simhei.ttf", "SimHei"),
        ("C:/Windows/Fonts/simsun.ttc", "SimSun"),
        ("C:/Windows/Fonts/arialuni.ttf", "Arial Unicode MS"),
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
        available = ["Microsoft YaHei", "Microsoft YaHei UI", "SimHei", "Arial Unicode MS", "Noto Sans CJK SC"]
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = (
        available
        + ["Noto Sans CJK SC", "Source Han Sans CN", "WenQuanYi Zen Hei", "DejaVu Sans", "Arial Unicode MS"]
    )
    plt.rcParams["axes.unicode_minus"] = False


def _apply_style() -> None:
    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except Exception:
        pass
    _configure_fonts()
    plt.rcParams.update(
        {
            "axes.spines.top": False,
            "axes.spines.right": False,
            "grid.alpha": 0.28,
            "grid.linestyle": "--",
            "figure.dpi": 180,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    mpl.rcParams["svg.fonttype"] = "none"
    mpl.rcParams["pdf.fonttype"] = 42
    mpl.rcParams["ps.fonttype"] = 42


def _ensure_plotly_temp_dir() -> None:
    if go is None:
        return
    PLOTLY_TMP_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = str(PLOTLY_TMP_DIR.resolve())
    for env_key in ("TMPDIR", "TMP", "TEMP"):
        os.environ[env_key] = tmp_path


def _ensure_style() -> None:
    global _STYLE_READY
    if _STYLE_READY:
        return
    _ensure_plotly_temp_dir()
    _apply_style()
    _STYLE_READY = True


def _safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _is_preg_related_diag(text: Any) -> bool:
    t = str(text or "").strip()
    if t == "" or t.lower() in {"nan", "none"}:
        return False
    return bool(PREG_RELATED_PAT.search(t))


def _is_d2_none_diag(text: Any) -> bool:
    t = str(text or "").strip()
    if t == "" or t.lower() in {"nan", "none"}:
        return True
    if D2_NONE_PAT.search(t):
        return True
    return False


def _adjust_palm_label_by_rule(stage4: str, diag_text: Any, raw_label: str) -> tuple[str, str]:
    label = str(raw_label or "").strip()
    if label == "":
        label = "N-非肿瘤"
    if _is_preg_related_diag(diag_text):
        return "不适用", "妊娠相关诊断不纳入PALM-COEIN"
    if stage4 == "D2" and _is_d2_none_diag(diag_text):
        return "沿用上轮", "修正诊断为“无”或空值，按沿用上一轮处理"
    if label not in PALM_COEIN_ORDER:
        return "N-非肿瘤", "标签归一化到N-非肿瘤"
    return label, ""


def _replace_d2_follow_with_previous_label(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty or not {"stage4", "palm_coein"}.issubset(detail.columns):
        return detail
    out = detail.copy()
    group_cols = [c for c in ["center", "source_model", "model", "model_short", "case_id"] if c in out.columns]
    if "case_id" not in group_cols:
        return out
    d1_cols = group_cols + ["palm_coein"]
    d1_map = (
        out[out["stage4"].astype(str).eq("D1")][d1_cols]
        .drop_duplicates(subset=group_cols, keep="first")
        .rename(columns={"palm_coein": "d1_palm_coein"})
    )
    if d1_map.empty:
        return out
    out = out.merge(d1_map, on=group_cols, how="left")
    mask = out["stage4"].astype(str).eq("D2") & out["palm_coein"].astype(str).eq("沿用上轮")
    repl = out["d1_palm_coein"].astype(str)
    valid_repl = repl.isin(PALM_COEIN_ORDER + ["不适用", "数据缺失"])
    out.loc[mask & valid_repl, "palm_coein"] = repl[mask & valid_repl]
    out.loc[mask & (~valid_repl), "palm_coein"] = "N-非肿瘤"
    return out.drop(columns=["d1_palm_coein"], errors="ignore")


def _map_icd10_chapter(code: Any) -> tuple[str, str]:
    raw = str(code or "").strip().upper()
    if raw == "" or raw in {"NAN", "NONE"}:
        return "U00-U99", "Codes for special purposes/Unknown"
    m = re.match(r"^([A-Z])(\d{2})?", raw)
    if not m:
        return "U00-U99", "Codes for special purposes/Unknown"
    letter = m.group(1)
    num = int(m.group(2)) if m.group(2) else None
    if letter in {"A", "B"}:
        return "A00-B99", "Certain infectious and parasitic diseases"
    if letter == "C":
        return "C00-D48", "Neoplasms"
    if letter == "D":
        if num is not None and num >= 50:
            return "D50-D89", "Diseases of the blood and blood-forming organs"
        return "C00-D48", "Neoplasms"
    if letter == "E":
        return "E00-E90", "Endocrine, nutritional and metabolic diseases"
    if letter == "F":
        return "F00-F99", "Mental and behavioural disorders"
    if letter == "G":
        return "G00-G99", "Diseases of the nervous system"
    if letter == "H":
        if num is not None and num >= 60:
            return "H60-H95", "Diseases of the ear and mastoid process"
        return "H00-H59", "Diseases of the eye and adnexa"
    if letter == "I":
        return "I00-I99", "Diseases of the circulatory system"
    if letter == "J":
        return "J00-J99", "Diseases of the respiratory system"
    if letter == "K":
        return "K00-K93", "Diseases of the digestive system"
    if letter == "L":
        return "L00-L99", "Diseases of the skin and subcutaneous tissue"
    if letter == "M":
        return "M00-M99", "Diseases of the musculoskeletal system"
    if letter == "N":
        return "N00-N99", "Diseases of the genitourinary system"
    if letter == "O":
        return "O00-O99", "Pregnancy, childbirth and the puerperium"
    if letter == "P":
        return "P00-P96", "Certain conditions originating in the perinatal period"
    if letter == "Q":
        return "Q00-Q99", "Congenital malformations, deformations and chromosomal abnormalities"
    if letter == "R":
        return "R00-R99", "Symptoms, signs and abnormal clinical findings"
    if letter in {"S", "T"}:
        return "S00-T98", "Injury, poisoning and certain other consequences of external causes"
    if letter in {"V", "W", "X", "Y"}:
        return "V01-Y98", "External causes of morbidity and mortality"
    if letter == "Z":
        return "Z00-Z99", "Factors influencing health status and contact with health services"
    return "U00-U99", "Codes for special purposes/Unknown"


def _build_icd_chapter_from_llm_taxonomy(llm_taxonomy: pd.DataFrame) -> pd.DataFrame:
    if llm_taxonomy.empty or "final_icd10_code" not in llm_taxonomy.columns:
        return pd.DataFrame()
    use = llm_taxonomy.copy()
    use["final_icd10_code"] = use["final_icd10_code"].astype(str).str.strip().str.upper()
    use = use[use["final_icd10_code"].astype(str) != ""].copy()
    if use.empty:
        return pd.DataFrame()
    if "final_icd10_name" not in use.columns:
        use["final_icd10_name"] = ""
    use["final_icd10_name"] = use["final_icd10_name"].astype(str).replace({"nan": "", "None": ""})
    icd = (
        use.groupby(["final_icd10_code", "final_icd10_name"], as_index=False)
        .agg(Cases=("case_id", "nunique"))
        .sort_values("Cases", ascending=False, kind="mergesort")
    )
    icd = icd.rename(columns={"final_icd10_code": "ICD10Code", "final_icd10_name": "ICD10Name"})
    return icd


def _save_matplotlib_sidecars(
    fig: plt.Figure,
    path: Path,
    bbox_inches: Any = "tight",
    facecolor: str | None = None,
) -> dict[str, Path]:
    """Save Illustrator-friendly vector sidecars for PNG figure outputs."""
    out: dict[str, Path] = {}
    if path.suffix.lower() != ".png":
        return out
    for fmt in ("svg", "pdf"):
        sidecar = path.with_suffix(f".{fmt}")
        try:
            save_kwargs: dict[str, Any] = {
                "format": fmt,
                "bbox_inches": bbox_inches,
            }
            if facecolor is not None:
                save_kwargs["facecolor"] = facecolor
            fig.savefig(sidecar, **save_kwargs)
            out[fmt] = sidecar
        except Exception as exc:
            print(f"[WARN] failed to save vector sidecar for {path.name}: {fmt}: {exc}")
    return out


def _save_plotly_image_bundle(fig: Any, out_path: Path, scale: int = 1) -> bool:
    """Save Plotly PNG plus native SVG/PDF sidecars when Kaleido is available."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.write_image(str(out_path), scale=max(1, int(scale)))
        if out_path.suffix.lower() == ".png":
            for fmt in ("svg", "pdf"):
                sidecar = out_path.with_suffix(f".{fmt}")
                try:
                    fig.write_image(str(sidecar), format=fmt, scale=max(1, int(scale)))
                except TypeError:
                    fig.write_image(str(sidecar), scale=max(1, int(scale)))
                except Exception as exc:
                    print(f"[WARN] failed to save Plotly vector sidecar for {out_path.name}: {fmt}: {exc}")
        stale_html = out_path.with_suffix(".html")
        if stale_html.exists():
            try:
                stale_html.unlink()
            except Exception:
                pass
        return True
    except Exception:
        return False


def _save_fig(path: Path, apply_tight: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.gcf()
    if apply_tight and (not bool(fig.get_constrained_layout())):
        plt.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    _save_matplotlib_sidecars(fig, path, bbox_inches="tight")
    plt.close()


def _archive_existing_output(path: Path, kind: str = "figures") -> None:
    """在覆盖写入前把既有产物备份到 archive 子目录。"""
    if not path.exists():
        return
    archive_dir = path.parent / "archive" / kind
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = archive_dir / f"{path.stem}_{ts}{path.suffix}"
    try:
        shutil.copy2(str(path), str(dst))
    except Exception:
        pass


def _draw_image_panel(ax: plt.Axes, image_path: Path, title: str = "", aspect: str = "equal") -> None:
    def _crop_image_whitespace(img: np.ndarray) -> np.ndarray:
        try:
            arr = np.asarray(img)
            if arr.ndim == 2:
                mask = arr < 0.985
            else:
                rgb = arr[..., :3]
                mask = np.any(rgb < 0.985, axis=2)
                if arr.shape[-1] >= 4:
                    alpha = arr[..., 3]
                    # 仅在图像存在透明背景时使用 alpha 参与裁剪；
                    # 若 alpha 全为 1（纯不透明画布），直接用 alpha 会导致整张图被视为“非空白”。
                    try:
                        if float(np.nanmin(alpha)) < 0.99:
                            mask = mask | (alpha > 0.02)
                    except Exception:
                        pass
            ys, xs = np.where(mask)
            if len(ys) == 0 or len(xs) == 0:
                return arr
            y0, y1 = ys.min(), ys.max()
            x0, x1 = xs.min(), xs.max()
            pad_y = max(2, int((y1 - y0 + 1) * 0.02))
            pad_x = max(2, int((x1 - x0 + 1) * 0.02))
            y0 = max(0, y0 - pad_y)
            y1 = min(arr.shape[0] - 1, y1 + pad_y)
            x0 = max(0, x0 - pad_x)
            x1 = min(arr.shape[1] - 1, x1 + pad_x)
            return arr[y0 : y1 + 1, x0 : x1 + 1]
        except Exception:
            return img

    if image_path.exists():
        try:
            img = plt.imread(image_path)
            img = _crop_image_whitespace(img)
            ax.imshow(img, aspect=aspect, interpolation="none")
        except Exception:
            ax.text(0.5, 0.5, f"无法读取图片:\n{image_path.name}", ha="center", va="center", fontsize=10)
    else:
        ax.text(0.5, 0.5, f"图片不存在:\n{image_path.name}", ha="center", va="center", fontsize=10)
    ax.axis("off")
    if title:
        ax.set_title(title, fontsize=12, pad=10)


def _set_full_axis_border(ax: plt.Axes, color: str = "#1F1F1F", lw: float = 1.1) -> None:
    for side in ["top", "right", "left", "bottom"]:
        ax.spines[side].set_visible(True)
        ax.spines[side].set_color(color)
        ax.spines[side].set_linewidth(lw)


def _apply_stage_progress_blocks(
    ax: plt.Axes,
    palette: list[str] | None = None,
    alpha: float = 0.22,
) -> None:
    """S1 背景分段：六个子环节渐进加深，并强调阶段交界。"""
    colors = palette or ["#F9FBFF", "#F1F6FE", "#E8F0FC", "#DFEAF9", "#D5E3F6", "#CCDCF3"]
    if len(colors) < 6:
        colors = (colors + [colors[-1]] * 6)[:6]
    blocks = [(-0.5, 0.5), (0.5, 1.5), (1.5, 2.5), (2.5, 3.5), (3.5, 4.5), (4.5, 5.5)]
    for (x0, x1), c in zip(blocks, colors):
        ax.axvspan(x0, x1, color=c, alpha=alpha, zorder=0)
    # 所有子环节边界（清晰可见）
    for cut in [0.5, 1.5, 2.5, 3.5, 4.5]:
        ax.axvline(cut, color="#93A9C5", linewidth=1.35, alpha=0.98, zorder=0.92)
    # 关键阶段交界线（强调）
    for cut in [1.5, 3.5]:
        ax.axvline(cut, color="#6F88A7", linewidth=2.05, alpha=0.99, zorder=0.97)


def _apply_s1_group_blocks(
    ax: plt.Axes,
    colors: list[str],
    labels: list[str] | None = None,
    alpha: float = 0.26,
) -> None:
    """按参考图7样式，将六个环节分成三段背景块并标注阶段。"""
    groups = [(-0.5, 1.5), (1.5, 3.5), (3.5, 5.5)]
    text_labels = labels or ["门诊阶段", "住院阶段", "术后与随访阶段"]
    for (x0, x1), c in zip(groups, colors):
        ax.axvspan(x0, x1, color=c, alpha=alpha, zorder=0.05)
    for cut in [1.5, 3.5]:
        ax.axvline(cut, color="#8D97A3", linewidth=1.2, alpha=0.9, zorder=0.2)
    for (x0, x1), t in zip(groups, text_labels):
        ax.text(
            (x0 + x1) / 2.0,
            0.965,
            t,
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=9,
            color="#5A616B",
        )


def _blend_hex_color(color_a: str, color_b: str, t: float) -> str:
    t = float(np.clip(t, 0.0, 1.0))
    ra = np.array(to_rgb(color_a), dtype=float)
    rb = np.array(to_rgb(color_b), dtype=float)
    return to_hex((1.0 - t) * ra + t * rb)


def _apply_s1_gradient_blocks(
    ax: plt.Axes,
    colors: list[str],
    labels: list[str] | None = None,
    alpha: float = 0.22,
    steps: int = 64,
) -> None:
    """S1 三段背景柔和过渡：门诊(2点)/入院(2点)/术后与随访(2点)，不画边界线。"""
    groups = [(-0.5, 1.5), (1.5, 3.5), (3.5, 5.5)]
    base = (colors + [colors[-1]] * 3)[:3]
    # 通过 [c0->c1], [c1->c2], [c2->c2] 三段保证边界处连续过渡
    grad_seq = [base[0], base[1], base[2], base[2]]
    text_labels = labels or ["门诊阶段", "入院阶段", "术后与随访阶段"]
    n_steps = max(12, int(steps))
    for idx, (x0, x1) in enumerate(groups):
        c0 = grad_seq[idx]
        c1 = grad_seq[idx + 1]
        seg_w = (x1 - x0) / float(n_steps)
        for k in range(n_steps):
            t = k / max(1, n_steps - 1)
            cc = _blend_hex_color(c0, c1, t)
            xx0 = x0 + k * seg_w
            xx1 = x0 + (k + 1) * seg_w
            ax.axvspan(xx0, xx1, color=cc, alpha=alpha, linewidth=0, edgecolor="none", zorder=0.02)
    for (x0, x1), t in zip(groups, text_labels):
        ax.text(
            (x0 + x1) / 2.0,
            0.965,
            t,
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=9,
            color="#626A73",
        )


def _panel_axes_list(panel: Any) -> list[plt.Axes]:
    if panel is None:
        return []
    if isinstance(panel, (list, tuple, set)):
        return [ax for ax in panel if ax is not None]
    return [panel]


def _save_subfigures(fig: plt.Figure, group: str, panel_axes: dict[str, Any]) -> dict[str, Path]:
    """从组图中裁切并导出子图。"""
    out: dict[str, Path] = {}
    if not panel_axes:
        return out
    all_axes = list(fig.axes)
    for panel_name, panel in panel_axes.items():
        axes = _panel_axes_list(panel)
        if not axes:
            continue
        sub_path = OUT_FIG_DIR / group / f"{panel_name}.png"
        sub_path.parent.mkdir(parents=True, exist_ok=True)
        old_visibility = {axis: axis.get_visible() for axis in all_axes}
        try:
            # Hide unrelated axes while saving, otherwise Matplotlib may serialize
            # off-bbox raster panels into the SVG as data:image/png;base64.
            for axis in all_axes:
                axis.set_visible(axis in axes)
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            bboxes = [axis.get_tightbbox(renderer) for axis in axes]
            bbox = Bbox.union([box for box in bboxes if box is not None])
            bbox_inches = bbox.transformed(fig.dpi_scale_trans.inverted()).expanded(1.08, 1.15)
            fig.savefig(sub_path, dpi=300, bbox_inches=bbox_inches, facecolor="white")
            _save_matplotlib_sidecars(fig, sub_path, bbox_inches=bbox_inches, facecolor="white")
            out[panel_name] = sub_path
        except Exception:
            continue
        finally:
            for axis, visible in old_visibility.items():
                axis.set_visible(visible)
            try:
                fig.canvas.draw()
            except Exception:
                pass
    return out


def _autosize(ws: openpyxl.worksheet.worksheet.Worksheet) -> None:
    max_width: dict[int, int] = {}
    for row in ws.iter_rows(values_only=True):
        for idx, value in enumerate(row, start=1):
            if value is None:
                continue
            s = str(value)
            max_width[idx] = max(max_width.get(idx, 0), min(60, len(s) + 2))
    for idx, width in max_width.items():
        col = openpyxl.utils.get_column_letter(idx)
        ws.column_dimensions[col].width = max(10, float(width))


def _style_workbook(path: Path) -> None:
    wb = openpyxl.load_workbook(path)
    red_bold = Font(color="FF0000", bold=True)
    header_fill = PatternFill(fill_type="solid", fgColor="E8F0FB")
    key_fill = PatternFill(fill_type="solid", fgColor="F8FBFF")
    raw_fill = PatternFill(fill_type="solid", fgColor="FFF8E8")
    calc_fill = PatternFill(fill_type="solid", fgColor="EEF8FF")
    formula_fill = PatternFill(fill_type="solid", fgColor="FDF2FF")
    result_fill = PatternFill(fill_type="solid", fgColor="EEF8EF")
    header_font = Font(color="1F2D3D", bold=True)
    for ws in wb.worksheets:
        if ws.max_row < 1 or ws.max_column < 1:
            continue
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            h = str(cell.value or "").lower()
            if ("原始" in h) or ("raw" in h):
                cell.fill = raw_fill
            elif ("计算" in h) or ("calc" in h):
                cell.fill = calc_fill
            elif ("公式" in h) or ("formula" in h):
                cell.fill = formula_fill
            elif ("结果" in h) or ("summary" in h) or ("汇总" in h):
                cell.fill = result_fill
        # 首列通常为 source_table，做轻量高亮，便于定位来源
        for r in range(2, ws.max_row + 1):
            c = ws.cell(row=r, column=1)
            c.fill = key_fill
            c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        for col_idx in range(1, ws.max_column + 1):
            col = openpyxl.utils.get_column_letter(col_idx)
            rng = f"{col}2:{col}{ws.max_row}"
            has_num = False
            for row in ws[rng]:
                for cell in row:
                    if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                        has_num = True
                        break
                if has_num:
                    break
            if has_num:
                ws.conditional_formatting.add(
                    rng,
                    CellIsRule(operator="equal", formula=[f"MAX({rng})"], font=red_bold),
                )
        _autosize(ws)
    wb.save(path)
    wb.close()


def _to_cn_sheet_name(name: str) -> str:
    s = str(name or "")
    repl_prefix = [
        ("d_", "明细_"),
        ("c_", "计算_"),
        ("s_", "汇总_"),
        ("f_", "公式_"),
        ("table_", "表_"),
    ]
    for a, b in repl_prefix:
        if s.startswith(a):
            s = b + s[len(a) :]
            break
    for a, b in [
        ("detail_", "明细_"),
        ("calculate_", "计算_"),
        ("summary_", "汇总_"),
        ("formula_", "公式_"),
        ("outcome", "结果"),
        ("system", "系统"),
        ("manual", "人工"),
        ("memory", "记忆"),
        ("consistency", "一致性"),
        ("reasoning", "推理"),
        ("diagnosis", "诊断"),
        ("reason", "逻辑"),
        ("result", "结果"),
        ("sankey", "桑基"),
        ("calib", "校准"),
        ("check", "检查"),
        ("score", "评分"),
        ("events", "事件"),
        ("event", "事件"),
        ("model", "模型"),
        ("stage", "阶段"),
        ("case", "病例"),
        ("center", "中心"),
        ("nodes", "节点"),
        ("links", "连线"),
        ("bins", "分箱"),
        ("fact", "事实"),
        ("cross", "跨阶段"),
        ("table", "表"),
        ("bin", "分箱"),
        ("overview", "总览"),
        ("special", "特殊"),
        ("count", "计数"),
        ("stats", "统计"),
        ("raw", "原始"),
        ("used", "已用"),
    ]:
        s = s.replace(a, b)
    for a, b in [("g1", "G1"), ("g2", "G2"), ("g3", "G3"), ("g4", "G4"), ("s1", "S1")]:
        s = re.sub(fr"(?:(?<=^)|(?<=_)){a}(?:(?=$)|(?=_))", b, s, flags=re.IGNORECASE)
    # 缩写仅按分隔符命中，避免 reason -> 推理son 这类误替换
    for a, b in [("mem", "记忆"), ("cons", "一致"), ("rea", "推理"), ("diag", "诊断"), ("plan", "方案"), ("comp", "合成"), ("bool", "布尔")]:
        s = re.sub(fr"(?:(?<=^)|(?<=_)){a}(?:(?=$)|(?=_))", b, s, flags=re.IGNORECASE)
    # Excel sheet name 不允许部分字符
    s = re.sub(r"[:\\/?*\[\]]+", "_", s).strip()
    if s == "":
        s = "表"
    return s


def _build_sheet_name_map(sheet_names: list[str], explicit_alias: dict[str, str] | None = None) -> dict[str, str]:
    explicit_alias = explicit_alias or {}
    out: dict[str, str] = {}
    used: set[str] = set()
    for old in sheet_names:
        base = explicit_alias.get(old) or _to_cn_sheet_name(old)
        base = base[:31]
        candidate = base
        idx = 1
        while candidate in used:
            suffix = f"_{idx}"
            candidate = (base[: max(1, 31 - len(suffix))] + suffix)[:31]
            idx += 1
        out[old] = candidate
        used.add(candidate)
    return out


def _rewrite_formula_sheet_refs(df: pd.DataFrame, sheet_name_map: dict[str, str]) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        return out
    obj_cols = [c for c in out.columns if out[c].dtype == object]
    if not obj_cols:
        return out

    def _guard_formula_text(s: str) -> str:
        t = str(s or "").strip()
        if not t.startswith("="):
            return t
        expr = t[1:].strip()
        if expr.upper().startswith("IFERROR("):
            return t
        return f'=IFERROR({expr},"")'

    for c in obj_cols:
        def _fix(v: Any) -> Any:
            if not (isinstance(v, str) and v.startswith("=")):
                return v
            s = v
            for old, new in sheet_name_map.items():
                s = s.replace(f"'{old}'!", f"'{new}'!")
                s = s.replace(f"{old}!", f"'{new}'!")
            return _guard_formula_text(s)
        out[c] = out[c].map(_fix)
    return out


def _cleanup_side_source_versions(fig_side: Path, stem: str, suffix: str, keep: int = 1) -> None:
    files = sorted(
        [p for p in fig_side.glob(f"{stem}*{suffix}") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if len(files) <= keep:
        return
    for p in files[keep:]:
        try:
            p.unlink()
        except Exception:
            pass


def _build_blue_shades(labels: list[str], fixed_last: dict[str, str] | None = None) -> dict[str, str]:
    fixed_last = fixed_last or {}
    dynamic = [x for x in labels if x not in fixed_last]
    if dynamic:
        shades = np.linspace(0.35, 0.95, len(dynamic))
        cmap = plt.get_cmap("Blues")
        base = {k: to_hex(cmap(float(v))) for k, v in zip(dynamic, shades)}
    else:
        base = {}
    base.update(fixed_last)
    return base


def _build_circle_legend_handles(labels: list[str], color_map: dict[str, str], marker_size: float = 8.0) -> list[Line2D]:
    handles: list[Line2D] = []
    for label in labels:
        handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="None",
                markerfacecolor=color_map.get(label, "#7FA7D1"),
                markeredgecolor="none",
                markersize=marker_size,
                label=str(label),
            )
        )
    return handles


def _build_model_legend_handles(models: list[str] | None = None, marker_size: float = 7.0) -> list[Line2D]:
    use_models = models or MODEL_ORDER
    return [
        Line2D(
            [0],
            [0],
            marker=MODEL_MARKER.get(m, "o"),
            linestyle="None",
            markerfacecolor=MODEL_COLOR.get(m, "#666666"),
            markeredgecolor="white",
            markeredgewidth=0.6,
            markersize=marker_size,
            label=m,
        )
        for m in use_models
    ]


def _set_full_border(ax: Any, color: str = "#6D86A7", lw: float = 0.9) -> None:
    if getattr(ax, "axison", False) is False:
        return
    for side in ("left", "right", "top", "bottom"):
        sp = ax.spines.get(side)
        if sp is not None:
            sp.set_visible(True)
            sp.set_linewidth(lw)
            sp.set_color(color)


def _write_source_workbook(group: str, stem: str, sheets: dict[str, pd.DataFrame], meta: dict[str, Any]) -> Path:
    out = OUT_DATA_DIR / group / f"{stem}_source.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    source_col_name = str(meta.get("source_col_name", "source_table"))
    meta_key_col = str(meta.get("meta_key_col", "key"))
    meta_value_col = str(meta.get("meta_value_col", "value"))
    meta_df = pd.DataFrame([{meta_key_col: k, meta_value_col: v} for k, v in meta.items()])
    explicit_alias = meta.get("sheet_name_alias")
    if not isinstance(explicit_alias, dict):
        explicit_alias = {}
    sheet_name_map = _build_sheet_name_map(list(sheets.keys()) + ["meta"], explicit_alias=explicit_alias)
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, df in sheets.items():
            out_df = df.copy()
            if (
                ("source_table" not in out_df.columns)
                and ("数据来源" not in out_df.columns)
                and (source_col_name not in out_df.columns)
            ):
                source_hint = (
                    meta.get(f"source_hint__{name}")
                    or meta.get("source_raw")
                    or meta.get("source_memory")
                    or meta.get("source_consistency")
                    or meta.get("source_reasoning")
                    or "see_meta"
                )
                out_df.insert(0, source_col_name, source_hint)
            out_df = _rewrite_formula_sheet_refs(out_df, sheet_name_map)
            out_df.to_excel(writer, sheet_name=sheet_name_map.get(name, name[:31]), index=False)
        meta_df = _rewrite_formula_sheet_refs(meta_df, sheet_name_map)
        meta_df.to_excel(writer, sheet_name=sheet_name_map.get("meta", "meta"), index=False)
    _style_workbook(out)
    fig_side = OUT_FIG_DIR / group / "source_data"
    fig_side.mkdir(parents=True, exist_ok=True)
    side_path = fig_side / out.name
    try:
        side_path.write_bytes(out.read_bytes())
    except PermissionError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        side_path = fig_side / f"{out.stem}_{ts}{out.suffix}"
        side_path.write_bytes(out.read_bytes())
    _cleanup_side_source_versions(fig_side, out.stem, out.suffix, keep=1)
    return out


def _write_single_caption_file(folder: Path, file_name: str, lines: list[str]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    keep_name = str(file_name or "caption.md").strip() or "caption.md"
    text = "\n".join(lines).strip() + "\n"
    for p in folder.glob("*.md"):
        if p.name == keep_name:
            continue
        lower = p.name.lower()
        if p.name == "caption.md" or p.name.startswith("图注_") or "caption" in lower:
            try:
                p.unlink()
            except Exception:
                pass
    out_path = folder / keep_name
    out_path.write_text(text, encoding="utf-8")
    return out_path


def _write_caption(group: str, lines: list[str]) -> None:
    folder = OUT_FIG_DIR / group
    pretty_name = CAPTION_FILE_BY_GROUP.get(group, f"图注_Figure_{group}.md")
    _write_single_caption_file(folder, pretty_name, lines)


def _archive_group_outputs(group: str, keep_fig_names: set[str], keep_source_names: set[str]) -> None:
    """将组内非保留产物归档，保持目录整洁。"""
    fig_root = OUT_FIG_DIR / group
    fig_archive = fig_root / "archive" / "figures"
    fig_archive.mkdir(parents=True, exist_ok=True)
    for keep_name in keep_fig_names:
        stale = fig_archive / keep_name
        if stale.exists():
            try:
                stale.unlink()
            except Exception:
                pass
    for p in fig_root.glob("*.png"):
        if p.name in keep_fig_names:
            continue
        dst = fig_archive / p.name
        try:
            if dst.exists():
                dst.unlink()
            shutil.copy2(str(p), str(dst))
            if p.exists():
                p.unlink()
        except Exception:
            pass
    for p in fig_root.glob("*.png"):
        if p.name in keep_fig_names:
            continue
        dst = fig_archive / p.name
        if dst.exists():
            try:
                p.unlink()
            except Exception:
                pass

    data_root = OUT_DATA_DIR / group
    data_archive = data_root / "archive" / "source_data"
    data_archive.mkdir(parents=True, exist_ok=True)
    for keep_name in keep_source_names:
        stale = data_archive / keep_name
        if stale.exists():
            try:
                stale.unlink()
            except Exception:
                pass
    for p in data_root.glob("*_source.xlsx"):
        if p.name in keep_source_names:
            continue
        dst = data_archive / p.name
        try:
            if dst.exists():
                dst.unlink()
            shutil.copy2(str(p), str(dst))
            if p.exists():
                p.unlink()
        except Exception:
            pass
    for p in data_root.glob("*_source.xlsx"):
        if p.name in keep_source_names:
            continue
        dst = data_archive / p.name
        if dst.exists():
            try:
                p.unlink()
            except Exception:
                pass

    fig_side_source = fig_root / "source_data"
    side_archive = fig_root / "archive" / "source_data"
    side_archive.mkdir(parents=True, exist_ok=True)
    for keep_name in keep_source_names:
        stale = side_archive / keep_name
        if stale.exists():
            try:
                stale.unlink()
            except Exception:
                pass
    for p in fig_side_source.glob("*_source.xlsx"):
        if p.name in keep_source_names:
            continue
        dst = side_archive / p.name
        try:
            if dst.exists():
                dst.unlink()
            shutil.copy2(str(p), str(dst))
            if p.exists():
                p.unlink()
        except Exception:
            pass
    for p in fig_side_source.glob("*_source.xlsx"):
        if p.name in keep_source_names:
            continue
        dst = side_archive / p.name
        if dst.exists():
            try:
                p.unlink()
            except Exception:
                pass


def _copy_to_supplement(src: Path, dst: Path) -> Path | None:
    if not src.exists():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dst)
        return dst
    except Exception:
        return None


def _load_d1_anomaly_set() -> set[tuple[str, str, str]]:
    df = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="d1_decision_anomalies")
    return set(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))


def _load_gate3_fail_set() -> set[tuple[str, str, str]]:
    df = pd.read_excel(RAW_DOCTOR_SUMMARY, sheet_name="人工评分_D4Gate3不通过")
    df = df.rename(columns={"中心": "center", "模型名称": "model", "病例ID": "case_id"})
    return set(zip(df["center"].astype(str), df["model"].astype(str), df["case_id"].astype(str)))


def _read_case_status_sheet(xlsx_path: Path, sheet_name: str) -> pd.DataFrame:
    try:
        df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
    except Exception:
        return pd.DataFrame(columns=["case_id", "status"])
    if df.empty or len(df.columns) < 2:
        return pd.DataFrame(columns=["case_id", "status"])
    case_col = df.columns[0]
    status_col = df.columns[1]
    out = df[[case_col, status_col]].copy()
    out = out.rename(columns={case_col: "case_id", status_col: "status"})
    out["case_id"] = out["case_id"].astype(str).str.strip()
    out["status"] = out["status"].fillna("").astype(str).str.strip()
    out = out[out["case_id"].ne("") & out["case_id"].str.lower().ne("nan")].copy()
    return out


def _load_d2_manual_rule_map() -> pd.DataFrame:
    """加载 D2 规则映射（优先 center_data 原始 judge 状态，fallback 到汇总表）。

    规则说明：
    1) D2 决策出现“不通过/已退出/流程不通过” -> 后续 D3/D4 强制视为未经过（流程止于入院决策）。
    2) D2 检查为“未经过”且 D2 决策不通过 -> 仅标记 d2_check_force_fail（用于核对），不改写 D2 检查状态。
    3) 标记 D2 不通过但后续仍通过的“链路不一致”样本，供 source/meta 追溯。
    """
    records: list[dict[str, Any]] = []

    if CENTER_DATA_DIR.exists():
        for center_dir in sorted(CENTER_DATA_DIR.iterdir(), key=lambda p: p.name):
            if not center_dir.is_dir():
                continue
            center = center_dir.name
            judge_dir = center_dir / "judge agent"
            if not judge_dir.exists():
                continue
            for model_full in MODEL_SHORT:
                judge_file = judge_dir / f"Evaluation_Summary_{model_full}_CN_Judge_Parsed.xlsx"
                if not judge_file.exists():
                    continue
                d2_loop = _read_case_status_sheet(judge_file, "D2_Admission_Loop").rename(
                    columns={"status": "d2_loop_status"}
                )
                d2_dec = _read_case_status_sheet(judge_file, "D2_Admission_Decision").rename(columns={"status": "d2_dec_status"})
                d3_dec = _read_case_status_sheet(judge_file, "D3_Surgery_Decision").rename(
                    columns={"status": "d3_status"}
                )
                d4_plan = _read_case_status_sheet(judge_file, "D4_Rehab_Plan").rename(
                    columns={"status": "d4_status"}
                )
                d2_dec_rule = pd.DataFrame(columns=["case_id", "d2_should_continue_raw", "d2_should_continue_source"])
                try:
                    d2_dec_full = pd.read_excel(judge_file, sheet_name="D2_Admission_Decision")
                except Exception:
                    d2_dec_full = pd.DataFrame()
                if not d2_dec_full.empty:
                    case_col = d2_dec_full.columns[0]
                    cont_col = _find_col_by_keywords(list(d2_dec_full.columns), ["是否能继续评测"])
                    json2_col = _find_col_by_keywords(list(d2_dec_full.columns), ["Gate2_二审原始JSON"], ["reasonableness", "是否能继续评测"])
                    tmp = d2_dec_full[[case_col]].copy()
                    tmp["case_id"] = tmp[case_col].astype(str).str.strip()
                    tmp = tmp[tmp["case_id"].ne("") & tmp["case_id"].str.lower().ne("nan")].copy()
                    tmp = tmp[["case_id"]]
                    if cont_col:
                        tmp["d2_should_continue_raw"] = d2_dec_full[cont_col].map(_coerce_bool_flag)
                        tmp["d2_should_continue_source"] = f"{judge_file.name}:D2_Admission_Decision:{cont_col}"
                    elif json2_col:
                        tmp["d2_should_continue_raw"] = d2_dec_full[json2_col].map(_extract_should_continue_from_json)
                        tmp["d2_should_continue_source"] = f"{judge_file.name}:D2_Admission_Decision:{json2_col}.should_continue"
                    else:
                        tmp["d2_should_continue_raw"] = None
                        tmp["d2_should_continue_source"] = ""
                    d2_dec_rule = tmp
                if d2_loop.empty and d2_dec.empty and d3_dec.empty and d4_plan.empty:
                    continue
                merged = d2_loop.merge(d2_dec, on="case_id", how="outer")
                merged = merged.merge(d3_dec, on="case_id", how="outer")
                merged = merged.merge(d4_plan, on="case_id", how="outer")
                merged = merged.merge(d2_dec_rule, on="case_id", how="left")
                for c in ["d2_loop_status", "d2_dec_status", "d3_status", "d4_status"]:
                    if c not in merged.columns:
                        merged[c] = ""
                    merged[c] = merged[c].fillna("").astype(str)
                if "d2_should_continue_raw" not in merged.columns:
                    merged["d2_should_continue_raw"] = None
                if "d2_should_continue_source" not in merged.columns:
                    merged["d2_should_continue_source"] = ""
                merged["d2_should_continue_source"] = merged["d2_should_continue_source"].fillna("").astype(str)

                d2_dec_s = merged["d2_dec_status"]
                d2_loop_s = merged["d2_loop_status"]
                d3_s = merged["d3_status"]
                d4_s = merged["d4_status"]
                d2_pass = d2_dec_s.str.contains("通过二审|二审通过|通过一审|一审通过|顺利通过|完成流程", regex=True)
                d2_fail_explicit = d2_dec_s.str.contains("二审不通过|流程不通过|已退出|退出|不通过", regex=True) & ~d2_pass
                d2_stop_from_continue = merged["d2_should_continue_raw"].map(lambda x: x is False)
                d2_stop_from_downstream = (
                    d2_pass
                    & (
                        d3_s.str.contains("未经过（流程终止于入院决策）|未经过\\(流程终止于入院决策\\)", regex=True)
                        | d4_s.str.contains("未经过（流程终止于入院决策）|未经过\\(流程终止于入院决策\\)", regex=True)
                    )
                )
                d2_force_stop = d2_fail_explicit | d2_stop_from_continue | d2_stop_from_downstream
                d2_check_force_fail = d2_loop_s.str.contains("未经过", regex=False) & d2_force_stop
                d2_inconsistent = d2_force_stop & (
                    d3_s.str.contains("通过一审|通过二审|一审通过|完成流程|顺利通过", regex=True)
                    | d4_s.str.contains("完成流程|顺利通过", regex=True)
                )
                d2_force_stop_reason = np.select(
                    [d2_fail_explicit, d2_stop_from_continue, d2_stop_from_downstream],
                    ["raw_decision_fail", "gate2_should_continue_false", "downstream_terminated_after_d2"],
                    default="raw_decision_pass",
                )
                d2_dec_fixed = np.where(
                    d2_force_stop & d2_pass,
                    "D2决策_进行一审_需要二审_二审不通过_完全不同",
                    d2_dec_s,
                )

                merged_out = merged[["case_id"]].copy()
                merged_out["center"] = center
                merged_out["model"] = model_full
                merged_out["d2_force_stop"] = d2_force_stop.astype(bool)
                merged_out["d2_check_force_fail"] = d2_check_force_fail.astype(bool)
                merged_out["d2_inconsistent"] = d2_inconsistent.astype(bool)
                merged_out["d2_loop_status_raw"] = d2_loop_s
                merged_out["d2_dec_status_raw"] = d2_dec_s
                merged_out["d2_dec_status_fixed"] = pd.Series(d2_dec_fixed).fillna("").astype(str)
                merged_out["d2_force_stop_reason"] = pd.Series(d2_force_stop_reason).fillna("").astype(str)
                merged_out["d2_should_continue_raw"] = merged["d2_should_continue_raw"]
                merged_out["d2_should_continue_source"] = merged["d2_should_continue_source"].fillna("").astype(str)
                merged_out["d3_status_raw"] = d3_s
                merged_out["d4_status_raw"] = d4_s
                merged_out["d2_rule_source"] = str(judge_file.relative_to(ROOT)).replace("\\", "/")
                records.extend(merged_out.to_dict(orient="records"))

    if records:
        out = pd.DataFrame.from_records(records)
        out["center"] = out["center"].astype(str)
        out["model"] = out["model"].astype(str)
        out["case_id"] = out["case_id"].astype(str)
        out = out.sort_values(["center", "model", "case_id"], kind="mergesort")
        out = out.drop_duplicates(subset=["center", "model", "case_id"], keep="last").reset_index(drop=True)
        return out

    # fallback: 若 center raw 不可用，再退回既有汇总表
    try:
        df = pd.read_excel(RAW_DOCTOR_SUMMARY, sheet_name="通过退出明细")
    except Exception:
        return pd.DataFrame(
            columns=[
                "center",
                "model",
                "case_id",
                "d2_force_stop",
                "d2_check_force_fail",
                "d2_inconsistent",
                "d2_loop_status_raw",
                "d2_dec_status_raw",
                "d2_dec_status_fixed",
                "d2_force_stop_reason",
                "d2_should_continue_raw",
                "d2_should_continue_source",
                "d3_status_raw",
                "d4_status_raw",
                "d2_rule_source",
            ]
        )
    df = df.rename(columns={"中心": "center", "模型名称": "model", "病例ID": "case_id"}).copy()
    need = {"center", "model", "case_id", "D2_Loop", "D2_Decision", "D3_Decision", "D4_Plan"}
    if not need.issubset(set(df.columns)):
        return pd.DataFrame(
            columns=[
                "center",
                "model",
                "case_id",
                "d2_force_stop",
                "d2_check_force_fail",
                "d2_inconsistent",
                "d2_loop_status_raw",
                "d2_dec_status_raw",
                "d2_dec_status_fixed",
                "d2_force_stop_reason",
                "d2_should_continue_raw",
                "d2_should_continue_source",
                "d3_status_raw",
                "d4_status_raw",
                "d2_rule_source",
            ]
        )
    d2_dec = df["D2_Decision"].fillna("").astype(str)
    d2_loop = df["D2_Loop"].fillna("").astype(str)
    d3_dec = df["D3_Decision"].fillna("").astype(str)
    d4_plan = df["D4_Plan"].fillna("").astype(str)
    out = df[["center", "model", "case_id"]].copy()
    out["center"] = out["center"].astype(str)
    out["model"] = out["model"].astype(str)
    out["case_id"] = out["case_id"].astype(str)
    d2_pass = d2_dec.str.contains("通过二审|二审通过|通过一审|一审通过|顺利通过|完成流程", regex=True)
    out["d2_force_stop"] = (d2_dec.str.contains("二审不通过|流程不通过|已退出|退出|不通过", regex=True) & ~d2_pass).astype(bool)
    out["d2_check_force_fail"] = (d2_loop.str.contains("未经过", regex=False) & out["d2_force_stop"]).astype(bool)
    out["d2_inconsistent"] = (
        out["d2_force_stop"]
        & (d3_dec.str.contains("通过一审|通过二审|一审通过|完成流程", regex=True) | d4_plan.str.contains("完成流程", regex=False))
    ).astype(bool)
    out["d2_loop_status_raw"] = d2_loop
    out["d2_dec_status_raw"] = d2_dec
    out["d2_dec_status_fixed"] = np.where(
        out["d2_force_stop"] & d2_dec.str.contains("通过二审|二审通过|通过一审|一审通过|顺利通过|完成流程", regex=True),
        "D2决策_进行一审_需要二审_二审不通过_完全不同",
        d2_dec,
    )
    out["d2_force_stop_reason"] = np.where(out["d2_force_stop"], "fallback_raw_summary_fail", "fallback_raw_summary_pass")
    out["d2_should_continue_raw"] = np.nan
    out["d2_should_continue_source"] = ""
    out["d3_status_raw"] = d3_dec
    out["d4_status_raw"] = d4_plan
    out["d2_rule_source"] = "fallback:RAW_DOCTOR_SUMMARY/通过退出明细"
    return out


def _attach_d2_manual_rules(df: pd.DataFrame, d2_rule_map: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if out.empty or d2_rule_map.empty:
        out["d2_force_stop"] = False
        out["d2_check_force_fail"] = False
        out["d2_inconsistent"] = False
        return out
    need = {"center", "model", "case_id"}
    if not need.issubset(set(out.columns)):
        out["d2_force_stop"] = False
        out["d2_check_force_fail"] = False
        out["d2_inconsistent"] = False
        return out
    out["center"] = out["center"].astype(str)
    out["model"] = out["model"].astype(str)
    out["case_id"] = out["case_id"].astype(str)
    merged = out.merge(d2_rule_map, on=["center", "model", "case_id"], how="left")
    for c in ["d2_force_stop", "d2_check_force_fail", "d2_inconsistent"]:
        merged[c] = merged[c].fillna(False).astype(bool)
    for c in [
        "d2_loop_status_raw",
        "d2_dec_status_raw",
        "d2_dec_status_fixed",
        "d2_force_stop_reason",
        "d2_should_continue_raw",
        "d2_should_continue_source",
        "d3_status_raw",
        "d4_status_raw",
        "d2_rule_source",
    ]:
        if c not in merged.columns:
            merged[c] = ""
        if c == "d2_should_continue_raw":
            continue
        merged[c] = merged[c].fillna("").astype(str)
    return merged


def _write_sankey_special_case_report(d2_rule_map: pd.DataFrame) -> dict[str, Path]:
    """输出 G4 Sankey 特殊样本核对报告（供人工确认状态归属）。"""
    out_dir = ANALYSIS_VIZ / "给用户看"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "14_G4_Sankey_特殊案例核对.csv"
    out_md = out_dir / "14_G4_Sankey_特殊案例核对.md"
    if d2_rule_map.empty:
        pd.DataFrame(columns=["note"]).to_csv(out_csv, index=False, encoding="utf-8-sig")
        out_md.write_text("# G4 Sankey 特殊案例核对\n\n无可用 d2_rule_map 数据。\n", encoding="utf-8")
        return {"report_csv": out_csv, "report_md": out_md}

    use_cols = [
        "center",
        "model",
        "case_id",
        "d2_force_stop",
        "d2_check_force_fail",
        "d2_inconsistent",
        "d2_loop_status_raw",
        "d2_dec_status_raw",
        "d2_dec_status_fixed",
        "d2_force_stop_reason",
        "d2_should_continue_raw",
        "d2_should_continue_source",
        "d3_status_raw",
        "d4_status_raw",
        "d2_rule_source",
    ]
    d2m = d2_rule_map[[c for c in use_cols if c in d2_rule_map.columns]].copy()
    for c in [
        "center",
        "model",
        "case_id",
        "d2_loop_status_raw",
        "d2_dec_status_raw",
        "d2_dec_status_fixed",
        "d2_force_stop_reason",
        "d2_should_continue_source",
        "d3_status_raw",
        "d4_status_raw",
        "d2_rule_source",
    ]:
        if c not in d2m.columns:
            d2m[c] = ""
        d2m[c] = d2m[c].fillna("").astype(str)
    for c in ["d2_force_stop", "d2_check_force_fail", "d2_inconsistent"]:
        if c not in d2m.columns:
            d2m[c] = False
        d2m[c] = d2m[c].fillna(False).astype(bool)
    if "d2_should_continue_raw" not in d2m.columns:
        d2m["d2_should_continue_raw"] = np.nan

    # 与 Fig7 detail_used 的现状对比（不做覆盖，仅做核对）
    fig7 = pd.read_excel(PAPER_FIGDATA_DIR / "Fig7__sankey_flow_source.xlsx", sheet_name="detail_used")
    base_cols = {
        "中心": "center",
        "模型名称": "model",
        "病例ID": "case_id",
        "入院检查": "d2_loop_status_summary",
        "入院决策": "d2_dec_status_summary",
        "术后康复": "d3_status_summary",
        "随访计划": "d4_status_summary",
    }
    fig7 = fig7.rename(columns=base_cols)
    need = ["center", "model", "case_id", "d2_loop_status_summary", "d2_dec_status_summary", "d3_status_summary", "d4_status_summary"]
    for c in need:
        if c not in fig7.columns:
            fig7[c] = ""
    fig7 = fig7[need].copy()
    for c in need:
        fig7[c] = fig7[c].fillna("").astype(str)

    rep = d2m.merge(fig7, on=["center", "model", "case_id"], how="left")
    for c in ["d2_loop_status_summary", "d2_dec_status_summary", "d3_status_summary", "d4_status_summary"]:
        rep[c] = rep[c].fillna("").astype(str)

    rep["d2_loop_norm"] = rep["d2_loop_status_raw"].map(lambda s: _split_sankey_label(_simplify_sankey_status("入院检查", s))[1])
    rep["d2_dec_norm"] = rep["d2_dec_status_raw"].map(lambda s: _split_sankey_label(_simplify_sankey_status("入院决策", s))[1])
    rep["d3_norm"] = rep["d3_status_raw"].map(lambda s: _split_sankey_label(_simplify_sankey_status("术后康复", s))[1])
    rep["d4_norm"] = rep["d4_status_raw"].map(lambda s: _split_sankey_label(_simplify_sankey_status("随访计划", s))[1])

    raw_pass = rep["d2_dec_status_raw"].str.contains("通过二审|二审通过|通过一审|一审通过|顺利通过|完成流程", regex=True)
    raw_fail = rep["d2_dec_status_raw"].str.contains("二审不通过|流程不通过|已退出|退出|不通过", regex=True) & ~raw_pass
    sum_pass = rep["d2_dec_status_summary"].str.contains("通过二审|二审通过|通过一审|一审通过|顺利通过|完全一致|高度相似|部分一致|不同但合理|完成流程", regex=True)
    sum_fail = rep["d2_dec_status_summary"].str.contains("二审不通过|流程不通过|已退出|退出|不通过", regex=True) & ~sum_pass
    rep["d2_dec_conflict_raw_vs_summary"] = (raw_pass & sum_fail) | (raw_fail & sum_pass)

    rep["d2_loop_special_marker"] = rep["d2_loop_status_summary"].str.contains(
        "裁剪|终止于入院循环|此前已中止|fail/terminated|terminated",
        case=False,
        regex=True,
    )
    rep["d2_loop_should_end_next_stage"] = rep["d2_loop_norm"].isin(["超过4轮检查", "流程不通过"])
    rep["recommended_d2_loop_status"] = rep["d2_loop_norm"]
    rep["recommended_d2_dec_status"] = np.where(
        rep["d2_loop_should_end_next_stage"],
        "本流程进行前已结束",
        np.where(rep["d2_force_stop"], rep["d2_dec_status_fixed"].where(rep["d2_dec_status_fixed"].str.strip().ne(""), rep["d2_dec_norm"]), rep["d2_dec_norm"]),
    )
    rep["recommended_d3_status"] = np.where(
        rep["d2_force_stop"] | rep["d2_loop_should_end_next_stage"],
        "本流程进行前已结束",
        rep["d3_norm"],
    )
    rep["recommended_d4_status"] = np.where(
        rep["d2_force_stop"] | rep["d2_loop_should_end_next_stage"],
        "本流程进行前已结束",
        rep["d4_norm"],
    )

    rep["rule_reason"] = np.select(
        [
            rep["d2_force_stop"],
            rep["d2_loop_should_end_next_stage"],
            rep["d2_dec_conflict_raw_vs_summary"],
            rep["d2_loop_special_marker"],
        ],
        [
            "D2决策失败：D3/D4归“本流程进行前已结束”",
            "D2检查“流程不通过/超过4轮检查”：后续阶段归“本流程进行前已结束”",
            "raw与summary在D2决策通过/失败语义冲突，建议以raw为准复核",
            "summary中出现裁剪/终止标签，建议替换为规范状态词",
        ],
        default="常规样本",
    )

    rep_out = rep[
        [
            "center",
            "model",
            "case_id",
            "d2_force_stop",
            "d2_check_force_fail",
            "d2_inconsistent",
            "d2_loop_status_raw",
            "d2_dec_status_raw",
            "d2_dec_status_fixed",
            "d2_force_stop_reason",
            "d2_should_continue_raw",
            "d2_should_continue_source",
            "d3_status_raw",
            "d4_status_raw",
            "d2_loop_status_summary",
            "d2_dec_status_summary",
            "d3_status_summary",
            "d4_status_summary",
            "recommended_d2_loop_status",
            "recommended_d2_dec_status",
            "recommended_d3_status",
            "recommended_d4_status",
            "d2_dec_conflict_raw_vs_summary",
            "d2_loop_special_marker",
            "rule_reason",
            "d2_rule_source",
        ]
    ].copy()
    rep_out = rep_out.sort_values(["d2_dec_conflict_raw_vs_summary", "d2_inconsistent", "center", "model", "case_id"], ascending=[False, False, True, True, True], kind="mergesort")
    rep_out.to_csv(out_csv, index=False, encoding="utf-8-sig")

    total_n = int(len(rep_out))
    n_conflict = int(rep_out["d2_dec_conflict_raw_vs_summary"].sum())
    n_inconsistent = int(rep_out["d2_inconsistent"].sum())
    n_force = int(rep_out["d2_force_stop"].sum())
    n_check_fail = int(rep_out["d2_check_force_fail"].sum())
    lines = [
        "# G4 Sankey 特殊案例核对",
        "",
        f"- 样本总数：{total_n}",
        f"- D2决策 raw/summary 冲突：{n_conflict}",
        f"- D2不通过但后续仍通过（raw标记不一致）：{n_inconsistent}",
        f"- D2决策失败（需裁剪D3/D4）：{n_force}",
        f"- D2检查未经过且D2决策失败（仅核对标记，不改写D2检查状态）：{n_check_fail}",
        "",
        "核对明细见同目录 CSV：`14_G4_Sankey_特殊案例核对.csv`。",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"report_csv": out_csv, "report_md": out_md}


def _attach_rules(df: pd.DataFrame, d1_set: set[tuple[str, str, str]], gate3_set: set[tuple[str, str, str]]) -> pd.DataFrame:
    out = df.copy()
    keys = list(zip(out["center"].astype(str), out["model"].astype(str), out["case_id"].astype(str)))
    out["is_d1_anomaly"] = [k in d1_set for k in keys]
    out["is_gate3_fail"] = [k in gate3_set for k in keys]
    return out


def _stage4_map(stage: str) -> str:
    s = str(stage)
    if s in {"D1_Loop", "D1_Decision", "D1", "D1_Outpatient_Loop", "D1_Outpatient_Decision"}:
        return "D1"
    if s in {"D2_Loop", "D2_Decision", "D2", "D2_Admission_Loop", "D2_Admission_Decision"}:
        return "D2"
    if s in {"D3", "D3_Decision", "D3_Surgery_Decision"}:
        return "D3"
    if s in {"D4", "D4_Plan", "D4_Rehab_Plan"}:
        return "D4"
    return s


def _find_col_by_keywords(columns: list[Any], must: list[str], must_not: list[str] | None = None) -> str:
    must_not = must_not or []
    for col in columns:
        s = str(col)
        if all(k in s for k in must) and all(k not in s for k in must_not):
            return s
    return ""


def _coerce_bool_flag(v: Any) -> bool | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    s = str(v).strip().lower()
    if s in {"", "nan", "none", "null"}:
        return None
    if s in {"1", "true", "yes", "y", "是"}:
        return True
    if s in {"0", "false", "no", "n", "否"}:
        return False
    try:
        fv = float(s)
        if np.isfinite(fv):
            return fv > 0
    except Exception:
        pass
    return None


def _extract_should_continue_from_json(raw_text: Any) -> bool | None:
    text = str(raw_text or "").strip()
    if text in {"", "nan", "None", "null"}:
        return None
    try:
        obj = json.loads(text)
    except Exception:
        return None
    if isinstance(obj, dict):
        for key in ["should_continue", "是否能继续评测", "continue_eval", "can_continue"]:
            if key in obj:
                return _coerce_bool_flag(obj.get(key))
    return None


def _is_none_like_text(text: Any) -> bool:
    if text is None:
        return True
    s = str(text).strip()
    if s == "":
        return True
    s2 = re.sub(r"[\s|｜;；,，。.!！:：]+", "", s).lower()
    if s2 in {"nan", "none", "null", "无", "暂无", "未做", "未行", "未进行", "未检查", "未提供", "未记录"}:
        return True
    if s2.startswith("无") and len(s2) <= 4:
        return True
    return False


def _extract_check_segment(text: Any, category: str) -> str:
    if text is None:
        return ""
    s = str(text)
    # 仅抓取该类别对应片段，直到下一个“辅助检查:”或文本结尾
    pattern = re.compile(rf"辅助检查:{re.escape(category)}:(.*?)(?=辅助检查:|$)", re.S)
    m = pattern.search(s)
    if not m:
        return ""
    return str(m.group(1)).strip()


def _map_outpatient_check_types(segment_text: str, raw_category: str) -> set[str]:
    """将门诊“检查/检验”文本映射到统一检查类型。"""
    s = str(segment_text or "")
    if _is_none_like_text(s):
        return set()

    hits: set[str] = set()
    lab_kw = [
        "血常规",
        "尿常规",
        "便常规",
        "凝血",
        "生化",
        "肝功",
        "肾功",
        "肝肾",
        "电解质",
        "激素",
        "肿瘤标志",
        "roma",
        "hcg",
        "hpv",
        "tct",
        "cea",
        "he4",
        "ca125",
        "ca199",
        "scc",
        "免疫",
        "传染病",
        "白带",
        "分泌物",
        "检验",
    ]
    image_kw = [
        "超声",
        "彩超",
        "b超",
        "ct",
        "mri",
        "mr",
        "磁共振",
        "x线",
        "dr",
        "胸片",
        "影像",
        "cdfi",
        "多普勒",
        "造影",
    ]
    endoscopy_kw = ["宫腔镜", "腹腔镜", "肠镜", "胃镜", "阴道镜", "膀胱镜", "支气管镜", "置镜"]
    # 去掉“镜下”等高误判关键词，避免把门诊常规描述误分到病理学检查
    pathology_kw = ["病理", "活检", "免疫组化", "送检组织", "制片", "病检", "病变区域"]
    other_kw = ["心电图", "ecg", "其他检查", "肺功能", "评估"]

    low = s.lower()
    if any(k in low for k in [x.lower() for x in lab_kw]):
        hits.add("实验室检查")
    if any(k in low for k in [x.lower() for x in image_kw]):
        hits.add("影像学检查")
    if any(k in low for k in [x.lower() for x in endoscopy_kw]):
        hits.add("内镜检查")
    if any(k in low for k in [x.lower() for x in pathology_kw]):
        hits.add("病理学检查")
    if any(k in low for k in [x.lower() for x in other_kw]):
        hits.add("其他检查")

    # 兜底：仅有“检验”但未命中实验室关键词时，仍归入实验室
    if ("检验" in str(raw_category)) and ("实验室检查" not in hits):
        hits.add("实验室检查")
    # 兜底：未命中任何类型但片段存在，归为其他检查
    if not hits:
        hits.add("其他检查")
    return hits


def _build_g1_check_type_from_gt() -> tuple[pd.DataFrame, pd.DataFrame]:
    """从 GT 原始文本重建 G1f 检查谱系。

    计数规则：
    - 门诊：GT_Outpatient_Checks 的“检查/检验”两个类别
    - 入院：GT_Admission_Checks 的“实验室检查/影像学检查/内镜检查/病理学检查/其他检查”
    - 对每个病例-类别：若该类别片段存在且非“无”，计 1；否则不计
    - 字段缺失或片段缺失：不计
    """
    records: list[dict[str, Any]] = []
    if not CENTER_DATA_DIR.exists():
        raise FileNotFoundError(f"center_data目录不存在: {CENTER_DATA_DIR}")

    outpatient_raw_cats = ["检查", "检验"]
    standard_cats = ["实验室检查", "影像学检查", "内镜检查", "病理学检查", "其他检查"]

    for center_dir in sorted(CENTER_DATA_DIR.iterdir(), key=lambda p: p.name):
        if not center_dir.is_dir():
            continue
        gt_dir = center_dir / "GT"
        gt_files = sorted(gt_dir.glob("*.xlsx"))
        if not gt_files:
            continue
        gt_file = gt_files[0]
        try:
            gt_df = pd.read_excel(gt_file, sheet_name="Sheet1")
        except Exception:
            continue
        if gt_df.empty:
            continue
        case_col = "CaseID" if "CaseID" in gt_df.columns else ("病例ID" if "病例ID" in gt_df.columns else "")
        if not case_col:
            continue

        for _, row in gt_df.iterrows():
            case_id = str(row.get(case_col, "")).strip()
            if case_id == "" or case_id.lower() in {"nan", "none"}:
                continue

            out_text = row.get("GT_Outpatient_Checks", "")
            d1_hits: dict[str, set[str]] = {cat: set() for cat in standard_cats}
            for raw_cat in outpatient_raw_cats:
                seg = _extract_check_segment(out_text, raw_cat)
                if seg == "" or _is_none_like_text(seg):
                    continue
                mapped = _map_outpatient_check_types(seg, raw_cat)
                for m in mapped:
                    d1_hits.setdefault(m, set()).add(raw_cat)

            for cat in standard_cats:
                evidence = "、".join(sorted(d1_hits.get(cat, set())))
                records.append(
                    {
                        "center": center_dir.name,
                        "case_id": case_id,
                        "Stage": "Outpatient",
                        "Category": cat,
                        "segment_text": evidence,
                        "is_counted": int(bool(d1_hits.get(cat))),
                        "source_sheet": f"{gt_file.name}:Sheet1",
                        "source_column": "GT_Outpatient_Checks",
                        "source_path": str(gt_file.relative_to(ROOT)).replace("\\", "/"),
                        "count_rule": "按文本关键词命中类型；若片段非无且未命中则归其他检查",
                    }
                )

            adm_text = row.get("GT_Admission_Checks", "")
            for cat in standard_cats:
                seg = _extract_check_segment(adm_text, cat)
                is_counted = int((seg != "") and (not _is_none_like_text(seg)))
                records.append(
                    {
                        "center": center_dir.name,
                        "case_id": case_id,
                        "Stage": "Admission",
                        "Category": cat,
                        "segment_text": seg,
                        "is_counted": is_counted,
                        "source_sheet": f"{gt_file.name}:Sheet1",
                        "source_column": "GT_Admission_Checks",
                        "source_path": str(gt_file.relative_to(ROOT)).replace("\\", "/"),
                        "count_rule": "segment_exists && segment_not_none",
                    }
                )

    detail = pd.DataFrame.from_records(records)
    if detail.empty:
        raise RuntimeError("未从 GT 重建出 G1f 检查类型明细")
    summary = (
        detail.groupby(["Stage", "Category"], as_index=False)["is_counted"]
        .sum()
        .rename(columns={"is_counted": "Cases"})
    )
    cat_order = {c: i for i, c in enumerate(standard_cats)}
    stage_order = {"Outpatient": 0, "Admission": 1}
    summary["_stage_order"] = summary["Stage"].map(stage_order).fillna(99)
    summary["_cat_order"] = summary["Category"].map(cat_order).fillna(99)
    summary = summary.sort_values(["_stage_order", "_cat_order"], kind="mergesort").drop(columns=["_stage_order", "_cat_order"])
    return detail, summary


def _classify_palm_coein(text: Any) -> tuple[str, str]:
    s = str(text or "").strip()
    if s == "" or s.lower() in {"nan", "none"}:
        return "N-非肿瘤", "empty_text"
    low = s.lower()

    def _hit(words: list[str]) -> list[str]:
        return [w for w in words if w.lower() in low]

    rules: list[tuple[str, list[str]]] = [
        (
            "M-恶性/增生",
            [
                "恶性",
                "癌",
                "癌前",
                "上皮内",
                "非典型增生",
                "重度不典型增生",
                "内膜增生",
                "高级别",
                "恶变",
                "肿瘤",
            ],
        ),
        ("L-肌瘤", ["子宫肌瘤", "肌瘤", "平滑肌瘤"]),
        ("A-腺肌症", ["子宫腺肌症", "腺肌症"]),
        ("P-息肉", ["子宫内膜息肉", "宫颈息肉", "息肉"]),
        ("C-凝血相关", ["凝血", "coagul", "vwd", "血小板", "血液病", "止血"]),
        ("O-排卵障碍", ["排卵障碍", "无排卵", "pcos", "多囊", "卵巢功能"]),
        ("E-子宫内膜原因", ["子宫内膜炎", "内膜炎", "子宫内膜功能", "黄体功能不足", "月经失调"]),
        ("I-医源性", ["医源", "药物", "激素", "抗凝", "宫内节育器", "iud", "置环", "手术后"]),
    ]
    for cat, words in rules:
        hit = _hit(words)
        if hit:
            return cat, "|".join(hit)
    return "N-非肿瘤", "no_keyword_matched"


def _build_palm_coein_from_gt() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    records: list[dict[str, Any]] = []
    if not CENTER_DATA_DIR.exists():
        raise FileNotFoundError(f"center_data目录不存在: {CENTER_DATA_DIR}")

    stage_cols = [
        ("D1", "GT_Admission_Diagnosis"),
        ("D2", "GT_Revised_Diagnosis"),
        ("D3", "GT_Final_Diagnosis"),
    ]
    for center_dir in sorted(CENTER_DATA_DIR.iterdir(), key=lambda p: p.name):
        if not center_dir.is_dir():
            continue
        gt_dir = center_dir / "GT"
        gt_files = sorted(gt_dir.glob("*.xlsx"))
        if not gt_files:
            continue
        gt_file = gt_files[0]
        try:
            gt_df = pd.read_excel(gt_file, sheet_name="Sheet1")
        except Exception:
            continue
        if gt_df.empty:
            continue
        case_col = "CaseID" if "CaseID" in gt_df.columns else ("病例ID" if "病例ID" in gt_df.columns else "")
        if not case_col:
            continue

        for _, row in gt_df.iterrows():
            case_id = str(row.get(case_col, "")).strip()
            if case_id == "" or case_id.lower() in {"nan", "none"}:
                continue
            for stage4, col in stage_cols:
                diag_text = row.get(col, "")
                palm_cat, palm_rule = _classify_palm_coein(diag_text)
                palm_cat, adjust_reason = _adjust_palm_label_by_rule(stage4, diag_text, palm_cat)
                records.append(
                    {
                        "center": center_dir.name,
                        "case_id": case_id,
                        "stage4": stage4,
                        "diag_text": str(diag_text or ""),
                        "palm_coein": palm_cat,
                        "rule_hit": palm_rule if adjust_reason == "" else f"{palm_rule}|{adjust_reason}",
                        "source_sheet": f"{gt_file.name}:Sheet1",
                        "source_column": col,
                        "source_path": str(gt_file.relative_to(ROOT)).replace("\\", "/"),
                    }
                )

    detail = pd.DataFrame.from_records(records)
    if detail.empty:
        raise RuntimeError("未从 GT 重建出 PALM-COEIN 分类明细")
    detail = _replace_d2_follow_with_previous_label(detail)
    detail["palm_coein"] = detail["palm_coein"].where(detail["palm_coein"].isin(PALM_COEIN_ORDER), "N-非肿瘤")
    summary_stage = (
        detail.groupby(["stage4", "palm_coein"], as_index=False)
        .agg(cases=("case_id", "nunique"))
        .sort_values(["stage4", "cases"], ascending=[True, False], kind="mergesort")
    )
    summary_overall = (
        detail.groupby("palm_coein", as_index=False)
        .agg(cases=("case_id", "nunique"))
        .sort_values("cases", ascending=False, kind="mergesort")
    )
    return detail, summary_stage, summary_overall


def _load_g1_llm_taxonomy() -> pd.DataFrame:
    if not G1_LLM_TAXONOMY_CSV.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(G1_LLM_TAXONOMY_CSV)
    except Exception:
        return pd.DataFrame()
    required_cols = {"center", "case_id", "d1_palm_class", "d2_palm_class", "d3_palm_class"}
    if not required_cols.issubset(set(df.columns)):
        return pd.DataFrame()
    out = df.copy()
    out["center"] = out["center"].astype(str)
    out["case_id"] = out["case_id"].astype(str)
    for col in ["d1_palm_class", "d2_palm_class", "d3_palm_class"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(9).astype(int)
    if "d1_palm_label" not in out.columns:
        out["d1_palm_label"] = out["d1_palm_class"].map(PALM_CLASS_TO_LABEL).fillna("N-非肿瘤")
    if "d2_palm_label" not in out.columns:
        out["d2_palm_label"] = out["d2_palm_class"].map(PALM_CLASS_TO_LABEL).fillna("N-非肿瘤")
    if "d3_palm_label" not in out.columns:
        out["d3_palm_label"] = out["d3_palm_class"].map(PALM_CLASS_TO_LABEL).fillna("N-非肿瘤")
    if "final_benign_malignant" not in out.columns:
        out["final_benign_malignant"] = "非肿瘤"
    out["final_benign_malignant_raw"] = (
        out["final_benign_malignant"]
        .astype(str)
        .str.strip()
        .replace({"": "非肿瘤", "nan": "非肿瘤", "None": "非肿瘤"})
    )
    out["final_benign_malignant"] = out["final_benign_malignant_raw"].replace(
        {
            "benign": "良性",
            "malignant": "恶性",
            "unknown": "非肿瘤",
            "其他": "非肿瘤",
            "不明确": "非肿瘤",
        }
    )
    # 口径纠偏：D3 PALM 若为 M-恶性/增生，则最终良恶性至少应为“恶性”
    out.loc[out["d3_palm_label"] == "M-恶性/增生", "final_benign_malignant"] = "恶性"
    # 若仍为空/异常，统一归一到三分类；不再将“非肿瘤”强制改写为“良性”
    out["final_benign_malignant"] = out["final_benign_malignant"].where(
        out["final_benign_malignant"].isin(["良性", "恶性", "非肿瘤"]),
        "非肿瘤",
    )
    for cls_col, lab_col in [
        ("surgery_plan_class", "surgery_plan_label"),
        ("postop_plan_class", "postop_plan_label"),
        ("rehab_plan_class", "rehab_plan_label"),
        ("followup_plan_class", "followup_plan_label"),
    ]:
        if cls_col in out.columns:
            out[cls_col] = pd.to_numeric(out[cls_col], errors="coerce").fillna(6).astype(int)
            if lab_col not in out.columns:
                out[lab_col] = out[cls_col].map(PLAN_CLASS_TO_LABEL).fillna("其他")
    return out


def _build_palm_coein_from_llm_taxonomy(
    llm_taxonomy: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if llm_taxonomy.empty:
        empty = pd.DataFrame()
        return empty, empty, empty, empty, empty

    records: list[dict[str, Any]] = []
    stage_spec = [
        ("D1", "d1_palm_class", "d1_palm_label"),
        ("D2", "d2_palm_class", "d2_palm_label"),
        ("D3", "d3_palm_class", "d3_palm_label"),
    ]
    diag_col_map = {"D1": "d1_diag", "D2": "d2_diag", "D3": "d3_diag"}
    for _, row in llm_taxonomy.iterrows():
        for stage4, cls_col, label_col in stage_spec:
            cls_num = pd.to_numeric(row.get(cls_col, 9), errors="coerce")
            raw_label = str(row.get(label_col, "N-非肿瘤")) or "N-非肿瘤"
            diag_text = row.get(diag_col_map.get(stage4, ""), "")
            adjusted_label, not_class_reason = _adjust_palm_label_by_rule(stage4, diag_text, raw_label)
            records.append(
                {
                    "center": str(row.get("center", "")),
                    "case_id": str(row.get("case_id", "")),
                    "stage4": stage4,
                    "palm_class": int(cls_num) if pd.notna(cls_num) else 9,
                    "palm_coein": adjusted_label,
                    "not_classify_reason": not_class_reason,
                    "source_sheet": str(row.get("source_gt_sheet", "Sheet1")),
                    "source_column": f"{cls_col}|rule_adjusted",
                    "source_path": str(row.get("source_gt_path", "")).replace("\\", "/"),
                    "source_model": str(row.get("model", "gemini-2.5-pro")),
                    "source_channel": str(row.get("channel", "gala_api")),
                    "source_prompt_version": str(row.get("prompt_version", "")),
                }
            )

    detail = pd.DataFrame.from_records(records)
    if detail.empty:
        empty = pd.DataFrame()
        return empty, empty, empty, empty, empty
    detail = _replace_d2_follow_with_previous_label(detail)
    detail["palm_coein"] = detail["palm_coein"].where(detail["palm_coein"].isin(PALM_COEIN_ORDER), "N-非肿瘤")
    summary_stage = (
        detail.groupby(["stage4", "palm_coein"], as_index=False)
        .agg(cases=("case_id", "nunique"))
    )
    summary_stage["palm_coein"] = pd.Categorical(summary_stage["palm_coein"], categories=PALM_COEIN_ORDER, ordered=True)
    summary_stage = summary_stage.sort_values(["stage4", "palm_coein"], ascending=[True, True], kind="mergesort")
    summary_overall = (
        detail[detail["stage4"] == "D3"]
        .groupby("palm_coein", as_index=False)
        .agg(cases=("case_id", "nunique"))
    )
    summary_overall["palm_coein"] = pd.Categorical(summary_overall["palm_coein"], categories=PALM_COEIN_ORDER, ordered=True)
    summary_overall = summary_overall.sort_values("palm_coein", kind="mergesort")
    bm_col = "final_benign_malignant"
    if bm_col not in llm_taxonomy.columns:
        bm_col = "d3_palm_label"
    summary_bm = (
        llm_taxonomy.groupby(bm_col, as_index=False)
        .agg(cases=("case_id", "nunique"))
        .sort_values("cases", ascending=False, kind="mergesort")
    )
    if bm_col == "d3_palm_label":
        summary_bm[bm_col] = summary_bm[bm_col].map(
            lambda x: "恶性" if str(x) == "M-恶性/增生" else ("非肿瘤" if str(x) == "N-非肿瘤" else "良性")
        )
    summary_bm[bm_col] = summary_bm[bm_col].replace(
        {"nan": "非肿瘤", "None": "非肿瘤", "": "非肿瘤"}
    )
    summary_bm = summary_bm.rename(columns={bm_col: "benign_malignant"})

    wide = (
        detail.pivot_table(index=["center", "case_id"], columns="stage4", values="palm_coein", aggfunc="first")
        .reset_index()
    )
    link_rows: list[dict[str, Any]] = []
    for stage_a, stage_b in [("D1", "D2"), ("D2", "D3")]:
        if stage_a not in wide.columns or stage_b not in wide.columns:
            continue
        pair = wide[[stage_a, stage_b]].dropna()
        if pair.empty:
            continue
        grouped = (
            pair.groupby([stage_a, stage_b], as_index=False)
            .size()
            .rename(columns={stage_a: "from_label", stage_b: "to_label", "size": "n_cases"})
        )
        grouped["from_stage"] = stage_a
        grouped["to_stage"] = stage_b
        link_rows.extend(grouped.to_dict(orient="records"))
    flow_links = pd.DataFrame(link_rows)
    return detail, summary_stage, summary_overall, flow_links, summary_bm


def _build_plan_continuity_from_llm_taxonomy(
    llm_taxonomy: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if llm_taxonomy.empty:
        empty = pd.DataFrame()
        return empty, empty, empty
    needed = {"surgery_plan_label", "postop_plan_label", "rehab_plan_label", "followup_plan_label"}
    if not needed.issubset(set(llm_taxonomy.columns)):
        empty = pd.DataFrame()
        return empty, empty, empty

    detail = pd.concat(
        [
            llm_taxonomy[["center", "case_id", "surgery_plan_label", "source_gt_path"]]
            .rename(columns={"surgery_plan_label": "plan_label"})
            .assign(plan_stage="Surgery"),
            llm_taxonomy[["center", "case_id", "postop_plan_label", "source_gt_path"]]
            .rename(columns={"postop_plan_label": "plan_label"})
            .assign(plan_stage="PostOp"),
            llm_taxonomy[["center", "case_id", "rehab_plan_label", "source_gt_path"]]
            .rename(columns={"rehab_plan_label": "plan_label"})
            .assign(plan_stage="Rehab"),
            llm_taxonomy[["center", "case_id", "followup_plan_label", "source_gt_path"]]
            .rename(columns={"followup_plan_label": "plan_label"})
            .assign(plan_stage="Followup"),
        ],
        ignore_index=True,
    )
    detail["plan_label"] = detail["plan_label"].where(detail["plan_label"].isin(PLAN_LABEL_ORDER), "其他")
    summary = (
        detail.groupby(["plan_stage", "plan_label"], as_index=False)
        .agg(cases=("case_id", "nunique"))
    )
    summary["plan_label"] = pd.Categorical(summary["plan_label"], categories=PLAN_LABEL_ORDER, ordered=True)
    summary = summary.sort_values(["plan_stage", "plan_label"], ascending=[True, True], kind="mergesort")

    wide = (
        detail.pivot_table(index=["center", "case_id"], columns="plan_stage", values="plan_label", aggfunc="first")
        .reset_index()
    )
    link_rows: list[dict[str, Any]] = []
    for stage_a, stage_b in zip(PLAN_STAGE_ORDER[:-1], PLAN_STAGE_ORDER[1:]):
        if stage_a not in wide.columns or stage_b not in wide.columns:
            continue
        pair = wide[[stage_a, stage_b]].dropna()
        if pair.empty:
            continue
        grouped = (
            pair.groupby([stage_a, stage_b], as_index=False)
            .size()
            .rename(columns={stage_a: "from_label", stage_b: "to_label", "size": "n_cases"})
        )
        grouped["from_stage"] = stage_a
        grouped["to_stage"] = stage_b
        link_rows.extend(grouped.to_dict(orient="records"))
    flow_links = pd.DataFrame(link_rows)
    return detail, summary, flow_links


def _build_stage_sankey_from_long(
    detail: pd.DataFrame,
    *,
    stage_col: str,
    label_col: str,
    stage_order: list[str],
    stage_label_map: dict[str, str],
    label_order: list[str],
    color_map: dict[str, str],
    out_path: Path,
    canvas_width: int = 1800,
    canvas_height: int = 920,
    show_all_labels: bool = False,
    annotate_with_n: bool = True,
    x_pad: float = 0.045,
    export_scale: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if detail.empty:
        return pd.DataFrame(), pd.DataFrame()
    needed = {"center", "case_id", stage_col, label_col}
    if not needed.issubset(set(detail.columns)):
        return pd.DataFrame(), pd.DataFrame()

    use = detail[["center", "case_id", stage_col, label_col]].copy()
    use["center"] = use["center"].astype(str)
    use["case_id"] = use["case_id"].astype(str)
    use[stage_col] = use[stage_col].astype(str)
    use[label_col] = use[label_col].astype(str)
    use = use[use[stage_col].isin(stage_order)]
    if use.empty:
        return pd.DataFrame(), pd.DataFrame()

    node_rows: list[dict[str, Any]] = []
    stage_nodes: dict[str, list[str]] = {}
    for stage in stage_order:
        sub = use[use[stage_col] == stage]
        if sub.empty:
            if show_all_labels:
                stage_nodes[stage] = [str(x) for x in label_order]
                for label in stage_nodes[stage]:
                    node_rows.append({"stage": stage, "label": label, "n_cases": 0})
            else:
                stage_nodes[stage] = []
            continue
        count = sub.groupby(label_col, as_index=False).agg(n_cases=("case_id", "nunique"))
        count[label_col] = pd.Categorical(count[label_col], categories=label_order, ordered=True)
        count = count.sort_values([label_col, "n_cases"], ascending=[True, False], kind="mergesort")
        if show_all_labels:
            labels = [str(x) for x in label_order]
            count_map = {str(row[label_col]): int(row["n_cases"]) for _, row in count.iterrows() if pd.notna(row[label_col])}
            stage_nodes[stage] = labels
            for label in labels:
                node_rows.append({"stage": stage, "label": label, "n_cases": int(count_map.get(label, 0))})
            continue
        labels = count[label_col].astype(str).tolist()
        stage_nodes[stage] = labels
        for _, row in count.iterrows():
            node_rows.append({"stage": stage, "label": str(row[label_col]), "n_cases": int(row["n_cases"])})

    wide = (
        use.pivot_table(index=["center", "case_id"], columns=stage_col, values=label_col, aggfunc="first")
        .reset_index()
    )
    link_rows: list[dict[str, Any]] = []
    for stage_a, stage_b in zip(stage_order[:-1], stage_order[1:]):
        if stage_a not in wide.columns or stage_b not in wide.columns:
            continue
        pair = wide[[stage_a, stage_b]].dropna()
        if pair.empty:
            continue
        grouped = (
            pair.groupby([stage_a, stage_b], as_index=False)
            .size()
            .rename(columns={stage_a: "from_label", stage_b: "to_label", "size": "n_cases"})
        )
        grouped["from_stage"] = stage_a
        grouped["to_stage"] = stage_b
        link_rows.extend(grouped.to_dict(orient="records"))

    node_df = pd.DataFrame(node_rows)
    link_df = pd.DataFrame(link_rows)
    if go is None:
        return node_df, link_df

    # 右侧最后一列在高分辨率导出时容易因节点厚度+标签外溢被裁切；
    # 支持调用方按图单独调节左右边距。
    x_pad = float(max(0.0, min(0.2, x_pad)))
    x_span = 1.0 - 2 * x_pad
    stage_x = {stage: x_pad + idx * (x_span / max(1, len(stage_order) - 1)) for idx, stage in enumerate(stage_order)}
    stage_n = {
        stage: int(use.loc[use[stage_col] == stage, "case_id"].nunique()) for stage in stage_order
    }
    node_index: dict[tuple[str, str], int] = {}
    labels: list[str] = []
    node_case_counts: list[int] = []
    node_stage_names: list[str] = []
    colors: list[str] = []
    xs: list[float] = []
    ys: list[float] = []
    counter = 0
    for stage_idx, stage in enumerate(stage_order):
        labels_in_stage = stage_nodes.get(stage, [])
        n = max(1, len(labels_in_stage))
        for idx, label in enumerate(labels_in_stage):
            node_index[(stage, label)] = counter
            # Plotly Sankey 在多阶段同名节点下，静态导出偶发末列节点“吞并/不显示”；
            # 这里附加零宽字符使标签在内部唯一，视觉保持不变。
            labels.append(f"{label}{chr(0x200B) * stage_idx}")
            colors.append(color_map.get(label, "#9AA0A6"))
            xs.append(stage_x[stage])
            ys.append((idx + 1) / (n + 1))
            counter += 1

    src: list[int] = []
    tar: list[int] = []
    val: list[float] = []
    lcolors: list[str] = []
    for _, row in link_df.iterrows():
        src_key = (str(row["from_stage"]), str(row["from_label"]))
        tar_key = (str(row["to_stage"]), str(row["to_label"]))
        if src_key not in node_index or tar_key not in node_index:
            continue
        src_idx = node_index[src_key]
        src.append(src_idx)
        tar.append(node_index[tar_key])
        val.append(float(row["n_cases"]))
        lcolors.append(_hex_to_rgba(colors[src_idx], 0.36))

    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="fixed",
                node=dict(
                    pad=16,
                    thickness=22,
                    line=dict(color="rgba(30,52,84,0.30)", width=0.85),
                    label=labels,
                    color=colors,
                    x=xs,
                    y=ys,
                ),
                link=dict(source=src, target=tar, value=val, color=lcolors),
            )
        ]
    )
    fig.update_layout(
        title_text="",
        font=dict(size=13, family="Microsoft YaHei, SimHei, Arial Unicode MS"),
        width=int(canvas_width),
        height=int(canvas_height),
        margin=dict(l=36, r=96, t=52, b=20),
        paper_bgcolor="#F8FBFF",
        plot_bgcolor="#F8FBFF",
        annotations=[
            dict(
                x=float(stage_x.get(stage, 0.0)),
                y=0.985,
                text=(
                    f"{stage_label_map.get(stage, stage)}<br>(n={stage_n.get(stage, 0)})"
                    if annotate_with_n
                    else f"{stage_label_map.get(stage, stage)}"
                ),
                showarrow=False,
                xanchor="center",
                yanchor="bottom",
                font=dict(size=15, family="Microsoft YaHei, SimHei, Arial Unicode MS"),
            )
            for stage in stage_order
        ],
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not _save_plotly_image_bundle(fig, out_path, scale=max(1, int(export_scale))):
        fig.write_html(str(out_path.with_suffix(".html")), include_plotlyjs="cdn")
    return node_df, link_df


def _status_not_evaluated(stage: str, status: Any) -> bool:
    s = str(status or "").strip()
    if s == "" or s.lower() in {"nan", "none"}:
        return True
    if "未经过" in s:
        return True
    if stage == "D2_Decision" and ("此前已中止" in s):
        return True
    return False


def _extract_round_score_cols(columns: list[Any]) -> list[str]:
    scored: list[tuple[int, str]] = []
    pat = re.compile(r"^第(\d+)轮_.*评分_综合评分$")
    for c in columns:
        cs = str(c)
        m = pat.match(cs)
        if m:
            scored.append((int(m.group(1)), cs))
    scored.sort(key=lambda x: x[0])
    return [c for _, c in scored]


def _to_float(v: Any) -> float:
    try:
        return float(pd.to_numeric(v, errors="coerce"))
    except Exception:
        return float("nan")


def _load_s1_judge_scores_from_center_raw() -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    if not CENTER_DATA_DIR.exists():
        raise FileNotFoundError(f"center_data目录不存在: {CENTER_DATA_DIR}")

    for center_dir in sorted(CENTER_DATA_DIR.iterdir(), key=lambda p: p.name):
        if not center_dir.is_dir():
            continue
        center = center_dir.name
        judge_dir = center_dir / "judge agent"
        if not judge_dir.exists():
            continue

        for model_full in MODEL_SHORT:
            judge_file = judge_dir / f"Evaluation_Summary_{model_full}_CN_Judge_Parsed.xlsx"
            if not judge_file.exists():
                continue

            # D1/D2 loop：按已执行轮次综合评分均值×5；未经过不参与
            for stage, sheet in [("D1_Loop", "D1_Outpatient_Loop"), ("D2_Loop", "D2_Admission_Loop")]:
                try:
                    df = pd.read_excel(judge_file, sheet_name=sheet)
                except Exception:
                    continue
                if df.empty:
                    continue
                case_col = "病例ID" if "病例ID" in df.columns else ("case_id" if "case_id" in df.columns else "")
                if not case_col:
                    continue
                status_col = "状态" if "状态" in df.columns else (str(df.columns[1]) if len(df.columns) > 1 else "")
                round_cols = _extract_round_score_cols(list(df.columns))
                if not round_cols:
                    continue
                for _, row in df.iterrows():
                    case_id = str(row.get(case_col, "")).strip()
                    if case_id == "" or case_id.lower() in {"nan", "none"}:
                        continue
                    status_val = row.get(status_col, "")
                    if _status_not_evaluated(stage, status_val):
                        score_0_5 = np.nan
                    else:
                        vals = pd.to_numeric(pd.Series([row.get(c, np.nan) for c in round_cols]), errors="coerce").dropna()
                        score_0_5 = float(vals.mean() * 5.0) if len(vals) > 0 else np.nan
                    records.append(
                        {
                            "center": center,
                            "model": model_full,
                            "case_id": case_id,
                            "stage": stage,
                            "judge_score_0_5_new": score_0_5,
                            "judge_source_sheet_new": f"{judge_file.name}:{sheet}",
                            "judge_source_col_new": "+".join(round_cols),
                            "judge_rule_new": "loop_mean(第X轮_评分_综合评分)*5；状态含未经过则不参与",
                            "judge_status_raw_new": str(status_val),
                            "judge_source_path_new": str(judge_file.relative_to(ROOT)).replace("\\", "/"),
                        }
                    )

            # D1 决策：0.7*诊断匹配 + 0.3*检查匹配，再×5
            try:
                d1d = pd.read_excel(judge_file, sheet_name="D1_Outpatient_Decision")
            except Exception:
                d1d = pd.DataFrame()
            if not d1d.empty:
                case_col = "病例ID" if "病例ID" in d1d.columns else ("case_id" if "case_id" in d1d.columns else "")
                status_col = "状态" if "状态" in d1d.columns else (str(d1d.columns[1]) if len(d1d.columns) > 1 else "")
                diag_col = (
                    "Gate1判官_原始JSON_诊断匹配_评分"
                    if "Gate1判官_原始JSON_诊断匹配_评分" in d1d.columns
                    else _find_col_by_keywords(list(d1d.columns), ["Gate1", "诊断匹配", "评分"], ["综合", "检查"])
                )
                chk_col = (
                    "Gate1判官_原始JSON_检查匹配_评分"
                    if "Gate1判官_原始JSON_检查匹配_评分" in d1d.columns
                    else _find_col_by_keywords(list(d1d.columns), ["Gate1", "检查匹配", "评分"], ["匹配度"])
                )
                comp_col = (
                    "Gate1判官_原始JSON_综合评分"
                    if "Gate1判官_原始JSON_综合评分" in d1d.columns
                    else _find_col_by_keywords(list(d1d.columns), ["Gate1", "综合评分"])
                )
                if case_col and diag_col and chk_col:
                    for _, row in d1d.iterrows():
                        case_id = str(row.get(case_col, "")).strip()
                        if case_id == "" or case_id.lower() in {"nan", "none"}:
                            continue
                        status_val = row.get(status_col, "")
                        diag_v = _to_float(row.get(diag_col, np.nan))
                        chk_v = _to_float(row.get(chk_col, np.nan))
                        if _status_not_evaluated("D1_Decision", status_val):
                            score_0_5 = np.nan
                        elif np.isfinite(diag_v) and np.isfinite(chk_v):
                            score_0_5 = float((diag_v * 0.7 + chk_v * 0.3) * 5.0)
                        else:
                            comp_v = _to_float(row.get(comp_col, np.nan)) if comp_col else np.nan
                            score_0_5 = float(comp_v * 5.0) if np.isfinite(comp_v) else np.nan
                        records.append(
                            {
                                "center": center,
                                "model": model_full,
                                "case_id": case_id,
                                "stage": "D1_Decision",
                                "judge_score_0_5_new": score_0_5,
                                "judge_source_sheet_new": f"{judge_file.name}:D1_Outpatient_Decision",
                                "judge_source_col_new": f"0.7*{diag_col}+0.3*{chk_col}",
                                "judge_rule_new": "D1决策综合评分=0.7*诊断匹配评分+0.3*检查匹配评分，再*5",
                                "judge_status_raw_new": str(status_val),
                                "judge_source_path_new": str(judge_file.relative_to(ROOT)).replace("\\", "/"),
                            }
                        )

            # D2/D3/D4 决策：综合评分×5（未经过/此前已中止不参与）
            stage_specs = [
                ("D2_Decision", "D2_Admission_Decision", ["Gate2", "综合评分"]),
                ("D3_Decision", "D3_Surgery_Decision", ["判官", "综合评分"]),
                ("D4_Plan", "D4_Rehab_Plan", ["判官", "综合评分"]),
            ]
            for stage, sheet, must in stage_specs:
                try:
                    df = pd.read_excel(judge_file, sheet_name=sheet)
                except Exception:
                    continue
                if df.empty:
                    continue
                case_col = "病例ID" if "病例ID" in df.columns else ("case_id" if "case_id" in df.columns else "")
                if not case_col:
                    continue
                status_col = "状态" if "状态" in df.columns else (str(df.columns[1]) if len(df.columns) > 1 else "")
                score_col = _find_col_by_keywords(list(df.columns), must)
                if not score_col:
                    continue
                for _, row in df.iterrows():
                    case_id = str(row.get(case_col, "")).strip()
                    if case_id == "" or case_id.lower() in {"nan", "none"}:
                        continue
                    status_val = row.get(status_col, "")
                    if _status_not_evaluated(stage, status_val):
                        score_0_5 = np.nan
                    else:
                        score_v = _to_float(row.get(score_col, np.nan))
                        score_0_5 = float(score_v * 5.0) if np.isfinite(score_v) else np.nan
                    records.append(
                        {
                            "center": center,
                            "model": model_full,
                            "case_id": case_id,
                            "stage": stage,
                            "judge_score_0_5_new": score_0_5,
                            "judge_source_sheet_new": f"{judge_file.name}:{sheet}",
                            "judge_source_col_new": score_col,
                            "judge_rule_new": "决策环节综合评分*5；状态为未经过/此前已中止则不参与",
                            "judge_status_raw_new": str(status_val),
                            "judge_source_path_new": str(judge_file.relative_to(ROOT)).replace("\\", "/"),
                        }
                    )
    if not records:
        raise RuntimeError("未能从 center_data/*/judge agent 重建 S1 judge 评分")
    out = pd.DataFrame.from_records(records)
    out["case_id"] = out["case_id"].astype(str)
    return out


def _load_g2_diag_from_center_judge(
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
) -> pd.DataFrame:
    records: list[pd.DataFrame] = []
    if not CENTER_DATA_DIR.exists():
        raise FileNotFoundError(f"center_data目录不存在: {CENTER_DATA_DIR}")

    stage_spec = [
        (
            "D1_Decision",
            "D1_Outpatient_Decision",
            "Gate1判官_原始JSON_诊断匹配_评分",
            ["Gate1", "诊断匹配", "评分"],
            ["综合", "检查"],
        ),
        (
            "D2_Decision",
            "D2_Admission_Decision",
            "Gate2判官_原始JSON_修正诊断匹配_评分",
            ["Gate2", "修正诊断", "评分"],
            ["综合", "方案"],
        ),
        (
            "D3_Decision",
            "D3_Surgery_Decision",
            "判官_原始JSON_诊断匹配评估_评分",
            ["判官", "诊断匹配评估", "评分"],
            ["综合", "方案"],
        ),
    ]

    for center_dir in sorted(CENTER_DATA_DIR.iterdir()):
        if not center_dir.is_dir():
            continue
        center = center_dir.name
        judge_dir = center_dir / "judge agent"
        if not judge_dir.exists():
            continue
        for model_full in MODEL_SHORT:
            judge_file = judge_dir / f"Evaluation_Summary_{model_full}_CN_Judge_Parsed.xlsx"
            if not judge_file.exists():
                continue

            for stage, sheet, expected_col, must, must_not in stage_spec:
                try:
                    raw = pd.read_excel(judge_file, sheet_name=sheet)
                except Exception:
                    continue
                if raw.empty:
                    continue

                case_col = "病例ID" if "病例ID" in raw.columns else ("case_id" if "case_id" in raw.columns else "")
                if not case_col:
                    continue
                score_col = expected_col if expected_col in raw.columns else _find_col_by_keywords(list(raw.columns), must, must_not)
                if not score_col:
                    continue

                out = raw[[case_col, score_col]].copy()
                out = out.rename(columns={case_col: "case_id"})
                out["center"] = center
                out["model"] = model_full
                out["model_short"] = MODEL_SHORT.get(model_full, model_full)
                out["stage"] = stage
                out["value"] = pd.to_numeric(out[score_col], errors="coerce")
                out["source_sheet"] = f"{judge_file.name}:{sheet}"
                out["source_column"] = score_col
                out["source_path"] = str(judge_file.relative_to(ROOT)).replace("\\", "/")
                out["case_id"] = out["case_id"].astype(str)
                out = out.drop(columns=[score_col]).dropna(subset=["value"])
                records.append(out)

    if not records:
        raise RuntimeError("未能从 center_data/*/judge agent 读取 G2-A 诊断评分明细")

    diag = pd.concat(records, ignore_index=True)
    diag = _attach_rules(diag, d1_set, gate3_set)
    diag = diag[~diag["is_d1_anomaly"]].copy()
    return diag


def _load_g2_plan_from_center_judge(
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    if not CENTER_DATA_DIR.exists():
        raise FileNotFoundError(f"center_data目录不存在: {CENTER_DATA_DIR}")

    for center_dir in sorted(CENTER_DATA_DIR.iterdir()):
        if not center_dir.is_dir():
            continue
        center = center_dir.name
        judge_dir = center_dir / "judge agent"
        if not judge_dir.exists():
            continue
        for model_full in MODEL_SHORT:
            judge_file = judge_dir / f"Evaluation_Summary_{model_full}_CN_Judge_Parsed.xlsx"
            if not judge_file.exists():
                continue

            # D2: 术前方案匹配评分
            try:
                d2 = pd.read_excel(judge_file, sheet_name="D2_Admission_Decision")
            except Exception:
                d2 = pd.DataFrame()
            if not d2.empty:
                case_col = "病例ID" if "病例ID" in d2.columns else ("case_id" if "case_id" in d2.columns else "")
                status_col = "状态" if "状态" in d2.columns else (str(d2.columns[1]) if len(d2.columns) > 1 else "")
                score_col = (
                    "Gate2判官_原始JSON_手术方案匹配_评分"
                    if "Gate2判官_原始JSON_手术方案匹配_评分" in d2.columns
                    else _find_col_by_keywords(list(d2.columns), ["Gate2", "手术方案匹配", "评分"], ["反馈", "理由", "结论", "综合"])
                )
                if case_col and score_col:
                    for _, row in d2.iterrows():
                        case_id = str(row.get(case_col, "")).strip()
                        if case_id == "" or case_id.lower() in {"nan", "none"}:
                            continue
                        status_val = row.get(status_col, "")
                        if _status_not_evaluated("D2_Decision", status_val):
                            score = np.nan
                        else:
                            score = _to_float(row.get(score_col, np.nan))
                        records.append(
                            {
                                "center": center,
                                "model": model_full,
                                "case_id": case_id,
                                "model_short": MODEL_SHORT.get(model_full, model_full),
                                "stage": "D2_Decision",
                                "value": score,
                                "source_sheet": f"{judge_file.name}:D2_Admission_Decision",
                                "source_column": score_col,
                                "source_path": str(judge_file.relative_to(ROOT)).replace("\\", "/"),
                                "source_rule": "D2方案正确性=Gate2判官_原始JSON_手术方案匹配_评分",
                            }
                        )

            # D3: 术后治疗方案匹配评分
            try:
                d3 = pd.read_excel(judge_file, sheet_name="D3_Surgery_Decision")
            except Exception:
                d3 = pd.DataFrame()
            if not d3.empty:
                case_col = "病例ID" if "病例ID" in d3.columns else ("case_id" if "case_id" in d3.columns else "")
                status_col = "状态" if "状态" in d3.columns else (str(d3.columns[1]) if len(d3.columns) > 1 else "")
                score_col = (
                    "判官_原始JSON_治疗方案匹配评估_评分"
                    if "判官_原始JSON_治疗方案匹配评估_评分" in d3.columns
                    else _find_col_by_keywords(list(d3.columns), ["判官", "治疗方案匹配评估", "评分"], ["反馈", "理由", "结论", "综合"])
                )
                if case_col and score_col:
                    for _, row in d3.iterrows():
                        case_id = str(row.get(case_col, "")).strip()
                        if case_id == "" or case_id.lower() in {"nan", "none"}:
                            continue
                        status_val = row.get(status_col, "")
                        if _status_not_evaluated("D3_Decision", status_val):
                            score = np.nan
                        else:
                            score = _to_float(row.get(score_col, np.nan))
                        records.append(
                            {
                                "center": center,
                                "model": model_full,
                                "case_id": case_id,
                                "model_short": MODEL_SHORT.get(model_full, model_full),
                                "stage": "D3_Decision",
                                "value": score,
                                "source_sheet": f"{judge_file.name}:D3_Surgery_Decision",
                                "source_column": score_col,
                                "source_path": str(judge_file.relative_to(ROOT)).replace("\\", "/"),
                                "source_rule": "D3方案正确性=判官_原始JSON_治疗方案匹配评估_评分",
                            }
                        )

            # D4: 随访与康复计划，取康复/随访两项评分均值
            try:
                d4 = pd.read_excel(judge_file, sheet_name="D4_Rehab_Plan")
            except Exception:
                d4 = pd.DataFrame()
            if not d4.empty:
                case_col = "病例ID" if "病例ID" in d4.columns else ("case_id" if "case_id" in d4.columns else "")
                status_col = "状态" if "状态" in d4.columns else (str(d4.columns[1]) if len(d4.columns) > 1 else "")
                rehab_col = (
                    "判官_原始JSON_康复计划评估_评分"
                    if "判官_原始JSON_康复计划评估_评分" in d4.columns
                    else _find_col_by_keywords(list(d4.columns), ["康复计划评估", "评分"], ["反馈", "理由", "结论", "综合"])
                )
                follow_col = (
                    "判官_原始JSON_随访计划评估_评分"
                    if "判官_原始JSON_随访计划评估_评分" in d4.columns
                    else _find_col_by_keywords(list(d4.columns), ["随访计划评估", "评分"], ["反馈", "理由", "结论", "综合"])
                )
                if case_col and (rehab_col or follow_col):
                    for _, row in d4.iterrows():
                        case_id = str(row.get(case_col, "")).strip()
                        if case_id == "" or case_id.lower() in {"nan", "none"}:
                            continue
                        status_val = row.get(status_col, "")
                        if _status_not_evaluated("D4_Plan", status_val):
                            score = np.nan
                        else:
                            vals = []
                            if rehab_col:
                                vals.append(_to_float(row.get(rehab_col, np.nan)))
                            if follow_col:
                                vals.append(_to_float(row.get(follow_col, np.nan)))
                            vals = [v for v in vals if np.isfinite(v)]
                            score = float(np.mean(vals)) if vals else np.nan
                        records.append(
                            {
                                "center": center,
                                "model": model_full,
                                "case_id": case_id,
                                "model_short": MODEL_SHORT.get(model_full, model_full),
                                "stage": "D4_Plan",
                                "value": score,
                                "source_sheet": f"{judge_file.name}:D4_Rehab_Plan",
                                "source_column": f"mean({rehab_col or '康复评分缺失'},{follow_col or '随访评分缺失'})",
                                "source_path": str(judge_file.relative_to(ROOT)).replace("\\", "/"),
                                "source_rule": "D4方案正确性=mean(康复计划评估_评分,随访计划评估_评分)",
                            }
                        )

    if not records:
        raise RuntimeError("未能从 center_data/*/judge agent 读取 G2-D 方案评分明细")
    plan = pd.DataFrame.from_records(records)
    plan["case_id"] = plan["case_id"].astype(str)
    plan["value"] = pd.to_numeric(plan["value"], errors="coerce")
    plan = plan.dropna(subset=["value"]).copy()
    plan = _attach_rules(plan, d1_set, gate3_set)
    plan = plan[~plan["is_d1_anomaly"]].copy()
    return plan


def _extract_round_json_cols(columns: list[Any], role: str) -> dict[int, str]:
    """提取“第X轮_<角色>_原始JSON”列（仅主 JSON 列，不含派生子字段）。"""
    out: dict[int, str] = {}
    role_pat = "判官" if role == "judge" else "医生"
    pat = re.compile(rf"^第(\d+)轮_{role_pat}_原始JSON$")
    for c in columns:
        s = str(c)
        m = pat.match(s)
        if not m:
            continue
        try:
            idx = int(m.group(1))
        except Exception:
            continue
        out[idx] = s
    return out


def _load_check_loop_trace_raw_for_source() -> pd.DataFrame:
    """读取 D1/D2 检查环节原始文本（doc+judge），用于 source data 可追溯。"""
    key_cols = ["center", "model", "case_id"]
    records_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    if not CENTER_DATA_DIR.exists():
        return pd.DataFrame(columns=key_cols)

    def _ensure_rec(center: str, model: str, case_id: str) -> dict[str, Any]:
        key = (center, model, case_id)
        if key not in records_map:
            records_map[key] = {
                "center": center,
                "model": model,
                "case_id": case_id,
                "model_short": MODEL_SHORT.get(model, model),
                "source_doc_path": "",
                "source_judge_path": "",
            }
        return records_map[key]

    stage_specs = [
        ("D1_Outpatient_Loop", "d1"),
        ("D2_Admission_Loop", "d2"),
    ]

    for center_dir in sorted(CENTER_DATA_DIR.iterdir(), key=lambda p: p.name):
        if not center_dir.is_dir():
            continue
        center = center_dir.name
        doc_dir = center_dir / "doc agent"
        judge_dir = center_dir / "judge agent"
        for model_full in MODEL_SHORT:
            doc_file = doc_dir / f"Evaluation_Summary_{model_full}_CN_Parsed.xlsx"
            judge_file = judge_dir / f"Evaluation_Summary_{model_full}_CN_Judge_Parsed.xlsx"

            for file_kind, xlsx_path in [("doc", doc_file), ("judge", judge_file)]:
                if not xlsx_path.exists():
                    continue
                for sheet_name, stage_tag in stage_specs:
                    try:
                        df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
                    except Exception:
                        continue
                    if df.empty:
                        continue
                    case_col = "病例ID" if "病例ID" in df.columns else ("case_id" if "case_id" in df.columns else "")
                    if not case_col:
                        continue
                    status_col = "状态" if "状态" in df.columns else (str(df.columns[1]) if len(df.columns) > 1 else "")
                    round_cols = _extract_round_json_cols(list(df.columns), role=("judge" if file_kind == "judge" else "doc"))
                    for _, row in df.iterrows():
                        case_id = str(row.get(case_col, "")).strip()
                        if case_id == "" or case_id.lower() in {"nan", "none"}:
                            continue
                        rec = _ensure_rec(center, model_full, case_id)
                        rec[f"{stage_tag}_{file_kind}_status_raw"] = str(row.get(status_col, "")).strip()
                        rec[f"source_{file_kind}_path"] = str(xlsx_path.relative_to(ROOT)).replace("\\", "/")
                        for ridx in range(1, 5):
                            col = round_cols.get(ridx, "")
                            rec[f"{stage_tag}_round{ridx}_{file_kind}_raw_json"] = str(row.get(col, "")).strip() if col else ""

    if not records_map:
        return pd.DataFrame(columns=key_cols)
    out = pd.DataFrame.from_records(list(records_map.values()))
    out["center"] = out["center"].astype(str)
    out["model"] = out["model"].astype(str)
    out["case_id"] = out["case_id"].astype(str)
    return out.sort_values(["center", "model", "case_id"], kind="mergesort").reset_index(drop=True)


def _adaptive_ylim(
    values: pd.Series,
    fallback: tuple[float, float],
    domain: tuple[float | None, float | None] | None = None,
    min_span: float = 0.12,
) -> tuple[float, float]:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    if vals.empty:
        return fallback
    lo = float(vals.min())
    hi = float(vals.max())
    span = hi - lo
    if span < 1e-8:
        span = min_span
        lo -= span / 2.0
        hi += span / 2.0
    pad = max(span * 0.15, min_span * 0.25)
    lo2 = lo - pad
    hi2 = hi + pad
    if domain is not None:
        d_lo, d_hi = domain
        if d_lo is not None:
            lo2 = max(float(d_lo), lo2)
        if d_hi is not None:
            hi2 = min(float(d_hi), hi2)
    if hi2 - lo2 < min_span:
        mid = (hi2 + lo2) / 2.0
        lo2 = mid - min_span / 2.0
        hi2 = mid + min_span / 2.0
        if domain is not None:
            d_lo, d_hi = domain
            if d_lo is not None and lo2 < d_lo:
                shift = d_lo - lo2
                lo2 += shift
                hi2 += shift
            if d_hi is not None and hi2 > d_hi:
                shift = hi2 - d_hi
                lo2 -= shift
                hi2 -= shift
    return lo2, hi2


def _plot_band_scatter(
    ax: plt.Axes,
    detail: pd.DataFrame,
    value_col: str,
    stage_order: list[str],
    stage_label_map: dict[str, str],
    title: str,
    y_label: str,
    ylim: tuple[float, float] | None = None,
    mean_color: str = "#1f77b4",
) -> None:
    if detail.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.set_title(title)
        return

    detail = detail.copy()
    detail["stage"] = detail["stage"].astype(str)
    detail["model_short"] = detail["model_short"].astype(str)
    summary = (
        detail.groupby(["stage", "model_short"], as_index=False)[value_col]
        .mean()
        .rename(columns={value_col: "model_mean"})
    )
    stage_stats = (
        summary.groupby("stage", as_index=False)["model_mean"]
        .agg(["mean", "std"])
        .reset_index()
        .rename(columns={"mean": "mean", "std": "std"})
    )
    stage_stats["std"] = stage_stats["std"].fillna(0.0)
    x = np.arange(len(stage_order))
    stat_map = {r["stage"]: (float(r["mean"]), float(r["std"])) for _, r in stage_stats.iterrows()}
    y = np.array([stat_map.get(s, (np.nan, np.nan))[0] for s in stage_order], dtype=float)
    y_std = np.array([stat_map.get(s, (np.nan, np.nan))[1] for s in stage_order], dtype=float)
    ax.plot(x, y, color=mean_color, linewidth=2.6, label="Mean (all models)")
    ax.fill_between(x, y - y_std, y + y_std, color=mean_color, alpha=0.22, label="SD ribbon")

    for model in MODEL_ORDER:
        sub = summary[summary["model_short"] == model]
        if sub.empty:
            continue
        m = {r["stage"]: float(r["model_mean"]) for _, r in sub.iterrows()}
        ys = [m.get(s, np.nan) for s in stage_order]
        ax.scatter(
            x,
            ys,
            s=48,
            marker=MODEL_MARKER.get(model, "o"),
            color=MODEL_COLOR.get(model, "#666666"),
            alpha=0.92,
            label=model,
            zorder=3,
        )

    ax.set_xticks(x)
    ax.set_xticklabels([stage_label_map.get(s, s) for s in stage_order])
    ax.set_title(title)
    ax.set_ylabel(y_label)
    if ylim:
        ax.set_ylim(*ylim)
    ax.grid(alpha=0.25)


def _build_manual_vs_target_plot(
    detail: pd.DataFrame,
    out_path: Path,
    score_col_human: str,
    score_col_target: str,
    title: str,
    y_label: str,
    show_scatter: bool = True,
) -> None:
    fig, ax = plt.subplots(figsize=(13.5, 5.2))
    _plot_manual_vs_target_on_ax(
        ax=ax,
        detail=detail,
        score_col_human=score_col_human,
        score_col_target=score_col_target,
        title=title,
        y_label=y_label,
        show_legend=True,
        show_scatter=show_scatter,
    )
    _save_fig(out_path)


def _build_manual_vs_target_legend_handles(
    human_line_color: str,
    human_band_color: str,
    target_line_color: str,
    target_band_color: str,
    include_scatter: bool = True,
) -> list[Line2D]:
    handles: list[Line2D] = [
        Line2D([0], [0], color=human_line_color, linewidth=2.2, label="医生均值"),
        Line2D([0], [0], color=human_band_color, linewidth=6.0, alpha=0.55, label="医生误差带"),
        Line2D([0], [0], color=target_line_color, linewidth=2.6, label="LLM/Judge 均值"),
        Line2D([0], [0], color=target_band_color, linewidth=6.0, alpha=0.55, label="LLM/Judge 误差带"),
    ]
    if not include_scatter:
        return handles
    handles.extend(
        [
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="None",
                markerfacecolor="none",
                markeredgecolor="#4a4a4a",
                markeredgewidth=1.4,
                markersize=7,
                label="医生散点（按模型）",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="None",
                markerfacecolor="#4a4a4a",
                markeredgecolor="white",
                markeredgewidth=0.6,
                markersize=7,
                label="LLM/Judge散点（按模型）",
            ),
        ]
    )
    for model in MODEL_ORDER:
        handles.append(
            Line2D(
                [0],
                [0],
                marker=MODEL_MARKER.get(model, "o"),
                linestyle="None",
                markerfacecolor=MODEL_COLOR.get(model, "#666666"),
                markeredgecolor="#333333",
                markeredgewidth=0.4,
                markersize=7,
                label=model,
            )
        )
    return handles


def _plot_manual_vs_target_on_ax(
    ax: plt.Axes,
    detail: pd.DataFrame,
    score_col_human: str,
    score_col_target: str,
    title: str,
    y_label: str,
    show_legend: bool = True,
    human_line_color: str = "#6C757D",
    human_band_color: str = "#6C757D",
    target_line_color: str = "#1f77b4",
    target_band_color: str = "#1f77b4",
    human_band_alpha: float = 0.34,
    target_band_alpha: float = 0.34,
    stage_blocks: bool = False,
    stage_block_palette: list[str] | None = None,
    stage_block_alpha: float = 0.22,
    show_scatter: bool = True,
) -> None:
    detail = detail.copy()
    detail["stage"] = detail["stage"].astype(str)
    detail["model_short"] = detail["model_short"].astype(str)
    stage_order = STAGE6_ORDER
    x = np.arange(len(stage_order))
    if stage_blocks:
        _apply_stage_progress_blocks(ax, palette=stage_block_palette, alpha=stage_block_alpha)

    agg_h = (
        detail.groupby(["stage", "model_short"], as_index=False)[score_col_human]
        .mean()
        .rename(columns={score_col_human: "h"})
    )
    agg_t = (
        detail.groupby(["stage", "model_short"], as_index=False)[score_col_target]
        .mean()
        .rename(columns={score_col_target: "t"})
    )
    st_h = agg_h.groupby("stage", as_index=False)["h"].agg(["mean", "std"]).reset_index()
    st_t = agg_t.groupby("stage", as_index=False)["t"].agg(["mean", "std"]).reset_index()
    st_h["std"] = st_h["std"].fillna(0)
    st_t["std"] = st_t["std"].fillna(0)
    hm = {r["stage"]: (float(r["mean"]), float(r["std"])) for _, r in st_h.iterrows()}
    tm = {r["stage"]: (float(r["mean"]), float(r["std"])) for _, r in st_t.iterrows()}
    hy = np.array([hm.get(s, (np.nan, np.nan))[0] for s in stage_order], dtype=float)
    hs = np.array([hm.get(s, (np.nan, np.nan))[1] for s in stage_order], dtype=float)
    ty = np.array([tm.get(s, (np.nan, np.nan))[0] for s in stage_order], dtype=float)
    ts = np.array([tm.get(s, (np.nan, np.nan))[1] for s in stage_order], dtype=float)
    ax.plot(
        x,
        hy,
        color=human_line_color,
        linewidth=2.25,
        marker="o",
        markersize=4.2,
        label="医生均值",
        zorder=3,
    )
    ax.fill_between(
        x,
        hy - hs,
        hy + hs,
        color=human_band_color,
        alpha=human_band_alpha,
        label="医生误差带",
        zorder=1.6,
    )
    ax.plot(x, hy - hs, color=human_band_color, linewidth=0.95, alpha=min(0.8, human_band_alpha + 0.12), zorder=1.85)
    ax.plot(x, hy + hs, color=human_band_color, linewidth=0.95, alpha=min(0.8, human_band_alpha + 0.12), zorder=1.85)
    ax.plot(
        x,
        ty,
        color=target_line_color,
        linewidth=2.65,
        marker="o",
        markersize=4.4,
        label="LLM/Judge 均值",
        zorder=3.1,
    )
    ax.fill_between(
        x,
        ty - ts,
        ty + ts,
        color=target_band_color,
        alpha=target_band_alpha,
        label="LLM/Judge 误差带",
        zorder=1.7,
    )
    ax.plot(x, ty - ts, color=target_band_color, linewidth=0.95, alpha=min(0.8, target_band_alpha + 0.12), zorder=1.9)
    ax.plot(x, ty + ts, color=target_band_color, linewidth=0.95, alpha=min(0.8, target_band_alpha + 0.12), zorder=1.9)
    if show_scatter:
        for model in MODEL_ORDER:
            sub_t = agg_t[agg_t["model_short"] == model]
            sub_h = agg_h[agg_h["model_short"] == model]
            mt = {r["stage"]: float(r["t"]) for _, r in sub_t.iterrows()} if not sub_t.empty else {}
            mh = {r["stage"]: float(r["h"]) for _, r in sub_h.iterrows()} if not sub_h.empty else {}
            ys_t = [mt.get(s, np.nan) for s in stage_order]
            ys_h = [mh.get(s, np.nan) for s in stage_order]
            # LLM/Judge 侧散点：实心
            ax.scatter(
                x,
                ys_t,
                marker=MODEL_MARKER.get(model, "o"),
                color=MODEL_COLOR.get(model, "#666666"),
                s=55,
                alpha=0.9,
                zorder=3,
                edgecolors="white",
                linewidths=0.5,
            )
            # 医生侧散点：空心（同模型同形状），用于区分评分来源
            ax.scatter(
                x,
                ys_h,
                marker=MODEL_MARKER.get(model, "o"),
                facecolors="none",
                edgecolors=MODEL_COLOR.get(model, "#666666"),
                s=78,
                alpha=0.95,
                zorder=4,
                linewidths=1.35,
            )
    ax.set_xticks(x)
    ax.set_xticklabels([STAGE6_CN.get(s, s) for s in stage_order], rotation=0)
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.grid(alpha=0.25)
    if show_legend:
        handles = _build_manual_vs_target_legend_handles(
            human_line_color=human_line_color,
            human_band_color=human_band_color,
            target_line_color=target_line_color,
            target_band_color=target_band_color,
            include_scatter=show_scatter,
        )
        ax.legend(handles=handles, loc="upper center", ncol=(6 if show_scatter else 4), fontsize=8, frameon=True)


def _plot_manual_vs_target_line_on_ax(
    ax: plt.Axes,
    detail: pd.DataFrame,
    score_col_human: str,
    score_col_target: str,
    title: str,
    y_label: str,
    human_label: str = "医生",
    target_label: str = "Judge",
    human_color: str = "#D77F72",
    target_color: str = "#7A3E9D",
    bg_colors: list[str] | None = None,
    stage_order: list[str] | None = None,
    stage_label_map: dict[str, str] | None = None,
    block_labels: list[str] | None = None,
    legend_mode: str = "lower_right",
    show_legend: bool = True,
) -> None:
    """S1 替代方案：纯折线（无条带），方形点标记，三段背景柔和过渡。"""
    d = detail.copy()
    d["stage"] = d["stage"].astype(str)
    d["model_short"] = d["model_short"].astype(str)
    stage_order = stage_order or STAGE6_ORDER
    x = np.arange(len(stage_order), dtype=float)

    agg_h = (
        d.groupby(["stage", "model_short"], as_index=False)[score_col_human]
        .mean()
        .rename(columns={score_col_human: "h"})
    )
    agg_t = (
        d.groupby(["stage", "model_short"], as_index=False)[score_col_target]
        .mean()
        .rename(columns={score_col_target: "t"})
    )
    h_stage = agg_h.groupby("stage", as_index=False)["h"].mean()
    t_stage = agg_t.groupby("stage", as_index=False)["t"].mean()
    h_stage_std = agg_h.groupby("stage", as_index=False)["h"].std().fillna(0.0)
    t_stage_std = agg_t.groupby("stage", as_index=False)["t"].std().fillna(0.0)
    hm = {str(r["stage"]): float(r["h"]) for _, r in h_stage.iterrows()}
    tm = {str(r["stage"]): float(r["t"]) for _, r in t_stage.iterrows()}
    hs = {str(r["stage"]): float(r["h"]) for _, r in h_stage_std.iterrows()}
    ts = {str(r["stage"]): float(r["t"]) for _, r in t_stage_std.iterrows()}
    hy = np.array([hm.get(s, np.nan) for s in stage_order], dtype=float)
    ty = np.array([tm.get(s, np.nan) for s in stage_order], dtype=float)
    hy_sd = np.array([hs.get(s, 0.0) for s in stage_order], dtype=float)
    ty_sd = np.array([ts.get(s, 0.0) for s in stage_order], dtype=float)

    if len(stage_order) == 6:
        _apply_s1_gradient_blocks(
            ax,
            colors=bg_colors or ["#F2DCCF", "#E6DACE", "#D9D5CD"],
            labels=block_labels or ["门诊阶段", "入院阶段", "术后与随访阶段"],
            alpha=0.36,
        )
    else:
        palette_raw = bg_colors or ["#F2DCCF", "#E6DACE", "#D9D5CD", "#D4D9E2"]
        if len(palette_raw) >= len(stage_order):
            palette = palette_raw[: len(stage_order)]
        else:
            start_c = palette_raw[0]
            end_c = palette_raw[-1]
            palette = [_blend_hex_color(start_c, end_c, (i + 1) / max(1, len(stage_order))) for i in range(len(stage_order))]
        for i, _s in enumerate(stage_order):
            ax.axvspan(i - 0.5, i + 0.5, color=palette[i], alpha=(0.24 + 0.12 * i), zorder=0.02)

    ax.fill_between(
        x,
        hy - hy_sd,
        hy + hy_sd,
        color=human_color,
        alpha=0.16,
        linewidth=0,
        zorder=2.6,
    )
    ax.fill_between(
        x,
        ty - ty_sd,
        ty + ty_sd,
        color=target_color,
        alpha=0.14,
        linewidth=0,
        zorder=2.65,
    )

    ax.plot(
        x,
        hy,
        color=human_color,
        linewidth=2.55,
        marker="s",
        markersize=8.8,
        markerfacecolor="white",
        markeredgecolor=human_color,
        markeredgewidth=1.9,
        label=human_label,
        zorder=3.1,
    )
    ax.plot(
        x,
        ty,
        color=target_color,
        linewidth=2.75,
        marker="s",
        markersize=9.0,
        markerfacecolor="white",
        markeredgecolor=target_color,
        markeredgewidth=2.0,
        label=target_label,
        zorder=3.2,
    )

    ax.set_xlim(-0.5, len(stage_order) - 0.5)
    ax.set_ylim(0.0, 5.0)
    ax.yaxis.set_major_locator(MultipleLocator(1.0))
    ax.set_xticks(x)
    label_map = stage_label_map or STAGE6_CN
    ax.set_xticklabels([label_map.get(s, s) for s in stage_order], rotation=0, fontsize=17)
    ax.tick_params(axis="y", labelsize=17)
    ax.set_ylabel(y_label, fontsize=20)
    ax.set_title(title, fontsize=21, pad=12, fontweight="bold")
    ax.grid(alpha=0.20, axis="y", linestyle="--", linewidth=0.8)
    if show_legend:
        if legend_mode == "pill_top":
            lg = ax.legend(
                loc="upper left",
                bbox_to_anchor=(0.01, 1.035),
                fontsize=15.2,
                frameon=True,
                fancybox=True,
                framealpha=0.98,
                edgecolor="#98A9B9",
                borderpad=0.48,
                handlelength=2.2,
                ncol=2,
                columnspacing=1.8,
            )
            try:
                lg.get_frame().set_facecolor("#F7FBFF")
                lg.get_frame().set_linewidth(1.35)
            except Exception:
                pass
        else:
            ax.legend(
                loc="lower right",
                bbox_to_anchor=(0.985, 0.04),
                fontsize=15,
                frameon=True,
                fancybox=True,
                framealpha=0.9,
                borderpad=0.45,
                handlelength=2.0,
                ncol=1,
            )
    _set_full_axis_border(ax)


def build_g1_dataset() -> dict[str, Path]:
    group = "G1_dataset"
    out_img = OUT_FIG_DIR / group / "G1_dataset_overview_v2.png"
    out_img_all_sankey = OUT_FIG_DIR / group / "G1_dataset_overview_all_sankey_v1.png"
    out_img_no_sankey = OUT_FIG_DIR / group / "G1_dataset_overview_no_sankey_v1.png"
    out_img_no_sankey_e_alt = OUT_FIG_DIR / group / "G1_dataset_overview_no_sankey_e_alt_v1.png"
    out_img_no_sankey_e_alt_2row = OUT_FIG_DIR / group / "G1_dataset_overview_no_sankey_e_alt_2row_v1.png"
    out_stage_detail = OUT_FIG_DIR / group / "G1b_stage_category_detail_v1.png"
    out_palm_stage = OUT_FIG_DIR / group / "G1b_palm_coein_stage_stack_v1.png"
    out_palm_stage_bar = OUT_FIG_DIR / group / "G1b_palm_coein_stage_bar_v1.png"
    out_palm_dist = OUT_FIG_DIR / group / "G1h_palm_coein_distribution_v1.png"
    out_e_palm_bar = OUT_FIG_DIR / group / "G1e_longtail_palm_bar_v1.png"
    out_e_palm_line = OUT_FIG_DIR / group / "G1e_longtail_palm_line_v1.png"
    out_plan_cont = OUT_FIG_DIR / group / "G1g_plan_continuity_sankey_v1.png"
    out_plan_mix_bar = OUT_FIG_DIR / group / "G1g_plan_mix_stacked_bar_v1.png"
    out_plan_split_bar = OUT_FIG_DIR / group / "G1g_plan_prepost_rehab_followup_v1.png"

    center = _safe_read_csv(PAPER_FIGDATA_DIR / "Fig1a__dataset_center_counts.csv")
    diag_stage = _safe_read_csv(PAPER_FIGDATA_DIR / "Fig1b__dataset_diagnosis_category_by_stage.csv")
    text_len = _safe_read_csv(PAPER_FIGDATA_DIR / "Fig1c__dataset_case_text_length.csv")
    icd = _safe_read_csv(PAPER_FIGDATA_DIR / "Fig1k__dataset_icd10_chapter_counts.csv")
    longtail = _safe_read_csv(PAPER_FIGDATA_DIR / "Fig1h__dataset_diagnosis_longtail.csv")
    check_type = _safe_read_csv(PAPER_FIGDATA_DIR / "Fig1f__dataset_check_type_counts.csv")
    plan_type = _safe_read_csv(PAPER_FIGDATA_DIR / "Fig1g__dataset_plan_type_counts.csv")
    llm_taxonomy = _load_g1_llm_taxonomy()
    if not llm_taxonomy.empty:
        try:
            icd_llm = _build_icd_chapter_from_llm_taxonomy(llm_taxonomy)
            if not icd_llm.empty:
                icd = icd_llm
        except Exception:
            pass

    palm_detail = pd.DataFrame()
    palm_stage = pd.DataFrame()
    palm_overall = pd.DataFrame()
    palm_flow_links = pd.DataFrame()
    bm_summary = pd.DataFrame()
    if not llm_taxonomy.empty:
        try:
            palm_detail, palm_stage, palm_overall, palm_flow_links, bm_summary = _build_palm_coein_from_llm_taxonomy(llm_taxonomy)
        except Exception:
            palm_detail = pd.DataFrame()
            palm_stage = pd.DataFrame()
            palm_overall = pd.DataFrame()
            palm_flow_links = pd.DataFrame()
            bm_summary = pd.DataFrame()
    if palm_detail.empty:
        try:
            palm_detail, palm_stage, palm_overall = _build_palm_coein_from_gt()
        except Exception:
            palm_detail = pd.DataFrame()
            palm_stage = pd.DataFrame()
            palm_overall = pd.DataFrame()

    plan_detail = pd.DataFrame()
    plan_summary = pd.DataFrame()
    plan_flow_links = pd.DataFrame()
    if not llm_taxonomy.empty:
        try:
            plan_detail, plan_summary, plan_flow_links = _build_plan_continuity_from_llm_taxonomy(llm_taxonomy)
        except Exception:
            plan_detail = pd.DataFrame()
            plan_summary = pd.DataFrame()
            plan_flow_links = pd.DataFrame()

    g1_center_colors = ["#3A6EA5", "#5B8EC1", "#A9C3DE", "#D0DFEE", "#E2ECF7"]
    g1_bm_colors = {"良性": "#6FA8DC", "恶性": "#2F6FA8", "非肿瘤": "#A6BBD1"}
    g1_palm_color = _build_blue_shades(
        PALM_COEIN_ORDER,
        fixed_last={"数据缺失": "#AEB6C2", "不适用": "#7F8691"},
    )
    g1_plan_color = _build_blue_shades(
        PLAN_LABEL_ORDER,
        fixed_last={"无/未提及": "#8F95A3"},
    )
    g1_panel_bg = "#F6FAFF"
    g1_grid_color = "#C7D8EA"

    fig = plt.figure(figsize=(18.6, 12.9))
    gs = fig.add_gridspec(3, 6, hspace=0.52, wspace=0.55)
    ax_a = fig.add_subplot(gs[0, 0:2])
    ax_b = fig.add_subplot(gs[0, 2:6])
    ax_c = fig.add_subplot(gs[1, 0:2])
    ax_d = fig.add_subplot(gs[1, 2:4])
    ax_e = fig.add_subplot(gs[1, 4:6])
    ax_f = fig.add_subplot(gs[2, 0:3])
    ax_g = fig.add_subplot(gs[2, 3:6])

    # a: 中心分布环图（外圈=中心；内圈=良恶性）
    c_name_map = {"Foshan": "佛山", "Wuhan": "武汉", "Xinjiang": "新疆"}
    if not center.empty:
        labels = [c_name_map.get(str(x), str(x)) for x in center["Center"]]
        values = center["Cases"].astype(float).to_numpy()
        total = int(values.sum())
        outer_colors = g1_center_colors
        ax_a.pie(
            values,
            labels=labels,
            autopct=lambda p: f"{p:.1f}%",
            pctdistance=0.84,
            startangle=140,
            radius=1.0,
            wedgeprops={"width": 0.30, "edgecolor": "white"},
            colors=outer_colors[: len(values)],
            textprops={"fontsize": 10},
        )
        outer_legend_labels = labels
        outer_leg = ax_a.legend(
            outer_legend_labels,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.03),
            fontsize=8,
            frameon=False,
            ncol=min(3, len(outer_legend_labels)),
        )
        ax_a.add_artist(outer_leg)
        bm_use = bm_summary.copy()
        if bm_use.empty and (not llm_taxonomy.empty):
            tmp = llm_taxonomy.copy()
            tmp["final_benign_malignant"] = tmp["d3_palm_label"].astype(str).map(
                lambda x: "恶性" if x == "M-恶性/增生" else ("非肿瘤" if x == "N-非肿瘤" else "良性")
            )
            bm_use = tmp.groupby("final_benign_malignant", as_index=False).agg(cases=("case_id", "nunique"))
            bm_use = bm_use.rename(columns={"final_benign_malignant": "benign_malignant"})
        if not bm_use.empty and {"benign_malignant", "cases"}.issubset(bm_use.columns):
            bm_order = ["良性", "恶性", "非肿瘤"]
            bm2 = bm_use.copy()
            bm2["benign_malignant"] = pd.Categorical(bm2["benign_malignant"], categories=bm_order, ordered=True)
            bm2 = bm2.sort_values("benign_malignant", kind="mergesort")
            bm2 = bm2[bm2["cases"] > 0]
            if not bm2.empty:
                ax_a.pie(
                    bm2["cases"].to_numpy(),
                    labels=None,
                    radius=0.67,
                    startangle=140,
                    autopct=lambda p: f"{p:.1f}%",
                    pctdistance=0.68,
                    wedgeprops={"width": 0.29, "edgecolor": "white"},
                    colors=[g1_bm_colors.get(str(x), "#A6BBD1") for x in bm2["benign_malignant"]],
                    textprops={"fontsize": 9, "color": "#1F1F1F"},
                )
                legend_labels = [str(row["benign_malignant"]) for _, row in bm2.iterrows()]
                ax_a.legend(
                    legend_labels,
                    loc="lower center",
                    bbox_to_anchor=(0.5, -0.16),
                    fontsize=8,
                    frameon=False,
                    ncol=min(3, len(legend_labels)),
                )
        ax_a.text(0, 0, f"N={total}", ha="center", va="center", fontsize=12, fontweight="bold")
    ax_a.set_title("a 样本中心与良恶性分布")

    # b: PALM-COEIN 三阶段 Sankey（优先）；缺失时退回堆叠占比
    palm_node_df = pd.DataFrame()
    palm_stage_pct = pd.DataFrame()
    if not palm_stage.empty:
        palm_node_df, palm_flow_links2 = _build_stage_sankey_from_long(
            palm_detail.rename(columns={"stage4": "stage", "palm_coein": "label"}),
            stage_col="stage",
            label_col="label",
            stage_order=["D1", "D2", "D3"],
            stage_label_map={"D1": "初步诊断", "D2": "修正诊断", "D3": "最终诊断"},
            label_order=PALM_COEIN_ORDER,
            color_map=g1_palm_color,
            out_path=out_palm_stage,
            canvas_width=3000,
            canvas_height=1450,
            show_all_labels=True,
            annotate_with_n=False,
        )
        if not palm_flow_links2.empty:
            palm_flow_links = palm_flow_links2
        # 生成非 Sankey 备用图（百分比堆叠）
        pv = (
            palm_stage.groupby(["stage4", "palm_coein"], as_index=False)["cases"]
            .sum()
            .pivot(index="stage4", columns="palm_coein", values="cases")
            .fillna(0.0)
            .reindex(["D1", "D2", "D3"])
        )
        for cat in PALM_COEIN_ORDER:
            if cat not in pv.columns:
                pv[cat] = 0.0
        pv = pv[PALM_COEIN_ORDER]
        palm_stage_pct = pv.div(pv.sum(axis=1), axis=0).fillna(0.0) * 100.0
        fig_pb, ax_pb = plt.subplots(figsize=(12.8, 6.4))
        ylab = ["初步诊断", "修正诊断", "最终诊断"]
        y = np.arange(len(ylab))
        left = np.zeros(len(palm_stage_pct))
        active_palm = [c for c in PALM_COEIN_ORDER if float(palm_stage_pct[c].sum()) > 0.0]
        if "不适用" in palm_stage_pct.columns and "不适用" not in active_palm:
            active_palm.append("不适用")
        palm_bar_color_map = {k: g1_palm_color.get(k, "#7FA7D1") for k in active_palm}
        for cat in active_palm:
            vals = palm_stage_pct[cat].to_numpy()
            ax_pb.barh(
                y,
                vals,
                left=left,
                label=cat,
                color=palm_bar_color_map.get(cat, "#7FA7D1"),
                height=0.62,
            )
            left += vals
        ax_pb.set_xlim(0, 100)
        ax_pb.set_yticks(y)
        ax_pb.set_yticklabels(ylab)
        ax_pb.invert_yaxis()
        ax_pb.set_xlabel("病例占比 (%)")
        ax_pb.set_title("b PALM-COEIN分型随诊断阶段变化", pad=14)
        ax_pb.grid(alpha=0.22, axis="x")
        pb_handles = _build_circle_legend_handles(active_palm, palm_bar_color_map, marker_size=7.6)
        ax_pb.legend(
            handles=pb_handles,
            loc="lower left",
            bbox_to_anchor=(0.0, 1.10, 1.0, 0.25),
            mode="expand",
            fontsize=8.2,
            frameon=False,
            ncol=max(1, len(active_palm)),
            handlelength=1.8,
            handletextpad=0.4,
        )
        _save_fig(out_palm_stage_bar)
        if out_palm_stage.exists():
            _draw_image_panel(ax_b, out_palm_stage, title="", aspect="auto")
        else:
            stage_order_cn = ["D1", "D2", "D3"]
            stage_label = {"D1": "初步诊断", "D2": "修正诊断", "D3": "最终诊断"}
            pv = (
                palm_stage.groupby(["stage4", "palm_coein"], as_index=False)["cases"]
                .sum()
                .pivot(index="stage4", columns="palm_coein", values="cases")
                .fillna(0.0)
                .reindex(stage_order_cn)
            )
            for cat in PALM_COEIN_ORDER:
                if cat not in pv.columns:
                    pv[cat] = 0.0
            pv = pv[PALM_COEIN_ORDER]
            pct = pv.div(pv.sum(axis=1), axis=0).fillna(0.0) * 100.0
            bottom = np.zeros(len(pct))
            xlab = [stage_label.get(s, s) for s in pct.index]
            for cat in PALM_COEIN_ORDER:
                vals = pct[cat].to_numpy()
                ax_b.bar(
                    xlab,
                    vals,
                    bottom=bottom,
                    label=cat,
                    color=g1_palm_color.get(cat, "#7FA7D1"),
                    width=0.62,
                )
                bottom += vals
            ax_b.set_ylim(0, 100)
            ax_b.set_ylabel("病例占比 (%)")
            b_handles = _build_circle_legend_handles(PALM_COEIN_ORDER, g1_palm_color, marker_size=7.4)
            ax_b.legend(handles=b_handles, loc="upper right", fontsize=7.2, frameon=False, ncol=2)
            ax_b.set_title("b PALM-COEIN分型随诊断阶段变化")
    elif not diag_stage.empty:
        stage_map = {"Admission": "D1 (初诊)", "Revised": "D2 (修订)", "Final": "D3 (终诊)"}
        diag_stage = diag_stage.copy()
        diag_stage["StageCN"] = diag_stage["Stage"].map(stage_map).fillna(diag_stage["Stage"].astype(str))
        diag_stage["Category2"] = (
            diag_stage["DiagnosisCategory"]
            .astype(str)
            .str.replace("其他/未分类", "其他", regex=False)
            .str.replace("其他未分类", "其他", regex=False)
        )
        top6 = (
            diag_stage.groupby("Category2", as_index=False)["Cases"]
            .sum()
            .sort_values("Cases", ascending=False)
            .head(6)["Category2"]
            .tolist()
        )
        diag_stage["Category2"] = diag_stage["Category2"].where(diag_stage["Category2"].isin(top6), "其他")
        pv = (
            diag_stage.groupby(["StageCN", "Category2"], as_index=False)["Cases"]
            .sum()
            .pivot(index="StageCN", columns="Category2", values="Cases")
            .fillna(0)
        )
        order = ["D1 (初诊)", "D2 (修订)", "D3 (终诊)"]
        pv = pv.reindex(order)
        pct = pv.div(pv.sum(axis=1), axis=0).fillna(0) * 100
        bottom = np.zeros(len(pct))
        color_pool = ["#BCD2E8", "#A7C4E4", "#8DB4DC", "#71A1D1", "#558CC5", "#3A77B8", "#1F5FA8"]
        for idx, col in enumerate(pct.columns):
            vals = pct[col].to_numpy()
            ax_b.bar(pct.index, vals, bottom=bottom, label=col, color=color_pool[idx % len(color_pool)], width=0.6)
            bottom += vals
        ax_b.set_ylim(0, 100)
        ax_b.set_ylabel("病例占比 (%)")
        ax_b.legend(loc="upper right", fontsize=8, frameon=False, ncol=2)
        ax_b.set_title("b 诊断类别随阶段变化")
    else:
        ax_b.set_title("b PALM-COEIN分型随诊断阶段变化")

    # c: 文本长度分布
    if not text_len.empty and "TextLen" in text_len.columns:
        vals = pd.to_numeric(text_len["TextLen"], errors="coerce").dropna()
        ax_c.hist(vals, bins=24, color="#AFC7E3", edgecolor="#4E7EAF", alpha=0.88, linewidth=0.9)
        if len(vals) > 0:
            med = float(np.median(vals))
            ax_c.axvline(med, color="#2E5F97", linestyle="--", linewidth=1.3, label=f"Median={med:.0f}")
            ax_c.legend(loc="upper right", fontsize=8, frameon=False)
        ax_c.set_xlabel("临床文本长度（非空格字符，含标点）")
        ax_c.set_ylabel("频数")
        ax_c.grid(alpha=0.24, axis="y", linestyle="--", linewidth=0.8, color=g1_grid_color)
        ax_c.set_facecolor(g1_panel_bg)
    ax_c.set_title("c 病例文本长度分布")

    # d: ICD10 编码分布（按最终诊断编码聚合）
    if not icd.empty:
        icd2 = icd.copy()
        if "ICD10Code" not in icd2.columns:
            if "ICD10Chapter" in icd2.columns:
                icd2["ICD10Code"] = icd2["ICD10Chapter"].astype(str)
            else:
                icd2["ICD10Code"] = "UNK"
        icd2["ICD10Code"] = icd2["ICD10Code"].astype(str).str.strip().str.upper()
        icd2["Cases"] = pd.to_numeric(icd2.get("Cases", 0), errors="coerce").fillna(0.0)
        icd2 = icd2.groupby("ICD10Code", as_index=False)["Cases"].sum().sort_values("Cases", ascending=True).tail(10)
        icd_vals = icd2["Cases"].to_numpy(dtype=float)
        if len(icd_vals) > 0:
            vmin = float(np.min(icd_vals))
            vmax = float(np.max(icd_vals))
            denom = max(vmax - vmin, 1e-9)
            shades = [0.45 + 0.45 * ((float(v) - vmin) / denom) for v in icd_vals]
            icd_colors = [to_hex(plt.get_cmap("Blues")(s)) for s in shades]
        else:
            icd_colors = "#4F8CC9"
        ax_d.barh(icd2["ICD10Code"], icd2["Cases"], color=icd_colors, edgecolor="#3E6F9E", linewidth=0.8, alpha=0.95)
        ax_d.tick_params(axis="y", labelsize=8)
        ax_d.set_xlabel("病例数")
        ax_d.grid(alpha=0.24, axis="x", linestyle="--", linewidth=0.8, color=g1_grid_color)
        ax_d.set_facecolor(g1_panel_bg)
    ax_d.set_title("d ICD-10编码分布")

    # e: 长尾分布
    if not longtail.empty and {"Diagnosis", "Cases"}.issubset(longtail.columns):
        tail = longtail.sort_values("Cases", ascending=False).reset_index(drop=True)
        tail["rank"] = np.arange(1, len(tail) + 1)
        ax_e.plot(tail["rank"], tail["Cases"], color="#2E5F97", linewidth=1.8, marker="o", markersize=3.6)
        ax_e.fill_between(tail["rank"], tail["Cases"], color="#9EC1E3", alpha=0.22)
        rare_ratio = float((tail["Cases"] <= 2).mean()) if len(tail) else 0.0
        ax_e.annotate(
            f"{rare_ratio * 100:.1f}% 低频病例",
            xy=(max(3, len(tail) * 0.05), max(1.0, tail["Cases"].median() if len(tail) else 1.0)),
            xytext=(max(8, len(tail) * 0.2), max(3.0, tail["Cases"].max() * 0.25 if len(tail) else 3.0)),
            arrowprops={"arrowstyle": "->", "lw": 1.2},
            fontsize=9,
        )
        ax_e.set_xlabel("诊断排名（按出现频次从高到低）")
        ax_e.set_ylabel("出现次数（病例频次）")
        ax_e.grid(alpha=0.24, axis="both", linestyle="--", linewidth=0.8, color=g1_grid_color)
        ax_e.set_facecolor(g1_panel_bg)
    ax_e.set_title("e 诊断长尾分布")

    # f: 检查谱系（门诊/住院）- 改为直接从 GT 文本字段重建
    check_type_detail = pd.DataFrame()
    try:
        check_type_detail, check_type = _build_g1_check_type_from_gt()
    except Exception:
        # 兜底：保留旧CSV（若存在），但优先应走 GT 重建
        pass

    if not check_type.empty:
        stage_map = {"Outpatient": "D1（门诊）", "Admission": "D2（住院）"}
        check2 = check_type.copy()
        check2["StageCN"] = check2["Stage"].map(stage_map).fillna(check2["Stage"].astype(str))
        pv = (
            check2.groupby(["Category", "StageCN"], as_index=False)["Cases"]
            .sum()
            .pivot(index="Category", columns="StageCN", values="Cases")
            .fillna(0)
        )
        cat_order = ["实验室检查", "影像学检查", "内镜检查", "病理学检查", "其他检查"]
        pv = pv.reindex([c for c in cat_order if c in pv.index] + [c for c in pv.index if c not in cat_order])
        x = np.arange(len(pv.index))
        w = 0.34
        d1 = pv["D1（门诊）"] if "D1（门诊）" in pv.columns else pd.Series([0] * len(pv.index), index=pv.index)
        d2 = pv["D2（住院）"] if "D2（住院）" in pv.columns else pd.Series([0] * len(pv.index), index=pv.index)
        ax_f.bar(x - w / 2, d1.to_numpy(), width=w, color="#3E74AF", edgecolor="#2E5F97", linewidth=0.75, label="D1（门诊）")
        ax_f.bar(x + w / 2, d2.to_numpy(), width=w, color="#9FC4E7", edgecolor="#5E8DB8", linewidth=0.75, label="D2（住院）")
        ax_f.set_xticks(x)
        ax_f.set_xticklabels(pv.index.tolist(), rotation=0)
        ax_f.set_ylabel("检查请求次数（病例×检查类型命中次数）")
        ax_f.legend(loc="upper right", fontsize=8, frameon=False)
        ax_f.grid(alpha=0.24, axis="y", linestyle="--", linewidth=0.8, color=g1_grid_color)
        ax_f.set_facecolor(g1_panel_bg)
    ax_f.set_title("f 门诊与住院检查类型分布")

    # g: 方案连续性（四阶段 Sankey；若缺失则退回原饼图）
    plan_node_df = pd.DataFrame()
    plan_stage_pct = pd.DataFrame()
    if not plan_detail.empty:
        plan_node_df, plan_flow_links2 = _build_stage_sankey_from_long(
            plan_detail.rename(columns={"plan_stage": "stage", "plan_label": "label"}),
            stage_col="stage",
            label_col="label",
            stage_order=PLAN_STAGE_ORDER,
            stage_label_map=PLAN_STAGE_LABEL,
            label_order=PLAN_LABEL_ORDER,
            color_map=g1_plan_color,
            out_path=out_plan_cont,
            canvas_width=3300,
            canvas_height=1700,
            show_all_labels=False,
            annotate_with_n=False,
            x_pad=0.11,
            export_scale=1,
        )
        if not plan_flow_links2.empty:
            plan_flow_links = plan_flow_links2
        # 非Sankey版1：四阶段百分比堆叠柱状图
        pv_plan = (
            plan_detail.groupby(["plan_stage", "plan_label"], as_index=False)["case_id"]
            .nunique()
            .rename(columns={"case_id": "cases"})
            .pivot(index="plan_stage", columns="plan_label", values="cases")
            .fillna(0.0)
            .reindex(PLAN_STAGE_ORDER)
        )
        for cat in PLAN_LABEL_ORDER:
            if cat not in pv_plan.columns:
                pv_plan[cat] = 0.0
        pv_plan = pv_plan[PLAN_LABEL_ORDER]
        plan_stage_pct = pv_plan.div(pv_plan.sum(axis=1), axis=0).fillna(0.0) * 100.0
        fig_pg_bar, ax_pg_bar = plt.subplots(figsize=(13.2, 6.4))
        y_plan = np.arange(len(plan_stage_pct))
        ylab_plan = [PLAN_STAGE_LABEL.get(s, s) for s in plan_stage_pct.index]
        left_plan = np.zeros(len(plan_stage_pct))
        active_plan = [c for c in PLAN_LABEL_ORDER if float(plan_stage_pct[c].sum()) > 0.0]
        if "无/未提及" in plan_stage_pct.columns and "无/未提及" not in active_plan:
            active_plan.append("无/未提及")
        plan_bar_color_map = {k: g1_plan_color.get(k, "#7FA7D1") for k in active_plan}
        for cat in active_plan:
            vals = plan_stage_pct[cat].to_numpy()
            ax_pg_bar.barh(
                y_plan,
                vals,
                left=left_plan,
                label=cat,
                color=plan_bar_color_map.get(cat, "#7FA7D1"),
                height=0.62,
            )
            left_plan += vals
        ax_pg_bar.set_xlim(0, 100)
        ax_pg_bar.set_yticks(y_plan)
        ax_pg_bar.set_yticklabels(ylab_plan)
        ax_pg_bar.invert_yaxis()
        ax_pg_bar.set_xlabel("病例占比 (%)")
        ax_pg_bar.set_title("g 术前术后及康复随访方案构成", pad=14)
        ax_pg_bar.grid(alpha=0.22, axis="x")
        pg_handles = _build_circle_legend_handles(active_plan, plan_bar_color_map, marker_size=7.6)
        ax_pg_bar.legend(
            handles=pg_handles,
            loc="lower left",
            bbox_to_anchor=(0.0, 1.10, 1.0, 0.25),
            mode="expand",
            fontsize=8.2,
            frameon=False,
            ncol=max(1, len(active_plan)),
            handlelength=1.8,
            handletextpad=0.4,
        )
        _save_fig(out_plan_mix_bar)

        # 非Sankey版2：拆分显示（术前/术后）与（康复/随访）
        fig_pg_split, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(14.8, 5.8), sharey=True)
        left_idx = [s for s in ["Surgery", "PostOp"] if s in plan_stage_pct.index]
        right_idx = [s for s in ["Rehab", "Followup"] if s in plan_stage_pct.index]
        for ax_sp, idx_list, ttl in [
            (ax_l, left_idx, "g1 术前/术后治疗策略构成"),
            (ax_r, right_idx, "g2 康复与随访方案构成"),
        ]:
            if not idx_list:
                ax_sp.axis("off")
                continue
            sub_pct = plan_stage_pct.loc[idx_list]
            xlab_sub = [PLAN_STAGE_LABEL.get(s, s) for s in sub_pct.index]
            bottom_sub = np.zeros(len(sub_pct))
            for cat in PLAN_LABEL_ORDER:
                vals = sub_pct[cat].to_numpy() if cat in sub_pct.columns else np.zeros(len(sub_pct))
                ax_sp.bar(
                    xlab_sub,
                    vals,
                    bottom=bottom_sub,
                    label=cat,
                    color=g1_plan_color.get(cat, "#7FA7D1"),
                    width=0.62,
                )
                bottom_sub += vals
            ax_sp.set_ylim(0, 100)
            ax_sp.set_title(ttl)
            ax_sp.grid(alpha=0.22, axis="y")
        ax_l.set_ylabel("病例占比 (%)")
        handles, labels = ax_r.get_legend_handles_labels()
        if handles:
            fig_pg_split.legend(handles, labels, loc="upper center", ncol=4, fontsize=8, frameon=False)
        fig_pg_split.suptitle("G1g 方案构成拆分视图（非Sankey）", fontsize=14, y=1.02)
        _save_fig(out_plan_split_bar)
        if out_plan_cont.exists():
            _draw_image_panel(ax_g, out_plan_cont, title="", aspect="auto")
        else:
            ax_g.axis("off")
            ax_g.set_title("g 四阶段方案连续性")
    elif not plan_type.empty:
        plan_agg = (
            plan_type.groupby("Category", as_index=False)["Cases"].sum().sort_values("Cases", ascending=False).head(5)
        )
        ax_g.pie(
            plan_agg["Cases"],
            labels=plan_agg["Category"],
            autopct=lambda p: f"{p:.1f}%",
            startangle=80,
            textprops={"fontsize": 9},
        )
        ax_g.set_title("g 术前术后及康复随访方案构成")
    else:
        ax_g.axis("off")
        ax_g.set_title("g 术前术后及康复随访方案构成")

    for border_ax in [ax_b, ax_c, ax_d, ax_e, ax_f]:
        _set_full_border(border_ax)
    if ax_g.axison:
        _set_full_border(ax_g)

    fig.suptitle("G1 数据集概况", fontsize=16, y=1.01)
    sub_figs = _save_subfigures(
        fig,
        group,
        {
            "G1a_center_distribution_v2": ax_a,
            "G1b_diagnosis_progression_v2": ax_b,
            "G1c_text_density_v2": ax_c,
            "G1d_icd_chapter_v2": ax_d,
            "G1e_longtail_v2": ax_e,
            "G1f_check_profile_v2": ax_f,
            "G1g_plan_mix_v2": ax_g,
        },
    )
    if out_plan_cont.exists() and ("G1g_plan_mix_v2" in sub_figs):
        try:
            shutil.copy2(out_plan_cont, sub_figs["G1g_plan_mix_v2"])
        except Exception:
            pass
    _save_fig(out_img)

    try:
        shutil.copy2(out_img, out_img_all_sankey)
    except Exception:
        pass

    # 无Sankey组图：复用子图并替换 b/g 为非Sankey版本
    if (
        ("G1a_center_distribution_v2" in sub_figs)
        and ("G1c_text_density_v2" in sub_figs)
        and ("G1d_icd_chapter_v2" in sub_figs)
        and ("G1e_longtail_v2" in sub_figs)
        and ("G1f_check_profile_v2" in sub_figs)
        and out_palm_stage_bar.exists()
        and out_plan_mix_bar.exists()
    ):
        fig_ns = plt.figure(figsize=(18.6, 12.9))
        gs_ns = fig_ns.add_gridspec(
            3,
            6,
            hspace=0.52,
            wspace=0.52,
            width_ratios=[2.2, 2.2, 1.55, 1.55, 1.55, 1.55],
            height_ratios=[1.08, 1.0, 1.08],
        )
        ax_ns_a = fig_ns.add_subplot(gs_ns[0, 0:2])
        ax_ns_b = fig_ns.add_subplot(gs_ns[0, 2:6])
        ax_ns_c = fig_ns.add_subplot(gs_ns[1, 0:2])
        ax_ns_d = fig_ns.add_subplot(gs_ns[1, 2:4])
        ax_ns_e = fig_ns.add_subplot(gs_ns[1, 4:6])
        ax_ns_f = fig_ns.add_subplot(gs_ns[2, 0:3])
        ax_ns_g = fig_ns.add_subplot(gs_ns[2, 3:6])
        # a：直接重绘，避免二次嵌图导致缩放失真
        if not center.empty:
            ns_labels = [c_name_map.get(str(x), str(x)) for x in center["Center"]]
            ns_values = center["Cases"].astype(float).to_numpy()
            ns_total = int(ns_values.sum())
            ax_ns_a.pie(
                ns_values,
                labels=ns_labels,
                autopct=lambda p: f"{p:.1f}%",
                pctdistance=0.84,
                startangle=140,
                radius=1.0,
                wedgeprops={"width": 0.30, "edgecolor": "white"},
                colors=g1_center_colors[: len(ns_values)],
                textprops={"fontsize": 10},
            )
            ns_outer_leg = ax_ns_a.legend(
                ns_labels,
                loc="lower center",
                bbox_to_anchor=(0.5, -0.03),
                fontsize=8,
                frameon=False,
                ncol=min(3, len(ns_labels)),
            )
            ax_ns_a.add_artist(ns_outer_leg)
            bm_ns = bm_summary.copy()
            if (bm_ns.empty) and (not llm_taxonomy.empty):
                tmp_ns = llm_taxonomy.copy()
                tmp_ns["benign_malignant"] = tmp_ns["d3_palm_label"].astype(str).map(
                    lambda x: "恶性" if x == "M-恶性/增生" else ("非肿瘤" if x == "N-非肿瘤" else "良性")
                )
                bm_ns = tmp_ns.groupby("benign_malignant", as_index=False).agg(cases=("case_id", "nunique"))
            if not bm_ns.empty and {"benign_malignant", "cases"}.issubset(bm_ns.columns):
                bm_ns["benign_malignant"] = pd.Categorical(
                    bm_ns["benign_malignant"], categories=["良性", "恶性", "非肿瘤"], ordered=True
                )
                bm_ns = bm_ns.sort_values("benign_malignant", kind="mergesort")
                bm_ns = bm_ns[bm_ns["cases"] > 0]
                if not bm_ns.empty:
                    ax_ns_a.pie(
                        bm_ns["cases"].to_numpy(),
                        labels=None,
                        radius=0.67,
                        startangle=140,
                        autopct=lambda p: f"{p:.1f}%",
                        pctdistance=0.68,
                        wedgeprops={"width": 0.29, "edgecolor": "white"},
                        colors=[g1_bm_colors.get(str(x), "#A6BBD1") for x in bm_ns["benign_malignant"]],
                        textprops={"fontsize": 9, "color": "#1F1F1F"},
                    )
                    ax_ns_a.legend(
                        [str(row["benign_malignant"]) for _, row in bm_ns.iterrows()],
                        loc="lower center",
                        bbox_to_anchor=(0.5, -0.16),
                        fontsize=8,
                        frameon=False,
                        ncol=min(3, len(bm_ns)),
                    )
            ax_ns_a.text(0, 0, f"N={ns_total}", ha="center", va="center", fontsize=12, fontweight="bold")
        ax_ns_a.set_title("a 样本中心与良恶性分布")
        if not palm_stage_pct.empty:
            ylab_b = ["初步诊断", "修正诊断", "最终诊断"]
            y_b = np.arange(len(ylab_b))
            left_b = np.zeros(len(ylab_b))
            active_palm_b = [c for c in PALM_COEIN_ORDER if c in palm_stage_pct.columns and float(palm_stage_pct[c].sum()) > 0.0]
            if "不适用" in palm_stage_pct.columns and "不适用" not in active_palm_b:
                active_palm_b.append("不适用")
            palm_bar_color_map_b = {k: g1_palm_color.get(k, "#7FA7D1") for k in active_palm_b}
            for cat in active_palm_b:
                vals = palm_stage_pct.loc[["D1", "D2", "D3"], cat].to_numpy() if cat in palm_stage_pct.columns else np.zeros(3)
                ax_ns_b.barh(
                    y_b,
                    vals,
                    left=left_b,
                    color=palm_bar_color_map_b.get(cat, "#7FA7D1"),
                    height=0.62,
                    label=cat,
                )
                left_b += vals
            ax_ns_b.set_xlim(0, 100)
            ax_ns_b.set_yticks(y_b)
            ax_ns_b.set_yticklabels(ylab_b)
            ax_ns_b.invert_yaxis()
            ax_ns_b.set_xlabel("病例占比 (%)", fontsize=8)
            ax_ns_b.set_title("b PALM-COEIN分型随诊断阶段变化", fontsize=11, y=0.97)
            ax_ns_b.grid(alpha=0.24, axis="x", linestyle="--", linewidth=0.8, color=g1_grid_color)
            ax_ns_b.set_facecolor(g1_panel_bg)
            ns_b_handles = _build_circle_legend_handles(active_palm_b, palm_bar_color_map_b, marker_size=7.0)
            ax_ns_b.legend(
                handles=ns_b_handles,
                loc="lower left",
                bbox_to_anchor=(0.0, 1.10, 1.0, 0.25),
                mode="expand",
                fontsize=7.8,
                frameon=False,
                ncol=max(1, len(active_palm_b)),
                handlelength=1.6,
                handletextpad=0.4,
            )
        else:
            _draw_image_panel(ax_ns_b, out_palm_stage_bar, "", aspect="equal")
        # c：直接重绘
        if not text_len.empty and "TextLen" in text_len.columns:
            vals_ns = pd.to_numeric(text_len["TextLen"], errors="coerce").dropna()
            ax_ns_c.hist(vals_ns, bins=24, color="#AFC7E3", edgecolor="#4E7EAF", alpha=0.88, linewidth=0.9)
            if len(vals_ns) > 0:
                med_ns = float(np.median(vals_ns))
                ax_ns_c.axvline(med_ns, color="#2E5F97", linestyle="--", linewidth=1.3, label=f"Median={med_ns:.0f}")
                ax_ns_c.legend(loc="upper right", fontsize=8, frameon=False)
            ax_ns_c.set_xlabel("临床文本长度（非空格字符，含标点）", fontsize=8)
            ax_ns_c.set_ylabel("频数")
            ax_ns_c.grid(alpha=0.24, axis="y", linestyle="--", linewidth=0.8, color=g1_grid_color)
            ax_ns_c.set_facecolor(g1_panel_bg)
        ax_ns_c.set_title("c 病例文本长度分布", fontsize=11, y=0.97)

        # d：直接重绘
        if not icd.empty:
            icd_ns = icd.copy()
            if "ICD10Code" not in icd_ns.columns:
                icd_ns["ICD10Code"] = icd_ns.get("ICD10Chapter", "UNK").astype(str)
            icd_ns["ICD10Code"] = icd_ns["ICD10Code"].astype(str).str.strip().str.upper()
            icd_ns["Cases"] = pd.to_numeric(icd_ns.get("Cases", 0), errors="coerce").fillna(0.0)
            icd_ns = icd_ns.groupby("ICD10Code", as_index=False)["Cases"].sum().sort_values("Cases", ascending=True).tail(10)
            icd_vals_ns = icd_ns["Cases"].to_numpy(dtype=float)
            if len(icd_vals_ns) > 0:
                vmin_ns = float(np.min(icd_vals_ns))
                vmax_ns = float(np.max(icd_vals_ns))
                denom_ns = max(vmax_ns - vmin_ns, 1e-9)
                shades_ns = [0.45 + 0.45 * ((float(v) - vmin_ns) / denom_ns) for v in icd_vals_ns]
                icd_colors_ns = [to_hex(plt.get_cmap("Blues")(s)) for s in shades_ns]
            else:
                icd_colors_ns = "#4F8CC9"
            ax_ns_d.barh(
                icd_ns["ICD10Code"],
                icd_ns["Cases"],
                color=icd_colors_ns,
                edgecolor="#3E6F9E",
                linewidth=0.8,
                alpha=0.95,
            )
            ax_ns_d.tick_params(axis="y", labelsize=7)
            ax_ns_d.set_xlabel("病例数", fontsize=8)
            ax_ns_d.grid(alpha=0.24, axis="x", linestyle="--", linewidth=0.8, color=g1_grid_color)
            ax_ns_d.set_facecolor(g1_panel_bg)
        ax_ns_d.set_title("d ICD-10编码分布", fontsize=11, y=0.97)

        # e：直接重绘
        if not longtail.empty and {"Diagnosis", "Cases"}.issubset(longtail.columns):
            tail_ns = longtail.sort_values("Cases", ascending=False).reset_index(drop=True)
            tail_ns["rank"] = np.arange(1, len(tail_ns) + 1)
            ax_ns_e.plot(tail_ns["rank"], tail_ns["Cases"], color="#2E5F97", linewidth=1.8, marker="o", markersize=3.4)
            ax_ns_e.fill_between(tail_ns["rank"], tail_ns["Cases"], color="#9EC1E3", alpha=0.22)
            rare_ratio_ns = float((tail_ns["Cases"] <= 2).mean()) if len(tail_ns) else 0.0
            ax_ns_e.annotate(
                f"{rare_ratio_ns * 100:.1f}% 低频病例",
                xy=(max(3, len(tail_ns) * 0.05), max(1.0, tail_ns["Cases"].median() if len(tail_ns) else 1.0)),
                xytext=(max(8, len(tail_ns) * 0.2), max(3.0, tail_ns["Cases"].max() * 0.25 if len(tail_ns) else 3.0)),
                arrowprops={"arrowstyle": "->", "lw": 1.2},
                fontsize=8,
            )
            ax_ns_e.set_xlabel("诊断排名（按出现频次从高到低）", fontsize=8)
            ax_ns_e.set_ylabel("出现次数（病例频次）")
            ax_ns_e.grid(alpha=0.24, axis="both", linestyle="--", linewidth=0.8, color=g1_grid_color)
            ax_ns_e.set_facecolor(g1_panel_bg)
        ax_ns_e.set_title("e 诊断长尾分布", fontsize=11, y=0.97)

        # f：直接重绘
        if not check_type.empty:
            check_ns = check_type.copy()
            check_ns["StageCN"] = check_ns["Stage"].map({"Outpatient": "D1（门诊）", "Admission": "D2（住院）"}).fillna(
                check_ns["Stage"].astype(str)
            )
            pv_ns = (
                check_ns.groupby(["Category", "StageCN"], as_index=False)["Cases"]
                .sum()
                .pivot(index="Category", columns="StageCN", values="Cases")
                .fillna(0)
            )
            cat_order_ns = ["实验室检查", "影像学检查", "内镜检查", "病理学检查", "其他检查"]
            pv_ns = pv_ns.reindex([c for c in cat_order_ns if c in pv_ns.index] + [c for c in pv_ns.index if c not in cat_order_ns])
            x_ns = np.arange(len(pv_ns.index))
            w_ns = 0.34
            d1_ns = pv_ns["D1（门诊）"] if "D1（门诊）" in pv_ns.columns else pd.Series([0] * len(pv_ns.index), index=pv_ns.index)
            d2_ns = pv_ns["D2（住院）"] if "D2（住院）" in pv_ns.columns else pd.Series([0] * len(pv_ns.index), index=pv_ns.index)
            ax_ns_f.bar(
                x_ns - w_ns / 2,
                d1_ns.to_numpy(),
                width=w_ns,
                color="#3E74AF",
                edgecolor="#2E5F97",
                linewidth=0.75,
                label="D1（门诊）",
            )
            ax_ns_f.bar(
                x_ns + w_ns / 2,
                d2_ns.to_numpy(),
                width=w_ns,
                color="#9FC4E7",
                edgecolor="#5E8DB8",
                linewidth=0.75,
                label="D2（住院）",
            )
            ax_ns_f.set_xticks(x_ns)
            ax_ns_f.set_xticklabels(pv_ns.index.tolist(), rotation=0)
            ax_ns_f.set_ylabel("检查请求次数（病例×检查类型命中次数）")
            ax_ns_f.legend(loc="upper right", fontsize=8, frameon=False)
            ax_ns_f.grid(alpha=0.24, axis="y", linestyle="--", linewidth=0.8, color=g1_grid_color)
            ax_ns_f.set_facecolor(g1_panel_bg)
        ax_ns_f.set_title("f 门诊与住院检查类型分布", fontsize=11, y=0.97)
        if not plan_stage_pct.empty:
            ylab_g = [PLAN_STAGE_LABEL.get(s, s) for s in PLAN_STAGE_ORDER if s in plan_stage_pct.index]
            idx_g = [s for s in PLAN_STAGE_ORDER if s in plan_stage_pct.index]
            y_g = np.arange(len(idx_g))
            left_g = np.zeros(len(idx_g))
            active_plan_g = [c for c in PLAN_LABEL_ORDER if c in plan_stage_pct.columns and float(plan_stage_pct[c].sum()) > 0.0]
            if "无/未提及" in plan_stage_pct.columns and "无/未提及" not in active_plan_g:
                active_plan_g.append("无/未提及")
            plan_bar_color_map_g = {k: g1_plan_color.get(k, "#7FA7D1") for k in active_plan_g}
            for cat in active_plan_g:
                vals = plan_stage_pct.loc[idx_g, cat].to_numpy() if cat in plan_stage_pct.columns else np.zeros(len(idx_g))
                ax_ns_g.barh(
                    y_g,
                    vals,
                    left=left_g,
                    color=plan_bar_color_map_g.get(cat, "#7FA7D1"),
                    height=0.62,
                    label=cat,
                )
                left_g += vals
            ax_ns_g.set_xlim(0, 100)
            ax_ns_g.set_yticks(y_g)
            ax_ns_g.set_yticklabels(ylab_g)
            ax_ns_g.invert_yaxis()
            ax_ns_g.set_xlabel("病例占比 (%)", fontsize=8)
            ax_ns_g.set_title("g 术前术后及康复随访方案构成", fontsize=11, y=0.97)
            ax_ns_g.grid(alpha=0.24, axis="x", linestyle="--", linewidth=0.8, color=g1_grid_color)
            ax_ns_g.set_facecolor(g1_panel_bg)
            ns_g_handles = _build_circle_legend_handles(active_plan_g, plan_bar_color_map_g, marker_size=7.0)
            ax_ns_g.legend(
                handles=ns_g_handles,
                loc="lower left",
                bbox_to_anchor=(0.0, 1.10, 1.0, 0.25),
                mode="expand",
                fontsize=7.8,
                frameon=False,
                ncol=max(1, len(active_plan_g)),
                handlelength=1.6,
                handletextpad=0.4,
            )
        else:
            _draw_image_panel(ax_ns_g, out_plan_mix_bar, "", aspect="equal")
        for border_ax in [ax_ns_a, ax_ns_b, ax_ns_c, ax_ns_d, ax_ns_e, ax_ns_f]:
            _set_full_border(border_ax)
        if ax_ns_g.axison:
            _set_full_border(ax_ns_g)
        fig_ns.suptitle("G1 数据集概况", fontsize=16, y=1.01)
        _save_fig(out_img_no_sankey)

    # 无Sankey + e替换版（使用 PALM-COEIN 分类长尾折线；直接绘制，避免嵌图缩放失真）
    if not center.empty:
        fig_alt = plt.figure(figsize=(18.6, 12.9))
        gs_alt = fig_alt.add_gridspec(
            3,
            6,
            hspace=0.52,
            wspace=0.52,
            width_ratios=[2.2, 2.2, 1.55, 1.55, 1.55, 1.55],
            height_ratios=[1.08, 1.0, 1.08],
        )
        ax_alt_a = fig_alt.add_subplot(gs_alt[0, 0:2])
        ax_alt_b = fig_alt.add_subplot(gs_alt[0, 2:6])
        ax_alt_c = fig_alt.add_subplot(gs_alt[1, 0:2])
        ax_alt_d = fig_alt.add_subplot(gs_alt[1, 2:4])
        ax_alt_e = fig_alt.add_subplot(gs_alt[1, 4:6])
        ax_alt_f = fig_alt.add_subplot(gs_alt[2, 0:3])
        ax_alt_g = fig_alt.add_subplot(gs_alt[2, 3:6])

        alt_labels = [c_name_map.get(str(x), str(x)) for x in center["Center"]]
        alt_values = center["Cases"].astype(float).to_numpy()
        alt_total = int(alt_values.sum())
        ax_alt_a.pie(
            alt_values,
            labels=alt_labels,
            autopct=lambda p: f"{p:.1f}%",
            pctdistance=0.84,
            startangle=140,
            radius=1.0,
            wedgeprops={"width": 0.30, "edgecolor": "white"},
            colors=g1_center_colors[: len(alt_values)],
            textprops={"fontsize": 10},
        )
        alt_outer_leg = ax_alt_a.legend(
            alt_labels,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.03),
            fontsize=8,
            frameon=False,
            ncol=min(3, len(alt_labels)),
        )
        ax_alt_a.add_artist(alt_outer_leg)
        bm_alt = bm_summary.copy()
        if (bm_alt.empty) and (not llm_taxonomy.empty):
            tmp_alt = llm_taxonomy.copy()
            tmp_alt["benign_malignant"] = tmp_alt["d3_palm_label"].astype(str).map(
                lambda x: "恶性" if x == "M-恶性/增生" else ("非肿瘤" if x == "N-非肿瘤" else "良性")
            )
            bm_alt = tmp_alt.groupby("benign_malignant", as_index=False).agg(cases=("case_id", "nunique"))
        if not bm_alt.empty and {"benign_malignant", "cases"}.issubset(bm_alt.columns):
            bm_alt["benign_malignant"] = pd.Categorical(
                bm_alt["benign_malignant"], categories=["良性", "恶性", "非肿瘤"], ordered=True
            )
            bm_alt = bm_alt.sort_values("benign_malignant", kind="mergesort")
            bm_alt = bm_alt[bm_alt["cases"] > 0]
            if not bm_alt.empty:
                ax_alt_a.pie(
                    bm_alt["cases"].to_numpy(),
                    labels=None,
                    radius=0.67,
                    startangle=140,
                    autopct=lambda p: f"{p:.1f}%",
                    pctdistance=0.68,
                    wedgeprops={"width": 0.29, "edgecolor": "white"},
                    colors=[g1_bm_colors.get(str(x), "#A6BBD1") for x in bm_alt["benign_malignant"]],
                    textprops={"fontsize": 9, "color": "#1F1F1F"},
                )
                ax_alt_a.legend(
                    [str(row["benign_malignant"]) for _, row in bm_alt.iterrows()],
                    loc="lower center",
                    bbox_to_anchor=(0.5, -0.16),
                    fontsize=8,
                    frameon=False,
                    ncol=min(3, len(bm_alt)),
                )
        ax_alt_a.text(0, 0, f"N={alt_total}", ha="center", va="center", fontsize=12, fontweight="bold")
        ax_alt_a.set_title("a 样本中心与良恶性分布")

        if not palm_stage_pct.empty:
            ylab_alt_b = ["初步诊断", "修正诊断", "最终诊断"]
            y_alt_b = np.arange(len(ylab_alt_b))
            left_alt_b = np.zeros(len(ylab_alt_b))
            active_palm_alt = [c for c in PALM_COEIN_ORDER if c in palm_stage_pct.columns and float(palm_stage_pct[c].sum()) > 0.0]
            if "不适用" in palm_stage_pct.columns and "不适用" not in active_palm_alt:
                active_palm_alt.append("不适用")
            for cat in active_palm_alt:
                vals = palm_stage_pct.loc[["D1", "D2", "D3"], cat].to_numpy() if cat in palm_stage_pct.columns else np.zeros(3)
                ax_alt_b.barh(
                    y_alt_b,
                    vals,
                    left=left_alt_b,
                    color=g1_palm_color.get(cat, "#7FA7D1"),
                    height=0.62,
                    label=cat,
                )
                left_alt_b += vals
            ax_alt_b.set_xlim(0, 100)
            ax_alt_b.set_yticks(y_alt_b)
            ax_alt_b.set_yticklabels(ylab_alt_b)
            ax_alt_b.invert_yaxis()
            ax_alt_b.set_xlabel("病例占比 (%)", fontsize=8)
            ax_alt_b.set_title("b PALM-COEIN分型随诊断阶段变化", fontsize=11, y=0.97)
            ax_alt_b.grid(alpha=0.24, axis="x", linestyle="--", linewidth=0.8, color=g1_grid_color)
            ax_alt_b.set_facecolor(g1_panel_bg)
            alt_b_handles = _build_circle_legend_handles(active_palm_alt, g1_palm_color, marker_size=7.0)
            ax_alt_b.legend(
                handles=alt_b_handles,
                loc="lower left",
                bbox_to_anchor=(0.0, 1.10, 1.0, 0.25),
                mode="expand",
                fontsize=7.8,
                frameon=False,
                ncol=max(1, len(active_palm_alt)),
                handlelength=1.6,
                handletextpad=0.4,
            )

        if not text_len.empty and "TextLen" in text_len.columns:
            vals_alt_c = pd.to_numeric(text_len["TextLen"], errors="coerce").dropna()
            ax_alt_c.hist(vals_alt_c, bins=24, color="#AFC7E3", edgecolor="#4E7EAF", alpha=0.88, linewidth=0.9)
            if len(vals_alt_c) > 0:
                med_alt_c = float(np.median(vals_alt_c))
                ax_alt_c.axvline(med_alt_c, color="#2E5F97", linestyle="--", linewidth=1.3, label=f"Median={med_alt_c:.0f}")
                ax_alt_c.legend(loc="upper right", fontsize=8, frameon=False)
            ax_alt_c.set_xlabel("临床文本长度（非空格字符，含标点）", fontsize=8)
            ax_alt_c.set_ylabel("频数")
            ax_alt_c.grid(alpha=0.24, axis="y", linestyle="--", linewidth=0.8, color=g1_grid_color)
            ax_alt_c.set_facecolor(g1_panel_bg)
        ax_alt_c.set_title("c 病例文本长度分布", fontsize=11, y=0.97)

        if not icd.empty:
            icd_alt = icd.copy()
            if "ICD10Code" not in icd_alt.columns:
                icd_alt["ICD10Code"] = icd_alt.get("ICD10Chapter", "UNK").astype(str)
            icd_alt["ICD10Code"] = icd_alt["ICD10Code"].astype(str).str.strip().str.upper()
            icd_alt["Cases"] = pd.to_numeric(icd_alt.get("Cases", 0), errors="coerce").fillna(0.0)
            icd_alt = icd_alt.groupby("ICD10Code", as_index=False)["Cases"].sum().sort_values("Cases", ascending=True).tail(10)
            icd_vals_alt = icd_alt["Cases"].to_numpy(dtype=float)
            if len(icd_vals_alt) > 0:
                vmin_alt = float(np.min(icd_vals_alt))
                vmax_alt = float(np.max(icd_vals_alt))
                denom_alt = max(vmax_alt - vmin_alt, 1e-9)
                shades_alt = [0.45 + 0.45 * ((float(v) - vmin_alt) / denom_alt) for v in icd_vals_alt]
                icd_colors_alt = [to_hex(plt.get_cmap("Blues")(s)) for s in shades_alt]
            else:
                icd_colors_alt = "#4F8CC9"
            ax_alt_d.barh(
                icd_alt["ICD10Code"],
                icd_alt["Cases"],
                color=icd_colors_alt,
                edgecolor="#3E6F9E",
                linewidth=0.8,
                alpha=0.95,
            )
            ax_alt_d.tick_params(axis="y", labelsize=7)
            ax_alt_d.set_xlabel("病例数", fontsize=8)
            ax_alt_d.grid(alpha=0.24, axis="x", linestyle="--", linewidth=0.8, color=g1_grid_color)
            ax_alt_d.set_facecolor(g1_panel_bg)
        ax_alt_d.set_title("d ICD-10编码分布", fontsize=11, y=0.97)

        if not palm_overall.empty and {"palm_coein", "cases"}.issubset(palm_overall.columns):
            palm_alt_e = palm_overall.copy()
            palm_alt_e["cases"] = pd.to_numeric(palm_alt_e["cases"], errors="coerce").fillna(0.0)
            palm_alt_e = palm_alt_e.sort_values("cases", ascending=False, kind="mergesort").reset_index(drop=True)
            palm_alt_e["rank"] = np.arange(1, len(palm_alt_e) + 1)
            ax_alt_e.plot(
                palm_alt_e["rank"],
                palm_alt_e["cases"],
                color="#2E5F97",
                linewidth=1.8,
                marker="o",
                markersize=3.8,
            )
            ax_alt_e.fill_between(palm_alt_e["rank"], palm_alt_e["cases"], color="#9EC1E3", alpha=0.22)
            ax_alt_e.set_xticks(palm_alt_e["rank"])
            ax_alt_e.set_xticklabels(palm_alt_e["palm_coein"], rotation=20)
            ax_alt_e.set_xlabel("PALM-COEIN 分类排名（按病例数降序）", fontsize=8)
            ax_alt_e.set_ylabel("病例数")
            rare_ratio_alt = float((palm_alt_e["cases"] <= 10).mean()) if len(palm_alt_e) else 0.0
            ax_alt_e.annotate(
                f"{rare_ratio_alt * 100:.1f}% 低频分类(<=10例)",
                xy=(max(1, int(len(palm_alt_e) * 0.25)), max(1.0, float(palm_alt_e["cases"].min()))),
                xytext=(max(2, int(len(palm_alt_e) * 0.55)), max(2.0, float(palm_alt_e["cases"].max()) * 0.6)),
                arrowprops={"arrowstyle": "->", "lw": 1.2},
                fontsize=8.5,
            )
            ax_alt_e.grid(alpha=0.24, axis="y", linestyle="--", linewidth=0.8, color=g1_grid_color)
            ax_alt_e.set_facecolor(g1_panel_bg)
        elif out_e_palm_line.exists():
            _draw_image_panel(ax_alt_e, out_e_palm_line, "", aspect="auto")
        ax_alt_e.set_title("e PALM-COEIN分类长尾分布", fontsize=11, y=0.97)

        if not check_type.empty:
            check_alt = check_type.copy()
            check_alt["StageCN"] = check_alt["Stage"].map({"Outpatient": "D1（门诊）", "Admission": "D2（住院）"}).fillna(
                check_alt["Stage"].astype(str)
            )
            pv_alt_f = (
                check_alt.groupby(["Category", "StageCN"], as_index=False)["Cases"]
                .sum()
                .pivot(index="Category", columns="StageCN", values="Cases")
                .fillna(0)
            )
            cat_order_alt = ["实验室检查", "影像学检查", "内镜检查", "病理学检查", "其他检查"]
            pv_alt_f = pv_alt_f.reindex([c for c in cat_order_alt if c in pv_alt_f.index] + [c for c in pv_alt_f.index if c not in cat_order_alt])
            x_alt_f = np.arange(len(pv_alt_f.index))
            w_alt_f = 0.34
            d1_alt_f = (
                pv_alt_f["D1（门诊）"]
                if "D1（门诊）" in pv_alt_f.columns
                else pd.Series([0] * len(pv_alt_f.index), index=pv_alt_f.index)
            )
            d2_alt_f = (
                pv_alt_f["D2（住院）"]
                if "D2（住院）" in pv_alt_f.columns
                else pd.Series([0] * len(pv_alt_f.index), index=pv_alt_f.index)
            )
            ax_alt_f.bar(
                x_alt_f - w_alt_f / 2,
                d1_alt_f.to_numpy(),
                width=w_alt_f,
                color="#3E74AF",
                edgecolor="#2E5F97",
                linewidth=0.75,
                label="D1（门诊）",
            )
            ax_alt_f.bar(
                x_alt_f + w_alt_f / 2,
                d2_alt_f.to_numpy(),
                width=w_alt_f,
                color="#9FC4E7",
                edgecolor="#5E8DB8",
                linewidth=0.75,
                label="D2（住院）",
            )
            ax_alt_f.set_xticks(x_alt_f)
            ax_alt_f.set_xticklabels(pv_alt_f.index.tolist(), rotation=0)
            ax_alt_f.set_ylabel("检查请求次数（病例×检查类型命中次数）")
            ax_alt_f.legend(loc="upper right", fontsize=8, frameon=False)
            ax_alt_f.grid(alpha=0.24, axis="y", linestyle="--", linewidth=0.8, color=g1_grid_color)
            ax_alt_f.set_facecolor(g1_panel_bg)
        ax_alt_f.set_title("f 门诊与住院检查类型分布", fontsize=11, y=0.97)

        if not plan_stage_pct.empty:
            ylab_alt_g = [PLAN_STAGE_LABEL.get(s, s) for s in PLAN_STAGE_ORDER if s in plan_stage_pct.index]
            idx_alt_g = [s for s in PLAN_STAGE_ORDER if s in plan_stage_pct.index]
            y_alt_g = np.arange(len(idx_alt_g))
            left_alt_g = np.zeros(len(idx_alt_g))
            active_plan_alt = [c for c in PLAN_LABEL_ORDER if c in plan_stage_pct.columns and float(plan_stage_pct[c].sum()) > 0.0]
            if "无/未提及" in plan_stage_pct.columns and "无/未提及" not in active_plan_alt:
                active_plan_alt.append("无/未提及")
            for cat in active_plan_alt:
                vals = plan_stage_pct.loc[idx_alt_g, cat].to_numpy() if cat in plan_stage_pct.columns else np.zeros(len(idx_alt_g))
                ax_alt_g.barh(
                    y_alt_g,
                    vals,
                    left=left_alt_g,
                    color=g1_plan_color.get(cat, "#7FA7D1"),
                    height=0.62,
                    label=cat,
                )
                left_alt_g += vals
            ax_alt_g.set_xlim(0, 100)
            ax_alt_g.set_yticks(y_alt_g)
            ax_alt_g.set_yticklabels(ylab_alt_g)
            ax_alt_g.invert_yaxis()
            ax_alt_g.set_xlabel("病例占比 (%)", fontsize=8)
            ax_alt_g.set_title("g 术前术后及康复随访方案构成", fontsize=11, y=0.97)
            ax_alt_g.grid(alpha=0.24, axis="x", linestyle="--", linewidth=0.8, color=g1_grid_color)
            ax_alt_g.set_facecolor(g1_panel_bg)
            alt_g_handles = _build_circle_legend_handles(active_plan_alt, g1_plan_color, marker_size=7.0)
            ax_alt_g.legend(
                handles=alt_g_handles,
                loc="lower left",
                bbox_to_anchor=(0.0, 1.10, 1.0, 0.25),
                mode="expand",
                fontsize=7.8,
                frameon=False,
                ncol=max(1, len(active_plan_alt)),
                handlelength=1.6,
                handletextpad=0.4,
            )

        for border_ax in [ax_alt_a, ax_alt_b, ax_alt_c, ax_alt_d, ax_alt_e, ax_alt_f]:
            _set_full_border(border_ax)
        if ax_alt_g.axison:
            _set_full_border(ax_alt_g)
        fig_alt.suptitle("G1 数据集概况", fontsize=16, y=1.01)
        _save_fig(out_img_no_sankey_e_alt)

        # no_sankey_e_alt 两排替换版（同一组子图，2行布局）
        fig_alt2 = plt.figure(figsize=(18.6, 9.8))
        gs_alt2 = fig_alt2.add_gridspec(
            2,
            12,
            hspace=0.18,
            wspace=0.22,
            width_ratios=[1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1, 1.0, 1.0, 1.0, 1.0],
            height_ratios=[1.0, 1.0],
        )
        ax2_a = fig_alt2.add_subplot(gs_alt2[0, 0:3])
        ax2_b = fig_alt2.add_subplot(gs_alt2[0, 3:9])
        ax2_c = fig_alt2.add_subplot(gs_alt2[0, 9:12])
        ax2_d = fig_alt2.add_subplot(gs_alt2[1, 0:3])
        ax2_e = fig_alt2.add_subplot(gs_alt2[1, 3:6])
        ax2_f = fig_alt2.add_subplot(gs_alt2[1, 6:9])
        ax2_g = fig_alt2.add_subplot(gs_alt2[1, 9:12])

        panel_paths = {
            "a": OUT_FIG_DIR / group / "G1a_center_distribution_v2.png",
            "b": out_palm_stage_bar,
            "c": OUT_FIG_DIR / group / "G1c_text_density_v2.png",
            "d": OUT_FIG_DIR / group / "G1d_icd_chapter_v2.png",
            "e": out_e_palm_line,
            "f": OUT_FIG_DIR / group / "G1f_check_profile_v2.png",
            "g": out_plan_mix_bar,
        }

        # 两排替换版保持子图原始宽高比，避免面板拉伸变形
        _draw_image_panel(ax2_a, panel_paths["a"], "", aspect="equal")
        _draw_image_panel(ax2_b, panel_paths["b"], "", aspect="equal")
        _draw_image_panel(ax2_c, panel_paths["c"], "", aspect="equal")
        _draw_image_panel(ax2_d, panel_paths["d"], "", aspect="equal")
        _draw_image_panel(ax2_e, panel_paths["e"], "", aspect="equal")
        _draw_image_panel(ax2_f, panel_paths["f"], "", aspect="equal")
        _draw_image_panel(ax2_g, panel_paths["g"], "", aspect="equal")

        fig_alt2.suptitle("G1 数据集概况", fontsize=16, y=0.995)
        _save_fig(out_img_no_sankey_e_alt_2row)

    # 额外图：按阶段详细类别分布（避免“其他/未分类”主导）
    if not diag_stage.empty and {"Stage", "DiagnosisCategory", "Cases"}.issubset(diag_stage.columns):
        stage_key = {"Admission": "D1 admission diagnosis", "Revised": "D2 revised diagnosis", "Final": "D3 final diagnosis"}
        norm = diag_stage.copy()
        norm["DiagnosisCategory"] = (
            norm["DiagnosisCategory"]
            .astype(str)
            .str.replace("其他/未分类", "其他", regex=False)
            .str.replace("其他未分类", "其他", regex=False)
        )
        fig_sd, axes_sd = plt.subplots(1, 3, figsize=(16.5, 6.8), sharex=False)
        for ax_sd, st in zip(axes_sd, ["Admission", "Revised", "Final"]):
            sub = norm[norm["Stage"] == st].copy()
            if sub.empty:
                ax_sd.axis("off")
                continue
            sub = (
                sub.groupby("DiagnosisCategory", as_index=False)["Cases"].sum().sort_values("Cases", ascending=False).head(10)
            )
            ax_sd.barh(sub["DiagnosisCategory"].tolist()[::-1], sub["Cases"].to_numpy()[::-1], color="#5C96CC")
            ax_sd.set_title(stage_key.get(st, st))
            ax_sd.set_xlabel("Cases")
            ax_sd.grid(alpha=0.2, axis="x")
        fig_sd.suptitle("Diagnosis Category Distribution by Stage", fontsize=17, y=1.01)
        _save_fig(out_stage_detail)

    palm_longtail = pd.DataFrame()
    # 额外图：PALM-COEIN 九分类整体分布 + E图替换版（长尾）
    if not palm_overall.empty:
        palm_show = palm_overall.copy()
        palm_show["palm_coein"] = pd.Categorical(palm_show["palm_coein"], categories=PALM_COEIN_ORDER, ordered=True)
        palm_show = palm_show.sort_values("palm_coein", kind="mergesort")
        fig_pd, ax_pd = plt.subplots(figsize=(12.6, 5.9))
        ax_pd.bar(
            palm_show["palm_coein"],
            palm_show["cases"],
            color=[g1_palm_color.get(c, "#7FA7D1") for c in palm_show["palm_coein"]],
            alpha=0.9,
        )
        ax_pd.set_ylabel("病例数")
        ax_pd.set_title("G1h PALM-COEIN 九分类样本分布")
        ax_pd.tick_params(axis="x", rotation=20)
        ax_pd.grid(alpha=0.2, axis="y")
        _save_fig(out_palm_dist)

        # E图替换版：按病例数降序，展示分类长尾（柱状 + 折线）
        palm_longtail = palm_overall.copy()
        palm_longtail["cases"] = pd.to_numeric(palm_longtail["cases"], errors="coerce").fillna(0.0)
        palm_longtail = palm_longtail.sort_values("cases", ascending=False, kind="mergesort").reset_index(drop=True)
        palm_longtail["rank"] = np.arange(1, len(palm_longtail) + 1)
        longtail_labels = palm_longtail["palm_coein"].astype(str).tolist()
        longtail_colors = _build_blue_shades(longtail_labels, fixed_last={"不适用": "#7F8691"})

        fig_elb, ax_elb = plt.subplots(figsize=(12.6, 5.8))
        ax_elb.bar(
            palm_longtail["palm_coein"],
            palm_longtail["cases"],
            color=[longtail_colors.get(str(x), "#5C96CC") for x in palm_longtail["palm_coein"]],
            alpha=0.95,
        )
        ax_elb.set_xlabel("PALM-COEIN 分类（按病例数降序）")
        ax_elb.set_ylabel("病例数")
        ax_elb.set_title("G1e替换版：PALM-COEIN 分类长尾 柱状")
        ax_elb.tick_params(axis="x", rotation=20)
        ax_elb.grid(alpha=0.2, axis="y")
        _set_full_border(ax_elb)
        _save_fig(out_e_palm_bar)

        fig_ell, ax_ell = plt.subplots(figsize=(12.6, 5.8))
        ax_ell.plot(
            palm_longtail["rank"],
            palm_longtail["cases"],
            color="#2E5F97",
            linewidth=1.8,
            marker="o",
            markersize=4.5,
        )
        ax_ell.set_xticks(palm_longtail["rank"])
        ax_ell.set_xticklabels(palm_longtail["palm_coein"], rotation=20)
        ax_ell.set_xlabel("PALM-COEIN 分类排名（按病例数降序）")
        ax_ell.set_ylabel("病例数")
        ax_ell.set_title("G1e替换版：PALM-COEIN 分类长尾 折线")
        rare_ratio = float((palm_longtail["cases"] <= 10).mean()) if len(palm_longtail) else 0.0
        ax_ell.annotate(
            f"{rare_ratio * 100:.1f}% 低频分类(<=10例)",
            xy=(max(1, int(len(palm_longtail) * 0.25)), max(1.0, float(palm_longtail["cases"].min()))),
            xytext=(max(2, int(len(palm_longtail) * 0.55)), max(2.0, float(palm_longtail["cases"].max()) * 0.6)),
            arrowprops={"arrowstyle": "->", "lw": 1.2},
            fontsize=9,
        )
        ax_ell.grid(alpha=0.22, axis="y")
        _set_full_border(ax_ell)
        _save_fig(out_e_palm_line)

    # 额外图 out_palm_stage 已由 Sankey 输出；若未生成且有阶段数据，则兜底输出堆叠图
    if (not out_palm_stage.exists()) and (not palm_stage.empty):
        fig_ps, ax_ps = plt.subplots(figsize=(12.4, 5.6))
        pv_ps = (
            palm_stage.groupby(["stage4", "palm_coein"], as_index=False)["cases"]
            .sum()
            .pivot(index="stage4", columns="palm_coein", values="cases")
            .fillna(0.0)
            .reindex(["D1", "D2", "D3"])
        )
        for cat in PALM_COEIN_ORDER:
            if cat not in pv_ps.columns:
                pv_ps[cat] = 0.0
        pv_ps = pv_ps[PALM_COEIN_ORDER]
        pct_ps = pv_ps.div(pv_ps.sum(axis=1), axis=0).fillna(0.0) * 100.0
        bottom = np.zeros(len(pct_ps))
        x_lbl = ["D1 (初诊)", "D2 (修订)", "D3 (终诊)"]
        for cat in PALM_COEIN_ORDER:
            vals = pct_ps[cat].to_numpy()
            ax_ps.bar(
                x_lbl,
                vals,
                bottom=bottom,
                color=g1_palm_color.get(cat, "#7FA7D1"),
                label=cat,
                width=0.62,
            )
            bottom += vals
        ax_ps.set_ylim(0, 100)
        ax_ps.set_ylabel("病例占比 (%)")
        ax_ps.set_title("G1b PALM-COEIN 九分类随阶段变化")
        ax_ps.legend(loc="upper right", fontsize=8, ncol=2, frameon=False)
        _save_fig(out_palm_stage)

    summary_center = center.copy()
    if not summary_center.empty and "Cases" in summary_center.columns:
        total_cases = float(summary_center["Cases"].sum()) if summary_center["Cases"].sum() else 0.0
        summary_center["sample_size"] = int(total_cases) if total_cases > 0 else 0
        if "Percent" not in summary_center.columns and total_cases > 0:
            summary_center["Percent"] = summary_center["Cases"] / total_cases
        rr = np.arange(2, len(summary_center) + 2)
        summary_center["formula_cases"] = [f"=SUMIFS(detail_center!$C:$C,detail_center!$B:$B,B{r})" for r in rr]
        summary_center["formula_percent"] = [f"=IFERROR(C{r}/SUM($C:$C),\"\")" for r in rr]
        summary_center["formula_sample_size"] = [f"=SUM($C:$C)" for _ in rr]

    summary_diag_stage = pd.DataFrame()
    if not diag_stage.empty and {"Stage", "DiagnosisCategory", "Cases"}.issubset(diag_stage.columns):
        summary_diag_stage = (
            diag_stage.groupby(["Stage", "DiagnosisCategory"], as_index=False)["Cases"].sum().sort_values(
                ["Stage", "Cases"], ascending=[True, False], kind="mergesort"
            )
        )
        rr = np.arange(2, len(summary_diag_stage) + 2)
        summary_diag_stage["formula_cases"] = [
            f"=SUMIFS(detail_diag_stage!$D:$D,detail_diag_stage!$B:$B,B{r},detail_diag_stage!$C:$C,C{r})"
            for r in rr
        ]
    summary_palm_stage = pd.DataFrame()
    summary_palm_overall = pd.DataFrame()
    if not palm_stage.empty:
        summary_palm_stage = palm_stage.copy()
        rr = np.arange(2, len(summary_palm_stage) + 2)
        summary_palm_stage["formula_cases"] = [
            f"=COUNTIFS(detail_diag_stage_palm!$D:$D,B{r},detail_diag_stage_palm!$F:$F,C{r})" for r in rr
        ]
    if not palm_overall.empty:
        summary_palm_overall = palm_overall.copy()
        rr = np.arange(2, len(summary_palm_overall) + 2)
        summary_palm_overall["formula_cases"] = [
            f"=COUNTIFS(detail_diag_stage_palm!$F:$F,B{r})" for r in rr
        ]
    summary_bm = bm_summary.copy() if not bm_summary.empty else pd.DataFrame()
    if not summary_bm.empty and {"benign_malignant", "cases"}.issubset(summary_bm.columns):
        rr = np.arange(2, len(summary_bm) + 2)
        summary_bm["formula_cases"] = [f"=COUNTIFS(detail_center_bm_case!$I:$I,B{r})" for r in rr]

    summary_text = pd.DataFrame()
    if not text_len.empty and "TextLen" in text_len.columns:
        vals = pd.to_numeric(text_len["TextLen"], errors="coerce").dropna()
        if len(vals) > 0:
            summary_text = pd.DataFrame(
                [
                    {"metric": "unit", "value": "non-space chars including punctuation"},
                    {"metric": "count", "value": int(vals.count())},
                    {"metric": "mean", "value": float(vals.mean())},
                    {"metric": "median", "value": float(vals.median())},
                    {"metric": "p25", "value": float(vals.quantile(0.25))},
                    {"metric": "p75", "value": float(vals.quantile(0.75))},
                    {"metric": "p95", "value": float(vals.quantile(0.95))},
                ]
            )
            rr = np.arange(2, len(summary_text) + 2)
            summary_text["formula_value"] = [
                (
                    f"=IF(B{r}=\"count\",COUNT(detail_text_len!$F:$F),"
                    f"IF(B{r}=\"mean\",AVERAGE(detail_text_len!$F:$F),"
                    f"IF(B{r}=\"median\",MEDIAN(detail_text_len!$F:$F),"
                    f"IF(B{r}=\"p25\",PERCENTILE.INC(detail_text_len!$F:$F,0.25),"
                    f"IF(B{r}=\"p75\",PERCENTILE.INC(detail_text_len!$F:$F,0.75),"
                    f"IF(B{r}=\"p95\",PERCENTILE.INC(detail_text_len!$F:$F,0.95),\"non-space chars including punctuation\"))))))"
                )
                for r in rr
            ]

    summary_icd = pd.DataFrame()
    if not icd.empty and "Cases" in icd.columns:
        summary_icd = icd.copy()
        summary_icd["sample_size"] = int(pd.to_numeric(icd["Cases"], errors="coerce").sum())
        rr = np.arange(2, len(summary_icd) + 2)
        summary_icd["formula_cases"] = [
            f"=SUMIFS(detail_icd!$D:$D,detail_icd!$B:$B,B{r})" for r in rr
        ]
        summary_icd["formula_sample_size"] = [f"=SUM($D:$D)" for _ in rr]

    summary_longtail = pd.DataFrame()
    if not longtail.empty and "Cases" in longtail.columns:
        tail = longtail.copy()
        tail["Cases"] = pd.to_numeric(tail["Cases"], errors="coerce")
        summary_longtail = pd.DataFrame(
            [
                {"metric": "unique_diagnosis", "value": int(tail["Diagnosis"].nunique()) if "Diagnosis" in tail.columns else 0},
                {"metric": "rare_case_ratio(<=2)", "value": float((tail["Cases"] <= 2).mean())},
                {"metric": "common_case_ratio(>=5)", "value": float((tail["Cases"] >= 5).mean())},
            ]
        )
        rr = np.arange(2, len(summary_longtail) + 2)
        summary_longtail["formula_value"] = [
            (
                f"=IF(B{r}=\"unique_diagnosis\",COUNTA(detail_longtail!$B:$B),"
                f"IF(B{r}=\"rare_case_ratio(<=2)\",COUNTIF(detail_longtail!$C:$C,\"<=2\")/COUNT(detail_longtail!$C:$C),"
                f"IF(B{r}=\"common_case_ratio(>=5)\",COUNTIF(detail_longtail!$C:$C,\">=5\")/COUNT(detail_longtail!$C:$C),\"\")))"
            )
            for r in rr
        ]
    summary_longtail_palm = pd.DataFrame()
    if not palm_longtail.empty and {"palm_coein", "cases", "rank"}.issubset(palm_longtail.columns):
        total_palm_cases = float(palm_longtail["cases"].sum())
        summary_longtail_palm = pd.DataFrame(
            [
                {"metric": "unique_palm_classes", "value": int(palm_longtail["palm_coein"].nunique())},
                {"metric": "rare_class_ratio(<=10)", "value": float((palm_longtail["cases"] <= 10).mean())},
                {
                    "metric": "top1_case_share",
                    "value": float(palm_longtail["cases"].iloc[0] / total_palm_cases) if total_palm_cases > 0 else 0.0,
                },
            ]
        )
        rr = np.arange(2, len(summary_longtail_palm) + 2)
        summary_longtail_palm["formula_value"] = [
            (
                f"=IF(B{r}=\"unique_palm_classes\",COUNTA(detail_longtail_palm!$B:$B),"
                f"IF(B{r}=\"rare_class_ratio(<=10)\",COUNTIF(detail_longtail_palm!$C:$C,\"<=10\")/COUNT(detail_longtail_palm!$C:$C),"
                f"IF(B{r}=\"top1_case_share\",MAX(detail_longtail_palm!$C:$C)/SUM(detail_longtail_palm!$C:$C),\"\")))"
            )
            for r in rr
        ]

    summary_check = pd.DataFrame()
    if not check_type.empty and {"Stage", "Category", "Cases"}.issubset(check_type.columns):
        summary_check = (
            check_type.groupby(["Stage", "Category"], as_index=False)["Cases"].sum().sort_values(
                ["Stage", "Cases"], ascending=[True, False], kind="mergesort"
            )
        )
        rr = np.arange(2, len(summary_check) + 2)
        summary_check["formula_cases"] = [
            f"=SUMIFS(detail_check_type!$D:$D,detail_check_type!$B:$B,B{r},detail_check_type!$C:$C,C{r})"
            for r in rr
        ]

    summary_plan = pd.DataFrame()
    if not plan_summary.empty and {"plan_stage", "plan_label", "cases"}.issubset(plan_summary.columns):
        summary_plan = plan_summary.rename(columns={"plan_stage": "Stage", "plan_label": "Category", "cases": "Cases"}).copy()
        summary_plan["Category"] = pd.Categorical(summary_plan["Category"], categories=PLAN_LABEL_ORDER, ordered=True)
        summary_plan = summary_plan.sort_values(["Stage", "Category"], ascending=[True, True], kind="mergesort")
        rr = np.arange(2, len(summary_plan) + 2)
        summary_plan["formula_cases"] = [
            f"=SUMIFS(detail_plan_type!$D:$D,detail_plan_type!$B:$B,B{r},detail_plan_type!$C:$C,C{r})"
            for r in rr
        ]
    elif not plan_type.empty and {"Category", "Cases"}.issubset(plan_type.columns):
        summary_plan = (
            plan_type.groupby("Category", as_index=False)["Cases"].sum().sort_values("Cases", ascending=False)
        )

    llm_detail = pd.DataFrame()
    llm_error_detail = pd.DataFrame()
    llm_quality_summary = pd.DataFrame()
    icd_case_detail = pd.DataFrame()
    center_bm_case_detail = pd.DataFrame()
    if not llm_taxonomy.empty:
        keep_cols = [
            "center",
            "case_id",
            "d1_palm_label",
            "d2_palm_label",
            "d3_palm_label",
            "final_icd10_code",
            "final_benign_malignant_raw",
            "final_benign_malignant",
            "surgery_plan_label",
            "postop_plan_label",
            "rehab_plan_label",
            "followup_plan_label",
            "fallback_used",
            "channel",
            "model",
            "prompt_version",
            "source_gt_path",
            "source_gt_sheet",
        ]
        llm_detail = llm_taxonomy[[c for c in keep_cols if c in llm_taxonomy.columns]].copy()
        if not llm_detail.empty:
            llm_detail["fallback_used"] = pd.to_numeric(llm_detail.get("fallback_used", 0), errors="coerce").fillna(0).astype(int)
            err_series = (
                llm_taxonomy.get("error", pd.Series([""] * len(llm_taxonomy), index=llm_taxonomy.index))
                .fillna("")
                .astype(str)
                .str.strip()
            )
            llm_detail["error_tag"] = np.select(
                [
                    err_series.str.contains("429|Too Many Requests", case=False, regex=True),
                    err_series.str.contains("SSLError|SSL|EOF|Connection", case=False, regex=True),
                    err_series != "",
                ],
                [
                    "HTTP_429",
                    "NETWORK_SSL",
                    "OTHER_ERROR",
                ],
                default="NONE",
            )
            llm_detail["llm_status"] = np.where(
                (llm_detail["fallback_used"] == 1) | (llm_detail["error_tag"] != "NONE"),
                "fallback_or_error",
                "llm_success",
            )
            bm_from_d3 = llm_detail["d3_palm_label"].astype(str).map(
                lambda x: "恶性" if x == "M-恶性/增生" else ("非肿瘤" if x == "N-非肿瘤" else "良性")
            )
            center_bm_case_detail = llm_detail.copy()
            center_bm_case_detail["benign_malignant_from_d3"] = bm_from_d3
            center_bm_case_detail["bm_conflict_flag"] = np.where(
                center_bm_case_detail["benign_malignant_from_d3"]
                != center_bm_case_detail["final_benign_malignant"].astype(str),
                1,
                0,
            )

            llm_error_detail = llm_taxonomy.copy()
            llm_error_detail["error"] = (
                llm_error_detail.get("error", pd.Series([""] * len(llm_error_detail), index=llm_error_detail.index))
                .fillna("")
                .astype(str)
                .str.strip()
            )
            llm_error_detail = llm_error_detail[llm_error_detail["error"] != ""].copy()
            if not llm_error_detail.empty:
                llm_error_detail["error_tag"] = np.select(
                    [
                        llm_error_detail["error"].str.contains("429|Too Many Requests", case=False, regex=True),
                        llm_error_detail["error"].str.contains("SSLError|SSL|EOF|Connection", case=False, regex=True),
                    ],
                    ["HTTP_429", "NETWORK_SSL"],
                    default="OTHER_ERROR",
                )
                err_cols = [
                    "center",
                    "case_id",
                    "fallback_used",
                    "error_tag",
                    "error",
                    "channel",
                    "model",
                    "source_gt_path",
                    "source_gt_sheet",
                ]
                llm_error_detail = llm_error_detail[[c for c in err_cols if c in llm_error_detail.columns]]

            total_n = int(llm_detail["case_id"].astype(str).nunique()) if "case_id" in llm_detail.columns else int(len(llm_detail))
            fallback_n = int(llm_detail["fallback_used"].sum())
            err_n = int((err_series != "").sum())
            err_429_n = int(err_series.str.contains("429|Too Many Requests", case=False, regex=True).sum())
            success_n = int(((llm_detail["fallback_used"] == 0) & (llm_detail["error_tag"] == "NONE")).sum())
            llm_quality_summary = pd.DataFrame(
                [
                    {"metric": "total_cases", "value": total_n},
                    {"metric": "fallback_cases", "value": fallback_n},
                    {"metric": "error_cases", "value": err_n},
                    {"metric": "error_429_cases", "value": err_429_n},
                    {"metric": "llm_success_cases", "value": success_n},
                ]
            )
            rr = np.arange(2, len(llm_quality_summary) + 2)
            llm_quality_summary["formula_value"] = [
                (
                    f"=IF(B{r}=\"total_cases\",COUNTA(detail_llm_taxonomy_case!$C:$C),"
                    f"IF(B{r}=\"fallback_cases\",COUNTIF(detail_llm_taxonomy_case!$N:$N,1),"
                    f"IF(B{r}=\"error_cases\",COUNTIFS(detail_llm_taxonomy_case!$T:$T,\"<>NONE\"),"
                    f"IF(B{r}=\"error_429_cases\",COUNTIF(detail_llm_taxonomy_case!$T:$T,\"HTTP_429\"),"
                    f"IF(B{r}=\"llm_success_cases\",COUNTIF(detail_llm_taxonomy_case!$U:$U,\"llm_success\"),\"\")))))"
                )
                for r in rr
            ]
        if {"center", "case_id", "final_icd10_code", "final_icd10_name", "source_gt_path"}.issubset(llm_taxonomy.columns):
            icd_case_detail = llm_taxonomy[
                ["center", "case_id", "final_icd10_code", "final_icd10_name", "source_gt_path"]
            ].copy()
            mapped = icd_case_detail["final_icd10_code"].map(_map_icd10_chapter)
            icd_case_detail["ICD10Chapter"] = mapped.map(lambda x: x[0])
            icd_case_detail["ICD10ChapterName"] = mapped.map(lambda x: x[1])

    current_g1_figure = out_img_no_sankey_e_alt
    current_g1e_figure = out_e_palm_line

    version_rows = [
        {
            "panel": "G1整体",
            "variant": "no_sankey_e_alt",
            "file": str(current_g1_figure.relative_to(ROOT)) if current_g1_figure.exists() else "",
            "style": "当前定版：e 面板替换为 PALM-COEIN 分类长尾折线",
            "is_latest": 1 if current_g1_figure.exists() else 0,
        },
        {
            "panel": "G1b",
            "variant": "barh_stacked",
            "file": str(out_palm_stage_bar.relative_to(ROOT)) if out_palm_stage_bar.exists() else "",
            "style": "当前定版：PALM-COEIN三阶段横向堆叠柱",
            "is_latest": 1 if out_palm_stage_bar.exists() else 0,
        },
        {
            "panel": "G1e",
            "variant": "palm_longtail",
            "file": str(current_g1e_figure.relative_to(ROOT)) if current_g1e_figure is not None and current_g1e_figure.exists() else "",
            "style": "当前定版：PALM-COEIN 分类长尾（按最终阶段病例数统计）",
            "is_latest": 1 if current_g1e_figure is not None and current_g1e_figure.exists() else 0,
        },
        {
            "panel": "G1g",
            "variant": "barh_stacked",
            "file": str(out_plan_mix_bar.relative_to(ROOT)) if out_plan_mix_bar.exists() else "",
            "style": "当前定版：方案四阶段横向堆叠柱",
            "is_latest": 1 if out_plan_mix_bar.exists() else 0,
        },
    ]
    summary_versions = pd.DataFrame(version_rows)
    source_path = _write_source_workbook(
        group=group,
        stem="G1_dataset_overview_v2",
        sheets={
            "detail_center": center,
            "detail_diag_stage": diag_stage,
            "detail_diag_stage_palm": palm_detail,
            "detail_llm_taxonomy_case": llm_detail if not llm_detail.empty else llm_taxonomy,
            "detail_center_bm_case": center_bm_case_detail,
            "detail_llm_taxonomy_error_case": llm_error_detail,
            "detail_palm_stage_pct_nonsankey": palm_stage_pct,
            "detail_text_len": text_len,
            "detail_icd": icd,
            "detail_icd_case": icd_case_detail,
            "detail_longtail": palm_longtail if not palm_longtail.empty else longtail,
            "detail_check_type": check_type,
            "detail_check_type_case_level": check_type_detail if not check_type_detail.empty else check_type,
            "detail_plan_type": plan_type,
            "detail_plan_continuity": plan_detail,
            "detail_plan_stage_pct_nonsankey": plan_stage_pct,
            "summary_center": summary_center,
            "summary_diag_stage": summary_diag_stage,
            "summary_diag_stage_palm": summary_palm_stage,
            "summary_center_benign_malignant": summary_bm,
            "summary_llm_taxonomy_quality": llm_quality_summary,
            "summary_text_len": summary_text,
            "summary_icd": summary_icd,
            "summary_longtail": summary_palm_overall if not summary_palm_overall.empty else summary_longtail,
            "summary_check_type": summary_check,
            "summary_plan_type": summary_plan,
            "summary_figure_versions": summary_versions,
        },
        meta={
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "figure": str(current_g1_figure.relative_to(ROOT)),
            "description": "G1 数据集概况当前定版切回 no_sankey_e_alt 方案；主图 e 面板与相关子图统一采用 PALM-COEIN 分类长尾口径。",
            "source_data_policy": "detail+summary+meta; 可复算；与paper figdata一致口径",
            "source_hint__detail_check_type_case_level": "analysis_viz/data/raw/center_data/*/GT/*.xlsx:Sheet1[GT_Outpatient_Checks,GT_Admission_Checks]",
            "source_hint__detail_diag_stage_palm": "analysis_viz/data/raw/center_data/*/GT/*.xlsx:Sheet1[GT_Admission_Diagnosis,GT_Revised_Diagnosis,GT_Final_Diagnosis]",
            "source_hint__detail_llm_taxonomy_case": "analysis_viz/data/derived/figdata/v2_subplots/G1_dataset/G1_llm_case_taxonomy_v1.csv",
            "source_hint__detail_llm_taxonomy_error_case": "analysis_viz/data/derived/figdata/v2_subplots/G1_dataset/G1_llm_case_taxonomy_v1.csv[error,fallback_used]",
            "source_hint__detail_icd": "analysis_viz/data/derived/figdata/v2_subplots/G1_dataset/G1_llm_case_taxonomy_v1.csv[final_icd10_code]",
            "source_hint__detail_icd_case": "analysis_viz/data/derived/figdata/v2_subplots/G1_dataset/G1_llm_case_taxonomy_v1.csv[center,case_id,final_icd10_code]",
            "source_hint__detail_plan_continuity": "analysis_viz/data/derived/figdata/v2_subplots/G1_dataset/G1_llm_case_taxonomy_v1.csv",
            "source_hint__detail_palm_stage_pct_nonsankey": "由 detail_diag_stage_palm 按 stage4×palm_coein 汇总后标准化为百分比",
            "source_hint__detail_longtail": "由 detail_diag_stage_palm 中 D3 最终阶段按 palm_coein 汇总；仅对应当前保留的 PALM-COEIN 长尾子图。",
            "source_hint__detail_plan_stage_pct_nonsankey": "由 detail_plan_continuity 按 plan_stage×plan_label 汇总后标准化为百分比",
            "source_hint__detail_center_bm_case": "A图内圈复现明细；final_benign_malignant 基于 d3_palm_label 进行恶性兜底纠偏",
            "formula_core": "总览公式已并入各 summary sheet（样本量/中心数/ICD与方案类别计数不再单独开公式sheet）。",
        },
    )
    _write_caption(
        group,
        [
            "# G1 组图图注",
            "",
            "- `G1_dataset_overview_no_sankey_e_alt_v1.png`：该组图为当前保留的主展示版本，统一展示中心构成、诊断迁移、文本密度、ICD编码分布、PALM-COEIN 分类长尾、检查谱系与治疗策略；其中 b/g 均改为非 Sankey 视图，以减少组图内部的视觉拥挤并提升论文排版可读性。",
            "- `G1a_center_distribution_v2.png`：该子图采用双层环图，外圈显示三中心样本占比，内圈显示全样本“良性/恶性/非肿瘤”划分，借此在同一视图同时给出数据来源结构与疾病性质结构，便于后续指标解释统一基数。",
            "- `G1b_palm_coein_stage_bar_v1.png`：该子图为当前保留的 b 子图，按“初步诊断→修正诊断→最终诊断”三阶段展示 PALM-COEIN 分型构成；其中“**不适用**”表示妊娠相关不纳入 PALM，`D2` 诊断为“无/空值”时继承同病例上一轮（D1）的具体分类。",
            "- `G1c_text_density_v2.png`：该子图用直方图呈现病例文本长度分布并标注中位线，统计单位统一为“非空格字符（含标点）”，用于衡量输入信息密度与长尾文本风险，为解释复杂病例的性能波动提供背景依据。",
            "- `G1d_icd_chapter_v2.png`：该子图改为最终诊断 ICD-10 编码分布（按编码聚合，不再按章节聚合），用于更直接地展示病种编码覆盖结构并支持后续按具体编码回溯数据来源。",
            "- `G1e_longtail_palm_line_v1.png`：该子图以“PALM-COEIN 分类排名（按病例数降序）—病例数”折线刻画当前保留主图所对应的长尾分布，并标注低频分类比例；该口径与主图 e 面板保持一致。",
            "- `G1f_check_profile_v2.png`：该子图对比门诊与住院阶段检查类型构成，纵轴“检查请求次数”定义为“病例×检查类型命中次数”；门诊关键词映射中剔除了高误判词（如‘镜下’）以降低病理学检查误分风险。",
            "- `G1g_plan_mix_stacked_bar_v1.png`：该子图为当前保留的 g 子图，按“手术→术后→康复→随访”四阶段展示方案类型构成；其中“无/未提及”固定置于最下方并使用灰色，便于区分真实方案延续与信息缺失路径。",
            "- `G1e_longtail_v2.png`：该历史版本按“最终诊断标签”统计长尾，统计对象与当前 PALM-COEIN 分类长尾不同，因此不再作为主图相关子图保留。",
            "- `G1_dataset_overview_v2.png`、`G1_dataset_overview_all_sankey_v1.png`、`G1_dataset_overview_no_sankey_v1.png`、`G1_dataset_overview_no_sankey_e_alt_2row_v1.png`、`G1b_diagnosis_progression_v2.png`、`G1g_plan_mix_v2.png` 及其他历史替代图已统一迁入 `archive/`，主目录仅保留当前论文展示所需版本。",
        ],
    )
    keep_fig = {
        current_g1_figure.name,
        sub_figs["G1a_center_distribution_v2"].name,
        sub_figs["G1c_text_density_v2"].name,
        sub_figs["G1d_icd_chapter_v2"].name,
        current_g1e_figure.name if current_g1e_figure is not None else out_e_palm_line.name,
        sub_figs["G1f_check_profile_v2"].name,
        out_palm_stage_bar.name,
        out_plan_mix_bar.name,
    }
    _archive_group_outputs(group=group, keep_fig_names=keep_fig, keep_source_names={source_path.name})

    kept_outputs: dict[str, Path] = {
        "figure": current_g1_figure,
        "source": source_path,
        "G1a_center_distribution_v2": sub_figs["G1a_center_distribution_v2"],
        "G1b_palm_coein_stage_bar_v1": out_palm_stage_bar,
        "G1c_text_density_v2": sub_figs["G1c_text_density_v2"],
        "G1d_icd_chapter_v2": sub_figs["G1d_icd_chapter_v2"],
        "G1e_longtail_palm_line_v1": current_g1e_figure if current_g1e_figure is not None else out_e_palm_line,
        "G1f_check_profile_v2": sub_figs["G1f_check_profile_v2"],
        "G1g_plan_mix_stacked_bar_v1": out_plan_mix_bar,
    }
    return kept_outputs


def build_g2_outcome(
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
    d2_rule_map: pd.DataFrame,
) -> dict[str, Path]:
    _ensure_style()
    group = "G2_outcome"
    out_img = OUT_FIG_DIR / group / "G2_outcome_metrics_v6.png"
    out_img_alt_bm = OUT_FIG_DIR / group / "G2_outcome_metrics_alt_bm_v3.png"
    out_check_rounds = OUT_FIG_DIR / group / "G2C_check_efficiency_rounds_v1.png"
    out_bm_stage = OUT_FIG_DIR / group / "G2B_diag_robustness_bm_stage_v1.png"
    out_ab_dual = OUT_FIG_DIR / group / "G2AB_diag_quality_robustness_dualaxis_v1.png"

    loop_case_src = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="metrics_by_case")

    diag = _load_g2_diag_from_center_judge(d1_set, gate3_set)
    diag["center"] = diag["center"].astype(str)
    diag["case_id"] = diag["case_id"].astype(str)
    diag = _attach_d2_manual_rules(diag, d2_rule_map)
    diag = diag[~(diag["d2_force_stop"] & diag["stage"].astype(str).isin(["D3_Decision"]))].copy()

    plan = _load_g2_plan_from_center_judge(d1_set, gate3_set)
    plan["center"] = plan["center"].astype(str)
    plan["case_id"] = plan["case_id"].astype(str)
    plan = _attach_d2_manual_rules(plan, d2_rule_map)
    plan = plan[~(plan["d2_force_stop"] & plan["stage"].astype(str).isin(["D3_Decision", "D4_Plan"]))].copy()

    cols = [
        "center",
        "model",
        "case_id",
        "D1_Outpatient_Loop__matched_total",
        "D1_Outpatient_Loop__requested_total",
        "D1_Outpatient_Loop__ineff_rounds_by_zero",
        "D1_Outpatient_Loop__executed_rounds",
        "D2_SuggestedFromD1Decision__matched_total",
        "D2_SuggestedFromD1Decision__requested_total",
        "D2_SuggestedFromD1Decision__ineff_rounds_by_zero",
        "D2_SuggestedFromD1Decision__executed_rounds",
        "D2_Admission_Loop__matched_total",
        "D2_Admission_Loop__requested_total",
        "D2_Admission_Loop__ineff_rounds_by_zero",
        "D2_Admission_Loop__executed_rounds",
    ]
    for c in cols:
        if c not in loop_case_src.columns:
            loop_case_src[c] = np.nan
    loop_base = loop_case_src[cols].copy()
    loop_base["model_short"] = loop_base["model"].map(MODEL_SHORT).fillna(loop_base["model"].astype(str))
    loop_base = _attach_rules(loop_base, d1_set, gate3_set)
    loop_base = loop_base[~loop_base["is_d1_anomaly"]].copy()
    loop_base["center"] = loop_base["center"].astype(str)
    loop_base["case_id"] = loop_base["case_id"].astype(str)
    for c in cols:
        if c not in {"center", "model", "case_id"}:
            loop_base[c] = pd.to_numeric(loop_base[c], errors="coerce").fillna(0.0)

    loop_base["d1_match_rate"] = np.where(
        loop_base["D1_Outpatient_Loop__requested_total"] > 0,
        loop_base["D1_Outpatient_Loop__matched_total"] / loop_base["D1_Outpatient_Loop__requested_total"],
        np.nan,
    )
    loop_base["d1_dec_check_match_rate"] = np.where(
        loop_base["D2_SuggestedFromD1Decision__requested_total"] > 0,
        loop_base["D2_SuggestedFromD1Decision__matched_total"] / loop_base["D2_SuggestedFromD1Decision__requested_total"],
        np.nan,
    )
    loop_base["d2_match_rate"] = np.where(
        loop_base["D2_Admission_Loop__requested_total"] > 0,
        loop_base["D2_Admission_Loop__matched_total"] / loop_base["D2_Admission_Loop__requested_total"],
        np.nan,
    )
    loop_base["d2_merge_match_rate"] = np.where(
        (loop_base["D2_SuggestedFromD1Decision__requested_total"] + loop_base["D2_Admission_Loop__requested_total"]) > 0,
        (loop_base["D2_SuggestedFromD1Decision__matched_total"] + loop_base["D2_Admission_Loop__matched_total"])
        / (loop_base["D2_SuggestedFromD1Decision__requested_total"] + loop_base["D2_Admission_Loop__requested_total"]),
        np.nan,
    )
    loop_base["d1_ineff_rate"] = np.where(
        loop_base["D1_Outpatient_Loop__executed_rounds"] > 0,
        loop_base["D1_Outpatient_Loop__ineff_rounds_by_zero"] / loop_base["D1_Outpatient_Loop__executed_rounds"],
        np.nan,
    )
    loop_base["d1_dec_check_ineff_rate"] = np.where(
        loop_base["D2_SuggestedFromD1Decision__executed_rounds"] > 0,
        loop_base["D2_SuggestedFromD1Decision__ineff_rounds_by_zero"] / loop_base["D2_SuggestedFromD1Decision__executed_rounds"],
        np.nan,
    )
    loop_base["d2_ineff_rate"] = np.where(
        loop_base["D2_Admission_Loop__executed_rounds"] > 0,
        loop_base["D2_Admission_Loop__ineff_rounds_by_zero"] / loop_base["D2_Admission_Loop__executed_rounds"],
        np.nan,
    )
    loop_base["d2_merge_ineff_rate"] = np.where(
        (loop_base["D2_SuggestedFromD1Decision__executed_rounds"] + loop_base["D2_Admission_Loop__executed_rounds"]) > 0,
        (loop_base["D2_SuggestedFromD1Decision__ineff_rounds_by_zero"] + loop_base["D2_Admission_Loop__ineff_rounds_by_zero"])
        / (loop_base["D2_SuggestedFromD1Decision__executed_rounds"] + loop_base["D2_Admission_Loop__executed_rounds"]),
        np.nan,
    )
    calc_loop_case = loop_base[
        [
            "center",
            "model",
            "case_id",
            "model_short",
            "D1_Outpatient_Loop__matched_total",
            "D1_Outpatient_Loop__requested_total",
            "D1_Outpatient_Loop__ineff_rounds_by_zero",
            "D1_Outpatient_Loop__executed_rounds",
            "D2_SuggestedFromD1Decision__matched_total",
            "D2_SuggestedFromD1Decision__requested_total",
            "D2_SuggestedFromD1Decision__ineff_rounds_by_zero",
            "D2_SuggestedFromD1Decision__executed_rounds",
            "D2_Admission_Loop__matched_total",
            "D2_Admission_Loop__requested_total",
            "D2_Admission_Loop__ineff_rounds_by_zero",
            "D2_Admission_Loop__executed_rounds",
            "d1_match_rate",
            "d2_merge_match_rate",
            "d1_ineff_rate",
            "d2_merge_ineff_rate",
        ]
    ].copy()
    calc_loop_case.insert(0, "source_table", "metrics_source_data.xlsx:metrics_by_case")
    loop_rows = np.arange(2, len(calc_loop_case) + 2)
    calc_loop_case["formula_d1_match_rate"] = [f"=IF(G{r}>0,F{r}/G{r},\"\")" for r in loop_rows]
    calc_loop_case["formula_d2_merge_match_rate"] = [f"=IF((K{r}+O{r})>0,(J{r}+N{r})/(K{r}+O{r}),\"\")" for r in loop_rows]
    calc_loop_case["formula_d1_ineff_rate"] = [f"=IF(I{r}>0,H{r}/I{r},\"\")" for r in loop_rows]
    calc_loop_case["formula_d2_merge_ineff_rate"] = [f"=IF((M{r}+Q{r})>0,(L{r}+P{r})/(M{r}+Q{r}),\"\")" for r in loop_rows]
    calc_loop_case["说明_分子分母"] = (
        "检查质量=matched_total/requested_total；无效循环率=ineff_rounds_by_zero/executed_rounds；D2为(建议检查+住院循环)合并口径"
    )

    check_score_stage3 = pd.concat(
        [
            loop_base[["center", "model", "case_id", "model_short", "d1_match_rate"]]
            .rename(columns={"d1_match_rate": "check_score"})
            .assign(stage="D1_Loop"),
            loop_base[["center", "model", "case_id", "model_short", "d1_dec_check_match_rate"]]
            .rename(columns={"d1_dec_check_match_rate": "check_score"})
            .assign(stage="D1_Decision_Check"),
            loop_base[["center", "model", "case_id", "model_short", "d2_match_rate"]]
            .rename(columns={"d2_match_rate": "check_score"})
            .assign(stage="D2_Loop"),
        ],
        ignore_index=True,
    ).dropna(subset=["check_score"])
    check_score_stage3["source_sheet"] = "metrics_source_data.xlsx:metrics_by_case"
    check_score_stage3["source_column"] = "matched_total / requested_total"
    check_score_stage3["source_path"] = "analysis_viz/data/raw/metrics_source_data.xlsx"

    check_score_stage2 = pd.concat(
        [
            loop_base[["center", "model", "case_id", "model_short", "d1_match_rate"]]
            .rename(columns={"d1_match_rate": "check_score"})
            .assign(stage="D1_Loop"),
            loop_base[["center", "model", "case_id", "model_short", "d2_merge_match_rate"]]
            .rename(columns={"d2_merge_match_rate": "check_score"})
            .assign(stage="D2_Check_Merged"),
        ],
        ignore_index=True,
    ).dropna(subset=["check_score"])
    check_score_stage2["source_sheet"] = "metrics_source_data.xlsx:metrics_by_case"
    check_score_stage2["source_column"] = "merged matched_total / merged requested_total"
    check_score_stage2["source_path"] = "analysis_viz/data/raw/metrics_source_data.xlsx"

    ineff_stage3 = pd.concat(
        [
            loop_base[["center", "model", "case_id", "model_short", "d1_ineff_rate"]]
            .rename(columns={"d1_ineff_rate": "ineff_rate"})
            .assign(stage="D1_Loop"),
            loop_base[["center", "model", "case_id", "model_short", "d1_dec_check_ineff_rate"]]
            .rename(columns={"d1_dec_check_ineff_rate": "ineff_rate"})
            .assign(stage="D1_Decision_Check"),
            loop_base[["center", "model", "case_id", "model_short", "d2_ineff_rate"]]
            .rename(columns={"d2_ineff_rate": "ineff_rate"})
            .assign(stage="D2_Loop"),
        ],
        ignore_index=True,
    ).dropna(subset=["ineff_rate"])
    ineff_stage3["source_sheet"] = "metrics_source_data.xlsx:metrics_by_case"
    ineff_stage3["source_column"] = "ineff_rounds_by_zero / executed_rounds"
    ineff_stage3["source_path"] = "analysis_viz/data/raw/metrics_source_data.xlsx"

    ineff_stage2 = pd.concat(
        [
            loop_base[["center", "model", "case_id", "model_short", "d1_ineff_rate"]]
            .rename(columns={"d1_ineff_rate": "ineff_rate"})
            .assign(stage="D1_Loop"),
            loop_base[["center", "model", "case_id", "model_short", "d2_merge_ineff_rate"]]
            .rename(columns={"d2_merge_ineff_rate": "ineff_rate"})
            .assign(stage="D2_Check_Merged"),
        ],
        ignore_index=True,
    ).dropna(subset=["ineff_rate"])
    ineff_stage2["source_sheet"] = "metrics_source_data.xlsx:metrics_by_case"
    ineff_stage2["source_column"] = "merged ineff_rounds_by_zero / merged executed_rounds"
    ineff_stage2["source_path"] = "analysis_viz/data/raw/metrics_source_data.xlsx"

    # 把病例级公式回并到明细表，减少“必须跨sheet追公式”的阅读成本
    loop_formula_map = calc_loop_case[
        [
            "center",
            "model",
            "case_id",
            "formula_d1_match_rate",
            "formula_d2_merge_match_rate",
            "formula_d1_ineff_rate",
            "formula_d2_merge_ineff_rate",
            "说明_分子分母",
        ]
    ].copy()
    check_score_stage2 = check_score_stage2.merge(loop_formula_map, on=["center", "model", "case_id"], how="left")
    check_score_stage2["formula_check_score_0_1"] = np.where(
        check_score_stage2["stage"].astype(str).eq("D1_Loop"),
        check_score_stage2["formula_d1_match_rate"],
        check_score_stage2["formula_d2_merge_match_rate"],
    )
    check_score_stage2["说明_阶段口径"] = "D1_Loop 使用门诊检查公式；D2_Check_Merged 使用(D1决策检查+住院检查)合并公式"

    ineff_stage2 = ineff_stage2.merge(loop_formula_map, on=["center", "model", "case_id"], how="left")
    ineff_stage2["formula_ineff_rate_0_1"] = np.where(
        ineff_stage2["stage"].astype(str).eq("D1_Loop"),
        ineff_stage2["formula_d1_ineff_rate"],
        ineff_stage2["formula_d2_merge_ineff_rate"],
    )
    ineff_stage2["说明_阶段口径"] = "D1_Loop 使用门诊无效循环率；D2_Check_Merged 使用(D1决策检查+住院检查)合并无效循环率"

    round_cols = [
        "center",
        "model",
        "case_id",
        "stage",
        "round_idx",
        "doc_status",
        "judge_match_score_raw",
        "ai_total_requested_count",
        "inefficient_round_by_zero",
    ]
    rounds = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="check_rounds")
    for c in round_cols:
        if c not in rounds.columns:
            rounds[c] = np.nan
    rounds = rounds[round_cols].copy()
    rounds = _attach_rules(rounds, d1_set, gate3_set)
    rounds = rounds[~rounds["is_d1_anomaly"]].copy()
    rounds["center"] = rounds["center"].astype(str)
    rounds["case_id"] = rounds["case_id"].astype(str)
    rounds["stage"] = rounds["stage"].astype(str)
    rounds = rounds[rounds["stage"].isin(["D1_Outpatient_Loop", "D2_SuggestedFromD1Decision", "D2_Admission_Loop"])].copy()
    rounds["round_idx"] = pd.to_numeric(rounds["round_idx"], errors="coerce").fillna(0).astype(int)
    rounds["requested_count"] = pd.to_numeric(rounds["ai_total_requested_count"], errors="coerce").fillna(0.0)
    rounds["match_rate"] = pd.to_numeric(rounds["judge_match_score_raw"], errors="coerce")
    rounds["doc_status"] = rounds["doc_status"].astype(str)
    rounds = rounds[rounds["round_idx"] > 0].copy()
    rounds["is_active_round"] = (
        (rounds["requested_count"] > 0)
        | rounds["match_rate"].notna()
        | (~rounds["doc_status"].str.contains("未经过", na=False))
    )
    ineff_num = pd.to_numeric(rounds["inefficient_round_by_zero"], errors="coerce")
    rounds["ineff_zero"] = ineff_num.fillna(0.0) > 0
    rounds.loc[ineff_num.isna(), "ineff_zero"] = (
        rounds.loc[ineff_num.isna(), "inefficient_round_by_zero"].astype(str).str.lower().isin({"true", "yes", "y"})
    )
    rounds["round_phase"] = ""
    rounds["round_bin"] = np.nan
    m_op = rounds["stage"] == "D1_Outpatient_Loop"
    rounds.loc[m_op, "round_phase"] = "OP"
    rounds.loc[m_op, "round_bin"] = rounds.loc[m_op, "round_idx"].clip(1, 3)
    m_dec = rounds["stage"] == "D2_SuggestedFromD1Decision"
    rounds.loc[m_dec, "round_phase"] = "IP"
    rounds.loc[m_dec, "round_bin"] = 1
    m_ip = rounds["stage"] == "D2_Admission_Loop"
    rounds.loc[m_ip, "round_phase"] = "IP"
    rounds.loc[m_ip, "round_bin"] = rounds.loc[m_ip, "round_idx"].clip(1, 3)
    rounds = rounds[rounds["round_phase"].isin(["OP", "IP"])].copy()
    rounds["round_bin"] = pd.to_numeric(rounds["round_bin"], errors="coerce").fillna(0).astype(int)
    rounds = rounds[rounds["round_bin"].between(1, 3)].copy()
    rounds["model_short"] = rounds["model"].map(MODEL_SHORT).fillna(rounds["model"].astype(str))
    rounds["stage_round"] = rounds["round_phase"] + "_R" + rounds["round_bin"].astype(str)
    rounds["match_num"] = rounds["match_rate"].fillna(0.0) * rounds["requested_count"]

    round_case = (
        rounds.groupby(["center", "model", "case_id", "model_short", "stage_round"], as_index=False)
        .agg(
            match_num=("match_num", "sum"),
            req_sum=("requested_count", "sum"),
            ineff_num=("ineff_zero", "sum"),
            active_num=("is_active_round", "sum"),
        )
    )
    round_case["check_score"] = np.where(round_case["req_sum"] > 0, round_case["match_num"] / round_case["req_sum"], np.nan)
    round_case["ineff_rate"] = np.where(round_case["active_num"] > 0, round_case["ineff_num"] / round_case["active_num"], np.nan)
    check_score_round = (
        round_case[["center", "model", "case_id", "model_short", "stage_round", "check_score"]]
        .rename(columns={"stage_round": "stage"})
        .dropna(subset=["check_score"])
    )
    ineff_round = (
        round_case[["center", "model", "case_id", "model_short", "stage_round", "ineff_rate"]]
        .rename(columns={"stage_round": "stage"})
        .dropna(subset=["ineff_rate"])
    )
    check_score_round["source_sheet"] = "metrics_source_data.xlsx:check_rounds"
    check_score_round["source_column"] = "sum(judge_match_score_raw * ai_total_requested_count) / sum(ai_total_requested_count)"
    check_score_round["source_path"] = "analysis_viz/data/raw/metrics_source_data.xlsx"
    ineff_round["source_sheet"] = "metrics_source_data.xlsx:check_rounds"
    ineff_round["source_column"] = "sum(inefficient_round_by_zero) / sum(active_round)"
    ineff_round["source_path"] = "analysis_viz/data/raw/metrics_source_data.xlsx"

    g1_source_candidates = [
        OUT_DATA_DIR / "G1_dataset" / "G1_dataset_overview_v2_source.xlsx",
        OUT_FIG_DIR / "G1_dataset" / "source_data" / "G1_dataset_overview_v2_source.xlsx",
    ]
    g1_diag_stage_palm = pd.DataFrame()
    g1_taxonomy_case = pd.DataFrame()
    g1_source_rel = ""
    for cpath in g1_source_candidates:
        if not cpath.exists():
            continue
        try:
            g1_diag_stage_palm = pd.read_excel(cpath, sheet_name="detail_diag_stage_palm")
            g1_taxonomy_case = pd.read_excel(cpath, sheet_name="detail_llm_taxonomy_case")
            g1_source_rel = str(cpath.relative_to(ROOT)).replace("\\", "/")
            break
        except Exception:
            continue

    diag_palm_final = pd.DataFrame()
    diag_palm_detail = pd.DataFrame()
    diag_final = diag[diag["stage"] == "D3_Decision"].copy()
    if not g1_diag_stage_palm.empty:
        palm_map = g1_diag_stage_palm.copy()
        if {"center", "case_id", "stage4", "palm_coein"}.issubset(set(palm_map.columns)):
            palm_map["center"] = palm_map["center"].astype(str)
            palm_map["case_id"] = palm_map["case_id"].astype(str)
            palm_map = palm_map[palm_map["stage4"].astype(str) == "D3"][["center", "case_id", "palm_coein"]].copy()
            diag_palm_detail = diag_final.merge(palm_map, on=["center", "case_id"], how="left")
    if diag_palm_detail.empty:
        try:
            palm_detail, _, _ = _build_palm_coein_from_gt()
            palm_map = palm_detail[palm_detail["stage4"] == "D3"][["center", "case_id", "palm_coein"]].copy()
            palm_map["center"] = palm_map["center"].astype(str)
            palm_map["case_id"] = palm_map["case_id"].astype(str)
            diag_palm_detail = diag_final.merge(palm_map, on=["center", "case_id"], how="left")
        except Exception:
            diag_palm_detail = diag_final.copy()
    diag_palm_detail["palm_coein"] = diag_palm_detail["palm_coein"].astype(str).where(
        diag_palm_detail["palm_coein"].astype(str).isin(PALM_COEIN_ORDER),
        "N-非肿瘤",
    )
    diag_palm_final = (
        diag_palm_detail.groupby("palm_coein", as_index=False)
        .agg(sample_cases=("case_id", "nunique"), diag_score_mean=("value", "mean"), model_case_n=("case_id", "count"))
        .copy()
    )
    diag_palm_final["palm_coein"] = pd.Categorical(diag_palm_final["palm_coein"], categories=PALM_COEIN_ORDER, ordered=True)
    diag_palm_final = (
        diag_palm_final.sort_values("palm_coein", kind="mergesort")
        .reset_index(drop=True)
    )

    bm_fallback = _load_g1_llm_taxonomy()
    if g1_taxonomy_case.empty and (not bm_fallback.empty):
        g1_taxonomy_case = bm_fallback[
            [c for c in ["center", "case_id", "final_benign_malignant", "d3_palm_label"] if c in bm_fallback.columns]
        ].copy()
    diag_bm_stage = pd.DataFrame()
    diag_bm_detail = pd.DataFrame()
    if not g1_taxonomy_case.empty and {"center", "case_id"}.issubset(set(g1_taxonomy_case.columns)):
        bm_map = g1_taxonomy_case.copy()
        bm_map["center"] = bm_map["center"].astype(str)
        bm_map["case_id"] = bm_map["case_id"].astype(str)
        if "final_benign_malignant" not in bm_map.columns:
            bm_map["final_benign_malignant"] = "非肿瘤"
        bm_map["final_benign_malignant"] = (
            bm_map["final_benign_malignant"]
            .astype(str)
            .str.strip()
            .replace(
                {
                    "benign": "良性",
                    "malignant": "恶性",
                    "unknown": "非肿瘤",
                    "None": "非肿瘤",
                    "nan": "非肿瘤",
                    "": "非肿瘤",
                }
            )
        )
        if "d3_palm_label" in bm_map.columns:
            bm_map.loc[bm_map["d3_palm_label"].astype(str) == "M-恶性/增生", "final_benign_malignant"] = "恶性"
        bm_map["final_benign_malignant"] = bm_map["final_benign_malignant"].where(
            bm_map["final_benign_malignant"].isin(["良性", "恶性", "非肿瘤"]),
            "非肿瘤",
        )
        bm_map = bm_map[["center", "case_id", "final_benign_malignant"]].drop_duplicates()
        diag_bm_detail = diag.merge(bm_map, on=["center", "case_id"], how="left")
        diag_bm_detail["final_benign_malignant"] = diag_bm_detail["final_benign_malignant"].fillna("非肿瘤")
        diag_bm_detail["stage_semantic"] = diag_bm_detail["stage"].map(
            {"D1_Decision": "初始诊断", "D2_Decision": "修正诊断", "D3_Decision": "最终诊断"}
        )
        diag_bm_detail = diag_bm_detail[diag_bm_detail["stage_semantic"].notna()].copy()
        diag_bm_stage = (
            diag_bm_detail.groupby(["stage_semantic", "final_benign_malignant"], as_index=False)
            .agg(sample_cases=("case_id", "nunique"), diag_score_mean=("value", "mean"), model_case_n=("case_id", "count"))
            .sort_values(["stage_semantic", "final_benign_malignant"], kind="mergesort")
        )

    diag_mean_for_ylim = (
        diag.groupby(["stage", "model_short"], as_index=False)["value"].mean().dropna(subset=["value"])
    )
    diag_ylim = _adaptive_ylim(
        diag_mean_for_ylim["value"] if not diag_mean_for_ylim.empty else diag["value"],
        fallback=(0.0, 1.0),
        domain=(0.0, 1.0),
        min_span=0.10,
    )
    plan_ylim = _adaptive_ylim(plan["value"], fallback=(0.0, 1.0), domain=(0.0, 1.0), min_span=0.2)
    check2_ylim = _adaptive_ylim(check_score_stage2["check_score"], fallback=(0.0, 1.0), domain=(0.0, 1.0), min_span=0.2)
    ineff2_ylim = _adaptive_ylim(ineff_stage2["ineff_rate"], fallback=(0.0, 1.0), domain=(0.0, 1.0), min_span=0.2)
    check_round_ylim = _adaptive_ylim(check_score_round["check_score"], fallback=(0.0, 1.0), domain=(0.0, 1.0), min_span=0.2)
    ineff_round_ylim = _adaptive_ylim(ineff_round["ineff_rate"], fallback=(0.0, 1.0), domain=(0.0, 1.0), min_span=0.2)

    fig = plt.figure(figsize=(18.2, 10.4))
    gs = fig.add_gridspec(2, 2, hspace=0.44, wspace=0.24)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, 0])
    ax_d = fig.add_subplot(gs[1, 1])

    def _plot_stage_quality_bar(
        ax: plt.Axes,
        detail: pd.DataFrame,
        stage_order: list[str],
        stage_label_map: dict[str, str],
        title: str,
        y_label: str,
        bar_color: str,
        ylim: tuple[float, float],
    ) -> None:
        d = detail.copy()
        d = d[d["stage"].astype(str).isin(stage_order)].copy()
        d["score"] = pd.to_numeric(d["score"], errors="coerce")
        d = d.dropna(subset=["score"])
        if d.empty:
            ax.text(0.5, 0.5, "无可绘制数据", ha="center", va="center", transform=ax.transAxes)
            ax.set_xticks([])
            return
        stage_model = (
            d.groupby(["stage", "model_short"], as_index=False)["score"]
            .mean()
            .sort_values(["stage", "model_short"], kind="mergesort")
        )
        stage_stat = (
            stage_model.groupby("stage", as_index=False)
            .agg(mean_score=("score", "mean"), std_score=("score", "std"))
            .sort_values("stage", key=lambda s: s.map({k: i for i, k in enumerate(stage_order)}), kind="mergesort")
        )
        x = np.arange(len(stage_order), dtype=float)
        mean_map = {str(r["stage"]): float(r["mean_score"]) for _, r in stage_stat.iterrows()}
        std_map = {str(r["stage"]): float(pd.to_numeric(r["std_score"], errors="coerce")) if pd.notna(r["std_score"]) else 0.0 for _, r in stage_stat.iterrows()}
        y = np.array([mean_map.get(s, np.nan) for s in stage_order], dtype=float)
        yerr = np.array([std_map.get(s, 0.0) for s in stage_order], dtype=float)
        bars = ax.bar(
            x,
            y,
            yerr=yerr,
            color=bar_color,
            edgecolor="#2B3A4A",
            linewidth=1.0,
            alpha=0.84,
            width=0.56,
            capsize=4,
            zorder=2.8,
            label="总体均值",
        )
        for m_idx, model in enumerate(MODEL_ORDER):
            sub = stage_model[stage_model["model_short"] == model]
            if sub.empty:
                continue
            m_map = {str(r["stage"]): float(r["score"]) for _, r in sub.iterrows()}
            ys = [m_map.get(s, np.nan) for s in stage_order]
            jitter = (m_idx - (len(MODEL_ORDER) - 1) / 2.0) * 0.035
            ax.scatter(
                x + jitter,
                ys,
                s=48,
                marker=MODEL_MARKER.get(model, "o"),
                color=MODEL_COLOR.get(model, "#666666"),
                edgecolors="white",
                linewidths=0.55,
                alpha=0.92,
                zorder=3.6,
            )
        for bar, val in zip(bars, y):
            if pd.isna(val):
                continue
            y_top = float(ax.get_ylim()[1])
            text_y = float(val) + 0.015
            va = "bottom"
            # 顶部空间不足时把数值标签放到柱内，避免挡住误差线/边界
            if text_y > y_top - 0.008:
                text_y = max(float(val) - 0.018, float(ax.get_ylim()[0]) + 0.012)
                va = "top"
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                text_y,
                f"{float(val):.2f}",
                ha="center",
                va=va,
                fontsize=8.8,
                color="#1F2D3D",
            )
        ax.set_xticks(x)
        ax.set_xticklabels([stage_label_map.get(s, s) for s in stage_order], fontsize=11.2)
        ax.set_title(title)
        ax.set_ylabel(y_label)
        ax.set_ylim(ylim[0], ylim[1])
        ax.grid(alpha=0.22, axis="y", zorder=0)
        ax.legend(loc="upper right", fontsize=8.2, frameon=True)

    _plot_stage_quality_bar(
        ax=ax_a,
        detail=diag.rename(columns={"value": "score"}),
        stage_order=["D1_Decision", "D2_Decision", "D3_Decision"],
        stage_label_map={
            "D1_Decision": "初始诊断",
            "D2_Decision": "修正诊断",
            "D3_Decision": "最终诊断",
        },
        title="A. 诊断质量",
        y_label="诊断质量得分",
        bar_color="#F3BE8A",
        ylim=(0.0, 1.0),
    )
    ax_a.yaxis.set_major_locator(MultipleLocator(0.1))
    ax_a.set_ylim(0.0, 1.0)

    if diag_palm_final.empty:
        ax_b.text(0.5, 0.5, "无 PALM-COEIN 数据", ha="center", va="center")
        ax_b.set_title("B. PALM 九分类鲁棒性")
    else:
        sub = diag_palm_final[diag_palm_final["sample_cases"] > 0].copy()
        x = np.arange(len(sub))
        bars_b = ax_b.bar(
            x,
            sub["sample_cases"],
            color=[PALM_COEIN_COLOR.get(str(c), "#999999") for c in sub["palm_coein"]],
            alpha=0.62,
            label="样本数",
        )
        ax_b2 = ax_b.twinx()
        ax_b2.plot(
            x,
            sub["diag_score_mean"],
            color="#1F6A8A",
            marker="o",
            linewidth=2.0,
            label="诊断质量",
        )
        # 样本柱与均值折线同时标注，便于审稿时快速读取
        for bar, n_val in zip(bars_b, pd.to_numeric(sub["sample_cases"], errors="coerce").to_numpy(dtype=float)):
            if not np.isfinite(n_val):
                continue
            ax_b.text(
                bar.get_x() + bar.get_width() / 2.0,
                n_val + max(1.0, 0.02 * float(np.nanmax(sub["sample_cases"]))),
                f"{int(round(n_val))}",
                ha="center",
                va="bottom",
                fontsize=8.2,
                color="#334155",
            )
        for xi, mean_val in zip(x, pd.to_numeric(sub["diag_score_mean"], errors="coerce").to_numpy(dtype=float)):
            if not np.isfinite(mean_val):
                continue
            ax_b2.text(
                float(xi),
                min(0.995, float(mean_val) + 0.025),
                f"{float(mean_val):.2f}",
                ha="center",
                va="bottom",
                fontsize=8.4,
                color="#1F6A8A",
            )
        ax_b.set_xticks(x)
        ax_b.set_xticklabels([str(v) for v in sub["palm_coein"]], rotation=28, ha="right", fontsize=8.5)
        ax_b.set_ylabel("病例数")
        ax_b2.set_ylim(0.0, 1.0)
        ax_b2.set_ylabel("诊断质量", color="#1F6A8A")
        ax_b2.tick_params(axis="y", colors="#1F6A8A")
        ax_b.set_title("B. PALM 九分类鲁棒性")
        ax_b.grid(alpha=0.2, axis="y")
        h1, l1 = ax_b.get_legend_handles_labels()
        h2, l2 = ax_b2.get_legend_handles_labels()
        ax_b.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=8, frameon=True)
        _set_full_axis_border(ax_b2)

    stage2_order = ["D1_Loop", "D2_Check_Merged"]
    stage2_label_map = {
        "D1_Loop": "门诊检查",
        "D2_Check_Merged": "住院检查",
    }
    x_check = np.arange(len(stage2_order))
    check_model = (
        check_score_stage2.groupby(["stage", "model_short"], as_index=False)["check_score"]
        .mean()
        .sort_values(["stage", "model_short"], kind="mergesort")
    )
    check_stage = check_model.groupby("stage", as_index=False)["check_score"].agg(["mean", "std"]).reset_index()
    check_map = {str(r["stage"]): float(r["mean"]) for _, r in check_stage.iterrows()}
    check_std_map = {str(r["stage"]): float(r["std"]) if pd.notna(r["std"]) else 0.0 for _, r in check_stage.iterrows()}
    y_check = np.array([check_map.get(s, np.nan) for s in stage2_order], dtype=float)
    y_check_std = np.array([check_std_map.get(s, 0.0) for s in stage2_order], dtype=float)
    ineff_model = (
        ineff_stage2.groupby(["stage", "model_short"], as_index=False)["ineff_rate"]
        .mean()
        .sort_values(["stage", "model_short"], kind="mergesort")
    )
    ineff_stage = ineff_model.groupby("stage", as_index=False)["ineff_rate"].agg(["mean", "std"]).reset_index()
    ineff_map = {str(r["stage"]): float(r["mean"]) for _, r in ineff_stage.iterrows()}
    ineff_std_map = {str(r["stage"]): float(r["std"]) if pd.notna(r["std"]) else 0.0 for _, r in ineff_stage.iterrows()}
    y_ineff = np.array([ineff_map.get(s, np.nan) for s in stage2_order], dtype=float)
    y_ineff_std = np.array([ineff_std_map.get(s, 0.0) for s in stage2_order], dtype=float)

    width_pair = 0.34
    bars_check = ax_c.bar(
        x_check - width_pair / 2.0,
        y_check,
        width=width_pair,
        yerr=y_check_std,
        color="#9CC0DF",
        edgecolor="#1f77b4",
        linewidth=1.2,
        alpha=0.88,
        capsize=4,
        label="检查匹配率均值",
        zorder=2,
    )
    ax_c2 = ax_c.twinx()
    bars_ineff = ax_c2.bar(
        x_check + width_pair / 2.0,
        y_ineff,
        width=width_pair,
        yerr=y_ineff_std,
        color="#F3B47F",
        edgecolor="#E17A24",
        linewidth=1.2,
        alpha=0.88,
        capsize=4,
        label="无效循环率均值",
        zorder=2.2,
    )
    # C 图恢复模型散点：左轴=检查匹配率，右轴=无效循环率（保持同一模型编码）
    for m_idx, model in enumerate(MODEL_ORDER):
        jitter = (m_idx - (len(MODEL_ORDER) - 1) / 2.0) * 0.035
        sub_check_m = check_model[check_model["model_short"] == model]
        if not sub_check_m.empty:
            c_map = {str(r["stage"]): float(r["check_score"]) for _, r in sub_check_m.iterrows()}
            c_vals = [c_map.get(s, np.nan) for s in stage2_order]
            ax_c.scatter(
                x_check - width_pair / 2.0 + jitter,
                c_vals,
                s=42,
                marker=MODEL_MARKER.get(model, "o"),
                color=MODEL_COLOR.get(model, "#666666"),
                edgecolors="white",
                linewidths=0.6,
                alpha=0.9,
                zorder=3.6,
            )
        sub_ineff_m = ineff_model[ineff_model["model_short"] == model]
        if not sub_ineff_m.empty:
            i_map = {str(r["stage"]): float(r["ineff_rate"]) for _, r in sub_ineff_m.iterrows()}
            i_vals = [i_map.get(s, np.nan) for s in stage2_order]
            ax_c2.scatter(
                x_check + width_pair / 2.0 + jitter,
                i_vals,
                s=42,
                marker=MODEL_MARKER.get(model, "o"),
                facecolors="none",
                edgecolors=MODEL_COLOR.get(model, "#666666"),
                linewidths=1.0,
                alpha=0.95,
                zorder=3.7,
            )
    # 柱顶均值标签
    for bar, val in zip(bars_check, y_check):
        if not np.isfinite(val):
            continue
        ax_c.text(
            bar.get_x() + bar.get_width() / 2.0,
            min(0.995, float(val) + 0.03),
            f"{float(val):.2f}",
            ha="center",
            va="bottom",
            fontsize=8.4,
            color="#1f77b4",
            zorder=4.0,
        )
    for bar, val in zip(bars_ineff, y_ineff):
        if not np.isfinite(val):
            continue
        ax_c2.text(
            bar.get_x() + bar.get_width() / 2.0,
            min(0.995, float(val) + 0.03),
            f"{float(val):.2f}",
            ha="center",
            va="bottom",
            fontsize=8.4,
            color="#E17A24",
            zorder=4.0,
        )

    ax_c.set_xticks(x_check)
    ax_c.set_xticklabels([stage2_label_map.get(s, s) for s in stage2_order], fontsize=12)
    ax_c.set_title("C. 检查匹配率与无效循环率")
    ax_c.set_ylabel("检查匹配率")
    ax_c.set_ylim(0.0, 1.0)
    ax_c2.set_ylabel("无效循环率", color="#E17A24")
    ax_c2.set_ylim(0.0, 1.0)
    ax_c2.tick_params(axis="y", colors="#E17A24")
    ax_c2.yaxis.label.set_color("#E17A24")
    ax_c.grid(alpha=0.22, axis="y")
    h_c1, l_c1 = ax_c.get_legend_handles_labels()
    h_c2, l_c2 = ax_c2.get_legend_handles_labels()
    ax_c.legend(h_c1 + h_c2, l_c1 + l_c2, loc="upper right", fontsize=8.5, frameon=True)
    _set_full_axis_border(ax_c2)

    _plot_stage_quality_bar(
        ax=ax_d,
        detail=plan.rename(columns={"value": "score"}),
        stage_order=["D2_Decision", "D3_Decision", "D4_Plan"],
        stage_label_map={
            "D2_Decision": "术前方案",
            "D3_Decision": "术后方案",
            "D4_Plan": "随访康复",
        },
        title="D. 方案质量",
        y_label="方案质量得分",
        bar_color="#9FD1A6",
        ylim=plan_ylim,
    )
    model_handles = _build_model_legend_handles(MODEL_ORDER, marker_size=7.2)
    fig.legend(
        model_handles,
        [h.get_label() for h in model_handles],
        loc="lower center",
        bbox_to_anchor=(0.08, 0.49, 0.84, 0.08),
        mode="expand",
        ncol=max(1, len(model_handles)),
        fontsize=8.5,
        frameon=True,
        borderaxespad=0.25,
    )

    _set_full_axis_border(ax_a)
    _set_full_axis_border(ax_b)
    _set_full_axis_border(ax_c)
    _set_full_axis_border(ax_d)

    fig.suptitle("G2 结果性指标", fontsize=16, y=1.01)
    fig.text(
        0.5,
        0.01,
        "检查口径一致：检查匹配率=匹配数/请求数；无效循环率=无效轮次/执行轮次。",
        ha="center",
        va="bottom",
        fontsize=9,
        color="#444444",
    )
    sub_figs = _save_subfigures(
        fig,
        group,
        {
            "G2A_diagnostic_quality_v2": ax_a,
            "G2B_diag_robustness_final_palm_v2": (ax_b, ax_b2),
            "G2C_check_efficiency_merged_v3": (ax_c, ax_c2),
            "G2D_plan_alignment_semantic_v1": ax_d,
        },
    )
    _save_fig(out_img)

    round_stage_full = ["OP_R1", "OP_R2", "OP_R3", "IP_R1", "IP_R2", "IP_R3"]
    stage_present = set(check_score_round["stage"].astype(str).tolist()) | set(ineff_round["stage"].astype(str).tolist())
    round_stage_order = [s for s in round_stage_full if s in stage_present]
    if not round_stage_order:
        round_stage_order = ["OP_R1", "IP_R1"]
    round_stage_label_map = {
        "OP_R1": "门诊第1轮",
        "OP_R2": "门诊第2轮",
        "OP_R3": "门诊第3轮",
        "IP_R1": "住院第1轮",
        "IP_R2": "住院第2轮",
        "IP_R3": "住院第3轮",
    }
    fig_r, ax_r = plt.subplots(figsize=(14.8, 5.8))
    _plot_band_scatter(
        ax=ax_r,
        detail=check_score_round,
        value_col="check_score",
        stage_order=round_stage_order,
        stage_label_map=round_stage_label_map,
        title="按实际执行轮次展示门诊/住院检查匹配率",
        y_label="检查匹配率",
        ylim=check_round_ylim,
        mean_color="#1f77b4",
    )
    ax_r2 = ax_r.twinx()
    _plot_band_scatter(
        ax=ax_r2,
        detail=ineff_round.rename(columns={"ineff_rate": "score"}),
        value_col="score",
        stage_order=round_stage_order,
        stage_label_map=round_stage_label_map,
        title="",
        y_label="无效循环率",
        ylim=ineff_round_ylim,
        mean_color="#F28E2B",
    )
    ax_r2.spines["right"].set_visible(True)
    ax_r2.tick_params(axis="y", colors="#F28E2B")
    ax_r2.yaxis.label.set_color("#F28E2B")
    ax_r.tick_params(axis="y", colors="#1f77b4")
    ax_r.yaxis.label.set_color("#1f77b4")
    lg2 = ax_r2.get_legend()
    if lg2:
        lg2.remove()
    _set_full_axis_border(ax_r)
    _set_full_axis_border(ax_r2)
    fig_r.text(0.5, 0.01, "", ha="center", va="bottom", fontsize=8.5, color="#444444")
    _save_fig(out_check_rounds)

    fig_bm, ax_bm = plt.subplots(figsize=(8.8, 5.2))
    bm_color = {"良性": "#6FA8DC", "恶性": "#2F6FA8", "非肿瘤": "#A6BBD1"}
    stage_order_bm = ["初始诊断", "修正诊断", "最终诊断"]
    bm_order = ["良性", "恶性", "非肿瘤"]
    if diag_bm_stage.empty:
        ax_bm.text(0.5, 0.5, "无良恶性分层数据", ha="center", va="center")
        ax_bm.set_title("B. 诊断鲁棒性")
    else:
        x = np.arange(len(stage_order_bm))
        width = 0.22
        for idx, bm in enumerate(bm_order):
            sub = diag_bm_stage[diag_bm_stage["final_benign_malignant"] == bm]
            val_map = {str(r["stage_semantic"]): float(r["diag_score_mean"]) for _, r in sub.iterrows()}
            yv = [val_map.get(s, np.nan) for s in stage_order_bm]
            ax_bm.bar(
                x + (idx - 1) * width,
                yv,
                width=width,
                color=bm_color.get(bm, "#A6BBD1"),
                alpha=0.85,
                label=bm,
            )
        ax_bm.set_xticks(x)
        ax_bm.set_xticklabels(stage_order_bm)
        ax_bm.set_ylim(0.0, 1.0)
        ax_bm.set_ylabel("诊断质量")
        ax_bm.set_title("B. 诊断鲁棒性")
        ax_bm.legend(loc="upper right", fontsize=8, frameon=True)
        ax_bm.grid(alpha=0.22, axis="y")
    _set_full_axis_border(ax_bm)
    _save_fig(out_bm_stage)

    fig_ab, ax_ab = plt.subplots(figsize=(12.2, 5.4))
    stage_order_bm = ["初始诊断", "修正诊断", "最终诊断"]
    stage_map_diag = {"D1_Decision": "初始诊断", "D2_Decision": "修正诊断", "D3_Decision": "最终诊断"}
    diag_stage_model = (
        diag.assign(stage_semantic=diag["stage"].map(stage_map_diag))
        .dropna(subset=["stage_semantic"])
        .groupby(["stage_semantic", "model_short"], as_index=False)["value"]
        .mean()
    )
    diag_stage_stats = (
        diag_stage_model.groupby("stage_semantic", as_index=False)["value"].agg(["mean", "std"]).reset_index()
    )
    diag_stage_mean = (
        diag.assign(stage_semantic=diag["stage"].map(stage_map_diag))
        .dropna(subset=["stage_semantic"])
        .groupby("stage_semantic", as_index=False)["value"]
        .mean()
    )
    diag_stage_map = {str(r["stage_semantic"]): float(r["value"]) for _, r in diag_stage_mean.iterrows()}
    diag_stage_std_map = {
        str(r["stage_semantic"]): (float(r["std"]) if pd.notna(r["std"]) else 0.0) for _, r in diag_stage_stats.iterrows()
    }
    x_ab = np.arange(len(stage_order_bm), dtype=float)
    y_diag_ab = np.array([diag_stage_map.get(s, np.nan) for s in stage_order_bm], dtype=float)
    y_diag_ab_std = np.array([diag_stage_std_map.get(s, 0.0) for s in stage_order_bm], dtype=float)
    band_low = y_diag_ab - y_diag_ab_std
    band_up = y_diag_ab + y_diag_ab_std
    ax_ab.fill_between(
        x_ab,
        band_low,
        band_up,
        color="#F6B48A",
        alpha=0.34,
        label="A 条带（±SD）",
        zorder=3.2,
    )
    ax_ab.plot(
        x_ab,
        y_diag_ab,
        color="#D16A39",
        linewidth=2.6,
        marker="o",
        markersize=6.6,
        label="A 诊断质量均值",
        zorder=3.5,
    )
    # A 通道补充各模型分点（与独立 A 子图一致）
    for model in MODEL_ORDER:
        sub_m = diag_stage_model[diag_stage_model["model_short"] == model]
        if sub_m.empty:
            continue
        m_map = {str(r["stage_semantic"]): float(r["value"]) for _, r in sub_m.iterrows()}
        y_m = np.array([m_map.get(s, np.nan) for s in stage_order_bm], dtype=float)
        valid = np.isfinite(y_m)
        if not valid.any():
            continue
        ax_ab.scatter(
            x_ab[valid],
            y_m[valid],
            s=78,
            marker=MODEL_MARKER.get(model, "o"),
            color=MODEL_COLOR.get(model, "#666666"),
            edgecolors="white",
            linewidths=0.8,
            alpha=0.95,
            label=f"A-{model}",
            zorder=3.8,
        )
    ax_ab.set_ylabel("诊断质量", color="#D16A39")
    ax_ab.tick_params(axis="y", colors="#D16A39")
    ax_ab.yaxis.label.set_color("#D16A39")
    ax_ab.set_xticks(x_ab)
    ax_ab.set_xticklabels(stage_order_bm, fontsize=11)
    ax_ab.set_ylim(diag_ylim[0], diag_ylim[1])
    tick_step = 0.1 if (diag_ylim[1] - diag_ylim[0]) <= 0.6 else 0.2
    ax_ab.yaxis.set_major_locator(MultipleLocator(tick_step))
    ax_ab.grid(alpha=0.2, axis="y")

    ax_ab_r = ax_ab.twinx()
    # 让 A 轴图层（条带/折线/散点）显示在 B 柱状图上方
    ax_ab.set_zorder(3.0)
    ax_ab_r.set_zorder(2.0)
    ax_ab.patch.set_alpha(0.0)
    if not diag_bm_stage.empty:
        width_ab = 0.2
        bm_color = {"良性": "#84AED4", "恶性": "#4D7EA8", "非肿瘤": "#B7C7D8"}
        bm_order = ["良性", "恶性", "非肿瘤"]
        for idx, bm in enumerate(bm_order):
            sub = diag_bm_stage[diag_bm_stage["final_benign_malignant"] == bm]
            val_map = {str(r["stage_semantic"]): float(r["diag_score_mean"]) for _, r in sub.iterrows()}
            yv = [val_map.get(s, np.nan) for s in stage_order_bm]
            ax_ab_r.bar(
                x_ab + (idx - 1) * width_ab,
                yv,
                width=width_ab,
                color=bm_color.get(bm, "#A6BBD1"),
                alpha=0.72,
                label=f"B-{bm}",
                zorder=2.2,
            )
    ax_ab_r.set_ylim(0.0, 1.0)
    ax_ab_r.set_ylabel("诊断鲁棒性（良恶性分层, 0-1）", color="#3D4E66")
    ax_ab_r.tick_params(axis="y", colors="#3D4E66")
    ax_ab_r.yaxis.label.set_color("#3D4E66")
    ax_ab.set_title("A+B. 诊断质量与鲁棒性")
    h_l, l_l = ax_ab.get_legend_handles_labels()
    h_r, l_r = ax_ab_r.get_legend_handles_labels()
    if h_l or h_r:
        fig_ab.legend(
            h_l + h_r,
            l_l + l_r,
            loc="lower center",
            bbox_to_anchor=(0.06, 0.02, 0.88, 0.12),
            mode="expand",
            ncol=5,
            fontsize=7.8,
            frameon=True,
            borderaxespad=0.25,
        )
        fig_ab.subplots_adjust(bottom=0.26, top=0.95, left=0.08, right=0.92)
    _set_full_axis_border(ax_ab)
    _set_full_axis_border(ax_ab_r)
    _save_fig(out_ab_dual, apply_tight=False)

    fig_alt = plt.figure(figsize=(18.2, 10.4), constrained_layout=True)
    gs_alt = fig_alt.add_gridspec(2, 2, hspace=0.08, wspace=0.07, height_ratios=[1.05, 1.0])
    bx_ab = fig_alt.add_subplot(gs_alt[0, :])
    bx_c = fig_alt.add_subplot(gs_alt[1, 0])
    bx_d = fig_alt.add_subplot(gs_alt[1, 1])
    _draw_image_panel(bx_ab, out_ab_dual, "")
    _draw_image_panel(bx_c, sub_figs["G2C_check_efficiency_merged_v3"], "")
    _draw_image_panel(bx_d, sub_figs["G2D_plan_alignment_semantic_v1"], "")
    fig_alt.suptitle("G2 结果性指标 Fig4备选方案B", fontsize=16, y=1.01)
    _save_fig(out_img_alt_bm)

    calc_check_stage2_case = (
        check_score_stage2.merge(
            ineff_stage2[["center", "model", "case_id", "stage", "ineff_rate"]],
            on=["center", "model", "case_id", "stage"],
            how="outer",
        )
        .sort_values(["stage", "model_short", "center", "case_id"], kind="mergesort")
        .reset_index(drop=True)
    )
    calc_check_stage2_stats = (
        calc_check_stage2_case.groupby("stage", as_index=False)
        .agg(
            check_quality_mean=("check_score", "mean"),
            check_quality_std=("check_score", "std"),
            ineff_rate_mean=("ineff_rate", "mean"),
            ineff_rate_std=("ineff_rate", "std"),
            sample_n=("case_id", "count"),
        )
        .sort_values("stage", kind="mergesort")
        .reset_index(drop=True)
    )
    if not calc_check_stage2_stats.empty:
        rr = np.arange(2, len(calc_check_stage2_stats) + 2)
        calc_check_stage2_stats["formula_check_quality_mean"] = [
            f"=AVERAGEIFS(c_g2_check_case!$G:$G,c_g2_check_case!$F:$F,A{r})" for r in rr
        ]
        calc_check_stage2_stats["formula_ineff_rate_mean"] = [
            f"=AVERAGEIFS(c_g2_check_case!$H:$H,c_g2_check_case!$F:$F,A{r})" for r in rr
        ]
        calc_check_stage2_stats["说明"] = "汇总均值直接由 c_g2_check_case 按 stage 公式回算"
    table_g2_model_stage = (
        pd.concat(
            [
                diag.assign(metric="诊断正确性", value=diag["value"], stage_key=diag["stage"])[
                    ["model_short", "stage_key", "metric", "value"]
                ],
                plan.assign(metric="方案正确性", value=plan["value"], stage_key=plan["stage"])[
                    ["model_short", "stage_key", "metric", "value"]
                ],
                check_score_stage2.assign(metric="检查质量", value=check_score_stage2["check_score"], stage_key=check_score_stage2["stage"])[
                    ["model_short", "stage_key", "metric", "value"]
                ],
                ineff_stage2.assign(metric="无效循环率", value=ineff_stage2["ineff_rate"], stage_key=ineff_stage2["stage"])[
                    ["model_short", "stage_key", "metric", "value"]
                ],
            ],
            ignore_index=True,
        )
        .groupby(["model_short", "stage_key", "metric"], as_index=False)["value"]
        .mean()
        .sort_values(["metric", "stage_key", "model_short"], kind="mergesort")
        .reset_index(drop=True)
    )
    s_g2_diag_model = (
        diag.groupby(["stage", "model_short"], as_index=False)["value"]
        .mean()
        .sort_values(["stage", "model_short"], kind="mergesort")
        .reset_index(drop=True)
    )
    if not s_g2_diag_model.empty:
        rr = np.arange(2, len(s_g2_diag_model) + 2)
        s_g2_diag_model["formula_value"] = [
            f"=AVERAGEIFS(d_g2_diag!$G:$G,d_g2_diag!$F:$F,B{r},d_g2_diag!$E:$E,C{r})" for r in rr
        ]

    s_g2_palm_final = diag_palm_final.copy()
    if not s_g2_palm_final.empty:
        rr = np.arange(2, len(s_g2_palm_final) + 2)
        s_g2_palm_final["formula_diag_score_mean"] = [
            f"=AVERAGEIFS(d_g2_palm_final!$G:$G,d_g2_palm_final!$Y:$Y,B{r})" for r in rr
        ]
        s_g2_palm_final["formula_model_case_n"] = [
            f"=COUNTIFS(d_g2_palm_final!$Y:$Y,B{r},d_g2_palm_final!$E:$E,\"<>\")" for r in rr
        ]
        s_g2_palm_final["说明"] = "diag_score_mean/model_case_n 可由 d_g2_palm_final 回算；sample_cases 为按病例去重统计"

    s_g2_check_model = (
        check_score_stage2.groupby(["stage", "model_short"], as_index=False)["check_score"]
        .mean()
        .sort_values(["stage", "model_short"], kind="mergesort")
        .reset_index(drop=True)
    )
    if not s_g2_check_model.empty:
        rr = np.arange(2, len(s_g2_check_model) + 2)
        s_g2_check_model["formula_check_score"] = [
            f"=AVERAGEIFS(d_g2_check2!$F:$F,d_g2_check2!$G:$G,B{r},d_g2_check2!$E:$E,C{r})" for r in rr
        ]

    s_g2_ineff_model = (
        ineff_stage2.groupby(["stage", "model_short"], as_index=False)["ineff_rate"]
        .mean()
        .sort_values(["stage", "model_short"], kind="mergesort")
        .reset_index(drop=True)
    )
    if not s_g2_ineff_model.empty:
        rr = np.arange(2, len(s_g2_ineff_model) + 2)
        s_g2_ineff_model["formula_ineff_rate"] = [
            f"=AVERAGEIFS(d_g2_ineff2!$F:$F,d_g2_ineff2!$G:$G,B{r},d_g2_ineff2!$E:$E,C{r})" for r in rr
        ]

    s_g2_plan_model = (
        plan.groupby(["stage", "model_short"], as_index=False)["value"]
        .mean()
        .sort_values(["stage", "model_short"], kind="mergesort")
        .reset_index(drop=True)
    )
    if not s_g2_plan_model.empty:
        rr = np.arange(2, len(s_g2_plan_model) + 2)
        s_g2_plan_model["formula_value"] = [
            f"=AVERAGEIFS(d_g2_plan!$G:$G,d_g2_plan!$F:$F,B{r},d_g2_plan!$E:$E,C{r})" for r in rr
        ]

    if not table_g2_model_stage.empty:
        rr = np.arange(2, len(table_g2_model_stage) + 2)
        table_g2_model_stage["formula_value"] = [
            (
                f"=IF(D{r}=\"诊断正确性\",AVERAGEIFS(s_g2_diag_model!$D:$D,s_g2_diag_model!$C:$C,B{r},s_g2_diag_model!$B:$B,C{r}),"
                f"IF(D{r}=\"方案正确性\",AVERAGEIFS(s_g2_plan_model!$D:$D,s_g2_plan_model!$C:$C,B{r},s_g2_plan_model!$B:$B,C{r}),"
                f"IF(D{r}=\"检查质量\",AVERAGEIFS(s_g2_check_model!$D:$D,s_g2_check_model!$C:$C,B{r},s_g2_check_model!$B:$B,C{r}),"
                f"AVERAGEIFS(s_g2_ineff_model!$D:$D,s_g2_ineff_model!$C:$C,B{r},s_g2_ineff_model!$B:$B,C{r}))))"
            )
            for r in rr
        ]
    source_path = _write_source_workbook(
        group=group,
        stem="G2_outcome_metrics_v6",
        sheets={
            "d_g2_diag": diag,
            "d_g2_palm_final": diag_palm_detail,
            "d_g2_check2": check_score_stage2,
            "d_g2_ineff2": ineff_stage2,
            "d_g2_plan": plan,
            "c_g2_check_case": calc_check_stage2_case,
            "c_g2_check_stats": calc_check_stage2_stats,
            "s_g2_diag_model": s_g2_diag_model,
            "s_g2_palm_final": s_g2_palm_final,
            "s_g2_check_model": s_g2_check_model,
            "s_g2_ineff_model": s_g2_ineff_model,
            "s_g2_plan_model": s_g2_plan_model,
            "table_g2_model": table_g2_model_stage,
        },
        meta={
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "figure_main": str(out_img.relative_to(ROOT)),
            "rule_diag_label": "D1/D2/D3 -> 初始诊断/修正诊断/最终诊断",
            "rule_plan_label": "D2/D3/D4 -> 术前治疗计划/术后治疗计划/随访与康复计划",
            "rule_check_main": "主图C采用门诊检查 vs 住院检查两点口径，左轴为检查匹配率、右轴为无效循环率",
            "formula_check_score": "检查匹配率 = matched_total / requested_total",
            "formula_ineff_rate": "无效循环率 = ineff_rounds_by_zero / executed_rounds",
            "formula_g2c_errorbar": "误差条为模型间标准差（按模型聚合后的std）",
            "rule_d1": "D1 anomaly excluded",
            "rule_gate3_d4": "Gate3 fail excluded from D4 where applicable",
            "source_diag_d1": "D1_Outpatient_Decision.Gate1判官_原始JSON_诊断匹配_评分",
            "source_diag_d2": "D2_Admission_Decision.Gate2判官_原始JSON_修正诊断匹配_评分",
            "source_diag_d3": "D3_Surgery_Decision.判官_原始JSON_诊断匹配评估_评分",
            "source_plan_d2": "D2_Admission_Decision.Gate2判官_原始JSON_手术方案匹配_评分",
            "source_plan_d3": "D3_Surgery_Decision.判官_原始JSON_治疗方案匹配评估_评分",
            "source_plan_d4": "D4_Rehab_Plan.mean(判官_原始JSON_康复计划评估_评分,判官_原始JSON_随访计划评估_评分)",
            "source_hint__d_g2_diag": "center_data/<中心>/judge agent/Evaluation_Summary_<model>_CN_Judge_Parsed.xlsx",
            "source_hint__d_g2_plan": "center_data/<中心>/judge agent/Evaluation_Summary_<model>_CN_Judge_Parsed.xlsx",
            "source_hint__d_g2_check2": "analysis_viz/data/raw/metrics_source_data.xlsx:metrics_by_case",
            "source_hint__d_g2_ineff2": "analysis_viz/data/raw/metrics_source_data.xlsx:metrics_by_case",
            "source_hint__c_g2_check_case": "d_g2_check2 与 d_g2_ineff2 按 center/model/case/stage 合并",
            "source_hint__table_g2_model": "三中心合并后按 model×stage×metric 汇总均值",
        },
    )
    _write_caption(
        group,
        [
            "# G2 组图图注",
            "",
            "- `G2_outcome_metrics_v6.png`：主图采用四面板布局。A 为“初始诊断/修正诊断/最终诊断”诊断质量柱图，B 为 PALM 九分类下最终诊断鲁棒性（样本柱+诊断质量折线），C 为门诊/住院两阶段“检查匹配率+无效循环率”双轴图，D 为“术前/术后/随访康复”方案质量柱图。",
            "- `G2C_check_efficiency_merged_v3.png`：门诊与住院两阶段同时展示检查匹配率均值与无效循环率均值（右轴），用于对照“匹配收益”与“循环代价”。",
            "- `G2C_check_efficiency_rounds_v1.png`（Fig4-B 版本①）：按每轮循环展示，门诊与住院均限制 1-3 轮；其中住院第1轮并入 D1 决策检查，作为最终采用的归并方式。",
            "- `G2D_plan_alignment_semantic_v1.png`：阶段语义固定为 `D2=术前治疗计划（含手术/放化疗等）`、`D3=术后治疗计划（结合病理/终诊）`、`D4=随访与康复计划（当前口径为随访与康复合并均值）`。",
            "- `G2AB_diag_quality_robustness_dualaxis_v1.png` 与 `G2_outcome_metrics_alt_bm_v3.png`：替代方案将 A 与 B 合并为共享 X 轴双 Y 轴同屏表达：左轴为诊断正确性折线，右轴为良恶性分层鲁棒性并列柱，满足“同阶段同画面”对照阅读需求。",
        ],
    )
    keep_fig = {out_img.name} | {p.name for p in sub_figs.values()}
    _archive_group_outputs(group=group, keep_fig_names=keep_fig, keep_source_names={source_path.name})
    return {
        "figure": out_img,
        "figure_alt_bm": out_img_alt_bm,
        "ab_dualaxis_panel": out_ab_dual,
        "check_rounds": out_check_rounds,
        "bm_panel": out_bm_stage,
        "source": source_path,
        **sub_figs,
    }

def _parse_error_tags(text: Any) -> list[str]:
    if text is None:
        return []
    raw = str(text).strip()
    if raw in {"", "[]", "nan", "None"}:
        return []
    try:
        arr = json.loads(raw)
        if isinstance(arr, list):
            return [str(x).strip().lower() for x in arr if str(x).strip() not in {"", "none", "nan"}]
    except Exception:
        pass
    return [raw.strip().lower()]


def build_g3_continuity(d2_rule_map: pd.DataFrame) -> dict[str, Path]:
    group = "G3_continuity"
    out_img = OUT_FIG_DIR / group / "G3_continuity_metrics_v4.png"
    out_img_tagstack = OUT_FIG_DIR / group / "G3_continuity_events_tagstack_v1.png"
    out_img_event_long = OUT_FIG_DIR / group / "G3_continuity_events_long_v1.png"
    out_table_stage = OUT_FIG_DIR / group / "G3_continuity_component_table_stage_v1.png"
    out_table_model = OUT_FIG_DIR / group / "G3_continuity_component_table_model_stage_v1.png"
    out_word = OUT_FIG_DIR / group / "G3_continuity_appendix_tables_v1.docx"
    out_logic_md = OUT_FIG_DIR / group / "G3_continuity_df_vs_score_logic_note_v1.md"
    stage_case_sets = _load_stage_case_sets_from_sankey_source(d2_rule_map)

    memory_raw = pd.read_excel(RAW_DIR / "llm_memory_gemini-2.5-pro__gala_api.xlsx", sheet_name=0)
    fact_raw = pd.read_excel(RAW_DIR / "llm_consistency_gemini-2.5-pro__gala_api.xlsx", sheet_name=0)
    cross_raw = pd.read_excel(RAW_DIR / "llm_consistency_gemini-2.5-pro__gala_api.xlsx", sheet_name=2)
    reasoning_raw = pd.read_excel(RAW_DIR / "llm_reasoning_gemini-2.5-pro__gala_api.xlsx", sheet_name=1)

    memory = memory_raw.rename(
        columns={
            "中心": "center",
            "被评测模型": "model",
            "病例ID": "case_id",
            "阶段": "stage",
            "历史信息继承度(0-1)": "inheritance_0_1",
            "历史信息利用率(0-1)": "utilization_0_1",
            "关键信息丢失率(0-1)": "key_info_loss_rate_0_1",
            "错误标签(JSON)": "error_tags_json",
        }
    ).copy()
    consistency_fact = fact_raw.rename(
        columns={
            "中心": "center",
            "被评测模型": "model",
            "病例ID": "case_id",
            "阶段": "stage",
            "一致性得分(0-1)": "consistency_score_0_1",
            "冲突条数": "conflict_count",
            "幻觉条数": "hallucination_count",
            "错误标签(JSON)": "error_tags_json",
        }
    ).copy()
    consistency = cross_raw.rename(
        columns={
            "中心": "center",
            "被评测模型": "model",
            "病例ID": "case_id",
            "阶段": "stage",
            "一致性得分(0-1)": "consistency_score_0_1",
            "错误标签(JSON)": "error_tags_json",
        }
    ).copy()
    reasoning = reasoning_raw.rename(
        columns={
            "中心": "center",
            "被评测模型": "model",
            "病例ID": "case_id",
            "阶段": "stage",
            "推理质量得分(0-1)": "reasoning_score_0_1",
            "错误标签(JSON)": "error_tags_json",
        }
    ).copy()

    for df in [memory, consistency, consistency_fact, reasoning]:
        df["model_short"] = df["model"].map(MODEL_SHORT).fillna(df["model"].astype(str))
        df["center"] = df["center"].astype(str)
        df["case_id"] = df["case_id"].astype(str)
        df["model"] = df["model"].astype(str)
        df["stage"] = df["stage"].astype(str)

    memory["stage4"] = memory["stage"].map({"D2_Admission_Decision": "D2", "D3_Surgery_Decision": "D3", "D4_Rehab_Plan": "D4"})
    memory = memory[memory["stage4"].isin(["D2", "D3", "D4"])].copy()
    consistency["stage4"] = consistency["stage"].map(_stage4_map)
    consistency = consistency[consistency["stage4"].isin(["D1", "D2", "D3", "D4"])].copy()
    consistency_fact["stage4"] = consistency_fact["stage"].map(_stage4_map)
    consistency_fact = consistency_fact[consistency_fact["stage4"].isin(["D1", "D2", "D3", "D4"])].copy()
    reasoning["stage_raw"] = reasoning["stage"].astype(str)
    reasoning["stage4"] = reasoning["stage_raw"].map(_stage4_map)
    reasoning = reasoning[reasoning["stage4"].isin(["D1", "D2", "D3", "D4"])].copy()

    memory = _attach_d2_manual_rules(memory, d2_rule_map)
    consistency = _attach_d2_manual_rules(consistency, d2_rule_map)
    consistency_fact = _attach_d2_manual_rules(consistency_fact, d2_rule_map)
    reasoning = _attach_d2_manual_rules(reasoning, d2_rule_map)

    memory = memory[~(memory["d2_force_stop"] & memory["stage4"].isin(["D3", "D4"]))].copy()
    consistency = consistency[~(consistency["d2_force_stop"] & consistency["stage4"].isin(["D3", "D4"]))].copy()
    consistency_fact = consistency_fact[~(consistency_fact["d2_force_stop"] & consistency_fact["stage4"].isin(["D3", "D4"]))].copy()
    reasoning = reasoning[~(reasoning["d2_force_stop"] & reasoning["stage4"].isin(["D3", "D4"]))].copy()
    memory = _filter_stage_case_eligibility(memory, "stage4", stage_case_sets)
    consistency = _filter_stage_case_eligibility(consistency, "stage4", stage_case_sets)
    consistency_fact = _filter_stage_case_eligibility(consistency_fact, "stage4", stage_case_sets)
    reasoning = _filter_stage_case_eligibility(reasoning, "stage4", stage_case_sets)
    memory["inheritance_0_1"] = pd.to_numeric(memory["inheritance_0_1"], errors="coerce")
    memory["utilization_0_1"] = pd.to_numeric(memory["utilization_0_1"], errors="coerce")
    memory["key_info_loss_rate_0_1"] = pd.to_numeric(memory["key_info_loss_rate_0_1"], errors="coerce")
    memory["memory_composite_0_1"] = (
        memory["inheritance_0_1"].fillna(0.0)
        + memory["utilization_0_1"].fillna(0.0)
        + (1.0 - memory["key_info_loss_rate_0_1"].fillna(0.0))
    ) / 3.0
    memory["tags"] = memory["error_tags_json"].apply(_parse_error_tags)
    memory["tags_text"] = memory["tags"].apply(lambda arr: "|".join(sorted({str(x).strip().lower() for x in arr if str(x).strip()})))

    def _tag_any(arr: list[str], targets: set[str]) -> int:
        low = {str(x).strip().lower() for x in arr}
        return int(any(t in low for t in targets))

    memory["tag_missing_prior_info"] = memory["tags"].apply(lambda arr: _tag_any(arr, {"missing_prior_info"}))
    memory["tag_unused_key_info"] = memory["tags"].apply(lambda arr: _tag_any(arr, {"unused_key_info"}))
    # other(literal)：仅统计标签中显式出现 "other"
    memory["tag_other_literal"] = memory["tags"].apply(lambda arr: _tag_any(arr, {"other"}))
    # other(bucket)：除 missing_prior_info / unused_key_info 外的任意事件收纳
    memory["tag_other_bucket"] = memory["tags"].apply(
        lambda arr: int(any(t not in {"missing_prior_info", "unused_key_info"} for t in {str(x).strip().lower() for x in arr}))
    )
    # 用户指定口径：tags 为空=未发生，非空=发生
    memory["inheritance_issue_event"] = memory["tags"].apply(lambda arr: int(len(arr) > 0))

    consistency["consistency_score_0_1"] = pd.to_numeric(consistency["consistency_score_0_1"], errors="coerce")
    consistency["tags"] = consistency["error_tags_json"].apply(_parse_error_tags)
    consistency["tags_text"] = consistency["tags"].apply(lambda arr: "|".join(sorted({str(x).strip().lower() for x in arr if str(x).strip()})))
    consistency["cross_tag_stage_conflict"] = consistency["tags"].apply(lambda arr: _tag_any(arr, {"stage_conflict"}))
    consistency["cross_tag_fact_shift"] = consistency["tags"].apply(lambda arr: _tag_any(arr, {"fact_shift"}))
    consistency["cross_tag_other"] = consistency["tags"].apply(lambda arr: _tag_any(arr, {"other"}))
    consistency["cross_event_any"] = (
        (consistency["cross_tag_stage_conflict"] > 0)
        | (consistency["cross_tag_fact_shift"] > 0)
        | (consistency["cross_tag_other"] > 0)
    ).astype(int)

    consistency_fact["conflict_count"] = pd.to_numeric(consistency_fact["conflict_count"], errors="coerce").fillna(0.0)
    consistency_fact["hallucination_count"] = pd.to_numeric(consistency_fact["hallucination_count"], errors="coerce").fillna(0.0)
    consistency_fact["consistency_score_0_1"] = pd.to_numeric(consistency_fact["consistency_score_0_1"], errors="coerce")
    consistency_fact["tags"] = consistency_fact["error_tags_json"].apply(_parse_error_tags)
    consistency_fact["tags_text"] = consistency_fact["tags"].apply(lambda arr: "|".join(sorted({str(x).strip().lower() for x in arr if str(x).strip()})))
    consistency_fact["fact_tag_contradiction"] = consistency_fact["tags"].apply(lambda arr: _tag_any(arr, {"contradiction"}))
    consistency_fact["fact_tag_hallucination"] = consistency_fact["tags"].apply(lambda arr: _tag_any(arr, {"hallucination"}))
    consistency_fact["fact_tag_missing"] = consistency_fact["tags"].apply(lambda arr: _tag_any(arr, {"missing"}))
    consistency_fact["fact_tag_other"] = consistency_fact["tags"].apply(lambda arr: _tag_any(arr, {"unsupported_detail", "other"}))
    consistency_fact["fact_event_any"] = (
        (consistency_fact["fact_tag_contradiction"] > 0)
        | (consistency_fact["fact_tag_hallucination"] > 0)
        | (consistency_fact["fact_tag_other"] > 0)
    ).astype(int)

    consistency_cross_used = consistency.copy()

    cons_case = (
        consistency_fact[
            [
                "center",
                "model",
                "case_id",
                "model_short",
                "stage4",
                "consistency_score_0_1",
                "fact_tag_contradiction",
                "fact_tag_hallucination",
                "fact_tag_other",
                "fact_event_any",
            ]
        ]
        .rename(columns={"consistency_score_0_1": "fact_score_0_1"})
        .merge(
            consistency[
                [
                    "center",
                    "model",
                    "case_id",
                    "stage4",
                    "consistency_score_0_1",
                    "cross_tag_stage_conflict",
                    "cross_tag_fact_shift",
                    "cross_tag_other",
                    "cross_event_any",
                ]
            ].rename(columns={"consistency_score_0_1": "cross_score_0_1"}),
            on=["center", "model", "case_id", "stage4"],
            how="outer",
        )
    )
    cons_case["model_short"] = cons_case["model"].map(MODEL_SHORT).fillna(cons_case["model"].astype(str))
    cons_case["consistency_score_0_1"] = cons_case[["fact_score_0_1", "cross_score_0_1"]].mean(axis=1, skipna=True)
    for c in [
        "fact_tag_contradiction",
        "fact_tag_hallucination",
        "fact_tag_other",
        "fact_event_any",
        "cross_tag_stage_conflict",
        "cross_tag_fact_shift",
        "cross_tag_other",
        "cross_event_any",
    ]:
        cons_case[c] = pd.to_numeric(cons_case[c], errors="coerce").fillna(0).astype(int)

    missing_key = (
        consistency_fact[["center", "model", "case_id", "stage4", "fact_tag_missing"]]
        .drop_duplicates(subset=["center", "model", "case_id", "stage4"], keep="last")
        .rename(columns={"fact_tag_missing": "memory_loss_event"})
    )
    memory = memory.merge(missing_key, on=["center", "model", "case_id", "stage4"], how="left")
    memory["memory_loss_event"] = pd.to_numeric(memory["memory_loss_event"], errors="coerce").fillna(0).astype(int)
    consistency = cons_case.copy()

    reasoning["reasoning_score_0_1"] = pd.to_numeric(reasoning["reasoning_score_0_1"], errors="coerce")
    reasoning["reasoning_score_1_5"] = reasoning["reasoning_score_0_1"] * 4.0 + 1.0
    reasoning["tags"] = reasoning["error_tags_json"].apply(_parse_error_tags)
    reasoning["tags_text"] = reasoning["tags"].apply(lambda arr: "|".join(sorted({str(x).strip().lower() for x in arr if str(x).strip()})))

    reasoning["event_missing_link"] = reasoning["tags"].apply(lambda arr: _tag_any(arr, {"missing_link"}))
    reasoning["event_over_integration"] = reasoning["tags"].apply(lambda arr: _tag_any(arr, {"over_integration"}))
    reasoning["event_narrative_bias"] = reasoning["tags"].apply(lambda arr: _tag_any(arr, {"narrative_bias"}))
    reasoning["event_logic_jump"] = reasoning["tags"].apply(lambda arr: _tag_any(arr, {"logic_jump"}))
    reasoning["event_other_tag"] = reasoning["tags"].apply(lambda arr: _tag_any(arr, {"other"}))
    # 总览图用 other(bucket)：除 missing_link / narrative_bias 外所有事件收纳
    reasoning["event_other_bucket"] = reasoning["tags"].apply(
        lambda arr: int(any(t not in {"missing_link", "narrative_bias"} for t in {str(x).strip().lower() for x in arr}))
    )

    def _half_avg(a: float, b: float) -> float:
        if np.isfinite(a) and np.isfinite(b):
            return float((a + b) / 2.0)
        if np.isfinite(a):
            return float(a)
        if np.isfinite(b):
            return float(b)
        return float("nan")

    # 推理质量 D1/D2 按 (loop均值 + decision值)/2 重算
    score_case = (
        reasoning.groupby(["center", "model", "case_id", "model_short", "stage_raw"], as_index=False)["reasoning_score_1_5"]
        .mean()
        .pivot_table(
            index=["center", "model", "case_id", "model_short"],
            columns="stage_raw",
            values="reasoning_score_1_5",
            aggfunc="mean",
        )
        .reset_index()
    )
    for c in [
        "D1_Outpatient_Loop",
        "D1_Outpatient_Decision",
        "D2_Admission_Loop",
        "D2_Admission_Decision",
        "D3_Surgery_Decision",
        "D4_Rehab_Plan",
    ]:
        if c not in score_case.columns:
            score_case[c] = np.nan
    score_case["D1"] = [_half_avg(a, b) for a, b in zip(score_case["D1_Outpatient_Loop"], score_case["D1_Outpatient_Decision"])]
    score_case["D2"] = [_half_avg(a, b) for a, b in zip(score_case["D2_Admission_Loop"], score_case["D2_Admission_Decision"])]
    score_case["D3"] = pd.to_numeric(score_case["D3_Surgery_Decision"], errors="coerce")
    score_case["D4"] = pd.to_numeric(score_case["D4_Rehab_Plan"], errors="coerce")
    reasoning_stage_score = (
        score_case.melt(
            id_vars=["center", "model", "case_id", "model_short"],
            value_vars=["D1", "D2", "D3", "D4"],
            var_name="stage",
            value_name="reasoning_score_1_5_adj",
        )
        .dropna(subset=["reasoning_score_1_5_adj"])
        .reset_index(drop=True)
    )

    # 推理负面事件概率：D1/D2按(loop概率 + decision概率)/2，D3/D4按该阶段概率
    def _event_prob_stage(event_col: str) -> dict[str, float]:
        out: dict[str, float] = {}
        loop_map = {"D1": "D1_Outpatient_Loop", "D2": "D2_Admission_Loop"}
        dec_map = {
            "D1": "D1_Outpatient_Decision",
            "D2": "D2_Admission_Decision",
            "D3": "D3_Surgery_Decision",
            "D4": "D4_Rehab_Plan",
        }
        for s in ["D1", "D2"]:
            loop_rate = pd.to_numeric(reasoning.loc[reasoning["stage_raw"] == loop_map[s], event_col], errors="coerce").mean()
            dec_rate = pd.to_numeric(reasoning.loc[reasoning["stage_raw"] == dec_map[s], event_col], errors="coerce").mean()
            out[s] = _half_avg(loop_rate, dec_rate)
        for s in ["D3", "D4"]:
            out[s] = float(pd.to_numeric(reasoning.loc[reasoning["stage_raw"] == dec_map[s], event_col], errors="coerce").mean())
        return out

    rea_missing = _event_prob_stage("event_missing_link")
    rea_narrative = _event_prob_stage("event_narrative_bias")
    rea_other = _event_prob_stage("event_other_bucket")
    rea_stage_case_n = reasoning_stage_score.groupby("stage")["case_id"].count().to_dict()
    rea_component_row_n = reasoning.groupby("stage4")["case_id"].count().to_dict()
    rea_prob = pd.DataFrame(
        {
            "stage": ["D1", "D2", "D3", "D4"],
            "missing_link_prob": [rea_missing.get(s, np.nan) for s in ["D1", "D2", "D3", "D4"]],
            "narrative_bias_prob": [rea_narrative.get(s, np.nan) for s in ["D1", "D2", "D3", "D4"]],
            "other_prob": [rea_other.get(s, np.nan) for s in ["D1", "D2", "D3", "D4"]],
            "stage_case_n": [int(rea_stage_case_n.get(s, 0)) for s in ["D1", "D2", "D3", "D4"]],
            "component_row_n": [int(rea_component_row_n.get(s, 0)) for s in ["D1", "D2", "D3", "D4"]],
        }
    )
    if not rea_prob.empty:
        rea_prob["formula_missing_link_prob"] = [
            "=0.5*AVERAGEIFS(c_rea_comp!$J:$J,c_rea_comp!$F:$F,\"D1_Outpatient_Loop\")+0.5*AVERAGEIFS(c_rea_comp!$J:$J,c_rea_comp!$F:$F,\"D1_Outpatient_Decision\")",
            "=0.5*AVERAGEIFS(c_rea_comp!$J:$J,c_rea_comp!$F:$F,\"D2_Admission_Loop\")+0.5*AVERAGEIFS(c_rea_comp!$J:$J,c_rea_comp!$F:$F,\"D2_Admission_Decision\")",
            "=AVERAGEIFS(c_rea_comp!$J:$J,c_rea_comp!$F:$F,\"D3_Surgery_Decision\")",
            "=AVERAGEIFS(c_rea_comp!$J:$J,c_rea_comp!$F:$F,\"D4_Rehab_Plan\")",
        ]
        rea_prob["formula_narrative_bias_prob"] = [
            "=0.5*AVERAGEIFS(c_rea_comp!$L:$L,c_rea_comp!$F:$F,\"D1_Outpatient_Loop\")+0.5*AVERAGEIFS(c_rea_comp!$L:$L,c_rea_comp!$F:$F,\"D1_Outpatient_Decision\")",
            "=0.5*AVERAGEIFS(c_rea_comp!$L:$L,c_rea_comp!$F:$F,\"D2_Admission_Loop\")+0.5*AVERAGEIFS(c_rea_comp!$L:$L,c_rea_comp!$F:$F,\"D2_Admission_Decision\")",
            "=AVERAGEIFS(c_rea_comp!$L:$L,c_rea_comp!$F:$F,\"D3_Surgery_Decision\")",
            "=AVERAGEIFS(c_rea_comp!$L:$L,c_rea_comp!$F:$F,\"D4_Rehab_Plan\")",
        ]
        rea_prob["formula_other_prob"] = [
            "=0.5*AVERAGEIFS(c_rea_comp!$O:$O,c_rea_comp!$F:$F,\"D1_Outpatient_Loop\")+0.5*AVERAGEIFS(c_rea_comp!$O:$O,c_rea_comp!$F:$F,\"D1_Outpatient_Decision\")",
            "=0.5*AVERAGEIFS(c_rea_comp!$O:$O,c_rea_comp!$F:$F,\"D2_Admission_Loop\")+0.5*AVERAGEIFS(c_rea_comp!$O:$O,c_rea_comp!$F:$F,\"D2_Admission_Decision\")",
            "=AVERAGEIFS(c_rea_comp!$O:$O,c_rea_comp!$F:$F,\"D3_Surgery_Decision\")",
            "=AVERAGEIFS(c_rea_comp!$O:$O,c_rea_comp!$F:$F,\"D4_Rehab_Plan\")",
        ]
        rea_prob["formula_stage_case_n"] = [
            "=COUNTIFS(c_rea_stage!$F:$F,\"D1\")",
            "=COUNTIFS(c_rea_stage!$F:$F,\"D2\")",
            "=COUNTIFS(c_rea_stage!$F:$F,\"D3\")",
            "=COUNTIFS(c_rea_stage!$F:$F,\"D4\")",
        ]
        rea_prob["formula_component_row_n"] = [
            "=COUNTIFS(c_rea_comp!$G:$G,\"D1\")",
            "=COUNTIFS(c_rea_comp!$G:$G,\"D2\")",
            "=COUNTIFS(c_rea_comp!$G:$G,\"D3\")",
            "=COUNTIFS(c_rea_comp!$G:$G,\"D4\")",
        ]
        rea_prob["说明"] = "D1/D2=(loop+decision)/2；D3/D4=decision。stage_case_n=融合后的病例数；component_row_n=c_rea_comp 原始 loop/decision 分量行数。"

    # 一致性负面事件概率：按标签布尔事件计算
    cons_prob = (
        consistency.groupby("stage4", as_index=False)
        .agg(
            fact_risk_prob=("fact_event_any", "mean"),
            cross_risk_prob=("cross_event_any", "mean"),
            sample_n=("case_id", "count"),
        )
        .rename(columns={"stage4": "stage"})
        .set_index("stage")
        .reindex(["D1", "D2", "D3", "D4"])
        .reset_index()
    )
    if not cons_prob.empty:
        cr = np.arange(2, len(cons_prob) + 2)
        cons_prob["formula_fact_risk_prob"] = [f"=AVERAGEIFS(c_cons_case!$M:$M,c_cons_case!$F:$F,B{r})" for r in cr]
        cons_prob["formula_cross_risk_prob"] = [f"=AVERAGEIFS(c_cons_case!$Q:$Q,c_cons_case!$F:$F,B{r})" for r in cr]
        cons_prob["formula_sample_n"] = [f"=COUNTIFS(c_cons_case!$F:$F,B{r})" for r in cr]
        cons_prob["说明"] = "事实风险=contradiction/hallucination/other任一出现；跨阶段风险=stage_conflict/fact_shift/other任一出现"

    # 记忆负面事件概率
    mem_prob = (
        memory.groupby("stage4", as_index=False)
        .agg(
            missing_prior_info_prob=("tag_missing_prior_info", "mean"),
            unused_key_info_prob=("tag_unused_key_info", "mean"),
            other_bucket_prob=("tag_other_bucket", "mean"),
            sample_n=("case_id", "count"),
        )
        .rename(columns={"stage4": "stage"})
        .set_index("stage")
        .reindex(["D2", "D3", "D4"])
        .reset_index()
    )

    # 三中心合并后按模型分列的对照表
    table_memory_model = (
        memory.groupby(["model_short", "stage4"], as_index=False)
        .agg(
            memory_composite=("memory_composite_0_1", "mean"),
            missing_prior_info_prob=("tag_missing_prior_info", "mean"),
            unused_key_info_prob=("tag_unused_key_info", "mean"),
            other_bucket_prob=("tag_other_bucket", "mean"),
        )
        .rename(columns={"stage4": "stage"})
        .sort_values(["stage", "model_short"], kind="mergesort")
    )
    table_cons_model = (
        consistency.groupby(["model_short", "stage4"], as_index=False)
        .agg(
            consistency_score_0_1=("consistency_score_0_1", "mean"),
            fact_risk_prob=("fact_event_any", "mean"),
            cross_risk_prob=("cross_event_any", "mean"),
        )
        .rename(columns={"stage4": "stage"})
        .sort_values(["stage", "model_short"], kind="mergesort")
    )
    table_rea_model = (
        reasoning_stage_score.groupby(["model_short", "stage"], as_index=False)
        .agg(reasoning_score_1_5_adj=("reasoning_score_1_5_adj", "mean"))
        .sort_values(["stage", "model_short"], kind="mergesort")
    )

    # 模型级事件概率（推理）
    def _event_prob_stage_model(event_col: str) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for m in MODEL_ORDER:
            subm = reasoning[reasoning["model_short"] == m]
            if subm.empty:
                continue
            loop_map = {"D1": "D1_Outpatient_Loop", "D2": "D2_Admission_Loop"}
            dec_map = {
                "D1": "D1_Outpatient_Decision",
                "D2": "D2_Admission_Decision",
                "D3": "D3_Surgery_Decision",
                "D4": "D4_Rehab_Plan",
            }
            for s in ["D1", "D2"]:
                loop_rate = pd.to_numeric(subm.loc[subm["stage_raw"] == loop_map[s], event_col], errors="coerce").mean()
                dec_rate = pd.to_numeric(subm.loc[subm["stage_raw"] == dec_map[s], event_col], errors="coerce").mean()
                rows.append({"model_short": m, "stage": s, "prob": _half_avg(loop_rate, dec_rate)})
            for s in ["D3", "D4"]:
                rows.append(
                    {
                        "model_short": m,
                        "stage": s,
                        "prob": float(pd.to_numeric(subm.loc[subm["stage_raw"] == dec_map[s], event_col], errors="coerce").mean()),
                    }
                )
        return pd.DataFrame(rows)

    rea_missing_model = _event_prob_stage_model("event_missing_link").rename(columns={"prob": "missing_link_prob"})
    rea_narrative_model = _event_prob_stage_model("event_narrative_bias").rename(columns={"prob": "narrative_bias_prob"})
    rea_other_model = _event_prob_stage_model("event_other_bucket").rename(columns={"prob": "other_prob"})
    table_rea_event_model = (
        rea_missing_model.merge(rea_narrative_model, on=["model_short", "stage"], how="outer")
        .merge(rea_other_model, on=["model_short", "stage"], how="outer")
        .sort_values(["stage", "model_short"], kind="mergesort")
    )
    table_model_overview = pd.concat(
        [
            table_memory_model.melt(
                id_vars=["model_short", "stage"],
                value_vars=["memory_composite", "missing_prior_info_prob", "unused_key_info_prob", "other_bucket_prob"],
                var_name="metric",
                value_name="value",
            ),
            table_cons_model.melt(
                id_vars=["model_short", "stage"],
                value_vars=["consistency_score_0_1", "fact_risk_prob", "cross_risk_prob"],
                var_name="metric",
                value_name="value",
            ),
            table_rea_model.melt(
                id_vars=["model_short", "stage"],
                value_vars=["reasoning_score_1_5_adj"],
                var_name="metric",
                value_name="value",
            ),
            table_rea_event_model.melt(
                id_vars=["model_short", "stage"],
                value_vars=["missing_link_prob", "narrative_bias_prob", "other_prob"],
                var_name="metric",
                value_name="value",
            ),
        ],
        ignore_index=True,
    ).sort_values(["metric", "stage", "model_short"], kind="mergesort")

    # 记忆/一致性复合指标拆解表（用于附录表格）
    stage_full_order = ["D1", "D2", "D3", "D4"]
    stage_model_grid = pd.MultiIndex.from_product([stage_full_order, MODEL_ORDER], names=["stage", "model_short"]).to_frame(index=False)
    mem_component_model = (
        memory.groupby(["stage4", "model_short"], as_index=False)
        .agg(
            inheritance_0_1=("inheritance_0_1", "mean"),
            utilization_0_1=("utilization_0_1", "mean"),
            key_info_loss_rate_0_1=("key_info_loss_rate_0_1", "mean"),
            memory_composite_0_1=("memory_composite_0_1", "mean"),
            memory_sample_n=("case_id", "count"),
        )
        .rename(columns={"stage4": "stage"})
    )
    cons_component_model = (
        consistency.groupby(["stage4", "model_short"], as_index=False)
        .agg(
            fact_score_0_1=("fact_score_0_1", "mean"),
            cross_score_0_1=("cross_score_0_1", "mean"),
            consistency_score_0_1=("consistency_score_0_1", "mean"),
            consistency_sample_n=("case_id", "count"),
        )
        .rename(columns={"stage4": "stage"})
    )
    table_mem_cons_component_model = (
        stage_model_grid.merge(mem_component_model, on=["stage", "model_short"], how="left")
        .merge(cons_component_model, on=["stage", "model_short"], how="left")
        .sort_values(["stage", "model_short"], kind="mergesort")
        .reset_index(drop=True)
    )
    if not table_mem_cons_component_model.empty:
        mr = np.arange(2, len(table_mem_cons_component_model) + 2)
        table_mem_cons_component_model["formula_inheritance_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_mem_raw!$G:$G,d_mem_raw!$F:$F,$A{r},d_mem_raw!$E:$E,$B{r}),\"\")" for r in mr
        ]
        table_mem_cons_component_model["formula_utilization_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_mem_raw!$H:$H,d_mem_raw!$F:$F,$A{r},d_mem_raw!$E:$E,$B{r}),\"\")" for r in mr
        ]
        table_mem_cons_component_model["formula_key_info_loss_rate_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_mem_raw!$I:$I,d_mem_raw!$F:$F,$A{r},d_mem_raw!$E:$E,$B{r}),\"\")" for r in mr
        ]
        table_mem_cons_component_model["formula_memory_composite_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_mem_raw!$J:$J,d_mem_raw!$F:$F,$A{r},d_mem_raw!$E:$E,$B{r}),\"\")" for r in mr
        ]
        table_mem_cons_component_model["formula_memory_sample_n"] = [
            f"=COUNTIFS(d_mem_raw!$F:$F,$A{r},d_mem_raw!$E:$E,$B{r})" for r in mr
        ]
        table_mem_cons_component_model["formula_fact_score_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_cons_fact_raw!$G:$G,d_cons_fact_raw!$F:$F,$A{r},d_cons_fact_raw!$E:$E,$B{r}),\"\")" for r in mr
        ]
        table_mem_cons_component_model["formula_cross_score_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_cons_fact_raw!$H:$H,d_cons_fact_raw!$F:$F,$A{r},d_cons_fact_raw!$E:$E,$B{r}),\"\")" for r in mr
        ]
        table_mem_cons_component_model["formula_consistency_score_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_cons_fact_raw!$I:$I,d_cons_fact_raw!$F:$F,$A{r},d_cons_fact_raw!$E:$E,$B{r}),\"\")" for r in mr
        ]
        table_mem_cons_component_model["formula_consistency_sample_n"] = [
            f"=COUNTIFS(d_cons_fact_raw!$F:$F,$A{r},d_cons_fact_raw!$E:$E,$B{r})" for r in mr
        ]
    table_mem_cons_component_model["说明"] = "记忆=继承度/利用率/1-丢失率的综合；一致性=事实一致性与跨阶段一致性均值。"

    mem_component_stage = (
        memory.groupby("stage4", as_index=False)
        .agg(
            inheritance_0_1=("inheritance_0_1", "mean"),
            utilization_0_1=("utilization_0_1", "mean"),
            key_info_loss_rate_0_1=("key_info_loss_rate_0_1", "mean"),
            memory_composite_0_1=("memory_composite_0_1", "mean"),
            memory_sample_n=("case_id", "count"),
        )
        .rename(columns={"stage4": "stage"})
    )
    cons_component_stage = (
        consistency.groupby("stage4", as_index=False)
        .agg(
            fact_score_0_1=("fact_score_0_1", "mean"),
            cross_score_0_1=("cross_score_0_1", "mean"),
            consistency_score_0_1=("consistency_score_0_1", "mean"),
            consistency_sample_n=("case_id", "count"),
        )
        .rename(columns={"stage4": "stage"})
    )
    table_mem_cons_component_stage = (
        pd.DataFrame({"stage": stage_full_order})
        .merge(mem_component_stage, on="stage", how="left")
        .merge(cons_component_stage, on="stage", how="left")
        .reset_index(drop=True)
    )
    if not table_mem_cons_component_stage.empty:
        sr = np.arange(2, len(table_mem_cons_component_stage) + 2)
        table_mem_cons_component_stage["formula_inheritance_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_mem_raw!$G:$G,d_mem_raw!$F:$F,$A{r}),\"\")" for r in sr
        ]
        table_mem_cons_component_stage["formula_utilization_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_mem_raw!$H:$H,d_mem_raw!$F:$F,$A{r}),\"\")" for r in sr
        ]
        table_mem_cons_component_stage["formula_key_info_loss_rate_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_mem_raw!$I:$I,d_mem_raw!$F:$F,$A{r}),\"\")" for r in sr
        ]
        table_mem_cons_component_stage["formula_memory_composite_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_mem_raw!$J:$J,d_mem_raw!$F:$F,$A{r}),\"\")" for r in sr
        ]
        table_mem_cons_component_stage["formula_memory_sample_n"] = [
            f"=COUNTIFS(d_mem_raw!$F:$F,$A{r})" for r in sr
        ]
        table_mem_cons_component_stage["formula_fact_score_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_cons_fact_raw!$G:$G,d_cons_fact_raw!$F:$F,$A{r}),\"\")" for r in sr
        ]
        table_mem_cons_component_stage["formula_cross_score_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_cons_fact_raw!$H:$H,d_cons_fact_raw!$F:$F,$A{r}),\"\")" for r in sr
        ]
        table_mem_cons_component_stage["formula_consistency_score_0_1"] = [
            f"=IFERROR(AVERAGEIFS(d_cons_fact_raw!$I:$I,d_cons_fact_raw!$F:$F,$A{r}),\"\")" for r in sr
        ]
        table_mem_cons_component_stage["formula_consistency_sample_n"] = [
            f"=COUNTIFS(d_cons_fact_raw!$F:$F,$A{r})" for r in sr
        ]
    table_mem_cons_component_stage["说明"] = "D1不含记忆指标（门诊首轮无历史信息），其记忆列留空。"

    table_mem_cons_component_stage_paper = (
        table_mem_cons_component_stage[
            [
                "stage",
                "inheritance_0_1",
                "utilization_0_1",
                "key_info_loss_rate_0_1",
                "memory_composite_0_1",
                "memory_sample_n",
                "fact_score_0_1",
                "cross_score_0_1",
                "consistency_score_0_1",
                "consistency_sample_n",
            ]
        ]
        .rename(
            columns={
                "stage": "环节",
                "inheritance_0_1": "继承度均分",
                "utilization_0_1": "利用率均分",
                "key_info_loss_rate_0_1": "关键信息丢失率均分",
                "memory_composite_0_1": "记忆综合指数均分",
                "memory_sample_n": "记忆样本数",
                "fact_score_0_1": "事实一致性均分",
                "cross_score_0_1": "跨阶段一致性均分",
                "consistency_score_0_1": "一致性综合均分",
                "consistency_sample_n": "一致性样本数",
            }
        )
    )
    table_mem_cons_component_model_paper = (
        table_mem_cons_component_model[
            [
                "stage",
                "model_short",
                "inheritance_0_1",
                "utilization_0_1",
                "key_info_loss_rate_0_1",
                "memory_composite_0_1",
                "memory_sample_n",
                "fact_score_0_1",
                "cross_score_0_1",
                "consistency_score_0_1",
                "consistency_sample_n",
            ]
        ]
        .rename(
            columns={
                "stage": "环节",
                "model_short": "模型",
                "inheritance_0_1": "继承度均分",
                "utilization_0_1": "利用率均分",
                "key_info_loss_rate_0_1": "关键信息丢失率均分",
                "memory_composite_0_1": "记忆综合指数均分",
                "memory_sample_n": "记忆样本数",
                "fact_score_0_1": "事实一致性均分",
                "cross_score_0_1": "跨阶段一致性均分",
                "consistency_score_0_1": "一致性综合均分",
                "consistency_sample_n": "一致性样本数",
            }
        )
    )
    _save_table_png(table_mem_cons_component_stage_paper, out_table_stage, "G3 附录表1：记忆保持与一致性分维度（总体）")
    _save_table_png(table_mem_cons_component_model_paper, out_table_model, "G3 附录表2：记忆保持与一致性分维度（模型×环节）")

    # 上排评分图对应的 summary（用于 source data 直接复核）
    summary_memory_score = (
        memory.groupby(["stage4", "model_short"], as_index=False)
        .agg(memory_composite_0_1=("memory_composite_0_1", "mean"), sample_n=("case_id", "count"))
        .rename(columns={"stage4": "stage"})
        .sort_values(["stage", "model_short"], kind="mergesort")
    )
    if not summary_memory_score.empty:
        rr = np.arange(2, len(summary_memory_score) + 2)
        summary_memory_score["formula_memory_composite_0_1"] = [
            f"=AVERAGEIFS(c_mem_case!$J:$J,c_mem_case!$F:$F,A{r},c_mem_case!$E:$E,B{r})" for r in rr
        ]
        summary_memory_score["formula_sample_n"] = [
            f"=COUNTIFS(c_mem_case!$F:$F,A{r},c_mem_case!$E:$E,B{r})" for r in rr
        ]
    summary_consistency_score = (
        consistency.groupby(["stage4", "model_short"], as_index=False)
        .agg(
            fact_score_0_1=("fact_score_0_1", "mean"),
            cross_score_0_1=("cross_score_0_1", "mean"),
            consistency_score_0_1=("consistency_score_0_1", "mean"),
            sample_n=("case_id", "count"),
        )
        .rename(columns={"stage4": "stage"})
        .sort_values(["stage", "model_short"], kind="mergesort")
    )
    if not summary_consistency_score.empty:
        rr = np.arange(2, len(summary_consistency_score) + 2)
        summary_consistency_score["formula_fact_score_0_1"] = [
            f"=AVERAGEIFS(c_cons_case!$G:$G,c_cons_case!$F:$F,A{r},c_cons_case!$E:$E,B{r})" for r in rr
        ]
        summary_consistency_score["formula_cross_score_0_1"] = [
            f"=AVERAGEIFS(c_cons_case!$H:$H,c_cons_case!$F:$F,A{r},c_cons_case!$E:$E,B{r})" for r in rr
        ]
        summary_consistency_score["formula_consistency_score_0_1"] = [
            f"=AVERAGEIFS(c_cons_case!$I:$I,c_cons_case!$F:$F,A{r},c_cons_case!$E:$E,B{r})" for r in rr
        ]
        summary_consistency_score["formula_sample_n"] = [
            f"=COUNTIFS(c_cons_case!$F:$F,A{r},c_cons_case!$E:$E,B{r})" for r in rr
        ]
    summary_reasoning_score = (
        reasoning_stage_score.groupby(["stage", "model_short"], as_index=False)
        .agg(reasoning_score_1_5_adj=("reasoning_score_1_5_adj", "mean"), sample_n=("case_id", "count"))
        .sort_values(["stage", "model_short"], kind="mergesort")
    )
    if not summary_reasoning_score.empty:
        rr = np.arange(2, len(summary_reasoning_score) + 2)
        summary_reasoning_score["formula_reasoning_score_1_5_adj"] = [
            f"=AVERAGEIFS(c_rea_stage!$G:$G,c_rea_stage!$F:$F,A{r},c_rea_stage!$E:$E,B{r})" for r in rr
        ]
        summary_reasoning_score["formula_sample_n"] = [
            f"=COUNTIFS(c_rea_stage!$F:$F,A{r},c_rea_stage!$E:$E,B{r})" for r in rr
        ]

    # 负面事件版本1：按 tag 细分（堆叠展示用）
    mem_tag_stack = (
        memory.groupby("stage4", as_index=False)
        .agg(
            missing_prior_info_prob=("tag_missing_prior_info", "mean"),
            unused_key_info_prob=("tag_unused_key_info", "mean"),
            other_prob=("tag_other_literal", "mean"),
            sample_n=("case_id", "count"),
        )
        .rename(columns={"stage4": "stage"})
        .set_index("stage")
        .reindex(["D2", "D3", "D4"])
        .reset_index()
    )
    if not mem_tag_stack.empty:
        rr = np.arange(2, len(mem_tag_stack) + 2)
        mem_tag_stack["formula_missing_prior_info_prob"] = [f"=AVERAGEIFS(c_mem_case!$L:$L,c_mem_case!$F:$F,B{r})" for r in rr]
        mem_tag_stack["formula_unused_key_info_prob"] = [f"=AVERAGEIFS(c_mem_case!$M:$M,c_mem_case!$F:$F,B{r})" for r in rr]
        mem_tag_stack["formula_other_prob"] = [f"=AVERAGEIFS(c_mem_case!$N:$N,c_mem_case!$F:$F,B{r})" for r in rr]
        mem_tag_stack["formula_sample_n"] = [f"=COUNTIFS(c_mem_case!$F:$F,B{r})" for r in rr]
    if not mem_prob.empty:
        mr = np.arange(2, len(mem_prob) + 2)
        mem_prob["formula_missing_prior_info_prob"] = [f"=AVERAGEIFS(c_mem_case!$L:$L,c_mem_case!$F:$F,B{r})" for r in mr]
        mem_prob["formula_unused_key_info_prob"] = [f"=AVERAGEIFS(c_mem_case!$M:$M,c_mem_case!$F:$F,B{r})" for r in mr]
        mem_prob["formula_other_bucket_prob"] = [f"=AVERAGEIFS(c_mem_case!$O:$O,c_mem_case!$F:$F,B{r})" for r in mr]
        mem_prob["formula_sample_n"] = [f"=COUNTIFS(c_mem_case!$F:$F,B{r})" for r in mr]
        mem_prob["说明"] = "三类事件按病例-阶段布尔发生率统计；other_bucket=除missing_prior_info/unused_key_info外任意标签"
    cons_tag_stack = (
        consistency.groupby("stage4", as_index=False)
        .agg(
            fact_contradiction_prob=("fact_tag_contradiction", "mean"),
            fact_hallucination_prob=("fact_tag_hallucination", "mean"),
            fact_other_prob=("fact_tag_other", "mean"),
            cross_stage_conflict_prob=("cross_tag_stage_conflict", "mean"),
            cross_fact_shift_prob=("cross_tag_fact_shift", "mean"),
            cross_other_prob=("cross_tag_other", "mean"),
            sample_n=("case_id", "count"),
        )
        .rename(columns={"stage4": "stage"})
        .set_index("stage")
        .reindex(["D1", "D2", "D3", "D4"])
        .reset_index()
    )
    if not cons_tag_stack.empty:
        rr = np.arange(2, len(cons_tag_stack) + 2)
        cons_tag_stack["formula_fact_contradiction_prob"] = [f"=AVERAGEIFS(c_cons_case!$J:$J,c_cons_case!$F:$F,B{r})" for r in rr]
        cons_tag_stack["formula_fact_hallucination_prob"] = [f"=AVERAGEIFS(c_cons_case!$K:$K,c_cons_case!$F:$F,B{r})" for r in rr]
        cons_tag_stack["formula_fact_other_prob"] = [f"=AVERAGEIFS(c_cons_case!$L:$L,c_cons_case!$F:$F,B{r})" for r in rr]
        cons_tag_stack["formula_cross_stage_conflict_prob"] = [f"=AVERAGEIFS(c_cons_case!$N:$N,c_cons_case!$F:$F,B{r})" for r in rr]
        cons_tag_stack["formula_cross_fact_shift_prob"] = [f"=AVERAGEIFS(c_cons_case!$O:$O,c_cons_case!$F:$F,B{r})" for r in rr]
        cons_tag_stack["formula_cross_other_prob"] = [f"=AVERAGEIFS(c_cons_case!$P:$P,c_cons_case!$F:$F,B{r})" for r in rr]
        cons_tag_stack["formula_sample_n"] = [f"=COUNTIFS(c_cons_case!$F:$F,B{r})" for r in rr]
    rea_tag_stack = (
        reasoning.groupby("stage4", as_index=False)
        .agg(
            missing_link_prob=("event_missing_link", "mean"),
            over_integration_prob=("event_over_integration", "mean"),
            narrative_bias_prob=("event_narrative_bias", "mean"),
            logic_jump_prob=("event_logic_jump", "mean"),
            other_prob=("event_other_tag", "mean"),
            component_row_n=("case_id", "count"),
        )
        .rename(columns={"stage4": "stage"})
        .set_index("stage")
        .reindex(["D1", "D2", "D3", "D4"])
        .reset_index()
    )
    if not rea_tag_stack.empty:
        rea_tag_stack["stage_case_n"] = rea_tag_stack["stage"].map(lambda s: int(rea_stage_case_n.get(str(s), 0)))
        rr = np.arange(2, len(rea_tag_stack) + 2)
        rea_tag_stack["formula_missing_link_prob"] = [f"=AVERAGEIFS(c_rea_comp!$J:$J,c_rea_comp!$G:$G,B{r})" for r in rr]
        rea_tag_stack["formula_over_integration_prob"] = [f"=AVERAGEIFS(c_rea_comp!$K:$K,c_rea_comp!$G:$G,B{r})" for r in rr]
        rea_tag_stack["formula_narrative_bias_prob"] = [f"=AVERAGEIFS(c_rea_comp!$L:$L,c_rea_comp!$G:$G,B{r})" for r in rr]
        rea_tag_stack["formula_logic_jump_prob"] = [f"=AVERAGEIFS(c_rea_comp!$M:$M,c_rea_comp!$G:$G,B{r})" for r in rr]
        rea_tag_stack["formula_other_prob"] = [f"=AVERAGEIFS(c_rea_comp!$N:$N,c_rea_comp!$G:$G,B{r})" for r in rr]
        rea_tag_stack["formula_stage_case_n"] = [f"=COUNTIFS(c_rea_stage!$F:$F,B{r})" for r in rr]
        rea_tag_stack["formula_component_row_n"] = [f"=COUNTIFS(c_rea_comp!$G:$G,B{r})" for r in rr]
        rea_tag_stack["说明"] = "D1/D2 的 component_row_n 含 loop+decision 两类原始分量；stage_case_n 为阶段融合后的病例数。"

    # G3 附录 Word 表：分维度 + 异常事件（分阶段）
    mem_event_bool_word = (
        mem_prob[["stage", "missing_prior_info_prob", "unused_key_info_prob", "other_bucket_prob", "sample_n"]]
        .rename(
            columns={
                "stage": "环节",
                "missing_prior_info_prob": "既往信息遗漏概率",
                "unused_key_info_prob": "关键信息未使用概率",
                "other_bucket_prob": "其他问题概率",
                "sample_n": "样本数",
            }
        )
        .copy()
    )
    cons_event_bool_word = (
        cons_prob[["stage", "fact_risk_prob", "cross_risk_prob", "sample_n"]]
        .rename(
            columns={
                "stage": "环节",
                "fact_risk_prob": "事实一致性风险概率",
                "cross_risk_prob": "跨阶段一致性风险概率",
                "sample_n": "样本数",
            }
        )
        .copy()
    )
    rea_event_bool_word = (
        rea_prob[["stage", "missing_link_prob", "narrative_bias_prob", "other_prob", "stage_case_n", "component_row_n"]]
        .rename(
            columns={
                "stage": "环节",
                "missing_link_prob": "推理链断点概率",
                "narrative_bias_prob": "叙事偏差概率",
                "other_prob": "其他问题概率",
                "stage_case_n": "阶段病例数",
                "component_row_n": "分量行数",
            }
        )
        .copy()
    )
    mem_event_stack_word = (
        mem_tag_stack[["stage", "missing_prior_info_prob", "unused_key_info_prob", "other_prob", "sample_n"]]
        .rename(
            columns={
                "stage": "环节",
                "missing_prior_info_prob": "既往信息遗漏概率",
                "unused_key_info_prob": "关键信息未使用概率",
                "other_prob": "other标签概率",
                "sample_n": "样本数",
            }
        )
        .copy()
    )
    cons_event_stack_word = (
        cons_tag_stack[
            [
                "stage",
                "fact_contradiction_prob",
                "fact_hallucination_prob",
                "fact_other_prob",
                "cross_stage_conflict_prob",
                "cross_fact_shift_prob",
                "cross_other_prob",
                "sample_n",
            ]
        ]
        .rename(
            columns={
                "stage": "环节",
                "fact_contradiction_prob": "事实矛盾概率",
                "fact_hallucination_prob": "事实幻觉概率",
                "fact_other_prob": "事实其他概率",
                "cross_stage_conflict_prob": "阶段冲突概率",
                "cross_fact_shift_prob": "事实漂移概率",
                "cross_other_prob": "跨阶段其他概率",
                "sample_n": "样本数",
            }
        )
        .copy()
    )
    rea_event_stack_word = (
        rea_tag_stack[
            [
                "stage",
                "missing_link_prob",
                "over_integration_prob",
                "narrative_bias_prob",
                "logic_jump_prob",
                "other_prob",
                "stage_case_n",
                "component_row_n",
            ]
        ]
        .rename(
            columns={
                "stage": "环节",
                "missing_link_prob": "推理链断点概率",
                "over_integration_prob": "过度整合概率",
                "narrative_bias_prob": "叙事偏差概率",
                "logic_jump_prob": "逻辑跳步概率",
                "other_prob": "other标签概率",
                "stage_case_n": "阶段病例数",
                "component_row_n": "分量行数",
            }
        )
        .copy()
    )
    _save_docx_tables(
        out_word,
        "G3 连续性附录表：分维度得分与异常事件（分阶段）",
        sections=[
            {
                "title": "表1 记忆保持/一致性分维度（总体）",
                "note": "用于附件展示复合指标的各构成维度均分；D1无记忆项。",
                "df": table_mem_cons_component_stage_paper,
            },
            {
                "title": "表2 记忆保持/一致性分维度（模型×环节）",
                "note": "同一环节下对比五模型的维度得分差异。",
                "df": table_mem_cons_component_model_paper,
            },
            {
                "title": "表3 记忆异常事件总览（图 d 口径）",
                "note": "事件为布尔发生率口径（可并发，不互斥）。",
                "df": mem_event_bool_word,
            },
            {
                "title": "表4 一致性异常事件总览（图 e 口径）",
                "note": "事实风险与跨阶段风险为两条独立事件轴，允许同病例同阶段同时发生。",
                "df": cons_event_bool_word,
            },
            {
                "title": "表5 推理异常事件总览（图 f 口径）",
                "note": "D1/D2 概率按 loop+decision 融合，D3/D4 按决策阶段概率。",
                "df": rea_event_bool_word,
            },
            {
                "title": "表6 记忆异常事件细分（tag级）",
                "note": "按 D2-D4 展示记忆相关标签发生概率。",
                "df": mem_event_stack_word,
            },
            {
                "title": "表7 一致性异常事件细分（tag级）",
                "note": "按 D1-D4 展示事实侧与跨阶段侧标签发生概率。",
                "df": cons_event_stack_word,
            },
            {
                "title": "表8 推理异常事件细分（tag级）",
                "note": "按 D1-D4 展示推理链标签发生概率；D1/D2含 loop+decision 分量。",
                "df": rea_event_stack_word,
            },
        ],
        intro_lines=[
            "数据来源：G3_continuity_metrics_v4_source.xlsx（明细/计算/汇总）。",
            "本附录用于论文附件直接粘贴引用；数值保留三位小数。",
        ],
    )

    # 解释文档：为何 d-f 事件概率高而 a-c 评分仍可 >0.5
    mem_sum = mem_prob.assign(event_prob_sum=mem_prob[["missing_prior_info_prob", "unused_key_info_prob", "other_bucket_prob"]].sum(axis=1))
    cons_sum = cons_prob.assign(event_prob_sum=cons_prob[["fact_risk_prob", "cross_risk_prob"]].sum(axis=1))
    rea_sum = rea_prob.assign(event_prob_sum=rea_prob[["missing_link_prob", "narrative_bias_prob", "other_prob"]].sum(axis=1))
    mem_score_stage = (
        table_mem_cons_component_stage[["stage", "memory_composite_0_1"]]
        .rename(columns={"memory_composite_0_1": "score_mean"})
        .dropna(subset=["score_mean"])
    )
    cons_score_stage = (
        table_mem_cons_component_stage[["stage", "consistency_score_0_1"]]
        .rename(columns={"consistency_score_0_1": "score_mean"})
        .dropna(subset=["score_mean"])
    )
    rea_score_stage = (
        reasoning_stage_score.groupby("stage", as_index=False)
        .agg(score_mean=("reasoning_score_1_5_adj", "mean"))
        .dropna(subset=["score_mean"])
    )
    mem_case_any = (memory[["tag_missing_prior_info", "tag_unused_key_info", "tag_other_bucket"]].fillna(0).sum(axis=1) > 0).astype(int)
    cons_case_any = (consistency[["fact_event_any", "cross_event_any"]].fillna(0).sum(axis=1) > 0).astype(int)
    rea_case_any = (
        reasoning[["event_missing_link", "event_over_integration", "event_narrative_bias", "event_logic_jump", "event_other_tag"]]
        .fillna(0)
        .sum(axis=1)
        > 0
    ).astype(int)
    mem_corr = pd.to_numeric(memory["memory_composite_0_1"], errors="coerce").corr(mem_case_any)
    cons_corr = pd.to_numeric(consistency["consistency_score_0_1"], errors="coerce").corr(cons_case_any)
    rea_corr = pd.to_numeric(reasoning["reasoning_score_1_5"], errors="coerce").corr(rea_case_any)
    mem_e1 = pd.to_numeric(memory.loc[mem_case_any == 1, "memory_composite_0_1"], errors="coerce").mean()
    mem_e0 = pd.to_numeric(memory.loc[mem_case_any == 0, "memory_composite_0_1"], errors="coerce").mean()
    cons_e1 = pd.to_numeric(consistency.loc[cons_case_any == 1, "consistency_score_0_1"], errors="coerce").mean()
    cons_e0 = pd.to_numeric(consistency.loc[cons_case_any == 0, "consistency_score_0_1"], errors="coerce").mean()
    rea_e1 = pd.to_numeric(reasoning.loc[rea_case_any == 1, "reasoning_score_1_5"], errors="coerce").mean()
    rea_e0 = pd.to_numeric(reasoning.loc[rea_case_any == 0, "reasoning_score_1_5"], errors="coerce").mean()

    lines_logic = [
        "# G3 说明：为何 d-f 事件概率较高，而 a-c 评分仍可保持中高",
        "",
        "## 结论",
        "- d/e/f 的事件柱是“不同事件类型的边际发生概率”，事件并不互斥，因此同一阶段把多类概率相加可接近或超过 1。",
        "- a/b/c 的评分是连续分值（且按复合公式聚合），不是“出现事件即清零”的扣分机制，所以分数仍可在 0.5 以上。",
        "",
        "## 关键口径差异（代码实现）",
        "- 记忆综合分：`memory_composite_0_1 = (inheritance + utilization + (1-loss_rate))/3`。",
        "- 一致性综合分：`consistency_score_0_1 = mean(fact_score_0_1, cross_score_0_1)`。",
        "- d/e/f 事件概率来自布尔事件发生率（`*_event_any` 或 tag 布尔列），是“是否发生”，不是“严重程度”。",
        "- 推理在 D1/D2 存在 loop 与 decision 双分量，图 c 与图 f 都做了融合，但仍保留了分量层统计（见 `component_row_n`）。",
        "",
        "## 本轮数据上的直接证据",
        "### 1) 事件概率求和 > 1 是统计口径导致（非数学错误）",
        "",
    ]
    for _, r in mem_sum.iterrows():
        lines_logic.append(f"- 记忆 {r['stage']}: 三类事件概率和 = {float(r['event_prob_sum']):.3f}")
    for _, r in cons_sum.iterrows():
        lines_logic.append(f"- 一致性 {r['stage']}: 两类风险概率和 = {float(r['event_prob_sum']):.3f}")
    for _, r in rea_sum.iterrows():
        lines_logic.append(f"- 推理 {r['stage']}: 三类事件概率和 = {float(r['event_prob_sum']):.3f}")
    lines_logic.extend(
        [
            "",
            "### 2) 事件与分数显著负相关，但不是“硬阈值淘汰”",
            f"- 记忆：corr(event_any, score) = {float(mem_corr):.3f}；事件发生/未发生均分 = {float(mem_e1):.3f} / {float(mem_e0):.3f}",
            f"- 一致性：corr(event_any, score) = {float(cons_corr):.3f}；事件发生/未发生均分 = {float(cons_e1):.3f} / {float(cons_e0):.3f}",
            f"- 推理：corr(event_any, score) = {float(rea_corr):.3f}；事件发生/未发生均分 = {float(rea_e1):.3f} / {float(rea_e0):.3f}",
            "",
            "## 为什么看起来“高事件率却还有中高分”",
            "1. 事件布尔率不含严重程度：轻微问题与严重问题都记为 1 次发生。",
            "2. 复合评分有补偿效应：某一维度下降，可被其它维度高分部分抵消。",
            "3. 事件类别可并发：同一个病例同一阶段可同时触发多个标签，导致柱状图可叠加超过 1。",
            "4. 阶段聚合口径不同：评分是均值，事件是发生率；同一批样本中二者可同时成立。",
            "",
            "## 论文中建议写法",
            "- 建议将 d-f 明确标注为“边际发生概率（非互斥，可并发）”。",
            "- 若要避免误读，可补充“any_event 总发生率”或“按病例互斥归一化后的事件构成”。",
            "",
            "## 相关文件",
            "- 图：`analysis_viz/figures/v2_subplots/G3_continuity/G3_continuity_metrics_v4.png`",
            "- Source：`analysis_viz/data/derived/figdata/v2_subplots/G3_continuity/G3_continuity_metrics_v4_source.xlsx`",
            "- Word 附录表：`analysis_viz/figures/v2_subplots/G3_continuity/G3_continuity_appendix_tables_v1.docx`",
        ]
    )
    out_logic_md.write_text("\n".join(lines_logic) + "\n", encoding="utf-8")

    memory_ylim = _adaptive_ylim(memory["memory_composite_0_1"], fallback=(0.0, 1.0), domain=(0.0, 1.0), min_span=0.2)
    consistency_ylim = _adaptive_ylim(consistency["consistency_score_0_1"], fallback=(0.0, 1.0), domain=(0.0, 1.0), min_span=0.2)
    reasoning_ylim = _adaptive_ylim(reasoning_stage_score["reasoning_score_1_5_adj"], fallback=(1.0, 5.0), domain=(1.0, 5.0), min_span=0.6)

    fig = plt.figure(figsize=(17.2, 10.6))
    gs = fig.add_gridspec(2, 3, hspace=0.42, wspace=0.3)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[0, 2])
    ax_d = fig.add_subplot(gs[1, 0])
    ax_e = fig.add_subplot(gs[1, 1])
    ax_f = fig.add_subplot(gs[1, 2])

    _plot_band_scatter(
        ax=ax_a,
        detail=memory.assign(stage=memory["stage4"])[["stage", "model_short", "memory_composite_0_1"]],
        value_col="memory_composite_0_1",
        stage_order=["D2", "D3", "D4"],
        stage_label_map={"D2": "D2", "D3": "D3", "D4": "D4"},
        title="a. 记忆保持与利用",
        y_label="记忆综合指数",
        ylim=memory_ylim,
        mean_color="#2A6F9E",
    )
    _plot_band_scatter(
        ax=ax_b,
        detail=consistency.assign(stage=consistency["stage4"])[["stage", "model_short", "consistency_score_0_1"]],
        value_col="consistency_score_0_1",
        stage_order=["D1", "D2", "D3", "D4"],
        stage_label_map={"D1": "D1", "D2": "D2", "D3": "D3", "D4": "D4"},
        title="b. 事实与跨阶段一致性",
        y_label="一致性得分",
        ylim=consistency_ylim,
        mean_color="#2ca02c",
    )
    _plot_band_scatter(
        ax=ax_c,
        detail=reasoning_stage_score.assign(stage=reasoning_stage_score["stage"])[["stage", "model_short", "reasoning_score_1_5_adj"]],
        value_col="reasoning_score_1_5_adj",
        stage_order=["D1", "D2", "D3", "D4"],
        stage_label_map={"D1": "D1", "D2": "D2", "D3": "D3", "D4": "D4"},
        title="c. 推理链质量",
        y_label="推理链得分",
        ylim=reasoning_ylim,
        mean_color="#8e44ad",
    )

    ax_a.legend(
        handles=[
            Line2D([0], [0], color="#2A6F9E", linewidth=2.6, label="总体均值"),
            Patch(facecolor="#2A6F9E", alpha=0.22, edgecolor="none", label="模型离散带"),
        ],
        loc="upper right",
        fontsize=8.0,
        frameon=True,
    )
    ax_b.legend(
        handles=[
            Line2D([0], [0], color="#2ca02c", linewidth=2.6, label="总体均值"),
            Patch(facecolor="#2ca02c", alpha=0.22, edgecolor="none", label="模型离散带"),
        ],
        loc="upper right",
        fontsize=8.0,
        frameon=True,
    )
    ax_c.legend(
        handles=[
            Line2D([0], [0], color="#8e44ad", linewidth=2.6, label="总体均值"),
            Patch(facecolor="#8e44ad", alpha=0.22, edgecolor="none", label="模型离散带"),
        ],
        loc="upper right",
        fontsize=8.0,
        frameon=True,
    )
    model_handles = _build_model_legend_handles(MODEL_ORDER, marker_size=7.2)
    fig.legend(
        model_handles,
        [h.get_label() for h in model_handles],
        loc="lower center",
        bbox_to_anchor=(0.08, 0.49, 0.84, 0.08),
        mode="expand",
        ncol=max(1, len(model_handles)),
        fontsize=8.5,
        frameon=True,
        borderaxespad=0.25,
    )

    # d/e/f：统一为事件发生概率（0-1）
    x_d = np.arange(len(mem_prob))
    w3m = 0.23
    ax_d.bar(x_d - w3m, mem_prob["missing_prior_info_prob"], width=w3m, color="#A6CEE3", label="既往信息遗漏")
    ax_d.bar(x_d, mem_prob["unused_key_info_prob"], width=w3m, color="#4A8BBF", label="关键信息未使用")
    ax_d.bar(x_d + w3m, mem_prob["other_bucket_prob"], width=w3m, color="#2A6F9E", label="其他问题")
    ax_d.set_xticks(x_d)
    ax_d.set_xticklabels(mem_prob["stage"].tolist())
    ax_d.set_ylim(0.0, 1.0)
    ax_d.set_ylabel("发生概率")
    ax_d.set_title("d. 记忆负向事件")
    ax_d.legend(loc="upper right", fontsize=8, frameon=False)

    x_e = np.arange(len(cons_prob))
    w2 = 0.34
    ax_e.bar(x_e - w2 / 2.0, cons_prob["fact_risk_prob"], width=w2, color="#9BD39A", label="事实一致性风险")
    ax_e.bar(x_e + w2 / 2.0, cons_prob["cross_risk_prob"], width=w2, color="#2CA02C", label="跨阶段一致性风险")
    ax_e.set_xticks(x_e)
    ax_e.set_xticklabels(cons_prob["stage"].tolist())
    ax_e.set_ylim(0.0, 1.0)
    ax_e.set_ylabel("发生概率")
    ax_e.set_title("e. 一致性风险事件")
    ax_e.legend(loc="upper right", fontsize=8, frameon=False)

    x_f = np.arange(len(rea_prob))
    w3 = 0.23
    ax_f.bar(x_f - w3, rea_prob["missing_link_prob"], width=w3, color="#D5B2E0", label="推理链断点")
    ax_f.bar(x_f, rea_prob["narrative_bias_prob"], width=w3, color="#B47CC7", label="叙事偏差")
    ax_f.bar(x_f + w3, rea_prob["other_prob"], width=w3, color="#8E44AD", label="其他问题")
    ax_f.set_xticks(x_f)
    ax_f.set_xticklabels(rea_prob["stage"].tolist())
    ax_f.set_ylim(0.0, 1.0)
    ax_f.set_ylabel("发生概率")
    ax_f.set_title("f. 推理缺陷事件")
    ax_f.legend(loc="upper right", fontsize=8, frameon=False)

    for axx in [ax_a, ax_b, ax_c, ax_d, ax_e, ax_f]:
        _set_full_axis_border(axx)

    fig.suptitle("G3 持续性指标监测", fontsize=16, y=1.01)
    fig.text(
        0.5,
        0.01,
        "注：上排为连续评分趋势；下排统一为事件发生概率。D1/D2 推理评分与推理事件按 loop+决策平均聚合。",
        ha="center",
        va="bottom",
        fontsize=9,
        color="#444444",
    )
    sub_figs = _save_subfigures(
        fig,
        group,
        {
            "G3A_memory_trend_v2": ax_a,
            "G3B_consistency_trend_v2": ax_b,
            "G3C_reasoning_trend_v2": ax_c,
            "G3D_memory_event_count_v2": ax_d,
            "G3E_consistency_event_count_v2": ax_e,
            "G3F_reasoning_event_count_v2": ax_f,
        },
    )
    _save_fig(out_img)

    # 负面事件方案一：按 tag 细分（堆叠）
    fig_tag = plt.figure(figsize=(16.8, 9.6))
    gs_tag = fig_tag.add_gridspec(2, 2, hspace=0.35, wspace=0.26)
    ax_tm = fig_tag.add_subplot(gs_tag[0, 0])
    ax_tcf = fig_tag.add_subplot(gs_tag[0, 1])
    ax_tcc = fig_tag.add_subplot(gs_tag[1, 0])
    ax_tr = fig_tag.add_subplot(gs_tag[1, 1])

    def _stacked_event_bars(
        ax: plt.Axes,
        df_stage: pd.DataFrame,
        stage_order: list[str],
        components: list[tuple[str, str, str]],
        title: str,
    ) -> None:
        d = df_stage.set_index("stage").reindex(stage_order).fillna(0.0).reset_index()
        x = np.arange(len(stage_order))
        bottom = np.zeros(len(stage_order), dtype=float)
        low_priority_tokens = ("本流程进行前已结束", "流程前已结束", "未经过")
        ordered_components = sorted(
            components,
            key=lambda item: 0 if any(tok in str(item[1]) for tok in low_priority_tokens) else 1,
        )
        for col, label, color in ordered_components:
            vals = pd.to_numeric(d[col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
            ax.bar(x, vals, bottom=bottom, width=0.72, color=color, edgecolor="white", linewidth=0.4, label=label)
            bottom += vals
        ax.set_xticks(x)
        ax.set_xticklabels(stage_order)
        ax.set_ylim(0.0, 1.0)
        ax.set_ylabel("发生概率")
        ax.set_title(title)
        ax.grid(alpha=0.22, axis="y")
        ax.legend(loc="upper right", fontsize=8, frameon=False)
        _set_full_axis_border(ax)

    _stacked_event_bars(
        ax_tm,
        mem_tag_stack,
        ["D2", "D3", "D4"],
        [
            ("missing_prior_info_prob", "既往信息遗漏", "#9FC6E7"),
            ("unused_key_info_prob", "关键信息未使用", "#4A8BBF"),
            ("other_prob", "其他问题", "#2F5D8A"),
        ],
        "a. 记忆负面事件",
    )
    _stacked_event_bars(
        ax_tcf,
        cons_tag_stack,
        ["D1", "D2", "D3", "D4"],
        [
            ("fact_contradiction_prob", "事实矛盾", "#A8D5A2"),
            ("fact_hallucination_prob", "事实幻觉", "#5DBB63"),
            ("fact_other_prob", "其他问题", "#2E8B57"),
        ],
        "b. 事实一致性负面事件",
    )
    _stacked_event_bars(
        ax_tcc,
        cons_tag_stack,
        ["D1", "D2", "D3", "D4"],
        [
            ("cross_stage_conflict_prob", "阶段冲突", "#C8E6A0"),
            ("cross_fact_shift_prob", "事实漂移", "#8BC34A"),
            ("cross_other_prob", "其他问题", "#4F8A10"),
        ],
        "c. 跨阶段矛盾负面事件",
    )
    _stacked_event_bars(
        ax_tr,
        rea_tag_stack,
        ["D1", "D2", "D3", "D4"],
        [
            ("missing_link_prob", "推理链断点", "#D9B3E6"),
            ("over_integration_prob", "过度整合", "#B57EDC"),
            ("narrative_bias_prob", "叙事偏差", "#A569BD"),
            ("logic_jump_prob", "逻辑跳步", "#8E44AD"),
            ("other_prob", "其他问题", "#6C3483"),
        ],
        "d. 推理负面事件",
    )
    fig_tag.suptitle("G3 持续性负面事件 细分版", fontsize=15, y=0.99)
    _save_fig(out_img_tagstack)

    # 负面事件方案二：替代版（上排三趋势 + 下排单框事件）
    fig_event_long = plt.figure(figsize=(17.8, 8.4))
    gs_long = fig_event_long.add_gridspec(2, 3, height_ratios=[1.0, 0.95], hspace=0.30, wspace=0.24)
    ax_lm_top = fig_event_long.add_subplot(gs_long[0, 0])
    ax_lc_top = fig_event_long.add_subplot(gs_long[0, 1])
    ax_lr_top = fig_event_long.add_subplot(gs_long[0, 2])
    ax_event_any = fig_event_long.add_subplot(gs_long[1, :])

    _plot_band_scatter(
        ax=ax_lm_top,
        detail=memory.assign(stage=memory["stage4"])[["stage", "model_short", "memory_composite_0_1"]],
        value_col="memory_composite_0_1",
        stage_order=["D2", "D3", "D4"],
        stage_label_map={"D2": "D2", "D3": "D3", "D4": "D4"},
        title="a. 记忆保持与利用",
        y_label="记忆综合指数",
        ylim=memory_ylim,
        mean_color="#2A6F9E",
    )
    _plot_band_scatter(
        ax=ax_lc_top,
        detail=consistency.assign(stage=consistency["stage4"])[["stage", "model_short", "consistency_score_0_1"]],
        value_col="consistency_score_0_1",
        stage_order=["D1", "D2", "D3", "D4"],
        stage_label_map={"D1": "D1", "D2": "D2", "D3": "D3", "D4": "D4"},
        title="b. 事实与跨阶段一致性",
        y_label="一致性得分",
        ylim=consistency_ylim,
        mean_color="#2ca02c",
    )
    _plot_band_scatter(
        ax=ax_lr_top,
        detail=reasoning_stage_score.assign(stage=reasoning_stage_score["stage"])[["stage", "model_short", "reasoning_score_1_5_adj"]],
        value_col="reasoning_score_1_5_adj",
        stage_order=["D1", "D2", "D3", "D4"],
        stage_label_map={"D1": "D1", "D2": "D2", "D3": "D3", "D4": "D4"},
        title="c. 推理链质量",
        y_label="推理链得分",
        ylim=reasoning_ylim,
        mean_color="#8e44ad",
    )
    ax_lm_top.legend(
        handles=[
            Line2D([0], [0], color="#2A6F9E", linewidth=2.6, label="总体均值"),
            Patch(facecolor="#2A6F9E", alpha=0.22, edgecolor="none", label="模型离散带"),
        ],
        loc="upper right",
        fontsize=8.0,
        frameon=True,
    )
    ax_lc_top.legend(
        handles=[
            Line2D([0], [0], color="#2ca02c", linewidth=2.6, label="总体均值"),
            Patch(facecolor="#2ca02c", alpha=0.22, edgecolor="none", label="模型离散带"),
        ],
        loc="upper right",
        fontsize=8.0,
        frameon=True,
    )
    ax_lr_top.legend(
        handles=[
            Line2D([0], [0], color="#8e44ad", linewidth=2.6, label="总体均值"),
            Patch(facecolor="#8e44ad", alpha=0.22, edgecolor="none", label="模型离散带"),
        ],
        loc="upper right",
        fontsize=8.0,
        frameon=True,
    )

    event_any_stage = pd.DataFrame({"stage": ["D1", "D2", "D3", "D4"]})
    mem_any = (
        memory.groupby("stage4", as_index=False)["inheritance_issue_event"]
        .mean()
        .rename(columns={"stage4": "stage", "inheritance_issue_event": "memory_any_prob"})
    )
    cons_any = (
        consistency.assign(
            any_event=(
                (pd.to_numeric(consistency["fact_event_any"], errors="coerce").fillna(0.0) > 0)
                | (pd.to_numeric(consistency["cross_event_any"], errors="coerce").fillna(0.0) > 0)
            ).astype(int)
        )
        .groupby("stage4", as_index=False)["any_event"]
        .mean()
        .rename(columns={"stage4": "stage", "any_event": "consistency_any_prob"})
    )
    rea_any = (
        reasoning.assign(any_event=reasoning["tags"].apply(lambda arr: int(len(arr) > 0)))
        .groupby("stage4", as_index=False)["any_event"]
        .mean()
        .rename(columns={"stage4": "stage", "any_event": "reasoning_any_prob"})
    )
    event_any_stage = (
        event_any_stage.merge(mem_any, on="stage", how="left")
        .merge(cons_any, on="stage", how="left")
        .merge(rea_any, on="stage", how="left")
    )
    x_any = np.arange(len(event_any_stage), dtype=float)
    w_any = 0.24
    ax_event_any.bar(
        x_any - w_any,
        pd.to_numeric(event_any_stage["memory_any_prob"], errors="coerce"),
        width=w_any,
        color="#4A8BBF",
        alpha=0.84,
        label="记忆负面事件",
    )
    ax_event_any.bar(
        x_any,
        pd.to_numeric(event_any_stage["consistency_any_prob"], errors="coerce"),
        width=w_any,
        color="#2CA02C",
        alpha=0.84,
        label="一致性负面事件",
    )
    ax_event_any.bar(
        x_any + w_any,
        pd.to_numeric(event_any_stage["reasoning_any_prob"], errors="coerce"),
        width=w_any,
        color="#8E44AD",
        alpha=0.84,
        label="推理负面事件",
    )
    ax_event_any.set_xticks(x_any)
    ax_event_any.set_xticklabels(event_any_stage["stage"].astype(str).tolist(), fontsize=10.2)
    ax_event_any.set_ylim(0.0, 1.0)
    ax_event_any.set_ylabel("发生概率")
    ax_event_any.set_title("d. 负面事件总览（单框替代版）")
    ax_event_any.grid(alpha=0.22, axis="y")
    ax_event_any.legend(loc="upper right", fontsize=9.0, frameon=True, ncol=3)

    for axx in [ax_lm_top, ax_lc_top, ax_lr_top, ax_event_any]:
        _set_full_axis_border(axx)
    fig_event_long.suptitle("G3 持续性替代版（上排趋势 + 下排单框事件）", fontsize=14.5, y=0.99)
    fig_event_long.subplots_adjust(left=0.06, right=0.995, top=0.90, bottom=0.09)
    _save_fig(out_img_event_long)

    calculate_memory_case = memory[
        [
            "center",
            "model",
            "case_id",
            "model_short",
            "stage4",
            "inheritance_0_1",
            "utilization_0_1",
            "key_info_loss_rate_0_1",
            "memory_composite_0_1",
            "tags_text",
            "tag_missing_prior_info",
            "tag_unused_key_info",
            "tag_other_literal",
            "tag_other_bucket",
            "inheritance_issue_event",
        ]
    ].copy()
    calculate_memory_case.insert(0, "source_table", "llm_memory_gemini-2.5-pro__gala_api.xlsx:记忆保持-明细")
    mem_rows = np.arange(2, len(calculate_memory_case) + 2)
    calculate_memory_case["formula_memory_composite_0_1"] = [f"=(G{r}+H{r}+(1-I{r}))/3" for r in mem_rows]
    calculate_memory_case["formula_tag_missing_prior_info"] = [f"=IF(ISNUMBER(SEARCH(\"missing_prior_info\",K{r})),1,0)" for r in mem_rows]
    calculate_memory_case["formula_tag_unused_key_info"] = [f"=IF(ISNUMBER(SEARCH(\"unused_key_info\",K{r})),1,0)" for r in mem_rows]
    calculate_memory_case["formula_tag_other_literal"] = [f"=IF(ISNUMBER(SEARCH(\"other\",K{r})),1,0)" for r in mem_rows]
    calculate_memory_case["formula_tag_other_bucket"] = [
        f"=IF(LEN(K{r})=0,0,IF(LEN(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(K{r},\"missing_prior_info\",\"\"),\"unused_key_info\",\"\"),\"|\",\"\"))>0,1,0))"
        for r in mem_rows
    ]
    calculate_memory_case["formula_inheritance_issue_event"] = [f"=IF(LEN(K{r})=0,0,1)" for r in mem_rows]
    calculate_memory_case["说明_记忆综合分"] = "memory_composite=(继承度+利用率+1-丢失率)/3"
    calculate_memory_case["说明_other收纳"] = "other_bucket=除missing_prior_info与unused_key_info外任意标签"
    calculate_cons_case = consistency[
        [
            "center",
            "model",
            "case_id",
            "model_short",
            "stage4",
            "fact_score_0_1",
            "cross_score_0_1",
            "consistency_score_0_1",
            "fact_tag_contradiction",
            "fact_tag_hallucination",
            "fact_tag_other",
            "fact_event_any",
            "cross_tag_stage_conflict",
            "cross_tag_fact_shift",
            "cross_tag_other",
            "cross_event_any",
        ]
    ].copy()
    calculate_cons_case.insert(0, "source_table", "llm_consistency_gemini-2.5-pro__gala_api.xlsx:一致性-事实/跨阶段-明细")
    cons_rows = np.arange(2, len(calculate_cons_case) + 2)
    calculate_cons_case["formula_fact_event_any"] = [f"=IF(OR(J{r}=1,K{r}=1,L{r}=1),1,0)" for r in cons_rows]
    calculate_cons_case["formula_cross_event_any"] = [f"=IF(OR(N{r}=1,O{r}=1,P{r}=1),1,0)" for r in cons_rows]
    calculate_cons_case["formula_consistency_score_0_1"] = [f"=IF(COUNTA(G{r}:H{r})=0,\"\",AVERAGE(G{r}:H{r}))" for r in cons_rows]
    calculate_cons_case["说明_一致性综合分"] = "consistency_score=mean(事实一致性分,跨阶段一致性分)"
    calculate_reason_component = reasoning[
        [
            "center",
            "model",
            "case_id",
            "model_short",
            "stage_raw",
            "stage4",
            "reasoning_score_1_5",
            "tags_text",
            "event_missing_link",
            "event_over_integration",
            "event_narrative_bias",
            "event_logic_jump",
            "event_other_tag",
            "event_other_bucket",
        ]
    ].copy()
    calculate_reason_component.insert(0, "source_table", "llm_reasoning_gemini-2.5-pro__gala_api.xlsx:推理质量-明细")
    rea_rows = np.arange(2, len(calculate_reason_component) + 2)
    calculate_reason_component["formula_event_missing_link"] = [f"=IF(ISNUMBER(SEARCH(\"missing_link\",I{r})),1,0)" for r in rea_rows]
    calculate_reason_component["formula_event_narrative_bias"] = [f"=IF(ISNUMBER(SEARCH(\"narrative_bias\",I{r})),1,0)" for r in rea_rows]
    calculate_reason_component["formula_event_other_bucket"] = [
        f"=IF(LEN(I{r})=0,0,IF(LEN(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(I{r},\"missing_link\",\"\"),\"narrative_bias\",\"\"),\"|\",\"\"))>0,1,0))"
        for r in rea_rows
    ]
    calculate_reason_component["说明_other收纳"] = "other_bucket=除missing_link与narrative_bias外任意标签"
    # 将关键计算公式前置到明细表，降低跨表追踪成本（仍保留 c_rea_stage 作为 D1/D2 推理聚合口径表）
    formula_ref_map = {
        "c_mem_case": "d_mem_raw",
        "c_cons_case": "d_cons_fact_raw",
        "c_rea_comp": "d_rea_raw",
    }
    summary_memory_score = _rewrite_formula_sheet_refs(summary_memory_score, formula_ref_map)
    summary_consistency_score = _rewrite_formula_sheet_refs(summary_consistency_score, formula_ref_map)
    summary_reasoning_score = _rewrite_formula_sheet_refs(summary_reasoning_score, formula_ref_map)
    mem_prob = _rewrite_formula_sheet_refs(mem_prob, formula_ref_map)
    cons_prob = _rewrite_formula_sheet_refs(cons_prob, formula_ref_map)
    rea_prob = _rewrite_formula_sheet_refs(rea_prob, formula_ref_map)
    mem_tag_stack = _rewrite_formula_sheet_refs(mem_tag_stack, formula_ref_map)
    cons_tag_stack = _rewrite_formula_sheet_refs(cons_tag_stack, formula_ref_map)
    rea_tag_stack = _rewrite_formula_sheet_refs(rea_tag_stack, formula_ref_map)

    detail_mem_export = calculate_memory_case.copy()
    detail_mem_export["说明_明细口径"] = "该表包含记忆原始评分、tag布尔化、事件聚合与公式列。"
    detail_cons_export = calculate_cons_case.copy()
    detail_cons_export["说明_明细口径"] = "该表包含事实/跨阶段一致性评分、tag布尔化、事件聚合与公式列。"
    detail_rea_export = calculate_reason_component.copy()
    detail_rea_export["说明_明细口径"] = "该表包含推理评分、tag布尔化、other收纳桶与公式列。"
    detail_cons_cross_export = consistency_cross_used.copy()
    detail_cons_cross_export["说明_明细口径"] = "保留跨阶段原始明细，便于与 d_cons_fact_raw 的公式化列交叉核对。"

    source_path = _write_source_workbook(
        group=group,
        stem="G3_continuity_metrics_v4",
        sheets={
            "d_mem_raw": detail_mem_export,
            "d_cons_fact_raw": detail_cons_export,
            "d_cons_cross_raw": detail_cons_cross_export,
            "d_rea_raw": detail_rea_export,
            "c_rea_stage": reasoning_stage_score,
            "c_mem_cons_component_model": table_mem_cons_component_model,
            "s_mem_score": summary_memory_score,
            "s_cons_score": summary_consistency_score,
            "s_rea_score": summary_reasoning_score,
            "s_mem_cons_component_stage": table_mem_cons_component_stage,
            "s_mem_events_bool": mem_prob,
            "s_cons_events_bool": cons_prob,
            "s_rea_events_bool": rea_prob,
            "s_mem_events_stack": mem_tag_stack,
            "s_cons_events_stack": cons_tag_stack,
            "s_rea_events_stack": rea_tag_stack,
        },
        meta={
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "figure": str(out_img.relative_to(ROOT)),
            "figure_tagstack": str(out_img_tagstack.relative_to(ROOT)),
            "figure_event_long": str(out_img_event_long.relative_to(ROOT)),
            "figure_component_table_stage": str(out_table_stage.relative_to(ROOT)),
            "figure_component_table_model": str(out_table_model.relative_to(ROOT)),
            "appendix_word_table": str(out_word.relative_to(ROOT)),
            "logic_note_md": str(out_logic_md.relative_to(ROOT)),
            "note": "明细表已并入关键计算公式列；下排事件图按布尔发生概率计算；D1/D2 推理按(loop+decision)/2聚合。",
            "rule_d2_manual": "D2 决策不通过/已退出样本在 G3 中剔除 D3/D4。",
            "source_memory_raw": "analysis_viz/data/raw/llm_memory_gemini-2.5-pro__gala_api.xlsx",
            "source_consistency_raw": "analysis_viz/data/raw/llm_consistency_gemini-2.5-pro__gala_api.xlsx",
            "source_reasoning_raw": "analysis_viz/data/raw/llm_reasoning_gemini-2.5-pro__gala_api.xlsx",
            "source_hint__d_mem_raw": "llm_memory_gemini-2.5-pro__gala_api.xlsx:记忆保持-明细",
            "source_hint__d_cons_fact_raw": "llm_consistency_gemini-2.5-pro__gala_api.xlsx:一致性-事实-明细",
            "source_hint__d_cons_cross_raw": "llm_consistency_gemini-2.5-pro__gala_api.xlsx:一致性-跨阶段-明细",
            "source_hint__d_rea_raw": "llm_reasoning_gemini-2.5-pro__gala_api.xlsx:推理质量-明细",
            "formula_memory_event": "记忆总览三类=missing_prior_info/unused_key_info/other_bucket；other_bucket=除前两类外任意标签。",
            "formula_consistency_event": "事实风险=contradiction/hallucination/other 任一出现；跨阶段风险=stage_conflict/fact_shift/other 任一出现。",
            "formula_reasoning_event": "推理总览三类=missing_link/narrative_bias/other_bucket；D1/D2 概率=(loop概率+decision概率)/2；D3/D4 概率=decision概率。",
            "formula_reasoning_score": "D1/D2得分=(loop均值+decision得分)/2；D3/D4使用决策得分。",
            "formula_memory_consistency_component": "记忆综合分=(继承度+利用率+1-丢失率)/3；一致性综合分=AVERAGE(事实一致性,跨阶段一致性)。",
        },
    )
    _write_caption(
        group,
        [
            "# G3 组图图注",
            "",
            "- `G3_continuity_metrics_v4.png`：上排展示记忆/一致性/推理评分趋势，下排展示对应负面事件发生概率（0-1）。",
            "- `G3_continuity_events_tagstack_v1.png`：负面事件方案一（tag堆叠），展示各标签在阶段层面的发生概率构成。",
            "- `G3_continuity_events_long_v1.png`：替代版将主图上排三项连续评分趋势保留，并把原下排三框负面事件合并为单框总览，便于在同一视图完成“趋势+风险”联合阅读。",
            "- `G3_continuity_component_table_stage_v1.png`：附录表1，按环节展示记忆与一致性的分维度均分（总体）。",
            "- `G3_continuity_component_table_model_stage_v1.png`：附录表2，按模型×环节展示记忆与一致性的分维度均分。",
            "- `G3_continuity_appendix_tables_v1.docx`：附录 Word 表，包含分维度得分表与分阶段异常事件表（总览+细分）。",
            "- `G3_continuity_df_vs_score_logic_note_v1.md`：解释 d-f 事件概率与 a-c 评分并存的统计口径与公式原因。",
            "- 记忆负面事件（总览）固定为三类：`missing_prior_info`、`unused_key_info`、`Other`；其中 `Other` 为除前两类外所有标签的收纳桶。",
            "- 一致性负面事件：事实侧采用 `contradiction/hallucination/other`，跨阶段侧采用 `stage_conflict/fact_shift/other`，均按病例-阶段布尔发生率计算。",
            "- 推理缺陷事件（总览）固定为三类：`missing_link`、`narrative_bias`、`Other`；其中 `Other` 为除前两类外所有标签收纳；D1/D2 按 `(loop概率 + 决策概率) / 2`，D3/D4 按决策阶段概率。",
            "- source data 已提供 `detail + calculate + summary` 三层，汇总sheet均补充公式列，减少跨sheet追踪成本。",
        ],
    )
    keep_fig = {out_img.name, out_img_tagstack.name, out_img_event_long.name, out_table_stage.name, out_table_model.name} | {
        p.name for p in sub_figs.values()
    }
    _archive_group_outputs(group=group, keep_fig_names=keep_fig, keep_source_names={source_path.name})
    return {
        "figure": out_img,
        "figure_tagstack": out_img_tagstack,
        "figure_event_long": out_img_event_long,
        "table_stage": out_table_stage,
        "table_model": out_table_model,
        "appendix_docx": out_word,
        "logic_note": out_logic_md,
        "source": source_path,
        **sub_figs,
    }

def _join_sankey_label(stage: str, status: str) -> str:
    return f"{stage}\n{status}"


def _split_sankey_label(label: str) -> tuple[str, str]:
    text = str(label or "")
    if "\n" in text:
        a, b = text.split("\n", 1)
        return a, b
    if ":" in text:
        a, b = text.split(":", 1)
        return a, b
    stage_names = sorted(set(STAGE6_CN.values()) | {"门诊检查", "门诊决策", "住院检查", "住院决策", "术后决策", "随访与康复计划"}, key=len, reverse=True)
    for s in stage_names:
        if text.startswith(s):
            return s, text[len(s) :]
    return text, text


def _wrap_sankey_status_display(status: str) -> str:
    s = str(status or "")
    repl = {
        "本流程进行前已结束": "流程前已结束",
        "随访与康复计划完成流程": "完成流程",
        "随访与康复计划流程不通过": "流程不通过",
    }
    for k, v in repl.items():
        if s == k:
            return v
    return s


def _simplify_sankey_status(stage_cn: str, status: str) -> str:
    stage_alias = {
        "门诊检查": "门诊检查",
        "门诊决策": "门诊决策",
        "入院检查": "住院检查",
        "入院决策": "住院决策",
        "术后康复": "术后决策",
        "随访计划": "随访与康复计划",
    }.get(stage_cn, stage_cn)
    s = str(status or "").strip()

    # 兼容英文终止态文本，统一为“流程前结束”
    s_low = s.lower()
    if ("fail/terminated" in s_low) or ("terminated" in s_low and "flow" in s_low):
        return _join_sankey_label(stage_alias, "本流程进行前已结束")

    if "未经过（流程终止于入院决策）" in s or "未经过（流程终止于入院检查）" in s:
        return _join_sankey_label(stage_alias, "本流程进行前已结束")

    # 空值/未经过：住院检查按“1轮检查”并入；随访空值视作“流程前结束”
    if not s:
        if stage_alias == "住院检查":
            return _join_sankey_label("住院检查", "1轮检查")
        if stage_alias in {"术后决策", "随访与康复计划"}:
            return _join_sankey_label(stage_alias, "本流程进行前已结束")
        if stage_alias == "随访与康复计划":
            return _join_sankey_label("随访与康复计划", "本流程进行前已结束")
        return _join_sankey_label(stage_alias, "未经过")
    if "未经过" in s:
        if stage_alias == "住院检查":
            return _join_sankey_label("住院检查", "1轮检查")
        if stage_alias in {"术后决策", "随访与康复计划"}:
            return _join_sankey_label(stage_alias, "本流程进行前已结束")
        return _join_sankey_label(stage_alias, "未经过")
    if "特殊" in s:
        return _join_sankey_label(stage_alias, "特殊案例")

    # 住院检查轮次口径：未经过->1轮；X轮->X+1；超3轮/超过4轮->超过4轮；流程不通过单独保留
    if stage_alias == "住院检查":
        # 兼容内部裁剪标签，统一到“超过4轮检查”
        if ("超4轮检查" in s) or ("超过4轮检查" in s):
            return _join_sankey_label("住院检查", "超过4轮检查")
        if ("终止于入院循环" in s) or ("第4轮后" in s):
            return _join_sankey_label("住院检查", "超过4轮检查")
        if "4轮及以上" in s:
            return _join_sankey_label("住院检查", "超过4轮检查")
        if "超3轮" in s:
            return _join_sankey_label("住院检查", "超过4轮检查")
        if "流程不通过" in s or "不通过" in s:
            return _join_sankey_label("住院检查", "流程不通过")
        if "退出" in s or "已退出" in s:
            return _join_sankey_label("住院检查", "流程不通过")
        m_round = re.search(r"通过_(\d+)轮", s)
        if m_round:
            rounds = int(m_round.group(1)) + 1
            if rounds >= 5:
                return _join_sankey_label("住院检查", "超过4轮检查")
            return _join_sankey_label("住院检查", f"{rounds}轮检查")

    # 决策环节“已退出”按不通过处理；其余环节“已退出”视为流程前结束
    if stage_alias == "门诊决策" and "已退出" in s:
        return _join_sankey_label("门诊决策", "不通过")
    if stage_alias in {"住院决策", "术后决策"} and "已退出" in s:
        return _join_sankey_label(stage_alias, "流程不通过")
    if "已退出" in s:
        return _join_sankey_label(stage_alias, "本流程进行前已结束")

    # 退出/不通过语义统一
    if stage_alias == "门诊决策" and "退出" in s:
        return _join_sankey_label("门诊决策", "不通过")
    if "退出" in s:
        return _join_sankey_label(stage_alias, "流程不通过")
    if "二审不通过" in s:
        if stage_alias in {"住院决策", "术后决策"}:
            return _join_sankey_label(stage_alias, "流程不通过")
        return _join_sankey_label(stage_alias, "不通过")
    if ("不通过" in s) and (stage_alias in {"门诊检查", "住院检查", "门诊决策", "住院决策", "术后决策", "随访与康复计划"}):
        return _join_sankey_label(stage_alias, "流程不通过")

    # 检查轮次（门诊）
    if stage_alias == "门诊检查":
        m_round = re.search(r"通过_(\d+)轮", s)
        if m_round:
            return _join_sankey_label("门诊检查", f"{int(m_round.group(1))}轮检查")

    # 决策/计划：统一为可读术语
    if "完全一致" in s:
        return _join_sankey_label(stage_alias, "完全一致")
    if "顺利通过" in s:
        return _join_sankey_label(stage_alias, "完全一致")
    if "高度相似" in s:
        return _join_sankey_label(stage_alias, "高度相似")
    if "包含关系/更精确" in s or "无法判断/包含关系存疑" in s:
        return _join_sankey_label(stage_alias, "部分一致")
    if "部分匹配且合理" in s:
        return _join_sankey_label(stage_alias, "不同但合理")
    if "通过二审_完全不同" in s:
        return _join_sankey_label(stage_alias, "不同但合理")
    if "通过二审" in s or "通过一审" in s or "一审通过" in s:
        return _join_sankey_label(stage_alias, "不同但合理")
    if "完成流程" in s:
        return _join_sankey_label(stage_alias, "完成流程")

    tail = s.split("_")[-1].replace("；", "，").replace(";", "，")
    return _join_sankey_label(stage_alias, tail)


def _sankey_color(label: str, stage_idx: int) -> str:
    stage, status = _split_sankey_label(str(label))

    # 状态分色：未经过 / 流程前结束 / 流程不通过
    if "未经过" in status:
        return "#D6DBE1"
    if "本流程进行前已结束" in status:
        return "#5C6775"
    if "不通过" in status or "超过4轮" in status:
        return "#B22222"
    if "特殊案例" in status:
        return "#8E44AD"

    # 检查阶段：按轮次渐深
    if stage in {"门诊检查", "住院检查"}:
        m = re.search(r"(\d+)轮检查", status)
        if m:
            rn = max(1, min(int(m.group(1)), 5))
            t = (rn - 1) / 4.0
            return _blend_hex_color("#BFE6CF", "#1D8E52", t)
        return "#2CA25F"

    # 决策/计划阶段：按一致性等级渐深
    if stage in {"门诊决策", "住院决策", "术后决策", "随访与康复计划"}:
        rank = {
            "完全一致": 0,
            "高度相似": 1,
            "部分一致": 2,
            "不同但合理": 3,
            "完成流程": 0,
        }.get(status, 2)
        return _blend_hex_color("#CEDCF1", "#316AA5", rank / 3.0)
    return "#3A6EA5"


def _sankey_label_rank(stage_cn: str, label: str, count: int) -> tuple[int, int, str]:
    _, status = _split_sankey_label(str(label))
    # 正常通过置顶，未经过/流程前结束与不通过置底（其中流程前结束最底）
    if any(k in status for k in ["不通过", "超过4轮"]):
        return (90, -int(count), status)
    if "本流程进行前已结束" in status:
        return (99, -int(count), status)
    if "未经过" in status:
        return (95, -int(count), status)
    if "特殊案例" in status:
        return (70, -int(count), status)
    m = re.search(r"(\d+)轮检查", status)
    if m:
        return (10 + int(m.group(1)), -int(count), status)
    status_rank = {
        "完全一致": 20,
        "高度相似": 22,
        "部分一致": 24,
        "不同但合理": 28,
        "完成流程": 30,
    }
    return (status_rank.get(status, 40), -int(count), status)


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return f"rgba(100,100,100,{alpha})"
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _prepare_sankey_flow_detail(detail_used: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    stage_cols = ["门诊检查", "门诊决策", "入院检查", "入院决策", "术后康复", "随访计划"]
    work = detail_used.copy()

    if "is_d1_anomaly" in work.columns:
        d1_anomaly = work["is_d1_anomaly"].astype(str).str.lower().isin({"true", "1", "yes", "y"})
        work = work[~d1_anomaly].copy()

    for col in stage_cols:
        work[col] = work[col].fillna("").astype(str)

    if "d2_dec_status_raw" in work.columns:
        raw_dec = work["d2_dec_status_raw"].fillna("").astype(str).str.strip()
        cur_dec = work["入院决策"].fillna("").astype(str).str.strip()
        raw_pass = raw_dec.str.contains("通过二审|二审通过|通过一审|一审通过|顺利通过|完成流程", regex=True)
        raw_fail = raw_dec.str.contains("二审不通过|流程不通过|已退出|退出|不通过", regex=True) & ~raw_pass
        cur_pass = cur_dec.str.contains("通过二审|二审通过|通过一审|一审通过|顺利通过|完全一致|高度相似|部分一致|不同但合理|完成流程", regex=True)
        cur_fail = cur_dec.str.contains("二审不通过|流程不通过|已退出|退出|不通过", regex=True) & ~cur_pass
        need_fix = raw_dec.ne("") & ((raw_pass & cur_fail) | (raw_fail & cur_pass) | cur_dec.eq(""))
        work.loc[need_fix, "入院决策"] = raw_dec.loc[need_fix]

    d1_dec_raw = work["门诊决策"].fillna("").astype(str)
    d1_pass = d1_dec_raw.str.contains("通过|顺利通过|完全一致|高度相似|部分一致|不同但合理|完成流程", regex=True)
    d1_fail = d1_dec_raw.str.contains("不通过|流程不通过|退出|已退出", regex=True) & ~d1_pass
    work.loc[d1_fail, "入院检查"] = "本流程进行前已结束"
    work.loc[d1_fail, "入院决策"] = "本流程进行前已结束"
    work.loc[d1_fail, "术后康复"] = "本流程进行前已结束"
    work.loc[d1_fail, "随访计划"] = "本流程进行前已结束"

    d2_dec_raw = work["入院决策"].fillna("").astype(str)
    d2_loop_raw = work["入院检查"].fillna("").astype(str)
    if "d2_loop_status_raw" in work.columns:
        d2_loop_ref = work["d2_loop_status_raw"].fillna("").astype(str)
        d2_loop_ref = d2_loop_ref.where(d2_loop_ref.str.strip().ne(""), d2_loop_raw)
    else:
        d2_loop_ref = d2_loop_raw
    if "d2_force_stop" in work.columns:
        d2_force_stop = work["d2_force_stop"].fillna(False).astype(bool)
    else:
        d2_pass = d2_dec_raw.str.contains("通过二审|二审通过|通过一审|一审通过|顺利通过|完成流程", regex=True)
        d2_force_stop = d2_dec_raw.str.contains("二审不通过|流程不通过|已退出|退出|不通过", regex=True) & ~d2_pass
    if "d2_dec_status_fixed" in work.columns:
        d2_dec_fixed = work["d2_dec_status_fixed"].fillna("").astype(str)
        use_fixed = d2_force_stop & d2_dec_fixed.str.strip().ne("")
        work.loc[use_fixed, "入院决策"] = d2_dec_fixed.loc[use_fixed]
    work.loc[d2_force_stop, "术后康复"] = "本流程进行前已结束"
    work.loc[d2_force_stop, "随访计划"] = "本流程进行前已结束"

    if "d2_check_force_fail" in work.columns:
        d2_check_force_fail = work["d2_check_force_fail"].fillna(False).astype(bool)
    else:
        d2_check_force_fail = d2_force_stop & d2_loop_ref.str.contains("未经过", regex=False)
    d2_check_force_fail = d2_check_force_fail | (d2_force_stop & d2_loop_ref.str.contains("未经过", regex=False))
    work.loc[d2_check_force_fail, "术后康复"] = "本流程进行前已结束"
    work.loc[d2_check_force_fail, "随访计划"] = "本流程进行前已结束"

    d2_loop_norm = d2_loop_ref.apply(lambda s: _split_sankey_label(_simplify_sankey_status("入院检查", str(s)))[1])
    d2_loop_terminal = d2_loop_norm.isin(["超过4轮检查", "流程不通过"])
    work.loc[d2_loop_terminal, "入院决策"] = "本流程进行前已结束"
    work.loc[d2_loop_terminal, "术后康复"] = "本流程进行前已结束"
    work.loc[d2_loop_terminal, "随访计划"] = "本流程进行前已结束"

    work_pretty = work.copy()
    return work, work_pretty


def _build_stage_case_sets_from_sankey_detail(detail_used: pd.DataFrame) -> dict[str, set[tuple[str, str, str]]]:
    _, work_pretty = _prepare_sankey_flow_detail(detail_used)
    key_cols = ["center", "model", "case_id"]
    if any(c not in work_pretty.columns for c in key_cols):
        return {stage: set() for stage in ["D1", "D2", "D3", "D4"]}

    def _to_keys(frame: pd.DataFrame) -> set[tuple[str, str, str]]:
        if frame.empty:
            return set()
        return set(map(tuple, frame[key_cols].astype(str).itertuples(index=False, name=None)))

    return {
        "D1": _to_keys(work_pretty),
        "D2": _to_keys(work_pretty[~work_pretty["入院决策"].astype(str).str.contains("本流程进行前已结束", regex=False)]),
        "D3": _to_keys(work_pretty[~work_pretty["术后康复"].astype(str).str.contains("本流程进行前已结束", regex=False)]),
        "D4": _to_keys(work_pretty[work_pretty["随访计划"].astype(str).eq("D4康复_完成流程")]),
    }


def _load_stage_case_sets_from_sankey_source(d2_rule_map: pd.DataFrame) -> dict[str, set[tuple[str, str, str]]]:
    sankey_detail = pd.read_excel(PAPER_FIGDATA_DIR / "Fig7__sankey_flow_source.xlsx", sheet_name="detail_used")
    sankey_detail = _attach_d2_manual_rules(sankey_detail, d2_rule_map)
    return _build_stage_case_sets_from_sankey_detail(sankey_detail)


def _filter_stage_case_eligibility(
    df: pd.DataFrame,
    stage_col: str,
    stage_case_sets: dict[str, set[tuple[str, str, str]]],
) -> pd.DataFrame:
    if df.empty or stage_col not in df.columns or not stage_case_sets:
        return df
    key_cols = ["center", "model", "case_id"]
    if any(c not in df.columns for c in key_cols):
        return df
    out = df.copy()
    keys = list(map(tuple, out[key_cols].astype(str).itertuples(index=False, name=None)))
    stages = out[stage_col].astype(str).tolist()
    keep_mask = [key in stage_case_sets.get(stage, set()) for key, stage in zip(keys, stages)]
    return out.loc[pd.Series(keep_mask, index=out.index)].copy()


def _build_sankey_figure(detail_used: pd.DataFrame, out_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    stage_cols = ["门诊检查", "门诊决策", "入院检查", "入院决策", "术后康复", "随访计划"]
    stage_header = {
        "门诊检查": "门诊检查",
        "门诊决策": "门诊决策",
        "入院检查": "住院检查",
        "入院决策": "住院决策",
        "术后康复": "术后决策",
        "随访计划": "随访与康复计划",
    }
    work, work_pretty = _prepare_sankey_flow_detail(detail_used)

    for col in stage_cols:
        work[col] = work[col].apply(lambda s: _simplify_sankey_status(col, s))

    node_rows: list[dict[str, Any]] = []
    link_rows: list[dict[str, Any]] = []
    stage_nodes: dict[str, list[str]] = {}
    stage_counts: dict[str, dict[str, int]] = {}
    for col in stage_cols:
        vc = work[col].value_counts()
        labels = sorted(vc.index.tolist(), key=lambda lb: _sankey_label_rank(col, str(lb), int(vc[lb])))
        stage_nodes[col] = labels
        stage_counts[col] = {str(lb): int(vc[lb]) for lb in labels}
        for label in labels:
            node_rows.append({"stage": col, "label": label, "n_cases": int(vc[label])})

    for a, b in zip(stage_cols[:-1], stage_cols[1:]):
        sub = work[[a, b]].copy()
        sub = sub[(sub[a].str.strip() != "") & (sub[b].str.strip() != "")]
        if sub.empty:
            continue
        gb = sub.groupby([a, b], as_index=False).size().rename(columns={"size": "n_cases"})
        gb["from_stage"] = a
        gb["to_stage"] = b
        gb = gb.rename(columns={a: "from_label", b: "to_label"})
        link_rows.extend(gb.to_dict(orient="records"))

    node_df = pd.DataFrame(node_rows)
    link_df = pd.DataFrame(link_rows)
    expected_n = int(len(work))
    if not node_df.empty:
        stage_total_map = node_df.groupby("stage", as_index=False)["n_cases"].sum().set_index("stage")["n_cases"].to_dict()
        node_df["stage_total"] = node_df["stage"].map(stage_total_map)
        node_df["stage_total_equals_n"] = node_df["stage_total"].eq(expected_n)
        rr = np.arange(2, len(node_df) + 2)
        stage_match_expr = '{"门诊检查","门诊决策","入院检查","入院决策","术后康复","随访计划"}'
        detail_stage_choose = (
            "'明细_桑基_已用'!$E:$E,'明细_桑基_已用'!$F:$F,'明细_桑基_已用'!$G:$G,"
            "'明细_桑基_已用'!$H:$H,'明细_桑基_已用'!$I:$I,'明细_桑基_已用'!$J:$J"
        )
        node_df["formula_n_cases"] = [
            (
                f"=IFERROR(SUMPRODUCT(--(CHOOSE(MATCH($B{r},{stage_match_expr},0),{detail_stage_choose})="
                f'IFERROR(MID($C{r},FIND(CHAR(10),$C{r})+1,99),$C{r}))),0)'
            )
            for r in rr
        ]
        node_df["formula_stage_total"] = [
            f"=IFERROR(SUMPRODUCT(--(CHOOSE(MATCH($B{r},{stage_match_expr},0),{detail_stage_choose})<>\"\")),0)"
            for r in rr
        ]
        node_df["formula_stage_total_equals_n"] = [f"=E{r}={expected_n}" for r in rr]
        node_df["说明"] = "n_cases=由明细_桑基_已用按(阶段,标签)重算；stage_total=阶段总样本数；stage_total_equals_n用于检查各列样本总量一致性"
    if not link_df.empty:
        rr_l = np.arange(2, len(link_df) + 2)
        stage_match_expr = '{"门诊检查","门诊决策","入院检查","入院决策","术后康复","随访计划"}'
        detail_stage_choose = (
            "'明细_桑基_已用'!$E:$E,'明细_桑基_已用'!$F:$F,'明细_桑基_已用'!$G:$G,"
            "'明细_桑基_已用'!$H:$H,'明细_桑基_已用'!$I:$I,'明细_桑基_已用'!$J:$J"
        )
        link_df["formula_n_cases"] = [
            (
                f"=IFERROR(SUMPRODUCT("
                f"--(CHOOSE(MATCH($E{r},{stage_match_expr},0),{detail_stage_choose})=IFERROR(MID($B{r},FIND(CHAR(10),$B{r})+1,99),$B{r})),"
                f"--(CHOOSE(MATCH($F{r},{stage_match_expr},0),{detail_stage_choose})=IFERROR(MID($C{r},FIND(CHAR(10),$C{r})+1,99),$C{r}))"
                f"),0)"
            )
            for r in rr_l
        ]
        link_df["formula_from_stage_total"] = [
            f"=IFERROR(SUMPRODUCT(--(CHOOSE(MATCH($E{r},{stage_match_expr},0),{detail_stage_choose})<>\"\")),0)"
            for r in rr_l
        ]
        link_df["formula_to_stage_total"] = [
            f"=IFERROR(SUMPRODUCT(--(CHOOSE(MATCH($F{r},{stage_match_expr},0),{detail_stage_choose})<>\"\")),0)"
            for r in rr_l
        ]
        link_df["说明"] = "连线n_cases=由明细_桑基_已用按(from_stage,from_label,to_stage,to_label)重算；from/to_stage_total用于核对两端阶段样本量"
    if go is None:
        return node_df, link_df, work, work_pretty

    x_pad = 0.022
    x_span = 0.82
    stage_x = {col: x_pad + idx * (x_span / max(1, len(stage_cols) - 1)) for idx, col in enumerate(stage_cols)}
    node_index: dict[tuple[str, str], int] = {}
    labels: list[str] = []
    node_case_counts: list[int] = []
    node_stage_names: list[str] = []
    colors: list[str] = []
    xs: list[float] = []
    ys: list[float] = []
    idx = 0
    for s_idx, col in enumerate(stage_cols):
        labels_in_stage = stage_nodes.get(col, [])
        n = max(1, len(labels_in_stage))
        counts = [int(stage_counts.get(col, {}).get(str(lb), 0)) for lb in labels_in_stage]
        total = float(sum(counts)) if sum(counts) > 0 else 1.0
        gap = 0.005
        total_gaps = gap * max(0, n - 1)
        # 将节点上下铺开，给外置标签腾出真实垂直空间。
        vertical_pad = 0.09 if n <= 4 else (0.07 if n <= 6 else 0.05)
        available = max(0.68, min(0.84, 1.0 - total_gaps - 2.0 * vertical_pad))
        y_start = max(vertical_pad, (1.0 - (available + total_gaps)) / 2.0)
        cur = y_start
        for j, label in enumerate(labels_in_stage):
            frac = (counts[j] / total) * available if total > 0 else (1.0 / n) * available
            y_center = cur + frac / 2.0
            node_index[(col, label)] = idx
            labels.append(label)
            node_case_counts.append(int(counts[j]))
            node_stage_names.append(col)
            colors.append(_sankey_color(label, s_idx))
            xs.append(stage_x[col])
            ys.append(float(min(0.95, max(0.05, y_center))))
            idx += 1
            cur += frac + (gap if j < (n - 1) else 0.0)

    src: list[int] = []
    tar: list[int] = []
    val: list[float] = []
    lcolors: list[str] = []
    for _, r in link_df.iterrows():
        key_a = (str(r["from_stage"]), str(r["from_label"]))
        key_b = (str(r["to_stage"]), str(r["to_label"]))
        if key_a not in node_index or key_b not in node_index:
            continue
        src.append(node_index[key_a])
        tar.append(node_index[key_b])
        val.append(float(r["n_cases"]))
        base_color = colors[node_index[key_a]]
        lcolors.append(_hex_to_rgba(base_color, 0.35))

    stage_total_map = (
        node_df.groupby("stage", as_index=False)["n_cases"].sum().set_index("stage")["n_cases"].to_dict()
        if not node_df.empty
        else {}
    )
    node_count = max(1, len(labels))
    max_nodes_per_stage = max((len(v) for v in stage_nodes.values()), default=1)
    if node_count <= 24:
        node_font_size = 20
    elif node_count <= 32:
        node_font_size = 19
    elif node_count <= 42:
        node_font_size = 18
    else:
        node_font_size = 17
    if max_nodes_per_stage >= 8:
        node_font_size = max(16, node_font_size - 1)
    header_font_size = max(16, min(20, node_font_size + 1))
    layout_font_size = max(13, node_font_size)
    sankey_text_font_size = max(15, node_font_size - 1)
    node_thickness = 30 if node_font_size >= 19 else (28 if node_font_size >= 17 else 26)
    node_pad = 18 if max_nodes_per_stage <= 6 else 16
    canvas_width = 1760 if node_count <= 34 else 1880
    canvas_height = 1360 if max_nodes_per_stage <= 6 else 1500

    header_annotations = []
    for col in stage_cols:
        header_annotations.append(
            dict(
                x=stage_x[col],
                y=1.015,
                xref="paper",
                yref="paper",
                text=f"<b>{stage_header.get(col, col)}</b>",
                showarrow=False,
                align="center",
                font=dict(size=header_font_size, color="#223247"),
            )
        )
    def _spread_label_positions(raw_positions: list[float], min_gap: float, lower: float = 0.055, upper: float = 0.945) -> list[float]:
        if not raw_positions:
            return []
        indexed = sorted(enumerate(raw_positions), key=lambda item: item[1])
        placed: list[list[float]] = []
        cursor = lower
        for idx_pos, y_pos in indexed:
            y_new = max(float(y_pos), cursor)
            placed.append([float(idx_pos), y_new])
            cursor = y_new + float(min_gap)
        overflow = placed[-1][1] - upper
        if overflow > 0:
            for item in placed:
                item[1] -= overflow
            for i in range(len(placed) - 2, -1, -1):
                if placed[i + 1][1] - placed[i][1] < min_gap:
                    placed[i][1] = placed[i + 1][1] - min_gap
            if placed[0][1] < lower:
                shift = lower - placed[0][1]
                for item in placed:
                    item[1] += shift
        out = [0.0] * len(raw_positions)
        for idx_pos, y_pos in placed:
            out[int(idx_pos)] = float(max(lower, min(upper, y_pos)))
        return out

    # 使用 Plotly 节点原生标签，保证标签贴在对应节点/流程旁，而不是悬浮在统一文本列。
    display_labels = [_wrap_sankey_status_display(_split_sankey_label(lb)[1]) for lb in labels]
    node_text_annotations: list[dict[str, Any]] = []

    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="fixed",
                textfont=dict(
                    size=sankey_text_font_size,
                    family="Microsoft YaHei, SimHei, Arial Unicode MS",
                    color="#1E2F45",
                ),
                node=dict(
                    pad=node_pad,
                    thickness=node_thickness,
                    line=dict(color="rgba(255,255,255,0.95)", width=1.1),
                    label=display_labels,
                    color=colors,
                    x=xs,
                    y=ys,
                ),
                link=dict(source=src, target=tar, value=val, color=lcolors),
            )
        ]
    )
    fig.update_layout(
        title_text="",
        font=dict(size=layout_font_size, family="Microsoft YaHei, SimHei, Arial Unicode MS"),
        width=canvas_width,
        height=canvas_height,
        margin=dict(l=24, r=72, t=68, b=120),
        paper_bgcolor="white",
        annotations=header_annotations + node_text_annotations,
        shapes=[
            dict(
                type="rect",
                xref="paper",
                yref="paper",
                x0=0,
                y0=0,
                x1=1,
                y1=1,
                line=dict(color="rgba(255,255,255,1.0)", width=10),
                fillcolor="rgba(0,0,0,0)",
                layer="above",
            )
        ],
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not _save_plotly_image_bundle(fig, out_path, scale=1):
        fig.write_html(str(out_path.with_suffix(".html")), include_plotlyjs="cdn")
    return node_df, link_df, work, work_pretty


def _build_sankey_arrow_rect_figure(
    node_df: pd.DataFrame,
    link_df: pd.DataFrame,
    out_path: Path,
    max_nodes_per_stage: int = 7,
) -> None:
    """替代版流程图：箭头+长方形节点，节点左侧显示样本数，右侧显示状态文本。"""
    stage_cols = ["门诊检查", "门诊决策", "入院检查", "入院决策", "术后康复", "随访计划"]
    stage_header = {
        "门诊检查": "门诊检查",
        "门诊决策": "门诊决策",
        "入院检查": "住院检查",
        "入院决策": "住院决策",
        "术后康复": "术后决策",
        "随访计划": "随访与康复计划",
    }
    fig, ax = plt.subplots(figsize=(23.0, 12.0))
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.axis("off")

    if node_df.empty or link_df.empty:
        ax.text(0.5, 0.5, "无可绘制流程数据", ha="center", va="center", fontsize=14)
        _save_fig(out_path, apply_tight=False)
        return

    node_work = node_df.copy()
    node_work["stage"] = node_work["stage"].astype(str)
    node_work["label"] = node_work["label"].astype(str)
    node_work["n_cases"] = pd.to_numeric(node_work["n_cases"], errors="coerce").fillna(0.0)
    node_work = node_work[node_work["stage"].isin(stage_cols)].copy()
    if node_work.empty:
        ax.text(0.5, 0.5, "无可绘制流程数据", ha="center", va="center", fontsize=14)
        _save_fig(out_path, apply_tight=False)
        return

    # 每阶段仅保留前若干高频状态，尾部合并为“其他状态”，提升可读性。
    collapsed_rows: list[dict[str, Any]] = []
    stage_label_map: dict[str, dict[str, str]] = {}
    for stage in stage_cols:
        sub = node_work[node_work["stage"] == stage].copy()
        if sub.empty:
            continue
        sub = sub.sort_values("n_cases", ascending=False, kind="mergesort").reset_index(drop=True)
        keep_n = max(3, int(max_nodes_per_stage) - 1)
        keep_labels = sub["label"].head(keep_n).tolist()
        stage_label_map[stage] = {}
        for lb in sub["label"].tolist():
            stage_label_map[stage][str(lb)] = str(lb) if str(lb) in keep_labels else _join_sankey_label(stage, "其他状态")
        kept = sub[sub["label"].isin(keep_labels)].copy()
        other_sum = float(sub.loc[~sub["label"].isin(keep_labels), "n_cases"].sum())
        collapsed_rows.extend(
            [{"stage": stage, "label": str(r["label"]), "n_cases": float(r["n_cases"])} for _, r in kept.iterrows()]
        )
        if other_sum > 0:
            collapsed_rows.append({"stage": stage, "label": _join_sankey_label(stage, "其他状态"), "n_cases": other_sum})

    draw_nodes = pd.DataFrame(collapsed_rows)
    draw_nodes = (
        draw_nodes.groupby(["stage", "label"], as_index=False)["n_cases"]
        .sum()
        .sort_values(["stage", "n_cases"], ascending=[True, False], kind="mergesort")
        .reset_index(drop=True)
    )
    if draw_nodes.empty:
        ax.text(0.5, 0.5, "无可绘制流程数据", ha="center", va="center", fontsize=14)
        _save_fig(out_path, apply_tight=False)
        return

    link_work = link_df.copy()
    link_work["from_stage"] = link_work["from_stage"].astype(str)
    link_work["to_stage"] = link_work["to_stage"].astype(str)
    link_work["from_label"] = link_work["from_label"].astype(str)
    link_work["to_label"] = link_work["to_label"].astype(str)
    link_work["n_cases"] = pd.to_numeric(link_work["n_cases"], errors="coerce").fillna(0.0)
    link_work = link_work[
        link_work["from_stage"].isin(stage_cols) & link_work["to_stage"].isin(stage_cols)
    ].copy()
    link_work["from_label_draw"] = link_work.apply(
        lambda r: stage_label_map.get(str(r["from_stage"]), {}).get(str(r["from_label"]), str(r["from_label"])),
        axis=1,
    )
    link_work["to_label_draw"] = link_work.apply(
        lambda r: stage_label_map.get(str(r["to_stage"]), {}).get(str(r["to_label"]), str(r["to_label"])),
        axis=1,
    )
    link_work = (
        link_work.groupby(
            ["from_stage", "to_stage", "from_label_draw", "to_label_draw"], as_index=False
        )["n_cases"]
        .sum()
        .rename(columns={"from_label_draw": "from_label", "to_label_draw": "to_label"})
    )

    rect_w = 0.058
    x_left = 0.09
    x_right = 0.82
    x_step = (x_right - x_left) / max(1, len(stage_cols) - 1)
    stage_x_center = {stage: x_left + idx * x_step for idx, stage in enumerate(stage_cols)}
    min_h = 0.02
    gap = 0.008
    y_lower, y_upper = 0.06, 0.94
    usable_h = y_upper - y_lower

    node_pos: dict[tuple[str, str], dict[str, float]] = {}
    for s_idx, stage in enumerate(stage_cols):
        sub = draw_nodes[draw_nodes["stage"] == stage].copy()
        if sub.empty:
            continue
        sub["rank_key"] = sub.apply(
            lambda r: _sankey_label_rank(stage, str(r["label"]), int(round(float(r["n_cases"])))), axis=1
        )
        sub = sub.sort_values(["rank_key", "n_cases"], ascending=[True, False], kind="mergesort").reset_index(drop=True)
        vals = pd.to_numeric(sub["n_cases"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        total = float(vals.sum()) if float(vals.sum()) > 0 else 1.0
        heights = np.maximum((vals / total) * (usable_h - gap * max(0, len(sub) - 1)), min_h)
        if float(heights.sum()) + gap * max(0, len(sub) - 1) > usable_h:
            scale = (usable_h - gap * max(0, len(sub) - 1)) / float(heights.sum())
            heights = heights * max(0.2, scale)
        cur_top = y_upper
        for idx_row, (_, row) in enumerate(sub.iterrows()):
            h = float(heights[idx_row])
            y1 = cur_top
            y0 = max(y_lower, y1 - h)
            yc = (y0 + y1) / 2.0
            x_center = stage_x_center[stage]
            x0 = x_center - rect_w / 2.0
            x1 = x_center + rect_w / 2.0
            label = str(row["label"])
            color = _sankey_color(label, s_idx)
            node_pos[(stage, label)] = {
                "x0": x0,
                "x1": x1,
                "y0": y0,
                "y1": y1,
                "yc": yc,
                "n": float(row["n_cases"]),
                "color": color,
            }
            rect = FancyBboxPatch(
                (x0, y0),
                rect_w,
                max(0.0075, y1 - y0),
                boxstyle="round,pad=0.003,rounding_size=0.004",
                facecolor=color,
                edgecolor="#FFFFFF",
                linewidth=0.9,
                alpha=0.93,
                zorder=3,
            )
            ax.add_patch(rect)
            status_text = _wrap_sankey_status_display(_split_sankey_label(label)[1])
            ax.text(x0 - 0.008, yc, f"{int(round(float(row['n_cases'])))}", ha="right", va="center", fontsize=8.4, color="#233549")
            ax.text(x1 + 0.008, yc, status_text, ha="left", va="center", fontsize=8.0, color="#1E2F45")
            cur_top = y0 - gap

    # 绘制主要连线：每个阶段对仅保留高频连线，避免完全重叠。
    link_draw_rows: list[pd.DataFrame] = []
    for a, b in zip(stage_cols[:-1], stage_cols[1:]):
        pair = link_work[(link_work["from_stage"] == a) & (link_work["to_stage"] == b)].copy()
        if pair.empty:
            continue
        pair = pair.sort_values("n_cases", ascending=False, kind="mergesort").reset_index(drop=True)
        threshold = max(8.0, float(pair["n_cases"].sum()) * 0.01)
        keep = pair[pair["n_cases"] >= threshold].head(20)
        if keep.empty:
            keep = pair.head(10)
        link_draw_rows.append(keep)
    link_draw = pd.concat(link_draw_rows, ignore_index=True) if link_draw_rows else pd.DataFrame()
    max_link = float(pd.to_numeric(link_draw.get("n_cases", pd.Series(dtype=float)), errors="coerce").max()) if not link_draw.empty else 1.0
    if not np.isfinite(max_link) or max_link <= 0:
        max_link = 1.0
    for _, row in link_draw.iterrows():
        key_a = (str(row["from_stage"]), str(row["from_label"]))
        key_b = (str(row["to_stage"]), str(row["to_label"]))
        if key_a not in node_pos or key_b not in node_pos:
            continue
        a = node_pos[key_a]
        b = node_pos[key_b]
        n_cases = float(pd.to_numeric(row.get("n_cases"), errors="coerce"))
        if not np.isfinite(n_cases) or n_cases <= 0:
            continue
        lw = 0.5 + 4.8 * (n_cases / max_link) ** 0.75
        base_rgb = to_rgb(str(a["color"]))
        arrow = FancyArrowPatch(
            (a["x1"] + 0.004, a["yc"]),
            (b["x0"] - 0.004, b["yc"]),
            arrowstyle="-|>",
            mutation_scale=6.0 + 10.0 * (n_cases / max_link),
            linewidth=lw,
            color=(base_rgb[0], base_rgb[1], base_rgb[2], 0.25),
            connectionstyle="arc3,rad=0.0",
            zorder=1,
        )
        ax.add_patch(arrow)

    for stage in stage_cols:
        x = stage_x_center[stage]
        ax.text(
            x,
            0.978,
            stage_header.get(stage, stage),
            ha="center",
            va="bottom",
            fontsize=12.5,
            color="#1F2D3D",
            fontweight="bold",
        )
    ax.text(0.01, 0.985, "节点左侧为样本数", ha="left", va="top", fontsize=9.0, color="#4A5568")
    ax.text(0.01, 0.955, "仅展示高频状态与主要流向，低频状态合并为“其他状态”", ha="left", va="top", fontsize=8.5, color="#6B7280")
    _save_fig(out_path, apply_tight=False)


def build_g4_system(
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
    d2_rule_map: pd.DataFrame,
) -> dict[str, Path]:
    _ensure_style()
    group = "G4_system"
    out_sankey = OUT_FIG_DIR / group / "G4A_sankey_all_center_model_v3.png"
    out_sankey_arrow_rect = OUT_FIG_DIR / group / "G4A_sankey_arrow_rect_v1.png"
    out_calib = OUT_FIG_DIR / group / "G4B_calibration_binned_stage_v3.png"
    out_calib_path = OUT_FIG_DIR / group / "G4B2_calibration_pathways_curve_v2.png"
    out_calib_diag_type = OUT_FIG_DIR / group / "G4B3_calibration_diag_decision_types_v1.png"
    out_calib_check_round = OUT_FIG_DIR / group / "G4B4_calibration_check_rounds_v1.png"
    out_calib_plan_type = OUT_FIG_DIR / group / "G4B5_calibration_plan_decision_types_v1.png"
    out_pass = OUT_FIG_DIR / group / "G4C_pass_rate_check_efficiency_v2.png"
    out_eff_scatter = OUT_FIG_DIR / group / "G4C2_efficiency_info_gain_scatter_v2.png"
    out_group_flow_pass = OUT_FIG_DIR / group / "G4_groupA_flow_pass_v2.png"
    out_group_flow_gain = OUT_FIG_DIR / group / "G4_groupB_flow_info_gain_v2.png"
    out_group_calib_suite = OUT_FIG_DIR / group / "G4_groupC_calibration_suite_v2.png"
    out_calib_overall_v4 = OUT_FIG_DIR / group / "G4B_calibration_stage_overall_v5.png"
    out_calib_overall_v5 = OUT_FIG_DIR / group / "G4B_calibration_overall_weighted_v6.png"
    out_calib_overall_stage = OUT_FIG_DIR / group / "G4B_calibration_overall_stage_v2.png"
    out_calib_stage_points = OUT_FIG_DIR / group / "G4B_stage_calibration_points_v1.png"
    out_calib_stage_table = OUT_FIG_DIR / group / "G4B_stage_calibration_table_v2.png"
    out_eff_box_v5 = OUT_FIG_DIR / group / "G4C_check_efficiency_box_v5.png"
    out_eff_panel = OUT_FIG_DIR / group / "G4C2_check_efficiency_panel_v2.png"
    out_ablation_main_c = OUT_FIG_DIR / group / "G4C_ablation_diag_dumbbell_v1.png"
    out_check_gain_panel = OUT_FIG_DIR / group / "G4C3_check_gain_marginal_info_panel_v2.png"
    out_check_gain_shift_panel = OUT_FIG_DIR / group / "G4C3_check_gain_decision_shift_panel_v1.png"
    out_final_dx_round_strata_panel = OUT_FIG_DIR / group / "G4C4_check_rounds_final_dx_proximity_panel_v1.png"
    out_final_dx_gain_round_panel = OUT_FIG_DIR / group / "G4C5_check_rounds_final_dx_gain_panel_v1.png"
    out_final_dx_gain_model_panel = OUT_FIG_DIR / group / "G4C6_check_rounds_final_dx_gain_model_v1.png"
    out_final_dx_admission_info_gain_panel = OUT_FIG_DIR / group / "G4C7_admission_info_vs_dx_gain_model_v1.png"
    out_check_gain_table = OUT_FIG_DIR / group / "G4C3_check_gain_summary_table_v2.png"
    out_group_ref_v5 = OUT_FIG_DIR / group / "G4_groupD_sankey_calib_efficiency_v5.png"
    out_group_ref_v6 = OUT_FIG_DIR / group / "G4_groupD_sankey_calib_efficiency_v7.png"
    out_special_case = OUT_FIG_DIR / group / "G4C_special_case_count_v1.png"
    out_group_special = OUT_FIG_DIR / group / "G4_groupE_sankey_calib_special_v2.png"
    ablation_overall_src = OUT_SUPPLE_DIR / "ablation" / "figures" / "ablation_dumbbell_overall_v2.png"

    sankey_detail = pd.read_excel(PAPER_FIGDATA_DIR / "Fig7__sankey_flow_source.xlsx", sheet_name="detail_used")
    sankey_detail = _attach_d2_manual_rules(sankey_detail, d2_rule_map)
    stage_case_sets = _build_stage_case_sets_from_sankey_detail(sankey_detail)
    node_df, link_df, sankey_mapped, sankey_detail_fixed = _build_sankey_figure(sankey_detail, out_sankey)
    _build_sankey_arrow_rect_figure(node_df, link_df, out_sankey_arrow_rect)

    # B1: D1-D4 分箱气泡校准散点（气泡大小=分箱样本量）
    calib = pd.read_excel(
        DERIVED_METRICS_DIR / "calibration" / "calibration_reliability_stagewise_source.xlsx",
        sheet_name="bin_summary_used",
    )
    calib_case = pd.read_excel(
        DERIVED_METRICS_DIR / "calibration" / "calibration_reliability_stagewise_source.xlsx",
        sheet_name="detail_used",
    )
    calib_case["model_short"] = calib_case["model"].map(MODEL_SHORT).fillna(calib_case["model"].astype(str))
    calib_case["stage4"] = calib_case["stage"].map(_stage4_map)
    calib_case = calib_case[calib_case["stage4"].isin(["D1", "D2", "D3", "D4"])].copy()
    calib_case = _filter_stage_case_eligibility(calib_case, "stage4", stage_case_sets)
    calib_case["confidence"] = pd.to_numeric(calib_case["confidence"], errors="coerce")
    calib_case["accuracy"] = pd.to_numeric(calib_case["accuracy"], errors="coerce")
    calib_case = calib_case.dropna(subset=["confidence", "accuracy"])
    calib_case["bin_calc"] = pd.cut(
        calib_case["confidence"].astype(float),
        bins=np.round(np.arange(0.0, 1.01, 0.1), 1),
        include_lowest=True,
        right=True,
    ).astype(str)
    calib_case["bin_calc"] = calib_case["bin_calc"].replace({"(-0.001, 0.1]": "(0.0, 0.1]"})
    calib_case.insert(0, "source_path", "analysis_viz/data/derived/metrics/calibration/calibration_reliability_stagewise_source.xlsx")
    calib_case.insert(1, "source_sheet", "detail_used")
    calib = (
        calib_case.assign(bin=calib_case["bin_calc"])
        .groupby(["center", "model", "model_short", "stage", "stage_cn", "category", "bin", "stage4"], as_index=False)
        .agg(
            conf=("confidence", "mean"),
            acc=("accuracy", "mean"),
            n=("case_id", "count"),
            n_cases=("case_id", "nunique"),
        )
        .sort_values(["center", "model_short", "stage", "bin"], kind="mergesort")
        .reset_index(drop=True)
    )

    stage_bin_model = (
        calib.groupby(["stage4", "model_short", "bin"], as_index=False)
        .agg(conf=("conf", "mean"), acc=("acc", "mean"), n=("n", "sum"))
        .sort_values(["stage4", "model_short", "bin"], kind="mergesort")
    )
    stage_bin_overall = (
        calib.groupby(["stage4", "bin"], as_index=False)
        .agg(conf=("conf", "mean"), acc=("acc", "mean"), n=("n", "sum"))
        .sort_values(["stage4", "bin"], kind="mergesort")
    )

    fig, axes = plt.subplots(2, 2, figsize=(13.2, 9.0), sharex=True, sharey=True)
    axes = axes.flatten()
    stage_order = ["D1", "D2", "D3", "D4"]

    def _paint_diag_bg(ax: plt.Axes) -> None:
        # 按老师反馈去掉背景色块，仅保留对角线参考
        ax.plot([0, 1], [0, 1], "--", color="#777777", linewidth=1)
        ax.set_xlim(0, 1.0)
        ax.set_ylim(0, 1.0)
        ax.set_xlabel("分箱置信度均值")
        ax.set_ylabel("分箱准确率均值")
        ax.grid(alpha=0.25)

    for ax, st in zip(axes, stage_order):
        _paint_diag_bg(ax)
        sub = stage_bin_model[stage_bin_model["stage4"] == st]
        for model in MODEL_ORDER:
            ms = sub[sub["model_short"] == model]
            if ms.empty:
                continue
            ax.scatter(
                ms["conf"],
                ms["acc"],
                s=np.clip(ms["n"] * 1.05, 22, 360),
                color=MODEL_COLOR.get(model, "#666666"),
                marker=MODEL_MARKER.get(model, "o"),
                edgecolors="white",
                linewidths=0.4,
                alpha=0.45,
            )
        st_mean = stage_bin_overall[stage_bin_overall["stage4"] == st].sort_values("bin")
        if not st_mean.empty:
            ax.plot(
                st_mean["conf"],
                st_mean["acc"],
                color="#111111",
                linewidth=2.0,
                marker="o",
                markersize=3.8,
                label="分箱均值轨迹",
            )
        ax.set_title(f"B{st[-1]}. {st} 阶段校准")
        ax.legend(loc="upper right", fontsize=7.4, frameon=True)
    for ax in axes[len(stage_order) :]:
        ax.axis("off")

    model_handles = _build_model_legend_handles(MODEL_ORDER, marker_size=7.0)
    fig.subplots_adjust(top=0.91, bottom=0.08, wspace=0.18, hspace=0.34)
    fig.legend(
        handles=model_handles,
        labels=[h.get_label() for h in model_handles],
        loc="lower center",
        bbox_to_anchor=(0.08, 0.47, 0.84, 0.08),
        mode="expand",
        ncol=max(1, len(model_handles)),
        fontsize=8.2,
        frameon=True,
    )
    fig.suptitle("G4B 置信度校准", fontsize=14, y=1.03)
    _save_fig(out_calib)

    # B(v3): 参考布局的整体校准散点（不展示模型散点，按阶段聚合）
    def _wavg(v: pd.Series, w: pd.Series) -> float:
        vv = pd.to_numeric(v, errors="coerce")
        ww = pd.to_numeric(w, errors="coerce").fillna(0.0)
        m = vv.notna() & (ww >= 0)
        if not bool(m.any()):
            return float("nan")
        vv2 = vv[m].astype(float)
        ww2 = ww[m].astype(float)
        sw = float(ww2.sum())
        if sw <= 0:
            return float(vv2.mean())
        return float((vv2 * ww2).sum() / sw)

    stage_bin_model_v3 = (
        calib.groupby(["stage4", "model_short", "bin"], as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "conf_model": _wavg(g["conf"], g["n"]),
                    "acc_model": _wavg(g["acc"], g["n"]),
                    "n_model": float(pd.to_numeric(g["n"], errors="coerce").fillna(0).sum()),
                }
            )
        )
        .reset_index(drop=True)
    )
    stage_bin_overall_v3 = (
        calib.groupby(["stage4", "bin"], as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "conf_mean": _wavg(g["conf"], g["n"]),
                    "acc_mean": _wavg(g["acc"], g["n"]),
                    "n_total": float(pd.to_numeric(g["n"], errors="coerce").fillna(0).sum()),
                }
            )
        )
        .reset_index(drop=True)
    )
    stage_bin_std_v3 = (
        stage_bin_model_v3.groupby(["stage4", "bin"], as_index=False)["acc_model"]
        .std()
        .rename(columns={"acc_model": "acc_sd_model"})
    )
    stage_bin_overall_v3 = stage_bin_overall_v3.merge(stage_bin_std_v3, on=["stage4", "bin"], how="left")
    stage_bin_overall_v3["acc_sd_model"] = pd.to_numeric(stage_bin_overall_v3["acc_sd_model"], errors="coerce").fillna(0.0)
    stage_bin_overall_v3["acc_low"] = (stage_bin_overall_v3["acc_mean"] - stage_bin_overall_v3["acc_sd_model"]).clip(0.0, 1.0)
    stage_bin_overall_v3["acc_high"] = (stage_bin_overall_v3["acc_mean"] + stage_bin_overall_v3["acc_sd_model"]).clip(0.0, 1.0)

    stage_color4 = {"D1": "#4C78A8", "D2": "#D4A72C", "D3": "#59A14F", "D4": "#C44E52"}
    fig_bv3, ax_bv3 = plt.subplots(figsize=(8.2, 5.4))
    ax_bv3.plot([0, 1], [0, 1], "--", color="#7A7A7A", linewidth=1.0, alpha=0.9)
    for st in ["D1", "D2", "D3", "D4"]:
        sub = stage_bin_overall_v3[stage_bin_overall_v3["stage4"] == st].sort_values("conf_mean")
        if sub.empty:
            continue
        sub_plot = sub[(sub["n_total"] >= 12) & (sub["conf_mean"] >= 0.65)].copy()
        if len(sub_plot) < 2:
            sub_plot = sub.sort_values("n_total", ascending=False).head(4).sort_values("conf_mean")
        c = stage_color4.get(st, "#666666")
        ax_bv3.plot(
            sub_plot["conf_mean"],
            sub_plot["acc_mean"],
            color=c,
            linewidth=1.6,
            alpha=0.9,
            zorder=2.2,
        )
        ax_bv3.scatter(
            sub_plot["conf_mean"],
            sub_plot["acc_mean"],
            s=np.clip(sub_plot["n_total"] * 1.35, 24, 360),
            color=c,
            alpha=0.62,
            edgecolors="white",
            linewidths=0.5,
            label=st,
            zorder=3,
        )
    overall_conf_v4 = _wavg(stage_bin_overall_v3["conf_mean"], stage_bin_overall_v3["n_total"])
    overall_acc_v4 = _wavg(stage_bin_overall_v3["acc_mean"], stage_bin_overall_v3["n_total"])
    if pd.notna(overall_conf_v4) and pd.notna(overall_acc_v4):
        ax_bv3.scatter(
            [overall_conf_v4],
            [overall_acc_v4],
            s=180,
            marker="*",
            color="#111111",
            edgecolors="white",
            linewidths=0.8,
            label="总体加权点",
            zorder=4.5,
        )
    _set_full_axis_border(ax_bv3, lw=1.2)
    ax_bv3.set_xlim(0.0, 1.0)
    ax_bv3.set_ylim(0.0, 1.0)
    ax_bv3.set_xlabel("分箱置信度均值（全模型+同阶段聚合）")
    ax_bv3.set_ylabel("分箱准确率均值")
    ax_bv3.set_title("B. 置信度校准")
    ax_bv3.grid(alpha=0.25)
    ax_bv3.legend(loc="upper left", fontsize=9, frameon=True, ncol=2)
    _save_fig(out_calib_overall_v4)

    # B0(v5): 全阶段总体校准（按阶段样本量加权，去除背景色/误差带）
    stage_weighted = (
        stage_bin_overall_v3.groupby("stage4", as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "conf_stage": _wavg(g["conf_mean"], g["n_total"]),
                    "acc_stage": _wavg(g["acc_mean"], g["n_total"]),
                    "stage_weight": float(pd.to_numeric(g["n_total"], errors="coerce").fillna(0).sum()),
                }
            )
        )
        .reset_index(drop=True)
    )
    model_overall = (
        stage_bin_model_v3.groupby("model_short", as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "conf_overall": _wavg(g["conf_model"], g["n_model"]),
                    "acc_overall": _wavg(g["acc_model"], g["n_model"]),
                    "n_overall": float(pd.to_numeric(g["n_model"], errors="coerce").fillna(0).sum()),
                }
            )
        )
        .reset_index(drop=True)
    )
    overall_conf = _wavg(stage_weighted["conf_stage"], stage_weighted["stage_weight"])
    overall_acc = _wavg(stage_weighted["acc_stage"], stage_weighted["stage_weight"])
    if not stage_weighted.empty:
        rr_stage = np.arange(2, len(stage_weighted) + 2)
        stage_weighted["formula_conf_stage"] = [
            f"=IFERROR(SUMPRODUCT((d_calib_bins!$M:$M=B{r})*(d_calib_bins!$I:$I)*(d_calib_bins!$K:$K))/SUMIFS(d_calib_bins!$K:$K,d_calib_bins!$M:$M,B{r}),\"\")"
            for r in rr_stage
        ]
        stage_weighted["formula_acc_stage"] = [
            f"=IFERROR(SUMPRODUCT((d_calib_bins!$M:$M=B{r})*(d_calib_bins!$J:$J)*(d_calib_bins!$K:$K))/SUMIFS(d_calib_bins!$K:$K,d_calib_bins!$M:$M,B{r}),\"\")"
            for r in rr_stage
        ]
        stage_weighted["formula_stage_weight"] = [f"=SUMIFS(d_calib_bins!$K:$K,d_calib_bins!$M:$M,B{r})" for r in rr_stage]
        stage_weighted["说明"] = "按stage4在d_calib_bins中做加权聚合：value=Σ(conf/acc*n)/Σn；stage_weight=Σn"
    if not model_overall.empty:
        rr_model = np.arange(2, len(model_overall) + 2)
        model_overall["formula_conf_overall"] = [
            f"=IFERROR(SUMPRODUCT((d_calib_bins!$D:$D=B{r})*(d_calib_bins!$I:$I)*(d_calib_bins!$K:$K))/SUMIFS(d_calib_bins!$K:$K,d_calib_bins!$D:$D,B{r}),\"\")"
            for r in rr_model
        ]
        model_overall["formula_acc_overall"] = [
            f"=IFERROR(SUMPRODUCT((d_calib_bins!$D:$D=B{r})*(d_calib_bins!$J:$J)*(d_calib_bins!$K:$K))/SUMIFS(d_calib_bins!$K:$K,d_calib_bins!$D:$D,B{r}),\"\")"
            for r in rr_model
        ]
        model_overall["formula_n_overall"] = [f"=SUMIFS(d_calib_bins!$K:$K,d_calib_bins!$D:$D,B{r})" for r in rr_model]
        model_overall["说明"] = "按model_short在d_calib_bins中做加权聚合：value=Σ(conf/acc*n)/Σn；n_overall=Σn"

    fig_b0, ax_b0 = plt.subplots(figsize=(9.8, 6.4))
    label_offset_map: dict[str, tuple[int, int]] = {
        "deepseek-v3": (12, 0),
        "gpt-5": (12, 8),
        "gemini-2.5p": (12, -8),
        "grok-4": (12, 10),
        "claude-4.1": (12, -10),
    }
    for m in MODEL_ORDER:
        sub = model_overall[model_overall["model_short"] == m]
        if sub.empty:
            continue
        ax_b0.scatter(
            sub["conf_overall"],
            sub["acc_overall"],
            s=np.clip(sub["n_overall"] * 0.06, 90, 260),
            marker=MODEL_MARKER.get(m, "o"),
            color=MODEL_COLOR.get(m, "#666666"),
            edgecolors="white",
            linewidths=0.7,
            alpha=0.92,
            zorder=3,
        )
        row = sub.iloc[0]
        dx, dy = label_offset_map.get(str(m), (10, 8))
        ax_b0.annotate(
            str(m),
            (float(row["conf_overall"]), float(row["acc_overall"])),
            xytext=(dx, dy),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=9.4,
            fontweight="semibold",
            color="#1F2D3D",
            path_effects=[pe.withStroke(linewidth=2.6, foreground="white")],
            zorder=5,
        )
    if pd.notna(overall_conf) and pd.notna(overall_acc):
        ax_b0.scatter(
            [overall_conf],
            [overall_acc],
            s=210,
            marker="*",
            color="#111111",
            edgecolors="white",
            linewidths=0.8,
            zorder=4,
        )
        ax_b0.annotate(
            "加权总体",
            (float(overall_conf), float(overall_acc)),
            xytext=(14, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=9.2,
            fontweight="bold",
            color="#111111",
            path_effects=[pe.withStroke(linewidth=2.8, foreground="white")],
            zorder=6,
        )
    x_vals = pd.to_numeric(model_overall["conf_overall"], errors="coerce").dropna().tolist()
    y_vals = pd.to_numeric(model_overall["acc_overall"], errors="coerce").dropna().tolist()
    if pd.notna(overall_conf):
        x_vals.append(float(overall_conf))
    if pd.notna(overall_acc):
        y_vals.append(float(overall_acc))
    x_zoom = _adaptive_ylim(pd.Series(x_vals), fallback=(0.74, 0.98), domain=(0.0, 1.0), min_span=0.18)
    y_zoom = _adaptive_ylim(pd.Series(y_vals), fallback=(0.64, 0.90), domain=(0.0, 1.0), min_span=0.18)
    # 统一坐标范围并设置等尺度，保证 y=x 参考线为标准对角线
    axis_lo = max(0.0, min(x_zoom[0], y_zoom[0]) - 0.004)
    axis_hi = min(1.0, max(x_zoom[1], y_zoom[1]) + 0.035)
    ax_b0.plot([axis_lo, axis_hi], [axis_lo, axis_hi], "--", color="#7A7A7A", linewidth=1.1, alpha=0.9, zorder=1)
    _set_full_axis_border(ax_b0, lw=1.2)
    ax_b0.set_xlim(axis_lo, axis_hi)
    ax_b0.set_ylim(axis_lo, axis_hi)
    ax_b0.set_aspect("equal", adjustable="box")
    ax_b0.set_xlabel("平均置信度（模型自报打分）")
    ax_b0.set_ylabel("观察准确率（与正确性指标同口径）")
    ax_b0.set_title("b. 全阶段校准")
    ax_b0.grid(alpha=0.22)
    fig_b0.subplots_adjust(bottom=0.10)
    _save_fig(out_calib_overall_v5)

    stage_model_points = (
        calib.groupby(["stage4", "model_short"], as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "conf_stage_model": _wavg(g["conf"], g["n"]),
                    "acc_stage_model": _wavg(g["acc"], g["n"]),
                    "n_stage_model": float(pd.to_numeric(g["n"], errors="coerce").fillna(0).sum()),
                }
            )
        )
        .reset_index(drop=True)
    )
    stage_model_points["calibration_gap"] = stage_model_points["conf_stage_model"] - stage_model_points["acc_stage_model"]
    stage_model_paper = stage_model_points.copy()
    stage_model_paper["环节"] = stage_model_paper["stage4"].map(STAGE4_CN).fillna(stage_model_paper["stage4"])
    stage_model_paper["模型"] = stage_model_paper["model_short"]
    stage_model_paper = stage_model_paper.rename(
        columns={
            "conf_stage_model": "平均置信度",
            "acc_stage_model": "观察准确率",
            "calibration_gap": "校准差值",
            "n_stage_model": "样本量",
        }
    )[["环节", "模型", "平均置信度", "观察准确率", "校准差值", "样本量"]].copy()
    for col in ["平均置信度", "观察准确率", "校准差值"]:
        stage_model_paper[col] = pd.to_numeric(stage_model_paper[col], errors="coerce").round(3)

    fig_stage_pts, axes_stage_pts = plt.subplots(2, 2, figsize=(11.8, 9.2))
    axes_stage_pts = axes_stage_pts.flatten()
    stage_plot_order = ["D1", "D2", "D3", "D4"]
    x_stage_vals = pd.to_numeric(stage_model_points["conf_stage_model"], errors="coerce").dropna().tolist()
    y_stage_vals = pd.to_numeric(stage_model_points["acc_stage_model"], errors="coerce").dropna().tolist()
    x_stage_vals.extend(pd.to_numeric(stage_weighted["conf_stage"], errors="coerce").dropna().tolist())
    y_stage_vals.extend(pd.to_numeric(stage_weighted["acc_stage"], errors="coerce").dropna().tolist())
    x_stage_zoom = _adaptive_ylim(pd.Series(x_stage_vals), fallback=(0.74, 0.98), domain=(0.0, 1.0), min_span=0.18)
    y_stage_zoom = _adaptive_ylim(pd.Series(y_stage_vals), fallback=(0.64, 0.90), domain=(0.0, 1.0), min_span=0.18)
    axis_lo_stage = max(0.0, min(x_stage_zoom[0], y_stage_zoom[0]) - 0.004)
    axis_hi_stage = min(1.0, max(x_stage_zoom[1], y_stage_zoom[1]) + 0.035)
    for ax_stage, st in zip(axes_stage_pts, stage_plot_order):
        ax_stage.plot(
            [axis_lo_stage, axis_hi_stage],
            [axis_lo_stage, axis_hi_stage],
            "--",
            color="#7A7A7A",
            linewidth=1.0,
            alpha=0.9,
            zorder=1,
        )
        for model_name in MODEL_ORDER:
            sub = stage_model_points[
                (stage_model_points["stage4"] == st) & (stage_model_points["model_short"] == model_name)
            ]
            if sub.empty:
                continue
            row = sub.iloc[0]
            ax_stage.scatter(
                [float(row["conf_stage_model"])],
                [float(row["acc_stage_model"])],
                s=np.clip(float(row["n_stage_model"]) * 0.06, 80, 240),
                marker=MODEL_MARKER.get(model_name, "o"),
                color=MODEL_COLOR.get(model_name, "#666666"),
                edgecolors="white",
                linewidths=0.7,
                alpha=0.92,
                zorder=3,
            )
        stage_star = stage_weighted[stage_weighted["stage4"] == st]
        if not stage_star.empty:
            star_row = stage_star.iloc[0]
            ax_stage.scatter(
                [float(star_row["conf_stage"])],
                [float(star_row["acc_stage"])],
                s=180,
                marker="*",
                color="#111111",
                edgecolors="white",
                linewidths=0.8,
                zorder=4,
            )
        _set_full_axis_border(ax_stage, lw=1.1)
        ax_stage.set_xlim(axis_lo_stage, axis_hi_stage)
        ax_stage.set_ylim(axis_lo_stage, axis_hi_stage)
        ax_stage.set_aspect("equal", adjustable="box")
        ax_stage.set_xlabel("")
        ax_stage.set_ylabel("")
        ax_stage.set_title(f"B{st[-1]}. {STAGE4_CN.get(st, st)}")
        ax_stage.grid(alpha=0.22)
    stage_handles = _build_model_legend_handles(MODEL_ORDER, marker_size=7.2)
    stage_handles.append(
        Line2D(
            [0],
            [0],
            marker="*",
            linestyle="None",
            markersize=11,
            markerfacecolor="#111111",
            markeredgecolor="white",
            markeredgewidth=0.8,
            label="阶段加权点",
        )
    )
    fig_stage_pts.suptitle("G4B 分阶段平均校准点", fontsize=14.0, y=0.98)
    fig_stage_pts.subplots_adjust(left=0.10, right=0.98, top=0.90, bottom=0.31, wspace=0.20, hspace=0.24)
    fig_stage_pts.text(0.5, 0.18, "平均置信度（模型自报打分）", ha="center", va="center", fontsize=10.5)
    fig_stage_pts.text(
        0.03,
        0.52,
        "观察准确率（与正确性指标同口径）",
        ha="center",
        va="center",
        rotation=90,
        fontsize=10.5,
    )
    fig_stage_pts.legend(
        handles=stage_handles,
        labels=[h.get_label() for h in stage_handles],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.04),
        ncol=min(6, len(stage_handles)),
        frameon=False,
        fontsize=8.8,
        handletextpad=0.4,
        columnspacing=1.2,
    )
    _save_fig(out_calib_stage_points)
    _save_fig(out_calib_overall_stage)

    _save_table_png(stage_model_paper, out_calib_stage_table, "G4-B 分阶段模型校准表（五模型合并三中心）")

    # B2: 诊断/检查/方案校准曲线
    def _load_bin(path: Path, category: str) -> pd.DataFrame:
        d = pd.read_excel(path, sheet_name="bin_summary_used")
        d["model_short"] = d["model"].map(MODEL_SHORT).fillna(d["model"].astype(str))
        d["stage4"] = d["stage"].map(_stage4_map)
        d = d[d["category"].astype(str).str.lower() == category.lower()].copy()
        return d

    bin_diag = _load_bin(DERIVED_METRICS_DIR / "calibration" / "calibration_line_diagnosis_stagewise_source.xlsx", "diagnosis")
    bin_check = _load_bin(DERIVED_METRICS_DIR / "calibration" / "calibration_line_check_stagewise_source.xlsx", "check")
    # 检查口径：D1决策检查并入 D2
    bin_check["stage4"] = bin_check["stage"].replace({"D1_Decision": "D2_Loop"}).map(_stage4_map)
    bin_plan = _load_bin(DERIVED_METRICS_DIR / "calibration" / "calibration_line_plan_stagewise_source.xlsx", "plan")

    fig, axs = plt.subplots(1, 3, figsize=(15.5, 4.8), sharex=True, sharey=True)
    for ax, ddf, title in [
        (axs[0], bin_diag, "诊断校准曲线"),
        (axs[1], bin_check, "检查校准曲线"),
        (axs[2], bin_plan, "方案校准曲线"),
    ]:
        ax.plot([0, 1], [0, 1], "--", color="#777777", linewidth=1)
        if not ddf.empty:
            summ = (
                ddf.groupby(["stage4", "bin"], as_index=False)
                .agg(conf=("conf", "mean"), acc=("acc", "mean"), n=("n", "sum"))
                .sort_values(["stage4", "bin"], kind="mergesort")
            )
            for st, g in summ.groupby("stage4", dropna=False):
                g = g.sort_values("conf")
                ax.plot(g["conf"], g["acc"], marker="o", linewidth=1.8, label=str(st))
        ax.set_title(title)
        ax.set_xlabel("置信度分箱均值")
        ax.set_ylabel("准确率分箱均值")
        ax.set_xlim(0, 1.0)
        ax.set_ylim(0, 1.0)
        ax.grid(alpha=0.25)
        ax.legend(loc="lower right", fontsize=8, frameon=True)
    fig.suptitle("G4B2 分类路径校准曲线", fontsize=14, y=1.03)
    _save_fig(out_calib_path)

    # B3/B4/B5: 按决策类型分组的平均校准点（模型点 + 总体加权点）
    diag_stage_order = ["D1_Decision", "D2_Decision", "D3_Decision"]
    diag_stage_label = {
        "D1_Decision": "D1 诊断",
        "D2_Decision": "D2 修正诊断",
        "D3_Decision": "D3 最终诊断",
    }
    plan_stage_order = ["D2_Decision", "D3_Decision", "D4_Plan"]
    plan_stage_label = {
        "D2_Decision": "D2 术前治疗",
        "D3_Decision": "D3 术后治疗",
        "D4_Plan": "D4 随访康复",
    }
    check_stage_order = ["D1_Loop", "D2_Loop"]
    check_stage_label = {"D1_Loop": "D1 门诊检查", "D2_Loop": "D2 入院检查"}
    check_round_order = [1, 2, 3, 4]

    diag_stage_bin = (
        bin_diag.groupby(["stage", "model_short", "bin"], as_index=False)
        .agg(conf=("conf", "mean"), acc=("acc", "mean"), n=("n", "sum"))
        .sort_values(["stage", "model_short", "bin"], kind="mergesort")
    )
    diag_stage_bin["decision_type_cn"] = diag_stage_bin["stage"].map(diag_stage_label).fillna(diag_stage_bin["stage"].astype(str))
    diag_stage_model_points = (
        diag_stage_bin.groupby(["stage", "decision_type_cn", "model_short"], as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "conf_point": _wavg(g["conf"], g["n"]),
                    "acc_point": _wavg(g["acc"], g["n"]),
                    "sample_n": float(pd.to_numeric(g["n"], errors="coerce").fillna(0).sum()),
                }
            )
        )
        .reset_index(drop=True)
    )
    diag_stage_model_points["calibration_gap"] = diag_stage_model_points["conf_point"] - diag_stage_model_points["acc_point"]
    diag_stage_overall_points = (
        diag_stage_bin.groupby(["stage", "decision_type_cn"], as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "conf_point": _wavg(g["conf"], g["n"]),
                    "acc_point": _wavg(g["acc"], g["n"]),
                    "sample_n": float(pd.to_numeric(g["n"], errors="coerce").fillna(0).sum()),
                }
            )
        )
        .reset_index(drop=True)
    )
    diag_stage_overall_points["calibration_gap"] = diag_stage_overall_points["conf_point"] - diag_stage_overall_points["acc_point"]
    diag_stage_summary = (
        diag_stage_overall_points.rename(columns={"conf_point": "conf_mean", "acc_point": "acc_mean"})
        .assign(calibration_gap=lambda d: d["conf_mean"] - d["acc_mean"])
        .sort_values(["stage"], kind="mergesort")
    )

    plan_stage_bin = (
        bin_plan.groupby(["stage", "model_short", "bin"], as_index=False)
        .agg(conf=("conf", "mean"), acc=("acc", "mean"), n=("n", "sum"))
        .sort_values(["stage", "model_short", "bin"], kind="mergesort")
    )
    plan_stage_bin["decision_type_cn"] = plan_stage_bin["stage"].map(plan_stage_label).fillna(plan_stage_bin["stage"].astype(str))
    plan_stage_model_points = (
        plan_stage_bin.groupby(["stage", "decision_type_cn", "model_short"], as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "conf_point": _wavg(g["conf"], g["n"]),
                    "acc_point": _wavg(g["acc"], g["n"]),
                    "sample_n": float(pd.to_numeric(g["n"], errors="coerce").fillna(0).sum()),
                }
            )
        )
        .reset_index(drop=True)
    )
    plan_stage_model_points["calibration_gap"] = plan_stage_model_points["conf_point"] - plan_stage_model_points["acc_point"]
    plan_stage_overall_points = (
        plan_stage_bin.groupby(["stage", "decision_type_cn"], as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "conf_point": _wavg(g["conf"], g["n"]),
                    "acc_point": _wavg(g["acc"], g["n"]),
                    "sample_n": float(pd.to_numeric(g["n"], errors="coerce").fillna(0).sum()),
                }
            )
        )
        .reset_index(drop=True)
    )
    plan_stage_overall_points["calibration_gap"] = plan_stage_overall_points["conf_point"] - plan_stage_overall_points["acc_point"]
    plan_stage_summary = (
        plan_stage_overall_points.rename(columns={"conf_point": "conf_mean", "acc_point": "acc_mean"})
        .assign(calibration_gap=lambda d: d["conf_mean"] - d["acc_mean"])
        .sort_values(["stage"], kind="mergesort")
    )

    check_round_detail = pd.read_excel(
        DERIVED_METRICS_DIR / "calibration" / "calibration_line_check_stagewise_source.xlsx",
        sheet_name="detail_round_all",
    )
    check_round_detail["confidence"] = pd.to_numeric(check_round_detail["confidence"], errors="coerce")
    check_round_detail["accuracy"] = pd.to_numeric(check_round_detail["accuracy"], errors="coerce")
    check_round_detail["round"] = pd.to_numeric(check_round_detail["round"], errors="coerce")
    check_round_detail["model_short"] = check_round_detail["model"].map(MODEL_SHORT).fillna(check_round_detail["model"].astype(str))
    check_round_detail = check_round_detail[
        check_round_detail["stage"].astype(str).isin(check_stage_order)
        & check_round_detail["confidence"].notna()
        & check_round_detail["accuracy"].notna()
        & check_round_detail["round"].notna()
    ].copy()
    check_round_detail["round_group"] = check_round_detail["round"].astype(int).clip(lower=1, upper=4)
    check_round_detail["round_group_cn"] = check_round_detail["round_group"].map(
        {1: "1轮检查", 2: "2轮检查", 3: "3轮检查", 4: "4轮检查"}
    )
    check_round_detail["check_type_cn"] = check_round_detail["stage"].map(check_stage_label).fillna(check_round_detail["stage"].astype(str))
    check_round_detail["bin"] = pd.cut(
        check_round_detail["confidence"].astype(float),
        bins=np.round(np.arange(0.0, 1.01, 0.1), 1),
        include_lowest=True,
        right=True,
    ).astype(str)
    check_round_detail["bin"] = check_round_detail["bin"].replace({"(-0.001, 0.1]": "(0.0, 0.1]"})

    check_round_bin = (
        check_round_detail.groupby(
            ["stage", "check_type_cn", "round_group", "round_group_cn", "model_short", "bin"], as_index=False
        )
        .agg(conf=("confidence", "mean"), acc=("accuracy", "mean"), n=("case_id", "count"))
        .sort_values(["stage", "round_group", "model_short", "bin"], kind="mergesort")
    )
    check_round_model_points = (
        check_round_bin.groupby(["stage", "check_type_cn", "round_group", "round_group_cn", "model_short"], as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "conf_point": _wavg(g["conf"], g["n"]),
                    "acc_point": _wavg(g["acc"], g["n"]),
                    "sample_n": float(pd.to_numeric(g["n"], errors="coerce").fillna(0).sum()),
                }
            )
        )
        .reset_index(drop=True)
    )
    check_round_model_points["calibration_gap"] = check_round_model_points["conf_point"] - check_round_model_points["acc_point"]
    check_round_overall_points = (
        check_round_bin.groupby(["stage", "check_type_cn", "round_group", "round_group_cn"], as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "conf_point": _wavg(g["conf"], g["n"]),
                    "acc_point": _wavg(g["acc"], g["n"]),
                    "sample_n": float(pd.to_numeric(g["n"], errors="coerce").fillna(0).sum()),
                }
            )
        )
        .reset_index(drop=True)
    )
    check_round_overall_points["calibration_gap"] = check_round_overall_points["conf_point"] - check_round_overall_points["acc_point"]
    check_round_summary = (
        check_round_overall_points.rename(columns={"conf_point": "conf_mean", "acc_point": "acc_mean"})
        .assign(calibration_gap=lambda d: d["conf_mean"] - d["acc_mean"])
        .sort_values(["stage", "round_group"], kind="mergesort")
    )

    def _calib_axis_bounds(
        model_points_df: pd.DataFrame,
        overall_points_df: pd.DataFrame,
        x_col: str = "conf_point",
        y_col: str = "acc_point",
    ) -> tuple[float, float]:
        x_vals = pd.to_numeric(model_points_df.get(x_col, pd.Series(dtype=float)), errors="coerce").dropna().tolist()
        y_vals = pd.to_numeric(model_points_df.get(y_col, pd.Series(dtype=float)), errors="coerce").dropna().tolist()
        x_vals.extend(pd.to_numeric(overall_points_df.get(x_col, pd.Series(dtype=float)), errors="coerce").dropna().tolist())
        y_vals.extend(pd.to_numeric(overall_points_df.get(y_col, pd.Series(dtype=float)), errors="coerce").dropna().tolist())
        x_zoom = _adaptive_ylim(pd.Series(x_vals), fallback=(0.72, 0.98), domain=(0.0, 1.0), min_span=0.18)
        y_zoom = _adaptive_ylim(pd.Series(y_vals), fallback=(0.62, 0.96), domain=(0.0, 1.0), min_span=0.18)
        axis_lo = max(0.0, min(x_zoom[0], y_zoom[0]) - 0.004)
        axis_hi = min(1.0, max(x_zoom[1], y_zoom[1]) + 0.035)
        return axis_lo, axis_hi

    def _plot_calib_points_panel(
        ax: plt.Axes,
        model_points: pd.DataFrame,
        overall_points: pd.DataFrame,
        title: str,
        axis_lo: float,
        axis_hi: float,
    ) -> None:
        ax.plot(
            [axis_lo, axis_hi],
            [axis_lo, axis_hi],
            "--",
            color="#7A7A7A",
            linewidth=1.0,
            alpha=0.9,
            zorder=1,
        )
        for model_name in MODEL_ORDER:
            sub = model_points[model_points["model_short"].astype(str).eq(model_name)]
            if sub.empty:
                continue
            row = sub.iloc[0]
            ax.scatter(
                [float(row["conf_point"])],
                [float(row["acc_point"])],
                s=np.clip(float(row.get("sample_n", 0.0)) * 0.06, 76, 220),
                marker=MODEL_MARKER.get(model_name, "o"),
                color=MODEL_COLOR.get(model_name, "#666666"),
                edgecolors="white",
                linewidths=0.7,
                alpha=0.92,
                zorder=3,
            )
        if not overall_points.empty:
            row = overall_points.iloc[0]
            ax.scatter(
                [float(row["conf_point"])],
                [float(row["acc_point"])],
                s=180,
                marker="*",
                color="#111111",
                edgecolors="white",
                linewidths=0.8,
                zorder=4,
            )
        else:
            ax.text(0.5, 0.5, "无样本", ha="center", va="center", transform=ax.transAxes, fontsize=10.5, color="#6B7280")
        _set_full_axis_border(ax, lw=1.05)
        ax.set_xlim(axis_lo, axis_hi)
        ax.set_ylim(axis_lo, axis_hi)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title(title, fontsize=11.0)
        ax.grid(alpha=0.22)

    model_plus_overall_handles = _build_model_legend_handles(MODEL_ORDER, marker_size=7.2)
    model_plus_overall_handles.append(
        Line2D(
            [0],
            [0],
            marker="*",
            linestyle="None",
            markersize=11,
            markerfacecolor="#111111",
            markeredgecolor="white",
            markeredgewidth=0.8,
            label="总体加权点",
        )
    )

    # B3 诊断决策：平均校准点（模型 + 总体）
    fig_diag, axs_diag = plt.subplots(1, 3, figsize=(16.8, 5.2), sharex=True, sharey=True)
    diag_lo, diag_hi = _calib_axis_bounds(diag_stage_model_points, diag_stage_overall_points)
    for idx, st in enumerate(diag_stage_order):
        ax = axs_diag[idx]
        panel_model = diag_stage_model_points[diag_stage_model_points["stage"].astype(str).eq(st)].copy()
        panel_overall = diag_stage_overall_points[diag_stage_overall_points["stage"].astype(str).eq(st)].copy()
        _plot_calib_points_panel(ax, panel_model, panel_overall, diag_stage_label.get(st, st), diag_lo, diag_hi)
    fig_diag.suptitle("G4B3 诊断决策类型平均校准点", fontsize=14.0, y=0.98)
    fig_diag.subplots_adjust(left=0.08, right=0.99, top=0.86, bottom=0.24, wspace=0.18)
    fig_diag.text(0.5, 0.12, "平均置信度（模型自报打分）", ha="center", va="center", fontsize=10.2)
    fig_diag.text(0.03, 0.52, "观察准确率（与正确性指标同口径）", ha="center", va="center", rotation=90, fontsize=10.2)
    fig_diag.legend(
        handles=model_plus_overall_handles,
        labels=[h.get_label() for h in model_plus_overall_handles],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.03),
        ncol=min(6, len(model_plus_overall_handles)),
        frameon=False,
        fontsize=8.7,
        handletextpad=0.4,
        columnspacing=1.1,
    )
    _archive_existing_output(out_calib_diag_type, "figures")
    _save_fig(out_calib_diag_type)

    # B4 检查决策：D1/D2 × 1/2/3/4轮 的平均校准点（模型 + 总体）
    fig_chk, axs_chk = plt.subplots(2, 4, figsize=(18.2, 9.2), sharex=True, sharey=True)
    chk_lo, chk_hi = _calib_axis_bounds(check_round_model_points, check_round_overall_points, "conf_point", "acc_point")
    for ridx, st in enumerate(check_stage_order):
        for cidx, r in enumerate(check_round_order):
            ax = axs_chk[ridx, cidx]
            panel_model = check_round_model_points[
                check_round_model_points["stage"].astype(str).eq(st)
                & check_round_model_points["round_group"].astype(float).eq(float(r))
            ].copy()
            panel_overall = check_round_overall_points[
                check_round_overall_points["stage"].astype(str).eq(st)
                & check_round_overall_points["round_group"].astype(float).eq(float(r))
            ].copy()
            _plot_calib_points_panel(ax, panel_model, panel_overall, f"{check_stage_label.get(st, st)} {r}轮", chk_lo, chk_hi)
    fig_chk.suptitle("G4B4 检查轮次分层平均校准点", fontsize=14.0, y=0.98)
    fig_chk.subplots_adjust(left=0.07, right=0.995, top=0.89, bottom=0.20, wspace=0.14, hspace=0.23)
    fig_chk.text(0.5, 0.10, "平均置信度（模型自报打分）", ha="center", va="center", fontsize=10.2)
    fig_chk.text(0.03, 0.52, "观察准确率（与正确性指标同口径）", ha="center", va="center", rotation=90, fontsize=10.2)
    fig_chk.legend(
        handles=model_plus_overall_handles,
        labels=[h.get_label() for h in model_plus_overall_handles],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.03),
        ncol=min(6, len(model_plus_overall_handles)),
        frameon=False,
        fontsize=8.7,
        handletextpad=0.4,
        columnspacing=1.1,
    )
    _archive_existing_output(out_calib_check_round, "figures")
    _save_fig(out_calib_check_round)

    # B5 方案决策：平均校准点（模型 + 总体）
    fig_plan, axs_plan = plt.subplots(1, 3, figsize=(16.8, 5.2), sharex=True, sharey=True)
    plan_lo, plan_hi = _calib_axis_bounds(plan_stage_model_points, plan_stage_overall_points)
    for idx, st in enumerate(plan_stage_order):
        ax = axs_plan[idx]
        panel_model = plan_stage_model_points[plan_stage_model_points["stage"].astype(str).eq(st)].copy()
        panel_overall = plan_stage_overall_points[plan_stage_overall_points["stage"].astype(str).eq(st)].copy()
        _plot_calib_points_panel(ax, panel_model, panel_overall, plan_stage_label.get(st, st), plan_lo, plan_hi)
    fig_plan.suptitle("G4B5 方案决策类型平均校准点", fontsize=14.0, y=0.98)
    fig_plan.subplots_adjust(left=0.08, right=0.99, top=0.86, bottom=0.24, wspace=0.18)
    fig_plan.text(0.5, 0.12, "平均置信度（模型自报打分）", ha="center", va="center", fontsize=10.2)
    fig_plan.text(0.03, 0.52, "观察准确率（与正确性指标同口径）", ha="center", va="center", rotation=90, fontsize=10.2)
    fig_plan.legend(
        handles=model_plus_overall_handles,
        labels=[h.get_label() for h in model_plus_overall_handles],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.03),
        ncol=min(6, len(model_plus_overall_handles)),
        frameon=False,
        fontsize=8.7,
        handletextpad=0.4,
        columnspacing=1.1,
    )
    _archive_existing_output(out_calib_plan_type, "figures")
    _save_fig(out_calib_plan_type)

    # C: 阶段通过率 + 检查效率
    flow = pd.read_excel(RAW_DOCTOR_SUMMARY, sheet_name="通过退出明细")
    flow = flow.rename(columns={"中心": "center", "模型名称": "model", "病例ID": "case_id"})
    flow = _attach_rules(flow, d1_set, gate3_set)
    flow = _attach_d2_manual_rules(flow, d2_rule_map)
    flow.loc[flow["d2_force_stop"], "D3_Decision"] = "未经过（流程终止于入院决策）"
    flow.loc[flow["d2_force_stop"], "D4_Plan"] = "未经过（流程终止于入院决策）"
    total_n = int(flow[["center", "model", "case_id"]].drop_duplicates().shape[0])  # 304*5

    d1_pass = (
        flow["D1_Decision"].fillna("").astype(str).str.contains("通过")
        & ~flow["D1_Decision"].fillna("").astype(str).str.contains("特殊")
    )
    d2_pass = (
        flow["D2_Decision"].fillna("").astype(str).str.contains("一审通过")
        | flow["D2_Decision"].fillna("").astype(str).str.contains("通过二审")
    )
    d3_pass = (
        flow["D3_Decision"].fillna("").astype(str).str.contains("通过一审")
        | flow["D3_Decision"].fillna("").astype(str).str.contains("通过二审")
    )
    d4_pass = flow["D4_Plan"].fillna("").astype(str).str.contains("完成流程")
    pass_df = pd.DataFrame(
        {
            "stage4": ["D1", "D2", "D3", "D4"],
            "pass_count": [int(d1_pass.sum()), int(d2_pass.sum()), int(d3_pass.sum()), int(d4_pass.sum())],
        }
    )
    pass_df["denominator"] = total_n
    pass_df["pass_rate"] = pass_df["pass_count"] / pass_df["denominator"]

    mcase = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="metrics_by_case")
    cols = [
        "center",
        "model",
        "case_id",
        "D1_Outpatient_Loop__requested_total",
        "D1_Outpatient_Loop__matched_total",
        "D1_Outpatient_Loop__ineff_rounds_by_zero",
        "D1_Outpatient_Loop__executed_rounds",
        "D2_SuggestedFromD1Decision__requested_total",
        "D2_SuggestedFromD1Decision__matched_total",
        "D2_SuggestedFromD1Decision__ineff_rounds_by_zero",
        "D2_SuggestedFromD1Decision__executed_rounds",
        "D2_Admission_Loop__requested_total",
        "D2_Admission_Loop__matched_total",
        "D2_Admission_Loop__ineff_rounds_by_zero",
        "D2_Admission_Loop__executed_rounds",
        "gate1_overall_score",
        "gate2_overall_score",
    ]
    for c in cols:
        if c not in mcase.columns:
            mcase[c] = 0
    chk = mcase[cols].copy()
    chk = _attach_rules(chk, d1_set, gate3_set)
    chk = _attach_d2_manual_rules(chk, d2_rule_map)
    chk = chk[~chk["is_d1_anomaly"]].copy()
    for c in cols:
        if c not in {"center", "model", "case_id"}:
            chk[c] = pd.to_numeric(chk[c], errors="coerce").fillna(0.0)

    chk["d1_match_rate"] = np.where(
        chk["D1_Outpatient_Loop__requested_total"] > 0,
        chk["D1_Outpatient_Loop__matched_total"] / chk["D1_Outpatient_Loop__requested_total"],
        np.nan,
    )
    chk["d2_match_rate"] = np.where(
        (chk["D2_SuggestedFromD1Decision__requested_total"] + chk["D2_Admission_Loop__requested_total"]) > 0,
        (chk["D2_SuggestedFromD1Decision__matched_total"] + chk["D2_Admission_Loop__matched_total"])
        / (chk["D2_SuggestedFromD1Decision__requested_total"] + chk["D2_Admission_Loop__requested_total"]),
        np.nan,
    )
    chk["d1_ineff_rate"] = np.where(
        chk["D1_Outpatient_Loop__executed_rounds"] > 0,
        chk["D1_Outpatient_Loop__ineff_rounds_by_zero"] / chk["D1_Outpatient_Loop__executed_rounds"],
        np.nan,
    )
    chk["d2_ineff_rate"] = np.where(
        (chk["D2_SuggestedFromD1Decision__executed_rounds"] + chk["D2_Admission_Loop__executed_rounds"]) > 0,
        (chk["D2_SuggestedFromD1Decision__ineff_rounds_by_zero"] + chk["D2_Admission_Loop__ineff_rounds_by_zero"])
        / (chk["D2_SuggestedFromD1Decision__executed_rounds"] + chk["D2_Admission_Loop__executed_rounds"]),
        np.nan,
    )
    # 检查次数口径修正：按轮次而非请求项数量统计
    # D1 = 门诊循环执行轮数；D2 = 住院循环轮数 + 1（并入D1决策检查）
    chk["d1_check_count"] = pd.to_numeric(chk["D1_Outpatient_Loop__executed_rounds"], errors="coerce").fillna(0.0)
    chk["d2_check_count"] = (
        pd.to_numeric(chk["D2_Admission_Loop__executed_rounds"], errors="coerce").fillna(0.0) + 1.0
    )
    chk["model_short"] = chk["model"].map(MODEL_SHORT).fillna(chk["model"].astype(str))
    chk.insert(0, "source_table", "metrics_source_data.xlsx:metrics_by_case")
    chk_rows = np.arange(2, len(chk) + 2)
    chk["formula_d1_match_rate"] = [f"=IF(E{r}>0,F{r}/E{r},\"\")" for r in chk_rows]
    chk["formula_d2_match_rate"] = [f"=IF((I{r}+M{r})>0,(J{r}+N{r})/(I{r}+M{r}),\"\")" for r in chk_rows]
    chk["formula_d1_ineff_rate"] = [f"=IF(H{r}>0,G{r}/H{r},\"\")" for r in chk_rows]
    chk["formula_d2_ineff_rate"] = [f"=IF((L{r}+P{r})>0,(K{r}+O{r})/(L{r}+P{r}),\"\")" for r in chk_rows]
    chk["formula_d1_check_count"] = [f"=H{r}" for r in chk_rows]
    chk["formula_d2_check_count"] = [f"=P{r}+1" for r in chk_rows]
    chk["说明_检查次数口径"] = "D1=门诊执行轮数；D2=住院执行轮数+1（并入D1决策检查）"
    chk_summary = pd.DataFrame(
        {
            "stage4": ["D1", "D2"],
            "match_rate": [float(chk["d1_match_rate"].mean()), float(chk["d2_match_rate"].mean())],
            "ineff_rate": [float(chk["d1_ineff_rate"].mean()), float(chk["d2_ineff_rate"].mean())],
            "avg_check_count": [float(chk["d1_check_count"].mean()), float(chk["d2_check_count"].mean())],
            "avg_check_count_std": [float(chk["d1_check_count"].std(ddof=0)), float(chk["d2_check_count"].std(ddof=0))],
        }
    )
    chk_summary_c2 = chk_summary[["stage4", "avg_check_count", "avg_check_count_std"]].copy()
    chk_summary_c2["formula_avg_check_count"] = [
        "=AVERAGE(c_check_case!$F:$F)",
        "=AVERAGE(c_check_case!$G:$G)",
    ]
    chk_summary_c2["formula_avg_check_count_std"] = [
        "=STDEV.P(c_check_case!$F:$F)",
        "=STDEV.P(c_check_case!$G:$G)",
    ]
    chk_summary_c2["说明"] = "主图C2仅展示平均检查次数；D2已并入D1决策检查"

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.8, 5.2))
    ax1.bar(pass_df["stage4"], pass_df["pass_rate"] * 100, color=["#4C72B0", "#55A868", "#F1CE63", "#C44E52"])
    for _, r in pass_df.iterrows():
        ax1.text(str(r["stage4"]), float(r["pass_rate"] * 100) + 1.8, f"{r['pass_rate'] * 100:.1f}%", ha="center")
    ax1.set_ylim(0, 105)
    ax1.set_ylabel("通过率 (%)")
    ax1.set_title("C1. D1-D4 通过率")

    x = np.arange(2)
    bar_colors = ["#4E9F8E", "#2F6F7E"]
    bars_c = ax2.bar(
        x,
        chk_summary["avg_check_count"],
        yerr=chk_summary["avg_check_count_std"],
        color=bar_colors,
        edgecolor="#204D58",
        linewidth=0.8,
        width=0.62,
        capsize=5,
        label="平均检查次数",
        zorder=3.2,
    )
    ax2.set_xticks(x)
    ax2.set_xticklabels(["D1门诊检查", "D2住院检查 含D1决策检查"])
    ymax = float(max(chk_summary["avg_check_count"].max() + chk_summary["avg_check_count_std"].max() + 0.5, 1.5))
    ax2.set_ylim(0, ymax)
    ax2.set_ylabel("平均检查次数/案例")
    ax2.set_title("c. 平均检查次数")
    ax2.legend(loc="upper right", fontsize=8, frameon=True)
    for rect, val, err in zip(bars_c, chk_summary["avg_check_count"], chk_summary["avg_check_count_std"]):
        ax2.text(
            rect.get_x() + rect.get_width() / 2.0,
            float(val) + float(err) + 0.04,
            f"{float(val):.2f}",
            ha="center",
            va="bottom",
            fontsize=9.2,
            color="#1F2D3D",
        )
    fig.suptitle("G4C 系统通过率与检查效率", fontsize=14, y=1.02)
    _save_fig(out_pass)

    # C2 独立面板：用于主图拼接（Sankey + B0校准 + C2检查效率）
    fig_c2, ax_c2 = plt.subplots(figsize=(7.4, 5.2))
    x = np.arange(2)
    bars_c2 = ax_c2.bar(
        x,
        chk_summary["avg_check_count"],
        yerr=chk_summary["avg_check_count_std"],
        color=bar_colors,
        edgecolor="#204D58",
        linewidth=0.8,
        width=0.62,
        capsize=5,
        label="平均检查次数",
        zorder=3.2,
    )
    ax_c2.set_xticks(x)
    ax_c2.set_xticklabels(["D1门诊检查", "D2住院检查 含D1决策检查"])
    ymax = float(max(chk_summary["avg_check_count"].max() + chk_summary["avg_check_count_std"].max() + 0.5, 1.5))
    ax_c2.set_ylim(0, ymax)
    ax_c2.set_ylabel("平均检查次数/案例")
    ax_c2.set_title("c. 平均检查次数")
    ax_c2.legend(loc="upper right", fontsize=8, frameon=True)
    for rect, val, err in zip(bars_c2, chk_summary["avg_check_count"], chk_summary["avg_check_count_std"]):
        ax_c2.text(
            rect.get_x() + rect.get_width() / 2.0,
            float(val) + float(err) + 0.04,
            f"{float(val):.2f}",
            ha="center",
            va="bottom",
            fontsize=9.4,
            color="#1F2D3D",
        )
    _set_full_axis_border(ax_c2, lw=1.2)
    _save_fig(out_eff_panel)

    try:
        shutil.copy2(out_calib_stage_points, out_calib_overall_stage)
    except Exception:
        pass

    # C2: 循环轮数与信息增益散点
    # 信息增益定义：对单样本(中心×模型×病例)所有循环轮，求和(每轮检查匹配率 * 每轮索要检查次数)
    completion_map = {
        (str(r["center"]), str(r["model"]), str(r["case_id"])): bool(v)
        for (_, r), v in zip(flow.iterrows(), d4_pass.tolist())
    }
    rounds = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="check_rounds")
    need_cols = [
        "center",
        "model",
        "case_id",
        "stage",
        "round_idx",
        "judge_match_score_raw",
        "ai_total_requested_count",
        "matched_count_final",
    ]
    for c in need_cols:
        if c not in rounds.columns:
            rounds[c] = np.nan
    rounds = rounds[need_cols].copy()
    rounds = _attach_rules(rounds, d1_set, gate3_set)
    rounds = rounds[~rounds["is_d1_anomaly"]].copy()
    rounds["stage"] = rounds["stage"].astype(str)
    rounds = rounds[
        rounds["stage"].isin(["D1_Outpatient_Loop", "D2_SuggestedFromD1Decision", "D2_Admission_Loop"])
    ].copy()
    rounds["round_idx"] = pd.to_numeric(rounds["round_idx"], errors="coerce").fillna(0).astype(int)
    rounds["match_rate"] = pd.to_numeric(rounds["judge_match_score_raw"], errors="coerce")
    rounds["requested_count"] = pd.to_numeric(rounds["ai_total_requested_count"], errors="coerce").fillna(0.0)
    rounds["matched_count_final"] = pd.to_numeric(rounds["matched_count_final"], errors="coerce")
    rounds["is_active_round"] = (rounds["requested_count"] > 0) | rounds["match_rate"].notna()
    rounds["per_round_info_gain"] = rounds["match_rate"].fillna(0.0) * rounds["requested_count"]
    rounds["source_sheet"] = "metrics_source_data.xlsx:check_rounds"
    rounds["source_column"] = "judge_match_score_raw * ai_total_requested_count"
    rounds["source_path"] = "analysis_viz/data/raw/metrics_source_data.xlsx"
    rounds_with_decision_baseline = rounds.copy()
    rounds = rounds[rounds["round_idx"] > 0].copy()

    key_cols = ["center", "model", "case_id"]
    sample_base = flow[key_cols].drop_duplicates().copy()
    sample_base["is_completed"] = [
        completion_map.get((str(r["center"]), str(r["model"]), str(r["case_id"])), False)
        for _, r in sample_base.iterrows()
    ]
    sample_base["sample_flag"] = np.where(sample_base["is_completed"], "Completed", "Blocked/Exit")

    case_gain = (
        rounds.groupby(key_cols, as_index=False).agg(
            cumulative_rounds=("is_active_round", "sum"),
            information_gain=("per_round_info_gain", "sum"),
            active_requested_total=("requested_count", "sum"),
        )
    )
    case_gain["cumulative_rounds"] = pd.to_numeric(case_gain["cumulative_rounds"], errors="coerce").fillna(0).astype(int)
    eff_scatter = sample_base.merge(case_gain, on=key_cols, how="left")
    eff_scatter["cumulative_rounds"] = pd.to_numeric(eff_scatter["cumulative_rounds"], errors="coerce").fillna(0).astype(int)
    eff_scatter["information_gain"] = pd.to_numeric(eff_scatter["information_gain"], errors="coerce").fillna(0.0)
    eff_scatter["active_requested_total"] = pd.to_numeric(eff_scatter["active_requested_total"], errors="coerce").fillna(0.0)
    eff_scatter["source_sheet"] = "metrics_source_data.xlsx:check_rounds"
    eff_scatter["source_column"] = "sum(match_rate * requested_count) by (center,model,case_id)"
    eff_scatter["source_path"] = "analysis_viz/data/raw/metrics_source_data.xlsx"

    fig, ax = plt.subplots(figsize=(10.4, 6.2))
    for flag, color, label in [(True, "#2ca02c", "Completed"), (False, "#d62728", "Blocked/Exit")]:
        sub = eff_scatter[eff_scatter["is_completed"] == flag]
        if sub.empty:
            continue
        ax.scatter(
            sub["cumulative_rounds"].astype(float),
            sub["information_gain"],
            s=22,
            alpha=0.33,
            color=color,
            edgecolors="none",
            label=label,
        )
    trend_all = (
        eff_scatter.groupby("cumulative_rounds", as_index=False)
        .agg(info_gain_mean=("information_gain", "mean"), samples=("case_id", "count"))
        .sort_values("cumulative_rounds", kind="mergesort")
    )
    if not trend_all.empty:
        ax.plot(
            trend_all["cumulative_rounds"],
            trend_all["info_gain_mean"],
            color="#1f2937",
            linewidth=2.2,
            marker="o",
            markersize=4.2,
            label="Overall mean",
        )

    y_lo, y_hi = _adaptive_ylim(eff_scatter["information_gain"], fallback=(0.0, 1.0), domain=(0.0, None), min_span=1.0)
    ax.set_xlabel("Cumulative Loop Rounds (LOOP1 + D1决策检查 + LOOP2)")
    ax.set_ylabel("Information Gain = Σ(每轮匹配率 × 每轮索要检查次数)")
    ax.set_title(f"G4C2. 效率散点：循环轮数 vs 信息增益（n={len(eff_scatter)}）")
    ax.set_ylim(max(0.0, y_lo), y_hi)
    ax.grid(alpha=0.25)
    ax.legend(loc="lower right", fontsize=9, frameon=True)
    _save_fig(out_eff_scatter)

    info_gain_round_summary = (
        eff_scatter.groupby("cumulative_rounds", as_index=False)
        .agg(
            n_cases=("case_id", "count"),
            info_gain_mean=("information_gain", "mean"),
            info_gain_median=("information_gain", "median"),
            info_gain_std=("information_gain", lambda s: float(pd.to_numeric(s, errors="coerce").std(ddof=0))),
            completed_rate=("is_completed", "mean"),
        )
        .sort_values("cumulative_rounds", kind="mergesort")
        .reset_index(drop=True)
    )
    info_gain_round_summary["delta_vs_prev_round"] = info_gain_round_summary["info_gain_mean"].diff()
    info_gain_round_paper = info_gain_round_summary.rename(
        columns={
            "cumulative_rounds": "累计循环轮次",
            "n_cases": "样本量",
            "info_gain_mean": "平均信息增益",
            "info_gain_median": "中位信息增益",
            "info_gain_std": "标准差",
            "completed_rate": "完成比例",
            "delta_vs_prev_round": "较前一轮增量",
        }
    ).copy()
    info_gain_round_paper["完成比例"] = pd.to_numeric(info_gain_round_paper["完成比例"], errors="coerce") * 100.0

    # C(v4): 用箱线图展示检查效率（信息增益量分布），避免稀疏散点可读性不足
    rounds["phase"] = rounds["stage"].map(
        {
            "D1_Outpatient_Loop": "LOOP1",
            "D2_SuggestedFromD1Decision": "LOOP2(含D1决策检查)",
            "D2_Admission_Loop": "LOOP2(含D1决策检查)",
        }
    )
    phase_case = (
        rounds.dropna(subset=["phase"])
        .groupby(key_cols + ["phase"], as_index=False)
        .agg(
            phase_rounds=("is_active_round", "sum"),
            phase_requested=("requested_count", "sum"),
            phase_info_gain=("per_round_info_gain", "sum"),
        )
    )
    phase_case = phase_case.merge(sample_base[key_cols + ["sample_flag", "is_completed"]], on=key_cols, how="left")

    round_meta = mcase[["center", "model", "case_id", "flow_end_stage"]].drop_duplicates().copy()
    round_meta["model_short"] = round_meta["model"].map(MODEL_SHORT).fillna(round_meta["model"].astype(str))
    rounds_c3_all = rounds_with_decision_baseline.merge(round_meta, on=key_cols, how="left")
    rounds_c3_all["flow_end_stage"] = rounds_c3_all["flow_end_stage"].fillna("").astype(str)
    rounds_c3_all = rounds_c3_all[~rounds_c3_all["flow_end_stage"].isin({"D1_Outpatient_Loop", "D2_Admission_Loop"})].copy()
    round_pair_base = (
        rounds_c3_all[rounds_c3_all["is_active_round"]]
        .groupby(key_cols + ["stage", "round_idx"], as_index=False)
        .agg(
            match_rate=("match_rate", "mean"),
            matched_count_final=("matched_count_final", "mean"),
            requested_count=("requested_count", "mean"),
            model_short=("model_short", "first"),
            flow_end_stage=("flow_end_stage", "first"),
            source_path=("source_path", "first"),
            source_sheet=("source_sheet", "first"),
            source_column=("source_column", "first"),
        )
    )
    d2_baseline_detail = round_pair_base[
        round_pair_base["stage"].eq("D2_SuggestedFromD1Decision") & round_pair_base["round_idx"].eq(0)
    ].copy()
    d2_baseline_summary = (
        d2_baseline_detail.groupby(["stage", "round_idx"], as_index=False)
        .agg(
            n_case_model=("case_id", "count"),
            n_case=("case_id", "nunique"),
            mean_matched_gain=("matched_count_final", "mean"),
            median_matched_gain=("matched_count_final", "median"),
            mean_match_rate=("match_rate", "mean"),
            mean_requested_count=("requested_count", "mean"),
        )
    )
    if not d2_baseline_summary.empty:
        d2_baseline_summary["decision_context"] = "入院诊断环节"
        d2_baseline_summary["round_label"] = "0轮入院基线信息"
        d2_baseline_summary["compare_to"] = "门诊决策后尚未追加住院检查"

    def _build_adjacent_round_pairs(
        curr_stage: str,
        phase_key: str,
        baseline_df: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        curr = round_pair_base[round_pair_base["stage"].eq(curr_stage)].copy()
        if curr.empty:
            return pd.DataFrame()
        prev = curr[
            key_cols + ["round_idx", "match_rate", "matched_count_final", "requested_count"]
        ].copy()
        prev["prev_round_idx"] = prev["round_idx"]
        prev["round_idx"] = prev["prev_round_idx"] + 1
        prev = prev.rename(
            columns={
                "match_rate": "prev_match_rate",
                "matched_count_final": "prev_matched_count_final",
                "requested_count": "prev_requested_count",
            }
        )
        merged = curr.merge(
            prev[
                key_cols
                + ["round_idx", "prev_round_idx", "prev_match_rate", "prev_matched_count_final", "prev_requested_count"]
            ],
            on=key_cols + ["round_idx"],
            how="left",
        )
        first_round_mask = merged["round_idx"].eq(1)
        if baseline_df is not None and not baseline_df.empty:
            base = baseline_df[
                key_cols + ["match_rate", "matched_count_final", "requested_count"]
            ].rename(
                columns={
                    "match_rate": "base_match_rate",
                    "matched_count_final": "base_matched_count_final",
                    "requested_count": "base_requested_count",
                }
            )
            merged = merged.merge(base, on=key_cols, how="left")
            merged.loc[first_round_mask, "prev_round_idx"] = 0
            merged.loc[first_round_mask, "prev_match_rate"] = merged.loc[first_round_mask, "base_match_rate"]
            merged.loc[first_round_mask, "prev_matched_count_final"] = merged.loc[first_round_mask, "base_matched_count_final"]
            merged.loc[first_round_mask, "prev_requested_count"] = merged.loc[first_round_mask, "base_requested_count"]
            merged = merged.drop(columns=["base_match_rate", "base_matched_count_final", "base_requested_count"])
        else:
            merged.loc[first_round_mask, "prev_round_idx"] = 0
            merged.loc[first_round_mask, ["prev_match_rate", "prev_matched_count_final", "prev_requested_count"]] = 0.0
        merged = merged[first_round_mask | merged["prev_match_rate"].notna()].copy()
        merged["phase_key"] = phase_key
        return merged

    def _round_label(phase_key: str, round_idx: int) -> str:
        if phase_key == "D1":
            if round_idx == 1:
                return "首轮门诊检查"
            return f"第{int(round_idx)}轮门诊检查"
        if round_idx == 1:
            return "首轮住院检查"
        return f"第{int(round_idx)}轮住院检查"

    def _compare_to_label(phase_key: str, round_idx: int) -> str:
        if phase_key == "D1":
            if round_idx == 1:
                return "相对问诊基线"
            return f"相对第{int(round_idx) - 1}轮门诊检查"
        if round_idx == 1:
            return "相对0轮住院检查基线"
        return f"相对第{int(round_idx) - 1}轮住院检查"

    def _plot_round_label(phase_key: str, round_idx: int) -> str:
        if phase_key == "D1":
            if round_idx == 1:
                return "门诊诊断：首轮检查 vs 问诊基线"
            return f"门诊诊断：第{int(round_idx)}轮 vs 第{int(round_idx) - 1}轮"
        if round_idx == 1:
            return "入院诊断：首轮检查 vs 0轮基线"
        return f"入院诊断：第{int(round_idx)}轮 vs 第{int(round_idx) - 1}轮"

    d1_round_pairs = _build_adjacent_round_pairs("D1_Outpatient_Loop", "D1")
    # Align with the manuscript wording: inpatient checks are counted from 0 within D2,
    # so the first inpatient round should be compared against a zero-check baseline.
    d2_round_pairs = _build_adjacent_round_pairs("D2_Admission_Loop", "D2")
    check_gain_detail = pd.concat([d1_round_pairs, d2_round_pairs], ignore_index=True)
    check_gain_detail["phase_order"] = check_gain_detail["phase_key"].map({"D1": 1, "D2": 2}).fillna(99).astype(int)
    check_gain_detail["decision_context"] = check_gain_detail["phase_key"].map(
        {"D1": "门诊诊断环节", "D2": "入院诊断环节"}
    )
    check_gain_detail["round_label"] = [
        _round_label(str(p), int(r)) for p, r in zip(check_gain_detail["phase_key"], check_gain_detail["round_idx"])
    ]
    check_gain_detail["compare_to"] = [
        _compare_to_label(str(p), int(r)) for p, r in zip(check_gain_detail["phase_key"], check_gain_detail["round_idx"])
    ]
    check_gain_detail["plot_label"] = [
        _plot_round_label(str(p), int(r)) for p, r in zip(check_gain_detail["phase_key"], check_gain_detail["round_idx"])
    ]
    check_gain_detail["matched_count_final"] = pd.to_numeric(check_gain_detail["matched_count_final"], errors="coerce")
    check_gain_detail["match_rate"] = pd.to_numeric(check_gain_detail["match_rate"], errors="coerce")
    check_gain_detail["prev_match_rate"] = pd.to_numeric(check_gain_detail["prev_match_rate"], errors="coerce")
    check_gain_detail["delta_match_rate"] = check_gain_detail["match_rate"] - check_gain_detail["prev_match_rate"]
    check_gain_detail["prev_matched_count_final"] = pd.to_numeric(
        check_gain_detail["prev_matched_count_final"], errors="coerce"
    )
    check_gain_detail["delta_matched_count_final"] = (
        check_gain_detail["matched_count_final"] - check_gain_detail["prev_matched_count_final"]
    )
    # The marginal information gain should reflect newly added matched items only.
    check_gain_detail["delta_matched_count_nonneg"] = pd.to_numeric(
        check_gain_detail["delta_matched_count_final"], errors="coerce"
    ).clip(lower=0.0)

    check_gain_summary = (
        check_gain_detail.groupby(
            ["phase_key", "phase_order", "decision_context", "round_idx", "round_label", "compare_to", "plot_label"],
            as_index=False,
        )
        .agg(
            n_case_model=("case_id", "count"),
            n_case=("case_id", "nunique"),
            mean_match_rate=("match_rate", "mean"),
            median_match_rate=("match_rate", "median"),
            mean_matched_gain=("delta_matched_count_nonneg", "mean"),
            median_matched_gain=("delta_matched_count_nonneg", "median"),
            std_matched_gain=(
                "delta_matched_count_nonneg",
                lambda s: float(pd.to_numeric(s, errors="coerce").std(ddof=0)),
            ),
            mean_delta_match_rate=("delta_match_rate", "mean"),
            median_delta_match_rate=("delta_match_rate", "median"),
        )
        .sort_values(["phase_order", "round_idx"], kind="mergesort")
        .reset_index(drop=True)
    )
    c3_min_plot_case_model_n = 1
    check_gain_summary["include_in_plot"] = check_gain_summary["n_case_model"] >= c3_min_plot_case_model_n
    check_gain_summary["phase_color"] = check_gain_summary["phase_key"].map({"D1": "#4C78A8", "D2": "#72A6D9"})
    check_gain_paper = check_gain_summary[
        [
            "decision_context",
            "round_label",
            "compare_to",
            "n_case_model",
            "n_case",
            "mean_matched_gain",
            "median_matched_gain",
            "std_matched_gain",
            "mean_delta_match_rate",
            "median_delta_match_rate",
            "mean_match_rate",
            "median_match_rate",
            "include_in_plot",
        ]
    ].rename(
        columns={
            "decision_context": "决策场景",
            "round_label": "当前额外检查轮次",
            "compare_to": "比较基线",
            "n_case_model": "样本量（病例-模型轨迹）",
            "n_case": "病例数",
            "mean_matched_gain": "平均新增匹配信息项数",
            "median_matched_gain": "中位新增匹配信息项数",
            "std_matched_gain": "标准差",
            "mean_delta_match_rate": "平均匹配率变化",
            "median_delta_match_rate": "中位匹配率变化",
            "mean_match_rate": "当前轮平均匹配率",
            "median_match_rate": "当前轮中位匹配率",
            "include_in_plot": "是否纳入主图",
        }
    ).copy()
    for col in [
        "平均新增匹配信息项数",
        "中位新增匹配信息项数",
        "标准差",
        "平均匹配率变化",
        "中位匹配率变化",
        "当前轮平均匹配率",
        "当前轮中位匹配率",
    ]:
        check_gain_paper[col] = pd.to_numeric(check_gain_paper[col], errors="coerce").round(3)

    plot_gain = check_gain_summary[check_gain_summary["include_in_plot"]].copy()
    fig_cmp, ax_cmp = plt.subplots(figsize=(10.4, 6.2))
    if not plot_gain.empty:
        y_pos = np.arange(len(plot_gain))
        plot_gain["mean_match_rate_pct"] = (
            pd.to_numeric(plot_gain["mean_match_rate"], errors="coerce").fillna(0.0) * 100.0
        )
        bars = ax_cmp.barh(
            y_pos,
            plot_gain["mean_match_rate_pct"].to_numpy(dtype=float),
            color=plot_gain["phase_color"].fillna("#4C78A8").tolist(),
            edgecolor="white",
            linewidth=0.9,
            height=0.62,
            zorder=3,
        )
        for bar, (_, row) in zip(bars, plot_gain.iterrows()):
            val = float(pd.to_numeric(row["mean_match_rate_pct"], errors="coerce"))
            mean_gain = float(pd.to_numeric(row["mean_matched_gain"], errors="coerce"))
            n_case_model = int(pd.to_numeric(row["n_case_model"], errors="coerce"))
            if n_case_model < 5:
                bar.set_hatch("//")
                bar.set_alpha(0.65)
            ax_cmp.text(
                val + 0.8,
                bar.get_y() + bar.get_height() / 2.0,
                (
                    f"{val:.1f}% | +{mean_gain:.2f}项 | n={n_case_model}，样本偏少，仅供参考"
                    if n_case_model < 5
                    else f"{val:.1f}% | +{mean_gain:.2f}项 | n={n_case_model}"
                ),
                va="center",
                ha="left",
                fontsize=8.9,
                color="#1F2D3D",
            )
        ax_cmp.set_yticks(y_pos)
        ax_cmp.set_yticklabels(plot_gain["plot_label"].tolist(), fontsize=9.2)
        ax_cmp.invert_yaxis()
        d1_split = int((plot_gain["phase_key"] == "D1").sum())
        if 0 < d1_split < len(plot_gain):
            ax_cmp.axhline(d1_split - 0.5, color="#D7E1EA", linewidth=1.0, linestyle="--", zorder=1)
    else:
        ax_cmp.text(0.5, 0.5, "无可绘制的额外检查轮次数据", ha="center", va="center", transform=ax_cmp.transAxes)
        ax_cmp.set_yticks([])
    x_max = float(pd.to_numeric(plot_gain["mean_match_rate_pct"], errors="coerce").max()) if not plot_gain.empty else 1.0
    ax_cmp.set_xlim(0, max(65.0, x_max + 24.0))
    ax_cmp.set_xlabel("当前轮次平均诊断信息匹配率 (%)")
    ax_cmp.set_ylabel("相邻额外检查轮次比较")
    ax_cmp.set_title("额外检查轮次与诊断证据充分性")
    ax_cmp.grid(alpha=0.20, axis="x", zorder=0)
    _set_full_axis_border(ax_cmp, lw=1.1)
    fig_cmp.subplots_adjust(left=0.31, right=0.97, top=0.88, bottom=0.12)
    _save_fig(out_check_gain_panel)
    _save_table_png(check_gain_paper, out_check_gain_table, "G4-C3 相邻额外检查轮次信息收益摘要表")

    final_dx_source_rel = ""
    final_dx_detail_sheet = ""
    final_dx_load_error = ""
    final_dx_stage_summary = pd.DataFrame(
        columns=[
            "stage_key",
            "stage_order",
            "stage_label",
            "n_case_model",
            "n_case",
            "n_center",
            "n_model",
            "mean_proximity_score",
            "median_proximity_score",
            "std_proximity_score",
            "mean_distance",
            "median_distance",
        ]
    )
    final_dx_transition_summary = pd.DataFrame(
        columns=[
            "compare_key",
            "compare_order",
            "compare_label",
            "n_case_model",
            "n_case",
            "mean_prev_score",
            "mean_curr_score",
            "mean_delta_score",
            "median_delta_score",
            "mean_prev_distance",
            "mean_curr_distance",
            "mean_distance_reduction",
            "n_more_near",
            "n_same",
            "n_farther",
            "pct_more_near",
            "pct_same",
            "pct_farther",
            "n_non_decreasing",
            "pct_non_decreasing",
        ]
    )
    final_dx_triplet = pd.DataFrame(
        columns=[
            "center",
            "model",
            "model_short",
            "case_id",
            "trajectory_id",
            "d1_score",
            "d2_score",
            "d3_score",
            "d1_distance",
            "d2_distance",
            "d3_distance",
            "delta_score_d2_vs_d1",
            "delta_score_d3_vs_d2",
            "delta_score_d3_vs_d1",
            "distance_reduction_d2_vs_d1",
            "distance_reduction_d3_vs_d2",
            "distance_reduction_d3_vs_d1",
            "transition_d2_vs_d1",
            "transition_d3_vs_d2",
            "transition_d3_vs_d1",
            "non_decreasing_d2_vs_d1",
            "non_decreasing_d3_vs_d2",
            "non_decreasing_d3_vs_d1",
            "all_non_decreasing",
            "strict_monotonic_non_decreasing",
            "trajectory_trend",
        ]
    )
    final_dx_detail = pd.DataFrame(
        columns=[
            "task_id",
            "center",
            "model",
            "model_short",
            "case_id",
            "trajectory_id",
            "stage",
            "stage_key",
            "stage_order",
            "stage_label",
            "proximity_score",
            "distance",
            "conclusion",
            "reason",
            "source_origin",
            "error",
            "source_path",
            "source_sheet",
        ]
    )
    final_dx_round_case = pd.DataFrame(
        columns=[
            "center",
            "model",
            "model_short",
            "case_id",
            "trajectory_id",
            "d1_score",
            "d2_score",
            "d3_score",
            "delta_score_d2_vs_d1",
            "delta_score_d3_vs_d2",
            "delta_score_d3_vs_d1",
            "non_decreasing_d3_vs_d1",
            "trajectory_trend",
            "d1_check_count",
            "d2_check_count",
            "total_check_count",
            "d1_match_rate",
            "d2_match_rate",
            "total_match_rate",
            "total_requested_count",
            "total_matched_count",
            "total_round_group",
            "total_round_group_order",
            "d1_round_group",
            "d1_round_group_order",
            "d2_round_group",
            "d2_round_group_order",
            "source_path_proximity",
            "source_sheet_proximity",
            "source_path_metrics",
            "source_sheet_metrics",
        ]
    )
    final_dx_round_stage_long = pd.DataFrame(
        columns=[
            "center",
            "model",
            "model_short",
            "case_id",
            "trajectory_id",
            "stage_key",
            "stage_order",
            "stage_label",
            "proximity_score",
            "total_round_group",
            "total_round_group_order",
            "d1_round_group",
            "d1_round_group_order",
            "d2_round_group",
            "d2_round_group_order",
            "source_path_proximity",
            "source_sheet_proximity",
            "source_path_metrics",
            "source_sheet_metrics",
        ]
    )
    final_dx_total_round_stage_summary = pd.DataFrame()
    final_dx_d1_round_stage_summary = pd.DataFrame()
    final_dx_d2_round_stage_summary = pd.DataFrame()
    final_dx_total_round_gain_summary = pd.DataFrame()
    final_dx_d1_round_gain_summary = pd.DataFrame()
    final_dx_d2_round_gain_summary = pd.DataFrame()
    final_dx_model_total_round_gain_summary = pd.DataFrame()
    admission_info_gain_case = pd.DataFrame()
    admission_info_gain_model_summary = pd.DataFrame()

    def _resolve_final_dx_proximity_workbook() -> Path:
        file_name = "llm_results_gemini-2.5-pro__yunwu_api.xlsx"
        candidates = [
            RAW_DIR / file_name,
            RAW_DIR / "latest_summary_snapshot" / file_name,
            ROOT / "outputs" / "latest" / "summary" / file_name,
        ]
        for path in candidates:
            if path.exists():
                return path
        raise FileNotFoundError(f"missing final diagnosis proximity workbook: {file_name}")

    def _classify_proximity_transition(delta: float, tol: float = 0.01) -> str:
        if pd.isna(delta):
            return "缺失"
        if float(delta) > tol:
            return "更接近"
        if float(delta) < -tol:
            return "更远"
        return "基本不变"

    def _round_group_info(value: Any, cap: int = 4, min_value: int = 1) -> tuple[str, int]:
        if pd.isna(value):
            return ("缺失", 99)
        try:
            round_value = int(round(float(value)))
        except Exception:
            return ("缺失", 99)
        round_value = max(min_value, round_value)
        if round_value >= cap:
            return (f"{cap}+", cap)
        return (str(round_value), round_value)

    try:
        final_dx_source_path = _resolve_final_dx_proximity_workbook()
        final_dx_source_rel = str(final_dx_source_path.relative_to(ROOT)).replace("\\", "/")
        final_dx_xl = pd.ExcelFile(final_dx_source_path)
        final_dx_detail_sheet = next(
            (sheet for sheet in final_dx_xl.sheet_names if "最终诊断接近度-明细" in str(sheet)),
            "",
        )
        if not final_dx_detail_sheet:
            raise ValueError("workbook missing sheet: 最终诊断接近度-明细")
        final_dx_raw = pd.read_excel(final_dx_source_path, sheet_name=final_dx_detail_sheet)
        final_dx_needed = {
            "任务ID": "task_id",
            "中心": "center",
            "被评测模型": "model",
            "病例ID": "case_id",
            "阶段": "stage",
            "接近度得分(0-1)": "proximity_score",
            "距离(0-1)": "distance",
            "结论": "conclusion",
            "理由": "reason",
            "来源": "source_origin",
            "错误": "error",
        }
        missing_final_dx_cols = [col for col in final_dx_needed if col not in final_dx_raw.columns]
        if missing_final_dx_cols:
            raise ValueError(f"final diagnosis proximity workbook missing columns: {missing_final_dx_cols}")
        final_dx_stage_map = {
            "D1_Outpatient_Decision": ("D1", 1, "D1 初始诊断"),
            "D2_Admission_Decision": ("D2", 2, "D2 修正诊断"),
            "D3_Surgery_Decision": ("D3", 3, "D3 最终诊断"),
        }
        final_dx_detail = final_dx_raw[list(final_dx_needed.keys())].rename(columns=final_dx_needed).copy()
        final_dx_detail = final_dx_detail[final_dx_detail["stage"].astype(str).isin(final_dx_stage_map)].copy()
        final_dx_detail["stage_key"] = final_dx_detail["stage"].map(lambda x: final_dx_stage_map.get(str(x), ("", np.nan, ""))[0])
        final_dx_detail["stage_order"] = final_dx_detail["stage"].map(
            lambda x: final_dx_stage_map.get(str(x), ("", np.nan, ""))[1]
        )
        final_dx_detail["stage_label"] = final_dx_detail["stage"].map(
            lambda x: final_dx_stage_map.get(str(x), ("", np.nan, ""))[2]
        )
        final_dx_detail["model_short"] = final_dx_detail["model"].map(MODEL_SHORT).fillna(final_dx_detail["model"].astype(str))
        final_dx_detail["trajectory_id"] = (
            final_dx_detail["center"].astype(str)
            + "|"
            + final_dx_detail["model"].astype(str)
            + "|"
            + final_dx_detail["case_id"].astype(str)
        )
        final_dx_detail["proximity_score"] = pd.to_numeric(final_dx_detail["proximity_score"], errors="coerce")
        final_dx_detail["distance"] = pd.to_numeric(final_dx_detail["distance"], errors="coerce")
        final_dx_detail["source_path"] = final_dx_source_rel
        final_dx_detail["source_sheet"] = final_dx_detail_sheet
        # 与 Sankey 一致口径：D2 手动不通过后不应进入 D3 最终诊断阶段
        final_dx_detail = _filter_stage_case_eligibility(final_dx_detail, "stage_key", stage_case_sets)
        final_dx_detail = (
            final_dx_detail.sort_values(["center", "model_short", "case_id", "stage_order"], kind="mergesort")
            .drop_duplicates(subset=["trajectory_id", "stage_key"], keep="last")
            .reset_index(drop=True)
        )
        complete_ids = (
            final_dx_detail.groupby("trajectory_id")["stage_key"].nunique().loc[lambda s: s >= 3].index.tolist()
        )
        final_dx_detail = final_dx_detail[final_dx_detail["trajectory_id"].isin(complete_ids)].copy()
        if final_dx_detail.empty:
            raise ValueError("no complete D1/D2/D3 trajectories found in final diagnosis proximity workbook")
        final_dx_triplet = (
            final_dx_detail.pivot_table(
                index=["center", "model", "model_short", "case_id", "trajectory_id"],
                columns="stage_key",
                values=["proximity_score", "distance"],
                aggfunc="first",
                observed=True,
            )
            .sort_index(axis=1)
            .reset_index()
        )
        final_dx_triplet.columns = [
            "_".join([part for part in col if part]).strip("_") if isinstance(col, tuple) else str(col)
            for col in final_dx_triplet.columns
        ]
        final_dx_triplet = final_dx_triplet.rename(
            columns={
                "proximity_score_D1": "d1_score",
                "proximity_score_D2": "d2_score",
                "proximity_score_D3": "d3_score",
                "distance_D1": "d1_distance",
                "distance_D2": "d2_distance",
                "distance_D3": "d3_distance",
            }
        )
        for col in ["d1_score", "d2_score", "d3_score", "d1_distance", "d2_distance", "d3_distance"]:
            final_dx_triplet[col] = pd.to_numeric(final_dx_triplet[col], errors="coerce")
        final_dx_triplet["delta_score_d2_vs_d1"] = final_dx_triplet["d2_score"] - final_dx_triplet["d1_score"]
        final_dx_triplet["delta_score_d3_vs_d2"] = final_dx_triplet["d3_score"] - final_dx_triplet["d2_score"]
        final_dx_triplet["delta_score_d3_vs_d1"] = final_dx_triplet["d3_score"] - final_dx_triplet["d1_score"]
        final_dx_triplet["distance_reduction_d2_vs_d1"] = final_dx_triplet["d1_distance"] - final_dx_triplet["d2_distance"]
        final_dx_triplet["distance_reduction_d3_vs_d2"] = final_dx_triplet["d2_distance"] - final_dx_triplet["d3_distance"]
        final_dx_triplet["distance_reduction_d3_vs_d1"] = final_dx_triplet["d1_distance"] - final_dx_triplet["d3_distance"]
        final_dx_triplet["transition_d2_vs_d1"] = final_dx_triplet["delta_score_d2_vs_d1"].map(_classify_proximity_transition)
        final_dx_triplet["transition_d3_vs_d2"] = final_dx_triplet["delta_score_d3_vs_d2"].map(_classify_proximity_transition)
        final_dx_triplet["transition_d3_vs_d1"] = final_dx_triplet["delta_score_d3_vs_d1"].map(_classify_proximity_transition)
        final_dx_triplet["non_decreasing_d2_vs_d1"] = final_dx_triplet["delta_score_d2_vs_d1"] >= -0.01
        final_dx_triplet["non_decreasing_d3_vs_d2"] = final_dx_triplet["delta_score_d3_vs_d2"] >= -0.01
        final_dx_triplet["non_decreasing_d3_vs_d1"] = final_dx_triplet["delta_score_d3_vs_d1"] >= -0.01
        final_dx_triplet["all_non_decreasing"] = (
            final_dx_triplet["non_decreasing_d2_vs_d1"] & final_dx_triplet["non_decreasing_d3_vs_d2"]
        )
        final_dx_triplet["strict_monotonic_non_decreasing"] = (
            final_dx_triplet["delta_score_d2_vs_d1"].ge(0.01) & final_dx_triplet["delta_score_d3_vs_d2"].ge(0.01)
        )
        final_dx_triplet["trajectory_trend"] = np.select(
            [
                ~(final_dx_triplet["non_decreasing_d2_vs_d1"] & final_dx_triplet["non_decreasing_d3_vs_d2"]),
                final_dx_triplet["strict_monotonic_non_decreasing"],
            ],
            ["存在回退", "持续更接近"],
            default="单调不下降",
        )
        final_dx_triplet = final_dx_triplet.sort_values(["center", "model_short", "case_id"], kind="mergesort").reset_index(drop=True)
        final_dx_stage_summary = (
            final_dx_detail.groupby(["stage_key", "stage_order", "stage_label"], as_index=False)
            .agg(
                n_case_model=("trajectory_id", "nunique"),
                n_case=("case_id", "nunique"),
                n_center=("center", "nunique"),
                n_model=("model", "nunique"),
                mean_proximity_score=("proximity_score", "mean"),
                median_proximity_score=("proximity_score", "median"),
                std_proximity_score=("proximity_score", lambda s: float(pd.to_numeric(s, errors="coerce").std(ddof=0))),
                mean_distance=("distance", "mean"),
                median_distance=("distance", "median"),
            )
            .sort_values(["stage_order"], kind="mergesort")
            .reset_index(drop=True)
        )
        transition_specs = [
            ("D2_vs_D1", 1, "D2 相对 D1", "d1_score", "d2_score", "d1_distance", "d2_distance"),
            ("D3_vs_D2", 2, "D3 相对 D2", "d2_score", "d3_score", "d2_distance", "d3_distance"),
            ("D3_vs_D1", 3, "D3 相对 D1", "d1_score", "d3_score", "d1_distance", "d3_distance"),
        ]
        transition_rows: list[dict[str, Any]] = []
        for compare_key, compare_order, compare_label, prev_score_col, curr_score_col, prev_dist_col, curr_dist_col in transition_specs:
            delta = pd.to_numeric(final_dx_triplet[curr_score_col], errors="coerce") - pd.to_numeric(
                final_dx_triplet[prev_score_col], errors="coerce"
            )
            cat = delta.map(_classify_proximity_transition)
            n_case_model = int(delta.notna().sum())
            transition_rows.append(
                {
                    "compare_key": compare_key,
                    "compare_order": compare_order,
                    "compare_label": compare_label,
                    "n_case_model": n_case_model,
                    "n_case": int(final_dx_triplet.loc[delta.notna(), "case_id"].nunique()),
                    "mean_prev_score": float(pd.to_numeric(final_dx_triplet[prev_score_col], errors="coerce").mean()),
                    "mean_curr_score": float(pd.to_numeric(final_dx_triplet[curr_score_col], errors="coerce").mean()),
                    "mean_delta_score": float(pd.to_numeric(delta, errors="coerce").mean()),
                    "median_delta_score": float(pd.to_numeric(delta, errors="coerce").median()),
                    "mean_prev_distance": float(pd.to_numeric(final_dx_triplet[prev_dist_col], errors="coerce").mean()),
                    "mean_curr_distance": float(pd.to_numeric(final_dx_triplet[curr_dist_col], errors="coerce").mean()),
                    "mean_distance_reduction": float(
                        (
                            pd.to_numeric(final_dx_triplet[prev_dist_col], errors="coerce")
                            - pd.to_numeric(final_dx_triplet[curr_dist_col], errors="coerce")
                        ).mean()
                    ),
                    "n_more_near": int((cat == "更接近").sum()),
                    "n_same": int((cat == "基本不变").sum()),
                    "n_farther": int((cat == "更远").sum()),
                    "pct_more_near": float((cat == "更接近").mean() * 100.0) if n_case_model else np.nan,
                    "pct_same": float((cat == "基本不变").mean() * 100.0) if n_case_model else np.nan,
                    "pct_farther": float((cat == "更远").mean() * 100.0) if n_case_model else np.nan,
                    "n_non_decreasing": int((delta >= -0.01).sum()),
                    "pct_non_decreasing": float((delta >= -0.01).mean() * 100.0) if n_case_model else np.nan,
                }
            )
        final_dx_transition_summary = pd.DataFrame(transition_rows)

        final_dx_metrics = chk[
            [
                "center",
                "model",
                "case_id",
                "d1_check_count",
                "d2_check_count",
                "d1_match_rate",
                "d2_match_rate",
                "D1_Outpatient_Loop__requested_total",
                "D2_SuggestedFromD1Decision__requested_total",
                "D2_Admission_Loop__requested_total",
                "D1_Outpatient_Loop__matched_total",
                "D2_SuggestedFromD1Decision__matched_total",
                "D2_Admission_Loop__matched_total",
            ]
        ].copy()
        for col in final_dx_metrics.columns:
            if col not in {"center", "model", "case_id"}:
                final_dx_metrics[col] = pd.to_numeric(final_dx_metrics[col], errors="coerce")
        final_dx_metrics["total_requested_count"] = (
            final_dx_metrics["D1_Outpatient_Loop__requested_total"].fillna(0.0)
            + final_dx_metrics["D2_SuggestedFromD1Decision__requested_total"].fillna(0.0)
            + final_dx_metrics["D2_Admission_Loop__requested_total"].fillna(0.0)
        )
        final_dx_metrics["total_matched_count"] = (
            final_dx_metrics["D1_Outpatient_Loop__matched_total"].fillna(0.0)
            + final_dx_metrics["D2_SuggestedFromD1Decision__matched_total"].fillna(0.0)
            + final_dx_metrics["D2_Admission_Loop__matched_total"].fillna(0.0)
        )
        final_dx_metrics["total_match_rate"] = np.where(
            final_dx_metrics["total_requested_count"] > 0,
            final_dx_metrics["total_matched_count"] / final_dx_metrics["total_requested_count"],
            np.nan,
        )
        final_dx_round_case = final_dx_triplet.merge(
            final_dx_metrics,
            on=["center", "model", "case_id"],
            how="left",
        )
        final_dx_round_case["total_check_count"] = (
            pd.to_numeric(final_dx_round_case["d1_check_count"], errors="coerce").fillna(0.0)
            + pd.to_numeric(final_dx_round_case["d2_check_count"], errors="coerce").fillna(0.0)
        )
        total_round_info = final_dx_round_case["total_check_count"].map(lambda v: _round_group_info(v, cap=4, min_value=1))
        d1_round_info = final_dx_round_case["d1_check_count"].map(lambda v: _round_group_info(v, cap=4, min_value=1))
        d2_round_info = final_dx_round_case["d2_check_count"].map(lambda v: _round_group_info(v, cap=4, min_value=1))
        final_dx_round_case["total_round_group"] = total_round_info.map(lambda item: item[0])
        final_dx_round_case["total_round_group_order"] = total_round_info.map(lambda item: item[1])
        final_dx_round_case["d1_round_group"] = d1_round_info.map(lambda item: item[0])
        final_dx_round_case["d1_round_group_order"] = d1_round_info.map(lambda item: item[1])
        final_dx_round_case["d2_round_group"] = d2_round_info.map(lambda item: item[0])
        final_dx_round_case["d2_round_group_order"] = d2_round_info.map(lambda item: item[1])
        final_dx_round_case["source_path_proximity"] = final_dx_source_rel
        final_dx_round_case["source_sheet_proximity"] = final_dx_detail_sheet
        final_dx_round_case["source_path_metrics"] = "analysis_viz/data/raw/metrics_source_data.xlsx"
        final_dx_round_case["source_sheet_metrics"] = "metrics_by_case"
        final_dx_round_case = final_dx_round_case[
            [
                "center",
                "model",
                "model_short",
                "case_id",
                "trajectory_id",
                "d1_score",
                "d2_score",
                "d3_score",
                "delta_score_d2_vs_d1",
                "delta_score_d3_vs_d2",
                "delta_score_d3_vs_d1",
                "non_decreasing_d3_vs_d1",
                "trajectory_trend",
                "d1_check_count",
                "d2_check_count",
                "total_check_count",
                "d1_match_rate",
                "d2_match_rate",
                "total_match_rate",
                "total_requested_count",
                "total_matched_count",
                "total_round_group",
                "total_round_group_order",
                "d1_round_group",
                "d1_round_group_order",
                "d2_round_group",
                "d2_round_group_order",
                "source_path_proximity",
                "source_sheet_proximity",
                "source_path_metrics",
                "source_sheet_metrics",
            ]
        ].sort_values(
            ["total_round_group_order", "d1_round_group_order", "d2_round_group_order", "center", "model_short", "case_id"],
            kind="mergesort",
        ).reset_index(drop=True)

        stage_rows: list[pd.DataFrame] = []
        for stage_key, stage_order, stage_label, score_col in [
            ("D1", 1, "D1 初始诊断", "d1_score"),
            ("D2", 2, "D2 修正诊断", "d2_score"),
            ("D3", 3, "D3 最终诊断", "d3_score"),
        ]:
            stage_frame = final_dx_round_case[
                [
                    "center",
                    "model",
                    "model_short",
                    "case_id",
                    "trajectory_id",
                    "total_round_group",
                    "total_round_group_order",
                    "d1_round_group",
                    "d1_round_group_order",
                    "d2_round_group",
                    "d2_round_group_order",
                    "source_path_proximity",
                    "source_sheet_proximity",
                    "source_path_metrics",
                    "source_sheet_metrics",
                ]
            ].copy()
            stage_frame["stage_key"] = stage_key
            stage_frame["stage_order"] = stage_order
            stage_frame["stage_label"] = stage_label
            stage_frame["proximity_score"] = pd.to_numeric(final_dx_round_case[score_col], errors="coerce")
            stage_rows.append(stage_frame)
        final_dx_round_stage_long = pd.concat(stage_rows, ignore_index=True)

        def _build_round_stage_summary(group_col: str, group_order_col: str) -> pd.DataFrame:
            summary = (
                final_dx_round_stage_long.groupby([group_col, group_order_col, "stage_key", "stage_order", "stage_label"], as_index=False)
                .agg(
                    n_case_model=("trajectory_id", "nunique"),
                    n_case=("case_id", "nunique"),
                    mean_proximity_score=("proximity_score", "mean"),
                    median_proximity_score=("proximity_score", "median"),
                    std_proximity_score=("proximity_score", lambda s: float(pd.to_numeric(s, errors="coerce").std(ddof=0))),
                )
                .sort_values([group_order_col, "stage_order"], kind="mergesort")
                .reset_index(drop=True)
            )
            return summary.rename(columns={group_col: "round_group", group_order_col: "round_group_order"})

        def _build_round_gain_summary(group_col: str, group_order_col: str) -> pd.DataFrame:
            grouped = (
                final_dx_round_case.groupby([group_col, group_order_col], as_index=False)
                .agg(
                    n_case_model=("trajectory_id", "nunique"),
                    n_case=("case_id", "nunique"),
                    mean_d1_score=("d1_score", "mean"),
                    mean_d2_score=("d2_score", "mean"),
                    mean_d3_score=("d3_score", "mean"),
                    mean_delta_score_d3_vs_d1=("delta_score_d3_vs_d1", "mean"),
                    median_delta_score_d3_vs_d1=("delta_score_d3_vs_d1", "median"),
                    std_delta_score_d3_vs_d1=("delta_score_d3_vs_d1", lambda s: float(pd.to_numeric(s, errors="coerce").std(ddof=0))),
                    pct_non_decreasing_d3_vs_d1=("non_decreasing_d3_vs_d1", lambda s: float(pd.to_numeric(s, errors="coerce").fillna(False).mean() * 100.0)),
                )
                .sort_values([group_order_col], kind="mergesort")
                .reset_index(drop=True)
            )
            return grouped.rename(columns={group_col: "round_group", group_order_col: "round_group_order"})

        final_dx_total_round_stage_summary = _build_round_stage_summary("total_round_group", "total_round_group_order")
        final_dx_d1_round_stage_summary = _build_round_stage_summary("d1_round_group", "d1_round_group_order")
        final_dx_d2_round_stage_summary = _build_round_stage_summary("d2_round_group", "d2_round_group_order")
        final_dx_total_round_gain_summary = _build_round_gain_summary("total_round_group", "total_round_group_order")
        final_dx_d1_round_gain_summary = _build_round_gain_summary("d1_round_group", "d1_round_group_order")
        final_dx_d2_round_gain_summary = _build_round_gain_summary("d2_round_group", "d2_round_group_order")
        final_dx_model_total_round_gain_summary = (
            final_dx_round_case.groupby(["model_short", "d2_round_group", "d2_round_group_order"], as_index=False)
            .agg(
                n_case_model=("trajectory_id", "nunique"),
                mean_delta_score_d2_vs_d1=("delta_score_d2_vs_d1", "mean"),
                median_delta_score_d2_vs_d1=("delta_score_d2_vs_d1", "median"),
                std_delta_score_d2_vs_d1=("delta_score_d2_vs_d1", lambda s: float(pd.to_numeric(s, errors="coerce").std(ddof=0))),
                mean_d2_score=("d2_score", "mean"),
            )
            .rename(columns={"d2_round_group": "admission_round_group", "d2_round_group_order": "admission_round_group_order"})
            .sort_values(["model_short", "admission_round_group_order"], kind="mergesort")
            .reset_index(drop=True)
        )
        final_dx_admission_round_gain_summary = (
            final_dx_round_case.groupby(["d2_round_group", "d2_round_group_order"], as_index=False)
            .agg(
                n_case_model=("trajectory_id", "nunique"),
                n_case=("case_id", "nunique"),
                mean_delta_score_d2_vs_d1=("delta_score_d2_vs_d1", "mean"),
                median_delta_score_d2_vs_d1=("delta_score_d2_vs_d1", "median"),
                std_delta_score_d2_vs_d1=("delta_score_d2_vs_d1", lambda s: float(pd.to_numeric(s, errors="coerce").std(ddof=0))),
            )
            .rename(columns={"d2_round_group": "admission_round_group", "d2_round_group_order": "admission_round_group_order"})
            .sort_values(["admission_round_group_order"], kind="mergesort")
            .reset_index(drop=True)
        )
    except Exception as exc:
        final_dx_load_error = str(exc)

    fig_shift, ax_shift = plt.subplots(figsize=(10.4, 6.2))
    if not final_dx_triplet.empty and not final_dx_stage_summary.empty:
        stage_summary = final_dx_stage_summary.sort_values("stage_order").copy()
        stage_order_plot = ["D1", "D2", "D3"]
        stage_label_map = {"D1": "D1 初始诊断", "D2": "D2 修正诊断", "D3": "D3 最终诊断"}
        box_data: list[np.ndarray] = []
        mean_vals: list[float] = []
        xticks: list[str] = []
        valid_stage_order: list[str] = []
        for st in stage_order_plot:
            vals = pd.to_numeric(
                final_dx_detail.loc[final_dx_detail["stage_key"].astype(str).eq(st), "proximity_score"],
                errors="coerce",
            ).dropna()
            if vals.empty:
                continue
            valid_stage_order.append(st)
            box_data.append(vals.to_numpy(dtype=float))
            mean_vals.append(float(vals.mean()))
            xticks.append(stage_label_map.get(st, st))
        if box_data:
            pos = np.arange(1, len(box_data) + 1)
            bxp = ax_shift.boxplot(
                box_data,
                positions=pos,
                widths=0.52,
                patch_artist=True,
                showmeans=True,
                medianprops={"color": "#1F2D3D", "linewidth": 1.3},
                meanprops={"marker": "o", "markerfacecolor": "#111111", "markeredgecolor": "white", "markersize": 5.2},
            )
            box_colors = ["#BFD6EA", "#86B4DA", "#4C78A8"]
            for i, patch in enumerate(bxp["boxes"]):
                patch.set_facecolor(box_colors[min(i, len(box_colors) - 1)])
                patch.set_alpha(0.82)
                patch.set_edgecolor("#2B3A4A")
                patch.set_linewidth(1.0)
            ax_shift.plot(pos, mean_vals, color="#111111", linewidth=2.2, marker="o", markersize=5.8, label="阶段均值", zorder=4)
            stage_n_map = {
                str(r["stage_key"]): int(pd.to_numeric(r["n_case_model"], errors="coerce"))
                for _, r in stage_summary.iterrows()
            }
            for idx, (x, score, st) in enumerate(zip(pos, mean_vals, valid_stage_order)):
                n_case_model = int(stage_n_map.get(str(st), 0))
                y_off = 0.03 if idx < len(pos) - 1 else 0.012
                txt = f"{score:.2f}  n={n_case_model}"
                if idx == len(pos) - 1:
                    txt = f"{score:.2f} n={n_case_model}"
                ax_shift.text(
                    x,
                    score + y_off,
                    txt,
                    ha="center",
                    va="bottom",
                    fontsize=9.0,
                    color="#111111",
                    fontweight="semibold",
                    zorder=5,
                )
        transition_box = final_dx_transition_summary.set_index("compare_key") if not final_dx_transition_summary.empty else None
        n_triplet = int(len(final_dx_triplet))
        summary_lines = [f"完整病例-模型轨迹 n={n_triplet}"]
        if transition_box is not None:
            if "D2_vs_D1" in transition_box.index:
                summary_lines.append(f"D2 ≥ D1: {int(transition_box.at['D2_vs_D1', 'n_non_decreasing'])}/{n_triplet}")
            if "D3_vs_D2" in transition_box.index:
                summary_lines.append(f"D3 ≥ D2: {int(transition_box.at['D3_vs_D2', 'n_non_decreasing'])}/{n_triplet}")
            if "D3_vs_D1" in transition_box.index:
                summary_lines.append(f"D3 ≥ D1: {int(transition_box.at['D3_vs_D1', 'n_non_decreasing'])}/{n_triplet}")
        summary_lines.append(
            f"全程无回退: {int(pd.to_numeric(final_dx_triplet['all_non_decreasing'], errors='coerce').fillna(False).sum())}/{n_triplet}"
        )
        if n_triplet < 30:
            summary_lines.append("当前样本量较小，按探索性结果解读")
        ax_shift.text(
            1.02,
            0.98,
            "\n".join(summary_lines),
            transform=ax_shift.transAxes,
            va="top",
            ha="left",
            fontsize=8.8,
            color="#1F2D3D",
            bbox={"facecolor": "white", "alpha": 0.92, "edgecolor": "#D7E1EA", "pad": 4.0},
            zorder=6,
        )
        ax_shift.set_xticks(np.arange(1, len(xticks) + 1))
        ax_shift.set_xticklabels(xticks, fontsize=9.4)
        ax_shift.set_ylim(-0.02, 1.05)
        ax_shift.legend(loc="lower right", fontsize=8.6, frameon=True)
    else:
        msg = "无可绘制的最终诊断接近度轨迹"
        if final_dx_load_error:
            msg += f"\n{final_dx_load_error}"
        ax_shift.text(0.5, 0.5, msg, ha="center", va="center", transform=ax_shift.transAxes)
        ax_shift.set_xticks([])
    ax_shift.set_ylabel("最终诊断接近度，越高越接近")
    ax_shift.set_xlabel("诊断阶段")
    ax_shift.set_title("同病例同模型：阶段信息增加后诊断是否更接近GT最终诊断")
    ax_shift.grid(alpha=0.20, axis="y", zorder=0)
    _set_full_axis_border(ax_shift, lw=1.1)
    fig_shift.subplots_adjust(left=0.12, right=0.78, top=0.88, bottom=0.14)
    _save_fig(out_check_gain_shift_panel)

    round_group_color_map = {
        1: "#CFE1F2",
        2: "#8FB9DD",
        3: "#4F8FC0",
        4: "#195A91",
    }

    def _round_group_label(order_value: int) -> str:
        return "4+轮" if int(order_value) >= 4 else f"{int(order_value)}轮"

    def _plot_round_stage_panel(
        ax: plt.Axes,
        stage_summary: pd.DataFrame,
        gain_summary: pd.DataFrame,
        panel_title: str,
    ) -> None:
        if stage_summary.empty:
            msg = "无可绘制的检查轮次分层结果"
            if final_dx_load_error:
                msg += f"\n{final_dx_load_error}"
            ax.text(0.5, 0.5, msg, ha="center", va="center", transform=ax.transAxes)
            ax.set_xticks([])
            _set_full_axis_border(ax, lw=1.1)
            return
        stage_positions = np.arange(3)
        for order_value in sorted(stage_summary["round_group_order"].dropna().unique()):
            order_int = int(order_value)
            sub = stage_summary[stage_summary["round_group_order"] == order_int].sort_values("stage_order", kind="mergesort")
            if sub.empty:
                continue
            gain_row = (
                gain_summary[gain_summary["round_group_order"] == order_int].head(1)
                if "round_group_order" in gain_summary.columns
                else pd.DataFrame()
            )
            n_case_model = int(gain_row["n_case_model"].iloc[0]) if not gain_row.empty else int(sub["n_case_model"].max())
            color = round_group_color_map.get(order_int, "#7F8EA3")
            ax.plot(
                stage_positions,
                sub["mean_proximity_score"].to_numpy(dtype=float),
                color=color,
                linewidth=2.3,
                marker="o",
                markersize=5.4,
                label=f"{_round_group_label(order_int)} (n={n_case_model})",
                zorder=3,
            )
        if not final_dx_stage_summary.empty:
            overall = final_dx_stage_summary.sort_values("stage_order", kind="mergesort")
            ax.plot(
                stage_positions,
                overall["mean_proximity_score"].to_numpy(dtype=float),
                color="#111111",
                linewidth=1.8,
                linestyle="--",
                marker="o",
                markersize=4.8,
                label="总体均值",
                zorder=2,
            )
        ax.set_xticks(stage_positions)
        ax.set_xticklabels(["D1", "D2", "D3"], fontsize=9.6)
        ax.set_ylim(0.45, 1.02)
        ax.set_title(panel_title)
        ax.grid(alpha=0.20, axis="y", zorder=0)
        ax.legend(loc="lower right", fontsize=7.8, frameon=True)
        _set_full_axis_border(ax, lw=1.1)

    fig_round_strata, (ax_round_total, ax_round_d1, ax_round_d2) = plt.subplots(1, 3, figsize=(19.6, 5.6), sharey=True)
    _plot_round_stage_panel(
        ax_round_total,
        final_dx_total_round_stage_summary,
        final_dx_total_round_gain_summary,
        "a. 按总检查轮次分层",
    )
    _plot_round_stage_panel(
        ax_round_d1,
        final_dx_d1_round_stage_summary,
        final_dx_d1_round_gain_summary,
        "b. 按门诊阶段检查轮次分层",
    )
    _plot_round_stage_panel(
        ax_round_d2,
        final_dx_d2_round_stage_summary,
        final_dx_d2_round_gain_summary,
        "c. 按住院阶段检查轮次分层",
    )
    ax_round_total.set_ylabel("最终诊断接近度，越高越接近")
    ax_round_total.set_xlabel("诊断阶段")
    ax_round_d1.set_xlabel("诊断阶段")
    ax_round_d2.set_xlabel("诊断阶段")
    fig_round_strata.suptitle("检查轮次分层后：三阶段最终诊断接近度轨迹", fontsize=14, y=0.98)
    fig_round_strata.subplots_adjust(left=0.06, right=0.99, top=0.87, bottom=0.14, wspace=0.08)
    _save_fig(out_final_dx_round_strata_panel)

    gain_y_lo, gain_y_hi = _adaptive_ylim(
        final_dx_round_case["delta_score_d3_vs_d1"],
        fallback=(-0.10, 0.26),
        domain=(None, None),
        min_span=0.30,
    )
    gain_pad = max(0.015, (gain_y_hi - gain_y_lo) * 0.06)

    def _plot_round_gain_box(
        ax: plt.Axes,
        group_col: str,
        order_col: str,
        gain_summary: pd.DataFrame,
        panel_title: str,
    ) -> None:
        if final_dx_round_case.empty or gain_summary.empty:
            msg = "无可绘制的接近度提升分布"
            if final_dx_load_error:
                msg += f"\n{final_dx_load_error}"
            ax.text(0.5, 0.5, msg, ha="center", va="center", transform=ax.transAxes)
            ax.set_xticks([])
            _set_full_axis_border(ax, lw=1.1)
            return
        order_values = [int(v) for v in gain_summary["round_group_order"].dropna().unique().tolist()]
        order_values = sorted(order_values)
        series_list: list[np.ndarray] = []
        used_orders: list[int] = []
        for order_value in order_values:
            vals = pd.to_numeric(
                final_dx_round_case.loc[final_dx_round_case[order_col] == order_value, "delta_score_d3_vs_d1"],
                errors="coerce",
            ).dropna().to_numpy(dtype=float)
            if len(vals) == 0:
                continue
            used_orders.append(order_value)
            series_list.append(vals)
        if not series_list:
            ax.text(0.5, 0.5, "无有效数值", ha="center", va="center", transform=ax.transAxes)
            ax.set_xticks([])
            _set_full_axis_border(ax, lw=1.1)
            return
        positions = list(range(1, len(series_list) + 1))
        bxp = ax.boxplot(
            series_list,
            positions=positions,
            widths=0.62,
            patch_artist=True,
            showmeans=True,
            meanprops={"marker": "o", "markerfacecolor": "#1F2937", "markeredgecolor": "white", "markersize": 5.0},
            medianprops={"color": "#222222", "linewidth": 1.4},
        )
        for patch, order_value in zip(bxp["boxes"], used_orders):
            patch.set_facecolor(round_group_color_map.get(order_value, "#7F8EA3"))
            patch.set_alpha(0.78)
            patch.set_edgecolor("#2B2B2B")
            patch.set_linewidth(1.0)
        for key in ["whiskers", "caps"]:
            for item in bxp.get(key, []):
                item.set_color("#555555")
                item.set_linewidth(1.0)
        xticklabels: list[str] = []
        for pos, order_value in zip(positions, used_orders):
            row = gain_summary[gain_summary["round_group_order"] == order_value].head(1)
            mean_gain = float(pd.to_numeric(row["mean_delta_score_d3_vs_d1"], errors="coerce").iloc[0]) if not row.empty else np.nan
            n_case_model = int(row["n_case_model"].iloc[0]) if not row.empty else 0
            xticklabels.append(f"{_round_group_label(order_value)}\n(n={n_case_model})")
            if not np.isnan(mean_gain):
                ax.text(
                    pos,
                    mean_gain + gain_pad,
                    f"{mean_gain:.2f}",
                    ha="center",
                    va="bottom",
                    fontsize=8.6,
                    color="#1F2D3D",
                )
        ax.axhline(0.0, color="#6B7280", linestyle="--", linewidth=1.0, alpha=0.8)
        ax.set_xticks(positions)
        ax.set_xticklabels(xticklabels, fontsize=9.0)
        ax.set_ylim(gain_y_lo, gain_y_hi + gain_pad * 2.2)
        ax.set_title(panel_title)
        ax.grid(alpha=0.20, axis="y")
        _set_full_axis_border(ax, lw=1.1)

    fig_round_gain, (ax_gain_total, ax_gain_d1, ax_gain_d2) = plt.subplots(1, 3, figsize=(19.6, 5.5), sharey=True)
    _plot_round_gain_box(
        ax_gain_total,
        "total_round_group",
        "total_round_group_order",
        final_dx_total_round_gain_summary,
        "a. 总检查轮次 vs D3-D1 接近度提升",
    )
    _plot_round_gain_box(
        ax_gain_d1,
        "d1_round_group",
        "d1_round_group_order",
        final_dx_d1_round_gain_summary,
        "b. 门诊阶段检查轮次 vs D3-D1 接近度提升",
    )
    _plot_round_gain_box(
        ax_gain_d2,
        "d2_round_group",
        "d2_round_group_order",
        final_dx_d2_round_gain_summary,
        "c. 住院阶段检查轮次 vs D3-D1 接近度提升",
    )
    ax_gain_total.set_ylabel("D3-D1 接近度提升，越高越接近")
    fig_round_gain.suptitle("检查轮次与最终诊断接近度提升分布", fontsize=14, y=0.98)
    fig_round_gain.subplots_adjust(left=0.06, right=0.99, top=0.87, bottom=0.18, wspace=0.08)
    _save_fig(out_final_dx_gain_round_panel)

    fig_model_gain, axes_model_gain = plt.subplots(2, 3, figsize=(14.8, 8.6), sharex=True, sharey=True)
    panel_models = list(MODEL_ORDER) + ["Overall"]
    model_gain_y_lo, model_gain_y_hi = _adaptive_ylim(
        final_dx_model_total_round_gain_summary["mean_delta_score_d2_vs_d1"],
        fallback=(-0.05, 0.24),
        domain=(None, None),
        min_span=0.24,
    )
    model_gain_y_lo = min(model_gain_y_lo, -0.03)
    model_gain_y_hi = max(model_gain_y_hi, 0.18)
    base_round_groups = pd.DataFrame(
        {
            "admission_round_group_order": [1, 2, 3, 4],
            "admission_round_group": ["1", "2", "3", "4+"],
        }
    )
    for ax_model_gain, panel_model in zip(axes_model_gain.flatten(), panel_models):
        if panel_model == "Overall":
            sub = base_round_groups.merge(
                final_dx_admission_round_gain_summary,
                on=["admission_round_group", "admission_round_group_order"],
                how="left",
            )
            color = "#111111"
            title = "Overall"
        else:
            sub = base_round_groups.merge(
                final_dx_model_total_round_gain_summary[final_dx_model_total_round_gain_summary["model_short"] == panel_model],
                on=["admission_round_group", "admission_round_group_order"],
                how="left",
            )
            color = MODEL_COLOR.get(panel_model, "#4C78A8")
            title = str(panel_model)
        ax_model_gain.axhline(0.0, color="#6B7280", linestyle="--", linewidth=0.9, alpha=0.8, zorder=1)
        ax_model_gain.plot(
            sub["admission_round_group_order"],
            pd.to_numeric(sub["mean_delta_score_d2_vs_d1"], errors="coerce"),
            color=color,
            linewidth=2.2,
            marker="o",
            markersize=5.4,
            zorder=3,
        )
        for _, row in sub.iterrows():
            if pd.isna(row["mean_delta_score_d2_vs_d1"]):
                continue
            ax_model_gain.text(
                float(row["admission_round_group_order"]),
                float(row["mean_delta_score_d2_vs_d1"]) + 0.012,
                f"n={int(row['n_case_model'])}",
                ha="center",
                va="bottom",
                fontsize=7.8,
                color="#1F2D3D",
            )
        ax_model_gain.set_title(title, fontsize=10.4)
        ax_model_gain.set_xticks([1, 2, 3, 4])
        ax_model_gain.set_xticklabels(["1轮", "2轮", "3轮", "4+轮"], fontsize=9.0)
        ax_model_gain.set_ylim(model_gain_y_lo, model_gain_y_hi + 0.03)
        ax_model_gain.grid(alpha=0.20, axis="y", zorder=0)
        _set_full_axis_border(ax_model_gain, lw=1.0)
    axes_model_gain[0, 0].set_ylabel("平均 D2-D1 接近度提升")
    axes_model_gain[1, 0].set_ylabel("平均 D2-D1 接近度提升")
    axes_model_gain[1, 0].set_xlabel("入院检查次数")
    axes_model_gain[1, 1].set_xlabel("入院检查次数")
    axes_model_gain[1, 2].set_xlabel("入院检查次数")
    fig_model_gain.suptitle("不同模型：入院检查次数对平均 D2-D1 的影响", fontsize=14, y=0.98)
    fig_model_gain.subplots_adjust(left=0.07, right=0.985, top=0.90, bottom=0.10, wspace=0.14, hspace=0.24)
    _save_fig(out_final_dx_gain_model_panel)

    key_cols = ["center", "model", "case_id"]
    if (not final_dx_round_case.empty) and (not check_gain_detail.empty):
        need_admission = (
            final_dx_round_case.assign(d2_need=lambda d: pd.to_numeric(d["d2_check_count"], errors="coerce").fillna(0.0) > 0)
            .groupby(["center", "case_id"], as_index=False)
            .agg(model_n=("model_short", "nunique"), all_need_admission=("d2_need", "all"))
        )
        selected_case = need_admission[
            (need_admission["model_n"] >= len(MODEL_ORDER)) & need_admission["all_need_admission"]
        ][["center", "case_id"]].copy()
        d2_last_info = (
            check_gain_detail[check_gain_detail["phase_key"].astype(str).eq("D2")]
            .sort_values(key_cols + ["round_idx"], kind="mergesort")
            .groupby(key_cols, as_index=False)
            .tail(1)
            .loc[:, key_cols + ["matched_count_final", "round_idx"]]
            .rename(columns={"round_idx": "admission_last_round", "matched_count_final": "admission_info_items"})
        )
        admission_info_gain_case = final_dx_round_case.merge(selected_case, on=["center", "case_id"], how="inner")
        admission_info_gain_case = admission_info_gain_case.merge(d2_last_info, on=key_cols, how="left")
        admission_info_gain_case["admission_info_items"] = pd.to_numeric(
            admission_info_gain_case["admission_info_items"], errors="coerce"
        )
        admission_info_gain_case["dx_gain_d3_vs_d1"] = pd.to_numeric(
            admission_info_gain_case["delta_score_d3_vs_d1"], errors="coerce"
        )
        admission_info_gain_case = admission_info_gain_case.dropna(subset=["admission_info_items", "dx_gain_d3_vs_d1"]).copy()
        if not admission_info_gain_case.empty:
            admission_info_gain_model_summary = (
                admission_info_gain_case.groupby("model_short", as_index=False)
                .agg(
                    n_case_model=("case_id", "count"),
                    mean_admission_info_items=("admission_info_items", "mean"),
                    mean_dx_gain_d3_vs_d1=("dx_gain_d3_vs_d1", "mean"),
                    median_dx_gain_d3_vs_d1=("dx_gain_d3_vs_d1", "median"),
                )
                .sort_values("model_short", kind="mergesort")
                .reset_index(drop=True)
            )
    fig_c7, axes_c7 = plt.subplots(2, 3, figsize=(15.0, 8.8), sharex=True, sharey=True)
    c7_panels = list(MODEL_ORDER) + ["Overall"]
    c7_x = pd.to_numeric(admission_info_gain_case.get("admission_info_items", pd.Series(dtype=float)), errors="coerce")
    c7_y = pd.to_numeric(admission_info_gain_case.get("dx_gain_d3_vs_d1", pd.Series(dtype=float)), errors="coerce")
    c7_x_lo, c7_x_hi = _adaptive_ylim(c7_x, fallback=(0.0, 6.0), domain=(0.0, None), min_span=4.0)
    c7_y_lo, c7_y_hi = _adaptive_ylim(c7_y, fallback=(-0.08, 0.25), domain=(None, None), min_span=0.24)
    for ax_c7, panel_model in zip(axes_c7.flatten(), c7_panels):
        if admission_info_gain_case.empty:
            ax_c7.text(0.5, 0.5, "无可绘制数据", ha="center", va="center", transform=ax_c7.transAxes)
            ax_c7.set_xticks([])
            _set_full_axis_border(ax_c7, lw=1.0)
            continue
        if panel_model == "Overall":
            sub = admission_info_gain_case.copy()
            color = "#111111"
            title = "Overall"
        else:
            sub = admission_info_gain_case[admission_info_gain_case["model_short"] == panel_model].copy()
            color = MODEL_COLOR.get(panel_model, "#4C78A8")
            title = str(panel_model)
        if sub.empty:
            ax_c7.text(0.5, 0.5, "样本不足", ha="center", va="center", transform=ax_c7.transAxes)
            ax_c7.set_xticks([])
            _set_full_axis_border(ax_c7, lw=1.0)
            continue
        ax_c7.scatter(
            sub["admission_info_items"],
            sub["dx_gain_d3_vs_d1"],
            s=36,
            alpha=0.75,
            color=color,
            edgecolors="white",
            linewidths=0.5,
            zorder=3,
        )
        if len(sub) >= 2:
            xx = pd.to_numeric(sub["admission_info_items"], errors="coerce").to_numpy(dtype=float)
            yy = pd.to_numeric(sub["dx_gain_d3_vs_d1"], errors="coerce").to_numpy(dtype=float)
            coef = np.polyfit(xx, yy, deg=1)
            x_line = np.linspace(max(0.0, float(np.nanmin(xx))), float(np.nanmax(xx)), 80)
            y_line = coef[0] * x_line + coef[1]
            ax_c7.plot(x_line, y_line, color=color, linewidth=1.8, alpha=0.85, zorder=2)
        ax_c7.set_title(f"{title} (n={len(sub)})", fontsize=10.2)
        ax_c7.set_xlim(max(0.0, c7_x_lo - 0.2), c7_x_hi + 0.4)
        ax_c7.set_ylim(c7_y_lo - 0.02, c7_y_hi + 0.04)
        ax_c7.axhline(0.0, color="#6B7280", linestyle="--", linewidth=0.9, alpha=0.7, zorder=1)
        ax_c7.grid(alpha=0.20, axis="both", zorder=0)
        _set_full_axis_border(ax_c7, lw=1.0)
    axes_c7[1, 0].set_xlabel("入院阶段最终匹配信息项数")
    axes_c7[1, 1].set_xlabel("入院阶段最终匹配信息项数")
    axes_c7[1, 2].set_xlabel("入院阶段最终匹配信息项数")
    axes_c7[0, 0].set_ylabel("D3 相对 D1 诊断接近度提升")
    axes_c7[1, 0].set_ylabel("D3 相对 D1 诊断接近度提升")
    fig_c7.suptitle("五模型均需住院检查病例：入院信息量与诊断提升关系", fontsize=14, y=0.98)
    fig_c7.subplots_adjust(left=0.08, right=0.985, top=0.90, bottom=0.11, wspace=0.16, hspace=0.24)
    _save_fig(out_final_dx_admission_info_gain_panel)

    fig_cv3, ax_cv3 = plt.subplots(figsize=(8.2, 5.3))
    order = [
        ("Completed", "LOOP1"),
        ("Completed", "LOOP2(含D1决策检查)"),
        ("Blocked/Exit", "LOOP1"),
        ("Blocked/Exit", "LOOP2(含D1决策检查)"),
    ]
    positions = [1.0, 2.0, 4.0, 5.0]
    series_list: list[np.ndarray] = []
    for flag, phase in order:
        sub = phase_case[(phase_case["sample_flag"] == flag) & (phase_case["phase"] == phase)]["phase_info_gain"]
        vals = pd.to_numeric(sub, errors="coerce").dropna().to_numpy(dtype=float)
        series_list.append(vals if len(vals) > 0 else np.array([0.0], dtype=float))
    bxp = ax_cv3.boxplot(
        series_list,
        positions=positions,
        widths=0.62,
        patch_artist=True,
        showmeans=True,
        meanprops={"marker": "o", "markerfacecolor": "#1F2937", "markeredgecolor": "white", "markersize": 5.0},
        medianprops={"color": "#222222", "linewidth": 1.4},
    )
    box_colors = ["#5BAE6A", "#D4B13D", "#A8DDB0", "#E9D27A"]
    for patch, c in zip(bxp["boxes"], box_colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.75)
        patch.set_edgecolor("#2B2B2B")
        patch.set_linewidth(1.0)
    for key in ["whiskers", "caps"]:
        for item in bxp.get(key, []):
            item.set_color("#555555")
            item.set_linewidth(1.0)
    ax_cv3.axvline(3.0, color="#8A8A8A", linestyle="--", linewidth=1.0, alpha=0.8)
    _set_full_axis_border(ax_cv3, lw=1.2)
    ax_cv3.set_xticks(positions)
    ax_cv3.set_xticklabels(["LOOP1\nCompleted", "LOOP2\nCompleted", "LOOP1\nBlocked", "LOOP2\nBlocked"], fontsize=9)
    y_hi_box = float(np.nanmax(np.concatenate(series_list))) if len(series_list) else 1.0
    y_hi_box = max(1.0, y_hi_box * 1.08)
    ax_cv3.set_ylabel("信息增益量 = Σ(每轮匹配率 × 每轮请求检查数)")
    ax_cv3.set_title("C. 检查效率分布")
    ax_cv3.set_ylim(0.0, y_hi_box)
    ax_cv3.grid(alpha=0.22, axis="y")
    loop_mean_done = float(eff_scatter.loc[eff_scatter["is_completed"], "cumulative_rounds"].mean())
    loop_mean_block = float(eff_scatter.loc[~eff_scatter["is_completed"], "cumulative_rounds"].mean())
    ax_cv3.text(
        0.98,
        0.96,
        f"平均循环轮数：Completed={loop_mean_done:.2f}, Blocked={loop_mean_block:.2f}",
        ha="right",
        va="top",
        fontsize=8.8,
        color="#444444",
        transform=ax_cv3.transAxes,
    )
    _save_fig(out_eff_box_v5)

    # C(特例版)：D1 特殊案例统计（按中心×模型）
    special_detail = pd.DataFrame(list(d1_set), columns=["center", "model", "case_id"])
    special_detail["model_short"] = special_detail["model"].map(MODEL_SHORT).fillna(special_detail["model"].astype(str))
    special_summary = (
        special_detail.groupby(["center", "model_short"], as_index=False)
        .agg(special_case_count=("case_id", "nunique"))
        .sort_values(["center", "special_case_count"], ascending=[True, False], kind="mergesort")
    )
    center_order = ["佛山", "武汉", "新疆"]
    center_label = {"佛山": "Foshan", "武汉": "Wuhan", "新疆": "Xinjiang"}
    fig_sp, axs_sp = plt.subplots(1, 3, figsize=(15.8, 4.6), sharey=True)
    for ax_sp, center_name in zip(axs_sp, center_order):
        sub = special_summary[special_summary["center"] == center_name].copy()
        base = pd.DataFrame({"model_short": MODEL_ORDER})
        sub = base.merge(sub, on="model_short", how="left").fillna({"special_case_count": 0})
        ax_sp.bar(
            sub["model_short"],
            sub["special_case_count"],
            color="#2A6F9E",
            alpha=0.9,
            width=0.62,
        )
        ax_sp.set_title(center_label.get(center_name, center_name))
        ax_sp.tick_params(axis="x", rotation=35, labelsize=8.4)
        ax_sp.grid(alpha=0.2, axis="y")
    axs_sp[0].set_ylabel("Count")
    fig_sp.suptitle("D1 Special Case Count by Model (by Center)", fontsize=15, y=1.02)
    _save_fig(out_special_case)

    # 组合组图（按不同展示重点）
    fig_gp1 = plt.figure(figsize=(18.5, 9.2), constrained_layout=True)
    gs1 = fig_gp1.add_gridspec(1, 2, width_ratios=[1.7, 1.0], wspace=0.04)
    ax1 = fig_gp1.add_subplot(gs1[0, 0])
    ax2 = fig_gp1.add_subplot(gs1[0, 1])
    _draw_image_panel(ax1, out_sankey, "", aspect="auto")
    _draw_image_panel(ax2, out_pass, "")
    fig_gp1.suptitle("G4 组图A：流程结构 + 通过效率", fontsize=16, y=1.01)
    _save_fig(out_group_flow_pass)

    fig_gp2 = plt.figure(figsize=(18.5, 9.2), constrained_layout=True)
    gs2 = fig_gp2.add_gridspec(1, 2, width_ratios=[1.45, 1.15], wspace=0.04)
    bx1 = fig_gp2.add_subplot(gs2[0, 0])
    bx2 = fig_gp2.add_subplot(gs2[0, 1])
    _draw_image_panel(bx1, out_sankey, "", aspect="auto")
    _draw_image_panel(bx2, out_eff_scatter, "")
    fig_gp2.suptitle("G4 组图B：流程结构 + 信息增益", fontsize=16, y=1.01)
    _save_fig(out_group_flow_gain)

    fig_gp3 = plt.figure(figsize=(18.5, 11.2), constrained_layout=True)
    gs3 = fig_gp3.add_gridspec(2, 1, height_ratios=[1.15, 1.0], hspace=0.06)
    cx1 = fig_gp3.add_subplot(gs3[0, 0])
    cx2 = fig_gp3.add_subplot(gs3[1, 0])
    _draw_image_panel(cx1, out_calib, "")
    _draw_image_panel(cx2, out_calib_path, "")
    fig_gp3.suptitle("G4 组图C：校准曲线套件", fontsize=16, y=1.005)
    _save_fig(out_group_calib_suite)

    # 主文布局（v6）：Sankey + B0总体校准 + Ablation诊断差距子图
    main_c_panel = out_eff_panel
    try:
        out_ablation_main_c.parent.mkdir(parents=True, exist_ok=True)
        source_panel = ablation_overall_src if ablation_overall_src.exists() else out_eff_panel
        # 回退仅用于保持主图 C 位引用稳定；矢量 sidecar 不做伪造。
        shutil.copy2(source_panel, out_ablation_main_c)
        for suffix in (".svg", ".pdf"):
            source_sidecar = source_panel.with_suffix(suffix)
            target_sidecar = out_ablation_main_c.with_suffix(suffix)
            if source_sidecar.exists():
                shutil.copy2(source_sidecar, target_sidecar)
            elif target_sidecar.exists():
                target_sidecar.unlink()
        main_c_panel = out_ablation_main_c
    except Exception:
        main_c_panel = out_eff_panel

    fig_gp4 = plt.figure(figsize=(28.6, 12.4), constrained_layout=False)
    gs4 = fig_gp4.add_gridspec(2, 2, width_ratios=[2.7, 1.3], height_ratios=[1.0, 1.0], wspace=0.028, hspace=0.11)
    dx1 = fig_gp4.add_subplot(gs4[:, 0])
    dx2 = fig_gp4.add_subplot(gs4[0, 1])
    dx3 = fig_gp4.add_subplot(gs4[1, 1])

    _draw_image_panel(dx1, out_sankey, "", aspect="equal")
    _draw_image_panel(dx2, out_calib_overall_v5, "", aspect="equal")
    _draw_image_panel(dx3, main_c_panel, "", aspect="equal")

    fig_gp4.suptitle("G4 系统性指标", fontsize=16, y=0.985)
    fig_gp4.text(0.265, 0.935, "a. 流程流转", ha="center", va="center", fontsize=13, color="#2F2F2F")
    fig_gp4.subplots_adjust(left=0.015, right=0.992, top=0.925, bottom=0.075, wspace=0.025, hspace=0.10)
    _save_fig(out_group_ref_v6, apply_tight=False)

    # 主文布局（替代比例版）：A 顶部全宽，B/C 底部并排（参考用户给定示例比例）
    layout_like_dir = OUT_FIG_DIR / group / "layout_like_fig1_v1"
    layout_like_dir.mkdir(parents=True, exist_ok=True)
    out_layout_like_main = layout_like_dir / "G4_groupD_sankey_calib_efficiency_layout_like_fig1_v1.png"
    out_layout_like_a = layout_like_dir / "G4A_flow_panel_v1.png"
    out_layout_like_b = layout_like_dir / "G4B_calibration_panel_v1.png"
    out_layout_like_c = layout_like_dir / "G4C_ablation_panel_v1.png"
    for src, dst in [
        (out_sankey, out_layout_like_a),
        (out_calib_overall_v5, out_layout_like_b),
        (main_c_panel, out_layout_like_c),
    ]:
        try:
            if src.exists():
                shutil.copy2(src, dst)
        except Exception:
            pass

    fig_gp6 = plt.figure(figsize=(19.4, 14.6), constrained_layout=False)
    gs6 = fig_gp6.add_gridspec(2, 2, height_ratios=[1.22, 1.0], width_ratios=[1.0, 1.0], wspace=0.045, hspace=0.09)
    fx1 = fig_gp6.add_subplot(gs6[0, :])
    fx2 = fig_gp6.add_subplot(gs6[1, 0])
    fx3 = fig_gp6.add_subplot(gs6[1, 1])
    _draw_image_panel(fx1, out_sankey, "", aspect="auto")
    _draw_image_panel(fx2, out_calib_overall_v5, "", aspect="auto")
    _draw_image_panel(fx3, main_c_panel, "", aspect="auto")
    fx1.text(-0.02, 1.02, "A", transform=fx1.transAxes, fontsize=18, fontweight="bold", va="top", ha="left")
    fx2.text(-0.02, 1.02, "B", transform=fx2.transAxes, fontsize=18, fontweight="bold", va="top", ha="left")
    fx3.text(-0.02, 1.02, "C", transform=fx3.transAxes, fontsize=18, fontweight="bold", va="top", ha="left")
    fig_gp6.subplots_adjust(left=0.03, right=0.992, top=0.97, bottom=0.055, wspace=0.05, hspace=0.10)
    _save_fig(out_layout_like_main, apply_tight=False)

    # 附录布局（特例统计版）：左Sankey，右上B0校准，右下D1特殊案例计数
    fig_gp5 = plt.figure(figsize=(28.6, 12.4), constrained_layout=False)
    gs5 = fig_gp5.add_gridspec(2, 2, width_ratios=[2.7, 1.3], height_ratios=[1.0, 1.0], wspace=0.028, hspace=0.11)
    ex1 = fig_gp5.add_subplot(gs5[:, 0])
    ex2 = fig_gp5.add_subplot(gs5[0, 1])
    ex3 = fig_gp5.add_subplot(gs5[1, 1])
    _draw_image_panel(ex1, out_sankey, "", aspect="equal")
    _draw_image_panel(ex2, out_calib_overall_v5, "", aspect="equal")
    _draw_image_panel(ex3, out_special_case, "", aspect="equal")
    fig_gp5.suptitle("G4 附录 特例统计版", fontsize=16, y=0.985)
    fig_gp5.subplots_adjust(left=0.015, right=0.992, top=0.925, bottom=0.075, wspace=0.025, hspace=0.10)
    _save_fig(out_group_special, apply_tight=False)

    eff_summary_bins = (
        eff_scatter.groupby(["sample_flag", "cumulative_rounds"], as_index=False)
        .agg(gain_mean=("information_gain", "mean"), gain_median=("information_gain", "median"), samples=("case_id", "count"))
        .sort_values(["sample_flag", "cumulative_rounds"], kind="mergesort")
    )
    chk_model_table = (
        chk.groupby("model_short", as_index=False)
        .agg(
            d1_match_rate=("d1_match_rate", "mean"),
            d2_match_rate=("d2_match_rate", "mean"),
            d1_ineff_rate=("d1_ineff_rate", "mean"),
            d2_ineff_rate=("d2_ineff_rate", "mean"),
            d1_avg_check_count=("d1_check_count", "mean"),
            d2_avg_check_count=("d2_check_count", "mean"),
        )
        .sort_values("model_short", kind="mergesort")
    )
    calib_stage_table = (
        stage_bin_overall.groupby("stage4", as_index=False)
        .agg(
            conf_mean=("conf", "mean"),
            acc_mean=("acc", "mean"),
            sample_n=("n", "sum"),
        )
        .assign(calibration_gap=lambda d: d["conf_mean"] - d["acc_mean"])
        .sort_values("stage4", kind="mergesort")
    )
    b0_model_points = model_overall[["model_short", "conf_overall", "acc_overall", "n_overall"]].copy()
    b0_model_points = b0_model_points.rename(columns={"conf_overall": "x_conf", "acc_overall": "y_acc"})
    b0_model_points["point_type"] = "model_point"
    b0_plot_points = pd.concat(
        [
            b0_model_points,
            pd.DataFrame([{"model_short": "B0 weighted overall", "x_conf": overall_conf, "y_acc": overall_acc, "point_type": "overall_star"}]),
        ],
        ignore_index=True,
    )
    if not b0_plot_points.empty:
        b0_plot_points["formula_x_conf"] = ""
        b0_plot_points["formula_y_acc"] = ""
        rr_b0 = np.arange(2, len(b0_plot_points) + 2)
        mask_model = b0_plot_points["point_type"].astype(str).eq("model_point")
        for idx, r in enumerate(rr_b0):
            if bool(mask_model.iloc[idx]):
                b0_plot_points.loc[idx, "formula_x_conf"] = (
                    f"=IFERROR(INDEX(c_b0_model!$C:$C,MATCH(B{r},c_b0_model!$B:$B,0)),\"\")"
                )
                b0_plot_points.loc[idx, "formula_y_acc"] = (
                    f"=IFERROR(INDEX(c_b0_model!$D:$D,MATCH(B{r},c_b0_model!$B:$B,0)),\"\")"
                )
        mask_overall = b0_plot_points["model_short"].astype(str).eq("B0 weighted overall")
        b0_plot_points.loc[mask_overall, "formula_x_conf"] = "=SUMPRODUCT(c_b0_stage!$C:$C,c_b0_stage!$E:$E)/SUM(c_b0_stage!$E:$E)"
        b0_plot_points.loc[mask_overall, "formula_y_acc"] = "=SUMPRODUCT(c_b0_stage!$D:$D,c_b0_stage!$E:$E)/SUM(c_b0_stage!$E:$E)"
        b0_plot_points["说明"] = "model_point从c_b0_model取值；overall_star按c_b0_stage样本量加权"
    calib_case_export = calib_case[
        [
            "source_path",
            "source_sheet",
            "center",
            "model",
            "case_id",
            "model_short",
            "stage",
            "stage_cn",
            "category",
            "confidence",
            "accuracy",
            "stage4",
            "bin_calc",
        ]
    ].copy()
    if not calib_case_export.empty:
        rr_case_bin = np.arange(2, len(calib_case_export) + 2)
        calib_case_export["formula_bin_from_conf"] = [
            (
                f"=IF(K{r}=\"\",\"\",CHOOSE(MIN(10,MAX(1,ROUNDUP(K{r}*10,0))),"
                "\"(0.0, 0.1]\",\"(0.1, 0.2]\",\"(0.2, 0.3]\",\"(0.3, 0.4]\","
                "\"(0.4, 0.5]\",\"(0.5, 0.6]\",\"(0.6, 0.7]\",\"(0.7, 0.8]\","
                "\"(0.8, 0.9]\",\"(0.9, 1.0]\"))"
            )
            for r in rr_case_bin
        ]
        calib_case_export["formula_bin_match"] = [f"=N{r}=O{r}" for r in rr_case_bin]
        calib_case_export["说明"] = "bin_calc由0.1间隔置信度分箱得到；conf=confidence；acc=accuracy"

    calib_bin_export = calib.copy()
    if not calib_bin_export.empty:
        rr_bin = np.arange(2, len(calib_bin_export) + 2)
        calib_bin_export["formula_conf_from_case"] = [
            f"=IFERROR(AVERAGEIFS(d_calib_case!$K:$K,d_calib_case!$D:$D,B{r},d_calib_case!$G:$G,D{r},d_calib_case!$H:$H,E{r},d_calib_case!$J:$J,G{r},d_calib_case!$N:$N,H{r}),\"\")"
            for r in rr_bin
        ]
        calib_bin_export["formula_acc_from_case"] = [
            f"=IFERROR(AVERAGEIFS(d_calib_case!$L:$L,d_calib_case!$D:$D,B{r},d_calib_case!$G:$G,D{r},d_calib_case!$H:$H,E{r},d_calib_case!$J:$J,G{r},d_calib_case!$N:$N,H{r}),\"\")"
            for r in rr_bin
        ]
        calib_bin_export["formula_n_from_case"] = [
            f"=COUNTIFS(d_calib_case!$D:$D,B{r},d_calib_case!$G:$G,D{r},d_calib_case!$H:$H,E{r},d_calib_case!$J:$J,G{r},d_calib_case!$N:$N,H{r})"
            for r in rr_bin
        ]
        calib_bin_export["formula_n_cases_from_case"] = [
            f"=COUNTIFS(d_calib_case!$D:$D,B{r},d_calib_case!$G:$G,D{r},d_calib_case!$H:$H,E{r},d_calib_case!$J:$J,G{r},d_calib_case!$N:$N,H{r})"
            for r in rr_bin
        ]
        calib_bin_export["说明"] = "bin行由d_calib_case聚合而来：conf/acc=均值，n/n_cases=计数"

    check_case_calc = chk[
        [
            "center",
            "model",
            "case_id",
            "model_short",
            "D1_Outpatient_Loop__executed_rounds",
            "D2_Admission_Loop__executed_rounds",
            "d1_check_count",
            "d2_check_count",
            "d2_force_stop",
            "d2_check_force_fail",
            "d2_inconsistent",
        ]
    ].copy()
    check_case_calc.insert(0, "source_path", "analysis_viz/data/raw/metrics_source_data.xlsx")
    check_case_calc.insert(1, "source_sheet", "metrics_by_case")
    check_case_calc["d2_merged_d1_decision_check"] = 1
    if not check_case_calc.empty:
        rr_case = np.arange(2, len(check_case_calc) + 2)
        col_idx_case = {c: i + 1 for i, c in enumerate(check_case_calc.columns)}
        c_d1_rounds_case = openpyxl.utils.get_column_letter(col_idx_case["D1_Outpatient_Loop__executed_rounds"] + 1)
        c_d2_rounds_case = openpyxl.utils.get_column_letter(col_idx_case["D2_Admission_Loop__executed_rounds"] + 1)
        c_d2_merge_case = openpyxl.utils.get_column_letter(col_idx_case["d2_merged_d1_decision_check"] + 1)
        check_case_calc["formula_d1_check_count"] = [
            f"=IF({c_d1_rounds_case}{r}=\"\",\"\",MAX(0,{c_d1_rounds_case}{r}))" for r in rr_case
        ]
        check_case_calc["formula_d2_merged_d1_decision_check"] = [f"={c_d2_merge_case}{r}" for r in rr_case]
        check_case_calc["formula_d2_check_count"] = [
            f"=IF({c_d2_rounds_case}{r}=\"\",\"\",MAX(0,{c_d2_rounds_case}{r})+{c_d2_merge_case}{r})" for r in rr_case
        ]
        check_case_calc["说明"] = "D1检查次数=门诊执行轮数；D2检查次数=住院执行轮数 + d2_merged_d1_decision_check，其中该列固定为1，表示并入D1决策检查。下方将由明细_检查_原始的轮次JSON公式回填核对。"

    check_trace_raw = _load_check_loop_trace_raw_for_source()
    check_raw_export = chk[
        [
            "center",
            "model",
            "case_id",
            "model_short",
            "D1_Outpatient_Loop__executed_rounds",
            "D2_Admission_Loop__executed_rounds",
            "d1_check_count",
            "d2_check_count",
            "d2_force_stop",
            "d2_check_force_fail",
            "d2_inconsistent",
        ]
    ].copy()
    check_raw_export = check_raw_export.merge(
        check_trace_raw,
        on=["center", "model", "case_id", "model_short"],
        how="left",
    )
    trace_cols_expect = [
        "d1_judge_status_raw",
        "d2_judge_status_raw",
        "d1_doc_status_raw",
        "d2_doc_status_raw",
        "d1_round1_judge_raw_json",
        "d1_round2_judge_raw_json",
        "d1_round3_judge_raw_json",
        "d1_round4_judge_raw_json",
        "d2_round1_judge_raw_json",
        "d2_round2_judge_raw_json",
        "d2_round3_judge_raw_json",
        "d2_round4_judge_raw_json",
        "d1_round1_doc_raw_json",
        "d1_round2_doc_raw_json",
        "d1_round3_doc_raw_json",
        "d1_round4_doc_raw_json",
        "d2_round1_doc_raw_json",
        "d2_round2_doc_raw_json",
        "d2_round3_doc_raw_json",
        "d2_round4_doc_raw_json",
        "source_judge_path",
        "source_doc_path",
    ]
    for c in trace_cols_expect:
        if c not in check_raw_export.columns:
            check_raw_export[c] = ""
    check_raw_export = check_raw_export[
        [
            "center",
            "model",
            "case_id",
            "model_short",
            "D1_Outpatient_Loop__executed_rounds",
            "D2_Admission_Loop__executed_rounds",
            "d1_check_count",
            "d2_check_count",
            "d1_judge_status_raw",
            "d2_judge_status_raw",
            "d1_doc_status_raw",
            "d2_doc_status_raw",
            "d1_round1_judge_raw_json",
            "d1_round2_judge_raw_json",
            "d1_round3_judge_raw_json",
            "d1_round4_judge_raw_json",
            "d2_round1_judge_raw_json",
            "d2_round2_judge_raw_json",
            "d2_round3_judge_raw_json",
            "d2_round4_judge_raw_json",
            "d1_round1_doc_raw_json",
            "d1_round2_doc_raw_json",
            "d1_round3_doc_raw_json",
            "d1_round4_doc_raw_json",
            "d2_round1_doc_raw_json",
            "d2_round2_doc_raw_json",
            "d2_round3_doc_raw_json",
            "d2_round4_doc_raw_json",
            "source_judge_path",
            "source_doc_path",
            "d2_force_stop",
            "d2_check_force_fail",
            "d2_inconsistent",
        ]
    ].copy()
    check_raw_export.insert(0, "source_path_metrics", "analysis_viz/data/raw/metrics_source_data.xlsx")
    check_raw_export.insert(1, "source_sheet_metrics", "metrics_by_case")
    check_raw_export["d2_merged_d1_decision_check"] = 1
    if not check_raw_export.empty:
        rr_raw = np.arange(2, len(check_raw_export) + 2)
        col_idx_raw_export = {c: i + 1 for i, c in enumerate(check_raw_export.columns)}
        d1_raw_cols = [
            openpyxl.utils.get_column_letter(col_idx_raw_export[f"d1_round{i}_judge_raw_json"] + 1) for i in range(1, 5)
        ]
        d2_raw_cols = [
            openpyxl.utils.get_column_letter(col_idx_raw_export[f"d2_round{i}_judge_raw_json"] + 1) for i in range(1, 5)
        ]
        c_d2_merge_raw = openpyxl.utils.get_column_letter(col_idx_raw_export["d2_merged_d1_decision_check"] + 1)
        c_d1_exec_raw = openpyxl.utils.get_column_letter(
            col_idx_raw_export["D1_Outpatient_Loop__executed_rounds"] + 1
        )
        c_d2_exec_raw = openpyxl.utils.get_column_letter(
            col_idx_raw_export["D2_Admission_Loop__executed_rounds"] + 1
        )
        check_raw_export["formula_d1_check_count"] = [
            "=" + "+".join([f"--(LEN({col}{r})>0)" for col in d1_raw_cols]) for r in rr_raw
        ]
        check_raw_export["formula_d2_check_count"] = [
            "=" + "+".join([f"--(LEN({col}{r})>0)" for col in d2_raw_cols]) + f"+{c_d2_merge_raw}{r}" for r in rr_raw
        ]
        check_raw_export["formula_d2_merged_d1_decision_check"] = [f"={c_d2_merge_raw}{r}" for r in rr_raw]
        check_raw_export["formula_d1_rounds_from_judge_json"] = [
            "=" + "+".join([f"--(LEN({col}{r})>0)" for col in d1_raw_cols]) for r in rr_raw
        ]
        check_raw_export["formula_d2_rounds_from_judge_json"] = [
            "=" + "+".join([f"--(LEN({col}{r})>0)" for col in d2_raw_cols]) for r in rr_raw
        ]
        check_raw_export["formula_d1_rounds_match"] = [
            f"=({'+'.join([f'--(LEN({col}{r})>0)' for col in d1_raw_cols])})={c_d1_exec_raw}{r}"
            for r in rr_raw
        ]
        check_raw_export["formula_d2_rounds_match"] = [
            f"=({'+'.join([f'--(LEN({col}{r})>0)' for col in d2_raw_cols])})={c_d2_exec_raw}{r}"
            for r in rr_raw
        ]
        check_raw_export["说明"] = "按 judge 轮次原始JSON列通过 LEN>0 统计执行轮数，并与 metrics_by_case 的 executed_rounds 动态列匹配核对；d2_merged_d1_decision_check 固定为1，表示D1决策检查并入D2。"
        if not check_case_calc.empty:
            col_idx_raw = {c: i + 1 for i, c in enumerate(check_raw_export.columns)}
            # _write_source_workbook 会在最前插入 source_table 列，写盘后列号整体 +1
            c_d1_rounds = openpyxl.utils.get_column_letter(col_idx_raw["formula_d1_rounds_from_judge_json"] + 1)
            c_d2_rounds = openpyxl.utils.get_column_letter(col_idx_raw["formula_d2_rounds_from_judge_json"] + 1)
            c_d2_merge = openpyxl.utils.get_column_letter(col_idx_raw["formula_d2_merged_d1_decision_check"] + 1)
            rr_case = np.arange(2, len(check_case_calc) + 2)
            check_case_calc["formula_d1_check_count"] = [
                (
                    f"=IFERROR(SUMIFS(d_check_raw!${c_d1_rounds}:${c_d1_rounds},"
                    f"d_check_raw!$D:$D,D{r},d_check_raw!$E:$E,E{r},d_check_raw!$F:$F,F{r}),\"\")"
                )
                for r in rr_case
            ]
            check_case_calc["formula_d2_check_count"] = [
                (
                    f"=IFERROR(SUMIFS(d_check_raw!${c_d2_rounds}:${c_d2_rounds},"
                    f"d_check_raw!$D:$D,D{r},d_check_raw!$E:$E,E{r},d_check_raw!$F:$F,F{r})+"
                    f"SUMIFS(d_check_raw!${c_d2_merge}:${c_d2_merge},"
                    f"d_check_raw!$D:$D,D{r},d_check_raw!$E:$E,E{r},d_check_raw!$F:$F,F{r}),\"\")"
                )
                for r in rr_case
            ]
    source_path = _write_source_workbook(
        group=group,
        stem="G4_system_metrics_v2",
        sheets={
            "d_sankey_used": sankey_detail_fixed,
            "s_sankey_nodes": node_df,
            "s_sankey_links": link_df,
            "d_calib_case": calib_case_export,
            "d_calib_bins": calib_bin_export,
            "d_b3_diag_bin_raw": bin_diag.copy(),
            "c_b3_diag_stage_bin": diag_stage_bin,
            "s_b3_diag_model_points": diag_stage_model_points,
            "s_b3_diag_overall_points": diag_stage_overall_points,
            "s_b3_diag_stage_summary": diag_stage_summary,
            "d_b4_check_round_raw": check_round_detail,
            "c_b4_check_stage_round_bin": check_round_bin,
            "s_b4_check_round_model_points": check_round_model_points,
            "s_b4_check_round_overall_points": check_round_overall_points,
            "s_b4_check_stage_round_summary": check_round_summary,
            "d_b5_plan_bin_raw": bin_plan.copy(),
            "c_b5_plan_stage_bin": plan_stage_bin,
            "s_b5_plan_model_points": plan_stage_model_points,
            "s_b5_plan_overall_points": plan_stage_overall_points,
            "s_b5_plan_stage_summary": plan_stage_summary,
            "c_b0_stage": stage_weighted,
            "c_b0_model": model_overall,
            "s_b_stage_model_points": stage_model_points,
            "s_b0_points": b0_plot_points,
            "s_b1_d1_table": stage_bin_model[stage_bin_model["stage4"] == "D1"].copy(),
            "s_b2_d2_table": stage_bin_model[stage_bin_model["stage4"] == "D2"].copy(),
            "s_b3_d3_table": stage_bin_model[stage_bin_model["stage4"] == "D3"].copy(),
            "s_b4_d4_table": stage_bin_model[stage_bin_model["stage4"] == "D4"].copy(),
            "d_check_raw": check_raw_export,
            "c_check_case": check_case_calc,
            "s_check_count": chk_summary_c2,
            "d_c3_marginal_gain_round": check_gain_detail,
            "s_c3_marginal_gain_summary": check_gain_summary,
            "d_c3_final_dx_proximity_case": final_dx_detail,
            "c_c3_final_dx_proximity_triplet": final_dx_triplet,
            "s_c3_final_dx_proximity_stage_summary": final_dx_stage_summary,
            "s_c3_final_dx_proximity_transition_summary": final_dx_transition_summary,
            "d_c4_final_dx_round_case": final_dx_round_case,
            "d_c4_final_dx_stage_long": final_dx_round_stage_long,
            "s_c4_total_round_stage": final_dx_total_round_stage_summary,
            "s_c4_d1_round_stage": final_dx_d1_round_stage_summary,
            "s_c4_d2_round_stage": final_dx_d2_round_stage_summary,
            "s_c5_total_round_gain": final_dx_total_round_gain_summary,
            "s_c5_d1_round_gain": final_dx_d1_round_gain_summary,
            "s_c5_d2_round_gain": final_dx_d2_round_gain_summary,
            "s_c6_model_total_round_gain": final_dx_model_total_round_gain_summary,
            "d_c7_admission_info_gain_case": admission_info_gain_case,
            "s_c7_admission_info_gain_model": admission_info_gain_model_summary,
            "s_c3_admission_baseline": d2_baseline_summary,
            "d_special_case": special_detail,
            "s_special_case": special_summary,
        },
        meta={
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "figures": "G4A_sankey_all_center_model_v3.png; G4A_sankey_arrow_rect_v1.png; G4B_calibration_overall_weighted_v6.png; G4B3_calibration_diag_decision_types_v1.png; G4B4_calibration_check_rounds_v1.png; G4B5_calibration_plan_decision_types_v1.png; G4C_ablation_diag_dumbbell_v1.png; G4_groupD_sankey_calib_efficiency_v7.png; G4C2_check_efficiency_panel_v2.png; G4B_calibration_overall_stage_v2.png; G4C3_check_gain_marginal_info_panel_v2.png; G4C3_check_gain_decision_shift_panel_v1.png; G4C4_check_rounds_final_dx_proximity_panel_v1.png; G4C5_check_rounds_final_dx_gain_panel_v1.png; G4C6_check_rounds_final_dx_gain_model_v1.png; G4C7_admission_info_vs_dx_gain_model_v1.png; G4C3_check_gain_summary_table_v2.png; layout_like_fig1_v1/G4_groupD_sankey_calib_efficiency_layout_like_fig1_v1.png",
            "sheet_name_alias": {
                "d_b3_diag_bin_raw": "明细_b3_diag_raw",
                "c_b3_diag_stage_bin": "计算_b3_diag_bin",
                "s_b3_diag_model_points": "汇总_b3_diag_model_pt",
                "s_b3_diag_overall_points": "汇总_b3_diag_overall",
                "s_b3_diag_stage_summary": "汇总_b3_diag_stage",
                "d_b4_check_round_raw": "明细_b4_check_round_raw",
                "c_b4_check_stage_round_bin": "计算_b4_check_round_bin",
                "s_b4_check_round_model_points": "汇总_b4_check_model_pt",
                "s_b4_check_round_overall_points": "汇总_b4_check_overall",
                "s_b4_check_stage_round_summary": "汇总_b4_check_round",
                "d_b5_plan_bin_raw": "明细_b5_plan_raw",
                "c_b5_plan_stage_bin": "计算_b5_plan_bin",
                "s_b5_plan_model_points": "汇总_b5_plan_model_pt",
                "s_b5_plan_overall_points": "汇总_b5_plan_overall",
                "s_b5_plan_stage_summary": "汇总_b5_plan_stage",
                "d_c3_final_dx_proximity_case": "明细_c3_final_dx_prox_case",
                "c_c3_final_dx_proximity_triplet": "计算_c3_final_dx_prox_triplet",
                "s_c3_final_dx_proximity_stage_summary": "汇总_c3_final_dx_stage",
                "s_c3_final_dx_proximity_transition_summary": "汇总_c3_final_dx_transition",
                "d_c4_final_dx_round_case": "明细_c4_final_dx_round_case",
                "d_c4_final_dx_stage_long": "明细_c4_final_dx_stage_long",
                "s_c4_total_round_stage": "汇总_c4_total_round_stage",
                "s_c4_d1_round_stage": "汇总_c4_d1_round_stage",
                "s_c4_d2_round_stage": "汇总_c4_d2_round_stage",
                "s_c5_total_round_gain": "汇总_c5_total_round_gain",
                "s_c5_d1_round_gain": "汇总_c5_d1_round_gain",
                "s_c5_d2_round_gain": "汇总_c5_d2_round_gain",
                "s_c6_model_total_round_gain": "汇总_c6_model_round_gain",
                "d_c7_admission_info_gain_case": "明细_c7_info_gain_case",
                "s_c7_admission_info_gain_model": "汇总_c7_info_gain_model",
            },
            "rule_label_fix": "D2决策“通过二审_完全不同”显示为“不同但合理”",
            "rule_color": "未经过=浅灰; 本流程进行前已结束=深灰; 流程不通过=红色; 检查轮次=绿色渐变; 决策一致性=蓝色渐变",
            "rule_check_merge": "D1决策检查并入D2Loop用于检查相关校准与效率计算",
            "rule_d1_gate3": "D1 anomaly excluded; Gate3 fail not counted into D4 calculations",
            "rule_stage_sync": "校准阶段样本口径与 Sankey 对齐：D2 剔除本流程进行前已结束；D3 剔除本流程进行前已结束；D4 仅保留完成流程。",
            "rule_calibration_bubble": "B图为分箱散点，气泡大小=该分箱样本量(n)",
            "formula_avg_check_count": "D1=门诊执行轮数；D2=住院执行轮数+1（并入D1决策检查）",
            "formula_c3_marginal_gain": "C3a 统计每个额外检查轮次相对前一轮的非负边际新增匹配信息项数，定义为 max(matched_count_final_x - matched_count_final_{x-1}, 0)；门诊阶段以问诊基线为0轮，入院阶段以0轮住院检查基线为0轮；剔除 flow_end_stage 停在 D1_Outpatient_Loop / D2_Admission_Loop 的轨迹。",
            "formula_c3_final_dx_proximity": "C3b 改为同一病例-模型轨迹的三阶段最终诊断接近度：D1/D2 来自 Gemini 2.5 Pro 按 D3 最终诊断 judge 口径对 GT_Final_Diagnosis 的重评分，D3 直接复用现有 Gate3 诊断匹配评估分数；score 越高表示越接近 GT_Final_Diagnosis，distance=1-score。",
            "formula_c3_final_dx_transition": "相邻阶段比较使用 proximity_score 的差值 delta_score，并设容忍阈值 ±0.01：delta>0.01 记为“更接近”，delta<-0.01 记为“更远”，其余为“基本不变”；strict_monotonic_non_decreasing 要求 D2-D1 >= 0.01 且 D3-D2 >= 0.01。",
            "formula_c4_round_groups": "C4 追加检查轮次分层：d1_check_count = D1_Outpatient_Loop__executed_rounds；d2_check_count = D2_Admission_Loop__executed_rounds + 1（并入D1决策检查）；total_check_count = d1_check_count + d2_check_count；并分别输出 total_round_group、d1_round_group、d2_round_group（>=4轮合并为4+）。",
            "formula_c5_round_gain": "C5 统计各检查轮次分层下 D3 相对 D1 的最终诊断接近度提升(delta_score_d3_vs_d1)分布与均值。",
            "formula_c6_model_round_gain": "C6 在各模型内部统计 d2_round_group（入院检查次数）下的平均 D2-D1 接近度提升，用于比较不同模型在入院阶段检查增加后修正诊断收益是否提升。",
            "formula_c7_admission_info_gain": "C7 仅保留同一病例下五模型均执行住院检查的轨迹，按每条轨迹最后一轮住院检查的 matched_count_final 作为入院信息量，关联 D3-D1 诊断接近度提升进行模型分面比较。",
            "source_final_dx_proximity_raw": final_dx_source_rel or "missing",
            "warning_c3_final_dx_proximity": final_dx_load_error or "",
            "source_hint__d_sankey_used": "analysis_viz/data/derived/figdata/paper/Fig7__sankey_flow_source.xlsx:detail_used",
            "source_hint__d_calib_case": "analysis_viz/data/derived/metrics/calibration/calibration_reliability_stagewise_source.xlsx:detail_used",
            "source_hint__d_calib_bins": "由 d_calib_case 在统一阶段过滤后按 center/model/stage/bin 重新聚合",
            "source_hint__d_b3_diag_bin_raw": "analysis_viz/data/derived/metrics/calibration/calibration_line_diagnosis_stagewise_source.xlsx:bin_summary_used",
            "source_hint__d_b4_check_round_raw": "analysis_viz/data/derived/metrics/calibration/calibration_line_check_stagewise_source.xlsx:detail_round_all",
            "source_hint__d_b5_plan_bin_raw": "analysis_viz/data/derived/metrics/calibration/calibration_line_plan_stagewise_source.xlsx:bin_summary_used",
            "source_hint__s_b3_diag_model_points": "由 c_b3_diag_stage_bin 按 stage+model_short 对 bin 做样本量加权聚合",
            "source_hint__s_b4_check_round_model_points": "由 c_b4_check_stage_round_bin 按 stage+round_group+model_short 对 bin 做样本量加权聚合",
            "source_hint__s_b5_plan_model_points": "由 c_b5_plan_stage_bin 按 stage+model_short 对 bin 做样本量加权聚合",
            "source_hint__d_check_raw": "metrics_by_case + center_data/*/(doc|judge) agent 的 D1/D2 loop 原始JSON（用于轮次追溯）",
            "source_hint__s_b1_d1_table": "由 d_calib_bins 按 stage4=D1 汇总",
            "source_hint__d_c3_final_dx_proximity_case": (
                f"{Path(final_dx_source_rel).name}:{final_dx_detail_sheet}" if final_dx_source_rel and final_dx_detail_sheet else "see_meta"
            ),
            "source_hint__d_c4_final_dx_round_case": "由 c_c3_final_dx_proximity_triplet 与 metrics_by_case 的检查轮次/匹配率字段按 center+model+case_id 合并得到",
            "source_hint__d_c4_final_dx_stage_long": "由 d_c4_final_dx_round_case 将 d1_score/d2_score/d3_score 展成长表得到",
            "source_hint__d_c7_admission_info_gain_case": "由 d_c4_final_dx_round_case 与 d_c3_marginal_gain_round(phase_key=D2末轮)按 center+model+case_id 合并，并筛选五模型均需住院检查病例",
        },
    )
    supple_dir = OUT_SUPPLE_DIR / group
    supple_fig_dir = supple_dir / "figures"
    supple_source_dir = supple_dir / "source_data"
    supple_fig_dir.mkdir(parents=True, exist_ok=True)
    supple_source_dir.mkdir(parents=True, exist_ok=True)
    supple_stage_tables = supple_source_dir / "G4B_stage_calibration_tables_supplement_v1.xlsx"
    supple_stage_tables.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(supple_stage_tables, engine="openpyxl") as writer:
        stage_bin_model[stage_bin_model["stage4"] == "D1"].copy().to_excel(writer, sheet_name="B1_D1", index=False)
        stage_bin_model[stage_bin_model["stage4"] == "D2"].copy().to_excel(writer, sheet_name="B2_D2", index=False)
        stage_bin_model[stage_bin_model["stage4"] == "D3"].copy().to_excel(writer, sheet_name="B3_D3", index=False)
        stage_bin_model[stage_bin_model["stage4"] == "D4"].copy().to_excel(writer, sheet_name="B4_D4", index=False)
        stage_weighted.copy().to_excel(writer, sheet_name="B0_weighted", index=False)
        stage_model_points.copy().to_excel(writer, sheet_name="B_stage_points", index=False)
        diag_stage_bin.copy().to_excel(writer, sheet_name="B3_diag_bin", index=False)
        diag_stage_model_points.copy().to_excel(writer, sheet_name="B3_diag_model_points", index=False)
        diag_stage_overall_points.copy().to_excel(writer, sheet_name="B3_diag_overall", index=False)
        diag_stage_summary.copy().to_excel(writer, sheet_name="B3_diag_summary", index=False)
        check_round_bin.copy().to_excel(writer, sheet_name="B4_check_round_bin", index=False)
        check_round_model_points.copy().to_excel(writer, sheet_name="B4_check_model_points", index=False)
        check_round_overall_points.copy().to_excel(writer, sheet_name="B4_check_overall", index=False)
        check_round_summary.copy().to_excel(writer, sheet_name="B4_check_round_summary", index=False)
        plan_stage_bin.copy().to_excel(writer, sheet_name="B5_plan_bin", index=False)
        plan_stage_model_points.copy().to_excel(writer, sheet_name="B5_plan_model_points", index=False)
        plan_stage_overall_points.copy().to_excel(writer, sheet_name="B5_plan_overall", index=False)
        plan_stage_summary.copy().to_excel(writer, sheet_name="B5_plan_summary", index=False)
        check_gain_summary.copy().to_excel(writer, sheet_name="C3_marginal_gain_summary", index=False)
        final_dx_stage_summary.copy().to_excel(writer, sheet_name="C3_final_dx_stage", index=False)
        final_dx_transition_summary.copy().to_excel(writer, sheet_name="C3_final_dx_transition", index=False)
        final_dx_total_round_stage_summary.copy().to_excel(writer, sheet_name="C4_total_round_stage", index=False)
        final_dx_d1_round_stage_summary.copy().to_excel(writer, sheet_name="C4_d1_round_stage", index=False)
        final_dx_d2_round_stage_summary.copy().to_excel(writer, sheet_name="C4_d2_round_stage", index=False)
        final_dx_total_round_gain_summary.copy().to_excel(writer, sheet_name="C5_total_round_gain", index=False)
        final_dx_d1_round_gain_summary.copy().to_excel(writer, sheet_name="C5_d1_round_gain", index=False)
        final_dx_d2_round_gain_summary.copy().to_excel(writer, sheet_name="C5_d2_round_gain", index=False)
        final_dx_model_total_round_gain_summary.copy().to_excel(writer, sheet_name="C6_model_total_round_gain", index=False)
        admission_info_gain_case.copy().to_excel(writer, sheet_name="C7_info_gain_case", index=False)
        admission_info_gain_model_summary.copy().to_excel(writer, sheet_name="C7_info_gain_model", index=False)
        d2_baseline_summary.copy().to_excel(writer, sheet_name="C3_admission_baseline", index=False)
    _style_workbook(supple_stage_tables)
    supple_main_source = None
    supple_copies = {
        "supple_stage_calibration": _copy_to_supplement(out_calib_overall_stage, supple_fig_dir / out_calib_overall_stage.name),
        "supple_stage_calibration_table": _copy_to_supplement(out_calib_stage_table, supple_fig_dir / out_calib_stage_table.name),
        "supple_diag_type_calibration": _copy_to_supplement(out_calib_diag_type, supple_fig_dir / out_calib_diag_type.name),
        "supple_check_round_calibration": _copy_to_supplement(out_calib_check_round, supple_fig_dir / out_calib_check_round.name),
        "supple_plan_type_calibration": _copy_to_supplement(out_calib_plan_type, supple_fig_dir / out_calib_plan_type.name),
        "supple_check_efficiency_panel": _copy_to_supplement(out_eff_panel, supple_fig_dir / out_eff_panel.name),
        "supple_check_gain_panel": _copy_to_supplement(out_check_gain_panel, supple_fig_dir / out_check_gain_panel.name),
        "supple_check_gain_shift_panel": _copy_to_supplement(
            out_check_gain_shift_panel, supple_fig_dir / out_check_gain_shift_panel.name
        ),
        "supple_final_dx_round_strata_panel": _copy_to_supplement(
            out_final_dx_round_strata_panel, supple_fig_dir / out_final_dx_round_strata_panel.name
        ),
        "supple_final_dx_gain_round_panel": _copy_to_supplement(
            out_final_dx_gain_round_panel, supple_fig_dir / out_final_dx_gain_round_panel.name
        ),
        "supple_final_dx_gain_model_panel": _copy_to_supplement(
            out_final_dx_gain_model_panel, supple_fig_dir / out_final_dx_gain_model_panel.name
        ),
        "supple_final_dx_admission_info_gain_panel": _copy_to_supplement(
            out_final_dx_admission_info_gain_panel, supple_fig_dir / out_final_dx_admission_info_gain_panel.name
        ),
    }
    keep_supple_fig = {
        out_calib_overall_stage.name,
        out_calib_stage_table.name,
        out_calib_diag_type.name,
        out_calib_check_round.name,
        out_calib_plan_type.name,
        out_eff_panel.name,
        out_check_gain_panel.name,
        out_check_gain_shift_panel.name,
        out_final_dx_round_strata_panel.name,
        out_final_dx_gain_round_panel.name,
        out_final_dx_gain_model_panel.name,
        out_final_dx_admission_info_gain_panel.name,
    }
    supple_fig_archive = supple_dir / "archive" / "figures"
    supple_fig_archive.mkdir(parents=True, exist_ok=True)
    for p in supple_fig_dir.glob("*.png"):
        if p.name not in keep_supple_fig:
            dst = supple_fig_archive / p.name
            try:
                if dst.exists():
                    dst.unlink()
                shutil.move(str(p), str(dst))
            except Exception:
                pass
    keep_supple_source = {supple_stage_tables.name}
    supple_source_archive = supple_dir / "archive" / "source_data"
    supple_source_archive.mkdir(parents=True, exist_ok=True)
    for p in supple_source_dir.glob("*.xlsx"):
        if p.name in keep_supple_source:
            continue
        dst = supple_source_archive / p.name
        try:
            if dst.exists():
                dst.unlink()
            shutil.move(str(p), str(dst))
        except Exception:
            pass
    supple_caption = _write_single_caption_file(
        supple_dir,
        "图注_Figure_G4_补充材料.md",
        [
            "# Figure G4 补充材料图注",
            "",
            "- `G4B_calibration_overall_stage_v2.png`：仅保留 D1-D4 四阶段平均校准点图；每阶段均显示五模型点与一个阶段加权星点，统一使用底部公共图例与公共坐标轴标签，不再展示总体面板或拟合曲线。",
            "- `G4B_stage_calibration_table_v2.png`：按环节×模型汇总展示平均置信度、观察准确率、校准差值与样本量，便于直接贴入论文表格。",
            "- `G4B3_calibration_diag_decision_types_v1.png`：按诊断决策类型拆分为 D1/D2/D3 三个子图，展示各模型平均校准点与总体加权点，便于横向比较诊断阶段校准偏差。",
            "- `G4B4_calibration_check_rounds_v1.png`：按检查决策类型拆分为 D1 门诊检查与 D2 入院检查，并进一步按 1/2/3/4 轮检查分格展示各模型平均校准点与总体加权点。",
            "- `G4B5_calibration_plan_decision_types_v1.png`：按方案决策类型拆分为 D2 术前治疗、D3 术后治疗与 D4 随访康复，展示各模型平均校准点与总体加权点。",
            "- `G4C2_check_efficiency_panel_v2.png`：原主文 C 子图（检查效率）移至补充材料保留，用于与新 C 子图（ablation 诊断差距）对照。",
            "- `G4C3_check_gain_marginal_info_panel_v2.png`：展示相邻额外检查轮次带来的边际新增诊断信息；每根条形对应当前轮次相对上一轮（或基线）的非负新增匹配信息项数，分别对应门诊诊断环节与入院诊断环节。",
            "- `G4C3_check_gain_decision_shift_panel_v1.png`：展示 D1 / D2 / D3 三阶段最终诊断接近度分布（箱线）与阶段均值，避免轨迹叠线造成视觉混杂。",
            "- `G4C4_check_rounds_final_dx_proximity_panel_v1.png`：分别按总检查轮次、门诊阶段检查轮次、住院阶段检查轮次分层，比较 D1 / D2 / D3 三阶段的平均最终诊断接近度轨迹，用于观察“检查越多时，三阶段诊断与 GT 最终诊断的距离是否整体更近”。",
            "- `G4C5_check_rounds_final_dx_gain_panel_v1.png`：展示不同检查轮次分层（总轮次/门诊轮次/住院轮次）下 `D3-D1` 最终诊断接近度提升的分布，用于衡量新增检查信息对最终诊断修正的净收益。",
            "- `G4C6_check_rounds_final_dx_gain_model_v1.png`：按模型分面展示入院检查次数与平均 `D2-D1` 接近度提升的关系，用于比较不同模型在入院阶段新增检查下的修正诊断收益差异。",
            "- `G4C7_admission_info_vs_dx_gain_model_v1.png`：在“五模型均执行住院检查”的病例子集中，按模型比较“入院阶段最终匹配信息项数”与 `D3-D1` 诊断接近度提升的关系。",
            "- `G4B_stage_calibration_tables_supplement_v1.xlsx`：除 B0 与阶段校准摘要外，新增 B3/B4/B5 决策类型校准曲线对应的明细与汇总，以及 C4/C5/C6/C7 的检查轮次分层、信息量与接近度收益汇总，便于逐项核查。",
        ],
    )
    _write_caption(
        group,
        [
            "# G4 组图图注",
            "",
            "- `G4A_sankey_all_center_model_v3.png`：主流程 Sankey 口径修正：不纳入 D1 特殊样本；`D1决策检查` 并入 `D2住院检查`；`D2循环_未经过` 映射为 `住院检查:1轮检查`，原 `X轮` 顺延为 `X+1轮`，`超3轮` 映射为 `超过4轮检查`。",
            "- `G4A_sankey_arrow_rect_v1.png`：A 图替代版，使用“箭头+长方形节点”展示主要流向；每个节点左侧标注样本数、右侧标注状态文本，低频状态按阶段合并为“其他状态”，用于替代 Sankey 的文字可读性审阅。",
            "- `G4B_calibration_overall_weighted_v6.png`：主文仅保留该校准图。横轴为平均置信度（模型自报打分），纵轴为观察准确率（与正确性指标同口径），黑色星形点为 D1-D4 按阶段样本量加权后的总体校准点；图中直接标注模型简称与“加权总体”，并已与 Sankey 同步剔除 D2 失败后的 D3/D4 残留样本。",
            "- `G4B_calibration_overall_stage_v2.png`：该图不再进入主文，但已作为 supplementary 保留“D1-D4 四阶段平均校准点”视图，便于核对阶段误差来源。",
            "- `G4C_ablation_diag_dumbbell_v1.png`：主文 C 子图替换为 ablation 总体哑铃图（D1/D2/D3 诊断），用于直接对比正常流程与消融流程的诊断差距。",
            "- `G4_groupD_sankey_calib_efficiency_v7.png`：主文定版组合图更新为 `Sankey + B0总体校准 + C(ablation诊断差距)`。",
            "- `layout_like_fig1_v1/G4_groupD_sankey_calib_efficiency_layout_like_fig1_v1.png`：按示例比例导出的替代排版（A 顶部全宽；B/C 底部并排），并在同目录额外输出 `G4A_flow_panel_v1.png`、`G4B_calibration_panel_v1.png`、`G4C_ablation_panel_v1.png` 便于单独引用。",
            "- `G4B_calibration_overall_stage_v2.png`、`G4B_stage_calibration_table_v2.png`、`G4B3_calibration_diag_decision_types_v1.png`、`G4B4_calibration_check_rounds_v1.png`、`G4B5_calibration_plan_decision_types_v1.png`、`G4C2_check_efficiency_panel_v2.png`、`G4C3_check_gain_marginal_info_panel_v2.png`、`G4C3_check_gain_decision_shift_panel_v1.png`、`G4C4_check_rounds_final_dx_proximity_panel_v1.png`、`G4C5_check_rounds_final_dx_gain_panel_v1.png`、`G4C6_check_rounds_final_dx_gain_model_v1.png` 与 `G4C7_admission_info_vs_dx_gain_model_v1.png`：作为补充材料使用；其中 B3/B4/B5 分别对应诊断、检查、方案的“模型平均校准点+总体加权点”视图，C3a 说明不同额外检查轮次对应的边际新增诊断信息，C3b 说明在同一病例、同一模型内，随着阶段信息增加，诊断是否更接近 `GT_Final_Diagnosis`，C4-C7 进一步把该接近度收益与检查轮次、信息量和模型差异结合起来展示（C6 当前口径为“入院检查次数 vs D2-D1”）。",
            "- 其余历史方案图（路径校准、信息增益散点与箱线等）已迁移到 `analysis_viz/figures/v2_subplots/G4_system/archive/figures/`；补充材料目录下的非定版图则迁移到 `analysis_viz/figures/v2_subplots/_supplementary/G4_system/archive/figures/`，对应 source 数据同步进入各自 `archive/source_data/`。",
        ],
    )

    # 主目录保留主文定版与其组成子图；其余自动归档
    fig_root = OUT_FIG_DIR / group
    fig_archive = fig_root / "archive" / "figures"
    fig_archive.mkdir(parents=True, exist_ok=True)
    keep_fig = {
        out_group_ref_v6.name,
        out_sankey.name,
        out_sankey_arrow_rect.name,
        out_calib_overall_v5.name,
        out_ablation_main_c.name,
        out_eff_panel.name,
    }
    for p in fig_root.glob("*.png"):
        if p.name in keep_fig:
            continue
        dst = fig_archive / p.name
        try:
            if dst.exists():
                dst.unlink()
            shutil.move(str(p), str(dst))
        except Exception:
            pass

    data_root = OUT_DATA_DIR / group
    data_archive = data_root / "archive" / "source_data"
    data_archive.mkdir(parents=True, exist_ok=True)
    for p in data_root.glob("*_source.xlsx"):
        if p.name == source_path.name:
            continue
        dst = data_archive / p.name
        try:
            if dst.exists():
                dst.unlink()
            shutil.move(str(p), str(dst))
        except Exception:
            pass

    fig_side_source = fig_root / "source_data"
    side_archive = fig_root / "archive" / "source_data"
    side_archive.mkdir(parents=True, exist_ok=True)
    for p in fig_side_source.glob("*_source.xlsx"):
        if p.name == source_path.name:
            continue
        dst = side_archive / p.name
        try:
            if dst.exists():
                dst.unlink()
            shutil.move(str(p), str(dst))
        except Exception:
            pass

    return {
        "figure_main_final": out_group_ref_v6,
        "figure_sub_sankey": out_sankey,
        "figure_sub_sankey_arrow_rect": out_sankey_arrow_rect,
        "figure_sub_b0_calibration": out_calib_overall_v5,
        "figure_sub_c_ablation": out_ablation_main_c,
        "figure_sub_c2_check_count": out_eff_panel,
        "figure_main_layout_like_fig1": out_layout_like_main,
        "layout_like_fig1_panel_a": out_layout_like_a,
        "layout_like_fig1_panel_b": out_layout_like_b,
        "layout_like_fig1_panel_c": out_layout_like_c,
        "source": source_path,
        "supple_stage_tables": supple_stage_tables,
        "supple_caption": supple_caption,
        **{k: v for k, v in supple_copies.items() if v is not None},
        **({"supple_source": supple_main_source} if supple_main_source is not None else {}),
    }


def build_s1_manual_vs_llm(d2_rule_map: pd.DataFrame) -> dict[str, Path]:
    _ensure_style()
    group = "S1_manual_vs_llm"
    out_result = OUT_FIG_DIR / group / "S1_result_quality_manual_vs_llm_v4.png"
    out_reason = OUT_FIG_DIR / group / "S1_reasoning_quality_manual_vs_llm_v4.png"
    out_combined = OUT_FIG_DIR / group / "S1_manual_vs_llm_stacked_v4.png"
    out_combined_alt = OUT_FIG_DIR / group / "S1_manual_vs_llm_stacked_legend_alt_v1.png"
    out_side_by_side_alt = OUT_FIG_DIR / group / "S1_manual_vs_llm_side_by_side_bottom_legend_v1.png"
    out_side_by_side_bar_alt = OUT_FIG_DIR / group / "S1_manual_vs_llm_side_by_side_bar_v1.png"
    stage_case_sets = _load_stage_case_sets_from_sankey_source(d2_rule_map)

    result = pd.read_excel(
        DERIVED_METRICS_DIR / "alignment" / "alignment_result_vs_judge_case_level_source.xlsx",
        sheet_name="detail_used",
    )
    reason = pd.read_excel(
        DERIVED_METRICS_DIR / "alignment" / "alignment_reasoning_vs_llm_case_level_source.xlsx",
        sheet_name="detail_used",
    )
    result = _attach_d2_manual_rules(result, d2_rule_map)
    reason = _attach_d2_manual_rules(reason, d2_rule_map)
    result = result[
        ~(result["d2_force_stop"] & result["stage"].astype(str).isin(["D3_Decision", "D4_Plan", "D3_Surgery_Decision", "D4_Rehab_Plan"]))
    ].copy()
    reason = reason[
        ~(reason["d2_force_stop"] & reason["stage"].astype(str).isin(["D3_Decision", "D4_Plan", "D3_Surgery_Decision", "D4_Rehab_Plan"]))
    ].copy()
    result["model_short"] = result["model"].map(MODEL_SHORT).fillna(result["model"].astype(str))
    reason["model_short"] = reason["model"].map(MODEL_SHORT).fillna(reason["model"].astype(str))

    # 按用户指定口径重算 judge score（来源：center_data/*/judge agent）
    try:
        judge_recalc = _load_s1_judge_scores_from_center_raw()
        result = result.merge(
            judge_recalc,
            on=["center", "model", "case_id", "stage"],
            how="left",
        )
        if "judge_score_0_5_new" in result.columns:
            result["judge_score_0_5"] = pd.to_numeric(result["judge_score_0_5_new"], errors="coerce")
            result["judge_source_sheet"] = result["judge_source_sheet_new"].fillna(result.get("judge_source_sheet", ""))
            result["judge_source_col"] = result["judge_source_col_new"].fillna(result.get("judge_source_col", ""))
            result["judge_rule"] = result["judge_rule_new"].fillna("")
            result["judge_status_raw"] = result["judge_status_raw_new"].fillna("")
            result["judge_source_path"] = result["judge_source_path_new"].fillna("")
            drop_cols = [
                "judge_score_0_5_new",
                "judge_source_sheet_new",
                "judge_source_col_new",
                "judge_rule_new",
                "judge_status_raw_new",
                "judge_source_path_new",
            ]
            result = result.drop(columns=[c for c in drop_cols if c in result.columns])
    except Exception:
        pass

    result["human_score_0_5"] = pd.to_numeric(result["human_score_0_5"], errors="coerce")
    result["judge_score_0_5"] = pd.to_numeric(result["judge_score_0_5"], errors="coerce")
    reason["human_score_0_5"] = pd.to_numeric(reason["human_score_0_5"], errors="coerce")
    reason["llm_reasoning_score_0_5"] = pd.to_numeric(reason["llm_reasoning_score_0_5"], errors="coerce")

    stage4_map = {
        "D1_Loop": "D1",
        "D1_Decision": "D1",
        "D2_Loop": "D2",
        "D2_Decision": "D2",
        "D3_Decision": "D3",
        "D4_Plan": "D4",
    }

    def _half_avg(a: float, b: float) -> float:
        if np.isfinite(a) and np.isfinite(b):
            return float((a + b) / 2.0)
        if np.isfinite(a):
            return float(a)
        if np.isfinite(b):
            return float(b)
        return float("nan")

    def _build_stage4(detail_df: pd.DataFrame, target_col: str) -> pd.DataFrame:
        d = detail_df.copy()
        d["stage"] = d["stage"].astype(str)
        d["stage4"] = d["stage"].map(stage4_map)
        d = d[d["stage4"].isin(["D1", "D2", "D3", "D4"])].copy()
        g = (
            d.groupby(["center", "model", "case_id", "model_short", "stage"], as_index=False)[["human_score_0_5", target_col]]
            .mean()
            .pivot_table(
                index=["center", "model", "case_id", "model_short"],
                columns="stage",
                values=["human_score_0_5", target_col],
                aggfunc="mean",
            )
            .reset_index()
        )
        # flatten multi-index columns
        g.columns = [
            "_".join([str(x) for x in c if str(x) != ""]).strip("_") if isinstance(c, tuple) else str(c) for c in g.columns
        ]
        for col in [
            f"human_score_0_5_D1_Loop",
            f"human_score_0_5_D1_Decision",
            f"human_score_0_5_D2_Loop",
            f"human_score_0_5_D2_Decision",
            f"human_score_0_5_D3_Decision",
            f"human_score_0_5_D4_Plan",
            f"{target_col}_D1_Loop",
            f"{target_col}_D1_Decision",
            f"{target_col}_D2_Loop",
            f"{target_col}_D2_Decision",
            f"{target_col}_D3_Decision",
            f"{target_col}_D4_Plan",
        ]:
            if col not in g.columns:
                g[col] = np.nan
        out_rows: list[dict[str, Any]] = []
        for _, r in g.iterrows():
            h_d1_loop = _to_float(r.get("human_score_0_5_D1_Loop", np.nan))
            h_d1_dec = _to_float(r.get("human_score_0_5_D1_Decision", np.nan))
            h_d2_loop = _to_float(r.get("human_score_0_5_D2_Loop", np.nan))
            h_d2_dec = _to_float(r.get("human_score_0_5_D2_Decision", np.nan))
            h_d1 = h_d1_dec
            h_d2 = h_d2_dec
            h_d3 = _to_float(r.get("human_score_0_5_D3_Decision", np.nan))
            h_d4 = _to_float(r.get("human_score_0_5_D4_Plan", np.nan))
            t_d1_loop = _to_float(r.get(f"{target_col}_D1_Loop", np.nan))
            t_d1_dec = _to_float(r.get(f"{target_col}_D1_Decision", np.nan))
            t_d2_loop = _to_float(r.get(f"{target_col}_D2_Loop", np.nan))
            t_d2_dec = _to_float(r.get(f"{target_col}_D2_Decision", np.nan))
            t_d1 = t_d1_dec
            t_d2 = t_d2_dec
            t_d3 = _to_float(r.get(f"{target_col}_D3_Decision", np.nan))
            t_d4 = _to_float(r.get(f"{target_col}_D4_Plan", np.nan))
            base = {
                "center": r["center"],
                "model": r["model"],
                "case_id": r["case_id"],
                "model_short": r["model_short"],
            }
            out_rows.extend(
                [
                    {
                        **base,
                        "stage": "D1",
                        "human_score_0_5": h_d1,
                        target_col: t_d1,
                        "human_loop_score": np.nan,
                        "human_decision_score": h_d1_dec,
                        "target_loop_score": np.nan,
                        "target_decision_score": t_d1_dec,
                        "merge_rule": "D1=decision",
                    },
                    {
                        **base,
                        "stage": "D2",
                        "human_score_0_5": h_d2,
                        target_col: t_d2,
                        "human_loop_score": np.nan,
                        "human_decision_score": h_d2_dec,
                        "target_loop_score": np.nan,
                        "target_decision_score": t_d2_dec,
                        "merge_rule": "D2=decision",
                    },
                    {
                        **base,
                        "stage": "D3",
                        "human_score_0_5": h_d3,
                        target_col: t_d3,
                        "human_loop_score": np.nan,
                        "human_decision_score": h_d3,
                        "target_loop_score": np.nan,
                        "target_decision_score": t_d3,
                        "merge_rule": "D3=decision",
                    },
                    {
                        **base,
                        "stage": "D4",
                        "human_score_0_5": h_d4,
                        target_col: t_d4,
                        "human_loop_score": np.nan,
                        "human_decision_score": h_d4,
                        "target_loop_score": np.nan,
                        "target_decision_score": t_d4,
                        "merge_rule": "D4=decision",
                    },
                ]
            )
        out = pd.DataFrame(out_rows)
        if not out.empty:
            src_hint = (
                "alignment_result_vs_judge_case_level_source.xlsx:detail_used"
                if target_col == "judge_score_0_5"
                else "alignment_reasoning_vs_llm_case_level_source.xlsx:detail_used"
            )
            out.insert(0, "source_table", src_hint)
        if not out.empty:
            rows = np.arange(2, len(out) + 2)
            out["formula_human_score_0_5"] = [
                f"=IF(COUNTA(I{rr}:J{rr})=0,\"\",IF(COUNTA(I{rr}:J{rr})=1,MAX(I{rr}:J{rr}),AVERAGE(I{rr}:J{rr})))"
                for rr in rows
            ]
            out[f"formula_{target_col}"] = [
                f"=IF(COUNTA(K{rr}:L{rr})=0,\"\",IF(COUNTA(K{rr}:L{rr})=1,MAX(K{rr}:L{rr}),AVERAGE(K{rr}:L{rr})))"
                for rr in rows
            ]
            out["说明_阶段融合"] = "D1/D2 仅取decision；D3/D4 仅取decision"
        return out.dropna(subset=["human_score_0_5", target_col], how="all").reset_index(drop=True)

    result_stage4 = _build_stage4(result, "judge_score_0_5")
    reason_stage4 = _build_stage4(reason, "llm_reasoning_score_0_5")
    result_stage4 = _filter_stage_case_eligibility(result_stage4, "stage", stage_case_sets)
    reason_stage4 = _filter_stage_case_eligibility(reason_stage4, "stage", stage_case_sets)
    stage4_order = ["D1", "D2", "D3", "D4"]
    stage4_labels = {"D1": "D1", "D2": "D2", "D3": "D3", "D4": "D4"}
    stage4_identity_map = {st: st for st in stage4_order}
    check_stage_map = {"D1_Loop": "D1_CHECK", "D2_Loop": "D2_CHECK"}
    check_stage_order = ["D1_CHECK", "D2_CHECK"]
    check_stage_label_map = {"D1_CHECK": "门诊检查", "D2_CHECK": "住院检查"}
    result_check_detail = result[result["stage"].astype(str).isin(list(check_stage_map.keys()))].copy()
    reason_check_detail = reason[reason["stage"].astype(str).isin(list(check_stage_map.keys()))].copy()
    result_check_detail["check_stage_cn"] = result_check_detail["stage"].map(check_stage_map).map(check_stage_label_map)
    reason_check_detail["check_stage_cn"] = reason_check_detail["stage"].map(check_stage_map).map(check_stage_label_map)
    s1_result_check_raw, s1_result_check_paper = _build_manual_target_stage_table(
        result_check_detail,
        target_col="judge_score_0_5",
        stage_group_map=check_stage_map,
        stage_order=check_stage_order,
        stage_label_map=check_stage_label_map,
        target_label="Judge均分",
    )
    s1_reason_check_raw, s1_reason_check_paper = _build_manual_target_stage_table(
        reason_check_detail,
        target_col="llm_reasoning_score_0_5",
        stage_group_map=check_stage_map,
        stage_order=check_stage_order,
        stage_label_map=check_stage_label_map,
        target_label="LLM均分",
    )
    s1_result_model_stage_raw, s1_result_model_stage_paper = _build_manual_target_model_stage_table(
        result_stage4,
        target_col="judge_score_0_5",
        stage_group_map=stage4_identity_map,
        stage_order=stage4_order,
        stage_label_map=stage4_labels,
        target_label="Judge均分",
    )
    s1_reason_model_stage_raw, s1_reason_model_stage_paper = _build_manual_target_model_stage_table(
        reason_stage4,
        target_col="llm_reasoning_score_0_5",
        stage_group_map=stage4_identity_map,
        stage_order=stage4_order,
        stage_label_map=stage4_labels,
        target_label="LLM均分",
    )

    # 单图（折线替代版）：去条带，保留医生/Judge双线，方形点标记，三段背景平滑过渡
    fig_a, ax_a = plt.subplots(figsize=(15.6, 6.6))
    _plot_manual_vs_target_line_on_ax(
        ax=ax_a,
        detail=result_stage4.dropna(subset=["human_score_0_5", "judge_score_0_5"]),
        score_col_human="human_score_0_5",
        score_col_target="judge_score_0_5",
        title="S1-A 结果质量",
        y_label="评分 (0-5)",
        human_label="医生",
        target_label="Judge",
        human_color="#6BA9D7",
        target_color="#2F6FAE",
        bg_colors=["#EDF5FC", "#E2EEF9", "#D4E5F3", "#C2D7E9"],
        stage_order=stage4_order,
        stage_label_map=stage4_labels,
        block_labels=["D1", "D2", "D3-D4"],
    )
    _archive_existing_output(out_result, "figures")
    _save_fig(out_result)

    fig_b, ax_b = plt.subplots(figsize=(15.6, 6.6))
    _plot_manual_vs_target_line_on_ax(
        ax=ax_b,
        detail=reason_stage4.dropna(subset=["human_score_0_5", "llm_reasoning_score_0_5"]),
        score_col_human="human_score_0_5",
        score_col_target="llm_reasoning_score_0_5",
        title="S1-B 逻辑质量",
        y_label="评分 (0-5)",
        human_label="医生",
        target_label="Judge",
        human_color="#87B58A",
        target_color="#C6D8C0",
        bg_colors=["#F2F8EF", "#E6F0E2", "#D7E6D1", "#C6D8C0"],
        stage_order=stage4_order,
        stage_label_map=stage4_labels,
        block_labels=["D1", "D2", "D3-D4"],
    )
    _archive_existing_output(out_reason, "figures")
    _save_fig(out_reason)

    fig, axs = plt.subplots(2, 1, figsize=(16.2, 11.8), sharex=True)
    axs[0].set_facecolor("white")
    axs[1].set_facecolor("white")
    _plot_manual_vs_target_line_on_ax(
        ax=axs[0],
        detail=result_stage4.dropna(subset=["human_score_0_5", "judge_score_0_5"]),
        score_col_human="human_score_0_5",
        score_col_target="judge_score_0_5",
        title="A. 结果质量",
        y_label="评分 (0-5)",
        human_label="医生",
        target_label="Judge",
        human_color="#6BA9D7",
        target_color="#2F6FAE",
        bg_colors=["#EDF5FC", "#E2EEF9", "#D4E5F3", "#C2D7E9"],
        stage_order=stage4_order,
        stage_label_map=stage4_labels,
        block_labels=["D1", "D2", "D3-D4"],
    )
    _plot_manual_vs_target_line_on_ax(
        ax=axs[1],
        detail=reason_stage4.dropna(subset=["human_score_0_5", "llm_reasoning_score_0_5"]),
        score_col_human="human_score_0_5",
        score_col_target="llm_reasoning_score_0_5",
        title="B. 逻辑质量",
        y_label="评分 (0-5)",
        human_label="医生",
        target_label="Judge",
        human_color="#87B58A",
        target_color="#C6D8C0",
        bg_colors=["#F2F8EF", "#E6F0E2", "#D7E6D1", "#C6D8C0"],
        stage_order=stage4_order,
        stage_label_map=stage4_labels,
        block_labels=["D1", "D2", "D3-D4"],
    )
    _archive_existing_output(out_combined, "figures")
    _save_fig(out_combined)

    # 替换版本：结果/推理统一双折线配色（蓝+绿）与绿到蓝背景渐变，图例采用胶囊样式
    fig_alt, axs_alt = plt.subplots(2, 1, figsize=(16.2, 11.8), sharex=True)
    axs_alt[0].set_facecolor("white")
    axs_alt[1].set_facecolor("white")
    _plot_manual_vs_target_line_on_ax(
        ax=axs_alt[0],
        detail=result_stage4.dropna(subset=["human_score_0_5", "judge_score_0_5"]),
        score_col_human="human_score_0_5",
        score_col_target="judge_score_0_5",
        title="A. 结果质量（替换版）",
        y_label="评分 (0-5)",
        human_label="Experts",
        target_label="Automated judge",
        human_color="#5E9ECF",
        target_color="#66A57A",
        bg_colors=["#EAF6EA", "#DEECDF", "#D3E4E0", "#C6DCE2"],
        stage_order=stage4_order,
        stage_label_map=stage4_labels,
        block_labels=["D1", "D2", "D3-D4"],
        legend_mode="pill_top",
        show_legend=True,
    )
    _plot_manual_vs_target_line_on_ax(
        ax=axs_alt[1],
        detail=reason_stage4.dropna(subset=["human_score_0_5", "llm_reasoning_score_0_5"]),
        score_col_human="human_score_0_5",
        score_col_target="llm_reasoning_score_0_5",
        title="B. 推理质量（替换版）",
        y_label="评分 (0-5)",
        human_label="Experts",
        target_label="Automated judge",
        human_color="#5E9ECF",
        target_color="#66A57A",
        bg_colors=["#EAF6EA", "#DEECDF", "#D3E4E0", "#C6DCE2"],
        stage_order=stage4_order,
        stage_label_map=stage4_labels,
        block_labels=["D1", "D2", "D3-D4"],
        show_legend=False,
    )
    _archive_existing_output(out_combined_alt, "figures")
    _save_fig(out_combined_alt)

    # 替换版本2：左右双图 + 底部外置图例（参考用户示例）
    def _stage_mean_pair(detail_df: pd.DataFrame, target_col: str) -> tuple[np.ndarray, np.ndarray]:
        use = detail_df.copy()
        use["stage"] = use["stage"].astype(str)
        use["model_short"] = use["model_short"].astype(str)
        use = use.groupby(["stage", "model_short"], as_index=False)[["human_score_0_5", target_col]].mean()
        h_map = use.groupby("stage", as_index=False)["human_score_0_5"].mean().set_index("stage")["human_score_0_5"].to_dict()
        t_map = use.groupby("stage", as_index=False)[target_col].mean().set_index("stage")[target_col].to_dict()
        h_arr = np.array([float(h_map.get(st, np.nan)) for st in stage4_order], dtype=float)
        t_arr = np.array([float(t_map.get(st, np.nan)) for st in stage4_order], dtype=float)
        return h_arr, t_arr

    x_side = np.arange(len(stage4_order), dtype=float)
    h_result, t_result = _stage_mean_pair(
        result_stage4.dropna(subset=["human_score_0_5", "judge_score_0_5"]),
        "judge_score_0_5",
    )
    h_reason, t_reason = _stage_mean_pair(
        reason_stage4.dropna(subset=["human_score_0_5", "llm_reasoning_score_0_5"]),
        "llm_reasoning_score_0_5",
    )
    fig_side, axs_side = plt.subplots(1, 2, figsize=(14.8, 5.4), sharex=True, sharey=True)
    panel_specs = [
        (axs_side[0], h_result, t_result, "Result quality", "#1F7A4D"),
        (axs_side[1], h_reason, t_reason, "Reasoning quality", "#2B4C9B"),
    ]
    for ax, y_h, y_t, ttl, ttl_color in panel_specs:
        ax.plot(
            x_side,
            y_h,
            color="#2EA160",
            linewidth=2.5,
            marker="o",
            markersize=7.2,
            markerfacecolor="#A9DDB7",
            markeredgecolor="#2EA160",
            markeredgewidth=1.7,
            label="Experts",
            zorder=3.0,
        )
        ax.plot(
            x_side,
            y_t,
            color="#2F6FAE",
            linewidth=2.5,
            marker="o",
            markersize=7.2,
            markerfacecolor="#BCD6EF",
            markeredgecolor="#2F6FAE",
            markeredgewidth=1.7,
            label="Automated judge",
            zorder=3.0,
        )
        ax.set_xticks(x_side)
        ax.set_xticklabels(["Stage 1", "Stage 2", "Stage 3", "Stage 4"], fontsize=14)
        ax.tick_params(axis="y", labelsize=14)
        ax.set_ylim(0.0, 5.0)
        ax.yaxis.set_major_locator(MultipleLocator(1.0))
        ax.grid(alpha=0.20, axis="y", linestyle="-", linewidth=0.8)
        ax.set_title(ttl, fontsize=21, color=ttl_color, fontweight="bold", pad=8)
        _set_full_axis_border(ax)
    axs_side[0].set_ylabel("Score", fontsize=19)
    handles_side = [
        Line2D(
            [0],
            [0],
            color="#2EA160",
            linewidth=2.5,
            marker="o",
            markersize=7.0,
            markerfacecolor="#A9DDB7",
            markeredgecolor="#2EA160",
            markeredgewidth=1.6,
            label="Experts",
        ),
        Line2D(
            [0],
            [0],
            color="#2F6FAE",
            linewidth=2.5,
            marker="o",
            markersize=7.0,
            markerfacecolor="#BCD6EF",
            markeredgecolor="#2F6FAE",
            markeredgewidth=1.6,
            label="Automated judge",
        ),
    ]
    fig_side.legend(
        handles=handles_side,
        labels=[h.get_label() for h in handles_side],
        loc="lower center",
        bbox_to_anchor=(0.5, -0.015),
        ncol=2,
        frameon=True,
        fancybox=True,
        framealpha=0.96,
        edgecolor="#AEB8C3",
        fontsize=15,
        handlelength=2.0,
        columnspacing=1.6,
        borderpad=0.45,
    )
    fig_side.subplots_adjust(left=0.07, right=0.995, top=0.88, bottom=0.23, wspace=0.24)
    _archive_existing_output(out_side_by_side_alt, "figures")
    _save_fig(out_side_by_side_alt, apply_tight=False)

    # 替换版本3：左右双图柱状图（保持与折线版一致的背景与配色体系）
    fig_bar, axs_bar = plt.subplots(1, 2, figsize=(14.8, 5.4), sharex=True, sharey=True)
    bar_width = 0.34
    bar_panel_specs = [
        (
            axs_bar[0],
            h_result,
            t_result,
            "Result quality",
            "#6BA9D7",
            "#2F6FAE",
            ["#EDF5FC", "#E2EEF9", "#D4E5F3", "#C2D7E9"],
        ),
        (
            axs_bar[1],
            h_reason,
            t_reason,
            "Reasoning quality",
            "#87B58A",
            "#C6D8C0",
            ["#F2F8EF", "#E6F0E2", "#D7E6D1", "#C6D8C0"],
        ),
    ]
    for ax, y_h, y_t, ttl, human_c, judge_c, bg_colors in bar_panel_specs:
        if len(bg_colors) >= len(stage4_order):
            palette = bg_colors[: len(stage4_order)]
        else:
            palette = [_blend_hex_color(bg_colors[0], bg_colors[-1], (i + 1) / max(1, len(stage4_order))) for i in range(len(stage4_order))]
        for i, _s in enumerate(stage4_order):
            ax.axvspan(i - 0.5, i + 0.5, color=palette[i], alpha=(0.24 + 0.12 * i), zorder=0.02)
        ax.bar(
            x_side - bar_width / 2.0,
            y_h,
            width=bar_width,
            color=human_c,
            alpha=0.88,
            edgecolor="white",
            linewidth=0.9,
            label="医生",
            zorder=2.9,
        )
        ax.bar(
            x_side + bar_width / 2.0,
            y_t,
            width=bar_width,
            color=judge_c,
            alpha=0.9,
            edgecolor="white",
            linewidth=0.9,
            label="Judge",
            zorder=3.0,
        )
        ax.set_xticks(x_side)
        ax.set_xticklabels([stage4_labels.get(s, s) for s in stage4_order], fontsize=14)
        ax.tick_params(axis="y", labelsize=14)
        ax.set_ylim(0.0, 5.0)
        ax.yaxis.set_major_locator(MultipleLocator(1.0))
        ax.grid(alpha=0.20, axis="y", linestyle="-", linewidth=0.8)
        ax.set_title(ttl, fontsize=18.5, fontweight="bold", pad=8)
        _set_full_axis_border(ax)
    axs_bar[0].set_ylabel("评分 (0-5)", fontsize=18)
    handles_bar = [
        Patch(facecolor="#6BA9D7", edgecolor="white", linewidth=0.9, label="医生（结果）"),
        Patch(facecolor="#2F6FAE", edgecolor="white", linewidth=0.9, label="Judge（结果）"),
        Patch(facecolor="#87B58A", edgecolor="white", linewidth=0.9, label="医生（推理）"),
        Patch(facecolor="#C6D8C0", edgecolor="white", linewidth=0.9, label="Judge（推理）"),
    ]
    fig_bar.legend(
        handles=handles_bar,
        labels=[h.get_label() for h in handles_bar],
        loc="lower center",
        bbox_to_anchor=(0.5, -0.01),
        ncol=4,
        frameon=True,
        fancybox=True,
        framealpha=0.96,
        edgecolor="#AEB8C3",
        fontsize=13.8,
        borderpad=0.42,
        columnspacing=1.2,
        handlelength=1.8,
    )
    fig_bar.subplots_adjust(left=0.07, right=0.995, top=0.88, bottom=0.25, wspace=0.08)
    _archive_existing_output(out_side_by_side_bar_alt, "figures")
    _save_fig(out_side_by_side_bar_alt, apply_tight=False)

    s1_result4_model = (
        result_stage4.groupby(["stage", "model_short"], as_index=False)[["human_score_0_5", "judge_score_0_5"]]
        .mean()
        .sort_values(["stage", "model_short"], kind="mergesort")
        .reset_index(drop=True)
    )
    if not s1_result4_model.empty:
        rr = np.arange(2, len(s1_result4_model) + 2)
        s1_result4_model["formula_human_score_0_5"] = [
            f"=AVERAGEIFS(c_s1_result4!$G:$G,c_s1_result4!$F:$F,A{r},c_s1_result4!$E:$E,B{r})" for r in rr
        ]
        s1_result4_model["formula_judge_score_0_5"] = [
            f"=AVERAGEIFS(c_s1_result4!$H:$H,c_s1_result4!$F:$F,A{r},c_s1_result4!$E:$E,B{r})" for r in rr
        ]

    s1_reason4_model = (
        reason_stage4.groupby(["stage", "model_short"], as_index=False)[["human_score_0_5", "llm_reasoning_score_0_5"]]
        .mean()
        .sort_values(["stage", "model_short"], kind="mergesort")
        .reset_index(drop=True)
    )
    if not s1_reason4_model.empty:
        rr = np.arange(2, len(s1_reason4_model) + 2)
        s1_reason4_model["formula_human_score_0_5"] = [
            f"=AVERAGEIFS(c_s1_reason4!$G:$G,c_s1_reason4!$F:$F,A{r},c_s1_reason4!$E:$E,B{r})" for r in rr
        ]
        s1_reason4_model["formula_judge_score_0_5"] = [
            f"=AVERAGEIFS(c_s1_reason4!$H:$H,c_s1_reason4!$F:$F,A{r},c_s1_reason4!$E:$E,B{r})" for r in rr
        ]

    source_path = _write_source_workbook(
        group=group,
        stem="S1_manual_vs_llm_v6",
        sheets={
            "d_s1_result": result,
            "d_s1_reason": reason,
            "c_s1_result4": result_stage4,
            "c_s1_reason4": reason_stage4,
            "c_s1_result_check": result_check_detail,
            "c_s1_reason_check": reason_check_detail,
            "s_s1_result4_model": s1_result4_model,
            "s_s1_reason4_model": s1_reason4_model,
            "s_s1_result_model_stage": s1_result_model_stage_raw,
            "s_s1_reason_model_stage": s1_reason_model_stage_raw,
            "s_s1_result_model_stage_paper": s1_result_model_stage_paper,
            "s_s1_reason_model_stage_paper": s1_reason_model_stage_paper,
            "s_s1_result_check_stage": s1_result_check_raw,
            "s_s1_reason_check_stage": s1_reason_check_raw,
        },
        meta={
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "figures": "S1_result_quality_manual_vs_llm_v4.png; S1_reasoning_quality_manual_vs_llm_v4.png; S1_manual_vs_llm_stacked_v4.png; S1_manual_vs_llm_stacked_legend_alt_v1.png; S1_manual_vs_llm_side_by_side_bottom_legend_v1.png; S1_manual_vs_llm_side_by_side_bar_v1.png",
            "description": "S1 主图只保留 D1-D4 决策环节；D1/D2 检查环节拆至 supplementary 表。医生与Judge在主图均按 decision-only 口径对齐。",
            "judge_score_rule": "D1/D2=对应 decision 得分；D3/D4=对应决策/计划得分",
            "rule_stage_sync": "S1四阶段样本与 Sankey 对齐：D2 剔除本流程进行前已结束；D3 仅保留完成 D2 决策病例；D4 仅保留完成 D3 且未被 Gate3 剔除病例。",
            "judge_source_raw": "analysis_viz/data/raw/center_data/*/judge agent/Evaluation_Summary_<model>_CN_Judge_Parsed.xlsx",
            "source_hint__c_s1_result4": "d_s1_result 按 case 级别仅保留 D1/D2 decision，并按 Sankey 阶段可用病例过滤",
            "source_hint__c_s1_reason4": "d_s1_reason 按 case 级别仅保留 D1/D2 decision，并按 Sankey 阶段可用病例过滤",
            "source_hint__c_s1_result_check": "d_s1_result 直接过滤 D1_Loop / D2_Loop，作为 supplementary 检查环节表",
            "source_hint__c_s1_reason_check": "d_s1_reason 直接过滤 D1_Loop / D2_Loop，作为 supplementary 检查环节表",
            "formula_stage_merge": "主图 D1/D2 仅取 decision；检查环节单独列出，不再与主图阶段融合",
        },
    )
    supple_dir = OUT_SUPPLE_DIR / group
    supple_fig_dir = supple_dir / "figures"
    supple_source_dir = supple_dir / "source_data"
    supple_fig_dir.mkdir(parents=True, exist_ok=True)
    supple_source_dir.mkdir(parents=True, exist_ok=True)
    out_result_check_png = supple_fig_dir / "S1_result_check_stage_table_v1.png"
    out_reason_check_png = supple_fig_dir / "S1_reason_check_stage_table_v1.png"
    _save_table_png(s1_result_check_paper, out_result_check_png, "S1-S1 检查环节结果一致性（补充）")
    _save_table_png(s1_reason_check_paper, out_reason_check_png, "S1-S2 检查环节推理一致性（补充）")
    for p in supple_fig_dir.glob("*.png"):
        if p.name not in {out_result_check_png.name, out_reason_check_png.name}:
            try:
                p.unlink()
            except Exception:
                pass
    supple_source = supple_source_dir / "S1_check_stage_tables_supplement_v1.xlsx"
    with pd.ExcelWriter(supple_source, engine="openpyxl") as writer:
        result_check_detail.to_excel(writer, sheet_name="c_s1_result_check", index=False)
        reason_check_detail.to_excel(writer, sheet_name="c_s1_reason_check", index=False)
        s1_result_model_stage_paper.to_excel(writer, sheet_name="s1_result_model_stage", index=False)
        s1_reason_model_stage_paper.to_excel(writer, sheet_name="s1_reason_model_stage", index=False)
        s1_result_check_raw.to_excel(writer, sheet_name="s_s1_result_check_stage", index=False)
        s1_reason_check_raw.to_excel(writer, sheet_name="s_s1_reason_check_stage", index=False)
        s1_result_check_paper.to_excel(writer, sheet_name="s_s1_result_check_paper", index=False)
        s1_reason_check_paper.to_excel(writer, sheet_name="s_s1_reason_check_paper", index=False)
    _style_workbook(supple_source)
    supple_caption = _write_single_caption_file(
        supple_dir,
        "图注_Figure_S1_补充材料.md",
        [
            "# Figure S1 补充材料图注",
            "",
            "- `S1_result_check_stage_table_v1.png`：单独展示 D1 门诊检查与 D2 住院检查在“结果质量”上的医生 vs Judge 一致性。",
            "- `S1_reason_check_stage_table_v1.png`：对应展示检查环节在“逻辑质量”上的医生 vs Judge 一致性。",
            "- `S1_check_stage_tables_supplement_v1.xlsx`：除检查环节补充表外，新增 D1-D4 的“模型×环节”中文表，包含医生均分、Judge/LLM均分、MAE、Spearman 与 Kappa(QW)。",
        ],
    )
    _write_caption(
        group,
        [
            "# S1 子图图注",
            "",
            "- `S1_result_quality_manual_vs_llm_v4.png`：主图采用 D1-D4 决策阶段口径，D1/D2 只取 decision 分数；结果质量改为蓝色渐变体系，线条、误差带与背景保持同色系。",
            "- `S1_reasoning_quality_manual_vs_llm_v4.png`：逻辑质量主图与上图同口径；推理质量改为绿色渐变体系（最深背景色 `#c6d8c0`），线条、误差带与背景同色系对齐。",
            "- `S1_manual_vs_llm_stacked_v4.png`：上下联图汇总“结果质量+逻辑质量”主版本；检查环节已移入 supplementary 表。",
            "- `S1_manual_vs_llm_stacked_legend_alt_v1.png`：替换版，结果/推理均使用统一蓝绿双折线，并采用绿色→蓝色背景渐变与胶囊式图例（Experts / Automated judge）。",
            "- `S1_manual_vs_llm_side_by_side_bottom_legend_v1.png`：替换版（左右双图），左侧结果质量、右侧推理质量，统一采用底部图外 legend（Experts / Automated judge）。",
            "- `S1_manual_vs_llm_side_by_side_bar_v1.png`：柱状图替换版（左右双图），将医生/Judge由折线改为分组柱状图，背景与配色保持与对应折线版一致；图例移至图外底部单行，避免遮挡柱体。",
        ],
    )
    keep_fig = {
        out_combined.name,
        out_result.name,
        out_reason.name,
        out_combined_alt.name,
        out_side_by_side_alt.name,
        out_side_by_side_bar_alt.name,
    }
    _archive_group_outputs(group=group, keep_fig_names=keep_fig, keep_source_names={source_path.name})
    return {
        "result": out_result,
        "reason": out_reason,
        "stacked": out_combined,
        "stacked_alt": out_combined_alt,
        "side_by_side_alt": out_side_by_side_alt,
        "side_by_side_bar_alt": out_side_by_side_bar_alt,
        "source": source_path,
        "supple_result_check": out_result_check_png,
        "supple_reason_check": out_reason_check_png,
        "supple_source": supple_source,
        "supple_caption": supple_caption,
    }


def _stage4_from_stage6(stage: Any) -> str:
    s = str(stage or "").strip()
    return STAGE6_TO_STAGE4.get(s, s[:2] if s.startswith("D") else s)


def _read_excel_sheet_by_required_cols(
    path: Path,
    required_cols: set[str],
    preferred_sheets: list[str] | None = None,
) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        return pd.DataFrame(), ""
    preferred_sheets = preferred_sheets or []
    try:
        xl = pd.ExcelFile(path)
    except Exception:
        return pd.DataFrame(), ""
    candidates: list[str] = []
    for name in preferred_sheets:
        if name in xl.sheet_names:
            candidates.append(name)
    for name in xl.sheet_names:
        if name not in candidates:
            candidates.append(name)
    for sheet in candidates:
        try:
            probe = pd.read_excel(path, sheet_name=sheet, nrows=1)
        except Exception:
            continue
        if not required_cols.issubset(set(probe.columns)):
            continue
        try:
            return pd.read_excel(path, sheet_name=sheet), sheet
        except Exception:
            continue
    return pd.DataFrame(), ""


def _iter_active_doctor_workbooks() -> list[tuple[str, str, Path]]:
    out: list[tuple[str, str, Path]] = []
    if not DOCTOR_EVAL_RESULTS_DIR.exists():
        return out
    for doctor_dir in sorted(p for p in DOCTOR_EVAL_RESULTS_DIR.iterdir() if p.is_dir()):
        if doctor_dir.name.lower().startswith(("bk", "backup")):
            continue
        for xlsx in sorted(doctor_dir.glob("*.xlsx")):
            center = xlsx.stem.split("-", 1)[0].strip()
            out.append((doctor_dir.name.strip(), center, xlsx))
    return out


def _normalize_remark_text(text: Any) -> str:
    s = str(text or "").strip()
    if s == "" or s.lower() == "nan":
        return ""
    s = s.lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[，。；;、,.!?！？:：()（）\\[\\]{}<>《》\"'“”‘’]+", "", s)
    return s


def _is_semantic_repeat(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.72


def _load_doctor_remark_long() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for doctor, center_from_file, path in _iter_active_doctor_workbooks():
        cov_df, cov_sheet = _read_excel_sheet_by_required_cols(
            path=path,
            required_cols={"病例ID", "行号", "模型名称"},
            preferred_sheets=["评分覆盖率", "评分覆盖率_D2正常"],
        )
        if cov_df.empty:
            continue
        rem_df, rem_sheet = _read_excel_sheet_by_required_cols(
            path=path,
            required_cols={"行号", "模型名称"},
            preferred_sheets=["评分", "评分_D2正常"],
        )
        if "中心" not in cov_df.columns:
            cov_df["中心"] = center_from_file
        cov_df["中心"] = cov_df["中心"].fillna(center_from_file).astype(str).str.strip()
        cov_df["病例ID"] = cov_df["病例ID"].astype(str).str.strip()
        cov_df["模型名称"] = cov_df["模型名称"].astype(str).str.strip()
        cov_df["行号"] = cov_df["行号"].astype(str).str.strip()

        remark_map: dict[tuple[str, str], dict[str, str]] = {}
        if not rem_df.empty:
            rem_df["模型名称"] = rem_df["模型名称"].astype(str).str.strip()
            rem_df["行号"] = rem_df["行号"].astype(str).str.strip()
            remark_cols = [c for c in rem_df.columns if str(c).endswith("备注") or str(c).endswith("_备注")]
            for _, r in rem_df.iterrows():
                key = (str(r.get("行号", "")).strip(), str(r.get("模型名称", "")).strip())
                remark_map[key] = {}
                for col in remark_cols:
                    v = str(r.get(col, "") or "").strip()
                    remark_map[key][str(col)] = "" if v.lower() == "nan" else v

        for prefix, stage6 in DOCTOR_PREFIX_TO_STAGE6.items():
            status_col = f"{prefix}_状态"
            reason_col = f"{prefix}_推理合理性"
            result_col = f"{prefix}_结果质量评分"
            remark_cov_col = f"{prefix}_备注"
            remark_row_col = f"{prefix}备注"
            if status_col not in cov_df.columns:
                continue
            for _, r in cov_df.iterrows():
                row_no = str(r.get("行号", "")).strip()
                model = str(r.get("模型名称", "")).strip()
                rem = ""
                if remark_cov_col in cov_df.columns:
                    rem = str(r.get(remark_cov_col, "") or "").strip()
                if (rem == "" or rem.lower() == "nan") and (row_no, model) in remark_map:
                    rem = (
                        remark_map[(row_no, model)].get(remark_row_col)
                        or remark_map[(row_no, model)].get(remark_cov_col)
                        or ""
                    )
                rem = "" if str(rem).lower() == "nan" else str(rem).strip()
                rows.append(
                    {
                        "doctor": doctor,
                        "center": str(r.get("中心", center_from_file)).strip(),
                        "model": model,
                        "model_short": MODEL_SHORT.get(model, model),
                        "case_id": str(r.get("病例ID", "")).strip(),
                        "row_no": row_no,
                        "stage": stage6,
                        "stage4": _stage4_from_stage6(stage6),
                        "stage_cn": STAGE6_CN.get(stage6, stage6),
                        "status": str(r.get(status_col, "") or "").strip(),
                        "result_score_0_5": pd.to_numeric(r.get(result_col), errors="coerce"),
                        "reasoning_score_0_5": pd.to_numeric(r.get(reason_col), errors="coerce"),
                        "remark_text": rem,
                        "remark_norm": _normalize_remark_text(rem),
                        "source_file": path.as_posix(),
                        "coverage_sheet": cov_sheet,
                        "remark_sheet": rem_sheet,
                    }
                )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out[
        out["case_id"].astype(str).str.strip().ne("")
        & out["case_id"].astype(str).str.lower().ne("nan")
        & out["stage4"].isin(STAGE4_ORDER)
    ].copy()
    return out.reset_index(drop=True)


def _center_to_cn(center: Any) -> str:
    s = str(center or "").strip()
    mapping = {
        "Foshan": "佛山",
        "Wuhan": "武汉",
        "Xinjiang": "新疆",
        "foshan": "佛山",
        "wuhan": "武汉",
        "xinjiang": "新疆",
    }
    return mapping.get(s, s)


def _zh_localize_a0_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        return out

    out.columns = [str(c).replace("\n", "").strip() for c in out.columns]
    rename_map = {
        "source_table": "数据来源",
        "stage_scope": "阶段范围",
        "stage_key": "阶段编码",
        "stage_cn": "阶段名称",
        "comparator": "对比类型",
        "dimension": "评分维度",
        "n_cases": "病例数",
        "n_pairs": "配对数",
        "mae": "MAE(二值)",
        "rmse": "RMSE(二值)",
        "exact_rate": "完全一致率(0-1)",
        "within1_rate": "±1分一致率(0-1)",
        "pearson_r": "Pearson相关(二值)",
        "spearman_rho": "Spearman相关(二值)",
        "quadratic_weighted_kappa": "加权Kappa(QW,二值)",
        "corr_missing_reason": "相关系数缺失原因",
        "binary_threshold_rule": "二值映射规则",
        "center": "中心",
        "model": "模型",
        "model_short": "模型简称",
        "case_id": "病例ID",
        "doctor": "医生",
        "doctor_a": "医生A",
        "doctor_b": "医生B",
        "stage": "原始环节",
        "human_score_0_5": "医生评分(0-5)",
        "judge_score_0_5": "Judge评分(0-5)",
        "llm_reasoning_score_0_5": "LLM推理评分(0-5)",
        "doctor_score_0_5_a": "医生A评分(0-5)",
        "doctor_score_0_5_b": "医生B评分(0-5)",
        "human_bin": "医生二值标签",
        "judge_bin": "Judge二值标签",
        "llm_bin": "LLM二值标签",
        "doctor_a_bin": "医生A二值标签",
        "doctor_b_bin": "医生B二值标签",
        "human_clinical_label": "医生临床标签",
        "judge_clinical_label": "Judge临床标签",
        "llm_clinical_label": "LLM临床标签",
        "doctor_a_clinical_label": "医生A临床标签",
        "doctor_b_clinical_label": "医生B临床标签",
        "binary_match": "二值是否一致",
        "binary_pair_type": "二值配对类型",
        "binary_rule": "二值规则说明",
    }
    out = out.rename(columns={k: v for k, v in rename_map.items() if k in out.columns})

    if "中心" in out.columns:
        out["中心"] = out["中心"].map(_center_to_cn)
    if "阶段范围" in out.columns:
        out["阶段范围"] = out["阶段范围"].map({"decision": "决策环节", "check": "检查环节"}).fillna(out["阶段范围"])
    if "对比类型" in out.columns:
        out["对比类型"] = out["对比类型"].map(
            {
                "human_vs_judge": "人机(医生 vs Judge)",
                "doctor_vs_doctor": "人人(医生A vs 医生B)",
            }
        ).fillna(out["对比类型"])
    if "评分维度" in out.columns:
        out["评分维度"] = out["评分维度"].map({"result": "结果评分", "reasoning": "推理评分"}).fillna(out["评分维度"])

    label_cols = [
        "医生临床标签",
        "Judge临床标签",
        "LLM临床标签",
        "医生A临床标签",
        "医生B临床标签",
    ]
    for col in label_cols:
        if col in out.columns:
            out[col] = out[col].map(
                {"significant": "临床显著", "non-significant": "临床不显著"}
            ).fillna(out[col])

    if "二值是否一致" in out.columns:
        out["二值是否一致"] = out["二值是否一致"].map({True: "一致", False: "不一致"}).fillna(out["二值是否一致"])
    if "二值配对类型" in out.columns:
        out["二值配对类型"] = out["二值配对类型"].map(
            {
                "TP": "TP(同为显著)",
                "TN": "TN(同为不显著)",
                "FP": "FP(医生不显著/Judge显著)",
                "FN": "FN(医生显著/Judge不显著)",
            }
        ).fillna(out["二值配对类型"])

    for col in ["二值映射规则", "二值规则说明"]:
        if col in out.columns:
            out[col] = out[col].astype(str).str.replace(
                "0-2=non-significant;3-5=significant",
                "0-2=临床不显著；3-5=临床显著",
                regex=False,
            )

    return out


def _spearman_rho(x: pd.Series, y: pd.Series) -> float:
    xs = pd.to_numeric(x, errors="coerce")
    ys = pd.to_numeric(y, errors="coerce")
    valid = xs.notna() & ys.notna()
    xs = xs[valid]
    ys = ys[valid]
    if len(xs) < 2 or xs.nunique(dropna=True) < 2 or ys.nunique(dropna=True) < 2:
        return float("nan")
    return float(xs.corr(ys, method="spearman"))


def _pearson_r(x: pd.Series, y: pd.Series) -> float:
    xs = pd.to_numeric(x, errors="coerce")
    ys = pd.to_numeric(y, errors="coerce")
    valid = xs.notna() & ys.notna()
    xs = xs[valid]
    ys = ys[valid]
    if len(xs) < 2 or xs.nunique(dropna=True) < 2 or ys.nunique(dropna=True) < 2:
        return float("nan")
    return float(xs.corr(ys, method="pearson"))


def _corr_missing_reason(x: pd.Series, y: pd.Series) -> str:
    xs = pd.to_numeric(x, errors="coerce")
    ys = pd.to_numeric(y, errors="coerce")
    valid = xs.notna() & ys.notna()
    xs = xs[valid]
    ys = ys[valid]
    if len(xs) < 2:
        return "样本不足(<2)"
    x_var = xs.nunique(dropna=True)
    y_var = ys.nunique(dropna=True)
    if x_var < 2 and y_var < 2:
        return "两端标签无方差(常量)"
    if x_var < 2:
        return "医生/左侧标签无方差(常量)"
    if y_var < 2:
        return "Judge/右侧标签无方差(常量)"
    return ""


def _quadratic_weighted_kappa(x: pd.Series, y: pd.Series, *, step: float = 0.5, max_score: float = 5.0) -> float:
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


def _binary_label_0_5(series: pd.Series, *, threshold: float = 3.0) -> pd.Series:
    vals = pd.to_numeric(series, errors="coerce")
    out = pd.Series(np.where(vals >= threshold, 1.0, 0.0), index=vals.index, dtype=float)
    out[vals.isna()] = np.nan
    return out


def _agreement_metrics_bundle(x: pd.Series, y: pd.Series) -> dict[str, Any]:
    xs = pd.to_numeric(x, errors="coerce")
    ys = pd.to_numeric(y, errors="coerce")
    valid = xs.notna() & ys.notna()
    xs = xs[valid]
    ys = ys[valid]
    if xs.empty:
        return {
            "n_pairs": 0,
            "mae": np.nan,
            "rmse": np.nan,
            "exact_rate": np.nan,
            "within1_rate": np.nan,
            "pearson_r": np.nan,
            "spearman_rho": np.nan,
            "quadratic_weighted_kappa": np.nan,
            "corr_missing_reason": "样本不足(<2)",
            "binary_threshold_rule": "0-2=non-significant;3-5=significant",
        }

    xb = _binary_label_0_5(xs)
    yb = _binary_label_0_5(ys)
    abs_diff = (xb - yb).abs()
    n = int(len(xb))
    return {
        "n_pairs": n,
        "mae": float(abs_diff.mean()),
        "rmse": float(np.sqrt(((xb - yb) ** 2).mean())),
        "exact_rate": float((abs_diff == 0).mean()),
        "within1_rate": float((abs_diff <= 1).mean()),
        "pearson_r": _pearson_r(xb, yb),
        "spearman_rho": _spearman_rho(xb, yb),
        "quadratic_weighted_kappa": _quadratic_weighted_kappa(xb, yb),
        "corr_missing_reason": _corr_missing_reason(xb, yb),
        "binary_threshold_rule": "0-2=non-significant;3-5=significant",
    }


def _build_human_machine_compact_table(
    result_detail: pd.DataFrame,
    reason_detail: pd.DataFrame,
    stage_group_map: dict[str, str],
    stage_order: list[str],
    stage_label_map: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    def _agg(detail: pd.DataFrame, target_col: str) -> pd.DataFrame:
        use = detail.copy()
        use["stage_key"] = use["stage"].map(stage_group_map)
        use["human_score_0_5"] = pd.to_numeric(use["human_score_0_5"], errors="coerce")
        use[target_col] = pd.to_numeric(use[target_col], errors="coerce")
        use = use[use["stage_key"].astype(str).isin(stage_order)].copy()
        use = use[use["human_score_0_5"].notna() & use[target_col].notna()].copy()
        if use.empty:
            return pd.DataFrame(
                columns=[
                    "stage_key",
                    "n_cases",
                    "mae",
                    "rmse",
                    "exact_rate",
                    "within1_rate",
                    "pearson_r",
                    "spearman_rho",
                    "quadratic_weighted_kappa",
                    "corr_missing_reason",
                    "binary_threshold_rule",
                ]
            )
        rows: list[dict[str, Any]] = []
        for stage_key, sub in use.groupby("stage_key", dropna=False):
            metrics = _agreement_metrics_bundle(sub["human_score_0_5"], sub[target_col])
            rows.append({"stage_key": stage_key, "n_cases": int(metrics["n_pairs"]), **metrics})
        return pd.DataFrame(rows)

    res = _agg(result_detail, "judge_score_0_5").add_suffix("_result").rename(columns={"stage_key_result": "stage_key"})
    rea = _agg(reason_detail, "llm_reasoning_score_0_5").add_suffix("_reason").rename(columns={"stage_key_reason": "stage_key"})
    grid = pd.DataFrame({"stage_key": stage_order})
    merged = grid.merge(res, on=["stage_key"], how="left").merge(rea, on=["stage_key"], how="left")
    merged = merged.rename(
        columns={
            "n_cases_result": "n_result",
            "n_cases_reason": "n_reason",
            "exact_rate_result": "exact_result",
            "within1_rate_result": "within1_result",
            "exact_rate_reason": "exact_reason",
            "within1_rate_reason": "within1_reason",
            "pearson_r_result": "pearson_result",
            "pearson_r_reason": "pearson_reason",
        }
    )
    merged["stage_cn"] = merged["stage_key"].map(stage_label_map).fillna(merged["stage_key"])
    paper = merged[
        [
            "stage_cn",
            "n_result",
            "mae_result",
            "exact_result",
            "within1_result",
            "pearson_result",
            "spearman_rho_result",
            "quadratic_weighted_kappa_result",
            "corr_missing_reason_result",
            "n_reason",
            "mae_reason",
            "exact_reason",
            "within1_reason",
            "pearson_reason",
            "spearman_rho_reason",
            "quadratic_weighted_kappa_reason",
            "corr_missing_reason_reason",
        ]
    ].copy()
    paper = paper.rename(
        columns={
            "stage_cn": "环节",
            "n_result": "样本量\n(结果)",
            "mae_result": "MAE\n(结果)",
            "exact_result": "完全一致率\n(结果)",
            "within1_result": "±1分一致率\n(结果)",
            "pearson_result": "Pearson\n(结果)",
            "spearman_rho_result": "Spearman\n(结果)",
            "quadratic_weighted_kappa_result": "Kappa(QW)\n(结果)",
            "corr_missing_reason_result": "相关系数缺失原因\n(结果)",
            "n_reason": "样本量\n(推理)",
            "mae_reason": "MAE\n(推理)",
            "exact_reason": "完全一致率\n(推理)",
            "within1_reason": "±1分一致率\n(推理)",
            "pearson_reason": "Pearson\n(推理)",
            "spearman_rho_reason": "Spearman\n(推理)",
            "quadratic_weighted_kappa_reason": "Kappa(QW)\n(推理)",
            "corr_missing_reason_reason": "相关系数缺失原因\n(推理)",
        }
    )
    for col in ["MAE\n(结果)", "MAE\n(推理)"]:
        paper[col] = pd.to_numeric(paper[col], errors="coerce").round(3)
    for col in ["完全一致率\n(结果)", "±1分一致率\n(结果)", "完全一致率\n(推理)", "±1分一致率\n(推理)"]:
        paper[col] = (pd.to_numeric(paper[col], errors="coerce") * 100.0).round(1)
    for col in [
        "Pearson\n(结果)",
        "Spearman\n(结果)",
        "Kappa(QW)\n(结果)",
        "Pearson\n(推理)",
        "Spearman\n(推理)",
        "Kappa(QW)\n(推理)",
    ]:
        paper[col] = pd.to_numeric(paper[col], errors="coerce").round(3)
    return merged, paper


def _build_doctor_doctor_compact_table(
    cons_result_pair: pd.DataFrame,
    cons_reason_pair: pd.DataFrame,
    stage_group_map: dict[str, str],
    stage_order: list[str],
    stage_label_map: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    def _agg(pair_df: pd.DataFrame) -> pd.DataFrame:
        use = pair_df.copy()
        use["stage_key"] = use["stage"].map(stage_group_map)
        use = use[use["stage_key"].astype(str).isin(stage_order)].copy()
        if use.empty:
            return pd.DataFrame(
                columns=[
                    "stage_key",
                    "n_pairs",
                    "mae",
                    "rmse",
                    "exact_rate",
                    "within1_rate",
                    "pearson_r",
                    "spearman_rho",
                    "quadratic_weighted_kappa",
                    "corr_missing_reason",
                    "binary_threshold_rule",
                ]
            )
        rows: list[dict[str, Any]] = []
        for stage_key, sub in use.groupby("stage_key", dropna=False):
            metrics = _agreement_metrics_bundle(sub["doctor_score_0_5_a"], sub["doctor_score_0_5_b"])
            rows.append({"stage_key": stage_key, "n_pairs": int(metrics["n_pairs"]), **metrics})
        return pd.DataFrame(rows)

    res = _agg(cons_result_pair).add_suffix("_result").rename(columns={"stage_key_result": "stage_key"})
    rea = _agg(cons_reason_pair).add_suffix("_reason").rename(columns={"stage_key_reason": "stage_key"})
    grid = pd.DataFrame({"stage_key": stage_order})
    merged = grid.merge(res, on=["stage_key"], how="left").merge(rea, on=["stage_key"], how="left")
    merged = merged.rename(
        columns={
            "n_pairs_result": "n_result",
            "n_pairs_reason": "n_reason",
            "exact_rate_result": "exact_result",
            "within1_rate_result": "within1_result",
            "exact_rate_reason": "exact_reason",
            "within1_rate_reason": "within1_reason",
            "pearson_r_result": "pearson_result",
            "pearson_r_reason": "pearson_reason",
        }
    )
    merged["stage_cn"] = merged["stage_key"].map(stage_label_map).fillna(merged["stage_key"])
    paper = merged[
        [
            "stage_cn",
            "n_result",
            "mae_result",
            "exact_result",
            "within1_result",
            "pearson_result",
            "spearman_rho_result",
            "quadratic_weighted_kappa_result",
            "corr_missing_reason_result",
            "n_reason",
            "mae_reason",
            "exact_reason",
            "within1_reason",
            "pearson_reason",
            "spearman_rho_reason",
            "quadratic_weighted_kappa_reason",
            "corr_missing_reason_reason",
        ]
    ].copy()
    paper = paper.rename(
        columns={
            "stage_cn": "环节",
            "n_result": "样本对\n(结果)",
            "mae_result": "平均绝对差\n(结果)",
            "exact_result": "完全一致率\n(结果)",
            "within1_result": "±1分一致率\n(结果)",
            "pearson_result": "Pearson\n(结果)",
            "spearman_rho_result": "Spearman\n(结果)",
            "quadratic_weighted_kappa_result": "Kappa(QW)\n(结果)",
            "corr_missing_reason_result": "相关系数缺失原因\n(结果)",
            "n_reason": "样本对\n(推理)",
            "mae_reason": "平均绝对差\n(推理)",
            "exact_reason": "完全一致率\n(推理)",
            "within1_reason": "±1分一致率\n(推理)",
            "pearson_reason": "Pearson\n(推理)",
            "spearman_rho_reason": "Spearman\n(推理)",
            "quadratic_weighted_kappa_reason": "Kappa(QW)\n(推理)",
            "corr_missing_reason_reason": "相关系数缺失原因\n(推理)",
        }
    )
    for col in ["平均绝对差\n(结果)", "平均绝对差\n(推理)"]:
        paper[col] = pd.to_numeric(paper[col], errors="coerce").round(3)
    for col in ["完全一致率\n(结果)", "±1分一致率\n(结果)", "完全一致率\n(推理)", "±1分一致率\n(推理)"]:
        paper[col] = (pd.to_numeric(paper[col], errors="coerce") * 100.0).round(1)
    for col in [
        "Pearson\n(结果)",
        "Spearman\n(结果)",
        "Kappa(QW)\n(结果)",
        "Pearson\n(推理)",
        "Spearman\n(推理)",
        "Kappa(QW)\n(推理)",
    ]:
        paper[col] = pd.to_numeric(paper[col], errors="coerce").round(3)
    return merged, paper


def _build_stage_metric_suite(
    detail_df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    stage_group_map: dict[str, str],
    stage_order: list[str],
    stage_label_map: dict[str, str],
    comparator: str,
    dimension: str,
) -> pd.DataFrame:
    use = detail_df.copy()
    use["stage_key"] = use["stage"].map(stage_group_map)
    use[x_col] = pd.to_numeric(use[x_col], errors="coerce")
    use[y_col] = pd.to_numeric(use[y_col], errors="coerce")
    use = use[use["stage_key"].astype(str).isin(stage_order)].copy()
    use = use[use[x_col].notna() & use[y_col].notna()].copy()
    rows: list[dict[str, Any]] = []
    for stage_key in stage_order:
        sub = use[use["stage_key"] == stage_key].copy()
        if sub.empty:
            metrics = _agreement_metrics_bundle(pd.Series(dtype=float), pd.Series(dtype=float))
            n_cases = 0
        else:
            metrics = _agreement_metrics_bundle(sub[x_col], sub[y_col])
            n_cases = int(sub["case_id"].nunique()) if "case_id" in sub.columns else int(metrics["n_pairs"])
        rows.append(
            {
                "stage_key": stage_key,
                "stage_cn": stage_label_map.get(stage_key, stage_key),
                "comparator": comparator,
                "dimension": dimension,
                "n_cases": n_cases,
                **metrics,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    order_map = {s: i for i, s in enumerate(stage_order)}
    out["stage_order"] = out["stage_key"].map(order_map)
    return out.sort_values(["stage_order"], kind="mergesort").drop(columns=["stage_order"]).reset_index(drop=True)


def _build_stage_binary_detail(
    detail_df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    x_name: str,
    y_name: str,
    stage_group_map: dict[str, str],
    stage_order: list[str],
    stage_label_map: dict[str, str],
) -> pd.DataFrame:
    use = detail_df.copy()
    use["stage_key"] = use["stage"].map(stage_group_map)
    use = use[use["stage_key"].astype(str).isin(stage_order)].copy()
    use[x_col] = pd.to_numeric(use[x_col], errors="coerce")
    use[y_col] = pd.to_numeric(use[y_col], errors="coerce")
    use = use[use[x_col].notna() & use[y_col].notna()].copy()
    if use.empty:
        return pd.DataFrame()
    use["stage_cn"] = use["stage_key"].map(stage_label_map).fillna(use["stage_key"])
    use[f"{x_name}_bin"] = _binary_label_0_5(use[x_col])
    use[f"{y_name}_bin"] = _binary_label_0_5(use[y_col])
    use[f"{x_name}_clinical_label"] = np.where(use[f"{x_name}_bin"] >= 1, "significant", "non-significant")
    use[f"{y_name}_clinical_label"] = np.where(use[f"{y_name}_bin"] >= 1, "significant", "non-significant")
    use["binary_match"] = use[f"{x_name}_bin"] == use[f"{y_name}_bin"]
    use["binary_pair_type"] = np.select(
        [
            (use[f"{x_name}_bin"] == 1) & (use[f"{y_name}_bin"] == 1),
            (use[f"{x_name}_bin"] == 0) & (use[f"{y_name}_bin"] == 0),
            (use[f"{x_name}_bin"] == 0) & (use[f"{y_name}_bin"] == 1),
            (use[f"{x_name}_bin"] == 1) & (use[f"{y_name}_bin"] == 0),
        ],
        ["TP", "TN", "FP", "FN"],
        default="NA",
    )
    use["binary_rule"] = "0-2=non-significant;3-5=significant"
    keep_cols = [
        "center",
        "model",
        "model_short",
        "case_id",
        "doctor",
        "doctor_a",
        "doctor_b",
        "stage",
        "stage_key",
        "stage_cn",
        x_col,
        y_col,
        f"{x_name}_bin",
        f"{y_name}_bin",
        f"{x_name}_clinical_label",
        f"{y_name}_clinical_label",
        "binary_match",
        "binary_pair_type",
        "binary_rule",
    ]
    existing_cols = [c for c in keep_cols if c in use.columns]
    return use[existing_cols].copy()


def _save_table_png(df: pd.DataFrame, out_path: Path, title: str) -> None:
    show = df.copy()
    for col in show.columns:
        if "一致率" in str(col):
            show[col] = show[col].map(lambda v: "" if pd.isna(v) else f"{float(v):.1f}%")
        elif "比例" in str(col):
            show[col] = show[col].map(
                lambda v: "" if pd.isna(v) else (f"{float(v):.1f}%" if abs(float(v)) > 1.0 else f"{float(v) * 100.0:.1f}%")
            )
        elif "MAE" in str(col) or "平均绝对差" in str(col):
            show[col] = show[col].map(lambda v: "" if pd.isna(v) else f"{float(v):.3f}")
        elif any(token in str(col) for token in ["增益", "增量", "标准差", "均分", "Pearson", "Spearman", "Kappa", "置信度", "准确率", "校准差值"]):
            show[col] = show[col].map(lambda v: "" if pd.isna(v) else f"{float(v):.3f}")
        elif "样本" in str(col):
            show[col] = show[col].map(lambda v: "" if pd.isna(v) else f"{int(float(v))}")
    n_rows, n_cols = max(1, len(show)), max(1, len(show.columns))
    fig_w = max(12.5, n_cols * 1.65)
    fig_h = max(4.6, n_rows * 0.46 + 1.7)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")
    tab = ax.table(
        cellText=show.fillna("").values.tolist(),
        colLabels=show.columns.tolist(),
        cellLoc="center",
        colLoc="center",
        loc="center",
    )
    tab.auto_set_font_size(False)
    tab.set_fontsize(9.2)
    tab.scale(1.0, 1.26)
    for (r, c), cell in tab.get_celld().items():
        if r == 0:
            cell.set_facecolor("#DCE8F6")
            cell.set_text_props(weight="bold", color="#1F2D3D")
        elif r % 2 == 1:
            cell.set_facecolor("#F7FAFF")
        cell.set_edgecolor("#9AB2CC")
        cell.set_linewidth(0.6)
    ax.set_title(title, fontsize=13.5, pad=12, fontweight="bold")
    _save_fig(out_path, apply_tight=False)


def _format_docx_table_value(col_name: str, value: Any) -> str:
    if pd.isna(value):
        return ""
    name = str(col_name)
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        fv = float(value)
        if any(token in name for token in ["样本", "数量", "行数", "例数"]):
            return f"{int(round(fv))}"
        if any(token in name for token in ["概率", "率", "均分", "指数", "得分", "继承", "利用", "丢失", "一致", "风险", "比例"]):
            return f"{fv:.3f}"
        if float(fv).is_integer():
            return f"{int(fv)}"
        return f"{fv:.3f}"
    return str(value)


def _save_docx_tables(
    out_path: Path,
    doc_title: str,
    sections: list[dict[str, Any]],
    intro_lines: list[str] | None = None,
) -> None:
    if Document is None:
        raise RuntimeError("python-docx 未安装，无法导出 Word 表格。")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.add_heading(doc_title, level=1)
    doc.add_paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if intro_lines:
        for line in intro_lines:
            if str(line).strip():
                doc.add_paragraph(str(line).strip())
    for sec in sections:
        sec_title = str(sec.get("title", "")).strip()
        sec_note = str(sec.get("note", "")).strip()
        sec_df = sec.get("df")
        df = sec_df.copy() if isinstance(sec_df, pd.DataFrame) else pd.DataFrame()
        if sec_title:
            doc.add_heading(sec_title, level=2)
        if sec_note:
            doc.add_paragraph(sec_note)
        if df.empty:
            doc.add_paragraph("（无数据）")
            continue
        table = doc.add_table(rows=1, cols=len(df.columns))
        try:
            table.style = "Table Grid"
        except Exception:
            pass
        header_cells = table.rows[0].cells
        for j, col in enumerate(df.columns):
            header_cells[j].text = str(col)
        for row in df.itertuples(index=False, name=None):
            cells = table.add_row().cells
            for j, (col, val) in enumerate(zip(df.columns, row)):
                cells[j].text = _format_docx_table_value(str(col), val)
        doc.add_paragraph("")
    doc.save(out_path)


def _build_manual_target_stage_table(
    detail_df: pd.DataFrame,
    target_col: str,
    stage_group_map: dict[str, str],
    stage_order: list[str],
    stage_label_map: dict[str, str],
    target_label: str = "Judge均分",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    use = detail_df.copy()
    use["stage_key"] = use["stage"].map(stage_group_map)
    use["human_score_0_5"] = pd.to_numeric(use["human_score_0_5"], errors="coerce")
    use[target_col] = pd.to_numeric(use[target_col], errors="coerce")
    use = use[use["stage_key"].astype(str).isin(stage_order)].copy()
    use = use[use["human_score_0_5"].notna() & use[target_col].notna()].copy()
    if use.empty:
        raw = pd.DataFrame(
            columns=[
                "stage_key",
                "n_samples",
                "human_mean",
                "target_mean",
                "mae",
                "exact_rate",
                "within1_rate",
                "pearson_r",
                "spearman_rho",
                "quadratic_weighted_kappa",
            ]
        )
    else:
        use["abs_diff"] = (use["human_score_0_5"] - use[target_col]).abs()
        rows: list[dict[str, Any]] = []
        for stage_key, sub in use.groupby("stage_key", dropna=False):
            rows.append(
                {
                    "stage_key": stage_key,
                    "n_samples": int(sub["case_id"].count()),
                    "human_mean": float(pd.to_numeric(sub["human_score_0_5"], errors="coerce").mean()),
                    "target_mean": float(pd.to_numeric(sub[target_col], errors="coerce").mean()),
                    "mae": float(pd.to_numeric(sub["abs_diff"], errors="coerce").mean()),
                    "exact_rate": float((pd.to_numeric(sub["abs_diff"], errors="coerce") == 0).mean()),
                    "within1_rate": float((pd.to_numeric(sub["abs_diff"], errors="coerce") <= 1).mean()),
                    "pearson_r": _pearson_r(sub["human_score_0_5"], sub[target_col]),
                    "spearman_rho": _spearman_rho(sub["human_score_0_5"], sub[target_col]),
                    "quadratic_weighted_kappa": _quadratic_weighted_kappa(sub["human_score_0_5"], sub[target_col]),
                }
            )
        raw = pd.DataFrame(rows)
    paper = pd.DataFrame({"stage_key": stage_order}).merge(raw, on="stage_key", how="left")
    paper["环节"] = paper["stage_key"].map(stage_label_map).fillna(paper["stage_key"])
    paper = paper.rename(
        columns={
            "n_samples": "样本量",
            "human_mean": "医生均分",
            "target_mean": target_label,
            "mae": "MAE",
            "exact_rate": "完全一致率",
            "within1_rate": "±1分一致率",
            "pearson_r": "Pearson",
            "spearman_rho": "Spearman",
            "quadratic_weighted_kappa": "Kappa(QW)",
        }
    )[
        ["环节", "样本量", "医生均分", target_label, "MAE", "完全一致率", "±1分一致率", "Pearson", "Spearman", "Kappa(QW)"]
    ].copy()
    for col in ["医生均分", target_label, "MAE"]:
        paper[col] = pd.to_numeric(paper[col], errors="coerce").round(3)
    for col in ["完全一致率", "±1分一致率"]:
        paper[col] = (pd.to_numeric(paper[col], errors="coerce") * 100.0).round(1)
    for col in ["Pearson", "Spearman", "Kappa(QW)"]:
        paper[col] = pd.to_numeric(paper[col], errors="coerce").round(3)
    return raw, paper


def _build_manual_target_model_stage_table(
    detail_df: pd.DataFrame,
    target_col: str,
    stage_group_map: dict[str, str],
    stage_order: list[str],
    stage_label_map: dict[str, str],
    target_label: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    use = detail_df.copy()
    use["stage_key"] = use["stage"].map(stage_group_map)
    use["human_score_0_5"] = pd.to_numeric(use["human_score_0_5"], errors="coerce")
    use[target_col] = pd.to_numeric(use[target_col], errors="coerce")
    use["model_short"] = use["model_short"].astype(str)
    use = use[use["stage_key"].astype(str).isin(stage_order)].copy()
    use = use[use["human_score_0_5"].notna() & use[target_col].notna()].copy()
    if use.empty:
        raw = pd.DataFrame(
            columns=[
                "stage_key",
                "model_short",
                "n_samples",
                "human_mean",
                "target_mean",
                "delta_mean",
                "mae",
                "pearson_r",
                "spearman_rho",
                "quadratic_weighted_kappa",
            ]
        )
    else:
        use["abs_diff"] = (use["human_score_0_5"] - use[target_col]).abs()
        use["delta"] = pd.to_numeric(use[target_col], errors="coerce") - pd.to_numeric(use["human_score_0_5"], errors="coerce")
        rows: list[dict[str, Any]] = []
        for (stage_key, model_short), sub in use.groupby(["stage_key", "model_short"], dropna=False):
            rows.append(
                {
                    "stage_key": stage_key,
                    "model_short": model_short,
                    "n_samples": int(sub["case_id"].count()),
                    "human_mean": float(pd.to_numeric(sub["human_score_0_5"], errors="coerce").mean()),
                    "target_mean": float(pd.to_numeric(sub[target_col], errors="coerce").mean()),
                    "delta_mean": float(pd.to_numeric(sub["delta"], errors="coerce").mean()),
                    "mae": float(pd.to_numeric(sub["abs_diff"], errors="coerce").mean()),
                    "pearson_r": _pearson_r(sub["human_score_0_5"], sub[target_col]),
                    "spearman_rho": _spearman_rho(sub["human_score_0_5"], sub[target_col]),
                    "quadratic_weighted_kappa": _quadratic_weighted_kappa(sub["human_score_0_5"], sub[target_col]),
                }
            )
        raw = pd.DataFrame(rows)
    grid = pd.MultiIndex.from_product([stage_order, MODEL_ORDER], names=["stage_key", "model_short"]).to_frame(index=False)
    paper = grid.merge(raw, on=["stage_key", "model_short"], how="left")
    paper["环节"] = paper["stage_key"].map(stage_label_map).fillna(paper["stage_key"])
    paper["模型"] = paper["model_short"]
    paper = paper.rename(
        columns={
            "n_samples": "样本量",
            "human_mean": "医生均分",
            "target_mean": target_label,
            "delta_mean": "均值差",
            "mae": "MAE",
            "pearson_r": "Pearson",
            "spearman_rho": "Spearman",
            "quadratic_weighted_kappa": "Kappa(QW)",
        }
    )[["环节", "模型", "样本量", "医生均分", target_label, "均值差", "MAE", "Pearson", "Spearman", "Kappa(QW)"]].copy()
    for col in ["医生均分", target_label, "均值差", "MAE", "Pearson", "Spearman", "Kappa(QW)"]:
        paper[col] = pd.to_numeric(paper[col], errors="coerce").round(3)
    return raw, paper


def _build_doctor_doctor_model_stage_table(
    pair_df: pd.DataFrame,
    stage_group_map: dict[str, str],
    stage_order: list[str],
    stage_label_map: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    use = pair_df.copy()
    use["stage_key"] = use["stage"].map(stage_group_map)
    use["model_short"] = use["model_short"].astype(str)
    use = use[use["stage_key"].astype(str).isin(stage_order)].copy()
    if use.empty:
        raw = pd.DataFrame(
            columns=[
                "stage_key",
                "model_short",
                "n_pairs",
                "abs_diff_mean",
                "exact_match_rate",
                "within_1pt_rate",
                "pearson_r",
                "spearman_rho",
                "quadratic_weighted_kappa",
            ]
        )
    else:
        use["abs_diff"] = pd.to_numeric(use["abs_diff"], errors="coerce")
        use["is_exact_match"] = pd.to_numeric(use["is_exact_match"], errors="coerce")
        use["is_within_1pt"] = pd.to_numeric(use["is_within_1pt"], errors="coerce")
        rows: list[dict[str, Any]] = []
        for (stage_key, model_short), sub in use.groupby(["stage_key", "model_short"], dropna=False):
            rows.append(
                {
                    "stage_key": stage_key,
                    "model_short": model_short,
                    "n_pairs": int(sub["case_id"].count()),
                    "abs_diff_mean": float(pd.to_numeric(sub["abs_diff"], errors="coerce").mean()),
                    "exact_match_rate": float(pd.to_numeric(sub["is_exact_match"], errors="coerce").mean()),
                    "within_1pt_rate": float(pd.to_numeric(sub["is_within_1pt"], errors="coerce").mean()),
                    "pearson_r": _pearson_r(sub["doctor_score_0_5_a"], sub["doctor_score_0_5_b"]),
                    "spearman_rho": _spearman_rho(sub["doctor_score_0_5_a"], sub["doctor_score_0_5_b"]),
                    "quadratic_weighted_kappa": _quadratic_weighted_kappa(sub["doctor_score_0_5_a"], sub["doctor_score_0_5_b"]),
                }
            )
        raw = pd.DataFrame(rows)
    grid = pd.MultiIndex.from_product([stage_order, MODEL_ORDER], names=["stage_key", "model_short"]).to_frame(index=False)
    paper = grid.merge(raw, on=["stage_key", "model_short"], how="left")
    paper["环节"] = paper["stage_key"].map(stage_label_map).fillna(paper["stage_key"])
    paper["模型"] = paper["model_short"]
    paper = paper.rename(
        columns={
            "n_pairs": "样本对",
            "abs_diff_mean": "平均绝对差",
            "exact_match_rate": "完全一致率",
            "within_1pt_rate": "±1分一致率",
            "pearson_r": "Pearson",
            "spearman_rho": "Spearman",
            "quadratic_weighted_kappa": "Kappa(QW)",
        }
    )[["环节", "模型", "样本对", "平均绝对差", "完全一致率", "±1分一致率", "Pearson", "Spearman", "Kappa(QW)"]].copy()
    paper["平均绝对差"] = pd.to_numeric(paper["平均绝对差"], errors="coerce").round(3)
    for col in ["完全一致率", "±1分一致率"]:
        paper[col] = (pd.to_numeric(paper[col], errors="coerce") * 100.0).round(1)
    for col in ["Pearson", "Spearman", "Kappa(QW)"]:
        paper[col] = pd.to_numeric(paper[col], errors="coerce").round(3)
    return raw, paper


def _parse_trace_output_cards(html_text: str) -> list[tuple[str, str]]:
    if not html_text:
        return []
    cards: list[tuple[str, str]] = []
    if BeautifulSoup is None:
        return cards
    soup = BeautifulSoup(html_text, "html.parser")
    for card in soup.select("div.log-card"):
        title_el = card.select_one("span.header-title")
        body = card.select_one("div.card-body")
        if title_el is None or body is None:
            continue
        title = title_el.get_text(" ", strip=True)
        output_block = None
        for pre in body.select("div.pre-wrap"):
            output_block = pre
            break
        if output_block is not None:
            txt = output_block.get_text("\n", strip=True)
        else:
            table = body.select_one("table.json-table")
            if table is not None:
                txt = table.get_text("\n", strip=True)
            else:
                txt = body.get_text("\n", strip=True)
        txt = html_unescape(re.sub(r"\n{3,}", "\n\n", txt)).strip()
        if not txt:
            continue
        cards.append((title, txt))
    return cards


def _iter_trace_output_roots() -> list[Path]:
    roots: list[Path] = []
    probe_centers = ["Foshan-v2", "Wuhan_Fixed-v2", "Xinjiang-v2", "Foshan", "Wuhan", "Xinjiang"]
    for base in [ROOT.parent, ROOT]:
        if not base.exists():
            continue
        direct = base / "output"
        if direct.exists() and any((direct / name).exists() for name in probe_centers):
            roots.append(direct)
        for child in sorted(p for p in base.iterdir() if p.is_dir()):
            cand = child / "output"
            if cand.exists() and any((cand / name).exists() for name in probe_centers):
                roots.append(cand)
    uniq: list[Path] = []
    seen: set[str] = set()
    for p in roots:
        key = p.resolve().as_posix() if p.exists() else p.as_posix()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def _resolve_trace_html_path(center_cn: str, model: str, case_id: str) -> Path | None:
    trace_root_candidates = _iter_trace_output_roots()
    center_dir_map = {
        "佛山": ["Foshan-v2", "Foshan"],
        "武汉": ["Wuhan_Fixed-v2", "Wuhan_fixed", "Wuhan"],
        "新疆": ["Xinjiang-v2", "Xinjiang"],
    }
    for trace_root in trace_root_candidates:
        if not trace_root.exists():
            continue
        for center_dir in center_dir_map.get(center_cn, []):
            trace_dir = trace_root / center_dir / str(model) / "html_traces"
            if not trace_dir.exists():
                continue
            exact = sorted(trace_dir.glob(f"*_{case_id}_trace.html"))
            if exact:
                return exact[0]
            fuzzy = sorted(trace_dir.glob(f"*{case_id}*trace.html"))
            if fuzzy:
                return fuzzy[0]
    return None


def _trace_title_group(title: str) -> str:
    t = str(title or "")
    if t == "Patient Info":
        return "病例摘要"
    if "Termination" in t or "Passed" in t or "Override" in t:
        return "流程状态"
    if "Gate" in t or t.endswith("_Judge") or "Judge" in t:
        return "Judge信号"
    if "_Doc" in t or t.startswith("Outcome_") or t.startswith("Decision_"):
        return "AI输出"
    return ""


def _trace_title_priority(title: str) -> int:
    group = _trace_title_group(title)
    priority_map = {"病例摘要": 0, "AI输出": 1, "Judge信号": 2, "流程状态": 3}
    return priority_map.get(group, 9)


def _build_case_study_with_traces(case_candidates: pd.DataFrame, remarks: pd.DataFrame, top_n: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    if case_candidates.empty:
        return pd.DataFrame(), pd.DataFrame()
    cands = case_candidates.copy()
    cands["center"] = cands["center"].map(_center_to_cn)
    cands = cands.sort_values(
        ["case_type_order", "type_rank", "candidate_score", "doctor_count", "critical_keyword_count", "remark_count"],
        ascending=[True, True, False, False, False, False],
        kind="mergesort",
    ).reset_index(drop=True)
    remark_used = remarks.copy() if not remarks.empty else pd.DataFrame()
    selected_rows: list[dict[str, Any]] = []
    snippet_rows: list[dict[str, Any]] = []
    picked_by_type: dict[str, int] = {}
    for _, row in cands.iterrows():
        if len(selected_rows) >= top_n:
            break
        case_type = str(row.get("case_type", "")).strip() or "MISC"
        if picked_by_type.get(case_type, 0) >= 1:
            continue
        center = str(row.get("center", "")).strip()
        model = str(row.get("model", "")).strip()
        model_short = str(row.get("model_short", MODEL_SHORT.get(model, model))).strip()
        case_id = str(row.get("case_id", "")).strip()
        if not center or not model or not case_id:
            continue
        trace_path = _resolve_trace_html_path(center, model, case_id)
        if trace_path is None or (not trace_path.exists()):
            continue
        try:
            html_text = trace_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        cards = _parse_trace_output_cards(html_text)
        if not cards:
            continue
        key_cards = [
            (t, s)
            for t, s in cards
            if _trace_title_group(t) != ""
        ]
        if not key_cards:
            continue
        snips: list[dict[str, Any]] = []
        for title, content in key_cards:
            content_clean = re.sub(r"\s+", " ", content).strip()
            if len(content_clean) < 20:
                continue
            snips.append(
                {
                    "trace_title": title,
                    "trace_output_snippet": content_clean[:420],
                    "trace_group": _trace_title_group(title),
                    "trace_priority": _trace_title_priority(title),
                }
            )
        if not snips:
            continue
        rem_text = ""
        if not remark_used.empty:
            rem_sub = remark_used[
                (remark_used["center"].map(_center_to_cn) == center)
                & (remark_used["model"].astype(str) == model)
                & (remark_used["case_id"].astype(str) == case_id)
                & (remark_used["remark_text"].astype(str).str.strip().ne(""))
            ].copy()
            if not rem_sub.empty:
                uniq = []
                seen: set[str] = set()
                for txt in rem_sub["remark_text"].astype(str).tolist():
                    t = txt.strip()
                    if not t:
                        continue
                    nrm = _normalize_remark_text(t)
                    if nrm in seen:
                        continue
                    seen.add(nrm)
                    uniq.append(t)
                rem_text = " || ".join(uniq[:4])
        selected_rows.append(
            {
                "center": center,
                "model": model,
                "model_short": model_short,
                "case_id": case_id,
                "case_type": case_type,
                "case_type_order": pd.to_numeric(row.get("case_type_order"), errors="coerce"),
                "type_rank": pd.to_numeric(row.get("type_rank"), errors="coerce"),
                "case_type_label": str(row.get("case_type_label", "")),
                "selection_note": str(row.get("selection_note", "")),
                "case_analysis_note": str(row.get("case_analysis_note", row.get("selection_note", ""))),
                "stage4_list": str(row.get("stage4_list", "")),
                "stage_list": str(row.get("stage_list", "")),
                "stage_cn_list": str(row.get("stage_cn_list", "")),
                "candidate_score": pd.to_numeric(row.get("candidate_score"), errors="coerce"),
                "candidate_reason": str(row.get("candidate_reason", "")),
                "doctor_count": pd.to_numeric(row.get("doctor_count"), errors="coerce"),
                "critical_keyword_hits": str(row.get("critical_keyword_hits", "")),
                "remark_text_all": str(row.get("remark_text_all", "")),
                "human_mean": pd.to_numeric(row.get("human_mean"), errors="coerce"),
                "judge_mean": pd.to_numeric(row.get("judge_mean"), errors="coerce"),
                "reason_human_mean": pd.to_numeric(row.get("reason_human_mean"), errors="coerce"),
                "llm_reason_mean": pd.to_numeric(row.get("llm_reason_mean"), errors="coerce"),
                "result_delta_mean": pd.to_numeric(row.get("result_delta_mean"), errors="coerce"),
                "result_abs_delta_max": pd.to_numeric(row.get("result_abs_delta_max"), errors="coerce"),
                "reason_delta_mean": pd.to_numeric(row.get("reason_delta_mean"), errors="coerce"),
                "reason_abs_delta_max": pd.to_numeric(row.get("reason_abs_delta_max"), errors="coerce"),
                "max_conf": pd.to_numeric(row.get("max_conf"), errors="coerce"),
                "min_acc": pd.to_numeric(row.get("min_acc"), errors="coerce"),
                "risk_stage_cn": str(row.get("risk_stage_cn", "")),
                "flow_end_stage": str(row.get("flow_end_stage", "")),
                "flow_end_detail": str(row.get("flow_end_detail", "")),
                "gate1_overall_score": pd.to_numeric(row.get("gate1_overall_score"), errors="coerce"),
                "gate2_overall_score": pd.to_numeric(row.get("gate2_overall_score"), errors="coerce"),
                "d3_overall_score": pd.to_numeric(row.get("d3_overall_score"), errors="coerce"),
                "d4_overall_score": pd.to_numeric(row.get("d4_overall_score"), errors="coerce"),
                "门诊检查": str(row.get("门诊检查", "")),
                "门诊决策": str(row.get("门诊决策", "")),
                "入院检查": str(row.get("入院检查", "")),
                "入院决策": str(row.get("入院决策", "")),
                "术后康复": str(row.get("术后康复", "")),
                "随访计划": str(row.get("随访计划", "")),
                "remark_summary": rem_text,
                "trace_path": trace_path.as_posix(),
                "trace_card_count": int(len(key_cards)),
            }
        )
        picked_by_type[case_type] = picked_by_type.get(case_type, 0) + 1
        snips = sorted(snips, key=lambda item: (item["trace_priority"], item["trace_title"]))
        for item in snips[:10]:
            snippet_rows.append(
                {
                    "center": center,
                    "model_short": model_short,
                    "case_id": case_id,
                    "case_type": case_type,
                    "trace_title": item["trace_title"],
                    "trace_group": item["trace_group"],
                    "trace_priority": item["trace_priority"],
                    "trace_output_snippet": item["trace_output_snippet"],
                    "trace_path": trace_path.as_posix(),
                }
            )
    return pd.DataFrame(selected_rows), pd.DataFrame(snippet_rows)


def _slugify_trace_asset(value: Any) -> str:
    text = re.sub(r"[^0-9A-Za-z._-]+", "-", str(value or "").strip())
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text or "trace"


def _materialize_case_study_traces(
    selected_cases: pd.DataFrame,
    trace_snippets: pd.DataFrame,
    trace_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trace_dir.mkdir(parents=True, exist_ok=True)
    # Keep the supplementary trace directory aligned with the current case selection after reruns.
    for stale_trace in trace_dir.glob("*_trace_*.html"):
        try:
            stale_trace.unlink()
        except Exception:
            pass
    if selected_cases.empty:
        empty_manifest = pd.DataFrame(
            columns=[
                "center",
                "case_id",
                "model_short",
                "case_type",
                "case_type_label",
                "selection_note",
                "case_analysis_note",
                "remark_summary",
                "trace_copy_relpath",
                "trace_original_path",
            ]
        )
        empty_cards = pd.DataFrame(
            columns=[
                "center",
                "case_id",
                "model_short",
                "case_type",
                "case_type_label",
                "card_order",
                "trace_group",
                "trace_title",
                "trace_output_full",
                "trace_copy_relpath",
                "trace_original_path",
            ]
        )
        return selected_cases.copy(), trace_snippets.copy(), empty_manifest, empty_cards

    selected = selected_cases.copy()
    snippets = trace_snippets.copy()
    manifest_rows: list[dict[str, Any]] = []
    card_rows: list[dict[str, Any]] = []
    rel_map: dict[tuple[str, str, str], tuple[str, str]] = {}
    for idx, row in selected.iterrows():
        center = str(row.get("center", "")).strip()
        case_id = str(row.get("case_id", "")).strip()
        model_short = str(row.get("model_short", "")).strip()
        case_type = str(row.get("case_type", "")).strip() or "case"
        order_num = pd.to_numeric(row.get("case_type_order"), errors="coerce")
        trace_raw = str(row.get("trace_path", "")).strip()
        original_path = Path(trace_raw) if trace_raw else None
        trace_copy_relpath = ""
        trace_copy_path = ""
        trace_original_path = original_path.as_posix() if original_path is not None else ""
        if original_path is not None and original_path.exists():
            order_prefix = int(order_num) if pd.notna(order_num) else idx + 1
            copy_name = (
                f"{order_prefix:02d}_"
                f"{_slugify_trace_asset(case_type)}_"
                f"{_slugify_trace_asset(center)}_"
                f"{_slugify_trace_asset(case_id)}_"
                f"{_slugify_trace_asset(model_short)}.html"
            )
            dst = trace_dir / copy_name
            try:
                shutil.copy2(original_path, dst)
                trace_copy_relpath = dst.relative_to(trace_dir.parent).as_posix()
                trace_copy_path = dst.as_posix()
            except Exception:
                trace_copy_relpath = ""
                trace_copy_path = ""
            try:
                html_text = original_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                html_text = ""
            if html_text:
                for card_order, (title, content) in enumerate(_parse_trace_output_cards(html_text), start=1):
                    trace_group = _trace_title_group(title)
                    if not trace_group:
                        continue
                    card_rows.append(
                        {
                            "center": center,
                            "case_id": case_id,
                            "model_short": model_short,
                            "case_type": case_type,
                            "case_type_label": str(row.get("case_type_label", "")),
                            "card_order": card_order,
                            "trace_group": trace_group,
                            "trace_title": title,
                            "trace_output_full": content,
                            "trace_copy_relpath": trace_copy_relpath,
                            "trace_original_path": trace_original_path,
                        }
                    )
        selected.at[idx, "trace_original_path"] = trace_original_path
        selected.at[idx, "trace_copy_relpath"] = trace_copy_relpath
        selected.at[idx, "trace_copy_path"] = trace_copy_path
        rel_map[(center, case_id, model_short)] = (trace_copy_relpath, trace_original_path)
        manifest_rows.append(
            {
                "center": center,
                "case_id": case_id,
                "model_short": model_short,
                "case_type": case_type,
                "case_type_label": str(row.get("case_type_label", "")),
                "selection_note": str(row.get("selection_note", "")),
                "case_analysis_note": str(row.get("case_analysis_note", row.get("selection_note", ""))),
                "remark_summary": str(row.get("remark_summary", "")),
                "trace_copy_relpath": trace_copy_relpath,
                "trace_original_path": trace_original_path,
            }
        )

    if not snippets.empty:
        snippets["trace_original_path"] = snippets["trace_path"].astype(str)
        snippets["trace_copy_relpath"] = [
            rel_map.get(
                (str(r.get("center", "")).strip(), str(r.get("case_id", "")).strip(), str(r.get("model_short", "")).strip()),
                ("", ""),
            )[0]
            for _, r in snippets.iterrows()
        ]
    return selected, snippets, pd.DataFrame(manifest_rows), pd.DataFrame(card_rows)


def _write_case_study_markdown(selected_cases: pd.DataFrame, trace_snippets: pd.DataFrame, out_md: Path) -> None:
    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# A0 附录案例研究（可直接在 Supplementary 援引）",
        "",
        "说明：优先保留与手稿主论点一致的 3 个主例（信息不足但路径稳健 / 缺病理仍下最终诊断 / D2失败级联），并附 3 个扩展示例用于补充说明风险边界。",
        "",
    ]
    if selected_cases.empty:
        lines.append("- 本轮未筛到同时满足“有trace且有有效AI输出”的高价值案例。")
        out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    for idx, row in selected_cases.reset_index(drop=True).iterrows():
        lines.append(f"## Case {idx + 1}: {row.get('center','')}-{row.get('case_id','')} ({row.get('model_short','')})")
        lines.append(f"- 候选分数：{pd.to_numeric(row.get('candidate_score'), errors='coerce'):.2f}")
        lines.append(f"- 入选理由：{row.get('candidate_reason','')}")
        lines.append(f"- 医生备注摘要：{row.get('remark_summary','（无）')}")
        lines.append(f"- 关键关键词：{row.get('critical_keyword_hits','（无）')}")
        lines.append(f"- Trace：`{row.get('trace_path','')}`")
        lines.append("")
        sub = trace_snippets[
            (trace_snippets["center"] == row.get("center"))
            & (trace_snippets["model_short"] == row.get("model_short"))
            & (trace_snippets["case_id"] == row.get("case_id"))
        ].copy()
        if sub.empty:
            lines.append("- 未提取到可展示的关键输出片段。")
            lines.append("")
            continue
        lines.append("**关键对话片段（节选）**")
        for _, sr in sub.head(5).iterrows():
            lines.append(f"- [{sr['trace_title']}] {sr['trace_output_snippet']}")
        lines.append("")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_case_study_html(
    selected_cases: pd.DataFrame,
    trace_snippets: pd.DataFrame,
    remarks: pd.DataFrame,
    out_html: Path,
) -> None:
    out_html.parent.mkdir(parents=True, exist_ok=True)
    if selected_cases.empty:
        out_html.write_text(
            "<html><body><h1>A0 案例研究</h1><p>本轮未筛到同时满足“有 trace 且有有效 AI 输出”的高价值案例。</p></body></html>",
            encoding="utf-8",
        )
        return

    def _esc(text: Any) -> str:
        return html.escape("" if text is None else str(text))

    def _fmt_num(value: Any, digits: int = 2) -> str:
        num = pd.to_numeric(value, errors="coerce")
        if pd.isna(num):
            return "—"
        return f"{float(num):.{digits}f}"

    def _timeline_status(value: Any) -> tuple[str, str]:
        stage_name, status = _split_sankey_label(str(value or ""))
        status = _wrap_sankey_status_display(status if status else str(value or ""))
        status = status.strip() or "未记录"
        low = status.lower()
        if ("不通过" in status) or ("terminated" in low) or ("失败" in status):
            return status, "bad"
        if ("通过" in status) or ("完成" in status):
            return status, "good"
        if ("结束" in status) or ("未经过" in status):
            return status, "muted"
        return status, "mid"

    cards: list[str] = []
    remarks = remarks.copy() if remarks is not None else pd.DataFrame()
    for idx, row in selected_cases.reset_index(drop=True).iterrows():
        center = str(row.get("center", ""))
        model = str(row.get("model", ""))
        case_id = str(row.get("case_id", ""))
        sub_trace = trace_snippets[
            (trace_snippets["center"].astype(str) == center)
            & (trace_snippets["case_id"].astype(str) == case_id)
            & (trace_snippets["model_short"].astype(str) == str(row.get("model_short", "")))
        ].copy()
        sub_remarks = remarks[
            (remarks["center"].astype(str) == center)
            & (remarks["model"].astype(str) == model)
            & (remarks["case_id"].astype(str) == case_id)
        ].copy() if not remarks.empty else pd.DataFrame()

        remark_rows = ""
        if not sub_remarks.empty:
            for _, rr in sub_remarks.iterrows():
                remark_rows += (
                    "<tr>"
                    f"<td>{_esc(rr.get('doctor', ''))}</td>"
                    f"<td>{_esc(rr.get('stage_cn', rr.get('stage', '')))}</td>"
                    f"<td>{_esc(rr.get('remark_text', ''))}</td>"
                    "</tr>"
                )
        else:
            remark_rows = "<tr><td colspan='3'>未提取到医生逐条备注。</td></tr>"

        trace_groups_html = ""
        if not sub_trace.empty:
            sub_trace = sub_trace.sort_values(["trace_priority", "trace_title"], kind="mergesort")
            for trace_group in ["病例摘要", "AI输出", "Judge信号", "流程状态"]:
                group_rows = sub_trace[sub_trace["trace_group"].astype(str) == trace_group].copy()
                if group_rows.empty:
                    continue
                block_html = ""
                for _, sr in group_rows.head(4).iterrows():
                    block_html += (
                        "<details class='trace-block'>"
                        f"<summary>{_esc(sr.get('trace_title', 'trace'))}</summary>"
                        f"<pre>{_esc(sr.get('trace_output_snippet', ''))}</pre>"
                        "</details>"
                    )
                trace_groups_html += (
                    f"<section class='evidence-section'><h3>{_esc(trace_group)}</h3>{block_html}</section>"
                )
        else:
            trace_groups_html = "<p class='muted'>未提取到可展示的关键 trace 片段。</p>"

        trace_href = str(row.get("trace_copy_relpath", "")).strip()
        if not trace_href:
            trace_path = str(row.get("trace_path", "")).strip()
            if trace_path:
                try:
                    trace_href = Path(trace_path).as_uri()
                except Exception:
                    trace_href = ""
        trace_link = (
            f"<a class='trace-link' href='{_esc(trace_href)}' target='_blank'>打开补充材料内原始 trace</a>"
            if trace_href
            else "<span class='muted'>无原始 trace 链接</span>"
        )

        timeline_html = ""
        stage_specs = [
            ("门诊检查", "门诊检查"),
            ("门诊决策", "门诊决策"),
            ("入院检查", "住院检查"),
            ("入院决策", "住院决策"),
            ("术后康复", "术后决策"),
            ("随访计划", "随访与康复计划"),
        ]
        for col_name, label in stage_specs:
            status_text, status_class = _timeline_status(row.get(col_name, ""))
            timeline_html += (
                "<div class='timeline-item'>"
                f"<div class='timeline-dot {status_class}'></div>"
                "<div class='timeline-content'>"
                f"<span class='timeline-stage'>{_esc(label)}</span>"
                f"<strong class='timeline-status {status_class}'>{_esc(status_text)}</strong>"
                "</div>"
                "</div>"
            )

        score_rows = "".join(
            [
                "<tr><td>结果人工均分</td><td>{}</td></tr>".format(_esc(_fmt_num(row.get("human_mean")))),
                "<tr><td>结果Judge均分</td><td>{}</td></tr>".format(_esc(_fmt_num(row.get("judge_mean")))),
                "<tr><td>推理人工均分</td><td>{}</td></tr>".format(_esc(_fmt_num(row.get("reason_human_mean")))),
                "<tr><td>推理LLM均分</td><td>{}</td></tr>".format(_esc(_fmt_num(row.get("llm_reason_mean")))),
                "<tr><td>平均结果分差</td><td>{}</td></tr>".format(_esc(_fmt_num(row.get("result_delta_mean")))),
                "<tr><td>高置信低准确风险</td><td>{}</td></tr>".format(
                    _esc(f"conf={_fmt_num(row.get('max_conf'))}, acc={_fmt_num(row.get('min_acc'))}")
                ),
            ]
        )

        cards.append(
            f"""
            <section class="case-card">
              <div class="case-head">
                <div>
                  <div class="type-badge">{_esc(row.get('case_type_label', row.get('case_type', 'Case')))}</div>
                  <h2>Case {idx + 1}: {_esc(center)} - {_esc(case_id)} <span class="model">{_esc(row.get('model_short', ''))}</span></h2>
                  <p class="subhead">{_esc(row.get('selection_note', row.get('candidate_reason', '')))}</p>
                </div>
                <div class="score-box">
                  <span>候选分数</span>
                  <strong>{_fmt_num(row.get('candidate_score'))}</strong>
                </div>
              </div>
              <div class="meta-grid">
                <div><span>关键阶段</span><strong>{_esc(row.get('stage_cn_list', row.get('stage4_list', '')) or '—')}</strong></div>
                <div><span>流程结束点</span><strong>{_esc(row.get('flow_end_stage', '—'))}</strong></div>
                <div><span>关键关键词</span><strong>{_esc(row.get('critical_keyword_hits', '（无）') or '（无）')}</strong></div>
                <div><span>结果最大分差</span><strong>{_esc(_fmt_num(row.get('result_abs_delta_max')))}</strong></div>
                <div><span>推理最大分差</span><strong>{_esc(_fmt_num(row.get('reason_abs_delta_max')))}</strong></div>
                <div><span>校准风险阶段</span><strong>{_esc(row.get('risk_stage_cn', '—') or '—')}</strong></div>
              </div>
              <div class="insight-box">
                <h3>为什么值得放进正文/附录例子</h3>
                <p>{_esc(row.get('case_analysis_note', row.get('selection_note', '（无）')))}</p>
                <p class="muted">{_esc(row.get('remark_summary', '（无备注摘要）'))}</p>
              </div>
              <div class="case-body">
                <div>
                  <h3>左侧流程时间线</h3>
                  <div class="timeline-wrap">{timeline_html}</div>
                  <div class="trace-link-wrap">{trace_link}</div>
                </div>
                <div>
                  <div class="split-grid">
                    <div>
                      <h3>评分与判定</h3>
                      <table class="score-table"><tbody>{score_rows}</tbody></table>
                    </div>
                    <div>
                      <h3>医生备注明细</h3>
                      <table class="remark-table">
                        <thead><tr><th>医生</th><th>环节</th><th>备注</th></tr></thead>
                        <tbody>{remark_rows}</tbody>
                      </table>
                    </div>
                  </div>
                  <div class="evidence-wrap">
                    <h3>右侧证据卡片</h3>
                    {trace_groups_html}
                  </div>
                </div>
              </div>
            </section>
            """
        )

    html_text = f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <title>A0 附录案例研究</title>
      <style>
        :root {{
          --ink: #1f2d3d;
          --muted: #607080;
          --line: #d9e2ec;
          --bg: #f6f9fc;
          --card: #ffffff;
          --accent: #1f5f8b;
          --accent-soft: #e9f2f8;
          --warn: #8b2f39;
          --good: #2f7d62;
          --bad: #b24b46;
          --mid: #7a5d2f;
          --shadow: 0 14px 36px rgba(31,45,61,0.08);
        }}
        body {{
          margin: 0;
          background: linear-gradient(180deg, #f4f8fb 0%, #edf3f8 100%);
          color: var(--ink);
          font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
        }}
        .page {{
          max-width: 1320px;
          margin: 0 auto;
          padding: 40px 32px 72px;
        }}
        h1 {{
          margin: 0 0 10px;
          font-size: 36px;
          letter-spacing: 0.5px;
        }}
        .lead {{
          margin: 0 0 30px;
          color: var(--muted);
          font-size: 16px;
          line-height: 1.7;
        }}
        .case-card {{
          background: var(--card);
          border: 1px solid var(--line);
          border-radius: 22px;
          box-shadow: var(--shadow);
          padding: 26px 28px 28px;
          margin-bottom: 24px;
        }}
        .case-head {{
          display: flex;
          justify-content: space-between;
          gap: 20px;
          align-items: flex-start;
          margin-bottom: 18px;
        }}
        .type-badge {{
          display: inline-flex;
          align-items: center;
          padding: 6px 12px;
          border-radius: 999px;
          background: linear-gradient(135deg, #ecf5fb 0%, #f6fafc 100%);
          border: 1px solid #c6d8e6;
          color: var(--accent);
          font-size: 13px;
          font-weight: 700;
          margin-bottom: 10px;
        }}
        .case-head h2 {{
          margin: 0 0 8px;
          font-size: 28px;
        }}
        .model {{
          color: var(--accent);
          font-size: 22px;
        }}
        .subhead {{
          margin: 0;
          color: var(--muted);
          font-size: 15px;
        }}
        .score-box {{
          min-width: 132px;
          background: linear-gradient(135deg, #e8f3fb 0%, #f3f8fb 100%);
          border: 1px solid #cfdce8;
          border-radius: 18px;
          padding: 12px 16px;
          text-align: center;
        }}
        .score-box span {{
          display: block;
          color: var(--muted);
          font-size: 13px;
        }}
        .score-box strong {{
          display: block;
          margin-top: 4px;
          color: var(--accent);
          font-size: 28px;
        }}
        .meta-grid {{
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 12px;
          margin-bottom: 18px;
        }}
        .meta-grid div {{
          background: var(--bg);
          border: 1px solid var(--line);
          border-radius: 14px;
          padding: 12px 14px;
        }}
        .meta-grid span {{
          display: block;
          color: var(--muted);
          font-size: 13px;
          margin-bottom: 5px;
        }}
        .meta-grid strong {{
          font-size: 16px;
          font-weight: 700;
        }}
        .insight-box {{
          background: linear-gradient(135deg, #fdf8f6 0%, #fffdfa 100%);
          border-left: 5px solid #c56b5d;
          border-radius: 16px;
          padding: 16px 18px;
          margin-bottom: 18px;
        }}
        .insight-box h3, .split-grid h3 {{
          margin: 0 0 10px;
          font-size: 18px;
        }}
        .insight-box p {{
          margin: 0 0 6px;
          line-height: 1.8;
        }}
        .case-body {{
          display: grid;
          grid-template-columns: 0.72fr 1.28fr;
          gap: 22px;
        }}
        .timeline-wrap {{
          position: relative;
          border: 1px solid var(--line);
          border-radius: 18px;
          background: linear-gradient(180deg, #fbfdff 0%, #f5f9fc 100%);
          padding: 18px 18px 10px 18px;
        }}
        .timeline-wrap::before {{
          content: "";
          position: absolute;
          left: 31px;
          top: 24px;
          bottom: 24px;
          width: 2px;
          background: linear-gradient(180deg, #d7e4ee 0%, #b9cfe0 100%);
        }}
        .timeline-item {{
          position: relative;
          display: flex;
          gap: 14px;
          align-items: flex-start;
          padding: 0 0 16px;
        }}
        .timeline-dot {{
          position: relative;
          z-index: 1;
          width: 16px;
          height: 16px;
          border-radius: 50%;
          margin-top: 4px;
          border: 3px solid white;
          box-shadow: 0 0 0 1px #c7d6e2;
          background: #9eb1c2;
        }}
        .timeline-dot.good {{ background: var(--good); }}
        .timeline-dot.bad {{ background: var(--bad); }}
        .timeline-dot.mid {{ background: var(--mid); }}
        .timeline-dot.muted {{ background: #aab6c2; }}
        .timeline-content {{
          flex: 1;
          background: white;
          border: 1px solid var(--line);
          border-radius: 14px;
          padding: 10px 12px;
        }}
        .timeline-stage {{
          display: block;
          color: var(--muted);
          font-size: 12px;
          margin-bottom: 4px;
        }}
        .timeline-status {{
          display: block;
          font-size: 16px;
          font-weight: 700;
        }}
        .timeline-status.good {{ color: var(--good); }}
        .timeline-status.bad {{ color: var(--bad); }}
        .timeline-status.mid {{ color: var(--mid); }}
        .timeline-status.muted {{ color: #6b7b8a; }}
        .split-grid {{
          display: grid;
          grid-template-columns: 0.88fr 1.12fr;
          gap: 20px;
        }}
        .score-table, .remark-table {{
          width: 100%;
          border-collapse: collapse;
          font-size: 14px;
        }}
        .score-table td, .remark-table th, .remark-table td {{
          border: 1px solid var(--line);
          padding: 10px 12px;
          vertical-align: top;
          text-align: left;
        }}
        .score-table tr:nth-child(odd) td {{
          background: #f8fbfe;
        }}
        .remark-table {{
        }}
        .remark-table thead th {{
          background: #eef5fb;
        }}
        .evidence-wrap {{
          margin-top: 18px;
        }}
        .evidence-section {{
          margin-bottom: 18px;
        }}
        .evidence-section h3 {{
          margin: 0 0 10px;
          font-size: 17px;
        }}
        .trace-block {{
          border: 1px solid var(--line);
          border-radius: 14px;
          background: #fbfdff;
          margin-bottom: 10px;
          overflow: hidden;
        }}
        .trace-block summary {{
          cursor: pointer;
          padding: 12px 14px;
          font-weight: 700;
          background: #eef5fb;
        }}
        .trace-block pre {{
          margin: 0;
          padding: 14px;
          white-space: pre-wrap;
          word-break: break-word;
          font-size: 13px;
          line-height: 1.7;
          color: #243647;
          background: #fcfdff;
        }}
        .trace-link-wrap {{
          margin-top: 12px;
        }}
        .trace-link {{
          color: var(--accent);
          text-decoration: none;
          font-weight: 700;
        }}
        .muted {{
          color: var(--muted);
        }}
        @media (max-width: 980px) {{
          .case-head, .split-grid, .meta-grid, .case-body {{
            grid-template-columns: 1fr;
            display: grid;
          }}
          .case-head {{
            align-items: stretch;
          }}
        }}
      </style>
    </head>
    <body>
      <main class="page">
        <h1>A0 附录案例研究</h1>
        <p class="lead">当前版本优先保留 3 个与手稿主论点直接对齐的主例，并补充 3 个扩展示例说明风险边界。每例统一采用“左侧流程时间线 + 右侧证据卡片”版式，同时展示流程状态、评分差、医生备注与 trace 证据，并在同目录 <code>traces/</code> 中保留可直接打开的原始 trace html，便于 supplementary 在线浏览、人工复核或截取单例局部作为正文例图。</p>
        {''.join(cards)}
      </main>
    </body>
    </html>
    """
    out_html.write_text(html_text, encoding="utf-8")


def _build_alignment_consistency_tables_and_case_studies(
    d1_set: set[tuple[str, str, str]],
    gate3_set: set[tuple[str, str, str]],
) -> dict[str, Path]:
    group = "A0_consistency_tables"
    align_dir = DERIVED_METRICS_DIR / "alignment"
    p_result = align_dir / "alignment_result_vs_judge_case_level_source.xlsx"
    p_reason = align_dir / "alignment_reasoning_vs_llm_case_level_source.xlsx"
    p_cons_result = align_dir / "alignment_doctor_consensus_result_source.xlsx"
    p_cons_reason = align_dir / "alignment_doctor_consensus_reasoning_source.xlsx"
    for p in [p_result, p_reason, p_cons_result, p_cons_reason]:
        if not p.exists():
            raise FileNotFoundError(f"Missing alignment source file: {p}")

    result_detail = pd.read_excel(p_result, sheet_name="detail_used")
    result_summary = pd.read_excel(p_result, sheet_name="summary_used")
    reason_detail = pd.read_excel(p_reason, sheet_name="detail_used")
    reason_summary = pd.read_excel(p_reason, sheet_name="summary_used")
    cons_result_pair = pd.read_excel(p_cons_result, sheet_name="pair_detail_used")
    cons_result_summary = pd.read_excel(p_cons_result, sheet_name="summary_used")
    cons_reason_pair = pd.read_excel(p_cons_reason, sheet_name="pair_detail_used")
    cons_reason_summary = pd.read_excel(p_cons_reason, sheet_name="summary_used")

    decision_stage_map = {
        "D1_Decision": "D1",
        "D2_Decision": "D2",
        "D3_Decision": "D3",
        "D4_Plan": "D4",
    }
    decision_stage_order = ["D1", "D2", "D3", "D4"]
    decision_stage_label_map = {
        "D1": "D1 门诊决策",
        "D2": "D2 住院决策",
        "D3": "D3 术后决策",
        "D4": "D4 随访计划",
    }
    check_stage_map = {"D1_Loop": "D1_CHECK", "D2_Loop": "D2_CHECK"}
    check_stage_order = ["D1_CHECK", "D2_CHECK"]
    check_stage_label_map = {"D1_CHECK": "门诊检查", "D2_CHECK": "住院检查"}

    for df, target_col in [(result_detail, "judge_score_0_5"), (reason_detail, "llm_reasoning_score_0_5")]:
        df["stage4"] = df["stage"].map(_stage4_from_stage6)
        df["abs_delta"] = (
            pd.to_numeric(df["human_score_0_5"], errors="coerce") - pd.to_numeric(df[target_col], errors="coerce")
        ).abs()
    for df in [result_summary, reason_summary, cons_result_summary, cons_reason_summary]:
        df["stage_key"] = df["stage"].map(decision_stage_map)

    def _weighted_stage_overall(
        df: pd.DataFrame,
        stage_group_map: dict[str, str],
        stage_order: list[str],
        value_cols: list[str],
        weight_col: str,
    ) -> pd.DataFrame:
        use = df.copy()
        if "stage_key" not in use.columns:
            use["stage_key"] = use["stage"].map(stage_group_map)
        use = use[use["stage_key"].astype(str).isin(stage_order)].copy()
        rows: list[dict[str, Any]] = []
        for stage in stage_order:
            sub = use[use["stage_key"] == stage].copy()
            if sub.empty:
                continue
            w = pd.to_numeric(sub[weight_col], errors="coerce").fillna(0.0)
            row: dict[str, Any] = {"stage_key": stage, "sample_weight_sum": float(w.sum())}
            for col in value_cols:
                v = pd.to_numeric(sub[col], errors="coerce")
                if w.sum() > 0:
                    row[col] = float((v.fillna(0.0) * w).sum() / w.sum())
                else:
                    row[col] = float(v.mean()) if v.notna().any() else np.nan
            rows.append(row)
        return pd.DataFrame(rows)

    result_stage_overall = _weighted_stage_overall(
        result_summary,
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        value_cols=["human_mean", "target_mean", "delta_mean", "mae", "rmse", "pearson_r"],
        weight_col="n_pairs",
    )
    reason_stage_overall = _weighted_stage_overall(
        reason_summary,
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        value_cols=["human_mean", "target_mean", "delta_mean", "mae", "rmse", "pearson_r"],
        weight_col="n_pairs",
    )
    cons_result_stage_overall = _weighted_stage_overall(
        cons_result_summary,
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        value_cols=["abs_diff_mean", "exact_match_rate", "within_1pt_rate"],
        weight_col="n_pairs",
    )
    cons_reason_stage_overall = _weighted_stage_overall(
        cons_reason_summary,
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        value_cols=["abs_diff_mean", "exact_match_rate", "within_1pt_rate"],
        weight_col="n_pairs",
    )
    human_machine_compact_raw, human_machine_paper = _build_human_machine_compact_table(
        result_detail,
        reason_detail,
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
    )
    doctor_doctor_compact_raw, doctor_doctor_paper = _build_doctor_doctor_compact_table(
        cons_result_pair,
        cons_reason_pair,
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
    )
    human_machine_check_raw, human_machine_check_paper = _build_human_machine_compact_table(
        result_detail,
        reason_detail,
        stage_group_map=check_stage_map,
        stage_order=check_stage_order,
        stage_label_map=check_stage_label_map,
    )
    doctor_doctor_check_raw, doctor_doctor_check_paper = _build_doctor_doctor_compact_table(
        cons_result_pair,
        cons_reason_pair,
        stage_group_map=check_stage_map,
        stage_order=check_stage_order,
        stage_label_map=check_stage_label_map,
    )
    hm_result_model_raw, hm_result_model_paper = _build_manual_target_model_stage_table(
        result_detail,
        target_col="judge_score_0_5",
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
        target_label="Judge均分",
    )
    hm_reason_model_raw, hm_reason_model_paper = _build_manual_target_model_stage_table(
        reason_detail,
        target_col="llm_reasoning_score_0_5",
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
        target_label="LLM均分",
    )
    doc_result_model_raw, doc_result_model_paper = _build_doctor_doctor_model_stage_table(
        cons_result_pair,
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
    )
    doc_reason_model_raw, doc_reason_model_paper = _build_doctor_doctor_model_stage_table(
        cons_reason_pair,
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
    )

    hm_decision_suite_result = _build_stage_metric_suite(
        result_detail,
        x_col="human_score_0_5",
        y_col="judge_score_0_5",
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
        comparator="human_vs_judge",
        dimension="result",
    )
    hm_decision_suite_reason = _build_stage_metric_suite(
        reason_detail,
        x_col="human_score_0_5",
        y_col="llm_reasoning_score_0_5",
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
        comparator="human_vs_judge",
        dimension="reasoning",
    )
    hm_check_suite_result = _build_stage_metric_suite(
        result_detail,
        x_col="human_score_0_5",
        y_col="judge_score_0_5",
        stage_group_map=check_stage_map,
        stage_order=check_stage_order,
        stage_label_map=check_stage_label_map,
        comparator="human_vs_judge",
        dimension="result",
    )
    hm_check_suite_reason = _build_stage_metric_suite(
        reason_detail,
        x_col="human_score_0_5",
        y_col="llm_reasoning_score_0_5",
        stage_group_map=check_stage_map,
        stage_order=check_stage_order,
        stage_label_map=check_stage_label_map,
        comparator="human_vs_judge",
        dimension="reasoning",
    )

    doc_decision_suite_result = _build_stage_metric_suite(
        cons_result_pair,
        x_col="doctor_score_0_5_a",
        y_col="doctor_score_0_5_b",
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
        comparator="doctor_vs_doctor",
        dimension="result",
    )
    doc_decision_suite_reason = _build_stage_metric_suite(
        cons_reason_pair,
        x_col="doctor_score_0_5_a",
        y_col="doctor_score_0_5_b",
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
        comparator="doctor_vs_doctor",
        dimension="reasoning",
    )
    doc_check_suite_result = _build_stage_metric_suite(
        cons_result_pair,
        x_col="doctor_score_0_5_a",
        y_col="doctor_score_0_5_b",
        stage_group_map=check_stage_map,
        stage_order=check_stage_order,
        stage_label_map=check_stage_label_map,
        comparator="doctor_vs_doctor",
        dimension="result",
    )
    doc_check_suite_reason = _build_stage_metric_suite(
        cons_reason_pair,
        x_col="doctor_score_0_5_a",
        y_col="doctor_score_0_5_b",
        stage_group_map=check_stage_map,
        stage_order=check_stage_order,
        stage_label_map=check_stage_label_map,
        comparator="doctor_vs_doctor",
        dimension="reasoning",
    )

    decision_metric_suite = pd.concat(
        [hm_decision_suite_result, hm_decision_suite_reason, doc_decision_suite_result, doc_decision_suite_reason],
        ignore_index=True,
    )
    check_metric_suite = pd.concat(
        [hm_check_suite_result, hm_check_suite_reason, doc_check_suite_result, doc_check_suite_reason],
        ignore_index=True,
    )
    if not decision_metric_suite.empty:
        decision_metric_suite.insert(0, "stage_scope", "decision")
    if not check_metric_suite.empty:
        check_metric_suite.insert(0, "stage_scope", "check")
    metric_suite_all = pd.concat([decision_metric_suite, check_metric_suite], ignore_index=True)
    metric_suite_key_cols = [
        "stage_scope",
        "stage_key",
        "stage_cn",
        "comparator",
        "dimension",
        "n_pairs",
        "mae",
        "rmse",
        "exact_rate",
        "within1_rate",
        "pearson_r",
        "spearman_rho",
        "quadratic_weighted_kappa",
        "corr_missing_reason",
    ]
    metric_suite_key = (
        metric_suite_all[[c for c in metric_suite_key_cols if c in metric_suite_all.columns]].copy()
        if not metric_suite_all.empty
        else pd.DataFrame(columns=metric_suite_key_cols)
    )

    hm_decision_binary_result = _build_stage_binary_detail(
        result_detail,
        x_col="human_score_0_5",
        y_col="judge_score_0_5",
        x_name="human",
        y_name="judge",
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
    )
    hm_decision_binary_reason = _build_stage_binary_detail(
        reason_detail,
        x_col="human_score_0_5",
        y_col="llm_reasoning_score_0_5",
        x_name="human",
        y_name="llm",
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
    )
    hm_check_binary_result = _build_stage_binary_detail(
        result_detail,
        x_col="human_score_0_5",
        y_col="judge_score_0_5",
        x_name="human",
        y_name="judge",
        stage_group_map=check_stage_map,
        stage_order=check_stage_order,
        stage_label_map=check_stage_label_map,
    )
    hm_check_binary_reason = _build_stage_binary_detail(
        reason_detail,
        x_col="human_score_0_5",
        y_col="llm_reasoning_score_0_5",
        x_name="human",
        y_name="llm",
        stage_group_map=check_stage_map,
        stage_order=check_stage_order,
        stage_label_map=check_stage_label_map,
    )
    doc_decision_binary_result = _build_stage_binary_detail(
        cons_result_pair,
        x_col="doctor_score_0_5_a",
        y_col="doctor_score_0_5_b",
        x_name="doctor_a",
        y_name="doctor_b",
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
    )
    doc_decision_binary_reason = _build_stage_binary_detail(
        cons_reason_pair,
        x_col="doctor_score_0_5_a",
        y_col="doctor_score_0_5_b",
        x_name="doctor_a",
        y_name="doctor_b",
        stage_group_map=decision_stage_map,
        stage_order=decision_stage_order,
        stage_label_map=decision_stage_label_map,
    )
    doc_check_binary_result = _build_stage_binary_detail(
        cons_result_pair,
        x_col="doctor_score_0_5_a",
        y_col="doctor_score_0_5_b",
        x_name="doctor_a",
        y_name="doctor_b",
        stage_group_map=check_stage_map,
        stage_order=check_stage_order,
        stage_label_map=check_stage_label_map,
    )
    doc_check_binary_reason = _build_stage_binary_detail(
        cons_reason_pair,
        x_col="doctor_score_0_5_a",
        y_col="doctor_score_0_5_b",
        x_name="doctor_a",
        y_name="doctor_b",
        stage_group_map=check_stage_map,
        stage_order=check_stage_order,
        stage_label_map=check_stage_label_map,
    )
    for df, stage_scope, comparator, dimension in [
        (hm_decision_binary_result, "decision", "human_vs_judge", "result"),
        (hm_decision_binary_reason, "decision", "human_vs_judge", "reasoning"),
        (hm_check_binary_result, "check", "human_vs_judge", "result"),
        (hm_check_binary_reason, "check", "human_vs_judge", "reasoning"),
        (doc_decision_binary_result, "decision", "doctor_vs_doctor", "result"),
        (doc_decision_binary_reason, "decision", "doctor_vs_doctor", "reasoning"),
        (doc_check_binary_result, "check", "doctor_vs_doctor", "result"),
        (doc_check_binary_reason, "check", "doctor_vs_doctor", "reasoning"),
    ]:
        if df.empty:
            continue
        df.insert(0, "stage_scope", stage_scope)
        df.insert(1, "comparator", comparator)
        df.insert(2, "dimension", dimension)

    binary_detail_decision_all = pd.concat(
        [hm_decision_binary_result, hm_decision_binary_reason, doc_decision_binary_result, doc_decision_binary_reason],
        ignore_index=True,
    )
    binary_detail_check_all = pd.concat(
        [hm_check_binary_result, hm_check_binary_reason, doc_check_binary_result, doc_check_binary_reason],
        ignore_index=True,
    )

    remarks = _load_doctor_remark_long()
    if not remarks.empty:
        keys = list(zip(remarks["center"].astype(str), remarks["model"].astype(str), remarks["case_id"].astype(str)))
        remarks["is_d1_anomaly"] = [k in d1_set for k in keys]
        remarks["is_gate3_fail"] = [k in gate3_set for k in keys]
        remarks = remarks[~remarks["is_d1_anomaly"]].copy()
        remarks = remarks[~((remarks["stage"] == "D4_Plan") & remarks["is_gate3_fail"])].copy()

    result_case_delta = (
        result_detail.groupby(["center", "model", "case_id"], as_index=False)
        .agg(
            human_mean=("human_score_0_5", "mean"),
            judge_mean=("judge_score_0_5", "mean"),
            result_delta_mean=(
                "judge_score_0_5",
                lambda s: np.nan,
            ),
            result_abs_delta_mean=("abs_delta", "mean"),
            result_abs_delta_max=("abs_delta", "max"),
            result_stage4_list=(
                "stage4",
                lambda s: "|".join(
                    sorted({str(x).strip() for x in s if pd.notna(x) and str(x).strip()})
                ),
            ),
        )
        .copy()
    )
    if not result_case_delta.empty:
        result_case_delta["result_delta_mean"] = result_case_delta["human_mean"] - result_case_delta["judge_mean"]
    reason_case_delta = (
        reason_detail.groupby(["center", "model", "case_id"], as_index=False)
        .agg(
            reason_human_mean=("human_score_0_5", "mean"),
            llm_reason_mean=("llm_reasoning_score_0_5", "mean"),
            reason_delta_mean=(
                "llm_reasoning_score_0_5",
                lambda s: np.nan,
            ),
            reason_abs_delta_mean=("abs_delta", "mean"),
            reason_abs_delta_max=("abs_delta", "max"),
            reason_stage4_list=(
                "stage4",
                lambda s: "|".join(
                    sorted({str(x).strip() for x in s if pd.notna(x) and str(x).strip()})
                ),
            ),
        )
        .copy()
    )
    if not reason_case_delta.empty:
        reason_case_delta["reason_delta_mean"] = reason_case_delta["reason_human_mean"] - reason_case_delta["llm_reason_mean"]

    critical_keywords = [
        "指南",
        "误诊",
        "漏诊",
        "禁忌",
        "风险",
        "恶性",
        "癌",
        "出血",
        "感染",
        "复发",
        "并发症",
        "必要检查",
        "手术",
    ]
    case_summary_rows: list[dict[str, Any]] = []
    if not remarks.empty:
        remark_text_series = remarks["remark_text"].astype(str)
        rem_used = remarks[
            remark_text_series.str.strip().ne("") & remark_text_series.str.lower().ne("nan")
        ].copy()
        grouped = rem_used.groupby(["center", "model", "model_short", "case_id"], as_index=False)
        for keys, sub in grouped:
            norms = [x for x in sub["remark_norm"].astype(str).tolist() if x]
            raw_texts = [str(x) for x in sub["remark_text"].astype(str).tolist() if str(x).strip() and str(x).lower() != "nan"]
            stage4_list = "|".join(
                sorted({str(x).strip() for x in sub["stage4"].tolist() if str(x).strip() and str(x).lower() != "nan"})
            )
            stage_list = "|".join(
                sorted({str(x).strip() for x in sub["stage"].tolist() if str(x).strip() and str(x).lower() != "nan"})
            )
            stage_cn_list = "|".join(
                sorted({str(x).strip() for x in sub["stage_cn"].tolist() if str(x).strip() and str(x).lower() != "nan"})
            )
            semantic_repeat = False
            for i in range(len(norms)):
                for j in range(i + 1, len(norms)):
                    if _is_semantic_repeat(norms[i], norms[j]):
                        semantic_repeat = True
                        break
                if semantic_repeat:
                    break
            concat_text = " | ".join(raw_texts)
            kw_hits = sorted({kw for kw in critical_keywords if kw in concat_text})
            doctors = sorted(set(sub["doctor"].astype(str).tolist()))
            case_summary_rows.append(
                {
                    "center": keys[0],
                    "model": keys[1],
                    "model_short": keys[2],
                    "case_id": keys[3],
                    "stage4_list": stage4_list,
                    "stage_list": stage_list,
                    "stage_cn_list": stage_cn_list,
                    "doctor_count": int(sub["doctor"].nunique()),
                    "remark_count": int(len(raw_texts)),
                    "unique_remark_count": int(len(set(norms))) if norms else 0,
                    "semantic_repeat": bool(semantic_repeat),
                    "critical_keyword_hits": ",".join(kw_hits),
                    "critical_keyword_count": int(len(kw_hits)),
                    "doctor_list": ",".join(doctors),
                    "remark_text_all": " || ".join(raw_texts),
                    "remark_preview": " || ".join(raw_texts[:3]),
                }
            )
    case_summary = pd.DataFrame(case_summary_rows)
    if case_summary.empty:
        case_summary = pd.DataFrame(
            columns=[
                "center",
                "model",
                "model_short",
                "case_id",
                "stage4_list",
                "stage_list",
                "stage_cn_list",
                "doctor_count",
                "remark_count",
                "unique_remark_count",
                "semantic_repeat",
                "critical_keyword_hits",
                "critical_keyword_count",
                "doctor_list",
                "remark_text_all",
                "remark_preview",
            ]
        )

    metrics_case = pd.read_excel(RAW_METRICS_SOURCE, sheet_name="metrics_by_case")[
        [
            "center",
            "model",
            "case_id",
            "flow_end_stage",
            "flow_end_detail",
            "gate1_overall_score",
            "gate2_overall_score",
            "d3_overall_score",
            "d4_overall_score",
        ]
    ].copy()

    calib_case = pd.read_excel(
        DERIVED_METRICS_DIR / "calibration" / "calibration_reliability_stagewise_source.xlsx",
        sheet_name="detail_used",
    )
    calib_case["model_short"] = calib_case["model"].map(MODEL_SHORT).fillna(calib_case["model"].astype(str))
    calib_case = calib_case[calib_case["category"].astype(str).str.lower().eq("overall")].copy()
    calib_case_summary = (
        calib_case.groupby(["center", "model", "case_id"], as_index=False)
        .agg(
            max_conf=("confidence", "max"),
            min_acc=("accuracy", "min"),
            risk_stage_cn=(
                "stage_cn",
                lambda s: "|".join(sorted({str(x).strip() for x in s if pd.notna(x) and str(x).strip()})),
            ),
        )
        .copy()
    )

    sankey_case = pd.read_excel(PAPER_FIGDATA_DIR / "Fig7__sankey_flow_source.xlsx", sheet_name="detail_used")
    if "model_short" not in sankey_case.columns:
        sankey_case["model_short"] = sankey_case["model"].map(MODEL_SHORT).fillna(sankey_case["model"].astype(str))
    sankey_case = sankey_case[
        ["center", "model", "case_id", "门诊检查", "门诊决策", "入院检查", "入院决策", "术后康复", "随访计划"]
    ].copy()

    case_key_cols = ["center", "model", "case_id"]

    def _case_seed(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=case_key_cols)
        return frame[case_key_cols].drop_duplicates().copy()

    case_candidates = pd.concat(
        [
            _case_seed(case_summary),
            _case_seed(result_case_delta),
            _case_seed(reason_case_delta),
            _case_seed(metrics_case),
            _case_seed(calib_case_summary),
            _case_seed(sankey_case),
        ],
        ignore_index=True,
    ).drop_duplicates().merge(
        case_summary, on=case_key_cols, how="left"
    ).merge(
        result_case_delta, on=["center", "model", "case_id"], how="left"
    ).merge(
        reason_case_delta, on=["center", "model", "case_id"], how="left"
    ).merge(
        metrics_case, on=["center", "model", "case_id"], how="left"
    ).merge(
        calib_case_summary, on=["center", "model", "case_id"], how="left"
    ).merge(
        sankey_case, on=["center", "model", "case_id"], how="left"
    )
    all_case_candidates = case_candidates.copy()
    if not case_candidates.empty:
        def _contains_any_literal(text: Any, keywords: list[str]) -> bool:
            s = str(text or "")
            return any(kw in s for kw in keywords)

        dispute_keywords = [
            "病例有问题",
            "诊断有误",
            "更合适",
            "不支持",
            "不正确",
            "不建议",
            "无指征",
            "不需要",
            "病理与临床严重不符合",
            "方案不正确",
        ]
        info_gap_keywords = [
            "缺",
            "无法",
            "没有",
            "未提示",
            "病理",
            "HPV",
            "TCT",
            "MRI",
            "B超",
            "宫腔镜",
        ]
        no_output_keywords = ["无AI输出", "没有输出", "输出空白", "缺失", "无法评分", "无法测评"]

        if "model_short_x" in case_candidates.columns:
            case_candidates["model_short"] = case_candidates["model_short_x"]
            case_candidates = case_candidates.drop(columns=["model_short_x"])
        if "model_short_y" in case_candidates.columns:
            if "model_short" not in case_candidates.columns:
                case_candidates["model_short"] = case_candidates["model_short_y"]
            else:
                case_candidates["model_short"] = (
                    case_candidates["model_short"]
                    .replace("", np.nan)
                    .fillna(case_candidates["model_short_y"].replace("", np.nan))
                )
            case_candidates = case_candidates.drop(columns=["model_short_y"])
        case_candidates["model_short"] = (
            case_candidates.get("model_short", pd.Series(index=case_candidates.index, dtype="object"))
            .replace("", np.nan)
            .fillna(case_candidates["model"].map(MODEL_SHORT).fillna(case_candidates["model"].astype(str)))
        )

        for col in [
            "stage4_list",
            "stage_list",
            "stage_cn_list",
            "critical_keyword_hits",
            "doctor_list",
            "remark_text_all",
            "remark_preview",
            "flow_end_stage",
            "flow_end_detail",
            "risk_stage_cn",
            "门诊检查",
            "门诊决策",
            "入院检查",
            "入院决策",
            "术后康复",
            "随访计划",
        ]:
            if col not in case_candidates.columns:
                case_candidates[col] = ""
            case_candidates[col] = case_candidates[col].fillna("").astype(str)
        for col in ["doctor_count", "remark_count", "unique_remark_count", "critical_keyword_count"]:
            if col not in case_candidates.columns:
                case_candidates[col] = 0
            case_candidates[col] = pd.to_numeric(case_candidates[col], errors="coerce").fillna(0)
        if "semantic_repeat" not in case_candidates.columns:
            case_candidates["semantic_repeat"] = False
        case_candidates["semantic_repeat"] = case_candidates["semantic_repeat"].fillna(False).astype(bool)

        for col in [
            "human_mean",
            "judge_mean",
            "result_delta_mean",
            "result_abs_delta_mean",
            "result_abs_delta_max",
            "reason_human_mean",
            "llm_reason_mean",
            "reason_delta_mean",
            "reason_abs_delta_mean",
            "reason_abs_delta_max",
            "max_conf",
            "min_acc",
            "gate1_overall_score",
            "gate2_overall_score",
            "d3_overall_score",
            "d4_overall_score",
        ]:
            case_candidates[col] = pd.to_numeric(case_candidates[col], errors="coerce")
        case_candidates["result_abs_delta_mean"] = pd.to_numeric(case_candidates["result_abs_delta_mean"], errors="coerce")
        case_candidates["result_abs_delta_max"] = pd.to_numeric(case_candidates["result_abs_delta_max"], errors="coerce")
        case_candidates["reason_abs_delta_mean"] = pd.to_numeric(case_candidates["reason_abs_delta_mean"], errors="coerce")
        case_candidates["reason_abs_delta_max"] = pd.to_numeric(case_candidates["reason_abs_delta_max"], errors="coerce")
        case_candidates["remark_text_all"] = (
            case_candidates["remark_text_all"].fillna(case_candidates["remark_preview"]).fillna("").astype(str)
        )
        case_candidates["has_dispute_note"] = case_candidates["remark_text_all"].map(
            lambda s: _contains_any_literal(s, dispute_keywords)
        )
        case_candidates["has_info_gap_note"] = case_candidates["remark_text_all"].map(
            lambda s: _contains_any_literal(s, info_gap_keywords)
        )
        case_candidates["has_no_output_note"] = case_candidates["remark_text_all"].map(
            lambda s: _contains_any_literal(s, no_output_keywords)
        )
        case_candidates["candidate_score"] = (
            case_candidates["doctor_count"].fillna(0) * 2.0
            + case_candidates["critical_keyword_count"].fillna(0) * 1.5
            + case_candidates["semantic_repeat"].astype(int) * 1.2
            + case_candidates["result_abs_delta_mean"].fillna(0.0)
            + case_candidates["reason_abs_delta_mean"].fillna(0.0)
        )
        case_candidates["candidate_reason"] = case_candidates.apply(
            lambda r: ";".join(
                [
                    item
                    for item in [
                        "多医生备注" if pd.to_numeric(r.get("doctor_count"), errors="coerce") >= 2 else "",
                        "语义重复" if bool(r.get("semantic_repeat", False)) else "",
                        "关键词命中" if pd.to_numeric(r.get("critical_keyword_count"), errors="coerce") > 0 else "",
                        "结果分差较大" if pd.to_numeric(r.get("result_abs_delta_max"), errors="coerce") >= 0.6 else "",
                        "推理分差较大" if pd.to_numeric(r.get("reason_abs_delta_max"), errors="coerce") >= 0.6 else "",
                    ]
                    if item
                ]
            )
            or "多医生备注",
            axis=1,
        )
        all_case_candidates = case_candidates.sort_values(
            ["candidate_score", "doctor_count", "critical_keyword_count", "remark_count"],
            ascending=[False, False, False, False],
            kind="mergesort",
        ).reset_index(drop=True)
        candidate_filtered = all_case_candidates[
            (
                (all_case_candidates["doctor_count"] >= 2)
                | (all_case_candidates["remark_count"] >= 1)
            )
            & (
                all_case_candidates["semantic_repeat"]
                | (all_case_candidates["critical_keyword_count"] > 0)
                | (all_case_candidates["result_abs_delta_max"] >= 0.6)
                | (all_case_candidates["reason_abs_delta_max"] >= 0.6)
                | (all_case_candidates["doctor_count"] >= 2)
            )
        ].copy()
        # narrative case set 仍优先使用“有医生备注且有明显信号”的病例；若不足，再回退到 flow-based 备选。
        if candidate_filtered.empty:
            candidate_filtered = all_case_candidates[all_case_candidates["remark_count"] >= 1].copy()
        if candidate_filtered.empty:
            candidate_filtered = all_case_candidates.copy()
        remark_case_candidates = candidate_filtered.sort_values(
            ["candidate_score", "doctor_count", "critical_keyword_count", "remark_count"],
            ascending=[False, False, False, False],
            kind="mergesort",
        ).reset_index(drop=True)
        typed_rows: list[pd.Series] = []
        used_case_keys: set[tuple[str, str, str]] = set()

        def _fmt_case_metric(value: Any) -> str:
            num = pd.to_numeric(value, errors="coerce")
            return "NA" if pd.isna(num) else f"{float(num):.2f}"

        story_case_overrides: dict[tuple[str, str, str], dict[str, str]] = {
            ("新疆", "gemini-2.5p", "Xinjiang_093"): {
                "selection_note": "该例用于展示“关键证据不足时，AI先补关键检查，再在活检与影像到位后完成定诊”。",
                "case_analysis_note": "医生备注强调“无活检、无 MRI、B 超也未提示异常，无法直接诊断宫颈癌并分期”。trace 中 AI 先要求阴道镜活检、MRI 与 HPV/TCT 等关键证据，后续再根据活检与影像修正诊断，适合作为正文主例中“信息不足但决策路径稳健”的正例。",
            },
            ("武汉", "deepseek-v3", "wuhan_33"): {
                "selection_note": "该例用于展示“缺少病理金标准时，AI仍把可疑病变写成最终诊断”的逻辑错误。",
                "case_analysis_note": "医生备注明确指出“无术后病理，不能诊断子宫内膜息肉”。但该例 trace 中 AI 在缺少病理金标准的情况下，仍将宫腔镜或术中所见直接收束为最终诊断，适合作为“把缺失证据当成已证实”的高置信低准确反例。",
            },
            ("佛山", "claude-4.1", "foshan_19"): {
                "selection_note": "该例用于展示“D2 住院决策阶段发生关键诊断降级，并被 Secondary Judge 确认终止”的失败级联。",
                "case_analysis_note": "该例门诊已有 TCT、HPV、活检病理和 MRI 指向宫颈鳞癌，但入院决策阶段 AI 仍将疾病降级为 CIN2-3，并提出局部锥切路径。Gate 2 Secondary Judge 明确指出其忽略了浸润癌证据，最终在 D2 终止，是最贴合手稿“D2 失败级联”主例的强负例。",
            },
            ("武汉", "claude-4.1", "wuhan_42"): {
                "selection_note": "该例用于展示“关键影像缺失且已被标记为不可得时，AI仍容易在门诊与入院边界上反复索检”的诊断边界问题。",
                "case_analysis_note": "医生备注指出“缺 B 超结果，无法得出宫腔积液诊断，案例无法评价”。该例 trace 可直接看到经阴道超声在门诊被标记为不可得后，AI 仍围绕缺失影像反复推进判断，适合作为扩展示例说明“信息边界处理”本身也是系统风险源。",
            },
            ("武汉", "claude-4.1", "wuhan_13"): {
                "selection_note": "该例用于展示“多个可疑病灶被一次性打包手术处理”的方案扩大化风险。",
                "case_analysis_note": "医生备注指出“子宫纵隔不需要手术，没有证据提示内膜息肉，手术方式不正确”。但 trace 中 AI 将肌瘤、纵隔和息肉合并纳入单次宫腔镜手术，适合作为扩展示例中的“多病灶打包处理”反例。",
            },
            ("武汉", "grok-4", "wuhan_5"): {
                "selection_note": "该例用于展示“诊断链条未必完全错误，但术后长期管理建议偏离临床原则”的管理层面负例。",
                "case_analysis_note": "医生备注集中在术后激素替代方案与真实临床原则不一致。该例可用于说明：即便前面诊断链条未必完全失真，AI 在术后长期管理建议上仍可能出现与临床实践不一致的偏差。",
            },
        }

        def _prioritize_story_candidates(
            frame: pd.DataFrame,
            preferred_keys: list[tuple[str, str, str]],
            sort_cols: list[str],
            ascending: list[bool],
        ) -> pd.DataFrame:
            if frame.empty:
                return frame
            out = frame.copy()
            out["_preferred_rank"] = 999
            center_norm = out["center"].astype(str).str.lower()
            model_norm = out["model_short"].astype(str).str.lower()
            case_norm = out["case_id"].astype(str).str.lower()
            for rank, (pref_center, pref_model_short, pref_case_id) in enumerate(preferred_keys, start=1):
                mask = (
                    center_norm.eq(str(pref_center).lower())
                    & model_norm.eq(str(pref_model_short).lower())
                    & case_norm.eq(str(pref_case_id).lower())
                )
                out.loc[mask, "_preferred_rank"] = rank
            return out.sort_values(["_preferred_rank", *sort_cols], ascending=[True, *ascending], kind="mergesort")

        def _ensure_story_candidates(
            frame: pd.DataFrame,
            fallback_source: pd.DataFrame,
            preferred_keys: list[tuple[str, str, str]],
        ) -> pd.DataFrame:
            out = frame.copy()
            if fallback_source.empty:
                return out
            existing = {
                (
                    str(r.get("center", "")).lower(),
                    str(r.get("model_short", "")).lower(),
                    str(r.get("case_id", "")).lower(),
                )
                for _, r in out.iterrows()
            }
            extras: list[pd.DataFrame] = []
            for pref_center, pref_model_short, pref_case_id in preferred_keys:
                key = (str(pref_center).lower(), str(pref_model_short).lower(), str(pref_case_id).lower())
                if key in existing:
                    continue
                mask = (
                    fallback_source["center"].astype(str).str.lower().eq(key[0])
                    & fallback_source["model_short"].astype(str).str.lower().eq(key[1])
                    & fallback_source["case_id"].astype(str).str.lower().eq(key[2])
                )
                pref_df = fallback_source[mask].copy()
                if not pref_df.empty:
                    extras.append(pref_df.head(1))
                    existing.add(key)
            if extras:
                out = pd.concat([out, *extras], ignore_index=True)
            return out

        def _append_type(
            frame: pd.DataFrame,
            *,
            case_type: str,
            case_type_order: int,
            case_type_label: str,
            max_candidates: int = 4,
        ) -> None:
            if frame.empty:
                return
            frame = frame.reset_index(drop=True)
            added = 0
            for type_rank, (_, cand_row) in enumerate(frame.iterrows(), start=1):
                key = (str(cand_row["center"]), str(cand_row["model"]), str(cand_row["case_id"]))
                if key in used_case_keys:
                    continue
                cand_out = cand_row.copy()
                override_key = (
                    str(cand_row.get("center", "")),
                    str(cand_row.get("model_short", "")),
                    str(cand_row.get("case_id", "")),
                )
                override = story_case_overrides.get(override_key, {})
                cand_out["case_type"] = case_type
                cand_out["case_type_order"] = case_type_order
                cand_out["case_type_label"] = case_type_label
                cand_out["type_rank"] = type_rank
                if override:
                    cand_out["selection_note"] = override.get("selection_note", str(cand_out.get("selection_note", "")))
                    cand_out["case_analysis_note"] = override.get(
                        "case_analysis_note",
                        override.get("selection_note", str(cand_out.get("selection_note", ""))),
                    )
                else:
                    cand_out["case_analysis_note"] = str(cand_out.get("selection_note", ""))
                typed_rows.append(cand_out)
                used_case_keys.add(key)
                added += 1
                if added >= max_candidates:
                    break

        story_1 = remark_case_candidates[
            (~remark_case_candidates["has_no_output_note"])
            & (remark_case_candidates["has_info_gap_note"])
            & remark_case_candidates["remark_text_all"].astype(str).str.contains("活检|MRI|HPV|TCT|B超", regex=True)
            & (remark_case_candidates["human_mean"].fillna(0) >= 4.0)
        ].copy()
        story_1 = _ensure_story_candidates(story_1, all_case_candidates, [("新疆", "gemini-2.5p", "Xinjiang_093")])
        story_1 = story_1.sort_values(
            ["human_mean", "candidate_score", "result_abs_delta_max"],
            ascending=[False, False, False],
            kind="mergesort",
        )
        story_1 = _prioritize_story_candidates(
            story_1,
            preferred_keys=[("新疆", "gemini-2.5p", "Xinjiang_093")],
            sort_cols=["human_mean", "candidate_score", "result_abs_delta_max"],
            ascending=[False, False, False],
        )
        story_1["selection_note"] = story_1.apply(
            lambda r: (
                f"该例适合展示“信息不足时先补关键证据，再完成诊断修正”。"
                f"医生结果均分={_fmt_case_metric(r.get('human_mean'))}，Judge均分={_fmt_case_metric(r.get('judge_mean'))}。"
            ),
            axis=1,
        ) if not story_1.empty else ""
        _append_type(
            story_1,
            case_type="STORY_1",
            case_type_order=1,
            case_type_label="主例 1: 信息不足时先补证据再定诊",
            max_candidates=1,
        )

        story_2 = remark_case_candidates[
            remark_case_candidates["remark_text_all"].astype(str).str.contains("无术后病理|不能诊断", regex=True)
        ].copy()
        story_2 = _ensure_story_candidates(story_2, all_case_candidates, [("武汉", "deepseek-v3", "wuhan_33")])
        story_2 = story_2.sort_values(
            ["candidate_score", "result_abs_delta_max", "human_mean"],
            ascending=[False, False, False],
            kind="mergesort",
        )
        story_2 = _prioritize_story_candidates(
            story_2,
            preferred_keys=[("武汉", "deepseek-v3", "wuhan_33")],
            sort_cols=["candidate_score", "result_abs_delta_max", "human_mean"],
            ascending=[False, False, False],
        )
        story_2["selection_note"] = story_2.apply(
            lambda r: "该例适合展示“关键病理缺失时，AI仍将可疑病变写成最终诊断”的逻辑风险。",
            axis=1,
        ) if not story_2.empty else ""
        _append_type(
            story_2,
            case_type="STORY_2",
            case_type_order=2,
            case_type_label="主例 2: 缺病理证据却提前下最终诊断",
            max_candidates=1,
        )

        story_3 = all_case_candidates[
            all_case_candidates["flow_end_stage"].astype(str).str.contains("D2", regex=False)
        ].copy()
        story_3 = _ensure_story_candidates(story_3, all_case_candidates, [("佛山", "claude-4.1", "foshan_19")])
        story_3 = story_3.sort_values(
            ["candidate_score", "human_mean", "result_abs_delta_max"],
            ascending=[False, False, False],
            kind="mergesort",
        )
        story_3 = _prioritize_story_candidates(
            story_3,
            preferred_keys=[("佛山", "claude-4.1", "foshan_19")],
            sort_cols=["candidate_score", "human_mean", "result_abs_delta_max"],
            ascending=[False, False, False],
        )
        story_3["selection_note"] = story_3.apply(
            lambda r: (
                f"该例适合展示“D2 住院决策阶段发生失败级联并在 Gate 2 被终止”。"
                f"Gate1={_fmt_case_metric(r.get('gate1_overall_score'))}，Gate2={_fmt_case_metric(r.get('gate2_overall_score'))}。"
            ),
            axis=1,
        ) if not story_3.empty else ""
        _append_type(
            story_3,
            case_type="STORY_3",
            case_type_order=3,
            case_type_label="主例 3: D2失败级联导致流程终止",
            max_candidates=1,
        )

        story_4 = remark_case_candidates[
            (~remark_case_candidates["has_no_output_note"])
            & remark_case_candidates["remark_text_all"].astype(str).str.contains(
                "缺B超结果|无法得出宫腔积液诊断|案例无法评价|经阴道超声",
                regex=True,
            )
        ].copy()
        story_4 = _ensure_story_candidates(story_4, all_case_candidates, [("武汉", "claude-4.1", "wuhan_42")])
        story_4 = story_4.sort_values(
            ["candidate_score", "human_mean", "result_abs_delta_max"],
            ascending=[False, False, False],
            kind="mergesort",
        )
        story_4 = _prioritize_story_candidates(
            story_4,
            preferred_keys=[("武汉", "claude-4.1", "wuhan_42")],
            sort_cols=["candidate_score", "human_mean", "result_abs_delta_max"],
            ascending=[False, False, False],
        )
        story_4["selection_note"] = story_4.apply(
            lambda r: "该例适合展示“关键影像不可得时，AI不应反复索要已被标记为不可得的检查并越界判断”。",
            axis=1,
        ) if not story_4.empty else ""
        _append_type(
            story_4,
            case_type="STORY_4",
            case_type_order=4,
            case_type_label="扩展示例 1: 关键影像缺失时的诊断边界",
            max_candidates=1,
        )

        story_5 = remark_case_candidates[
            remark_case_candidates["remark_text_all"].astype(str).str.contains("子宫纵隔不需要手术|手术方式不正确", regex=True)
        ].copy()
        story_5 = _ensure_story_candidates(story_5, all_case_candidates, [("武汉", "claude-4.1", "wuhan_13")])
        story_5 = story_5.sort_values(
            ["candidate_score", "human_mean", "result_abs_delta_max"],
            ascending=[False, False, False],
            kind="mergesort",
        )
        story_5 = _prioritize_story_candidates(
            story_5,
            preferred_keys=[("武汉", "claude-4.1", "wuhan_13")],
            sort_cols=["candidate_score", "human_mean", "result_abs_delta_max"],
            ascending=[False, False, False],
        )
        story_5["selection_note"] = story_5.apply(
            lambda r: "该例适合展示“多个可疑病灶被一次性打包手术处理”的方案扩大化风险。",
            axis=1,
        ) if not story_5.empty else ""
        _append_type(
            story_5,
            case_type="STORY_5",
            case_type_order=5,
            case_type_label="扩展示例 2: 多病灶打包手术扩大化",
            max_candidates=1,
        )

        story_6 = remark_case_candidates[
            remark_case_candidates["remark_text_all"].astype(str).str.contains("激素替代治疗|孕激素|没有子宫", regex=True)
        ].copy()
        story_6 = _ensure_story_candidates(story_6, all_case_candidates, [("武汉", "grok-4", "wuhan_5")])
        story_6 = story_6.sort_values(
            ["candidate_score", "human_mean", "result_abs_delta_max"],
            ascending=[False, False, False],
            kind="mergesort",
        )
        story_6 = _prioritize_story_candidates(
            story_6,
            preferred_keys=[("武汉", "grok-4", "wuhan_5")],
            sort_cols=["candidate_score", "human_mean", "result_abs_delta_max"],
            ascending=[False, False, False],
        )
        story_6["selection_note"] = story_6.apply(
            lambda r: "该例适合展示“诊断未必错误，但术后长期管理建议偏离临床原则”的负例。",
            axis=1,
        ) if not story_6.empty else ""
        _append_type(
            story_6,
            case_type="STORY_6",
            case_type_order=6,
            case_type_label="扩展示例 3: 术后长期管理建议偏离",
            max_candidates=1,
        )

        if len(typed_rows) < 6:
            story_7 = all_case_candidates[
                all_case_candidates["flow_end_stage"].astype(str).eq("D2_Admission_Decision")
            ].copy()
            story_7 = story_7.sort_values(
                ["candidate_score", "result_abs_delta_max", "critical_keyword_count"],
                ascending=[False, False, False],
                kind="mergesort",
            )
            story_7["selection_note"] = story_7.apply(
                lambda r: (
                    f"该例用于补充展示 D2 失败级联：gate1={_fmt_case_metric(r.get('gate1_overall_score'))}，"
                    f"gate2={_fmt_case_metric(r.get('gate2_overall_score'))}。"
                ),
                axis=1,
            ) if not story_7.empty else ""
            _append_type(
                story_7,
                case_type="STORY_7",
                case_type_order=7,
                case_type_label="Story 7: D2失败导致流程截断",
                max_candidates=2,
            )

        typed_case_candidates = (
            pd.DataFrame(typed_rows).reset_index(drop=True)
            if typed_rows
            else all_case_candidates.head(6).assign(
                case_type="MISC",
                case_type_order=99,
                case_type_label="Story M: 高价值补充病例",
                type_rank=np.arange(1, min(6, len(all_case_candidates)) + 1),
                selection_note="高价值备注与分差病例，用于补充展示。",
            )
        )
    else:
        typed_case_candidates = case_candidates.copy()
    selected_cases, trace_snippets = _build_case_study_with_traces(typed_case_candidates, remarks, top_n=6)

    out_human_png = OUT_FIG_DIR / group / "A0_human_machine_consistency_summary_v1.png"
    out_doctor_png = OUT_FIG_DIR / group / "A0_doctor_doctor_consistency_summary_v1.png"
    _save_table_png(human_machine_paper, out_human_png, "A0-A 人机一致性总表（五模型合并）")
    _save_table_png(doctor_doctor_paper, out_doctor_png, "A0-B 人人一致性总表（五模型合并）")

    summary_md = OUT_FIG_DIR / group / "A0_论文结论摘要.md"
    hm_mae_col = "MAE\n(结果)"
    hm_exact_col = "完全一致率\n(结果)"
    dd_mae_col = "平均绝对差\n(结果)"
    dd_exact_col = "完全一致率\n(结果)"
    hm_best = human_machine_paper.sort_values(hm_mae_col, ascending=True).head(1)
    hm_worst = human_machine_paper.sort_values(hm_mae_col, ascending=False).head(1)
    dd_best = doctor_doctor_paper.sort_values(dd_mae_col, ascending=True).head(1)
    dd_worst = doctor_doctor_paper.sort_values(dd_mae_col, ascending=False).head(1)
    hm_best_txt = (
        f"{hm_best.iloc[0]['环节']}：MAE={float(hm_best.iloc[0][hm_mae_col]):.3f}，"
        f"完全一致率={float(hm_best.iloc[0][hm_exact_col]):.1f}%"
        if not hm_best.empty
        else "暂无"
    )
    hm_worst_txt = (
        f"{hm_worst.iloc[0]['环节']}：MAE={float(hm_worst.iloc[0][hm_mae_col]):.3f}，"
        f"完全一致率={float(hm_worst.iloc[0][hm_exact_col]):.1f}%"
        if not hm_worst.empty
        else "暂无"
    )
    dd_best_txt = (
        f"{dd_best.iloc[0]['环节']}：平均绝对差={float(dd_best.iloc[0][dd_mae_col]):.3f}，"
        f"完全一致率={float(dd_best.iloc[0][dd_exact_col]):.1f}%"
        if not dd_best.empty
        else "暂无"
    )
    dd_worst_txt = (
        f"{dd_worst.iloc[0]['环节']}：平均绝对差={float(dd_worst.iloc[0][dd_mae_col]):.3f}，"
        f"完全一致率={float(dd_worst.iloc[0][dd_exact_col]):.1f}%"
        if not dd_worst.empty
        else "暂无"
    )
    summary_lines = [
        "# A0 论文结论摘要",
        "",
        "说明：以下两张主表均为 `五模型合并 + 全中心汇总 + 决策环节口径`，只保留 D1-D4 的主要临床决策阶段，适合直接放入正文。",
        "",
        "## 人机一致性",
        "- 指标定义：MAE 越小越好；完全一致率与 ±1分一致率越高越好。",
        "- 表格文件：`A0_human_machine_consistency_summary_v1.png`",
        "",
        "## 人人一致性",
        "- 指标定义：平均绝对差越小越好；完全一致率与 ±1分一致率越高越好。",
        "- 表格文件：`A0_doctor_doctor_consistency_summary_v1.png`",
        "",
        "## 可直接写进论文的结论",
        f"- 人机一致性最好环节：{hm_best_txt}",
        f"- 人机一致性最弱环节：{hm_worst_txt}",
        f"- 医生间一致性最好环节：{dd_best_txt}",
        f"- 医生间一致性最弱环节：{dd_worst_txt}",
        "- 当前数据下，D4 通常更容易获得较高一致性，而 D2 住院环节更容易成为人机分歧集中区，适合在正文讨论其原因。",
        "",
        "## 结果解释建议",
        "- 正文优先引用 D1-D4 四环节趋势，不建议再次拆成五模型大表。",
        "- `门诊检查/住院检查` 一致性已从主表剥离，作为 supplementary 表展示，避免把“信息获取积极性”误写成“回复质量”。",
        "- 一致性指标现已统一为“先二值化再计算旧指标”口径（0-2 vs 3-5），可在 source workbook 的 `指标汇总_主表口径`、`指标汇总_决策环节`、`明细_决策二值化` 中直接选取论文主指标。",
        "- source workbook 已精简为论文写作必需表，减少中间过程表对阅读的干扰。",
    ]
    summary_md.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    supple_dir = OUT_SUPPLE_DIR / group
    supple_fig_dir = supple_dir / "figures"
    supple_source_dir = supple_dir / "source_data"
    supple_trace_dir = supple_dir / "traces"
    supple_fig_dir.mkdir(parents=True, exist_ok=True)
    supple_source_dir.mkdir(parents=True, exist_ok=True)
    selected_cases, trace_snippets, trace_manifest, trace_cards_full = _materialize_case_study_traces(
        selected_cases,
        trace_snippets,
        supple_trace_dir,
    )
    out_human_check_png = supple_fig_dir / "A0_human_machine_check_consistency_supp_v1.png"
    out_doctor_check_png = supple_fig_dir / "A0_doctor_doctor_check_consistency_supp_v1.png"
    _save_table_png(human_machine_check_paper, out_human_check_png, "A0-S1 检查环节人机一致性（补充）")
    _save_table_png(doctor_doctor_check_paper, out_doctor_check_png, "A0-S2 检查环节人人一致性（补充）")
    for p in supple_fig_dir.glob("*.png"):
        if p.name not in {out_human_check_png.name, out_doctor_check_png.name}:
            try:
                p.unlink()
            except Exception:
                pass
    case_study_html = supple_dir / "A0_案例研究_supplement.html"
    _write_case_study_html(selected_cases, trace_snippets, remarks, case_study_html)
    legacy_case_md = supple_dir / "A0_案例研究_supplement.md"
    if legacy_case_md.exists():
        try:
            legacy_case_md.unlink()
        except Exception:
            pass
    check_supple_xlsx = supple_source_dir / "A0_check_consistency_supplement_v1.xlsx"
    hm_check_paper_zh = _zh_localize_a0_frame(human_machine_check_paper)
    doc_check_paper_zh = _zh_localize_a0_frame(doctor_doctor_check_paper)
    decision_metric_suite_zh = _zh_localize_a0_frame(decision_metric_suite)
    check_metric_suite_zh = _zh_localize_a0_frame(check_metric_suite)
    metric_suite_key_zh = _zh_localize_a0_frame(metric_suite_key)
    binary_check_detail_zh = _zh_localize_a0_frame(binary_detail_check_all)
    with pd.ExcelWriter(check_supple_xlsx, engine="openpyxl") as writer:
        hm_check_paper_zh.to_excel(writer, sheet_name="检查_人机一致性", index=False)
        doc_check_paper_zh.to_excel(writer, sheet_name="检查_人人一致性", index=False)
        decision_metric_suite_zh.to_excel(writer, sheet_name="指标汇总_决策环节", index=False)
        check_metric_suite_zh.to_excel(writer, sheet_name="指标汇总_检查环节", index=False)
        metric_suite_key_zh.to_excel(writer, sheet_name="指标汇总_主表口径", index=False)
        binary_check_detail_zh.to_excel(writer, sheet_name="明细_检查二值化", index=False)
    _style_workbook(check_supple_xlsx)
    case_study_xlsx = supple_source_dir / "A0_case_studies_supplement_v1.xlsx"
    with pd.ExcelWriter(case_study_xlsx, engine="openpyxl") as writer:
        selected_cases.to_excel(writer, sheet_name="selected_cases", index=False)
        trace_manifest.to_excel(writer, sheet_name="trace_manifest", index=False)
        trace_snippets.to_excel(writer, sheet_name="trace_snippets", index=False)
        trace_cards_full.to_excel(writer, sheet_name="trace_cards_full", index=False)
        typed_case_candidates.to_excel(writer, sheet_name="typed_cases", index=False)
        all_case_candidates.head(120).to_excel(writer, sheet_name="candidate_pool_top120", index=False)
    _style_workbook(case_study_xlsx)
    supple_caption = _write_single_caption_file(
        supple_dir,
        "图注_Figure_A0_补充材料.md",
        [
            "# Figure A0 补充材料图注",
            "",
            "- `A0_human_machine_check_consistency_supp_v1.png`：将 D1 门诊检查与 D2 住院检查从主表剥离，单独展示“模型 vs 专家”的一致性指标。",
            "- `A0_doctor_doctor_check_consistency_supp_v1.png`：对应展示“专家 vs 专家”的检查环节一致性，用于验证医生间对检查积极性的评价稳定性。",
            "- `A0_案例研究_supplement.html`：优先展示 3 个与手稿主论点对齐的主例（信息不足但路径稳健 / 缺病理仍下最终诊断 / D2失败级联），并附 3 个扩展示例。每例整合流程时间线、评分差、医生备注与 trace 证据折叠块，并直接链接到同目录 `traces/` 中复制保存的原始 trace html。",
            "- `A0_check_consistency_supplement_v1.xlsx`：已精简为中文可读版本，仅保留检查环节总表、指标汇总（决策/检查/主表口径）和检查环节二值化明细。",
            "- `A0_case_studies_supplement_v1.xlsx`：提供案例研究的 narrative candidate pool、最终入选病例、trace manifest、关键片段与全文卡片追溯，便于核对筛选来源并进一步人工分析。",
        ],
    )

    a0_source_sheets = {
        "paper_hm_decision": _zh_localize_a0_frame(human_machine_paper),
        "paper_doc_decision": _zh_localize_a0_frame(doctor_doctor_paper),
        "paper_hm_check": _zh_localize_a0_frame(human_machine_check_paper),
        "paper_doc_check": _zh_localize_a0_frame(doctor_doctor_check_paper),
        "metric_suite_key": _zh_localize_a0_frame(metric_suite_key),
        "metric_suite_decision": _zh_localize_a0_frame(decision_metric_suite),
        "metric_suite_check": _zh_localize_a0_frame(check_metric_suite),
        "binary_decision_detail": _zh_localize_a0_frame(binary_detail_decision_all),
        "binary_check_detail": _zh_localize_a0_frame(binary_detail_check_all),
    }
    a0_sheet_alias = {
        "paper_hm_decision": "正文_人机一致性总表",
        "paper_doc_decision": "正文_人人一致性总表",
        "paper_hm_check": "补充_检查人机一致性",
        "paper_doc_check": "补充_检查人人一致性",
        "metric_suite_key": "指标汇总_主表口径",
        "metric_suite_decision": "指标汇总_决策环节",
        "metric_suite_check": "指标汇总_检查环节",
        "binary_decision_detail": "明细_决策二值化",
        "binary_check_detail": "明细_检查二值化",
        "meta": "元信息",
    }
    source_path = _write_source_workbook(
        group=group,
        stem="A0_consistency_tables_v2",
        sheets=a0_source_sheets,
        meta={
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "description": "A0 一致性 source data（精简版）：仅保留论文写作必需的总表、指标汇总和二值化明细；全部表头中文化。",
            "sheet_name_alias": a0_sheet_alias,
            "source_col_name": "数据来源",
            "meta_key_col": "键",
            "meta_value_col": "值",
            "source_human_judge_result": "analysis_viz/data/derived/metrics/alignment/alignment_result_vs_judge_case_level_source.xlsx",
            "source_human_judge_reasoning": "analysis_viz/data/derived/metrics/alignment/alignment_reasoning_vs_llm_case_level_source.xlsx",
            "source_doctor_consensus_result": "analysis_viz/data/derived/metrics/alignment/alignment_doctor_consensus_result_source.xlsx",
            "source_doctor_consensus_reasoning": "analysis_viz/data/derived/metrics/alignment/alignment_doctor_consensus_reasoning_source.xlsx",
            "source_doctor_raw": "analysis_viz/data/raw/doctor_eval_results/*/*.xlsx",
            "rule_d1_gate3": "D1异常样本剔除；Gate3 fail 不计入 D4 计算",
            "rule_binary_mapping": "0-2 => 临床不显著；3-5 => 临床显著",
            "metric_suite_binary_first": "先二值化(0-2/3-5)，再计算 MAE, RMSE, ExactRate, Within1Rate, Pearson, Spearman, QWK",
            "table_policy": "主文仅看 D1-D4 决策环节；检查环节单列补充表",
        },
    )
    _write_caption(
        group,
        [
            "# A0 一致性与案例研究图注",
            "",
            "- `A0_human_machine_consistency_summary_v1.png`：论文友好的人机一致性主表，仅保留 D1-D4 决策阶段，并已将五个模型与三中心统一汇总。",
            "- `A0_doctor_doctor_consistency_summary_v1.png`：论文友好的人人一致性主表，口径与上表一致，仅保留 D1-D4 决策阶段。",
            "- `A0_consistency_tables_v2_source.xlsx`：已精简为论文写作版 source data，仅保留正文/补充总表、指标汇总与二值化明细，并统一中文表头。",
            "- 案例候选优先级依据：优先满足手稿主例需求（信息不足但路径稳健 / 缺病理仍下最终诊断 / D2失败级联），其余再补充过度治疗或术后管理偏离等扩展示例。",
        ],
    )

    hm_metric_suite_all = (
        metric_suite_all[metric_suite_all["comparator"].astype(str) == "human_vs_judge"].copy()
        if ("comparator" in metric_suite_all.columns and not metric_suite_all.empty)
        else pd.DataFrame()
    )
    doc_metric_suite_all = (
        metric_suite_all[metric_suite_all["comparator"].astype(str) == "doctor_vs_doctor"].copy()
        if ("comparator" in metric_suite_all.columns and not metric_suite_all.empty)
        else pd.DataFrame()
    )

    LIVING_REVISION_DIR.mkdir(parents=True, exist_ok=True)
    human_table = LIVING_REVISION_DIR / "human_judge_consistency_table_v1.xlsx"
    with pd.ExcelWriter(human_table, engine="openpyxl") as writer:
        human_machine_paper.to_excel(writer, sheet_name="论文总表_中文", index=False)
        human_machine_check_paper.to_excel(writer, sheet_name="检查环节_中文补充表", index=False)
        hm_result_model_paper.to_excel(writer, sheet_name="结果_模型x环节", index=False)
        hm_reason_model_paper.to_excel(writer, sheet_name="推理_模型x环节", index=False)
        result_summary.to_excel(writer, sheet_name="result_all_stage6", index=False)
        result_stage_overall.to_excel(writer, sheet_name="result_decision_stage_overall", index=False)
        reason_summary.to_excel(writer, sheet_name="reason_all_stage6", index=False)
        reason_stage_overall.to_excel(writer, sheet_name="reason_decision_stage_overall", index=False)
        hm_metric_suite_all.to_excel(writer, sheet_name="metric_suite_hm", index=False)
        case_candidates.head(80).to_excel(writer, sheet_name="case_candidates_top80", index=False)
    _style_workbook(human_table)

    doctor_table = LIVING_REVISION_DIR / "doctor_interrater_consistency_table_v1.xlsx"
    with pd.ExcelWriter(doctor_table, engine="openpyxl") as writer:
        doctor_doctor_paper.to_excel(writer, sheet_name="论文总表_中文", index=False)
        doctor_doctor_check_paper.to_excel(writer, sheet_name="检查环节_中文补充表", index=False)
        doc_result_model_paper.to_excel(writer, sheet_name="结果_模型x环节", index=False)
        doc_reason_model_paper.to_excel(writer, sheet_name="推理_模型x环节", index=False)
        cons_result_summary.to_excel(writer, sheet_name="result_all_stage6", index=False)
        cons_result_stage_overall.to_excel(writer, sheet_name="result_decision_stage_overall", index=False)
        cons_reason_summary.to_excel(writer, sheet_name="reason_all_stage6", index=False)
        cons_reason_stage_overall.to_excel(writer, sheet_name="reason_decision_stage_overall", index=False)
        doc_metric_suite_all.to_excel(writer, sheet_name="metric_suite_doc", index=False)
        case_summary.to_excel(writer, sheet_name="multi_doctor_case_summary", index=False)
    _style_workbook(doctor_table)

    case_csv = ANALYSIS_VIZ / "docs" / "formula_audit" / "example_case_candidates_from_S1.csv"
    case_csv.parent.mkdir(parents=True, exist_ok=True)
    case_candidates.to_csv(case_csv, index=False, encoding="utf-8-sig")

    _archive_group_outputs(
        group=group,
        keep_fig_names={out_human_png.name, out_doctor_png.name},
        keep_source_names={source_path.name},
    )
    return {
        "source": source_path,
        "figure_human_machine": out_human_png,
        "figure_doctor_doctor": out_doctor_png,
        "summary_md": summary_md,
        "living_human_table": human_table,
        "living_doctor_table": doctor_table,
        "case_candidates_csv": case_csv,
        "supple_check_human": out_human_check_png,
        "supple_check_doctor": out_doctor_check_png,
        "supple_check_source": check_supple_xlsx,
        "supple_case_html": case_study_html,
        "supple_case_source": case_study_xlsx,
        "supple_caption": supple_caption,
    }


def _style_v3_docs(output_paths: dict[str, dict[str, Path]]) -> None:
    """更新本轮可读文档与变更摘要（中文可读）。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    todo_csv = ANALYSIS_VIZ / "给用户看" / "todo_v3_图像改进跟踪.csv"
    todo_csv.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "任务": "S1 judge评分口径重算",
            "状态": "完成",
            "备注": "D1/D2 loop与D1决策按center_data judge原始列重算并回填source",
            "更新时间": now,
        },
        {
            "任务": "G4主体布局与特例版本",
            "状态": "完成",
            "备注": "左侧Sankey主体化，新增special-case版本组图与对应子图",
            "更新时间": now,
        },
        {
            "任务": "G1/G2 PALM-COEIN扩展图",
            "状态": "完成",
            "备注": "新增九分类分布、阶段变化与G2分层诊断表现图",
            "更新时间": now,
        },
        {
            "任务": "A0论文一致性总表",
            "状态": "完成",
            "备注": "新增中文论文友好总表：人机一致性、人人一致性，均按3中心×4环节且五模型合并",
            "更新时间": now,
        },
        {
            "任务": "G4 supplementary整理",
            "状态": "完成",
            "备注": "主文外的special case、阶段校准与效率补充图复制到 _supplementary 目录，并保留source data",
            "更新时间": now,
        },
    ]
    pd.DataFrame(rows).to_csv(todo_csv, index=False, encoding="utf-8-sig")

    summary_md = ANALYSIS_VIZ / "给用户看" / "09_v3图像改进说明_2026-02-12.md"
    lines: list[str] = [
        "# 09 v3图像改进说明（2026-02-12）",
        "",
        f"更新时间：{now}",
        "",
        "## 本轮完成（v6/v7 定版与归档）",
        "- G2：诊断质量改为语义化阶段标签（初始/修正/最终），新增 PALM 九分类鲁棒性与良恶性替代方案双版本；检查效率同时提供“按轮次”和“门诊/住院合并”两版。",
        "- G3：负面事件图改为“平均每例每阶段事件数”，并在图注中明确记忆/事实一致性/推理三维定义与评审来源。",
        "- G4：主文定版固定为 `Sankey + B0总体校准 + C2检查效率`；D1 决策检查并入住院检查口径，特殊情况仅保留附录链路。",
        "- A0：新增两张可直接放论文的中文总表，分别对应人机一致性与医生间一致性，均按中心×四阶段汇总并合并五模型。",
        "- 归档：非定版/历史方案图与对应 source workbook 已迁移至各组 `archive/`，并按 sheet 拆分到 `archive/source_data/sheets/` 便于回溯。",
        "",
        "## 本轮关键图",
        "- `analysis_viz/figures/v2_subplots/G2_outcome/G2_outcome_metrics_v6.png`",
        "- `analysis_viz/figures/v2_subplots/G2_outcome/G2_outcome_metrics_alt_bm_v3.png`",
        "- `analysis_viz/figures/v2_subplots/G3_continuity/G3_continuity_metrics_v4.png`",
        "- `analysis_viz/figures/v2_subplots/G4_system/G4_groupD_sankey_calib_efficiency_v7.png`",
        "- `analysis_viz/figures/v2_subplots/S1_manual_vs_llm/S1_manual_vs_llm_stacked_v4.png`",
        "",
        "## 对应 source data",
        "- `analysis_viz/data/derived/figdata/v2_subplots/G2_outcome/G2_outcome_metrics_v6_source.xlsx`",
        "- `analysis_viz/data/derived/figdata/v2_subplots/G3_continuity/G3_continuity_metrics_v4_source.xlsx`",
        "- `analysis_viz/data/derived/figdata/v2_subplots/G4_system/G4_system_metrics_v2_source.xlsx`",
        "- `analysis_viz/data/derived/figdata/v2_subplots/S1_manual_vs_llm/S1_manual_vs_llm_v6_source.xlsx`",
        "",
        "## 产物总览",
    ]
    for g, m in output_paths.items():
        lines.append(f"- **{g}**")
        for k, p in m.items():
            rel = p.relative_to(ROOT).as_posix() if p.exists() else p.as_posix()
            lines.append(f"  - {k}: `{rel}`")
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_progress_docs(outputs: dict[str, dict[str, Path]]) -> None:
    progress_csv = ANALYSIS_VIZ / "给用户看" / "任务进度跟踪.csv"
    progress_csv.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = [
        {
            "任务": "v2组图与子图生成（G1/G2/G3/G4/S1）",
            "状态": "已完成",
            "说明": f"{now} 已输出先子图后组图的新版本，并保留原图不覆盖。",
            "关联文件": "analysis_viz/figures/v2_subplots",
        },
        {
            "任务": "v2 source data 一图一表",
            "状态": "已完成",
            "说明": "每图至少包含 detail+summary+meta，并补充规则说明与来源。",
            "关联文件": "analysis_viz/data/derived/figdata/v2_subplots",
        },
    ]
    old = pd.read_csv(progress_csv) if progress_csv.exists() else pd.DataFrame(columns=["任务", "状态", "说明", "关联文件"])
    task_names = {r["任务"] for r in rows}
    task_names.add("v2组图生成（G1/G2/G3/G4/S1）")
    old = old[~old["任务"].isin(task_names)].copy()
    merged = pd.concat([old, pd.DataFrame(rows)], ignore_index=True)
    merged.to_csv(progress_csv, index=False, encoding="utf-8-sig")

    summary_md = ANALYSIS_VIZ / "给用户看" / "06_v2组图与source数据说明.md"
    lines = [
        "# v2组图与source数据说明",
        "",
        f"生成时间：{now}",
        "",
        "## 输出目录",
        "- 图（含子图与组图）：`analysis_viz/figures/v2_subplots/`",
        "- 源数据：`analysis_viz/data/derived/figdata/v2_subplots/`",
        "",
        "## 本轮关键约束",
        "- `G2` 检查效率同时输出两版：按轮次（门诊/住院各 1-3 轮）与语义合并（门诊检查/住院检查）；住院检查口径包含 `D1决策检查` 并入。",
        "- `G3` 事件图采用归一化口径：`平均事件数 = 该阶段事件总数 / 该阶段样本数`。",
        "- `G4` 主文只保留 `B0总体校准`；特殊情况图仅作为附录，不纳入主图结论链路。",
        "- `D1 anomaly` 样本不参与计算；`Gate3 fail` 不计入 `D4` 计算。",
        "- 非定版与历史方案图统一归档到各组 `archive/`，对应 source workbook 与拆分 sheet 进入 `archive/source_data/`。",
        "",
        "## 产物清单",
    ]
    for g, m in outputs.items():
        lines.append(f"- **{g}**")
        for k, p in m.items():
            rel = p.relative_to(ROOT).as_posix() if p.exists() else p.as_posix()
            lines.append(f"  - {k}: `{rel}`")
    lines.extend(
        [
            "",
            "## 图注",
            "每个多图目录仅保留一个命名后的图注文件（如 `图注_Figure_G4_系统评估.md`），避免重复 caption 干扰追溯。",
        ]
    )
    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    index_md = ANALYSIS_VIZ / "docs" / "index.md"
    if index_md.exists():
        txt = index_md.read_text(encoding="utf-8")
        marker = "## 6) 参考原始脚本位置"
        insert = (
            "\n## 5.1) v2 组图与子图（新增）\n\n"
            "- 图目录：`analysis_viz/figures/v2_subplots/`\n"
            "- 源数据目录：`analysis_viz/data/derived/figdata/v2_subplots/`\n"
            "- 说明文档：`analysis_viz/给用户看/06_v2组图与source数据说明.md`\n"
            "- 生成脚本：`analysis_viz/scripts/wrappers/build_v2_subplots_bundle.py`\n\n"
        )
        if "v2 组图与子图（新增）" not in txt:
            if marker in txt:
                txt = txt.replace(marker, insert + marker)
            else:
                txt += "\n" + insert
            index_md.write_text(txt, encoding="utf-8")


def main() -> None:
    _apply_style()
    d1_set = _load_d1_anomaly_set()
    gate3_set = _load_gate3_fail_set()
    d2_rule_map = _load_d2_manual_rule_map()

    outputs: dict[str, dict[str, Path]] = {}
    outputs["G4_sankey_review"] = _write_sankey_special_case_report(d2_rule_map)
    outputs["G1_dataset"] = build_g1_dataset()
    outputs["G2_outcome"] = build_g2_outcome(d1_set, gate3_set, d2_rule_map)
    outputs["G3_continuity"] = build_g3_continuity(d2_rule_map)
    outputs["G4_system"] = build_g4_system(d1_set, gate3_set, d2_rule_map)
    outputs["S1_manual_vs_llm"] = build_s1_manual_vs_llm(d2_rule_map)
    outputs["A0_consistency_tables"] = _build_alignment_consistency_tables_and_case_studies(d1_set, gate3_set)

    update_progress_docs(outputs)
    _style_v3_docs(outputs)
    for group, files in outputs.items():
        print(f"[DONE] {group}")
        for name, path in files.items():
            print(f"  - {name}: {path}")


if __name__ == "__main__":
    main()

