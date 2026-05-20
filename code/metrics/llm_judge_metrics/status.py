from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import ast
import json

import pandas as pd

from .parsing import is_empty, parse_list_cell


@dataclass(frozen=True)
class StageStatus:
    stage: str
    status_raw: str
    is_evaluated: bool


STAGE_ORDER = [
    "D1_Outpatient_Loop",
    "D1_Outpatient_Decision",
    "D2_Admission_Loop",
    "D2_Admission_Decision",
    "D3_Surgery_Decision",
    "D4_Rehab_Plan",
]

_LOOP_STAGES = {"D1_Outpatient_Loop", "D2_Admission_Loop"}

_TERMINATION_STATUS_BASE = {
    "D1_Outpatient_Loop": "终止于门诊循环",
    "D1_Outpatient_Decision": "终止于门诊决策",
    "D2_Admission_Loop": "终止于入院循环",
    "D2_Admission_Decision": "终止于入院决策",
    "D3_Surgery_Decision": "终止于手术决策",
}


def _get_status_col(df: pd.DataFrame) -> str | None:
    if df.shape[1] < 2:
        return None
    return str(df.columns[1])


def _get_row(df: pd.DataFrame, case_id: str) -> pd.Series | None:
    if df.empty:
        return None
    cid_col = df.columns[0]
    sel = df.loc[df[cid_col].astype(str) == case_id]
    if sel.empty:
        return None
    return sel.iloc[0]


def _row_has_output_for_stage(stage: str, df: pd.DataFrame, row: pd.Series | None) -> bool:
    """
    Decide whether this case actually produced outputs in a stage.

    IMPORTANT: Do not use "any non-empty cell" as signal, because some sheets contain
    abnormal spill-over key-values/columns. Use stage-specific evidence fields.
    """
    if row is None or df.shape[1] <= 2:
        return False

    def any_nonempty_cols(cols: list[str]) -> bool:
        for c in cols:
            if c in df.columns and not is_empty(row.get(c)):
                return True
        return False

    if stage in {"D1_Outpatient_Loop", "D2_Admission_Loop"}:
        # Round raw JSON is the most reliable signal.
        round_cols = [f"第{r}轮_医生_原始JSON" for r in range(1, 5)]
        if any_nonempty_cols(round_cols):
            return True
        # Fallback: any "第r轮_医生_原始JSON_*" non-empty.
        for r in range(1, 5):
            prefix = f"第{r}轮_医生_原始JSON"
            cols = [c for c in df.columns if str(c).startswith(prefix)]
            if cols and any(not is_empty(row.get(c)) for c in cols):
                return True
        return False

    if stage in {"D1_Outpatient_Decision", "D2_Admission_Decision"}:
        # Prefer the raw JSON cell over derived boolean fields (which may default to False).
        raw_cols = [c for c in df.columns if str(c).strip() == "医生决策_原始JSON"]
        if raw_cols and not is_empty(row.get(raw_cols[0])):
            return True

        # Fallback: only consider rich-text evidence fields (avoid pure boolean flags).
        evidence_keys = [
            "初步诊断列表",
            "建议检查项目",
            "门诊信息汇总",
            "修正诊断",
            "初步治疗方案",
            "诊疗经过回顾",
            "治疗方案",
        ]
        evidence_cols = [c for c in df.columns if "医生决策_原始JSON_" in str(c) and any(k in str(c) for k in evidence_keys)]
        return any(evidence_cols) and any(not is_empty(row.get(c)) for c in evidence_cols)

    if stage in {"D3_Surgery_Decision", "D4_Rehab_Plan"}:
        # Prefer the raw JSON cell; avoid derived boolean fields (e.g., "是否需要常规随访").
        raw_cols = [c for c in df.columns if str(c).strip() == "医生_原始JSON"]
        if raw_cols and not is_empty(row.get(raw_cols[0])):
            return True

        evidence_keys = [
            "诊断名称",
            "方案详情",
            "信息汇总",
            "诊疗经过回顾",
            "制定依据",
        ]
        evidence_cols = [c for c in df.columns if str(c).startswith("医生_原始JSON_") and any(k in str(c) for k in evidence_keys)]
        return any(evidence_cols) and any(not is_empty(row.get(c)) for c in evidence_cols)

    # Unknown stage: conservative fallback
    return False


