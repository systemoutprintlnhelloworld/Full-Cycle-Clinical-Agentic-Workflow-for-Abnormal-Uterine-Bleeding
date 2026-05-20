import os
import sys
import logging
import subprocess

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_script(script_name):
    script_path = os.path.join(os.path.dirname(__file__), script_name)
    logger.info(f"Running {script_name}...")
    try:
        result = subprocess.run([sys.executable, script_path], check=True, capture_output=True, text=True)
        logger.info(result.stdout)
        if result.stderr:
            logger.warning(result.stderr)
        logger.info(f"Finished {script_name}.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running {script_name}: {e}")
        logger.error(e.stderr)
        sys.exit(1)

def main():
    logger.info("Starting Analysis Pipeline...")
    
    # 1. Analyze Data
    run_script("analyze_data.py")
    
    # 2. Visualize Results
    run_script("visualize_results.py")
    
    logger.info("Pipeline completed successfully!")
    logger.info("Results saved to: output/figures")

if __name__ == "__main__":
    main()
