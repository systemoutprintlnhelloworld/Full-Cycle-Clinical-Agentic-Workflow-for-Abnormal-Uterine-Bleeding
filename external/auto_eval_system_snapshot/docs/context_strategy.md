# 双上下文方案对比 v2.0

> 本文档对比"简练型上下文"和"完整型上下文"两种方案，分析优缺点、token消耗，并提供可配置的实现方案。

---

## 方案概览

| 维度 | 简练型上下文 | 完整型上下文 |
|:---|:---|:---|
| **传递内容** | 仅核心决策信息（诊断、检查结果） | 所有交互历史（User/Assistant messages） |
| **Token消耗** | 低（约30-50% of 完整型） | 高（包含系统Prompt和所有轮次） |
| **临床真实性** | 中（提炼后的信息） | 高（完整对话记录，模拟真实临床交接） |
| **AI理解难度** | 低（结构化数据，清晰明确） | 高（需处理长上下文，提取关键信息） |
| **调试难度** | 低（容易定位问题） | 高（需追溯完整历史） |
| **推荐场景** | Token受限、快速评测 | 模拟真实临床、深度评估 |

---

## 方案详解

### 方案A: 简练型上下文

#### 设计思路
每个决策阶段仅向下一阶段传递**必要的决策结果**，而非完整对话。

#### 决策1 → 决策2 传递内容

```python
decision1_summary = {
    "患者基本信息": "女性，40岁，汉族",
    "患者主诉": "阴道不规则出血1月+",
    "门诊循环摘要": {
        "循环次数": 1,
        "AI请求的检查": ["血常规", "妇科超声"],
        "实际得到的检查结果": "血常规: Hb 110g/L\\n妇科超声: 子宫形态规整...",
        "缺失检查警告": "盆腔MRI在门诊阶段并未进行"
    },
    "门诊初步诊断": "1. 子宫内膜息肉\\n2. 异常子宫出血",
    "建议检查项目": "宫腔镜检查、子宫内膜活检、肿瘤标志物"
}
```

**User Prompt模板**:
```
## 【门诊阶段信息回顾】

### 患者基本信息
{basic_info}

### 门诊初步诊断（AI生成）
{preliminary_diagnosis}

### 门诊阶段获得的所有检查信息
{outpatient_checks_feedback}

**注**: 以上是门诊阶段你进行决策获得的所有临床信息。

---

## 【入院检查结果】
{admission_checks}
```

#### 优点
- ✅ Token消耗低（约2-4K tokens per stage）
- ✅ 结构清晰，AI容易理解
- ✅ 调试方便，容易定位问题
- ✅ 快速评测，成本低

#### 缺点
- ❌ 丢失了诊断推理过程
- ❌ 无法回溯AI的思考链
- ❌ 不完全模拟真实临床交接

---

### 方案B: 完整型上下文

#### 设计思路
将前面所有决策阶段的**完整messages数组**传递给下一阶段，模拟真实临床中医生查阅完整病历的场景。

#### 决策1 → 决策2 传递内容

```python
decision1_messages_history = [
    # 决策1初次调用
    {"role": "system", "content": DECISION1_SYSTEM_PROMPT},
    {"role": "user", "content": "患者信息：...\n患者描述：...\n..."},
    {"role": "assistant", "content": '{"需要补充门诊检查": true, ...}'},
    
    # 循环1
    {"role": "user", "content": "检查结果：血常规: Hb 110g/L\n妇科超声: ..."},
    {"role": "assistant", "content": '{"需要进一步检查": true, ...}'},
]
```

**User Prompt模板**:
```
## 【完整诊疗历史】

你之前已经完成了门诊阶段的诊疗，以下是完整的对话记录供你回顾：

{decision1_full_messages}  // 直接展示所有messages，或总结形式

现在患者已入院手机 准备收听音箱，请基于新的检查结果继续诊疗决策。

## 【入院检查结果】
{admission_checks}
```

#### 优点
- ✅ 完整保留诊断推理链
- ✅ 高度模拟真实临床场景
- ✅ AI可以回溯思考过程
- ✅ 有助于AI建立连贯的决策逻辑

#### 缺点
- ❌ Token消耗高（约8-15K tokens per stage）
- ❌ 长上下文可能导致AI注意力分散
- ❌ 成本高，速度慢
- ❌ 调试复杂

---

## Token消耗对比

### 假设场景
- 决策1: 1次循环
- 决策2: 2次循环
- 决策3-4: 无循环

### Token估算

| 阶段 | 简练型 (tokens) | 完整型 (tokens) | 差异 |
|:---|:---|:---|:---|
| **决策1** | | | |
| - 输入 | 2,000 | 2,000 | 0 |
| - 输出 | 500 | 500 | 0 |
| **决策2** | | | |
| - 输入 | 3,000 | 8,000 | +5,000 |
| - 输出 | 800 | 800 | 0 |
| **决策3** | | | |
| - 输入 | 4,500 | 14,000 | +9,500 |
| - 输出 | 600 | 600 | 0 |
| **决策4** | | | |
| - 输入 | 5,000 | 18,000 | +13,000 |
| - 输出 | 700 | 700 | 0 |
| **总计** | **17,100** | **44,600** | **+161%** |

### 成本估算（以Gemini 2.5 Pro为例）

- 输入token价格: $0.00125 / 1K
- 输出token价格: $0.005 / 1K

| 方案 | 每病例成本 | 300病例成本 |
|:---|:---|:---|
| 简练型 | $0.02 | $6.00 |
| 完整型 | $0.05 | $15.00 |

