# 检查器能力矩阵

> 本文档列出所有 20 个注册检查器的能力、触发条件和依赖关系。  
> 便于回答："哪个检查器能检测 X？"和"检查器 Y 检测什么？"  
> 维护：新增检查器时同步更新。

---

## 1. P0 级检查器（FATAL — 无条件执行）

### ProjectIDChecker
- **文件**: `check_project_id_consistency.py`
- **触发条件**: 无条件
- **检测内容**: 代码文件中所有项目编号是否与文件夹名一致；硬编码错误编号
- **规则**: R12
- **依赖**: code_dir/*.R/*.py
- **典型发现**: 代码里残留上一个项目的 "25YHB654F" 而当前项目是 "26YHB051F"

### TermConsistencyChecker
- **文件**: `check_term_consistency.py`
- **触发条件**: **needs_project_type=True**（需知道疾病类型才能选择术语黑名单）
- **检测内容**: 报告术语是否混入其他疾病类型（如肾结石项目出现 "Tumor/Normal"）
- **规则**: R04, R05
- **依赖**: report_text.txt, TERM_MATCHING_LIBRARY.md, disease_types.json
- **典型发现**: 干细胞项目报告残留 "non-small cell lung cancer" 模板文字

### DataFlowValidator
- **文件**: `check_data_flow.py`
- **触发条件**: 无条件
- **检测内容**: DEG→富集、ML→GSEA、交集→monocle、scRNA→spatial 基因数流一致性；数据流断裂
- **规则**: R01, R03
- **依赖**: report_structure.json, 各模块结果文件
- **典型发现**: 报告声称 DEG 有 523 个交集基因但 Venn 图只有 312 个

### SpeciesChecker
- **文件**: `check_species_match.py`
- **触发条件**: 无条件
- **检测内容**: .gmt 文件物种标识 (Hs/Mm/Rn) 与项目数据物种匹配；代码引用校验
- **规则**: R03
- **依赖**: *.gmt 文件, 代码引用, GSE 数据集
- **典型发现**: 人类项目使用了小鼠 GO 注释文件

---

## 2. P1 级检查器（CRITICAL — 条件执行）

### EvidenceCompletenessChecker
- **文件**: `check_evidence_completeness.py`
- **触发条件**: 无条件
- **检测内容**: LASSO 参数规则完整性、表达验证仅图无表、分子对接结合能数值表、分子动力学原始数据、QC 图重复使用
- **规则**: R13, R14, R15, R16, R17, R18, R19
- **依赖**: report_structure.json, 交付目录
- **典型发现**: 分子对接只有热图没有结合能数值表

### ClinicalStatisticsChecker
- **文件**: `check_clinical_statistics.py`
- **触发条件**: **silent_if_empty=True**（无临床模块自动跳过）
- **检测内容**: Baseline 统计表、Logistic 单因素→VIF→多因素、Nomogram 校准/DCA、ML SHAP、方向判断 (HR>1=风险因素)
- **规则**: R06, R10, R18
- **依赖**: 01_baseline/, 02_Logistic/, 03_Nomogram/, 04_ML/*
- **典型发现**: HR=0.72 被报告描述为"风险因素"（应为保护因素）

### GeneSetQualityProjectChecker
- **文件**: `check_gene_set_quality.py`
- **触发条件**: **silent_if_empty=True**（无基因集文件跳过）
- **检测内容**: 蛋白复合物基因检测（含 - 和 _ 双向）、非标准基因分类 (MT-, HLA-, IG*, lncRNA)、命名格式
- **规则**: R04, R07
- **依赖**: 基因集 *.csv 文件, STANDARD_GENE_SETS.md
- **典型发现**: 基因集中混入线粒体基因 MT-CO1

### GeneNamingChecker
- **文件**: `check_gene_naming.py`
- **触发条件**: 无条件
- **检测内容**: 基因名全文一致性 (IGFBP vs IGF2BP 混用)、格式标准化 (大写/无符号)、非标准分类
- **规则**: R07
- **依赖**: 各模块 *.csv 的基因列, STANDARD_GENE_SETS.md
- **典型发现**: 同一报告前半部分写 "IGF2BP2" 后半部分写 "IGFBP2"

### NumberCrossrefChecker
- **文件**: `check_number_crossref.py`
- **触发条件**: **silent_if_empty=True**
- **检测内容**: 报告中 GO/KEGG/DEG/ML 特征数 vs .csv 实际行数对比；数字矛盾
- **规则**: R08, R09
- **依赖**: report_text.txt, GO.csv, KEGG.csv, DEG*.csv
- **典型发现**: 报告写 "共富集到 187 条 GO 通路" 但 GO.csv 只有 154 行

### ScRNAQCChecker
- **文件**: `check_scrna_qc.py`
- **触发条件**: **silent_if_empty=True**（无 scRNA 模块跳过）
- **检测内容**: QC 前后细胞数逻辑 (QC 后>QC 前=CRITICAL)、合并后>各样本之和、阴性结果隐藏
- **规则**: R02, R08
- **依赖**: report_text.txt, 代码 QC 参数
- **典型发现**: QC 后细胞数大于 QC 前（数据逻辑不可能）

### ReportDataMatchChecker
- **文件**: `check_report_data_match.py`
- **触发条件**: **silent_if_empty=True**（无报告文本降级运行）
- **检测内容**: DEG 计数、基因列表长度、通路数、免疫浸润细胞数 vs CSV 实际数值；标签互换
- **规则**: R08, R09
- **依赖**: report_text.txt, *.csv/*.tsv
- **典型发现**: 报告声称 "上调 DEG 287 个" 但 DEG_up.csv 有 342 行

### FigureDataMatchChecker
- **文件**: `check_figure_data_match.py`
- **触发条件**: **silent_if_empty=True**
- **检测内容**: 模块图件/数据表比例异常、有图无支撑 CSV、特定模块应有 CSV 清单
- **规则**: R13, R15
- **依赖**: 结果文件/*/*.png/*.csv
- **典型发现**: GSEA 模块有 20 张图但只有 3 个 CSV

### VisualizationThresholdChecker
- **文件**: `check_visualization_thresholds.py`
- **触发条件**: 无条件
- **检测内容**: 火山图 vline/hline 与 logFC 筛选标准一致；热图颜色刻度；PCA 分组标签
- **规则**: R10
- **依赖**: *.R/*.py (geom_vline/axvline/breaks)
- **典型发现**: 火山图虚线在 |logFC|=1 但方法段声称 |logFC|>0.585

### FigureIntegrityChecker
- **文件**: `check_figure_integrity.py`
- **触发条件**: 无条件
- **检测内容**: 空文件/0 页 PDF→CRITICAL；PDF 异常小/图像超小→WARNING；文件名拼写错误；编号不连续
- **规则**: R11
- **依赖**: 结果文件/*.pdf/*.png/*.jpg/*.tif
- **典型发现**: Figure_3.png 和 Figure_5.png 存在但缺少 Figure_4.png

### MLAnomalyChecker
- **文件**: `check_ml_anomaly.py`
- **触发条件**: **silent_if_empty=True**（无 ML 模块跳过）
- **检测内容**: AUC=1.0 过拟合；AUC>0.8 但 Accuracy<0.4 矛盾；全模型 AUC 异常一致（数据泄漏）；训练 >> 验证
- **规则**: R06
- **依赖**: ML 模块/0*/*.csv
- **典型发现**: 5 个 ML 模型 AUC 全部为 0.923（高度可疑）

