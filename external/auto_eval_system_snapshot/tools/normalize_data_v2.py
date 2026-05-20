
import pandas as pd
import os
import re

# ==========================================
# Configuration
# ==========================================
SOURCE_FOSHAN_LEGACY = r"data\佛山医院-黄医生\佛山医生-前50例数据-修订并使用.xlsx"
SOURCE_FOSHAN_V2 = r"data\佛山医院-黄医生\佛山-后50例数据-改.xlsx"
SOURCE_XINJIANG = r"data\新疆医院-乔医生\副本新疆医生-95例.xlsx"

OUT_FOSHAN = r"data\standardized_foshan.xlsx"
OUT_XINJIANG = r"data\standardized_xinjiang.xlsx"

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
# Helpers
# ==========================================
def clean_text(val):
    if pd.isna(val): return "无"
    s = str(val).strip()
    if s.lower() in ["nan", "none", "", "无"]: return "无"
    return s

def find_header_row_simple(df, keywords):
    for i in range(min(10, len(df))):
        row_str = " ".join([str(x) for x in df.iloc[i].values])
        if any(k in row_str for k in keywords):
            return i
    return 0

# ==========================================
# Foshan Legacy (V3 Logic - Strict Split)
# ==========================================
def process_foshan_legacy(file_path):
    print(f"Processing Foshan Legacy: {file_path}")
    try:
        df_raw = pd.read_excel(file_path, header=None)
    except Exception as e:
        print(e)
        return []

    header_idx = find_header_row_simple(df_raw, ["主诉"])
    l1 = df_raw.iloc[header_idx].fillna(method='ffill').astype(str).values
    try:
        l2 = df_raw.iloc[header_idx+1].fillna("").astype(str).values
    except:
        l2 = [""] * len(l1)
    
    # Combined Header
    cols = [f"{str(c1)}_{str(c2)}".replace("nan", "") for c1, c2 in zip(l1, l2)]
    
    def find_indices(keywords, exclude=None):
        idxs = []
        for i, c in enumerate(cols):
             if any(k in c for k in keywords):
                 if exclude and any(e in c for e in exclude): continue
                 idxs.append(i)
        return idxs

    idx_cc = find_indices(["主诉"])[0]
    idx_basic_range = list(range(0, idx_cc))
    i_cc = find_indices(["主诉"])
    i_pi = find_indices(["现病史"])
    i_ph = find_indices(["既往史"])
    i_mh = find_indices(["月经", "婚育", "生育"])
    i_fh = find_indices(["家族史"])
    i_pe = find_indices(["体格检查", "专科检查", "妇科检查"])
    
    # --- STRICT CHECK SEPARATION ---
    # Outpatient: "门诊", "辅助检查"(but not Lab/Image/Path/etc), "检验"
    # Note: "辅助检查" header in Legacy often covers everything.
    # L2 usually distinguishes.
    # Outpatient keywords in L2: "检验", "检查" (generic), but NOT "实验室", "影像".
    # Wait, "实验室检查" contains "检查". So "检查" is dangerous.
    # Best exclude list for Outpatient: 
    adm_keywords = ["入院", "实验室", "影像", "病理", "内镜", "超声", "心电", "术前"]
    
    i_out = find_indices(["门诊"], exclude=["诊断"]) 
    # Also add "辅助检查" if L2 is NOT Admission-like
    i_out_aux = find_indices(["辅助检查"], exclude=adm_keywords + ["诊断", "处理"])
    # Combine unique indices
    i_out = sorted(list(set(i_out + i_out_aux)))

    # Admission: "入院", "实验室", "影像", "病理", "内镜", "超声", etc.
    i_adm = find_indices(adm_keywords, exclude=["诊断", "处理", "门诊"])
    
    i_adm_diag = find_indices(["入院诊断", "初步诊断"])
    i_rev_diag = find_indices(["修正诊断", "确定诊断"])
    i_surg_plan = find_indices(["手术方案", "拟施手术"])
    i_surg_find = find_indices(["术中所见"])
    i_patho = find_indices(["术后病理", "石蜡病理"])
    i_final = find_indices(["最终诊断", "出院诊断"])
    i_post = find_indices(["术后治疗", "术后医嘱"])
    i_wish = find_indices(["意愿", "特殊情况"])

    parsed = []
    data_start = header_idx + 2
    for i in range(data_start, len(df_raw)):
        row = df_raw.iloc[i]
        if clean_text(row[idx_cc]) == "无": continue
        
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
            "CaseID": f"Foshan_{len(parsed)+1:03d}_L",
            "Center": "Foshan",
            "SourceFile": "Legacy",
            "SourceRow": i+1,
            "BasicInfo": get_vals(idx_basic_range),
            "ChiefComplaint": get_vals(i_cc),
            "PresentIllness": get_vals(i_pi),
            "PastHistory": get_vals(i_ph),
            "MenstrualHistory": get_vals(i_mh),
            "FamilyHistory": get_vals(i_fh),
            "PhysicalExam": get_vals(i_pe),
            "GT_Outpatient_Checks": get_vals(i_out),
            "GT_Admission_Diagnosis": get_vals(i_adm_diag),
            "GT_Admission_Checks": get_vals(i_adm),
            "GT_Revised_Diagnosis": get_vals(i_rev_diag),
            "GT_Surgery_Plan": get_vals(i_surg_plan), # Legacy has specific col? Yes "拟施手术"
            "GT_Surgery_Findings": get_vals(i_surg_find),
            "GT_Pathology": get_vals(i_patho),
            "GT_Final_Diagnosis": get_vals(i_final),
            "GT_PostOp_Plan": get_vals(i_post),
            "GT_Patient_Wishes": get_vals(i_wish)
        }
        parsed.append(item)
    return parsed

