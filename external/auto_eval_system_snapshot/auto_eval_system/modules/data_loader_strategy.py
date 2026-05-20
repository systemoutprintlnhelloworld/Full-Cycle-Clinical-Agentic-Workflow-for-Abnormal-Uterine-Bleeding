# -*- coding: utf-8 -*-
import pandas as pd
import os
import re
import logging

logger = logging.getLogger(__name__)

class CenterStrategy:
    def load_patients(self, file_path):
        raise NotImplementedError

    def _clean_str(self, val):
        """Helper to clean cell values"""
        if pd.isna(val):
            return "无"
        s = str(val).strip()
        return s if s else "无"
    
    def _extract_age_gender(self, basic_info_str):
        """Fail-safe extraction if columns are merged"""
        age = "未知"
        gender = "未知"
        ethnicity = "未知"
        
        basic_info_str = str(basic_info_str)
        
        # Age extraction: "28岁"
        m_age = re.search(r'(\d+)岁', basic_info_str)
        if m_age: 
            age = m_age.group(1)
        
        # Gender extraction
        if "男" in basic_info_str: gender = "男"
        if "女" in basic_info_str: gender = "女"
        
        # Ethnicity extraction (Simple heuristic)
        # Assuming format like "汉族" or "维吾尔族"
        m_eth = re.search(r'([^\s\d,，]+族)', basic_info_str)
        if m_eth:
            ethnicity = m_eth.group(1)
            
        return age, gender, ethnicity

    def _load_standardized_common(self, file_path, center_name):
        """
        Unified loading logic for Standardized Excel Files.
        Expects columns: CaseID, BasicInfo, ChiefComplaint, PresentIllness, etc.
        """
        df = pd.read_excel(file_path)
        patients = []
        
        for idx, row in df.iterrows():
            def get(col, default="无"):
                return self._clean_str(row.get(col, default))

            # Base Data
            case_id = str(row.get("CaseID", f"{center_name.lower()}_{idx+1}"))
            basic_info = get("BasicInfo", "未知")
            
            # Extract Age/Gender for Agent (CRITICAL FIX)
            age, gender, ethnicity = self._extract_age_gender(basic_info)
            
            p = {
                "case_id": case_id,
                "center": center_name, # Start Case
                "source_file": os.path.basename(file_path),
                "row_index": idx,
                
                # Input for Agent
                "age": age,
                "gender": gender,
                "ethnicity": ethnicity,
                "basic_info": basic_info, # Keep raw string too
                
                "chief_complaint": get("ChiefComplaint"),
                "present_illness": get("PresentIllness"),
                "past_history": get("PastHistory"),
                "menstrual_history": get("MenstrualHistory"),
                "family_history": get("FamilyHistory"),
                "physical_exam": get("PhysicalExam"),
                
                # Ground Truths
                "gt_outpatient_checks": get("GT_Outpatient_Checks"),
                "gt_admission_diagnosis": get("GT_Admission_Diagnosis"),
                "gt_admission_checks": get("GT_Admission_Checks"),
                
                "gt_revised_diagnosis": get("GT_Revised_Diagnosis"),
                "gt_surgery_plan": get("GT_Surgery_Plan"),
                "gt_surgery_findings": get("GT_Surgery_Findings"),
                "gt_pathology": get("GT_Pathology"),
                "gt_final_diagnosis": get("GT_Final_Diagnosis"),
                "gt_post_op_plan": get("GT_PostOp_Plan"),
                "gt_patient_wishes": get("GT_Patient_Wishes"),
                "gt_rehab_plan": get("GT_Rehab_Plan"), 
                "gt_followup_plan": get("GT_Followup_Plan")
            }
            
            # --- Center Specific Linking Logic (if any) ---
            if center_name == "Xinjiang":
                 # Xinjiang specific merging for findings
                 oncology_check = get("oncology check", "")
                 other_check = get("other check", "")
                 findings = p["gt_surgery_findings"]
                 
                 if "同可视电吸清宫术所见" in findings and other_check != "无":
                     p["gt_surgery_findings"] += f" (补充检查结果: {other_check})"
                 elif ("同腹腔镜" in findings or "同宫腔镜" in findings) and oncology_check != "无":
                     p["gt_surgery_findings"] += f" (补充检查结果: {oncology_check})"

            # Comprehensive Description for Logs (Fixes user confusion)
            p["patient_description_raw"] = (
                f"【基本信息】{age}岁 {gender} ({basic_info})\n"
                f"【主诉】{p['chief_complaint']}\n"
                f"【现病史】{p['present_illness']}\n"
                f"【月经婚育】{p['menstrual_history']}"
            )
            
            patients.append(p)
            
        logger.info(f"Loaded {len(patients)} patients using Standardized Strategy for {center_name}")
        return patients

    def _is_standardized(self, df):
        # Heuristic to detect standardized format
        required = ["CaseID", "ChiefComplaint"] # Minimal set
        return all(col in df.columns for col in required)

