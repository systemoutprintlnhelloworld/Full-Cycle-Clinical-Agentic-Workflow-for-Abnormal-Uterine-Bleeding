import pandas as pd
import json

# 读取一个有问题的文件
file_path = r"D:\研究生\项目\课题7-临床评测\自动测评系统\测评结果\佛山\Evaluation_Summary_gemini-2.5-pro_CN.xlsx"

xls = pd.ExcelFile(file_path)
print("所有sheets:", xls.sheet_names)

# 读取D1_Outpatient_Decision和D2_Admission_Loop
d1_decision = pd.read_excel(file_path, sheet_name="D1_Outpatient_Decision")
d2_loop = pd.read_excel(file_path, sheet_name="D2_Admission_Loop")

print("\n=== D1_Outpatient_Decision ===")
print("列名:", list(d1_decision.columns))
print("前3个病例ID:", d1_decision['病例ID'].head(3).tolist())

# 检查第一个病例
case_id = d1_decision['病例ID'].iloc[0]
print(f"\n检查病例: {case_id}")

# 检查D1_Outpatient_Decision中的数据
print("\nD1_Outpatient_Decision中的医生JSON:")
for col in d1_decision.columns:
    if '医生' in col and 'JSON' in col:
        val = d1_decision[d1_decision['病例ID'] == case_id][col].iloc[0]
        has_data = pd.notna(val) and str(val).strip() != ""
        print(f"  {col}: {'有数据' if has_data else '空'}")

print("\nD1_Outpatient_Decision中的判官JSON:")
for col in d1_decision.columns:
    if any(kw in col for kw in ['判官', 'Judge', 'Gate']) and 'JSON' in col:
        val = d1_decision[d1_decision['病例ID'] == case_id][col].iloc[0]
        has_data = pd.notna(val) and str(val).strip() != ""
        print(f"  {col}: {'有数据' if has_data else '空'}")

print("\n=== D2_Admission_Loop ===")
print("列名:", list(d2_loop.columns))

# 检查D2中是否有该病例
case_in_d2 = d2_loop[d2_loop['病例ID'] == case_id]
print(f"病例{case_id}在D2中: {'存在' if not case_in_d2.empty else '不存在'}")

if not case_in_d2.empty:
    print("\nD2_Admission_Loop中的医生JSON:")
    for col in d2_loop.columns:
        if '医生' in col and 'JSON' in col:
            val = case_in_d2[col].iloc[0]
            has_data = pd.notna(val) and str(val).strip() != ""
            print(f"  {col}: {'有数据' if has_data else '空'} (长度:{len(str(val)) if pd.notna(val) else 0})")
    
    print("\nD2_Admission_Loop中的判官JSON:")
    for col in d2_loop.columns:
        if any(kw in col for kw in ['判官', 'Judge', 'Gate']) and 'JSON' in col:
            val = case_in_d2[col].iloc[0]
            has_data = pd.notna(val) and str(val).strip() != ""
            print(f"  {col}: {'有数据' if has_data else '空'} (长度:{len(str(val)) if pd.notna(val) else 0})")
