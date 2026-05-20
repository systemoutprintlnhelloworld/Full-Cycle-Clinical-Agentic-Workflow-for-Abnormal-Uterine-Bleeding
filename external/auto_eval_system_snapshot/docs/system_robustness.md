# 系统稳健性与可观测性设计 v1.0

> 本文档详细描述为保证临床评测系统长期稳定运行、防止数据丢失及支持深度数据分析所采取的技术方案。

---

## 1. 核心目标
1. **零数据丢失**：即使程序崩溃、断电或 API 异常，已评测的数据必须安全。
2. **可恢复性**：程序重启后能自动从断点继续，无需人工干预重复跑。
3. **深度可观测**：记录 LLM 的原始概率分布（Logprobs），支持后续的幻觉检测与置信度分析。

---

## 2. 断点续传机制 (Resume Capability)

### 2.1 Checkpoint 设计
系统将实时维护一个 `checkpoint.json` 文件，记录当前评测的全局进度。

```json
{
  "session_id": "20231210_103000",
  "start_time": "2025-12-10T10:30:00",
  "completed_cases": [
    "foshan_1", "foshan_2", "wuhan_5"
  ],
  "failed_cases": [
    {"case_id": "foshan_3", "error": "API Timeout", "stage": "decision_1"}
  ],
  "current_status": "running"
}
```

### 2.2 启动逻辑
每次程序启动时：
1. 检查是否存在 `checkpoint.json`。
2. 如果存在，读取 `completed_cases` 列表。
3. 在 DataLoader 加载数据时，过滤掉已完成的 `case_id`。
4. 仅对未完成的病例发起评测。

---

## 3. 数据安全写入 (Safe Data Persistence)

### 3.1 Excel 增量写入
严禁使用 `pandas.DataFrame.to_excel()` 直接覆盖文件，因为这会导致无法挽回的数据丢失。
**技术方案**：
- 使用 `openpyxl` 库以 `append` 模式打开 Excel 文件。
- 每完成一个 case 的评测，立即将该行数据追加到对应的 Sheet 中。
- 只有在首次创建文件时写入表头。

```python
def append_to_excel(file_path, sheet_name, row_data):
    wb = load_workbook(file_path)
    if sheet_name not in wb.sheetnames:
        wb.create_sheet(sheet_name)
    ws = wb[sheet_name]
    ws.append(row_data)  # 增量追加
    wb.save(file_path)
```

### 3.2 自动备份
- **频率**：每次程序启动前，或每处理 N 个病例后。
- **策略**：将当前输出文件复制到 `backup/` 目录，并加上时间戳。
  - `output/evaluation_results.xlsx` -> `backup/evaluation_results_20251210_103500.xlsx`

---

## 4. 深度数据记录 (Logprobs & Raw JSON)

为了支持后续的“认知偏差指数”和“置信度校准”分析，必须保存 LLM 的原始响应数据。

### 4.1 存储结构
采用 **JSONL (JSON Lines)** 格式，每行一个完整的 JSON 对象，对应一轮对话。这种格式对追加写入非常友好，且损坏风险低。

**文件路径**：`logs/raw_traces/{model_name}/{case_id}.jsonl`

### 4.2 记录内容示例
```json
{
  "timestamp": "2025-12-10T10:35:05",
  "case_id": "foshan_5",
  "stage": "decision_1",
  "loop_index": 0,
  "model": "gemini-2.5-pro",
  "input_messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "response_content": "{\"需要补充门诊检查\": true, ...}",
  "logprobs": {
    "content": [
      {"token": "子", "logprob": -0.05, "bytes": [...]},
      {"token": "宫", "logprob": -0.01, "bytes": [...]}, 
      ...
    ]
  },
  "usage": {
    "prompt_tokens": 1050,
    "completion_tokens": 120
  }
}
```

### 4.3 Logprobs 获取
在调用 LLM API 时，显式开启 `logprobs` 参数（如果模型支持）：
```python
client.chat.completions.create(
    model="mapped-model-name",
    messages=...,
    logprobs=True,
    top_logprobs=5
)
```

---

## 5. 异常处理策略 (Error Recovery)

### 5.1 API 级容错
- **超时/网络错误**：
  - 指数退避重试 (Exponential Backoff)，最多重试 3 次。
  - 间隔：2s -> 4s -> 8s。
- **429 Rate Limit**：
  - 自动等待 `Retry-After` 建议的时间，或默认等待 20s。

### 5.2 渠道 Fallback
- 若主渠道（如 Gala API）连续失败，自动切换到备用渠道（如 Yunwu API）。

### 5.3 病例级容错
- 若某病例在所有重试后仍失败（如 Prompt 过长、特定数据格式错误）：
  1. 捕获异常，打印错误堆栈。
  2. 将该 `case_id` 加入 `failed_cases` 列表。
  3. **跳过该病例**，继续执行下一个病例。
  4. 绝不让单个病例的失败导致整个评测程序崩溃。

---

## 6. 总结
通过上述机制，系统将具备极强的“韧性”。无论遇到何种网络波动或数据异常，系统都能最大限度地保全已完成的工作，并提供详尽的现场日志供后续诊断。