### ReportCoverageChecker
- **文件**: `check_report_coverage.py`
- **触发条件**: **silent_if_empty=True**
- **检测内容**: GSE 数据集报告提及 vs 实际使用覆盖缺口；模块目录 vs 报告描述缺失；阴性结果隐藏
- **规则**: R01, R02, R03
- **依赖**: report_structure.json, project_structure.json
- **典型发现**: 结果文件夹有 NicheNet 目录但报告未提及

### CodeExistenceChecker
- **文件**: `check_code_existence.py`
- **触发条件**: **silent_if_empty=True**（仅 INFO 警告）
- **检测内容**: 分析脚本是否存在 (.R/.py/.Rmd/.ipynb)；代码目录覆盖可视化模块类型
- **规则**: R17
- **依赖**: CODE/scripts/各模块/*.R/*.py
- **典型发现**: 项目无任何分析脚本（只有结果文件）

### ThresholdConsistencyChecker
- **文件**: `check_threshold_consistency.py`
- **触发条件**: **silent_if_empty=True**（无代码跳过）
- **检测内容**: 报告方法段声称阈值 (p<0.05/|logFC|>1) vs R/Python 脚本实际赋值比对
- **规则**: R18, R10
- **依赖**: report_text.txt, *.R/*.py
- **典型发现**: 报告写 "|logFC|>1" 但代码中是 `abs(logFC)>0.585`

### ModelConsistencyChecker
- **文件**: `check_model_consistency.py`
- **触发条件**: **silent_if_empty=True**（无 R 脚本跳过）
- **检测内容**: 同一脚本内 lrm/glm/coxph 公式变量集一致性（列线图 vs 校准曲线 vs DCA）
- **规则**: R19
- **依赖**: *.R（识别模型公式）
- **典型发现**: Nomogram 用了 5 个变量但 DCA 代码只用了 3 个

### ChineseProofreadingChecker
- **文件**: `check_chinese_proofreading.py`
- **触发条件**: **silent_if_empty=True**
- **检测内容**: 缺字检测（缺"免"→疫细胞浸润）、同音错字（巨势→巨噬）、术语错误（网路→网络）
- **规则**: R05
- **依赖**: report_text.txt
- **典型发现**: "巨势细胞" 应为 "巨噬细胞"

---

## 3. 触发条件速查

| 条件标志 | 含义 | 适用检查器 |
|---------|------|-----------|
| *(无标志)* | 无条件执行 | ProjectIDChecker, DataFlowValidator, SpeciesChecker, EvidenceCompletenessChecker, GeneNamingChecker, VisualizationThresholdChecker, FigureIntegrityChecker |
| `needs_project_type=True` | 需知道疾病类型 | TermConsistencyChecker |
| `silent_if_empty=True` | 无相关模块/数据时静默跳过 | ClinicalStatisticsChecker, GeneSetQualityProjectChecker, NumberCrossrefChecker, ScRNAQCChecker, ReportDataMatchChecker, FigureDataMatchChecker, MLAnomalyChecker, ReportCoverageChecker, CodeExistenceChecker, ThresholdConsistencyChecker, ModelConsistencyChecker, ChineseProofreadingChecker |

## 4. 执行顺序

```
P0 检查器（串行，阻断式）
  1. ProjectIDChecker
  2. TermConsistencyChecker
  3. DataFlowValidator
  4. SpeciesChecker
  ↓ 无 FATAL → 继续
P1 检查器（并行，max_workers≤4）
  5-20. 全部 16 个 P1 检查器并行执行
  ↓ 汇总结果
QualityGate 评估
```

> **注意**: P0 发现 FATAL 问题后 P1 仍然会执行（收集完整问题清单），但 QualityGate 会标记为不合格。
