# 工作流程 — 模块检查详册

> 本文件从 [WORKFLOW.md](WORKFLOW.md) 提取，仅包含物种预检细则和逐模块检查详细流程。
> 核心工作流程见 [WORKFLOW.md](WORKFLOW.md)。

---

## 第零阶段：物种和质量预检（保留原有）

### 步骤0：基因集物种和质量验证

**为什么这是第一步？**
- 基因集物种错误会导致整个分析结果不可用
- 质量问题（如蛋白复合物、非标准命名）会影响结果可靠性
- 这类问题在分析前必须发现，否则浪费大量检查时间

**真实案例教训**：
- 项目25YYS110F使用小鼠基因集(mmc3.gmt)分析人类数据 → 整个免疫浸润模块不可用
- 项目25YYS110F基因集包含4个蛋白复合物基因 → 影响ERGs分析可靠性

#### 0.1 基因集物种验证 ⭐⭐⭐

**检查范围**：
- [ ] 所有原始数据文件（01_Rawdata/）
- [ ] 所有功能分析使用的.gmt文件
- [ ] 所有参考基因集
- [ ] 所有注释数据库

**检查方法**：

**方法1：文件名检查（快速筛选）**
```powershell
# 搜索所有.gmt文件
Get-ChildItem -Path "项目路径" -Filter "*.gmt" -Recurse

# 常见小鼠基因集标识
mmc3.gmt          # Mouse Microarray Cell Compendium 3
mouse*.gmt        # 任何带mouse的gmt文件
mm10_*.gmt        # 小鼠基因组版本mm10
```

**方法2：代码检查（定位使用位置）**
```powershell
# 搜索.gmt文件引用
Select-String -Path "CODE/*.R" -Pattern "\.gmt"

# 检查是否有可疑的小鼠基因集
Select-String -Path "CODE/*.R" -Pattern "mmc3|mouse|mm10"
```

**方法3：基因集文件检查（验证物种标签）**
```powershell
# 检查.gmt文件前几行
Get-Content "结果文件/path/to/file.gmt" -First 5

# 人类基因集示例：
# h.all.v2023.2.Hs.gmt    # Hs = Homo sapiens
# c2.cp.kegg.v2023.2.Hs.gmt
# xCell sigs are human

# 小鼠基因集示例：
# mmc3.gmt               # Mouse
# c2.cp.kegg.v2023.2.Mm.gmt  # Mm = Mus musculus
```

**物种匹配检查表**：

| 分析数据物种 | 基因集物种 | 结果 | 操作 |
|------------|-----------|------|------|
| 人类 (GSE*, H*) | 人类 (Hs, h.all) | ✅ 通过 | 无需操作 |
| 人类 (GSE*, H*) | 小鼠 (Mm, mmc3) | ❌ FATAL | 必须替换 |
| 小鼠 (GSE*M) | 小鼠 (Mm) | ✅ 通过 | 无需操作 |
| 小鼠 (GSE*M) | 人类 (Hs) | ❌ FATAL | 必须替换 |

**常见人类基因集**：
- MSigDB: `*.Hs.gmt` (Hs = Homo sapiens)
- xCell: `xCell_sig.txt` (人类)
- CIBERSORT: `LM22.txt` (人类)
- EPIC: `EPIC_sig.txt` (人类)

**常见小鼠基因集**：
- MSigDB: `*.Mm.gmt` (Mm = Mus musculus)
- mmc3.gmt (Mouse Microarray Cell Compendium)

#### 0.2 基因集质量检查

**检查项目**：

**1) 基因命名格式验证**
```python
# 检查基因名格式
# 人类标准基因名：大写字母，无符号，无数字前缀
# 例如：TP53, ABCB1, RORA

# 错误格式示例：
scf-fbxl5_human        # ❌ 蛋白复合物，包含下划线和连字符
bola3-glrx5_human      # ❌ 蛋白复合物
MT-ND1                 # ⚠️ 线粒体基因（需确认是否保留）
HLA-A                 # ⚠️ HLA基因（需确认是否保留）
IGKV1D-43             # ⚠️ 免疫球蛋白（需确认是否保留）
LINC00152             # ⚠️ lncRNA（需确认是否应该分析）
```

