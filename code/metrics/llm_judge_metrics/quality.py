from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

import pandas as pd

from .parsing import is_empty


_KNOWN_HEADER_REPLACEMENTS = {
    # Observed mojibake in some Parsed files (e.g., gemini-2.5-pro Foshan D1 loop).
    "门žen检查": "门诊检查",
    "门zhen检查": "门诊检查",
    # Mixed English/Chinese (judge loop)
    "matched_examinations": "匹配的检查项目",
    "matched_examination_content": "匹配的检查项目",
    "ai_suggested_but_not_performed": "AI建议但实际未执行的检查",
    "匹配的检查内容": "匹配的检查项目",
    "匹配的check项目": "匹配的检查项目",
    "匹配的check内容": "匹配的检查项目",
    "未匹配的check项目": "未匹配的检查项目",
    "AI建议但实际未执行的check": "AI建议但实际未执行的检查",
    # Judge text fields
    "判官_原始JSON_康复计划评估_details": "判官_原始JSON_康复计划评估_理由",
    "判官_原始JSON_随访计划评估_details": "判官_原始JSON_随访计划评估_理由",
    "判官_原始JSON_康复计划评估_markdown_reason": "判官_原始JSON_康复计划评估_理由",
    "判官_原始JSON_随访计划评估_markdown_reason": "判官_原始JSON_随访计划评估_理由",
    "判官_原始JSON_诊断匹配评估_more_info_reason": "判官_原始JSON_诊断匹配评估_理由",
    "判官_原始JSON_诊断匹配评估_need_more_info": "判官_原始JSON_诊断匹配评估_理由",
    "Gate2判官_原始JSON_修正诊断匹配_是否继续评测": "Gate2判官_原始JSON_是否继续评测",
    # Doc decision variants
    "医生决策_原始JSON_治疗方案": "医生决策_原始JSON_初步治疗方案",
    "医生_原始JSON_方案思维": "医生_原始JSON_术后治疗方案_方案详情",
    # Mixed English tokens
    "Diagnosis": "诊断",
    "diagnosis": "诊断",
    "Diagnos": "诊断",
    "diagnos": "诊断",
    "Check": "检查",
    "check": "检查",
    "建议:": "建议检查项目",
    "治疗后随访及评估": "诊疗经过回顾",
    "需要-补充检查": "需要补充检查",
    "能确定的诊断": "能够确诊",
    "诊断经过回顾": "诊疗经过回顾",
    "rehabilitation": "康复",
    "diagnostics_confidence": "诊断置信度",
    "诊断tics_confidence": "诊断置信度",
    "treatment_confidence": "治疗方案置信度",
    "初步治疗方案思维": "治疗方案思维",
    "置信度评估_A诊断置信度": "置信度评估_诊断置信度",
    "置信度评估_Stellen治疗方案置信度": "置信度评估_治疗方案置信度",
    "置信度评估_ Stellen治疗方案置信度": "置信度评估_治疗方案置信度",
    "WAAW-": "",
}

_CHECK_COL_KEYWORDS = [
    "诊断前所需检查",
    "需要补充门诊检查",
    "需要补充检查",
    "建议检查项目",
]

_DECISION_TERMS = [
    "修正诊断",
    "初步治疗方案",
    "最终诊断",
    "出院康复计划",
    "长期随访计划",
]


