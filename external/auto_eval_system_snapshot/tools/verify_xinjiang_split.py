
import pandas as pd

def verify_xinjiang_separation():
    df = pd.read_excel(r"data\standardized_xinjiang.xlsx")
    print(f"Total Rows: {len(df)}")
    
    # Check rows containing "超声" in ANY check column
    has_echo = df[df["GT_Admission_Checks"].astype(str).str.contains("超声") | 
                  df["GT_Outpatient_Checks"].astype(str).str.contains("超声")]
    
    print(f"Rows with Ultrasound: {len(has_echo)}")
    if len(has_echo) > 0:
        sample = has_echo.iloc[0]
        print("\n--- Sample Row ---")
        print(f"ID: {sample['CaseID']}")
        print(f"Outpatient: {sample['GT_Outpatient_Checks']}")
        print(f"Admission: {sample['GT_Admission_Checks']}")
        
        # Validation Logic
        if "超声" in str(sample["GT_Outpatient_Checks"]):
             print("\n[FAIL] Ultrasound found in Outpatient Checks!")
        elif "超声" in str(sample["GT_Admission_Checks"]):
             print("\n[PASS] Ultrasound found in Admission Checks.")
        else:
             print("\n[?] Ultrasound not found??")

if __name__ == "__main__":
    verify_xinjiang_separation()
