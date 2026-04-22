# 25YZF106F项目审核经验教训

**项目**: 网络药理学分析中药复方治疗小儿抽动障碍的机制
**审核日期**: 2026-03-10
**评级**: ⭐⭐ (55/100) - 需要重大修改
**框架版本**: v4.2

---

## 关键发现

### FATAL级错误（2个）

#### 1. Word报告疾病名称复制粘贴错误
- **位置**: 第31行
- **错误**: 说检索"小儿抽动障碍"，但出现"非小细胞肺癌"
- **原因**: 模板化报告，复制了其他项目的文本但未修改
- **影响**: 审稿会直接拒稿
- **教训**: 必须系统性检查报告中的疾病名称一致性

#### 2. 靶点基因数严重不一致
- **报告**: 1310个靶点基因
- **实际**: 583个unique靶点基因（5211条记录）
- **差异**: 55.5%
- **原因**: 混淆了"关系数"（5211）和"unique基因数"（583）
- **影响**: 核心数据错误，影响整个研究可信度
- **教训**: 网络药理学项目必须区分"记录数"和"unique数"

---

## 新问题模式

### 模式6: 数字严重不一致（FATAL级）

**特征**: 报告中的核心数字与实际数据相差超过50%

**检测方法**:
```python
import pandas as pd

# 读取数据
df = pd.read_csv('Target_all_Result.csv')
total_records = len(df)  # 总记录数
unique_genes = df['Target'].nunique()  # unique基因数

# 检查报告数字
report_num = 1310
if report_num == total_records and unique_genes != total_records:
    print("WARNING: 报告混淆了记录数和unique数")
    print(f"  报告数字: {report_num}")
    print(f"  记录数: {total_records}")
    print(f"  Unique数: {unique_genes}")
```

**常见场景**:
- 靶点预测: 化合物-靶点关系数 vs unique靶点基因数
- 疾病基因: 合并前 vs 合并去重后
- 富集分析: 所有结果 vs 显著结果

**检查清单**:
- [ ] 报告中的"靶点数"是指unique基因还是关系？
- [ ] 报告中的"成分数"是指unique化合物还是关系？
- [ ] GeneCards/OMIM合并后是否正确去重？

---

### 模式7: 疾病名称复制粘贴错误（FATAL级）

**特征**: 方法部分出现错误项目的疾病名称

**示例**:
- 当前项目: 小儿抽动障碍
- Word报告: "检索非小细胞肺癌疾病相关基因"

**检测方法**:
```python
# 搜索正确的疾病名称
correct_diseases = ["小儿抽动障碍", "Tourette", "Pediatric Tic Disorder"]

# 常见错误疾病名称（来自其他项目）
wrong_diseases = {
    "非小细胞肺癌": "25YBB233F项目",
    "ICP": "26YHB205F项目",
    "脓毒症": "25YSH092F项目",
    "妊娠期": "26YHB205F项目",
    "PFDoDA": "26YHB205F化合物",
}

# 检查报告文本
with open('report_text.txt', 'r', encoding='utf-8') as f:
    content = f.read()
    for wrong, source in wrong_diseases.items():
        if wrong in content:
            print(f"FATAL: 发现{wrong}（来自{source}）")
```

**预防措施**:
1. 在Word报告撰写时，建立术语检查清单
2. 使用查找替换功能，检查所有疾病名称
3. 特别注意方法部分的复制粘贴内容

---

### 模式8: 图表编号跳跃/重复（严重级）

**特征**: 图表编号不连续或重复

**示例**:
```
Figure 5A: AKT1-quercetin
Figure 5B: BCL2-Acorine
Figure 5C: CTNNB1-Paeoniflorin
Figure 5D: IL1B-Beauvericin
Figure 5E: IL6-Geniposide
Figure 5E: PTGS2-curcumin  ❌ 重复
Figure 5E: STAT3-Gastrodin ❌ 重复
Figure 5E: TP53-kaempferol ❌ 重复
```

