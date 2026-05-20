import os
import shutil
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    base_dir = r"D:\研究生\项目\课题7-临床评测\自动测评系统"
    analysis_dir = os.path.join(base_dir, "analysis")
    output_dir = os.path.join(base_dir, "output")
    archive_dir = os.path.join(output_dir, "archive")
    
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
        
    # List of files to move (Legacy CSVs, old pngs in analysis folder if any)
    files_to_move = [
        "analysis_summary.csv",
        "analysis_details.csv",
        "merged_data.csv",
        "metrics_summary.csv"
    ]
    
    logger.info("Cleaning up project structure...")
    
    for fname in files_to_move:
        src = os.path.join(analysis_dir, fname)
        if os.path.exists(src):
            dst = os.path.join(archive_dir, fname)
            shutil.move(src, dst)
            logger.info(f"Moved {fname} -> output/archive/")
            
    # Also clean up any loose pngs in analysis root
    for f in os.listdir(analysis_dir):
        if f.endswith(".png"):
            src = os.path.join(analysis_dir, f)
            dst = os.path.join(archive_dir, f)
            shutil.move(src, dst)
            logger.info(f"Moved {f} -> output/archive/")
            
    logger.info("Cleanup complete.")

if __name__ == "__main__":
    main()
