import pandas as pd
import os

def inspect_headers(file_path):
    print(f"=== Inspecting Headers for {os.path.basename(file_path)} ===")
    
    # Read first 5 rows to see the header structure
    df_raw = pd.read_excel(file_path, header=None, nrows=5)
    print("\n[Raw First 5 Rows]:")
    print(df_raw.to_string())

    print("\n[Analysis]:")
    # Check for "辅助检查"
    for r_idx, row in df_raw.iterrows():
        row_str = row.astype(str).tolist()
        if any("辅助检查" in s for s in row_str):
            print(f"-> Found '辅助检查' at Row {r_idx}")
        if any("入院检查" in s for s in row_str):
            print(f"-> Found '入院检查' at Row {r_idx}")
        if any("门诊检查" in s for s in row_str):
            print(f"-> Found '门诊检查' at Row {r_idx}")

    print("\n" + "="*50 + "\n")

# Target Data
data_dir = r"data\佛山医院-黄医生"
files = [f for f in os.listdir(data_dir) if f.endswith(".xlsx") and not f.startswith("~$")]

for f in files:
    inspect_headers(os.path.join(data_dir, f))