**应为**: 5E, 5F, 5G, 5H

**检测方法**:
```python
import re

with open('report_text.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# 提取所有Figure编号
figures = re.findall(r'Figure\s+(\d+)([A-Z]?)', content)

# 检查重复
from collections import Counter
fig_counts = Counter(figures)
duplicates = [fig for fig, count in fig_counts.items() if count > 1]

if duplicates:
    print(f"ERROR: 发现重复的图表编号: {duplicates}")
```

---

## 网络药理学项目特殊注意事项

### 1. 靶点数字验证（P0级）

**必须区分**:
- **关系数**: 化合物-靶点对的数目（如5211）
- **Unique靶点数**: 不同基因的数目（如583）
- **报告应该**: 明确说明是unique基因数

**检查方法**:
```python
# 检查靶点文件
df = pd.read_csv('02_Target/Target_all_Result.csv')

# 方法1: 检查unique数
unique_targets = df['Target'].nunique()
print(f"Unique靶点: {unique_targets}")

# 方法2: 检查是否是关系数
compound_target_pairs = len(df)
print(f"化合物-靶点关系: {compound_target_pairs}")

# 如果报告数字 = 关系数，但报告说"靶点基因"，则是错误
```

### 2. Hub基因一致性检查（P1级）

**规则**: 分子对接的蛋白应该是Hub基因

**检查方法**:
```python
# 报告中的Hub基因
hub_genes = {"AKT1", "TP53", "CTNNB1", "PTGS2", "IL6", "STAT3", "BCL2"}

# 分子对接的蛋白
docking_proteins = {"AKT1", "BCL2", "CTNNB1", "IL1B", "IL6", "PTGS2", "STAT3", "TP53"}

# 检查不一致
not_hub = docking_proteins - hub_genes
if not_hub:
    print(f"WARNING: 对接的蛋白不是Hub基因: {not_hub}")

missing_in_docking = hub_genes - docking_proteins
if missing_in_docking:
    print(f"INFO: Hub基因未进行对接: {missing_in_docking}")
```

**25YZF106F项目问题**:
- Hub基因列表: AKT1, TP53, CTNNB1, PTGS2, IL6, STAT3, BCL2
- 分子对接包含: IL1B（不是Hub基因）
- **问题**: 逻辑不一致

### 3. 成分-靶点关系数（P1级）

**常见混淆**:
- 123个活性成分（unique化合物）
- 138对关系（化合物-成分映射）

**检查方法**:
```python
# TCMSP成分
df_tcmsp = pd.read_excel('01_Ingredient/TCMSP_ingredient_filtered.xlsx')
print(f"TCMSP关系数: {len(df_tcmsp)}")

# HERB成分
df_herb = pd.read_csv('01_Ingredient/HERB_ingredient_SwissADME_filtered.csv')
print(f"HERB关系数: {len(df_herb)}")

# Unique化合物数
all_compounds = pd.concat([
    df_tcmsp['Mol'],
    df_herb['Mol']
]).unique()
print(f"Unique化合物数: {len(all_compounds)}")
```

### 4. 疾病基因筛选验证（P1级）

**GeneCards中位数筛选**:
- 报告说: Relevance score大于中位数
- 需要验证: 中位数的计算是否正确

**检查方法**:
```python
# 如果有原始的GeneCards数据
df_genecards = pd.read_csv('GeneCards_raw.csv')

# 计算中位数
median_score = df_genecards['Relevance_score'].median()
print(f"Relevance score中位数: {median_score}")

# 筛选后的基因数
filtered = df_genecards[df_genecards['Relevance_score'] > median_score]
print(f"筛选后基因数: {len(filtered)}")

# 对比报告数字
report_num = 1064
if len(filtered) != report_num:
    print(f"WARNING: 报告数字{report_num}与实际{len(filtered)}不一致")
```

**25YZF106F项目问题**:
- 报告说: GeneCards得到1064个
- 实际: Disease_Target_Result.csv有1682个
- **差异**: 可能是GeneCards和OMIM合并后的数字混淆

