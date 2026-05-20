
import pandas as pd

file_path = r"data\佛山医院-黄医生\佛山-后50例数据-改.xlsx"
df = pd.read_excel(file_path, header=None)

print("-" * 50)
print("Row 0 Non-Null:")
print(df.iloc[0].dropna().to_dict())
print("-" * 50)
print("Row 1 Non-Null:")
print(df.iloc[1].dropna().to_dict())
print("-" * 50)
print("Row 2 Non-Null:")
print(df.iloc[2].dropna().to_dict())
print("-" * 50)
print("Row 3 Non-Null:")
print(df.iloc[3].dropna().to_dict())
