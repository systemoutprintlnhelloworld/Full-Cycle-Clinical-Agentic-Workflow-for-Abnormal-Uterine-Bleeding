import os
import json
import logging
import shutil
from bs4 import BeautifulSoup

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = r"d:\研究生\项目\课题7-临床评测\自动测评系统"
OUTPUT_ROOT = os.path.join(PROJECT_ROOT, "output")

def check_trace_validity(html_path):
    """
    Returns True if trace is valid (Completed or Valid Termination like Dangerous Op).
    Returns False if trace indicates System Crash (Traceback).
    """
    if not os.path.exists(html_path):
        return False
        
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
            
        # 1. Check for explicit Error card
        error_cards = soup.find_all('div', class_='log-card error')
        if error_cards:
            # Check content of error card
            for card in error_cards:
                text = card.get_text()
                if "Dangerous Operation" in text:
                    # VALID TERMINATION
                    return True
                if "Traceback" in text:
                    # SYSTEM CRASH
                    return False
            
            # If generic error without traceback or dangerous op, define as valid or invalid?
            # User example showed "Dangerous Operation" inside an Error card.
            # Assuming other errors are crashes.
            return False
            
        # 2. Check for "Error" in titles (redundant usually if card class is error)
        headers = soup.find_all('span', class_='header-title')
        for h in headers:
            if "Error" in h.get_text():
                # Double check content if possible, but title usually implies card is error
                # We defer to the card body check above which is more robust if we parse all cards.
                # If we missed it above, it means maybe the card didn't have error class but title did?
                # Let's assume Valid unless proven Crash.
                pass
                
        return True
        
    except Exception as e:
        logger.error(f"Error reading {html_path}: {e}")
        return False

def fix_checkpoints_and_clean(center_name):
    center_dir = os.path.join(OUTPUT_ROOT, center_name)
    if not os.path.exists(center_dir):
        logger.error(f"Center {center_name} not found")
        return

    models = [d for d in os.listdir(center_dir) if os.path.isdir(os.path.join(center_dir, d))]
    
    for model in models:
        model_dir = os.path.join(center_dir, model)
        json_ckpt = os.path.join(model_dir, "checkpoint.json")
        html_dir = os.path.join(model_dir, "html_traces")
        backup_dir = os.path.join(model_dir, "retest_backup")
        
        # 1. Rebuild Checkpoint from Scratch based on HTML Files
        # We trust the disk (html_traces) more than the old checkpoint
        
        if not os.path.exists(html_dir): continue
        
        all_traces = [f for f in os.listdir(html_dir) if f.endswith("_trace.html")]
        valid_cases = []
        invalid_cases = []
        
        for fname in all_traces:
            # parse ID: {model}_{center}_{cid}_trace.html
            # heuristic: split by '_'
            try:
                # e.g gpt-5_Wuhan_wuhan_51_trace.html
                # easiest is to parse from file content or regex
                # Let's try to extract ID from filename. 
                # CaseID is usually at end: ..._wuhan_51_trace.html -> wuhan_51
                base = fname.replace("_trace.html", "")
                # Find where "wuhan_" starts
                idx = base.rfind(f"{center_name.lower()}_")
                if idx == -1: 
                     # try generic
                     cid = base.split("_")[-2] + "_" + base.split("_")[-1] # risky
                else:
                     cid = base[idx:]
            except:
                continue

            fpath = os.path.join(html_dir, fname)
            if check_trace_validity(fpath):
                valid_cases.append(cid)
            else:
                invalid_cases.append(cid)
        
        # 2. Update Checkpoint
        data = {}
        if os.path.exists(json_ckpt):
            try:
                with open(json_ckpt, 'r', encoding='utf-8') as f: data = json.load(f)
            except: pass
            
        data["completed_cases"] = sorted(list(set(valid_cases)))
        
        with open(json_ckpt, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        logger.info(f"[{model}] Checkpoint Rebuilt. Valid: {len(valid_cases)}, Invalid: {len(invalid_cases)}")
        
        # 3. Move Invalid Files to Backup
        if invalid_cases:
            if not os.path.exists(backup_dir): os.makedirs(backup_dir)
            
            moved_count = 0
            for cid in invalid_cases:
                # Move HTML, JSONL, XLSX (single)
                # Patterns: 
                # HTML: {file_prefix}_trace.html (we iterate files usually)
                # JSONL: {model}_{center}_{cid}.jsonl
                # XLSX: {model}_{center}_{cid}.xlsx
                
                # We need exact filename prefix
                # It's safer to glob or iterate directory again looking for cid
                
                for root_d, _, files in os.walk(model_dir):
                    if "retest_backup" in root_d: continue
                    for f in files:
                        if cid in f: # Risky if cid="1" matches "10", "11". 
                            # Strict check: 
                            # Should end with _{cid}.jsonl or _{cid}_trace.html or _{cid}.xlsx
                            is_match = False
                            if f.endswith(f"_{cid}.jsonl") or f.endswith(f"_{cid}_trace.html") or f.endswith(f"_{cid}.xlsx"):
                                is_match = True
                            
                            if is_match:
                                try:
                                    src = os.path.join(root_d, f)
                                    dst = os.path.join(backup_dir, f)
                                    if os.path.exists(dst): os.remove(dst) # Overwrite backup
                                    shutil.move(src, dst)
                                    moved_count += 1
                                except Exception as e:
                                    logger.error(f"Move failed {f}: {e}")
            
            logger.info(f"  Moved {moved_count} invalid files to {backup_dir}")

if __name__ == "__main__":
    fix_checkpoints_and_clean("Wuhan")
