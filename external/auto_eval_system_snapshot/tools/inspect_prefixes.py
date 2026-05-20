
import pandas as pd

files = [
    r"data\佛山医院-黄医生\佛山-后50例数据-改.xlsx",
    r"data\新疆医院-乔医生\副本新疆医生-95例.xlsx"
]

for f in files:
    print(f"\nScanning: {f}")
    try:
        df = pd.read_excel(f, header=None)
        # User said "Look at the 5th row". Index 4.
        row_idx = 4
        if len(df) > row_idx:
            row = df.iloc[row_idx]
            print(f"Row {row_idx} (Index {row_idx}):")
            for col_i, val in enumerate(row):
                s = str(val).strip()
                if s and s != "nan":
                    # Print first 20 chars to see prefix
                    print(f"  Col {col_i}: {s[:30]}...")
        else:
            print("File has fewer than 5 rows.")
    except Exception as e:
        print(f"Error: {e}")
