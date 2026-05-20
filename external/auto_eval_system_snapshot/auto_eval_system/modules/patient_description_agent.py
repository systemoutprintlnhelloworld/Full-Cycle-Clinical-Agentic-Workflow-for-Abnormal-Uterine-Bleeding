# -*- coding: utf-8 -*-
import logging
from ..config import prompts_v2
from ..utils.channel_manager import get_channel_manager

logger = logging.getLogger(__name__)

class PatientDescriptionAgent:
    def __init__(self, model_name: str = "gemini-2.5-pro"): # Main generation uses Gemini
        self.channel_manager = get_channel_manager()
        self.model_name = model_name
        self.verify_model_name = "gpt-4o" # Verification uses GPT-4o

    def generate_description(self, patient_data: dict) -> str:
        # Clean inputs to remove redundant headers if present
        def clean(val):
            val = str(val).strip()
            if str(val) in ["无", "nan", "None"]: return "无"
            # Remove common prefixes
            for prefix in ["主诉", "现病史", "月经史", "婚育史", "：", ":"]:
                val = val.replace(prefix, "").strip()
            return val

        # logger.info(f"DescAgent Raw Inputs - CC: {patient_data.get('chief_complaint')}, HPI: {patient_data.get('present_illness')}")
        
        age = clean(patient_data.get("age", "未知"))
        gender = clean(patient_data.get("gender", "未知"))
        chief_complaint = clean(patient_data.get("chief_complaint", "无"))
        present_illness = clean(patient_data.get("present_illness", "无"))
        menstrual_history = clean(patient_data.get("menstrual_history", "无"))
        
        # FIX: Extract raw basic info to capture Vitals (Height/Weight/BMI)
        basic_info_raw = clean(str(patient_data.get("basic_info", "无")))

        logger.info(f"DescAgent Cleaned Inputs - CC: {chief_complaint}, HPI: {present_illness}")
        
        prompt = prompts_v2.PATIENT_DESCRIPTION_PROMPT.format(
            age=age,
            gender=gender,
            ethnicity=patient_data.get("ethnicity", "未知"), 
            basic_info_raw=basic_info_raw, # Pass raw info
            chief_complaint=chief_complaint,
            present_illness=present_illness,
            menstrual_history=menstrual_history
        )
        
        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.channel_manager.call_with_fallback(
                model_name=self.model_name,
                messages=messages,
                temperature=0.7
            )
            desc_content = response.choices[0].message.content.strip()
            
            # --- Verification Step (GPT-4o) ---
            verify_prompt = f"""
            你是一个医疗信息核查员。请对比【原始结构化数据】和AI生成的【患者口述】，检查是否遗漏了关键信息。
            
            【原始结构化数据】
            1. 原始基本信息: {basic_info_raw}  <-- 重点核查！
            2. 基本信息解析: {age}岁 {gender}
            3. 主诉: {chief_complaint}
            4. 现病史: {present_illness}
            5. 月经婚育史: {menstrual_history}
            
            【生成的患者口述】
            {desc_content}
            
            【核查任务】
            1. **数值一致性**: 检查【原始基本信息】中的客观数值（如 **身高、体重、BMI**、体温、血压等）是否在口述中准确体现。
            2. **既往经历逐字核对**: 检查口述末尾是否包含 `[现病史-既往就诊经历]` 区块。如果包含，核对该区块内容是否与【现病史】中的相关描述**逐字一致**（不缺字、不改数）。
            3. **信息完整性**: 检查口述中是否包含了所有关键的医学事实。
            
            【输出要求】
            如果发现有数值遗漏、关键信息缺失或既往经历未逐字保留，请直接输出**修正后的最终口述内容**（包含口语正文 + 修正后的 `[现病史-既往就诊经历]` 区块）。
            如果没有遗漏且格式正确，请直接输出"无遗漏"。
            """
            
            v_messages = [{"role": "user", "content": verify_prompt}]
            v_resp = self.channel_manager.call_with_fallback(
                model_name=self.verify_model_name, # Explicitly use GPT-4o
                messages=v_messages,
                temperature=0.1
            )
            v_content = v_resp.choices[0].message.content.strip()
            
            if "无遗漏" not in v_content and len(v_content) > len(desc_content):
                logger.info("Patient Description Agent corrected the description.")
                return v_content
            else:
                return desc_content
                
        except Exception as e:
            import traceback
            logger.error(f"Failed to generate patient description: {e}\nTraceback:\n{traceback.format_exc()}")
            # Better Fallback: Narrative style
            return f"医生你好，我今年{age}岁。主要是不舒服：{chief_complaint}。具体的经过是：{present_illness}。我的月经情况是：{menstrual_history}。"
