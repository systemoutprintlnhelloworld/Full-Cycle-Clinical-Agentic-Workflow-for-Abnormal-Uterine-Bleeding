
import pandas as pd
import os

files = [
    r"d:\研究生\项目\课题7-临床评测\自动测评系统\data\standardized_foshan.xlsx",
    r"d:\研究生\项目\课题7-临床评测\自动测评系统\data\武汉医院-杨医生\武汉杨医生-100例-正式测评.xlsx"
]

for f in files:
    print(f"\n{'='*20}\nFile: {os.path.basename(f)}")
    if not os.path.exists(f):
        print("File not found!")
        continue
    
    # Try reading first few rows to confirm header location
    try:
        df_head = pd.read_excel(f, nrows=5, header=None)
        print("First 5 rows (raw):")
        print(df_head)
    except Exception as e:
        print(f"Error reading file: {e}")