# ==========================================
# Foshan V2 (V3 Logic - Robust Prefix)
# ==========================================
def process_foshan_v2(file_path):
    print(f"Processing Foshan V2 (Prefix Mode): {file_path}")
    try:
        df = pd.read_excel(file_path, header=None)
    except: return []

    parsed = []
    start_idx = 56 # Row 57
    
    for i in range(start_idx, len(df)):
        row = df.iloc[i]
        if all(clean_text(x)=="无" for x in row): continue
        
        item = {k: "无" for k in STANDARD_COLUMNS}
        item["CaseID"] = f"Foshan_{53 + (len(parsed)+1):03d}" 
        item["Center"] = "Foshan"
        item["SourceFile"] = "Foshan_V2"
        item["SourceRow"] = i + 1
        
        out_checks = []
        adm_checks = []
        
        for val in row:
            txt = clean_text(val)
            if txt == "无": continue
            
            # --- MAPPING ---
            if txt.startswith("基本情况") or txt.startswith("基本信息"): item["BasicInfo"] = txt 
            elif txt.startswith("主诉"): item["ChiefComplaint"] = txt
            elif txt.startswith("现病史"): item["PresentIllness"] = txt
            elif txt.startswith("既往史"): item["PastHistory"] = txt
            elif "月经" in txt and "生育" in txt: item["MenstrualHistory"] = txt
            elif txt.startswith("家族史"): item["FamilyHistory"] = txt
            elif "体格检查" in txt: item["PhysicalExam"] = txt
            
            # Checks
            elif "辅助检查:检验" in txt or "辅助检查:检查" in txt:
                out_checks.append(txt)
            
            elif "辅助检查:实验室" in txt or "辅助检查:影像" in txt or "辅助检查:病理" in txt or "辅助检查:内镜" in txt or "辅助检查:其他" in txt:
                adm_checks.append(txt)
            
            # Robust Diagnosis Matching (Loose 'in')
            elif "修正诊断" in txt: item["GT_Admission_Diagnosis"] = txt
            
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
                 
        item["GT_Outpatient_Checks"] = " ; ".join(out_checks) if out_checks else "无"
        item["GT_Admission_Checks"] = " ; ".join(adm_checks) if adm_checks else "无"
        parsed.append(item) # Debug print removed for cleanness, verified by V2 script logic
    
    print(f"Extracted {len(parsed)} rows from V2.")
    return parsed

