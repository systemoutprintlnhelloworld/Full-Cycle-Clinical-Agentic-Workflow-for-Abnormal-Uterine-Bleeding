import pandas as pd
import os

# 1. 验证 foshan_6 的分列情况 (gemini-2.5-pro)
print("=== 验证 foshan_6 分列情况 ===")
excel_path = r'D:\研究生\项目\课题7-临床评测\自动测评系统\output\Foshan-v2\gemini-2.5-pro\Evaluation_Summary_gemini-2.5-pro_CN.xlsx'
if os.path.exists(excel_path):
    df_d3 = pd.read_excel(excel_path, sheet_name='D3_Surgery_Decision')
    row = df_d3[df_d3['病例ID'] == 'foshan_6']
    if not row.empty:
        col_list = [c for c in df_d3.columns if '医生_原始JSON' in c]
        print(f"包含'医生_原始JSON'的列: {col_list}")
        for col in col_list:
            val = row[col].iloc[0]
            print(f"  {col} 长度: {len(str(val)) if pd.notna(val) else 'N/A'}")
    else:
        print("foshan_6 未找到")
else:
    print(f"文件不存在: {excel_path}")

print("\n=== 验证 foshan_36 归档情况 (gpt-5-2025-08-07) ===")
# 2. 验证 foshan_36 是否在 D1 Decision (gpt-5-2025-08-07)
excel_path_gpt = r'D:\研究生\项目\课题7-临床评测\自动测评系统\output\Foshan-v2\gpt-5-2025-08-07\Evaluation_Summary_gpt-5-2025-08-07_CN.xlsx'
if os.path.exists(excel_path_gpt):
    df_d1_dec = pd.read_excel(excel_path_gpt, sheet_name='D1_Outpatient_Decision')
    row = df_d1_dec[df_d1_dec['病例ID'] == 'foshan_36']
    if not row.empty:
        print("✅ foshan_36 已成功归档至 D1_Outpatient_Decision!")
        print(f"   状态: {row['状态'].iloc[0]}")
        print(f"   AI_初步诊断: {row['AI_初步诊断'].iloc[0]}")
    else:
        print("❌ foshan_36 未出现在 D1_Outpatient_Decision")
else:
    print(f"文件不存在: {excel_path_gpt}")
