
import pandas as pd
import re

# ==========================================
# TARGETED FIX SCRIPT (Column-Level Updates)
# Does NOT overwrite entire file, only modifies specified columns
# ==========================================

FOSHAN_PATH = r"data\standardized_foshan.xlsx"
XINJIANG_PATH = r"data\standardized_xinjiang.xlsx"
FOSHAN_V2_SOURCE = r"data\佛山医院-黄医生\佛山-后50例数据-改.xlsx"
XINJIANG_SOURCE = r"data\新疆医院-乔医生\副本新疆医生-95例.xlsx"

def clean_text(val):
    if pd.isna(val): return "无"
    s = str(val).strip()
    if s.lower() in ["nan", "none", "", "无"]: return "无"
    return s

def deduplicate_field(text):
    """Remove duplicated content in a field like 'A ; B ; A ; B' -> 'A ; B'"""
    if pd.isna(text) or text == "无": return text
    parts = [p.strip() for p in str(text).split(" ; ")]
    seen = set()
    unique = []
    for p in parts:
        if p and p not in seen:
            unique.append(p)
            seen.add(p)
    return " ; ".join(unique) if unique else "无"

def fix_foshan():
    print("=== FIXING FOSHAN (Column-Level) ===")
    df = pd.read_excel(FOSHAN_PATH)
    
    # --- FIX 1: First 50 rows - Move "其他检查" from Outpatient to Admission ---
    for i in range(min(53, len(df))): # Legacy rows (0-52)
        out_val = str(df.loc[i, "GT_Outpatient_Checks"]) if pd.notna(df.loc[i, "GT_Outpatient_Checks"]) else ""
        adm_val = str(df.loc[i, "GT_Admission_Checks"]) if pd.notna(df.loc[i, "GT_Admission_Checks"]) else ""
        
        # Find "辅助检查:其他检查:XXX" pattern in Outpatient
        other_checks = []
        remaining_out = []
        for part in out_val.split(" ; "):
            if "辅助检查:其他检查" in part or "其他检查" in part:
                other_checks.append(part.strip())
            else:
                remaining_out.append(part.strip())
        
        if other_checks:
            # Update Outpatient (remove other checks)
            df.loc[i, "GT_Outpatient_Checks"] = " ; ".join([p for p in remaining_out if p and p != "无"]) or "无"
            # Update Admission (add other checks)
            adm_parts = [p.strip() for p in adm_val.split(" ; ") if p.strip() and p.strip() != "无"]
            adm_parts.extend(other_checks)
            df.loc[i, "GT_Admission_Checks"] = " ; ".join(adm_parts) if adm_parts else "无"
    
    # --- FIX 2: Last 56 rows (V2) - Deduplicate Outpatient and Admission Checks ---
    for i in range(53, len(df)):
        df.loc[i, "GT_Outpatient_Checks"] = deduplicate_field(df.loc[i, "GT_Outpatient_Checks"])
        df.loc[i, "GT_Admission_Checks"] = deduplicate_field(df.loc[i, "GT_Admission_Checks"])
    
    # --- FIX 3: Add 康复计划 and 随访计划 from V2 Source ---
    # Read V2 source for these fields
    try:
        df_v2_src = pd.read_excel(FOSHAN_V2_SOURCE, header=None)
        start_idx = 56 # Row 57 in source
        
        # Add columns if not exist
        if "GT_Rehab_Plan" not in df.columns: df["GT_Rehab_Plan"] = "无"
        if "GT_Followup_Plan" not in df.columns: df["GT_Followup_Plan"] = "无"
        
        v2_data_idx = 0
        for src_row in range(start_idx, len(df_v2_src)):
            if v2_data_idx >= 56: break # Only 56 V2 rows
            row = df_v2_src.iloc[src_row]
            
            rehab = "无"
            followup = "无"
            for val in row:
                txt = clean_text(val)
                if "康复计划" in txt:
                    rehab = txt
                elif "随访计划" in txt:
                    followup = txt
            
            df_idx = 53 + v2_data_idx # Map to standardized file
            if df_idx < len(df):
                df.loc[df_idx, "GT_Rehab_Plan"] = rehab
                df.loc[df_idx, "GT_Followup_Plan"] = followup
            v2_data_idx += 1
            
    except Exception as e:
        print(f"Error reading V2 source for Rehab/Followup: {e}")
    
    df.to_excel(FOSHAN_PATH, index=False)
    print(f"Saved Foshan: {FOSHAN_PATH}")

def fix_xinjiang():
    print("=== FIXING XINJIANG (Column-Level) ===")
    df = pd.read_excel(XINJIANG_PATH)
    df_src = pd.read_excel(XINJIANG_SOURCE, header=None)
    
    # Header at Row 1 (index 1)
    header_idx = 1
    
    # Excel Columns: J=9, K=10, M=12, N=13, O=14, P=15, Q=16
    # (0-indexed: J=9, K=10, M=12-16)
    out_cols = [9, 10] # J, K
    adm_cols = [12, 13, 14, 15, 16] # M to Q
    
    # Find 康复计划 and 随访计划 columns (Headers show Col 24, 25)
    rehab_col = 24
    followup_col = 25
    
    if "GT_Rehab_Plan" not in df.columns: df["GT_Rehab_Plan"] = "无"
    if "GT_Followup_Plan" not in df.columns: df["GT_Followup_Plan"] = "无"
    
    for i, src_row_idx in enumerate(range(header_idx + 1, len(df_src))):
        if i >= len(df): break
        src_row = df_src.iloc[src_row_idx]
        
        # Outpatient (J, K)
        out_parts = []
        for col in out_cols:
            if col < len(src_row):
                val = clean_text(src_row[col])
                if val != "无": out_parts.append(val)
        df.loc[i, "GT_Outpatient_Checks"] = " ; ".join(out_parts) if out_parts else "无"
        
        # Admission (M to Q)
        adm_parts = []
        for col in adm_cols:
            if col < len(src_row):
                val = clean_text(src_row[col])
                if val != "无": adm_parts.append(val)
        df.loc[i, "GT_Admission_Checks"] = " ; ".join(adm_parts) if adm_parts else "无"
        
        # Rehab and Followup
        if rehab_col < len(src_row):
            df.loc[i, "GT_Rehab_Plan"] = clean_text(src_row[rehab_col])
        if followup_col < len(src_row):
            df.loc[i, "GT_Followup_Plan"] = clean_text(src_row[followup_col])
    
    df.to_excel(XINJIANG_PATH, index=False)
    print(f"Saved Xinjiang: {XINJIANG_PATH}")

if __name__ == "__main__":
    fix_foshan()
    fix_xinjiang()
    print("\n=== ALL FIXES APPLIED ===")
