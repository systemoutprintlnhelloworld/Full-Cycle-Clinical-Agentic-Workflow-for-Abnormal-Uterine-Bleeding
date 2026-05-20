from __future__ import annotations

import json
from typing import Any

import pandas as pd

from .parsing import is_empty


def _find_col(df: pd.DataFrame, name: str) -> str | None:
    for c in df.columns:
        if str(c).strip() == name:
            return str(c)
    return None


def _case_id_to_row_index(df: pd.DataFrame) -> dict[str, int]:
    if df.empty:
        return {}
    cid_col = df.columns[0]
    out: dict[str, int] = {}
    for idx, v in df[cid_col].items():
        cid = str(v).strip()
        if cid and cid.lower() != "nan":
            out[cid] = int(idx)
    return out


def _normalize_raw_json_str(v: Any) -> str | None:
    if is_empty(v):
        return None
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def repair_doc_loop_decision_duplicate_raw_json(
    doc_sheets: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    """
    Repair a known parse anomaly:
    some cases have D1/D2 loop round-1 raw JSON identical to the corresponding decision raw JSON.

    Observed impact:
    - Loop stage is effectively "not executed", but has spill-over decision content.
    - Judge loop sheets often have no outputs, so loop match metrics become NA and sample sizes look wrong.

    Strategy (safe auto-fix):
    - If (loop_raw_json_round1 == decision_raw_json) for the same case, then clear the loop row outputs
      (cols >= 3) and set loop status to "未经过".
    - Record the repair as a parse-anomaly row (with case_id samples) for transparency.
    """
    if not doc_sheets:
        return doc_sheets, []

    out = dict(doc_sheets)
    repairs: list[dict[str, Any]] = []

    def _repair_pair(loop_stage: str, decision_stage: str) -> None:
        loop_df = out.get(loop_stage)
        dec_df = out.get(decision_stage)
        if loop_df is None or dec_df is None or loop_df.empty or dec_df.empty:
            return

        loop_raw_col = _find_col(loop_df, "第1轮_医生_原始JSON")
        dec_raw_col = _find_col(dec_df, "医生决策_原始JSON")
        if loop_raw_col is None or dec_raw_col is None:
            return

        loop_idx = _case_id_to_row_index(loop_df)
        dec_idx = _case_id_to_row_index(dec_df)
        if not loop_idx or not dec_idx:
            return

        # Build decision raw JSON map (case_id -> normalized raw json string)
        dec_raw_map: dict[str, str] = {}
        for cid, ridx in dec_idx.items():
            dec_raw = _normalize_raw_json_str(dec_df.at[ridx, dec_raw_col])
            if dec_raw is not None:
                dec_raw_map[cid] = dec_raw

        dup_cases: list[str] = []
        # Only copy when we actually apply any change.
        loop_df2: pd.DataFrame | None = None

        for cid, ridx in loop_idx.items():
            loop_raw = _normalize_raw_json_str(loop_df.at[ridx, loop_raw_col])
            dec_raw = dec_raw_map.get(cid)
            if loop_raw is None or dec_raw is None:
                continue
            if loop_raw != dec_raw:
                continue

            dup_cases.append(cid)
            if loop_df2 is None:
                loop_df2 = loop_df.copy()

            # Column 0: case_id (keep). Column 1: 状态 (set to 未经过). Others: clear.
            if loop_df2.shape[1] >= 2:
                loop_df2.iat[ridx, 1] = "未经过"
            for c in loop_df2.columns[2:]:
                loop_df2.at[ridx, c] = pd.NA

        if dup_cases and loop_df2 is not None:
            out[loop_stage] = loop_df2
            repairs.append(
                {
                    "sheet": loop_stage,
                    "anomaly_type": "loop_raw_json_equals_decision_raw_json",
                    "column": loop_raw_col,
                    "details": json.dumps(
                        {
                            "decision_sheet": decision_stage,
                            "count": len(dup_cases),
                            # keep samples short; full list can be derived by re-scanning
                            "case_ids": sorted(dup_cases)[:20],
                            "auto_fix": "clear_loop_outputs_and_mark_not_executed",
                        },
                        ensure_ascii=False,
                    ),
                }
            )

    _repair_pair("D1_Outpatient_Loop", "D1_Outpatient_Decision")
    _repair_pair("D2_Admission_Loop", "D2_Admission_Decision")

    return out, repairs


def repair_doc_decision_nested_fields(
    doc_sheets: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    """
    Merge nested decision fields into their parent columns to reduce spurious extra columns.
    - 初步治疗方案_* -> 初步治疗方案
    - 术后信息汇总_* -> 诊疗经过回顾
    - 初步治疗方案_术后信息汇总_* -> 诊疗经过回顾
    - 方案思维 -> 术后治疗方案_方案详情
    """
    if not doc_sheets:
        return doc_sheets, []

    out = dict(doc_sheets)
    repairs: list[dict[str, Any]] = []

    def _merge_children(
        df: pd.DataFrame,
        *,
        parent: str,
        child_prefixes: list[str],
        drop: bool = True,
        label: str,
    ) -> tuple[pd.DataFrame, int]:
        if df is None or df.empty:
            return df, 0
        child_cols: list[str] = []
        for c in df.columns:
            c_str = str(c)
            if any(c_str.startswith(p) for p in child_prefixes):
                child_cols.append(c_str)
        if not child_cols:
            return df, 0

        df2 = df.copy()
        if parent not in df2.columns:
            df2[parent] = pd.NA

        applied = 0
        for idx in df2.index:
            payload: dict[str, Any] = {}
            for c in child_cols:
                v = df2.at[idx, c]
                if is_empty(v):
                    continue
                subkey = c
                for p in child_prefixes:
                    if subkey.startswith(p):
                        subkey = subkey[len(p) :]
                        break
                subkey = subkey.lstrip("_") or "内容"
                payload[subkey] = v
            if not payload:
                continue
            parent_val = df2.at[idx, parent] if parent in df2.columns else pd.NA
            payload_json = json.dumps(payload, ensure_ascii=False)
            if is_empty(parent_val):
                df2.at[idx, parent] = payload_json
                applied += 1
            else:
                # Append only when parent already has content.
                if payload_json not in str(parent_val):
                    df2.at[idx, parent] = f"{parent_val} | {payload_json}"
                    applied += 1

        if drop:
            df2 = df2.drop(columns=child_cols, errors="ignore")
        return df2, applied

    # D1/D2 decision: merge nested treatment plan into parent
    for stage in ["D1_Outpatient_Decision", "D2_Admission_Decision"]:
        df = out.get(stage)
        if df is None or df.empty:
            continue
        df2, applied = _merge_children(
            df,
            parent="医生决策_原始JSON_初步治疗方案",
            child_prefixes=["医生决策_原始JSON_初步治疗方案_"],
            label="初步治疗方案嵌套字段",
        )
        if applied > 0:
            repairs.append(
                {
                    "sheet": stage,
                    "anomaly_type": "nested_fields_merged",
                    "column": "医生决策_原始JSON_初步治疗方案_*",
                    "details": json.dumps({"note": "已合并嵌套字段到初步治疗方案", "count": applied}, ensure_ascii=False),
                }
            )
        df3, applied2 = _merge_children(
            df2,
            parent="医生决策_原始JSON_诊疗经过回顾",
            child_prefixes=[
                "医生决策_原始JSON_术后信息汇总_",
                "医生决策_原始JSON_术后信息汇总",
                "医生决策_原始JSON_初步治疗方案_术后信息汇总_",
                "医生决策_原始JSON_初步治疗方案_术后信息汇总",
            ],
            label="术后信息汇总嵌套字段",
        )
        if applied2 > 0:
            repairs.append(
                {
                    "sheet": stage,
                    "anomaly_type": "nested_fields_merged",
                    "column": "医生决策_原始JSON_术后信息汇总_*",
                    "details": json.dumps({"note": "已合并术后信息汇总到诊疗经过回顾", "count": applied2}, ensure_ascii=False),
                }
            )
        out[stage] = df3

    # D3 decision: map plan thought into plan detail
    stage = "D3_Surgery_Decision"
    df = out.get(stage)
    if df is not None and not df.empty:
        plan_col = "医生_原始JSON_术后治疗方案_方案详情"
        if "医生_原始JSON_方案思维" in df.columns:
            df2 = df.copy()
            if plan_col not in df2.columns:
                df2[plan_col] = pd.NA
            applied = 0
            for idx in df2.index:
                if not is_empty(df2.at[idx, "医生_原始JSON_方案思维"]):
                    if is_empty(df2.at[idx, plan_col]):
                        df2.at[idx, plan_col] = df2.at[idx, "医生_原始JSON_方案思维"]
                        applied += 1
            df2 = df2.drop(columns=["医生_原始JSON_方案思维"], errors="ignore")
            if applied > 0:
                repairs.append(
                    {
                        "sheet": stage,
                        "anomaly_type": "nested_fields_merged",
                        "column": "医生_原始JSON_方案思维",
                        "details": json.dumps({"note": "已合并方案思维到术后治疗方案_方案详情", "count": applied}, ensure_ascii=False),
                    }
                )
            out[stage] = df2

    return out, repairs
