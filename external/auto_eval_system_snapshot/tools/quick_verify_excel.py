import pandas as pd
import os
import glob

def check_excel(file_path):
    print(f"Checking: {os.path.basename(file_path)}")
    try:
        df_dict = pd.read_excel(file_path, sheet_name=None)
        
        # Check D3 Decision for Gate3 Status
        if "D3_Surgery_Decision" in df_dict:
            df = df_dict["D3_Surgery_Decision"]
            if "Gate3_状态" in df.columns: # Gate3_Status -> Gate3_状态
                print("  [OK] D3 Sheet has 'Gate3_状态'")
                print(f"       Sample: {df['Gate3_状态'].head(3).tolist()}")
            elif "状态" in df.columns:
                 print("  [OK] D3 Sheet has '状态'")
                 print(f"       Sample: {df['状态'].head(3).tolist()}")
            else:
                print("  [FAIL] D3 Sheet MISSING Status column")
        
        # Check D1 Decision for Status
        if "D1_Outpatient_Decision" in df_dict:
            df = df_dict["D1_Outpatient_Decision"]
            if "状态" in df.columns:
                print("  [OK] D1 Decision has '状态'")
                print(f"       Sample: {df['状态'].head(3).tolist()}")
            else:
                print("  [FAIL] D1 Decision MISSING '状态'")

        # Check Gate 4 Data
        if "D4_Rehab_Plan" in df_dict:
             df = df_dict["D4_Rehab_Plan"]
             # Check if purely empty (all nulls)
             non_null = df.dropna(how='all').shape[0]
             print(f"  [INFO] D4 Rows with data: {non_null}/{len(df)}")
             if "判官_原始JSON" in df.columns:
                 print(f"       Sample Judge: {df['判官_原始JSON'].dropna().head(1).tolist()}")

    except Exception as e:
        print(f"  [ERROR] {e}")

def main():
    root = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output"
    # Check one file from each center
    centers = ["Foshan", "Xinjiang", "Wuhan"]
    for c in centers:
        path = os.path.join(root, c)
        if not os.path.exists(path): continue
        
        # Find first model dir
        models = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]
        if models:
            model = models[0]
            # Find excel
            excels = glob.glob(os.path.join(path, model, "Evaluation_Summary_*_CN.xlsx"))
            if excels:
                check_excel(excels[0])

if __name__ == "__main__":
    main()
