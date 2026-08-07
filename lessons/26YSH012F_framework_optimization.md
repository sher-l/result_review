# 26YSH012F framework_optimization_notes

## 本次命中的可复用模式
1. 相近基因名漂移（MUC16/MUC6）会跨方法段、FASTA/promoter文件、CSV列名和图件标签同时出现；现有机械检查未自动识别。
2. DEG 文件名含阈值时，可自动复算 `abs(logFC)`、`p.adjust` 和 `regulated` 计数，能提前发现数量级错误。
3. 网络药理报告中的“药物对象中文名残留”不一定体现为项目编号残留，需要将题名药物与正文药物名做一致性扫描。
4. KM/ROC PDF-only 可支持图件存在，但不足以支撑结构化统计复核；应作为生存模块固定证据缺口提示。

## 建议收紧的框架位置
- `script_utils/check_number_crossref.py`：增加 DEG 阈值文件自动计数规则。
- `script_utils/check_gene_naming.py`：增加相近基因名跨文件对象一致性检查，尤其 MUC1/MUC6/MUC16。
- `script_utils/check_term_consistency.py`：增加项目题名药物/疾病关键词与正文同类实体残留扫描。
- 子代理 prompt：在网络药理 + TCGA 生存报告中强制检查 ADMET、KM/ROC、Cox 是否有结构化统计导出。

## 不建议新增硬门禁的项
- 单纯无代码仍维持 WARNING，不应因本项目缺代码直接升级；本次 CRITICAL 来自结构化结果与正文冲突、核心对象混用和药物对象残留。
