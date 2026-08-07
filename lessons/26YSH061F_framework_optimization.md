# 26YSH061F 框架优化记录

## 本次应强化的规则

1. 对接模块最低值校验：结构化结合能表、Figure 标题/图注、正文最低值对象必须一致；若正文出现未入表药物，直接标 CRITICAL。
2. 药物预测 TopN 校验：同时输出全表 TopN、限定靶点 TopN、同分项和排除说明；未说明限定规则时至少 MAJOR，影响后续对接/MD 时升为 CRITICAL。
3. MD 复现材料清单：mdp/top/itp/tpr/xtc或trr/log/edr/QC/脚本缺失时，不得支持强稳定性结论。
4. 附件声明校验：报告称 PP/PE 或多子集均提供 GO/KEGG 时，逐子集核对 GO 与 KEGG 文件是否成套。

## 无需修改的规则

- 无代码单独作为 WARNING 的口径仍适用；本次不因 total_code_files=0 单独升级，而是因高风险模块复现材料缺失另列问题。
- KEGG “Cancer: specific types” 在通路分类语境下不应机械判为模板残留；需结合项目方向和上下文仲裁。

## 建议落地位置

- `result_review_framework/lessons/patterns/figure_visual_errors.md`
- `result_review_framework/lessons/patterns/data_flow_coverage.md`
- 高风险模块 subagent prompt：c03 docking/MD 专项。
