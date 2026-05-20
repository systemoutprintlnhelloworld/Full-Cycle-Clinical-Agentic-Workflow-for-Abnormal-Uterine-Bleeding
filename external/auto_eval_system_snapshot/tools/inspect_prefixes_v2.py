
import pandas as pd

files = [
    ("FoshanV2", r"data\佛山医院-黄医生\佛山-后50例数据-改.xlsx", 60),
    ("Xinjiang", r"data\新疆医院-乔医生\副本新疆医生-95例.xlsx", 4)
]

for name, f, ridx in files:
    print(f"\n=== {name} (Row {ridx}) ===")
    try:
        df = pd.read_excel(f, header=None)
        if len(df) > ridx:
            row = df.iloc[ridx]
            for i, val in enumerate(row):
                s = str(val).strip()
                if s and s not in ["nan", "无"]:
                    # Print first 15 chars
                    print(f"{i}: {s[:15]}")
        else:
            print("Row index out of bounds")
    except Exception as e:
        print(e)
