# -*- coding: utf-8 -*-
import json
import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

import json
import os
import logging
from typing import List, Dict, Any
import pandas as pd

logger = logging.getLogger(__name__)

class DataLoader:
    def __init__(self, data_path: str):
        self.data_path = data_path

    def load_patients(self) -> List[Dict[str, Any]]:
        """
        Loads patient data from the specified path (JSON or Excel).
        """
        patients = []
        if os.path.isdir(self.data_path):
            # Recurse for directories
            for root, dirs, files in os.walk(self.data_path):
                for filename in files:
                    # Filter out temp files (Excel lock files)
                    if filename.startswith("~$"):
                        continue
                        
                    file_path = os.path.join(root, filename)
                    if filename.endswith(".json"):
                        patients.extend(self._load_json_file(file_path))
                    elif filename.endswith(".xlsx") or filename.endswith(".xls"):
                        patients.extend(self._load_excel_file(file_path))
        elif os.path.isfile(self.data_path):
            if self.data_path.endswith(".json"):
                patients.extend(self._load_json_file(self.data_path))
            elif self.data_path.endswith(".xlsx") or self.data_path.endswith(".xls"):
                patients.extend(self._load_excel_file(self.data_path))
        
        logger.info(f"Loaded {len(patients)} patients from {self.data_path}")
        return patients

    def _load_json_file(self, file_path: str) -> List[Dict]:
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                content = json.load(f)
                if isinstance(content, list):
                    return content
                else:
                    return [content]
        except Exception as e:
            logger.error(f"Failed to load JSON {file_path}: {e}")
            return []

    def _load_excel_file(self, file_path: str) -> List[Dict]:
        """
        Loads patients from Excel using CenterStrategy.
        """
        from .data_loader_strategy import get_strategy
        
        logger.info(f"Loading Excel file: {file_path}")
        strategy = get_strategy(file_path)
        try:
            return strategy.load_patients(file_path)
        except Exception as e:
            logger.error(f"Error loading Excel with strategy: {e}")
            return []

    def validate_patient_data(self, patient: Dict[str, Any]) -> bool:
        """
        Validates if the patient data has the necessary fields.
        """
        required_fields = ["id", "info", "description"] 
        for field in required_fields:
            if field not in patient:
                logger.warning(f"Patient data missing field: {field}")
                return False
        return True
