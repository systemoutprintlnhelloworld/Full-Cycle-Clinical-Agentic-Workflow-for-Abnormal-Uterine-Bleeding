
import pandas as pd
import os

file_path = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output\Wuhan\deepseek-v3-1-think-250821\Evaluation_Summary_deepseek-v3-1-think-250821_CN.xlsx"

if not os.path.exists(file_path):
    print(f"File not found: {file_path}")
    exit(1)

try:
    # Read D1 Loop sheet
    sheet_name = "D1_Outpatient_Loop"
    df_d1 = pd.read_excel(file_path, sheet_name=sheet_name)
    # Find Case ID column (could be "CaseID" or "病例ID")
    cid_col = next((c for c in df_d1.columns if "CaseID" in c or "病例ID" in c), None)
    
    if not cid_col:
        print(f"CaseID column not found in {sheet_name}. Columns: {df_d1.columns}")
    else:
        row_d1 = df_d1[df_d1[cid_col].astype(str).str.contains('wuhan_8', case=False, na=False)]
        if not row_d1.empty:
            # Find loop count column
            loop_col = next((c for c in df_d1.columns if "Total_Loops" in c or "循环总轮次" in c), None)
            val = row_d1.iloc[0][loop_col] if loop_col else "Unknown"
            print(f"Wuhan_8 D1 Loop Count: {val}")
        else:
            print("Wuhan_8 not found in D1 Loop sheet (Correct if filtered)")

    # Read D2 Loop sheet
    sheet_name = "D2_Admission_Loop"
    df_d2 = pd.read_excel(file_path, sheet_name=sheet_name)
    cid_col = next((c for c in df_d2.columns if "CaseID" in c or "病例ID" in c), None)

    if cid_col:
        row_d2 = df_d2[df_d2[cid_col].astype(str).str.contains('wuhan_7', case=False, na=False)]
        if not row_d2.empty:
             loop_col = next((c for c in df_d2.columns if "Total_Loops" in c or "循环总轮次" in c), None)
             val = row_d2.iloc[0][loop_col] if loop_col else "Unknown"
             print(f"Wuhan_7 D2 Loop Count: {val}")
        else:
             print("Wuhan_7 not found in D2 Loop sheet (Correct if filtered)")



    # Check Status for Wuhan_5 in D2 Decision
    sheet_name = "D2_Admission_Decision"
    df_d2_dec = pd.read_excel(file_path, sheet_name=sheet_name)
    cid_col = next((c for c in df_d2_dec.columns if "CaseID" in c or "病例ID" in c), None)
    if cid_col:
        row_w5 = df_d2_dec[df_d2_dec[cid_col].astype(str).str.contains('wuhan_5', case=False, na=False)]
        if not row_w5.empty:
             val = row_w5.iloc[0].get("状态", "Unknown")
             print(f"Wuhan_5 Status in D2 Dec: {val}")
        else:
             print("Wuhan_5 not found in D2 Dec")
except Exception as e:
    print(f"Error: {e}")