---

## 实现方案

### 可配置切换

#### `config/settings.py`

```python
# 上下文方案配置
CONTEXT_MODE = "concise"  # "concise" | "full"

# 方案特定配置
CONTEXT_CONFIG = {
    "concise": {
        "include_reasoning": False,  # 是否包含AI的诊断思维
        "max_summary_length": 2000,  # 摘要最大长度
    },
    "full": {
        "include_system_prompts": True,  // 是否包含System Prompt
        "compress_old_messages": False,  # 是否压缩早期messages
    }
}
```

#### 上下文构建器

```python
class ContextBuilder:
    """上下文构建器"""
    
    def __init__(self, mode: str = "concise"):
        self.mode = mode
        self.config = CONTEXT_CONFIG[mode]
    
    def build_decision2_context(self, decision1_data: dict) -> str:
        """构建决策2的上下文"""
        if self.mode == "concise":
            return self._build_concise_context(decision1_data)
        else:
            return self._build_full_context(decision1_data)
    
    def _build_concise_context(self, decision1_data: dict) -> str:
        """简练型上下文"""
        template = """
## 【门诊阶段信息回顾】

### 患者基本信息
{basic_info}

### 门诊初步诊断（AI生成）
{preliminary_diagnosis}

### 门诊阶段获得的所有检查信息
{outpatient_checks_summary}

**注**: 以上是门诊阶段你进行决策获得的所有临床信息。
"""
        return template.format(
            basic_info=decision1_data["basic_info"],
            preliminary_diagnosis=decision1_data["ai_output"]["初步诊断列表"],
            outpatient_checks_summary=self._summarize_checks(decision1_data["loop_history"])
        )
    
    def _build_full_context(self, decision1_data: dict) -> str:
        """完整型上下文"""
        # 方式1: 完整展示messages
        messages_str = ""
        for msg in decision1_data["full_messages"]:
            role_label = {"system": "系统", "user": "医生输入", "assistant": "AI回复"}[msg["role"]]
            messages_str += f"\n**【{role_label}】**\n{msg['content']}\n\n---\n"
        
        template = """
## 【门诊阶段完整对话记录】

{messages}

**注**: 以上是你在门诊阶段的完整诊疗对话。现在患者已入院，请基于新检查结果继续决策。
"""
        return template.format(messages=messages_str)
    
    def _summarize_checks(self, loop_history: list) -> str:
        """总结循环检查历史"""
        if not loop_history:
            return "未进行门诊检查循环。"
        
        summary = f"门诊阶段进行了{len(loop_history)}次检查循环：\n\n"
        for i, loop in enumerate(loop_history, 1):
            summary += f"**循环{i}**:\n"
            summary += f"- AI请求: {loop['ai_requested']}\n"
            summary += f"- 实际获得: {loop['judge_returned']}\n"
            if loop.get("warning"):
                summary += f"- 警告: {loop['warning']}\n"
            summary += "\n"
        
        return summary
```

### 在Workflow中使用

```python
class EvaluationWorkflow:
    def __init__(self, model_name: str, context_mode: str = "concise"):
        self.model_name = model_name
        self.context_builder = ContextBuilder(mode=context_mode)
        self.doctor_agent = DoctorAgent(model_name)
        ...
    
    def run_decision2(self, patient_data: dict, decision1_result: dict) -> dict:
        """执行决策2"""
        # 构建上下文
        context = self.context_builder.build_decision2_context(decision1_result)
        
        # 调用Doc Agent
        decision2_output = self.doctor_agent.make_admission_decision(
            context=context,
            admission_checks=patient_data["stage2_gt"]["actual_checks"]
        )
        
        return decision2_output
```

---

## 混合方案（推荐）

### 设计思路
结合两种方案的优点：
- **早期阶段（决策1-2）**: 使用完整型上下文，保留完整推理链
- **后期阶段（决策3-4）**: 使用简练型上下文，避免过长

### 配置

```python
CONTEXT_MODE = "hybrid"

CONTEXT_CONFIG = {
    "hybrid": {
        "decision1_to_2": "full",     # 决策1→2: 完整型
        "decision2_to_3": "full",     # 决策2→3: 完整型
        "decision3_to_4": "concise",  # 决策3→4: 简练型(已有完整病理)
    }
}
```

### Token估算

| 阶段 | 混合型 (tokens) | vs简练型 | vs完整型 |
|:---|:---|:---|:---|
| 决策1 | 2,500 | +500 | 0 |
| 决策2 | 9,300 | +6,300 | +1,300 |
| 决策3 | 10,000 | +5,500 | -4,000 |
| 决策4 | 6,000 | +1,000 | -12,000 |
| **总计** | **27,800** | **+63%** | **-38%** |

---

## 推荐建议

### 场景1: 研究/深度评估
- **方案**: 完整型或混合型
- **理由**: 需要完整保留AI的推理过程，便于后续分析

### 场景2: 大规模批量评测
- **方案**: 简练型
- **理由**: 成本优先，快速完成300+病例评测

### 场景3: 日常测试/调试
- **方案**: 简练型
- **理由**: 快速迭代，降低开发成本

---

## 实验建议

建议先使用**5-10个病例**分别测试两种方案：
1. 对比AI在两种方案下的决策质量
2. 统计实际token消耗
3. 评估调试难度
4. 根据实验结果选择最终方案

---

**实现位置**: `auto_eval_system/utils/context_builder.py`
