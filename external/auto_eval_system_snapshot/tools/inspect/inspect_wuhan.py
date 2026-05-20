import pandas as pd

def inspect_wuhan_raw(file_path):
    print(f"Reading: {file_path}")
    try:
        # Read without header to check raw grid
        df = pd.read_excel(file_path, header=None)
    except Exception as e:
        print(f"Error: {e}")
        return

    # Target Row: 5th row (Index 4) -> 'wuhan_5'
    target_row_idx = 4
    if len(df) <= target_row_idx:
        print("File has fewer than 5 rows!")
        return

    row = df.iloc[target_row_idx]
    
    print(f"\n--- Intepecting Row {target_row_idx+1} (Index {target_row_idx}) ---")
    
    # Print first 30 columns with their Index and Value
    for i in range(30):
        if i < len(row):
            val = str(row[i])[:50].replace('\n', ' ')  # Truncate and flatten
            print(f"Index {i} (Col {chr(65+i) if i<26 else 'AA..'}): {val}")

if __name__ == "__main__":
    file_path = r'd:\研究生\项目\课题7-临床评测\自动测评系统\data\武汉医院-杨医生\武汉杨医生-100例-正式测评.xlsx'
    inspect_wuhan_raw(file_path)
