# script_utils — 审核框架工具脚本库

> **版本**: v6.5  
> **更新日期**: 2026-04-17  
> **用途**: 为 `auto_audit_pipeline.py` 和手动审核提供底层检查与工具能力

---

## 架构总览

```
auto_audit_pipeline.py (scripts/ 入口)
    ├── Layer 0: 代码预解析
    │   ├── parse_report_structure.py → report_structure.json
    │   ├── parse_project_structure.py → project_structure.json
    │   └── mechanical_checks.py → mechanical_check_result.json
    │
    ├── Layer 1: 自动预检查
    │   └── check_orchestrator.py  ← 调度所有检查器
    │       ├── BaseProjectChecker (基类，提供 Layer 0 数据 + 工具方法)
    │       ├── [P0 FATAL] 4 个检查器
    │       └── [P1 CRITICAL] 17 个检查器
    │
    └── Layer 2: AI 深度审核 (Agent 端)
        └── quality_gate.py  ← 汇总评估
```

### 继承体系

所有项目级检查器（21/21）继承 `BaseProjectChecker`（含包装器），获得：
- `self.find_code_directory()` — 代码目录定位（优先 Layer 0 → 文件系统扫描兜底）
- `self.load_report_text()` — 报告文本加载
- `self.find_modules()` — 编号模块目录查找（优先 Layer 0 → 文件系统扫描兜底）
- `self.report_structure` / `self.project_structure` — Layer 0 预解析数据
- `self._relative_path(path)` — 安全相对路径

---

## 检查器（Checkers）— 由编排器调度

### P0 级（FATAL）

| 脚本 | 类名 | 说明 |
|------|------|------|
| `check_project_id_consistency.py` | `ProjectIDChecker` | 检测代码文件中项目编号是否统一 |
| `check_term_consistency.py` | `TermConsistencyChecker` | 检测是否混入其他疾病类型术语 |
| `check_data_flow.py` | `DataFlowValidator` | 验证跨模块基因数/数据流是否一致 |
| `check_species_match.py` | `SpeciesChecker` | 验证基因集物种标识与分析数据一致性 |

### P1 级（CRITICAL）

| 脚本 | 类名 | 说明 |
|------|------|------|
| `check_evidence_completeness.py` | `EvidenceCompletenessChecker` | 验证表文件、图件格式及参数记录完整性 |
| `check_clinical_statistics.py` | `ClinicalStatisticsChecker` | 检测临床统计项目（HR/OR/CI等）完整性 |
| `check_gene_naming.py` | `GeneNamingChecker` | 验证基因名格式规范（大小写、非标准名检测） |
| `check_visualization_thresholds.py` | `VisualizationThresholdChecker` | 验证图件阈值与代码筛选标准是否对应 |
| `check_figure_integrity.py` | `FigureIntegrityChecker` | 验证图件文件完整性（空文件/异常尺寸/拼写） |
| `check_figure_data_match.py` | `FigureDataMatchChecker` | 检测模块中图件与数据的比例异常 |
| `check_scrna_qc.py` | `ScRNAQCChecker` | 单细胞 QC 指标单调性检查 |
| `check_report_coverage.py` | `ReportCoverageChecker` | 报告对模块的覆盖矩阵检查 |
| `check_report_data_match.py` | `ReportDataMatchChecker` | 报告-数据交叉验证 |
| `check_ml_anomaly.py` | `MLAnomalyChecker` | 机器学习异常检测 |
| `check_code_existence.py` | `CodeExistenceChecker` | 代码存在性/可复现性检查 |
| `check_number_crossref.py` | `NumberCrossrefChecker` | 数字交叉验证 |
| `check_threshold_consistency.py` | `ThresholdConsistencyChecker` | 方法-代码阈值一致性 |
| `check_model_consistency.py` | `ModelConsistencyChecker` | 模型口径一致性检查 |
| `check_chinese_proofreading.py` | `ChineseProofreadingChecker` | 中文报告校对（缺字/错字/术语） |
| `check_gene_set_quality.py` | `GeneSetQualityProjectChecker` | 基因集质量评估（蛋白复合物/非标准基因/命名格式） |

> 详细的检查器触发条件、规则映射和依赖信息参见 [CHECKER_CAPABILITIES.md](CHECKER_CAPABILITIES.md)。  
> 标准资源与检查器的双向映射参见 [standards/STANDARD_CHECKER_MAPPING.md](../standards/STANDARD_CHECKER_MAPPING.md)。

---

## 工具模块（Utilities）

| 脚本 | 说明 | 主要接口 |
|------|------|---------|
| `base_project_checker.py` | 检查器基类，Layer 0 数据桥接 + 工具方法 | `BaseProjectChecker` 类 |
| `check_orchestrator.py` | 统一检查调度器，按 P0→P1 优先级编排 | `CheckOrchestrator` 类 |
| `quality_gate.py` | 质量门禁评估 (FATAL/CRITICAL/MAJOR/WARNING/INFO) | `QualityGate`, `QualityGateBuilder` |
| `project_metadata.py` | 项目元数据（类型推断、目录定位） | `ProjectMetadata` 类 |
| `utils.py` | 通用工具函数（safe_read_file 带 LRU 缓存） | `extract_project_id()`, `find_report_text()`, `safe_read_file()` |

---

## 统一接口

所有注册在 orchestrator 中的检查器统一通过 `check_all()` 方法调用。  
历史遗留的专用方法（`check_all_files`, `check_code_files`, `validate_all_flows`, `check_all_gene_files`）仍然保留作为内部实现，由 `check_all()` 委托调用。

---

## 添加新检查器

1. 在 `script_utils/` 下创建 `check_xxx.py`  
2. 继承 `BaseProjectChecker`，实现 `check_all() -> Dict`  
3. 在 `check_orchestrator.py` 的 `P1_CHECKERS` 中注册  
4. 创建对应测试文件 `tests/test_check_xxx.py`  
5. 更新本 README 文档
