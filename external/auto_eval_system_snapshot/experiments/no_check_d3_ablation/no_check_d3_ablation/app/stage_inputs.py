from __future__ import annotations

from typing import Any

from ..config import prompts_ablation


def normalize_text(value: Any, default: str = "无") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "null"}:
        return default
    return text


def build_patient_description(patient: dict) -> str:
    parts = [
        f"年龄/性别: {normalize_text(patient.get('age'), '未知')}岁 {normalize_text(patient.get('gender'), '未知')}",
        f"基本信息: {normalize_text(patient.get('basic_info'))}",
        f"主诉: {normalize_text(patient.get('chief_complaint'))}",
        f"现病史: {normalize_text(patient.get('present_illness'))}",
        f"月经婚育史: {normalize_text(patient.get('menstrual_history'))}",
        f"既往史: {normalize_text(patient.get('past_history'))}",
        f"家族史: {normalize_text(patient.get('family_history'))}",
        f"体格检查: {normalize_text(patient.get('physical_exam'))}",
    ]
    return "\n".join(f"- {part}" for part in parts)


def build_outpatient_context(patient: dict) -> str:
    return "\n".join(
        [
            f"- 患者概况: {normalize_text(patient.get('basic_info'))}",
            f"- 患者描述: {build_patient_description(patient)}",
            f"- 民族: {normalize_text(patient.get('ethnicity'), '未知')}",
        ]
    )


def build_d1_prompts(patient: dict) -> tuple[str, str]:
    user_prompt = prompts_ablation.D1_USER_PROMPT_TEMPLATE.format(
        outpatient_context=build_outpatient_context(patient)
    )
    return prompts_ablation.D1_SYSTEM_PROMPT, user_prompt


def summarize_d1_result(d1_result: dict) -> str:
    diagnosis = normalize_text(d1_result.get("初步诊断"), default="")
    if not diagnosis:
        diagnosis = normalize_text(d1_result.get("初始诊断"))
    reasoning = normalize_text(d1_result.get("初始诊断思维"), default="")
    if not reasoning:
        reasoning = normalize_text(d1_result.get("诊断思维"), default="无")
    return "\n".join(
        [
            f"- 初步诊断: {diagnosis or '无'}",
            f"- 诊断思维: {reasoning}",
        ]
    )


def build_d2_prompts(patient: dict, d1_result: dict) -> tuple[str, str]:
    user_prompt = prompts_ablation.D2_USER_PROMPT_TEMPLATE.format(
        outpatient_summary=build_outpatient_context(patient),
        d1_summary=summarize_d1_result(d1_result),
    )
    return prompts_ablation.D2_SYSTEM_PROMPT, user_prompt


def build_d3_history(patient: dict, d1_result: dict, d2_result: dict) -> str:
    d1_diag = normalize_text(d1_result.get("初步诊断"), default="")
    if not d1_diag:
        d1_diag = normalize_text(d1_result.get("初始诊断"))
    d1_reasoning = normalize_text(d1_result.get("初始诊断思维"), default="")
    if not d1_reasoning:
        d1_reasoning = normalize_text(d1_result.get("诊断思维"), default="无")
    lines = [
        "### D1 门诊阶段",
        f"- 患者描述: {build_patient_description(patient)}",
        f"- 初步诊断: {d1_diag}",
        f"- 初步诊断思维: {d1_reasoning}",
        "",
        "### D2 入院阶段",
        f"- 修正诊断: {normalize_text(d2_result.get('修正诊断'))}",
        f"- 修正诊断思维: {normalize_text(d2_result.get('修正诊断思维'))}",
        f"- 初步治疗方案: {normalize_text(d2_result.get('初步治疗方案'))}",
        f"- 治疗方案思维: {normalize_text(d2_result.get('治疗方案思维'))}",
    ]
    return "\n".join(lines)


def build_d3_prompts(patient: dict, d1_result: dict, d2_result: dict) -> tuple[str, str]:
    user_prompt = prompts_ablation.D3_USER_PROMPT_TEMPLATE.format(
        full_history=build_d3_history(patient, d1_result, d2_result),
        actual_surgery_plan=normalize_text(patient.get("gt_surgery_plan")),
        surgery_findings_and_pathology=(
            f"术中所见: {normalize_text(patient.get('gt_surgery_findings'))}\n"
            f"病理结果: {normalize_text(patient.get('gt_pathology'))}"
        ),
    )
    return prompts_ablation.D3_SYSTEM_PROMPT, user_prompt


def build_all_gt_info(patient: dict) -> str:
    return (
        "【门诊阶段GT】\n"
        f"检查: {normalize_text(patient.get('gt_outpatient_checks'))}\n"
        "【入院阶段GT】\n"
        f"诊断: {normalize_text(patient.get('gt_admission_diagnosis'))}\n"
        f"检查: {normalize_text(patient.get('gt_admission_checks'))}\n"
        f"修正诊断: {normalize_text(patient.get('gt_revised_diagnosis'))}\n"
        f"手术方案: {normalize_text(patient.get('gt_surgery_plan'))}\n"
        "【手术阶段GT】\n"
        f"术中所见: {normalize_text(patient.get('gt_surgery_findings'))}\n"
        f"病理: {normalize_text(patient.get('gt_pathology'))}\n"
        f"最终诊断: {normalize_text(patient.get('gt_final_diagnosis'))}\n"
        f"术后治疗计划: {normalize_text(patient.get('gt_post_op_plan'))}"
    )


def extract_d1_diagnosis(result: dict) -> str:
    primary = normalize_text(result.get("初步诊断"), default="")
    if primary:
        return primary
    return normalize_text(result.get("初始诊断"))


def extract_d1_plan(result: dict) -> str:
    return "不适用"


def extract_d2_diagnosis(result: dict) -> str:
    return normalize_text(result.get("修正诊断"))


def extract_d2_plan(result: dict) -> str:
    return normalize_text(result.get("初步治疗方案"))


def extract_d3_diagnosis(result: dict) -> str:
    return normalize_text(result.get("最终诊断", {}).get("诊断名称"))


def extract_d3_plan(result: dict) -> str:
    return normalize_text(result.get("术后治疗方案", {}).get("方案详情"))