**2) 蛋白复合物基因检测**
```python
# 使用Python检查
import pandas as pd

df = pd.read_csv('final_ERGs.csv')

# 检测蛋白复合物（包含连字符和下划线）
protein_complexes = df[df['gene_name'].str.contains('-', regex=True) & 
                        df['gene_name'].str.contains('_', regex=True)]

print(f"发现 {len(protein_complexes)} 个蛋白复合物基因")
print(protein_complexes)
```

**3) 非标准基因名分类统计**
```python
# 分类统计
categories = {
    'protein_complex': df['gene_name'].str.contains('-', regex=True) & df['gene_name'].str.contains('_', regex=True),
    'mitochondrial': df['gene_name'].str.startswith('MT-'),
    'hla': df['gene_name'].str.startswith('HLA-'),
    'immunoglobulin': df['gene_name'].str.startswith('IG'),
    'lncrna': df['gene_name'].str.startswith('LINC') | df['gene_name'].str.startswith('MIR')
}

for category, mask in categories.items():
    count = mask.sum()
    if count > 0:
        print(f"{category}: {count} 个")
        print(df[mask]['gene_name'].tolist()[:10])  # 显示前10个
```

**质量检查记录表**：

| 检查项 | 结果 | 数量 | 处理建议 |
|-------|------|------|---------|
| 总基因数 | ______ | - | 基准数量 |
| 标准基因名 | ✅/❌ | ______ | 应占绝大多数 |
| 蛋白复合物 | ❌ | ______ | **必须删除** |
| 线粒体基因 | ⚠️ | ______ | 确认是否保留 |
| HLA基因 | ⚠️ | ______ | 确认是否保留 |
| 免疫球蛋白 | ⚠️ | ______ | 确认是否保留 |
| lncRNA | ⚠️ | ______ | 确认是否应该分析 |

#### 0.3 参考数据库物种验证

**检查项目**：
- [ ] 基因组注释文件（如GTEx, Ensembl）
- [ ] 通路数据库（KEGG, Reactome）
- [ ] 蛋白互作数据库（STRING, BioGRID）
- [ ] 转录因子数据库（TRRUST, DoRothEA）

**检查命令**：
```powershell
# 搜索数据库引用
Select-String -Path "CODE/*.R" -Pattern "GTEx|Ensembl|KEGG|Reactome|STRING"

# 检查数据集编号（GSE开头通常是人类）
Select-String -Path "CODE/*.R" -Pattern "GSE[0-9]"
```

**数据集物种判断**：
- GSE* (无M后缀) → 通常是人类数据
- GSE*M (有M后缀) → 可能是小鼠数据
- 需要结合GEO数据库确认

#### 0.4 记录和报告

**记录格式**：
```markdown
### Step 0: 物种和质量预检结果

#### 物种验证
- [ ] 分析数据物种: 人类/小鼠/大鼠
- [ ] 基因集物种: 人类/小鼠/大鼠
- [ ] 物种匹配: ✅/❌

#### 质量检查
- 基因集总数: ______
- 蛋白复合物: ______ (必须删除)
- 非标准基因名: ______ (需验证)

#### 发现的问题
1. 
2. 
3. 

#### 处理建议
- [ ] FATAL: 物种不匹配，必须替换基因集
- [ ] FATAL: 包含蛋白复合物，必须删除
- [ ] WARNING: 包含大量非标准基因名，需确认
```

**如果发现问题**：
- 🔴 **FATAL级别**：物种不匹配 → **停止后续检查，建议重新分析**
- 🔴 **FATAL级别**：包含蛋白复合物 → **建议修正基因集**
- ⚠️ **WARNING级别**：非标准基因名过多 → **需确认分析目的**

