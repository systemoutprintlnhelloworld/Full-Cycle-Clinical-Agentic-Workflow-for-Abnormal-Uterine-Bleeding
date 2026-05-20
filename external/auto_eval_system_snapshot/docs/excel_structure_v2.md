# Excel 6表输出结构定义 v2.0

> 本文档详细说明评测系统的Excel输出结构。
>
> **关键设计**：6个Sheet，每个Sheet的每一行对应同一病例的测评结果。

---

## 总览

| Sheet | 名称 | 说明 | 包含循环 |
|:---|:---|:---|:---|
| 1 | 门诊检查循环 | Loop1-3循环的详细记录 | ✅ 3循环 |
| 2 | 门诊决策 | 决策1最终输出和Gate结果 | ❌ |
| 3 | 入院检查循环 | Loop1-3循环的详细记录 | ✅ 3循环 |
| 4 | 入院决策 | 决策2最终输出和Gate结果 | ❌ |
| 5 | 手术决策 | 决策3输出和Gate结果 | ❌ |
| 6 | 出院康复 | 决策4输出和评估 | ❌ |

**重要约束**：
- 所有Sheet的**第N行**对应**同一个病例**
- 循环Sheet预留Loop1/2/3三组列
- 如果某病例只循环1次，Loop2/3列留空

---

## Sheet 1: 门诊检查循环

### 字段定义

| 列名 | 说明 | 数据类型 | 数据来源 |
|:---|:---|:---|:---|
| **元数据** | | | |
| 病例ID | 病例唯一标识 | String | Context |
| 行号 | Excel原始行号(参考) | Integer | System |
| 模型 | Doc Agent模型名 | String | Config |
| Judge模型 | 固定Gemini 2.5 Pro | String | Config |
| 评测中心 | 佛山/武汉/新疆 | String | Context |
| | | | |
| **循环次数** | 实际循环次数(0-3) | Integer | System |
| | | | |
| **Loop1信息** | | | |
| Loop1_AI请求的检查项 | Doc Agent输出 | String(列表) | AI |
| Loop1_Judge匹配结果 | match数组 | String(JSON) | Judge |
| Loop1_Judge理由 | reason | String(MD) | Judge |
| Loop1_返回的检查内容 | 建议下一步输入的检查内容 | String | Judge |
| Loop1_未执行检查警告 | AI建议但实际未执行的检查 | String | Judge |
| Loop1_警告等级 | 1/2/3 | Integer | Judge |
| Loop1_检查匹配度 | 0.0-1.0 | Float | Judge |
| Loop1_合理性评分 | 0.0-1.0 | Float | Judge |
| Loop1_综合评分 | 0.0-1.0 | Float | Judge |
| | | | |
| **Loop2信息** | （同Loop1，字段前缀改为Loop2_） | | |
| Loop2_AI请求的检查项 | ... | ... | ... |
| ... | | | |
| | | | |
| **Loop3信息** | （同Loop1，字段前缀改为Loop3_） | | |
| Loop3_AI请求的检查项 | ... | ... | ... |
| ... | | | |

**列数**: 约30列（元数据6列 + Loop1-3各8列）

---

## Sheet 2: 门诊决策

### 字段定义

