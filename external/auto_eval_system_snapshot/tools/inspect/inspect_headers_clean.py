import pandas as pd
import os

def inspect_headers(file_path):
    print(f"Inspecting: {file_path}")
    if not os.path.exists(file_path):
        print("File not found.")
        return

    # Try header=0, 1, 2 to see where headers might be
    for h in [0, 1, 2, 3]:
        print(f"\n--- Header Row: {h} ---")
        try:
            df = pd.read_excel(file_path, header=h, nrows=0)
            print(list(df.columns))
        except Exception as e:
            print(f"Error: {e}")

# Path based on previous logs
file_path = r"d:\研究生\项目\课题7-临床评测\自动测评系统\data\佛山医院-黄医生\佛山-后50例数据-改.xlsx"
inspect_headers(file_path)
