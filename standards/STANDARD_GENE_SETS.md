# 标准基因集库
> **用途**: 生物信息学项目审核时，快速验证常见基因集的数量和组成
>
> **创建日期**: 2026-02-13
> **最后更新**: 2026-03-20
> **基于项目**: 25YLC105F（M6A基因集数量验证）、26YHB202F（铁死亡/自噬口径）、26YTY013F（焦亡口径）

---

## 使用说明

> **重要说明**: 除 M6A 外，多数“细胞死亡/自噬”基因集不存在唯一全球统一数量。
> 审核时必须先确认报告使用的数据源，再按对应口径核对，不能把不同数据库的数量直接互相判错。

```python
# 使用示例
from STANDARD_GENE_SETS import GENE_SETS, validate_gene_set

# 验证M6A基因集
result = validate_gene_set('M6A', gene_list)
print(f"预期: {result['expected']}, 实际: {result['actual']}")
print(f"匹配: {result['match']}")
if not result['match']:
    print(f"缺失: {result['missing']}")
```

---

## M6A基因集（25个）

### 完整列表

| 分类 | 基因 | 数量 |
|-----|------|-----|
| **Writers (书写酶)** | METTL3, METTL14, METTL16, WTAP, VIRMA, ZC3H13 | 6 |
| **Erasers (擦除酶)** | FTO, ALKBH5 | 2 |
| **Readers (阅读器)** | YTHDC1, YTHDC2, YTHDF1, YTHDF2, YTHDF3,<br>HNRNPC, FMR1, LRPPRC, HNRNPA2B1, RBMX,<br>RBM15, RBM15B | 12 ⚠️ |
| **IGFBP family** | IGFBP1, IGFBP2, IGFBP3, IGFBP7 | 4 |
| **总计** | | **24** ⚠️ |

> ⚠️ **计数说明**: 此前 Readers 标注为 13、总计 25，但实际仅列出 12 个 Reader 基因（6+2+12+4=24）。
> 部分文献将 ELAVL1 (HuR) 列为第 13 个 Reader（此时总计恢复为 25）。
> 审核时请以项目引用的原始文献为准，不要假设固定数量。

### 基因功能说明

```
Writers (甲基转移酶):
  METTL3   - Methyltransferase like protein 3
  METTL14  - Methyltransferase like protein 14
  METTL16  - Methyltransferase like protein 16
  WTAP     - Wilms tumor 1-associating protein
  VIRMA    - Vir like m6A methyltransferase associated
  ZC3H13   - Zinc finger CCCH-type containing 13

Erasers (去甲基酶):
  FTO      - Fat mass and obesity-associated protein
  ALKBH5   - AlkB homolog 5, RNA demethylase

Readers (m6A识别蛋白):
  YTHDC1   - YTH domain containing 1
  YTHDC2   - YTH domain containing 2
  YTHDF1   - YTH N6-methyladenosine RNA binding protein 1
  YTHDF2   - YTH N6-methyladenosine RNA binding protein 2
  YTHDF3   - YTH N6-methyladenosine RNA binding protein 3
  HNRNPC   - Heterogeneous nuclear ribonucleoprotein C
  FMR1     - Fragile X mental retardation 1
  LRPPRC   - Leucine-rich pentatricopeptide repeat-containing protein
  HNRNPA2B1 - Heterogeneous nuclear ribonucleoprotein A2B1
  RBMX     - RNA binding motif protein, X-linked
  RBM15    - RNA binding motif protein 15
  RBM15B   - RNA binding motif protein 15B

IGFBP family (胰岛素样生长因子结合蛋白):
  IGFBP1   - Insulin-like growth factor binding protein 1
  IGFBP2   - Insulin-like growth factor binding protein 2
  IGFBP3   - Insulin-like growth factor binding protein 3
  IGFBP7   - Insulin-like growth factor binding protein 7
```

### 验证规则

