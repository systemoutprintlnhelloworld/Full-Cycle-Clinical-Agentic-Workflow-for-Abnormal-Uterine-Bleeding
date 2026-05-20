import pandas as pd
import json
import os
import shutil
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = r"D:\研究生\项目\课题7-临床评测\自动测评系统"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
FINAL_RESULT_DIR = os.path.join(BASE_DIR, "测评结果")

TARGET_CENTERS = ["Foshan-v2", "Wuhan_Fixed-v2", "Xinjiang-v2"]

# Sheets to check
SHEET_NAMES = [
    "D1_Outpatient_Loop",
    "D1_Outpatient_Decision",
    "D2_Admission_Loop", 
    "D2_Admission_Decision",
    "D3_Surgery_Decision",
    "D4_Rehab_Plan"
]

def validate_json_in_excel(file_path):
    """
    Validates that all columns containing '原始JSON' in specific sheets are valid JSON.
    Returns: (is_valid, error_list)
    """
    errors = []
    is_valid = True
    
    try:
        xls = pd.ExcelFile(file_path)
    except Exception as e:
        return False, [f"无法打开Excel文件: {str(e)}"]

    for sheet_name in SHEET_NAMES:
        if sheet_name not in xls.sheet_names:
            continue
            
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            
            # Find JSON columns
            json_cols = [col for col in df.columns if "原始JSON" in col]
            
            for col in json_cols:
                for idx, row in df.iterrows():
                    val = row[col]
                    case_id = row.get('病例ID', f'Row_{idx+1}')
                    
                    if pd.isna(val) or str(val).strip() == "":
                        # Empty is considered valid or invalid? 
                        # Based on previous context, empty might be okay if the case didn't reach that stage,
                        # but if it's there it should be valid. Let's assume non-empty check only for now.
                        continue
                        
                    val_str = str(val)
                    
                    # Check for our split markers or truncation markers
                    # If it was split, we need to handle that, but current requirement is just to check "validity"
                    # However, rescue_excel_v3 now produced CLEANED json, not split.
                    # So it should be valid JSON.
                    
                    try:
                        json.loads(val_str)
                    except json.JSONDecodeError as e:
                        # Check if it is the "Truncated" message
                        if "[已截断" in val_str:
                             # This is technically "valid" in our context as we intentionally truncated it
                             # But wait, latest fix uses CLEANING not truncation. 
                             # So we expect valid JSON.
                             errors.append(f"Sheet: {sheet_name}, Case: {case_id}, Col: {col} - Invalid JSON (可能是截断残留?): {str(e)}")
                             is_valid = False
                        else:
                             errors.append(f"Sheet: {sheet_name}, Case: {case_id}, Col: {col} - Invalid JSON: {str(e)}")
                             is_valid = False
                             
        except Exception as e:
            errors.append(f"Error processing sheet {sheet_name}: {str(e)}")
            is_valid = False
            
    return is_valid, errors

def main():
    logger.info("Starting JSON Validation and Move process...")
    
    validation_failures = []
    
    if not os.path.exists(FINAL_RESULT_DIR):
        os.makedirs(FINAL_RESULT_DIR)
        
    for center in TARGET_CENTERS:
        center_path = os.path.join(OUTPUT_DIR, center)
        if not os.path.exists(center_path):
            logger.warning(f"Center directory not found: {center_path}")
            continue
            
        # Iterate over models
        for model_name in os.listdir(center_path):
            model_dir = os.path.join(center_path, model_name)
            if not os.path.isdir(model_dir):
                continue
                
            excel_filename = f"Evaluation_Summary_{model_name}_CN.xlsx"
            excel_path = os.path.join(model_dir, excel_filename)
            
            if not os.path.exists(excel_path):
                logger.warning(f"Excel report not found in: {model_dir}")
                continue
                
            logger.info(f"Validating: {center} - {model_name}")
            
            is_valid, errors = validate_json_in_excel(excel_path)
            
            if is_valid:
                # Prepare Destination
                # 测评结果/{Center}/{Model}/...
                dest_dir = os.path.join(FINAL_RESULT_DIR, center, model_name)
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir)
                    
                dest_path = os.path.join(dest_dir, excel_filename)
                
                try:
                    shutil.copy2(excel_path, dest_path)
                    logger.info(f"✅ Valid & Moved to: {dest_path}")
                except Exception as e:
                    logger.error(f"Failed to copy file: {e}")
            else:
                logger.error(f"❌ Validation Failed for {center} - {model_name}")
                for err in errors:
                    logger.error(f"  - {err}")
                validation_failures.extend([f"[{center}/{model_name}] {e}" for e in errors])

    # Report
    if validation_failures:
        error_log_path = os.path.join(OUTPUT_DIR, "json_validation_errors.log")
        with open(error_log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(validation_failures))
        logger.info(f"Validation finished. Errors logged to {error_log_path}")
    else:
        logger.info("🎉 All Excel files passed JSON validation and have been moved!")

if __name__ == "__main__":
    main()
