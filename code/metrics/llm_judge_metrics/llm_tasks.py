from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .checks import _likely_same_check
from .parsing import is_empty, parse_check_list_cell, parse_list_cell, parse_wuhan_dx
from .status import detect_d1_decision_anomaly
from .types import LoadedData


def _load_prompt_template(project_root: Path, prompt_rel_path: str) -> str:
    path = project_root / prompt_rel_path
    return path.read_text(encoding="utf-8")


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _render_template(tpl: str, variables: dict[str, Any]) -> str:
    out = tpl
    for k, v in variables.items():
        out = out.replace("{{" + k + "}}", "" if v is None else str(v))
    return out


def generate_d1_diagnosis_topk_tasks(
    project_root: Path,
    loaded: LoadedData,
    allowed_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_diagnosis_semantic_match.md` (D1 only; k={1,3,5}).
    Inputs must be from Excel extracted columns only.
    """
    prompt_rel = "prompts/llm_diagnosis_semantic_match.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt_map = {}
    if "GT_Admission_Diagnosis" in gt.columns:
        for _, r in gt.iterrows():
            cid = str(r.get("CaseID", "")).strip()
            if not cid:
                continue
            gt_map[cid] = r.get("GT_Admission_Diagnosis")

    doc = loaded.doc_sheets["D1_Outpatient_Decision"]
    cid_col = doc.columns[0]
    ai_col = "医生决策_原始JSON_初步诊断列表"
    tasks: list[dict[str, Any]] = []
    anomalies = detect_d1_decision_anomaly(doc, None)

    for _, r in doc.iterrows():
        case_id = str(r.get(cid_col, "")).strip()
        if not case_id:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        # Special-case: D1 decision anomaly output (has revised dx / treatment but lacks prelim dx/checks)
        # should NOT participate in D1 preliminary diagnosis Top-k evaluation.
        if case_id in anomalies:
            continue
        gt_text_raw = gt_map.get(case_id)
        gt_text = "" if is_empty(gt_text_raw) else str(gt_text_raw)
        if not gt_text.strip():
            continue

        # Wuhan: split template, only use primary for Top-k main metric.
        if loaded.fileset.center == "武汉" and gt_text:
            parsed = parse_wuhan_dx(gt_text)
            if parsed.primary:
                gt_text = "\n".join(parsed.primary)

        ai_raw = r.get(ai_col) if ai_col in doc.columns else ""
        ai_list = parse_list_cell(ai_raw)
        # Some rare D1-decision outputs are actually "staging / workup items" mixed into the diagnosis list
        # (e.g., many entries end with “待排/转移/浸润/分期”), which should NOT be evaluated as D1 preliminary Top-k.
        if ai_list:
            suspicious_terms = ["待排", "转移", "浸润", "分期", "分级", "肌层浸润"]
            suspicious = sum(1 for s in ai_list if any(t in str(s) for t in suspicious_terms))
            if len(ai_list) >= 3 and suspicious >= max(2, int(len(ai_list) * 0.6)):
                continue
        ai_text = "\n".join(ai_list) if ai_list else ("" if is_empty(ai_raw) else str(ai_raw))
        if not ai_text.strip():
            # No preliminary diagnosis list -> skip
            continue

        variables = {
            "case_id": case_id,
            "stage": "D1",
            "gt_diagnosis_text": gt_text,
            "ai_diagnosis_list_text": ai_text,
            "strictness": json.dumps({"require_staging": False}, ensure_ascii=False),
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.diagnosis_semantic_match",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|D1|topk",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": "D1",
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    return tasks


def _build_gt_facts_text(gt_row: pd.Series) -> str:
    fact_cols = [
        "BasicInfo",
        "ChiefComplaint",
        "PresentIllness",
        "PastHistory",
        "MenstrualHistory",
        "FamilyHistory",
        "PhysicalExam",
        "GT_Patient_Wishes",
    ]
    parts: list[str] = []
    for c in fact_cols:
        if c not in gt_row.index:
            continue
        v = gt_row.get(c)
        if is_empty(v):
            continue
        parts.append(f"{c}: {str(v).strip()}")
    return "\n".join(parts)


def _build_gt_context_for_stage(gt_row: pd.Series, stage: str) -> str:
    """
    Build a stage-aware GT context block for LLM judge tasks.
    Goal: avoid false hallucination flags caused by missing GT evidence in prompt.
    """
    stage_key = str(stage).strip().upper()
    if stage_key.startswith("D1"):
        extra_cols = ["GT_Outpatient_Checks", "GT_Admission_Diagnosis"]
    elif stage_key.startswith("D2"):
        extra_cols = [
            "GT_Outpatient_Checks",
            "GT_Admission_Diagnosis",
            "GT_Admission_Checks",
            "GT_Revised_Diagnosis",
            "GT_Surgery_Plan",
        ]
    elif stage_key.startswith("D3"):
        extra_cols = [
            "GT_Outpatient_Checks",
            "GT_Admission_Diagnosis",
            "GT_Admission_Checks",
            "GT_Revised_Diagnosis",
            "GT_Surgery_Plan",
            "GT_Pathology",
            "GT_Surgery_Findings",
            "GT_Final_Diagnosis",
            "GT_PostOp_Plan",
        ]
    elif stage_key.startswith("D4"):
        extra_cols = ["GT_Final_Diagnosis", "GT_Rehab_Plan", "GT_Followup_Plan"]
    else:
        extra_cols = []

    parts: list[str] = []
    base = _build_gt_facts_text(gt_row)
    if base.strip():
        parts.append(base.strip())

    for c in extra_cols:
        if c not in gt_row.index:
            continue
        v = gt_row.get(c)
        if is_empty(v):
            continue
        parts.append(f"{c}: {str(v).strip()}")

    return "\n\n".join(parts)


def _build_gt_reference_for_stage(gt_row: pd.Series, stage: str) -> str:
    """
    Build a stage-aware *reference* GT block.

    This is used to provide historical evidence context, so D3/D4 recap text that
    mentions earlier verified facts is not over-penalized as hallucination.
    """
    stage_key = str(stage).strip().upper()
    if stage_key.startswith("D1"):
        ref_cols: list[str] = []
    elif stage_key.startswith("D2"):
        ref_cols = ["GT_Outpatient_Checks"]
    elif stage_key.startswith("D3"):
        ref_cols = [
            "GT_Outpatient_Checks",
            "GT_Admission_Diagnosis",
            "GT_Admission_Checks",
            "GT_Revised_Diagnosis",
            "GT_Surgery_Plan",
        ]
    elif stage_key.startswith("D4"):
        ref_cols = [
            "GT_Outpatient_Checks",
            "GT_Admission_Diagnosis",
            "GT_Admission_Checks",
            "GT_Revised_Diagnosis",
            "GT_Surgery_Plan",
            "GT_PostOp_Plan",
            "GT_Surgery_Findings",
            "GT_Pathology",
        ]
    else:
        ref_cols = []

    parts: list[str] = []
    for c in ref_cols:
        if c not in gt_row.index:
            continue
        v = gt_row.get(c)
        if is_empty(v):
            continue
        parts.append(f"{c}: {str(v).strip()}")
    return "\n\n".join(parts)


def _get_row_by_case_id(df: pd.DataFrame, case_id: str) -> pd.Series | None:
    if df is None or df.empty:
        return None
    cid_col = df.columns[0]
    sel = df.loc[df[cid_col].astype(str) == str(case_id)]
    if sel.empty:
        return None
    return sel.iloc[0]


def generate_unmatched_check_reasonableness_tasks(
    project_root: Path,
    loaded: LoadedData,
    allowed_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_unmatched_check_reasonableness.md`.

    Output granularity: case × stage (D1_Outpatient / D2_Admission), aggregated across rounds.
    """
    prompt_rel = "prompts/llm_unmatched_check_reasonableness.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt.copy()
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.set_index(gt["CaseID"].astype(str), drop=False)

    tasks: list[dict[str, Any]] = []

    def emit_for_stage(stage: str) -> None:
        if stage == "D1_Outpatient":
            doc = loaded.doc_sheets["D1_Outpatient_Loop"]
            judge = loaded.judge_sheets["D1_Outpatient_Loop"]
            req_patterns = [
                "第{r}轮_医生_原始JSON_诊断前所需检查（优先）",
                "第{r}轮_医生_原始JSON_诊断前所需检查(优先)",
                "第{r}轮_医生_原始JSON_诊断前所需检查",
                # Some exports use this synonym in loop outputs (rare but observed).
                "第{r}轮_医生_原始JSON_建议检查项目",
                # Legacy exports may store the list under this key.
                "第{r}轮_医生_原始JSON_需要补充检查",
            ]
            rationale_pat = "第{r}轮_医生_原始JSON_理由"
            unmatched_pat = "第{r}轮_判官_原始JSON_AI建议但实际未执行的检查"
            gt_checks_col = "GT_Outpatient_Checks"
        else:
            # D2 admission: include D1 decision suggestions + D2 loop
            doc_loop = loaded.doc_sheets["D2_Admission_Loop"]
            judge_loop = loaded.judge_sheets["D2_Admission_Loop"]
            doc_dec = loaded.doc_sheets["D1_Outpatient_Decision"]
            judge_dec = loaded.judge_sheets["D1_Outpatient_Decision"]
            judge_d1_loop = loaded.judge_sheets["D1_Outpatient_Loop"]

            # We will aggregate (case_id -> lists) manually below.
            req_patterns = []
            rationale_pat = ""
            unmatched_pat = ""
            gt_checks_col = "GT_Admission_Checks"

        # Helper: aggregate by case_id
        if stage == "D1_Outpatient":
            case_col = doc.columns[0]
            case_ids = [str(x) for x in doc[case_col].dropna().astype(str).unique()]
        else:
            # Use D1 decision as anchor to avoid missing cases that did not enter D2 loop.
            case_col = doc_dec.columns[0]
            case_ids = [str(x) for x in doc_dec[case_col].dropna().astype(str).unique()]

        for case_id in case_ids:
            if allowed_case_ids is not None and case_id not in allowed_case_ids:
                continue
            if case_id not in gt.index:
                continue
            gt_row = gt.loc[case_id]
            gt_facts = _build_gt_facts_text(gt_row)

            # Stage-specific GT checks: D1 only outpatient; D2 includes outpatient + admission.
            gt_checks_parts: list[str] = []
            out_checks = gt_row.get("GT_Outpatient_Checks") if "GT_Outpatient_Checks" in gt_row.index else None
            adm_checks = gt_row.get("GT_Admission_Checks") if "GT_Admission_Checks" in gt_row.index else None
            if stage == "D1_Outpatient":
                if not is_empty(out_checks):
                    gt_checks_parts.append(f"GT_门诊检查:\\n{str(out_checks).strip()}")
            else:
                if not is_empty(out_checks):
                    gt_checks_parts.append(f"GT_门诊检查:\\n{str(out_checks).strip()}")
                if not is_empty(adm_checks):
                    gt_checks_parts.append(f"GT_入院检查:\\n{str(adm_checks).strip()}")
            gt_checks_text = "\\n\\n".join(gt_checks_parts) if gt_checks_parts else ""

            ai_requested: list[str] = []
            judge_matched: list[str] = []
            unmatched: list[str] = []
            rationales: list[str] = []
            prior_matched: list[str] = []

            if stage == "D1_Outpatient":
                doc_row = doc.loc[doc[case_col].astype(str) == case_id]
                judge_row = judge.loc[judge[judge.columns[0]].astype(str) == case_id]
                if doc_row.empty:
                    continue
                doc_r = doc_row.iloc[0]
                judge_r = judge_row.iloc[0] if not judge_row.empty else None

                for r in range(1, 5):
                    req_col = next((pat.format(r=r) for pat in req_patterns if pat.format(r=r) in doc.columns), None)
                    if req_col:
                        ai_requested.extend(parse_check_list_cell(doc_r.get(req_col)))
                    rat_col = rationale_pat.format(r=r)
                    if rat_col in doc.columns and not is_empty(doc_r.get(rat_col)):
                        rationales.append(f"Round{r}: {str(doc_r.get(rat_col)).strip()}")
                    un_col = unmatched_pat.format(r=r)
                    if judge_r is not None and un_col in judge.columns:
                        unmatched.extend(parse_list_cell(judge_r.get(un_col)))
                    m_col = f"第{r}轮_判官_原始JSON_匹配的检查项目"
                    if judge_r is not None and m_col in judge.columns:
                        judge_matched.extend(parse_list_cell(judge_r.get(m_col)))

            else:
                # D2: part A - D1 decision suggested admission checks
                doc_dec_row = doc_dec.loc[doc_dec[doc_dec.columns[0]].astype(str) == case_id]
                judge_dec_row = judge_dec.loc[judge_dec[judge_dec.columns[0]].astype(str) == case_id]
                if not doc_dec_row.empty:
                    d = doc_dec_row.iloc[0]
                    if "医生决策_原始JSON_建议检查项目" in doc_dec.columns:
                        ai_requested.extend(parse_check_list_cell(d.get("医生决策_原始JSON_建议检查项目")))
                    if "医生决策_原始JSON_建议检查思维" in doc_dec.columns and not is_empty(d.get("医生决策_原始JSON_建议检查思维")):
                        rationales.append(f"D1Decision: {str(d.get('医生决策_原始JSON_建议检查思维')).strip()}")
                if not judge_dec_row.empty:
                    j = judge_dec_row.iloc[0]
                    if "Gate1判官_原始JSON_检查匹配_匹配的检查项目" in judge_dec.columns:
                        judge_matched.extend(parse_list_cell(j.get("Gate1判官_原始JSON_检查匹配_匹配的检查项目")))
                    if "Gate1判官_原始JSON_检查匹配_未匹配的检查项目" in judge_dec.columns:
                        unmatched.extend(parse_list_cell(j.get("Gate1判官_原始JSON_检查匹配_未匹配的检查项目")))

                # part B - D2 loop
                doc_loop_row = doc_loop.loc[doc_loop[doc_loop.columns[0]].astype(str) == case_id]
                judge_loop_row = judge_loop.loc[judge_loop[judge_loop.columns[0]].astype(str) == case_id]
                if doc_loop_row.empty:
                    # still allow tasks if D1 decision had unmatched
                    pass
                else:
                    d = doc_loop_row.iloc[0]
                    j = judge_loop_row.iloc[0] if not judge_loop_row.empty else None
                    for r in range(1, 5):
                        req_col = f"第{r}轮_医生_原始JSON_需要补充检查"
                        if req_col in doc_loop.columns:
                            ai_requested.extend(parse_check_list_cell(d.get(req_col)))
                        rat_col = f"第{r}轮_医生_原始JSON_理由"
                        if rat_col in doc_loop.columns and not is_empty(d.get(rat_col)):
                            rationales.append(f"Round{r}: {str(d.get(rat_col)).strip()}")
                        un_col = f"第{r}轮_判官_原始JSON_AI建议但实际未执行的检查"
                        if j is not None and un_col in judge_loop.columns:
                            unmatched.extend(parse_list_cell(j.get(un_col)))
                        m_col = f"第{r}轮_判官_原始JSON_匹配的检查项目"
                        if j is not None and m_col in judge_loop.columns:
                            judge_matched.extend(parse_list_cell(j.get(m_col)))

                # D2 redundancy reference: D1 loop matched checks (已在门诊执行/匹配)
                d1_judge_row = judge_d1_loop.loc[judge_d1_loop[judge_d1_loop.columns[0]].astype(str) == case_id]
                if not d1_judge_row.empty:
                    jr = d1_judge_row.iloc[0]
                    for r in range(1, 5):
                        m_col = f"第{r}轮_判官_原始JSON_匹配的检查项目"
                        if m_col in judge_d1_loop.columns:
                            prior_matched.extend(parse_list_cell(jr.get(m_col)))

            # Dedupe (preserve order)
            def dedupe(xs: list[str]) -> list[str]:
                seen = set()
                out = []
                for x in xs:
                    key = x.strip()
                    if not key:
                        continue
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(key)
                return out

            ai_requested = dedupe(ai_requested)
            judge_matched = dedupe(judge_matched)
            unmatched = dedupe(unmatched)
            prior_matched = dedupe(prior_matched)

            if not unmatched:
                continue

            # Filter judge lists to AI-requested items; then compute unmatched by AI items.
            unmatched_to_judge: list[str] = []
            if ai_requested:
                judge_matched = [x for x in judge_matched if any(_likely_same_check(x, a) for a in ai_requested)]
                unmatched = [x for x in unmatched if any(_likely_same_check(x, a) for a in ai_requested)]
                if judge_matched or unmatched:
                    matched_flags = []
                    for a in ai_requested:
                        matched_flags.append(any(_likely_same_check(a, m) for m in judge_matched))
                    unmatched_to_judge = [a for a, is_matched in zip(ai_requested, matched_flags) if not is_matched]
            else:
                unmatched_to_judge = list(unmatched)

            if not unmatched_to_judge:
                continue

            variables = {
                "case_id": case_id,
                "stage": stage,
                "gt_facts": gt_facts,
                "gt_checks_text": gt_checks_text,
                "ai_requested_checks_all": "\n".join(ai_requested),
                "judge_matched_checks_all": "\n".join(judge_matched),
                "judge_unmatched_checks_all": "\n".join(unmatched),
                "unmatched_checks_to_judge": "\n".join(unmatched_to_judge),
                "prior_matched_checks": "\n".join(prior_matched),
                "ai_rationale": "\n".join(rationales),
                "prompt_sha256": prompt_sha256,
            }
            prompt = _render_template(tpl, variables)
            tasks.append(
                {
                    "task": "llm.unmatched_check_reasonableness",
                    "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|{stage}|unmatched_reasonableness",
                    "center": loaded.fileset.center,
                    "model": loaded.fileset.model,
                    "case_id": case_id,
                    "stage": stage,
                    "prompt_template": prompt_rel,
                    "inputs": variables,
                    "prompt": prompt,
                }
            )

    emit_for_stage("D1_Outpatient")
    emit_for_stage("D2_Admission")
    return tasks


def generate_rationale_quality_tasks(
    project_root: Path,
    loaded: LoadedData,
    allowed_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_rationale_quality.md`.

    Stages:
    - D1_Outpatient_Loop (aggregate round rationales)
    - D2_Admission_Loop (aggregate round rationales)
    - D1_Outpatient_Decision
    - D2_Admission_Decision
    - D3_Surgery_Decision
    - D4_Rehab_Plan
    """
    prompt_rel = "prompts/llm_rationale_quality.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt.copy()
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.set_index(gt["CaseID"].astype(str), drop=False)

    anomalies = detect_d1_decision_anomaly(
        loaded.doc_sheets["D1_Outpatient_Decision"],
        loaded.doc_sheets.get("D2_Admission_Decision"),
    )

    def _fmt_list(val: Any, parser: Callable[[Any], list[str]]) -> str:
        items = parser(val)
        if items:
            return "；".join(items)
        if is_empty(val):
            return ""
        return str(val).strip()

    def _append_if(parts: list[str], label: str, value: str) -> None:
        if value:
            parts.append(f"{label}: {value}")

    def _build_gt_rationale_context(gt_row: pd.Series, stage: str) -> str:
        base_cols = [
            "BasicInfo",
            "ChiefComplaint",
            "PresentIllness",
            "PhysicalExam",
            "PastHistory",
            "FamilyHistory",
            "MenstrualHistory",
        ]
        stage_key = str(stage).strip()
        if stage_key == "D1_Outpatient_Loop":
            extra_cols: list[str] = []
        elif stage_key == "D2_Admission_Loop":
            extra_cols = ["GT_Outpatient_Checks", "GT_Admission_Diagnosis"]
        elif stage_key == "D1_Outpatient_Decision":
            extra_cols = ["GT_Outpatient_Checks"]
        elif stage_key == "D2_Admission_Decision":
            extra_cols = ["GT_Outpatient_Checks", "GT_Admission_Checks", "GT_Admission_Diagnosis"]
        elif stage_key == "D3_Surgery_Decision":
            extra_cols = [
                "GT_Outpatient_Checks",
                "GT_Admission_Checks",
                "GT_Admission_Diagnosis",
                "GT_Revised_Diagnosis",
                "GT_Surgery_Plan",
                "GT_Pathology",
                "GT_Surgery_Findings",
                "GT_Patient_Wishes",
            ]
        elif stage_key == "D4_Rehab_Plan":
            extra_cols = [
                "GT_Outpatient_Checks",
                "GT_Admission_Checks",
                "GT_Admission_Diagnosis",
                "GT_Revised_Diagnosis",
                "GT_Surgery_Plan",
                "GT_Pathology",
                "GT_Surgery_Findings",
                "GT_Patient_Wishes",
                "GT_Final_Diagnosis",
                "GT_PostOp_Plan",
            ]
        else:
            extra_cols = []

        cols = base_cols + extra_cols
        parts: list[str] = []
        for c in cols:
            if c not in gt_row.index:
                continue
            v = gt_row.get(c)
            if is_empty(v):
                continue
            parts.append(f"{c}: {str(v).strip()}")
        return "\n".join(parts)

    tasks: list[dict[str, Any]] = []

    def emit(case_id: str, stage: str, ai_output_text: str, ai_rationale_text: str) -> None:
        if not ai_output_text.strip() and not ai_rationale_text.strip():
            return
        gt_row = gt.loc[case_id] if case_id in gt.index else None
        gt_facts = _build_gt_rationale_context(gt_row, stage) if gt_row is not None else ""
        variables = {
            "case_id": case_id,
            "stage": stage,
            "gt_facts": gt_facts,
            "ai_output_text": ai_output_text,
            "ai_rationale_text": ai_rationale_text,
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.rationale_quality",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|{stage}|rationale_quality",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": stage,
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    # Anchor case_ids from D1 decision (covers all cases; loop may be missing)
    d1_dec = loaded.doc_sheets["D1_Outpatient_Decision"]
    cid_col = d1_dec.columns[0]
    for case_id in d1_dec[cid_col].dropna().astype(str).tolist():
        case_id = case_id.strip()
        if not case_id:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id not in gt.index:
            continue

        # --- D1 loop (aggregate)
        d1_loop = loaded.doc_sheets["D1_Outpatient_Loop"]
        r = _get_row_by_case_id(d1_loop, case_id)
        loop_status = "" if r is None else str(r.get(d1_loop.columns[1], "")).strip()
        if r is not None and (not loop_status.startswith("未经过")):
            req_patterns = [
                "第{r}轮_医生_原始JSON_诊断前所需检查（优先）",
                "第{r}轮_医生_原始JSON_诊断前所需检查(优先)",
                "第{r}轮_医生_原始JSON_诊断前所需检查",
                "第{r}轮_医生_原始JSON_建议检查项目",
                "第{r}轮_医生_原始JSON_需要补充门诊检查",
                "第{r}轮_医生_原始JSON_需要补充检查",
            ]
            output_parts: list[str] = []
            rationale_parts: list[str] = []
            for i in range(1, 5):
                items: list[str] = []
                for pat in req_patterns:
                    col = pat.format(r=i)
                    if col in d1_loop.columns and not is_empty(r.get(col)):
                        items.extend(parse_check_list_cell(r.get(col)))
                if items:
                    output_parts.append(f"Round{i} 请求检查: {'；'.join(items)}")
                reason_col = f"第{i}轮_医生_原始JSON_理由"
                if reason_col in d1_loop.columns and not is_empty(r.get(reason_col)):
                    rationale_parts.append(f"Round{i} 理由: {str(r.get(reason_col)).strip()}")
            emit(case_id, "D1_Outpatient_Loop", "\n".join(output_parts), "\n".join(rationale_parts))

        # --- D1 decision (skip anomalies)
        if case_id not in anomalies:
            r = _get_row_by_case_id(d1_dec, case_id)
            if r is not None:
                status = str(r.get(d1_dec.columns[1], "")).strip()
                if not status.startswith("未经过"):
                    output_parts: list[str] = []
                    diag_text = _fmt_list(r.get("医生决策_原始JSON_初步诊断列表"), parse_list_cell)
                    check_text = _fmt_list(r.get("医生决策_原始JSON_建议检查项目"), parse_check_list_cell)
                    _append_if(output_parts, "初步诊断", diag_text)
                    _append_if(output_parts, "建议检查", check_text)
                    parts: list[str] = []
                    for col in ["医生决策_原始JSON_初步诊断思维", "医生决策_原始JSON_建议检查思维"]:
                        if col in d1_dec.columns and not is_empty(r.get(col)):
                            parts.append(f"{col}: {str(r.get(col)).strip()}")
                    emit(case_id, "D1_Outpatient_Decision", "\n".join(output_parts), "\n".join(parts))

        # --- D2 loop (aggregate)
        d2_loop = loaded.doc_sheets["D2_Admission_Loop"]
        r = _get_row_by_case_id(d2_loop, case_id)
        loop_status = "" if r is None else str(r.get(d2_loop.columns[1], "")).strip()
        if r is not None and (not loop_status.startswith("未经过")):
            req_patterns = [
                "第{r}轮_医生_原始JSON_需要补充检查（优先）",
                "第{r}轮_医生_原始JSON_需要补充检查",
                "第{r}轮_医生_原始JSON_建议检查项目",
                "第{r}轮_医生_原始JSON_诊断前所需检查",
                "第{r}轮_医生_原始JSON_需要补充门诊检查",
            ]
            output_parts: list[str] = []
            rationale_parts: list[str] = []
            # include D1 suggested checks as prior context
            d1_row = _get_row_by_case_id(d1_dec, case_id)
            if d1_row is not None and "医生决策_原始JSON_建议检查项目" in d1_dec.columns:
                d1_checks = _fmt_list(d1_row.get("医生决策_原始JSON_建议检查项目"), parse_check_list_cell)
                _append_if(output_parts, "D1建议检查", d1_checks)
            for i in range(1, 5):
                items: list[str] = []
                for pat in req_patterns:
                    col = pat.format(r=i)
                    if col in d2_loop.columns and not is_empty(r.get(col)):
                        items.extend(parse_check_list_cell(r.get(col)))
                if items:
                    output_parts.append(f"Round{i} 请求检查: {'；'.join(items)}")
                reason_col = f"第{i}轮_医生_原始JSON_理由"
                if reason_col in d2_loop.columns and not is_empty(r.get(reason_col)):
                    rationale_parts.append(f"Round{i} 理由: {str(r.get(reason_col)).strip()}")
            emit(case_id, "D2_Admission_Loop", "\n".join(output_parts), "\n".join(rationale_parts))

        # --- D2 decision
        d2_dec = loaded.doc_sheets["D2_Admission_Decision"]
        r = _get_row_by_case_id(d2_dec, case_id)
        if r is not None:
            status = str(r.get(d2_dec.columns[1], "")).strip()
            if not status.startswith("未经过"):
                output_parts: list[str] = []
                diag_text = _fmt_list(r.get("医生决策_原始JSON_修正诊断"), parse_list_cell)
                plan_text = ""
                if "医生决策_原始JSON_初步治疗方案" in d2_dec.columns:
                    plan_text = _fmt_list(r.get("医生决策_原始JSON_初步治疗方案"), parse_list_cell)
                if not plan_text and "医生决策_原始JSON_治疗方案" in d2_dec.columns:
                    plan_text = _fmt_list(r.get("医生决策_原始JSON_治疗方案"), parse_list_cell)
                _append_if(output_parts, "修正诊断", diag_text)
                _append_if(output_parts, "初步治疗方案", plan_text)
                parts: list[str] = []
                for col in ["医生决策_原始JSON_修正诊断思维", "医生决策_原始JSON_治疗方案思维"]:
                    if col in d2_dec.columns and not is_empty(r.get(col)):
                        parts.append(f"{col}: {str(r.get(col)).strip()}")
                emit(case_id, "D2_Admission_Decision", "\n".join(output_parts), "\n".join(parts))

        # --- D3 decision
        d3 = loaded.doc_sheets["D3_Surgery_Decision"]
        r = _get_row_by_case_id(d3, case_id)
        if r is not None:
            status = str(r.get(d3.columns[1], "")).strip()
            if not status.startswith("未经过"):
                output_parts: list[str] = []
                diag_text = _fmt_list(r.get("医生_原始JSON_最终诊断_诊断名称"), parse_list_cell)
                plan_text = _fmt_list(r.get("医生_原始JSON_术后治疗方案_方案详情"), parse_list_cell)
                _append_if(output_parts, "最终诊断", diag_text)
                _append_if(output_parts, "术后治疗方案", plan_text)
                parts: list[str] = []
                for col in ["医生_原始JSON_最终诊断_诊断思维", "医生_原始JSON_术后治疗方案_方案思维"]:
                    if col in d3.columns and not is_empty(r.get(col)):
                        parts.append(f"{col}: {str(r.get(col)).strip()}")
                emit(case_id, "D3_Surgery_Decision", "\n".join(output_parts), "\n".join(parts))

        # --- D4 plan
        d4 = loaded.doc_sheets["D4_Rehab_Plan"]
        r = _get_row_by_case_id(d4, case_id)
        if r is not None:
            status = str(r.get(d4.columns[1], "")).strip()
            if not status.startswith("未经过"):
                output_parts: list[str] = []
                rehab_text = _fmt_list(r.get("医生_原始JSON_出院康复计划_方案详情"), parse_list_cell)
                follow_text = _fmt_list(r.get("医生_原始JSON_长期随访计划_方案详情"), parse_list_cell)
                _append_if(output_parts, "出院康复计划", rehab_text)
                _append_if(output_parts, "长期随访计划", follow_text)
                parts: list[str] = []
                for col in ["医生_原始JSON_出院康复计划_康复思维", "医生_原始JSON_长期随访计划_随访思维"]:
                    if col in d4.columns and not is_empty(r.get(col)):
                        parts.append(f"{col}: {str(r.get(col)).strip()}")
                for col in ["医生_原始JSON_出院康复计划_制定依据"]:
                    if col in d4.columns and not is_empty(r.get(col)):
                        parts.append(f"{col}: {str(r.get(col)).strip()}")
                emit(case_id, "D4_Rehab_Plan", "\n".join(output_parts), "\n".join(parts))

    return tasks


def generate_fact_consistency_and_missing_tasks(
    project_root: Path,
    loaded: LoadedData,
    allowed_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_fact_consistency_and_missing.md`.
    """
    prompt_rel = "prompts/llm_fact_consistency_and_missing.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt.copy()
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.set_index(gt["CaseID"].astype(str), drop=False)

    tasks: list[dict[str, Any]] = []

    def emit(case_id: str, stage: str, ai_summary_or_review: str) -> None:
        if not ai_summary_or_review.strip():
            return
        gt_row = gt.loc[case_id] if case_id in gt.index else None
        gt_facts_core = _build_gt_context_for_stage(gt_row, stage) if gt_row is not None else ""
        gt_facts_reference = _build_gt_reference_for_stage(gt_row, stage) if gt_row is not None else ""
        gt_facts = gt_facts_core
        if gt_facts_reference.strip():
            gt_facts = f"{gt_facts_core}\n\n[REFERENCE_FACTS]\n{gt_facts_reference}".strip()
        variables = {
            "case_id": case_id,
            "stage": stage,
            "gt_facts_core": gt_facts_core,
            "gt_facts_reference": gt_facts_reference,
            "gt_facts": gt_facts,
            "ai_summary_or_review": ai_summary_or_review,
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.fact_consistency_and_missing",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|{stage}|fact_consistency",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": stage,
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    d1_dec = loaded.doc_sheets["D1_Outpatient_Decision"]
    for case_id in d1_dec[d1_dec.columns[0]].dropna().astype(str).tolist():
        case_id = case_id.strip()
        if not case_id:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id not in gt.index:
            continue

        # D1 decision: 门诊信息汇总
        r = _get_row_by_case_id(d1_dec, case_id)
        if r is not None:
            status = str(r.get(d1_dec.columns[1], "")).strip()
            if not status.startswith("未经过"):
                col = "医生决策_原始JSON_门诊信息汇总"
                if col in d1_dec.columns and not is_empty(r.get(col)):
                    emit(case_id, "D1", str(r.get(col)).strip())

        # D2 decision: 诊疗经过回顾
        d2 = loaded.doc_sheets["D2_Admission_Decision"]
        r = _get_row_by_case_id(d2, case_id)
        if r is not None:
            status = str(r.get(d2.columns[1], "")).strip()
            if not status.startswith("未经过"):
                col = "医生决策_原始JSON_诊疗经过回顾"
                if col in d2.columns and not is_empty(r.get(col)):
                    emit(case_id, "D2", str(r.get(col)).strip())

        # D3 decision: 术后信息汇总 + 诊疗经过回顾
        d3 = loaded.doc_sheets["D3_Surgery_Decision"]
        r = _get_row_by_case_id(d3, case_id)
        if r is not None:
            status = str(r.get(d3.columns[1], "")).strip()
            if not status.startswith("未经过"):
                parts: list[str] = []
                for col in ["医生_原始JSON_术后信息汇总", "医生_原始JSON_诊疗经过回顾"]:
                    if col in d3.columns and not is_empty(r.get(col)):
                        parts.append(f"{col}: {str(r.get(col)).strip()}")
                emit(case_id, "D3", "\n".join(parts))

        # D4 plan: 康复阶段信息汇总 + 诊疗经过回顾
        d4 = loaded.doc_sheets["D4_Rehab_Plan"]
        r = _get_row_by_case_id(d4, case_id)
        if r is not None:
            status = str(r.get(d4.columns[1], "")).strip()
            if not status.startswith("未经过"):
                parts: list[str] = []
                for col in ["医生_原始JSON_康复阶段信息汇总", "医生_原始JSON_诊疗经过回顾"]:
                    if col in d4.columns and not is_empty(r.get(col)):
                        parts.append(f"{col}: {str(r.get(col)).strip()}")
                emit(case_id, "D4", "\n".join(parts))

    return tasks


def generate_plan_quality_tasks(
    project_root: Path,
    loaded: LoadedData,
    allowed_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_plan_quality.md`.

    - D2_Admission_Decision: compare AI 初步治疗方案 vs GT_Surgery_Plan
    - D3_Surgery_Decision: compare AI 术后治疗方案 vs GT_PostOp_Plan
    """
    prompt_rel = "prompts/llm_plan_quality.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt.copy()
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.set_index(gt["CaseID"].astype(str), drop=False)

    tasks: list[dict[str, Any]] = []

    def emit(case_id: str, stage: str, gt_plan_text: str, ai_plan_text: str, ai_plan_rationale: str) -> None:
        if not ai_plan_text.strip():
            return
        gt_row = gt.loc[case_id] if case_id in gt.index else None
        gt_facts = _build_gt_facts_text(gt_row) if gt_row is not None else ""
        context_facts = _build_gt_context_for_stage(gt_row, stage) if gt_row is not None else ""
        variables = {
            "case_id": case_id,
            "stage": stage,
            "gt_facts": gt_facts,
            "context_facts": context_facts,
            "gt_plan_text": gt_plan_text,
            "ai_plan_text": ai_plan_text,
            "ai_plan_rationale": ai_plan_rationale,
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.plan_quality",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|{stage}|plan_quality",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": stage,
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    d1_dec = loaded.doc_sheets["D1_Outpatient_Decision"]
    for case_id in d1_dec[d1_dec.columns[0]].dropna().astype(str).tolist():
        case_id = case_id.strip()
        if not case_id:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id not in gt.index:
            continue
        gt_row = gt.loc[case_id]

        # D2 plan
        d2 = loaded.doc_sheets["D2_Admission_Decision"]
        r = _get_row_by_case_id(d2, case_id)
        if r is not None:
            status = str(r.get(d2.columns[1], "")).strip()
            if not status.startswith("未经过"):
                gt_plan = "" if is_empty(gt_row.get("GT_Surgery_Plan")) else str(gt_row.get("GT_Surgery_Plan")).strip()
                ai_plan = "" if is_empty(r.get("医生决策_原始JSON_初步治疗方案")) else str(r.get("医生决策_原始JSON_初步治疗方案")).strip()
                ai_rat = "" if is_empty(r.get("医生决策_原始JSON_治疗方案思维")) else str(r.get("医生决策_原始JSON_治疗方案思维")).strip()
                emit(case_id, "D2_Admission_Decision", gt_plan, ai_plan, ai_rat)

        # D3 post-op plan
        d3 = loaded.doc_sheets["D3_Surgery_Decision"]
        r = _get_row_by_case_id(d3, case_id)
        if r is not None:
            status = str(r.get(d3.columns[1], "")).strip()
            if not status.startswith("未经过"):
                gt_plan = "" if is_empty(gt_row.get("GT_PostOp_Plan")) else str(gt_row.get("GT_PostOp_Plan")).strip()
                ai_plan = "" if is_empty(r.get("医生_原始JSON_术后治疗方案_方案详情")) else str(r.get("医生_原始JSON_术后治疗方案_方案详情")).strip()
                ai_rat = "" if is_empty(r.get("医生_原始JSON_术后治疗方案_方案思维")) else str(r.get("医生_原始JSON_术后治疗方案_方案思维")).strip()
                emit(case_id, "D3_Surgery_Decision", gt_plan, ai_plan, ai_rat)

    return tasks


def generate_memory_retention_tasks(
    project_root: Path,
    loaded: LoadedData,
    allowed_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_memory_retention.md`.

    Stages:
    - D2_Admission_Decision
    - D3_Surgery_Decision
    - D4_Rehab_Plan
    """
    prompt_rel = "prompts/llm_memory_retention.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt.copy()
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.set_index(gt["CaseID"].astype(str), drop=False)

    anomalies = detect_d1_decision_anomaly(
        loaded.doc_sheets["D1_Outpatient_Decision"],
        loaded.doc_sheets.get("D2_Admission_Decision"),
    )

    tasks: list[dict[str, Any]] = []

    def _collect_text(df: pd.DataFrame, case_id: str, cols: list[str]) -> tuple[str, str]:
        r = _get_row_by_case_id(df, case_id)
        if r is None:
            return "", ""
        status = str(r.get(df.columns[1], "")).strip()
        if status.startswith("未经过"):
            return "", status
        parts: list[str] = []
        for c in cols:
            if c in df.columns and not is_empty(r.get(c)):
                parts.append(f"{c}: {str(r.get(c)).strip()}")
        return "\n".join(parts), status

    def _join_prior(parts: list[tuple[str, str]]) -> str:
        out: list[str] = []
        for label, text in parts:
            if text:
                out.append(f"{label}: {text}")
        return "\n\n".join(out)

    def emit(case_id: str, stage: str, prior_summary: str, current_review: str) -> None:
        if not prior_summary.strip() or not current_review.strip():
            return
        gt_row = gt.loc[case_id] if case_id in gt.index else None
        gt_facts = _build_gt_context_for_stage(gt_row, stage) if gt_row is not None else ""
        variables = {
            "case_id": case_id,
            "stage": stage,
            "prior_stage_summary": prior_summary,
            "current_stage_review": current_review,
            "gt_facts": gt_facts,
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.memory_retention",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|{stage}|memory_retention",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": stage,
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    d1_dec = loaded.doc_sheets["D1_Outpatient_Decision"]
    d2_dec = loaded.doc_sheets["D2_Admission_Decision"]
    d3_dec = loaded.doc_sheets["D3_Surgery_Decision"]
    d4_dec = loaded.doc_sheets["D4_Rehab_Plan"]

    for case_id in d1_dec[d1_dec.columns[0]].dropna().astype(str).tolist():
        case_id = case_id.strip()
        if not case_id:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id not in gt.index:
            continue
        if case_id in anomalies:
            continue

        d1_summary, _ = _collect_text(d1_dec, case_id, ["医生决策_原始JSON_门诊信息汇总"])
        d2_summary, _ = _collect_text(d2_dec, case_id, ["医生决策_原始JSON_诊疗经过回顾"])
        d3_summary, _ = _collect_text(d3_dec, case_id, ["医生_原始JSON_术后信息汇总"])

        # D2 current review/thoughts
        d2_review, _ = _collect_text(
            d2_dec,
            case_id,
            ["医生决策_原始JSON_诊疗经过回顾", "医生决策_原始JSON_修正诊断思维", "医生决策_原始JSON_治疗方案思维"],
        )
        prior_d2 = _join_prior([("D1门诊信息汇总", d1_summary)])
        if d2_review.strip():
            emit(case_id, "D2_Admission_Decision", prior_d2, d2_review)

        # D3 current review/thoughts
        d3_review, _ = _collect_text(
            d3_dec,
            case_id,
            ["医生_原始JSON_诊疗经过回顾", "医生_原始JSON_最终诊断_诊断思维", "医生_原始JSON_术后治疗方案_方案思维"],
        )
        prior_d3 = _join_prior([("D1门诊信息汇总", d1_summary), ("D2诊疗回顾", d2_summary)])
        if d3_review.strip():
            emit(case_id, "D3_Surgery_Decision", prior_d3, d3_review)

        # D4 current review/thoughts
        d4_review, _ = _collect_text(
            d4_dec,
            case_id,
            ["医生_原始JSON_诊疗经过回顾", "医生_原始JSON_出院康复计划_康复思维", "医生_原始JSON_长期随访计划_随访思维"],
        )
        prior_d4 = _join_prior([("D1门诊信息汇总", d1_summary), ("D2诊疗回顾", d2_summary), ("D3术后信息汇总", d3_summary)])
        if d4_review.strip():
            emit(case_id, "D4_Rehab_Plan", prior_d4, d4_review)

    return tasks


def generate_cross_stage_consistency_tasks(
    project_root: Path,
    loaded: LoadedData,
    allowed_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_cross_stage_consistency.md`.

    Cross-stage (D1-D4 decision) consistency for each case.
    """
    prompt_rel = "prompts/llm_cross_stage_consistency.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt.copy()
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.set_index(gt["CaseID"].astype(str), drop=False)

    anomalies = detect_d1_decision_anomaly(
        loaded.doc_sheets["D1_Outpatient_Decision"],
        loaded.doc_sheets.get("D2_Admission_Decision"),
    )

    tasks: list[dict[str, Any]] = []

    def _collect_text(df: pd.DataFrame, case_id: str, cols: list[str]) -> tuple[str, str]:
        r = _get_row_by_case_id(df, case_id)
        if r is None:
            return "", ""
        status = str(r.get(df.columns[1], "")).strip()
        if status.startswith("未经过"):
            return "", status
        parts: list[str] = []
        for c in cols:
            if c in df.columns and not is_empty(r.get(c)):
                parts.append(f"{c}: {str(r.get(c)).strip()}")
        return "\n".join(parts), status

    def _stage_block(label: str, text: str, status: str) -> str:
        if text:
            return f"{label}:\n{text}"
        if status.startswith("未经过"):
            return f"{label}: 未经过"
        return ""

    d1_dec = loaded.doc_sheets["D1_Outpatient_Decision"]
    d2_dec = loaded.doc_sheets["D2_Admission_Decision"]
    d3_dec = loaded.doc_sheets["D3_Surgery_Decision"]
    d4_dec = loaded.doc_sheets["D4_Rehab_Plan"]

    for case_id in d1_dec[d1_dec.columns[0]].dropna().astype(str).tolist():
        case_id = case_id.strip()
        if not case_id:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id not in gt.index:
            continue
        if case_id in anomalies:
            continue

        d1_text, d1_status = _collect_text(d1_dec, case_id, ["医生决策_原始JSON_门诊信息汇总"])
        d2_text, d2_status = _collect_text(d2_dec, case_id, ["医生决策_原始JSON_诊疗经过回顾"])
        d3_text, d3_status = _collect_text(
            d3_dec, case_id, ["医生_原始JSON_术后信息汇总", "医生_原始JSON_诊疗经过回顾"]
        )
        d4_text, d4_status = _collect_text(
            d4_dec, case_id, ["医生_原始JSON_康复阶段信息汇总", "医生_原始JSON_诊疗经过回顾"]
        )

        content_count = sum(1 for v in [d1_text, d2_text, d3_text, d4_text] if v.strip())
        if content_count < 2:
            continue

        blocks = [
            _stage_block("D1", d1_text, d1_status),
            _stage_block("D2", d2_text, d2_status),
            _stage_block("D3", d3_text, d3_status),
            _stage_block("D4", d4_text, d4_status),
        ]
        multi_stage_summaries = "\n\n".join([b for b in blocks if b.strip()])

        gt_row = gt.loc[case_id] if case_id in gt.index else None
        gt_facts = _build_gt_context_for_stage(gt_row, "D4") if gt_row is not None else ""
        variables = {
            "case_id": case_id,
            "stage": "D1-D4",
            "multi_stage_summaries": multi_stage_summaries,
            "gt_facts": gt_facts,
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.cross_stage_consistency",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|D1-D4|cross_stage_consistency",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": "D1-D4",
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    return tasks


def generate_rehab_followup_quality_tasks(
    project_root: Path,
    loaded: LoadedData,
    allowed_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_rehab_followup_quality.md` (D4 only).
    """
    prompt_rel = "prompts/llm_rehab_followup_quality.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt.copy()
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.set_index(gt["CaseID"].astype(str), drop=False)

    tasks: list[dict[str, Any]] = []

    d4 = loaded.doc_sheets["D4_Rehab_Plan"]
    for case_id in d4[d4.columns[0]].dropna().astype(str).tolist():
        case_id = case_id.strip()
        if not case_id:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id not in gt.index:
            continue

        r = _get_row_by_case_id(d4, case_id)
        if r is None:
            continue
        status = str(r.get(d4.columns[1], "")).strip()
        if status.startswith("未经过"):
            continue

        ai_rehab_plan = "" if is_empty(r.get("医生_原始JSON_出院康复计划_方案详情")) else str(r.get("医生_原始JSON_出院康复计划_方案详情")).strip()
        ai_followup_plan = "" if is_empty(r.get("医生_原始JSON_长期随访计划_方案详情")) else str(r.get("医生_原始JSON_长期随访计划_方案详情")).strip()
        if not ai_rehab_plan and not ai_followup_plan:
            continue

        rehab_rationale_parts: list[str] = []
        for col in ["医生_原始JSON_出院康复计划_康复思维", "医生_原始JSON_出院康复计划_制定依据"]:
            if col in d4.columns and not is_empty(r.get(col)):
                rehab_rationale_parts.append(f"{col}: {str(r.get(col)).strip()}")
        ai_rehab_rationale = "\n".join(rehab_rationale_parts)

        followup_rationale_parts: list[str] = []
        for col in ["医生_原始JSON_长期随访计划_随访思维"]:
            if col in d4.columns and not is_empty(r.get(col)):
                followup_rationale_parts.append(f"{col}: {str(r.get(col)).strip()}")
        ai_followup_rationale = "\n".join(followup_rationale_parts)

        gt_row = gt.loc[case_id]
        gt_facts = _build_gt_facts_text(gt_row)
        context_facts = _build_gt_context_for_stage(gt_row, "D4_Rehab_Plan")
        gt_rehab_plan = "" if is_empty(gt_row.get("GT_Rehab_Plan")) else str(gt_row.get("GT_Rehab_Plan")).strip()
        gt_followup_plan = "" if is_empty(gt_row.get("GT_Followup_Plan")) else str(gt_row.get("GT_Followup_Plan")).strip()

        variables = {
            "case_id": case_id,
            "stage": "D4_Rehab_Plan",
            "context_facts": context_facts,
            "gt_facts": gt_facts,
            "gt_rehab_plan": gt_rehab_plan,
            "gt_followup_plan": gt_followup_plan,
            "ai_rehab_plan": ai_rehab_plan,
            "ai_rehab_rationale": ai_rehab_rationale,
            "ai_followup_plan": ai_followup_plan,
            "ai_followup_rationale": ai_followup_rationale,
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.rehab_followup_quality",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|D4_Rehab_Plan|rehab_followup_quality",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": "D4_Rehab_Plan",
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    return tasks


def generate_diagnosis_quality_tasks(
    project_root: Path,
    loaded: LoadedData,
    allowed_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_diagnosis_quality.md`.

    Stages:
    - D1_Outpatient_Decision: 初步诊断质量
    - D2_Admission_Decision: 修正诊断质量
    - D3_Surgery_Decision: 最终诊断质量
    """
    prompt_rel = "prompts/llm_diagnosis_quality.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt.copy()
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.set_index(gt["CaseID"].astype(str), drop=False)

    tasks: list[dict[str, Any]] = []

    def emit(
        case_id: str,
        stage: str,
        gt_diag_text: str,
        ai_diag_text: str,
        ai_diag_rationale: str,
        strictness: dict[str, Any],
    ) -> None:
        if not gt_diag_text.strip() or not ai_diag_text.strip():
            return
        gt_row = gt.loc[case_id] if case_id in gt.index else None
        gt_facts = _build_gt_facts_text(gt_row) if gt_row is not None else ""
        context_facts = _build_gt_context_for_stage(gt_row, stage) if gt_row is not None else ""
        variables = {
            "case_id": case_id,
            "stage": stage,
            "gt_diagnosis_text": gt_diag_text,
            "ai_diagnosis_text": ai_diag_text,
            "ai_diagnosis_rationale": ai_diag_rationale,
            "context_facts": context_facts,
            "strictness": json.dumps(strictness, ensure_ascii=False),
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.diagnosis_quality",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|{stage}|dx_quality",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": stage,
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    # D1 preliminary diagnosis quality
    d1_dec = loaded.doc_sheets["D1_Outpatient_Decision"]
    anomalies = detect_d1_decision_anomaly(d1_dec, loaded.doc_sheets.get("D2_Admission_Decision"))
    for case_id in d1_dec[d1_dec.columns[0]].dropna().astype(str).tolist():
        case_id = case_id.strip()
        if not case_id or case_id in anomalies:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id not in gt.index:
            continue
        gt_text_raw = gt.loc[case_id].get("GT_Admission_Diagnosis")
        gt_text = "" if is_empty(gt_text_raw) else str(gt_text_raw).strip()
        if loaded.fileset.center == "武汉" and gt_text:
            parsed = parse_wuhan_dx(gt_text)
            if parsed.primary:
                gt_text = "\n".join(parsed.primary)
        r = _get_row_by_case_id(d1_dec, case_id)
        if r is None:
            continue
        ai_raw = r.get("医生决策_原始JSON_初步诊断列表")
        ai_list = parse_list_cell(ai_raw)
        ai_text = "\n".join(ai_list) if ai_list else ("" if is_empty(ai_raw) else str(ai_raw))
        ai_rat = "" if is_empty(r.get("医生决策_原始JSON_初步诊断思维")) else str(r.get("医生决策_原始JSON_初步诊断思维")).strip()
        emit(case_id, "D1_Outpatient_Decision", gt_text, ai_text, ai_rat, {"require_staging": False})

    # D2 revised diagnosis quality
    d2 = loaded.doc_sheets["D2_Admission_Decision"]
    for case_id in d2[d2.columns[0]].dropna().astype(str).tolist():
        case_id = case_id.strip()
        if not case_id:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id not in gt.index:
            continue
        r = _get_row_by_case_id(d2, case_id)
        if r is None:
            continue
        status = str(r.get(d2.columns[1], "")).strip()
        if status.startswith("未经过"):
            continue
        gt_text_raw = gt.loc[case_id].get("GT_Revised_Diagnosis")
        gt_text = "" if is_empty(gt_text_raw) else str(gt_text_raw).strip()
        ai_raw = r.get("医生决策_原始JSON_修正诊断")
        ai_text = "" if is_empty(ai_raw) else str(ai_raw).strip()
        ai_rat = "" if is_empty(r.get("医生决策_原始JSON_修正诊断思维")) else str(r.get("医生决策_原始JSON_修正诊断思维")).strip()
        emit(case_id, "D2_Admission_Decision", gt_text, ai_text, ai_rat, {"require_staging": False})

    # D3 final diagnosis quality
    d3 = loaded.doc_sheets["D3_Surgery_Decision"]
    for case_id in d3[d3.columns[0]].dropna().astype(str).tolist():
        case_id = case_id.strip()
        if not case_id:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id not in gt.index:
            continue
        r = _get_row_by_case_id(d3, case_id)
        if r is None:
            continue
        status = str(r.get(d3.columns[1], "")).strip()
        if status.startswith("未经过"):
            continue
        gt_text_raw = gt.loc[case_id].get("GT_Final_Diagnosis")
        gt_text = "" if is_empty(gt_text_raw) else str(gt_text_raw).strip()
        ai_raw = r.get("医生_原始JSON_最终诊断_诊断名称")
        ai_text = "" if is_empty(ai_raw) else str(ai_raw).strip()
        ai_rat = "" if is_empty(r.get("医生_原始JSON_最终诊断_诊断思维")) else str(r.get("医生_原始JSON_最终诊断_诊断思维")).strip()
        emit(case_id, "D3_Surgery_Decision", gt_text, ai_text, ai_rat, {"require_staging": True})

    return tasks


def generate_final_diagnosis_proximity_tasks(
    project_root: Path,
    loaded: LoadedData,
    allowed_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_final_diagnosis_proximity.md`.

    Stages:
    - D1_Outpatient_Decision: 初步诊断列表相对最终诊断的接近度
    - D2_Admission_Decision: 修正诊断相对最终诊断的接近度

    D3 is intentionally excluded here because we directly reuse the
    existing Gate3 final-diagnosis judge score as the D3 proximity proxy.
    """
    prompt_rel = "prompts/llm_final_diagnosis_proximity.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt.copy()
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.set_index(gt["CaseID"].astype(str), drop=False)

    def _build_context(gt_row: pd.Series, stage: str) -> str:
        parts: list[str] = []
        base = _build_gt_facts_text(gt_row)
        if base.strip():
            parts.append(base.strip())
        extra_cols: list[str]
        stage_key = str(stage).strip().upper()
        if stage_key.startswith("D1"):
            extra_cols = ["GT_Outpatient_Checks"]
        else:
            extra_cols = ["GT_Outpatient_Checks", "GT_Admission_Checks"]
        for col in extra_cols:
            if col not in gt_row.index:
                continue
            v = gt_row.get(col)
            if is_empty(v):
                continue
            parts.append(f"{col}: {str(v).strip()}")
        return "\n\n".join(parts)

    tasks: list[dict[str, Any]] = []

    d1_dec = loaded.doc_sheets["D1_Outpatient_Decision"]
    anomalies = detect_d1_decision_anomaly(
        loaded.doc_sheets["D1_Outpatient_Decision"],
        loaded.doc_sheets.get("D2_Admission_Decision"),
    )
    for case_id in d1_dec[d1_dec.columns[0]].dropna().astype(str).tolist():
        case_id = case_id.strip()
        if not case_id or case_id in anomalies:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id not in gt.index:
            continue
        r = _get_row_by_case_id(d1_dec, case_id)
        if r is None:
            continue
        status = str(r.get(d1_dec.columns[1], "")).strip()
        if status.startswith("未经过"):
            continue
        gt_row = gt.loc[case_id]
        gt_final = "" if is_empty(gt_row.get("GT_Final_Diagnosis")) else str(gt_row.get("GT_Final_Diagnosis")).strip()
        if not gt_final:
            continue
        ai_raw = r.get("医生决策_原始JSON_初步诊断列表")
        ai_list = parse_list_cell(ai_raw)
        ai_diag = "\n".join(ai_list) if ai_list else ("" if is_empty(ai_raw) else str(ai_raw).strip())
        if not ai_diag:
            continue
        ai_rationale = (
            "" if is_empty(r.get("医生决策_原始JSON_初步诊断思维")) else str(r.get("医生决策_原始JSON_初步诊断思维")).strip()
        )
        variables = {
            "case_id": case_id,
            "stage": "D1_Outpatient_Decision",
            "stage_label": "D1初步诊断",
            "gt_final_diagnosis": gt_final,
            "ai_stage_diagnosis": ai_diag,
            "ai_stage_diagnosis_rationale": ai_rationale,
            "context_facts": _build_context(gt_row, "D1_Outpatient_Decision"),
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.final_diagnosis_proximity",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|D1_Outpatient_Decision|final_dx_proximity",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": "D1_Outpatient_Decision",
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    d2_dec = loaded.doc_sheets["D2_Admission_Decision"]
    for case_id in d2_dec[d2_dec.columns[0]].dropna().astype(str).tolist():
        case_id = case_id.strip()
        if not case_id:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id not in gt.index:
            continue
        r = _get_row_by_case_id(d2_dec, case_id)
        if r is None:
            continue
        status = str(r.get(d2_dec.columns[1], "")).strip()
        if status.startswith("未经过"):
            continue
        gt_row = gt.loc[case_id]
        gt_final = "" if is_empty(gt_row.get("GT_Final_Diagnosis")) else str(gt_row.get("GT_Final_Diagnosis")).strip()
        if not gt_final:
            continue
        ai_raw = r.get("医生决策_原始JSON_修正诊断")
        ai_list = parse_list_cell(ai_raw)
        ai_diag = "\n".join(ai_list) if ai_list else ("" if is_empty(ai_raw) else str(ai_raw).strip())
        if not ai_diag:
            continue
        ai_rationale = (
            "" if is_empty(r.get("医生决策_原始JSON_修正诊断思维")) else str(r.get("医生决策_原始JSON_修正诊断思维")).strip()
        )
        variables = {
            "case_id": case_id,
            "stage": "D2_Admission_Decision",
            "stage_label": "D2修正诊断",
            "gt_final_diagnosis": gt_final,
            "ai_stage_diagnosis": ai_diag,
            "ai_stage_diagnosis_rationale": ai_rationale,
            "context_facts": _build_context(gt_row, "D2_Admission_Decision"),
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.final_diagnosis_proximity",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|D2_Admission_Decision|final_dx_proximity",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": "D2_Admission_Decision",
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    return tasks


def generate_gate1_dx_rescore_tasks(
    project_root: Path,
    loaded: LoadedData,
    allowed_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_gate1_dx_rescore.md`.

    Stage:
    - D1_Outpatient_Decision (Gate1 初步诊断重评分)
    """
    prompt_rel = "prompts/llm_gate1_dx_rescore.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt.copy()
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.set_index(gt["CaseID"].astype(str), drop=False)

    d1_dec = loaded.doc_sheets["D1_Outpatient_Decision"]
    anomalies = detect_d1_decision_anomaly(
        loaded.doc_sheets["D1_Outpatient_Decision"],
        loaded.doc_sheets.get("D2_Admission_Decision"),
    )

    def _fmt_list(val: Any) -> str:
        items = parse_list_cell(val)
        if items:
            return "；".join(items)
        if is_empty(val):
            return ""
        return str(val).strip()

    def _build_context_facts(gt_row: pd.Series) -> str:
        cols = [
            "BasicInfo",
            "ChiefComplaint",
            "PresentIllness",
            "PhysicalExam",
            "PastHistory",
            "FamilyHistory",
            "MenstrualHistory",
            "GT_Outpatient_Checks",
        ]
        parts: list[str] = []
        for c in cols:
            if c not in gt_row.index:
                continue
            v = gt_row.get(c)
            if is_empty(v):
                continue
            parts.append(f"{c}: {str(v).strip()}")
        return "\n".join(parts)

    tasks: list[dict[str, Any]] = []
    for _, row in d1_dec.iterrows():
        case_id = str(row.get(d1_dec.columns[0], "")).strip()
        if not case_id:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id in anomalies:
            continue

        status = str(row.get(d1_dec.columns[1], "")).strip()
        if status.startswith("未经过"):
            continue

        ai_diag = _fmt_list(row.get("医生决策_原始JSON_初步诊断列表"))
        if not ai_diag:
            continue

        ai_rationale = str(row.get("医生决策_原始JSON_初步诊断思维") or "").strip()

        gt_row = gt.loc[case_id] if case_id in gt.index else None
        if gt_row is None:
            continue
        gt_diag = str(gt_row.get("GT_Admission_Diagnosis") or "").strip()
        if not gt_diag:
            continue
        parsed_gt = parse_wuhan_dx(gt_diag)
        gt_primary = "；".join(parsed_gt.primary) if parsed_gt.primary else ""
        gt_diff = "；".join(parsed_gt.differential) if parsed_gt.differential else ""

        context_facts = _build_context_facts(gt_row)

        variables = {
            "case_id": case_id,
            "stage": "D1_Outpatient_Decision",
            "gt_admission_diagnosis": gt_diag,
            "gt_primary_diagnosis": gt_primary,
            "gt_differential_diagnoses": gt_diff,
            "ai_preliminary_diagnosis": ai_diag,
            "ai_diagnosis_rationale": ai_rationale,
            "context_facts": context_facts,
            "judge_reason": "",
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.gate1_dx_rescore",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|D1_Outpatient_Decision|gate1_dx_rescore",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": "D1_Outpatient_Decision",
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    return tasks


def generate_gate2_dx_plan_rescore_tasks(
    project_root: Path,
    loaded: LoadedData,
    allowed_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_gate2_dx_plan_rescore.md`.

    Stage:
    - D2_Admission_Decision (Gate2 修正诊断/方案重评分)
    """
    prompt_rel = "prompts/llm_gate2_dx_plan_rescore.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt.copy()
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.set_index(gt["CaseID"].astype(str), drop=False)

    d2_dec = loaded.doc_sheets["D2_Admission_Decision"]
    anomalies = detect_d1_decision_anomaly(
        loaded.doc_sheets["D1_Outpatient_Decision"],
        loaded.doc_sheets.get("D2_Admission_Decision"),
    )

    def _fmt_list(val: Any) -> str:
        items = parse_list_cell(val)
        if items:
            return "；".join(items)
        if is_empty(val):
            return ""
        return str(val).strip()

    def _build_context_facts(gt_row: pd.Series) -> str:
        cols = [
            "BasicInfo",
            "ChiefComplaint",
            "PresentIllness",
            "PhysicalExam",
            "PastHistory",
            "FamilyHistory",
            "MenstrualHistory",
            "GT_Outpatient_Checks",
            "GT_Admission_Checks",
            "GT_Admission_Diagnosis",
            "GT_Final_Diagnosis",
            "GT_Patient_Wishes",
        ]
        parts: list[str] = []
        for c in cols:
            if c not in gt_row.index:
                continue
            v = gt_row.get(c)
            if is_empty(v):
                continue
            parts.append(f"{c}: {str(v).strip()}")
        return "\n".join(parts)

    tasks: list[dict[str, Any]] = []
    for _, row in d2_dec.iterrows():
        case_id = str(row.get(d2_dec.columns[0], "")).strip()
        if not case_id:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id in anomalies:
            continue

        status = str(row.get(d2_dec.columns[1], "")).strip()
        if status.startswith("未经过"):
            continue

        ai_diag = _fmt_list(row.get("医生决策_原始JSON_修正诊断"))
        ai_plan = _fmt_list(row.get("医生决策_原始JSON_初步治疗方案"))
        if not ai_plan:
            ai_plan = _fmt_list(row.get("医生决策_原始JSON_治疗方案"))

        if not ai_diag and not ai_plan:
            continue

        ai_diag_rationale = str(row.get("医生决策_原始JSON_修正诊断思维") or "").strip()
        ai_plan_rationale = str(row.get("医生决策_原始JSON_治疗方案思维") or "").strip()

        gt_row = gt.loc[case_id] if case_id in gt.index else None
        if gt_row is None:
            continue

        gt_revised = str(gt_row.get("GT_Revised_Diagnosis") or "").strip()
        gt_admission = str(gt_row.get("GT_Admission_Diagnosis") or "").strip()
        gt_final = str(gt_row.get("GT_Final_Diagnosis") or "").strip()
        if not gt_revised:
            fallback = "；".join([v for v in [gt_admission, gt_final] if v])
            gt_revised = fallback

        gt_surgery_plan = str(gt_row.get("GT_Surgery_Plan") or "").strip()
        gt_patient_wishes = str(gt_row.get("GT_Patient_Wishes") or "").strip()

        context_facts = _build_context_facts(gt_row)

        variables = {
            "case_id": case_id,
            "stage": "D2_Admission_Decision",
            "gt_revised_diagnosis": gt_revised,
            "gt_admission_diagnosis": gt_admission,
            "gt_final_diagnosis": gt_final,
            "gt_surgery_plan": gt_surgery_plan,
            "gt_patient_wishes": gt_patient_wishes,
            "ai_revised_diagnosis": ai_diag,
            "ai_treatment_plan": ai_plan,
            "ai_diagnosis_rationale": ai_diag_rationale,
            "ai_plan_rationale": ai_plan_rationale,
            "context_facts": context_facts,
            "judge_reason": "",
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.gate2_dx_plan_rescore",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|D2_Admission_Decision|gate2_dx_plan_rescore",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": "D2_Admission_Decision",
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    return tasks

def generate_diagnosis_bias_tasks(
    project_root: Path,
    loaded: LoadedData,
    allowed_case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_diagnosis_bias.md`.
    """
    prompt_rel = "prompts/llm_diagnosis_bias.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt.copy()
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.set_index(gt["CaseID"].astype(str), drop=False)

    tasks: list[dict[str, Any]] = []

    d1_dec = loaded.doc_sheets["D1_Outpatient_Decision"]
    for case_id in d1_dec[d1_dec.columns[0]].dropna().astype(str).tolist():
        case_id = case_id.strip()
        if not case_id:
            continue
        if allowed_case_ids is not None and case_id not in allowed_case_ids:
            continue
        if case_id not in gt.index:
            continue
        gt_row = gt.loc[case_id]
        gt_dx = "" if is_empty(gt_row.get("GT_Final_Diagnosis")) else str(gt_row.get("GT_Final_Diagnosis")).strip()
        if not gt_dx:
            continue

        d3 = loaded.doc_sheets["D3_Surgery_Decision"]
        r = _get_row_by_case_id(d3, case_id)
        if r is None:
            continue
        status = str(r.get(d3.columns[1], "")).strip()
        if status.startswith("未经过"):
            continue

        ai_dx = "" if is_empty(r.get("医生_原始JSON_最终诊断_诊断名称")) else str(r.get("医生_原始JSON_最终诊断_诊断名称")).strip()
        if not ai_dx:
            continue

        ctx_parts: list[str] = []
        for col in ["GT_Pathology", "GT_Surgery_Findings"]:
            if col in gt_row.index and not is_empty(gt_row.get(col)):
                ctx_parts.append(f"{col}: {str(gt_row.get(col)).strip()}")
        context_facts = "\n".join(ctx_parts)

        variables = {
            "case_id": case_id,
            "gt_final_diagnosis": gt_dx,
            "ai_final_diagnosis": ai_dx,
            "context_facts": context_facts,
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.diagnosis_bias",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|D3|diagnosis_bias",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": "D3",
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    return tasks


def generate_gate2_dx_plan_rescore_review_tasks(
    project_root: Path,
    loaded: LoadedData,
    case_ids_to_review: set[str],
) -> list[dict[str, Any]]:
    """
    Generate tasks for `prompts/llm_gate2_dx_plan_rescore_review.md`.

    Stage:
    - D2_Admission_Decision (Gate2 二审重评分)
    """
    if not case_ids_to_review:
        return []

    prompt_rel = "prompts/llm_gate2_dx_plan_rescore_review.md"
    tpl = _load_prompt_template(project_root, prompt_rel)
    prompt_sha256 = _sha256_text(tpl)

    gt = loaded.gt.copy()
    if "CaseID" not in gt.columns:
        gt = gt.rename(columns={gt.columns[0]: "CaseID"})
    gt = gt.set_index(gt["CaseID"].astype(str), drop=False)

    d2_dec = loaded.doc_sheets["D2_Admission_Decision"]
    anomalies = detect_d1_decision_anomaly(
        loaded.doc_sheets["D1_Outpatient_Decision"],
        loaded.doc_sheets.get("D2_Admission_Decision"),
    )

    def _fmt_list(val: Any) -> str:
        items = parse_list_cell(val)
        if items:
            return "；".join(items)
        if is_empty(val):
            return ""
        return str(val).strip()

    def _build_full_context(gt_row: pd.Series) -> str:
        cols = [
            "BasicInfo",
            "ChiefComplaint",
            "PresentIllness",
            "PhysicalExam",
            "PastHistory",
            "FamilyHistory",
            "MenstrualHistory",
            "GT_Outpatient_Checks",
            "GT_Admission_Checks",
            "GT_Admission_Diagnosis",
            "GT_Revised_Diagnosis",
            "GT_Surgery_Plan",
            "GT_Pathology",
            "GT_Surgery_Findings",
            "GT_Final_Diagnosis",
            "GT_Patient_Wishes",
        ]
        parts: list[str] = []
        for c in cols:
            if c not in gt_row.index:
                continue
            v = gt_row.get(c)
            if is_empty(v):
                continue
            parts.append(f"{c}: {str(v).strip()}")
        return "\n".join(parts)

    tasks: list[dict[str, Any]] = []
    for _, row in d2_dec.iterrows():
        case_id = str(row.get(d2_dec.columns[0], "")).strip()
        if not case_id or case_id not in case_ids_to_review:
            continue
        if case_id in anomalies:
            continue

        status = str(row.get(d2_dec.columns[1], "")).strip()
        if status.startswith("未经过"):
            continue

        ai_diag = _fmt_list(row.get("医生决策_原始JSON_修正诊断"))
        ai_plan = _fmt_list(row.get("医生决策_原始JSON_初步治疗方案"))
        if not ai_plan:
            ai_plan = _fmt_list(row.get("医生决策_原始JSON_治疗方案"))
        if not ai_diag and not ai_plan:
            continue

        ai_diag_rationale = str(row.get("医生决策_原始JSON_修正诊断思维") or "").strip()
        ai_plan_rationale = str(row.get("医生决策_原始JSON_治疗方案思维") or "").strip()

        gt_row = gt.loc[case_id] if case_id in gt.index else None
        if gt_row is None:
            continue

        gt_revised = str(gt_row.get("GT_Revised_Diagnosis") or "").strip()
        gt_admission = str(gt_row.get("GT_Admission_Diagnosis") or "").strip()
        gt_final = str(gt_row.get("GT_Final_Diagnosis") or "").strip()
        if not gt_revised:
            fallback = "；".join([v for v in [gt_admission, gt_final] if v])
            gt_revised = fallback

        gt_surgery_plan = str(gt_row.get("GT_Surgery_Plan") or "").strip()
        gt_patient_wishes = str(gt_row.get("GT_Patient_Wishes") or "").strip()
        full_context = _build_full_context(gt_row)

        variables = {
            "case_id": case_id,
            "stage": "D2_Admission_Decision",
            "gt_revised_diagnosis": gt_revised,
            "gt_admission_diagnosis": gt_admission,
            "gt_final_diagnosis": gt_final,
            "gt_surgery_plan": gt_surgery_plan,
            "gt_patient_wishes": gt_patient_wishes,
            "ai_revised_diagnosis": ai_diag,
            "ai_treatment_plan": ai_plan,
            "ai_diagnosis_rationale": ai_diag_rationale,
            "ai_plan_rationale": ai_plan_rationale,
            "full_context_facts": full_context,
            "prompt_sha256": prompt_sha256,
        }
        prompt = _render_template(tpl, variables)
        tasks.append(
            {
                "task": "llm.gate2_dx_plan_rescore_review",
                "task_id": f"{loaded.fileset.center}|{loaded.fileset.model}|{case_id}|D2_Admission_Decision|gate2_dx_plan_rescore_review",
                "center": loaded.fileset.center,
                "model": loaded.fileset.model,
                "case_id": case_id,
                "stage": "D2_Admission_Decision",
                "prompt_template": prompt_rel,
                "inputs": variables,
                "prompt": prompt,
            }
        )

    return tasks

def write_tasks_jsonl(path: Path, tasks: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
