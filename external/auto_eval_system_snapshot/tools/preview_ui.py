import json
import os
import sys
from datetime import datetime

# --- CONFIG: ECHO / CASSETTE FUTURISM ---
# Style v3 base, with refinements for data completeness
COLORS = {
    "bg": "#f4f4f0",       # Off-white paper
    "grid": "#e5e5e5",
    "orange": "#ff5f1f",   # Echo Orange
    "black": "#101010",    # Deep Black
    "dark_grey": "#333",
    "light_grey": "#aaa",
}

def load_data(filepath):
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    data.append(json.loads(line))
                except: pass
    
    # Metadata calculations
    start_dt = None
    end_dt = None
    
    processed = []
    for item in data:
        ts = item.get('timestamp')
        dt = None
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                if not start_dt or dt < start_dt: start_dt = dt
                if not end_dt or dt > end_dt: end_dt = dt
            except: pass
            
        # Role Detection
        stage = item.get('stage', 'Unknown')
        role = "SYS"
        if "Prompt" in stage: role = "AI_PROMPT"
        elif "Judge" in stage: role = "JUDGE"
        elif "Doc" in stage or "Doctor" in stage: role = "DOCTOR"
        elif "Gate" in stage: role = "GATE"
        elif "Case" in stage: role = "DATA"
        
        processed.append({
            "raw": item,
            "dt": dt,
            "time": dt.strftime("%H:%M:%S") if dt else "",
            "role": role
        })

    duration = "0s"
    if start_dt and end_dt:
        diff = end_dt - start_dt
        m, s = divmod(diff.seconds, 60)
        duration = f"{m}m {s}s"

    return processed, duration, start_dt