| 列名 | 说明 | 数据类型 | 数据来源 |
|:---|:---|:---|:---|
| **元数据** | | | |
| 病例ID | 病例唯一标识 | String | Context |
| 模型 | Doc Agent模型名 | String | Config |
| Judge模型 | Judge模型名 | String | Config |
| 评测中心 | 佛山/武汉/新疆 | String | Context |
| 环节状态 | 完成/终止/错误 | String | System |
| 终止原因 | 如状态=终止，说明原因 | String | System |
| | | | |
| **上下文信息** | | | |
| 门诊前信息 | basic_info + patient_description等 | String(MD) | Context |
| 经过的循环次数 | 0-3 | Integer | System |
| | | | |
| **AI输出（场景1）** | | | |
| AI_需要补充门诊检查 | true/false | Boolean | AI |
| AI_门诊信息汇总 | Markdown | String(MD) | AI |
| AI_诊断前所需检查 | Markdown列表 | String(MD) | AI |
| AI_理由 | | String | AI |
| AI_置信度_门诊检查方案 | 0.0-1.0 | Float | AI |
| | | | |
| **AI输出（场景2）** | | | |
| AI_需要进一步检查 | true/false | Boolean | AI |
| AI_门诊信息汇总 | Markdown | String(MD) | AI |
| AI_初步诊断列表 | Markdown列表 | String(MD) | AI |
| AI_建议检查项目 | Markdown列表 | String(MD) | AI |
| AI_诊断思维过程 | Markdown列表 | String(MD) | AI |
| AI_置信度_诊断 | 0.0-1.0 | Float | AI |
| AI_置信度_检查方案 | 0.0-1.0 | Float | AI |
| | | | |
| **AI输出（场景3）** | | | |
| AI_修正诊断 | | String | AI |
| AI_治疗方案 | Markdown列表 | String(MD) | AI |
| AI_诊断思维过程 | Markdown列表 | String(MD) | AI |
| AI_置信度_诊断 | 0.0-1.0 | Float | AI |
| | | | |
| **AI原始JSON** | 完整输出 | String(JSON) | AI |
| | | | |
| **GT参考信息** | | | |
| GT_门诊检查 | | String | GT |
| GT_入院诊断 | 用于Gate判断 | String | GT |
| | | | |
| **Gate Judge结果** | （仅场景2有） | | |
| Gate_诊断匹配结论 | 匹配/不匹配 | String | Judge |
| Gate_诊断匹配理由 | Markdown列表 | String(MD) | Judge |
| Gate_诊断评分 | 0.0-1.0 | Float | Judge |
| Gate_检查匹配度 | 0.0-1.0 | Float | Judge |
| Gate_检查评分 | 0.0-1.0 | Float | Judge |
| Gate_是否继续评测 | true/false | Boolean | Judge |
| Gate_综合评分 | 0.0-1.0 | Float | Judge |

**列数**: 约40列

---

## Sheet 3: 入院检查循环

### 字段定义

（结构同Sheet 1，但所有字段说明中的"门诊"改为"入院"）

主要区别：
- 警告文本改为"在入院检查阶段并未进行"
- 循环发生在决策2阶段

**列数**: 约30列

---

## Sheet 4: 入院决策

### 字段定义

| 列名 | 说明 | 数据类型 | 数据来源 |
|:---|:---|:---|:---|
| **元数据** | （同Sheet 2） | | |
| 病例ID | ... | ... | ... |
| | | | |
| **上下文信息** | | | |
| 决策1传递的上下文 | 完整门诊历史 | String(MD) | Context |
| 入院检查合并情况 | 是否合并了门诊检查 | String | Context |
| 经过的循环次数 | 0-3 | Integer | System |
| | | | |
| **AI输出（能够确诊）** | | | |
| AI_能够确诊 | true/false | Boolean | AI |
| AI_诊疗经过回顾 | Markdown表格 | String(MD) | AI |
| AI_修正诊断 | | String | AI |
| AI_修正诊断思维 | Markdown列表 | String(MD) | AI |
| AI_初步治疗方案 | Markdown列表 | String(MD) | AI |
| AI_治疗方案思维 | Markdown列表 | String(MD) | AI |
| AI_术后信息汇总 | | String(MD) | AI |
| AI_置信度_诊断 | 0.0-1.0 | Float | AI |
| AI_置信度_治疗方案 | 0.0-1.0 | Float | AI |
| | | | |
| **AI输出（无法确诊）** | | | |
| AI_需要补充检查 | Markdown列表 | String(MD) | AI |
| AI_理由 | | String | AI |
| | | | |
| **AI原始JSON** | 完整输出 | String(JSON) | AI |
| | | | |
| **GT参考信息** | | | |
| GT_修正诊断 | | String | GT |
| GT_手术方案 | | String | GT |
| GT_最终诊断 | 用于权衡判断 | String | GT |
| | | | |
| **Gate Judge结果** | | | |
| Gate_修正诊断匹配结论 | 完全一致/高度相似/... | String | Judge |
| Gate_修正诊断匹配理由 | Markdown列表 | String(MD) | Judge |
| Gate_修正诊断评分 | 0.0-1.0 | Float | Judge |
| Gate_手术方案匹配结论 | 完全一致/部分匹配/... | String | Judge |
| Gate_手术方案匹配理由 | Markdown列表 | String(MD) | Judge |
| Gate_手术方案反馈内容 | 如不匹配，反馈给AI | String | Judge |
| Gate_手术方案评分 | 0.0-1.0 | Float | Judge |
| Gate_是否继续评测 | true/false | Boolean | Judge |
| Gate_综合评分 | 0.0-1.0 | Float | Judge |

