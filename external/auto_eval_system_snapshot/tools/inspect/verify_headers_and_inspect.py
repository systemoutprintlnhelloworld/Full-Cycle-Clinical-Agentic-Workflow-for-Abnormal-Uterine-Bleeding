# -*- coding: utf-8 -*-
import os
import pandas as pd
import logging
from auto_eval_system.modules.logger import EvaluationLogger
from auto_eval_system.modules.data_loader_strategy import get_strategy

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_system_headers():
    """生成系统预期的Excel表头并输出"""
    print("\n=== 1. System Output Headers Verification ===")
    output_dir = "output_verification"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    eval_logger = EvaluationLogger(output_dir=output_dir, model_name="header_check")
    
    # Access headers directly
    headers = eval_logger.headers
    
    report_lines = []
    report_lines.append("# System Output Header Report\n")
    
    for sheet, cols in headers.items():
        print(f"Sheet: [{sheet}] - {len(cols)} columns")
        report_lines.append(f"## Sheet: {sheet}")
        report_lines.append(f"Count: {len(cols)}")
        report_lines.append("| Index | Column Name |")
        report_lines.append("|---|---|")
        for idx, col in enumerate(cols):
            report_lines.append(f"| {idx+1} | {col} |")
        report_lines.append("\n")
        
    with open("docs/system_headers_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print("Report saved to docs/system_headers_report.md")

def inspect_raw_data_headers(data_dir="data/raw"):
    """扫描原始数据的表头"""
    print(f"\n=== 2. Raw Data Headers Inspection ({data_dir}) ===")
    
    if not os.path.exists(data_dir):
        print(f"Directory {data_dir} does not exist.")
        return

    report_lines = []
    report_lines.append("# Raw Data Columns Report\n")
    
    for root, dirs, files in os.walk(data_dir):
        for file in files:
            if not file.endswith((".xlsx", ".xls")):
                continue
                
            file_path = os.path.join(root, file)
            print(f"Inspecting {file}...")
            
            try:
                # Simple read to find possible header
                df = pd.read_excel(file_path, header=None, nrows=10)
                
                # Heuristic to find header row (longest row of strings?)
                # Or just print first few rows
                report_lines.append(f"## File: {file}")
                
                # Strategy identification
                strategy = get_strategy(file_path)
                report_lines.append(f"**Strategy**: {strategy.__class__.__name__}")
                
                report_lines.append("### First 5 Rows (Raw):")
                markdown_table = df.head(5).to_markdown(index=True)
                report_lines.append(markdown_table)
                report_lines.append("\n")
                
            except Exception as e:
                print(f"Error reading {file}: {e}")
                report_lines.append(f"Error reading {file}: {e}\n")

    with open("docs/raw_data_columns_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print("Report saved to docs/raw_data_columns_report.md")

if __name__ == "__main__":
    if not os.path.exists("docs"):
        os.makedirs("docs")
        
    try:
        verify_system_headers()
        inspect_raw_data_headers()
    except Exception as e:
        print(f"An error occurred: {e}")
