
import pandas as pd
import os
import re

# ==========================================
# Configuration
# ==========================================
SOURCE_FILES = [
    {
        "center": "Foshan",
        "path": r"data\佛山医院-黄医生\佛山医生-前50例数据-修订并使用.xlsx",
        "strategy": "foshan_legacy" # Assuming similar to updated but check headers
    },
    {
        "center": "Foshan",
        "path": r"data\佛山医院-黄医生\佛山-后50例数据-改.xlsx",
        "strategy": "foshan_v2"
    },
    {
        "center": "Xinjiang",
        "path": r"data\新疆医院-乔医生\副本新疆医生-95例.xlsx",
        "strategy": "xinjiang"
    }
]

OUTPUT_FILE = r"data\standardized_eval_dataset.xlsx"

STANDARD_COLUMNS = [
    "CaseID", "Center", "SourceFile", "SourceRow",
    "BasicInfo", "ChiefComplaint", "PresentIllness", 
    "PastHistory", "MenstrualHistory", "FamilyHistory", "PhysicalExam",
    "GT_Outpatient_Checks", "GT_Admission_Diagnosis", "GT_Admission_Checks",
    "GT_Revised_Diagnosis", "GT_Surgery_Plan",
    "GT_Surgery_Findings", "GT_Pathology", "GT_Final_Diagnosis", 
    "GT_PostOp_Plan", "GT_Patient_Wishes"
]

# ==========================================
# Helper Functions
# ==========================================
def clean_text(val):
    if pd.isna(val): return "无"
    s = str(val).strip()
    if s.lower() in ["nan", "none", "", "无"]: return "无"
    return s

def find_header_row(df, keywords):
    """Scan first 10 rows to find header"""
    for i in range(min(10, len(df))):
        row_str = " ".join([str(x) for x in df.iloc[i].values])
        # Relaxed check: Match any key keyword (e.g. 主诉 is distinctive enough)
        # But ensure it's not a data row (data row also contains 主诉 value?? No mainly text)
        # Usually Header row has "主诉" literally.
        count = sum(1 for k in keywords if k in row_str)
        if count >= 1: # At least one match
             return i
    return 0

def get_col_idx(headers, keywords):
    """Find column index by fuzzy matching keywords in list of headers"""
    for idx, h in enumerate(headers):
        h_str = str(h).replace("\n", "")
        if any(k in h_str for k in keywords):
            return idx
    return -1

def get_col_indices(headers, keywords):
    """Return all indices matching keywords"""
    indices = []
    for idx, h in enumerate(headers):
        h_str = str(h).replace("\n", "")
        if any(k in h_str for k in keywords):
            indices.append(idx)
    return indices

