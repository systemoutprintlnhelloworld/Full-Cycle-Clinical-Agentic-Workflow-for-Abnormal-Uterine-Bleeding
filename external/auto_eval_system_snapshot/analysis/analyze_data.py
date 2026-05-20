import os
import pandas as pd
import logging
import re
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = r"D:\研究生\项目\课题7-临床评测\自动测评系统\测评结果"
OUTPUT_METRICS_DIR = r"D:\研究生\项目\课题7-临床评测\自动测评系统\output\metrics"
if not os.path.exists(OUTPUT_METRICS_DIR):
    os.makedirs(OUTPUT_METRICS_DIR)

CENTERS = ["佛山", "武汉", "新疆"]
# Auto-detect models logic can be added, currently fixed list
MODELS = ["claude-opus-4-1-20250805-thinking", "deepseek-v3-1-think-250821", "gemini-2.5-pro", "gpt-5-2025-08-07", "grok-4"]

SHEET_MAP = {
    "D1_Loop": "D1_Outpatient_Loop",
    "D1_Decision": "D1_Outpatient_Decision",
    "D2_Loop": "D2_Admission_Loop",
    "D2_Decision": "D2_Admission_Decision",
    "D3_Decision": "D3_Surgery_Decision",
    "D4_Rehab": "D4_Rehab_Plan"
}

def load_excel_data(center, model):
    """Load Parsed and Judge_Parsed Excel files."""
    parsed_path = os.path.join(BASE_DIR, center, model, f"Evaluation_Summary_{model}_CN_Parsed.xlsx")
    judge_path = os.path.join(BASE_DIR, center, model, f"Evaluation_Summary_{model}_CN_Judge_Parsed.xlsx")
    
    data = {}
    
    if os.path.exists(parsed_path):
        try:
            xls_parsed = pd.ExcelFile(parsed_path)
            for sheet in xls_parsed.sheet_names:
                data[f"Parsed_{sheet}"] = pd.read_excel(parsed_path, sheet_name=sheet)
        except Exception as e:
            logger.error(f"Failed to load Parsed Excel for {center}/{model}: {e}")
            
    if os.path.exists(judge_path):
        try:
            xls_judge = pd.ExcelFile(judge_path)
            for sheet in xls_judge.sheet_names:
                data[f"Judge_{sheet}"] = pd.read_excel(judge_path, sheet_name=sheet)
        except Exception as e:
            logger.error(f"Failed to load Judge Excel for {center}/{model}: {e}")
            
    return data

def count_loop_columns(row):
    """Count number of non-empty 'Round X' columns."""
    count = 0
    # Assuming max 20 rounds
    for i in range(1, 21):
        col_patterns = [f"第{i}轮", f"Round{i}", f"Round {i}"]
        found = False
        for col_name in row.index:
            # Check if column starts with pattern and is a JSON or content column (not just a specific field)
            # Strategy: Simply check if any column related to this round has content? 
            # Better: Check the main JSON column like "第1轮_医生_原始JSON"
            if any(col_name.startswith(p) for p in col_patterns) and "原始JSON" in col_name and "需要" not in col_name and "理由" not in col_name:
                 if pd.notna(row[col_name]) and str(row[col_name]).strip() != "":
                     count = i # Update max found round
                     found = True
                     break
        # If we didn't find specific JSON, maybe check any col starting with 第i轮?
        if not found:
             # Fallback: check all cols starting with Round i
            relevant_cols = [c for c in row.index if any(c.startswith(p) for p in col_patterns)]
            if any(pd.notna(row[c]) and str(row[c]).strip() != "" for c in relevant_cols):
                 count = i
    return count