def generate_css():
    return f"""
    :root {{
        --c-bg: {COLORS['bg']};
        --c-orange: {COLORS['orange']};
        --c-black: {COLORS['black']};
        --font-mono: 'JetBrains Mono', monospace;
        --font-sans: 'Inter', sans-serif;
    }}
    
    body {{
        margin: 0;
        background: var(--c-bg);
        background-image: linear-gradient(var(--c-black) 1px, transparent 1px),
                          linear-gradient(90deg, var(--c-black) 1px, transparent 1px);
        background-size: 40px 40px;
        background-position: -1px -1px;
        /* Grid opacity */
        background-blend-mode: overlay;
        color: var(--c-black);
        font-family: var(--font-sans);
        height: 100vh;
        display: flex;
        overflow: hidden;
    }}
    
    /* === CRT EFFECT OVERLAY === */
    .crt-overlay {{
        position: fixed;
        top: 0; left: 0; width: 100%; height: 100%;
        background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.1) 50%);
        background-size: 100% 4px; /* Scanliness */
        pointer-events: none;
        z-index: 999;
        opacity: 0.15;
    }}
    
    .screen-glow {{
        position: fixed;
        top:0; left:0; width:100%; height:100%;
        box-shadow: inset 0 0 100px rgba(0,0,0,0.1);
        z-index: 998;
        pointer-events: none;
    }}

    /* === SIDEBAR === */
    .sidebar {{
        width: 350px;
        background: #fff;
        border-right: 3px solid var(--c-black);
        display: flex;
        flex-direction: column;
        z-index: 50;
    }}
    
    .sidebar-header {{
        background: var(--c-orange);
        padding: 15px;
        border-bottom: 3px solid var(--c-black);
        color: #fff;
    }}
    
    .brand {{ 
        font-family: var(--font-mono); 
        font-weight: 800; 
        font-size: 1.5rem; 
        text-transform: uppercase;
        display: block; 
        letter-spacing: -1px;
    }}
    
    .meta-info {{
        font-family: var(--font-mono);
        font-size: 0.75rem;
        margin-top: 8px;
        line-height: 1.4;
        opacity: 0.9;
    }}

    .nav-scroll {{
        flex: 1;
        overflow-y: auto;
        padding: 0;
    }}
    
    /* Navigation Items - DENSE LIST */
    .nav-group-label {{
        background: var(--c-black);
        color: #fff;
        font-family: var(--font-mono);
        font-size: 0.7rem;
        padding: 4px 12px;
        font-weight: 700;
        letter-spacing: 1px;
        margin-top: 0; 
    }}
    
    .nav-item {{
        display: flex;
        align-items: center;
        padding: 8px 12px;
        text-decoration: none;
        color: var(--c-black);
        font-family: var(--font-mono);
        font-size: 0.75rem;
        border-bottom: 1px solid #eee;
        transition: 0.1s;
    }}
    .nav-item:hover {{ background: #fff8e1; color: var(--c-orange); }}
    .nav-item.active {{ background: var(--c-black); color: var(--c-orange); }}
    
    .nav-role-icon {{ width: 14px; text-align: center; margin-right: 6px; font-weight: bold; font-size: 0.9rem; }}
    .nav-text {{ flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .nav-time {{ opacity: 0.5; font-size: 0.7rem; margin-left: 5px; }}
    
    /* === MAIN CONTENT === */
    .main {{
        flex: 1;
        overflow-y: auto;
        padding: 30px;
        position: relative;
    }}
    
    .log-card {{
        background: #fff;
        border: 2px solid var(--c-black);
        box-shadow: 6px 6px 0px var(--c-black);
        margin-bottom: 24px;
        position: relative;
    }}
    
    .card-header {{
        background: #eee;
        border-bottom: 2px solid var(--c-black);
        padding: 10px 15px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-family: var(--font-mono);
    }}
    
    .header-badge {{
        background: var(--c-black);
        color: #fff;
        padding: 2px 6px;
        font-size: 0.7rem;
        font-weight: 700;
        margin-right: 8px;
    }}
    .header-title {{ font-weight: 700; font-size: 0.9rem; }}
    .header-meta {{ font-size: 0.7rem; color: #555; }}
    
    .card-body {{ padding: 20px; font-size: 0.9rem; }}
    
    /* Data Tables */
    .json-table {{
        width: 100%;
        border-collapse: collapse;
        font-family: var(--font-mono);
        font-size: 0.8rem;
        border: 2px solid var(--c-black);
        margin-top: 10px;
    }}
    .json-table th, .json-table td {{ border: 1px solid var(--c-black); padding: 8px; vertical-align: top; }}
    .json-table th {{ background: var(--c-black); color: #fff; width: 150px; text-align: right; }}
    .json-table td {{ background: #fff; }}
    
    .pre-wrap {{
        white-space: pre-wrap;
        font-family: var(--font-mono);
        background: #f1f1f1;
        padding: 10px;
        border: 1px solid #ccc;
        font-size: 0.85rem;
    }}
    
    ::-webkit-scrollbar {{ width: 10px; background: #fff; border-left: 2px solid #000; }}
    ::-webkit-scrollbar-thumb {{ background: var(--c-orange); border: 2px solid #000; }}
    """

