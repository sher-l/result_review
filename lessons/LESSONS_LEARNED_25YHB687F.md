# 项目25YHB687F审核经验总结

> **审核日期**: 2026-02-11
> **项目**: 25YHB687F - 糖尿病心肌病+O糖基化、外泌体+巨噬细胞-成纤维细胞的互作
> **审核框架**: Agent Team v3.0 + WORKFLOW.md v2.3

---

## 📌 核心发现

### 1. FATAL问题：物种混淆（代码与结果不一致）

**问题描述**：
- 单细胞数据 GSE290932 是小鼠数据（Nature Communications 2025）
- 富集分析代码使用人类注释包 `org.Hs.eg.db` 和 `organism="hsa"`
- 但实际结果文件使用小鼠注释（mmu前缀）

**关键证据**：
```r
# r.02_integrated.r:654
library(org.Hs.eg.db) # 人类注释包，如果是小鼠请换成 org.Mm.eg.db
# ↑ 注释说明开发者知道这是小鼠数据，但仍用人类注释

# r.02_integrated.r:755
organism = "hsa"  # ❌ 应该是 "mmu"

# 但实际结果文件:
# KEGG_FIB.csv: mmu04510, mmu04144... (小鼠前缀)
# key_gene.csv: Adam17, Cd55, Rtn4... (首字母大写，小鼠格式)
```

**教训**：
> ✅ **Step 0物种验证是最关键的一步**
>
> 这个问题在第一步就被发现了，避免了数小时的无效检查。
> 如果没有Step 0，可能在检查其他模块后才意识到基础数据有问题。

---

### 2. FATAL问题：Word报告模板残留

**问题描述**：
- 报告中出现 "M6A" 术语（应该是 "O-GlcNAcylation"）
- 出现 "视锥细胞"（视网膜细胞，与心肌病无关）
- 出现 "增殖细胞"（语境可疑）

**证据**：
```
"Figure 5 high-M6A组细胞通讯分析"  ← 应该是 high-O-GlcNAcylation
"Figure 6 low-M6A差异图"           ← 应该是 low-O-GlcNAcylation
```

**教训**：
> ✅ **系统性文本搜索比抽样检查更有效**
>
> 使用Python提取Word报告全文并统计术语频率，比人工浏览更准确。
> 特别是检测模板残留问题时，系统性搜索不会遗漏。

---

### 3. 关键发现：数字验证的重要性

**验证数据**：
- 成纤维细胞GO: 4,033条
- 巨噬细胞GO: 3,686条
- 成纤维细胞KEGG: 146条（全部mmu前缀）
- 巨噬细胞KEGG: 174条（全部mmu前缀）
- CellChat: Mac→Fib 6对, Fib→Mac 19对
- 关键基因: 6个

**教训**：
> ✅ **数字验证必须使用代码统计，不能人工估算**
>
> 使用Python pandas直接读取CSV文件统计，比人工数数准确100倍。
> 特别是大文件（几千条数据），人工统计几乎不可能准确。

---

## 🎯 审核框架优化建议

### 建议1: 增强Step 0物种验证

**当前流程**：
```
Step 0: 物种和质量预检
- 检查.gmt文件物种
- 检查基因集质量
```

**优化后**：
```
Step 0: 物种和质量预检（增强版）
- [ ] 数据集物种验证（GEO数据库查询）
- [ ] 代码注释包验证（org.Hs.eg.db vs org.Mm.eg.db）
- [ ] KEGG organism参数验证（hsa vs mmu）
- [ ] 基因命名格式验证（大写 vs 首字母大写）
- [ ] 结果文件物种前缀验证（mmu vs hsa）
- [ ] 交叉验证：代码 vs 结果的一致性
```

**新增检查项**：
```python
# 新增：代码与结果物种一致性检查
def check_species_consistency(project_path):
    """
    检查代码中的物种注释是否与结果文件一致
    """
    # 1. 扫描代码中的org.XX.eg.db引用
    code_species = scan_code_annot_packages(project_path)

    # 2. 扫描结果文件中的通路ID前缀
    result_species = scan_result_kegg_prefix(project_path)

    # 3. 对比
    if code_species != result_species:
        return {
            "status": "FATAL",
            "issue": "代码使用%s注释，但结果使用%s前缀" % (code_species, result_species),
            "code_evidence": code_species,
            "result_evidence": result_species
        }
```