**检查完成标准**：
- ✅ 所有基因集物种与分析数据匹配
- ✅ 基因集无蛋白复合物错误命名
- ✅ 非标准基因名已验证并确认合理性

**时间投入**：约10-15分钟
**价值**：避免数小时的无效检查 + 发现FATAL问题

---


---

## 第二阶段：逐模块详细检查（核心）⭐ 重要更新！

### ⭐⭐⭐ 数字验证优先级表（最重要！）

**来自26YTY013F项目的教训**: DEG数量错误442%导致审核不合格

**P0级数字（必须验证，错误即不合格）**:
| 数字项 | 报告位置 | 验证文件 | 验证方法 |
|--------|----------|----------|----------|
| DEG总数 | 差异分析章节 | `results/02_DeAnalysis/DEGs sig.csv` | `len(df)` |
| 上调基因数 | 同上 | 同上 | `sum(df['Regulated']=='up')` |
| 下调基因数 | 同上 | 同上 | `sum(df['Regulated']=='down')` |
| logFC阈值 | 方法章节 | 代码/文件名 | `abs(logFC) > threshold` |
| 基因集总数 | 数据来源 | `results/00_rawdata/` | 去重统计 |

**P1级数字（重要验证）**:
| 数字项 | 验证文件 | 验证方法 |
|--------|----------|----------|
| WGCNA模块基因数 | `results/04_WGCNA/moduleGene/*.txt` | 统计各模块 |
| ML筛选结果数 | `results/07_ML/*.txt` | 逐个文件统计 |
| 交集基因数 | `results/04_WGCNA/Module*.csv` | `len(df)` |
| 富集通路数 | `results/05_Enrichment_Analysis/` | 结果文件统计 |

**数字验证流程**:
```python
# Step 1: 从报告中提取数字
# Step 2: 定位对应文件
# Step 3: 用代码统计（不要人工数！）
# Step 4: 对比差异
# Step 5: 差异>5%记录，>20%标记严重问题
```

**Python验证示例**:
```python
import pandas as pd

# DEG验证
deg = pd.read_csv('results/02_DeAnalysis/DEGs sig.csv')
print(f"DEG总数: {len(deg)}")
print(f"上调: {sum(deg['Regulated']=='up')}")
print(f"下调: {sum(deg['Regulated']=='down')}")

# 基因集验证
import glob
pyro_genes = set()
for f in glob.glob('results/00_rawdata/**/*.csv'):
    df = pd.read_csv(f)
    pyro_genes.update(df.iloc[:, 0].dropna().tolist())
print(f"细胞焦亡基因: {len(pyro_genes)}")
```

---

### ⭐ 检查策略：逐模块验证

```
对于每个分析模块（01_Rawdata → 02_DEG → 03_WGCNA ...）：

┌─────────────────────────────────────┐
│ 模块X检查流程                        │
├─────────────────────────────────────┤
│ 1. 报告描述记录                      │
│    - 记录报告中对模块X的描述         │
│    - 记录关键数字（输入/输出）       │
│    - 记录方法描述                    │
│                                      │
│ 2. 结果文件验证                      │
│    - 找到模块X的结果文件             │
│    - 统计实际数字                    │
│    - 与报告描述对比                  │
│    - 记录：一致/不一致               │
│                                      │
│ 3. 代码实现验证                      │
│    - 找到模块X的代码文件             │
│    - 理解分析逻辑                    │
│    - 检查参数设置                    │
│    - 确认：描述错了？结果错了？都对？│
│                                      │
│ 4. 问题判断                          │
│    - 如果不一致：                    │
│      ✓ 报告描述错误 → 报告问题       │
│      ✓ 结果文件错误 → 分析问题       │
│      ✓ 代码实现错误 → 代码问题       │
│      ✓ 都没错但不同 → 说明差异原因   │
│                                      │
│ 5. 记录检查结果                      │
│    - 模块状态：✅/⚠️/❌              │
│    - 发现的问题列表                  │
│    - 问题定位（报告/文件/代码）       │
└─────────────────────────────────────┘

然后进入下一个模块...
```

