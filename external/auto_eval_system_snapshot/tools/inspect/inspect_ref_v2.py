
import pandas as pd
import json

ref_path = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output\Foshan\grok-4\evaluation_grok-4.xlsx"
print(f"--- Finding Valid Gate JSON in: {ref_path} ---")

try:
    xl = pd.ExcelFile(ref_path)
    df = xl.parse("门诊决策") # Sheet name with Gate
    
    # Find col
    gate_cols = [c for c in df.columns if "Gate" in c and "JSON" in c]
    if not gate_cols:
        print("No Gate JSON column found in Sheet '门诊决策'")
    else:
        col = gate_cols[0]
        print(f"Inspecting Column: {col}")
        
        # Find first non-na
        valid_rows = df[df[col].notna()]
        if not valid_rows.empty:
            val = valid_rows.iloc[0][col]
            print(f"Found Value in Row {valid_rows.index[0]}:")
            try:
                # Try pretty print
                obj = json.loads(val)
                print(json.dumps(obj, ensure_ascii=False, indent=2))
            except:
                print(val)
        else:
            print("All values in Gate JSON column are NaN.")

except Exception as e:
    print(f"Error: {e}")
