import os
import pandas as pd
import glob
from collections import defaultdict

# Config
PROJECT_ROOT = r"d:\研究生\项目\课题7-临床评测\自动测评系统"
OUTPUT_ROOT = os.path.join(PROJECT_ROOT, "output")
DATA_ROOT = os.path.join(PROJECT_ROOT, "data")
RETEST_MD_PATH = os.path.join(PROJECT_ROOT, "retest.md")

CENTERS = ["Wuhan_Fixed-v2", "Foshan-v2", "Xinjiang-v2"] # Updated for V2 Batch

def get_total_cases(center):
    """Load total cases from standardized excel."""
    # Try standardized path
    # Mapping for V2 / Fixed
    data_center = center.split("-")[0] # Strip -v2
    if "wuhan" in data_center.lower() and "fixed" in center.lower():
         path = os.path.join(DATA_ROOT, "standardized_wuhan - 移动信息.xlsx")
    else:
         path = os.path.join(DATA_ROOT, f"standardized_{data_center.lower()}.xlsx")
    
    if not os.path.exists(path):
        # Fallback for Xinjiang maybe?
        path = os.path.join(DATA_ROOT, data_center, f"standardized_{data_center.lower()}.xlsx")
        if not os.path.exists(path):
            print(f"[WARN] Could not find source data for {center}")
            return set()
    
    try:
        df = pd.read_excel(path)
        if "case_id" in df.columns:
            return set(df["case_id"].astype(str).tolist())
        elif "CaseID" in df.columns:
             return set(df["CaseID"].astype(str).tolist())
    except Exception as e:
        print(f"[ERR] Failed reading {path}: {e}")
    return set()

