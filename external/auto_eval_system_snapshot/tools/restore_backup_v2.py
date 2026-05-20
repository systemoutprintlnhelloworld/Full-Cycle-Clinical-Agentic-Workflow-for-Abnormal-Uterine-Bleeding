import os
import shutil

OUTPUT_ROOT = r"d:\研究生\项目\课题7-临床评测\自动测评系统\output"

def restore(center, model):
    backup_dir = os.path.join(OUTPUT_ROOT, center, model, "retest_backup_2")
    if not os.path.exists(backup_dir):
        return

    print(f"Restoring {center}/{model}...")
    files = os.listdir(backup_dir)
    count = 0
    for f in files:
        src = os.path.join(backup_dir, f)
        
        dst_folder = ""
        if f.endswith(".jsonl"):
            dst_folder = "raw_traces"
        elif f.endswith("trace.html"): # careful with _trace.html
            dst_folder = "html_traces"
        elif f.endswith(".xlsx") and "Evaluation" not in f and "results" not in f:
             dst_folder = "single_excels"
        
        if dst_folder:
            dst_dir = os.path.join(OUTPUT_ROOT, center, model, dst_folder)
            if not os.path.exists(dst_dir):
                os.makedirs(dst_dir)
            dst = os.path.join(dst_dir, f)
            shutil.move(src, dst)
            count += 1
            
    print(f"  Restored {count} files.")
    
    # Remove empty backup dir
    if not os.listdir(backup_dir):
        os.rmdir(backup_dir)
        print("  Removed empty backup dir.")

centers = ["Wuhan_Fixed-v2", "Foshan-v2", "Xinjiang-v2"]
for c in centers:
    c_path = os.path.join(OUTPUT_ROOT, c)
    if not os.path.exists(c_path): continue
    
    models = [d for d in os.listdir(c_path) if os.path.isdir(os.path.join(c_path, d))]
    for m in models:
        restore(c, m)
