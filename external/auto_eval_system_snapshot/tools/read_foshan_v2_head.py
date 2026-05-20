
import pandas as pd
import os

file_path = r"data\佛山医院-黄医生\佛山-后50例数据-改.xlsx"
try:
    df = pd.read_excel(file_path, header=None)
    print(f"Shape: {df.shape}")
    print("First 10 rows:")
    print(df.head(10))
    
    # Also print row 56 just in case
    if len(df) > 56:
        print("\nRow 56:")
        print(df.iloc[56])
except Exception as e:
    print(f"Error: {e}")
