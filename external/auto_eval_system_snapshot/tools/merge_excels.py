
import os
import glob
import pandas as pd
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def merge_single_excels(output_dir, output_filename="merged_evaluation.xlsx"):
    """
    Merges all single-case Excel files in `output_dir/single_excels` into one master Excel.
    """
    single_dir = os.path.join(output_dir, "single_excels")
    if not os.path.exists(single_dir):
        logger.error(f"Single excels directory not found: {single_dir}")
        return

    all_files = glob.glob(os.path.join(single_dir, "*.xlsx"))
    if not all_files:
        logger.warning("No Excel files found to merge.")
        return

    logger.info(f"Found {len(all_files)} files. Starting merge...")

    # Dictionary to hold dataframes for each sheet
    # Key: SheetName, Value: List of DataFrames
    sheets_data = {}

    for i, fpath in enumerate(all_files):
        try:
            # Read all sheets from the file
            xls = pd.ExcelFile(fpath)
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                
                if sheet_name not in sheets_data:
                    sheets_data[sheet_name] = []
                
                sheets_data[sheet_name].append(df)
        except Exception as e:
            logger.error(f"Error reading {fpath}: {e}")

        if (i + 1) % 50 == 0:
            logger.info(f"Processed {i + 1}/{len(all_files)} files...")

    # Write to Master Excel
    save_path = os.path.join(output_dir, output_filename)
    logger.info(f"Writing merged data to {save_path}...")
    
    try:
        with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
            for sheet_name, dfs in sheets_data.items():
                if dfs:
                    merged_df = pd.concat(dfs, ignore_index=True)
                    # Sort by CaseID if possible
                    if "病例ID" in merged_df.columns: # Chinese Header
                        # Extract number for sorting if possible, else string sort
                        try:
                             merged_df['sort_key'] = merged_df['病例ID'].apply(lambda x: int(str(x).split('_')[-1]) if '_' in str(x) and str(x).split('_')[-1].isdigit() else 999999)
                             merged_df = merged_df.sort_values(by='sort_key').drop(columns=['sort_key'])
                        except:
                             merged_df = merged_df.sort_values(by='病例ID')
                    elif "CaseID" in merged_df.columns:
                         merged_df = merged_df.sort_values(by="CaseID")

                    merged_df.to_excel(writer, sheet_name=sheet_name, index=False)
        logger.info("Merge Complete!")
    except Exception as e:
        logger.error(f"Failed to save merged file: {e}")

if __name__ == "__main__":
    # Example Usage: User can modify this path
    # TARGET_DIR = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output\Foshan\gemini-2.5-pro"
    import argparse
    parser = argparse.ArgumentParser(description="Merge Single Excels")
    parser.add_argument("--dir", type=str, required=True, help="Path to the model output directory (containing single_excels folder)")
    parser.add_argument("--name", type=str, default="merged_evaluation.xlsx", help="Output filename")
    
    args = parser.parse_args()
    merge_single_excels(args.dir, args.name)
