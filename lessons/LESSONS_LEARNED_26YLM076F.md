# 26YLM076F 经验教训 — 标准生信项目审核

> **项目编号**: 26YLM076F
> **项目类型**: 癌症生信（DEGs + WGCNA + GOKEGG + ML + Nomogram）
> **审核日期**: 2026-03-25
> **发现级别**: 🔴 CRITICAL（跨项目数据集编号 + 覆盖缺失 + 代码不可复现）

---

## 1. 核心发现

### 1.1 数据来源段跨项目模板残留（CRITICAL）

- 1.1 段前半正确写 GSE49972、GSE73209
- 后半却写"分别对 GSE43292、GSE100927 和 GSE28829 进行预处理"
- 这 3 个数据集完全不属于本项目

**检测方法**: 提取报告中所有 GSE 编号 `GSE\d+`，与 01_Rawdata/ 目录中的实际文件名交叉验证。

**根因**: 分析师从动脉粥样硬化（AS）项目模板复制了数据预处理段。

### 1.2 核心模块覆盖缺失（CRITICAL）

- 结果目录存在 06_Nomogram 完整图件（列线图、ROC、DCA、校准曲线）
- 但正文完全没有对应章节
- 这是"有结果无报告"类型的覆盖缺失

**新规则**: 覆盖矩阵建立时，必须以**结果目录**为基准逐目录检查正文对应段落，而非仅以正文为基准检查结果。

### 1.3 代码硬编码绝对路径（CRITICAL）

- 所有 6 个 R 脚本使用 `setwd("/media/desk16/iyunzjx/project/11.26YLM076F/")`
- 这是 Linux 绝对路径，用户无法在 Windows 环境复跑

**补充说明**: 此问题在当前框架 check_data_flow 检查器中已部分覆盖（搜索绝对路径），但严重性界定可强化为 CRITICAL。

### 1.4 WGCNA 方法与代码不一致（MAJOR）

- 报告写"剔除了最小 MAD 的前 50% 基因"
- 代码实际保留 MAD 最大的前 50%（`top50Percent <- order(datExpr.mad, decreasing=TRUE)[1:nTop]`）
- 意思完全相反

**检测方法**: 搜索代码中的 `MAD|mad`，核对排序方向（`decreasing=TRUE` → 保留最大值），与报告描述对比。

### 1.5 图号与样本口径错误（MAJOR）

- GOKEGG 结果段把 KEGG 图写成 "Figure 4B"，实际图题属于 Figure 3
- 正文写"两个验证集"，实际只有 1 个验证集 GSE73209

---

## 2. 审核经验提炼

### 2.1 覆盖矩阵双向检查法

```text
方向一：报告正文 → 结果目录（正文提到的是否有文件支撑？）
方向二：结果目录 → 报告正文（有文件的是否在正文中覆盖？）  ← 本项目漏在这里
```

两个方向缺一不可。仅做方向一会漏掉"有结果但无报告"的情况。

### 2.2 GSE 编号全量交叉验证

```python
import re

# 从报告提取所有 GSE 编号
report_gse = set(re.findall(r'GSE\d+', report_text))

# 从结果目录提取实际使用的 GSE
actual_gse = set()
for f in os.listdir('01_Rawdata'):
    m = re.findall(r'GSE\d+', f)
    actual_gse.update(m)

# 检查不一致
extra_in_report = report_gse - actual_gse  # 报告中多出的 → 可能是模板残留
missing_in_report = actual_gse - report_gse  # 报告中缺少的 → 可能遗漏
```

### 2.3 WGCNA 方法描述要点

WGCNA MAD 过滤是高频不一致点。关键核查：
- "保留"还是"剔除"？
- "最大"还是"最小"？
- `decreasing=TRUE` = 保留最大值 = 保留高变异基因

---

## 3. 关键教训

1. **覆盖矩阵必须双向建立**，不能只从报告出发
2. **GSE 编号是 Copy-paste 残留的高灵敏度标记物**，全量提取交叉验证成本低、价值高
3. **WGCNA MAD 过滤方向**是方法描述的常见反转点
4. **验证集数量**需要从代码和数据文件两端确认，不能只信报告
5. **ROC/DCA/校准曲线需要结构化统计表**，仅有图件时应标注"证据不充分"
