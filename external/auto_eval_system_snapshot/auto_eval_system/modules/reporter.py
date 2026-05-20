import json
import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)

class Reporter:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def save_report(self, patient_id: str, report_data: Dict):
        """
        Saves the evaluation report for a single patient.
        """
        filename = f"{patient_id}_report.json"
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved report for patient {patient_id} to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save report for patient {patient_id}: {e}")

    def save_summary(self, summary_data: List[Dict]):
        """
        Saves a summary of all evaluations.
        """
        filepath = os.path.join(self.output_dir, "summary_report.json")
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved summary report to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save summary report: {e}")
