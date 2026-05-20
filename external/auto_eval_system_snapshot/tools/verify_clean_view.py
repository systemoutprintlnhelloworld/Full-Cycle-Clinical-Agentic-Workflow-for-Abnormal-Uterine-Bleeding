import pandas as pd
import os
import glob

# Find a Parsed file
base_dir = r"D:\研究生\项目\课题7-临床评测\自动测评系统\测评结果"
parsed_files = glob.glob(os.path.join(base_dir, "**", "*_Parsed.xlsx"), recursive=True)

if not parsed_files:
    print("No parsed files found yet.")
    exit()

target_file = parsed_files[0]
print(f"Verifying: {target_file}")

df = pd.read_excel(target_file, sheet_name="D3_Surgery_Decision")
print(f"Columns in D3_Surgery_Decision ({len(df.columns)}):")
for col in df.columns[:10]:
    print(f"  - {col}")
if len(df.columns) > 10: print("  ... (and more)")

# Check if non-JSON columns exist (e.g. 'Status', 'Date', 'AI_Final_Diagnosis' - these should be GONE unless they are flattened keys)
# The flattened keys will be prefixed with the JSON column name.
# So if we see 'AI_Final_Diagnosis', it's BAD (failed to filter).
# If we see '医生_原始JSON_最终诊断_诊断名称', it's GOOD.

unexpected_cols = [c for c in df.columns if "JSON" not in c and "CaseID" not in c and "病例ID" not in c and "_" not in c]
# Note: flattened keys contain underscores. Original columns often do too.
# Use specific known columns that should be removed: e.g. "Center", "Model", "Duration"
banned_cols = ["Center", "Model", "Duration", "Total_Loops", "Gate1_Reason"]

found_banned = [c for c in df.columns if c in banned_cols]

if found_banned:
    print(f"❌ FAIL: Found banned columns: {found_banned}")
else:
    print("✅ PASS: No banned columns found. Clean view confirmed.")

# Check for JSON column presence
json_cols = [c for c in df.columns if "原始JSON" in c and "_" not in c.split("JSON")[1:]] # Heuristic
# Actually, just check if the base JSON column exists
print("JSON Base Columns present:")
print([c for c in df.columns if c.endswith("_原始JSON") or c == "原始JSON"])
