import pandas as pd
import os
import glob

def inspect_wuhan():
    root = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output\Wuhan"
    # Find first model
    if not os.path.exists(root):
        print("Wuhan dir not found")
        return

    models = [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]
    for model in models:
        excel_path = os.path.join(root, model, f"Evaluation_Summary_{model}_CN.xlsx")
        if os.path.exists(excel_path):
            print(f"Inspecting: {excel_path}")
            xls = pd.ExcelFile(excel_path)
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                print(f"\nSheet: {sheet}")
                print(f"Columns: {list(df.columns)}")
                if sheet == "D3_Surgery_Decision":
                    curr_status = df.get("状态", df.get("Gate3_状态", "Not Found"))
                    print("Sample D3 Status:", curr_status.head().tolist() if hasattr(curr_status, "head") else curr_status)
                    pass_val = df.get("Gate3_是否通过", "Not Found")
                    print("Sample Judge Pass (Gate3):", pass_val.head().tolist() if hasattr(pass_val, "head") else pass_val)
                    nmi = df.get("判官_请求更多信息", "Not Found")
                    print("Sample Need More Info:", nmi.head().tolist() if hasattr(nmi, "head") else nmi)
                if sheet == "D4_Rehab_Plan":
                    plan = df.get("医生_康复计划", "Not Found")
                    print("Sample Doc Plan (D4):", plan.head().tolist() if hasattr(plan, "head") else plan)
                    score = df.get("判官_评分", "Not Found")
                    print("Sample Judge Score (D4):", score.head().tolist() if hasattr(score, "head") else score)
            return # Just inspect one

if __name__ == "__main__":
    inspect_wuhan()
