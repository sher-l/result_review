# 26YLM158F 审核错题集

> 审核日期：2026-05-12
> 项目主题：肾纤维化与过氧化物酶体脂代谢，转录组 + 单细胞联合分析
> 最终结论：不建议提交，需补代码与修正文稿后复审

## 1. 错误类型：代码不可复现与方法-代码断裂

- 具体表现：项目有 13 个分析模块，但 `project_structure.json` 显示 `total_code_files=0`；报告声明 Seurat、AUCell、limma、sva、caret、Boruta、glmnet、rms、pROC 等方法，却没有任何 R/Python/Notebook 脚本可复核。
- 触发场景：仅交付 Word 报告和结果图表，缺少全流程代码。
- 证据依据：`project_structure.json` metadata.total_modules=13、metadata.total_code_files=0；`mechanical_check_result.json` MC-014。
- 正确标准：每个模块应有可执行脚本、参数配置、环境说明、输入输出映射，能追溯报告里的阈值和结果。
- 下次审核提醒：遇到多模块生信报告时，先看 `total_code_files`；若为 0，应直接升级为代码不可复现阻断项。
- 严重程度：CRITICAL。

## 2. 错误类型：外项目/外数据集残留

- 具体表现：LASSO 方法段写“基于 TCGA-STAD 数据集”，但项目为肾纤维化 GEO 数据，数据来源表和交付目录均无 TCGA-STAD。
- 触发场景：机器学习方法模板从肿瘤项目复制到非肿瘤项目后未替换数据源。
- 证据依据：report_text.txt L11-L19 数据来源为 GSE182256、GSE76882、GSE65326、GSE7392、GSE22459；report_text.txt L44 写 TCGA-STAD；`project_structure.json` 无 TCGA-STAD。
- 正确标准：正文方法、数据来源表、项目交付物和实际脚本输入必须指向同一数据源。
- 下次审核提醒：全文检索 TCGA、STAD、HCC、PAAD、BRCA 等癌种/数据库缩写，尤其关注 LASSO、Cox、免疫和药物预测模板段。
- 严重程度：MAJOR。

## 3. 错误类型：模型验证集合与建模输入集合不一致

- 具体表现：表达验证段称满足筛选条件的基因只有 ACOT8，但列线图仍使用 10 个关键基因，并把训练集表现作为主要模型证据。
- 触发场景：机器学习筛选、表达验证、诊断建模分属不同段落，未统一最终入模基因集合。
- 证据依据：report_text.txt L140-L141 为 ACOT8-only 验证；report_text.txt L151-L155 为 10 基因列线图和训练集验证。
- 正确标准：若建模输入不同于验证通过集合，必须说明保留规则、统计依据和外部验证结果。
- 下次审核提醒：机器学习项目要核对“筛选基因 → 验证通过基因 → 入模基因 → 结论基因”的集合是否逐步一致。
- 严重程度：MAJOR。

## 4. 错误类型：诊断模型只有图件、缺少结构化数值导出

- 具体表现：`10_nomogram` 仅提供 Nomogram、ROC、calibrate、DCA 的 PDF/PNG，缺少 AUC、CI、模型系数、校准和 DCA 的 CSV/表格导出。
- 触发场景：报告正文给出 AUC、P 值、n 值等数字，但结果目录只交付图片。
- 证据依据：`10_nomogram` 目录文件清单；`project_structure.json` module 10 file_counts 中 csv=0、code=0。
- 正确标准：诊断模型结论必须有结构化数值表支撑，不能只依赖图件。
- 下次审核提醒：列线图、ROC、校准曲线、DCA 模块要固定检查 CSV/Excel/JSON 导出和 95%CI。
- 严重程度：MAJOR。

## 5. 错误类型：参考文献编号错配

- 具体表现：AUCell 方法引用标为 [3]，但参考文献 [3] 是 SCENIC 论文。
- 触发场景：单细胞方法包列表批量插入参考文献后未逐条核对。
- 证据依据：report_text.txt L26、L189。
- 正确标准：方法包、版本和参考文献编号必须一一对应。
- 下次审核提醒：对 AUCell、UCell、GSVA、clusterProfiler、CIBERSORT 等方法包逐条核对参考文献。
- 严重程度：WARNING。
