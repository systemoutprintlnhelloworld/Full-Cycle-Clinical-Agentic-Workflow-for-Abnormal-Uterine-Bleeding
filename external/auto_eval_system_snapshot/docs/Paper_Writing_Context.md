# 论文写作上下文材料 (Paper Writing Context)

## 1. 系统概览 (System Overview)
本项目旨在开发一种**基于多智能体协作的自动化临床诊疗评测系统** (Automated Clinical Evaluation System based on Multi-Agent Collaboration)，用于评估大语言模型 (LLM) 在复杂临床场景（特别是妇科肿瘤）中的诊疗能力。

### 核心贡献点
1.  **全流程模拟**: 覆盖门诊问诊、入院决策、手术方案、术后康复四个完整临床阶段，而非单点问答。
2.  **动态信息获取 (Information Gathering)**: 模拟医生通过多轮对话主动获取病史和检查结果的过程，而非一次性根据完整病历做题。
3.  **双重评估机制 (Dual-Judge System)**: 结合规则匹配与 LLM 语义判断，引入“二次判官 (Secondary Judge)”机制解决模糊匹配问题。
4.  **真实世界数据**: 基于真实脱敏病历（佛山、武汉、新疆三中心），涵盖不同地区医疗习惯差异。

---

## 2. 评测流程方法论 (Methodology)

系统采用 **Doctor Agent (被测模型)** 与 **Judge Agent (评估模型，如 Gemini-2.5-Pro / GPT-4)** 对抗/协作的架构。流程分为四个阶段 (Stages)：

### Stage 1: 门诊问诊 (Outpatient Decision)
-   **输入**: 患者模拟 Agent (Patient Description Agent) 将病历转换为口语化主诉。
-   **交互**: Doctor Agent 需通过多轮对话 (Decision 1 Loop, max 4 rounds) 主动询问病史和体格检查。
-   **关键行为**:
    -   系统根据 Doctor 的请求，逐步披露“门诊检查结果”。
    -   Doctor 需判断信息是否充足，决定“补充检查”或“下诊断”。
-   **评估点 (Gate 1)**: 初步诊断准确性、建议检查的合理性与经济性。

### Stage 2: 入院决策 (Admission Decision)
-   **环境**: 假设患者已入院。
-   **交互**: Doctor Agent 获得入院后的详细检查结果 (Decision 2 Loop, max 4 rounds)。
-   **关键行为**: 修正门诊的初步诊断，提出具体的治疗方案（如手术术式）。
-   **评估点 (Gate 2)**: 修正诊断准确性、治疗方案与手术指征的匹配度。
    -   *创新点*: 引入 **Secondary Judge** 处理“包含关系”或“更精确诊断”的模糊判定（如 Doctor 诊断更细致是否算对）。

### Stage 3: 手术决策 (Surgery & Pathology)
-   **输入**: 系统的手术所见 (Surgery Findings) 和术后病理报告 (Pathology)。
-   **任务**: Doctor Agent 需结合病理结果给出 **最终诊断 (Final Diagnosis)** 和 **术后治疗方案 (Post-op Plan)**（如放化疗）。
-   **评估点 (Gate 3)**: 最终诊断（分期分级）的准确性、术后辅助治疗方案是否符合指南 (NCCN/CSCO)。
    -   *More Info 机制*: 如果 Judge 无法判定，会请求更多上下文信息进行二次裁决。

### Stage 4: 康复与随访 (Rehab & Follow-up)
-   **任务**: 制定个性化的出院指导和长期随访计划。
-   **评估点**: 方案的可行性、是否过度医疗（如良性病变不需要密集随访）。

---

## 3. 关键评估指标 (Metrics)

| 维度 | 指标名称 (Excel 列名) | 定义 |
| :--- | :--- | :--- |
| **诊断准确性** | `Gate_Diagnosis_Match` | 初步/修正/最终诊断与 Ground Truth (GT) 的语义匹配度（完全一致/包含/方向一致）。 |
| **检查合理性** | `Score_Check_Match` | 建议检查项目与 GT 实际检查的重合度。 |
| **治疗规范性** | `Gate_Surgery_Score` | 治疗方案是否符合 GT 方案及医疗指南。 |
| **信息获取效率** | `Loop_Count` | 在门诊/入院阶段完成决策所需的对话轮次。 |
| **安全性** | `Critical_Miss_Rate` | 是否遗漏关键检查或禁忌症（如危险操作导致提前终止）。 |

---

## 4. 数据集与实验设置 (Experiments)

### 数据集 (Privacy-Preserved Real-world Data)
-   **来源**: 三家三甲医院（佛山、武汉、新疆）。
-   **规模**: 300+ 真实完整病历（覆盖常见妇科良恶性肿瘤）。
-   **包含**: 主诉、现病史、既往史、家族史、体格检查、影像报告、病理报告、手术记录。

### 实验基准 (Baselines)
-   **被测模型**:
    -   Gemini 1.5 Pro / 2.5 Pro
    -   GPT-4o (GPT-5 Preview)
    -   Claude 3.5 Sonnet / Opus
    -   DeepSeek V3
    -   Grok-4
-   **Judge 模型**: 固定使用 Gemini 2.5 Pro 或 GPT-4，保证评估标准一致性。

---

## 5. 提示词工程策略 (Prompt Engineering)

基于 `prompts_v2.py` 的设计亮点：

1.  **结构化思维链 (Structured CoT)**: 强制模型输出 JSON，并包含独立的 `*_思维` 字段（如 `诊断思维`、`治疗方案思维`），迫使模型先解释逻辑再下结论。
2.  **动态反馈注入**: 在 Loop 循环中，将上一轮的 Judge 反馈（警告、已获得信息）注入到下一轮 Prompt 中，模拟真实的“医生-检验科/患者”闭环。
3.  **角色扮演增强**:
    -   *Patient Agent*: 使用“数值保护指令”和“口语化转换”技术，确保患者描述真实自然且不丢失关键体征数据。
    -   *Doctor Agent*: 设定为“中国三甲医院专家”，强调遵循中国医疗系统规范。
4.  **防御性指令 (Defensive Instructions)**: 明确禁止编造不存在的检查结果，强制在缺失信息时根据风险评估做决策。

---

## 6. 技术实现细节 (Implementation Details)

-   **超长上下文处理**: 针对长病历导致的 JSON 截断问题，实现了智能清洗与分列存储策略。
-   **自动纠错**: 在 Agent 输出非 JSON 格式时，包含自动重试机制。
-   **数据清洗**: `flatten_parsed_excels.py` 脚本实现了对嵌套 JSON 结构的自动展开，便于后续统计分析。
-   **完整性验证**: `validate_and_move_excels.py` 确保评估结果无损坏。

---

## 7. 潜在的讨论点 (Discussion Points)

-   **主动问诊 vs 被动做题**: 实验表明，能够在 Loop 中主动发现缺失信息并请求检查的模型，最终诊断准确率显著更高。
-   **幻觉抑制**: 通过提供明确的“检查列表”反馈机制，显著降低了模型编造检查结果的幻觉率。
-   **复杂决策推理**: 在 Decision 3 (手术/病理) 阶段，模型需要结合多模态信息（文字描述的影像/病理），展示了高阶临床推理能力。
