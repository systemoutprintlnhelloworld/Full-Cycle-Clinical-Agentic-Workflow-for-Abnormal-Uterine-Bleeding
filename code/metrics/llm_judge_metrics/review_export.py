from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import load_workbook
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .sorting import case_id_sort_key


_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")  # dark blue
_HEADER_FONT = Font(color="FFFFFF", bold=True)

_GROUP_FILL_PALETTE = [
    PatternFill("solid", fgColor="D9E1F2"),  # blue
    PatternFill("solid", fgColor="E2EFDA"),  # green
    PatternFill("solid", fgColor="FFF2CC"),  # yellow
    PatternFill("solid", fgColor="FCE4D6"),  # orange
    PatternFill("solid", fgColor="E7E6E6"),  # grey
]
_SUBHEADER_FILL_PALETTE = [
    PatternFill("solid", fgColor="B4C6E7"),  # darker blue
    PatternFill("solid", fgColor="C6E0B4"),  # darker green
    PatternFill("solid", fgColor="FFE699"),  # darker yellow
    PatternFill("solid", fgColor="F8CBAD"),  # darker orange
    PatternFill("solid", fgColor="D0CECE"),  # darker grey
]


def _sort_by_case_id(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df
    out = df.copy()
    out["_case_sort"] = out[col].map(case_id_sort_key)
    out = out.sort_values(by=["_case_sort"], kind="mergesort").drop(columns=["_case_sort"])
    return out
_GROUP_HEADER_FONT = Font(color="000000", bold=True)
_SUBHEADER_FONT = Font(color="000000", bold=True)

_FILL_GREEN = PatternFill("solid", fgColor="C6EFCE")
_FILL_ORANGE = PatternFill("solid", fgColor="FFEB9C")
_FILL_GREY = PatternFill("solid", fgColor="E7E6E6")
_FILL_RED = PatternFill("solid", fgColor="FFC7CE")


_STAGE_CN = {
    "D1_Outpatient_Loop": "D1 门诊循环",
    "D1_Outpatient_Decision": "D1 门诊决策",
    "D2_SuggestedFromD1Decision": "D2 入院检查(源自D1决策建议)",
    "D2_Admission_Loop": "D2 入院循环",
    "D2_Admission_Decision": "D2 入院决策",
    "D3_Surgery_Decision": "D3 手术决策",
    "D4_Rehab_Plan": "D4 康复计划",
    "NOT_STARTED": "未开始",
}

_MATCH_COUNT_SOURCE_CN = {
    "unexecuted_list": "按“未执行列表”推导(锚定AI请求)",
    "unmatched_list": "按“未匹配列表”推导(锚定AI请求)",
    "judge_count": "直接用判官计数",
    "judge_list_len": "按判官列表计数(匹配/未匹配)",
    "match_score_proxy": "匹配度×请求数(估算)",
    "match_degree_proxy": "匹配度×请求数(估算)",
    "matched_list_len": "匹配列表长度(可能污染)",
}

_AI_TOTAL_SOURCE_CN = {
    "judge_total_count": "直接用判官“总请求数量”",
    "judge_matched_count+unexec_len": "判官“匹配数量”+未执行列表长度推导",
    "judge_list_len": "判官列表长度(匹配+未执行)",
    "doc_parse": "按AI请求原文拆分(兜底)",
}

_STATUS_ISSUE_CODE_CN = {
    "status_but_no_output": "状态非“未经过”，但该阶段无输出(疑似状态漂移)",
    "output_but_status_EMPTY": "该阶段有输出，但状态为空/未经过(疑似状态漂移)",
    "terminated_but_next_has_output": "标记“终止”，但后续阶段仍有输出(逻辑冲突)",
    "no_output_but_later_has_output": "该决策阶段无输出，但后续阶段有输出(疑似漏解析/漏抽取)",
}


def stage_cn(stage: str) -> str:
    return _STAGE_CN.get(stage, stage)


def match_count_source_cn(source: str | None) -> str:
    if not source:
        return ""
    return _MATCH_COUNT_SOURCE_CN.get(source, source)


def ai_total_source_cn(source: str | None) -> str:
    if not source:
        return ""
    return _AI_TOTAL_SOURCE_CN.get(source, source)


def _explain_status_issues_cn(s: str) -> str:
    parts = [p.strip() for p in str(s or "").split(";") if p and p.strip()]
    out: list[str] = []
    for p in parts:
        if ":" in p:
            st, code = p.split(":", 1)
            st = st.strip()
            code = code.strip()
            out.append(f"{stage_cn(st)}：{_STATUS_ISSUE_CODE_CN.get(code, code)}")
        else:
            out.append(p)
    return "；".join([x for x in out if x])


@dataclass(frozen=True)
class ReviewWorkbookSpec:
    center: str
    model: str
    summary_row: pd.DataFrame
    cases_flow: pd.DataFrame
    cases_recall: pd.DataFrame
    cases_inefficiency: pd.DataFrame
    cases_judge: pd.DataFrame
    check_rounds: pd.DataFrame
    loop_ineff_detail: pd.DataFrame
    review_check_rounds: pd.DataFrame
    status_issues: pd.DataFrame
    parse_anomalies: pd.DataFrame
    field_anomalies: pd.DataFrame


def build_review_workbook_spec(
    *,
    center: str,
    model: str,
    metrics_by_center_model: pd.DataFrame,
    metrics_by_case: pd.DataFrame,
    judge_scores_by_case: pd.DataFrame,
    check_rounds: pd.DataFrame,
    check_rounds_review: pd.DataFrame,
    parse_anomalies: pd.DataFrame | None,
    field_anomalies: pd.DataFrame | None = None,
    review_feedback: pd.DataFrame | None = None,
) -> ReviewWorkbookSpec:
    # --- 汇总（单行）
    summary = metrics_by_center_model.copy()
    if not summary.empty:
        summary = summary.loc[:, [c for c in summary.columns if c in summary.columns]].copy()
    summary = summary.copy()
    if not summary.empty:
        # Ensure first row only
        summary = summary.head(1)
        summary = summary.rename(
            columns={
                "center": "中心",
                "model": "模型",
                "cases": "病例数",
                "d1_check_match_rate_mean": "D1检查匹配率(病例均值)",
                "d1_check_match_rate_weighted": "D1检查匹配率(总匹配/总请求)",
                "d1_check_match_rate_n": "D1检查匹配率样本数(已评测)",
                "d1_check_match_rate_requested_n": "D1检查匹配率样本数(有请求)",
                "d1_check_match_rate_not_scored_n": "D1检查匹配率未评测数(裁判缺失)",
                "d2_check_match_rate_mean": "D2检查匹配率(病例均值)",
                "d2_check_match_rate_weighted": "D2检查匹配率(总匹配/总请求)",
                "d2_check_match_rate_n": "D2检查匹配率样本数(已评测)",
                "d2_check_match_rate_requested_n": "D2检查匹配率样本数(有请求)",
                "d2_check_match_rate_not_scored_n": "D2检查匹配率未评测数(裁判缺失)",
                "d1_inefficiency_by_zero_mean": "D1无效循环率(0匹配)均值",
                "d1_inefficiency_by_zero_n": "D1无效循环率样本数",
                "d2_inefficiency_by_zero_mean": "D2无效循环率(0匹配)均值",
                "d2_inefficiency_by_zero_n": "D2无效循环率样本数",
                # Gate (flow-based)
                "gate1_flow_pass_rate": "Gate1 流程通过率(基于流程状态)",
                "gate1_flow_reached_n": "Gate1 流程样本数(到达D1决策)",
                "gate1_flow_pass_n": "Gate1 流程通过数(到达D2及以后)",
                "gate2_flow_pass_rate": "Gate2 流程通过率(基于流程状态)",
                "gate2_flow_reached_n": "Gate2 流程样本数(到达D2决策)",
                "gate2_flow_pass_n": "Gate2 流程通过数(到达D3及以后)",
                # Gate (judge-based)
                "gate1_continue_rate": "Gate1 Judge通过率(继续评测)",
                "gate1_continue_n": "Gate1 Judge样本数",
                "gate1_overall_score_mean": "Gate1 Judge总分均值",
                "gate1_dx_score_mean": "Gate1 Judge诊断评分均值",
                "gate1_check_score_mean": "Gate1 Judge检查匹配评分均值",
                "gate1_check_match_degree_mean": "Gate1 Judge检查匹配度均值",
                "gate2_continue_rate": "Gate2 Judge初审通过率(继续评测)",
                "gate2_continue_n": "Gate2 Judge初审样本数",
                "gate2_secondary_rate": "Gate2 Judge复审通过率(is_reasonable)",
                "gate2_secondary_n": "Gate2 Judge复审样本数",
                "gate2_overall_score_mean": "Gate2 Judge总分均值",
                "gate2_revised_dx_score_mean": "Gate2 Judge修正诊断评分均值",
                "gate2_surgery_score_mean": "Gate2 Judge手术方案评分均值",
                "d3_continue_rate": "D3是否继续评测通过率",
                "d3_continue_n": "D3是否继续评测样本数",
                "d3_overall_score_mean": "D3总分均值",
                "d3_dx_score_mean": "D3最终诊断评分均值",
                "d3_plan_score_mean": "D3术后方案评分均值",
                "d4_overall_score_mean": "D4总分均值",
                "d4_rehab_score_mean": "D4康复计划评分均值",
                "d4_followup_score_mean": "D4随访计划评分均值",
            }
        )

    # --- 病例：流程状态（用于核对“终止于XXX”是否传播一致）
    flow_cols = [
        "center",
        "model",
        "case_id",
        "flow_end_stage",
        "doc_status_inferred__D1_Outpatient_Loop",
        "doc_status_inferred__D1_Outpatient_Decision",
        "doc_status_inferred__D2_Admission_Loop",
        "doc_status_inferred__D2_Admission_Decision",
        "doc_status_inferred__D3_Surgery_Decision",
        "doc_status_inferred__D4_Rehab_Plan",
        "issues",
        "is_anomaly_d1_to_d2",
    ]
    flow_cols = [c for c in flow_cols if c in metrics_by_case.columns]
    cases_flow = metrics_by_case.loc[:, flow_cols].copy()
    if not cases_flow.empty:
        cases_flow = cases_flow.rename(
            columns={
                "center": "中心",
                "model": "模型",
                "case_id": "病例ID",
                "flow_end_stage": "流程终止环节",
                "doc_status_inferred__D1_Outpatient_Loop": "D1门诊循环",
                "doc_status_inferred__D1_Outpatient_Decision": "D1门诊决策",
                "doc_status_inferred__D2_Admission_Loop": "D2入院循环",
                "doc_status_inferred__D2_Admission_Decision": "D2入院决策",
                "doc_status_inferred__D3_Surgery_Decision": "D3手术决策",
                "doc_status_inferred__D4_Rehab_Plan": "D4康复计划",
                "issues": "状态疑点(自动检测)",
                "is_anomaly_d1_to_d2": "D1异常输出",
            }
        )
        cases_flow["流程终止环节"] = cases_flow["流程终止环节"].astype(str).map(stage_cn)
        cases_flow = _sort_by_case_id(cases_flow, "病例ID")

    # --- 病例：检查召回（可手算）
    m = metrics_by_case.copy()
    cols = [
        "center",
        "model",
        "case_id",
        "flow_end_stage",
        "doc_status_inferred__D1_Outpatient_Loop",
        "doc_status_inferred__D2_Admission_Loop",
        "D1_Outpatient_Loop__requested_total",
        "D1_Outpatient_Loop__matched_total",
        "d1_check_match_rate",
        "D2_Check__requested_total",
        "D2_SuggestedFromD1Decision__matched_total",
        "D2_Admission_Loop__matched_total",
        "D2_Check__matched_total",
        "d2_check_match_rate",
        "is_anomaly_d1_to_d2",
    ]
    cols = [c for c in cols if c in m.columns]
    recall = m.loc[:, cols].copy()
    recall = recall.rename(
        columns={
            "center": "中心",
            "model": "模型",
            "case_id": "病例ID",
            "flow_end_stage": "流程终止环节",
            "doc_status_inferred__D1_Outpatient_Loop": "D1门诊循环状态(推断)",
            "doc_status_inferred__D2_Admission_Loop": "D2入院循环状态(推断)",
            "D1_Outpatient_Loop__requested_total": "D1分母_AI请求检查数",
            "D1_Outpatient_Loop__matched_total": "D1分子_已执行匹配数合计",
            "d1_check_match_rate": "D1检查匹配率(已执行/AI请求)",
            "D2_Check__requested_total": "D2分母_AI请求检查数(总)",
            "D2_SuggestedFromD1Decision__matched_total": "D2分子A_D1决策建议(匹配数)",
            "D2_Admission_Loop__matched_total": "D2分子B_入院循环(匹配数)",
            "D2_Check__matched_total": "D2分子_已执行匹配数合计(A+B)",
            "d2_check_match_rate": "D2检查匹配率(已执行/AI请求)",
            "is_anomaly_d1_to_d2": "D1异常输出(计D1失败但D2照常评分)",
        }
    )
    recall["流程终止环节"] = recall["流程终止环节"].astype(str).map(stage_cn)

    recall["D1分子来源说明"] = "来自“4_检查-轮次明细”中：阶段=D1 门诊循环 的【匹配数(最终)】求和"
    recall["D2分子来源说明"] = "来自“4_检查-轮次明细”中：阶段=D2 入院检查(源自D1决策建议)+D2 入院循环 的【匹配数(最终)】求和"

    # Reorder columns to match group-header layout (17 cols)
    recall = recall[
        [
            "中心",
            "模型",
            "病例ID",
            "流程终止环节",
            "D1门诊循环状态(推断)",
            "D2入院循环状态(推断)",
            "D1分母_AI请求检查数",
            "D1分子_已执行匹配数合计",
            "D1检查匹配率(已执行/AI请求)",
            "D1分子来源说明",
            "D1异常输出(计D1失败但D2照常评分)",
            "D2分母_AI请求检查数(总)",
            "D2分子A_D1决策建议(匹配数)",
            "D2分子B_入院循环(匹配数)",
            "D2分子_已执行匹配数合计(A+B)",
            "D2检查匹配率(已执行/AI请求)",
            "D2分子来源说明",
        ]
    ].copy()
    recall = _sort_by_case_id(recall, "病例ID")

    # --- 病例：无效循环率（0匹配）（可手算）
    m2 = metrics_by_case.copy()
    ineff_cols = [
        "center",
        "model",
        "case_id",
        "flow_end_stage",
        "doc_status_inferred__D1_Outpatient_Loop",
        "D1_Outpatient_Loop__executed_rounds",
        "D1_Outpatient_Loop__ineff_rounds_by_zero",
        "d1_inefficiency_by_zero",
        "doc_status_inferred__D2_Admission_Loop",
        "D2_Admission_Loop__executed_rounds",
        "D2_Admission_Loop__ineff_rounds_by_zero",
        "d2_inefficiency_by_zero",
        "is_anomaly_d1_to_d2",
    ]
    ineff_cols = [c for c in ineff_cols if c in m2.columns]
    ineff = m2.loc[:, ineff_cols].copy()
    if not ineff.empty:
        ineff = ineff.rename(
            columns={
                "center": "中心",
                "model": "模型",
                "case_id": "病例ID",
                "flow_end_stage": "流程终止环节",
                "doc_status_inferred__D1_Outpatient_Loop": "D1门诊循环状态(推断)",
                "D1_Outpatient_Loop__executed_rounds": "D1循环轮次总数(有请求)",
                "D1_Outpatient_Loop__ineff_rounds_by_zero": "D1无效循环轮次(0匹配)",
                "d1_inefficiency_by_zero": "D1无效循环率(0匹配)",
                "doc_status_inferred__D2_Admission_Loop": "D2入院循环状态(推断)",
                "D2_Admission_Loop__executed_rounds": "D2循环轮次总数(有请求)",
                "D2_Admission_Loop__ineff_rounds_by_zero": "D2无效循环轮次(0匹配)",
                "d2_inefficiency_by_zero": "D2无效循环率(0匹配)",
                "is_anomaly_d1_to_d2": "D1异常输出(计D1失败但D2照常评分)",
            }
        )
        ineff["流程终止环节"] = ineff["流程终止环节"].astype(str).map(stage_cn)
        ineff["D1计算说明"] = "D1无效循环率= D1无效循环轮次(0匹配) / D1循环轮次总数(有请求)；0匹配来自“4_检查-轮次明细”的匹配数(最终)=0"
        ineff["D2计算说明"] = "D2无效循环率= D2无效循环轮次(0匹配) / D2循环轮次总数(有请求)；0匹配来自“4_检查-轮次明细”的匹配数(最终)=0"
        # Column order
        ineff = ineff[
            [
                "中心",
                "模型",
                "病例ID",
                "流程终止环节",
                "D1门诊循环状态(推断)",
                "D1循环轮次总数(有请求)",
                "D1无效循环轮次(0匹配)",
                "D1无效循环率(0匹配)",
                "D1计算说明",
                "D1异常输出(计D1失败但D2照常评分)",
                "D2入院循环状态(推断)",
                "D2循环轮次总数(有请求)",
                "D2无效循环轮次(0匹配)",
                "D2无效循环率(0匹配)",
                "D2计算说明",
            ]
        ].copy()
        ineff = _sort_by_case_id(ineff, "病例ID")

    # --- 病例：裁判评分（核心列）
    js = judge_scores_by_case.copy()
    if not js.empty:
        keep = [
            "center",
            "model",
            "case_id",
            "gate1_continue",
            "gate1_overall_score",
            "gate1_dx_score",
            "gate1_check_score",
            "gate1_check_match_degree",
            "gate2_continue",
            "gate2_secondary_is_reasonable",
            "gate2_overall_score",
            "gate2_revised_dx_score",
            "gate2_surgery_score",
            "d3_continue",
            "d3_overall_score",
            "d3_dx_score",
            "d3_plan_score",
            "d4_overall_score",
            "d4_rehab_score",
            "d4_followup_score",
        ]
        keep = [c for c in keep if c in js.columns]
        js = js.loc[:, keep].copy()
        js = js.rename(
            columns={
                "center": "中心",
                "model": "模型",
                "case_id": "病例ID",
                "gate1_continue": "Gate1 Judge_是否继续评测",
                "gate1_overall_score": "Gate1 Judge_总分",
                "gate1_dx_score": "Gate1 Judge_诊断评分",
                "gate1_check_score": "Gate1 Judge_检查匹配评分",
                "gate1_check_match_degree": "Gate1 Judge_检查匹配度(0-1)",
                "gate2_continue": "Gate2 Judge初审_是否继续评测",
                "gate2_secondary_is_reasonable": "Gate2 Judge复审_is_reasonable(0/1)",
                "gate2_overall_score": "Gate2 Judge_总分",
                "gate2_revised_dx_score": "Gate2 Judge_修正诊断评分",
                "gate2_surgery_score": "Gate2 Judge_手术方案评分",
                "d3_continue": "D3_是否继续评测",
                "d3_overall_score": "D3_总分",
                "d3_dx_score": "D3_最终诊断评分",
                "d3_plan_score": "D3_术后方案评分",
                "d4_overall_score": "D4_总分",
                "d4_rehab_score": "D4_康复计划评分",
                "d4_followup_score": "D4_随访计划评分",
            }
        )
        # Make gate-like booleans human-friendly (avoid raw True/False).
        def _gate_cn(v: Any) -> str:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return ""
            if isinstance(v, bool):
                return "通过" if v else "不通过"
            s = str(v).strip().lower()
            if s in {"1", "true", "yes", "y", "是", "通过"}:
                return "通过"
            if s in {"0", "false", "no", "n", "否", "不通过"}:
                return "不通过"
            return str(v)

        for c in ["Gate1 Judge_是否继续评测", "Gate2 Judge初审_是否继续评测", "Gate2 Judge复审_is_reasonable(0/1)", "D3_是否继续评测"]:
            if c in js.columns:
                js[c] = js[c].map(_gate_cn)
    judge_cases = _sort_by_case_id(js, "病例ID") if not js.empty else js

    # --- 检查：轮次明细（每轮一行）
    cr = check_rounds.copy()
    keep = [
        "center",
        "model",
        "case_id",
        "stage",
        "round_idx",
        "doc_status",
        "ai_total_requested_count",
        "ai_total_source",
        "matched_count_final",
        "unmatched_count_final",
        "matched_count_source",
        "judge_match_score_raw",
        "judge_matched_count_raw",
        "judge_total_requested_count_raw",
        "judge_count_vs_unexec_conflict",
        "ai_total_vs_judge_total_mismatch",
        "judge_extra_matched_items_suspect",
        "doc_ai_requests_text",
        "judge_unexecuted_items_raw",
        "judge_matched_items_raw",
    ]
    keep = [c for c in keep if c in cr.columns]
    cr = cr.loc[:, keep].copy()
    cr["stage"] = cr["stage"].astype(str).map(stage_cn)
    cr["matched_count_source"] = cr["matched_count_source"].astype(str).map(match_count_source_cn)
    if "ai_total_source" in cr.columns:
        cr["ai_total_source"] = cr["ai_total_source"].astype(str).map(ai_total_source_cn)
    cr = cr.rename(
        columns={
            "center": "中心",
            "model": "模型",
            "case_id": "病例ID",
            "stage": "阶段",
            "round_idx": "轮次",
            "doc_status": "医生状态(原表)",
            "ai_total_requested_count": "AI请求检查数",
            "ai_total_source": "AI请求数来源",
            "matched_count_final": "匹配数(最终)",
            "unmatched_count_final": "未匹配数(最终)",
            "matched_count_source": "匹配数来源(解释)",
            "judge_match_score_raw": "判官_匹配度分(0-1)",
            "judge_matched_count_raw": "判官_匹配数量(原始)",
            "judge_total_requested_count_raw": "判官_总请求数量(原始)",
            "judge_count_vs_unexec_conflict": "异常标记_计数冲突",
            "ai_total_vs_judge_total_mismatch": "异常标记_总数不一致",
            "judge_extra_matched_items_suspect": "疑似额外匹配项(列表)",
            "doc_ai_requests_text": "AI请求原文(提取字段)",
            "judge_unexecuted_items_raw": "未匹配检查(判官-未执行列表)",
            "judge_matched_items_raw": "匹配检查(判官列表)",
        }
    )
    if not cr.empty and "AI请求检查数" in cr.columns and "匹配数(最终)" in cr.columns:
        ai = pd.to_numeric(cr["AI请求检查数"], errors="coerce")
        matched = pd.to_numeric(cr["匹配数(最终)"], errors="coerce")
        cr["匹配度(修正=匹配数/请求数)"] = (matched / ai.where(ai != 0)).clip(lower=0, upper=1)
    if not cr.empty:
        order = [
            "中心",
            "模型",
            "病例ID",
            "阶段",
            "轮次",
            "医生状态(原表)",
            "AI请求检查数",
            "AI请求数来源",
            "匹配数(最终)",
            "未匹配数(最终)",
            "匹配度(修正=匹配数/请求数)",
            "匹配数来源(解释)",
            "判官_匹配度分(0-1)",
            "判官_匹配数量(原始)",
            "判官_总请求数量(原始)",
            "异常标记_计数冲突",
            "异常标记_总数不一致",
            "疑似额外匹配项(列表)",
            "AI请求原文(提取字段)",
            "未匹配检查(判官-未执行列表)",
            "匹配检查(判官列表)",
        ]
        cr = cr.loc[:, [c for c in order if c in cr.columns]].copy()
    if not cr.empty:
        cr["_case_sort"] = cr["病例ID"].map(case_id_sort_key)
        cr["轮次"] = pd.to_numeric(cr["轮次"], errors="coerce")
        cr = cr.sort_values(by=["_case_sort", "阶段", "轮次"], kind="mergesort").drop(columns=["_case_sort"])

    # --- 循环：无效循环(0匹配)逐轮明细（可手算/可追溯）
    loop_detail = pd.DataFrame()
    if not cr.empty:
        loop_detail = cr.copy()
        loop_detail = loop_detail.loc[loop_detail["阶段"].isin(["D1 门诊循环", "D2 入院循环"])].copy()
        loop_detail["AI请求检查数"] = pd.to_numeric(loop_detail["AI请求检查数"], errors="coerce")
        loop_detail["匹配数(最终)"] = pd.to_numeric(loop_detail["匹配数(最终)"], errors="coerce")
        loop_detail = loop_detail.loc[loop_detail["AI请求检查数"].fillna(0) > 0].copy()
        loop_detail["评测状态"] = loop_detail["匹配数(最终)"].map(lambda v: "未评测(裁判缺失)" if pd.isna(v) else "已评测")
        loop_detail["是否0匹配"] = loop_detail.apply(
            lambda r: "" if pd.isna(r.get("匹配数(最终)")) else ("是" if float(r.get("匹配数(最终)") or 0) == 0 else "否"),
            axis=1,
        )
        # Keep only the columns needed for manual recomputation.
        keep_cols = [
            "中心",
            "模型",
            "病例ID",
            "阶段",
            "轮次",
            "医生状态(原表)",
            "AI请求检查数",
            "匹配数(最终)",
            "未匹配数(最终)",
            "是否0匹配",
            "评测状态",
            "AI请求原文(提取字段)",
            "未匹配检查(判官-未执行列表)",
            "匹配检查(判官列表)",
        ]
        loop_detail = loop_detail.loc[:, [c for c in keep_cols if c in loop_detail.columns]].copy()

    # --- 需要复核：检查匹配异常
    rr = check_rounds_review.copy()
    if not rr.empty:
        rr = rr.copy()
        # Curated columns (avoid 40+ columns)
        keep = [
            "center",
            "model",
            "case_id",
            "stage",
            "round_idx",
            "review_reasons",
            "ai_total_requested_count",
            "ai_total_source",
            "matched_count_final",
            "unmatched_count_final",
            "matched_count_source",
            "doc_ai_requests_text",
            "judge_match_score_raw",
            "judge_matched_count_raw",
            "judge_total_requested_count_raw",
            "judge_unexecuted_items_raw",
            "judge_matched_items_raw",
            "judge_extra_matched_items_suspect",
        ]
        keep = [c for c in keep if c in rr.columns]
        rr = rr.loc[:, keep].copy()

        rr["stage"] = rr["stage"].astype(str).map(stage_cn)
        rr["matched_count_source"] = rr["matched_count_source"].astype(str).map(match_count_source_cn)
        if "ai_total_source" in rr.columns:
            rr["ai_total_source"] = rr["ai_total_source"].astype(str).map(ai_total_source_cn)

        rr = rr.rename(
            columns={
                "center": "中心",
                "model": "模型",
                "case_id": "病例ID",
                "stage": "阶段",
                "round_idx": "轮次",
                "review_reasons": "复核原因(为何入表)",
                "ai_total_requested_count": "AI请求检查数",
                "ai_total_source": "AI请求数来源",
                "matched_count_final": "匹配数(最终)",
                "unmatched_count_final": "未匹配数(最终)",
                "matched_count_source": "匹配数来源(解释)",
                "doc_ai_requests_text": "AI请求原文(提取字段)",
                "judge_match_score_raw": "判官_匹配度分(0-1)",
                "judge_matched_count_raw": "判官_匹配数量(原始)",
                "judge_total_requested_count_raw": "判官_总请求数量(原始)",
                "judge_unexecuted_items_raw": "未匹配检查(判官-未执行列表)",
                "judge_matched_items_raw": "匹配检查(判官列表)",
                "judge_extra_matched_items_suspect": "疑似额外匹配项(列表)",
            }
        )
        if "AI请求检查数" in rr.columns and "匹配数(最终)" in rr.columns:
            ai = pd.to_numeric(rr["AI请求检查数"], errors="coerce")
            matched = pd.to_numeric(rr["匹配数(最终)"], errors="coerce")
            rr["匹配度(修正=匹配数/请求数)"] = (matched / ai.where(ai != 0)).clip(lower=0, upper=1)

        rr["反馈_结论"] = ""
        rr["反馈_建议动作"] = ""
        rr["反馈_备注"] = ""
        if "复核原因(为何入表)" in rr.columns:
            rr["裁判缺失/未评测"] = rr["复核原因(为何入表)"].astype(str).str.contains("裁判缺失").fillna(False)
        rr = rr[
            [
                "中心",
                "模型",
                "病例ID",
                "阶段",
                "轮次",
                "复核原因(为何入表)",
                "裁判缺失/未评测",
                "AI请求检查数",
                "AI请求数来源",
                "匹配数(最终)",
                "未匹配数(最终)",
                "匹配度(修正=匹配数/请求数)",
                "匹配数来源(解释)",
                "疑似额外匹配项(列表)",
                "AI请求原文(提取字段)",
                "判官_匹配度分(0-1)",
                "判官_匹配数量(原始)",
                "判官_总请求数量(原始)",
                "未匹配检查(判官-未执行列表)",
                "匹配检查(判官列表)",
                "反馈_结论",
                "反馈_建议动作",
                "反馈_备注",
            ]
        ].copy()

        # Prefill feedback from persisted CSV (extracted from previous review workbooks).
        if review_feedback is not None and not review_feedback.empty:
            fb = review_feedback.copy()
            need_cols = {"中心", "模型", "病例ID", "阶段", "轮次", "反馈_结论", "反馈_建议动作", "反馈_备注"}
            if need_cols.issubset(set(fb.columns)):
                # Normalize "nan"/NaN into empty strings.
                for c in ["反馈_结论", "反馈_建议动作", "反馈_备注"]:
                    fb[c] = fb[c].fillna("").astype(str).replace({"nan": ""}).map(lambda x: x.strip())
                fb["轮次"] = pd.to_numeric(fb["轮次"], errors="coerce").astype("Int64")
                rr["轮次"] = pd.to_numeric(rr["轮次"], errors="coerce").astype("Int64")
                fb = fb.loc[fb["中心"].astype(str).str.strip().ne(""), list(need_cols)].copy()
                rr = rr.merge(
                    fb,
                    on=["中心", "模型", "病例ID", "阶段", "轮次"],
                    how="left",
                    suffixes=("", "__fb"),
                )
                for c in ["反馈_结论", "反馈_建议动作", "反馈_备注"]:
                    if f"{c}__fb" in rr.columns:
                        rr[c] = rr[f"{c}__fb"].where(rr[f"{c}__fb"].astype(str).str.strip().ne(""), rr[c])
                        rr = rr.drop(columns=[f"{c}__fb"])

        # Sort for readability: case_id natural order, then stage, then round.
        rr["_case_sort"] = rr["病例ID"].map(case_id_sort_key)
        rr["轮次"] = pd.to_numeric(rr["轮次"], errors="coerce")
        rr = rr.sort_values(by=["_case_sort", "阶段", "轮次"], kind="mergesort").drop(columns=["_case_sort"])
    review_rr = rr

    # --- 需要复核：状态逻辑问题（基于 metrics_by_case 的 issues 字段）
    status_issues = pd.DataFrame()
    if "issues" in metrics_by_case.columns:
        tmp = metrics_by_case.loc[metrics_by_case["issues"].astype(str).str.strip().ne(""), ["center", "model", "case_id", "issues"]].copy()
        if not tmp.empty:
            tmp = tmp.rename(columns={"center": "中心", "model": "模型", "case_id": "病例ID", "issues": "问题描述"})
            tmp["问题解释(中文)"] = tmp["问题描述"].map(_explain_status_issues_cn)
            status_issues = _sort_by_case_id(tmp, "病例ID")

    # --- 解析异常（当前 group 过滤）
    pa = (parse_anomalies.copy() if parse_anomalies is not None else pd.DataFrame()).copy()
    if not pa.empty:
        # Keep only this group if center/model exists
        if "center" in pa.columns and "model" in pa.columns:
            pa = pa.loc[(pa["center"] == center) & (pa["model"] == model)].copy()
        pa = pa.rename(
            columns={
                "center": "中心",
                "model": "模型",
                "kind": "来源(医生/裁判)",
                "sheet": "工作表",
                "anomaly_type": "异常类型",
                "column": "字段/列名",
                "details": "详情",
            }
        )
        if "来源(医生/裁判)" in pa.columns:
            pa["来源(医生/裁判)"] = pa["来源(医生/裁判)"].map({"doc": "医生", "judge": "裁判"}).fillna(pa["来源(医生/裁判)"])
        if "异常类型" in pa.columns:
            pa.insert(pa.columns.get_loc("异常类型") + 1, "异常类型代码", pa["异常类型"])
            pa["异常类型"] = (
                pa["异常类型"]
                .map(
                    {
                        "header_known_mojibake": "表头乱码(已自动修复)",
                        "header_non_ascii_latin": "表头包含异常拉丁字符(已自动修复)",
                        "check_col_contains_decision_terms": "检查列疑似混入决策内容",
                        "loop_raw_json_equals_decision_raw_json": "循环原始JSON与对应决策完全相同(已自动按未经过处理)",
                        "doc_request_missing_used_judge_list": "AI请求文本缺失(已用裁判列表兜底)",
                        "doc_request_recovered_from_round_raw_json": "AI请求列缺失(已从轮次原始JSON恢复)",
                        "canonicalize_rename": "表头已自动修正(重命名)",
                        "canonicalize_merge_duplicate_after_rename": "表头重复(重命名后)已自动合并",
                        "canonicalize_drop_duplicate_after_rename": "表头重复(重命名后)已自动丢弃",
                    }
                )
                .fillna(pa["异常类型"])
            )

    # --- Doc/Judge 字段异常（当前 group 过滤）
    fa = (field_anomalies.copy() if field_anomalies is not None else pd.DataFrame()).copy()
    if not fa.empty:
        if "center" in fa.columns and "model" in fa.columns:
            fa = fa.loc[(fa["center"] == center) & (fa["model"] == model)].copy()
        fa = fa.rename(
            columns={
                "center": "中心",
                "model": "模型",
                "kind": "来源(医生/裁判)",
                "sheet": "工作表",
                "case_id": "病例ID",
                "round_idx": "轮次",
                "anomaly_type": "异常类型",
                "column": "字段/列名",
                "details": "详情",
            }
        )
        if "来源(医生/裁判)" in fa.columns:
            fa["来源(医生/裁判)"] = fa["来源(医生/裁判)"].map({"doc": "医生", "judge": "裁判"}).fillna(fa["来源(医生/裁判)"])
        if "异常类型" in fa.columns:
            fa.insert(fa.columns.get_loc("异常类型") + 1, "异常类型代码", fa["异常类型"])
            fa["异常类型"] = (
                fa["异常类型"]
                .map(
                    {
                        "missing_common_column": "缺失通用列",
                        "extra_rare_column": "非通用列(可能异常)",
                        "doc_missing_required_field": "医生关键字段缺失",
                        "doc_missing_required_any": "医生关键字段缺失(需至少一项)",
                        "judge_missing_required_field": "裁判关键字段缺失",
                        "judge_missing_all_fields": "裁判关键字段全缺失",
                        "judge_missing_check_round": "裁判缺失/未评测(检查匹配)",
                    }
                )
                .fillna(fa["异常类型"])
            )
        if "病例ID" in fa.columns:
            fa = _sort_by_case_id(fa, "病例ID")

    return ReviewWorkbookSpec(
        center=center,
        model=model,
        summary_row=summary,
        cases_flow=cases_flow,
        cases_recall=recall,
        cases_inefficiency=ineff,
        cases_judge=judge_cases,
        check_rounds=cr,
        loop_ineff_detail=loop_detail,
        review_check_rounds=review_rr,
        status_issues=status_issues,
        parse_anomalies=pa,
        field_anomalies=fa,
    )


def _humanize_bools_cn(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for c in out.columns:
        s = out[c]
        # Only convert TRUE booleans, NOT numeric 0/1 counters.
        if pd.api.types.is_bool_dtype(s):
            out[c] = s.map(lambda x: "是" if bool(x) else "否")
            continue
        if pd.api.types.is_numeric_dtype(s):
            continue
        non_na = s.dropna()
        if non_na.empty:
            continue
        uniq = set(non_na.unique())
        # Guard: in Python, {True, False} == {1, 0}; avoid converting integer counters.
        if uniq and all(isinstance(x, (bool,)) for x in uniq):
            out[c] = s.map(lambda x: "" if pd.isna(x) else ("是" if bool(x) else "否"))
    return out


def export_review_workbook_xlsx(path: Path, spec: ReviewWorkbookSpec) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    # 0_说明
    info_lines = [
        "本工作簿用于人工审阅与手工复算（尽量少列、中文表头）。",
        "",
        "【检查匹配率(严格)】= 已执行匹配数合计 / AI请求检查数（衡量“医生输出与实际执行的一致程度”）。",
        "  - 若该阶段存在AI请求但“裁判缺失/未评测”，则该病例的分子/匹配率会留空，并进入 `5_需要复核-检查匹配`（复核原因含“裁判缺失/未评测”）。",
        "【检查合理性率(匹配+合理/请求)】属于 LLM 指标：若已跑 LLM，会出现在 8_LLM-检查合理性(按病例) 与 summary/检查合理性(LLM)_按病例.csv。",
        "【诊断TopK语义命中(D1)】属于 LLM 指标：若已跑 LLM，会出现在 8_LLM-诊断TopK(D1) 与 summary/诊断TopK(LLM)_按病例.csv。",
        "【Gate通过率】分两套：",
        "  - Gate* 流程通过率：基于流程状态推断（区分“未评测”与“失败”）。",
        "  - Gate* Judge通过率：基于裁判 `是否继续评测` 字段（仅统计有裁判数据的样本）。",
        "",
        "你主要需要看：",
        "- 2_病例-检查匹配：分子/分母是否合理，可手算核对。",
        "- 5_需要复核-检查匹配：只列出“疑似有问题”的轮次，请在反馈列填结论/动作/备注。",
        "- 4_无效循环-逐轮明细：无效循环率(0匹配)的逐轮可追溯表（可手算）。",
        "- 7_解析异常：表头/字段异常（例如门žen检查）已经做了内存修复并记录在这里。",
        "- 9_doc_judge_异常：doc/judge 字段缺失与列异常清单（不改 data，仅供修复反馈）。",
        "",
        "反馈方式（推荐）：在 5_需要复核-检查匹配 中填写“反馈_结论/反馈_建议动作/反馈_备注”，保存后把文件发我或告诉我你填了哪些病例ID。",
    ]
    df_info = pd.DataFrame({"说明": info_lines})

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df_info.to_excel(writer, sheet_name="0_说明", index=False)
        _humanize_bools_cn(spec.summary_row).to_excel(writer, sheet_name="1_汇总(中心-模型)", index=False)
        _humanize_bools_cn(spec.cases_flow).to_excel(writer, sheet_name="2_病例-流程状态", index=False)
        _humanize_bools_cn(spec.cases_recall).to_excel(writer, sheet_name="2_病例-检查匹配", index=False)
        _humanize_bools_cn(spec.cases_inefficiency).to_excel(writer, sheet_name="2_病例-无效循环", index=False)
        _humanize_bools_cn(spec.cases_judge).to_excel(writer, sheet_name="3_病例-裁判评分", index=False)
        _humanize_bools_cn(spec.check_rounds).to_excel(writer, sheet_name="4_检查-轮次明细", index=False)
        _humanize_bools_cn(spec.loop_ineff_detail).to_excel(writer, sheet_name="4_无效循环-逐轮明细", index=False)
        _humanize_bools_cn(spec.review_check_rounds).to_excel(writer, sheet_name="5_需要复核-检查匹配", index=False)
        _humanize_bools_cn(spec.status_issues).to_excel(writer, sheet_name="6_需要复核-状态逻辑", index=False)
        _humanize_bools_cn(spec.parse_anomalies).to_excel(writer, sheet_name="7_解析异常", index=False)
        _humanize_bools_cn(spec.field_anomalies).to_excel(writer, sheet_name="9_doc_judge_异常", index=False)

    wb = load_workbook(path)
    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        # Header style (row 1)
        for cell in ws[1]:
            cell.fill = _HEADER_FILL
            cell.font = _HEADER_FONT
            cell.alignment = Alignment(vertical="center")

        # Reasonable column widths
        max_col = ws.max_column
        max_row = min(ws.max_row, 1500)
        for col_idx in range(1, max_col + 1):
            letter = get_column_letter(col_idx)
            values = []
            for row_idx in range(1, max_row + 1):
                v = ws.cell(row=row_idx, column=col_idx).value
                if v is None:
                    continue
                values.append(str(v))
            header_len = len(str(ws.cell(row=1, column=col_idx).value or ""))
            sample_len = max([len(v) for v in values[:120]] + [0])
            ws.column_dimensions[letter].width = max(10, min(60, max(header_len, sample_len) + 2))

        # Conditional formatting for status-like columns
        for col_idx in range(1, max_col + 1):
            header = ws.cell(row=1, column=col_idx).value
            if not header:
                continue
            h = str(header)
            if "状态" not in h and "流程" not in h:
                continue
            col_letter = get_column_letter(col_idx)
            rng = f"{col_letter}2:{col_letter}{ws.max_row}"
            ws.conditional_formatting.add(rng, FormulaRule(formula=[f'ISNUMBER(SEARCH("顺利通过",{col_letter}2))'], fill=_FILL_GREEN))
            ws.conditional_formatting.add(rng, FormulaRule(formula=[f'ISNUMBER(SEARCH("终止",{col_letter}2))'], fill=_FILL_ORANGE))
            ws.conditional_formatting.add(rng, FormulaRule(formula=[f'ISNUMBER(SEARCH("未经过",{col_letter}2))'], fill=_FILL_GREY))
            ws.conditional_formatting.add(rng, FormulaRule(formula=[f'ISNUMBER(SEARCH("异常",{col_letter}2))'], fill=_FILL_RED))

        # Highlight "裁判缺失/未评测" in review sheet
        if ws.title == "5_需要复核-检查匹配":
            for col_idx in range(1, max_col + 1):
                header = ws.cell(row=1, column=col_idx).value
                if str(header).strip() != "裁判缺失/未评测":
                    continue
                col_letter = get_column_letter(col_idx)
                rng = f"{col_letter}2:{col_letter}{ws.max_row}"
                ws.conditional_formatting.add(rng, FormulaRule(formula=[f'ISNUMBER(SEARCH("是",{col_letter}2))'], fill=_FILL_RED))

        # Highlight zero-match in loop detail sheet
        if ws.title == "4_无效循环-逐轮明细":
            for col_idx in range(1, max_col + 1):
                header = ws.cell(row=1, column=col_idx).value
                if str(header).strip() == "是否0匹配":
                    col_letter = get_column_letter(col_idx)
                    rng = f"{col_letter}2:{col_letter}{ws.max_row}"
                    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'ISNUMBER(SEARCH("是",{col_letter}2))'], fill=_FILL_RED))
                if str(header).strip() == "评测状态":
                    col_letter = get_column_letter(col_idx)
                    rng = f"{col_letter}2:{col_letter}{ws.max_row}"
                    ws.conditional_formatting.add(
                        rng, FormulaRule(formula=[f'ISNUMBER(SEARCH("未评测",{col_letter}2))'], fill=_FILL_GREY)
                    )
                    ws.conditional_formatting.add(
                        rng, FormulaRule(formula=[f'ISNUMBER(SEARCH("已评测",{col_letter}2))'], fill=_FILL_GREEN)
                    )

        # Heatmap for summary sheet
        if ws.title == "1_汇总(中心-模型)":
            for col_idx in range(1, max_col + 1):
                header = ws.cell(row=1, column=col_idx).value
                if not header:
                    continue
                h = str(header)
                if any(k in h for k in ["样本数", "病例数", "通过数"]):
                    continue
                if any(k in h for k in ["率", "均值", "评分", "命中", "覆盖"]):
                    col_letter = get_column_letter(col_idx)
                    rng = f"{col_letter}2:{col_letter}{ws.max_row}"
                    ws.conditional_formatting.add(
                        rng,
                        ColorScaleRule(
                            start_type="min",
                            start_color="F8696B",
                            mid_type="percentile",
                            mid_value=50,
                            mid_color="FFEB84",
                            end_type="max",
                            end_color="63BE7B",
                        ),
                    )
                    for row_idx in range(2, ws.max_row + 1):
                        cell = ws.cell(row=row_idx, column=col_idx)
                        if isinstance(cell.value, (int, float)):
                            cell.number_format = "0.000"

    # Add simple group header rows for key sheets (merge cells)
    _apply_group_headers(wb)
    wb.save(path)


