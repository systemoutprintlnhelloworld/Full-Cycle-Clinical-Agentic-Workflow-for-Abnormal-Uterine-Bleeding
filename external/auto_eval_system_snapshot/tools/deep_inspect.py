
import pandas as pd
import os

files = {
    "Foshan_Legacy": r"data\佛山医院-黄医生\佛山医生-前50例数据-修订并使用.xlsx",
    "Foshan_V2": r"data\佛山医院-黄医生\佛山-后50例数据-改.xlsx",
    "Xinjiang": r"data\新疆医院-乔医生\副本新疆医生-95例.xlsx"
}

def inspect_foshan_legacy(path):
    print(f"\n=== INSPECTING: {path} ===")
    try:
        df = pd.read_excel(path, header=None)
        # Dump first 5 rows to see headers
        print("--- First 5 Rows (Raw) ---")
        print(df.iloc[:5].to_string())
        
        # Try to detect "Key" rows
        for i in range(5):
            row = df.iloc[i].astype(str).tolist()
            if any("主诉" in x for x in row):
                print(f"[!] Possible Header at Row {i}")
    except Exception as e:
        print(f"Error: {e}")

def inspect_xinjiang(path):
    print(f"\n=== INSPECTING: {path} ===")
    try:
        df = pd.read_excel(path, header=None)
        print("--- First 5 Rows (Raw) ---")
        print(df.iloc[:5].to_string())
        
        for i in range(5):
            row = df.iloc[i].astype(str).tolist()
            if any("主诉" in x for x in row):
                print(f"[!] Possible Header at Row {i}")
    except Exception as e:
        print(f"Error: {e}")

def inspect_foshan_v2_diagnosis(path):
    print(f"\n=== INSPECTING V2 DIAGNOSIS: {path} ===")
    try:
        df = pd.read_excel(path, header=None)
        start_idx = 56
        count = 0
        print(f"Scanning from row {start_idx} for '修正诊断'...")
        for i in range(start_idx, len(df)):
            row = df.iloc[i]
            found = False
            for val in row:
                s = str(val).strip()
                if "修正诊断" in s:
                    print(f"Row {i} MATCH: '{s}' (Repr: {repr(s)})")
                    found = True
            if not found:
                 pass # Too much output to print mismatch
            else:
                 count += 1
            if count >= 5: break # Just showing first 5 matches
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_foshan_legacy(files["Foshan_Legacy"])
    inspect_xinjiang(files["Xinjiang"])
    inspect_foshan_v2_diagnosis(files["Foshan_V2"])
