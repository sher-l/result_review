# 26YBB096F framework_optimization_notes

## 本次应强化的框架点

1. Cox/列线图模块：增加 HR/CI/p 值自洽性自动检查，CI 跨 1 与 p<0.05 冲突时升级 CRITICAL。
2. 药敏模块：对 `drug_sensitivity_pvalue.xls` 自动统计 P<0.05 与 FDR<0.05，并与报告数量比对。
3. 单细胞下游对象：NicheNet/beyondcell/scTenifold 的目标细胞、对象名、输出目录需要三方一致性检查。
4. 多GEO项目：代码中全部 GSE 编号与报告/原始数据清单做集合差异，含疾病名关键词残留。

## 无需改变的口径

- 生存曲线/Cox 出现在预后模型项目中不应自动视为模板残留；应结合项目类型降级或转为图号/统计证据复核。
