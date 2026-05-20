
import pandas as pd
import json

path = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output\Foshan\gemini-2.5-pro\evaluation_gemini-2.5-pro.xlsx"
print(f"--- Verifying: {path} ---")

try:
    # 1. Check Gate JSON in Outpatient Decision
    df_gate = pd.read_excel(path, sheet_name="门诊决策")
    gate_col = [c for c in df_gate.columns if "Gate原始JSON" in c][0]
    # Find foshan_23
    row = df_gate[df_gate["病例ID"].astype(str).str.contains("foshan_23")]
    if not row.empty:
        val = row.iloc[0][gate_col]
        print("\n[Gate JSON for foshan_23]:")
        try:
            print(json.dumps(json.loads(val), indent=2, ensure_ascii=False)[:300] + "...")
        except:
            print(val)
    
    # 2. Check Loop Data
    df_loop = pd.read_excel(path, sheet_name="门诊检查循环")
    # Check headers
    print("\n[Loop Sheet Headers]:", [c for c in df_loop.columns if "第1轮" in c])
    
    row_l = df_loop[df_loop["病例ID"].astype(str).str.contains("foshan_23")]
    if not row_l.empty:
        req = row_l.iloc[0].get("第1轮_AI请求", "N/A")
        print(f"\n[Loop 1 AI Request]: {str(req)[:100]}...")
    else:
        print("foshan_23 not found in Loop Sheet.")

except Exception as e:
    print(f"Error: {e}")
