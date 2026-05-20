# -*- coding: utf-8 -*-
import logging
import json
from ..config import prompts_v2
from ..utils.channel_manager import get_channel_manager
from ..utils.json_parser import extract_json

logger = logging.getLogger(__name__)

class DoctorAgent:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.channel_manager = get_channel_manager()

    def make_outpatient_decision(self, patient_data: dict) -> dict:
        """
        Stage 1: 门诊决策
        """
        system_prompt = prompts_v2.DECISION1_SYSTEM_PROMPT
        
        # 提取字段，使用 get 避免 KeyError，提供默认空值
        user_prompt = prompts_v2.DECISION1_USER_PROMPT_TEMPLATE.format(
            age=patient_data.get("age", "未知"),
            gender=patient_data.get("gender", "未知"),
            ethnicity=patient_data.get("ethnicity", "未知"),
            patient_description=patient_data.get("patient_description", "无"),
            past_history=patient_data.get("past_history", "无"),
            menstrual_history=patient_data.get("menstrual_history", "无"),
            family_history=patient_data.get("family_history", "无"),
            physical_exam=patient_data.get("physical_exam", "无")
        )
        
        return self._call_llm(system_prompt, user_prompt, "outpatient_decision_1")

    def make_admission_decision(self, context: str, admission_checks: str) -> dict:
        """
        Stage 2: 入院诊断决策 (Decision 2)
        上下文通常由 run_check_loop 的结果或 ContextBuilder 构建
        """
        system_prompt = prompts_v2.DECISION2_SYSTEM_PROMPT
        
        # 这里假设 context 是构建好的上下文文本，或者通过 ContextBuilder 构建
        # 根据 API 设计，这里可能需要调整参数
        # 如果 context 已经包含了之前的摘要，那么 admission_checks 是新的输入
        
        # 但 DECISION2_USER_PROMPT_TEMPLATE 需要具体的字段填充
        # 我们假设外部 Workflow 负责填充 Template，或者在这里填充
        # 为了灵活，建议 Workflow 填充好完整的 User Prompt 传进来，或者传参数
        
        # 暂时采用: context 是已经格式化好的 User Prompt 的一部分，或者这函数接收构建所需的字段
        # 根据 prompts_v2.py, Template 需要: {basic_info}, {patient_description}, {preliminary_diagnosis}, {outpatient_checks_feedback}, {admission_checks}
        
        # 这种情况下，DoctorAgent 的接口最好接收 "ready-to-use" 的 prompt 变量，或者一个包含所有上下文的 dict
        pass # 实现将由 Workflow 调用时决定

    def make_decision_with_context(self, stage_name: str, system_prompt: str, user_prompt: str) -> dict:
        """
        通用的决策方法，接收构建好的 Prompts
        """
        return self._call_llm(system_prompt, user_prompt, stage_name)

    def _call_llm(self, system_prompt: str, user_prompt: str, stage_name: str):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        logger.info(f"Doctor Agent ({self.model_name}) thinking in {stage_name}...")
        
        try:
            # 传递 logprobs=True 以获取置信度数据
            response = self.channel_manager.call_with_fallback(
                model_name=self.model_name,
                messages=messages,
                temperature=0.5,
                response_format={"type": "json_object"}
                # logprobs=True # User requested to disable
            )
            
            content = response.choices[0].message.content
            decision_json = extract_json(content)
            
            # 附加 logprobs 数据到结果中 (如果存在)
            # if hasattr(response.choices[0], 'logprobs') and response.choices[0].logprobs:
            #     if decision_json:
            #         try:
            #             decision_json["_logprobs"] = self._process_logprobs(response.choices[0].logprobs)
            #         except Exception as e:
            #             logger.warning(f"Failed to process logprobs: {e}")

            if not decision_json:
                logger.error(f"Doctor Agent returned invalid JSON in {stage_name}: {content}")
                return None
            
            # Inject Prompts for transparent logging (Will be stripped by Workflow before saving)
            decision_json["_metadata"] = {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt
            }
                
            return decision_json
            
        except Exception as e:
            logger.error(f"Error calling LLM in {stage_name}: {e}")
            raise e

    def _process_logprobs(self, logprobs):
        """处理 logprobs 对象为可序列化的字典"""
        # 简单转换，保留 content token logprobs
        try:
            # 根据 openai 版本，logprobs 结构可能不同
            data = []
            if hasattr(logprobs, 'content'):
                for item in logprobs.content:
                    data.append({
                        "token": item.token,
                        "logprob": item.logprob,
                        # "bytes": item.bytes # bytes 可能非 utf-8，序列化 json 困难，略去
                    })
            return data
        except Exception as e:
            logger.warning(f"Failed to process logprobs: {e}")
            return None
