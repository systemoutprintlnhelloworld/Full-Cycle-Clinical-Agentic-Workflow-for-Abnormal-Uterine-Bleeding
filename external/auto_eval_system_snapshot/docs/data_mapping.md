# 三中心数据字段映射规范 (v2.0)

> 本文档定义了系统如何从佛山、武汉、新疆三个中心的 Excel 文件中提取字段，并映射到 Doc Agent 的输入。
> **状态**: Based on `data_loader_strategy.py` implementation.

---

## 1. 通用字段定义 (System Schema)

所有中心的解析器 (`Strategy`) 都必须输出包含以下 Key 的字典。

| 字段 Key | 说明 | Doc Agent 对应 Prompt 占位符 | 是否必填 |
| :--- | :--- | :--- | :--- |
| `case_id` | 病例唯一标识 (如 `foshan_5`) | (Logger使用) | ✅ |
| `age` | 患者年龄 | `{age}` | ⚠️ (缺省"未知") |
| `gender` | 性别 | `{gender}` | ⚠️ (缺省"未知") |
| `ethnicity` | 种族/民族 | `{ethnicity}` | ⚠️ (缺省"未知") |
| `chief_complaint` | 主诉 | `{chief_complaint}` | ✅ |
| `present_illness` | 现病史 | `{present_illness}` | ✅ |
| `past_history` | 既往史 | `{past_history}` | ⚠️ (缺省"无") |
| `menstrual_history` | 月经婚育史 | `{menstrual_history}` | ⚠️ (缺省"无") |
| `family_history` | 家族史 | `{family_history}` | ⚠️ (缺省"无") |
| `physical_exam` | 体格/专科检查 | `{physical_exam}` | ⚠️ (缺省"无") |

---

## 2. 佛山中心 (Foshan)

**策略类**: `FoshanStrategy`
**Header识别**: 自动搜索包含 "基本情况" 或 "主诉" 的行。

### 字段映射表

| 系统字段 | Excel 列名关键词 (模糊匹配) | 处理逻辑 | 待确认/TODO |
| :--- | :--- | :--- | :--- |
| `age/gender` | "基本情况", "一般情况" | 从文本中正则提取 "X岁", "男/女" | 确认是否有独立列 |
| `chief_complaint` | "主诉" | 直接读取 | |
| `present_illness` | "现病史" | 直接读取 | |
| `past_history` | "既往史" | 直接读取 | |
| `menstrual_history`| "月经", "婚育" | 优先匹配同时包含的列，或分别读取合并 | |
| `family_history` | "家族史" | 直接读取 | |
| `physical_exam` | "体格检查", "妇科检查" | 合并读取 | |
| `gt_outpatient_checks` | "门诊", "辅助检查" | | 确认列名是否唯一 |
| `gt_admission_diagnosis` | "入院诊断", "初步诊断" | | |

---

## 3. 武汉中心 (Wuhan)

**策略类**: `WuhanStrategy`
**Header识别**: 硬编码为 **第4行** (Index 3)。

### 字段映射表

| 系统字段 | Excel 列名关键词 | 处理逻辑 | 待确认/TODO |
| :--- | :--- | :--- | :--- |
| `age` | "年龄" | 独立列读取 | |
| `gender` | "性别" | 独立列读取 (若无，尝试从种族列推断，或默认女) | 确认武汉表是否有性别列 |
| `ethnicity` | "种族" | 独立列读取 | |
| `chief_complaint` | "主诉" | | |
| `present_illness` | "现病史" | | |
| `gt_pathology` | "常规病理" | | |

---

## 4. 新疆中心 (Xinjiang)

**策略类**: `XinjiangStrategy`
**Header识别**: 硬编码为 **第4行** (Index 3)。

### 字段映射表

| 系统字段 | Excel 列名关键词 | 说明 |
| :--- | :--- | :--- |
| `ethnicity` | "民族" | |
| `physical_exam` | "查体" | 注意与"专科检查"的区别，代码目前匹配"查体" |
| `gt_surgery_plan` | "治疗方案" | |

---

## 5. 如何核验与完善

1. 将三个中心的 Excel 样本文件放入 `data/raw/` 目录。
2. 运行 `python verify_headers_and_inspect.py`。
3. 查看生成报告 `docs/raw_data_columns_report.md`。
4. 检查报告中的实际列名是否与上述关键词匹配。
5. 如有不匹配，修改 `auto_eval_system/modules/data_loader_strategy.py` 中的 `keywords` 列表。
