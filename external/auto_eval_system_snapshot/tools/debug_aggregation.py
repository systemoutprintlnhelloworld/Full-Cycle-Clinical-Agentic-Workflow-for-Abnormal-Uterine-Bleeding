import pandas as pd
import os

file_path = r"D:\研究生\项目\课题7-临床评测\自动测评系统\测评结果\佛山\Evaluation_Summary_claude-opus-4-1-20250805-thinking_CN_Judge_Parsed.xlsx"

try:
    xls = pd.ExcelFile(file_path)
    print("Sheets:", xls.sheet_names)
    
    if "D1_Outpatient_Decision" in xls.sheet_names:
        df = pd.read_excel(xls, "D1_Outpatient_Decision")
        print("D1 Columns:", df.columns.tolist())
        print("D1 Head:", df.head(1).to_dict())
        print("D1 Shape:", df.shape)
    else:
        print("D1_Outpatient_Decision sheet missing")
        
except Exception as e:
    print(f"Error: {e}")
