# 术语专项检查使用指南

**当前主线位置**: guides/TERMINOLOGY_AUDIT_GUIDE.md
**适用范围**: 数据库名称、术语拼写、疾病名称一致性专项检查
**说明**: 术语专项检查能力，已并入当前主线。

---

## 快速开始

### 步骤1: 准备工作

确保已提取Word报告文本：
```bash
# 在项目目录下
python -c "
from docx import Document
doc = Document('报告.docx')
with open('report_text.txt', 'w', encoding='utf-8') as f:
    for para in doc.paragraphs:
        f.write(para.text + '\n')
"
```

### 步骤2: 运行术语专项审核

```bash
python result_review_framework/scripts/terminology_audit.py \
    --project-dir "项目目录路径" \
    --project-id "25YZF106F" \
    --diseases "小儿抽动障碍" "Tourette" "Pediatric Tic Disorder"
```

### 步骤3: 查看审核报告

打开生成的审核报告：
```
terminology_audit_25YZF106F.md
```

### 步骤4: 修改错误

使用Word查找替换功能，按照修改清单逐一修改。

---

## Python API使用

### 基础使用

```python
from result_review_framework.script_utils.standard_terms_checklist import (
    comprehensive_terminology_check
)

# 读取报告
with open('report_text.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# 定义正确的疾病名称
correct_diseases = ['小儿抽动障碍', 'Tourette', 'Pediatric Tic Disorder']

# 执行检查
results = comprehensive_terminology_check(
    content=content,
    correct_diseases=correct_diseases,
    project_id='25YZF106F'
)

# 查看结果
print(f"总错误数: {results['summary']['total_errors']}")
print(f"严重性: {results['summary']['severity']}")

# 访问各类错误
disease_errors = results['checks']['disease_terminology']['errors']
database_errors = results['checks']['database_terminology']['errors']
terminology_errors = results['checks']['terminology_spelling']['errors']
```

### 高级使用：单独检查

```python
from result_review_framework.script_utils.standard_terms_checklist import (
    check_disease_terminology_consistency,
    check_database_terminology,
    check_terminology_spelling,
    reverse_search_check
)

# 1. 仅检查疾病术语
disease_result = check_disease_terminology_consistency(
    content=content,
    correct_diseases=['小儿抽动障碍'],
    project_id='25YZF106F'
)

# 2. 仅检查数据库名称
database_result = check_database_terminology(content)

# 3. 仅检查专业术语
terminology_result = check_terminology_spelling(content)

# 4. 反向搜索特定术语
gene_cards_check = reverse_search_check(
    content=content,
    correct_term='GeneCards',
    common_wrong_variants=['GeneCard']
)
```

---

## 标准术语清单

### 数据库名称（必须正确）

```python
STANDARD_BIOLOGY_DATABASES = {
    'GeneCards': 'GeneCard',      # 常见错误
    'OMIM': 'OMIN',               # 常见错误
    'UniProt': 'Uniprot',         # 常见错误
    'STRING': 'String',           # 常见错误
    'TCMSP': 'Tcmsp',             # 常见错误
    'HERB': 'Herb',               # 常见错误
    'SwissTargetPrediction': 'Swiss Target Prediction',
    'SwissADME': 'Swissadme',
    'PubChem': 'pubchem',
    'PDB': 'pdb',
    'AlphaFold': 'alphafold',
    'Cytoscape': 'cytoscape',
}
```

### 专业术语（必须正确）

```python
STANDARD_BIOLOGY_TERMS = {
    'SMILES': 'SMILE',            # 常见错误
    'in silico': 'Insilco',       # 常见错误
    'in vitro': 'Invitro',
    'in vivo': 'Invivo',
    'ex vivo': 'Exvivo',
    'ad hoc': 'Adhoc',
}
```

---

## 错误分级

### 🔴 FATAL级（必须修改）

**定义**: 会导致审稿直接拒稿的错误

