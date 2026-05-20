# 临床自动测评系统 (Clinical Auto-Evaluation System)

> 基于 LLM 的临床决策能力自动测评框架，模拟医生问诊、检查、诊断、治疗全流程，并引入 Expert LLM 进行质控与评分。

## 1. 项目简介

本系统旨在评估大语言模型（Doc Agent）在特定临床专科（如妇科）中的决策能力。系统通过模拟真实的诊疗流程（门诊 -> 入院 -> 手术 -> 康复），引入“检查循环”、“Gatekeeper 质控”和“3次警告”机制，对模型的临床思维进行全方位考核。

**核心特性**：
- **多阶段仿真**：覆盖门诊、入院、手术、康复全程。
- **闭环反馈**：Judge Agent 对 AI 请求的检查进行审核与反馈（含 3 次警告机制）。
- **多模型支持**：支持 GPT-4, Claude, Gemini, DeepSeek 等多模型评测（基于 OpenAI 兼容 API）。
- **数据持久化**：增量写入 Excel（6 表结构），支持断点续传。
- **可观测性**：记录详细的交互轨迹与 Logprobs。

## 2. 环境配置

### 2.1 依赖安装
建议使用 Python 3.10+ 环境。

```bash
pip install -r requirements.txt
```

### 2.2 API 配置
复制 `.env.example` 为 `.env`，并填入 API Key。

```bash
cp .env.example .env
```

配置项说明：
- `YUNWU_API_KEY`: 云雾 API Key（主要渠道）
- `GALA_API_KEY`: Gala API Key
- 其他渠道 Key...

### 2.3 渠道配置
在 `auto_eval_system/config/channels.yaml` 中配置模型与 API 的映射关系。

## 3. 运行指南

### 3.1 准备数据
将脱敏后的 Excel 病例数据放入 `data/raw/` 目录。
支持文件名包含“佛山”、“武汉”、“新疆”以自动识别数据格式。

### 3.2 启动评测

**单模型评测**：
```bash
python main.py --model gemini-2.5-pro
```

**支持的模型列表** (在 `main.py` 中定义)：
- `gemini-2.5-pro`
- `gpt-5-2025-08-07`
- `claude-opus-4-1-20250805`
- `deepseek-v3-1-think-250821`
- `grok-4`


### 3.3 查看结果
- **Excel 报告**: `output/evaluation_{model_name}.xlsx`
  - 包含 6 个 Sheet，详细记录各阶段得分与决策内容。
- **原始轨迹 (HTML/JSONL)**: 
  - `output/raw_traces/`: 原始 JSONL 数据。
  - `output/html_traces/`: 可视化 HTML 报告。支持 **"Minimalist Theme" (极简主题)**，点击右上角 "Theme" 按钮即可切换至类似 sspai 的清爽阅读模式。
- **系统日志**: `system.log`

### 3.4 辅助工具
- **重测清理工具**: `tools/clean_retest_cases.py`
  - **用途**: 当测评因网络或 API 错误中断后，自动识别需要重测的病例（Blocked/Error），并将其旧的轨迹文件移动到 `retest_backup` 目录，同时清理 Excel 中的对应行，以便干净地重新运行。
  - **用法**:
    ```bash
    # 预览将要清理的文件（Dry Run）
    python tools/clean_retest_cases.py
    
    # 执行清理
    python tools/clean_retest_cases.py --execute
    ```

## 4. 关键逻辑说明

- **3-Strike Rule**: 若 Doc Agent 在同一阶段连续 3 次收到警告（请求了不需要的检查或遗漏必须检查），第 4 次仍未纠正，系统将强制终止该病例的评测。
- **Gate 机制**: 每个关键节点（门诊后、入院后、术后）都有 Gatekeeper，若诊断严重偏离 GT，评测提前终止。
- **断点续传**: 系统会自动记录已完成的 Case ID 到 `output/checkpoint.json`。重启程序会自动跳过已完成的病例。

## 5. 项目结构

- `auto_eval_system/`: 核心代码库
  - `modules/`: 业务模块 (Workflow, Agents, Logger, DataLoader)
  - `config/`: 配置文件 (Prompts, Channels)
  - `utils/`: 工具库 (ChannelManager, Checkpoint)
- `docs/`: 详细文档
  - `workflow_详解.md`: 完整架构与逻辑说明
- `main.py`: 启动入口
