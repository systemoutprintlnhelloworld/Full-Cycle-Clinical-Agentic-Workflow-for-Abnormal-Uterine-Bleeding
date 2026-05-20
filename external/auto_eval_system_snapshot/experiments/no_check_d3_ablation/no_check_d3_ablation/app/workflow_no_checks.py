from __future__ import annotations

import copy
import json
import logging
import time
from pathlib import Path

from ..adapters.agent_adapter import DoctorClient
from .judge_hooks import StageJudge
from .output_writer import CaseTraceWriter
from .stage_inputs import (
    build_d1_prompts,
    build_d2_prompts,
    build_d3_prompts,
    extract_d1_diagnosis,
    extract_d2_diagnosis,
    extract_d2_plan,
    extract_d3_diagnosis,
    extract_d3_plan,
)

logger = logging.getLogger(__name__)


class NoCheckAblationWorkflow:
    def __init__(self, model_name: str, judge_model: str, center_name: str, output_dir: Path):
        self.model_name = model_name
        self.judge_model = judge_model
        self.center_name = center_name
        self.output_dir = output_dir
        self.doctor = DoctorClient(model_name=model_name)
        self.stage_judge = StageJudge(judge_model=judge_model)

    def run_single_case(self, patient: dict, resume_state: dict | None = None) -> dict:
        patient = copy.deepcopy(patient)
        case_id = str(patient["case_id"])
        writer = CaseTraceWriter(self.output_dir, self.center_name, self.model_name, case_id)
        stage_payloads: dict[str, dict] = copy.deepcopy(resume_state or {})
        try:
            d1_state = stage_payloads.setdefault("D1", {})
            d1_result = d1_state.get("doctor") or self._run_doctor_stage("D1", *build_d1_prompts(patient), writer=writer)
            d1_judge = d1_state.get("judge") or self._run_judge_stage(
                stage_label="D1",
                stage_note="只基于初始门诊信息的首次判断",
                ai_diagnosis=extract_d1_diagnosis(d1_result),
                ai_plan="不适用",
                patient=patient,
                writer=writer,
                evaluate_plan=False,
            )
            d1_state["doctor"] = d1_result
            d1_state["judge"] = d1_judge

            d2_state = stage_payloads.setdefault("D2", {})
            d2_result = d2_state.get("doctor") or self._run_doctor_stage("D2", *build_d2_prompts(patient, d1_result), writer=writer)
            d2_judge = d2_state.get("judge") or self._run_judge_stage(
                stage_label="D2",
                stage_note="基于门诊与入院阶段上下文给出的修正判断",
                ai_diagnosis=extract_d2_diagnosis(d2_result),
                ai_plan=extract_d2_plan(d2_result),
                patient=patient,
                writer=writer,
            )
            d2_state["doctor"] = d2_result
            d2_state["judge"] = d2_judge

            d3_state = stage_payloads.setdefault("D3", {})
            d3_result = d3_state.get("doctor") or self._run_doctor_stage("D3", *build_d3_prompts(patient, d1_result, d2_result), writer=writer)
            d3_judge = d3_state.get("judge") or self._run_judge_stage(
                stage_label="D3",
                stage_note="默认直接提供手术方案、术中所见与病理后的判断",
                ai_diagnosis=extract_d3_diagnosis(d3_result),
                ai_plan=extract_d3_plan(d3_result),
                patient=patient,
                writer=writer,
            )
            d3_state["doctor"] = d3_result
            d3_state["judge"] = d3_judge

            summary = self._build_summary(case_id, stage_payloads)
            result = {
                "status": "success",
                "center": self.center_name,
                "model": self.model_name,
                "case_id": case_id,
                "judge_model": self.judge_model,
                "stages": stage_payloads,
                "summary": summary,
            }
            writer.save_case_result(result)
            return result
        except Exception as exc:
            logger.exception("病例执行失败，case_id=%s model=%s", case_id, self.model_name)
            writer.log_event("system", "error", {"message": str(exc)})
            error_result = {
                "status": "error",
                "center": self.center_name,
                "model": self.model_name,
                "case_id": case_id,
                "judge_model": self.judge_model,
                "error": str(exc),
                "stages": stage_payloads,
                "summary": {
                    "center": self.center_name,
                    "model": self.model_name,
                    "case_id": case_id,
                    "status": "error",
                    "error": str(exc),
                },
            }
            writer.save_case_result(error_result)
            raise

    def _run_doctor_stage(self, stage_label: str, system_prompt: str, user_prompt: str, writer: CaseTraceWriter) -> dict:
        writer.log_event(stage_label, "doctor_prompt", {"system_prompt": system_prompt, "user_prompt": user_prompt})
        last_error = None
        for attempt in range(1, 4):
            try:
                result = self.doctor.decide(stage_name=f"ablation_{stage_label}", system_prompt=system_prompt, user_prompt=user_prompt)
                if not result:
                    raise ValueError("Doctor 返回空结果")
                clean_result = self._strip_metadata(result)
                writer.log_event(stage_label, "doctor_output", {"attempt": attempt, "output": clean_result})
                return result
            except Exception as exc:
                last_error = exc
                writer.log_event(stage_label, "doctor_retry", {"attempt": attempt, "error": str(exc)})
                time.sleep(attempt)
        raise RuntimeError(f"{stage_label} doctor 调用失败: {last_error}")

    def _run_judge_stage(
        self,
        stage_label: str,
        stage_note: str,
        ai_diagnosis: str,
        ai_plan: str,
        patient: dict,
        writer: CaseTraceWriter,
        evaluate_plan: bool = True,
    ) -> dict:
        result = self.stage_judge.evaluate(
            stage_label,
            stage_note,
            ai_diagnosis,
            ai_plan,
            patient,
            evaluate_plan=evaluate_plan,
        )
        clean_result = self._strip_metadata(result)
        writer.log_event(
            stage_label,
            "judge_output",
            {
                "input_diagnosis": ai_diagnosis,
                "input_plan": ai_plan if evaluate_plan else "不适用",
                "output": clean_result,
            },
        )
        return result

    def _build_summary(self, case_id: str, stage_payloads: dict[str, dict]) -> dict:
        summary = {
            "center": self.center_name,
            "model": self.model_name,
            "judge_model": self.judge_model,
            "case_id": case_id,
            "status": "success",
        }
        for stage_name, payload in stage_payloads.items():
            judge_payload = payload["judge"]
            diag_section = judge_payload.get("诊断匹配评估", {})
            plan_section = judge_payload.get("治疗方案匹配评估", {})
            diag_score = diag_section.get("评分")
            summary[f"{stage_name.lower()}_diag_score"] = diag_score
            summary[f"{stage_name.lower()}_diag_distance"] = None if diag_score is None else round(1 - float(diag_score), 4)
            summary[f"{stage_name.lower()}_diag_conclusion"] = diag_section.get("结论")
            if stage_name == "D1":
                summary[f"{stage_name.lower()}_plan_score"] = None
                summary[f"{stage_name.lower()}_plan_conclusion"] = "不适用"
            else:
                summary[f"{stage_name.lower()}_plan_score"] = plan_section.get("评分") if isinstance(plan_section, dict) else None
                summary[f"{stage_name.lower()}_plan_conclusion"] = (
                    plan_section.get("结论") if isinstance(plan_section, dict) else None
                )
            summary[f"{stage_name.lower()}_overall_score"] = judge_payload.get("综合评分")
            summary[f"{stage_name.lower()}_need_more_info"] = judge_payload.get("need_more_info")
            summary[f"{stage_name.lower()}_more_info_retry"] = judge_payload.get("ablation_more_info_retry")
        return summary

    @staticmethod
    def _strip_metadata(payload: dict) -> dict:
        if not isinstance(payload, dict):
            return payload
        clean = json.loads(json.dumps(payload, ensure_ascii=False))
        clean.pop("_metadata", None)
        return clean
