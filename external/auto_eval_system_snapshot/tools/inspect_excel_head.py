import pandas as pd
import sys

def inspect(path):
    print(f"Inspecting: {path}")
    try:
        xls = pd.ExcelFile(path)
        print(f"Sheets: {xls.sheet_names}")
        if "Case_Overview" in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name="Case_Overview")
            print("Headers:", df.columns.tolist())
            print(df.head(5).to_string())
        else:
            print("No Case_Overview sheet!")
            
        if "D2_Admission_Loop" in xls.sheet_names:
             df2 = pd.read_excel(xls, sheet_name="D2_Admission_Loop")
             print("D2 Loop Headers:", df2.columns.tolist())
             print(df2.head(3).to_string())
             # Check wuhan_100
             row = df2[df2['病例ID'] == 'wuhan_100']
             if not row.empty:
                 print("\nWuhan_100 Data:")
                 print(row.to_string())
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        inspect(sys.argv[1])
    else:
        inspect(r"d:\研究生\项目\课题7-临床评测\自动测评系统\output\Wuhan\grok-4\Evaluation_Summary_grok-4_CN.xlsx")
