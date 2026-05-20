import os
import shutil
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = r"d:\研究生\项目\课题7-临床评测\自动测评系统"
OUTPUT_ROOT = os.path.join(PROJECT_ROOT, "output")

def restore_center(center_name):
    center_dir = os.path.join(OUTPUT_ROOT, center_name)
    if not os.path.exists(center_dir):
        logger.error(f"Center dir not found: {center_dir}")
        return

    models = [d for d in os.listdir(center_dir) if os.path.isdir(os.path.join(center_dir, d))]
    
    for model in models:
        model_dir = os.path.join(center_dir, model)
        backup_dir = os.path.join(model_dir, "retest_backup")
        
        if not os.path.exists(backup_dir):
            continue
            
        logger.info(f"Restoring {center_name}/{model} from {backup_dir}...")
        
        # Target Dirs
        raw_traces_dir = os.path.join(model_dir, "raw_traces")
        html_traces_dir = os.path.join(model_dir, "html_traces")
        single_excels_dir = os.path.join(model_dir, "single_excels")
        
        for d in [raw_traces_dir, html_traces_dir, single_excels_dir]:
            if not os.path.exists(d): os.makedirs(d)
        
        # Move Files
        files = os.listdir(backup_dir)
        restored_count = 0
        restored_ids = set()
        
        for f in files:
            src = os.path.join(backup_dir, f)
            dst = ""
            
            if f.endswith(".jsonl"):
                dst = os.path.join(raw_traces_dir, f)
                # Extract ID: {model}_{center}_{cid}.jsonl
                prefix = f"{model}_{center_name}_"
                if f.startswith(prefix):
                    cid = f[len(prefix):-6]
                    restored_ids.add(cid)
            elif f.endswith(".html"):
                dst = os.path.join(html_traces_dir, f)
            elif f.endswith(".xlsx"):
                dst = os.path.join(single_excels_dir, f)
            
            if dst:
                try:
                    shutil.move(src, dst)
                    restored_count += 1
                except Exception as e:
                    logger.error(f"Failed to move {f}: {e}")

        logger.info(f"  Moved {restored_count} files back.")
        
        # Rebuild Checkpoint
        # We assume if the jsonl trace exists and we just restored it, it might be valid.
        # But to be safe, we should add these IDs back to completed_cases in checkpoint.json
        # ONLY if they are not already there.
        
        json_ckpt = os.path.join(model_dir, "checkpoint.json")
        if restored_ids:
            data = {}
            if os.path.exists(json_ckpt):
                try:
                    with open(json_ckpt, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except:
                    data = {}
            
            completed = set(str(x) for x in data.get("completed_cases", []))
            
            # Add restored IDs to completed
            # Note: Ideally we verify the trace is "complete", but for restoration we assume
            # they were complete before being cleaned.
            new_completed = completed.union(restored_ids)
            
            data["completed_cases"] = sorted(list(new_completed))
            
            with open(json_ckpt, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"  Restored {len(restored_ids)} cases to checkpoint.json")

    logger.info("Restoration Complete.")

if __name__ == "__main__":
    restore_center("Wuhan")