def extract_stage_metrics(data, center, model, stage_key, output_name_prefix):
    """Generic function to extract metrics for a specific stage."""
    sheet_name = SHEET_MAP.get(stage_key)
    if not sheet_name: return None
    
    # 1. Parsed Data (Status, Loops)
    parsed_key = f"Parsed_{sheet_name}"
    parsed_df = data.get(parsed_key)
    
    if parsed_df is None: return None
    
    id_col = '病例ID' if '病例ID' in parsed_df.columns else 'CaseID'
    
    out_df = parsed_df[[id_col]].copy()
    out_df['Center'] = center
    out_df['Model'] = model
    
    # Status (For Decision Sheets)
    if 'Decision' in stage_key or 'Rehab' in stage_key:
        if '状态' in parsed_df.columns:
            out_df['Status_Text'] = parsed_df['状态']
            out_df['Passed'] = parsed_df['状态'].astype(str).apply(lambda x: 1 if '顺利通过' in x or '通过' in x else 0)
        
        # Extract Confidence (Heuristic: Look for '置信度' in cols)
        # Prioritize 'diagnostics_confidence' or '最终诊断置信度'
        conf_cols = [c for c in parsed_df.columns if '置信度' in c]
        if conf_cols:
            # Pick the most relevant one (usually diagnostic confidence)
            # D1/D2 usually 'diagnostics_confidence', D3 '最终诊断置信度'
            # If multiple, prefer one containing 'diagnostics' or '诊断'
            best_conf = next((c for c in conf_cols if 'diagnostics' in c), None)
            if not best_conf:
                best_conf = next((c for c in conf_cols if '最终诊断' in c), None)
            if not best_conf:
                best_conf = conf_cols[0] # Fallback
            
            # Normalize Confidence to 0-1 (Sometimes it's 1-5 or 0-100?)
            # Usually prompts ask for 1-5 or 0-1.
            # We will just save raw for now, and handle normalization in vis.
            out_df['Confidence_Raw'] = parsed_df[best_conf]
            out_df['Confidence_Inferred_Col'] = best_conf
            
    # Loop Counts (For Loop Sheets)
    if 'Loop' in stage_key:
        # Fix: Count columns instead of rows
        out_df['Loop_Count'] = parsed_df.apply(count_loop_columns, axis=1)

    # 2. Judge Scores (For Decision Sheets)
    judge_key = f"Judge_{sheet_name}"
    judge_df = data.get(judge_key)
    
    if judge_df is not None:
        # Merge scores
        judge_id_col = '病例ID' if '病例ID' in judge_df.columns else 'CaseID'
        score_cols = [c for c in judge_df.columns if '评分' in c]
        if score_cols:
            judge_subset = judge_df[[judge_id_col] + score_cols].copy()
            out_df = pd.merge(out_df, judge_subset, left_on=id_col, right_on=judge_id_col, how='left')
            if id_col != judge_id_col:
                out_df = out_df.drop(columns=[judge_id_col])

    return out_df

