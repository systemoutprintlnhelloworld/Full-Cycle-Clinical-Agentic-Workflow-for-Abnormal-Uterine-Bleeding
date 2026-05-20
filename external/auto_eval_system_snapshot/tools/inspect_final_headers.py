
import pandas as pd

def check_headers():
    files = [
        r"data\standardized_foshan.xlsx",
        r"data\standardized_xinjiang.xlsx"
    ]
    
    for f in files:
        try:
            df = pd.read_excel(f, nrows=0)
            print(f"File: {f}")
            print(f"Columns: {list(df.columns)}")
            print("-" * 30)
        except Exception as e:
            print(f"Error reading {f}: {e}")

if __name__ == "__main__":
    check_headers()
