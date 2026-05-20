import os
import glob
import pandas as pd
import logging
import argparse
from parse_html_trace import HtmlTraceParser

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def batch_process(root_dir, output_file="Evaluation_Full_Report.xlsx"):
    """
    Scans root_dir for all HTML traces, parses them, and accumulates data.
    """
    html_files = glob.glob(os.path.join(root_dir, "**", "*_trace.html"), recursive=True)
    
    if not html_files:
        logger.error(f"No HTML trace files found in {root_dir}")
        return

    logger.info(f"Found {len(html_files)} traces. Starting extraction...")

    overview_list = []
    d1_list = []
    d2_list = []
    d3_list = []
    d4_list = []

    for i, fpath in enumerate(html_files):
        try:
            parser = HtmlTraceParser(fpath)
            parser.parse()
            data = parser.get_flat_data()
            
            # --- Overview Sheet ---
            case_id = data["Meta"].get("case id", "Unknown")
            # Try to infer model from path if possible, or parsing filename
            # filename example: claude-opus-4-1-20250805-thinking_Foshan_foshan_10_trace.html
            filename = os.path.basename(fpath)
            model_name = "Unknown"
            if "claude" in filename: model_name = "claude-opus" # Simplified
            elif "gemini" in filename: model_name = "gemini-pro"
            elif "grok" in filename: model_name = "grok"

            # Determine Final Status (Proxy: if D4 exists, likely PASS)
            has_d4 = bool(data["D4"].get("Doc_Rehab_Plan"))
            status = "PASS" if has_d4 else "INCOMPLETE"
            
            overview_row = {
                "CaseID": case_id,
                "Model": model_name,
                "Date": data["Meta"].get("date"),
                "Duration": data["Meta"].get("duration"),
                "Final_Status": status,
                "Total_Loops_D1": len(data["D1"]),
                "Total_Loops_D2": len(data["D2"]),
                "D1_Pass": len(data["D1"]) > 0, # Rough proxy
                "D2_Pass": len(data["D2"]) > 0,
                "D3_Pass": bool(data["D3"].get("Doc_Final_Diagnosis")),
                "D4_Pass": has_d4,
                "Final_Diagnosis": data["D3"].get("Doc_Final_Diagnosis", "")
            }
            overview_list.append(overview_row)

            # --- D1 Sheet ---
            for loop in data["D1"]:
                loop_row = {"CaseID": case_id}
                loop_row.update(loop)
                d1_list.append(loop_row)

            # --- D2 Sheet ---
            for loop in data["D2"]:
                loop_row = {"CaseID": case_id}
                loop_row.update(loop)
                d2_list.append(loop_row)

            # --- D3 Sheet ---
            if data["D3"]:
                d3_row = {"CaseID": case_id}
                d3_row.update(data["D3"])
                d3_list.append(d3_row)

            # --- D4 Sheet ---
            if data["D4"]:
                d4_row = {"CaseID": case_id}
                d4_row.update(data["D4"])
                d4_list.append(d4_row)

        except Exception as e:
            logger.error(f"Error parsing {fpath}: {e}")

        if (i+1) % 10 == 0:
            logger.info(f"Processed {i+1}/{len(html_files)}...")

    # --- Create Excel ---
    logger.info("Generating Excel Report...")
    
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        pd.DataFrame(overview_list).to_excel(writer, sheet_name="Overview", index=False)
        pd.DataFrame(d1_list).to_excel(writer, sheet_name="D1_Outpatient", index=False)
        pd.DataFrame(d2_list).to_excel(writer, sheet_name="D2_Admission", index=False)
        pd.DataFrame(d3_list).to_excel(writer, sheet_name="D3_Surgery", index=False)
        pd.DataFrame(d4_list).to_excel(writer, sheet_name="D4_Rehab", index=False)

    logger.info(f"Successfully saved to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="Root directory containing html_traces")
    parser.add_argument("--out", default="Evaluation_Report.xlsx", help="Output Excel filename")
    args = parser.parse_args()
    
    batch_process(args.dir, args.out)
