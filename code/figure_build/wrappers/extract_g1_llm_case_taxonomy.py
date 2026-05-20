"""基于 GT 原始病例调用 LLM 生成 G1 分类缓存（PALM-COEIN / ICD / 良恶性 / 方案分类）。

设计要点：
1) 一病例一次调用，输入含三阶段诊断 + 患者信息 + 四阶段计划文本，降低调用次数。
2) 结果持久化到 CSV/JSONL，按 input_hash 复用缓存，避免重复调用。
3) 失败时回退关键词规则，保证产物可继续用于绘图与 source data。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_VIZ = ROOT / "analysis_viz"
CENTER_DATA_DIR = ANALYSIS_VIZ / "data" / "raw" / "center_data"
OUT_DIR = ANALYSIS_VIZ / "data" / "derived" / "figdata" / "v2_subplots" / "G1_dataset"
OUT_CSV = OUT_DIR / "G1_llm_case_taxonomy_v1.csv"
OUT_JSONL = OUT_DIR / "G1_llm_case_taxonomy_v1.raw.jsonl"
OUT_PALM_LONG = OUT_DIR / "G1_llm_palm_stage_detail_v1.csv"
OUT_PLAN_LONG = OUT_DIR / "G1_llm_plan_stage_detail_v1.csv"
PROMPT_REF = ANALYSIS_VIZ / "figures" / "v2_subplots" / "G1_dataset" / "sys prompt.txt"

sys.path.insert(0, str(ROOT / "src"))
from llm_judge_metrics.llm_runner import (  # noqa: E402
    _chat_completions,
    _extract_first_json_object,
    load_channel_config,
)

PALM_INT_TO_LABEL = {
    1: "P-息肉",
    2: "A-腺肌症",
    3: "L-肌瘤",
    4: "M-恶性/增生",
    5: "C-凝血相关",
    6: "O-排卵障碍",
    7: "E-子宫内膜原因",
    8: "I-医源性",
    9: "N-未分类",
}

PLAN_INT_TO_LABEL = {
    1: "手术处置",
    2: "药物/内分泌治疗",
    3: "检查/监测",
    4: "康复/护理",
    5: "随访管理",
    6: "无/未提及",
    7: "其他",
}

PROMPT_VERSION = "g1-llm-taxonomy-v1"


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def _is_none_like_text(value: Any) -> bool:
    text = _safe_text(value)
    if text == "":
        return True
    normalized = re.sub(r"[\s|｜;；,，。.!！:：]+", "", text).lower()
    if normalized in {"无", "暂无", "未做", "未行", "未进行", "未检查", "未提供", "未记录"}:
        return True
    if normalized.startswith("无") and len(normalized) <= 4:
        return True
    return False


def _hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _classify_palm_by_keyword(text: str) -> str:
    low = text.lower()
    rules: list[tuple[str, list[str]]] = [
        (
            "M-恶性/增生",
            ["恶性", "癌", "癌前", "上皮内", "非典型增生", "重度不典型增生", "内膜增生", "高级别", "恶变", "肿瘤"],
        ),
        ("L-肌瘤", ["子宫肌瘤", "肌瘤", "平滑肌瘤"]),
        ("A-腺肌症", ["子宫腺肌症", "腺肌症"]),
        ("P-息肉", ["子宫内膜息肉", "宫颈息肉", "息肉"]),
        ("C-凝血相关", ["凝血", "coagul", "vwd", "血小板", "血液病", "止血"]),
        ("O-排卵障碍", ["排卵障碍", "无排卵", "pcos", "多囊", "卵巢功能"]),
        ("E-子宫内膜原因", ["子宫内膜炎", "内膜炎", "子宫内膜功能", "黄体功能不足", "月经失调"]),
        ("I-医源性", ["医源", "药物", "激素", "抗凝", "宫内节育器", "iud", "置环", "手术后"]),
    ]
    for label, words in rules:
        if any(word.lower() in low for word in words):
            return label
    return "N-未分类"


def _palm_label_to_int(label: str) -> int:
    for key, value in PALM_INT_TO_LABEL.items():
        if value == label:
            return key
    return 9


def _fallback_icd_code(final_diag: str, palm_label: str) -> tuple[str, str]:
    low = final_diag.lower()
    if "子宫内膜息肉" in final_diag or "宫颈息肉" in final_diag:
        return "N84.0", "Polyp of corpus uteri"
    if any(word in final_diag for word in ["子宫肌瘤", "平滑肌瘤"]):
        return "D25", "Leiomyoma of uterus"
    if "子宫腺肌症" in final_diag or "腺肌症" in final_diag:
        return "N80.0", "Endometriosis of uterus"
    if any(word in final_diag for word in ["恶性", "癌", "肉瘤"]):
        return "C55", "Malignant neoplasm of uterus, part unspecified"
    if "增生" in final_diag:
        return "N85.0", "Endometrial glandular hyperplasia"
    if "妊娠" in final_diag or "流产" in final_diag:
        return "O99.8", "Other specified diseases and conditions complicating pregnancy"
    if "炎" in final_diag or "感染" in final_diag:
        return "N71", "Inflammatory disease of uterus"
    if "凝血" in final_diag or "血小板" in final_diag:
        return "D68.9", "Coagulation defect, unspecified"
    if "排卵" in final_diag or "多囊" in final_diag:
        return "N97.0", "Female infertility associated with anovulation"
    if "医源" in final_diag or "药物" in final_diag or "激素" in final_diag:
        return "Y57.9", "Drug or medicament, unspecified"
    if palm_label == "M-恶性/增生":
        return "C55", "Malignant/Hyperplasia related"
    return "Z03.9", "Observation for suspected disease, unspecified"


def _fallback_plan_class(text: str, stage_name: str) -> int:
    if _is_none_like_text(text):
        return 6
    low = text.lower()
    if any(keyword in low for keyword in ["切除", "手术", "镜下", "宫腔镜", "腹腔镜", "刮宫", "缝合", "术中"]):
        return 1
    if any(keyword in low for keyword in ["孕激素", "激素", "药物", "用药", "止血", "抗炎", "抗生素", "内分泌"]):
        return 2
    if any(keyword in low for keyword in ["复查", "复评", "监测", "超声", "化验", "检查", "检验", "病理"]):
        return 3 if stage_name != "followup" else 5
    if any(keyword in low for keyword in ["康复", "护理", "运动", "营养", "宣教", "心理"]):
        return 4
    if any(keyword in low for keyword in ["随访", "门诊", "观察", "三月", "六月", "一年", "定期"]):
        return 5
    return 7


def _fallback_result(case: dict[str, Any], error: str) -> dict[str, Any]:
    d1_label = _classify_palm_by_keyword(case["d1_diag"])
    d2_label = _classify_palm_by_keyword(case["d2_diag"])
    d3_label = _classify_palm_by_keyword(case["d3_diag"])
    final_icd, final_icd_name = _fallback_icd_code(case["d3_diag"], d3_label)
    final_bm = "恶性" if d3_label == "M-恶性/增生" or final_icd.startswith("C") else "良性"
    if d3_label == "N-未分类" and final_icd.startswith("Z"):
        final_bm = "未分类"
    return {
        "d1_palm_coein_class": _palm_label_to_int(d1_label),
        "d2_palm_coein_class": _palm_label_to_int(d2_label),
        "d3_palm_coein_class": _palm_label_to_int(d3_label),
        "final_icd10_code": final_icd,
        "final_icd10_name": final_icd_name,
        "final_benign_malignant": final_bm,
        "surgery_plan_class": _fallback_plan_class(case["surgery_plan"], "surgery"),
        "postop_plan_class": _fallback_plan_class(case["postop_plan"], "postop"),
        "rehab_plan_class": _fallback_plan_class(case["rehab_plan"], "rehab"),
        "followup_plan_class": _fallback_plan_class(case["followup_plan"], "followup"),
        "_fallback_error": error,
    }


def _validate_llm_json(obj: dict[str, Any]) -> tuple[bool, str]:
    need_int = [
        "d1_palm_coein_class",
        "d2_palm_coein_class",
        "d3_palm_coein_class",
        "surgery_plan_class",
        "postop_plan_class",
        "rehab_plan_class",
        "followup_plan_class",
    ]
    for key in need_int:
        if key not in obj:
            return False, f"missing_{key}"
        try:
            value = int(obj[key])
        except Exception:
            return False, f"invalid_int_{key}"
        if "palm" in key and not (1 <= value <= 9):
            return False, f"out_of_range_{key}"
        if "plan" in key and not (1 <= value <= 7):
            return False, f"out_of_range_{key}"
    code = _safe_text(obj.get("final_icd10_code", ""))
    if code == "":
        return False, "missing_final_icd10_code"
    bm = _safe_text(obj.get("final_benign_malignant", ""))
    if bm not in {"良性", "恶性", "未分类"}:
        return False, "invalid_final_benign_malignant"
    return True, ""


def _build_system_prompt() -> str:
    ref_text = ""
    if PROMPT_REF.exists():
        ref_text = PROMPT_REF.read_text(encoding="utf-8", errors="ignore")
    return (
        "你是妇科临床分型与编码助手。请根据病例信息输出严格 JSON。\n"
        "分类任务：\n"
        "1) D1/D2/D3 三阶段 PALM-COEIN 分型（整数 1-9）：\n"
        "   1=P(息肉), 2=A(腺肌症), 3=L(肌瘤), 4=M(恶性/增生), 5=C(凝血相关),\n"
        "   6=O(排卵障碍), 7=E(子宫内膜原因), 8=I(医源性), 9=N(未分类/妊娠相关)。\n"
        "2) 最终诊断 ICD-10 编码（基于最终诊断）。\n"
        "3) 最终诊断良恶性：良性/恶性/未分类。\n"
        "4) 四阶段方案分类（整数 1-7）：\n"
        "   1=手术处置, 2=药物/内分泌治疗, 3=检查/监测, 4=康复/护理, 5=随访管理, 6=无/未提及, 7=其他。\n"
        "输出 JSON 仅含以下键：\n"
        "{\n"
        '  "d1_palm_coein_class": int,\n'
        '  "d2_palm_coein_class": int,\n'
        '  "d3_palm_coein_class": int,\n'
        '  "final_icd10_code": "string",\n'
        '  "final_icd10_name": "string",\n'
        '  "final_benign_malignant": "良性|恶性|未分类",\n'
        '  "surgery_plan_class": int,\n'
        '  "postop_plan_class": int,\n'
        '  "rehab_plan_class": int,\n'
        '  "followup_plan_class": int\n'
        "}\n"
        "不要输出额外解释。\n\n"
        "参考提示词（仅供术语口径一致）：\n"
        f"{ref_text[:3200]}"
    )


def _build_user_prompt(case: dict[str, Any]) -> str:
    payload = {
        "center": case["center"],
        "case_id": case["case_id"],
        "patient_info": {
            "basic_info": case["basic_info"],
            "chief_complaint": case["chief_complaint"],
            "present_illness": case["present_illness"],
            "past_history": case["past_history"],
            "menstrual_history": case["menstrual_history"],
            "family_history": case["family_history"],
            "physical_exam": case["physical_exam"],
        },
        "diagnosis_by_stage": {
            "D1_admission": case["d1_diag"],
            "D2_revised": case["d2_diag"],
            "D3_final": case["d3_diag"],
        },
        "plans": {
            "surgery_plan": case["surgery_plan"],
            "postop_plan": case["postop_plan"],
            "rehab_plan": case["rehab_plan"],
            "followup_plan": case["followup_plan"],
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _read_gt_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    if not CENTER_DATA_DIR.exists():
        raise FileNotFoundError(f"GT目录不存在: {CENTER_DATA_DIR}")
    for center_dir in sorted(CENTER_DATA_DIR.iterdir(), key=lambda item: item.name):
        if not center_dir.is_dir():
            continue
        gt_files = sorted((center_dir / "GT").glob("*.xlsx"))
        if not gt_files:
            continue
        gt_file = gt_files[0]
        frame = pd.read_excel(gt_file, sheet_name="Sheet1")
        if frame.empty:
            continue
        case_col = "CaseID" if "CaseID" in frame.columns else ("病例ID" if "病例ID" in frame.columns else "")
        if case_col == "":
            continue
        for _, row in frame.iterrows():
            case_id = _safe_text(row.get(case_col, ""))
            if case_id == "":
                continue
            cases.append(
                {
                    "center": center_dir.name,
                    "case_id": case_id,
                    "source_gt_path": str(gt_file.relative_to(ROOT)).replace("\\", "/"),
                    "source_gt_sheet": "Sheet1",
                    "basic_info": _safe_text(row.get("BasicInfo", "")),
                    "chief_complaint": _safe_text(row.get("ChiefComplaint", "")),
                    "present_illness": _safe_text(row.get("PresentIllness", "")),
                    "past_history": _safe_text(row.get("PastHistory", "")),
                    "menstrual_history": _safe_text(row.get("MenstrualHistory", "")),
                    "family_history": _safe_text(row.get("FamilyHistory", "")),
                    "physical_exam": _safe_text(row.get("PhysicalExam", "")),
                    "d1_diag": _safe_text(row.get("GT_Admission_Diagnosis", "")),
                    "d2_diag": _safe_text(row.get("GT_Revised_Diagnosis", "")),
                    "d3_diag": _safe_text(row.get("GT_Final_Diagnosis", "")),
                    "surgery_plan": _safe_text(row.get("GT_Surgery_Plan", "")),
                    "postop_plan": _safe_text(row.get("GT_PostOp_Plan", "")),
                    "rehab_plan": _safe_text(row.get("GT_Rehab_Plan", "")),
                    "followup_plan": _safe_text(row.get("GT_Followup_Plan", "")),
                }
            )
    return cases


def _load_existing_cache() -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    if not OUT_CSV.exists():
        return {}
    frame = pd.read_csv(OUT_CSV)
    if frame.empty:
        return {}
    cache: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for _, row in frame.iterrows():
        key = (
            _safe_text(row.get("center", "")),
            _safe_text(row.get("case_id", "")),
            _safe_text(row.get("input_hash", "")),
            _safe_text(row.get("prompt_version", "")),
            _safe_text(row.get("model", "")),
        )
        cache[key] = dict(row)
    return cache


def _is_http_429_error(error_text: str) -> bool:
    s = str(error_text or "")
    return ("429" in s) or ("Too Many Requests" in s)


def _call_case_llm(
    *,
    channel_cfg: Any,
    model_name: str,
    temperature: float,
    system_prompt: str,
    case: dict[str, Any],
    max_retries: int,
    max_429_retries: int,
) -> tuple[dict[str, Any], str, str]:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": _build_user_prompt(case)},
    ]
    retry = max(1, int(max_retries))
    retry_429 = max(0, int(max_429_retries))
    last_error = ""
    response_text = ""
    for attempt in range(1, retry + 1):
        try:
            _, response_text = _chat_completions(channel_cfg, model_name, messages, temperature)
            parsed, parse_error = _extract_first_json_object(response_text)
            if parsed is None:
                last_error = parse_error or "empty_json"
                raise ValueError(last_error)
            ok, err = _validate_llm_json(parsed)
            if not ok:
                last_error = err
                raise ValueError(err)
            return parsed, response_text, ""
        except Exception as exc:
            last_error = str(exc)
            can_retry = attempt < retry
            if not can_retry:
                continue
            if _is_http_429_error(last_error):
                if attempt <= retry_429:
                    # 429 使用更长退避，降低并发突发对网关的冲击
                    time.sleep(2.0 * attempt + 0.6)
                else:
                    # 达到429重试上限后不再重试
                    break
            else:
                time.sleep(1.2 * attempt)
    return {}, response_text, last_error or "llm_call_failed"


def main() -> None:
    parser = argparse.ArgumentParser(description="提取 G1 LLM 分类缓存（PALM/ICD/良恶性/方案连续性）。")
    parser.add_argument("--channel", default="gala_api", help="channels.yaml 中的 channel 名称")
    parser.add_argument("--model", default="gemini-2.5-pro", help="调用模型名称")
    parser.add_argument("--temperature", type=float, default=0.0, help="采样温度")
    parser.add_argument("--max-cases", type=int, default=0, help="仅处理前N个病例（0=全部）")
    parser.add_argument("--max-workers", type=int, default=6, help="并发线程数（默认6）")
    parser.add_argument("--max-retries", type=int, default=3, help="单病例最大重试次数（默认3）")
    parser.add_argument("--max-429-retries", type=int, default=3, help="HTTP429额外重试上限（默认3）")
    parser.add_argument("--force-refresh", action="store_true", help="忽略缓存，强制重算")
    parser.add_argument(
        "--retry-fallback-only",
        action="store_true",
        help="仅重跑缓存中 fallback/error 的病例（不影响成功缓存）",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = _read_gt_cases()
    if args.max_cases and args.max_cases > 0:
        cases = cases[: args.max_cases]
    if not cases:
        raise RuntimeError("未读取到 GT 病例")

    channel_cfg = load_channel_config(ROOT, args.channel)
    system_prompt = _build_system_prompt()
    cache = _load_existing_cache()
    rows_by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []
    total_cases = len(cases)

    def build_case_hash_payload(case_row: dict[str, Any]) -> dict[str, Any]:
        return {
            "center": case_row["center"],
            "case_id": case_row["case_id"],
            "d1_diag": case_row["d1_diag"],
            "d2_diag": case_row["d2_diag"],
            "d3_diag": case_row["d3_diag"],
            "basic_info": case_row["basic_info"],
            "chief_complaint": case_row["chief_complaint"],
            "present_illness": case_row["present_illness"],
            "past_history": case_row["past_history"],
            "menstrual_history": case_row["menstrual_history"],
            "family_history": case_row["family_history"],
            "physical_exam": case_row["physical_exam"],
            "surgery_plan": case_row["surgery_plan"],
            "postop_plan": case_row["postop_plan"],
            "rehab_plan": case_row["rehab_plan"],
            "followup_plan": case_row["followup_plan"],
        }

    for case in cases:
        input_hash = _hash_payload(build_case_hash_payload(case))
        key = (case["center"], case["case_id"], input_hash, PROMPT_VERSION, args.model)
        case_pack = {"case": case, "input_hash": input_hash, "key": key}
        if (not args.force_refresh) and key in cache:
            cached = cache[key].copy()
            cached_err = _safe_text(cached.get("error", ""))
            cached_fallback = int(pd.to_numeric(cached.get("fallback_used", 0), errors="coerce") or 0)
            if args.retry_fallback_only and (cached_fallback == 1 or cached_err != ""):
                pending.append(case_pack)
            else:
                cached["cache_hit"] = 1
                rows_by_key[key] = cached
        else:
            pending.append(case_pack)

    def normalize_row(
        *,
        case: dict[str, Any],
        input_hash: str,
        parsed: dict[str, Any],
        raw_text: str,
        error: str,
        fallback_used: int,
        cache_hit: int,
    ) -> dict[str, Any]:
        row = {
            "center": case["center"],
            "case_id": case["case_id"],
            "input_hash": input_hash,
            "prompt_version": PROMPT_VERSION,
            "channel": args.channel,
            "model": args.model,
            "cache_hit": cache_hit,
            "fallback_used": fallback_used,
            "error": error,
            "source_gt_path": case["source_gt_path"],
            "source_gt_sheet": case["source_gt_sheet"],
            "d1_diag": case["d1_diag"],
            "d2_diag": case["d2_diag"],
            "d3_diag": case["d3_diag"],
            "d1_palm_class": int(parsed.get("d1_palm_coein_class", 9)),
            "d2_palm_class": int(parsed.get("d2_palm_coein_class", 9)),
            "d3_palm_class": int(parsed.get("d3_palm_coein_class", 9)),
            "final_icd10_code": _safe_text(parsed.get("final_icd10_code", "")),
            "final_icd10_name": _safe_text(parsed.get("final_icd10_name", "")),
            "final_benign_malignant": _safe_text(parsed.get("final_benign_malignant", "未分类")) or "未分类",
            "surgery_plan_class": int(parsed.get("surgery_plan_class", 6)),
            "postop_plan_class": int(parsed.get("postop_plan_class", 6)),
            "rehab_plan_class": int(parsed.get("rehab_plan_class", 6)),
            "followup_plan_class": int(parsed.get("followup_plan_class", 6)),
            "raw_response": raw_text,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        row["d1_palm_label"] = PALM_INT_TO_LABEL.get(row["d1_palm_class"], "N-未分类")
        row["d2_palm_label"] = PALM_INT_TO_LABEL.get(row["d2_palm_class"], "N-未分类")
        row["d3_palm_label"] = PALM_INT_TO_LABEL.get(row["d3_palm_class"], "N-未分类")
        row["surgery_plan_label"] = PLAN_INT_TO_LABEL.get(row["surgery_plan_class"], "其他")
        row["postop_plan_label"] = PLAN_INT_TO_LABEL.get(row["postop_plan_class"], "其他")
        row["rehab_plan_label"] = PLAN_INT_TO_LABEL.get(row["rehab_plan_class"], "其他")
        row["followup_plan_label"] = PLAN_INT_TO_LABEL.get(row["followup_plan_class"], "其他")
        return row

    def save_rows_snapshot() -> None:
        if not rows_by_key:
            return
        frame = pd.DataFrame(rows_by_key.values())
        frame["case_id"] = frame["case_id"].astype(str)
        frame = frame.sort_values(["center", "case_id"], kind="mergesort").reset_index(drop=True)
        frame.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    def process_case(case_pack: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        case = case_pack["case"]
        input_hash = case_pack["input_hash"]
        parsed, raw_text, error = _call_case_llm(
            channel_cfg=channel_cfg,
            model_name=args.model,
            temperature=args.temperature,
            system_prompt=system_prompt,
            case=case,
            max_retries=args.max_retries,
            max_429_retries=args.max_429_retries,
        )
        fallback_used = 0
        if error:
            parsed = _fallback_result(case, error)
            fallback_used = 1
        row = normalize_row(
            case=case,
            input_hash=input_hash,
            parsed=parsed,
            raw_text=raw_text,
            error=error,
            fallback_used=fallback_used,
            cache_hit=0,
        )
        raw = {
            "center": case["center"],
            "case_id": case["case_id"],
            "input_hash": input_hash,
            "error": error,
            "fallback_used": fallback_used,
            "response": raw_text,
            "parsed": parsed,
        }
        return row, raw

    done_count = len(rows_by_key)
    print(f"[INFO] total={total_cases}, cache_hit={done_count}, pending={len(pending)}")
    flush_every = 12
    with OUT_JSONL.open("a", encoding="utf-8") as raw_writer:
        if pending:
            max_workers = max(1, int(args.max_workers))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {executor.submit(process_case, item): item for item in pending}
                for done_idx, future in enumerate(as_completed(future_map), start=1):
                    case_item = future_map[future]
                    case = case_item["case"]
                    key = case_item["key"]
                    try:
                        row, raw_item = future.result()
                    except Exception as exc:
                        err_text = f"worker_exception:{exc}"
                        parsed = _fallback_result(case, err_text)
                        row = normalize_row(
                            case=case,
                            input_hash=case_item["input_hash"],
                            parsed=parsed,
                            raw_text="",
                            error=err_text,
                            fallback_used=1,
                            cache_hit=0,
                        )
                        raw_item = {
                            "center": case["center"],
                            "case_id": case["case_id"],
                            "input_hash": case_item["input_hash"],
                            "error": err_text,
                            "fallback_used": 1,
                            "response": "",
                            "parsed": parsed,
                        }
                    rows_by_key[key] = row
                    done_count += 1
                    raw_writer.write(json.dumps(raw_item, ensure_ascii=False) + "\n")
                    if (done_idx % flush_every) == 0:
                        save_rows_snapshot()
                    print(
                        f"[{done_count}/{total_cases}] {case['center']} {case['case_id']} "
                        f"fallback={int(row.get('fallback_used', 0))}"
                    )
    save_rows_snapshot()

    frame = pd.DataFrame(rows_by_key.values())
    if frame.empty:
        raise RuntimeError("未生成任何分类结果")
    frame["case_id"] = frame["case_id"].astype(str)
    frame = frame.sort_values(["center", "case_id"], kind="mergesort").reset_index(drop=True)
    frame.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    palm_long = pd.concat(
        [
            frame[["center", "case_id", "d1_palm_class", "d1_palm_label", "source_gt_path"]]
            .rename(columns={"d1_palm_class": "palm_class", "d1_palm_label": "palm_label"})
            .assign(stage4="D1"),
            frame[["center", "case_id", "d2_palm_class", "d2_palm_label", "source_gt_path"]]
            .rename(columns={"d2_palm_class": "palm_class", "d2_palm_label": "palm_label"})
            .assign(stage4="D2"),
            frame[["center", "case_id", "d3_palm_class", "d3_palm_label", "source_gt_path"]]
            .rename(columns={"d3_palm_class": "palm_class", "d3_palm_label": "palm_label"})
            .assign(stage4="D3"),
        ],
        ignore_index=True,
    )
    palm_long["source_model"] = args.model
    palm_long["source_channel"] = args.channel
    palm_long.to_csv(OUT_PALM_LONG, index=False, encoding="utf-8-sig")

    plan_long = pd.concat(
        [
            frame[["center", "case_id", "surgery_plan_class", "surgery_plan_label", "source_gt_path"]]
            .rename(columns={"surgery_plan_class": "plan_class", "surgery_plan_label": "plan_label"})
            .assign(plan_stage="Surgery"),
            frame[["center", "case_id", "postop_plan_class", "postop_plan_label", "source_gt_path"]]
            .rename(columns={"postop_plan_class": "plan_class", "postop_plan_label": "plan_label"})
            .assign(plan_stage="PostOp"),
            frame[["center", "case_id", "rehab_plan_class", "rehab_plan_label", "source_gt_path"]]
            .rename(columns={"rehab_plan_class": "plan_class", "rehab_plan_label": "plan_label"})
            .assign(plan_stage="Rehab"),
            frame[["center", "case_id", "followup_plan_class", "followup_plan_label", "source_gt_path"]]
            .rename(columns={"followup_plan_class": "plan_class", "followup_plan_label": "plan_label"})
            .assign(plan_stage="Followup"),
        ],
        ignore_index=True,
    )
    plan_long["source_model"] = args.model
    plan_long["source_channel"] = args.channel
    plan_long.to_csv(OUT_PLAN_LONG, index=False, encoding="utf-8-sig")

    print(f"[DONE] case_taxonomy: {OUT_CSV}")
    print(f"[DONE] palm_stage_detail: {OUT_PALM_LONG}")
    print(f"[DONE] plan_stage_detail: {OUT_PLAN_LONG}")


if __name__ == "__main__":
    main()