class FoshanStrategy(CenterStrategy):
    def load_patients(self, file_path):
        # 0. Try Standardized First
        try:
            df_check = pd.read_excel(file_path, nrows=1)
            if self._is_standardized(df_check):
                return self._load_standardized_common(file_path, "Foshan")
        except Exception as e:
            pass # Fallthrough

        # Legacy: Foshan Raw Table (Complex Header)
        # 1. 查找表头所在行
        df_raw = pd.read_excel(file_path, header=None, nrows=10)
        header_row_idx = 0
        for i in range(10):
            row_vals = df_raw.iloc[i].astype(str).values
            if any("基本情况" in v or "主诉" in v or "CaseID" in v for v in row_vals):
                header_row_idx = i
                break
        
        # 2. 读取数据
        df = pd.read_excel(file_path, header=header_row_idx)
        
        def find_cols(keywords, scope="any"):
             # ... (Same Legacy Logic Simplified for overwrite) ...
             # Note: For brevity in this fix, I am assuming the user PRIMARILY wants standardized fix.
             # But I must preserve legacy logic in case they switch back. 
             # I will copy the legacy logic from previous file view carefully.
             if isinstance(keywords, str): keywords = [keywords]
             matches = []
             for c_idx in range(len(df.columns)):
                 h1 = str(df.columns[c_idx]).strip()
                 val_r1 = str(df.iloc[0, c_idx]).strip() if len(df) > 0 else ""
                 val_r2 = str(df.iloc[1, c_idx]).strip() if len(df) > 1 else ""
                 if any(k in h1 or k in val_r1 or k in val_r2 for k in keywords):
                     matches.append(c_idx)
             
             if not matches: return []
             
             # Cutoff logic for Admission vs Outpatient overlap
             cutoff = 999
             for c_idx in range(len(df.columns)):
                 val_r1 = str(df.iloc[0, c_idx]).strip() if len(df) > 0 else ""
                 if "入院诊断" in val_r1 or "初步诊断" in val_r1:
                     cutoff = c_idx
                     break
             
             if scope == "outpatient": return [i for i in matches if i < cutoff]
             elif scope == "admission": return [i for i in matches if i > cutoff]
             return matches

        # Pre-calculate indices
        idx_basic = find_cols(["基本情况", "一般情况"])
        idx_cc = find_cols("主诉")
        idx_pi = find_cols("现病史")
        idx_ph = find_cols("既往史")
        idx_mh = find_cols(["月经", "婚育", "生育"])
        idx_fh = find_cols("家族史")
        idx_pe = find_cols(["体格检查", "专科检查", "妇科检查"])
        
        idx_out_checks = find_cols(["门诊检查", "检查", "检验", "辅助检查"], scope="outpatient")
        idx_adm_checks = find_cols(["入院检查", "实验室检查", "影像学检查"], scope="admission")
        
        idx_adm_diag = find_cols(["入院诊断", "初步诊断"])
        idx_rev_diag = find_cols(["修正诊断", "确定诊断"])
        idx_surg_plan = find_cols(["手术方案", "治疗方案"])
        idx_post_plan = find_cols(["术后治疗", "术后医嘱"])
        idx_followup = find_cols("随访")
        
        idx_final_diag = find_cols(["最终诊断", "出院诊断"])
        idx_surg_find = find_cols(["术中所见"])
        idx_pathology = find_cols(["手术病理", "术后病理"])
        idx_wishes = find_cols(["患者意愿"])

        patients = []
        for idx, row in df.iterrows():
            r_val0 = str(row[0])
            if "基本情况" in r_val0 or "主诉" in r_val0: continue # Header skip

            def get_content(indices):
                vals = []
                seen = set()
                for i in indices:
                    v = self._clean_str(row[i])
                    if v not in ["无", "nan", ""] and v not in seen:
                        vals.append(v); seen.add(v)
                return " ; ".join(vals) if vals else "无"

            cc = get_content(idx_cc)
            if cc == "无" or len(cc) < 2: continue
            
            p = {
                "case_id": f"foshan_{idx+2}",
                "center": "Foshan",
                "source_file": os.path.basename(file_path),
                "row_index": idx + 2,
                "basic_info": get_content(idx_basic),
                "chief_complaint": cc,
                "present_illness": get_content(idx_pi),
                "past_history": get_content(idx_ph),
                "menstrual_history": get_content(idx_mh),
                "family_history": get_content(idx_fh),
                "physical_exam": get_content(idx_pe),
                "gt_outpatient_checks": get_content(idx_out_checks),
                "gt_admission_diagnosis": get_content(idx_adm_diag),
                "gt_admission_checks": get_content(idx_adm_checks),
                "gt_revised_diagnosis": get_content(idx_rev_diag),
                "gt_surgery_plan": get_content(idx_surg_plan),
                "gt_post_op_plan": get_content(idx_post_plan),
                "gt_followup_plan": get_content(idx_followup),
                "gt_final_diagnosis": get_content(idx_final_diag),
                "gt_surgery_findings": get_content(idx_surg_find),
                "gt_pathology": get_content(idx_pathology),
                "gt_patient_wishes": get_content(idx_wishes)
            }
            # Infer Age/Gender legacy
            a, g, _ = self._extract_age_gender(p['basic_info'])
            p['age'] = a
            p['gender'] = g
            
            p["patient_description_raw"] = p["chief_complaint"] # Simplified fallback
            patients.append(p)
        return patients

