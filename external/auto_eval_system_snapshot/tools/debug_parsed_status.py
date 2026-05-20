import pandas as pd

# 检查Parsed文件的状态列
file_path = r"D:\研究生\项目\课题7-临床评测\自动测评系统\测评结果\佛山\Evaluation_Summary_gemini-2.5-pro_CN_Judge_Parsed.xlsx"

d1 = pd.read_excel(file_path, sheet_name="D1_Outpatient_Decision")
d2 = pd.read_excel(file_path, sheet_name="D2_Admission_Loop")

print("=== D1_Outpatient_Decision Parsed ===")
print("列名:", list(d1.columns)[:5])
print("\n前5个病例的状态:")
print(d1[['病例ID', '状态']].head())

print("\n=== D2_Admission_Loop Parsed ===")
print("列名:", list(d2.columns)[:5])
print("\n前5个病例的状态:")
print(d2[['病例ID', '状态']].head())

# 检查第一个病例在两个sheet中的数据
case_id = d1['病例ID'].iloc[0]
print(f"\n=== 病例 {case_id} 详情 ===")
print("D1状态:", d1[d1['病例ID'] == case_id]['状态'].iloc[0])
print("D1数据列数:", len(d1.columns))

d2_case = d2[d2['病例ID'] == case_id]
if not d2_case.empty:
    print("D2状态:", d2_case['状态'].iloc[0])
    print("D2数据列数:", len(d2.columns))
    print("D2该行所有列（前10列）:")
    for col in list(d2.columns)[:10]:
        print(f"  {col}: {d2_case[col].iloc[0]}")
else:
    print("D2中无此病例")
