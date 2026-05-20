import sys
import os
import json
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from auto_eval_system.utils.html_logger import HtmlTraceLogger

def generate_test_trace():
    test_dir = "output_ui_test"
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)
        
    logger = HtmlTraceLogger(test_dir, model_name="Design_Test_Pro_Max")
    
    # Simulate a case flow
    case_info = {
        "name": "张三",
        "age": 45,
        "history": "Hypertension",
        "complaint": "Headache for 3 days"
    }
    logger.start_case("CASE_TEST_001", case_info)
    time.sleep(0.1)
    
    # 1. Info Log
    logger.add_log("Validating", "Checking data integrity...", "info")
    
    # 2. Prompt Log
    system_prompt = "You are a helpful doctor."
    user_prompt = "Patient complains of headache. What to do?"
    logger.add_log("Decision_1_Prompt", f"System:\n{system_prompt}\n\nUser:\n{user_prompt}", "prompt")
    
    # 3. JSON Log (Complex)
    complex_data = {
        "diagnosis": "Migraine",
        "confidence": 0.85,
        "plan": ["Rest", "NSAIDs"],
        "details": {
            "severity": "moderate",
            "recurrence": False,
            "nested": {
                "deep": "value",
                "list": [1, 2, 3]
            }
        }
    }
    logger.add_log("Decision_1_Result", json.dumps(complex_data), "json")
    
    # 4. Warnings and Errors
    logger.add_log("Gate_Check", "Diagnosis mismatch detected! AI says Migraine, GT says Stroke.", "warning")
    
    # 5. Success
    logger.add_log("Final_Gate", "Gate passed successfully.", "success")
    
    # Save
    logger.save_trace()
    print(f"Trace saved to: {os.path.abspath(os.path.join(test_dir, 'html_traces', 'CASE_TEST_001_trace.html'))}")

if __name__ == "__main__":
    generate_test_trace()
