
import pandas as pd
import os

files = [r"data\standardized_foshan.xlsx", r"data\standardized_xinjiang.xlsx"]
for f in files:
    if os.path.exists(f):
        try:
            df = pd.read_excel(f)
            print(f"\nFile: {f}")
            print(f"Total Rows: {len(df)}")
            if len(df) > 0:
                print("First Row ID:", df.iloc[0]["CaseID"])
                print("Last Row ID:", df.iloc[-1]["CaseID"])
        except Exception as e:
            print(f"Error reading {f}: {e}")
    else:
        print(f"\nFile not found: {f}")
