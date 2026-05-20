
import pandas as pd
import sys
import os

# Mock the setup to import strategy
sys.path.append(os.path.join(os.getcwd()))
from auto_eval_system.modules.data_loader_strategy import FoshanStrategy

def analyze_strategy(file_path):
    print(f"Analyzing file: {file_path}")
    strat = FoshanStrategy()
    
    # 1. Check Standardized Load Logic (First 1 row)
    try:
        df_top = pd.read_excel(file_path, nrows=1)
        print(f"Top Columns: {list(df_top.columns)}")
        if "CaseID" in df_top.columns and "GT_Outpatient_Checks" in df_top.columns:
            print("Detected Standardized Format (Clean Headers)")
            # Try to load one patient
            patients = strat._load_standardized(file_path)
            if patients:
                p = patients[0]
                print(f"\n--- Patient 0: {p['case_id']} ---")
                print(f"GT Outpatient Checks: {len(str(p.get('gt_outpatient_checks')))} chars")
                print(str(p.get('gt_outpatient_checks'))[:200])
                print(f"GT Admission Checks: {len(str(p.get('gt_admission_checks')))} chars")
                print(str(p.get('gt_admission_checks'))[:200])
                
                # Check for pollution
                out_snippet = str(p.get('gt_outpatient_checks'))[:20]
                adm_full = str(p.get('gt_admission_checks'))
                if out_snippet in adm_full and len(out_snippet) > 5:
                     print("\n[WARNING] Outpatient content found in Admission Checks!")
            return
    except Exception as e:
        print(f"Standardized check failed: {e}")

    # 2. Check Legacy Logic (Raw Table)
    print("\nFallback to Legacy Logic...")
    df = pd.read_excel(file_path, header=None)
    
    print("Printing first 5 rows raw values:")
    for i in range(5):
        print(f"Row {i}: {[str(x).strip() for x in df.iloc[i].tolist()]}")

    # Simulate step 2 of load_patients
    # Find header row
    header_row_idx = -1
    for i in range(10):
        row_vals = [str(x).strip() for x in df.iloc[i].tolist()]
        # Exact logic from Strategy
        if "姓名" in row_vals or "CaseID" in row_vals or "病历号" in row_vals or "年龄" in row_vals:
            header_row_idx = i
            break
            
    print(f"Header Row Index: {header_row_idx}")
    if header_row_idx == -1: return

    # Extract headers
    headers = df.iloc[header_row_idx].fillna("").astype(str).tolist()
    print(f"Headers (first 20): {headers[:20]}")

    # Find cutoff for Admission
    idx_adm_start = -1
    for idx, col in enumerate(headers):
        if "入院诊断" in str(col):
            idx_adm_start = idx
            break
    print(f"Calculated Cutoff (Admission Diagnosis): {idx_adm_start}")
    
    # Simulate find_cols
    def find_cols(keywords, scope, cutoff):
        res = []
        for idx, col in enumerate(headers):
            # Scope check
            if scope == "outpatient" and idx >= cutoff and cutoff != -1: continue
            if scope == "admission" and idx < cutoff: continue
            
            # Keyword check
            if any(k in col for k in keywords):
                res.append((idx, col))
        return res

    out_cols = find_cols(["门诊检查", "检查", "检验", "辅助检查"], "outpatient", idx_adm_start)
    adm_cols = find_cols(["入院检查", "实验室检查", "影像学检查", "病理学检查", "内镜检查", "其他检查", "辅助检查"], "admission", idx_adm_start)

    print(f"Outpatient Columns Found: {out_cols}")
    print(f"Admission Columns Found: {adm_cols}")
    
    # Check for overlap or pollution logic
    # In original code, merged cells might mean '辅助检查' header covers many columns, but Pandas reads it only in the first column of the merge?
    # Or if 'header=None', we read the specific row. Merged cells usually appear as "Header", NaN, NaN...
    # FoshanStrategy handles this by forward filling?
    # Let's see if we should forward fill headers. 
    # Current FoshanStrategy does NOT forward fill headers in the logic I saw.
    # It reads `df.iloc[header_row_idx]`.

    try:
        patients = strat.load_patients(file_path)
        if patients:
             p = patients[0]
             print(f"\n--- Legacy Patient 0: {p['case_id']} ---")
             print(f"GT Outpatient Checks: {str(p.get('gt_outpatient_checks'))[:100]}")
             print(f"GT Admission Checks: {str(p.get('gt_admission_checks'))[:100]}")
    except Exception as e:
        print(f"Legacy load failed: {e}")

if __name__ == "__main__":
    analyze_strategy("data/standardized_foshan.xlsx")
