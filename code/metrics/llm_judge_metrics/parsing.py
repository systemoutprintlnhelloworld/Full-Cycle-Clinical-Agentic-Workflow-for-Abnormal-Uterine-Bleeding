from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    # pandas.NA / numpy.nan
    try:
        # Guard against listlike objects where pd.isna returns an array.
        if not isinstance(value, (list, tuple, dict, set)) and bool(pd.isna(value)):
            return True
    except Exception:
        pass
    s = str(value).strip()
    return s == "" or s.lower() in {"nan", "<na>"}


_SPLIT_RE = re.compile(r"[,\n\r\t，、;；]+")


def parse_list_cell(value: Any) -> list[str]:
    if is_empty(value):
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if not is_empty(x)]

    s = str(value).strip()
    if not s:
        return []
    if s in {"无", "无。", "无.", "None", "none"}:
        return []

    # JSON list
    if s.startswith("[") and s.endswith("]"):
        try:
            data = json.loads(s)
            if isinstance(data, list):
                return [str(x).strip() for x in data if not is_empty(x)]
        except Exception:
            pass
        # Python list repr
        try:
            data = ast.literal_eval(s)
            if isinstance(data, list):
                return [str(x).strip() for x in data if not is_empty(x)]
        except Exception:
            pass

    # Fallback split
    parts = [p.strip().strip("'\"") for p in _SPLIT_RE.split(s) if p and p.strip()]
    return [p for p in parts if p and p not in {"无", "None", "none"}]


def _split_outside_parens(s: str, seps: set[str]) -> list[str]:
    """
    Split string by separators only when NOT inside parentheses (both () and （）).
    This is primarily used for "检查列表" parsing, to avoid splitting items like:
    - 性激素六项（FSH、LH、E2、P、PRL、T）
    """
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in s:
        if ch in {"(", "（"}:
            depth += 1
        elif ch in {")", "）"}:
            depth = max(0, depth - 1)
        if depth == 0 and ch in seps:
            part = "".join(buf).strip()
            if part:
                out.append(part)
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def parse_check_list_cell(value: Any) -> list[str]:
    """
    Parse a check-item list cell conservatively.
    - Keep "、" inside parentheses
    - Split on common separators outside parentheses: newline, comma, semicolon, Chinese punctuation.
    """
    if is_empty(value):
        return []
    # Some extracted fields are boolean flags (e.g., "需要补充门诊检查": True/False).
    # They should never be treated as a check-item list.
    if isinstance(value, bool):
        return []
    # Defensive: numeric values (except NaN handled above) are not check lists.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if not is_empty(x)]

    s = str(value).strip()
    if not s:
        return []
    if s in {"无", "无。", "无.", "None", "none"}:
        return []

    # JSON / Python list repr (keep each item as-is; do NOT further split by punctuation)
    if s.startswith("[") and s.endswith("]"):
        try:
            data = json.loads(s)
            if isinstance(data, list):
                return [str(x).strip() for x in data if not is_empty(x)]
        except Exception:
            pass
        try:
            data = ast.literal_eval(s)
            if isinstance(data, list):
                return [str(x).strip() for x in data if not is_empty(x)]
        except Exception:
            pass

    parts = _split_outside_parens(s, seps={",", "，", ";", "；", "\n", "\r", "\t", "、"})
    cleaned: list[str] = []
    for p in parts:
        p2 = p.strip().strip("'\"").strip()
        if not p2 or p2 in {"无", "None", "none"}:
            continue
        cleaned.append(p2)
    return cleaned


def normalize_text(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_check_name(s: str) -> str:
    s = normalize_text(s)
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"[\"'“”‘’]", "", s)
    s = s.lower()
    s = re.sub(r"\s+", "", s)
    return s


@dataclass(frozen=True)
class GTCheckItem:
    name: str
    result_text: str
    raw_text: str


def parse_gt_checks(text: Any) -> list[GTCheckItem]:
    if is_empty(text):
        return []
    s = str(text).strip()
    if not s or s in {"无", "无。", "无.", "None", "none"}:
        return []

    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # Also split by semicolons commonly used in GT cells.
    s = re.sub(r"\s*[;；]\s*", "\n", s)
    raw_lines = [ln.strip() for ln in s.split("\n") if ln.strip()]

    items: list[GTCheckItem] = []
    for ln in raw_lines:
        ln_clean = re.sub(r"^\s*[\-\*•]\s*", "", ln)
        ln_clean = re.sub(r"^\s*\d+[\.\、]\s*", "", ln_clean)
        if not ln_clean:
            continue

        name = ln_clean
        result = ""
        # Common prefix in GT columns: "辅助检查:"; remove it to make names more informative.
        if ln_clean.startswith("辅助检查:") or ln_clean.startswith("辅助检查："):
            ln_clean = ln_clean.replace("辅助检查:", "", 1).replace("辅助检查：", "", 1).strip()

        if "：" in ln_clean:
            name, result = ln_clean.split("：", 1)
        elif ":" in ln_clean:
            name, result = ln_clean.split(":", 1)

        # If still looks like hierarchical tags (e.g., "实验室检查:血型：..."), prefer the second tag as name.
        if ("：" in result or ":" in result) and name in {"检查", "检验", "实验室检查", "影像学检查", "病理学检查", "内镜检查", "其他检查"}:
            r2 = result
            if "：" in r2:
                n2, rest2 = r2.split("：", 1)
                if n2.strip():
                    name = f"{name}/{n2.strip()}"
                    result = rest2.strip()
            elif ":" in r2:
                n2, rest2 = r2.split(":", 1)
                if n2.strip():
                    name = f"{name}/{n2.strip()}"
                    result = rest2.strip()

        name = name.strip()
        result = result.strip()

        if name in {"无", "none", "None"}:
            continue
        items.append(GTCheckItem(name=name, result_text=result, raw_text=ln_clean))

    return items


def is_gt_check_effective(item: GTCheckItem) -> bool:
    # “有效”按已拍板口径：GT中明确记录“已做且有结果”的检查
    if not item.name.strip():
        return False
    if is_empty(item.result_text):
        return False
    v = normalize_text(item.result_text)
    if v in {"无", "未做", "未检查", "none", "nan"}:
        return False
    return True


_WUHAN_DX_RE = re.compile(r"初步诊断\s*[:：]\s*(.+?)(?:\n|;|；|$)\s*鉴别诊断\s*[:：]\s*(.+)$", re.S)


@dataclass(frozen=True)
class DiagnosisText:
    primary: list[str]
    differential: list[str]
    raw: str


def parse_wuhan_dx(text: str) -> DiagnosisText:
    s = normalize_text(text)
    m = _WUHAN_DX_RE.search(text)
    if not m:
        # fallback: treat whole as primary
        return DiagnosisText(primary=[s] if s else [], differential=[], raw=text)
    primary_text = m.group(1).strip()
    differential_text = m.group(2).strip()
    primary = parse_list_cell(primary_text)
    differential = parse_list_cell(differential_text)
    return DiagnosisText(primary=primary, differential=differential, raw=text)