---

### 步骤4：逐模块详细检查

#### 🔍 模块检查示例：01_Rawdata

**第一步：记录报告描述**
```markdown
### 01_Rawdata 模块检查

报告描述：
- ERGs（必需微量元素代谢相关基因）数量：XXX个
- 数据来源：XXX数据库/文献
- 文件名：final_ERGs.csv
```

**第二步：验证结果文件**
```powershell
# 检查文件
ls 结果文件/01_Rawdata/

# 统计实际数量
$ergs = Import-Csv "结果文件/01_Rawdata/final_ERGs.csv"
Write-Host "实际ERGs数量: $($ergs.Count)"
```

```markdown
结果文件验证：
- ✅ 文件存在：final_ERGs.csv
- 实际数量：XXX个基因
- 与报告对比：✅一致 / ❌不一致
```

**第三步：验证代码实现**
```r
# 查看 CODE/01_Rawdata_GSE117261.R
# 理解：
# 1. 数据是如何加载的？
# 2. 是否有筛选？
# 3. 参数设置是什么？
```

```markdown
代码验证：
- 代码文件：01_Rawdata_GSE117261.R
- 分析逻辑：[描述]
- 参数设置：[记录关键参数]
- 与报告一致性：✅ / ⚠️ / ❌
```

**第四步：问题判断**

如果发现不一致：
```markdown
### 问题诊断

⚠️ 重要：必须包含完整的文件路径！

发现不一致：
- 报告说：XXX个基因
- 实际文件：YYY个基因
- 文件路径：[项目根目录]/结果文件/子目录/具体文件.csv

可能原因分析：
1. 报告描述错误？
   - 检查报告其他章节是否有矛盾描述
   - 检查是否有笔误

2. 结果文件错误？
   - 检查代码执行时间
   - 检查是否有中间步骤遗漏
   - 确认是否读取了正确的文件

3. 代码实现错误？
   - 检查筛选逻辑
   - 检查参数设置
   - 定位具体代码行号

4. 描述不清晰？
   - 可能"XXX个"指筛选前的数量
   - 可能YYY个是去重后的数量

文件路径格式要求：
- ✅ 正确：`26YTY013F-数据分析结果/results/02_DeAnalysis/DEGs sig.csv`
- ✅ 正确：`results/02_DeAnalysis/DEGs sig.csv` (在明确项目上下文时)
- ❌ 错误：`DEGs sig.csv` (不完整)
- ❌ 错误：只写"结果文件" (无路径)

结论：[具体判断]
```

**第五步：记录结果**
```markdown
### 01_Rawdata 检查结果

状态：✅ 通过 / ⚠️ 警告 / ❌ 错误

问题列表：
- [ ] 无问题
- [ ] 问题1：...
- [ ] 问题2：...

问题定位：
- 📄 报告问题：是/否
- 📊 结果文件问题：是/否
- 💻 代码问题：是/否

备注：[其他说明]
```

---

#### 🔍 模块检查示例：02_DEG

**第一步：记录报告描述**
```markdown
### 02_DEG 模块检查

报告描述：
- 数据集：GSE117261
- DEG总数：415个
  - 上调：222个
  - 下调：193个
- 阈值：|log2FC| > 0.5, adj.P.Val < 0.05
- 参考基因组：XXX
```

**第二步：验证结果文件**
```powershell
# 检查文件
ls 结果文件/04_DEG_GSE117261/

# 统计实际数量
$deg = Import-Csv "结果文件/04_DEG_GSE117261/DEG_logFC0.5.csv"
$up = ($deg | Where-Object { $_.logFC -gt 0 }).Count
$down = ($deg | Where-Object { $_.logFC -lt 0 }).Count
Write-Host "上调: $up, 下调: $down, 总计: $($deg.Count)"
```

