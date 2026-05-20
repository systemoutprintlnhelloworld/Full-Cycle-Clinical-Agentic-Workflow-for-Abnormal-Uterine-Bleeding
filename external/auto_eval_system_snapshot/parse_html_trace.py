import os
import re
import json
import logging
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Optional

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class HtmlTraceParser:
    def __init__(self, html_path: str):
        self.html_path = html_path
        self.soup = None
        self.case_id = "Unknown"
        self.overview = {}
        self.d1_loops = [] 
        self.d1_decision = {}
        self.d2_loops = [] 
        self.d2_decision = {}
        self.d3_decision = {}
        self.d4_plan = {}
        self.raw_cards = []

    def load(self):
        """Loads and parses the HTML file."""
        if not os.path.exists(self.html_path):
            return False
            # raise FileNotFoundError(f"File not found: {self.html_path}")
        
        try:
            with open(self.html_path, 'r', encoding='utf-8') as f:
                self.soup = BeautifulSoup(f, 'html.parser')
            
            # Extract basic meta info from Sidebar
            self._parse_sidebar_meta()
            
            # Fallback: Extract CaseID from filename if unknown
            if self.case_id == "Unknown":
                self._derive_case_id_from_filename()
                
            # Load all cards
            self.raw_cards = self.soup.find_all('div', class_='log-card')
            # Parse
            self._parse_cards()
            return True
        except Exception as e:
            logger.error(f"Error parsing {self.html_path}: {e}")
            return False

    def _derive_case_id_from_filename(self):
        try:
            filename = os.path.basename(self.html_path)
            # Expected format: model_Center_caseId_trace.html
            # e.g. grok-4_Wuhan_wuhan_100_trace.html
            match = re.search(r"_([a-zA-Z]+_\d+)_trace", filename)
            if match:
                self.case_id = match.group(1)
                self.overview["CaseID"] = self.case_id
                # logger.info(f"Derived CaseID from filename: {self.case_id}")
        except:
            pass

    def _parse_sidebar_meta(self):
        """Extracts CaseID, Date, Duration from sidebar."""
        sidebar = self.soup.find('div', class_='sidebar')
        if not sidebar:
            return
        
        meta_div = sidebar.find('div', class_='meta-info')
        if meta_div:
            text = meta_div.get_text(separator='|', strip=True)
            parts = text.split('|')
            for i in range(0, len(parts)-1, 2):
                key = parts[i].replace(':', '').strip().lower()
                val = parts[i+1].strip()
                if "case id" in key: 
                    self.case_id = val
                    self.overview["CaseID"] = val
                if "date" in key: self.overview["Date"] = val
                if "duration" in key: self.overview["Duration"] = val

    def _extract_card_title(self, card) -> str:
        # Robust extraction: find 'header-title' class anywhere in card
        title_span = card.find('span', class_='header-title')
        if title_span:
            return title_span.get_text(strip=True)
            
        header = card.find('div', class_='card-header')
        if header:
             return header.get_text(strip=True)
             
        return "Unknown"

    def _extract_card_json(self, card) -> (Dict, str):
        """Robust extraction of structured data and raw JSON string."""
        data = {}
        raw_json_str = ""
        
        body = card.find('div', class_='card-body')
        if not body:
            return {}, ""

        # 1. JSON Table
        tables = card.find_all('table', class_='json-table')
        if tables:
            target_table = tables[-1]
            rows = target_table.find_all('tr')
            for row in rows:
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    key = th.get_text(strip=True)
                    pre = td.find('pre')
                    val = pre.get_text(strip=True) if pre else td.get_text(strip=True)
                    
                    # Try to parse nested JSON string
                    if val.strip().startswith('{') and val.strip().endswith('}'):
                        try:
                            val = json.loads(val)
                        except:
                            pass
                    data[key] = val
            raw_json_str = json.dumps(data, ensure_ascii=False)

        # 2. Pre-wrap (often contains the raw JSON output from LLM)
        pre_wraps = card.find_all('div', class_='pre-wrap')
        for pre in pre_wraps:
            text = pre.get_text(strip=True)
            if text.strip().startswith('{') or text.strip().startswith('['):
                raw_json_str = text
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        data.update(parsed)
                except:
                    pass
                    
        return data, raw_json_str

    def _parse_cards(self):
        current_d1_loop = {}
        current_d2_loop = {}
        last_stage = "初始化"

        for card in self.raw_cards:
            title = self._extract_card_title(card)
            
            # --- Error Detection ---
            if "Error" in title:
                self.overview["Final_Result"] = "Error"
                self.overview["Terminated_At_Stage"] = last_stage
                continue

            data, raw_json = self._extract_card_json(card)

            # --- D1 Loop ---
            if "D1_Loop" in title and "Doc" in title:
                if current_d1_loop:
                    self.d1_loops.append(current_d1_loop)
                current_d1_loop = {
                    "CaseID": self.case_id,
                    "Loop_Index": len(self.d1_loops) + 1,
                    "Doc_Raw_JSON": raw_json,
                    "Doc_Diagnosis": data.get("初步诊断列表", data.get("初步诊断", "")),
                    "Doc_Checks": data.get("建议检查项目", data.get("门诊检查", "")),
                    "AI_Request": data.get("诊断前所需检查", "")
                }
            elif "D1_Loop" in title and "Judge" in title and "Prompt" not in title:
                current_d1_loop["Judge_Raw_JSON"] = raw_json
                
                checks_match = data.get("检查匹配", {})
                if isinstance(checks_match, str):
                    try: checks_match = json.loads(checks_match)
                    except: checks_match = {}
                if not isinstance(checks_match, dict): checks_match = {}
                
                current_d1_loop["Judge_Missed_Checks"] = str(checks_match.get("AI建议但实际未执行的检查", checks_match.get("未匹配的检查项目", data.get("Judge_Warning", ""))))
                
                # Fallback: look in root data if not in checks_match
                match_list = checks_match.get("匹配的检查项目", [])
                if not match_list and "匹配的检查项目" in data:
                    match_list = data["匹配的检查项目"]
                current_d1_loop["Judge_Match_List"] = str(match_list)

                current_d1_loop["Judge_Match_Reason"] = str(checks_match.get("reason", data.get("reason", "")))
                current_d1_loop["Judge_Response"] = raw_json

                score_dict = data.get("评分", {})
                if isinstance(score_dict, str):
                     try: score_dict = json.loads(score_dict)
                     except: score_dict = {}

                current_d1_loop["Score_Match"] = score_dict.get("检查匹配度", data.get("Score_Match", ""))
                current_d1_loop["Score_Overall"] = score_dict.get("综合评分", data.get("Score_Overall", ""))
                current_d1_loop["Judge_Total_Count"] = data.get("总请求数量", data.get("Judge_Total_Count", ""))
                
                # Standardized key for match count
                if "匹配数量" in data:
                     current_d1_loop["Judge_Match_Count"] = data["匹配数量"]
                else:
                     current_d1_loop["Judge_Match_Count"] = data.get("Judge_Match_Count", "")
                
                self.d1_loops.append(current_d1_loop)
                current_d1_loop = {}
                last_stage = "门诊问诊"

            # --- D1 Decision ---
            if "Decision_1_Doc" in title:
                if current_d1_loop:
                    self.d1_loops.append(current_d1_loop)
                    current_d1_loop = {}
                self.d1_decision["CaseID"] = self.case_id
                self.d1_decision["Doc_Final_Decision_JSON"] = raw_json
                self.d1_decision["AI_Preliminary_Diagnosis"] = str(data.get("初步诊断列表", ""))
                self.d1_decision["AI_Suggested_Checks"] = str(data.get("建议检查项目", ""))
                last_stage = "门诊决策"
            
            if "D1_Gate_Judge" in title:
                self.d1_decision["Gate1_Judge_JSON"] = raw_json
                self.d1_decision["Gate1_Pass"] = str(data.get("是否继续评测", "Unknown"))
                self.d1_decision["Gate1_Reason"] = str(data.get("综合评分", ""))
                self.d1_decision["Gate_Diagnosis_Match"] = data.get("Gate_Diagnosis_Match", "")
                self.d1_decision["Gate_Diagnosis_Score"] = data.get("Gate_Diagnosis_Score", "")
                self.d1_decision["Gate_Check_Match"] = data.get("Gate_Check_Match", "")
                self.d1_decision["Gate_Check_Score"] = data.get("Gate_Check_Score", "")
                self.d1_decision["GT_Admission_Diagnosis"] = data.get("GT_Admission_Diagnosis", "")
                
                if self.d1_decision.get("Gate1_Pass") == "True":
                    self.d1_decision["Decision_Status"] = "Pass"
                else:
                    self.d1_decision["Decision_Status"] = "Fail"

            # --- D2 Loop ---
            # Consolidated Logic preventing duplicates
            if "D2_Loop" in title and "Doc" in title:
                if current_d2_loop:
                    self.d2_loops.append(current_d2_loop)
                current_d2_loop = {
                    "CaseID": self.case_id,
                    "Loop_Index": len(self.d2_loops) + 1,
                    "Doc_Raw_JSON": raw_json,
                    "AI_Request": data.get("补充检查申请", data.get("AI_Request", ""))
                }
            elif ("D2" in title and "Loop" in title and ("Judge" in title or "判官" in title) and "Prompt" not in title):
                current_d2_loop["Judge_Raw_JSON"] = raw_json
                
                checks_match = data.get("检查匹配", {})
                if isinstance(checks_match, str):
                    try: checks_match = json.loads(checks_match)
                    except: checks_match = {}
                
                if not isinstance(checks_match, dict): checks_match = {}
                
                current_d2_loop["Judge_Missed_Checks"] = str(checks_match.get("AI建议但实际未执行的检查", checks_match.get("未匹配的检查项目", data.get("Judge_Warning", ""))))
                # Fallback: look in root data if not in checks_match
                match_list = checks_match.get("匹配的检查项目", [])
                if not match_list and "匹配的检查项目" in data:
                    match_list = data["匹配的检查项目"]
                
                current_d2_loop["Judge_Missed_Checks"] = str(checks_match.get("AI建议但实际未执行的检查", checks_match.get("未匹配的检查项目", data.get("Judge_Warning", ""))))
                current_d2_loop["Judge_Match_List"] = str(match_list)
                
                # Score
                score_dict = data.get("评分", {})
                if isinstance(score_dict, str):
                     try: score_dict = json.loads(score_dict)
                     except: score_dict = {}
                
                current_d2_loop["Score_Match"] = score_dict.get("检查匹配度", data.get("Score_Match", ""))
                current_d2_loop["Score_Reasonable"] = score_dict.get("合理性评分", data.get("Score_Reasonable", ""))
                current_d2_loop["Judge_Total_Count"] = data.get("总请求数量", data.get("Judge_Total_Count", ""))
                
                if "匹配数量" in data:
                     current_d2_loop["Judge_Match_Count"] = data["匹配数量"]
                else:
                     current_d2_loop["Judge_Match_Count"] = data.get("Judge_Match_Count", "")
                
                current_d2_loop["Judge_Response"] = raw_json 
                current_d2_loop["Judge_Reasoning"] = str(data.get("reason", data.get("理由", raw_json)))
                
                self.d2_loops.append(current_d2_loop)
                current_d2_loop = {}
                last_stage = "入院检查"

            # --- D2 Decision ---
            if "Decision_2_Doc" in title:
                if current_d2_loop:
                    self.d2_loops.append(current_d2_loop)
                    current_d2_loop = {}
                self.d2_decision["CaseID"] = self.case_id
                self.d2_decision["Doc_Decision_JSON"] = raw_json
                self.d2_decision["AI_Revised_Diagnosis"] = data.get("修正诊断", "")
                last_stage = "入院决策"
            
            if "Gate_2_Judge" in title and "Secondary" not in title:
                self.d2_decision["Gate2_Judge_JSON"] = raw_json
                self.d2_decision["Gate2_Primary_Result"] = str(data.get("修正诊断匹配", {}))
                self.d2_decision["Gate2_Primary_Pass"] = str(data.get("是否继续评测", "Unknown"))
                self.d2_decision["Gate_Diagnosis_Match"] = data.get("Gate_Diagnosis_Match", "")
                self.d2_decision["Gate_Diagnosis_Score"] = data.get("Gate_Diagnosis_Score", "")
                self.d2_decision["Gate_Surgery_Match"] = data.get("Gate_Surgery_Match", "")
                self.d2_decision["Gate_Surgery_Score"] = data.get("Gate_Surgery_Score", "")
                self.d2_decision["GT_Revised_Diagnosis"] = data.get("GT_Revised_Diagnosis", "")

                if self.d2_decision.get("Gate2_Primary_Pass") == "True":
                    self.d2_decision["Decision_Status"] = "Pass"
                else:
                    self.d2_decision["Decision_Status"] = "Fail"

            if "Gate_2_Secondary_Judge" in title:
                self.d2_decision["Gate2_Secondary_Triggered"] = True
                self.d2_decision["Gate2_Secondary_JSON"] = raw_json
                self.d2_decision["Gate2_Secondary_Analysis"] = data.get("reasonableness_analysis", "")
                self.d2_decision["Gate2_Secondary_Conclusion"] = data.get("is_reasonable", "Unknown")
                self.d2_decision["Secondary_Judge_Override"] = data.get("Secondary_Judge_Override", "False")

            # --- D3 Surgery ---
            if "Outcome_Surgery" in title or "Outcome_D3" in title:
                self.d3_decision["CaseID"] = self.case_id
                self.d3_decision["Doc_Raw_JSON"] = raw_json
                self.d3_decision["Doc_Surgery_Plan"] = data.get("最终手术方案", data.get("手术方案", ""))
                self.d3_decision["GT_Surgery_Plan"] = data.get("GT_Surgery_Plan", "")
                self.d3_decision["AI_Final_Diagnosis"] = data.get("AI_Final_Diagnosis", "")
                self.d3_decision["AI_PostOp_Plan"] = data.get("AI_PostOp_Plan", "")
                self.d3_decision["AI_Final_Thinking"] = data.get("AI_Final_Thinking", "")
                self.d3_decision["AI_PostOp_Thinking"] = data.get("AI_PostOp_Thinking", "")
                self.d3_decision["GT_Final_Diagnosis"] = data.get("GT_Final_Diagnosis", "")
                self.d3_decision["GT_PostOp_Plan"] = data.get("GT_PostOp_Plan", "")
                last_stage = "手术阶段"

            if "Gate_3_Judge" in title:
                self.d3_decision["Gate3_Pass"] = str(data.get("是否继续评测", str(data.get("是否通过", "Unknown"))))
                self.d3_decision["Judge_Analysis"] = raw_json
                self.d3_decision["Judge_Diagnosis_Match"] = data.get("Judge_Diagnosis_Match", "")
                self.d3_decision["Judge_Plan_Match"] = data.get("Judge_Plan_Match", "")
                
                # Robost check for need_more_info which might be nested
                nmi = data.get("need_more_info", data.get("需要更多信息", "False"))
                self.d3_decision["Judge_Need_More_Info"] = str(nmi)
                
                diag_eval = data.get("诊断匹配评估", "")
                plan_eval = data.get("治疗方案匹配评估", "")
                
                conclusions = []
                def get_conclusion(json_or_str):
                    if not json_or_str: return ""
                    if isinstance(json_or_str, dict): return str(json_or_str.get("结论", ""))
                    try:
                        parsed = json.loads(json_or_str)
                        if isinstance(parsed, dict): return str(parsed.get("结论", ""))
                    except:
                        pass
                    return str(json_or_str)

                conclusions.append(get_conclusion(diag_eval))
                conclusions.append(get_conclusion(plan_eval))
                conclusions.append(str(data.get("结论", ""))) 

                need_sec = False
                for c in conclusions:
                    if "部分匹配" in c or "完全不同" in c or "方案不合理" in c:
                        need_sec = True
                        break
                
                self.d3_decision["Gate3_Need_Second_Opinion"] = need_sec
            
            # --- D4 Rehab ---
            if "Outcome_Discharge" in title or "D4_Rehab" in title:
                self.d4_plan["CaseID"] = self.case_id
                self.d4_plan["Doc_Raw_JSON"] = raw_json
                self.d4_plan["Doc_Rehab_Plan"] = data.get("出院康复计划", data.get("康复计划", ""))
                self.d4_plan["AI_Rehab_Plan"] = data.get("AI_Rehab_Plan", "")
                self.d4_plan["AI_Followup_Plan"] = data.get("AI_Followup_Plan", "")
                last_stage = "出院阶段"
            
            if "Judge_Discharge" in title or "Gate_4_Judge" in title:
                self.d4_plan["Judge_Raw_JSON"] = raw_json
                self.d4_plan["Judge_Rehab_Score"] = data.get("综合评分", data.get("Score", ""))
                self.d4_plan["Judge_Overall_Score"] = data.get("Judge_Overall_Score", "")
                self.d4_plan["GT_Rehab_Plan"] = data.get("GT_Rehab_Plan", "")
                self.d4_plan["GT_Followup_Plan"] = data.get("GT_Followup_Plan", "")

            if "Termination" in title:
                self.overview["Terminated_At_Stage"] = last_stage
                self.overview["Final_Result"] = "Fail/Terminated"

        # Cleanup leftover loops
        if current_d1_loop: self.d1_loops.append(current_d1_loop)
        if current_d2_loop: self.d2_loops.append(current_d2_loop)

        if not self.d3_decision: self.d3_decision = {"CaseID": self.case_id}
        if not self.d4_plan: self.d4_plan = {"CaseID": self.case_id}
        
        # Populate Overview
        self.overview["Gate2_Secondary_Triggered"] = self.d2_decision.get("Gate2_Secondary_Triggered", False)
        self.overview["Gate1_Pass"] = self.d1_decision.get("Gate1_Pass", "未经过")
        self.overview["Gate2_Primary_Pass"] = self.d2_decision.get("Gate2_Primary_Pass", "未经过")
        self.overview["Gate3_Pass"] = self.d3_decision.get("Gate3_Pass", "未经过")
        
        # Ensure Terminated_At_Stage field exists (initialize as empty if not set by Termination card)
        if "Terminated_At_Stage" not in self.overview:
            self.overview["Terminated_At_Stage"] = ""
        
        # Determine Final Result if not set
        if "Final_Result" not in self.overview:
            if self.d4_plan.get("Doc_Rehab_Plan") or self.d4_plan.get("Judge_Rehab_Score"):
                 self.overview["Final_Result"] = "Pass"
            else:
                 self.overview["Final_Result"] = "Incomplete/Unknown"

if __name__ == "__main__":
    test_file = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output\Foshan\claude-opus-4-1-20250805-thinking\html_traces\claude-opus-4-1-20250805-thinking_Foshan_foshan_10_trace.html"
    parser = HtmlTraceParser(test_file)
    if parser.load():
        print(f"Loaded {len(parser.d1_loops)} D1 loops")
        print(f"Gate 3: {parser.d3_decision}")
        print(f"Gate 4: {parser.d4_plan}")

