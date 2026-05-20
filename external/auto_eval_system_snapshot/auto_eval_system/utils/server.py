# -*- coding: utf-8 -*-
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import logging

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list = []
        self.history: list = [] # Store recent logs

    async def connect(self):
        queue = asyncio.Queue()
        # Send history first
        for log in self.history:
            await queue.put(log)
        self.active_connections.append(queue)
        return queue

    def disconnect(self, queue):
        if queue in self.active_connections:
            self.active_connections.remove(queue)

    async def broadcast(self, message: dict):
        self.history.append(message)
        # Keep history manageable
        if len(self.history) > 2000: # Increased buffer
            self.history.pop(0)
            
        for queue in self.active_connections:
            await queue.put(message)

manager = ConnectionManager()

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AutoEval Live Monitor</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; margin: 0; display: flex; height: 100vh; overflow: hidden; }
        
        /* Sidebar */
        .sidebar { width: 320px; background: #fff; border-right: 1px solid #ddd; display: flex; flex-direction: column; box-shadow: 2px 0 5px rgba(0,0,0,0.05); z-index: 10; }
        .sidebar-header { padding: 10px 15px; background: #1a73e8; color: white; display: flex; flex-direction: column; gap: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .title-row { display: flex; justify-content: space-between; align-items: center; }
        .sidebar-title { font-weight: bold; font-size: 1.1rem; }
        
        /* Sidebar Filters */
        .sidebar-filters { display: flex; flex-direction: column; gap: 5px; }
        .filter-select { padding: 4px; border: 1px solid rgba(255,255,255,0.3); background: rgba(255,255,255,0.1); color: white; border-radius: 4px; font-size: 0.85em; }
        .filter-select option { background: #fff; color: #333; }
        
        .sidebar-list { overflow-y: auto; flex: 1; list-style: none; padding: 0; margin: 0; }
        .sidebar-item { padding: 12px 15px; border-bottom: 1px solid #eee; cursor: pointer; transition: background 0.2s; position: relative; }
        .sidebar-item:hover { background: #f5f5f5; }
        .sidebar-item.active { background: #e8f0fe; border-left: 4px solid #1a73e8; }
        .sidebar-item.hidden { display: none; }
        
        .sidebar-item .case-id { font-weight: 500; color: #333; font-size: 0.95em; }
        .sidebar-item .model-tag { font-size: 0.75em; color: #1a73e8; background: rgba(26, 115, 232, 0.1); padding: 1px 4px; border-radius: 3px; margin-left: 5px; }
        .sidebar-item .meta { font-size: 0.75em; color: #666; margin-top: 4px; display: flex; justify-content: space-between; }
        
        .stage-list { list-style: none; padding: 0; margin: 5px 0 0 0; display: none; border-left: 1px solid #ddd; margin-left: 5px; }
        .sidebar-item.active .stage-list { display: block; }
        .stage-item { padding: 3px 8px; font-size: 0.75em; color: #666; cursor: pointer; position: relative; }
        .stage-item:hover { color: #1a73e8; font-weight: 500; }
        .stage-item::before { content: "•"; position: absolute; left: -4px; color: #ccc; }
        
        /* Main Area */
        .main-content { flex: 1; padding: 0; overflow-y: hidden; display: flex; flex-direction: column; position: relative; }
        .log-container { flex: 1; padding: 20px; overflow-y: auto; scroll-behavior: smooth; }
        
        .empty-state { display: flex; align-items: center; justify-content: center; height: 100%; color: #aaa; font-size: 1.2em; flex-direction: column; gap: 10px; }
        
        /* Logs */
        .log-entry { margin-bottom: 15px; border-left: 5px solid #ccc; padding: 15px; background: #fff; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .type-info { border-color: #2196f3; }
        .type-prompt { border-color: #9c27b0; background: #fafafa; }
        .type-json { border-color: #4caf50; }
        .type-warning { border-color: #ff9800; background: #fff8e1; }
        .type-error { border-color: #f44336; background: #ffebee; }
        .type-success { border-color: #00c853; }
        
        .log-header { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 0.85em; color: #888; border-bottom: 1px solid #eee; padding-bottom: 5px; }
        .stage-badge { background: #eee; padding: 2px 6px; border-radius: 4px; font-weight: bold; color: #555; }
        .content { font-family: Consolas, monospace; font-size: 0.9em; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; }
        
        table.json-table { border-collapse: collapse; width: 100%; font-size: 0.9em; margin-top: 5px; background: #fff; border: 1px solid #e0e0e0; }
        table.json-table th, table.json-table td { border: 1px solid #e0e0e0; padding: 8px; vertical-align: top; text-align: left; }
        table.json-table th { background: #f8f9fa; color: #444; font-weight: 600; width: 30%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        table.json-table td { color: #333; font-family: Consolas, monospace; }
        
        /* Controls */
        .floating-controls { position: fixed; right: 30px; bottom: 30px; display: flex; flex-direction: column; gap: 10px; z-index: 100; }
        .fab { width: 40px; height: 40px; border-radius: 50%; background: #1a73e8; color: white; border: none; box-shadow: 0 2px 5px rgba(0,0,0,0.2); cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 1.2rem; transition: transform 0.2s; }
        .fab:hover { transform: scale(1.1); background: #1557b0; }
        .fab.active { background: #f44336; }
        
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="sidebar-header">
            <div class="title-row">
                <span class="sidebar-title">Clinical Eval</span>
                <div id="status-indicator" style="width:10px; height:10px; background:#ccc; border-radius:50%;" title="Disconnected"></div>
            </div>
            <div class="sidebar-filters">
                <select id="center-filter" class="filter-select" onchange="applySidebarFilters()">
                    <option value="all">📍 All Centers</option>
                </select>
                <select id="model-filter" class="filter-select" onchange="applySidebarFilters()">
                    <option value="all">🤖 All Models</option>
                </select>
            </div>
        </div>
        <ul id="case-list" class="sidebar-list"></ul>
    </div>

    <div class="main-content">
        <div id="log-container" class="log-container">
            <div class="empty-state">
                <span>👈 Select a case from the sidebar</span>
                <span style="font-size:0.7em;">Use filters above if list is too long</span>
            </div>
        </div>
    </div>
    
    <div class="floating-controls">
        <button class="fab" onclick="scrollToTop()" title="Top">↑</button>
        <button class="fab" id="btn-lock" onclick="toggleScrollLock()" title="Lock/Unlock">🔓</button>
        <button class="fab" onclick="scrollToBottom()" title="Bottom">↓</button>
    </div>

    <script>
        const logsDiv = document.getElementById('log-container');
        const caseList = document.getElementById('case-list');
        const centerSel = document.getElementById('center-filter');
        const modelSel = document.getElementById('model-filter');
        const statusInd = document.getElementById('status-indicator');
        const btnLock = document.getElementById('btn-lock');

        let allLogs = [];
        let cases = new Map(); // Key -> {id, model, center, start, last, uniqueKey}
        let currentCaseKey = null;
        let eventSource = null;
        let autoScroll = true;
        
        let centers = new Set();
        let models = new Set();

        function connect() {
            if(eventSource) eventSource.close();
            eventSource = new EventSource("/stream");
            
            eventSource.onopen = () => { statusInd.style.background = "#4caf50"; statusInd.title = "Connected"; };
            eventSource.onmessage = (e) => processLog(JSON.parse(e.data));
            eventSource.onerror = () => { statusInd.style.background = "#f44336"; statusInd.title = "Disconnected"; setTimeout(connect, 3000); };
        }

        function processLog(data) {
            allLogs.push(data);
            
            // Extract Metrics
            const c = data.center || "Unknown";
            const m = data.session_model || data.model || data.model_name || "Unknown";
            const cid = data.case_id;
            const uniqueKey = cid + "_" + m;
            
            // 1. Update Filters
            if (!centers.has(c)) { centers.add(c); addOption(centerSel, c); }
            if (!models.has(m)) { models.add(m); addOption(modelSel, m); }
            
            // 2. Register Case
            if (cid && cid !== "undefined") {
                const logTime = new Date(data.timestamp); 
                if (!cases.has(uniqueKey)) {
                    cases.set(uniqueKey, { 
                        uniqueKey, id: cid, model: m, center: c, 
                        start: logTime, last: logTime, stages: new Set() 
                    });
                    renderSidebarItem(uniqueKey, cid, m, c);
                } else {
                    const info = cases.get(uniqueKey);
                    info.last = logTime;
                    updateSidebarTime(uniqueKey);
                }
                
                // Track Stage
                const groupName = getGroupName(data.stage);
                const caseInfo = cases.get(uniqueKey);
                if (!caseInfo.stages.has(groupName)) {
                    caseInfo.stages.add(groupName);
                    appendStageToSidebar(uniqueKey, groupName, allLogs.length - 1);
                }
            }

            // 3. Render Log if Active
            if (currentCaseKey === uniqueKey) {
                renderLogEntry(data, allLogs.length - 1);
                if (autoScroll) scrollToBottom();
            }
        }
        
        function addOption(select, val) {
            const o = document.createElement('option');
            o.value = val; o.textContent = val;
            select.appendChild(o);
        }

        function renderSidebarItem(key, cid, model, center) {
            const li = document.createElement('li');
            li.className = 'sidebar-item';
            li.dataset.center = center;
            li.dataset.model = model;
            li.id = `sidebar-${key}`;
            li.onclick = () => switchCase(key);
            li.innerHTML = `
                <div class="case-id">
                    ${cid} <span class="model-tag">${model}</span>
                </div>
                <div class="meta">
                    <span id="time-${key}">Just now</span>
                    <span>${center}</span>
                </div>
                <ul id="stages-${key}" class="stage-list"></ul>
            `;
            
            // Apply current filters visibility
            if (!isSidebarVisible(center, model)) li.classList.add('hidden');
            
            caseList.insertBefore(li, caseList.firstChild);
        }
        
        function updateSidebarTime(key) {
            const info = cases.get(key);
            const span = document.getElementById(`time-${key}`);
            if (span) {
                const diff = Math.round((info.last - info.start) / 1000);
                span.textContent = diff < 60 ? `${diff}s` : `${Math.floor(diff/60)}m ${diff%60}s`;
            }
        }
        
        function applySidebarFilters() {
            const cFilter = centerSel.value;
            const mFilter = modelSel.value;
            
            document.querySelectorAll('.sidebar-item').forEach(li => {
                const c = li.dataset.center;
                const m = li.dataset.model;
                if ((cFilter === 'all' || c === cFilter) && (mFilter === 'all' || m === mFilter)) {
                    li.classList.remove('hidden');
                } else {
                    li.classList.add('hidden');
                }
            });
        }
        
        function isSidebarVisible(c, m) {
            const cFilter = centerSel.value;
            const mFilter = modelSel.value;
            return (cFilter === 'all' || c === cFilter) && (mFilter === 'all' || m === mFilter);
        }

        function switchCase(key) {
            currentCaseKey = key;
            
            // Highlight Sidebar
            document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));
            const active = document.getElementById(`sidebar-${key}`);
            if (active) active.classList.add('active');
            
            // Clear and Re-render Main Logs
            logsDiv.innerHTML = '';
            lastGroup = null; // Reset group tracker
            
            // Filter all logs for this case
            allLogs.forEach((log, index) => {
                const logKey = (log.case_id || "") + "_" + (log.session_model || log.model || log.model_name || "");
                if (logKey === key) {
                    renderLogEntry(log, index);
                }
            });
            
            scrollToBottom();
        }
        
        let lastGroup = null;
        function getGroupName(stage) {
            if (stage.startsWith("Patient") || stage.startsWith("D1_Init")) return "00. Initialization";
            if (stage.startsWith("D1_") || stage.includes("Gate 1") || stage.includes("Decision_1")) return "01. Outpatient Stage";
            if (stage.startsWith("D2_") || stage.includes("Decision_2") || stage.includes("Gate_2") || stage.includes("Gate 2")) return "02. Admission Stage";
            if (stage.startsWith("D3_") || stage.includes("Decision_3") || stage.includes("Gate 3") || stage.includes("Outcome_Surgery")) return "03. Surgery Stage";
            if (stage.startsWith("D4_") || stage.includes("Decision_4") || stage.includes("Judge_Discharge") || stage.includes("Outcome_Discharge")) return "04. Discharge/Rehab";
            return "05. Other";
        }

        function appendStageToSidebar(key, stageName, logIndex) {
            const ul = document.getElementById(`stages-${key}`);
            if (!ul) return;
            const li = document.createElement('li');
            li.className = 'stage-item';
            li.textContent = stageName;
            li.onclick = (e) => {
                e.stopPropagation();
                if (currentCaseKey !== key) switchCase(key);
                // Wait for render
                setTimeout(() => {
                    const logDiv = document.getElementById(`log-${logIndex}`);
                    if (logDiv) logDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }, 50);
            };
            ul.appendChild(li);
        }

        function renderLogEntry(data, index) {
            // Group Header Logic
            const groupName = getGroupName(data.stage);
            if (groupName !== lastGroup) {
                const headerDiv = document.createElement('div');
                headerDiv.style.cssText = "background:#eee; padding:8px 15px; font-weight:bold; color:#555; margin:20px 0 10px 0; border-radius:4px; font-size:0.9em; text-transform:uppercase; box-shadow:0 1px 2px rgba(0,0,0,0.05); position:sticky; top:0; z-index:5;";
                headerDiv.textContent = groupName;
                logsDiv.appendChild(headerDiv);
                lastGroup = groupName;
            }

            const div = document.createElement('div');
            div.className = `log-entry type-${data.type}`;
            div.id = `log-${index}`;
            
            // Render Content Helpers
            const renderSection = (label, content) => {
                if (!content) return '';
                let html = escapeHtml(content);
                if (typeof content === 'string' && content.trim().startsWith('{')) {
                    try { content = JSON.parse(content); } catch(e) {}
                }
                if (typeof content === 'object') html = jsonToTable(content);
                return `<div style="margin-top:10px;"><span style="font-size:0.7em; font-weight:bold; background:#eee; padding:2px 4px; border-radius:3px; color:#555;">${label}</span><div class="content" style="margin-top:5px;">${html}</div></div>`;
            };

            let bodyHtml = "";
            if (data.inputs) bodyHtml += renderSection("INPUTS", data.inputs);
            if (data.output) bodyHtml += renderSection("OUTPUT", data.output);
            if (!data.inputs && !data.output && data.content) bodyHtml += renderSection("CONTENT", data.content);
            if (data.error) bodyHtml += `<div style="margin-top:10px; color:red; font-weight:bold;">ERROR: ${data.error}</div>`;

            div.innerHTML = `
                <div class="log-header">
                    <span class="stage-badge">${data.stage}</span>
                    <span>${data.timestamp}</span>
                </div>
                ${bodyHtml}
            `;
            logsDiv.appendChild(div);
        }

        function jsonToTable(obj) {
            if (obj === null) return "null";
            if (Array.isArray(obj)) return obj.length === 0 ? "[]" : `<div style="padding-left:10px; border-left:2px solid #eee;">[Array(${obj.length})]<br>${obj.map(item => jsonToTable(item)).join('<hr style="border:0;border-top:1px dashed #eee;margin:5px 0;">')}</div>`;
            if (typeof obj === 'object') {
                 if (Object.keys(obj).length === 0) return "{}";
                 let html = '<table class="json-table">';
                 for (const [k, v] of Object.entries(obj)) {
                     if (['AI_Raw_JSON', '_metadata'].includes(k)) continue;
                     html += `<tr><th>${k}</th><td>${jsonToTable(v)}</td></tr>`;
                 }
                 html += '</table>';
                 return html;
            }
            return String(obj);
        }

        function escapeHtml(text) { return typeof text !== 'string' ? text : text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
        function scrollToTop() { logsDiv.scrollTop = 0; }
        function scrollToBottom() { logsDiv.scrollTop = logsDiv.scrollHeight; }
        function toggleScrollLock() { autoScroll = !autoScroll; btnLock.textContent = autoScroll ? "🔓" : "🔒"; btnLock.classList.toggle('active', !autoScroll); }

        connect();
    </script>
</body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(content=TEMPLATE)

@app.get("/stream")
async def stream(request: Request):
    async def event_generator():
        queue = await manager.connect()
        try:
            while True:
                if await request.is_disconnected():
                    break
                data = await queue.get()
                yield f"data: {json.dumps(data)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            manager.disconnect(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/push_log")
async def push_log(log: dict):
    await manager.broadcast(log)
    return {"status": "ok"}

def start_server():
    import uvicorn
    import sys
    
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
            
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    start_server()