# ==========================================
# Processing Strategies
# ==========================================
def process_foshan(file_path, version="v2"):
    print(f"Processing Foshan ({version}): {file_path}")
    try:
        # Load Raw to inspect headers manually
        df_raw = pd.read_excel(file_path, header=None)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return []

    # 1. Find the "Main" Header Row (Contains "主诉", "入院诊断")
    header_idx = find_header_row(df_raw, ["主诉", "入院诊断"])
    print(f"  > Detected Header Row at Index: {header_idx}")
    
    # Extract headers for mapping (handling multi-row context if needed)
    # Foshan headers might be split across rows (e.g. Row 2: "辅助检查", Row 3: "门诊", "入院")
    # We construct a composite header list from Header Row down to Data Start
    
    # Heuristic: Data starts 1 or 2 rows after Header
    # Let's inspect rows around header_idx
    # L1 = header_idx, L2 = header_idx + 1
    
    # Build Composite Headers (L1 + L2)
    l1 = df_raw.iloc[header_idx].fillna(method='ffill').astype(str).values
    try:
        l2 = df_raw.iloc[header_idx+1].fillna("").astype(str).values
    except:
        l2 = [""] * len(l1)
        
    cols = []
    for i in range(len(l1)):
        c1 = l1[i].replace("nan", "")
        c2 = l2[i].replace("nan", "")
        cols.append(f"{c1}_{c2}")
    
    # Identify Data Start Row: Look for numeric index or valid content
    data_start_idx = header_idx + 2
    # Determine if Row (header_idx+1) is sub-header or data
    # If L2 contains keywords like "门诊", "入院", it's subheader.
    if any(x in " ".join(l2) for x in ["门诊", "入院", "术中", "术后"]):
         data_start_idx = header_idx + 2
    else:
         data_start_idx = header_idx + 1
         
    print(f"  > Data starts at Index: {data_start_idx}")

    # Column Mapping Logic (Index based on Composite Headers)
    def find_indices(keywords, exclude=None):
        idxs = []
        for i, c in enumerate(cols):
            if any(k in c for k in keywords):
                if exclude and any(e in c for e in exclude):
                    continue
                idxs.append(i)
        return idxs

    # Mappings
    # Basic Info: Often "基本情况" or split
    # For simplicity, we grab all columns before "主诉" as Basic Info
    idx_cc = find_indices(["主诉"])[0] if find_indices(["主诉"]) else 0
    idx_basic_range = list(range(0, idx_cc))
    
    # Specifics
    i_cc = find_indices(["主诉"])
    i_pi = find_indices(["现病史"])
    i_ph = find_indices(["既往史"])
    i_mh = find_indices(["月经", "婚育", "生育"])
    i_fh = find_indices(["家族史"])
    i_pe = find_indices(["体格检查", "专科检查", "妇科检查"])
    
    # Checks - Crucial Split
    # "辅助检查_门诊", "辅助检查_入院"
    # Or L1="辅助检查", L2="门诊"
    i_out_checks = find_indices(["门诊"], exclude=["诊断"])
    if not i_out_checks: # Fallback
         i_out_checks = find_indices(["辅助检查"], exclude=["入院", "诊断"])
         
    i_adm_checks = find_indices(["入院", "术前"], exclude=["诊断", "处理", "小结", "前准备"])
    # Filter to ensure it's check related
    i_adm_checks = [x for x in i_adm_checks if "检查" in cols[x] or "检验" in cols[x] or "病理" in cols[x] or "影像" in cols[x]]

    i_adm_diag = find_indices(["入院诊断", "初步诊断"])
    i_rev_diag = find_indices(["修正诊断", "确定诊断"])
    i_surg_plan = find_indices(["手术方案", "拟施手术"])
    
    i_surg_find = find_indices(["术中所见"])
    i_patho = find_indices(["术后病理", "石蜡病理", "大体病理"])
    i_final_diag = find_indices(["最终诊断", "出院诊断", "术后诊断"])
    i_post_plan = find_indices(["术后治疗", "术后医嘱"])
    i_wishes = find_indices(["意愿", "特殊情况"])

    print(f"  > Indices: CC={idx_cc} (Range: {i_cc}), Basic={idx_basic_range}, ValidOutChecks={i_out_checks}, ValidAdmChecks={i_adm_checks}")
    print(f"  > Inspecting Row {data_start_idx} (First Data Row):")
    first_row = df_raw.iloc[data_start_idx]
    print(f"    CC Value: {clean_text(first_row[idx_cc])}")

    parsed_rows = []
    
    for i in range(data_start_idx, len(df_raw)):
        row = df_raw.iloc[i]
        
        # Check valid row (Must have CC or Diagnosis)
        val_cc = clean_text(row[idx_cc])
        val_diag = clean_text(row[i_adm_diag[0]]) if i_adm_diag else "无"
        
        if val_cc == "无" and val_diag == "无":
            # Debug: Print why skipped first few times
            if i < data_start_idx + 5:
                 print(f"    Skipping Row {i}: CC='{val_cc}', Diag='{val_diag}'")
            continue

        def get_vals(indices):
            v_list = []
            seen = set()
            for idx in indices:
                if idx < len(row):
                    val = clean_text(row[idx])
                    if val != "无" and val not in seen:
                        v_list.append(val)
                        seen.add(val)
            return " ; ".join(v_list) if v_list else "无"

        # Case ID Logic
        case_id = f"Foshan_{len(parsed_rows)+1:03d}"
        if version == "foshan_legacy": case_id += "_L"
        
        item = {
            "CaseID": case_id,
            "Center": "Foshan",
            "SourceFile": os.path.basename(file_path),
            "SourceRow": i + 1,
            "BasicInfo": get_vals(idx_basic_range),
            "ChiefComplaint": get_vals(i_cc),
            "PresentIllness": get_vals(i_pi),
            "PastHistory": get_vals(i_ph),
            "MenstrualHistory": get_vals(i_mh),
            "FamilyHistory": get_vals(i_fh),
            "PhysicalExam": get_vals(i_pe),
            "GT_Outpatient_Checks": get_vals(i_out_checks),
            "GT_Admission_Diagnosis": get_vals(i_adm_diag),
            "GT_Admission_Checks": get_vals(i_adm_checks),
            "GT_Revised_Diagnosis": get_vals(i_rev_diag),
            "GT_Surgery_Plan": get_vals(i_surg_plan),
            "GT_Surgery_Findings": get_vals(i_surg_find),
            "GT_Pathology": get_vals(i_patho),
            "GT_Final_Diagnosis": get_vals(i_final_diag),
            "GT_PostOp_Plan": get_vals(i_post_plan),
            "GT_Patient_Wishes": get_vals(i_wishes)
        }
        parsed_rows.append(item)
        
    print(f"  > Extracted {len(parsed_rows)} rows.")
    return parsed_rows

