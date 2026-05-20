"""Export Word-ready three-line tables for v2_subplots supplementary figures.

This script is intentionally independent from ``build_v2_subplots_bundle.py``.
It reads the already materialized source workbooks under
``analysis_viz/figures/v2_subplots/_supplementary`` and writes a single Word
document containing the tables that were previously rendered as PNGs.

The generated document uses a three-line style:
- no vertical borders
- top border on the header row
- bottom border on the header row
- bottom border on the last row

Best values are highlighted with light gray shading so that the table can be
copied directly into Word and still preserve the visual emphasis requested by
the paper draft.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt


ROOT = Path(__file__).resolve().parents[3]
A0_MAIN_XLSX = (
    ROOT
    / "analysis_viz"
    / "data"
    / "derived"
    / "figdata"
    / "v2_subplots"
    / "A0_consistency_tables"
    / "A0_consistency_tables_v1_source.xlsx"
)
A0_SUPPLE_XLSX = (
    ROOT
    / "analysis_viz"
    / "figures"
    / "v2_subplots"
    / "_supplementary"
    / "A0_consistency_tables"
    / "source_data"
    / "A0_check_consistency_supplement_v1.xlsx"
)
S1_SUPPLE_XLSX = (
    ROOT
    / "analysis_viz"
    / "figures"
    / "v2_subplots"
    / "_supplementary"
    / "S1_manual_vs_llm"
    / "source_data"
    / "S1_check_stage_tables_supplement_v1.xlsx"
)
G2_SOURCE_XLSX = (
    ROOT
    / "analysis_viz"
    / "data"
    / "derived"
    / "figdata"
    / "v2_subplots"
    / "G2_outcome"
    / "G2_outcome_metrics_v6_source.xlsx"
)
G3_SOURCE_XLSX = (
    ROOT
    / "analysis_viz"
    / "data"
    / "derived"
    / "figdata"
    / "v2_subplots"
    / "G3_continuity"
    / "G3_continuity_metrics_v4_source.xlsx"
)
GT_CENTER_ROOT = ROOT / "analysis_viz" / "data" / "raw" / "center_data"
SUPPLE_G4_XLSX = (
    ROOT
    / "analysis_viz"
    / "figures"
    / "v2_subplots"
    / "_supplementary"
    / "G4_system"
    / "source_data"
    / "G4B_stage_calibration_tables_supplement_v1.xlsx"
)
G4_SOURCE_XLSX = (
    ROOT
    / "analysis_viz"
    / "figures"
    / "v2_subplots"
    / "_supplementary"
    / "G4_system"
    / "source_data"
    / "G4_system_metrics_v2_source.xlsx"
)
OUT_DIR = ROOT / "论文" / "revision" / "living" / "v2_subplots_word_tables"
OUT_DOCX = OUT_DIR / "G4_v2_subplots_word_tables.docx"
OUT_MD = OUT_DIR / "G4_v2_subplots_word_tables.md"
OUT_SOURCE_DIR = OUT_DIR / "source_data"


@dataclass(frozen=True)
class HighlightRule:
    group_cols: tuple[str, ...]
    target_col: str
    mode: str  # max | min | min_abs


@dataclass(frozen=True)
class TableSpec:
    title: str
    source: Path | None = None
    sheet: str = ""
    column_order: tuple[str, ...] = ()
    column_labels: dict[str, str] = None
    numeric_format: dict[str, str] = None
    align_left_cols: tuple[str, ...] = ()
    sort_by: tuple[str, ...] = ()
    highlight_rules: tuple[HighlightRule, ...] = ()
    note: str = ""
    builder: Callable[[], pd.DataFrame] | None = None
    source_label: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "column_labels", self.column_labels or {})
        object.__setattr__(self, "numeric_format", self.numeric_format or {})


def _sheet_name(path: Path, sheet_idx: int) -> str:
    return pd.ExcelFile(path).sheet_names[sheet_idx]


def _scale_pct(value: float | int | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value) * 100.0


def _stage_sort_key(stage_label: str) -> int:
    order = {"D1": 1, "D2": 2, "D3": 3, "D4": 4}
    return order.get(str(stage_label), 99)


def _build_stage_core_metrics_table() -> pd.DataFrame:
    OUT_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    g2_diag = pd.read_excel(G2_SOURCE_XLSX, sheet_name=7)
    g2_plan = pd.read_excel(G2_SOURCE_XLSX, sheet_name=11)
    g2_check = pd.read_excel(G2_SOURCE_XLSX, sheet_name=9)
    g2_ineff = pd.read_excel(G2_SOURCE_XLSX, sheet_name=10)
    g3_mem = pd.read_excel(G3_SOURCE_XLSX, sheet_name=5)
    g3_cons = pd.read_excel(G3_SOURCE_XLSX, sheet_name=6)
    g3_reason = pd.read_excel(G3_SOURCE_XLSX, sheet_name=7)
    g3_cons_detail = pd.read_excel(G3_SOURCE_XLSX, sheet_name=1)

    diag_map = (
        g2_diag.groupby("stage", as_index=False)["value"]
        .mean()
        .assign(stage4=lambda d: d["stage"].map({"D1_Decision": "D1", "D2_Decision": "D2", "D3_Decision": "D3"}))
        .dropna(subset=["stage4"])
        .set_index("stage4")["value"]
        .to_dict()
    )
    plan_map = (
        g2_plan.groupby("stage", as_index=False)["value"]
        .mean()
        .assign(stage4=lambda d: d["stage"].map({"D2_Decision": "D2", "D3_Decision": "D3", "D4_Plan": "D4"}))
        .dropna(subset=["stage4"])
        .set_index("stage4")["value"]
        .to_dict()
    )
    check_map = (
        g2_check.groupby("stage", as_index=False)["check_score"]
        .mean()
        .assign(stage4=lambda d: d["stage"].map({"D1_Loop": "D1", "D2_Check_Merged": "D2"}))
        .dropna(subset=["stage4"])
        .set_index("stage4")["check_score"]
        .to_dict()
    )
    ineff_map = (
        g2_ineff.groupby("stage", as_index=False)["ineff_rate"]
        .mean()
        .assign(stage4=lambda d: d["stage"].map({"D1_Loop": "D1", "D2_Check_Merged": "D2"}))
        .dropna(subset=["stage4"])
        .set_index("stage4")["ineff_rate"]
        .to_dict()
    )
    mem_map = g3_mem.groupby("stage", as_index=False)["memory_composite_0_1"].mean().set_index("stage")["memory_composite_0_1"].to_dict()
    cons_map = g3_cons.groupby("stage", as_index=False)["consistency_score_0_1"].mean().set_index("stage")["consistency_score_0_1"].to_dict()
    reason_map = (
        g3_reason.groupby("stage", as_index=False)["reasoning_score_1_5_adj"]
        .mean()
        .set_index("stage")["reasoning_score_1_5_adj"]
        .to_dict()
    )
    stage_n_map = (
        g3_cons_detail.assign(case_key=lambda d: d["center"].astype(str) + "::" + d["case_id"].astype(str))
        .groupby("stage4")["case_key"]
        .nunique()
        .to_dict()
    )

    rows: list[dict[str, object]] = []
    for stage in ["D1", "D2", "D3", "D4"]:
        rows.append(
            {
                "stage4": stage,
                "sample_n": stage_n_map.get(stage),
                "diagnosis_accuracy_pct": _scale_pct(diag_map.get(stage)),
                "plan_accuracy_pct": _scale_pct(plan_map.get(stage)),
                "check_quality_pct": _scale_pct(check_map.get(stage)),
                "ineff_rate_pct": _scale_pct(ineff_map.get(stage)),
                "memory_composite_pct": _scale_pct(mem_map.get(stage)),
                "consistency_composite_pct": _scale_pct(cons_map.get(stage)),
                "reasoning_quality_score": reason_map.get(stage),
            }
        )

    df = pd.DataFrame(rows).sort_values("stage4", key=lambda s: s.map(_stage_sort_key)).reset_index(drop=True)
    (
        df.rename(
            columns={
                "stage4": "阶段",
                "sample_n": "样本量",
                "diagnosis_accuracy_pct": "诊断正确性(%)",
                "plan_accuracy_pct": "方案正确性(%)",
                "check_quality_pct": "检查质量(%)",
                "ineff_rate_pct": "无效循环率(%)",
                "memory_composite_pct": "记忆综合分(%)",
                "consistency_composite_pct": "一致性综合分(%)",
                "reasoning_quality_score": "推理质量分(1-5)",
            }
        )
        .to_csv(OUT_SOURCE_DIR / "stage_core_metrics_table.csv", index=False, encoding="utf-8-sig")
    )
    return df


def _build_gt_patient_column_glossary() -> pd.DataFrame:
    OUT_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    glossary = {
        "BasicInfo": ("基本信息", "患者基线", "记录年龄、生育史、婚育情况、转诊背景等基础资料。", "提供后续全部推理的起点约束。"),
        "ChiefComplaint": ("主诉", "门诊首诊", "概括患者首次就诊时最核心的不适与求诊目的。", "定义门诊问诊与初步诊断的入口问题。"),
        "PresentIllness": ("现病史", "门诊首诊", "描述本次疾病的发展过程、持续时间、诱因、伴随症状及既往处理。", "把静态主诉扩展为时间连续的症状轨迹。"),
        "PastHistory": ("既往史", "患者基线", "汇总既往疾病、手术、用药及重要合并症。", "为鉴别诊断与方案风险评估提供长期背景。"),
        "MenstrualHistory": ("月经史", "患者基线", "记录周期、经量、痛经及异常出血等妇科专科信息。", "连接症状表型与妇科疾病机制。"),
        "FamilyHistory": ("家族史", "患者基线", "记录家族中相关肿瘤、遗传病或相似病史。", "补充遗传与风险分层线索。"),
        "PhysicalExam": ("体格检查", "门诊首诊", "记录查体与妇科检查发现。", "将主观症状延伸为客观体征证据。"),
        "GT_Outpatient_Checks": ("门诊检查金标准", "门诊检查", "给出门诊阶段应完成或已完成的辅助检查、检验及影像学信息。", "体现从首诊信息到检查证据的第一次扩展。"),
        "GT_Admission_Diagnosis": ("入院初步诊断金标准", "入院决策", "记录门诊后进入住院阶段时的初步诊断判断。", "标记门诊信息向住院管理的过渡节点。"),
        "GT_Admission_Checks": ("入院检查金标准", "住院检查", "记录住院后为手术评估或诊断修正而增加的检查。", "体现住院阶段继续补充证据的连续过程。"),
        "GT_Revised_Diagnosis": ("修正诊断金标准", "住院决策", "整合住院新证据后形成的修正诊断。", "反映检查结果如何回流并改变诊断结论。"),
        "GT_Surgery_Plan": ("手术/治疗方案金标准", "治疗决策", "记录最终采取的手术或核心治疗路径。", "把诊断结论落实为可执行处置方案。"),
        "GT_PostOp_Plan": ("术后处理计划金标准", "术后管理", "记录围手术期后的即时处理与用药安排。", "延续治疗闭环，体现短期管理连续性。"),
        "GT_Rehab_Plan": ("康复计划金标准", "康复阶段", "记录恢复期康复、生活方式与功能恢复建议。", "把治疗结果延伸到恢复管理。"),
        "GT_Followup_Plan": ("随访计划金标准", "随访阶段", "记录复查节点、长期监测与再评估安排。", "体现长期连续照护与复发监测。"),
        "GT_Final_Diagnosis": ("最终诊断金标准", "终局结论", "记录综合手术、病理与随访后确认的最终诊断。", "作为前序所有决策链条的终点参照。"),
        "GT_Surgery_Findings": ("术中所见金标准", "术中证据", "描述手术过程中的直接观察结果。", "提供病理前的关键实体证据。"),
        "GT_Pathology": ("病理结果金标准", "病理证据", "记录组织病理、术后病理或其他确诊性结果。", "为最终诊断提供最高等级证据。"),
        "GT_Patient_Wishes": ("患者意愿", "偏好约束", "记录生育需求、治疗偏好、手术接受度等患者价值取向。", "把医学决策与患者偏好绑定，形成真实世界约束。"),
        "oncology check": ("肿瘤专项检查", "专项补充", "记录肿瘤相关的专项检查或会诊信息。", "体现部分中心在复杂病例中的扩展证据链。"),
        "other check": ("其他补充检查", "专项补充", "记录未归入标准字段的其他补充检查。", "保留跨中心异质但真实存在的额外证据来源。"),
    }

    coverage_rows: list[tuple[str, str]] = []
    for path in sorted(GT_CENTER_ROOT.glob("*/GT/*.xlsx")):
        center = path.parent.parent.name
        cols = pd.read_excel(path, nrows=0).columns.tolist()
        for idx, col in enumerate(cols):
            if idx >= cols.index("BasicInfo"):
                coverage_rows.append((center, col))
    coverage_df = pd.DataFrame(coverage_rows, columns=["center", "raw_column"])
    coverage_map = (
        coverage_df.groupby("raw_column")["center"]
        .apply(lambda s: "、".join(sorted(set(map(str, s)))))
        .to_dict()
    )

    ordered_cols: list[str] = []
    for path in sorted(GT_CENTER_ROOT.glob("*/GT/*.xlsx")):
        cols = pd.read_excel(path, nrows=0).columns.tolist()
        basic_idx = cols.index("BasicInfo")
        for col in cols[basic_idx:]:
            if col not in ordered_cols:
                ordered_cols.append(col)

    rows = []
    for raw_col in ordered_cols:
        cn_name, layer, meaning, continuity = glossary.get(
            raw_col,
            (raw_col, "待补充", "待补充字段释义。", "待补充连续性角色。"),
        )
        rows.append(
            {
                "raw_column": raw_col,
                "cn_name": cn_name,
                "info_layer": layer,
                "field_meaning": meaning,
                "continuity_role": continuity,
                "center_coverage": coverage_map.get(raw_col, ""),
            }
        )
    df = pd.DataFrame(rows)
    (
        df.rename(
            columns={
                "raw_column": "原始列名",
                "cn_name": "中文字段名",
                "info_layer": "信息层级",
                "field_meaning": "字段含义",
                "continuity_role": "连续性作用",
                "center_coverage": "中心覆盖",
            }
        )
        .to_csv(OUT_SOURCE_DIR / "gt_patient_column_glossary.csv", index=False, encoding="utf-8-sig")
    )
    return df


def _metric_rules(
    result_cols: tuple[str, str, str, str, str],
    reason_cols: tuple[str, str, str, str, str],
) -> tuple[HighlightRule, ...]:
    return (
        HighlightRule((), result_cols[0], "min"),
        HighlightRule((), result_cols[1], "max"),
        HighlightRule((), result_cols[2], "max"),
        HighlightRule((), result_cols[3], "max"),
        HighlightRule((), result_cols[4], "max"),
        HighlightRule((), reason_cols[0], "min"),
        HighlightRule((), reason_cols[1], "max"),
        HighlightRule((), reason_cols[2], "max"),
        HighlightRule((), reason_cols[3], "max"),
        HighlightRule((), reason_cols[4], "max"),
    )


TABLE_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        title="主文建议补充表：D1-D4 阶段核心指标总表",
        builder=_build_stage_core_metrics_table,
        source_label=(
            "synthetic / analysis_viz/data/derived/figdata/v2_subplots/G2_outcome/"
            "G2_outcome_metrics_v6_source.xlsx + analysis_viz/data/derived/figdata/v2_subplots/"
            "G3_continuity/G3_continuity_metrics_v4_source.xlsx"
        ),
        column_order=(
            "stage4",
            "sample_n",
            "diagnosis_accuracy_pct",
            "plan_accuracy_pct",
            "check_quality_pct",
            "ineff_rate_pct",
            "memory_composite_pct",
            "consistency_composite_pct",
            "reasoning_quality_score",
        ),
        column_labels={
            "stage4": "阶段",
            "sample_n": "样本量",
            "diagnosis_accuracy_pct": "诊断正确性(%)",
            "plan_accuracy_pct": "方案正确性(%)",
            "check_quality_pct": "检查质量(%)",
            "ineff_rate_pct": "无效循环率(%)",
            "memory_composite_pct": "记忆综合分(%)",
            "consistency_composite_pct": "一致性综合分(%)",
            "reasoning_quality_score": "推理质量分(1-5)",
        },
        numeric_format={
            "sample_n": "{:d}",
            "diagnosis_accuracy_pct": "{:.1f}",
            "plan_accuracy_pct": "{:.1f}",
            "check_quality_pct": "{:.1f}",
            "ineff_rate_pct": "{:.1f}",
            "memory_composite_pct": "{:.1f}",
            "consistency_composite_pct": "{:.1f}",
            "reasoning_quality_score": "{:.2f}",
        },
        align_left_cols=("stage4",),
        sort_by=("stage4",),
        highlight_rules=(
            HighlightRule((), "diagnosis_accuracy_pct", "max"),
            HighlightRule((), "plan_accuracy_pct", "max"),
            HighlightRule((), "check_quality_pct", "max"),
            HighlightRule((), "ineff_rate_pct", "min"),
            HighlightRule((), "memory_composite_pct", "max"),
            HighlightRule((), "consistency_composite_pct", "max"),
            HighlightRule((), "reasoning_quality_score", "max"),
        ),
        note="空白表示该阶段无对应指标或该指标不适用；除推理质量分外，0-1 指标均已统一换算为百分制，以便主文快速横向比较。",
    ),
    TableSpec(
        title="补充表：GT 患者信息连续字段释义表",
        builder=_build_gt_patient_column_glossary,
        source_label="synthetic / analysis_viz/data/raw/center_data/*/GT/*.xlsx",
        column_order=("raw_column", "cn_name", "info_layer", "field_meaning", "continuity_role", "center_coverage"),
        column_labels={
            "raw_column": "原始列名",
            "cn_name": "中文字段名",
            "info_layer": "信息层级",
            "field_meaning": "字段含义",
            "continuity_role": "连续性作用",
            "center_coverage": "中心覆盖",
        },
        numeric_format={},
        align_left_cols=("raw_column", "cn_name", "info_layer", "field_meaning", "continuity_role", "center_coverage"),
        note="仅纳入 GT 患者信息表中从 BasicInfo 开始的连续字段，用于说明病例数据如何跨门诊、住院、术中、病理、术后与随访阶段逐步展开。",
    ),
    TableSpec(
        title="A0 人机一致性决策环节汇总表",
        source=A0_MAIN_XLSX,
        sheet="汇总_hm_decision_cn_paper",
        column_order=(
            "环节",
            "样本量\n(结果)",
            "MAE\n(结果)",
            "完全一致率\n(结果)",
            "±1分一致率\n(结果)",
            "Spearman\n(结果)",
            "Kappa(QW)\n(结果)",
            "样本量\n(推理)",
            "MAE\n(推理)",
            "完全一致率\n(推理)",
            "±1分一致率\n(推理)",
            "Spearman\n(推理)",
            "Kappa(QW)\n(推理)",
        ),
        column_labels={},
        numeric_format={
            "样本量\n(结果)": "{:d}",
            "MAE\n(结果)": "{:.3f}",
            "完全一致率\n(结果)": "{:.1f}",
            "±1分一致率\n(结果)": "{:.1f}",
            "Spearman\n(结果)": "{:.3f}",
            "Kappa(QW)\n(结果)": "{:.3f}",
            "样本量\n(推理)": "{:d}",
            "MAE\n(推理)": "{:.3f}",
            "完全一致率\n(推理)": "{:.1f}",
            "±1分一致率\n(推理)": "{:.1f}",
            "Spearman\n(推理)": "{:.3f}",
            "Kappa(QW)\n(推理)": "{:.3f}",
        },
        align_left_cols=("环节",),
        sort_by=("环节",),
        highlight_rules=_metric_rules(
            ("MAE\n(结果)", "完全一致率\n(结果)", "±1分一致率\n(结果)", "Spearman\n(结果)", "Kappa(QW)\n(结果)"),
            ("MAE\n(推理)", "完全一致率\n(推理)", "±1分一致率\n(推理)", "Spearman\n(推理)", "Kappa(QW)\n(推理)"),
        ),
        note="灰底表示该列在当前表中的最优或最值得关注值；MAE 越小越好，其余一致性指标越大越好。",
    ),
    TableSpec(
        title="A0 医生间一致性决策环节汇总表",
        source=A0_MAIN_XLSX,
        sheet="汇总_doc_decision_cn_paper",
        column_order=(
            "环节",
            "样本对\n(结果)",
            "平均绝对差\n(结果)",
            "完全一致率\n(结果)",
            "±1分一致率\n(结果)",
            "Spearman\n(结果)",
            "Kappa(QW)\n(结果)",
            "样本对\n(推理)",
            "平均绝对差\n(推理)",
            "完全一致率\n(推理)",
            "±1分一致率\n(推理)",
            "Spearman\n(推理)",
            "Kappa(QW)\n(推理)",
        ),
        column_labels={},
        numeric_format={
            "样本对\n(结果)": "{:d}",
            "平均绝对差\n(结果)": "{:.3f}",
            "完全一致率\n(结果)": "{:.1f}",
            "±1分一致率\n(结果)": "{:.1f}",
            "Spearman\n(结果)": "{:.3f}",
            "Kappa(QW)\n(结果)": "{:.3f}",
            "样本对\n(推理)": "{:d}",
            "平均绝对差\n(推理)": "{:.3f}",
            "完全一致率\n(推理)": "{:.1f}",
            "±1分一致率\n(推理)": "{:.1f}",
            "Spearman\n(推理)": "{:.3f}",
            "Kappa(QW)\n(推理)": "{:.3f}",
        },
        align_left_cols=("环节",),
        sort_by=("环节",),
        highlight_rules=_metric_rules(
            ("平均绝对差\n(结果)", "完全一致率\n(结果)", "±1分一致率\n(结果)", "Spearman\n(结果)", "Kappa(QW)\n(结果)"),
            ("平均绝对差\n(推理)", "完全一致率\n(推理)", "±1分一致率\n(推理)", "Spearman\n(推理)", "Kappa(QW)\n(推理)"),
        ),
        note="灰底表示该列在当前表中的最优或最值得关注值；平均绝对差越小越好，其余一致性指标越大越好。",
    ),
    TableSpec(
        title="A0 人机一致性检查环节汇总表",
        source=A0_SUPPLE_XLSX,
        sheet="hm_check_paper",
        column_order=(
            "环节",
            "样本量\n(结果)",
            "MAE\n(结果)",
            "完全一致率\n(结果)",
            "±1分一致率\n(结果)",
            "Spearman\n(结果)",
            "Kappa(QW)\n(结果)",
            "样本量\n(推理)",
            "MAE\n(推理)",
            "完全一致率\n(推理)",
            "±1分一致率\n(推理)",
            "Spearman\n(推理)",
            "Kappa(QW)\n(推理)",
        ),
        column_labels={},
        numeric_format={
            "样本量\n(结果)": "{:d}",
            "MAE\n(结果)": "{:.3f}",
            "完全一致率\n(结果)": "{:.1f}",
            "±1分一致率\n(结果)": "{:.1f}",
            "Spearman\n(结果)": "{:.3f}",
            "Kappa(QW)\n(结果)": "{:.3f}",
            "样本量\n(推理)": "{:d}",
            "MAE\n(推理)": "{:.3f}",
            "完全一致率\n(推理)": "{:.1f}",
            "±1分一致率\n(推理)": "{:.1f}",
            "Spearman\n(推理)": "{:.3f}",
            "Kappa(QW)\n(推理)": "{:.3f}",
        },
        align_left_cols=("环节",),
        sort_by=("环节",),
        highlight_rules=_metric_rules(
            ("MAE\n(结果)", "完全一致率\n(结果)", "±1分一致率\n(结果)", "Spearman\n(结果)", "Kappa(QW)\n(结果)"),
            ("MAE\n(推理)", "完全一致率\n(推理)", "±1分一致率\n(推理)", "Spearman\n(推理)", "Kappa(QW)\n(推理)"),
        ),
        note="灰底表示该列在当前表中的最优或最值得关注值；MAE 越小越好，其余一致性指标越大越好。",
    ),
    TableSpec(
        title="A0 医生间一致性检查环节汇总表",
        source=A0_SUPPLE_XLSX,
        sheet="doc_check_paper",
        column_order=(
            "环节",
            "样本对\n(结果)",
            "平均绝对差\n(结果)",
            "完全一致率\n(结果)",
            "±1分一致率\n(结果)",
            "Spearman\n(结果)",
            "Kappa(QW)\n(结果)",
            "样本对\n(推理)",
            "平均绝对差\n(推理)",
            "完全一致率\n(推理)",
            "±1分一致率\n(推理)",
            "Spearman\n(推理)",
            "Kappa(QW)\n(推理)",
        ),
        column_labels={},
        numeric_format={
            "样本对\n(结果)": "{:d}",
            "平均绝对差\n(结果)": "{:.3f}",
            "完全一致率\n(结果)": "{:.1f}",
            "±1分一致率\n(结果)": "{:.1f}",
            "Spearman\n(结果)": "{:.3f}",
            "Kappa(QW)\n(结果)": "{:.3f}",
            "样本对\n(推理)": "{:d}",
            "平均绝对差\n(推理)": "{:.3f}",
            "完全一致率\n(推理)": "{:.1f}",
            "±1分一致率\n(推理)": "{:.1f}",
            "Spearman\n(推理)": "{:.3f}",
            "Kappa(QW)\n(推理)": "{:.3f}",
        },
        align_left_cols=("环节",),
        sort_by=("环节",),
        highlight_rules=_metric_rules(
            ("平均绝对差\n(结果)", "完全一致率\n(结果)", "±1分一致率\n(结果)", "Spearman\n(结果)", "Kappa(QW)\n(结果)"),
            ("平均绝对差\n(推理)", "完全一致率\n(推理)", "±1分一致率\n(推理)", "Spearman\n(推理)", "Kappa(QW)\n(推理)"),
        ),
        note="灰底表示该列在当前表中的最优或最值得关注值；平均绝对差越小越好，其余一致性指标越大越好。",
    ),
    TableSpec(
        title="S1 检查环节结果质量对照表",
        source=S1_SUPPLE_XLSX,
        sheet="s_s1_result_check_paper",
        column_order=("环节", "样本量", "医生均分", "Judge均分", "MAE", "完全一致率", "±1分一致率", "Spearman", "Kappa(QW)"),
        column_labels={},
        numeric_format={
            "样本量": "{:d}",
            "医生均分": "{:.3f}",
            "Judge均分": "{:.3f}",
            "MAE": "{:.3f}",
            "完全一致率": "{:.1f}",
            "±1分一致率": "{:.1f}",
            "Spearman": "{:.3f}",
            "Kappa(QW)": "{:.3f}",
        },
        align_left_cols=("环节",),
        sort_by=("环节",),
        highlight_rules=(
            HighlightRule((), "MAE", "min"),
            HighlightRule((), "完全一致率", "max"),
            HighlightRule((), "±1分一致率", "max"),
            HighlightRule((), "Spearman", "max"),
            HighlightRule((), "Kappa(QW)", "max"),
        ),
        note="灰底表示该列在当前表中的最优或最值得关注值；MAE 越小越好，其余一致性指标越大越好。",
    ),
    TableSpec(
        title="S1 检查环节逻辑质量对照表",
        source=S1_SUPPLE_XLSX,
        sheet="s_s1_reason_check_paper",
        column_order=("环节", "样本量", "医生均分", "LLM均分", "MAE", "完全一致率", "±1分一致率", "Spearman", "Kappa(QW)"),
        column_labels={},
        numeric_format={
            "样本量": "{:d}",
            "医生均分": "{:.3f}",
            "LLM均分": "{:.3f}",
            "MAE": "{:.3f}",
            "完全一致率": "{:.1f}",
            "±1分一致率": "{:.1f}",
            "Spearman": "{:.3f}",
            "Kappa(QW)": "{:.3f}",
        },
        align_left_cols=("环节",),
        sort_by=("环节",),
        highlight_rules=(
            HighlightRule((), "MAE", "min"),
            HighlightRule((), "完全一致率", "max"),
            HighlightRule((), "±1分一致率", "max"),
            HighlightRule((), "Spearman", "max"),
            HighlightRule((), "Kappa(QW)", "max"),
        ),
        note="灰底表示该列在当前表中的最优或最值得关注值；MAE 越小越好，其余一致性指标越大越好。",
    ),
    TableSpec(
        title="G4B 分阶段平均校准点表",
        source=SUPPLE_G4_XLSX,
        sheet="B_stage_points",
        column_order=("stage4", "model_short", "conf_stage_model", "acc_stage_model", "calibration_gap", "n_stage_model"),
        column_labels={
            "stage4": "阶段",
            "model_short": "模型",
            "conf_stage_model": "平均置信度",
            "acc_stage_model": "观察准确率",
            "calibration_gap": "校准差值",
            "n_stage_model": "样本量",
        },
        numeric_format={
            "conf_stage_model": "{:.3f}",
            "acc_stage_model": "{:.3f}",
            "calibration_gap": "{:.3f}",
            "n_stage_model": "{:d}",
        },
        align_left_cols=("model_short",),
        sort_by=("stage4", "model_short"),
        highlight_rules=(
            HighlightRule(("stage4",), "conf_stage_model", "max"),
            HighlightRule(("stage4",), "acc_stage_model", "max"),
            HighlightRule(("stage4",), "calibration_gap", "min_abs"),
        ),
        note="灰底表示同阶段内的最优值：平均置信度与观察准确率取最大值，校准差值取绝对值最小值。",
    ),
    TableSpec(
        title="G4B 阶段加权总体校准表",
        source=SUPPLE_G4_XLSX,
        sheet="B0_weighted",
        column_order=("stage4", "conf_stage", "acc_stage", "stage_weight"),
        column_labels={
            "stage4": "阶段",
            "conf_stage": "加权平均置信度",
            "acc_stage": "加权观察准确率",
            "stage_weight": "样本量",
        },
        numeric_format={
            "conf_stage": "{:.3f}",
            "acc_stage": "{:.3f}",
            "stage_weight": "{:d}",
        },
        sort_by=("stage4",),
        highlight_rules=(
            HighlightRule((), "conf_stage", "max"),
            HighlightRule((), "acc_stage", "max"),
        ),
        note="灰底表示四阶段中对应指标的最佳值，便于直接复制到正文三线表。",
    ),
    TableSpec(
        title="G4C3 相邻额外检查轮次的边际诊断信息收益表",
        source=G4_SOURCE_XLSX,
        sheet="汇总_c3_marginal_gain_summary",
        column_order=(
            "phase_key",
            "decision_context",
            "round_idx",
            "round_label",
            "compare_to",
            "plot_label",
            "n_case_model",
            "n_case",
            "mean_matched_gain",
            "median_matched_gain",
            "std_matched_gain",
            "include_in_plot",
        ),
        column_labels={
            "phase_key": "阶段",
            "decision_context": "决策场景",
            "round_idx": "额外轮次",
            "round_label": "当前额外检查轮次",
            "compare_to": "比较基线",
            "plot_label": "展示标签",
            "n_case_model": "样本量（病例-模型轨迹）",
            "n_case": "病例数",
            "mean_matched_gain": "平均新增匹配信息项数",
            "median_matched_gain": "中位新增匹配信息项数",
            "std_matched_gain": "标准差",
            "include_in_plot": "是否纳入主图",
        },
        numeric_format={
            "round_idx": "{:d}",
            "n_case_model": "{:d}",
            "n_case": "{:d}",
            "mean_matched_gain": "{:.3f}",
            "median_matched_gain": "{:.3f}",
            "std_matched_gain": "{:.3f}",
        },
        align_left_cols=("decision_context", "round_label", "compare_to", "plot_label"),
        sort_by=("phase_order", "round_idx"),
        highlight_rules=(HighlightRule(("decision_context",), "mean_matched_gain", "max"),),
        note="灰底表示同一决策场景中平均新增匹配信息项数的最优轮次；`是否纳入主图` 保留为 paper 与 supplementary 共享的过滤标记。",
    ),
    TableSpec(
        title="G4C3 三阶段最终诊断接近度变化摘要表",
        source=G4_SOURCE_XLSX,
        sheet="汇总_c3_final_dx_transition",
        column_order=(
            "n_case_model",
            "n_case",
            "compare_label",
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
            "pct_non_decreasing",
        ),
        column_labels={
            "n_case_model": "完整病例-模型轨迹数",
            "n_case": "病例数",
            "compare_label": "阶段比较",
            "mean_prev_score": "上一阶段平均接近度",
            "mean_curr_score": "当前阶段平均接近度",
            "mean_delta_score": "平均接近度变化",
            "median_delta_score": "中位接近度变化",
            "mean_prev_distance": "上一阶段平均距离",
            "mean_curr_distance": "当前阶段平均距离",
            "mean_distance_reduction": "平均距离缩短",
            "n_more_near": "更接近轨迹数",
            "n_same": "基本不变轨迹数",
            "n_farther": "更远轨迹数",
            "pct_more_near": "更接近占比(%)",
            "pct_same": "基本不变占比(%)",
            "pct_farther": "更远占比(%)",
            "pct_non_decreasing": "非下降占比(%)",
        },
        numeric_format={
            "n_case_model": "{:d}",
            "n_case": "{:d}",
            "mean_prev_score": "{:.3f}",
            "mean_curr_score": "{:.3f}",
            "mean_delta_score": "{:.3f}",
            "median_delta_score": "{:.3f}",
            "mean_prev_distance": "{:.3f}",
            "mean_curr_distance": "{:.3f}",
            "mean_distance_reduction": "{:.3f}",
            "n_more_near": "{:d}",
            "n_same": "{:d}",
            "n_farther": "{:d}",
            "pct_more_near": "{:.1f}",
            "pct_same": "{:.1f}",
            "pct_farther": "{:.1f}",
            "pct_non_decreasing": "{:.1f}",
        },
        align_left_cols=("compare_label",),
        sort_by=("compare_order",),
        note="`平均距离缩短 = 上一阶段平均距离 - 当前阶段平均距离`，正值表示诊断更接近 GT 最终诊断；`非下降占比` 采用 ±0.01 容忍阈值。",
    ),
)


def _set_font(run, name: str = "宋体", size: int | None = 9, bold: bool = False) -> None:
    run.font.name = name
    run.bold = bold
    if size is not None:
        run.font.size = Pt(size)
    r_fonts = run._element.rPr.rFonts if run._element.rPr is not None and run._element.rPr.rFonts is not None else None
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        run._element.get_or_add_rPr().append(r_fonts)
    r_fonts.set(qn("w:eastAsia"), name)
    r_fonts.set(qn("w:ascii"), name)
    r_fonts.set(qn("w:hAnsi"), name)


def _set_cell_text(cell, text: str, *, bold: bool = False, align: WD_ALIGN_PARAGRAPH = WD_ALIGN_PARAGRAPH.CENTER) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = align
    run = paragraph.add_run(text)
    _set_font(run, bold=bold)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _set_cell_shading(cell, fill: str = "D9D9D9") -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)
    shd.set(qn("w:color"), "auto")


def _set_cell_border(cell, **kwargs: dict[str, str] | None) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.first_child_found_in("w:tcBorders")
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    for edge in ("left", "top", "right", "bottom"):
        edge_data = kwargs.get(edge)
        edge_el = tc_borders.find(qn(f"w:{edge}"))
        if edge_el is None:
            edge_el = OxmlElement(f"w:{edge}")
            tc_borders.append(edge_el)
        if edge_data is None:
            edge_el.set(qn("w:val"), "nil")
            edge_el.set(qn("w:sz"), "0")
            edge_el.set(qn("w:space"), "0")
            edge_el.set(qn("w:color"), "auto")
            continue
        edge_el.set(qn("w:val"), edge_data.get("val", "single"))
        edge_el.set(qn("w:sz"), edge_data.get("sz", "8"))
        edge_el.set(qn("w:space"), edge_data.get("space", "0"))
        edge_el.set(qn("w:color"), edge_data.get("color", "000000"))


def _apply_three_line_style(table) -> None:
    row_count = len(table.rows)
    for row_idx, row in enumerate(table.rows):
        for cell in row.cells:
            _set_cell_border(cell)
            if row_idx == 0:
                _set_cell_border(
                    cell,
                    top={"val": "single", "sz": "12", "color": "000000"},
                    bottom={"val": "single", "sz": "10", "color": "000000"},
                )
            elif row_idx == row_count - 1:
                _set_cell_border(cell, bottom={"val": "single", "sz": "12", "color": "000000"})


def _format_value(value, fmt: str | None) -> str:
    if pd.isna(value):
        return ""
    if fmt is None:
        if isinstance(value, bool):
            return "是" if value else "否"
        return str(value)
    if fmt == "{:d}":
        return fmt.format(int(round(float(value))))
    return fmt.format(float(value))


def _normalize_display_df(df: pd.DataFrame, spec: TableSpec) -> pd.DataFrame:
    working = df.copy()
    if spec.sort_by:
        sort_cols = [c for c in spec.sort_by if c in working.columns]
        if sort_cols:
            working = working.sort_values(sort_cols, kind="mergesort")
    display_cols = [c for c in spec.column_order if c in working.columns]
    working = working.loc[:, display_cols].reset_index(drop=True)
    rename_map = {k: v for k, v in spec.column_labels.items() if k in working.columns}
    working = working.rename(columns=rename_map)
    return working


def _display_col_name(col_name: str, spec: TableSpec) -> str:
    return spec.column_labels.get(col_name, col_name)


def _is_left_align_col(display_col: str, spec: TableSpec) -> bool:
    return display_col in {_display_col_name(col, spec) for col in spec.align_left_cols} | set(spec.align_left_cols)


def _apply_highlight_rules(table, df: pd.DataFrame, spec: TableSpec) -> None:
    if not spec.highlight_rules:
        return
    for rule in spec.highlight_rules:
        group_cols: list[str] = []
        for col in rule.group_cols:
            display_col = _display_col_name(col, spec)
            if display_col in df.columns:
                group_cols.append(display_col)
            elif col in df.columns:
                group_cols.append(col)
        if group_cols:
            grouped = df.groupby(group_cols, sort=False)
            group_iter = (sub.index for _, sub in grouped)
        else:
            group_iter = [df.index]
        for row_index in group_iter:
            subset = df.loc[row_index]
            display_target = _display_col_name(rule.target_col, spec)
            target_col = display_target if display_target in subset.columns else rule.target_col
            if subset.empty or target_col not in subset.columns:
                continue
            values = pd.to_numeric(subset[target_col], errors="coerce")
            if rule.mode == "max":
                target = values.max()
                mask = values.eq(target)
            elif rule.mode == "min":
                target = values.min()
                mask = values.eq(target)
            elif rule.mode == "min_abs":
                abs_values = values.abs()
                target = abs_values.min()
                mask = abs_values.eq(target)
            else:
                continue
            col_pos = list(df.columns).index(target_col)
            for ridx in subset.index[mask.fillna(False)]:
                _set_cell_shading(table.rows[int(ridx) + 1].cells[col_pos])


def _set_column_widths(table, df: pd.DataFrame, spec: TableSpec) -> None:
    widths_cm = []
    for col in df.columns:
        if col in {"字段含义", "连续性作用"}:
            widths_cm.append(6.4)
        elif col in {"原始列名", "中文字段名", "信息层级", "中心覆盖"}:
            widths_cm.append(3.4)
        elif _is_left_align_col(col, spec) or df[col].astype(str).map(len).max() > 12:
            widths_cm.append(4.3)
        elif "样本量" in col or "病例数" in col or "轮次" in col or "样本对" in col:
            widths_cm.append(2.2)
        else:
            widths_cm.append(2.7)
    for col_idx, width in enumerate(widths_cm):
        for row in table.rows:
            row.cells[col_idx].width = Cm(width)


def build_docx() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "宋体"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal.font.size = Pt(9)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("v2_subplots Word 三线表输出（A0 / S1 / G4）")
    _set_font(run, name="黑体", size=13, bold=True)

    intro = doc.add_paragraph()
    intro.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = intro.add_run(
        "本文件由独立导出器生成，用于将当前 A0、S1、G4 中以表格为主的 figure 统一转为可直接复制到论文 Word 的三线表；灰底表示各分组内的最优值。"
    )
    _set_font(run, size=9)

    timestamp = doc.add_paragraph()
    timestamp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = timestamp.add_run(f"生成时间：{datetime.now().isoformat(timespec='seconds')}")
    _set_font(run, size=8)

    for idx, spec in enumerate(TABLE_SPECS):
        if idx > 0:
            doc.add_page_break()

        if spec.builder is not None:
            source_df = spec.builder()
            source_text = spec.source_label or "synthetic"
        else:
            source_df = pd.read_excel(spec.source, sheet_name=spec.sheet, engine="openpyxl")
            source_text = f"{spec.source.relative_to(ROOT).as_posix()} / {spec.sheet}"
        display_df = _normalize_display_df(source_df, spec)

        heading = doc.add_paragraph()
        run = heading.add_run(spec.title)
        _set_font(run, name="黑体", size=12, bold=True)

        src = doc.add_paragraph()
        src_run = src.add_run(f"来源：{source_text}")
        _set_font(src_run, size=8)

        table = doc.add_table(rows=1, cols=len(display_df.columns))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        hdr = table.rows[0].cells
        for col_idx, col_name in enumerate(display_df.columns):
            _set_cell_text(hdr[col_idx], col_name, bold=True)
        _apply_three_line_style(table)

        for _, row in display_df.iterrows():
            cells = table.add_row().cells
            for col_idx, col_name in enumerate(display_df.columns):
                orig_name = next((k for k, v in spec.column_labels.items() if v == col_name), col_name)
                fmt = spec.numeric_format.get(orig_name)
                value = _format_value(row[col_name], fmt)
                align = WD_ALIGN_PARAGRAPH.LEFT if _is_left_align_col(col_name, spec) else WD_ALIGN_PARAGRAPH.CENTER
                _set_cell_text(cells[col_idx], value, align=align)

        _apply_three_line_style(table)
        _set_column_widths(table, display_df, spec)
        _apply_highlight_rules(table, display_df, spec)

        if spec.note:
            note = doc.add_paragraph()
            note.alignment = WD_ALIGN_PARAGRAPH.LEFT
            note_run = note.add_run(spec.note)
            _set_font(note_run, size=8)

    out_docx = OUT_DOCX
    try:
        doc.save(out_docx)
    except PermissionError:
        out_docx = OUT_DIR / f"G4_v2_subplots_word_tables__{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        doc.save(out_docx)

    OUT_MD.write_text(
        "\n".join(
            [
                "# v2_subplots Word 三线表导出说明",
                "",
                f"- 输出文件：`{out_docx.relative_to(ROOT).as_posix()}`",
                f"- synthetic source csv：`{OUT_SOURCE_DIR.relative_to(ROOT).as_posix()}`",
                "- 规则：三线表，无竖线；灰底表示分组内最优值。",
                "- 主线程集成：先运行 `analysis_viz/scripts/wrappers/build_v2_subplots_bundle.py` 生成最新 source data，再运行本脚本生成 Word 表。",
                "- 当前覆盖表：阶段核心指标总表、GT 患者信息连续字段释义表、A0 人机/医生间一致性决策与检查环节表、S1 检查环节结果与逻辑质量对照表、G4B 分阶段校准表、G4B 阶段加权总体校准表、G4C3 边际诊断信息收益表、G4C3 最终诊断接近度变化摘要表。",
            ]
        ),
        encoding="utf-8",
    )

    return out_docx


def main() -> None:
    out = build_docx()
    print(f"WROTE {out}")
    print(f"WROTE {OUT_MD}")


if __name__ == "__main__":
    main()
