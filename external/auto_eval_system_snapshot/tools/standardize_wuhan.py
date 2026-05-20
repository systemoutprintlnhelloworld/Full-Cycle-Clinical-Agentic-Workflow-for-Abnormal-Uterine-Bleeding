import pandas as pd
import os

def standardize_wuhan(file_path):
    print(f"Reading source: {file_path}")
    try:
        df = pd.read_excel(file_path, header=None)
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return

    standardized_data = []

    def clean_cell(val):
        if pd.isna(val) or str(val).strip() == "" or str(val).lower() == "nan":
            return ""
        return str(val).strip()

    def normalize_gender(val):
        s = clean_cell(val)
        if "男" in s: return "男"
        if "女" in s: return "女"
        return s

    start_row_index = 4 
    
    for index, row in df.iterrows():
        if index < start_row_index:
            continue
            
        # 1. Meta
        case_id = f"wuhan_{index + 1}"
        center = "Wuhan"
        source_row = index + 1
        
        # 2. BasicInfo: C(2) + D(3)
        c_val = clean_cell(row.iloc[2])
        d_val = clean_cell(row.iloc[3])
        basic_info = f"{c_val} {d_val}".strip()

        # 3. ChiefComplaint: E(4)
        chief_complaint = clean_cell(row.iloc[4])

        # 4. PresentIllness: F(5)
        present_illness = clean_cell(row.iloc[5])

        # 5. MenstrualHistory: G(6)
        menstrual_history = clean_cell(row.iloc[6])

        # 6. PastHistory: H(7)
        past_history = clean_cell(row.iloc[7])

        # 7. FamilyHistory: I(8)
        family_history = clean_cell(row.iloc[8])

        # 8. PhysicalExam: J(9)
        physical_exam = clean_cell(row.iloc[9])

        # 9. GT_Outpatient_Checks: K(10) + L(11)
        out_checks = []
        k_val = clean_cell(row.iloc[10])
        l_val = clean_cell(row.iloc[11])
        if k_val: out_checks.append(k_val)
        if l_val: out_checks.append(l_val)
        gt_out_checks = "\n".join(out_checks) if out_checks else "无"

        # 10. GT_Admission_Diagnosis: M(12) + N(13)
        prelim_parts = []
        val_m = clean_cell(row.iloc[12])
        val_n = clean_cell(row.iloc[13])
        if val_m: prelim_parts.append(val_m)
        if val_n: prelim_parts.append(val_n)
        gt_adm_diag = "\n".join(prelim_parts) if prelim_parts else "无"

        # 11. GT_Admission_Checks: O(14) - S(18)
        adm_checks = []
        for i in range(14, 19): 
            val = clean_cell(row.iloc[i])
            if val: adm_checks.append(val)
        gt_adm_checks = "\n".join(adm_checks) if adm_checks else "无"

        # 12. GT_Revised_Diagnosis: T(19)
        gt_revised_diag = clean_cell(row.iloc[19])
        if not gt_revised_diag: gt_revised_diag = "无"

        # 13. GT_Surgery_Plan: U(20)
        gt_surg_plan = clean_cell(row.iloc[20])

        # 14. GT_PostOp_Plan: Y(24) "术后治疗"
        gt_postop_plan = clean_cell(row.iloc[24])
        if not gt_postop_plan: gt_postop_plan = "无"

        # 15. GT_Rehab_Plan: None/Empty?
        gt_rehab_plan = "无"

        # 16. GT_Followup_Plan: AA(26) "出院医嘱"
        gt_followup_plan = clean_cell(row.iloc[26])
        if not gt_followup_plan: gt_followup_plan = "无"

        # 17. GT_Final_Diagnosis: X(23)
        gt_final_diag = clean_cell(row.iloc[23])

        # 18. GT_Surgery_Findings: V(21)
        gt_surg_findings = clean_cell(row.iloc[21])

        # 19. GT_Pathology: W(22)
        gt_pathology = clean_cell(row.iloc[22])

        # 20. GT_Patient_Wishes: Z(25)
        gt_patient_wishes = clean_cell(row.iloc[25])

        if not chief_complaint and not present_illness and case_id != "wuhan_5":
             continue

        # Data map with exact keys
        case_data = {
            "CaseID": case_id,
            "Center": center,
            # SourceFile omitted
            "SourceRow": source_row,
            "BasicInfo": basic_info,
            "ChiefComplaint": chief_complaint,
            "PresentIllness": present_illness,
            "PastHistory": past_history,
            "MenstrualHistory": menstrual_history,
            "FamilyHistory": family_history,
            "PhysicalExam": physical_exam,
            "GT_Outpatient_Checks": gt_out_checks,
            "GT_Admission_Diagnosis": gt_adm_diag,
            "GT_Admission_Checks": gt_adm_checks,
            "GT_Revised_Diagnosis": gt_revised_diag,
            "GT_Surgery_Plan": gt_surg_plan,
            "GT_PostOp_Plan": gt_postop_plan,
            "GT_Rehab_Plan": gt_rehab_plan,
            "GT_Followup_Plan": gt_followup_plan,
            "GT_Final_Diagnosis": gt_final_diag,
            "GT_Surgery_Findings": gt_surg_findings,
            "GT_Pathology": gt_pathology,
            "GT_Patient_Wishes": gt_patient_wishes
        }
        
        standardized_data.append(case_data)

    standardized_df = pd.DataFrame(standardized_data)
    
    # Enforce EXACT order from verified Foshan list
    cols_order = [
        "CaseID", "Center", "SourceRow", "BasicInfo", 
        "ChiefComplaint", "PresentIllness", "PastHistory", "MenstrualHistory", 
        "FamilyHistory", "PhysicalExam", 
        "GT_Outpatient_Checks", "GT_Admission_Diagnosis", "GT_Admission_Checks", 
        "GT_Revised_Diagnosis", "GT_Surgery_Plan", 
        "GT_PostOp_Plan", "GT_Rehab_Plan", "GT_Followup_Plan", 
        "GT_Final_Diagnosis", "GT_Surgery_Findings", "GT_Pathology", 
        "GT_Patient_Wishes"
    ]
    
    # Check for missing columns in our data map
    # (Assuming all keys above match)
    
    standardized_df = standardized_df[cols_order]
    
    output_path = r'data\standardized_wuhan.xlsx'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    standardized_df.to_excel(output_path, index=False)
    print(f"Standardized data saved to {output_path}")
    print("Final Columns:", list(standardized_df.columns))

if __name__ == "__main__":
    file_path = r'd:\研究生\项目\课题7-临床评测\自动测评系统\data\武汉医院-杨医生\武汉杨医生-100例-正式测评.xlsx'
    standardize_wuhan(file_path)