# ==========================================
# Xinjiang (V3 Logic - Content Based Split)
# ==========================================
def process_xinjiang(file_path):
    print(f"Processing Xinjiang: {file_path}")
    try:
        df_raw = pd.read_excel(file_path, header=None)
    except: return []

    header_idx = find_header_row_simple(df_raw, ["主诉"])
    headers = df_raw.iloc[header_idx].astype(str).values
    
    cols = [str(x) for x in headers]
    
    def find_indices(keywords, exclude=None):
        idxs = []
        for i, c in enumerate(cols):
             if any(k in c for k in keywords):
                 if exclude and any(e in c for e in exclude): continue
                 idxs.append(i)
        return idxs
        
    i_basic = [] 
    for x in ["年龄", "性别", "婚", "职业"]: i_basic.extend(find_indices([x]))
    
    i_cc = find_indices(["主诉"])
    i_pi = find_indices(["现病史"])
    i_ph = find_indices(["既往史"])
    i_mh = find_indices(["月经"])
    i_fh = find_indices(["家族"])
    i_pe = find_indices(["体格检查", "查体", "妇科检查"])
    
    # Checks Separation Strategy:
    # 1. Explicit Headers (if any)
    # 2. Ambiguous "辅助检查" columns -> Split by Content
    
    # Explicit Outpatient Headers
    i_out_explicit = find_indices(["门诊", "门诊检查"], exclude=["诊断", "辅助"])
    
    # Explicit Admission Headers
    i_adm_explicit = find_indices(["入院", "实验室", "影像", "病理", "内镜", "超声", "心电", "术前"], exclude=["诊断", "处理", "辅助", "门诊"])
    
    # Ambiguous "辅助检查" Headers
    i_aux = find_indices(["辅助检查"], exclude=["诊断"])
    
    # Others
    i_adm_diag = find_indices(["入院诊断", "初步诊断"])
    i_rev_diag = find_indices(["修正诊断", "确诊"])
    i_surg_plan = find_indices(["手术方案"])
    i_surg_find = find_indices(["术中所见"])
    i_patho = find_indices(["病理"], exclude=["辅助", "检查"]) 
    i_final = find_indices(["出院诊断", "最终诊断"])
    i_post = find_indices(["出院医嘱", "治疗方案"]) 
    i_wish = find_indices(["意愿", "特殊情况"])

    parsed = []
    
    # Keywords indicating Admission/Advanced Checks
    adm_content_keywords = ["实验室", "影像", "超声", "CT", "MRI", "病理", "内镜", "心电", "血常规", "尿常规", "生化"]
    
    for i in range(header_idx+1, len(df_raw)):
        row = df_raw.iloc[i]
        if i_cc and clean_text(row[i_cc[0]]) == "无": continue
        
        def get_vals(indices):
            v_list = []
            seen = set()
            for idx in indices:
                if idx < len(row):
                    val = clean_text(row[idx])
                    if val != "无" and val not in seen:
                        v_list.append(val)
                        seen.add(val)
            return v_list

        # Basic Fields
        basic = " ; ".join(get_vals(i_basic)) if i_basic else "无"
        cc = " ; ".join(get_vals(i_cc)) if i_cc else "无"
        pi = " ; ".join(get_vals(i_pi)) if i_pi else "无"
        ph = " ; ".join(get_vals(i_ph)) if i_ph else "无"
        mh = " ; ".join(get_vals(i_mh)) if i_mh else "无"
        fh = " ; ".join(get_vals(i_fh)) if i_fh else "无"
        pe = " ; ".join(get_vals(i_pe)) if i_pe else "无"
        
        # Checks Splitting
        out_checks = get_vals(i_out_explicit)
        adm_checks = get_vals(i_adm_explicit)
        
        # Process Ambiguous Cols
        aux_vals = get_vals(i_aux)
        for val in aux_vals:
            # Check content
            is_adm = False
            for k in adm_content_keywords:
                if k in val:
                    is_adm = True
                    break
            if is_adm:
                adm_checks.append(val)
            else:
                out_checks.append(val)
        
        gt_out = " ; ".join(out_checks) if out_checks else "无"
        gt_adm = " ; ".join(adm_checks) if adm_checks else "无"
        
        gt_adm_diag = " ; ".join(get_vals(i_adm_diag)) if i_adm_diag else "无"
        gt_rev_diag = " ; ".join(get_vals(i_rev_diag)) if i_rev_diag else "无"
        gt_surg_plan = " ; ".join(get_vals(i_surg_plan)) if i_surg_plan else "无"
        gt_surg_find = " ; ".join(get_vals(i_surg_find)) if i_surg_find else "无"
        gt_patho = " ; ".join(get_vals(i_patho)) if i_patho else "无"
        gt_final = " ; ".join(get_vals(i_final)) if i_final else "无"
        gt_post = " ; ".join(get_vals(i_post)) if i_post else "无"
        gt_wish = " ; ".join(get_vals(i_wish)) if i_wish else "无"

        item = {
            "CaseID": f"Xinjiang_{len(parsed)+1:03d}",
            "Center": "Xinjiang",
            "SourceFile": "Xinjiang",
            "SourceRow": i+1,
            "BasicInfo": basic,
            "ChiefComplaint": cc,
            "PresentIllness": pi,
            "PastHistory": ph,
            "MenstrualHistory": mh,
            "FamilyHistory": fh,
            "PhysicalExam": pe,
            "GT_Outpatient_Checks": gt_out,
            "GT_Admission_Diagnosis": gt_adm_diag,
            "GT_Admission_Checks": gt_adm,
            "GT_Revised_Diagnosis": gt_rev_diag,
            "GT_Surgery_Plan": gt_surg_plan,
            "GT_Surgery_Findings": gt_surg_find,
            "GT_Pathology": gt_patho,
            "GT_Final_Diagnosis": gt_final,
            "GT_PostOp_Plan": gt_post,
            "GT_Patient_Wishes": gt_wish
        }
        parsed.append(item)
    return parsed

# ==========================================
# Main
# ==========================================
if __name__ == "__main__":
    foshan_data = []
    foshan_data.extend(process_foshan_legacy(SOURCE_FOSHAN_LEGACY))
    foshan_data.extend(process_foshan_v2(SOURCE_FOSHAN_V2))
    df_foshan = pd.DataFrame(foshan_data, columns=STANDARD_COLUMNS)
    df_foshan.to_excel(OUT_FOSHAN, index=False)
    print(f"Saved Foshan: {OUT_FOSHAN} ({len(df_foshan)} cases)")
    
    xinjiang_data = process_xinjiang(SOURCE_XINJIANG)
    df_xinjiang = pd.DataFrame(xinjiang_data, columns=STANDARD_COLUMNS)
    df_xinjiang.to_excel(OUT_XINJIANG, index=False)
    print(f"Saved Xinjiang: {OUT_XINJIANG} ({len(df_xinjiang)} cases)")