```python
M6A_STANDARD = {
    'total_count': 24,  # ⚠️ 若含 ELAVL1 则为 25，以项目引用文献为准
    'categories': {
        'writers': {'count': 6, 'genes': ['METTL3', 'METTL14', 'METTL16', 'WTAP', 'VIRMA', 'ZC3H13']},
        'erasers': {'count': 2, 'genes': ['FTO', 'ALKBH5']},
        'readers': {'count': 12, 'genes': ['YTHDC1', 'YTHDC2', 'YTHDF1', 'YTHDF2', 'YTHDF3', 'HNRNPC', 'FMR1', 'LRPPRC', 'HNRNPA2B1', 'RBMX', 'RBM15', 'RBM15B']},  # ⚠️ 部分文献包含 ELAVL1 作为第 13 个 Reader
        'igfbp': {'count': 4, 'genes': ['IGFBP1', 'IGFBP2', 'IGFBP3', 'IGFBP7']}
    }
}

def validate_m6a_gene_set(gene_list):
    """
    验证M6A基因集

    参数:
        gene_list: 实际基因列表

    返回:
        {
            'match': True/False,
            'expected': 25,
            'actual': 实际数量,
            'missing': 缺失的基因列表,
            'extra': 多余的基因列表,
            'category_validation': 各分类验证结果
        }
    """
    gene_set = set(g.upper() for g in gene_list)

    # 检查总数
    actual_count = len(gene_set)
    match = (actual_count == M6A_STANDARD['total_count'])

    # 检查每个分类
    category_validation = {}
    for category, info in M6A_STANDARD['categories'].items():
        expected_genes = set(info['genes'])
        actual_genes = gene_set & expected_genes
        category_validation[category] = {
            'expected_count': info['count'],
            'actual_count': len(actual_genes),
            'match': len(actual_genes) == info['count'],
            'missing': list(expected_genes - actual_genes)
        }

    # 计算总体缺失
    all_expected = set()
    for info in M6A_STANDARD['categories'].values():
        all_expected.update(info['genes'])

    missing = list(all_expected - gene_set)
    extra = list(gene_set - all_expected)

    return {
        'match': match,
        'expected': M6A_STANDARD['total_count'],
        'actual': actual_count,
        'missing': missing,
        'extra': extra,
        'category_validation': category_validation
    }
```

### 常见错误

| 错误类型 | 描述 | 严重性 |
|---------|------|--------|
| 数量不足 | 实际24个，应为25个 | 🔴 严重 |
| 缺失核心基因 | 缺少FTO或ALKBH5 | 🔴 FATAL |
| 分类不完整 | 某分类基因数明显不足 | 🟡 严重 |
| 包含非标准基因 | 出现不在标准列表中的基因 | 🟢 轻微 |

---

## 铁死亡基因集（Ferroptosis）

> **审核口径A（数据库拉取）**: FerrDb V3 去重后约 **3481个**
> **审核口径B（富集分析）**: KEGG hsa04216 = **41个**
> **参考资料**: FerrDb V3, KEGG hsa04216

**核心审查基因**（12个）:
- GPX4
- AIFM2 (FSP1)
- SLC7A11
- ACSL4
- LPCAT3
- TFRC
- NCOA4
- FTH1
- FTL
- HMOX1
- SAT1
- NFE2L2

**审核建议**:
- 报告若写“FerrDb V3 铁死亡基因” → 应核对是否接近 3481 个
- 报告若写“KEGG Ferroptosis 通路” → 应核对 hsa04216 通路基因集是否为 41 个
- 不同来源数量不同，不能直接互判

---

## 铜死亡基因集（Cuproptosis）

> **审核口径**: Science 2022 经典 cuproptosis 核心基因 = **13个**
> **参考资料**: Tsvetkov P, et al. Science. 2022

**标准基因**（13个）:
- FDX1
- LIAS
- LIPT1
- DLD
- DLAT
- PDHA1
- PDHB
- MTF1
- GLS
- CDKN2A
- ATP7B
- SLC31A1
- DBT

---

## 凋亡基因集（Apoptosis）

> **审核口径A（富集分析）**: KEGG hsa04210 = **136个**
> **审核口径B（核心 marker）**: 常用核心凋亡基因 **15个**
> **参考资料**: KEGG hsa04210

**核心审查基因**（15个）:
- BAX
- BAK1
- BCL2
- BCL2L1
- BAD
- BID
- APAF1
- CASP3
- CASP6
- CASP8
- CASP9
- FAS
- FASLG
- TNFRSF10B
- CYCS

---

## 自噬基因集（Autophagy）

> **审核口径A（量化/并集）**: HADb 371个 + MSigDB GO_REGULATION_OF_AUTOPHAGY 377个，并集 **604个**
> **审核口径B（数据库原表）**: HADb = **371个**
> **参考资料**: HADb, MSigDB

**核心审查基因**（14个）:
- ULK1
- BECN1
- RB1CC1
- PIK3C3
- ATG3
- ATG5
- ATG7
- ATG12
- ATG16L1
- MAP1LC3B
- GABARAP
- SQSTM1
- WIPI1
- WIPI2

---

## 焦亡基因集（Pyroptosis）

> **审核口径A（审核基线）**: 多来源合并去重后常见焦亡基因集 = **76个**
> **审核口径B（富集分析）**: Reactome pyroptosis 核心通路 ≈ **26个**
> **参考资料**: Reactome R-HSA-5620971，已审核项目 26YTY013F

**核心审查基因**（14个）:
- AIM2
- NLRP1
- NLRP3
- PYCARD
- CASP1
- CASP4
- CASP5
- CASP8
- GSDMD
- GSDME
- IL1A
- IL1B
- IL18
- PLCG1

---

## 使用检查清单

- [ ] 确认基因集类型
- [ ] 查找标准数量
- [ ] 统计实际基因数量
- [ ] 验证核心基因是否存在
- [ ] 检查分类完整性
- [ ] 记录缺失/多余的基因
- [ ] 评估严重性等级

---

**文档版本**: v6.5
**最后更新**: 2026-03-20
**维护者**: Lead Auditor
