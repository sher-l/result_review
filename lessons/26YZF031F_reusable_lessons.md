# 26YZF031F reusable lessons

## ML 未声明外部队列进入选模
- Trigger: 代码中的 `list_train_vali_Data`/模型开发对象包含未在报告数据来源和 rawdata 披露的队列。
- Rule: 至少 MAJOR；若参与最终选模或改变核心模型，升级 CRITICAL。
- Reminder: 同时核对 report_text、rawdata、code、模型性能图表。

## 高风险 in silico 模块缺主输入
- Trigger: docking/MD/virtual knockout 只交付图、结构或后处理曲线，缺脚本、参数、日志、轨迹或完整对象生成链。
- Rule: 不得支撑强机制或治疗结论；至少 MAJOR，必要时要求降格为探索性。
- Reminder: C03 切片必须列出缺失主输入清单。

## 模型基因名截断/错写
- Trigger: 正文模型基因短名与模型 CSV/下游分析标准符号不一致。
- Rule: 若影响模型解释、对接、表达定位或总结，至少 MAJOR。
- Reminder: B01/C02 需逐基因核对正文、表格、代码和附件。
