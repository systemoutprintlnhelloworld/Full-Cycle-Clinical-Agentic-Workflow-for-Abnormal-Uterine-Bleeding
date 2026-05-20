
import pandas as pd
import sys

def inspect_input(path):
    print(f"Inspecting Input: {path}")
    try:
        df = pd.read_excel(path, sheet_name=0) # Read first sheet
        print("Sheet 0 Headers:", df.columns.tolist())
        print("First row Sample:")
        first_row = df.iloc[0].to_dict()
        # Print a few key columns to verify content
        keys_to_show = ["病例ID", "主诉", "辅助检查", "术中所见", "CaseID"]
        for k in keys_to_show:
            found_k = next((c for c in df.columns if k in c), None)
            if found_k:
                print(f"  {found_k}: {str(first_row[found_k])[:50]}...")
            else:
                print(f"  {k}: Not Found")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_input(r"d:\研究生\项目\课题7-临床评测\自动测评系统\data\standardized_wuhan - 移动信息.xlsx")
