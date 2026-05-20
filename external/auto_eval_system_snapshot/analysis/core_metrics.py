import pandas as pd
import numpy as np
import json
import logging
import ast

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MetricsCalculator:
    def __init__(self, input_csv: str):
        self.df = pd.read_csv(input_csv)
        
    def calculate_all(self) -> pd.DataFrame:
        """Calculates ALL core metrics and returns a summary DataFrame by Model/Center."""
        
        # 0. Calculate Derived Status Columns (Fix for missing columns)
        self.df["Metric_Gate1_Passed"] = self.df["D1_Judge_是否继续评测"].apply(lambda x: "Passed" if str(x) == "True" else "Failed")
        # Check for secondary override if column exists
        if "D1_Judge_是否启动二级Recheck" in self.df.columns: 
             # Logic might be complex, simplified for now: if recheck triggered and output passed -> Override?
             # Actually "Status" column in original excel might have "Secondary_Judge_Override"
             pass
        
        self.df["Metric_Gate2_Passed"] = self.df.get("D2_Judge_是否继续评测", pd.Series(["Failed"]*len(self.df))).apply(lambda x: "Passed" if str(x) == "True" else "Failed")
        self.df["Metric_Gate3_Passed"] = self.df.get("D3_Judge_是否继续评测", pd.Series(["Failed"]*len(self.df))).apply(lambda x: "Passed" if str(x) == "True" else "Failed")

        # 1. Preprocess for JSON fields if needed
        self._preprocess_json_cols()
        
        # 2. Calculate Row-level Metrics (e.g. check precision per case)
        self.df["Metric_Check_Recall"] = self.df.apply(self._calc_recall, axis=1)
        self.df["Metric_Check_Precision"] = self.df.apply(self._calc_precision, axis=1)
        self.df["Metric_Check_F1"] = self.df.apply(lambda r: self._calc_f1(r["Metric_Check_Precision"], r["Metric_Check_Recall"]), axis=1)
        
        # 3. Aggregation by Model + Center
        group_cols = ["Center", "Model"]
        summary = self.df.groupby(group_cols).agg({
            "Metric_Check_Recall": "mean",
            "Metric_Check_Precision": "mean",
            "Metric_Check_F1": "mean",
            "Metric_Loop_Count_D1": "mean",
            "Metric_Loop_Count_D2": "mean",
            "CaseID": "count" # Total cases
        }).reset_index()
        
        # 4. Gate Pass Rates
        gate_summary = self._calc_gate_pass_rates(group_cols)
        summary = pd.merge(summary, gate_summary, on=group_cols, how="left")
        
        # 5. Loop Efficiency
        # Loop Efficiency = 1 / (Average Loop Count). Higher is better.
        summary["Metric_Loop_Efficiency_D1"] = 1 / summary["Metric_Loop_Count_D1"]
        
        # 6. Error Cascade (Experimental)
        cascade_stats = self._calc_error_cascade(group_cols)
        summary = pd.merge(summary, cascade_stats, on=group_cols, how="left")

        return summary

    def _preprocess_json_cols(self):
        pass

    def _calc_recall(self, row):
        # Recall = Matched / GT_Total
        # Try finding "检查匹配_匹配度" (0.0 - 1.0)
        col_candidates = [
            "D1_Judge_检查匹配_匹配度",
            "D1_Judge_Gate1判官_原始JSON_检查匹配_匹配度" # In case regex didn't catch header
        ]
        
        for col in col_candidates:
            val = row.get(col)
            if pd.notna(val): 
                try:
                    return float(val)
                except: pass
        
        # Fallback: Parse from JSON
        start_json = row.get("D1_Judge_Gate1判官_原始JSON")
        if pd.notna(start_json):
            try:
                data = json.loads(str(start_json))
                return float(data.get("检查匹配", {}).get("匹配度", 0))
            except: pass
            
        return np.nan

    def _calc_precision(self, row):
        # Precision proxy: Score / 100
        col_candidates = ["D1_Judge_检查匹配_评分", "D1_Judge_综合评分"]
        for col in col_candidates:
            val = row.get(col)
            if pd.notna(val):
                try: 
                    return float(val) / 100.0
                except: pass
        return np.nan

    def _calc_f1(self, prec, rec):
        if pd.isna(prec) or pd.isna(rec) or (prec + rec) == 0:
            return 0
        return 2 * (prec * rec) / (prec + rec)

    def _calc_gate_pass_rates(self, group_cols):
        res = []
        grouped = self.df.groupby(group_cols)
        for name, group in grouped:
            stats = {k:v for k,v in zip(group_cols, name)}
            
            # Gate 1
            g1_counts = group["Metric_Gate1_Passed"].value_counts(normalize=True)
            stats["Gate1_Pass_Rate"] = g1_counts.get("Passed", 0) + g1_counts.get("Override", 0)
            
            # Gate 2
            g2_counts = group["Metric_Gate2_Passed"].value_counts(normalize=True)
            stats["Gate2_Pass_Rate"] = g2_counts.get("Passed", 0)
            
            # Gate 3
            g3_counts = group["Metric_Gate3_Passed"].value_counts(normalize=True)
            stats["Gate3_Pass_Rate"] = g3_counts.get("Passed", 0)
            
            res.append(stats)
            
        return pd.DataFrame(res)

    def _calc_error_cascade(self, group_cols):
        res = []
        grouped = self.df.groupby(group_cols)
        for name, group in grouped:
            stats = {k:v for k,v in zip(group_cols, name)}
            
            d1_failed = group[group["Metric_Gate1_Passed"] == "Failed"]
            if len(d1_failed) > 0:
                d2_failed_given_d1 = d1_failed[d1_failed["Metric_Gate2_Passed"] == "Failed"]
                cascade_rate = len(d2_failed_given_d1) / len(d1_failed)
            else:
                cascade_rate = 0.0
            
            stats["Metric_Error_Cascade_D1_to_D2"] = cascade_rate
            res.append(stats)
        return pd.DataFrame(res)

if __name__ == "__main__":
    input_path = r"D:\研究生\项目\课题7-临床评测\自动测评系统\analysis\merged_data.csv"
    output_path = r"D:\研究生\项目\课题7-临床评测\自动测评系统\analysis\metrics_summary.csv"
    
    calc = MetricsCalculator(input_path)
    summary_df = calc.calculate_all()
    
    summary_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"Metrics calculated. Saved to {output_path}")
    print(summary_df.head())
