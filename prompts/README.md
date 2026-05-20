# Prompts（LLM as Judge / LLM中间量）

本目录存放所有 LLM 评测提示词模板，用于：

1) 产出算法指标所需的“LLM中间量”（语义归一/逐项标注/信息增益判定等）；  
2) 产出新增/补齐的 LLM as Judge 指标评分。  

## 通用约束

- **输入来源**：只允许使用现有 Excel 中的已抽取字段值（GT standardized + doc Parsed + judge Judge_Parsed）。  
- **输出格式**：必须输出严格 JSON（不包含 Markdown、注释、额外文本）。  
- **输出最小化**：仅输出评分/计数/必要标签，不输出长文本解释。  
- **不确定性**：若信息不足，允许输出低置信度或计数为 0，并用 `issue_tags` 标记。  

## 变量占位（由实现侧填充）

模板中使用 `{{...}}` 表示占位符，例如：

- `{{case_id}}`, `{{center}}`, `{{doc_model}}`
- `{{gt_facts}}`：拼接后的GT病历事实（来自 standardized_*.xlsx）\n
- `{{ai_output}}`：doc agent 已抽取字段拼接\n
- `{{judge_signals}}`：已有 judge 结果（可选，仅用于弱监督/一致性校验）\n

> 具体每个任务需要哪些字段，在对应 prompt 文件顶部会写明。