**列数**: 约45列

---

## Sheet 5: 手术决策

### 字段定义

| 列名 | 说明 | 数据类型 | 数据来源 |
|:---|:---|:---|:---|
| **元数据** | （同Sheet 2） | | |
| | | | |
| **上下文信息** | | | |
| 决策1-2传递的上下文 | 完整历史 | String(MD) | Context |
| | | | |
| **AI输出** | | | |
| AI_最终诊断_诊断名称 | | String | AI |
| AI_最终诊断_诊断思维 | Markdown列表 | String(MD) | AI |
| AI_术后治疗方案_方案详情 | Markdown列表 | String(MD) | AI |
| AI_术后治疗方案_方案思维 | Markdown列表 | String(MD) | AI |
| AI_术后信息汇总 | | String(MD) | AI |
| AI_置信度_最终诊断 | 0.0-1.0 | Float | AI |
| AI_置信度_术后方案 | 0.0-1.0 | Float | AI |
| | | | |
| **AI原始JSON** | 完整输出 | String(JSON) | AI |
| | | | |
| **GT参考信息** | | | |
| GT_最终诊断 | | String | GT |
| GT_术后治疗计划 | | String | GT |
| GT_术中所见及病理 | 用于AI输入 | String | GT |
| GT_实际手术方案 | 用于AI输入 | String | GT |
| | | | |
| **Gate Judge结果** | | | |
| Judge_诊断匹配评估_结论 | 完全一致/高度相似/... | String | Judge |
| Judge_诊断匹配评估_理由 | Markdown列表 | String(MD) | Judge |
| Judge_诊断匹配评估_评分 | 0.0-1.0 | Float | Judge |
| Judge_方案匹配评估_结论 | 完全一致/合理但有差异/... | String | Judge |
| Judge_方案匹配评估_理由 | Markdown列表 | String(MD) | Judge |
| Judge_方案匹配评估_评分 | 0.0-1.0 | Float | Judge |
| Judge_need_more_info | true/false | Boolean | Judge |
| Judge_more_info_reason | | String | Judge |
| Judge_综合评价 | | String(MD) | Judge |
| Judge_是否继续评测 | true/false | Boolean | Judge |
| Judge_综合评分 | 0.0-1.0 | Float | Judge |

**列数**: 约30列

---

## Sheet 6: 出院康复

### 字段定义

| 列名 | 说明 | 数据类型 | 数据来源 |
|:---|:---|:---|:---|
| **元数据** | （同Sheet 2） | | |
| | | | |
| **上下文信息** | | | |
| 决策1-3传递的上下文 | 按三阶段分割 | String(MD) | Context |
| | | | |
| **AI输出** | | | |
| AI_出院康复计划_方案详情 | Markdown列表 | String(MD) | AI |
| AI_出院康复计划_康复思维 | Markdown列表 | String(MD) | AI |
| AI_出院康复计划_制定依据 | | String | AI |
| AI_长期随访计划_是否需要常规随访 | true/false | Boolean | AI |
| AI_长期随访计划_方案详情 | Markdown列表 | String(MD) | AI |
| AI_长期随访计划_随访思维 | Markdown列表 | String(MD) | AI |
| AI_长期随访计划_制定依据 | | String | AI |
| AI_康复阶段信息汇总 | | String(MD) | AI |
| AI_置信度_康复计划 | 0.0-1.0 | Float | AI |
| AI_置信度_随访计划 | 0.0-1.0 | Float | AI |
| | | | |
| **AI原始JSON** | 完整输出 | String(JSON) | AI |
| | | | |
| **GT参考信息** | | | |
| GT_患者意愿情况 | | String | GT |
| GT_康复计划 | （如有） | String | GT |
| GT_随访计划 | （如有） | String | GT |
| GT_实际术后治疗计划 | 用于AI输入 | String | GT |
| | | | |
| **Judge评估结果** | | | |
| Judge_康复计划评估_评价 | 优秀/良好/... | String | Judge |
| Judge_康复计划评估_理由 | Markdown列表 | String(MD) | Judge |
| Judge_康复计划评估_评分 | 0.0-1.0 | Float | Judge |
| Judge_随访计划评估_评价 | 优秀/良好/.../过度随访 | String | Judge |
| Judge_随访计划评估_理由 | Markdown列表 | String(MD) | Judge |
| Judge_随访计划评估_评分 | 0.0-1.0 | Float | Judge |
| Judge_综合反馈 | | String(MD) | Judge |
| Judge_综合评分 | 0.0-1.0 | Float | Judge |

