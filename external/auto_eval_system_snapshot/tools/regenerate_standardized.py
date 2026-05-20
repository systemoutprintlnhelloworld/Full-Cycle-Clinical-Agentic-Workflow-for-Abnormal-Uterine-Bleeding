
import pandas as pd
import os
import sys

# Setup path
sys.path.append(os.getcwd())
from auto_eval_system.modules.data_loader_strategy import FoshanStrategy

def regenerate():
    print("Regenerating standardized_foshan.xlsx using FIXED FoshanStrategy...")
    
    strat = FoshanStrategy()
    
    # Original Source File
    raw_file = "data/佛山医院-黄医生/佛山医生-前50例数据-修订并使用.xlsx"
    if not os.path.exists(raw_file):
        # Fallback search
        import glob
        files = glob.glob("data/佛山医院-黄医生/*.xlsx")
        if files: raw_file = files[0]
        else:
            print(f"Error: Original file not found at {raw_file}")
            return
            
    print(f"Loading from: {raw_file}")
    
    try:
        patients = strat.load_patients(raw_file)
        print(f"Loaded {len(patients)} patients.")
        
        if not patients:
            print("Error: No patients loaded.")
            return

        # Convert to DataFrame matching Standardized Format
        rows = []
        for p in patients:
            row = {
                "CaseID": p["case_id"],
                "Center": p["center"],
                "SourceFile": p["source_file"],
                "SourceRow": p["row_index"],
                "BasicInfo": p["basic_info"],
                "ChiefComplaint": p["chief_complaint"],
                "PresentIllness": p["present_illness"],
                "PastHistory": p["past_history"],
                "MenstrualHistory": p["menstrual_history"],
                "FamilyHistory": p["family_history"],
                "PhysicalExam": p["physical_exam"],
                "GT_Outpatient_Checks": p["gt_outpatient_checks"],
                "GT_Admission_Diagnosis": p["gt_admission_diagnosis"],
                "GT_Admission_Checks": p["gt_admission_checks"],
                "GT_Revised_Diagnosis": p["gt_revised_diagnosis"],
                "GT_Surgery_Plan": p["gt_surgery_plan"],
                "GT_PostOp_Plan": p["gt_post_op_plan"],
                "GT_Followup_Plan": p["gt_followup_plan"],
                "GT_Final_Diagnosis": p.get("gt_final_diagnosis", "无"),
                "GT_Surgery_Findings": p.get("gt_surgery_findings", "无"),
                "GT_Pathology": p.get("gt_pathology", "无"),
                "GT_Patient_Wishes": p.get("gt_patient_wishes", "无")
            }
            rows.append(row)
            
        df_new = pd.DataFrame(rows)
        out_path = "data/standardized_foshan_repaired.xlsx"
        df_new.to_excel(out_path, index=False)
        print(f"Saved standardized data to: {out_path}")
        
        # Try to replace original if possible
        orig_path = "data/standardized_foshan.xlsx"
        try:
            if os.path.exists(orig_path):
                os.remove(orig_path)
                os.rename(out_path, orig_path)
                print("Successfully overwrote original file.")
            else:
                os.rename(out_path, orig_path)
        except PermissionError:
             print(f"[Warning] Could not overwrite {orig_path} (File Open?). Data saved to {out_path}")
        except Exception as e:
             print(f"[Warning] Rename failed: {e}")
        
    except Exception as e:
        print(f"Error during regeneration: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    regenerate()
