# -*- coding: utf-8 -*-
import logging
import json
from ..config import prompts_v2
from ..utils.channel_manager import get_channel_manager
from ..utils.json_parser import extract_json

logger = logging.getLogger(__name__)

class JudgeAgent:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.channel_manager = get_channel_manager()

    def evaluate_outpatient_checks(self, ai_requested: str, gt_actual: str, loop_count: int) -> dict:
        """门诊检查循环评估"""
        output = self._call_judge(
            system_prompt=prompts_v2.JUDGE_OUTPATIENT_CHECK_PROMPT.format(
                ai_requested_checks=ai_requested,
                gt_actual_checks=gt_actual,
                loop_count=loop_count
            ),
            stage_name="judge_outpatient_check"
        )
        return output

    def evaluate_admission_checks(self, ai_requested: str, gt_actual: str, loop_count: int) -> dict:
        """入院检查循环评估"""
        output = self._call_judge(
            system_prompt=prompts_v2.JUDGE_ADMISSION_CHECK_PROMPT.format(
                ai_requested_checks=ai_requested,
                gt_actual_checks=gt_actual,
                loop_count=loop_count
            ),
            stage_name="judge_admission_check"
        )
        return output

    def evaluate_decision1_gate(self, ai_diagnosis: str, gt_diagnosis: str, ai_checks: str, gt_checks: str) -> dict:
        """决策1 Gate评估"""
        output = self._call_judge(
            system_prompt=prompts_v2.JUDGE_DECISION1_GATE_PROMPT.format(
                ai_preliminary_diagnosis=ai_diagnosis,
                gt_admission_diagnosis=gt_diagnosis,
                ai_suggested_checks=ai_checks,
                gt_admission_checks=gt_checks
            ),
            stage_name="judge_decision1_gate"
        )
        return output
    
    def evaluate_decision2_gate(self, ai_revised: str, gt_revised: str, gt_admission: str, gt_final: str, ai_treatment: str, gt_surgery: str, gt_wishes: str = "无") -> dict:
        """决策2 Gate评估"""
        output = self._call_judge(
            system_prompt=prompts_v2.JUDGE_DECISION2_GATE_PROMPT.format(
                ai_revised_diagnosis=ai_revised,
                gt_revised_diagnosis=gt_revised,
                gt_admission_diagnosis=gt_admission,
                gt_final_diagnosis=gt_final,
                ai_treatment_plan=ai_treatment,
                gt_surgery_plan=gt_surgery,
                gt_patient_wishes=gt_wishes
            ),
            stage_name="judge_decision2_gate"
        )
        return output

    def evaluate_decision3_gate(self, ai_final: str, gt_final: str, ai_post_op: str, gt_post_op: str, gt_surgery_findings: str = "", gt_pathology: str = "", all_gt_info: str = "", gt_wishes: str = "无") -> dict:
        """决策3 Gate评估"""
        # Safety Check for Missing GT
        if not gt_final or str(gt_final).lower() in ["none", "null", "nan", "无"]:
            logger.warning("GT Final Diagnosis is missing for Decision 3. Triggering Need More Info.")
            return {
                "诊断匹配评估": {
                    "结论": "GT数据缺失", 
                    "理由": "系统检测到 Ground Truth 最终诊断为空。",
                    "评分": 0.0 # Placeholder
                },
                "治疗方案匹配评估": {
                    "结论": "GT数据缺失",
                    "理由": "无 GT 方案对比",
                    "评分": 0.0
                },
                "need_more_info": True,
                "more_info_reason": "Ground Truth 数据缺失，无法进行评估。",
                "是否继续评测": True
            }

        output = self._call_judge(
            system_prompt=prompts_v2.JUDGE_DECISION3_GATE_PROMPT.format(
                ai_final_diagnosis=ai_final,
                gt_final_diagnosis=gt_final,
                ai_post_op_plan=ai_post_op,
                gt_post_op_plan=gt_post_op,
                gt_surgery_findings=gt_surgery_findings,
                gt_pathology=gt_pathology,
                all_gt_info_d1_d3=all_gt_info,
                gt_patient_wishes=gt_wishes
            ),
            stage_name="judge_decision3_gate"
        )
        return output

    def evaluate_decision4_judge(self, ai_rehab: str, ai_followup: str, gt_rehab: str, gt_followup: str) -> dict:
        """决策4 Judge评估"""
        output = self._call_judge(
            system_prompt=prompts_v2.JUDGE_DECISION4_COMMON_PROMPT.format(
                ai_rehab_plan=ai_rehab,
                ai_followup_plan=ai_followup,
                gt_rehab_plan=gt_rehab,
                gt_followup_plan=gt_followup
            ),
            stage_name="judge_decision4_common"
        )
        return output

    def evaluate_reasonableness(self, patient_full_context: str, ai_output: str, gt_output: str) -> dict:
        """二次深度判断 (Reasonableness Check)"""
        output = self._call_judge(
            system_prompt=prompts_v2.JUDGE_REASONABLENESS_PROMPT.format(
                patient_full_context=patient_full_context,
                ai_output=ai_output,
                gt_output=gt_output
            ),
            stage_name="judge_reasonableness_check"
        )
        return output

    def generate_warning(self, loop_count: int, missing_tests_list: list, all_requested_list: list, stage: str = "outpatient") -> str:
        """
        根据循环次数生成警告文本
        Args:
            stage: 'outpatient' or 'admission'
        """
        missing_str = "、".join(missing_tests_list)
        all_str = "、".join(all_requested_list)
        
        if stage == "outpatient":
            if loop_count == 1:
                return prompts_v2.WARNING_LEVEL_1_TEMPLATE.format(missing_tests=missing_str)
            elif loop_count == 2:
                return prompts_v2.WARNING_LEVEL_2_TEMPLATE.format(missing_tests=missing_str)
            elif loop_count >= 3:
                return prompts_v2.WARNING_LEVEL_3_TEMPLATE.format(all_requested_tests=all_str)
        else: # admission
            if loop_count == 1:
                return prompts_v2.ADMISSION_WARNING_LEVEL_1_TEMPLATE.format(missing_tests=missing_str)
            elif loop_count == 2:
                return prompts_v2.ADMISSION_WARNING_LEVEL_2_TEMPLATE.format(missing_tests=missing_str)
            elif loop_count >= 3:
                return prompts_v2.ADMISSION_WARNING_LEVEL_3_TEMPLATE.format(all_requested_tests=all_str)
        
        return ""

    def _call_judge(self, system_prompt: str, stage_name: str) -> dict:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请开始评估并输出JSON。"} 
        ]
        
        logger.info(f"Judge Agent ({self.model_name}) evaluating in {stage_name}...")
        
        # Implement Retry Logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.channel_manager.call_with_fallback(
                    model_name=self.model_name,
                    messages=messages,
                    temperature=0.1, # Judge 需要低温
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content
                logger.info(f"DEBUG Judge Content (Attempt {attempt+1}): {content[:200]}...") # Log first 200 chars
                if not content:
                    logger.warning(f"Judge Agent returned empty content in {stage_name} (Attempt {attempt+1}/{max_retries})")
                    continue
                    
                decision_json = extract_json(content)
                
                if not decision_json:
                    logger.error(f"Judge Agent returned invalid JSON in {stage_name} (Attempt {attempt+1}/{max_retries}). Content: {content[:200]}")
                    continue
                
                logger.info(f"DEBUG JSON Parse Success. Keys: {list(decision_json.keys())}")
                        
                # Success
                # Post-process: Calculate scores (Refactoring: System calculates match rate)
                decision_json = self._calculate_scores(decision_json, stage_name)
                
                # Metadata injection for logging
                decision_json["_metadata"] = {
                    "system_prompt": system_prompt,
                    "user_prompt": messages[-1]["content"]
                }
                
                logger.info("Judge Success, returning result.")
                return decision_json
                    
            except Exception as e:
                import traceback
                logger.warning(f"Error calling Judge LLM in {stage_name} (Attempt {attempt+1}/{max_retries}): {e}\nTraceback:\n{traceback.format_exc()}")
                if attempt == max_retries - 1:
                    logger.error(f"Final Failure Traceback:\n{traceback.format_exc()}")
                    raise e
        
        # If all retries fail
        logger.error(f"Judge Agent failed after {max_retries} attempts in {stage_name}")
        return {"error": "Max Retries Exceeded", "是否继续评测": True} # Default to continue to avoid hard crash logic elsewhere

    def _calculate_scores(self, decision_json: dict, stage_name: str) -> dict:
        """
        System-side score calculation to avoid LLM math errors.
        """
        try:
            if stage_name in ["judge_outpatient_check", "judge_admission_check"]:
                # System-side calculation of match rate based on list lengths
                match_list = decision_json.get("匹配的检查项目", [])
                if isinstance(match_list, str): match_list = [] 
                
                missing_list = decision_json.get("AI建议但实际未执行的检查", [])
                if isinstance(missing_list, str): missing_list = []
                
                match_count = len(match_list)
                total_count = match_count + len(missing_list)
                
                if total_count > 0:
                    match_rate = match_count / total_count
                else:
                    match_rate = 1.0 # No requests made, assume compliant
                
                # Default reasonable score if prompt doesn't return it (removed from prompt, so default 1.0)
                reasonable_score = 1.0
                
                # Overall Score matches match_rate
                overall = match_rate 
                
                decision_json["评分"] = {
                    "检查匹配度": round(match_rate, 2),
                    "合理性评分": reasonable_score,
                    "综合评分": round(overall, 2)
                }
                # Inject calculated counts for logging transparency
                decision_json["匹配数量"] = match_count
                decision_json["总请求数量"] = total_count
                
            elif stage_name == "judge_decision1_gate":
                # Diagnosis
                diag_concl = decision_json.get("诊断匹配", {}).get("结论", "")
                diag_score = 1.0 if "匹配" in diag_concl and "不匹配" not in diag_concl else 0.0
                if "诊断匹配" not in decision_json: decision_json["诊断匹配"] = {}
                decision_json["诊断匹配"]["评分"] = diag_score
                
                # Check
                check_list = decision_json.get("检查匹配", {}).get("匹配的检查项目", [])
                if isinstance(check_list, str): check_list = []
                missing_list = decision_json.get("检查匹配", {}).get("未匹配的检查项目", [])
                if isinstance(missing_list, str): missing_list = []
                # Check
                check_list = decision_json.get("检查匹配", {}).get("匹配的检查项目", [])
                if isinstance(check_list, str): check_list = []
                missing_list = decision_json.get("检查匹配", {}).get("未匹配的检查项目", [])
                if isinstance(missing_list, str): missing_list = []
                
                check_match = len(check_list)
                check_total = check_match + len(missing_list)
                if check_total == 0: check_total = 1
                check_score = check_match / check_total
                
                if "检查匹配" not in decision_json: decision_json["检查匹配"] = {}
                decision_json["检查匹配"]["评分"] = round(check_score, 2)
                decision_json["检查匹配"]["匹配度"] = round(check_score, 2) # For log consistency
                
                overall = 0.6 * diag_score + 0.4 * check_score
                decision_json["综合评分"] = round(overall, 2)
                
            elif stage_name == "judge_decision2_gate":
                # Diagnosis
                diag_concl = decision_json.get("修正诊断匹配", {}).get("结论", "")
                diag_score = 0.0
                if "完全一致" in diag_concl: diag_score = 1.0
                elif "高度相似" in diag_concl: diag_score = 0.9
                elif "部分匹配" in diag_concl: diag_score = 0.6
                
                if "修正诊断匹配" not in decision_json: decision_json["修正诊断匹配"] = {}
                decision_json["修正诊断匹配"]["评分"] = diag_score
                
                # Surgery (Reference only)
                surg_concl = decision_json.get("手术方案匹配", {}).get("结论", "")
                surg_score = 0.0
                if "完全一致" in surg_concl: surg_score = 1.0
                elif "部分匹配" in surg_concl: surg_score = 0.6
                
                if "手术方案匹配" not in decision_json: decision_json["手术方案匹配"] = {}
                decision_json["手术方案匹配"]["评分"] = surg_score
                
                decision_json["综合评分"] = diag_score
                
            elif stage_name == "judge_decision3_gate":
                # Final Diagnosis
                diag_concl = decision_json.get("诊断匹配评估", {}).get("结论", "")
                diag_score = 0.0
                if "完全一致" in diag_concl: diag_score = 1.0
                elif "高度相似" in diag_concl: diag_score = 0.9
                elif "部分匹配" in diag_concl: diag_score = 0.6
                
                if "诊断匹配评估" not in decision_json: decision_json["诊断匹配评估"] = {}
                decision_json["诊断匹配评估"]["评分"] = diag_score
                
                # Post-op Plan
                plan_concl = decision_json.get("治疗方案匹配评估", {}).get("结论", "")
                plan_score = 0.0
                if "完全一致" in plan_concl: plan_score = 1.0
                elif "方案合理" in plan_concl: plan_score = 0.8
                elif "遗漏" in plan_concl: plan_score = 0.5
                
                if "治疗方案匹配评估" not in decision_json: decision_json["治疗方案匹配评估"] = {}
                decision_json["治疗方案匹配评估"]["评分"] = plan_score
                
                overall = 0.7 * diag_score + 0.3 * plan_score
                decision_json["综合评分"] = round(overall, 2)
            
            elif stage_name == "judge_decision4_common":
                # Rehab
                rehab_eval = decision_json.get("康复计划评估", {}).get("评价", "")
                rehab_score = 0.0
                if "优秀" in rehab_eval: rehab_score = 1.0
                elif "良好" in rehab_eval: rehab_score = 0.8
                elif "一般" in rehab_eval: rehab_score = 0.6
                elif "不足" in rehab_eval: rehab_score = 0.4
                
                if "康复计划评估" not in decision_json: decision_json["康复计划评估"] = {}
                decision_json["康复计划评估"]["评分"] = rehab_score
                
                # Followup
                followup_eval = decision_json.get("随访计划评估", {}).get("评价", "")
                followup_score = 0.0
                if "优秀" in followup_eval: followup_score = 1.0
                elif "良好" in followup_eval: followup_score = 0.8
                elif "一般" in followup_eval: followup_score = 0.6
                elif "不足" in followup_eval: followup_score = 0.4
                elif "过度" in followup_eval: followup_score = 0.5 # Penalty for overuse
                
                if "随访计划评估" not in decision_json: decision_json["随访计划评估"] = {}
                decision_json["随访计划评估"]["评分"] = followup_score
                
                overall = (rehab_score + followup_score) / 2
                decision_json["综合评分"] = round(overall, 2)
                
        except Exception as e:
            logger.error(f"Error calculating scores in {stage_name}: {e}")
            # Do not crash, just leave scores missing or partial
            pass
            
        return decision_json
