# 26YZF063F 框架优化记录

## 本项目是否需要框架更新

需要。当前框架已捕获 GSE13911/GSE26942、GROMACS/对接脚本缺失和 DEG 数字问题，但仍建议强化以下规则。

## 建议收紧的 policy/check/subagent prompt

1. `check_report_coverage` / `mechanical_check MC-008`：不仅比较 rawdata 文件，还应比较所有代码中的 GSE/TCGA/GWAS ID 与报告数据来源，未披露 ID 自动进入 MAJOR。
2. `check_evidence_completeness`：对 GROMACS/分子动力学目录若仅 PDF/PNG、无 xvg/csv/xtc/tpr/top/gro/mdp/log，应直接输出 MAJOR 级“MD 原始运行包缺失”。
3. `check_threshold_consistency`：DESeq2/limma 输出存在 `padj`/`adj.P.Val` 时，如代码筛选 `pvalue`/`P.Value` 而报告作为正式 DEG，应标记统计口径风险。
4. 小切片 prompt `c01/c02/c03`：增加“外部项目相对路径 ../../<project_id>”显式检索项，尤其 GMT、模型输入、RData、annotation CSV。
5. 最终报告 linter：可检查 `figure_audit.md` 是否残留待复核占位，同时允许由视觉 slice JSON 作为闭合证据。

## No-op 项

- Tumor/Cancer 模板残留规则本项目为胃癌语境，自动 CRITICAL 应允许人工降级；不建议简单禁止肿瘤通用词。
