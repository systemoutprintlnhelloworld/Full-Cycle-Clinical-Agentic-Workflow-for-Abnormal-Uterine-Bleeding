
import pandas as pd
import os
import json

ref_path = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output\Foshan\grok-4\evaluation_grok-4.xlsx"
print(f"--- Inspecting Reference: {ref_path} ---")

try:
    xl = pd.ExcelFile(ref_path)
    print(f"Sheets: {xl.sheet_names}")
    
    for sheet in xl.sheet_names:
        print(f"\n[Sheet: {sheet}]")
        df = xl.parse(sheet)
        print(f"Columns: {list(df.columns)}")
        if not df.empty:
            row0 = df.iloc[0].to_dict()
            # Print non-null values to see what 'good' data looks like
            clean_row = {k: str(v)[:100] for k, v in row0.items() if pd.notna(v)}
            print(f"Sample Row (First 100 chars): {json.dumps(clean_row, ensure_ascii=False, indent=2)}")
            
            # Specifically check Gate/Judge columns if present
            gate_col = [c for c in df.columns if "Gate" in c and "JSON" in c]
            if gate_col:
                print(f"Gate JSON Sample: {row0.get(gate_col[0])}")

except Exception as e:
    print(f"Error reading excel: {e}")
