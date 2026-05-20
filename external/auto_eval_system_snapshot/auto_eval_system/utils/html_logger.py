import json
import os
import requests # Added for Live Monitor
import threading
from datetime import datetime

class HtmlTraceLogger:
    def __init__(self, output_dir_base=None, trace_dir=None, case_id=None, model_name="Unknown", center_name="Unknown", monitor_port=8000):
        """
        Hybrid Init: Supports both legacy (output_dir_base) and new (trace_dir) patterns.
        """
        self.model_name = model_name
        self.center_name = center_name # Store center name
        self.lock = threading.RLock() # Changed to RLock to fix deadlock
        self.dashboard_url = f"http://localhost:{monitor_port}/push_log"
        
        # Legacy Mode Support setup
        if output_dir_base:
            self.base_dir = output_dir_base
            # If legacy, we might not know case_id yet, wait for start_case
            self.output_dir = os.path.join(output_dir_base, "html_traces")
        elif trace_dir:
            self.output_dir = trace_dir
            self.base_dir = os.path.dirname(trace_dir)
        else:
            self.output_dir = "output/html_traces"
            self.base_dir = "output"

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
            
        # Instance state
        self.case_id = case_id
        self.logs = []
        self.start_time = datetime.now()
        
    def start_case(self, case_id, patient_data=None, center_name="Unknown"):
        """
        Legacy method called by workflow.py to begin a case.
        Resets state for reuse of the logger instance if needed.
        """
        with self.lock:
            self.case_id = case_id
            if center_name != "Unknown":
                self.center_name = center_name # Update if provided
            self.logs = []
            self.start_time = datetime.now()
            # Optionally log patient info immediately
            if patient_data:
                # Format a nice summary or just raw json
                self.log("Patient Info", patient_data, "Case Initialization", center=center_name)

    def _push_to_dashboard(self, entry):
        """Fire and forget push to dashboard"""
        def _send():
            try:
                # Ensure entry is JSON serializable
                # Ensure Model field is consistently the Evaluator Model (System)
                # entry['model'] might be Agent Model (e.g. gpt-4 used for description)
                # We want Monitor to filter by Evaluation Model (gemini-2.5-pro)
                # So we add a specific field for session filter
                if isinstance(entry, dict):
                    entry['session_model'] = self.model_name
                    entry['center'] = self.center_name
                
                requests.post(self.dashboard_url, json=entry, timeout=0.5)
            except:
                pass # Ignore connection errors (dashboard might be down)
        
        # Run in separate thread to avoid blocking main execution
        threading.Thread(target=_send, daemon=True).start()

    def add_log(self, stage, content, log_type='info', **kwargs):
        """
        Legacy Alias: Workflow.py calls this.
        Maps to new log() method.
        """
        # Map legacy types to new signature (stage, inputs, output, error)
        inputs = None
        output = None
        error_msg = None
        
        # Heuristic mapping
        if log_type == 'prompt':
            inputs = content
        elif log_type == 'json':
            output = content # JSON usually output
        elif log_type == 'error':
            error_msg = content
        else:
            if isinstance(content, dict):
                 output = content
            else:
                 # If 'info' but looks like output, maybe output? 
                 # Default to inputs/general info for simple strings?
                 # Actually legacy mapped simple strings to "output" often.
                 output = content # Default to output if uncertain
            
        # Delegate to new method ONCE
        self.log(stage, inputs, output, error=error_msg, **kwargs)

    def log(self, stage, inputs, output, error=None, model=None, center=None):
        """
        New Thread-safe logging method (Batch Runner uses this).
        Supports overriding model and center.
        """
        current_model = model if model else (self.model_name if self.model_name else "Unknown")
        # Use passed center, or stored center, or inputs heuristic, or Unknown
        current_center = center if center else getattr(self, 'center_name', "Unknown")
        
        # Heuristic for center if available in inputs (common pattern) AND NOT explicitly set
        if current_center == "Unknown" and hasattr(inputs, 'get'):
             if inputs.get('center'): current_center = inputs.get('center')
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "stage": stage,
            "inputs": inputs,
            "output": output,
            "error": str(error) if error else None,
            "model": current_model,
            "case_id": self.case_id if self.case_id else "Unknown",
            "center": current_center,
            "type": "info" # Default type
        }
        
        if error:
            entry["type"] = "error"
        elif output and (isinstance(output, dict) or (isinstance(output, str) and output.strip().startswith('{'))):
            entry["type"] = "json"
            
        # Deduplication Guard
        # Check if identical to last log (ignoring timestamp/unique ids if needed, but here content is key)
        with self.lock:
            if self.logs:
                last = self.logs[-1]
                # Compare critical fields
                if (last['stage'] == stage and 
                    last.get('inputs') == inputs and 
                    last.get('output') == output and 
                    last.get('error') == str(error) if error else None):
                    # Duplicate detected, ignore
                    return

            self.logs.append(entry)
            
        self._push_to_dashboard(entry)

    def save_trace(self):
        """
        Generates the HTML trace file (Project Echo / Cassette Futurism Style) with Grouped Sidebar.
        """
        if not self.case_id:
            return # Nothing to save
            
        # Filename Update: Model_Center_CaseID_trace.html
        base_name = f"{self.model_name}_{getattr(self, 'center_name', 'Unknown')}_{self.case_id}_trace.html"
        # Sanitize filename
        base_name = base_name.replace("/", "_").replace("\\", "_").replace(":", "-")
        filepath = os.path.join(self.output_dir, base_name)
        
        # Calculate Metadata
        end_time = datetime.now()
        duration = end_time - self.start_time
        m, s = divmod(duration.seconds, 60)
        duration_text = f"{m}m {s}s"
        
        # --- CSS GENERATION (Multi-Theme System) ---
        css = """
        :root {
            /* THME 1: ECHO (Default - Cassette Futurism) */
            /* Restored original softer aesthetic */
            --bg-color: #f4f4f0;
            --text-color: #101010;
            --accent-color: #ff5f1f; /* Orange */
            --border-color: #101010;
            
            --card-bg: #ffffff;
            --card-shadow: 6px 6px 0px var(--border-color); /* Original hard shadow kept */
            --card-radius: 6px;      /* Rounded corners restored */
            
            --sidebar-bg: #ffffff;
            --code-bg: #f1f1f1;
            
            --error-bg: #ffebee;
            --error-text: #b71c1c;
            --error-border: #d32f2f;
            --error-accent: #d32f2f;
            
            --font-mono: 'JetBrains Mono', monospace;
            --font-sans: 'Inter', sans-serif;
            --crt-opacity: 0.15;
            --border-width: 2px;     /* Standard border */
        }
        
        [data-theme="neo"] {
            /* THEME 2: NEO (Neo-Brutalism) */
            /* The new aggressive style */
            --bg-color: #e0e0e0;
            --text-color: #000000;
            --accent-color: #5555ff; /* Blurple */
            --border-color: #000000;
            
            --card-bg: #ffffff;
            --card-shadow: 8px 8px 0px #000000;
            --card-radius: 0px;      /* Square */
            
            --sidebar-bg: #f0f0f0;
            --code-bg: #e6e6e6;
            
            --error-bg: #ff0000;     /* High saturation red */
            --error-text: #000000;
            --error-border: #000000;
            --error-accent: #000000;
            
            --crt-opacity: 0.0;
            --border-width: 4px;     /* Thick border */
        }

        [data-theme="cyber"] {
            /* THEME 3: CYBER (Terminal / Glitch) */
            --bg-color: #050505;
            --text-color: #00ff41;
            --accent-color: #00ff41;
            --border-color: #003b00;
            
            --card-bg: #0d1117;
            --card-shadow: 5px 5px 0px #003b00;
            --card-radius: 0px;
            
            --sidebar-bg: #0d1117;
            --code-bg: #001a00;
            
            --error-bg: #1a0000;
            --error-text: #ff3333;
            --error-border: #ff3333;
            --error-accent: #ff0000;
            
            --crt-opacity: 0.3;
            --border-width: 2px;
        }

        [data-theme="paper"] {
            /* THEME 4: PAPER (Arch / Blueprint) */
            --bg-color: #ffffff;
            --text-color: #000000;
            --accent-color: #0056b3;
            --border-color: #000000;
            
            --card-bg: #ffffff;
            --card-shadow: 4px 4px 0px #000000;
            --card-radius: 2px;
            
            --sidebar-bg: #ffffff;
            --code-bg: #f4f4f4;
            
            --error-bg: #ffffff;
            --error-text: #000000;
            --error-border: #000000;
            --error-accent: #000000;
            
            --crt-opacity: 0.0;
            --border-width: 2px;
        }

        [data-theme="minimalist"] {
            /* THEME 5: MINIMALIST (Sspai / Clean) */
            --bg-color: #fcfcfc;
            --text-color: #333333;
            --accent-color: #d93535; /* Sspai Red */
            --border-color: #eaeaea;
            
            --card-bg: #ffffff;
            --card-shadow: 0 4px 12px rgba(0,0,0,0.05);
            --card-radius: 8px;
            
            --sidebar-bg: #fafafa;
            --code-bg: #f9f9f9;
            
            --error-bg: #fff5f5;
            --error-text: #c53030;
            --error-border: #fc8181;
            --error-accent: #e53e3e;
            
            --crt-opacity: 0.0;
            --border-width: 1px;
        }
        
        * { box-sizing: border-box; }
        
        body {
            margin: 0;
            background: var(--bg-color);
            background-image: linear-gradient(var(--border-color) 1px, transparent 1px),
                              linear-gradient(90deg, var(--border-color) 1px, transparent 1px);
            background-size: 40px 40px;
            background-position: -1px -1px;
            background-blend-mode: overlay;
            color: var(--text-color);
            font-family: var(--font-sans);
            height: 100vh;
            display: flex;
            overflow: hidden;
            transition: background 0.3s, color 0.3s;
        }

        /* Minimalist Background Override */
        [data-theme="minimalist"] body { background-image: none; }
        
        /* CRT for Echo/Cyber */
        .crt-overlay {
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.1) 50%);
            background-size: 100% 4px; /* Scanlines */
            pointer-events: none;
            z-index: 999;
            opacity: var(--crt-opacity);
            transition: opacity 0.3s;
        }
        
        /* === SIDEBAR === */
        .sidebar {
            width: 350px;
            background: var(--sidebar-bg);
            border-right: var(--border-width) solid var(--border-color);
            display: flex;
            flex-direction: column;
            z-index: 50;
            transition: background 0.3s, border-color 0.3s;
        }
        [data-theme="minimalist"] .sidebar { border-right: none; box-shadow: inset -1px 0 0 #eee; }
        
        .sidebar-header {
            background: var(--accent-color);
            padding: 20px;
            border-bottom: var(--border-width) solid var(--border-color);
            color: #fff;
        }
        [data-theme="cyber"] .sidebar-header { color: #000; font-weight: bold; }
        [data-theme="minimalist"] .sidebar-header { background: transparent; color: #333; border-bottom: 1px solid #eee; }
        
        .brand { 
            font-family: var(--font-mono); 
            font-weight: 800; font-size: 1.6rem; 
            text-transform: uppercase; display: block; 
            letter-spacing: -1px; line-height: 1;
        }
        
        .meta-info {
            font-family: var(--font-mono); font-size: 0.7rem; margin-top: 10px;
            line-height: 1.4; opacity: 0.9; font-weight: 700; text-transform: uppercase;
        }

        .nav-scroll { flex: 1; overflow-y: auto; padding: 0; }
        
        .nav-group-label {
            background: var(--border-color);
            color: var(--bg-color); 
            font-family: var(--font-mono); font-size: 0.75rem;
            padding: 6px 15px; font-weight: 800;
            border-bottom: var(--border-width) solid var(--border-color);
        }
        [data-theme="minimalist"] .nav-group-label { 
            background: transparent; color: #999; 
            border-bottom: none; padding: 15px 20px 5px; 
            font-weight: 700; 
        }
        
        .nav-item {
            display: flex; align-items: center; padding: 10px 15px;
            text-decoration: none; color: var(--text-color);
            font-family: var(--font-mono); font-size: 0.8rem;
            border-bottom: 1px solid var(--border-color);
            transition: 0.1s; opacity: 0.85;
        }
        [data-theme="minimalist"] .nav-item { 
            border-bottom: none; padding: 8px 20px; 
            border-left: 3px solid transparent; 
            opacity: 0.8; 
        }
        
        .nav-item:hover { 
            background: var(--border-color); color: var(--bg-color);
            opacity: 1;
        }
        [data-theme="minimalist"] .nav-item:hover { 
            background: #f4f4f4; color: #000; 
            border-left-color: #ddd; 
        }
        /* Neo-Brutalism Sidebar Hover: Translation */
        [data-theme="neo"] .nav-item:hover {
            transform: translateX(4px);
            box-shadow: -2px 2px 0px var(--text-color);
        }
        
        .nav-item.active { 
            background: var(--border-color); color: var(--accent-color); 
            opacity: 1; font-weight: bold;
        }
        [data-theme="cyber"] .nav-item.active { color: #000; background: var(--accent-color); }
        [data-theme="minimalist"] .nav-item.active { 
            background: transparent; 
            color: var(--accent-color); 
            border-left-color: var(--accent-color); 
        }
        [data-theme="neo"] .nav-item.active {
            transform: translateX(4px);
            box-shadow: -4px 4px 0px var(--text-color);
            background: var(--accent-color); color: #fff;
        }
        
        .nav-role-icon { width: 16px; text-align: center; margin-right: 8px; font-weight: bold; }
        .nav-text { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 600; }
        .nav-time { opacity: 0.6; font-size: 0.7rem; margin-left: 5px; }
        
        /* === MAIN CONTENT === */
        .main {
            flex: 1; overflow-y: auto; padding: 40px; position: relative;
        }
        
        .log-card {
            background: var(--card-bg);
            border: var(--border-width) solid var(--border-color);
            box-shadow: var(--card-shadow);
            border-radius: var(--card-radius);
            margin-bottom: 30px;
            position: relative;
            transition: all 0.2s;
        }
        [data-theme="minimalist"] .log-card { border: 1px solid #eee; }
        
        /* Only shake on hover/error if intended, or just hover lift */
        .log-card:hover { text-transform: none; } /* Reset potential inheritances */
        
        /* Neo-Brutalism Card Hover: Pop Effect */
        [data-theme="neo"] .log-card:hover {
            transform: translate(-4px, -4px);
            box-shadow: 12px 12px 0px var(--border-color);
        }
        
        .card-header {
            background: var(--bg-color); 
            border-bottom: var(--border-width) solid var(--border-color);
            border-radius: calc(var(--card-radius) - 2px) calc(var(--card-radius) - 2px) 0 0;
            padding: 12px 20px;
            display: flex; justify-content: space-between; align-items: center;
            font-family: var(--font-mono);
        }
        
        /* === ERROR STYLE === */
        .log-card.error {
            border-color: var(--error-border);
            box-shadow: 10px 10px 0px var(--error-border);
        }
        [data-theme="minimalist"] .log-card.error { box-shadow: 0 4px 12px rgba(197, 48, 48, 0.2); }
        
        [data-theme="neo"] .log-card.error, [data-theme="cyber"] .log-card.error {
            /* Aggressive Shake only for Neo/Cyber */
            animation: shake 0.5s cubic-bezier(.36,.07,.19,.97) both;
            border-width: 4px;
        }
        @keyframes shake {
            10%, 90% { transform: translate3d(-1px, 0, 0); }
            20%, 80% { transform: translate3d(2px, 0, 0); }
            30%, 50%, 70% { transform: translate3d(-4px, 0, 0); }
            40%, 60% { transform: translate3d(4px, 0, 0); }
        }

        .log-card.error .card-header {
            background: var(--error-accent);
            border-bottom-color: var(--error-border);
            color: #fff;
        }
        [data-theme="neo"] .log-card.error .card-header { color: #000; }
        [data-theme="cyber"] .log-card.error .card-header { color: #000; }
        [data-theme="paper"] .log-card.error .card-header { color: #fff; background: #000; }
        
        .log-card.error .card-body {
            background: var(--error-bg); color: var(--error-text);
            font-weight: 600;
            border-radius: 0 0 calc(var(--card-radius) - 2px) calc(var(--card-radius) - 2px);
        }
        
        .header-badge {
            background: var(--border-color); color: var(--bg-color);
            padding: 4px 8px; font-size: 0.8rem; font-weight: 900;
            margin-right: 12px; border-radius: 4px;
        }
        [data-theme="neo"] .header-badge { border-radius: 0px; }
        [data-theme="minimalist"] .header-badge { background: #eee; color: #555; }
        
        .header-title { font-weight: 800; font-size: 1rem; }
        .header-meta { font-size: 0.75rem; opacity: 1; font-weight: 500; }
        
        .card-body { padding: 20px; font-size: 0.95rem; line-height: 1.6; }
        
        /* Data Tables */
        .json-table {
            width: 100%; border-collapse: separate; border-spacing: 0;
            font-family: var(--font-mono); font-size: 0.85rem;
            border: var(--border-width) solid var(--border-color);
            margin-top: 15px; border-radius: var(--card-radius);
            overflow: hidden;
        }
        .json-table th, .json-table td { border-bottom: 1px solid var(--border-color); padding: 10px; vertical-align: top; }
        .json-table th { background: var(--border-color); color: var(--bg-color); width: 180px; text-align: right; border-right: 1px solid var(--border-color); }
        .json-table td { background: var(--card-bg); color: var(--text-color); }
        
        /* Minimalist Table Override */
        [data-theme="minimalist"] .json-table { border: 1px solid #eee; }
        [data-theme="minimalist"] .json-table th { background: #f9f9f9; color: #555; border-right: 1px solid #eee; border-bottom: 1px solid #eee; }
        [data-theme="minimalist"] .json-table td { border-bottom: 1px solid #eee; }
        
        .pre-wrap {
            white-space: pre-wrap; font-family: var(--font-mono);
            background: var(--code-bg); padding: 15px;
            border: 1px solid var(--border-color); border-radius: 4px;
            font-size: 0.85rem; color: var(--text-color);
        }
        [data-theme="neo"] .pre-wrap { border: var(--border-width) solid var(--border-color); border-radius: 0; }
        
        /* FAB */
        .fab-theme {
            position: fixed; bottom: 30px; right: 30px;
            width: 50px; height: 50px;
            background: var(--accent-color);
            border: var(--border-width) solid var(--border-color);
            box-shadow: 4px 4px 0px var(--border-color);
            border-radius: 50%; /* Default round for Echo */
            color: #fff; display: flex; align-items: center; justify-content: center;
            font-size: 24px; cursor: pointer; z-index: 1000;
            transition: all 0.2s;
        }
        [data-theme="neo"] .fab-theme { border-radius: 0; width: 60px; height: 60px; box-shadow: 6px 6px 0px var(--border-color); }
        [data-theme="cyber"] .fab-theme { color: #000; border-radius: 0; }
        [data-theme="minimalist"] .fab-theme { border: none; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        
        .fab-theme:hover { transform: translateY(-3px); box-shadow: 6px 6px 0px var(--border-color); }
        [data-theme="minimalist"] .fab-theme:hover { box-shadow: 0 6px 16px rgba(0,0,0,0.2); }
        
        ::-webkit-scrollbar { width: 12px; background: var(--bg-color); border-left: 1px solid var(--border-color); }
        ::-webkit-scrollbar-thumb { background: var(--accent-color); border: 1px solid var(--border-color); border-radius: 6px; }
        [data-theme="neo"] ::-webkit-scrollbar-thumb { border-radius: 0; border: 2px solid #000; }
        [data-theme="minimalist"] ::-webkit-scrollbar { background: transparent; border: none; }
        [data-theme="minimalist"] ::-webkit-scrollbar-thumb { background: #ccc; border: 3px solid transparent; background-clip: content-box; border-radius: 99px; }
        """
        
        # --- HTML Logic ---
        # Group Logs Logic (Same as before)
        grouped_logs = []
        current_group = None
        current_logs = []
        
        def get_group_name(stage):
            s = stage.lower()
            if any(x in s for x in ["patient", "d1_init", "description"]): return "00. INITIALIZATION"
            if any(x in s for x in ["decision_1", "d1_", "gate_1", "gate 1", "outpatient"]): return "01. OUTPATIENT STAGE"
            if any(x in s for x in ["decision_2", "d2_", "gate_2", "gate 2", "admission"]): return "02. ADMISSION STAGE"
            if any(x in s for x in ["decision_3", "d3_", "gate_3", "gate 3", "surgery", "outcome_surgery"]): return "03. SURGERY DECISION"
            if any(x in s for x in ["decision_4", "d4_", "judge_discharge", "outcome_discharge", "rehab"]): return "04. REHAB & FOLLOWUP"
            return "99. OTHER / SYSTEM"

        for i, log in enumerate(self.logs):
            g_name = get_group_name(log['stage'])
            if g_name != current_group:
                if current_group: grouped_logs.append((current_group, current_logs))
                current_group = g_name
                current_logs = []
            log['global_index'] = i 
            current_logs.append(log)
        if current_group: grouped_logs.append((current_group, current_logs))

        # Render Content
        sidebar_html = ""
        main_html = ""
        
        for group_title, logs in grouped_logs:
            sidebar_html += f'<div class="nav-group-label">{group_title}</div>'
            for log in logs:
                i = log['global_index']
                anchor = f"log-{i}"
                stage = log['stage']
                ts_str = log['timestamp'].split('T')[-1][:8]
                stage_display = stage
                if "D1_Loop" in stage: stage_display = f"D1 Loop {stage.split('_')[2]}"
                elif "D2_Loop" in stage: stage_display = f"D2 Loop {stage.split('_')[2]}"
                
                icon = "●"
                if "Judge" in stage: icon = "⚖"
                elif "Doc" in stage: icon = "✚"
                elif "Prompt" in stage: icon = "➤"
                elif "Gate" in stage: icon = "⚔"
                
                sidebar_html += f"""
                <a href="#{anchor}" class="nav-item">
                    <span class="nav-role-icon">{icon}</span>
                    <span class="nav-text">{stage_display}</span>
                    <span class="nav-time">{ts_str}</span>
                </a>
                """
                
                # Card Content
                log_model = log.get('model', self.model_name)
                def render_value(val):
                    if isinstance(val, str):
                        val = val.strip()
                        if (val.startswith("{") and val.endswith("}")) or (val.startswith("[") and val.endswith("]")):
                            try:
                                return f"<pre style='margin:0; white-space:pre-wrap'>{json.dumps(json.loads(val), ensure_ascii=False, indent=2)}</pre>"
                            except: pass
                        return str(val).replace("\\n", "<br>")
                    if isinstance(val, (dict, list)):
                        return f"<pre style='margin:0; white-space:pre-wrap'>{json.dumps(val, ensure_ascii=False, indent=2)}</pre>"
                    return str(val).replace("\\n", "<br>")

                content_html = ""
                if log.get('inputs'):
                    content_html += '<div style="font-weight:700; font-family:var(--font-mono); margin-bottom:5px; opacity:0.7">// INPUT</div>'
                    inp = log['inputs']
                    if isinstance(inp, dict):
                        inp_safe = inp.copy()
                        if "_metadata" in inp_safe: del inp_safe["_metadata"]
                        rows = ""
                        for k, v in inp_safe.items():
                             rows += f"<tr><th>{k}</th><td>{render_value(v)}</td></tr>"
                        content_html += f'<table class="json-table">{rows}</table>'
                    elif isinstance(inp, list):
                         for item in inp: content_html += f'<div class="pre-wrap">{item}</div>'
                    else:
                        content_html += f'<div class="pre-wrap">{str(inp)}</div>'
                
                if log.get('inputs') and log.get('output'):
                    content_html += '<br><hr style="border:0; border-top:1px dashed var(--border-color); margin:20px 0;">'

                if log.get('output'):
                    content_html += '<div style="font-weight:700; font-family:var(--font-mono); margin-bottom:5px; color:var(--accent-color)">// OUTPUT</div>'
                    out = log['output']
                    try:
                        if isinstance(out, str) and (out.strip().startswith("{") or out.strip().startswith("[")): out = json.loads(out)
                    except: pass
                    
                    if isinstance(out, dict):
                        out_safe = out.copy()
                        if "_metadata" in out_safe: del out_safe["_metadata"]
                        rows = ""
                        for k, v in out_safe.items():
                            rows += f"<tr><th>{k}</th><td>{render_value(v)}</td></tr>"
                        content_html += f'<table class="json-table">{rows}</table>'
                    else:
                        content_html += f'<div class="pre-wrap">{str(out)}</div>'

                if log.get('error'):
                    content_html += '<div style="font-weight:800; font-family:var(--font-mono); margin-bottom:5px; color:var(--error-accent)">!! ERROR TRACE !!</div>'
                    content_html += f'<div class="pre-wrap" style="background:var(--error-bg); border:1px solid var(--error-border); color:var(--error-text); font-weight:bold;">{str(log["error"])}</div>'

                card_class = "log-card"
                if log.get('type') == 'error': card_class += " error"

                main_html += f"""
                <div id="{anchor}" class="{card_class}">
                    <div class="card-header">
                        <div>
                            <span class="header-badge">#{i}</span>
                            <span class="header-title">{stage}</span>
                        </div>
                        <div class="header-meta">
                            <span>{log_model}</span> | <span>{ts_str}</span>
                        </div>
                    </div>
                    <div class="card-body">{content_html}</div>
                </div>
                """
        
        # --- Navigation Buttons Logic ---
        nav_buttons_html = ""
        try:
            # Try to extract numeric ID from case_id (e.g. wuhan_10 -> 10)
            import re
            current_id_match = re.search(r'(\d+)$', str(self.case_id))
            if current_id_match:
                curr_id = int(current_id_match.group(1))
                prefix = str(self.case_id)[:current_id_match.start(1)]
                center_val = getattr(self, 'center_name', 'Unknown')
                
                buttons = []
                # Prev Button
                if curr_id > 1:
                    prev_id = curr_id - 1
                    prev_case_id = f"{prefix}{prev_id}"
                    # Reconstruct filename: Model_Center_CaseID_trace.html
                    prev_fname = f"{self.model_name}_{center_val}_{prev_case_id}_trace.html"
                    # Sanitize
                    prev_fname = prev_fname.replace("/", "_").replace("\\", "_").replace(":", "-")
                    buttons.append(f'<a href="./{prev_fname}" class="nav-btn">← Prev</a>')
                
                # Next Button (Always generate as we don't know the end)
                next_id = curr_id + 1
                next_case_id = f"{prefix}{next_id}"
                next_fname = f"{self.model_name}_{center_val}_{next_case_id}_trace.html"
                next_fname = next_fname.replace("/", "_").replace("\\", "_").replace(":", "-")
                buttons.append(f'<a href="./{next_fname}" class="nav-btn">Next →</a>')
                
                if buttons:
                    nav_buttons_html = f'<div class="nav-buttons">{"".join(buttons)}</div>'
        except Exception as e:
            # print(f"Navgen error: {e}")
            pass

        full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>ECHO TRACE | {self.case_id}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=JetBrains+Mono:wght@400;700;800&display=swap" rel="stylesheet">
    <style>{css}</style>
    <style>
    .nav-buttons {{
        position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
        z-index: 1000; display: flex; gap: 15px; pointer-events: none;
    }}
    .nav-btn {{
        pointer-events: auto; background: rgba(255, 255, 255, 0.8); color: #333;
        border: 1px solid #ccc; padding: 8px 16px; border-radius: 4px;
        text-decoration: none; font-family: sans-serif; font-size: 14px; font-weight: bold;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1); transition: all 0.2s; opacity: 0.7;
    }}
    .nav-btn:hover {{ opacity: 1; background: #fff; box-shadow: 0 4px 8px rgba(0,0,0,0.2); transform: translateY(-2px); color: #000; }}
    [data-theme="cyber"] .nav-btn, [data-theme="neo"] .nav-btn {{ border-width: 2px; }}
    </style>
</head>
<body data-theme="echo">
    <div class="crt-overlay"></div>
    <div class="sidebar">
        <div class="sidebar-header">
            <span class="brand">Project Echo</span>
            <div class="meta-info">
                CASE: {self.case_id}<br>
                DATE: {self.start_time.strftime('%Y-%m-%d')}<br>
                TIME: {duration_text}
            </div>
        </div>
        <div class="nav-scroll">{sidebar_html}</div>
    </div>
    <div class="main"><div class="container">{main_html}</div></div>
    
    {nav_buttons_html}
    
    <button class="fab-theme" onclick="cycleTheme()" title="Switch Theme">🎨</button>
    <script>
        const themes = ["echo", "neo", "cyber", "paper", "minimalist"];
        let currentThemeIndex = 0;
        const savedTheme = localStorage.getItem('echo_theme');
        if (savedTheme && themes.includes(savedTheme)) {{
            currentThemeIndex = themes.indexOf(savedTheme);
            document.body.setAttribute('data-theme', savedTheme);
        }}
        function cycleTheme() {{
            currentThemeIndex = (currentThemeIndex + 1) % themes.length;
            const newTheme = themes[currentThemeIndex];
            document.body.setAttribute('data-theme', newTheme);
            localStorage.setItem('echo_theme', newTheme);
        }}
    </script>
</body>
</html>"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_html)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_html)