```markdown
结果文件验证：
- ✅ 文件存在：DEG_logFC0.5.csv
- 实际数量：
  - 总计：415个 ✅
  - 上调：222个 ✅
  - 下调：193个 ✅
- 阈值验证：[检查logFC和P.Value列]
- 与报告对比：✅完全一致
```

**第三步：验证代码实现** ⭐⭐⭐ **关键新增：代码-报告参数一致性检查！**

```r
# 查看 CODE/02_DEG_GSE117261.R
library(limma)
# 关键参数：
logFC_cutoff <- 0.5
fdr_cutoff <- 0.05
# 分析逻辑：标准的limma流程
```

**⚠️ 关键检查：代码参数必须与报告描述一致！**

来自26YTY013F项目的教训：
- **报告声称**: logFC阈值 = 1
- **代码实际**: foldChange = 0.5
- **结果**: DEG数量差异443%（报告548个 vs 实际2977个）

**代码-报告一致性检查清单**:
| 参数类型 | 报告描述 | 代码实际 | 一致性 |
|---------|---------|---------|--------|
| logFC阈值 | 1 | 0.5 | ❌ 不一致！ |
| p-value阈值 | 0.05 | 0.05 | ✅ 一致 |
| 筛选方向 | abs(logFC) > threshold | abs(logFC) > foldChange | ✅ 一致 |

**检查方法**:
```python
# Step 1: 从报告中提取参数描述
# Step 2: 在代码中搜索对应参数
# Step 3: 逐一对比验证
# Step 4: 发现不一致立即记录

# 示例：检查logFC阈值
import re

# 从报告提取："logFC阈值设置为1"
report_threshold = 1

# 从代码提取：foldChange = 0.5
with open('scripts/r.02_DeAnalysis.R', 'r') as f:
    content = f.read()
    match = re.search(r'foldChange\s*=\s*([\d.]+)', content)
    if match:
        code_threshold = float(match.group(1))
        if abs(code_threshold - report_threshold) > 0.01:
            print(f"❌ 严重问题：代码阈值({code_threshold}) != 报告阈值({report_threshold})")
```

```markdown
代码验证：
- ✅ 代码文件：02_DEG_GSE117261.R
- ✅ 分析逻辑：标准limma差异分析
- ⚠️ 参数设置：logFC>0.5（代码） vs logFC>1（报告）→ **不一致！**
- ❌ 与报告不一致：参数不匹配
```

**第四步：问题判断**
```markdown
### 问题诊断

🔴 发现严重不一致：
- 报告说：logFC阈值=1，应得到约548个DEG
- 代码用：foldChange=0.5，实际得到2977个DEG
- 结果文件：2977个DEG（与代码一致）
- **结论**：报告描述错误，代码实际执行正确
- **影响**：报告与代码执行脱节，严重影响可信度
```

**第五步：记录结果**
```markdown
### 02_DEG 检查结果

状态：✅ 完全通过

问题列表：
- [x] 无问题

问题定位：
- 📄 报告问题：否
- 📊 结果文件问题：否
- 💻 代码问题：否

备注：分析流程标准，结果准确
```

---

#### 🔍 模块检查示例：08_Machine（机器学习）

**第一步：记录报告描述**
```markdown
### 08_Machine 模块检查

报告描述：
- 候选基因：11个（来自DEG∩WGCNA∩scPagwas∩ERGs）
- LASSO筛选：9个基因
- SVM筛选：10个基因
- RF筛选：前10个基因（按重要性）
- 三方交集：9个基因
- 验证后：2个基因（ABCB1, RORA）
```