def process_xinjiang(file_path):
    print(f"Processing Xinjiang: {file_path}")
    try:
        df_raw = pd.read_excel(file_path, header=None)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return []

    # Xinjiang format usually simpler: Row 0 is header?
    header_idx = find_header_row(df_raw, ["主诉"]) # Xinjiang might just have "主诉"
    print(f"  > Detected Header Row at Index: {header_idx}")
    
    headers = df_raw.iloc[header_idx].astype(str).values
    
    # Mapping
    def get_idxs(kws):
        return get_col_indices(headers, kws)
        
    i_basic = get_idxs(["年龄", "性别", "婚", "职业"])
    i_cc = get_idxs(["主诉"])
    i_pi = get_idxs(["现病史"])
    i_ph = get_idxs(["既往史"])
    i_mh = get_idxs(["月经"])
    i_fh = get_idxs(["家族"])
    i_pe = get_idxs(["体格检查", "查体", "妇科检查"])
    
    # Checks
    i_out_checks = get_idxs(["门诊检查", "辅助检查"]) # Often mixed in Xinjiang?
    i_adm_checks = get_idxs(["入院检查", "实验室", "影像"])
    
    i_adm_diag = get_idxs(["入院诊断", "初步诊断"])
    i_rev_diag = get_idxs(["修正诊断", "确诊"])
    i_surg_plan = get_idxs(["手术方案"])
    i_surg_find = get_idxs(["术中所见"])
    i_patho = get_idxs(["病理"])
    i_final_diag = get_idxs(["出院诊断", "最终诊断"])
    i_post_plan = get_idxs(["出院医嘱", "治疗方案"]) # Check ambiguity
    i_wishes = get_idxs(["意愿"])

    parsed_rows = []
    
    for i in range(header_idx + 1, len(df_raw)):
        row = df_raw.iloc[i]
        
        # Validation
        if clean_text(row[i_cc[0] if i_cc else 0]) == "无": continue
        
        def get_vals(indices):
            v_list = []
            seen = set()
            for idx in indices:
                if idx < len(row):
                    val = clean_text(row[idx])
                    if val != "无" and val not in seen:
                        v_list.append(val)
                        seen.add(val)
            return " ; ".join(v_list) if v_list else "无"

        item = {
            "CaseID": f"Xinjiang_{len(parsed_rows)+1:03d}",
            "Center": "Xinjiang",
            "SourceFile": os.path.basename(file_path),
            "SourceRow": i + 1,
            "BasicInfo": get_vals(i_basic),
            "ChiefComplaint": get_vals(i_cc),
            "PresentIllness": get_vals(i_pi),
            "PastHistory": get_vals(i_ph),
            "MenstrualHistory": get_vals(i_mh),
            "FamilyHistory": get_vals(i_fh),
            "PhysicalExam": get_vals(i_pe),
            "GT_Outpatient_Checks": get_vals(i_out_checks),
            "GT_Admission_Diagnosis": get_vals(i_adm_diag),
            "GT_Admission_Checks": get_vals(i_adm_checks),
            "GT_Revised_Diagnosis": get_vals(i_rev_diag),
            "GT_Surgery_Plan": get_vals(i_surg_plan),
            "GT_Surgery_Findings": get_vals(i_surg_find),
            "GT_Pathology": get_vals(i_patho),
            "GT_Final_Diagnosis": get_vals(i_final_diag),
            "GT_PostOp_Plan": get_vals(i_post_plan),
            "GT_Patient_Wishes": get_vals(i_wishes)
        }
        parsed_rows.append(item)
        
    print(f"  > Extracted {len(parsed_rows)} rows.")
    return parsed_rows

# ==========================================
# Main
# ==========================================
if __name__ == "__main__":
    all_data = []
    
    for source in SOURCE_FILES:
        if source["center"] == "Foshan":
            data = process_foshan(source["path"], source["strategy"])
        elif source["center"] == "Xinjiang":
            data = process_xinjiang(source["path"])
        else:
            data = []
            
        all_data.extend(data)
        
    # Convert to DataFrame
    df_out = pd.DataFrame(all_data, columns=STANDARD_COLUMNS)
    
    # Save
    if os.path.exists(OUTPUT_FILE):
        try:
            os.remove(OUTPUT_FILE)
        except:
            pass
            
    df_out.to_excel(OUTPUT_FILE, index=False)
    print(f"\n======================================")
    print(f"Normalization Complete.")
    print(f"Total Cases: {len(df_out)}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"======================================\n")
    
    # Preview
    print(df_out[["CaseID", "ChiefComplaint", "GT_Admission_Diagnosis"]].head(3))
