# 26YZF036F 复审可复用教训（2026-05-28）

## 适用场景

多疾病、多组学、含单细胞/scPagwas/菌群代谢/分子对接/MD 的报告复审。

## 复用规则

1. 若结果表含 FDR、padj、adj.P.Val 或 qvalue，而报告按 raw p-value 给出核心结论，应进入 CRITICAL 候选。
2. 方案文件名、docx XML 或正文出现非当前项目编号，且伴随未声明数据源，应进入外项目残留 CRITICAL 候选。
3. AD 与肌少症等多疾病章节必须按疾病对象核对图号、样本量、训练/验证集和结论归属；跨疾病图号或疾病名残留至少 MAJOR，影响核心图时可升 CRITICAL。
4. docx_only 或 total_code_files=0 不能作为可复现通过证据；高风险模块存在时必须在终稿中明确代码不可复现风险。
5. scPagwas、ROC、LASSO、AUCell 不能只接受图片；需要结构化 p/CI/estimate、AUC/CI/阈值/坐标、lambda/CV、相关统计导出。
6. 对接/MD 的 PDB、xvg 和图片只能证明有展示结果，不能证明可复跑；需检查任务日志、输入文件、参数、轨迹和命令链。

## 本次证据锚点

- 最终报告：result_review_report/26YZF036F/final_review_report.md
- 错题集：result_review_report/26YZF036F/wrong_question_set.md
- 框架优化：result_review_report/26YZF036F/framework_optimization_notes.md
