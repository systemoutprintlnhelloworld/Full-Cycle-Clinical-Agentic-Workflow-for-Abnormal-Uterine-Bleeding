
import pandas as pd
import os

try:
    df_f = pd.read_excel(r"data\standardized_foshan.xlsx")
    print(f"FOSHAN_COUNT: {len(df_f)}")
    if len(df_f) > 0:
        print(f"FOSHAN_HEAD: {df_f.iloc[0]['CaseID']}")
        print(f"FOSHAN_TAIL: {df_f.iloc[-1]['CaseID']}")
except Exception as e:
    print(f"FOSHAN_ERROR: {e}")

try:
    df_x = pd.read_excel(r"data\standardized_xinjiang.xlsx")
    print(f"XINJIANG_COUNT: {len(df_x)}")
except Exception as e:
    print(f"XINJIANG_ERROR: {e}")
