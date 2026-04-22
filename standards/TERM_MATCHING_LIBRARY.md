# 术语主题匹配库
> **用途**: 生物信息学项目审核时，检测术语是否与项目疾病/主题类型匹配
>
> **创建日期**: 2026-02-13
> **基于项目**: 25YLC105F（肾结石项目使用癌症术语Tumor/Normal）

---

## 使用说明

```python
# 使用示例
from TERM_MATCHING import validate_terms, get_project_terms

# 获取项目正确术语
correct_terms = get_project_terms('肾结石')

# 验证代码中的术语
result = validate_terms(code_text, '肾结石', correct_terms)
if result['mismatch_terms']:
    print(f"发现不匹配术语: {result['mismatch_terms']}")
```

---

## 疾病类型术语库

### 1. 癌症 (Cancer)

**正确术语**:
- 样本分组: Tumor / Normal
- 组织类型: Tumor tissue / Normal tissue
- 细胞状态: Malignant / Benign

**相关术语**:
- Cancer, Malignant, Metastasis, Carcinoma, Sarcoma, Adenocarcinoma
- Biopsy, Resection, Chemotherapy, Radiotherapy

**数据库通路特征**:
- KEGG: hsa05200 (Pathways in cancer), hsa05220 (Chronic myeloid leukemia)
- GO: 癌症相关生物过程

---

### 2. 肾结石/兰德尔斑块 (Kidney Stone / Randall's Plaque)

**正确术语**:
- 样本分组: Disease / Control 或 Randall's plaque / Healthy
- 组织类型: Diseased tissue / Healthy tissue
- 细胞状态: Affected / Normal

**相关术语**:
- Kidney stone, Renal calculus, Nephrolithiasis
- Randall's plaque, Calcification, Papillary, Ductal
- Calcium oxalate, Uric acid, Struvite, Cystine

**数据库通路特征**:
- KEGG: hsa04910 (Proximal tubule bicarbonate reclamation)
- GO: 肾脏发育、离子运输相关

---

### 3. 心血管疾病 (Cardiovascular)

**正确术语**:
- 样本分组: Disease / Control 或 Case / Control
- 组织类型: Cardiac tissue / Normal tissue
- 细胞状态: Affected / Healthy

**相关术语**:
- Heart, Cardiac, Myocardial, Cardiovascular
- Hypertension, Heart failure, Arrhythmia
- Atherosclerosis, Coronary, Myocardial infarction, Stroke

**数据库通路特征**:
- KEGG: hsa04060 (Cytokine-cytokine receptor interaction)
- GO: 心肌收缩、心脏发育相关

---

### 4. 代谢疾病 (Metabolic)

**正确术语**:
- 样本分组: Disease / Control
- 组织类型: Affected tissue / Normal tissue

**相关术语**:
- Diabetes, Glucose, Insulin, Glucagon
- Obesity, Lipid, Cholesterol, Triglyceride
- Metabolic syndrome, Insulin resistance

**数据库通路特征**:
- KEGG: hsa04920 (Adipocytokine signaling)
- GO: 胰岛素分泌、血糖调节相关

---

### 5. 神经系统疾病 (Neurological)

**正确术语**:
- 样本分组: Disease / Control

**相关术语**:
- Brain, Neuron, Neural, Synapse, Neurotransmitter
- Alzheimer's, Parkinson's, Huntington's, ALS
- Dementia, Cognitive, Neurodegeneration

