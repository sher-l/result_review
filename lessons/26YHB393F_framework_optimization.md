# 26YHB393F framework_optimization_notes

## 应加严项
1. `visual_prefilter` 对 MD/对接图件重复应与报告靶标语义绑定；不同靶标重复图默认进入 CRITICAL 候选。
2. `check_evidence_completeness` 对 DrugReflector/Geneformer/scTenifoldKnk 增加输入签名、模型版本、全量输出、参数日志字段。
3. `check_report_coverage` 对 “00_Rawdata/GSE” 声明增加原始数据目录和文件名命中检查，尤其单细胞 GSE。
4. `check_report_data_match` 对 scRNA DEG 声称数量区分 cluster marker 与 disease-vs-control DEG。

## 无需修改项
- “无代码交付只作为 WARNING”规则适用，本次没有因为无代码本身升级。

## 可复用沉淀
- 已同步到 `result_review_framework/lessons/26YHB393F_wrong_questions.md` 和 `result_review_framework/lessons/26YHB393F_framework_optimization.md`。
