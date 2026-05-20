import pandas as pd
import os
import glob

base_dir = r"d:/研究生/项目/课题7-临床评测/自动测评系统/data"

def inspect_file(filepath, center_name):
    print(f"\n--- Inspecting {center_name}: {os.path.basename(filepath)} ---")
    try:
        # Read first 10 rows without header initially to see the layout
        df_preview = pd.read_excel(filepath, header=None, nrows=10)
        print("Raw Top 5 Rows:")
        print(df_preview.head(5).to_string())
        
        # Try to guess header row (User said row 4 usually, which is index 3)
        # But Foshan first 50 might be different.
        print("\nAttempting to read with header=1 (Row 2) and header=3 (Row 4)...")
        
        try:
            df_h1 = pd.read_excel(filepath, header=1, nrows=2)
            print(f"Header Row=2 Columns: {list(df_h1.columns)[:5]} ...")
        except:
            pass

        try:
            df_h3 = pd.read_excel(filepath, header=3, nrows=2)
            print(f"Header Row=4 Columns: {list(df_h3.columns)[:5]} ...")
        except:
            pass

    except Exception as e:
        print(f"Error reading {filepath}: {e}")

centers = {
    "Foshan": os.path.join(base_dir, "佛山医院-黄医生"),
    "Xinjiang": os.path.join(base_dir, "新疆医院-乔医生"),
    "Wuhan": os.path.join(base_dir, "武汉医院-杨医生")
}

for center, path in centers.items():
    files = glob.glob(os.path.join(path, "*.xlsx"))
    for f in files:
        if "~$" in f: continue
        inspect_file(f, center)