def generate_html(filepath, output_path):
    items, duration_str, start_dt = load_data(filepath)
    css = generate_css()
    
    # --- BUILD SIDEBAR ---
    # User constraint: "Show everything like the screenshot"
    # We will list items chronologically but maybe inject date/phase headers?
    # Simple dense list is best for "missing fields" complaint.
    
    sidebar_html = ""
    current_phase = ""
    
    for i, item in enumerate(items):
        stage = item['raw'].get('stage', 'Unknown')
        
        # Heuristic Phase Grouping for Headers (optional, enables scanning)
        phase = "INIT"
        if "D1" in stage: phase = "PHASE 1 (OUTPATIENT)"
        elif "D2" in stage: phase = "PHASE 2 (ADMISSION)"
        elif "D3" in stage: phase = "PHASE 3 (SURGERY)"
        elif "D4" in stage: phase = "PHASE 4 (REHAB)"
        elif "Gate" in stage or "Decision" in stage: phase = "DECISION NODE"
        
        if phase != current_phase and phase != "DECISION NODE": # Decision nodes interleave, don't spam headers
            sidebar_html += f'<div class="nav-group-label">{phase}</div>'
            current_phase = phase
            
        # Icon
        icon = "▪"
        if item['role'] == "JUDGE": icon = "⚖"
        elif item['role'] == "DOCTOR": icon = "✚"
        elif item['role'] == "AI_PROMPT": icon = "➤"
        
        # Color coding for errors
        raw_out = str(item['raw'].get('output','')).lower()
        style = ""
        if "error" in raw_out: style = "color: red;"
        
        sidebar_html += f"""
        <a href="#log-{i}" class="nav-item" style="{style}">
            <span class="nav-role-icon">{icon}</span>
            <span class="nav-text">{stage}</span>
            <span class="nav-time">{item['time']}</span>
        </a>
        """

    # --- BUILD MAIN CARDS ---
    main_html = ""
    for i, item in enumerate(items):
        raw = item['raw']
        stage = raw.get('stage')
        model = raw.get('model', 'Unknown Model')
        
        # Content Rendering
        content_html = ""
        inputs = raw.get('inputs')
        output = raw.get('output')
        
        if inputs:
            content_html += '<div style="font-weight:bold; font-family:var(--font-mono); margin-bottom:5px;">// INPUT</div>'
            if isinstance(inputs, list):
                for inp in inputs: content_html += f'<div class="pre-wrap">{inp}</div><br>'
            elif isinstance(inputs, dict):
                rows = "".join([f"<tr><th>{k}</th><td>{json.dumps(dict(v) if isinstance(v, (dict, list)) else v, ensure_ascii=False)}</td></tr>" for k,v in inputs.items()])
                content_html += f'<table class="json-table">{rows}</table>'
            else:
                 content_html += f'<div class="pre-wrap">{inputs}</div>'
                 
        if inputs and output: content_html += '<hr style="border:1px dashed #ccc; margin:15px 0;">'
        
        if output:
            content_html += '<div style="font-weight:bold; font-family:var(--font-mono); margin-bottom:5px; color:#ff5f1f">// OUTPUT</div>'
            if isinstance(output, dict):
                rows = ""
                for k, v in output.items():
                    # Handle complex values
                    val_str = json.dumps(v, ensure_ascii=False, indent=2) if isinstance(v, (dict, list)) else str(v)
                    rows += f"<tr><th>{k}</th><td><pre style='margin:0; white-space:pre-wrap'>{val_str}</pre></td></tr>"
                content_html += f'<table class="json-table">{rows}</table>'
            else:
                content_html += f'<div class="pre-wrap">{output}</div>'

        main_html += f"""
        <div id="log-{i}" class="log-card">
            <div class="card-header">
                <div>
                    <span class="header-badge">#{i}</span>
                    <span class="header-title">{stage}</span>
                </div>
                <div class="header-meta">
                    <span>{model}</span> | <span>{item['time']}</span>
                </div>
            </div>
            <div class="card-body">
                {content_html}
            </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>ECHO TRACE</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>{css}</style>
</head>
<body>
    <div class="crt-overlay"></div>
    <div class="screen-glow"></div>
    
    <div class="sidebar">
        <div class="sidebar-header">
            <span class="brand">Project Echo</span>
            <div class="meta-info">
                CASE: {items[0]['raw'].get('case_id')}<br>
                DATE: {start_dt.strftime('%Y-%m-%d') if start_dt else 'N/A'}<br>
                DURATION: <span style="background:#000; color:#fff; padding:0 4px">{duration_str}</span>
            </div>
        </div>
        <div class="nav-scroll">
            {sidebar_html}
        </div>
    </div>
    
    <div class="main">
        {main_html}
    </div>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Generated Echo UI with CRT Filter: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/preview_ui.py <jsonl_file>")
        sys.exit(1)
        
    jsonl_path = sys.argv[1]
    output_path = os.path.join("output_ui_test", "preview_foshan_3_echo_crt.html")
    if not os.path.exists("output_ui_test"):
        os.makedirs("output_ui_test")

    generate_html(jsonl_path, output_path)
