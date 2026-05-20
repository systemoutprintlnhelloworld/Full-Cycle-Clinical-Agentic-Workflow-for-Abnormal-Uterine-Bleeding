from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


_STAGE_CN = {
    "D1_Outpatient_Loop": "D1 门诊循环",
    "D1_Outpatient_Decision": "D1 门诊决策",
    "D2_SuggestedFromD1Decision": "D2 入院检查(源自D1决策建议)",
    "D2_Admission_Loop": "D2 入院循环",
    "D2_Admission_Decision": "D2 入院决策",
    "D3_Surgery_Decision": "D3 手术决策",
    "D4_Rehab_Plan": "D4 康复计划",
}
_STAGE_CN_TO_CODE = {v: k for k, v in _STAGE_CN.items()}


def stage_cn(stage: str) -> str:
    return _STAGE_CN.get(stage, stage)


def stage_code(stage: str) -> str:
    if stage in _STAGE_CN:
        return stage
    return _STAGE_CN_TO_CODE.get(stage, stage)


def _to01(v: Any) -> int:
    if v is None:
        return 0
    if isinstance(v, (int, float)) and not (isinstance(v, float) and pd.isna(v)):
        return 1 if float(v) != 0 else 0
    if isinstance(v, bool):
        return 1 if v else 0
    s = str(v).strip().lower()
    if s in {"1", "1.0", "true", "yes", "y", "是"}:
        return 1
    return 0


def _safe_int(v: Any) -> int | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if s == "" or s.lower() == "nan":
        return None
    try:
        return int(round(float(s)))
    except Exception:
        return None


def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    s = str(v).strip()
    return s == "" or s.lower() == "nan"


def _normalize_text(text: Any) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    s = str(text)
    return (
        s.replace("，", ",")
        .replace("：", ":")
        .replace("；", ";")
        .replace("＝", "=")
        .replace("（", "(")
        .replace("）", ")")
    )


