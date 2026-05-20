from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import json
import pandas as pd

from .parsing import is_empty, normalize_check_name, parse_check_list_cell, parse_list_cell
from .status import safe_float
from .types import LoadedData


@dataclass(frozen=True)
class CheckRoundConfig:
    stage: str
    doc_sheet: str
    judge_sheet: str
    request_col_candidates: Callable[[int], list[str]]
    judge_matched_col: Callable[[int], str]
    judge_unexecuted_col: Callable[[int], str]
    judge_reason_col: Callable[[int], str]
    judge_matched_count_col: Callable[[int], str]
    judge_total_count_col: Callable[[int], str]
    judge_match_score_col: Callable[[int], str]
    judge_reasonable_score_col: Callable[[int], str]
    judge_composite_score_col: Callable[[int], str]


def _get_row(df: pd.DataFrame, case_id: str) -> pd.Series | None:
    if df.empty:
        return None
    cid_col = df.columns[0]
    sel = df.loc[df[cid_col].astype(str) == case_id]
    if sel.empty:
        return None
    return sel.iloc[0]


def _get_status(df: pd.DataFrame, row: pd.Series | None) -> str:
    if row is None or df.shape[1] < 2:
        return ""
    status_col = df.columns[1]
    v = row.get(status_col)
    return "" if is_empty(v) else str(v).strip()


def _first_existing_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = set(str(c) for c in df.columns)
    for c in candidates:
        if c in cols:
            return c
    return None


def _pick_request_col(df: pd.DataFrame, row: pd.Series | None, candidates: list[str]) -> str | None:
    """
    Pick the first *non-empty* check-list column from candidates.

    Why: in some Parsed Excels, a higher-priority column exists but is empty for a case,
    while a lower-priority synonym column is populated.
    """
    if row is not None:
        for c in candidates:
            if c not in df.columns:
                continue
            # Use the same parser as metric computation to judge "non-empty"
            # (also avoids boolean flag fields being treated as check items).
            if parse_check_list_cell(row.get(c)):
                return c
    # Fallback: first existing (may be empty) so we can still surface the column name in audits.
    return _first_existing_col(df, candidates)


def _extract_checks_from_round_raw_json(stage: str, raw_json_value: Any) -> tuple[str, list[str], Any] | None:
    """
    Fallback for cases where the extracted check-list column is empty but the round raw JSON exists.

    This only extracts the *check list* keys that belong to the loop stage schema:
    - D1 loop: 诊断前所需检查 / 需要补充检查
    - D2 loop: 需要补充检查
    """
    if is_empty(raw_json_value):
        return None
    s = str(raw_json_value).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        obj = json.loads(s)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None

    keys_by_stage: dict[str, list[str]] = {
        "D1_Outpatient_Loop": ["诊断前所需检查", "需要补充检查"],
        "D2_Admission_Loop": ["需要补充检查"],
    }
    keys = keys_by_stage.get(stage, [])
    for k in keys:
        v = obj.get(k)
        items = parse_check_list_cell(v)
        if items:
            return k, items, v
    return None


def _coerce_int(v: Any) -> int | None:
    f = safe_float(v)
    if f is None:
        return None
    try:
        return int(round(f))
    except Exception:
        return None


def _has_any(norm: str, tokens: set[str]) -> bool:
    return any(t in norm for t in tokens)


_CHECK_TOKEN_GROUPS: list[set[str]] = [
    {"超声", "彩超", "b超"},
    {"mri", "核磁"},
    {"ct", "petct", "pet-ct"},
    {"tct"},
    {"hpv"},
    {"宫腔镜"},
    {"病理", "活检", "锥切"},
    {"性激素", "fsh", "lh", "e2", "prl"},
    {"血常规"},
    {"凝血"},
    {"肿瘤标志物", "ca125", "ca199", "ca19-9", "cea", "he4"},
    {"心电图", "ecg"},
]


