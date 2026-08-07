# 26YSH035F 审核框架优化建议

生成时间：2026-06-01T18:16:16

## 本案暴露的框架短板

1. convergence_report 对小切片 findings 的字段完整性较敏感，C03 有完整证据但 route 聚合后部分标题为空，影响仲裁队列可读性。
2. 代码缺失规则已能识别 total_code_files=0，但需要更清楚地区分“缺代码本身”和“缺代码叠加核心证据矛盾”。
3. 共定位阴性与后续核心因果链条的矛盾应前置为高风险自动检查。
4. MD 对象选择可以由结合能表和 Dynamic 目录自动比对，目前仍依赖审阅切片发现。
5. 图号跨章节重复已有机械检查，但 panel 误引和重复图号对正文定位的影响需要自动进入最终问题草案。

## 建议优化 1：共定位阴性后续链条检测

- 触发条件：正文或结果表显示无显著共定位，同时后文出现核心基因、因果基因、关键机制、机器学习交集等强链条表述。
- 建议严重度：CRITICAL 或 MAJOR，取决于是否进入最终核心结论。
- 应强化的位置：mechanical_check_result 与 Agent B/C 高风险提示。

## 建议优化 2：Docking-MD 选择规则自动比对

- 触发条件：方法出现“选择 N 对最高结合能”且交付存在结合能表和 Dynamic 目录。
- 检查逻辑：解析 topN、并列值、Dynamic 对象集合，输出缺失、额外和并列未说明三类结果。
- 建议严重度：MAJOR。

## 建议优化 3：route 聚合 schema 修复

- 问题：slice JSON 里的 claim、source_type、quote_or_value 字段在合并为 route result 时可能丢失 title、location、evidence。
- 建议：聚合脚本统一将 claim 映射为 title，将 source_path 与 locator 合并为 location，将 quote_or_value 和 rationale 合并为 evidence。
- 预期效果：convergence_report 和 arbitration_queue 不再出现空标题 finding。

## 建议优化 4：模型和生存统计结构化表检查

- 触发条件：正文出现 AUC、ROC、HL P、DCA、calibration、log-rank、Cox、HR、显著相关。
- 检查逻辑：在对应模块查找 csv/xlsx/tsv 中的 AUC、CI、threshold、sensitivity、specificity、HR、P value 等列。
- 建议严重度：缺表时 MAJOR。

## 建议优化 5：强结论词降级规则

- 触发词：证实、阐明、显著调控、靶向干预潜力、因果关联。
- 适用模块：MD、PheWAS-MR、scTenifoldKnk、CellChat、轨迹分析等预测或模拟模块。
- 检查逻辑：若缺实验验证、脚本或配置，则建议改为“提示、预测、探索性”。

## 本案执行状态

- 预检查：已完成。
- 小切片：8 个第一层 subagent 已完成。
- 收敛：converged=false，已由 Lead AI裁定整合。
- 最终报告：已生成并进入 lint/finalize 门禁。
