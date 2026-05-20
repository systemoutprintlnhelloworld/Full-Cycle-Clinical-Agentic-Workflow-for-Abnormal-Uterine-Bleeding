import pandas as pd
import os

def inspect_deepseek():
    # Path provided by user
    excel_path = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output\Wuhan\deepseek-v3-1-think-250821\Evaluation_Summary_deepseek-v3-1-think-250821_CN.xlsx"
    
    if not os.path.exists(excel_path):
        print(f"File not found: {excel_path}")
        return

    xls = pd.ExcelFile(excel_path)
    
    print(f"Inspecting: {os.path.basename(excel_path)}")
    
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        print(f"\n[Sheet: {sheet}] Shape: {df.shape}")
        
        # Check Status Columns
        status_cols = [c for c in df.columns if "状态" in c or "Status" in c]
        print(f"  Status Cols: {status_cols}")
        
        # Check specific issues asked by user
        if sheet == "D2_Admission_Loop":
            # Check for Judge JSON and Counts
            target_col = "第1轮_Judge原始JSON"
            if target_col in df.columns:
                non_empty = df[target_col].dropna().astype(str)
                non_empty = non_empty[non_empty != ""]
                print(f"  Judge JSON (Rd1) Non-Empty Rows: {len(non_empty)} / {len(df)}")
                if not non_empty.empty:
                    print(f"  Sample Judge JSON: {non_empty.iloc[0][:100]}...")
            else:
                print(f"  ERROR: '{target_col}' column missing! Cols: {df.columns.tolist()[:5]}...")
        
        if sheet == "D3_Surgery_Decision":
             doc_json = [c for c in df.columns if "Doc" in c or "医生" in c and "JSON" in c]
             print(f"  Doc JSON Cols: {doc_json}")

if __name__ == "__main__":
    inspect_deepseek()