---

## 框架改进建议

### v4.3框架新增检查

#### 1. 数字一致性验证（P0级）
```python
def verify_number_consistency(report_num, actual_num, category, tolerance=0.2):
    """
    验证报告数字与实际数字的一致性

    参数:
        report_num: 报告中的数字
        actual_num: 实际数据中的数字
        category: 数据类别（用于报告）
        tolerance: 容忍的差异比例（默认20%）
    """
    if report_num == 0:
        return "SKIP: 报告数字为0"

    diff_ratio = abs(report_num - actual_num) / report_num

    if diff_ratio > tolerance:
        if diff_ratio > 0.5:
            return f"FATAL: {category}数字差异{diff_ratio*100:.1f}%（报告{report_num} vs 实际{actual_num}）"
        else:
            return f"ERROR: {category}数字差异{diff_ratio*100:.1f}%（报告{report_num} vs 实际{actual_num}）"
    else:
        return f"PASS: {category}数字一致（报告{report_num} vs 实际{actual_num}）"
```

#### 2. 靶点/记录数区分检查（P0级）
```python
def check_target_vs_records(df, report_num, label="靶点基因"):
    """
    网络药理学/毒理学项目特别检查：区分记录数和unique数

    参数:
        df: 靶点数据DataFrame
        report_num: 报告中的数字
        label: 数据标签
    """
    total_records = len(df)

    # 尝试找到基因列
    gene_col = None
    for col in df.columns:
        if 'gene' in col.lower() or 'target' in col.lower() or 'symbol' in col.lower():
            gene_col = col
            break

    if gene_col:
        unique_genes = df[gene_col].nunique()

        # 检查报告数字匹配哪种
        if report_num == total_records and unique_genes != total_records:
            return f"FATAL: {label}报告混淆了记录数（{total_records}）和unique数（{unique_genes}）"
        elif report_num == unique_genes:
            return f"PASS: {label}数字正确（unique {unique_genes}）"
        else:
            diff = min(abs(report_num - unique_genes), abs(report_num - total_records))
            return f"WARNING: {label}数字不匹配（报告{report_num}，记录{total_records}，unique{unique_genes}）"
    else:
        return f"INFO: 无法找到基因列进行验证"
```

#### 3. 图表编号连续性检查（P1级）
```python
def check_figure_numbering(text):
    """
    检查图表编号是否连续，无跳跃或重复
    """
    import re
    from collections import Counter

    # 提取Figure编号
    figures = re.findall(r'Figure\s+(\d+)([A-Z]?)', text)

    # 检查重复
    fig_counts = Counter(figures)
    duplicates = [(fig, count) for fig, count in fig_counts.items() if count > 1]

    issues = []
    if duplicates:
        for fig, count in duplicates:
            num, letter = fig
            issues.append(f"ERROR: Figure {num}{letter}重复{count}次")

    # 检查连续性（针对同一主编号的子图）
    fig_groups = {}
    for num, letter in figures:
        if num not in fig_groups:
            fig_groups[num] = []
        if letter:
            fig_groups[num].append(letter)

    for num, letters in fig_groups.items():
        if len(letters) > 1:
            # 检查字母是否连续
            expected = [chr(ord('A') + i) for i in range(len(letters))]
            if sorted(letters) != expected:
                issues.append(f"WARNING: Figure {num}子图编号不连续（{sorted(letters)}）")

    return issues
```

