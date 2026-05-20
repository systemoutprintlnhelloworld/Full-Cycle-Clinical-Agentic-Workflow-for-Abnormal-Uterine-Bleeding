
import os
import json
import glob
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output\Foshan"

def sync_model_checkpoint(model_name):
    model_dir = os.path.join(BASE_DIR, model_name)
    raw_dir = os.path.join(model_dir, "raw_traces")
    checkpoint_file = os.path.join(model_dir, "checkpoint.json")
    
    if not os.path.exists(raw_dir):
        print(f"[{model_name}] No raw_traces dir found.")
        return
        
    # Standardize reading checkpoint
    completed = set()
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                completed = set(data.get("completed_cases", []))
        except: pass
        
    print(f"[{model_name}] Current Checkpoint Count: {len(completed)}")
    
    # Scan JSONLs
    jsonls = glob.glob(os.path.join(raw_dir, "*.jsonl"))
    valid_count = 0
    new_cases = set()
    
    for jf in jsonls:
        if os.path.getsize(jf) == 0:
            continue
            
        fname = os.path.basename(jf)
        # Format: Model_Center_CaseID.jsonl
        parts = fname.replace(".jsonl", "").split("_")
        
        if len(parts) >= 3:
            case_id = "_".join(parts[2:])
            
            # Smart Completion Check:
            # - D4_Rehab -> Valid (Finished)
            # - D3_Surgery -> Valid (Gate 3 Termination or Success)
            # - D1/D2: Valid if Loop 4 (Limit) OR NeedsChecks=False (Gate Entry)
            # - D1/D2: Invalid if Loop < 4 AND NeedsChecks=True (Crashed mid-loop)
            
            is_valid = False
            last_line = ""
            try:
                with open(jf, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        last_line = lines[-1].strip()
                        
                if last_line:
                    record = json.loads(last_line)
                    stage = record.get("stage", "")
                    loop = record.get("loop", 0)
                    output = record.get("output", {})
                    
                    if "D4_Rehab" in stage:
                        is_valid = True
                    elif "D3_Surgery" in stage:
                        is_valid = True
                    elif "D1_Outpatient" in stage or "D2_Admission" in stage:
                        # Check Loop Limit
                        if loop >= 4:
                            is_valid = True
                        else:
                            # Check Intent
                            # D1 key: "需要补充门诊检查"
                            # D2 key: "需要补充检查" or "能够确诊"
                            need_more = False
                            if "D1" in stage:
                                need_more = output.get("需要补充门诊检查", False)
                            else:
                                # D2 logic: Need more if NOT Diagnosed OR explicit need list
                                can_diagnose = output.get("能够确诊", False)
                                need_checks_str = output.get("需要补充检查", "")
                                if not can_diagnose or need_checks_str:
                                    need_more = True
                                    
                            if not need_more:
                                is_valid = True
                            # Else (Need More AND Loop < 4) -> Crash -> Invalid
                    
            except Exception as e:
                # print(f"Error analyzing {jf}: {e}")
                pass
                
            if is_valid:
                new_cases.add(case_id)
                valid_count += 1

    # Update
    original_len = len(completed)
    completed.update(new_cases)
    
    if len(completed) > original_len:
        print(f"[{model_name}] Found {valid_count} valid traces. Updating Checkpoint: {original_len} -> {len(completed)} (+{len(completed)-original_len})")
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump({
                "last_updated_by": "sync_script_strict",
                "completed_cases": list(completed)
            }, f, indent=2, ensure_ascii=False)
    else:
        print(f"[{model_name}] No new completed cases found (Scanned {valid_count} valid jsonls).")

def main():
    models = [d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d))]
    print(f"Found models: {models}")
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(sync_model_checkpoint, models)

if __name__ == "__main__":
    main()