def _likely_same_check(j: str, a: str) -> bool:
    jn = normalize_check_name(j)
    an = normalize_check_name(a)
    if not jn or not an:
        return False
    if (jn in an) or (an in jn):
        return True
    for g in _CHECK_TOKEN_GROUPS:
        if _has_any(jn, g) and _has_any(an, g):
            return True
    return False


def _align_judge_items_to_ai_requested(judge_items: list[str], ai_items: list[str]) -> tuple[list[str], list[str]]:
    """
    Align judge list items to the checks that the AI actually requested.

    This helps avoid counting judge "extra matched items" that were NOT requested by the AI.
    Returns (aligned_items, extras).
    """
    if not judge_items:
        return [], []
    if not ai_items:
        return list(judge_items), []
    aligned: list[str] = []
    extras: list[str] = []
    for j in judge_items:
        if any(_likely_same_check(j, a) for a in ai_items):
            aligned.append(j)
        else:
            extras.append(j)
    return aligned, extras


def _pick_extra_items(
    judge_matched_items: list[str],
    ai_items: list[str],
    matched_count_raw: int | None,
) -> list[str]:
    if matched_count_raw is None:
        return []
    if len(judge_matched_items) <= matched_count_raw:
        return []
    extra_count = len(judge_matched_items) - matched_count_raw

    candidates: list[str] = []
    for j in judge_matched_items:
        if any(_likely_same_check(j, a) for a in ai_items):
            continue
        candidates.append(j)

    if len(candidates) >= extra_count:
        return candidates[:extra_count]
    # fallback: take last N
    return (candidates + judge_matched_items)[-extra_count:]


