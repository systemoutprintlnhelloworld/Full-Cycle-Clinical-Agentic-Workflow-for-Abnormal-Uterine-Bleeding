
import pandas as pd

try:
    df = pd.read_excel(r"data\standardized_foshan.xlsx")
    # Get V2 rows (start from index 53)
    df_v2 = df.iloc[53:].reset_index(drop=True)
    
    print(f"V2 Count: {len(df_v2)}")
    if len(df_v2) > 0:
        # Check first 5 rows
        cols_to_check = [
            "CaseID", "GT_Outpatient_Checks", "GT_Admission_Checks", 
            "GT_Surgery_Plan", "GT_Surgery_Findings", "GT_Pathology", "GT_Final_Diagnosis", "GT_PostOp_Plan"
        ]
        print(df_v2[cols_to_check].head(5).to_string())
        
        # Check if any are just "无"
        print("\n--- '无' Count per column (V2) ---")
        for c in cols_to_check:
            counts = (df_v2[c] == "无").sum()
            print(f"{c}: {counts} / {len(df_v2)}")
            
except Exception as e:
    print(e)
