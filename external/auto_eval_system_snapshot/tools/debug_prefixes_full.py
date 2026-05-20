
import pandas as pd
import re

file_path = r"data\佛山医院-黄医生\佛山-后50例数据-改.xlsx"
df = pd.read_excel(file_path, header=None)

# Set of unique prefixes (first 10 chars, split by colon)
prefixes = set()

start_idx = 56
print(f"Scanning rows {start_idx} to {len(df)}...")

for i in range(start_idx, len(df)):
    row = df.iloc[i]
    for val in row:
        s = str(val).strip()
        if s and s not in ["nan", "无"]:
            # Try to grab "Key:" or "Key::" pattern
            # Matches "characters" + "optional :" + "optional :"
            # But simpler: just split by colon usually works
            # Handle both English : and Chinese ：
            # Normalize colons
            s_norm = s.replace("：", ":")
            parts = s_norm.split(":")
            if len(parts) > 1:
                # Key is the part before first colon, or first 2 parts if double colon
                key = parts[0]
                # If double colon "Key::Value", split leaves empty string in middle?
                # "Key::Value" -> ["Key", "", "Value"]
                if parts[1] == "":
                     key += "::"
                else:
                     key += ":"
                prefixes.add(key)
            else:
                # No colon? Just grab first few chars
                prefixes.add(s[:6] + "...")

print("\n--- Unique Prefixes Found ---")
for p in sorted(list(prefixes)):
    print(p)
