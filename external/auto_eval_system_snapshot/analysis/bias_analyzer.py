import pandas as pd
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BiasAnalyzer:
    def __init__(self, raw_data_path: str, output_dir: str):
        self.df = pd.read_csv(raw_data_path)
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            pass # assumed created

    def prepare_data_for_judge(self):
        """
        Extracts Final Diagnosis pairs for Bias Analysis.
        Logic:
        1. Get GT Final Diagnosis (D3 or D2)
        2. Get AI Final Diagnosis (D3 Decision or D2 Revised)
        3. Save to CSV for external Judge Agent 
        """
        # Columns in merged data might be:
        # D3_Doc_医生决策_原始JSON_修正诊断 (if D2) or D3 Final
        # Let's check headers in merged_data.csv carefully.
        # Ideally agg script pulled D3_Doc columns.
        
        # Candidate columns for AI Final Diagnosis
        ai_diag_cols = [
            "D3_Doc_医生_原始JSON_最终诊断_诊断名称",
            "D3_Doc_最终诊断", 
            "D3_Doc_修正诊断",
            "D2_Doc_修正诊断"
        ]
        
        # Candidate columns for GT
        gt_diag_cols = [
            "GT_Final_Diagnosis",
            "D3_Doc_GT_Final_Diagnosis", # If merged with prefix
            "D1_Doc_GT_Admission_Diagnosis" # Fallback
        ]
        
        export_rows = []
        
        for idx, row in self.df.iterrows():
            case_id = row.get("CaseID")
            
            # Find AI Diag
            ai_diag = None
            for col in ai_diag_cols:
                val = row.get(col)
                if pd.notna(val):
                    ai_diag = val
                    break
            
            # Find GT Diag
            gt_diag = row.get("GT_Final_Diagnosis")
            
            if ai_diag and gt_diag:
                export_rows.append({
                    "CaseID": case_id,
                    "Center": row.get("Center"),
                    "Model": row.get("Model"),
                    "AI_Diagnosis": ai_diag,
                    "GT_Diagnosis": gt_diag
                })
        
        if not export_rows:
            logger.warning("No valid diagnosis pairs found for bias analysis.")
            return
            
        out_df = pd.DataFrame(export_rows)
        out_path = os.path.join(self.output_dir, "bias_analysis_input.csv")
        out_df.to_csv(out_path, index=False, encoding='utf-8-sig')
        logger.info(f"Exported {len(out_df)} cases for bias analysis to {out_path}")

if __name__ == "__main__":
    analyzer = BiasAnalyzer(
        raw_data_path=r"D:\研究生\项目\课题7-临床评测\自动测评系统\analysis\merged_data.csv",
        output_dir=r"D:\研究生\项目\课题7-临床评测\自动测评系统\analysis"
    )
    analyzer.prepare_data_for_judge()