def main():
    logger.info("Starting Analysis Pipeline v2 (6 Stages)...")
    
    # Containers for all collected data
    all_data = {
        "D1_Loop": [],
        "D1_Decision": [],
        "D2_Loop": [],
        "D2_Decision": [],
        "D3_Decision": [],
        "D4_Rehab": []
    }
    
    for center in CENTERS:
        center_dir = os.path.join(BASE_DIR, center)
        if not os.path.exists(center_dir):
            continue
            
        models_in_dir = [d for d in os.listdir(center_dir) if os.path.isdir(os.path.join(center_dir, d))]
        
        for model in models_in_dir:
            # if model not in MODELS: continue # Optional filter
            
            logger.info(f"Processing {center} - {model}...")
            data = load_excel_data(center, model)
            if not data: continue
            
            # Extract for each stage
            for stage_key in all_data.keys():
                df = extract_stage_metrics(data, center, model, stage_key, f"Metric_{stage_key}")
                if df is not None:
                    all_data[stage_key].append(df)
                    
    # Export all
    for stage_key, df_list in all_data.items():
        if df_list:
            full_df = pd.concat(df_list, ignore_index=True)
            # Reorder cols: Center, Model, CaseID ...
            cols = list(full_df.columns)
            priorities = ['Center', 'Model', '病例ID', 'CaseID', 'Status_Text', 'Passed', 'Loop_Count']
            
            ordered_cols = [c for c in priorities if c in cols] + [c for c in cols if c not in priorities]
            full_df = full_df[ordered_cols]
            
            file_name = f"Metric_{stage_key}.xlsx"
            out_path = os.path.join(OUTPUT_METRICS_DIR, file_name)
            full_df.to_excel(out_path, index=False)
            logger.info(f"Saved {file_name}")

    # Create Summary CSV for Visualization (Simplified Aggregation)
    logger.info("Generating Summary for Visualization...")
    summary_rows = []
    
    # We need to aggregate stats for each stage
    # Helper to get df for a stage
    def get_stage_df(key):
        if all_data[key]:
            return pd.concat(all_data[key])
        return pd.DataFrame()

    d1_dec = get_stage_df("D1_Decision")
    d1_loop = get_stage_df("D1_Loop")
    d2_dec = get_stage_df("D2_Decision")
    d2_loop = get_stage_df("D2_Loop")
    d3_dec = get_stage_df("D3_Decision")
    d4_rehab = get_stage_df("D4_Rehab")
    
    # Get all unique Center/Models
    # It's safer to iterate through folders again or just extract from one of the DFs
    if not d1_dec.empty:
        combinations = d1_dec[['Center', 'Model']].drop_duplicates()
        
        for _, row_meta in combinations.iterrows():
            center, model = row_meta['Center'], row_meta['Model']
            row = {'Center': center, 'Model': model}
            
            # 1. D1 Pass Rate
            d1_sub = d1_dec[(d1_dec['Center']==center) & (d1_dec['Model']==model)]
            if not d1_sub.empty:
                if 'Passed' in d1_sub.columns:
                    row['Pass_Rate_D1'] = d1_sub['Passed'].mean()
                    row['Count_D1'] = d1_sub['Passed'].sum()
                    row['Total_Cases'] = len(d1_sub)
                
                # Confidence D1
                if 'Confidence_Raw' in d1_sub.columns:
                    # Clean and Mean
                    # Assuming some might be mixed strings, force numeric
                    c_clean = pd.to_numeric(d1_sub['Confidence_Raw'], errors='coerce')
                    row['Confidence_D1_Mean'] = c_clean.mean()

                # Extract Scores
                score_cols = [c for c in d1_sub.columns if '评分' in c]
                for sc in score_cols:
                    row[f'Score_D1_{sc}'] = d1_sub[sc].mean()
            
            # 2. D1 Loop Stats
            if not d1_loop.empty:
                l1_sub = d1_loop[(d1_loop['Center']==center) & (d1_loop['Model']==model)]
                if not l1_sub.empty and 'Loop_Count' in l1_sub.columns:
                    row['Loop_D1_Mean'] = l1_sub['Loop_Count'].mean()
                    row['Loop_D1_Std'] = l1_sub['Loop_Count'].std()
            
            # 3. D2 Pass Rate & Scores
            if not d2_dec.empty:
                d2_sub = d2_dec[(d2_dec['Center']==center) & (d2_dec['Model']==model)]
                if not d2_sub.empty:
                    if 'Passed' in d2_sub.columns:
                        row['Pass_Rate_D2'] = d2_sub['Passed'].mean()
                        row['Count_D2'] = d2_sub['Passed'].sum()
                    
                    if 'Confidence_Raw' in d2_sub.columns:
                        c_clean = pd.to_numeric(d2_sub['Confidence_Raw'], errors='coerce')
                        row['Confidence_D2_Mean'] = c_clean.mean()

                    score_cols = [c for c in d2_sub.columns if '评分' in c]
                    for sc in score_cols:
                        row[f'Score_D2_{sc}'] = d2_sub[sc].mean()

            # 4. D2 Loop Stats
            if not d2_loop.empty:
                l2_sub = d2_loop[(d2_loop['Center']==center) & (d2_loop['Model']==model)]
                if not l2_sub.empty and 'Loop_Count' in l2_sub.columns:
                    row['Loop_D2_Mean'] = l2_sub['Loop_Count'].mean()
                    row['Loop_D2_Std'] = l2_sub['Loop_Count'].std()

            # 5. D3 Pass Rate
            if not d3_dec.empty:
                d3_sub = d3_dec[(d3_dec['Center']==center) & (d3_dec['Model']==model)]
                if not d3_sub.empty:
                     if 'Passed' in d3_sub.columns:
                        row['Pass_Rate_D3'] = d3_sub['Passed'].mean()
                        row['Count_D3'] = d3_sub['Passed'].sum()
                     
                     if 'Confidence_Raw' in d3_sub.columns:
                        c_clean = pd.to_numeric(d3_sub['Confidence_Raw'], errors='coerce')
                        row['Confidence_D3_Mean'] = c_clean.mean()

            # 6. D4 Rehab Scores
            if not d4_rehab.empty:
                 d4_sub = d4_rehab[(d4_rehab['Center']==center) & (d4_rehab['Model']==model)]
                 if not d4_sub.empty:
                     score_cols = [c for c in d4_sub.columns if '评分' in c]
                     for sc in score_cols:
                        row[f'Score_D4_{sc}'] = d4_sub[sc].mean()

            # Calculate Comprehensive Score (Average of all available score means)
            # This is a heuristic "Overall" score
            all_score_vals = [v for k, v in row.items() if 'Score_' in k and pd.notna(v)]
            if all_score_vals:
                row['Overall_Score'] = sum(all_score_vals) / len(all_score_vals)

            summary_rows.append(row)
            
    summary_df = pd.DataFrame(summary_rows)
    
    summary_path = os.path.join("analysis", "analysis_summary.csv")
    summary_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
    logger.info(f"Summary saved to {summary_path}")

if __name__ == "__main__":
    main()
