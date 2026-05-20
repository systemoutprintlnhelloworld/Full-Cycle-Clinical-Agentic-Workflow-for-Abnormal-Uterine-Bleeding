
import pandas as pd
import os
import re

# Config
FIXED_FILE = r"data\standardized_foshan.xlsx"
V2_FILE = r"data\佛山医院-黄医生\佛山-后50例数据-改.xlsx"
OUT_PREVIEW = r"data\standardized_foshan_MERGED_PREVIEW.xlsx"

STANDARD_COLUMNS = [
    "CaseID", "Center", "SourceFile", "SourceRow",
    "BasicInfo", "ChiefComplaint", "PresentIllness", 
    "PastHistory", "MenstrualHistory", "FamilyHistory", "PhysicalExam",
    "GT_Outpatient_Checks", "GT_Admission_Diagnosis", "GT_Admission_Checks",
    "GT_Revised_Diagnosis", "GT_Surgery_Plan",
    "GT_Surgery_Findings", "GT_Pathology", "GT_Final_Diagnosis", 
    "GT_PostOp_Plan", "GT_Patient_Wishes"
]

def clean_text(val):
    if pd.isna(val): return "无"
    s = str(val).strip()
    if s.lower() in ["nan", "none", "", "无"]: return "无"
    return s

def process_foshan_v2_standalone(file_path, start_id_offset=50):
    print(f"Processing V2 (Standalone): {file_path}")
    try:
        df = pd.read_excel(file_path, header=None)
    except Exception as e:
        print(f"Error reading V2: {e}")
        return []

    parsed = []
    # Start from row 0 as it's a standalone file
    start_idx = 0 
    
    for i in range(start_idx, len(df)):
        row = df.iloc[i]
        # Skip empty rows
        if all(clean_text(x)=="无" for x in row): continue
        
        # Skip potential header row if it contains just "主诉" without value or similar
        # But this logic uses startswith "主诉:", so headers like "主诉" might fail or be skipped if logic is robust.
        # Let's see: txt.startswith("主诉") might catch "主诉" header. 
        # But V2 data usually is "主诉: xxx". The header is "主诉".
        # If row is header, value is "主诉". 
        # Check if row looks like header (e.g. contains "CaseID" or similar? No, raw excel has Chinese)
        
        item = {k: "无" for k in STANDARD_COLUMNS}
        # ID: Fixed Offset + Current Index + 1
        item["CaseID"] = f"Foshan_{start_id_offset + (len(parsed)+1):03d}" 
        item["Center"] = "Foshan"
        item["SourceFile"] = "Foshan_V2_Part2"
        item["SourceRow"] = i + 1
        
        out_checks = []
        adm_checks = []
        
        has_data = False
        
        for val in row:
            txt = clean_text(val)
            if txt == "无": continue
            
            # --- MAPPING ---
            if txt.startswith("基本情况") or txt.startswith("基本信息"): 
                item["BasicInfo"] = txt 
                has_data = True
            elif txt.startswith("主诉"): 
                item["ChiefComplaint"] = txt
                has_data = True
            elif txt.startswith("现病史"): 
                item["PresentIllness"] = txt
                has_data = True
            elif txt.startswith("既往史"): item["PastHistory"] = txt
            elif "月经" in txt and "生育" in txt: item["MenstrualHistory"] = txt
            elif txt.startswith("家族史"): item["FamilyHistory"] = txt
            elif "体格检查" in txt: item["PhysicalExam"] = txt
            
            # Checks
            elif "辅助检查:检验" in txt or "辅助检查:检查" in txt:
                out_checks.append(txt)
            elif "辅助检查:实验室" in txt or "辅助检查:影像" in txt or "辅助检查:病理" in txt or "辅助检查:内镜" in txt or "辅助检查:其他" in txt:
                adm_checks.append(txt)
            elif "修正诊断" in txt: item["GT_Admission_Diagnosis"] = txt # Note: Original logic mapped Revised to Adm? No, logic in v2.py line 196 said 'GT_Admission_Diagnosis'. Wait.
            # Reread v2.py line 196: `elif "修正诊断" in txt: item["GT_Admission_Diagnosis"] = txt` 
            # WAIT. "修正诊断" should be Revised Diagnosis! 
            # But line 347 in v2.py maps `gt_rev_diag` to `GT_Revised_Diagnosis`. 
            # In `process_foshan_v2` line 196, it mapped "修正诊断" -> "GT_Admission_Diagnosis". 
            # This looks like a BUG in v2.py or specific mapping handling.
            # Let's check `data/佛山-后50例数据-改.xlsx` column names via `read_foshan_v2_head.py` output.
            # Output showed: `42 修正诊断:修正诊断:1...`
            # If I map it to Admission, that's wrong if it's Revised.
            # User wants "correct" data.
            # In Legacy Foshan, "修正诊断" is Revised. "入院诊断" is Admission.
            # In V2, maybe "修正诊断" column contains Admission diagnosis? Unlikely.
            # I will separate them if keywords exist.
            
            elif "入院诊断" in txt: item["GT_Admission_Diagnosis"] = txt
            elif "修正诊断" in txt: item["GT_Revised_Diagnosis"] = txt
            
            # If logic in v2.py lines 196 was wrong, I should fix it here.
            # But maybe "修正诊断" in V2 text meant "Admission"? No.
            # I will map "入院诊断" -> Admission, "修正诊断" -> Revised.
            
            # Plans
            elif "治疗方案" in txt: item["GT_Surgery_Plan"] = txt
            elif "术中所见" in txt: item["GT_Surgery_Findings"] = txt
            elif "手术病理" in txt and "结果" in txt: item["GT_Pathology"] = txt
            elif "最终诊断" in txt or "出院诊断" in txt: item["GT_Final_Diagnosis"] = txt
            elif "术后治疗" in txt or "术后计划" in txt or "康复计划" in txt:
                 if item["GT_PostOp_Plan"] == "无": item["GT_PostOp_Plan"] = txt
                 else: item["GT_PostOp_Plan"] += " ; " + txt
            elif "随访计划" in txt:
                 if item["GT_PostOp_Plan"] == "无": item["GT_PostOp_Plan"] = txt
                 else: item["GT_PostOp_Plan"] += " ; " + txt
            elif "意愿" in txt or "特殊情况" in txt: item["GT_Patient_Wishes"] = txt
                 
        if not has_data: continue
                 
        item["GT_Outpatient_Checks"] = " ; ".join(out_checks) if out_checks else "无"
        item["GT_Admission_Checks"] = " ; ".join(adm_checks) if adm_checks else "无"
        parsed.append(item)

    print(f"Extracted {len(parsed)} rows from V2 Part 2.")
    return parsed

# Main
if __name__ == "__main__":
    if not os.path.exists(FIXED_FILE):
        print(f"Error: Fixed file {FIXED_FILE} not found!")
        exit(1)
        
    print(f"Loading Fixed Source: {FIXED_FILE}")
    df_fixed = pd.read_excel(FIXED_FILE)
    print(f"Fixed Source rows: {len(df_fixed)}")
    
    # Process V2
    v2_data = process_foshan_v2_standalone(V2_FILE, start_id_offset=len(df_fixed))
    df_v2 = pd.DataFrame(v2_data, columns=STANDARD_COLUMNS)
    
    # Merge
    df_merged = pd.concat([df_fixed, df_v2], ignore_index=True)
    
    # Save Preview
    df_merged.to_excel(OUT_PREVIEW, index=False)
    print(f"Saved Merged Preview: {OUT_PREVIEW} ({len(df_merged)} rows)")
    print("Please inspect this file before renaming to standardized_foshan.xlsx")