def _infer_loop_rounds_executed(df: pd.DataFrame, row: pd.Series | None) -> int:
    if row is None:
        return 0
    max_round = 0
    for r in range(1, 5):
        col = f"第{r}轮_医生_原始JSON"
        if col in df.columns and not is_empty(row.get(col)):
            max_round = r
    if max_round:
        return max_round
    # Fallback: look at any non-empty "第r轮_" column.
    for r in range(1, 5):
        prefix = f"第{r}轮_"
        cols = [c for c in df.columns[2:] if str(c).startswith(prefix)]
        if any(cols) and any(not is_empty(row.get(c)) for c in cols):
            max_round = r
    return max_round


def stage_status_map(doc_sheets: dict[str, pd.DataFrame], case_id: str) -> dict[str, StageStatus]:
    out: dict[str, StageStatus] = {}
    for stage, df in doc_sheets.items():
        status_col = _get_status_col(df)
        if not status_col:
            out[stage] = StageStatus(stage=stage, status_raw="", is_evaluated=False)
            continue
        r = _get_row(df, case_id)
        if r is None:
            out[stage] = StageStatus(stage=stage, status_raw="", is_evaluated=False)
            continue
        status_raw = str(r.get(status_col, "")).strip()
        # Prefer evidence-based evaluation to avoid doc-status drift:
        # - has output -> evaluated
        # - otherwise, fall back to status text
        has_output = _row_has_output_for_stage(stage, df, r)
        is_eval = has_output or (status_raw != "" and status_raw != "未经过")
        out[stage] = StageStatus(stage=stage, status_raw=status_raw, is_evaluated=is_eval)
    return out


