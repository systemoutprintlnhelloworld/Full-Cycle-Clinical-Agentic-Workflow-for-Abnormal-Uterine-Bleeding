import concurrent.futures
import time
import os
import threading
import json
from typing import List, Dict, Any
from auto_eval_system.modules.workflow import EvaluationWorkflow
from auto_eval_system.modules.data_loader import DataLoader
import logging

logger = logging.getLogger(__name__)

class BatchEvaluator:
    def __init__(self, centers: List[str], models: List[str], max_workers: int = 4, monitor_port: int = 8000):
        self.centers = centers
        self.models = models
        self.max_workers = max_workers
        self.monitor_port = monitor_port
        self.results = []
        self.lock = threading.Lock()

    def evaluate_single_case(self, center: str, model_name: str, patient_data: Dict[str, Any], output_dir: str):
        """
        Runs evaluation for a single case using a specific model and center configuration.
        """
        case_id = patient_data.get('case_id', 'Unknown')
        try:
            # Instantiate Workflow for this case (Lightweight if possible, but workflow is heavy)
            # Optimization: We could reuse workflow if shared, but thread safety of agents is key.
            # Agents (HTTP Clients) are generally thread safe if new instances.
            
            # Since data_path argument is required by __init__ but we already have patient_data,
            # we pass a dummy path or None if handled. 
            # Ideally Workflow should allow run_single_case without loading file.
            
            workflow = EvaluationWorkflow(
                center_name=center,
                model_name=model_name,
                output_dir=output_dir,
                data_path="DUMMY_PATH", # Not used since we call run_single_case direct
                monitor_port=self.monitor_port
            )
            
            # Execute
            workflow.run_single_case(patient_data)
            
            with self.lock:
                self.results.append({
                    "center": center,
                    "model": model_name,
                    "case": case_id,
                    "status": "success"
                })
            return True

        except Exception as e:
            logger.error(f"[{threading.current_thread().name}] Error: {center} - {model_name} - {case_id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            with self.lock:
                self.results.append({
                    "center": center,
                    "model": model_name,
                    "case": case_id,
                    "status": "error",
                    "error": str(e)
                })
            return False

    def run(self, limit: int = 0, progress_callback=None):
        """
        Main entry point to run the batch evaluation.
        limit: Max cases PER (Center, Model) pair. (Consistent with Legacy behavior)
        """
        tasks = []
        
        # 1. Discover Cases & Prepare Tasks
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for center in self.centers:
                # Handle -v2 suffix for data loading (User Request for Output Isolation)
                data_center_name = center
                if center.endswith("-v2"):
                    data_center_name = center[:-3]
                    logger.info(f"Center alias '{center}' detected. Using data from '{data_center_name}'")
                
                # Load Cases using DataLoader
                # Logic to find standardized excel for center
                # We reuse the logic from main.py or infer
                
                # Check for standardized file first
                excel_path = f"data/standardized_{data_center_name.lower()}.xlsx"
                
                # Special Hook for Wuhan Modified Data (User Request)
                # Use a distinct center name "Wuhan_Fixed" to avoid overwriting "Wuhan" outputs
                # Map Wuhan_Fixed-v2 logic as well if needed
                if data_center_name.lower() == "wuhan_fixed":
                    modified_path = r"data/standardized_wuhan - 移动信息.xlsx"
                    if os.path.exists(modified_path):
                        logger.info(f"Using Modified Wuhan Data for 'Wuhan_Fixed': {modified_path}")
                        excel_path = modified_path
                    else:
                        logger.error(f"Wuhan_Fixed requested but file not found: {modified_path}")

                if not os.path.exists(excel_path):
                     # Fallback to recursively finding
                     # For now, let's assume standardized path exists or error
                     # Or try raw path
                     raw_path = os.path.join("data", "raw", data_center_name)
                     if os.path.exists(raw_path):
                         excel_path = raw_path
                     else:
                         excel_path = os.path.join("data", data_center_name)
                
                logger.info(f"Loading cases for Center {center} (Data: {data_center_name}) from {excel_path}")
                try:
                    loader = DataLoader(excel_path)
                    all_patients = loader.load_patients()
                    
                    # Apply Limit PER CENTER (or per model-center pair)
                    # If limit is applied here, it applies to all models for this center
                    if limit > 0:
                        all_patients = all_patients[:limit]
                        
                    for model in self.models:
                        # Prepare Output Dir
                        output_dir = os.path.join("output", center, model)
                        if not os.path.exists(output_dir):
                            os.makedirs(output_dir, exist_ok=True)
                        
                        # Load Excel to check completion status
                        completed_cases = set()
                        # Load Excel to check completion status
                        completed_cases = set()
                        # Try Standardized Name first (produced by rescue_excel_v3)
                        excel_path = os.path.join(output_dir, f"Evaluation_Summary_{model}_CN.xlsx")
                        if not os.path.exists(excel_path):
                             # Fallback to legacy name
                             excel_path = os.path.join(output_dir, f"{model}_{center}_results.xlsx")
                        
                        if os.path.exists(excel_path):
                            try:
                                df_res = pd.read_excel(excel_path)
                                if "CaseID" in df_res.columns:
                                    completed_cases.update(set(df_res["CaseID"].astype(str).tolist()))
                                elif "病例ID" in df_res.columns:
                                    completed_cases.update(set(df_res["病例ID"].astype(str).tolist()))
                            except:
                                pass
                        
                        # Fix: Also read checkpoint.json for robustness (e.g. grok-4)
                        json_ckpt = os.path.join(output_dir, "checkpoint.json")
                        if os.path.exists(json_ckpt):
                            try:
                                with open(json_ckpt, 'r', encoding='utf-8') as f:
                                    data = json.load(f)
                                    if "completed_cases" in data:
                                        completed_cases.update(set([str(c) for c in data["completed_cases"]]))
                            except:
                                pass

                        for patient in all_patients:
                            case_id = str(patient.get("case_id"))
                            
                            # CHECKPOINT: Skip if in Excel OR if JSONL trace exists (Dual Checkpoint)
                            # Handle Wuhan_Fixed naming: if center starts with Wuhan, files are named with Wuhan
                            fname_center = center
                            if center.startswith("Wuhan"): fname_center = "Wuhan"
                            elif center.startswith("Foshan"): fname_center = "Foshan"
                            elif center.startswith("Xinjiang"): fname_center = "Xinjiang"
                            
                            jsonl_path = os.path.join(output_dir, "raw_traces", f"{model}_{fname_center}_{case_id}.jsonl")
                            
                            if case_id in completed_cases:
                                logger.info(f"Skipping completed case (Excel): {case_id} ({model})")
                                continue
                            
                            if os.path.exists(jsonl_path):
                                logger.info(f"Skipping completed case (File Found): {case_id} ({model})")
                                continue
                                
                            tasks.append(
                                executor.submit(self.evaluate_single_case, center, model, patient, output_dir)
                            )
                            
                except Exception as e:
                    logger.error(f"Failed to load cases for center {center}: {e}")
            
            # Init Total
            if progress_callback:
                progress_callback(0, len(tasks))

            # Real-time Progress Update
            for future in concurrent.futures.as_completed(tasks):
                if progress_callback:
                    progress_callback(1)
            
        return self.results