def canonicalize_sheet_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """
    Fix known column-header mojibake and MERGE duplicates introduced by the rename.
    Returns (new_df, changes).
    """
    if df.empty and df.shape[1] == 0:
        return df, []

    changes: list[dict[str, Any]] = []

    # Compute target header name for each column, preserving original order.
    target_names: list[str] = []
    target_to_cols: dict[str, list[Any]] = {}
    first_seen_order: list[str] = []
    for col in df.columns:
        old = str(col)
        new = old
        # Normalize whitespace first (including NBSP).
        new = "".join(" " if ch.isspace() else ch for ch in new)
        for src, tgt in _KNOWN_HEADER_REPLACEMENTS.items():
            if src in new:
                new = new.replace(src, tgt)

        # Remove stray spaces/punctuation in header names.
        new = new.replace(" ", "")
        new = new.replace(",", "").replace("，", "")
        new = new.replace(":", "").replace("：", "")

        # Normalize follow-up plan variants.
        if new.startswith("医生_原始JSON_长期随访计划_") and new.endswith("_"):
            new = "医生_原始JSON_长期随访计划_方案详情"
        if "长期随访计划_是否" in new and "需要常规随访" not in new:
            new = new.replace("长期随访计划_是否", "长期随访计划_是否需要常规随访")
        new = re.sub(r"(是否需要常规随访)[A-Za-z]+$", r"\1", new)
        new = new.replace("方案详情方案详情", "方案详情")

        # Normalize loop "思维" to "理由" for round-level JSON fields.
        if "轮_医生_原始JSON_" in new and new.endswith("思维"):
            new = new.replace("思维", "理由")
        if "轮_医生_原始JSON_" in new and "诊疗经过回顾" in new:
            new = new.replace("诊疗经过回顾", "理由")
        if "匹配的检查内容" in new:
            new = new.replace("匹配的检查内容", "匹配的检查项目")

        target_names.append(new)
        if new not in target_to_cols:
            target_to_cols[new] = []
            first_seen_order.append(new)
        target_to_cols[new].append(col)
        if new != old:
            changes.append({"action": "rename", "column": old, "new_column": new})

    case_id_col = df.columns[0] if df.shape[1] >= 1 else None

    def _to_na(s: pd.Series) -> pd.Series:
        # Treat empty strings/"nan"/NaN as NA so we can combine_first safely.
        return s.map(lambda v: pd.NA if is_empty(v) else v)

    out = pd.DataFrame(index=df.index)
    for new_name in first_seen_order:
        cols = target_to_cols.get(new_name, [])
        if not cols:
            continue
        if len(cols) == 1:
            out[new_name] = df[cols[0]]
            continue

        # Merge duplicates: keep the first non-empty value per row.
        merged = _to_na(df[cols[0]])
        conflict_cases: list[str] = []
        conflict_count = 0
        for col in cols[1:]:
            s2 = _to_na(df[col])
            conflict_mask = merged.notna() & s2.notna() & (merged.astype(str) != s2.astype(str))
            if conflict_mask.any():
                conflict_count += int(conflict_mask.sum())
                if case_id_col is not None and case_id_col in df.columns:
                    # Collect a few sample case IDs for audit (if available).
                    try:
                        samples = df.loc[conflict_mask, case_id_col].astype(str).head(5).tolist()
                        conflict_cases.extend([c for c in samples if c])
                    except Exception:
                        pass
            merged = merged.combine_first(s2)

        out[new_name] = merged
        changes.append(
            {
                "action": "merge_duplicate_after_rename",
                "new_column": new_name,
                "columns": [str(c) for c in cols],
                "conflict_count": conflict_count,
                "conflict_cases": conflict_cases[:5],
            }
        )

    return out, changes


def scan_sheet_anomalies(kind: str, sheet: str, df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Detect "human review" anomalies:
    - mojibake column headers
    - non-ASCII latin letters inside headers
    - check-list columns containing decision-terms (stage-mixing)
    """
    anomalies: list[dict[str, Any]] = []
    if df.empty or df.shape[1] < 2:
        return anomalies

    case_id_col = df.columns[0]

    def non_ascii_latin_chars(s: str) -> list[str]:
        bad: list[str] = []
        for ch in s:
            if ord(ch) <= 127:
                continue
            name = unicodedata.name(ch, "")
            if "LATIN" in name:
                bad.append(ch)
        return bad

    # Header anomalies
    for col in df.columns:
        c = str(col)
        for src, tgt in _KNOWN_HEADER_REPLACEMENTS.items():
            if src in c:
                anomalies.append(
                    {
                        "kind": kind,
                        "sheet": sheet,
                        "anomaly_type": "header_known_mojibake",
                        "column": c,
                        "details": json.dumps({"suggest": c.replace(src, tgt)}, ensure_ascii=False),
                    }
                )
        bad = non_ascii_latin_chars(c)
        if bad:
            anomalies.append(
                {
                    "kind": kind,
                    "sheet": sheet,
                    "anomaly_type": "header_non_ascii_latin",
                    "column": c,
                    "details": json.dumps({"bad_chars": bad}, ensure_ascii=False),
                }
            )

    # Value anomalies (focus on check-list columns)
    for col in df.columns[2:]:
        col_s = str(col)
        if not any(k in col_s for k in _CHECK_COL_KEYWORDS):
            continue

        # Scan rows: look for decision-terms (wrong-stage content)
        bad_cases: list[str] = []
        bad_samples: list[str] = []
        for _, r in df[[case_id_col, col]].iterrows():
            cid = str(r.get(case_id_col, "")).strip()
            v = r.get(col)
            if is_empty(v):
                continue
            s = str(v)
            if any(t in s for t in _DECISION_TERMS):
                bad_cases.append(cid)
                bad_samples.append(s[:120])
                if len(bad_cases) >= 5:
                    break

        if bad_cases:
            anomalies.append(
                {
                    "kind": kind,
                    "sheet": sheet,
                    "anomaly_type": "check_col_contains_decision_terms",
                    "column": col_s,
                    "details": json.dumps({"case_ids": bad_cases, "samples": bad_samples}, ensure_ascii=False),
                }
            )

    return anomalies
