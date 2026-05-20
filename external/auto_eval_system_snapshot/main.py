# -*- coding: utf-8 -*-
import argparse
import logging
import sys
import os
import subprocess
import time
from datetime import datetime

# Rich Imports
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, TimeElapsedColumn, MofNCompleteColumn

# Ensure project root in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from auto_eval_system.modules.workflow import EvaluationWorkflow
from auto_eval_system.batch_runner import BatchEvaluator

# Ensure logs directory exists
if not os.path.exists("logs"):
    os.makedirs("logs")

log_filename = f"logs/system_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Setup Rich Console
console = Console(force_terminal=True)

# Configure Logging with RichHandler
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[
        RichHandler(console=console, rich_tracebacks=True, show_path=False),
        logging.FileHandler(log_filename, encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

AVAILABLE_MODELS = [
    "gemini-2.5-pro",
    "gpt-5-2025-08-07",
    "claude-opus-4-1-20250805-thinking",
    "deepseek-v3-1-think-250821",
    "grok-4"
]

def kill_port(port=8000):
    """Kills any process listening on the specified port"""
    try:
        import subprocess
        # Find PID
        result = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True).decode()
        if "LISTENING" in result:
            pid = result.strip().split()[-1]
            subprocess.run(f"taskkill /F /PID {pid}", shell=True)
            print(f"Killed process {pid} on port {port}")
    except:
        pass # No process found

def infer_center_from_path(data_path):
    """
    Infers center name from data filename.
    Standardized Strategy: data/standardized_xinjiang.xlsx -> Xinjiang
    """
    if not data_path: return "Unknown"
    basename = os.path.basename(data_path).lower()
    if "xinjiang" in basename: return "Xinjiang"
    if "wuhan" in basename: return "Wuhan"
    if "foshan" in basename: return "Foshan"
    return "Unknown"

def main():
    parser = argparse.ArgumentParser(description="Clinical Evaluation System")
    
    # Mode Selection
    parser.add_argument("--legacy", action="store_true", help="Force run in legacy single-threaded mode")
    
    # Batch / Scalability Args
    parser.add_argument("--threads", type=int, default=1, help="Number of concurrent threads (default: 1)")
    parser.add_argument("--centers", nargs="+", help="List of centers to evaluate (e.g. foshan wuhan). Defaults to all in data/clinical_cases")
    parser.add_argument("--models", nargs="+", help="List of models to run. Defaults to gemini-2.5-pro")
    
    # Legacy / Single Path Args
    parser.add_argument("--model", type=str, help="Legacy: Specific model to run")
    parser.add_argument("--all-models", action="store_true", help="Legacy: Run all available models sequentially")
    parser.add_argument("--data", type=str, default="data/raw", help="Legacy: Path to data directory or file")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of cases to run (0 for all)")
    parser.add_argument("--port", type=int, default=8000, help="Port for Live Monitor Server (default: 8000)")
    
    args = parser.parse_args()
    
    # --- Model Alias Mapping ---
    model_aliases = {
        "gpt-5": "gpt-5-2025-08-07",
        "gemini-2.5": "gemini-2.5-pro",
        "claude-opus": "claude-opus-4-1-20250805-thinking",
        "deepseek": "deepseek-v3-1-think-250821",
        "grok": "grok-4"
    }
    # Determine Models
    target_models = []
    if args.models:
        target_models = args.models
    elif args.all_models:
        target_models = AVAILABLE_MODELS
    elif args.model:
        raw = args.model
        mapped = model_aliases.get(raw, raw)
        if raw != mapped:
            logger.info(f"Mapping model alias '{raw}' -> '{mapped}'")
        target_models = [mapped]
    else:
        if args.legacy or (args.threads == 1 and not args.centers):
             logger.warning("No model specified. Using default: gemini-2.5-pro")
             target_models = ["gemini-2.5-pro"]
        else:
             logger.info(f"No model specified in Batch Mode. Defaulting to ALL {len(AVAILABLE_MODELS)} models.")
             target_models = AVAILABLE_MODELS
    
    target_models = [model_aliases.get(m, m) for m in target_models]
    target_centers = args.centers if args.centers else []

    # Init Progress Bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,  # Keep bar after finish
        refresh_per_second=10
    ) as progress:

        if not args.legacy and (args.threads > 1 or len(target_centers) > 0):
            logger.info(f"=== RUNNING IN BATCH MODE (Threads: {args.threads}) ===")
            
            # Setup Task
            task_id = progress.add_task("Batch Evaluation...", total=None)
            
            def batch_progress(advance, total=None):
                if total is not None:
                    progress.update(task_id, total=total)
                    if total > 0:
                         progress.start_task(task_id)
                progress.update(task_id, advance=advance)
                # Update Description with Count
                current_task = progress.tasks[task_id]
                progress.update(task_id, description=f"Batch Progress: {current_task.completed}/{current_task.total if current_task.total else '?'} cases")

            try:
                # Assuming data is in 'data/clinical_cases' or similar structure if centers specified
                # We need to refine where BatchEvaluator looks for data.
                # Since BatchEvaluator logic was placeholder, we rely on its defaults.
                runner = BatchEvaluator(target_centers, target_models, max_workers=args.threads, monitor_port=args.port)
                runner.run(limit=args.limit, progress_callback=batch_progress)
            except Exception as e:
                logger.error(f"Batch execution failed: {e}")
            
        else:
            # --- LEGACY / SINGLE MODE ---
            logger.info("=== RUNNING IN LEGACY/SINGLE MODE ===")
            
            task_id = progress.add_task("Legacy Evaluation...", total=None)

            def legacy_progress(advance, total=None):
                 if total is not None:
                      progress.update(task_id, total=total)
                      if total > 0: progress.start_task(task_id)
                 progress.update(task_id, advance=advance)

            if args.centers:
                # Legacy Hybrid: Iterate Centers
                for center in args.centers:
                    center_path = os.path.join("data", "raw", center) 
                    if not os.path.exists(center_path):
                        center_path = os.path.join("data", center)
                    
                    real_center_name = infer_center_from_path(center)
                    
                    for model in target_models:
                        progress.update(task_id, description=f"Evaluating {model} @ {real_center_name}")
                        
                        structured_out_dir = os.path.join("output", real_center_name, model)
                        
                        logger.info(f"Starting pipeline for model: {model} on center: {center}")
                        try:
                            workflow = EvaluationWorkflow(
                                model_name=model, 
                                data_path=center_path,
                                output_dir=structured_out_dir,
                                center_name=real_center_name,
                                monitor_port=args.port
                            )
                            workflow.run(limit=args.limit, progress_callback=legacy_progress)
                        except Exception as e:
                            logger.error(f"Failed to run workflow for {model}: {e}")
            else:
                # Pure Legacy
                center_from_file = infer_center_from_path(args.data)
                
                for model in target_models:
                    progress.update(task_id, description=f"Evaluating {model} @ {center_from_file}")
                    
                    structured_out_dir = os.path.join("output", center_from_file, model)
                    
                    logger.info(f"Starting pipeline for model: {model} (Center: {center_from_file})")
                    logger.info(f"Output Directory: {structured_out_dir}")
                    
                    try:
                        workflow = EvaluationWorkflow(
                            model_name=model, 
                            data_path=args.data,
                            output_dir=structured_out_dir,
                            center_name=center_from_file,
                            monitor_port=args.port
                        )
                        workflow.run(limit=args.limit, progress_callback=legacy_progress)
                    except Exception as e:
                        logger.error(f"Failed to run workflow for {model}: {e}")
            
    logger.info("All tasks completed.")

if __name__ == "__main__":
    # Parse port manually for server startup
    import sys
    port = 8000
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            try:
                port = int(sys.argv[i+1])
            except ValueError:
                pass
                
    # Clean up old server
    kill_port(port) 
    
    # START LIVE MONITOR SERVER (Subprocess)
    print(f"Starting Live Monitor Server on port {port}...")
    server_process = subprocess.Popen([sys.executable, "auto_eval_system/utils/server.py", str(port)])
    
    import time
    time.sleep(2)
    
    print("\n" + "="*50)
    print(f" ACCESS LIVE MONITOR: http://localhost:{port} ")
    print("="*50 + "\n")

    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nShutting down Live Monitor Server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        print("Server shutdown complete.")