---

### 建议2: Word报告检查自动化

**当前流程**：
```
手工浏览Word报告，查找问题
```

**优化后**：
```python
# 自动化Word报告检查工具
class WordReportChecker:
    def check_template_residues(self, docx_path):
        """检查模板残留"""
        wrong_terms = {
            "M6A": "O-GlcNAcylation",
            "m6A": "O-GlcNAcylation",
            "视锥细胞": "巨噬细胞/成纤维细胞",
            # ... 更多模板术语
        }
        return self._search_and_count(docx_path, wrong_terms)

    def check_disease_names(self, docx_path, project_disease):
        """检查疾病名称一致性"""
        # 统计正确和错误的疾病名称
        pass

    def check_dataset_consistency(self, docx_path, code_gses):
        """检查GSE编号一致性"""
        # 报告中的GSE vs 代码中的GSE
        pass
```

---

### 建议3: 数字验证自动化模板

**当前流程**：
```
手动读取CSV文件，人工统计
```

**优化后**：
```python
# 数字验证自动化模板
class DataVerificationTemplate:
    def verify_deg_counts(self, deg_csv_path):
        """验证DEG数量"""
        df = pd.read_csv(deg_csv_path)
        return {
            "total": len(df),
            "up": sum(df['logFC'] > 0),
            "down": sum(df['logFC'] < 0),
            "significant": sum(df['p.adjust'] < 0.05)
        }

    def verify_kegg_species(self, kegg_csv_path):
        """验证KEGG物种前缀"""
        df = pd.read_csv(kegg_csv_path)
        prefixes = df['ID'].str[:3].value_counts().to_dict()
        return prefixes  # {'mmu': 146, 'hsa': 0}

    def verify_gene_format(self, gene_list):
        """验证基因命名格式"""
        # 检测是人类（全大写）还是小鼠（首字母大写）
        pass
```

---

## 📋 本次审核的框架改进

### 已实施的改进

1. **Step 0物种预检增强**
   - 新增GEO数据集验证
   - 新增KEGG organism参数检查
   - 新增代码与结果一致性验证

2. **系统性文本搜索**
   - 使用Python提取Word报告全文
   - 统计术语频率
   - 定位模板残留位置

3. **数字验证自动化**
   - 使用pandas读取CSV统计
   - 验证物种前缀（mmu vs hsa）
   - 验证基因命名格式

### 待实施的改进

1. **Agent Team结果收集**
   - agents未保存JSON输出到指定路径
   - 需要完善agent output收集机制

2. **报告生成自动化**
   - 需要一个模板引擎自动生成HTML报告
   - 避免手动拼接HTML

3. **问题严重性自动评级**
   - 基于规则自动判断FATAL/HIGH/MEDIUM/LOW
   - 减少人工判断的主观性

---

## 🔧 框架文件需要更新的位置

### WORKFLOW.md
- [ ] 增强Step 0的检查项（新增代码与结果一致性验证）
- [ ] 新增Word报告自动化检查流程
- [ ] 新增数字验证自动化模板

### AGENT_TEAM_PLAN_v3.md
- [ ] 明确agent输出文件路径规范
- [ ] 新增agent output收集机制

### CHECKLIST_TEMPLATE.md
- [ ] 新增"代码与结果一致性验证"检查项
- [ ] 新增"Word报告模板残留"系统性搜索检查项

---

## ✅ 本次审核成功经验

### 1. 严格遵循框架流程
```
Step 0 → Round 1 → Meeting 1 → Round 2 → Meeting 2 → Round 3 → Meeting 3
```
每一步都有明确的目标，避免了遗漏。

### 2. 物种验证放在第一步
这是最正确的决策，避免了在错误的假设上进行后续检查。

### 3. 数据验证使用代码统计
比人工统计准确、快速、可追溯。

### 4. 系统性文本搜索
比抽样检查更全面，不会遗漏模板残留。

---

## 📝 审核统计数据

| 指标 | 数值 |
|-----|------|
| 总审核时间 | ~2小时 |
| 发现问题数 | 42个 |
| FATAL问题 | 7个 |
| 代码文件检查 | 7个 |
| 结果文件验证 | 15个 |
| Word报告段落检查 | 100+ |

---

**更新日期**: 2026-02-11
**维护者**: Claude Code Agent Team