def build_check_rounds(loaded: LoadedData, match_score_threshold: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    center = loaded.fileset.center
    model = loaded.fileset.model

    # D1 loop config
    def d1_req_cols(i: int) -> list[str]:
        return [
            f"第{i}轮_医生_原始JSON_诊断前所需检查（优先）",
            f"第{i}轮_医生_原始JSON_诊断前所需检查(优先)",
            f"第{i}轮_医生_原始JSON_诊断前所需检查",
            # NOTE: Do NOT use "建议检查项目" as D1-loop check source.
            # User-confirmed: D1 decision "建议检查项目" corresponds to admission checks (D2),
            # and some rare files also spill decision-like keys into loop sheets. We treat that as
            # a parse/anomaly issue to be fixed explicitly (rather than silently mixing stages).
            # Legacy exports may store the list under "需要补充检查" (string list, NOT bool flags).
            f"第{i}轮_医生_原始JSON_需要补充检查",
        ]

    def j1(prefix: str) -> Callable[[int], str]:
        return lambda i: f"第{i}轮_判官_原始JSON_{prefix}"

    d1_cfg = CheckRoundConfig(
        stage="D1_Outpatient_Loop",
        doc_sheet="D1_Outpatient_Loop",
        judge_sheet="D1_Outpatient_Loop",
        request_col_candidates=d1_req_cols,
        judge_matched_col=j1("匹配的检查项目"),
        judge_unexecuted_col=j1("AI建议但实际未执行的检查"),
        judge_reason_col=j1("reason"),
        judge_matched_count_col=j1("匹配数量"),
        judge_total_count_col=j1("总请求数量"),
        judge_match_score_col=j1("评分_检查匹配度"),
        judge_reasonable_score_col=j1("评分_合理性评分"),
        judge_composite_score_col=j1("评分_综合评分"),
    )

    # D2 loop config
    def d2_req_cols(i: int) -> list[str]:
        return [f"第{i}轮_医生_原始JSON_需要补充检查"]

    d2_cfg = CheckRoundConfig(
        stage="D2_Admission_Loop",
        doc_sheet="D2_Admission_Loop",
        judge_sheet="D2_Admission_Loop",
        request_col_candidates=d2_req_cols,
        judge_matched_col=j1("匹配的检查项目"),
        judge_unexecuted_col=j1("AI建议但实际未执行的检查"),
        judge_reason_col=j1("reason"),
        judge_matched_count_col=j1("匹配数量"),
        judge_total_count_col=j1("总请求数量"),
        judge_match_score_col=j1("评分_检查匹配度"),
        judge_reasonable_score_col=j1("评分_合理性评分"),
        judge_composite_score_col=j1("评分_综合评分"),
    )

    def emit_loop_rows(cfg: CheckRoundConfig) -> None:
        doc_df = loaded.doc_sheets[cfg.doc_sheet]
        judge_df = loaded.judge_sheets[cfg.judge_sheet]
        cid_col = doc_df.columns[0]
        case_ids = [str(x) for x in doc_df[cid_col].dropna().astype(str).unique()]

        for case_id in case_ids:
            doc_row = _get_row(doc_df, case_id)
            judge_row = _get_row(judge_df, case_id)
            status_doc = _get_status(doc_df, doc_row)
            status_judge = _get_status(judge_df, judge_row)

            for round_idx in range(1, 5):
                req_col = _pick_request_col(doc_df, doc_row, cfg.request_col_candidates(round_idx))
                if not req_col:
                    continue
                ai_text = "" if doc_row is None else doc_row.get(req_col)
                doc_ai_items = parse_check_list_cell(ai_text)
                # Fallback: if the extracted check-list column is empty but the round raw JSON exists,
                # try extracting the intended loop-stage check list from the raw JSON itself.
                if not doc_ai_items and doc_row is not None:
                    raw_col = f"第{round_idx}轮_医生_原始JSON"
                    if raw_col in doc_df.columns:
                        extracted = _extract_checks_from_round_raw_json(cfg.stage, doc_row.get(raw_col))
                        if extracted is not None:
                            key, items, v = extracted
                            doc_ai_items = items
                            ai_text = v
                            req_col = f"{raw_col}:{key}"

                matched_col = cfg.judge_matched_col(round_idx)
                unexec_col = cfg.judge_unexecuted_col(round_idx)
                reason_col = cfg.judge_reason_col(round_idx)
                matched_count_col = cfg.judge_matched_count_col(round_idx)
                total_count_col = cfg.judge_total_count_col(round_idx)
                match_score_col = cfg.judge_match_score_col(round_idx)
                reasonable_score_col = cfg.judge_reasonable_score_col(round_idx)
                composite_score_col = cfg.judge_composite_score_col(round_idx)

                judge_matched_items_raw = [] if judge_row is None else parse_list_cell(judge_row.get(matched_col))
                judge_unexecuted_items_raw = [] if judge_row is None else parse_list_cell(judge_row.get(unexec_col))
                judge_reason = "" if judge_row is None else ("" if is_empty(judge_row.get(reason_col)) else str(judge_row.get(reason_col)))

                judge_matched_count = None if judge_row is None else _coerce_int(judge_row.get(matched_count_col))
                judge_total_count = None if judge_row is None else _coerce_int(judge_row.get(total_count_col))
                judge_match_score = None if judge_row is None else safe_float(judge_row.get(match_score_col))
                judge_reasonable_score = None if judge_row is None else safe_float(judge_row.get(reasonable_score_col))
                judge_composite_score = None if judge_row is None else safe_float(judge_row.get(composite_score_col))

                # If doc-extracted request text is missing, but judge provides structured matched/unexecuted lists,
                # keep the pipeline runnable and make the review sheet interpretable by using judge lists as a proxy
                # of "what was requested". (Source is still recorded via ai_total_source/judge_list_len.)
                if not doc_ai_items and (judge_matched_items_raw or judge_unexecuted_items_raw) and is_empty(ai_text):
                    doc_ai_items = [str(x).strip() for x in (judge_matched_items_raw + judge_unexecuted_items_raw) if not is_empty(x)]
                    ai_text = json_safe(doc_ai_items)
                    req_col = "判官列表(兜底)"

                doc_ai_total = len(doc_ai_items)
                has_ai_request = bool(doc_ai_items) or (
                    not is_empty(ai_text)
                    and str(ai_text).strip() not in {"无", "无。", "无."}
                    and str(ai_text).strip().lower() not in {"nan", "<na>"}
                )

                # Align judge lists to the checks that the AI actually requested.
                # This prevents "extra matched items" from inflating counts.
                judge_matched_items, extras_suspect = _align_judge_items_to_ai_requested(judge_matched_items_raw, doc_ai_items)
                judge_unexecuted_items, _ = _align_judge_items_to_ai_requested(judge_unexecuted_items_raw, doc_ai_items)

                # Prefer judge totals over parsing AI text. Fall back to robust combinations before doc parsing.
                unmatched_count_from_list_len: int | None = len(judge_unexecuted_items) if judge_unexecuted_items else None

                # Prefer aligned judge lists when available (most interpretable and robust to splitting issues).
                ai_total_source: str | None = None
                if judge_matched_items or judge_unexecuted_items:
                    ai_total = len(judge_matched_items) + len(judge_unexecuted_items)
                    ai_total_source = "judge_list_len"
                elif judge_total_count is not None and judge_total_count > 0:
                    ai_total = judge_total_count
                    ai_total_source = "judge_total_count"
                elif judge_matched_count is not None and unmatched_count_from_list_len is not None:
                    ai_total = max(0, int(judge_matched_count) + int(unmatched_count_from_list_len))
                    ai_total_source = "judge_matched_count+unexec_len"
                else:
                    ai_total = doc_ai_total
                    ai_total_source = "doc_parse"

                matched_count_from_judge: int | None = None
                if judge_matched_count is not None and judge_matched_count >= 0:
                    if judge_total_count is None or (judge_total_count >= 0 and judge_matched_count <= judge_total_count):
                        matched_count_from_judge = int(judge_matched_count)

                matched_count_from_unexec_len: int | None = None
                if unmatched_count_from_list_len is not None and judge_total_count is not None:
                    matched_count_from_unexec_len = max(0, judge_total_count - unmatched_count_from_list_len)

                matched_count_final: int | None = None
                matched_count_source: str | None = None

                # Prefer aligned judge list length when available (keeps denominator tied to AI requests).
                if ai_total_source == "judge_list_len" and (judge_matched_items or judge_unexecuted_items):
                    matched_count_final = len(judge_matched_items)
                    matched_count_source = "judge_list_len"
                elif matched_count_from_judge is not None:
                    matched_count_final = matched_count_from_judge
                    matched_count_source = "judge_count"
                elif matched_count_from_unexec_len is not None:
                    matched_count_final = matched_count_from_unexec_len
                    matched_count_source = "unexecuted_list"
                elif ai_total > 0 and judge_match_score is not None:
                    # last resort: use match_score as proxy (cap)
                    matched_count_final = int(round(ai_total * max(0.0, min(1.0, judge_match_score))))
                    matched_count_source = "match_score_proxy"

                unmatched_count_final: int | None = None
                if unmatched_count_from_list_len is not None:
                    unmatched_count_final = int(unmatched_count_from_list_len)
                elif matched_count_final is not None:
                    unmatched_count_final = max(0, int(ai_total) - int(matched_count_final))

                judge_count_vs_unexec_conflict = (
                    matched_count_from_unexec_len is not None
                    and matched_count_from_judge is not None
                    and matched_count_from_unexec_len != matched_count_from_judge
                )

                # Evidence-driven: if AI requested checks in this round, treat as executed
                # (do not rely on column-B status which can drift).
                executed_round = ai_total > 0
                inefficient_by_zero = executed_round and (matched_count_final == 0)
                inefficient_by_score = executed_round and (judge_match_score is not None) and (judge_match_score < match_score_threshold)

                # Fallback extra detection using judge numeric count (rare); keep for audit.
                extras = _pick_extra_items(judge_matched_items_raw, doc_ai_items, judge_matched_count)

                # If judge lists are empty and all judge numeric fields are missing, surface as "未评测"
                # to avoid misleading empty lists in review sheets.
                missing_judge_lists = (
                    judge_row is None
                    or (
                        not judge_matched_items_raw
                        and not judge_unexecuted_items_raw
                        and judge_matched_count is None
                        and judge_total_count is None
                        and judge_match_score is None
                        and judge_reasonable_score is None
                        and judge_composite_score is None
                        and is_empty(judge_reason)
                    )
                )
                display_judge_status = "未评测" if (missing_judge_lists and has_ai_request) else status_judge
                display_matched_items = "未评测" if (missing_judge_lists and has_ai_request) else json_safe(judge_matched_items)
                display_unexecuted_items = "未评测" if (missing_judge_lists and has_ai_request) else json_safe(judge_unexecuted_items)

                rows.append(
                    {
                        "center": center,
                        "model": model,
                        "case_id": case_id,
                        "stage": cfg.stage,
                        "round_idx": round_idx,
                        "doc_status": status_doc,
                        "judge_status": display_judge_status,
                        "doc_request_col": req_col,
                        "doc_ai_requests_text": "" if is_empty(ai_text) else str(ai_text),
                        "ai_total_requested_count": ai_total,
                        "ai_total_source": ai_total_source,
                        "judge_matched_items_raw": display_matched_items,
                        "judge_unexecuted_items_raw": display_unexecuted_items,
                        "judge_matched_count_raw": judge_matched_count,
                        "judge_total_requested_count_raw": judge_total_count,
                        "judge_match_score_raw": judge_match_score,
                        "judge_reasonable_score_raw": judge_reasonable_score,
                        "judge_composite_score_raw": judge_composite_score,
                        "judge_reason_raw": judge_reason,
                        "matched_count_source": matched_count_source,
                        "unmatched_count_from_unexecuted_list": unmatched_count_from_list_len,
                        "unmatched_count_final": unmatched_count_final,
                        "judge_count_vs_unexec_conflict": judge_count_vs_unexec_conflict,
                        "matched_count_final": matched_count_final,
                        "inefficient_round_by_zero": inefficient_by_zero,
                        "inefficient_round_by_score": inefficient_by_score,
                        "judge_extra_matched_items_suspect": json_safe(extras_suspect or extras),
                        "ai_total_vs_judge_total_mismatch": (
                            (judge_total_count is not None) and (doc_ai_total != judge_total_count) and (doc_ai_total > 0)
                        ),
                    }
                )

    def emit_gate1_d2_suggest_rows() -> None:
        doc_df = loaded.doc_sheets["D1_Outpatient_Decision"]
        judge_df = loaded.judge_sheets["D1_Outpatient_Decision"]
        cid_col = doc_df.columns[0]
        case_ids = [str(x) for x in doc_df[cid_col].dropna().astype(str).unique()]

        doc_req_col = "医生决策_原始JSON_建议检查项目"
        judge_matched_col = "Gate1判官_原始JSON_检查匹配_匹配的检查项目"
        judge_unmatched_col = "Gate1判官_原始JSON_检查匹配_未匹配的检查项目"
        judge_match_degree_col = "Gate1判官_原始JSON_检查匹配_匹配度"
        judge_score_col = "Gate1判官_原始JSON_检查匹配_评分"

        for case_id in case_ids:
            doc_row = _get_row(doc_df, case_id)
            judge_row = _get_row(judge_df, case_id)
            status_doc = _get_status(doc_df, doc_row)
            status_judge = _get_status(judge_df, judge_row)

            if doc_row is None or doc_req_col not in doc_df.columns:
                continue
            ai_text = doc_row.get(doc_req_col)
            doc_ai_items = parse_check_list_cell(ai_text)

            judge_matched_items_raw = [] if judge_row is None else parse_list_cell(judge_row.get(judge_matched_col))
            judge_unmatched_items_raw = [] if judge_row is None else parse_list_cell(judge_row.get(judge_unmatched_col))
            match_degree = None if judge_row is None else safe_float(judge_row.get(judge_match_degree_col))
            score = None if judge_row is None else safe_float(judge_row.get(judge_score_col))

            doc_ai_total = len(doc_ai_items)

            # Align judge lists to the AI-requested checks (avoid counting fabricated extras).
            judge_matched_items, extras = _align_judge_items_to_ai_requested(judge_matched_items_raw, doc_ai_items)
            judge_unmatched_items, _ = _align_judge_items_to_ai_requested(judge_unmatched_items_raw, doc_ai_items)
            judge_total_from_lists: int | None = None
            if judge_matched_items or judge_unmatched_items:
                judge_total_from_lists = len(judge_matched_items) + len(judge_unmatched_items)
            if judge_total_from_lists is not None and judge_total_from_lists > 0:
                ai_total = judge_total_from_lists
                ai_total_source = "judge_list_len"
            else:
                ai_total = doc_ai_total
                ai_total_source = "doc_parse"

            matched_count_final: int | None = None
            matched_count_source: str | None = None
            if judge_total_from_lists is not None:
                matched_count_final = len(judge_matched_items)
                matched_count_source = "judge_list_len"
            elif ai_total > 0 and match_degree is not None:
                matched_count_final = int(round(ai_total * max(0.0, min(1.0, match_degree))))
                matched_count_source = "match_degree_proxy"
            else:
                matched_count_final = len(judge_matched_items) if judge_matched_items else None
                matched_count_source = "matched_list_len" if matched_count_final is not None else None

            unmatched_count_final: int | None = None
            if judge_total_from_lists is not None:
                unmatched_count_final = len(judge_unmatched_items)
            elif matched_count_final is not None:
                unmatched_count_final = max(0, ai_total - matched_count_final)

            rows.append(
                {
                    "center": center,
                    "model": model,
                    "case_id": case_id,
                    "stage": "D2_SuggestedFromD1Decision",
                    "round_idx": 0,
                    "doc_status": status_doc,
                    "judge_status": status_judge,
                    "doc_request_col": doc_req_col,
                    "doc_ai_requests_text": "" if is_empty(ai_text) else str(ai_text),
                    "ai_total_requested_count": ai_total,
                    "ai_total_source": ai_total_source,
                    "judge_matched_items_raw": json_safe(judge_matched_items),
                    "judge_unexecuted_items_raw": json_safe(judge_unmatched_items),
                    "judge_matched_count_raw": len(judge_matched_items) if judge_matched_items else None,
                    "judge_total_requested_count_raw": judge_total_from_lists,
                    "judge_match_score_raw": match_degree,
                    "judge_reasonable_score_raw": None,
                    "judge_composite_score_raw": score,
                    "judge_reason_raw": "",
                    "matched_count_source": matched_count_source,
                    "unmatched_count_from_unexecuted_list": len(judge_unmatched_items) if judge_unmatched_items else None,
                    "unmatched_count_final": unmatched_count_final,
                    "judge_count_vs_unexec_conflict": False,
                    "matched_count_final": matched_count_final,
                    "inefficient_round_by_zero": False,
                    "inefficient_round_by_score": False,
                    "judge_extra_matched_items_suspect": json_safe(extras),
                    "ai_total_vs_judge_total_mismatch": (
                        (judge_total_from_lists is not None) and (doc_ai_total != judge_total_from_lists) and (doc_ai_total > 0)
                    ),
                }
            )

    emit_loop_rows(d1_cfg)
    emit_gate1_d2_suggest_rows()
    emit_loop_rows(d2_cfg)

    return pd.DataFrame(rows)


def json_safe(items: list[str]) -> str:
    # Keep in a single cell for Excel/CSV readability.
    if not items:
        return "[]"
    escaped = [str(x).replace("\n", "\\n") for x in items]
    return "[" + ", ".join(f"\"{x}\"" for x in escaped) + "]"
