
import pandas as pd

def check_foshan():
    print("\n=== CHECKING FOSHAN V3 ===")
    try:
        df = pd.read_excel(r"data\standardized_foshan.xlsx")
        
        # 1. Check Legacy (First 50 rows approx) for Check Separation
        print("\n--- Legacy Check Separation (Sample) ---")
        legacy_sample = df[df['CaseID'].str.contains("_L")].head(3)
        cols = ["CaseID", "GT_Outpatient_Checks", "GT_Admission_Checks"]
        print(legacy_sample[cols].to_string())
        
        # 2. Check V2 (Rows 53+) for Diagnosis and Checks
        print("\n--- V2 Diagnosis & Checks (Sample) ---")
        v2_sample = df.iloc[53:].head(3)
        cols_v2 = ["CaseID", "GT_Admission_Diagnosis", "GT_Outpatient_Checks", "GT_Admission_Checks"]
        print(v2_sample[cols_v2].to_string())
        
        # 3. Stats for V2 Diagnosis
        v2_full = df.iloc[53:]
        missing_diag = (v2_full["GT_Admission_Diagnosis"] == "无").sum()
        print(f"\nV2 Missing Admission Diagnosis: {missing_diag} / {len(v2_full)}")

    except Exception as e:
        print(e)

def check_xinjiang():
    print("\n=== CHECKING XINJIANG V3 ===")
    try:
        df = pd.read_excel(r"data\standardized_xinjiang.xlsx")
        
        print("\n--- Xinjiang Check Separation (Sample) ---")
        sample = df.head(3)
        cols = ["CaseID", "GT_Outpatient_Checks", "GT_Admission_Checks"]
        print(sample[cols].to_string())
        
        # Check if they are distinct
        # Basic heuristic: Outpatient checks shouldn't contain "实验室" usually
    except Exception as e:
        print(e)

if __name__ == "__main__":
    check_foshan()
    check_xinjiang()