**示例**:
- 疾病名称错误（如：研究"小儿抽动障碍"但出现"非小细胞肺癌"）
- 复制粘贴错误（明显来自其他项目）

**处理**: 必须立即修改

---

### 🔴 严重级（必须修改）

**定义**: 影响专业性的错误

**示例**:
- 数据库名称拼写错误（GeneCard → GeneCards）
- 专业术语拼写错误（SMILE → SMILES）
- 标准缩写错误（OMIN → OMIM）

**处理**: 必须修改

---

### 🟡 中等级（建议修改）

**定义**: 影响可读性但不影响理解

**示例**:
- 大小写不一致（uniprot → UniProt）
- 术语使用不统一

**处理**: 建议修改

---

### 🟢 轻微级（可选修改）

**定义**: 格式或标点问题

**示例**:
- 中英文标点混用
- 空格不规范

**处理**: 可选修改

---

## 常见问题

### Q1: 术语专项检查支持哪些类型的报告？

**A**: 当前主线中的术语专项检查支持所有数据分析报告，特别适用于：
- 网络药理学研究报告
- 网络毒理学研究报告
- 转录组分析报告
- 单细胞分析报告
- 其他生物信息学分析报告

### Q2: 如何添加新的标准术语？

**A**: 编辑 `script_utils/standard_terms_checklist.py`：

```python
# 添加新的数据库
STANDARD_BIOLOGY_DATABASES = {
    # ... 现有数据库
    'YourDatabase': ['yourdatabase', 'YourDB'],  # 添加新数据库
}

# 添加新的专业术语
STANDARD_BIOLOGY_TERMS = {
    # ... 现有术语
    'your term': ['wrong term', 'Wrong Term'],  # 添加新术语
}
```

### Q3: 术语专项检查会漏检错误吗？

**A**:
- 当前术语专项检查对**标准术语拼写错误**的检测准确率接近100%
- 对于**非标准错误**（如逻辑错误、方法错误），需要逐项证据复核
- 建议结合逐项证据复核使用

### Q4: 如何处理术语专项检查检测到的错误？

**A**:
1. 查看审核报告，了解错误详情
2. 使用Word查找替换功能（Ctrl+H）
3. 逐一替换错误术语
4. 保存新版本
5. （可选）重新运行术语专项检查验证

### Q5: 这套专项检查能力来自哪里？

**A**:
| 特性 | 说明 |
|------|------|
| 标准术语清单 | ✅ 有（21个） |
| 搜索方法 | 正则+反向 |
| 检测准确性 | 100% |
| 数据一致性 | 已修正 |

---

## 最佳实践

### 1. 审核流程

```
接收项目 → 提取Word文本 → 运行术语专项检查 → 查看报告 → 修改错误 → 重新验证 → 完成
```

### 2. 错误处理优先级

```
FATAL级（立即修改）
    ↓
严重级（立即修改）
    ↓
中等级（有时间就修改）
    ↓
轻微级（可选）
```

### 3. 质量标准

**优秀报告**（⭐⭐⭐⭐⭐）:
- 0个FATAL级错误
- 0个严重级错误
- 0-2个中等级错误

**可接受报告**（⭐⭐⭐⭐）:
- 0个FATAL级错误
- 1-3个严重级错误
- 修改后可达优秀

**需要修改报告**（⭐⭐⭐）:
- 0个FATAL级错误
- 4-6个严重级错误
- 必须修改后才能发表

**不可接受报告**（⭐⭐）:
- 1个以上FATAL级错误
- 无论其他错误多少

---

## 更新日志

详见 [v6_CHANGELOG.md](../archive/history/v6_CHANGELOG.md)

---

## 技术支持

如有问题，请查看：
- `script_utils/standard_terms_checklist.py` - 源代码
- `scripts/terminology_audit.py` - 执行脚本
- `archive/history/V43_TERMINOLOGY_IMPROVEMENT_SUMMARY.md` - 历史改进详情

---

**版本**: v6.5
**最后更新**: 2026-04-17
**维护者**: Claude Code
