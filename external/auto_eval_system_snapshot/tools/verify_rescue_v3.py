import pandas as pd
import os
import sys


def verify_excel(path, center_prefix="Foshan"):
    if not os.path.exists(path):
        print(f"[FAIL] File not found: {path}")
        return

    print(f"----- Verifying: {path} -----")
    xls = pd.ExcelFile(path)
    
    # Check Loop 4 in D2
    df_d2 = None
    if "D2_Admission_Loop" in xls.sheet_names:
        df_d2 = pd.read_excel(xls, "D2_Admission_Loop")
    elif "D2_Loop" in xls.sheet_names:
         df_d2 = pd.read_excel(xls, "D2_Loop")
    
    if df_d2 is not None:
        cols = df_d2.columns.tolist()
        d2_l4 = [c for c in cols if "第4轮" in c]
        print(f"D2 Loop 4 Columns: {len(d2_l4)} found")
        if d2_l4:
            print(f"  Examples: {d2_l4[:3]}") # Show first 3 matches
        else:
            print("[FAIL] No Loop 4 columns in D2!")
        
        # Check specific case logic
        # For Wuhan, logic might differ if standardization uses wuhan_5 etc.
        # But generally we look for *any* case with 4 loops if possible, or just check existence.
        
        # Simple Check: Any non-empty value in a 4th round column?
        if d2_l4:
            col_target = d2_l4[0]
            non_empty = df_d2[df_d2[col_target].notna()]
            if not non_empty.empty:
                 print(f"[PASS] Found {len(non_empty)} rows with Loop 4 data. Sample Case: {non_empty.iloc[0]['病例ID']}")
            else:
                 print(f"[WARN] No rows have Loop 4 data (Might be normal if no case reached 4 loops).")

    else:
         print("[FAIL] D2 Loop sheet not found!")

    # Check Overview Status
    df_ov = pd.read_excel(xls, "Case_Overview")
    if "未经过" in df_ov.values.astype(str):
         print("[PASS] '未经过' status found in Overview")
    else:
         print("[WARN] '未经过' not found (Maybe all cases finished?)")

if __name__ == "__main__":
    FOSHAN_FILE = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output\Foshan\gpt-5-2025-08-07\Evaluation_Summary_gpt-5-2025-08-07_CN.xlsx"
    WUHAN_FILE = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output\Wuhan\gpt-5-2025-08-07\Evaluation_Summary_gpt-5-2025-08-07_CN.xlsx"
    
    verify_excel(FOSHAN_FILE, "Foshan")
    verify_excel(WUHAN_FILE, "Wuhan")
