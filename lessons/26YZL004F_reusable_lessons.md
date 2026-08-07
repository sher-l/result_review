# 26YZL004F 可复用审核经验

- 当前项目编号：26YZL004F。
- 可复用主题：非模式物种 scRNA 报告中的外项目输入、物种数据库口径、细胞级伪重复和拟时序证据闭环。

## 可复用规则

1. 结论图反向追踪到代码时，只要发现读取路径包含其他项目编号，应优先判定为结果链污染；若该图进入正式报告核心结论，严重度可升至 CRITICAL。
2. 中华鳖等非模式物种使用 human/hsa/org.Hs.eg.db 不能默认成立；没有同源映射、背景集和未映射比例时，功能富集结论证据不足。
3. scRNA 细胞组成差异不能仅以细胞数作为独立样本解释组间显著性；应要求 sample-level count/proportion 与统计明细。
4. 拟时序模块需同时满足脚本语言一致、方法名一致、cell-level 结果表齐全、分支基因和富集表齐全。
5. 活动代码中的其他项目编号、疾病标签、细胞类型和物种参数残留，应作为复现隔离风险记录。

## 建议落地位置

- `result_review_framework/lessons/patterns/method_code_mismatch.md`
- `result_review_framework/lessons/patterns/data_flow_coverage.md`
- `result_review_framework/lessons/patterns/structural_special.md`
