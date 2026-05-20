# -*- coding: utf-8 -*-
import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class HtmlTraceLogger:
    def __init__(self, output_dir_base="output", model_name="unknown"):
        self.output_dir_base = output_dir_base
        self.model_name = model_name
        self.current_case_id = None
        self.logs = []
        self.center_name = "Unknown"
        self.start_time = None
        self.output_dir = None # Set in start_case

    def start_case(self, case_id, patient_data, center_name=None):
        self.current_case_id = case_id
        if center_name:
            self.center_name = center_name
        else:
            self.center_name = patient_data.get('center', 'Unknown')
            
        self.logs = []
        self.start_time = datetime.now()
        
        # Create directory: output/Center/Model/html_traces
        # Updated to structure logs better
        self.output_dir = os.path.join(self.output_dir_base, self.center_name, self.model_name, "html_traces")
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Log Patient Info as first item
        self.add_log("Patient Info", json.dumps(patient_data, ensure_ascii=False, indent=2), "json")

    def add_log(self, stage, content, log_type="info", model=None):
        """
        Add a log entry.
        stage: e.g., "D1_Loop_1_Prompt"
        content: string content
        log_type: "info", "json", "prompt", "error", "warning", "success"
        model: Optional override for model attribution
        """
        entry = {
            "stage": stage,
            "content": content,
            "type": log_type,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "model": model if model else self.model_name
        }
        self.logs.append(entry)

    def log(self, stage, metadata, content, log_type="info", model=None):
        """Compatibility wrapper for add_log if needed"""
        # Some older calls might use this signature
        # metadata is ignored or appended
        if metadata:
             # If metadata has Agent info, prepend it
             if isinstance(metadata, dict) and "Agent" in metadata:
                 content = f"[Agent: {metadata['Agent']}]\n{content}"
        
        self.add_log(stage, content, log_type, model)

    def save_trace(self):
        if not self.current_case_id:
            return

        filename = f"{self.model_name}_{self.center_name}_{self.current_case_id}_trace.html"
        filepath = os.path.join(self.output_dir, filename)
        
        html_content = self._generate_html()
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"Saved HTML trace to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save HTML trace: {e}")

    def _generate_html(self):
        # Generate Sidebar Items
        sidebar_items = []
        
        # Grouping Logic
        grouped_logs = {}
        
        # Refined Grouping Logic (User Point 3 & 8)
        def get_group_name(stage):
            s = stage.lower()
            if any(x in s for x in ["patient", "d1_init", "description"]): return "00. Initialization"
            # Outpatient: D1 loop, D1 decisions, Gate 1
            if any(x in s for x in ["d1_", "gate_1", "gate 1", "outpatient"]): return "01. Outpatient Stage"
            # Admission: D2 loop, D2 decisions, Gate 2
            if any(x in s for x in ["d2_", "decision_2", "gate_2", "gate 2", "admission"]): return "02. Admission Stage"
            # Surgery: D3, Gate 3
            if any(x in s for x in ["d3_", "decision_3", "gate_3", "gate 3", "surgery"]): return "03. Surgery Stage"
            # Rehab: D4, Gate 4
            if any(x in s for x in ["d4_", "decision_4", "judge_discharge", "outcome_discharge", "rehab"]): return "04. Discharge/Rehab"
            if "error" in s: return "99. Errors"
            
            return "05. Other"

        for i, log in enumerate(self.logs):
            group = get_group_name(log['stage'])
            if group not in grouped_logs:
                grouped_logs[group] = []
            grouped_logs[group].append((i, log))

        # Build Sidebar HTML
        sidebar_html = ""
        for group in sorted(grouped_logs.keys()):
            sidebar_html += f'<div class="group-header">{group}</div>'
            for idx, log in grouped_logs[group]:
                # Shorten specific long stage names if needed
                display_name = log['stage']
                sidebar_html += f'<div class="sidebar-item" onclick="scrollToLog({idx})">{display_name}</div>'

        # Generate Main Content
        main_content = ""
        for i, log in enumerate(self.logs):
            bg_class = "scale-white" # Default
            if log['type'] == 'error': bg_class = "scale-red"
            elif log['type'] == 'warning': bg_class = "scale-yellow"
            elif log['type'] == 'success': bg_class = "scale-green"
            elif log['type'] == 'prompt': bg_class = "scale-gray"
            
            # Format JSON content
            content_display = log['content']
            if log['type'] == 'json':
                content_display = f"<pre>{log['content']}</pre>"
            elif log['type'] == 'prompt':
                content_display = f"<pre style='white-space: pre-wrap;'>{log['content']}</pre>"
            else:
                content_display = f"<div style='white-space: pre-wrap;'>{log['content']}</div>"

            main_content += f"""
            <div id="log-{i}" class="log-card {bg_class}">
                <div class="log-header">
                    <span class="log-stage">{log['stage']}</span>
                    <span class="log-meta">{log['timestamp']} | {log['model']}</span>
                </div>
                <div class="log-body">
                    {content_display}
                </div>
            </div>
            """

        template = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Eval Trace: {self.model_name} - {self.current_case_id}</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; margin: 0; display: flex; height: 100vh; overflow: hidden; background: #f0f2f5; }}
        #sidebar {{ width: 280px; background: #2c3e50; color: #ecf0f1; overflow-y: auto; display: flex; flex-direction: column; }}
        .group-header {{ background: #34495e; padding: 10px 15px; font-weight: bold; font-size: 0.9em; text-transform: uppercase; border-bottom: 1px solid #2c3e50; position: sticky; top: 0; }}
        .sidebar-item {{ padding: 8px 20px; cursor: pointer; border-bottom: 1px solid #34495e; font-size: 0.85em; }}
        .sidebar-item:hover {{ background: #3e5871; }}
        #main {{ flex: 1; padding: 20px; overflow-y: auto; scroll-behavior: smooth; }}
        .log-card {{ background: white; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 20px; overflow: hidden; border-left: 5px solid #bdc3c7; }}
        .log-header {{ background: #f8f9fa; padding: 10px 15px; border-bottom: 1px solid #eaeaea; display: flex; justify-content: space_between; align-items: center; }}
        .log-stage {{ font-weight: bold; color: #2c3e50; }}
        .log-meta {{ font-size: 0.8em; color: #7f8c8d; }}
        .log-body {{ padding: 15px; font-family: Consolas, monospace; font-size: 0.9em; line-height: 1.5; color: #333; overflow-x: auto; }}
        
        /* Accents */
        .scale-white {{ border-left-color: #bdc3c7; }}
        .scale-gray {{ border-left-color: #95a5a6; background: #fcfcfc; }}
        .scale-green {{ border-left-color: #27ae60; }}
        .scale-yellow {{ border-left-color: #f1c40f; }}
        .scale-red {{ border-left-color: #c0392b; }}
        
        pre {{ margin: 0; }}
    </style>
    <script>
        function scrollToLog(index) {{
            document.getElementById('log-' + index).scrollIntoView({{block: 'start', behavior: 'smooth'}});
        }}
    </script>
</head>
<body>
    <div id="sidebar">
        {sidebar_html}
    </div>
    <div id="main">
        {main_content}
    </div>
</body>
</html>
        """
        return template