def _apply_group_headers(wb) -> None:
    def add_group_row(sheet_name: str, groups: list[tuple[str, int, int]]) -> None:
        if sheet_name not in wb.sheetnames:
            return
        ws = wb[sheet_name]
        ws.insert_rows(1)
        for idx, (label, start, end) in enumerate(groups):
            group_fill = _GROUP_FILL_PALETTE[idx % len(_GROUP_FILL_PALETTE)]
            subheader_fill = _SUBHEADER_FILL_PALETTE[idx % len(_SUBHEADER_FILL_PALETTE)]
            ws.merge_cells(start_row=1, start_column=start, end_row=1, end_column=end)
            cell = ws.cell(row=1, column=start)
            cell.value = label
            cell.fill = group_fill
            cell.font = _GROUP_HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center")
            for c in range(start, end + 1):
                ws.cell(row=2, column=c).fill = subheader_fill
                ws.cell(row=2, column=c).font = _SUBHEADER_FONT
                ws.cell(row=2, column=c).alignment = Alignment(vertical="center")
        ws.freeze_panes = "A3"
        last_col = get_column_letter(ws.max_column)
        ws.auto_filter.ref = f"A2:{last_col}{ws.max_row}"

    # 2_病例-检查匹配
    add_group_row(
        "2_病例-检查匹配",
        groups=[
            ("基本信息", 1, 6),
            ("D1 检查匹配（可手算）", 7, 11),
            ("D2 检查匹配（可手算）", 12, 17),
        ],
    )

    # 3_病例-裁判评分
    add_group_row(
        "3_病例-裁判评分",
        groups=[
            ("基本信息", 1, 3),
            ("Gate1", 4, 8),
            ("Gate2", 9, 13),
            ("D3", 14, 17),
            ("D4", 18, 20),
        ],
    )

    # 2_病例-无效循环
    add_group_row(
        "2_病例-无效循环",
        groups=[
            ("基本信息", 1, 4),
            ("D1 无效循环（可手算）", 5, 10),
            ("D2 无效循环（可手算）", 11, 15),
        ],
    )

    # 5_需要复核-检查匹配
    add_group_row(
        "5_需要复核-检查匹配",
        groups=[
            ("定位信息", 1, 5),
            ("计数与原因(为何入表)", 6, 13),
            ("原文与判官字段(供核对)", 14, 19),
            ("你的反馈(请填写)", 20, 22),
        ],
    )
