# Task: llm.rationale_quality（推理证据链质量）

## Inputs（仅来自Excel字段）

- `case_id`: `{{case_id}}`
- `stage`: `{{stage}}`（D1 loop / D1 decision / D2 loop / D2 decision / D3 / D4）
- `gt_facts`: `{{gt_facts}}`（阶段相关GT上下文）
- `ai_output_text`: `{{ai_output_text}}`（AI输出：诊断/方案/检查）
- `ai_rationale_text`: `{{ai_rationale_text}}`（AI理由/思维）

## Instruction (System)

你需要评估 AI 推理是否形成清晰且可信的“观察-推断-结论”证据链。请结合 `gt_facts` 与 `ai_output_text`，判断 `ai_rationale_text` 是否与输出一致且有足够证据支撑。

重点检查：
1) 是否从病例事实/检查结果出发（Observation）
2) 推断是否合乎医学逻辑（Inference）
3) 结论是否与推断一致（Conclusion）
4) 是否存在：叙事干扰（编故事/无根据扩展）、过度整合、跳步推理

**评分要求：必须输出 0-1 的连续分值（如 0.2/0.5/0.8），不要只给 0 或 1。**
**issue_tags 只是问题标签，不代表必须打 0 分。**
参考区间（用于把分数拉开）：  
- 0.0-0.2：严重缺乏证据或推理多处错误  
- 0.3-0.5：部分有据但链条不完整/跳步较多  
- 0.6-0.8：大部分合理，存在少量瑕疵  
- 0.9-1.0：证据链清晰、几乎无明显问题  
仅在完全不可信或几乎完美时使用 0 或 1。

输出要求：仅输出评分 + 必要的错误标签，不输出长文本解释。
不要输出 case_id/stage（由程序附加）。
必须输出严格 JSON。

## Output JSON Schema

```json
{
  "score": 0.0,
  "issue_tags": ["missing_link", "over_integration", "narrative_bias", "logic_jump", "other"]
}
```
