# 25YLC105F 项目审核经验总结（v3.2更新版）

**审核日期**: 2026-02-13
**项目类型**: 多组学（普通转录、单细胞、空转）数据研究肾结石兰德尔斑块与M6A和细胞死亡
**框架版本**: v3.1 → v3.2
**审核人员**: Lead Auditor

---

## 一、审核概述

本次审核通过Agent Team v3.1框架执行，发现了多个新的问题类型，推动框架升级到v3.2。

### 初次审核失败原因

| 问题 | 影响 |
|------|------|
| 未使用Agent Team v3.1 | 审核不全面 |
| 未系统性检查报告文本 | 遗漏细胞类型命名错误 |
| 未验证基因名称大小写一致性 | 遗漏专业术语错误 |
| 未深入验证三方交集逻辑 | 遗漏CLU基因被排除问题 |
| 用户指出问题后才补充审核 | 被动响应，主动发现能力差 |

---

## 二、v3.2框架新增问题类型（25YLC105F项目）

基于25YLC105F项目的审核，发现以下新问题类型，已整合到v3.2框架：

### 问题类型 #001: 项目编号系统性错误（FATAL级）⭐⭐⭐

**描述**: 所有代码文件中使用统一错误的项目编号

**发现位置**:
- 所有14个R代码文件第3行左右
- `setwd("~/06_25YLC135F/")` 应为 `setwd("~/06_25YLC105F/")`

**影响**:
- 🔴 代码完全无法复现
- 🔴 所有路径指向错误的项目文件夹

**检测方法**:
```bash
grep -rn "25YLC" CODE/
```

**首次在框架中记录**: 是

---

### 问题类型 #002: 术语与主题严重不符（FATAL级）⭐⭐⭐

**描述**: 肾结石研究项目使用癌症研究术语

**发现位置**: `CODE/r.00_Rawdata.r:147`

**错误代码**:
```r
# 如果包含，就标记为 "Tumor"；否则，标记为 "Normal"
```

**正确术语**: `Disease`/`Control` 或 `Randall's plaque`/`Healthy`

**术语主题匹配库**:
| 疾病类型 | 正确术语 | 错误术语 |
|----------|----------|----------|
| 癌症 | Tumor, Normal | - |
| 肾结石 | Disease, Control | Tumor, Normal ❌ |

**首次在框架中记录**: 是

---

### 问题类型 #003: M6A基因集数量差异（严重级）⭐⭐

**描述**: 标准M6A基因集应为25个，实际只有24个

**预期**: 25个（6 Writers + 2 Erasers + 13 Readers + 4 IGFBP）

**实际**: 24个基因

**可能缺失**: RBM15, RBM15B, 或 IGFBP7

**首次在框架中记录**: 是

---

### 问题类型 #004: 可视化阈值不一致（严重级）⭐

**描述**: 火山图阈值线与筛选标准不一致

**代码位置**: `r.01_limma.r`
- 第47行: `logFC_cutoff <- 0.5` (筛选标准)
- 第95行: `geom_vline(xintercept = c(-1,1))` (绘图阈值)

**影响**: 图表与实际筛选不符，误导读者

**首次在框架中记录**: 是

---

### 问题类型 #005: 跨模块数据流断裂（FATAL级）⭐⭐⭐

**描述**: monocle分析只用3个基因，而上游交集有19个

**代码位置**: `r.11_monocle.r:18`
```r
features <- c("PTGS1", "FHIT", "AR")  # 只有3个！
```

**交集结果**: 19个基因（PTGS1, CLU, GLS, ..., FHIT, AR）

**影响**: 数据流断裂，monocle结果与交集不对应

**检测方法**: 验证下游输入 = 上游输出

**首次在框架中记录**: 是

---

### 问题类型 #006: 方法命名不一致（严重级）⭐

**描述**: 使用DESeq2方法但描述为limma

**代码位置**: `r.01_limma.r:208`, `r.09_GSEA.r:9`
```r
library(DESeq2)  # 但文件夹名为limma
```

**影响**: 方法描述不准确

**首次在框架中记录**: 是

---

## 三、v3.2框架核心改进

### 1. 新增FATAL级检查（最高优先级）

| 检查项 | 检测方法 | 说明 |
|---------|----------|------|
| 项目编号一致性 | grep搜索项目编号 | 代码与文件夹名必须匹配 |
| 术语主题匹配 | 术语库验证 | 不能使用其他疾病类型术语 |
| 跨模块数据流 | 验证输入=输出 | 数据流完整性 |
| 物种匹配 | .gmt文件验证 | 人类数据不能用小鼠基因集 |

### 2. 建立标准基因集库

**M6A基因集（25个标准）**:
```
Writers: METTL3, METTL14, METTL16, WTAP, VIRMA, ZC3H13 (6个)
Erasers: FTO, ALKBH5 (2个)
Readers: YTHDC1, YTHDC2, YTHDF1, YTHDF2, YTHDF3,
          HNRNPC, FMR1, LRPPRC, HNRNPA2B1, RBMX, RBM15, RBM15B (13个)
IGFBP: IGFBP1, IGFBP2, IGFBP3, IGFBP7 (4个)
```

### 3. 自动化验证脚本

```python
def verify_project_integrity(project_code, project_type, code_dir):
    """v3.2综合验证"""
    # 1. 项目编号一致性
    id_errors = check_project_id_consistency(project_code, code_dir)

    # 2. 术语主题匹配
    term_errors = check_term_consistency(project_type, code_dir)

    # 3. 基因集数量验证
    gene_set_errors = validate_gene_sets(code_dir)

    # 4. 数据流验证
    flow_errors = validate_data_flow(code_dir)

    return combine_all_errors(id_errors, term_errors, gene_set_errors, flow_errors)
```

---


---

> v3.1 及之前的旧问题类型已移至 `archive/old_docs/25YLC105F_legacy_issues.md`。
