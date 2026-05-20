# -*- coding: utf-8 -*-
import os
import json
import logging
from datetime import datetime
import threading
from openpyxl import load_workbook, Workbook
from typing import List, Dict, Set, Any

logger = logging.getLogger(__name__)

class CheckpointManager:
    def __init__(self, output_dir: str):
        self.checkpoint_file = os.path.join(output_dir, "checkpoint.json")
        self._ensure_dir(output_dir)

    def _ensure_dir(self, path):
        if not os.path.exists(path):
            os.makedirs(path)

    def load_completed_cases(self) -> Set[str]:
        if not os.path.exists(self.checkpoint_file):
            return set()
        try:
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data.get("completed_cases", []))
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return set()

    def mark_case_completed(self, case_id: str):
        completed = self.load_completed_cases()
        if case_id in completed:
            return
        
        completed.add(case_id)
        current_data = {
            "last_updated": datetime.now().isoformat(),
            "completed_cases": list(completed)
        }
        try:
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(current_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to update checkpoint: {e}")

    # Static lock registry for thread safety across instances
class EvaluationLogger:
    _file_locks = {}
    _registry_lock = threading.Lock()

    def __init__(self, output_dir="output", model_name="unknown", channel_config="default", center_name=None):
        self.output_dir = output_dir
        self.model_name = model_name
        self.channel_config = channel_config
        self.center_name = center_name
        
        # Excel File Path (Legacy / Merge Target)
        if center_name:
            self.excel_file = os.path.join(output_dir, f"evaluation_{model_name}_{center_name}.xlsx")
        else:
            self.excel_file = os.path.join(output_dir, f"evaluation_{model_name}.xlsx")
        
        # Single Excels Dir
        self.single_excels_dir = os.path.join(output_dir, "single_excels")
        if not os.path.exists(self.single_excels_dir):
            os.makedirs(self.single_excels_dir, exist_ok=True)
            
        self.abs_excel_path = os.path.abspath(self.excel_file)
        
        # JSONL Log Dir
        self.jsonl_dir = os.path.join(output_dir, "raw_traces")
        if not os.path.exists(self.jsonl_dir):
            os.makedirs(self.jsonl_dir, exist_ok=True)
            
        self.checkpoint_manager = CheckpointManager(output_dir)
        self.current_case_buffer = {}
        self.headers = self._define_headers()

    # _init_excel_file is no longer strictly needed for single mode, but kept for compatibility or merge target
    def _init_excel_file(self):
        pass

    def commit_case(self, status="Success"):
        """Save current case to a unique Excel file"""
        from openpyxl.styles import PatternFill
        try:
            base_info = {k: self.current_case_buffer.get(k) for k in ["CaseID", "Timestamp", "Model", "Center"]}
            current_case_id = base_info.get("CaseID")
            
            if not current_case_id:
                logger.error("Missing CaseID, cannot save Excel.")
                return

            # Create New Workbook for this Case
            wb = Workbook()
            default_ws = wb.active
            wb.remove(default_ws)
            
            error_fill = PatternFill(start_color="FFCCCC", end_color="FFCCCC", fill_type="solid") if status != "Success" else None

            for sheet_name, mapping in self.headers.items():
                ws = wb.create_sheet(sheet_name)
                # Header
                ws.append(list(mapping.values()))
                
                # Data
                sheet_data = self.current_case_buffer.get(sheet_name, {})
                row_values = []
                for internal_key in mapping.keys():
                    if internal_key in base_info:
                        row_values.append(base_info[internal_key])
                    else:
                        row_values.append(sheet_data.get(internal_key, None))
                
                ws.append(row_values)
                
                if error_fill:
                    target_row = ws.max_row
                    for col in range(1, len(row_values) + 1):
                        ws.cell(row=target_row, column=col).fill = error_fill
            
            # Save Single File
            save_path = os.path.join(self.single_excels_dir, f"{self.model_name}_{self.center_name}_{current_case_id}.xlsx")
            wb.save(save_path)
            
            # Update Checkpoint
            if status == "Success":
                self.checkpoint_manager.mark_case_completed(current_case_id)
                logger.info(f"Saved Single Excel: {save_path}")
            else:
                logger.warning(f"Saved ERROR Excel (Pink): {save_path}")
            
        except Exception as e:
            logger.error(f"Failed to save single Excel: {e}")

    def get_existing_cases(self):
        return self.checkpoint_manager.load_completed_cases()



    def _flatten_json(self, json_data: Dict, prefix: str = "") -> Dict:
        """Helper to flatten selected JSON fields for Excel"""
        flat = {}
        if not isinstance(json_data, dict):
            return flat
            
        # Common keys to extract
        target_keys = [
            "初步诊断列表", "建议检查项目", "初步诊断思维", "建议检查思维",
            "诊断前所需检查", "理由",
            "修正诊断", "修正诊断思维", "治疗方案", "治疗方案思维",
            "最终诊断", "最终诊断思维", "术后治疗方案", "术后治疗方案思维",
            "出院康复计划", "长期随访计划"
        ]
        
        for k, v in json_data.items():
            if k in target_keys:
                # If value is complex (dict/list), stringify it
                if isinstance(v, (dict, list)):
                    flat[f"{prefix}AI_{k}"] = json.dumps(v, ensure_ascii=False)
                else:
                    flat[f"{prefix}AI_{k}"] = str(v)
            
            # Special case for "置信度评估"
            if k == "置信度评估" and isinstance(v, dict):
                for ck, cv in v.items():
                    flat[f"{prefix}AI_Conf_{ck}"] = str(cv)
                    
        return flat

    def _define_headers(self):
        """定义6个Sheet的表头映射 (Internal Key -> Display Header)"""
        # Base Meta
        self.base_map = {
            "CaseID": "病例ID", "Timestamp": "时间戳", "Model": "模型", "Center": "中心"
        }
        
        # Helper to generate loop columns
        def match_judge_cols(prefix, zh_prefix):
            return {
                f"{prefix}AI_Request": f"{zh_prefix}AI请求",
                f"{prefix}Judge_Match_Count": f"{zh_prefix}匹配数量",
                f"{prefix}Judge_Total_Count": f"{zh_prefix}请求总数",
                f"{prefix}Judge_Reason": f"{zh_prefix}匹配理由",
                f"{prefix}Judge_Response": f"{zh_prefix}Judge反馈",
                f"{prefix}Judge_Warning": f"{zh_prefix}Judge警告",
                f"{prefix}Score_Match": f"{zh_prefix}匹配得分",
                f"{prefix}Score_Reasonable": f"{zh_prefix}合理得分",
                f"{prefix}Score_Overall": f"{zh_prefix}综合得分",
                f"{prefix}AI_Raw_JSON": f"{zh_prefix}原始请求JSON"
            }

        # Sheet 1: 门诊检查循环
        s1_map = self.base_map.copy()
        s1_map["Loop_Count"] = "循环次数"
        for i in range(1, 4):
            s1_map.update(match_judge_cols(f"Loop{i}_", f"第{i}轮_"))
            
        # Sheet 2: 门诊决策
        s2_map = self.base_map.copy()
        s2_map.update({
            "Status": "状态", "Context_Summary": "门诊前信息", "Loop_Count": "循环次数",
            "AI_Need_More_Checks": "需补充检查", "AI_Diagnosis_Info": "门诊信息汇总", 
            "AI_Preliminary_Diagnosis": "初步诊断", "AI_Suggested_Checks": "建议检查",
            "AI_Diagnosis_Reasoning": "诊断思维", "AI_Check_Reasoning": "检查思维",
            "AI_Conf_Diagnosis": "诊断置信度", "AI_Conf_Check": "检查置信度",
            "AI_Raw_JSON": "原始JSON", "GT_Outpatient_Checks": "GT门诊检查", 
            "GT_Admission_Diagnosis": "GT入院诊断",
            "Gate_Diagnosis_Match": "Gate诊断匹配", "Gate_Diagnosis_Reason": "Gate诊断理由",
            "Gate_Diagnosis_Score": "Gate诊断分", "Gate_Check_Match": "Gate检查匹配",
            "Gate_Check_Score": "Gate检查分", "Gate_Proceed": "Gate通过", "Gate_Overall_Score": "Gate综合分",
            "Gate_Raw_JSON": "Gate原始JSON",
            # Flattened Fields
            "AI_初步诊断列表": "AI初步诊断列表(JSON)", "AI_建议检查项目": "AI建议检查项目(JSON)",
            "AI_初步诊断思维": "AI初步诊断思维(JSON)", "AI_建议检查思维": "AI建议检查思维(JSON)",
            "AI_诊断前所需检查": "AI诊断前所需检查(JSON)", "AI_理由": "AI理由(JSON)",
            "AI_Conf_门诊检查方案置信度": "AI门诊检查置信度", "AI_Conf_诊断置信度": "AI诊断置信度", "AI_Conf_检查方案置信度": "AI检查方案置信度"
        })

        # Sheet 3: 入院检查循环
        s3_map = s1_map.copy() # Same structure
            
        # Sheet 4: 入院决策
        s4_map = self.base_map.copy()
        s4_map.update({
            "Context_Summary": "决策1历史上下文", "Loop_Count": "循环次数",
            "AI_Can_Diagnose": "能够确诊", "AI_History_Review": "诊疗经过回顾",
            "AI_Revised_Diagnosis": "修正诊断", "AI_Diagnosis_Reasoning": "修正诊断思维",
            "AI_Treatment_Plan": "初步治疗方案", "AI_Treatment_Reasoning": "治疗方案思维",
            "AI_PostOp_Summary": "术后信息汇总", "AI_Conf_Diagnosis": "诊断置信度",
            "AI_Conf_Treatment": "治疗置信度", "AI_Raw_JSON": "原始JSON",
            "GT_Revised_Diagnosis": "GT入院/修正诊断", "GT_Surgery_Plan": "GT手术方案",
            "Gate_Diagnosis_Match": "Gate诊断匹配", "Gate_Diagnosis_Reason": "Gate诊断理由",
            "Gate_Diagnosis_Score": "Gate诊断分", "Gate_Surgery_Match": "Gate手术匹配",
            "Gate_Surgery_Reason": "Gate手术理由", "Gate_Surgery_Feedback": "Gate手术反馈",
            "Gate_Surgery_Score": "Gate手术分", "Gate_Proceed": "Gate通过", "Gate_Overall_Score": "Gate综合分",
            "Gate_Raw_JSON": "Gate原始JSON",
            # Flattened Fields
            "AI_修正诊断": "AI修正诊断(JSON)", "AI_修正诊断思维": "AI修正诊断思维(JSON)",
            "AI_初步治疗方案": "AI治疗方案(JSON)", "AI_治疗方案思维": "AI治疗方案思维(JSON)",
            "AI_需要补充检查": "AI需补充检查(JSON)", "AI_Conf_治疗方案置信度": "AI治疗方案置信度"
        })
                               
        # Sheet 5: 手术决策
        s5_map = self.base_map.copy()
        s5_map.update({
            "AI_Final_Diagnosis": "最终诊断", "AI_Final_Thinking": "最终诊断思维",
            "AI_PostOp_Plan": "术后治疗方案", "AI_PostOp_Thinking": "术后方案思维",
            "AI_Info_Summary": "术后信息汇总", "AI_Medical_Review": "诊疗经过回顾", 
            "AI_Conf_Diagnosis": "诊断置信度",
            "AI_Conf_Plan": "方案置信度", "AI_Raw_JSON": "原始JSON",
            "GT_Final_Diagnosis": "GT最终诊断", "GT_PostOp_Plan": "GT术后方案",
            "Judge_Diagnosis_Match": "诊断匹配结论", "Judge_Diagnosis_Reason": "诊断匹配理由",
            "Judge_Diagnosis_Score": "诊断得分", "Judge_Plan_Match": "方案匹配结论",
            "Judge_Plan_Reason": "方案匹配理由", "Judge_Plan_Score": "方案得分",
            "Judge_Need_More_Info": "需更多信息", "Judge_Proceed": "是否通过", "Judge_Overall_Score": "综合得分",
            "Gate_Raw_JSON": "Gate原始JSON",
            # Flattened Fields
            "AI_最终诊断": "AI最终诊断(JSON)", "AI_最终诊断思维": "AI最终诊断思维(JSON)",
            "AI_术后治疗方案": "AI术后治疗方案(JSON)", "AI_术后治疗方案思维": "AI术后治疗方案思维(JSON)",
             "AI_Conf_最终诊断置信度": "AI最终诊断置信度", "AI_Conf_术后治疗方案置信度": "AI术后治疗方案置信度"
        })

        # Sheet 6: 出院康复
        s6_map = self.base_map.copy()
        s6_map.update({
            "AI_Rehab_Plan": "出院康复计划", "AI_Rehab_Thinking": "康复思维", "AI_Rehab_Basis": "康复依据",
            "AI_Followup_Need": "需常规随访", "AI_Followup_Plan": "长期随访计划", 
            "AI_Followup_Thinking": "随访思维", "AI_Followup_Basis": "随访依据",
            "AI_Info_Summary": "康复信息汇总", "AI_Medical_Review": "诊疗经过回顾",
            "AI_Conf_Rehab": "康复置信度", "AI_Conf_Followup": "随访置信度",
            "AI_Raw_JSON": "原始JSON", "GT_Patient_Wishes": "患者意愿", "GT_Rehab_Plan": "GT康复计划", 
            "GT_Followup_Plan": "GT随访计划",
            "Judge_Rehab_Eval": "康复评价", "Judge_Rehab_Reason": "康复理由", "Judge_Rehab_Score": "康复得分",
            "Judge_Followup_Eval": "随访评价", "Judge_Followup_Reason": "随访理由", "Judge_Followup_Score": "随访得分",
            "Judge_Overall_Feedback": "综合反馈", "Judge_Overall_Score": "综合得分",
            "Gate_Raw_JSON": "Gate原始JSON",
            # Flattened Fields
            "AI_出院康复计划": "AI出院康复计划(JSON)", "AI_长期随访计划": "AI长期随访计划(JSON)",
            "AI_Conf_康复计划置信度": "AI康复计划置信度", "AI_Conf_随访计划置信度": "AI随访计划置信度"
        })

        return {
            "门诊检查循环": s1_map,
            "门诊决策": s2_map,
            "入院检查循环": s3_map,
            "入院决策": s4_map,
            "手术决策": s5_map,
            "出院康复": s6_map
        }



    # ... (skipping log methods as they don't need changes)

    def start_case_capture(self, case_id: str, center: str):
        """Start capturing logs for a new case"""
        self.current_case_buffer = {
            "CaseID": case_id,
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Model": self.model_name,
            "Center": center
        }
        # Initialize JSONL file for this case
        # Update Filename Format: Model_Center_CaseID.jsonl (User Request)
        model = self.current_case_buffer.get("Model", "Unknown")
        center_f = self.current_case_buffer.get("Center", "Unknown")
        self.current_jsonl_path = os.path.join(self.jsonl_dir, f"{model}_{center_f}_{case_id}.jsonl")
        # Clear existing if any (re-run)
        with open(self.current_jsonl_path, 'w', encoding='utf-8') as f:
            pass
        logger.info(f"Started capture for Case {case_id} -> {self.current_jsonl_path}")

    def log_raw_trace(self, case_id: str, stage: str, loop: int, inputs: list, output: Any):
        """
        Log raw interaction to JSONL and Console
        """
        # Strip metadata from output for logging
        log_output = output
        if isinstance(output, dict):
            log_output = output.copy()
            if "_metadata" in log_output:
                del log_output["_metadata"]

        record = {
            "timestamp": datetime.now().isoformat(),
            "case_id": case_id,
            "stage": stage,
            "loop": loop,
            "inputs": inputs, # List of prompt messages or context strings
            "output": log_output
        }
        
        # 1. File Log
        # Check for logprobs in output (original output to check if it existed)
        if isinstance(output, dict) and "_logprobs" in output:
             record["logprobs_available"] = True
        
        try:
            with open(self.current_jsonl_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to write raw trace: {e}")
            
        # 2. Console Transparency (User Request)
        # Print a summarized version
        print(f"\n[TRACE] {stage} (Loop {loop}) | Case: {case_id}")
        if isinstance(log_output, dict):
            # Print keys or summary
            summary = {k: str(v)[:50] + "..." for k, v in log_output.items() if isinstance(v, str)}
            print(f"Output Summary: {json.dumps(summary, ensure_ascii=False)}")
        else:
            print(f"Output: {str(log_output)[:100]}...")

    def log_loop_data(self, sheet_name: str, loop_i: int, data: Dict):
        """Log data specific to a loop iteration (e.g. Loop1_AI_Request)"""
        if sheet_name not in self.current_case_buffer:
            self.current_case_buffer[sheet_name] = {}
            
        prefix = f"Loop{loop_i}_"
        for k, v in data.items():
            # Strip metadata from AI_Raw_JSON if present
            val = v
            if k == "AI_Raw_JSON" and isinstance(v, str):
                try:
                    loaded = json.loads(v)
                    if isinstance(loaded, dict) and "_metadata" in loaded:
                        del loaded["_metadata"]
                        val = json.dumps(loaded, ensure_ascii=False)
                except: pass

            internal_key = f"{prefix}{k}"
            self.current_case_buffer[sheet_name][internal_key] = val

    def log_data(self, sheet_name: str, data: Dict):
        """Log general data to a sheet"""
        current_data = data.copy() # Initialize current_data with the original data

        # Strip metadata from AI_Raw_JSON or Gate_Raw_JSON if present in data
        for key_json in ["AI_Raw_JSON", "Gate_Raw_JSON"]:
            if key_json in current_data and isinstance(current_data[key_json], str):
                try:
                    loaded = json.loads(current_data[key_json])
                    if isinstance(loaded, dict) and "_metadata" in loaded:
                        del loaded["_metadata"]
                        current_data[key_json] = json.dumps(loaded, ensure_ascii=False)
                except: pass

        # Try to parse AI_Raw_JSON to extract more fields if possible
        if "AI_Raw_JSON" in current_data:
            try:
                raw_json = json.loads(current_data["AI_Raw_JSON"])
                flat_data = self._flatten_json(raw_json)
                current_data.update(flat_data)
            except:
                pass
                
        # Update buffer
        if self.current_case_buffer.get(sheet_name) is None:
            self.current_case_buffer[sheet_name] = {}
        
        self.current_case_buffer[sheet_name].update(current_data)