def analyze_model(center, model):
    model_dir = os.path.join(OUTPUT_ROOT, center, model)
    checkpoint_path = os.path.join(model_dir, f"{model}_{center}_results.xlsx")
    raw_traces_dir = os.path.join(model_dir, "raw_traces")
    
    # 1. Total Expected
    total_cases = get_total_cases(center)
    total_count = len(total_cases)
    
    # 2. Completed (Checkpoints)
    completed_cases = set()
    
    # Priority 1: checkpoint.json (Produced by batch_runner.py)
    json_ckpt = os.path.join(model_dir, "checkpoint.json")
    if os.path.exists(json_ckpt):
        try:
            import json
            with open(json_ckpt, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "completed_cases" in data:
                    # Extracts raw case IDs (e.g., "foshan_15")
                    # Need to normalize if necessary. 
                    # Standardized excel usually uses "15" or "foshan_15".
                    # Let's align with get_total_cases format.
                    
                    # Check format of total_cases first element to guess standard
                    # But total_cases usually has "1", "2" etc from standardized_foshan.xlsx?
                    # Let's inspect standardized_foshan.xlsx content in memory if possible?
                    # The get_total_cases loads from excel.
                    
                    # Assuming completed_cases in json are valid IDs.
                    completed_cases = set([str(c) for c in data["completed_cases"]])
        except Exception as e:
            print(f"  [ERR] Reading JSON checkpoint {json_ckpt}: {e}")

    # Priority 2: Excel Result (Legacy or Manual) + Error Detection
    # Only if JSON didn't give us anything (or purely additive?)
    # Let's be additive to be safe.
    # xlsx_ckpt = os.path.join(model_dir, f"{model}_{center}_results.xlsx") # OLD
    xlsx_ckpt = os.path.join(model_dir, f"Evaluation_Summary_{model}_CN.xlsx") # NEW
    error_cases = set()
    
    if os.path.exists(xlsx_ckpt):
        try:
            # df = pd.read_excel(xlsx_ckpt) # Default sheet might NOT be Case_Overview if saved oddly? 
            # rescue_excel_v3 writes Case_Overview first, but let's be explicit.
            df = pd.read_excel(xlsx_ckpt, sheet_name="Case_Overview")
            col = next((c for c in df.columns if c.lower().replace("_","") == "caseid" or "病例ID" in c), None)
            
            # Check for Final Result column (English or Chinese)
            res_col = next((c for c in df.columns if "Final_Result" in c or "最终结果" in c), None)

            if col:
                excel_cases = set(df[col].astype(str).tolist())
                completed_cases.update(excel_cases)
                
                # Check for Errors
                if res_col:
                    # Find all cases with "Error" in result
                    err_df = df[df[res_col].astype(str).str.contains("Error", case=False, na=False)]
                    if "gpt-5" in model:
                        print(f"DEBUG: Model {model} - Res Col: {res_col}")
                        print(f"DEBUG: Found {len(err_df)} error rows.")
                        if not err_df.empty:
                            print(f"DEBUG: Error IDs: {err_df[col].tolist()}")

                    error_cases = set(err_df[col].astype(str).tolist())
                else:
                    if "gpt-5" in model:
                        print(f"DEBUG: Model {model} - Res Col NOT FOUND. Columns: {list(df.columns)}")

        except Exception as e:
            print(f"  [ERR] Reading Excel checkpoint {xlsx_ckpt}: {e}")
            pass

    # 3. Existing Traces (Potential Blockers)
    trace_files = glob.glob(os.path.join(raw_traces_dir, "*.jsonl"))
    trace_cases = set()
    for f in trace_files:
        # filename format: {model}_{center}_{case_id}.jsonl
        # Warning: model name might contain underscores.
        # Strategy: remove prefix "{model}_{center}_"
        # But verify logic in batch_runner.py uses: f"{model}_{center}_{case_id}.jsonl"
        basename = os.path.basename(f)
        
        # Determine prefix based on center alias
        fname_center_part = center
        if center.startswith("Wuhan"): fname_center_part = "Wuhan"
        elif center.startswith("Foshan"): fname_center_part = "Foshan"
        elif center.startswith("Xinjiang"): fname_center_part = "Xinjiang"
            
        prefix = f"{model}_{fname_center_part}_"
        if basename.startswith(prefix) and basename.endswith(".jsonl"):
            cid = basename[len(prefix):-6]
            trace_cases.add(cid)
    
    # Analysis
    # Missing from Checkpoint
    missing_from_checkpoint = total_cases - completed_cases
    
    # Blocked: Missing from checkpoint BUT has trace file
    blocked_cases = missing_from_checkpoint.intersection(trace_cases)
    
    return {
        "total": total_count,
        "completed": len(completed_cases),
        "missing": len(missing_from_checkpoint),
        "blocked": len(blocked_cases),
        "blocked_list": list(blocked_cases),
        "error": len(error_cases),
        "error_list": list(error_cases)
    }

def main():
    report_lines = ["# 重测需求分析报告 (Retest Analysis)", "", f"生成时间: {pd.Timestamp.now()}", ""]
    
    grand_total_todo = 0
    
    for center in CENTERS:
        center_path = os.path.join(OUTPUT_ROOT, center)
        if not os.path.exists(center_path):
            continue
            
        report_lines.append(f"## Center: {center}")
        
        # Find model folders
        models = [d for d in os.listdir(center_path) if os.path.isdir(os.path.join(center_path, d))]
        
        for model in models:
            stats = analyze_model(center, model)
            
            report_lines.append(f"### Model: {model}")
            report_lines.append(f"- **总病例数 (Source)**: {stats['total']}")
            report_lines.append(f"- **已完成 (Checkpoint)**: {stats['completed']}")
            report_lines.append(f"- **待重测 (Missing)**: {stats['missing']}")
            report_lines.append(f"- **受阻病例 (Blocked)**: **{stats['blocked']}**")
            report_lines.append(f"- **错误病例 (Error)**: **{stats['error']}** (Checkpoints中标记为Error)")
            
            grand_total_todo += stats['blocked'] + stats['error']
            
            cases_to_clean = sorted(list(set(stats['blocked_list'] + stats['error_list'])))
            
            if cases_to_clean:
                report_lines.append("  > **需要重新运行 (Blocked + Error)**:")
                # List ALL cases (no truncation)
                list_str = ", ".join(cases_to_clean)
                report_lines.append(f"  > `Cases: {list_str}`")
                
                # Generate Delete Command Hint
                report_lines.append("")
                report_lines.append("  ```bash")
                report_lines.append(f"  # 删除命令参考 (PowerShell - 请在 output/{center}/{model}/raw_traces 下执行)")
                report_lines.append(f"  # Remove-Item *_{center}_caseID.jsonl")
                report_lines.append("  ```")
            
            report_lines.append("")
            
    report_lines.append("---")
    report_lines.append(f"**总计需重测病例数 (Blocked + Error)**: {grand_total_todo}")
    report_lines.append("请根据此表手动清理受阻文件后，重新运行评测脚本。")

    with open(RETEST_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    
    print(f"Report generated at: {RETEST_MD_PATH}")
    print(f"Total Cases to Retest: {grand_total_todo}")

if __name__ == "__main__":
    main()
