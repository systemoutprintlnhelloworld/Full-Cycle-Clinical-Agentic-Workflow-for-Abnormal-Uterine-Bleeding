
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from auto_eval_system.modules.data_loader_strategy import XinjiangStrategy

def test_linking():
    fpath = r"data/standardized_xinjiang.xlsx"
    if not os.path.exists(fpath):
        print(f"File not found: {fpath}")
        return

    strategy = XinjiangStrategy()
    try:
        patients = strategy.load_patients(fpath)
        print(f"Loaded {len(patients)} patients.")
        
        count_linked = 0
        for p in patients:
            findings = p.get("gt_surgery_findings", "")
            if "补充检查结果" in findings:
                count_linked += 1
                print(f"\n[MATCH] Case: {p['case_id']}")
                print(f"Findings: {findings}")
        
        print(f"\nTotal Linkages Found: {count_linked}")
        
    except Exception as e:
        print(f"Error loading: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_linking()
