import os
import glob
import pandas as pd
import sys
import shutil

# Constants
PROJECT_ROOT = r"d:\研究生\项目\课题7-临床评测\自动测评系统"
OUTPUT_ROOT = os.path.join(PROJECT_ROOT, "output")
CENTERS = ["Wuhan_Fixed-v2", "Foshan-v2", "Xinjiang-v2"] # Updated for V2 Batch

def get_target_cases(center, model):
    """
    Re-implements logic to find Blocked and Error cases.
    We don't import check_retest_status to avoid messing with paths/prints.
    """
    model_dir = os.path.join(OUTPUT_ROOT, center, model)
    raw_traces_dir = os.path.join(model_dir, "raw_traces")
    # xlsx_ckpt = os.path.join(model_dir, f"{model}_{center}_results.xlsx")
    xlsx_ckpt = os.path.join(model_dir, f"Evaluation_Summary_{model}_CN.xlsx")
    json_ckpt = os.path.join(model_dir, "checkpoint.json")

    completed_cases = set()
    error_cases = set()

    # 1. Read Excel for Completed & Error
    if os.path.exists(xlsx_ckpt):
        try:
            df = pd.read_excel(xlsx_ckpt, sheet_name="Case_Overview") # Explicitly read overview
            col = next((c for c in df.columns if c.lower().replace("_","") == "caseid" or "病例ID" in c), None)
            res_col = next((c for c in df.columns if "Final_Result" in c or "最终结果" in c), None)

            if col:
                completed_cases.update(set(df[col].astype(str).tolist()))
                if res_col:
                    err_df = df[df[res_col].astype(str).str.contains("Error", case=False, na=False)]
                    error_cases = set(err_df[col].astype(str).tolist())
        except:
            pass

    # 2. Read JSON Checkpoint (Priority for Batch V2 if excel missing)
    if os.path.exists(json_ckpt):
        try:
            import json
            with open(json_ckpt, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "completed_cases" in data:
                    completed_cases.update(set([str(c) for c in data["completed_cases"]]))
        except Exception as e:
            print(f"    [ERR] Reading JSON checkpoint: {e}", flush=True)
    
    # 2. Find Traces for Blocked Logic
    # Blocked = Has Trace BUT Not in Completed (or in Error)
    # Actually, if it's in Error, it IS in Completed set usually.
    # So we want to clean: (Trace exists AND (Not Completed OR Error))
    
    trace_files = glob.glob(os.path.join(raw_traces_dir, "*.jsonl"))
    cases_to_clean = set()

    # Add Errors (even if they are "completed")
    cases_to_clean.update(error_cases)

    for f in trace_files:
        basename = os.path.basename(f)
        
        # Handle Wuhan_Fixed naming mismatch (Files are named with 'Wuhan')
        target_center_name = center
        if center.startswith("Wuhan"): target_center_name = "Wuhan"
        elif center.startswith("Foshan"): target_center_name = "Foshan"
        elif center.startswith("Xinjiang"): target_center_name = "Xinjiang"
            
        prefix = f"{model}_{target_center_name}_"
        
        # Also try exact match if center name was strictly used (Legacy fallback)
        if not basename.startswith(prefix) and "Fixed" in center:
             pass # Logic above handles it generally

        if basename.startswith(prefix) and basename.endswith(".jsonl"):
            cid = basename[len(prefix):-6]
            if cid not in completed_cases:
                cases_to_clean.add(cid)
            elif cid in error_cases:
                cases_to_clean.add(cid) 
                
    return sorted(list(cases_to_clean))

def sync_checkpoint_from_backup(center, model, backup_dir, json_ckpt):
    if not os.path.exists(backup_dir):
        return
        
    files = os.listdir(backup_dir)
    backup_cases = set()
    for f in files:
        if f.endswith(".jsonl"):
            # {model}_{center}_{cid}.jsonl
            prefix = f"{model}_{center}_"
            if f.startswith(prefix):
                 cid = f[len(prefix):-6]
                 backup_cases.add(cid)
        elif f.endswith("_trace.html"):
             prefix = f"{model}_{center}_"
             if f.startswith(prefix):
                 cid = f[len(prefix):-11]
                 backup_cases.add(cid)
    
    if not backup_cases:
        return

    if os.path.exists(json_ckpt):
        try:
            import json
            with open(json_ckpt, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if "completed_cases" in data:
                original = set(str(c) for c in data["completed_cases"])
                # Only remove if present
                to_remove = original.intersection(backup_cases)
                
                if to_remove:
                    print(f"    [Sync] Removing {len(to_remove)} cases from checkpoint (Found in Re-test Backup): {sorted(list(to_remove))}", flush=True)
                    new_completed = [c for c in data["completed_cases"] if str(c) not in to_remove]
                    data["completed_cases"] = new_completed
                    
                    if "failed_cases" in data:
                         data["failed_cases"] = [c for c in data["failed_cases"] if str(c) not in to_remove]

                    with open(json_ckpt, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"    [ERR] Syncing checkpoint: {e}", flush=True)

def clean_model(center, model, dry_run=True):
    print(f"\nScanning {center} / {model} ...", flush=True)
    cases = get_target_cases(center, model)
    
    if not cases:
        print("  >> No cases to clean.", flush=True)
        return

    print(f"  >> Found {len(cases)} cases to clean (Blocked/Error): {', '.join(cases)}", flush=True)
    
    if dry_run:
        print("  >> [Dry Run] Would delete .html/.jsonl and remove from Excel.", flush=True)
        return

    # Delete Files
    model_dir = os.path.join(OUTPUT_ROOT, center, model)
    raw_traces_dir = os.path.join(model_dir, "raw_traces")
    html_traces_dir = os.path.join(model_dir, "html_traces")

    # Define Backup Directory
    backup_dir = os.path.join(model_dir, "retest_backup_3")
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        print(f"    Created backup dir: {backup_dir}", flush=True)

    for cid in cases:
        # Determine likely center name in filename
        fname_center = center
        if center.startswith("Wuhan"): fname_center = "Wuhan"
        elif center.startswith("Foshan"): fname_center = "Foshan"
        elif center.startswith("Xinjiang"): fname_center = "Xinjiang"

        # JSONL
        # Try expected filename first
        jsonl = os.path.join(raw_traces_dir, f"{model}_{fname_center}_{cid}.jsonl")
        if not os.path.exists(jsonl):
             # Fallback to exact center name
             jsonl = os.path.join(raw_traces_dir, f"{model}_{center}_{cid}.jsonl")
             
        if os.path.exists(jsonl):
            shutil.move(jsonl, os.path.join(backup_dir, os.path.basename(jsonl)))
            print(f"    Moved jsonl: {cid} ({os.path.basename(jsonl)})", flush=True)
        else:
            print(f"    [WARN] JSONL not found for {cid}: {jsonl}", flush=True)
        
        # HTML
        html = os.path.join(html_traces_dir, f"{model}_{fname_center}_{cid}_trace.html")
        if not os.path.exists(html):
             html = os.path.join(html_traces_dir, f"{model}_{center}_{cid}_trace.html")

        if os.path.exists(html):
            shutil.move(html, os.path.join(backup_dir, os.path.basename(html)))
            print(f"    Moved html:  {cid} ({os.path.basename(html)})", flush=True)
            
        # Single Excel (Report)
        single_xlsx = os.path.join(model_dir, "single_excels", f"{model}_{fname_center}_{cid}.xlsx")
        if not os.path.exists(single_xlsx):
             single_xlsx = os.path.join(model_dir, "single_excels", f"{model}_{center}_{cid}.xlsx")

        if os.path.exists(single_xlsx):
            shutil.move(single_xlsx, os.path.join(backup_dir, os.path.basename(single_xlsx)))
            print(f"    Moved xlsx:  {cid}", flush=True)

    # Remove from Excel
    xlsx_ckpt = os.path.join(model_dir, f"Evaluation_Summary_{model}_CN.xlsx")
    json_ckpt = os.path.join(model_dir, "checkpoint.json")
    
    if os.path.exists(xlsx_ckpt):
        try:
            df = pd.read_excel(xlsx_ckpt, sheet_name=None)
            with pd.ExcelWriter(xlsx_ckpt, engine='openpyxl') as writer:
                for sheet_name, sheet_df in df.items():
                    col = next((c for c in sheet_df.columns if c.lower().replace("_","") == "caseid" or "病例ID" in c), None)
                    if col:
                        original_len = len(sheet_df)
                        clean_set = set(str(c) for c in cases)
                        new_df = sheet_df[~sheet_df[col].astype(str).isin(clean_set)]
                        new_df.to_excel(writer, sheet_name=sheet_name, index=False)
                        if len(new_df) < original_len:
                            print(f"    Updated sheet '{sheet_name}': Removed {original_len - len(new_df)} rows.", flush=True)
                    else:
                        sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
        except Exception as e:
            print(f"    [ERR] Updating Excel: {e}", flush=True)
            
    # Final Step: Sync Checkpoint with Backup (Robustness)
    sync_checkpoint_from_backup(center, model, backup_dir, json_ckpt)




def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--execute':
        dry_run = False
    else:
        dry_run = True
        print("RUNNING IN DRY RUN MODE. Use '--execute' to apply changes.")

    for center in CENTERS:
        c_path = os.path.join(OUTPUT_ROOT, center)
        if not os.path.exists(c_path): continue
        models = [d for d in os.listdir(c_path) if os.path.isdir(os.path.join(c_path, d))]
        for model in models:
            clean_model(center, model, dry_run=dry_run)

if __name__ == "__main__":
    main()
