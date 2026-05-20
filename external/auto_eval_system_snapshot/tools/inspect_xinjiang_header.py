
import pandas as pd
path = r"data\新疆医院-乔医生\副本新疆医生-95例.xlsx"
df = pd.read_excel(path, header=None)

# Find header row
for i in range(5):
    row_str = " ".join([str(x) for x in df.iloc[i].values])
    if "主诉" in row_str:
        print(f"Header at Row {i}")
        # Print all non-null values in this row
        row = df.iloc[i]
        for col_idx, val in enumerate(row):
            if pd.notna(val) and str(val).strip() != "":
                print(f"Col {col_idx}: {val}")
        break
