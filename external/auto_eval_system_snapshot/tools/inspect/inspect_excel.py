
import pandas as pd
import os

def inspect_excel(filepath):
    print(f"--- Inspecting {os.path.basename(filepath)} ---")
    try:
        df = pd.read_excel(filepath, nrows=2) 
        print("Columns:", list(df.columns))
        print("First row data:", df.iloc[0].to_dict())
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    print("\n")

base_dir = r"d:/研究生/项目/课题7-临床评测/自动测评系统/ref"
files_to_inspect = [
    os.path.join(base_dir, "AI/gemini-2.5-pro.xlsx"),
    os.path.join(base_dir, "GT/gemini-2.5-pro.xlsx"), 
    os.path.join(base_dir, "Context/gemini-2.5-pro.xlsx")
]

for f in files_to_inspect:
    if os.path.exists(f):
        inspect_excel(f)
    else:
        print(f"File not found: {f}")
