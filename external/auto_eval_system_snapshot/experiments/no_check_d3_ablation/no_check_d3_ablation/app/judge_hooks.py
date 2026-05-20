from __future__ import annotations

from ..adapters.agent_adapter import JudgeClient
from ..config.prompts_ablation import (
    STAGE_DISTANCE_JUDGE_PROMPT_D1_DIAG_ONLY_TEMPLATE,
    STAGE_DISTANCE_JUDGE_PROMPT_TEMPLATE,
)
from .stage_inputs import build_all_gt_info, normalize_text


class StageJudge:
    def __init__(self, judge_model: str):
        self.client = JudgeClient(judge_model)

    def evaluate(
        self,
        stage_label: str,
        stage_note: str,
        ai_diagnosis: str,
        ai_plan: str,
        patient: dict,
        evaluate_plan: bool = True,
    ) -> dict:
        prompt = self._build_prompt(stage_label, stage_note, ai_diagnosis, ai_plan, patient, "", evaluate_plan)
        result = self.client.evaluate_with_d3_scoring(prompt)
        if result.get("need_more_info"):
            prompt = self._build_prompt(
                stage_label,
                stage_note,
                ai_diagnosis,
                ai_plan,
                patient,
                build_all_gt_info(patient),
                evaluate_plan,
            )
            result = self.client.evaluate_with_d3_scoring(prompt)
            result["ablation_more_info_retry"] = True
        else:
            result["ablation_more_info_retry"] = False
        if not evaluate_plan:
            result["治疗方案匹配评估"] = {
                "结论": "不适用",
                "理由": "D1 阶段不进行治疗方案匹配评估",
                "评分": None,
            }
            result["综合评分"] = result.get("诊断匹配评估", {}).get("评分")
            result.setdefault(
                "阶段说明",
                {
                    "内容": "D1 仅诊断评分",
                },
            )
        return result

    def _build_prompt(
        self,
        stage_label: str,
        stage_note: str,
        ai_diagnosis: str,
        ai_plan: str,
        patient: dict,
        all_gt_info: str,
        evaluate_plan: bool,
    ) -> str:
        if not evaluate_plan:
            return STAGE_DISTANCE_JUDGE_PROMPT_D1_DIAG_ONLY_TEMPLATE.format(
                stage_label=stage_label,
                stage_note=stage_note,
                ai_diagnosis=normalize_text(ai_diagnosis),
                gt_final_diagnosis=normalize_text(patient.get("gt_final_diagnosis")),
                all_gt_info_d1_d3=all_gt_info,
            )
        return STAGE_DISTANCE_JUDGE_PROMPT_TEMPLATE.format(
            stage_label=stage_label,
            stage_note=stage_note,
            ai_diagnosis=normalize_text(ai_diagnosis),
            gt_final_diagnosis=normalize_text(patient.get("gt_final_diagnosis")),
            ai_plan=normalize_text(ai_plan),
            gt_post_op_plan=normalize_text(patient.get("gt_post_op_plan")),
            gt_surgery_plan=normalize_text(patient.get("gt_surgery_plan")),
            gt_surgery_findings=normalize_text(patient.get("gt_surgery_findings")),
            gt_pathology=normalize_text(patient.get("gt_pathology")),
            gt_patient_wishes=normalize_text(patient.get("gt_patient_wishes")),
            all_gt_info_d1_d3=all_gt_info,
        )