**列数**: 约30列

---

## 数据一致性保证

### 行对齐机制

所有6个Sheet必须保证：
- **Sheet1[行N] ↔ Sheet2[行N] ↔ ... ↔ Sheet6[行N]** 对应同一个病例
- 实现方式：所有Sheet都按照 `case_id` 排序，顺序一致
- 验证方式：每个Sheet的第1-3列必须包含 `病例ID` `模型` `评测中心`

### 循环数据处理

**场景1**: 病例A循环1次
- Sheet1 Loop1列：填充数据
- Sheet1 Loop2/3列：留空（或填充"N/A"）

**场景2**: 病例B循环3次
- Sheet1 Loop1/2/3列：全部填充数据

**场景3**: 病例C未循环（场景3直接确诊）
- Sheet1 所有Loop列：留空
- Sheet2 环节状态：`Terminated at D1 (Scene3)`

---

## Logger实现要点

### 初始化

```python
class EvaluationLogger:
    def __init__(self, model_name, output_dir="output"):
        self.excel_path = f"{output_dir}/evaluation_{model_name}.xlsx"
        # 初始化6个Sheet，每个都包含对应的列头
        self.sheets = {
            "门诊检查循环": self._init_sheet1_headers(),
            "门诊决策": self._init_sheet2_headers(),
            "入院检查循环": self._init_sheet3_headers(),
            "入院决策": self._init_sheet4_headers(),
            "手术决策": self._init_sheet5_headers(),
            "出院康复": self._init_sheet6_headers()
        }
        # 每个Sheet维护一个DataFrame缓存
        self.dfs = {name: pd.DataFrame(columns=headers) for name, headers in self.sheets.items()}
```

### 追加数据

```python
def append_case(self, case_id, sheet_name, data_dict):
    """
    追加一个病例的数据到指定Sheet
    
    关键：所有Sheet追加时，case_id必须相同，确保行对齐
    """
    # 确保case_id在所有Sheet中的行号一致
    row_idx = self._get_or_create_row(case_id)
    
    # 填充数据
    for col, value in data_dict.items():
        self.dfs[sheet_name].at[row_idx, col] = value
```

### 保存Excel

```python
def save(self):
    """将所有DataFrame写入Excel的不同Sheet"""
    with pd.ExcelWriter(self.excel_path, engine='openpyxl') as writer:
        for sheet_name, df in self.dfs.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
```

---

## 使用示例

```python
# 初始化Logger
logger = EvaluationLogger(model_name="gemini-2.5-pro")

# 病例开始评测
case_id = "FS001"

# 门诊检查循环（Loop 1）
logger.append_case(case_id, "门诊检查循环", {
    "病例ID": case_id,
    "模型": "gemini-2.5-pro",
    "循环次数": 1,
    "Loop1_AI请求的检查项": "['血常规', '妇科超声']",
    "Loop1_Judge匹配结果": "['是', '相似']",
    ...
})

# 门诊决策
logger.append_case(case_id, "门诊决策", {
    "病例ID": case_id,
    "模型": "gemini-2.5-pro",
    "AI_需要进一步检查": True,
    "AI_初步诊断列表": "1. 子宫内膜息肉\n2. 异常子宫出血",
    ...
})

# 保存
logger.save()
```

---

**实现位置**: `auto_eval_system/modules/logger_v2.py`
