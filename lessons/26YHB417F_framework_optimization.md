# 26YHB417F 框架优化记录

生成时间：2026-06-02 10:20

## 应收紧规则
1. 统计校正规则：当方法段声明 BH/FDR/adjust.method 时，正文显著性必须优先匹配 adj.P.Val/qvalue；raw P 结论必须降级。
2. 高风险模块规则：对接/MD 不能只检查图和分数表，必须检查输入结构、参数、原始输出、轨迹/日志和位姿选择依据。
3. 引用规则：数据库/工具引用需要编号-书目双向核验，特别是 PharmMapper、SEA、STRING、SwissTargetPrediction、OMIM、GeneCards。
4. 视觉闭环规则：visual_prefilter 标记后，figure_audit.md 不得保留未处置占位。

## 无需改变的规则
- 无代码交付仍按 WARNING 记录，不把“无代码”作为唯一 CRITICAL 或唯一不合格原因；本次不合格来自统计显著性、证据不足和过度外推。

## 建议沉淀到 lessons
- 26YHB417F 显示：新版包虽有结构化结果目录，但统计校正、高风险原始材料、引用链和图注仍需逐项核查。