#### 4. 疾病术语一致性检查（P0级）
```python
def check_disease_consistency(text, correct_diseases, project_id):
    """
    检查报告中的疾病术语是否与项目一致

    参数:
        text: 报告文本
        correct_diseases: 正确的疾病名称列表
        project_id: 项目编号
    """
    # 常见错误疾病术语（来自其他项目）
    wrong_terms = {
        '非小细胞肺癌': '25YBB233F',
        'ICP': '26YHB205F',
        '脓毒症': '25YSH092F',
        '妊娠期': '26YHB205F',
        'PFDoDA': '26YHB205F',
        'COPD': '其他项目',
        'ARDS': '其他项目',
    }

    issues = []

    # 检查是否出现错误术语
    for wrong, source in wrong_terms.items():
        if wrong in text:
            idx = text.find(wrong)
            context = text[max(0, idx-50):min(len(text), idx+50)]
            issues.append(f"FATAL: 发现错误术语'{wrong}'（来自{source}）\n  上下文: ...{context}...")

    # 检查正确术语是否出现
    correct_found = [d for d in correct_diseases if d in text]
    if not correct_found:
        issues.append(f"WARNING: 未找到正确的疾病术语: {correct_diseases}")

    return issues
```

---

## 与26YHB205F项目的对比

### 相似点
1. ✅ 都存在Word报告复制粘贴错误
2. ✅ GO/KEGG数字完全一致
3. ✅ 都是网络药理学/毒理学项目

### 不同点
| 方面 | 26YHB205F | 25YZF106F |
|------|-----------|-----------|
| 评级 | ⭐⭐⭐ (65/100) | ⭐⭐ (55/100) |
| 主要问题 | 报告内容描述错误 | **报告错误 + 数据严重不一致** |
| 数字一致性 | 基本一致 | **靶点基因差55.5%** |
| 术语翻译 | 多处错误 | 未发现明显翻译错误 |
| URL错误 | 有（STRING→DrugBank） | 无 |
| 数据库功能 | UniProt提供3D结构错误 | 未发现 |

### 结论
25YZF106F的问题**比26YHB205F更严重**，因为涉及核心数据错误。

---

## 审核流程优化

### Phase 2重点（Word报告检查）

**必须执行**:
1. ✅ 疾病术语一致性检查（P0级）
2. ✅ 数据库URL和名称检查（P0级）
3. ✅ 拼写错误检查（P1级）
4. ✅ 方法学描述验证（P1级）
5. ✅ 图表编号一致性检查（P1级）
6. ✅ 关键数字提取（P0级）

**优先级**:
- P0级: FATAL级错误，必须修改
- P1级: 严重级错误，建议修改

### Phase 3重点（数据验证）

**必须验证**:
1. ✅ 靶点基因: unique数 vs 报告数字
2. ✅ 疾病基因: GeneCards + OMIM vs 报告数字
3. ✅ 交集基因: 实际交集数 vs 报告数字
4. ✅ GO/KEGG: 实际条目数 vs 报告数字
5. ✅ Hub基因: PPI文件验证
6. ✅ 分子对接: 蛋白是否是Hub基因

---

## 给用户的建议

### 对于25YZF106F项目

1. **立即修改**（FATAL级）:
   - Word报告第31行: "非小细胞肺癌" → "小儿抽动障碍"
   - 重新计算靶点基因数: 1310 → 583
   - 验证疾病基因数: 1622 vs 1682

2. **建议修改**（严重级）:
   - "OMIN" → "OMIM"
   - Figure 5编号修正
   - 澄清IL1B对接逻辑

3. **修改后重新审核**:
   - 所有数字修正后
   - 需要重新验证一致性

### 对于未来项目

1. **使用v4.3框架**（整合本次经验）:
   - 增加数字一致性验证
   - 增加靶点/记录数区分检查
   - 增加图表编号连续性检查
   - 增加疾病术语一致性检查

2. **审核重点**:
   - Phase 2: Word报告检查（最重要！）
   - Phase 3: 数据验证（特别是unique vs 记录数）

3. **质量标准**:
   - ⭐⭐⭐⭐⭐ (90-100): 可直接发表
   - ⭐⭐⭐⭐ (80-89): 小修后发表
   - ⭐⭐⭐ (65-79): 需要修改
   - ⭐⭐ (50-64): 需要重大修改
   - ⭐ (0-49): 不可接受

---

**经验总结完成时间**: 2026-03-10
**框架版本**: v4.2 → v4.3（建议升级）
**下一次审核**: 整合v4.3新检查项