def infer_flow_status_row(doc_sheets: dict[str, pd.DataFrame], case_id: str) -> dict[str, Any]:
    """
    Infer per-stage execution/status + global flow end from sheet content (not just column-B status).
    Returns a flat dict (good for DataFrame rows).
    """
    stages = list(STAGE_ORDER)
    stage_map: dict[str, dict[str, Any]] = {}

    for stage in stages:
        df = doc_sheets.get(stage)
        if df is None or df.empty:
            stage_map[stage] = {"status_raw": "", "has_output": False, "rounds_executed": 0}
            continue
        r = _get_row(df, case_id)
        status_col = _get_status_col(df)
        status_raw = "" if (r is None or not status_col) else str(r.get(status_col, "")).strip()
        has_output = _row_has_output_for_stage(stage, df, r)
        rounds_executed = _infer_loop_rounds_executed(df, r) if stage in _LOOP_STAGES else 0
        stage_map[stage] = {"status_raw": status_raw, "has_output": has_output, "rounds_executed": rounds_executed}

    executed_stages = [s for s in stages if stage_map.get(s, {}).get("has_output") is True]
    flow_end_stage = executed_stages[-1] if executed_stages else "NOT_STARTED"
    flow_end_detail = flow_end_stage
    if flow_end_stage in _LOOP_STAGES:
        r = int(stage_map.get(flow_end_stage, {}).get("rounds_executed") or 0)
        if r > 0:
            flow_end_detail = f"{flow_end_stage}_R{r}"

    issues: list[str] = []
    inferred_status: dict[str, str] = {}
    flow_end_label = ""
    if flow_end_stage == "NOT_STARTED":
        flow_end_label = "未开始"
    elif flow_end_stage == "D4_Rehab_Plan":
        flow_end_label = "流程完成"
    else:
        flow_end_label = _TERMINATION_STATUS_BASE.get(flow_end_stage, flow_end_stage)

    for idx, stage in enumerate(stages):
        raw = str(stage_map[stage]["status_raw"]).strip()
        has_output = bool(stage_map[stage]["has_output"])
        rounds_executed = int(stage_map[stage]["rounds_executed"] or 0)
        next_stage = stages[idx + 1] if idx + 1 < len(stages) else None
        next_has_output = bool(stage_map.get(next_stage, {}).get("has_output")) if next_stage else False
        later_has_output = any(bool(stage_map.get(s, {}).get("has_output")) for s in stages[idx + 1 :])

        # Infer status with minimal "safe" corrections.
        if flow_end_stage != "NOT_STARTED" and stages.index(stage) > stages.index(flow_end_stage):
            # After the flow ends, keep NOT_EVALUATED meaning but annotate the reason.
            inferred = f"未经过（流程{flow_end_label}）" if flow_end_label else "未经过"
        elif not has_output:
            if raw and raw != "未经过":
                issues.append(f"{stage}:status_but_no_output")
            # Decision stages are expected to exist if later stages have outputs.
            if stage in {"D1_Outpatient_Decision", "D2_Admission_Decision", "D3_Surgery_Decision", "D4_Rehab_Plan"} and later_has_output:
                issues.append(f"{stage}:no_output_but_later_has_output")
            inferred = "未经过"
        else:
            if raw in {"", "未经过"}:
                issues.append(f"{stage}:output_but_status_{raw or 'EMPTY'}")
            if "终止" in raw and next_has_output:
                issues.append(f"{stage}:terminated_but_next_has_output")

            # If loop is last executed stage and next decision not executed -> mark termination at loop.
            if stage == flow_end_stage and stage != "D4_Rehab_Plan" and not next_has_output:
                base = _TERMINATION_STATUS_BASE.get(stage, "终止")
                inferred = f"{base}（第{rounds_executed}轮后）" if rounds_executed > 0 else base
            elif stage == "D4_Rehab_Plan":
                inferred = "顺利通过（流程完成）"
            elif "终止" in raw and not next_has_output:
                # Keep termination label if it is truly the end.
                inferred = raw
            else:
                # Prefer existing non-empty status (e.g., 顺利通过/终止于XX) else default to 顺利通过.
                inferred = raw if raw and raw != "未经过" and not ("终止" in raw and next_has_output) else "顺利通过"

        inferred_status[stage] = inferred

    out: dict[str, Any] = {"case_id": case_id, "flow_end_stage": flow_end_stage, "flow_end_detail": flow_end_detail, "issues": "; ".join(issues)}
    for stage in stages:
        out[f"doc_status_raw__{stage}"] = stage_map[stage]["status_raw"]
        out[f"has_output__{stage}"] = bool(stage_map[stage]["has_output"])
        out[f"rounds_executed__{stage}"] = int(stage_map[stage]["rounds_executed"] or 0)
        out[f"doc_status_inferred__{stage}"] = inferred_status[stage]
        out[f"status_changed__{stage}"] = str(stage_map[stage]["status_raw"]).strip() != inferred_status[stage]
        out[f"is_evaluated_inferred__{stage}"] = inferred_status[stage] != "未经过"
    return out