class WuhanStrategy(CenterStrategy):
    def load_patients(self, file_path):
        # 0. Try Standardized First
        try:
            df_check = pd.read_excel(file_path, nrows=1)
            if self._is_standardized(df_check):
                return self._load_standardized_common(file_path, "Wuhan")
        except: pass

        # Wuhan: Header at row 4 (index 3)
        df = pd.read_excel(file_path, header=3)
        patients = []
        
        for idx, row in df.iterrows():
            def get(keywords):
                if isinstance(keywords, str): keywords = [keywords]
                for col in df.columns:
                    if any(k in str(col) for k in keywords): return self._clean_str(row[col])
                return "无"
            
            p = {
                "case_id": f"wuhan_{idx+4}",
                "center": "Wuhan",
                "source_file": os.path.basename(file_path),
                "row_index": idx + 4,
                "age": get("年龄"), "gender": get("性别"), "ethnicity": get("种族"),
                "basic_info": f"{get('种族')} {get('性别')} {get('年龄')}",
                "chief_complaint": get("主诉"),
                "present_illness": get("现病史"),
                "past_history": get("既往史"), 
                "menstrual_history": get(["月经", "婚育"]),
                "family_history": get("家族史"),
                "physical_exam": get(["体格检查", "专科检查"]),
                "gt_outpatient_checks": get(["门诊", "辅助检查"]),
                "gt_admission_diagnosis": get(["入院诊断", "初步诊断"]),
                "gt_admission_checks": get("入院检查"),
                "gt_revised_diagnosis": get(["修正", "确诊"]),
                "gt_surgery_plan": get("手术"),
                "gt_surgery_findings": get("术中"),
                "gt_pathology": get("病理"),
                "gt_final_diagnosis": get("出院诊断"),
                "gt_post_op_plan": get("出院医嘱"),
                "gt_patient_wishes": "无",
                "gt_rehab_plan": "无",
                "gt_followup_plan": get("随访")
            }
            if p["gender"] == "无" and "女" in p["ethnicity"]: p["gender"] = "女"
            p["patient_description_raw"] = f"【主诉】{p['chief_complaint']} 【现病史】{p['present_illness']}"
            if p["chief_complaint"] != "无": patients.append(p)
        return patients

class XinjiangStrategy(CenterStrategy):
    def load_patients(self, file_path):
        # 0. Try Standardized First
        try:
            df_check = pd.read_excel(file_path, nrows=1)
            if self._is_standardized(df_check) or "GT_Surgery_Findings" in df_check.columns:
                 return self._load_standardized_common(file_path, "Xinjiang")
        except: pass

        # RAW FORMAT LOGIC (Legacy)
        df = pd.read_excel(file_path, header=3)
        patients = []
        for idx, row in df.iterrows():
            def get(keywords, default="无"):
                if isinstance(keywords, str): keywords = [keywords]
                for col in df.columns:
                    if any(k in str(col) for k in keywords): return self._clean_str(row[col])
                return default
            
            p = {
                "case_id": f"xinjiang_{idx+4}",
                "center": "Xinjiang",
                "source_file": os.path.basename(file_path),
                "row_index": idx + 4,
                "basic_info": f"{get('民族')} {get('性别')} {get('年龄')}",
                "chief_complaint": get("主诉"),
                "present_illness": get("现病史"),
                "past_history": get("既往史"),
                "menstrual_history": get(["月经", "婚育"]),
                "family_history": get("家族史"),
                "physical_exam": get("查体"),
                "gt_outpatient_checks": get(["门诊", "辅助检查"]),
                "gt_admission_diagnosis": get("初步诊断"),
                "gt_admission_checks": get("入院检查"),
                "gt_revised_diagnosis": get("修正诊断"),
                "gt_surgery_plan": get("治疗方案"),
                "gt_surgery_findings": get("术中"),
                "gt_pathology": get("病理"),
                "gt_final_diagnosis": get("出院诊断"),
                "gt_post_op_plan": get("出院医嘱"),
                "gt_patient_wishes": "无", "gt_rehab_plan": "无", "gt_followup_plan": get("随访")
            }
            # Implicit age extraction lacking in legacy, keep as is or improve? 
            # Legacy raw reading uses column '年龄' directly if available? Yes 'get("年龄")' used in basic_info but not p['age'].
            # Let's fix raw too
            p['age'] = get("年龄", "未知")
            p['gender'] = get("性别", "未知")
            
            p["patient_description_raw"] = f"【主诉】{p['chief_complaint']}..."
            if p["chief_complaint"] != "无": patients.append(p)
        return patients

def get_strategy(file_path):
    fn = os.path.basename(file_path)
    if "佛山" in fn or "foshan" in fn.lower(): return FoshanStrategy()
    if "武汉" in fn or "wuhan" in fn.lower(): return WuhanStrategy()
    if "新疆" in fn or "xinjiang" in fn.lower(): return XinjiangStrategy()
    return FoshanStrategy()