def _extract_int(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _parse_counts_from_feedback(text: str) -> tuple[int | None, int | None, int | None, str]:
    """
    Parse ai_total / matched / unmatched counts from free text.
    Returns (ai_total, matched, unmatched, note)
    """
    t = _normalize_text(text)
    if not t.strip():
        return None, None, None, ""

    ai = _extract_int(r"(?:AI请求检查数|AI请求数|请求数|AI请求)[^0-9]{0,6}(\d+)", t)
    unmatched = _extract_int(r"(?:未匹配|不匹配|未执行)[^0-9]{0,6}(\d+)", t)
    matched = _extract_int(r"(?<!未)(?<!不)匹配[^0-9]{0,6}(\d+)", t)

    note_parts = []
    if ai is not None:
        note_parts.append("ai_total:文本")
    if matched is not None:
        note_parts.append("matched:文本")
    if unmatched is not None:
        note_parts.append("unmatched:文本")

    if ai is None and matched is not None and unmatched is not None:
        ai = matched + unmatched
        note_parts.append("ai_total=matched+unmatched")
    if matched is None and ai is not None and unmatched is not None:
        matched = ai - unmatched
        note_parts.append("matched=ai-unmatched")
    if unmatched is None and ai is not None and matched is not None:
        unmatched = ai - matched
        note_parts.append("unmatched=ai-matched")

    # Guard invalid
    for label, v in [("ai_total", ai), ("matched", matched), ("unmatched", unmatched)]:
        if v is not None and v < 0:
            note_parts.append(f"{label}:invalid")
    if (matched is not None and ai is not None and matched > ai) or (unmatched is not None and ai is not None and unmatched > ai):
        note_parts.append("counts>ai_total")

    if "invalid" in " ".join(note_parts) or "counts>ai_total" in note_parts:
        return None, None, None, ";".join(note_parts)

    return ai, matched, unmatched, ";".join(note_parts)


def _should_apply_feedback(conclusion: str, text: str) -> bool:
    c = str(conclusion or "").strip()
    t = _normalize_text(text)
    if not t.strip():
        return False
    positive = any(k in c for k in ["正常", "无误", "通过", "没问题", "无需修改", "无需修正"])
    negative = any(k in c for k in ["异常", "有误", "错误", "需修正", "需要修正", "修改", "不对"])
    if positive and not negative:
        return False
    has_digit = re.search(r"\d+", t) is not None
    has_keywords = any(k in t for k in ["AI请求", "请求数", "匹配", "未匹配", "未执行"])
    return has_digit and has_keywords


def apply_review_feedback_to_override_template(
    overrides_path: Path, review_feedback: pd.DataFrame, audit_path: Path | None = None
) -> pd.DataFrame:
    """
    Auto-map review feedback into overrides template (no data/ writes).
    - Only fills missing override fields.
    - Does not override rows with explicit "采用修正(0/1)=0".
    Returns audit DataFrame (what was applied / skipped).
    """
    if review_feedback is None or review_feedback.empty or not overrides_path.exists():
        return pd.DataFrame()

    try:
        ov = pd.read_csv(overrides_path, encoding="utf-8-sig")
    except Exception:
        ov = pd.read_csv(overrides_path, encoding="utf-8")
    if ov.empty:
        return pd.DataFrame()

    key_cols = ["中心", "模型", "病例ID", "阶段代码", "轮次"]
    if not set(key_cols) <= set(ov.columns):
        return pd.DataFrame()
    if "备注" in ov.columns:
        ov["备注"] = ov["备注"].astype("object")

    fb = review_feedback.copy()
    need = {"中心", "模型", "病例ID", "阶段", "轮次", "反馈_结论", "反馈_建议动作", "反馈_备注"}
    if not need <= set(fb.columns):
        return pd.DataFrame()

    for c in ["中心", "模型", "病例ID", "阶段"]:
        fb[c] = fb[c].astype(str).str.strip()
    fb["阶段代码"] = fb["阶段"].map(stage_code)
    fb["轮次"] = pd.to_numeric(fb["轮次"], errors="coerce").fillna(-1).astype(int)

    ov["轮次"] = pd.to_numeric(ov["轮次"], errors="coerce").fillna(-1).astype(int)

    audit_rows = []
    updated = False

    for _, r in fb.iterrows():
        text = " ".join([str(r.get("反馈_建议动作") or ""), str(r.get("反馈_备注") or "")]).strip()
        if not _should_apply_feedback(str(r.get("反馈_结论") or ""), text):
            audit_rows.append(
                {
                    "中心": r.get("中心"),
                    "模型": r.get("模型"),
                    "病例ID": r.get("病例ID"),
                    "阶段代码": r.get("阶段代码"),
                    "轮次": r.get("轮次"),
                    "反馈_结论": r.get("反馈_结论"),
                    "反馈_建议动作": r.get("反馈_建议动作"),
                    "反馈_备注": r.get("反馈_备注"),
                    "解析_AI请求检查数": "",
                    "解析_匹配数": "",
                    "解析_未匹配数": "",
                    "处理结果": "跳过(结论正常或无数字)",
                }
            )
            continue

        ai, matched, unmatched, note = _parse_counts_from_feedback(text)
        if ai is None and matched is None and unmatched is None:
            audit_rows.append(
                {
                    "中心": r.get("中心"),
                    "模型": r.get("模型"),
                    "病例ID": r.get("病例ID"),
                    "阶段代码": r.get("阶段代码"),
                    "轮次": r.get("轮次"),
                    "反馈_结论": r.get("反馈_结论"),
                    "反馈_建议动作": r.get("反馈_建议动作"),
                    "反馈_备注": r.get("反馈_备注"),
                    "解析_AI请求检查数": "",
                    "解析_匹配数": "",
                    "解析_未匹配数": "",
                    "处理结果": f"跳过(无法解析){note}",
                }
            )
            continue

        mask = (
            (ov["中心"].astype(str).str.strip() == str(r.get("中心") or "").strip())
            & (ov["模型"].astype(str).str.strip() == str(r.get("模型") or "").strip())
            & (ov["病例ID"].astype(str).str.strip() == str(r.get("病例ID") or "").strip())
            & (ov["阶段代码"].astype(str).str.strip() == str(r.get("阶段代码") or "").strip())
            & (ov["轮次"] == int(r.get("轮次")))
        )
        if not mask.any():
            audit_rows.append(
                {
                    "中心": r.get("中心"),
                    "模型": r.get("模型"),
                    "病例ID": r.get("病例ID"),
                    "阶段代码": r.get("阶段代码"),
                    "轮次": r.get("轮次"),
                    "反馈_结论": r.get("反馈_结论"),
                    "反馈_建议动作": r.get("反馈_建议动作"),
                    "反馈_备注": r.get("反馈_备注"),
                    "解析_AI请求检查数": ai,
                    "解析_匹配数": matched,
                    "解析_未匹配数": unmatched,
                    "处理结果": "跳过(未找到对应行)",
                }
            )
            continue

        for idx in ov.loc[mask].index:
            apply_val = ov.at[idx, "采用修正(0/1)"] if "采用修正(0/1)" in ov.columns else ""
            if not _is_blank(apply_val) and _to01(apply_val) == 0:
                audit_rows.append(
                    {
                        "中心": r.get("中心"),
                        "模型": r.get("模型"),
                        "病例ID": r.get("病例ID"),
                        "阶段代码": r.get("阶段代码"),
                        "轮次": r.get("轮次"),
                        "反馈_结论": r.get("反馈_结论"),
                        "反馈_建议动作": r.get("反馈_建议动作"),
                        "反馈_备注": r.get("反馈_备注"),
                        "解析_AI请求检查数": ai,
                        "解析_匹配数": matched,
                        "解析_未匹配数": unmatched,
                        "处理结果": "跳过(显式不采用修正)",
                    }
                )
                continue

            row_changed = False
            if ai is not None and "修正_AI请求检查数" in ov.columns and _is_blank(ov.at[idx, "修正_AI请求检查数"]):
                ov.at[idx, "修正_AI请求检查数"] = ai
                row_changed = True
            if matched is not None and "修正_匹配数" in ov.columns and _is_blank(ov.at[idx, "修正_匹配数"]):
                ov.at[idx, "修正_匹配数"] = matched
                row_changed = True
            if unmatched is not None and "修正_未匹配数" in ov.columns and _is_blank(ov.at[idx, "修正_未匹配数"]):
                ov.at[idx, "修正_未匹配数"] = unmatched
                row_changed = True

            if row_changed and "采用修正(0/1)" in ov.columns and _is_blank(ov.at[idx, "采用修正(0/1)"]):
                ov.at[idx, "采用修正(0/1)"] = 1

            if row_changed and "备注" in ov.columns:
                note_prefix = "auto:来自审阅反馈"
                existing = "" if _is_blank(ov.at[idx, "备注"]) else str(ov.at[idx, "备注"])
                ov.at[idx, "备注"] = note_prefix if existing == "" else f"{existing} | {note_prefix}"

            updated = updated or row_changed
            audit_rows.append(
                {
                    "中心": r.get("中心"),
                    "模型": r.get("模型"),
                    "病例ID": r.get("病例ID"),
                    "阶段代码": r.get("阶段代码"),
                    "轮次": r.get("轮次"),
                    "反馈_结论": r.get("反馈_结论"),
                    "反馈_建议动作": r.get("反馈_建议动作"),
                    "反馈_备注": r.get("反馈_备注"),
                    "解析_AI请求检查数": ai,
                    "解析_匹配数": matched,
                    "解析_未匹配数": unmatched,
                    "处理结果": "已写入" if row_changed else "未变更(已有修正值)",
                }
            )

    audit_df = pd.DataFrame(audit_rows)
    if updated:
        ov.to_csv(overrides_path, index=False, encoding="utf-8-sig")
    if audit_path is not None and not audit_df.empty:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_df.to_csv(audit_path, index=False, encoding="utf-8-sig")
    return audit_df


def load_check_round_overrides_csv(path: Path) -> pd.DataFrame:
    """
    Load human overrides for check-round counts.

    Expected columns (Chinese, editable in Excel):
    - 中心, 模型, 病例ID, 阶段代码, 轮次
    - 修正_AI请求检查数, 修正_匹配数, 修正_未匹配数
    - 采用修正(0/1)
    - 备注
    """
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(path, encoding="utf-8")
    if df.empty:
        return df

    col_map = {
        "中心": "center",
        "模型": "model",
        "病例ID": "case_id",
        "阶段代码": "stage",
        "轮次": "round_idx",
        "修正_AI请求检查数": "override_ai_total",
        "修正_匹配数": "override_matched",
        "修正_未匹配数": "override_unmatched",
        "采用修正(0/1)": "apply_override",
        "备注": "note",
    }
    out = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}).copy()

    need = {"center", "model", "case_id", "stage", "round_idx"}
    if not need <= set(out.columns):
        return pd.DataFrame()

    out["center"] = out["center"].astype(str).str.strip()
    out["model"] = out["model"].astype(str).str.strip()
    out["case_id"] = out["case_id"].astype(str).str.strip()
    out["stage"] = out["stage"].astype(str).str.strip()
    out["round_idx"] = pd.to_numeric(out["round_idx"], errors="coerce").fillna(-1).astype(int)

    out["apply_override"] = out.get("apply_override", 0).map(_to01).astype(int)

    for c in ["override_ai_total", "override_matched", "override_unmatched"]:
        if c not in out.columns:
            out[c] = pd.NA
        out[c] = out[c].map(_safe_int)

    if "note" not in out.columns:
        out["note"] = ""
    out["note"] = out["note"].astype(str)

    # Keep only rows that opted-in
    out = out.loc[out["apply_override"] == 1].copy()
    return out


