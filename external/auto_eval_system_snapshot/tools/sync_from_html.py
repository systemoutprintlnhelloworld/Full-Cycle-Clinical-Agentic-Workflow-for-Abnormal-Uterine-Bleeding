
import os
import json
import glob
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

def check_html_content_for_errors(filepath):
    """
    Returns True if the HTML file appears to contain a critical system error.
    Heuristics:
    - Contains 'Traceback (most recent call last)'
    - Contains 'System_Error'
    - Contains 'Terminated_Gate' (This might be a valid termination, but user might want to review?)
      User said: "e.g. this case has error".
      Usually "Error" implies Crash. Terminated at Gate is a logic outcome.
      I will flag 'Traceback' and explicit 'Error' logs.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if "Traceback (most recent call last)" in content:
                return "Traceback detected"
            if "System_Error" in content:
                return "System_Error logged"
            # if "Status: Terminated" in content: 
            #     return "Terminated" # Optional, maybe not an error.
            if len(content) < 500: # Very small file
                return "File too small (<500 bytes)"
    except Exception as e:
        return f"Read Error: {e}"
    
    return None

def process_model_directory(model_dir):
    """
    Process a model directory (e.g. output/Xinjiang/grok-4)
    Expects 'html_traces' subdir.
    """
    html_dir = os.path.join(model_dir, "html_traces")
    checkpoint_file = os.path.join(model_dir, "checkpoint.json")
    
    if not os.path.exists(html_dir):
        return
        
    print(f"Scanning {html_dir}...")
    
    # 1. Identify Valid (Root) vs Invalid (Subdirs)
    valid_cases = set()
    suspicious_cases = [] # (CaseID, Reason)
    
    # List files in root of html_traces
    # os.listdir just names
    root_files = [f for f in os.listdir(html_dir) if f.endswith(".html") and os.path.isfile(os.path.join(html_dir, f))]
    
    for fname in root_files:
        # Content Based CaseID Extraction (Most Reliable)
        true_case_id = None
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                head = f.read(2000) # Read enough header
                # Pattern: CASE ID: <span class="meta-tag">{self.case_id}</span>
                import re
                # Try specific echo template pattern
                m = re.search(r'CASE ID:\s*<span[^>]*>([^<]+)</span>', head)
                if m:
                    true_case_id = m.group(1).strip()
                else:
                    # Fallback or older format
                    m2 = re.search(r'Case:\s*([A-Za-z0-9_]+)', head)
                    if m2:
                        true_case_id = m2.group(1).strip()
        except Exception as e:
            print(f"Error reading {fname}: {e}")

        # Fallback to smart filename parsing if content fail
        # Format: Model_Center_CaseID_trace.html
        if not true_case_id:
            name_no_ext = fname.replace("_trace.html", "").replace(".html", "")
            # Heuristic: Remove Model and Center
            # We know the directory is output/Center/Model
            # But the script is running with 'model_dir' arg...
            # We can deduce Model and Center from path?
            # path: output/Foshan/gemini-2.5-pro/html_traces/file.html
            # parent: output/Foshan/gemini-2.5-pro
            path_parts = model_dir.replace("\\", "/").split("/")
            if len(path_parts) >= 2:
                model_name_dir = path_parts[-1]
                center_name_dir = path_parts[-2]
                
                prefix = f"{model_name_dir}_{center_name_dir}_"
                if name_no_ext.startswith(prefix):
                    true_case_id = name_no_ext[len(prefix):]
                else:
                    # Try just removing trace
                    true_case_id = name_no_ext
        
        case_id_candidate = true_case_id if true_case_id else fname.replace(".html", "")
        
        # Restore error check
        fpath = os.path.join(html_dir, fname)
        error_reason = check_html_content_for_errors(fpath)
        
        if error_reason:
            suspicious_cases.append((case_id_candidate, fpath, error_reason))
            # Still add to Valid if in root (User accepted it)
            valid_cases.add(case_id_candidate)
        else:
            valid_cases.add(case_id_candidate)

    # 2. Update Checkpoint
    if valid_cases:
        # Load existing (optional merge? No, user says "Use THIS as record")
        # So I should Overwrite or Merge?
        # "据此作为...记录" -> likely "Overwrite" or "Sync to this state".
        # But to be safe, I'll merge (Union), or strictly trust this folder?
        # If user deleted files (moved to error), they should be REMOVED from checkpoint.
        # So strictly trusting this list (Overwrite) is better for "removing bad ones".
        # BUT, what if other files are valid but just not generated yet?
        # User says "record checkpoint based on this".
        # If I strictly overwrite, and I haven't run the other cases, that's fine (empty).
        # But if I ran 100, and user sorted 10 into Error, and kept 90.
        # I should record 90.
        # So Overwriting the "completed_cases" list with `valid_cases` seems correct for those 100 ID range.
        # But what if there are other cases not yet run? They wouldn't be in the list anyway.
        # So Overwrite is the correct logic for "Sync status to disk state".
        
        current_data = {}
        if os.path.exists(checkpoint_file):
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                try: current_data = json.load(f)
                except: pass
        
        current_data["completed_cases"] = list(valid_cases)
        current_data["last_updated_by"] = "sync_from_html_structure"
        
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, indent=2, ensure_ascii=False)
            
        print(f"Updated {checkpoint_file}: {len(valid_cases)} cases.")
    
    # 3. Generate Checklist if suspicious
    if suspicious_cases:
        checklist_path = os.path.join(model_dir, "review_checklist.md")
        with open(checklist_path, 'w', encoding='utf-8') as f:
            f.write("# Suspicious Valid Cases Checklist\n")
            f.write("The following cases are in the 'Valid' (root) folder but detected potential errors:\n\n")
            f.write("| Case ID | Path | Reason |\n")
            f.write("| --- | --- | --- |\n")
            for cid, path, reason in suspicious_cases:
                f.write(f"| {cid} | `{path}` | {reason} |\n")
        print(f"WARNING: Found {len(suspicious_cases)} suspicious cases. See {checklist_path}")

def main():
    # Walk all output dirs
    for root, dirs, files in os.walk(OUTPUT_DIR):
        if "html_traces" in dirs:
            # This 'root' is a model directory (e.g. .../grok-4)
            process_model_directory(root)

if __name__ == "__main__":
    main()