**第二步：验证结果文件**
```powershell
# 逐个文件验证
$lasso = Import-Csv "结果文件/08_Machine/01_PAH_lasso_genes.csv"
$svm = Import-Csv "结果文件/08_Machine/04_PAH_svm_gene.csv"
$rf = Import-Csv "结果文件/08_Machine/08_PAH_RF_features_top10.csv"
$intersection = Import-Csv "结果文件/08_Machine/10_PAH_common_genes.csv"
$final = Import-Csv "结果文件/11_Nomo/01_final_key_gene.csv"

Write-Host "LASSO: $($lasso.Count)"
Write-Host "SVM: $($svm.Count)"
Write-Host "RF前10: $($rf.Count)"
Write-Host "三方交集: $($intersection.Count)"
Write-Host "最终: $($final.Count)"
```

```markdown
结果文件验证：
- ✅ LASSO：9个基因
- ✅ SVM：10个基因
- ✅ RF前10：10个基因
- ✅ 三方交集：9个基因
- ✅ 最终基因：2个基因
- 与报告对比：✅完全一致
```

**第三步：验证代码实现**
```r
# 查看 CODE/09_Machine_GSE117261.R
# LASSO
lasso_model <- cv.glmnet(x, y, alpha=1)  # alpha=1表示LASSO
# 提取非零系数基因
lasso_genes <- rownames(coef(lasso_model))[coef(lasso_model)!=0]

# SVM
svm_model <- svm(x, y, cost=best_cost)
# 提取最优准确率对应的基因

# RF
rf_model <- randomForest(x, y, importance=TRUE)
rf_importance <- importance(rf_model)
# ⚠️ 关键：取前10个
rf_top10 <- head(rf_importance, 10)
```

```markdown
代码验证：
- ✅ RF实现：top=10（与报告"前10个"一致）
- ✅ 三方交集逻辑正确
- ✅ 表达验证：训练集+验证集独立检验
```

**第四步：问题判断**
```markdown
### 问题诊断

⚠️ 初步疑问：为什么11→9→2？

代码分析：
1. 11个候选基因 → ML筛选
2. RF取前10，GZMA排第11被排除 ✅
3. 三方交集自然排除 ✅
4. 表达验证进一步筛选到2个 ✅

✅ 结论：流程完全合理，每步筛选有明确依据
```

**第五步：记录结果**
```markdown
### 08_Machine 检查结果

状态：✅ 完全通过

问题列表：
- [x] 无问题（初始误解已澄清）

问题定位：
- 📄 报告问题：否
- 📊 结果文件问题：否
- 💻 代码问题：否

备注：
- 报告描述清晰准确
- RF"前10个"策略正确
- 表达验证逻辑严谨
- 结果可追溯性强
```

---

### ⭐ 问题诊断决策树

```
发现报告描述与结果文件不一致
         │
         ▼
    ┌──────────────┐
    │ 检查代码实现 │
    └──────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
 代码与     代码与
 报告一致   结果一致
    │         │
    ▼         ▼
 📄报告问题  📊结果问题
            │
            ▼
      检查代码逻辑
            │
      ┌─────┴─────┐
      │           │
      ▼           ▼
   逻辑正确    逻辑错误
      │           │
      ▼           ▼
   📊结果问题  💻代码问题
```

---

### 步骤5：所有模块检查汇总

```markdown
## 模块检查汇总表

| 模块 | 报告 | 结果 | 代码 | 状态 | 问题 |
|------|------|------|------|------|------|
| 01_Rawdata | ✅ | ✅ | ✅ | ✅ | 无 |
| 02_DEG | ✅ | ✅ | ✅ | ✅ | 无 |
| 03_WGCNA | ✅ | ⚠️ | ✅ | ⚠️ | 数量略差 |
| 08_Machine | ✅ | ✅ | ✅ | ✅ | 无 |
| ... | ... | ... | ... | ... | ... |

总体统计：
- 完全通过：X个
- 有警告：Y个
- 有错误：Z个
```

---