def apply_check_round_overrides(check_rounds: pd.DataFrame, overrides: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Apply overrides onto check_rounds.
    Returns:
    - new_check_rounds
    - applied_overrides (audit table)
    """
    if check_rounds.empty or overrides.empty:
        return check_rounds, pd.DataFrame()

    key_cols = ["center", "model", "case_id", "stage", "round_idx"]
    if not set(key_cols) <= set(check_rounds.columns):
        return check_rounds, pd.DataFrame()

    ov = overrides.copy()
    keep = key_cols + ["override_ai_total", "override_matched", "override_unmatched", "note"]
    ov = ov.loc[:, [c for c in keep if c in ov.columns]].copy()

    cr = check_rounds.copy()
    merged = cr.merge(ov, on=key_cols, how="left", suffixes=("", "_ov"))

    applied_mask = merged["override_ai_total"].notna() | merged["override_matched"].notna() | merged["override_unmatched"].notna()
    if not applied_mask.any():
        return check_rounds, pd.DataFrame()

    before_ai = pd.to_numeric(merged.get("ai_total_requested_count"), errors="coerce")
    before_m = pd.to_numeric(merged.get("matched_count_final"), errors="coerce")
    before_u = pd.to_numeric(merged.get("unmatched_count_final"), errors="coerce")

    # Apply overrides (fallback to existing)
    ai = merged["override_ai_total"].where(merged["override_ai_total"].notna(), before_ai)
    m = merged["override_matched"].where(merged["override_matched"].notna(), before_m)
    u = merged["override_unmatched"].where(merged["override_unmatched"].notna(), before_u)

    # If unmatched not provided but ai+matched are, compute.
    need_calc_u = merged["override_unmatched"].isna() & ai.notna() & m.notna()
    u = u.where(~need_calc_u, (ai - m).clip(lower=0))

    ai = ai.clip(lower=0)
    m = m.clip(lower=0)
    u = u.clip(lower=0)

    # Cap matched to ai_total when possible.
    cap_mask = ai.notna() & m.notna()
    m = m.where(~cap_mask, m.clip(upper=ai))
    # Recompute unmatched to keep consistent if needed.
    u = u.where(~cap_mask, u.clip(upper=(ai - m).clip(lower=0)))

    merged["ai_total_requested_count"] = ai
    merged["matched_count_final"] = m
    merged["unmatched_count_final"] = u
    merged["ai_total_source"] = merged["ai_total_source"].where(~applied_mask, "override")
    merged["matched_count_source"] = merged["matched_count_source"].where(~applied_mask, "override")

    # Recompute zero-match inefficiency flag (used in aggregation)
    merged["inefficient_round_by_zero"] = (ai.fillna(0) > 0) & (m.fillna(0) == 0)

    audit = merged.loc[applied_mask, key_cols].copy()
    audit["AI请求检查数_修改前"] = before_ai.loc[applied_mask].tolist()
    audit["AI请求检查数_修改后"] = ai.loc[applied_mask].tolist()
    audit["匹配数_修改前"] = before_m.loc[applied_mask].tolist()
    audit["匹配数_修改后"] = m.loc[applied_mask].tolist()
    audit["未匹配数_修改前"] = before_u.loc[applied_mask].tolist()
    audit["未匹配数_修改后"] = u.loc[applied_mask].tolist()
    audit["备注"] = merged.loc[applied_mask, "note"].fillna("").astype(str).tolist()

    # Drop helper columns
    merged = merged.drop(columns=[c for c in merged.columns if c.startswith("override_") or c == "note"], errors="ignore")
    return merged, audit


def update_check_round_override_template(path: Path, check_rounds_review: pd.DataFrame) -> None:
    """
    Upsert a human-editable template CSV.
    - If path doesn't exist: create it.
    - If exists: preserve human columns (修正_*, 采用修正, 备注) while refreshing "当前" fields.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if check_rounds_review is None or check_rounds_review.empty:
        return

    df = check_rounds_review.copy()
    key_cols = ["center", "model", "case_id", "stage", "round_idx"]
    if not set(key_cols) <= set(df.columns):
        return

    def norm_json(v: Any) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        if isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)
        s = str(v)
        # If already JSON-ish, keep
        return s

    tmpl = pd.DataFrame(
        {
            "中心": df["center"].astype(str),
            "模型": df["model"].astype(str),
            "病例ID": df["case_id"].astype(str),
            "阶段代码": df["stage"].astype(str),
            "阶段": df["stage"].astype(str).map(stage_cn),
            "轮次": pd.to_numeric(df["round_idx"], errors="coerce").fillna(-1).astype(int),
            "复核原因(为何入表)": df.get("review_reasons", "").astype(str),
            "AI请求检查数(当前)": pd.to_numeric(df.get("ai_total_requested_count"), errors="coerce"),
            "匹配数(当前)": pd.to_numeric(df.get("matched_count_final"), errors="coerce"),
            "未匹配数(当前)": pd.to_numeric(df.get("unmatched_count_final"), errors="coerce"),
            "AI请求原文(供核对)": df.get("doc_ai_requests_text", "").map(norm_json),
            "未匹配检查(判官-未执行列表)": df.get("judge_unexecuted_items_raw", "").map(norm_json),
            "匹配检查(判官列表)": df.get("judge_matched_items_raw", "").map(norm_json),
            "疑似额外匹配项(列表)": df.get("judge_extra_matched_items_suspect", "").map(norm_json),
        }
    )

    # Human-editable columns
    human_cols = [
        "修正_AI请求检查数",
        "修正_匹配数",
        "修正_未匹配数",
        "采用修正(0/1)",
        "备注",
    ]
    for c in human_cols:
        tmpl[c] = pd.NA

    if path.exists():
        try:
            old = pd.read_csv(path, encoding="utf-8-sig")
        except Exception:
            old = pd.read_csv(path, encoding="utf-8")
        if not old.empty:
            keys_cn = ["中心", "模型", "病例ID", "阶段代码", "轮次"]
            keep = [c for c in human_cols if c in old.columns] + keys_cn
            old_h = old.loc[:, [c for c in keep if c in old.columns]].copy()
            tmpl = tmpl.merge(old_h, on=keys_cn, how="left", suffixes=("", "_old"))
            for c in human_cols:
                if c in tmpl.columns and f"{c}_old" in tmpl.columns:
                    tmpl[c] = tmpl[c].where(tmpl[c].notna(), tmpl[f"{c}_old"])
            tmpl = tmpl.drop(columns=[c for c in tmpl.columns if c.endswith("_old")], errors="ignore")

    tmpl = tmpl.sort_values(["中心", "模型", "病例ID", "阶段代码", "轮次"])
    tmpl.to_csv(path, index=False, encoding="utf-8-sig")
