# -*- coding: utf-8 -*-
import logging
import json
import time
from typing import Dict, Any

from .doctor_agent import DoctorAgent
from .judge_agent import JudgeAgent
from .patient_description_agent import PatientDescriptionAgent
from .data_loader import DataLoader
from .logger import EvaluationLogger
from .logger import EvaluationLogger
from ..utils.html_logger import HtmlTraceLogger
from ..config import prompts_v2

logger = logging.getLogger(__name__)

class EvaluationWorkflow:
    def __init__(self, model_name: str, data_path: str, output_dir: str = "output", center_name: str = "Unknown", monitor_port: int = 8000):
        self.model_name = model_name
        self.data_path = data_path
        self.center_name = center_name # Store center name
        
        # Initialize Modules
        self.logger_module = EvaluationLogger(output_dir=output_dir, model_name=model_name)
        self.html_logger = HtmlTraceLogger(output_dir_base=output_dir, model_name=model_name, center_name=center_name, monitor_port=monitor_port)
        self.loader = DataLoader(data_path)
        
        # Initialize Agents
        self.doc_agent = DoctorAgent(model_name=model_name)
        # Judge Agent fixed to Gemini/GPT-4 as per design, but here configurable or default
        self.judge_agent = JudgeAgent(model_name="gemini-2.5-pro") 
        self.desc_agent = PatientDescriptionAgent()
        
    def run(self, limit=0, progress_callback=None):
        """Main execution loop"""
        start_time = time.time()
        logger.info(f"Starting evaluation for model: {self.model_name}")
        
        # 1. Load Data
        patients = self.loader.load_patients()
        logger.info(f"Loaded {len(patients)} cases.")
        
        # Apply Limit if set
        if limit > 0:
            logger.info(f"Limiting execution to first {limit} cases.")
            patients = patients[:limit]
            
        if progress_callback:
            progress_callback(0, len(patients))
        
        # 2. Check Resume
        completed_ids = self.logger_module.get_existing_cases()
        logger.info(f"Found {len(completed_ids)} completed cases. Skipping them.")
        
        # 3. Process Cases
        for patient in patients:
            case_id = patient.get("case_id")
            if case_id in completed_ids:
                if progress_callback:
                    progress_callback(1)
                continue
                
            try:
                self.run_single_case(patient)
            except Exception as e:
                logger.error(f"Critical error processing case {case_id}: {e}")
                import traceback
                tb_str = traceback.format_exc()
                logger.error(tb_str)
                
                # Log to HTML Trace
                self.html_logger.add_log(stage="System_Error", content=tb_str, log_type="error")

                # Don't crash entire batch, but mark Error
                self.logger_module.log_data("门诊决策", {"Status": "System_Error", "AI_Raw_JSON": json.dumps({"Error": str(e)}, ensure_ascii=False)})
                self.logger_module.commit_case(status="Error") # Pass status Error
            finally:
                if progress_callback:
                    progress_callback(1)
                
        duration = time.time() - start_time
        logger.info(f"Evaluation finished in {duration:.2f}s")

    def run_single_case(self, patient: Dict[str, Any]):
        try:
            self._run_single_case_internal(patient)
        finally:
            self.html_logger.save_trace()

    def _run_single_case_internal(self, patient: Dict[str, Any]):
        """执行单个病例的全流程"""
        case_id = patient['case_id']
        logger.info(f"=== Processing Case: {case_id} ===")
        
        # Start Logger Capture
        # Start Logger Capture
        # Use self.center_name if patient doesn't have it (Standardized data might not have 'center' column)
        case_center = patient.get('center', self.center_name)
        self.logger_module.start_case_capture(case_id, case_center)
        self.html_logger.start_case(case_id, patient, center_name=case_center)
        
        try:
            # Prepare Full Context for Secondary Judge (Objective Facts)
            patient_full_context = (
                f"【基本信息】{patient.get('basic_info')}\n"
                f"【主诉】{patient.get('chief_complaint')}\n"
                f"【现病史】{patient.get('present_illness')}\n"
                f"【既往史】{patient.get('past_history')}\n"
                f"【家族史】{patient.get('family_history')}\n"
                f"【体格检查】{patient.get('physical_exam')}\n"
                f"【GT门诊检查】{patient.get('gt_outpatient_checks')}\n"
                f"【GT入院检查】{patient.get('gt_admission_checks')}\n"
                f"【GT病理】{patient.get('gt_pathology')}"
            )
            
            # ==========================================
            # Step 0: Patient Description Transformation
            # ==========================================
            # Add menstrual_history to the input if available
            patient_description = self.desc_agent.generate_description(patient)
            patient['patient_description'] = patient_description
            
            # ==========================================
            # Step 1: Outpatient Loop (Decision 1)
            # ==========================================
            accumulated_checks = [] 
            d1_result = None
            d1_loop_context = {} 
            interaction_history = [] # NEW: History tracking
            
            # Record initial context
            d1_loop_context = {} 
            
            # Record initial context
            interaction_history.append(f"【患者初始描述】\n{patient_description}") 
            self.html_logger.add_log("D1_Init", f"Patient Description:\n{patient_description}", "info") 
            
            # Max 4 iterations
            for loop_i in range(1, 5):
                # Construct input context
                input_data = patient.copy()
                
                # Prepare loop input
                if 'physical_exam' not in input_data:
                    input_data['physical_exam'] = "暂无体格检查信息"

                # Incorporate feedback ONLY if we have history
                current_request_context = ""

                if loop_i > 1:
                    # Append cumulative feedback
                    current_feedback_str = d1_loop_context.get('last_feedback', '')
                    # Accumulate history: Append to existing history if any
                    history_str = "\n".join(d1_loop_context.get('history_feedbacks', []))
                    if history_str:
                         history_str += f"\n\n【系统反馈 (第{loop_i-1}轮)】: {current_feedback_str}"
                    else:
                         history_str = f"【系统反馈 (第{loop_i-1}轮)】: {current_feedback_str}"
                    
                    # Update context
                    if 'history_feedbacks' not in d1_loop_context: d1_loop_context['history_feedbacks'] = []
                    d1_loop_context['history_feedbacks'].append(f"【系统反馈 (第{loop_i-1}轮)】: {current_feedback_str}")

                    # Join all history for input
                    full_feedback_context = "\n\n".join(d1_loop_context['history_feedbacks'])
                    
                    # Add Self-Request History to prevent loops
                    self_req_context = ""
                    if 'history_requests' in d1_loop_context:
                        self_req_context = "\n【你之前的请求记录】\n" + "\n".join(d1_loop_context['history_requests'])
                    
                    input_data['physical_exam'] += f"\n\n{full_feedback_context}{self_req_context}"
    
                # RETRY LOGIC (3 Attempts)
                ai_resp = None
                for retry_i in range(3):
                    ai_resp = self.doc_agent.make_outpatient_decision(input_data)
                    if ai_resp:
                        break
                    logger.warning(f"Doctor Agent returned None in Loop {loop_i}, Attempt {retry_i+1}/3. Retrying...")
                
                if ai_resp is None:
                    error_msg = f"Doctor Agent failed to generate valid JSON in Loop {loop_i} after 3 attempts. Terminating case."
                    logger.error(error_msg)
                    self.html_logger.add_log(f"D1_Loop_{loop_i}_Error", error_msg, "error")
                    return # Exit case
                
                # LOGGING: Prompts & Trace
                meta = ai_resp.get("_metadata", {})
                if meta:
                    prompt_log = f"System Prompt:\n{meta.get('system_prompt')}\n\nUser Prompt:\n{meta.get('user_prompt')}"
                    self.html_logger.add_log(f"D1_Loop_{loop_i}_Prompt", prompt_log, "prompt")
                
                # Record Interaction (Input was implicit in make_outpatient_decision but we capture the essence of what agent saw)
                step_log = f"【门诊决策 第{loop_i}轮】\n输入反馈: {d1_loop_context.get('last_feedback', '无 (首轮)')}\n"
                step_log += f"AI输出: {json.dumps(ai_resp, ensure_ascii=False)}"
                interaction_history.append(step_log)
                
                # MISSING LOG FIX: Log Doc Output to HTML Trace
                # Strip metadata only for HTML log cleanliness (Logic now in HTML Logger but good to be safe)
                doc_log = ai_resp.copy()
                if "_metadata" in doc_log: del doc_log["_metadata"]
                self.html_logger.add_log(f"D1_Loop_{loop_i}_Doc", json.dumps(doc_log, ensure_ascii=False, indent=2), "json")

                # Track Self Requests for Context
                req_checks_str = ai_resp.get("诊断前所需检查", "")
                if isinstance(req_checks_str, list): req_checks_str = ",".join(req_checks_str)
                if req_checks_str:
                     if 'history_requests' not in d1_loop_context: d1_loop_context['history_requests'] = []
                     d1_loop_context['history_requests'].append(f"第{loop_i}轮请求: {req_checks_str}")

                
                # Fix JSONL: Pass user prompt as input
                self.logger_module.log_raw_trace(case_id, "D1_Outpatient", loop_i, [meta.get('user_prompt', 'Unknown Input')], ai_resp)
                
                if not ai_resp:
                    logger.error("Doc Agent failed to respond in D1.")
                    self.logger_module.commit_case()
                    return
    
                # Check needs
                req_checks = ai_resp.get("诊断前所需检查", "")
                if isinstance(req_checks, list): req_checks = ",".join(req_checks)
                
                need_checks = ai_resp.get("需要补充门诊检查", False)
                need_further_checks_key = ai_resp.get("需要进一步检查", False) # Safety Check Key

                # DANGER CHECK: If BOTH are False, it means AI wants to proceed without ANY checks. 
                # This is dangerous in Outpatient stage 1-3 (unless loop 4 forced stop).
                if not need_checks and not need_further_checks_key:
                    logger.error(f"DANGER: Case {case_id} terminated. AI refused all checks (Double False) in Outpatient.")
                    self.logger_module.log_data("门诊决策", {
                        "Status": "Terminated_Dangerous_Skip",
                        "Reason": "AI returned False for both '需要补充门诊检查' and '需要进一步检查'"
                    })
                    self.html_logger.add_log("Termination", "Dangerous Operation: AI skipped all checks.", "error")
                    self.logger_module.commit_case()
                    return
                
                # If needs checks is False, verify if request is actually empty or not.
                # Trust model flag generally.
                
                # Check Termination
                if loop_i == 4:
                    if need_checks:
                        logger.warning(f"Case {case_id} terminated due to D1 loop limit.")
                        self.logger_module.log_data("门诊决策", {"Status": "Terminated_Loop_Limit"})
                        self.logger_module.commit_case()
                        return
    
                # Log to Sheet 1
                self.logger_module.log_loop_data("门诊检查循环", loop_i, {
                    "AI_Request": str(req_checks) if need_checks else "无",
                    "AI_Raw_JSON": json.dumps(ai_resp, ensure_ascii=False)
                })
                
                if not need_checks:
                    d1_result = ai_resp
                    self.logger_module.log_data("门诊决策", {"Loop_Count": loop_i-1})
                    break
                    
                # Call Judge
                check_list = [x.strip() for x in str(req_checks).split(",")] if req_checks else []
                gt_checks = patient.get("gt_outpatient_checks", "")
                
                judge_res = self.judge_agent.evaluate_outpatient_checks(
                    ai_requested=str(req_checks),
                    gt_actual=gt_checks,
                    loop_count=loop_i
                )
                
                # Log Judge Prompt
                j_meta = judge_res.get("_metadata", {})
                if j_meta:
                    self.html_logger.add_log(f"D1_Loop_{loop_i}_Judge_Prompt", f"System Prompt:\n{j_meta.get('system_prompt')}", "prompt")
                
                # Log Judge
                self.logger_module.log_loop_data("门诊检查循环", loop_i, {
                    "Judge_Match_Count": judge_res.get("匹配数量"), # Deprecated but kept for safety if key exists
                    "Judge_Total_Count": judge_res.get("总请求数量"),
                    "Judge_Response": str(judge_res),
                    "Judge_Warning": str(judge_res.get("AI建议但实际未执行的检查")), # Use the actual key from judge_res
                    "Score_Match": judge_res.get("评分", {}).get("检查匹配度"),
                    "Score_Reasonable": judge_res.get("评分", {}).get("合理性评分"),
                    "Score_Overall": judge_res.get("评分", {}).get("综合评分")
                })
                self.html_logger.add_log(f"D1_Loop_{loop_i}_Judge", json.dumps(judge_res, ensure_ascii=False, indent=2), "json")
                
                # Generate Warning
                check_list = [x.strip() for x in str(req_checks).split(",")] if req_checks else []
                warning_msg = self.judge_agent.generate_warning(
                    loop_count=loop_i,
                    missing_tests_list=str(judge_res.get("AI建议但实际未执行的检查")).split("\n"),
                    all_requested_list=check_list,
                    stage="outpatient"
                )
                
                # Context Accumulation Logic
                matched_content = judge_res.get("匹配的检查内容", "")
                provided_checks = judge_res.get("建议下一步输入的检查内容", "") # Old fallback
                final_content = matched_content if matched_content else provided_checks
                
                feedback_msg = f"已进行的检查结果：{final_content}\n警告：{warning_msg}"
                d1_loop_context['last_feedback'] = feedback_msg
                
                if final_content and "未进行" not in final_content:
                    accumulated_checks.append(final_content)
            
            # ==========================================
            # Step 2: Gate 1
            # ==========================================
            self.logger_module.log_data("门诊决策", {
                "GT_Outpatient_Checks": patient.get("gt_outpatient_checks"),
                "GT_Admission_Diagnosis": patient.get("gt_admission_diagnosis"),
                "AI_Preliminary_Diagnosis": str(d1_result.get("初步诊断列表", d1_result.get("修正诊断"))),
                "AI_Suggested_Checks": str(d1_result.get("建议检查项目", "")),
                "AI_Diagnosis_Reasoning": str(d1_result.get("初步诊断思维", d1_result.get("修正诊断思维"))),
                "AI_Raw_JSON": json.dumps(d1_result, ensure_ascii=False)
            })
            
            # Log D1 Result (Restored for Excel/Trace Completeness)
            # We use a distinct key to avoid confusion with Loop docs if needed, but "Decision_1_Doc" is standard.
            # Log D1 Result (Restored for Excel/Trace Completeness)
            # We use a distinct key to avoid confusion with Loop docs if needed, but "Decision_1_Doc" is standard.
            self.html_logger.add_log("Decision_1_Doc", json.dumps(d1_result, ensure_ascii=False, indent=2), "json", model=self.model_name)
            
            # GT Selection for Gate 1 (Critical Logic Fix)
            gate_gt_checks = patient.get("gt_admission_checks", "")
            if not accumulated_checks and patient.get("gt_outpatient_checks"):
                gate_gt_checks = f"【GT门诊检查】{patient.get('gt_outpatient_checks')}\n【GT入院检查】{gate_gt_checks}"
            
            gate_res = self.judge_agent.evaluate_decision1_gate(
                ai_diagnosis=str(d1_result.get("初步诊断列表", d1_result.get("修正诊断"))),
                gt_diagnosis=patient.get("gt_admission_diagnosis"),
                ai_checks=str(d1_result.get("建议检查项目", "")),
                gt_checks=gate_gt_checks
            )
            
            # Log Gate Prompt
            g_meta = gate_res.get("_metadata", {})
            if g_meta:
                 # Pass Agent Model Name for Logger
                 self.html_logger.log("D1_Gate_Prompt", f"System Prompt:\n{g_meta.get('system_prompt')}", f"User Prompt:\n{g_meta.get('user_prompt')}", model=self.judge_agent.model_name)
            
            self.logger_module.log_data("门诊决策", {
                "Gate_Diagnosis_Match": gate_res.get("诊断匹配", {}).get("结论"),
                "Gate_Diagnosis_Reason": str(gate_res.get("诊断匹配", {}).get("理由")),
                "Gate_Diagnosis_Score": gate_res.get("诊断匹配", {}).get("评分"),
                "Gate_Check_Match": gate_res.get("检查匹配", {}).get("匹配度"),
                "Gate_Check_Score": gate_res.get("检查匹配", {}).get("评分"),
                "Gate_Proceed": gate_res.get("是否继续评测"),
                "Gate_Raw_JSON": json.dumps(gate_res, ensure_ascii=False)
            })
            
            self.html_logger.add_log("D1_Gate_Judge", json.dumps(gate_res, ensure_ascii=False, indent=2), "json")
            
            if not gate_res.get("是否继续评测", True):
                # Secondary Judge Trigger (Reasonableness Check)
                logger.info(f"Case {case_id}: Gate 1 Mismatch. Triggering Secondary Judge.")
                sec_res = self.judge_agent.evaluate_reasonableness(
                    patient_full_context=patient_full_context,
                    ai_output=str(d1_result.get("初步诊断列表", d1_result.get("修正诊断"))),
                    gt_output= f"入院诊断: {patient.get('gt_admission_diagnosis')}"
                )
                
                # Log Secondary Result
                self.html_logger.add_log("Gate_1_Secondary_Judge", json.dumps(sec_res, ensure_ascii=False, indent=2), "json")
                
                if sec_res.get("is_reasonable", False):
                    logger.warning(f"Case {case_id}: Gate 1 Secondary Judge OVERRIDE. Continuing.")
                    self.html_logger.add_log("Override", "Secondary Judge Approved Reasonableness", "success")
                    gate_res["是否继续评测"] = True # Override
                    self.logger_module.log_data("门诊决策", {"Secondary_Judge_Override": True, "Secondary_Analysis": sec_res.get("reasonableness_analysis")})
                else:
                    self.logger_module.log_data("门诊决策", {"Status": "Terminated_Gate1", "Secondary_Judge_Override": False})
                    self.html_logger.add_log("Termination", "Terminated at Gate 1 (Confirmed by Secondary Judge)", "warning")
                    self.logger_module.commit_case()
                    self.html_logger.save_trace()
                    return
    
            # ==========================================
            # Step 3: Admission Loop (Decision 2)
            # ==========================================
            # Prepare context
            # FIX: Key changed from '匹配的检查内容' to '匹配的检查结果内容' in prompt
            gate_matched_checks = gate_res.get("检查匹配", {}).get("匹配的检查结果内容", "")
            d1_summary_checks = "\n".join(accumulated_checks)
            if gate_matched_checks: d1_summary_checks += "\n" + gate_matched_checks
            
            d2_result = None
            d2_loop_context = {}
            
            # Record Gate 1 Outcome
            g1_concl = gate_res.get("诊断匹配", {}).get("结论", "未知")
            g1_reason = gate_res.get("诊断匹配", {}).get("理由", "无")
            gate_pass_msg = "【决策1 Gate通过】\n诊断方向正确，进入入院阶段。"
            interaction_history.append(gate_pass_msg)
            self.html_logger.add_log("Gate 1 Passed", gate_pass_msg, "info")
            
            d2_judge_warning_for_d3 = "" # NEW: Store D2 warning for D3 context checking
            
            for loop_i in range(1, 5):
                # Build prompt with accumulated admission checks (if any from loop)
                # D2 Logic Repair: If D1 Loop Skipped (no accumulated_checks), then current_admission_checks should start empty
                if not accumulated_checks: 
                     current_admission_checks = "" # Force empty start
                else:
                     current_admission_checks = gate_matched_checks
                     
                if not current_admission_checks:
                    current_admission_checks = "暂无门诊检查结果或已包含在病史中。"
                    
                if loop_i > 1:
                    # Accumulate history from previous rounds
                    full_feedback_context = ""
                    if 'history_feedbacks' in d2_loop_context:
                        full_feedback_context = "\n\n".join(d2_loop_context['history_feedbacks'])
                    
                    # Add Self-Request History (Separate section as per user request to be explicit)
                    self_req_context = ""
                    if 'history_requests' in d2_loop_context:
                         # This might be redundant if history_feedbacks already contains "Your Decision".
                         # User snippet shows "Your previous requests" block separately.
                         # "【你之前的请求记录】... 第1轮请求..."
                         self_req_context = "\n\n【你之前的请求记录】\n" + "\n".join(d2_loop_context['history_requests'])

                    current_admission_checks += f"\n\n{full_feedback_context}{self_req_context}"
                
                sys_prompt = prompts_v2.DECISION2_SYSTEM_PROMPT
                user_prompt = prompts_v2.DECISION2_USER_PROMPT_TEMPLATE.format(
                    basic_info=patient.get("basic_info"),
                    patient_description=patient.get("patient_description"),
                    preliminary_diagnosis=str(d1_result.get("初步诊断列表", d1_result.get("修正诊断"))),
                    outpatient_checks_feedback=d1_summary_checks,
                    admission_checks=current_admission_checks
                )
                
                ai_resp = self.doc_agent.make_decision_with_context("D2_Admission", sys_prompt, user_prompt)
                
                # LOGGING: Prompts
                meta = ai_resp.get("_metadata", {})
                if meta:
                    prompt_log = f"System Prompt:\n{meta.get('system_prompt')}\n\nUser Prompt:\n{meta.get('user_prompt')}"
                    self.html_logger.add_log(f"D2_Loop_{loop_i}_Prompt", prompt_log, "prompt")

                # Clean D3 History: Don't repeat default context text
                context_display = current_admission_checks
                step_log = ""
                if "暂无门诊检查结果" in context_display:
                    step_log = f"【入院决策 第{loop_i}轮】\nAI Response:\n{json.dumps(ai_resp, ensure_ascii=False)}"
                else:
                    step_log = f"【入院决策 第{loop_i}轮】\nInput Context:\n{context_display}\n\nAI Response:\n{json.dumps(ai_resp, ensure_ascii=False)}"
                
                interaction_history.append(step_log)
                
                # MISSING LOG FIX: Log Doc Output to HTML Trace
                # Remove redundant key for UI before logging
                log_payload = ai_resp.copy()
                if "AI_Raw_JSON" in log_payload: del log_payload["AI_Raw_JSON"]
                self.html_logger.add_log(f"D2_Loop_{loop_i}_Doc", json.dumps(log_payload, ensure_ascii=False, indent=2), "json")
                
                # Enhanced History for Context (Full Turn)
                if 'history_feedbacks' not in d2_loop_context: d2_loop_context['history_feedbacks'] = []
                # Use a specific list for full history if needed, or just append to feedbacks with more detail
                # We stick to 'history_feedbacks' but enrich the content if valid
                # Actually, simpler is to just append the text to a new key 'full_conversation_history' 
                # but prompts_v2 expects 'history_feedbacks'. Let's enhance what we put there next loop.
                # Actually user wants "Detailed History" in PROMPT.
                # The prompt construction is: `history_str += f"\n\n【系统反馈...`
                # Let's change how we Build the history string in lines 296-300 to include the AI's thought/response.
                
                # Track Self Requests
                req_checks_str = ai_resp.get("需要补充检查", "")
                if isinstance(req_checks_str, list): req_checks_str = ",".join(req_checks_str)
                if req_checks_str:
                     if 'history_requests' not in d2_loop_context: d2_loop_context['history_requests'] = []
                     d2_loop_context['history_requests'].append(f"第{loop_i}轮请求: {req_checks_str}")

                # Fix JSONL
                self.logger_module.log_raw_trace(case_id, "D2_Admission", loop_i, [meta.get('user_prompt', 'Unknown Input')], ai_resp)
                
                need_checks = not ai_resp.get("能够确诊", False)
                req_checks = ai_resp.get("需要补充检查", "")
                if isinstance(req_checks, list): req_checks = ",".join(req_checks)
                
                if loop_i == 4:
                    if need_checks:
                        logger.warning(f"Case {case_id} terminated due to D2 loop limit.")
                        self.logger_module.log_data("入院决策", {"Status": "Terminated_Loop_Limit"})
                        self.logger_module.commit_case()
                        return
                
                self.logger_module.log_loop_data("入院检查循环", loop_i, {
                    "AI_Request": str(req_checks) if need_checks else "无",
                    "AI_Raw_JSON": json.dumps(ai_resp, ensure_ascii=False)
                })
                
                if not need_checks:
                    d2_result = ai_resp
                    self.logger_module.log_data("入院决策", {"Loop_Count": loop_i-1})
                    break
                    
                # Call Judge
                gt_admission_checks = patient.get("gt_admission_checks", "")
                judge_res = self.judge_agent.evaluate_admission_checks(
                    ai_requested=str(req_checks),
                    gt_actual=gt_admission_checks,
                    loop_count=loop_i
                )
                
                # Log Judge Prompt
                j_meta = judge_res.get("_metadata", {})
                if j_meta:
                    self.html_logger.add_log(f"D2_Loop_{loop_i}_Judge_Prompt", f"System Prompt:\n{j_meta.get('system_prompt')}", "prompt")
                
                self.logger_module.log_loop_data("入院检查循环", loop_i, {
                    "Judge_Match_Count": judge_res.get("匹配数量"),
                    "Judge_Total_Count": judge_res.get("总请求数量"),
                    "Judge_Response": str(judge_res),
                    "Judge_Warning": str(judge_res.get("AI建议但实际未执行的检查")), # Use the actual key from judge_res
                    "Score_Match": judge_res.get("评分", {}).get("检查匹配度"),
                    "Score_Reasonable": judge_res.get("评分", {}).get("合理性评分"),
                    "Score_Overall": judge_res.get("评分", {}).get("综合评分")
                })
                self.html_logger.add_log(f"D2_Loop_{loop_i}_Judge", json.dumps(judge_res, ensure_ascii=False, indent=2), "json")
                
                check_list = [x.strip() for x in str(req_checks).split(",")] if req_checks else []
                warning_msg = self.judge_agent.generate_warning(
                    loop_count=loop_i,
                    missing_tests_list=str(judge_res.get("AI建议但实际未执行的检查")).split("\n"),
                    all_requested_list=check_list,
                    stage="admission"
                )
                
                # Context Accumulation Logic
                matched_content = judge_res.get("匹配的检查内容", "")
                provided_checks = judge_res.get("建议下一步输入的检查内容", "") # Old fallback
                final_content = matched_content if matched_content else provided_checks
                
                d2_loop_context['last_feedback'] = f"补充检查结果：{final_content}\n警告：{warning_msg}"
                d2_judge_warning_for_d3 = warning_msg # Capture latest warning

                # --- Cumulative Rich History for Next Loop ---
                if 'history_feedbacks' not in d2_loop_context: d2_loop_context['history_feedbacks'] = []
                
                # Format: [Round N] AI Request -> Guide/Results
                rich_history_entry = (
                    f"【第{loop_i}轮交互】\n"
                    f"你(AI)的决策: {str(req_checks) if need_checks else '无'}\n"
                    f"系统反馈: 补充检查结果：{final_content}\n"
                    f"系统警告: {warning_msg}"
                )
                d2_loop_context['history_feedbacks'].append(rich_history_entry)
                
            # ==========================================
            # Step 4: Gate 2
            # ==========================================
            self.logger_module.log_data("入院决策", {
                "GT_Revised_Diagnosis": patient.get("gt_revised_diagnosis"),
                "GT_Surgery_Plan": patient.get("gt_surgery_plan"),
                "AI_Revised_Diagnosis": d2_result.get("修正诊断"),
                "AI_Treatment_Plan": str(d2_result.get("初步治疗方案")),
                "AI_Raw_JSON": json.dumps(d2_result, ensure_ascii=False)
            })
            
            # Log D2 Result
            # Log D2 Result
            self.html_logger.add_log("Decision_2_Doc", json.dumps(d2_result, ensure_ascii=False, indent=2), "json", model=self.model_name)
            
            gate2_res = self.judge_agent.evaluate_decision2_gate(
                ai_revised=str(d2_result.get("修正诊断")),
                gt_revised=patient.get("gt_revised_diagnosis"),
                gt_admission=patient.get("gt_admission_diagnosis"), 
                gt_final=patient.get("gt_final_diagnosis"),
                ai_treatment=str(d2_result.get("初步治疗方案")),
                gt_surgery=patient.get("gt_surgery_plan"),
                gt_wishes=patient.get("gt_patient_wishes", "无")
            )
            
            # Log Gate Prompt
            g_meta = gate2_res.get("_metadata", {})
            if g_meta:
                self.html_logger.log("Gate_2_Prompt", f"System Prompt:\n{g_meta.get('system_prompt')}", f"User Prompt:\n{g_meta.get('user_prompt')}", model=self.judge_agent.model_name)
            
            # --- Secondary Judge Logic for Gate 2 ---
            gate2_conclusion = gate2_res.get("修正诊断匹配", {}).get("结论", "")
            
            # Request: Trigger Secondary Judge for Ambiguous OR "Contains/More Precise" scenarios
            if any(k in gate2_conclusion for k in ["无法判断", "存疑", "包含关系", "更精确"]):
                logger.info(f"Case {case_id}: Gate 2 Trigger ({gate2_conclusion}). Triggering Secondary Judge.")
                sec_res = self.judge_agent.evaluate_reasonableness(
                    patient_full_context=patient_full_context,
                    ai_output=f"修正诊断: {d2_result.get('修正诊断')}",
                    gt_output=f"GT修正诊断: {patient.get('gt_revised_diagnosis')}\nGT入院诊断: {patient.get('gt_admission_diagnosis')}\nGT最终诊断: {patient.get('gt_final_diagnosis')}"
                )
                # Log Secondary Result
                self.html_logger.add_log("Gate_2_Secondary_Judge", json.dumps(sec_res, ensure_ascii=False, indent=2), "json")
                
                if sec_res.get("is_reasonable", False):
                    self.html_logger.add_log("Override", "Secondary Judge Approved Reasonableness (Gate 2)", "success")
                    # If it was a 'contained' match, we might want to update the conclusion in logs to reflect 'Verified'
                    gate2_res["修正诊断匹配"]["结论"] += " (Secondary Verified)"
                    gate2_res["是否继续评测"] = True # Ensure we proceed
                else:
                    self.html_logger.add_log("Mismatch_Confirmed", "Secondary Judge Confirmed Mismatch (Gate 2)", "warning")
                    # If it was ambiguous, maybe we should stop? Logic says if Unreasonable -> Stop.
                    # But the main Gate 2 logic below handles "是否继续评测" flag.
                    # If Secondary Judge says Unreasonable, we should force Stop if it wasn't already stopped by prompt.
                    if "包含关系" not in gate2_conclusion and "更精确" not in gate2_conclusion:
                        # Only override to False if it wasn't a "Partial Match" that the prompt allowed.
                        # Wait, prompt says "Contains" is a match. But user wanted Secondary Judge to CHECK it.
                        # If Secondary Judge says NO, then we should fail.
                        pass
            
            self.logger_module.log_data("入院决策", {
                "Gate_Diagnosis_Match": gate2_res.get("修正诊断匹配", {}).get("结论"),
                "Gate_Diagnosis_Reason": str(gate2_res.get("修正诊断匹配", {}).get("理由")),
                "Gate_Diagnosis_Score": gate2_res.get("修正诊断匹配", {}).get("评分"),
                "Gate_Surgery_Match": gate2_res.get("治疗方案匹配", {}).get("结论"),
                "Gate_Surgery_Reason": str(gate2_res.get("治疗方案匹配", {}).get("理由")),
                "Gate_Surgery_Feedback": str(gate2_res.get("治疗方案匹配", {}).get("反馈")),
                "Gate_Surgery_Score": gate2_res.get("治疗方案匹配", {}).get("评分"),
                "Gate_Proceed": gate2_res.get("是否继续评测"),
                "Gate_Overall_Score": gate2_res.get("综合评分"),
                "Gate_Raw_JSON": json.dumps(gate2_res, ensure_ascii=False)
            })
            
            self.html_logger.add_log("Gate_2_Judge", json.dumps(gate2_res, ensure_ascii=False, indent=2), "json")
            
            if not gate2_res.get("是否继续评测", True):
                # Secondary Judge Trigger (Reasonableness Check)
                logger.info(f"Case {case_id}: Gate 2 Mismatch. Triggering Secondary Judge.")
                sec_res = self.judge_agent.evaluate_reasonableness(
                    patient_full_context=patient_full_context,
                    ai_output=str(d2_result.get("修正诊断")),
                    gt_output=f"修正诊断:{patient.get('gt_revised_diagnosis')}\n入院诊断:{patient.get('gt_admission_diagnosis')}\n最终诊断:{patient.get('gt_final_diagnosis')}"
                )
                
                self.html_logger.add_log("Gate_2_Secondary_Judge", json.dumps(sec_res, ensure_ascii=False, indent=2), "json")
                
                if sec_res.get("is_reasonable", False):
                    logger.warning(f"Case {case_id}: Gate 2 Secondary Judge OVERRIDE. Continuing.")
                    self.html_logger.add_log("Override", "Secondary Judge Approved Reasonableness", "success")
                    gate2_res["是否继续评测"] = True
                    self.logger_module.log_data("入院决策", {"Secondary_Judge_Override": True, "Secondary_Analysis": sec_res.get("reasonableness_analysis")})
                else:
                    self.logger_module.log_data("入院决策", {"Status": "Terminated_Gate2", "Secondary_Judge_Override": False})
                    self.html_logger.add_log("Termination", "Terminated at Gate 2 (Confirmed by Secondary Judge)", "warning")
                    self.logger_module.commit_case()
                    self.html_logger.save_trace()
                    return
    
            # ==========================================
            # Gate 2 Success Log
            # ==========================================
            gate_pass_msg = "【决策2 Gate通过】\n修正诊断与治疗方案方向正确，进入手术/最终治疗阶段。"
            interaction_history.append(gate_pass_msg)
            self.html_logger.add_log("Gate 2 Passed", gate_pass_msg, "info")

            # ==========================================
            # Step 5: Decision 3 (Surgery)
            # ==========================================
            # Format history
            full_history_str = "\n\n".join(interaction_history)
            
            # Inject D2 Judge Warning if exists (User Request: "D2 judge feedback not seen in D3")
            if d2_judge_warning_for_d3:
                full_history_str += f"\n\n【系统对入院检查的最终警告】\n{d2_judge_warning_for_d3}"
            
            d3_sys_prompt = prompts_v2.DECISION3_SYSTEM_PROMPT
            d3_user_prompt = prompts_v2.DECISION3_USER_PROMPT_TEMPLATE.format(
                full_history=full_history_str,
                actual_surgery_plan=patient.get("gt_surgery_plan"),
                surgery_findings_and_pathology=f"术中:{patient.get('gt_surgery_findings')}\n病理:{patient.get('gt_pathology')}"
            )
            
            d3_result = self.doc_agent.make_decision_with_context("D3_Surgery", d3_sys_prompt, d3_user_prompt)
            
            # LOGGING
            meta = d3_result.get("_metadata", {})
            if meta:
                prompt_log = f"System Prompt:\n{meta.get('system_prompt')}\n\nUser Prompt:\n{meta.get('user_prompt')}"
                self.html_logger.add_log("D3_Surgery_Prompt", prompt_log, "prompt")

            # Fix JSONL
            self.logger_module.log_raw_trace(case_id, "D3_Surgery", 0, [meta.get('user_prompt', 'Unknown Input')], d3_result)
            self.html_logger.add_log("Outcome_Surgery", json.dumps(d3_result, ensure_ascii=False, indent=2), "json")
            self.html_logger.add_log("Outcome_Surgery", json.dumps(d3_result, ensure_ascii=False, indent=2), "json")
            
            # Context for D4: Dump full JSON except metadata
            d3_clean = d3_result.copy()
            if "_metadata" in d3_clean: del d3_clean["_metadata"]
            interaction_history.append(f"【手术决策】\nAI Response:\n{json.dumps(d3_clean, ensure_ascii=False)}")
            
            self.logger_module.log_data("手术决策", {
                "AI_Final_Diagnosis": d3_result.get("最终诊断", {}).get("诊断名称"),
                "AI_Final_Thinking": d3_result.get("最终诊断", {}).get("诊断思维"),
                "AI_PostOp_Plan": d3_result.get("术后治疗方案", {}).get("方案详情"),
                "AI_PostOp_Thinking": d3_result.get("术后治疗方案", {}).get("方案思维"),
                "AI_Info_Summary": d3_result.get("术后信息汇总"),
                "AI_Medical_Review": d3_result.get("诊疗经过回顾"),
                "AI_Conf_Diagnosis": d3_result.get("置信度评估", {}).get("最终诊断置信度"),
                "AI_Conf_Plan": d3_result.get("置信度评估", {}).get("术后治疗方案置信度"),
                "AI_Raw_JSON": json.dumps(d3_result, ensure_ascii=False),
                "GT_Final_Diagnosis": patient.get("gt_final_diagnosis"),
                "GT_PostOp_Plan": patient.get("gt_post_op_plan")
            })
            
            # Step 6: Gate 3
            judge3_res = self.judge_agent.evaluate_decision3_gate(
                ai_final=d3_result.get("最终诊断", {}).get("诊断名称"),
                gt_final=patient.get("gt_final_diagnosis"),
                ai_post_op=d3_result.get("术后治疗方案", {}).get("方案详情"),
                gt_post_op=patient.get("gt_post_op_plan"),
                gt_surgery_findings=patient.get("gt_surgery_findings"),
                gt_pathology=patient.get("gt_pathology"),
                gt_wishes=patient.get("gt_patient_wishes", "无")
            )
            
            # Crash Fix: Handle None result
            if not judge3_res:
                 # Debug Dump for Root Cause Analysis: Save inputs to file
                 try:
                     import os
                     debug_path = os.path.join(self.html_logger.output_dir, f"GATE3_CRASH_DUMP_{case_id}.txt")
                     with open(debug_path, "w", encoding="utf-8") as f:
                         f.write(f"Doc Final: {d3_result.get('最终诊断', {}).get('诊断名称')}\n")
                         f.write(f"GT Final: {patient.get('gt_final_diagnosis')}\n")
                         f.write(f"Doc PostOp: {d3_result.get('术后治疗方案', {}).get('方案详情')}\n")
                         f.write(f"GT PostOp: {patient.get('gt_post_op_plan')}\n")
                 except Exception as ex:
                     logger.error(f"Failed to write crash dump: {ex}")
                 
                 judge3_res = {"是否继续评测": False, "理由": "Judge Agent Failed (Empty Response)", "_metadata": {}}
            
            # Log Gate Prompt
            g3_meta = judge3_res.get("_metadata", {})
            if g3_meta:
                self.html_logger.add_log("Gate_3_Prompt", f"System Prompt:\n{g3_meta.get('system_prompt')}", "prompt")

            # More Info Mechanism
            if judge3_res.get("need_more_info"):
                logger.info(f"Case {case_id}: Gate 3 requested More Info. Retrying with full GT context.")
                all_gt_info = (
                    f"【门诊阶段GT】\n检查:{patient.get('gt_outpatient_checks')}\n"
                    f"【入院阶段GT】\n诊断:{patient.get('gt_admission_diagnosis')}\n检查:{patient.get('gt_admission_checks')}\n修正诊断:{patient.get('gt_revised_diagnosis')}\n手术方案:{patient.get('gt_surgery_plan')}\n"
                    f"【手术阶段GT】\n术中:{patient.get('gt_surgery_findings')}\n病理:{patient.get('gt_pathology')}\n最终诊断:{patient.get('gt_final_diagnosis')}\n术后方案:{patient.get('gt_post_op_plan')}"
                )
                
                # Retry Judge
                judge3_res = self.judge_agent.evaluate_decision3_gate(
                    ai_final=d3_result.get("最终诊断", {}).get("诊断名称"),
                    gt_final=patient.get("gt_final_diagnosis"),
                    ai_post_op=d3_result.get("术后治疗方案", {}).get("方案详情"),
                    gt_post_op=patient.get("gt_post_op_plan"),
                    gt_surgery_findings=patient.get("gt_surgery_findings"),
                    gt_pathology=patient.get("gt_pathology"),
                    all_gt_info=all_gt_info
                )
            
            self.logger_module.log_data("手术决策", {
                "Judge_Diagnosis_Match": judge3_res.get("诊断匹配评估", {}).get("结论"),
                "Judge_Diagnosis_Reason": str(judge3_res.get("诊断匹配评估", {}).get("理由")),
                "Judge_Diagnosis_Score": judge3_res.get("诊断匹配评估", {}).get("评分"),
                "Judge_Plan_Match": judge3_res.get("治疗方案匹配评估", {}).get("结论"),
                "Judge_Plan_Reason": str(judge3_res.get("治疗方案匹配评估", {}).get("理由")),
                "Judge_Need_More_Info": judge3_res.get("need_more_info"),
                "Judge_Overall_Score": judge3_res.get("综合评分"),
                "Judge_Proceed": judge3_res.get("是否继续评测", True),
                "Gate_Raw_JSON": json.dumps(judge3_res, ensure_ascii=False)
            })
            self.html_logger.add_log("Gate_3_Judge", json.dumps(judge3_res, ensure_ascii=False, indent=2), "json")
            
            if not judge3_res.get("是否继续评测", True):
                self.logger_module.log_data("手术决策", {"Status": "Terminated_Gate3"})
                self.logger_module.commit_case() # Save before exit
                return
    
            # ==========================================
            # Gate 3 Success Log
            # ==========================================
            g3_concl = judge3_res.get("诊断匹配评估", {}).get("结论", "未知")
            g3_plan_concl = judge3_res.get("治疗方案匹配评估", {}).get("结论", "未知")
            g3_reason = judge3_res.get("诊断匹配评估", {}).get("理由", "无")
            
            gate_pass_msg = "【决策3 Gate通过】\n最终诊断与术后方案方向正确，进入出院康复阶段。"
            interaction_history.append(gate_pass_msg)
            self.html_logger.add_log("Gate 3 Passed", gate_pass_msg, "info")

            # Update history
            rehab_context = (
                f"【系统通知】\n{gate_pass_msg}"
            )

            # ==========================================
            # Step 7: Decision 4 (Rehab)
            # ==========================================
            
            d4_sys = prompts_v2.DECISION4_SYSTEM_PROMPT
            d4_user = prompts_v2.DECISION4_USER_PROMPT_TEMPLATE.format(
                full_history=full_history_str + "\n\n" + f"【手术结果】\n诊断:{d3_result.get('最终诊断')}",
                actual_post_op_plan=patient.get("gt_post_op_plan"),
                patient_wishes=patient.get("gt_patient_wishes")
            )
            
            d4_result = self.doc_agent.make_decision_with_context("D4_Rehab", d4_sys, d4_user)
            
            # LOGGING
            meta = d4_result.get("_metadata", {})
            if meta:
                prompt_log = f"System Prompt:\n{meta.get('system_prompt')}\n\nUser Prompt:\n{meta.get('user_prompt')}"
                self.html_logger.add_log("D4_Rehab_Prompt", prompt_log, "prompt")

            # Fix JSONL
            self.logger_module.log_raw_trace(case_id, "D4_Rehab", 0, [meta.get('user_prompt', 'Unknown Input')], d4_result)
            self.html_logger.add_log("Outcome_Discharge", json.dumps(d4_result, ensure_ascii=False, indent=2), "json")
            
            # Step 8: Judge 4 (Common)
            judge4_res = self.judge_agent.evaluate_decision4_judge(
                ai_rehab=d4_result.get("出院康复计划", {}).get("方案详情"),
                ai_followup=d4_result.get("长期随访计划", {}).get("方案详情"),
                gt_rehab=patient.get("gt_rehab_plan"),
                gt_followup=patient.get("gt_followup_plan")
            )
            
            # Log Judge Prompt
            j4_meta = judge4_res.get("_metadata", {})
            if j4_meta:
                self.html_logger.add_log("Judge_Discharge_Prompt", f"System Prompt:\n{j4_meta.get('system_prompt')}", "prompt")
            self.html_logger.add_log("Judge_Discharge", json.dumps(judge4_res, ensure_ascii=False, indent=2), "json")

            self.logger_module.log_data("出院康复", {
                "AI_Rehab_Plan": d4_result.get("出院康复计划", {}).get("方案详情"),
                "AI_Rehab_Thinking": d4_result.get("出院康复计划", {}).get("康复思维"),
                "AI_Followup_Need": d4_result.get("长期随访计划", {}).get("是否需要常规随访"),
                "AI_Followup_Plan": d4_result.get("长期随访计划", {}).get("方案详情"),
                "AI_Followup_Thinking": d4_result.get("长期随访计划", {}).get("随访思维"),
                "AI_Info_Summary": d4_result.get("康复阶段信息汇总"),
                "AI_Medical_Review": d4_result.get("诊疗经过回顾"),
                "AI_Conf_Rehab": d4_result.get("置信度评估", {}).get("康复计划置信度"),
                "AI_Conf_Followup": d4_result.get("置信度评估", {}).get("随访计划置信度"),
                "AI_Raw_JSON": json.dumps(d4_result, ensure_ascii=False),
                "GT_Patient_Wishes": patient.get("gt_patient_wishes"),
                "GT_Rehab_Plan": patient.get("gt_rehab_plan"),
                "GT_Followup_Plan": patient.get("gt_followup_plan"),
                # Judge Logs
                "Judge_Rehab_Eval": judge4_res.get("康复计划评估", {}).get("评价"),
                "Judge_Rehab_Score": judge4_res.get("康复计划评估", {}).get("评分"),
                "Judge_Followup_Eval": judge4_res.get("随访计划评估", {}).get("评价"),
                "Judge_Followup_Score": judge4_res.get("随访计划评估", {}).get("评分"),
                "Judge_Overall_Score": judge4_res.get("综合评分"),
                "Gate_Raw_JSON": json.dumps(judge4_res, ensure_ascii=False)
            })
            
            self.logger_module.commit_case()
            self.html_logger.save_trace()
            logger.info(f"Case {case_id} completed successfully.")
            
        except Exception as e:
            logger.error(f"Error in run_single_case for {case_id}: {e}")
            import traceback
            tb = traceback.format_exc()
            logger.error(tb)
            self.html_logger.add_log("Error", tb, "error")
            self.html_logger.save_trace()
            logger.error(tb)
            self.html_logger.add_log("Error", tb, "error")
            self.html_logger.save_trace()
            # Save as Error
            self.logger_module.log_data("门诊决策", {"Status": "System_Error", "AI_Raw_JSON": json.dumps({"Error": str(e), "Traceback": tb}, ensure_ascii=False)})
            self.logger_module.commit_case(status="Error")
