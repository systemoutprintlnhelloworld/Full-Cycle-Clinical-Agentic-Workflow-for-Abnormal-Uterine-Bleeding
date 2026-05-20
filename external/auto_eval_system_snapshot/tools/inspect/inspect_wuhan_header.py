import pandas as pd
import sys

# Set output encoding to utf-8
sys.stdout.reconfigure(encoding='utf-8')

file_path = r'd:\研究生\项目\课题7-临床评测\自动测评系统\data\武汉医院-杨医生\武汉杨医生-100例-正式测评.xlsx'

try:
    # Read row 3 (which is the 4th row, containing column headers like '主诉')
    df = pd.read_excel(file_path, header=3, nrows=0)
    
    with open('wuhan_headers.txt', 'w', encoding='utf-8') as f:
        f.write("Columns in Row 3 (Index 3):\n")
        for i, col in enumerate(df.columns):
            f.write(f"Index {i}: {col}\n")
            
    # Also check if there are any merged headers in previous rows
    df_raw = pd.read_excel(file_path, header=None, nrows=4)
    with open('wuhan_raw_rows.txt', 'w', encoding='utf-8') as f:
         f.write(df_raw.to_string())

    print("Headers saved to wuhan_headers.txt and wuhan_raw_rows.txt")

except Exception as e:
    print(f"Error: {e}")