def detect_d1_decision_anomaly(doc_d1_decision: pd.DataFrame, doc_d2_decision: pd.DataFrame | None = None) -> set[str]:
    # Same rule as data-dictionary generator (v1):
    # - has revised_dx or treatment text
    # - AND does NOT have prelim diagnosis/checks (both empty)
    def find_cols(sub: str) -> list[str]:
        return [c for c in doc_d1_decision.columns if sub in str(c)]

    cols_prelim_dx = find_cols("初步诊断列表")
    cols_prelim_checks = find_cols("建议检查项目")
    cols_revised_dx = [c for c in doc_d1_decision.columns if "修正诊断" in str(c) and "思维" not in str(c)]
    cols_treatment = [c for c in doc_d1_decision.columns if "治疗方案" in str(c) and "思维" not in str(c)]
    cols_need_more = find_cols("需要进一步检查")
    cols_need_out = find_cols("需要补充门诊检查")

    cols_raw = find_cols("医生决策_原始JSON")

    def _has_text(v: Any) -> bool:
        if is_empty(v):
            return False
        s = str(v).strip()
        if not s:
            return False
        if s in {"无", "无。", "无.", "none", "None", "N/A", "NA"}:
            return False
        return True

    def _parse_json_like(v: Any) -> Any | None:
        if is_empty(v):
            return None
        if isinstance(v, (dict, list)):
            return v
        s = str(v).strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            try:
                return ast.literal_eval(s)
            except Exception:
                return None

    def _json_has_key_value(v: Any, keys: list[str]) -> bool:
        if is_empty(v):
            return False
        obj = _parse_json_like(v)
        if isinstance(obj, dict):
            return any(_has_text(obj.get(k)) for k in keys)
        if isinstance(obj, list):
            return any(k in str(obj) for k in keys)
        if obj is None:
            s = str(v)
            return any(k in s for k in keys)
        return False

    def _json_get(v: Any, key: str) -> Any | None:
        if is_empty(v):
            return None
        obj = _parse_json_like(v)
        if isinstance(obj, dict):
            return obj.get(key)
        return None

    anomalies: set[str] = set()
    if doc_d1_decision.shape[1] < 2:
        doc_d1_decision = pd.DataFrame(columns=doc_d1_decision.columns)
    case_col = doc_d1_decision.columns[0]

    for _, row in doc_d1_decision.iterrows():
        case_id = str(row.get(case_col, "")).strip()
        if not case_id:
            continue

        # Only treat rows with real outputs as candidates.
        if not _row_has_output_for_stage("D1_Outpatient_Decision", doc_d1_decision, row):
            continue

        has_revised = any(_has_text(row.get(c)) for c in cols_revised_dx)
        has_treat = any(_has_text(row.get(c)) for c in cols_treatment)
        if cols_raw:
            has_revised = has_revised or any(_json_has_key_value(row.get(c), ["修正诊断"]) for c in cols_raw)
            has_treat = has_treat or any(_json_has_key_value(row.get(c), ["治疗方案", "初步治疗方案"]) for c in cols_raw)
        has_special = bool(has_revised or has_treat)

        has_prelim_dx = any(parse_list_cell(row.get(c)) for c in cols_prelim_dx)
        has_prelim_checks = any(parse_list_cell(row.get(c)) for c in cols_prelim_checks)
        if cols_raw:
            for c in cols_raw:
                v = _json_get(row.get(c), "初步诊断列表")
                if parse_list_cell(v):
                    has_prelim_dx = True
                    break
            for c in cols_raw:
                v = _json_get(row.get(c), "建议检查项目")
                if parse_list_cell(v):
                    has_prelim_checks = True
                    break

        # Special case rule (user-confirmed):
        # D1 outputs are actually D2-like (revised dx + treatment) AND no prelim dx/checks,
        # AND both "need outpatient check" and "need further check" are FALSE.
        if has_special:
            def _boolish(v: Any) -> bool | None:
                if is_empty(v):
                    return None
                if isinstance(v, bool):
                    return bool(v)
                s = str(v).strip().lower()
                if s in {"true", "1", "yes", "y", "是"}:
                    return True
                if s in {"false", "0", "no", "n", "否"}:
                    return False
                return None

            need_more = None
            for c in cols_need_more:
                b = _boolish(row.get(c))
                if b is not None:
                    need_more = b
                    break
            need_out = None
            for c in cols_need_out:
                b = _boolish(row.get(c))
                if b is not None:
                    need_out = b
                    break
            if cols_raw and need_more is None:
                for c in cols_raw:
                    b = _boolish(_json_get(row.get(c), "需要进一步检查"))
                    if b is not None:
                        need_more = b
                        break
            if cols_raw and need_out is None:
                for c in cols_raw:
                    b = _boolish(_json_get(row.get(c), "需要补充门诊检查"))
                    if b is not None:
                        need_out = b
                        break
            if not has_prelim_dx and not has_prelim_checks:
                # If either "need more check" is True, this is a normal D1 decision (not special).
                if need_more is True or need_out is True:
                    continue
                anomalies.add(case_id)
            continue

        # NOTE: previously we flagged “staging/workup list” items (e.g., many “待排”) as anomalies,
        # but this caused false positives for normal D1 decisions with multiple differential diagnoses.
        # Keep the anomaly rule strictly to special-case D1 (revised dx + treatment, no prelim dx/checks).
        continue

    # --- Fallback: detect special cases from D2 decision when D1 is empty/missing.
    if doc_d2_decision is not None and not doc_d2_decision.empty:
        d2 = doc_d2_decision
        case_ids: set[str] = set()
        if not doc_d1_decision.empty:
            cid_col = doc_d1_decision.columns[0]
            case_ids |= set(doc_d1_decision[cid_col].dropna().astype(str).tolist())
        cid2 = d2.columns[0]
        case_ids |= set(d2[cid2].dropna().astype(str).tolist())

        d1_keys = [
            "初步诊断列表",
            "建议检查项目",
            "初步诊断思维",
            "建议检查思维",
            "需要进一步检查",
            "需要补充门诊检查",
        ]
        d2_keys = [
            "修正诊断",
            "初步治疗方案",
            "治疗方案",
            "诊疗经过回顾",
        ]

        raw_cols_d2 = [c for c in d2.columns if "医生决策_原始JSON" in str(c)]

        def _raw_has_keys(v: Any, keys: list[str]) -> bool:
            if is_empty(v):
                return False
            s = str(v).strip()
            if not s:
                return False
            obj = _parse_json_like(v)
            if isinstance(obj, dict):
                for k in keys:
                    if k in obj and _has_text(obj.get(k)):
                        return True
                return False
            if isinstance(obj, list):
                return any(k in str(obj) for k in keys)
            if obj is None:
                return any(k in s for k in keys)
            return False

        for case_id in case_ids:
            case_id = str(case_id).strip()
            if not case_id or case_id in anomalies:
                continue
            # If D1 has output, we already handled above.
            d1_row = None
            if not doc_d1_decision.empty:
                sel = doc_d1_decision.loc[doc_d1_decision[doc_d1_decision.columns[0]].astype(str) == case_id]
                if not sel.empty:
                    d1_row = sel.iloc[0]
            if d1_row is not None and _row_has_output_for_stage("D1_Outpatient_Decision", doc_d1_decision, d1_row):
                continue

            # D2 must have output.
            sel2 = d2.loc[d2[cid2].astype(str) == case_id]
            if sel2.empty:
                continue
            d2_row = sel2.iloc[0]
            if not _row_has_output_for_stage("D2_Admission_Decision", d2, d2_row):
                continue

            raw_val = d2_row.get(raw_cols_d2[0]) if raw_cols_d2 else None
            has_d1_keys = _raw_has_keys(raw_val, d1_keys) or any(
                (k in str(c) and not is_empty(d2_row.get(c))) for c in d2.columns for k in d1_keys
            )
            if has_d1_keys:
                # Likely a misplacement (D1 content stored in D2). Do not mark as special.
                continue

            has_d2_keys = _raw_has_keys(raw_val, d2_keys) or any(
                (k in str(c) and not is_empty(d2_row.get(c))) for c in d2.columns for k in d2_keys
            )
            if has_d2_keys:
                anomalies.add(case_id)

    return anomalies


def detect_d1_skipped_to_d2(doc_sheets: dict[str, pd.DataFrame]) -> set[str]:
    """
    Identify cases that skipped D1 entirely but have D2 outputs.
    Rule (user-confirmed):
      - D1 loop NOT evaluated AND D1 decision NOT evaluated
      - AND D2 loop OR D2 decision has output
    """
    case_ids: set[str] = set()
    for df in doc_sheets.values():
        if df is None or df.empty:
            continue
        cid_col = df.columns[0]
        case_ids |= set(df[cid_col].dropna().astype(str).str.strip().tolist())

    special: set[str] = set()
    for cid in case_ids:
        if not cid:
            continue
        row = infer_flow_status_row(doc_sheets, cid)
        d1_loop_eval = bool(row.get("is_evaluated_inferred__D1_Outpatient_Loop"))
        d1_dec_eval = bool(row.get("is_evaluated_inferred__D1_Outpatient_Decision"))
        has_d2 = bool(row.get("has_output__D2_Admission_Loop")) or bool(row.get("has_output__D2_Admission_Decision"))
        if (not d1_loop_eval) and (not d1_dec_eval) and has_d2:
            special.add(cid)
    return special



def safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        if isinstance(v, float) and pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None
