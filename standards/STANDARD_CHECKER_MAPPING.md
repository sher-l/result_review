# 标准资源 — 检查器映射表

> 本文档记录框架中每份标准资源被哪些检查器引用、以及每条核心规则由哪些检查器执行。  
> 维护要求：新增/修改检查器或标准时同步更新本文件。

---

## 1. 标准资源 → 检查器（正向映射）

| 标准资源 | 位置 | 检查器 | 调用方式 |
|---------|------|--------|---------|
| TERM_MATCHING_LIBRARY.md | standards/ | TermConsistencyChecker (P0) | 按疾病类型加载术语黑名单 |
| STANDARD_GENE_SETS.md | standards/ | GeneSetQualityProjectChecker (P1) | 蛋白复合物基因检测、命名格式验证 |
| STANDARD_GENE_SETS.md | standards/ | GeneNamingChecker (P1) | 基因名全文一致性、标准化格式 |
| STATISTICS_REFERENCE.md | / | ClinicalStatisticsChecker (P1) | HR/OR 方向判断、p 值阈值 |
| STATISTICS_REFERENCE.md | / | ThresholdConsistencyChecker (P1) | 报告声称阈值 vs 代码实际赋值 |
| disease_types.json | standards/ | TermConsistencyChecker (P0) | 疾病编码 → 术语库选择 |
| disease_types.json | standards/ | SpeciesChecker (P0) | 物种标签匹配 |

---

## 2. 核心规则 → 检查器（反向映射）

| 规则 | 说明 | 执行检查器（按优先级） | 补充层 |
|------|------|----------------------|--------|
| R01 | 流程图覆盖完整性 | DataFlowValidator (P0), ReportCoverageChecker (P1) | Layer 2 |
| R02 | 阴性结果完整 | ScRNAQCChecker (P1), ReportCoverageChecker (P1) | — |
| R03 | 数据集声明-使用-存在 | DataFlowValidator (P0), SpeciesChecker (P0), ReportCoverageChecker (P1) | — |
| R04 | 数据库名/URL/功能三方一致 | TermConsistencyChecker (P0), GeneSetQualityProjectChecker (P1) | — |
| R05 | 术语翻译正确 | TermConsistencyChecker (P0), ChineseProofreadingChecker (P1) | — |
| R06 | 统计方向正确 | ClinicalStatisticsChecker (P1), MLAnomalyChecker (P1) | Layer 3-C |
| R07 | 基因名全文一致 | GeneNamingChecker (P1), GeneSetQualityProjectChecker (P1) | — |
| R08 | 数字三处一致 | NumberCrossrefChecker (P1), ReportDataMatchChecker (P1), ScRNAQCChecker (P1) | Layer 3-B |
| R09 | TopN 列表一致 | NumberCrossrefChecker (P1), ReportDataMatchChecker (P1) | Layer 3-B |
| R10 | 参数上下文一致 | VisualizationThresholdChecker (P1), ThresholdConsistencyChecker (P1), ClinicalStatisticsChecker (P1) | — |
| R11 | 文件存在性 | FigureIntegrityChecker (P1) | — |
| R12 | 无硬编码路径/残留 | ProjectIDChecker (P0) | — |
| R13 | 证据充分（有表） | EvidenceCompletenessChecker (P1), FigureDataMatchChecker (P1) | Layer 3-A |
| R14 | 药物检索完整 | EvidenceCompletenessChecker (P1) | — |
| R15 | 对接有数值表 | EvidenceCompletenessChecker (P1), FigureDataMatchChecker (P1) | — |
| R16 | 单细胞 QC 图重复使用 | EvidenceCompletenessChecker (P1) | Layer 2 |
| R17 | 代码-包名一致 | CodeExistenceChecker (P1), EvidenceCompletenessChecker (P1) | Layer 3-C |
| R18 | 报告 vs 代码阈值 | ThresholdConsistencyChecker (P1), EvidenceCompletenessChecker (P1) | Layer 3-C |
| R19 | ML 算法-包-特征一致 | ModelConsistencyChecker (P1) | Layer 3-C |
| R20 | 流程图视觉检查 | *(仅 Layer 2 figure_audit.md)* | Layer 2 |

---

## 3. 覆盖盲区

以下规则**仅依赖人工层**（Layer 2/3/4），无 Layer 1 自动检查器：

| 规则 | 覆盖层 | 原因 |
|------|--------|------|
| R20 | Layer 2 | 流程图语义需人工/AI 视觉判断 |
| R14 | Layer 1 (部分) + Layer 3 | 药物检索完整性超出模式匹配范围 |

---

## 4. 检查器 → 标准依赖汇总

> 便于标准更新时定位须同步修改的检查器。

| 检查器 | 依赖的标准资源 |
|--------|--------------|
| ProjectIDChecker | *(无外部标准)* |
| TermConsistencyChecker | TERM_MATCHING_LIBRARY.md, disease_types.json |
| DataFlowValidator | *(无外部标准)* |
| SpeciesChecker | disease_types.json |
| EvidenceCompletenessChecker | *(内置规则)* |
| ClinicalStatisticsChecker | STATISTICS_REFERENCE.md |
| GeneSetQualityProjectChecker | STANDARD_GENE_SETS.md |
| GeneNamingChecker | STANDARD_GENE_SETS.md |
| NumberCrossrefChecker | *(无外部标准)* |
| ScRNAQCChecker | *(无外部标准)* |
| ReportDataMatchChecker | *(无外部标准)* |
| FigureDataMatchChecker | *(无外部标准)* |
| VisualizationThresholdChecker | *(无外部标准)* |
| FigureIntegrityChecker | *(无外部标准)* |
| MLAnomalyChecker | *(无外部标准)* |
| ReportCoverageChecker | *(无外部标准)* |
| CodeExistenceChecker | *(无外部标准)* |
| ThresholdConsistencyChecker | STATISTICS_REFERENCE.md |
| ModelConsistencyChecker | *(无外部标准)* |
| ChineseProofreadingChecker | *(内置词库)* |
