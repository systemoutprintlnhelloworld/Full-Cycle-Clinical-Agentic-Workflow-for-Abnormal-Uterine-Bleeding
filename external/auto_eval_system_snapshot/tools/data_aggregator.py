import os
import pandas as pd
import logging
from typing import Dict, List, Optional
import re

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DataAggregator:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.case_id_col = "病例ID"
        
    def load_and_merge_data(self, target_centers: List[str] = None, target_models: List[str] = None) -> pd.DataFrame:
        all_cases = []
        
        results_dir = os.path.join(self.base_dir, "测评结果")
        if not os.path.exists(results_dir):
            logger.error(f"Results directory not found: {results_dir}")
            return pd.DataFrame()

        centers = [d for d in os.listdir(results_dir) if os.path.isdir(os.path.join(results_dir, d))]
        if target_centers:
            centers = [c for c in centers if c in target_centers]

        for center in centers:
            center_path = os.path.join(results_dir, center)
            files = [f for f in os.listdir(center_path) if f.endswith("_Parsed.xlsx") and not f.startswith("~") and "_Judge_" not in f]
            
            for doc_file in files:
                try:
                    prefix = "Evaluation_Summary_"
                    suffix = "_CN_Parsed.xlsx"
                    if not (doc_file.startswith(prefix) and doc_file.endswith(suffix)):
                        continue
                        
                    model_name = doc_file[len(prefix):-len(suffix)]
                    if target_models and model_name not in target_models:
                        continue
                        
                    judge_file = doc_file.replace("_Parsed.xlsx", "_Judge_Parsed.xlsx")
                    judge_path = os.path.join(center_path, judge_file)
                    doc_path = os.path.join(center_path, doc_file)
                    
                    if not os.path.exists(judge_path):
                        logger.warning(f"Missing Judge file for {model_name} in {center}: {judge_file}")
                        continue
                        
                    logger.info(f"Processing Center: {center}, Model: {model_name}")
                    
                    case_data = self._process_model_files(doc_path, judge_path, center, model_name)
                    all_cases.extend(case_data)
                    
                except Exception as e:
                    logger.error(f"Error processing file {doc_file} in {center}: {e}")

        df = pd.DataFrame(all_cases)
        logger.info(f"Aggregated {len(df)} cases total.")
        return df

    def _process_model_files(self, doc_path: str, judge_path: str, center: str, model_name: str) -> List[Dict]:
        try:
            xls_doc = pd.ExcelFile(doc_path)
            xls_judge = pd.ExcelFile(judge_path)
        except Exception as e:
            logger.error(f"Failed to open Excel files: {e}")
            return []

        doc_sheets = {name: pd.read_excel(xls_doc, name) for name in xls_doc.sheet_names}
        judge_sheets = {name: pd.read_excel(xls_judge, name) for name in xls_judge.sheet_names}

        # Use D1 Decision as base
        if "D1_Outpatient_Decision" not in doc_sheets:
            return []
            
        base_df = doc_sheets["D1_Outpatient_Decision"]
        if self.case_id_col not in base_df.columns:
            logger.error(f"Missing ID column '{self.case_id_col}' in {doc_path}")
            return []

        merged_cases = []
        
        for _, row in base_df.iterrows():
            case_id = row.get(self.case_id_col)
            if pd.isna(case_id): continue
            
            record = {
                "CaseID": case_id,
                "Center": center,
                "Model": model_name
            }
            
            # --- Merge Logic with Chinese Column Handling ---
            
            # 1. D1 Doc
            self._merge_sheet_row(record, row, "D1_Doc")
            
            # 2. D1 Judge
            if "D1_Outpatient_Decision" in judge_sheets:
                j_row = self._find_row(judge_sheets["D1_Outpatient_Decision"], case_id)
                self._merge_sheet_row(record, j_row, "D1_Judge")
                
            # 3. D2 Doc & Judge
            if "D2_Admission_Decision" in doc_sheets:
                d2_row = self._find_row(doc_sheets["D2_Admission_Decision"], case_id)
                self._merge_sheet_row(record, d2_row, "D2_Doc")
            if "D2_Admission_Decision" in judge_sheets:
                j2_row = self._find_row(judge_sheets["D2_Admission_Decision"], case_id)
                self._merge_sheet_row(record, j2_row, "D2_Judge")
                
            # 4. D3 Doc & Judge
            if "D3_Surgery_Decision" in doc_sheets:
                d3_row = self._find_row(doc_sheets["D3_Surgery_Decision"], case_id)
                self._merge_sheet_row(record, d3_row, "D3_Doc")
            if "D3_Surgery_Decision" in judge_sheets:
                j3_row = self._find_row(judge_sheets["D3_Surgery_Decision"], case_id)
                self._merge_sheet_row(record, j3_row, "D3_Judge")
                
            # 5. Loop Counts
            if "D1_Outpatient_Loop" in doc_sheets:
                loops = doc_sheets["D1_Outpatient_Loop"]
                loops = loops[loops[self.case_id_col] == case_id]
                record["Metric_Loop_Count_D1"] = len(loops)
                
            if "D2_Admission_Loop" in doc_sheets:
                loops = doc_sheets["D2_Admission_Loop"]
                loops = loops[loops[self.case_id_col] == case_id]
                record["Metric_Loop_Count_D2"] = len(loops)

            merged_cases.append(record)
            
        return merged_cases

    def _find_row(self, df: pd.DataFrame, case_id: str) -> Optional[pd.Series]:
        if self.case_id_col not in df.columns: return None
        matches = df[df[self.case_id_col] == case_id]
        if len(matches) > 0:
            return matches.iloc[0]
        return None

    def _merge_sheet_row(self, record: Dict, row: pd.Series, prefix: str):
        if row is None: return
        for col in row.index:
            if col == self.case_id_col: continue
            
            # Simple Rename for cleaner keys
            clean_col = col.replace("医生决策_原始JSON_", "").replace("Gate1判官_原始JSON_", "").replace("Gate2判官_原始JSON_", "")
            # keep chinese or handle unicode? Pandas handles unicode fine.
            # Ideally verify if pandas output creates readable CSV.
            
            key = f"{prefix}_{clean_col}"
            record[key] = row[col]

if __name__ == "__main__":
    agg = DataAggregator(r"D:\研究生\项目\课题7-临床评测\自动测评系统")
    df = agg.load_and_merge_data()
    print(f"Loaded DataFrame with shape: {df.shape}")
    if not df.empty:
        output_path = r"D:\研究生\项目\课题7-临床评测\自动测评系统\analysis\merged_data.csv"
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"Saved to {output_path}")
