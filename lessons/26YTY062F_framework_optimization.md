# 26YTY062F 框架优化 notes

## 本次是否需要框架变更

需要轻量增强；现有框架已捕获 FATAL 项目编号残留，但对虚拟敲除组合可复现性、top20/FDR 口径和多组合标签错配仍主要依赖人工切片。

## 建议加强的策略/检查

1. `mechanical_checks.py` / 高风险模块策略
   - 新增虚拟敲除专项：统计报告声称的细胞-基因组合数，与脚本中 `gKO`、`idents`、输出目录循环覆盖范围比对。
   - 若结果组合数明显多于脚本覆盖范围，标记 CRITICAL 可复现性风险。

2. `WORKFLOW_MODULE_CHECKS.md` / subagent prompt
   - 对 `scTenifoldKnk`、虚拟敲除、扰动网络新增最低证据包：输入对象、目标基因清单、细胞类型、随机种子、参数、完整差异表、topN 规则、GO/KEGG 规则。

3. `final_report_linter.py` 或机械统计检查
   - 当报告出现“显著/top20/富集”且代码或结果中存在 `pvalue`、`p.adjust`、`qvalue` 时，要求最终报告说明使用的是原始 p 值还是 FDR。
   - 对 `qvalueCutoff=100` 与“显著富集”并存给出 WARNING/MAJOR。

4. 视觉/文本一致性 prompt
   - 对目标基因清单做模糊匹配：`S100a11` vs `S100a1`、`Cers2` vs `Cers`、`Cenpp` vs `Genpp` 这类短基因截断/错字应重点提示。

## 本次已执行的无代码优化

- 项目内写入 `wrong_question_set.md`，覆盖身份残留、虚拟敲除不可复现、top20/FDR 口径、基因/图号错配。
- 镜像可复用教训到 `result_review_framework/lessons/26YTY062F_wrong_questions.md` 与 `26YTY062F_framework_optimization.md`。

## 不做的变更

- 不在本次审核中修改框架脚本，避免在正式审核任务内引入未经测试的框架行为变化。
- 不触发企业微信测试发送；仅允许 finalize 正式完成通知。