**数据库通路特征**:
- KEGG: hsa05010 (Huntington's disease)
- GO: 神经传递、突触相关

---

### 6. 免疫疾病 (Immunological)

**正确术语**:
- 样本分组: Disease / Control

**相关术语**:
- Inflammation, Immune, Inflammatory response
- Cytokine, Chemokine, Interleukin
- Antibody, Antigen, T cell, B cell, Macrophage

**数据库通路特征**:
- KEGG: hsa04660 (T cell receptor signaling)
- GO: 免疫反应相关

---

### 7. 炎症性肠病 (IBD / Inflammatory Bowel Disease)

**正确术语**:
- 样本分组: Disease / Control 或 Inflamed / Non-inflamed 或 UC / CD / Healthy
- 组织类型: Inflamed mucosa / Normal mucosa
- 细胞状态: Active / Remission

**相关术语**:
- Ulcerative colitis (UC), Crohn's disease (CD), IBD
- Colitis, Inflammatory bowel disease, Mucosa, Intestinal
- Dysbiosis, Microbiome, Epithelial barrier

**数据库通路特征**:
- KEGG: hsa04060 (Cytokine-cytokine receptor interaction), hsa04659 (Th17 cell differentiation), hsa04668 (TNF signaling)
- GO: NF-κB signaling, IL-17 production, Th17/Treg balance, Mucosal immunity

**常见误用**:
- ❌ Tumor / Normal（癌症术语混入 IBD 项目）
- ❌ Case / Control 在肠道样本中应视实际标注决定，部分数据集使用 Case/Control 作为标准标签

---

## 癌种缩写冲突检测
> **背景**：26YYS083F（胰腺癌PAAD）报告中残留"HCC"（肝癌），25YYF085F未涉及但同类风险高。
> **规则**：癌症项目报告中出现的TCGA癌种缩写必须与项目实际癌种一致。

### TCGA 癌种缩写表

| 缩写 | 英文全称 | 中文 |
|------|----------|------|
| ACC | Adrenocortical carcinoma | 肾上腺皮质癌 |
| BLCA | Bladder urothelial carcinoma | 膀胱尿路上皮癌 |
| BRCA | Breast invasive carcinoma | 乳腺浸润性癌 |
| CESC | Cervical squamous cell carcinoma | 宫颈鳞状细胞癌 |
| CHOL | Cholangiocarcinoma | 胆管癌 |
| COAD | Colon adenocarcinoma | 结肠腺癌 |
| DLBC | DLBCL | 弥漫性大B细胞淋巴瘤 |
| ESCA | Esophageal carcinoma | 食管癌 |
| GBM | Glioblastoma multiforme | 胶质母细胞瘤 |
| HNSC | Head and neck squamous cell carcinoma | 头颈部鳞状细胞癌 |
| KICH | Kidney chromophobe | 肾嫌色细胞癌 |
| KIRC | Kidney renal clear cell carcinoma | 肾透明细胞癌 |
| KIRP | Kidney renal papillary cell carcinoma | 肾乳头状细胞癌 |
| LAML | Acute myeloid leukemia | 急性髓系白血病 |
| LGG | Brain lower grade glioma | 脑低级别胶质瘤 |
| LIHC | Liver hepatocellular carcinoma | 肝细胞癌 |
| LUAD | Lung adenocarcinoma | 肺腺癌 |
| LUSC | Lung squamous cell carcinoma | 肺鳞状细胞癌 |
| MESO | Mesothelioma | 间皮瘤 |
| OV | Ovarian serous cystadenocarcinoma | 卵巢浆液性囊腺癌 |
| PAAD | Pancreatic adenocarcinoma | 胰腺腺癌 |
| PCPG | Pheochromocytoma and paraganglioma | 嗜铬细胞瘤 |
| PRAD | Prostate adenocarcinoma | 前列腺腺癌 |
| READ | Rectum adenocarcinoma | 直肠腺癌 |
| SARC | Sarcoma | 肉瘤 |
| SKCM | Skin cutaneous melanoma | 皮肤黑色素瘤 |
| STAD | Stomach adenocarcinoma | 胃腺癌 |
| TGCT | Testicular germ cell tumors | 睾丸生殖细胞瘤 |
| THCA | Thyroid carcinoma | 甲状腺癌 |
| THYM | Thymoma | 胸腺瘤 |
| UCEC | Uterine corpus endometrial carcinoma | 子宫内膜癌 |
| UCS | Uterine carcinosarcoma | 子宫癌肉瘤 |
| UVM | Uveal melanoma | 葡萄膜黑色素瘤 |

### 常用非TCGA癌种缩写

| 缩写 | 中文 | 注意 |
|------|------|------|
| HCC | 肝细胞癌 | TCGA中为LIHC |
| NSCLC | 非小细胞肺癌 | 含LUAD+LUSC |
| CRC | 结直肠癌 | 含COAD+READ |
| RCC | 肾细胞癌 | 含KIRC+KIRP+KICH |
| LSCC | 肺鳞癌 | 同义LUSC |
| PDAC | 胰腺导管腺癌 | 常与PAAD互用 |
| GC | 胃癌 | 同义STAD |

### 检测规则

1. 确定项目的目标癌种缩写（如 PAAD）
2. 全文搜索所有出现的 TCGA 癌种缩写
3. 若出现非目标癌种缩写 → 🔴 FATAL（跨项目Copy-paste证据）
4. 特殊：TCGA-PAAD 项目出现 PDAC 不算错误（同义词）
5. 特殊：泛癌分析(pan-cancer)项目中多种缩写同时出现是正常的

---

## 术语冲突检测表

| 当前项目类型 | 正确术语 | 不应使用的术语 | 冲突来源 |
|------------|----------|---------------|----------|
| 肾结石 | Disease/Control | Tumor/Normal ❌ | 癌症项目 |
| 肾结石 | Randall's plaque | Cancer ❌ | 癌症项目 |
| 心血管 | Cardiac/Heart | Tumor ❌ | 癌症项目 |
| 心血管 | Disease/Control | Diabetes ❌ | 代谢项目 |
| 代谢 | Diabetes/Glucose | Cardiac ❌ | 心血管项目 |
| 神经 | Brain/Neuron | Cardiac ❌ | 心血管项目 |
| 免疫 | Inflammation | Tumor ❌ | 癌症项目 |
| IBD | UC/CD/Inflamed | Tumor/Normal ❌ | 癌症项目 |
| IBD | Disease/Control | Cancer ❌ | 癌症项目 |

---

## 检测方法

### Python脚本

```python
#!/usr/bin/env python3
"""
术语主题匹配检测

检测代码/报告中的术语是否与项目疾病类型匹配
"""

import re
from typing import Dict, List, Set

TERM_DATABASE = {
    '癌症': {
        'correct': ['Tumor', 'Normal', 'Cancer', 'Malignant'],
        'wrong': [],  # 癌症是通用术语，无特定错误术语
        'keywords': ['Tumor', 'Normal', 'Cancer', 'Malignant', 'Metastasis'],
        # 癌种缩写交叉检测
        'cancer_abbreviations': [
            'ACC', 'BLCA', 'BRCA', 'CESC', 'CHOL', 'COAD', 'DLBC', 'ESCA',
            'GBM', 'HNSC', 'KICH', 'KIRC', 'KIRP', 'LAML', 'LGG', 'LIHC',
            'LUAD', 'LUSC', 'MESO', 'OV', 'PAAD', 'PCPG', 'PRAD', 'READ',
            'SARC', 'SKCM', 'STAD', 'TGCT', 'THCA', 'THYM', 'UCEC', 'UCS', 'UVM',
            'HCC', 'NSCLC', 'CRC', 'RCC', 'LSCC', 'PDAC', 'GC'
        ],
        # 同义映射：检测到某缩写时，这些也算正确
        'cancer_synonyms': {
            'LIHC': ['HCC'],
            'HCC': ['LIHC'],
            'LUSC': ['LSCC'],
            'LSCC': ['LUSC'],
            'PAAD': ['PDAC'],
            'PDAC': ['PAAD'],
            'STAD': ['GC'],
            'GC': ['STAD'],
            'COAD': ['CRC'],
            'READ': ['CRC'],
            'CRC': ['COAD', 'READ'],
            'KIRC': ['RCC'],
            'KIRP': ['RCC'],
            'KICH': ['RCC'],
            'RCC': ['KIRC', 'KIRP', 'KICH'],
            'LUAD': ['NSCLC'],
            'LUSC': ['NSCLC'],
            'NSCLC': ['LUAD', 'LUSC'],
        }
    },
    '肾结石': {
        'correct': ['Disease', 'Control', 'Randall', 'plaque', 'Kidney', 'stone'],
        'wrong': ['Tumor', 'Normal', 'Cancer', 'Malignant'],  # 不应使用癌症术语
        'keywords': ['Disease', 'Control', 'Randall', 'plaque', 'calcification']
    },
    '心血管': {
        'correct': ['Cardiac', 'Heart', 'Case', 'Control'],
        'wrong': ['Tumor', 'Normal', 'Cancer'],
        'keywords': ['Cardiac', 'Heart', 'Myocardial', 'cardiovascular']
    },
    '代谢': {
        'correct': ['Disease', 'Control', 'Diabetes', 'Glucose'],
        'wrong': ['Cardiac', 'Heart', 'Tumor'],
        'keywords': ['Diabetes', 'Glucose', 'Insulin', 'metabolic']
    },
    '神经': {
        'correct': ['Disease', 'Control', 'Brain', 'Neuron'],
        'wrong': ['Cardiac', 'Heart', 'Tumor'],
        'keywords': ['Brain', 'Neural', 'neuron', 'synapse']
    },
    '免疫': {
        'correct': ['Disease', 'Control', 'Inflammation'],
        'wrong': ['Tumor', 'Normal'],
        'keywords': ['Inflammation', 'immune', 'cytokine', 'antibody']
    },
    'IBD': {
        'correct': ['Disease', 'Control', 'Inflamed', 'Non-inflamed', 'UC', 'CD', 'Healthy'],
        'wrong': ['Tumor', 'Normal', 'Cancer', 'Malignant'],
        'keywords': ['IBD', 'colitis', 'Crohn', 'mucosa', 'intestinal', 'dysbiosis']
    }
}

def validate_terms(text: str, project_type: str, project_disease_terms: str = None) -> Dict:
    """
    验证文本中的术语是否与项目类型匹配

    参数:
        text: 要检查的文本内容
        project_type: 项目疾病类型（如'肾结石', '癌症'）
        project_disease_terms: 项目特定的正确术语列表（可选）

    返回:
        {
            'match': True/False,
            'mismatch_terms': [...],
            'mismatch_locations': [...],
            'severity': 'FATAL'/'SERIOUS'/'INFO'
        }
    """
    if project_type not in TERM_DATABASE:
        return {'error': f'未知项目类型: {project_type}'}

    project_terms = TERM_DATABASE[project_type]
    wrong_terms = project_terms['wrong']
    correct_terms = project_terms['correct']

    mismatches = []

    # 检查错误术语
    for wrong_term in wrong_terms:
        # 不区分大小写搜索
        pattern = re.compile(re.escape(wrong_term), re.IGNORECASE)
        matches = pattern.finditer(text)

        for match in matches:
            mismatches.append({
                'term': match.group(),
                'position': match.start(),
                'context': _get_context(text, match.start(), 50)
            })

    # 计算严重性
    if mismatches:
        # 如果使用了其他疾病的特征术语（如Tumor在肾结石项目），为FATAL
        if any(m['term'].lower() in ['tumor', 'normal', 'cancer'] for m in mismatches):
            severity = 'FATAL'
        else:
            severity = 'SERIOUS'
    else:
        severity = 'INFO'

    return {
        'match': len(mismatches) == 0,
        'mismatch_terms': [m['term'] for m in mismatches],
        'mismatch_positions': [m['position'] for m in mismatches],
        'mismatch_contexts': [m['context'] for m in mismatches],
        'severity': severity
    }

def _get_context(text: str, position: int, window: int = 50) -> str:
    """获取匹配位置的上下文"""
    start = max(0, position - window // 2)
    end = min(len(text), position + window // 2)
    return text[start:end]

# 使用示例
if __name__ == '__main__':
    code_file = 'CODE/r.00_Rawdata.r'
    project_type = '肾结石'

    with open(code_file, 'r', encoding='utf-8') as f:
        content = f.read()

    result = validate_terms(content, project_type)

    if result['match']:
        print("✅ 术语匹配检查通过")
    else:
        print(f"❌ 发现{len(result['mismatch_terms'])处术语不匹配")
        for i, term in enumerate(result['mismatch_terms'][:10]):
            print(f"  {i+1}. {term} (位置: {result['mismatch_positions'][i]})")
            print(f"     上下文: ...{result['mismatch_contexts'][i]}...")
        print(f"严重性: {result['severity']}")
```

### R脚本

```r
#!/usr/bin/env Rscript
# 术语主题匹配检测 (R版本)

library(stringr)

# 定义术语库
TERM_DATABASE <- list(
  `癌症` = list(
    correct = c("Tumor", "Normal", "Cancer"),
    wrong = c("Disease", "Control", "Randall"),  # 在癌症项目中不应使用
    keywords = c("Tumor", "Normal", "Cancer", "Malignant")
  ),
  `肾结石` = list(
    correct = c("Disease", "Control", "Randall", "plaque", "Kidney"),
    wrong = c("Tumor", "Normal", "Cancer", "Malignant"),  # 在肾结石项目中不应使用！
    keywords = c("Disease", "Control", "Randall", "plaque")
  ),
  `心血管` = list(
    correct = c("Cardiac", "Heart", "Case", "Control"),
    wrong = c("Tumor", "Normal", "Cancer"),
    keywords = c("Cardiac", "Heart", "Myocardial")
  )
)

validate_terms <- function(content, project_type) {
  # 获取项目术语配置
  if (!(project_type %in% names(TERM_DATABASE))) {
    return(list(error = paste("未知项目类型:", project_type)))
  }

  config <- TERM_DATABASE[[project_type]]
  wrong_terms <- config$wrong

  # 检测错误术语
  mismatches <- list()

  for (term in wrong_terms) {
    # 查找所有匹配
    matches <- str_locate_all(content, fixed(term), ignore_case = TRUE)

    if (length(matches) > 0) {
      mismatches[[term]] <- matches
    }
  }

  # 判断严重性
  if (length(mismatches) > 0) {
    # 检查是否包含癌症术语（最严重）
    has_cancer_terms <- any(names(mismatches) %in% c("Tumor", "Normal", "Cancer"))
    severity <- ifelse(has_cancer_terms, "FATAL", "SERIOUS")
  } else {
    severity <- "INFO"
  }

  return(list(
    match = length(mismatches) == 0,
    mismatch_terms = names(mismatches),
    mismatch_counts = sapply(mismatches, length),
    severity = severity
  )
}

# 使用示例
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("用法: Rscript term_check.R <file> <project_type>")
}

content <- readLines(args[1])
project_type <- args[2]

result <- validate_terms(content, project_type)

if (result$match) {
  cat("✅ 术语匹配检查通过\n")
} else {
  cat(sprintf("❌ 发现%d处术语不匹配\n", length(result$mismatch_terms)))
  for (term in names(result$mismatch_counts)) {
    cat(sprintf("  %s: %d处\n", term, result$mismatch_counts[[term]]))
  }
  cat(sprintf("严重性: %s\n", result$severity))
}
```

---

## 快速参考表

| 项目类型 | 正确分组术语 | 代码变量命名示例 |
|---------|-------------|----------------|
| 癌症 | Tumor/Normal | `group <- ifelse(sample == "Tumor", 1, 0)` |
| 肾结石 | Disease/Control | `group <- ifelse(sample == "Disease", 1, 0)` |
| 心血管 | Case/Control | `group <- ifelse(sample == "Case", 1, 0)` |
| 代谢 | Disease/Control | `group <- ifelse(sample == "Disease", 1, 0)` |
| 神经 | Disease/Control | `group <- ifelse(sample == "Disease", 1, 0)` |
| 免疫 | Disease/Control | `group <- ifelse(sample == "Disease", 1, 0)` |

---

## 检查清单

- [ ] 确认项目疾病类型
- [ ] 选择正确的术语库
- [ ] 运行术语匹配检测脚本
- [ ] 检查代码中的变量命名
- [ ] 检查注释中的术语使用
- [ ] 检查报告文档中的术语
- [ ] 验证样本分组术语一致性
- [ ] 记录所有不匹配术语的位置
- [ ] 评估严重性等级（FATAL/SERIOUS/INFO）

---

**文档版本**: v6.5
**最后更新**: 2026-02-13
**维护者**: Lead Auditor
