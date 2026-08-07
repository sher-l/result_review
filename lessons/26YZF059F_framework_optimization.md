# 26YZF059F framework_optimization_notes.md

## 本项目需要加强的框架点

1. **数据集追溯策略**：报告中出现在方法、Table 1、结论或模型矩阵中的 GEO 编号，应自动生成数据集覆盖矩阵。若编号未在 raw/结果目录出现，但用于核心结论，应进入 CRITICAL/MAJOR 候选队列。
2. **Geneformer/虚拟扰动专项检查**：增加对 `used_fallback`、`final_input_data_file`、目标细胞类型名、p value/FDR、effect threshold 的结构化检查。全 fallback 或输入路径非目标细胞时不得直接通过。
3. **核心数值结构化证据检查**：对 AUC、HL P、MAE、DCA、module-trait correlation、soft power、MR nsnp 等关键词，要求存在 CSV/TSV/XLSX 表或脚本日志，否则至少 MAJOR 候选。
4. **高风险模块复现文件检查**：对 docking/MD 目录加入参数、日志、轨迹、拓扑、配置文件的文件类型规则；有图和汇总表但无运行文件时标记复现性不足。
5. **视觉审查闭环**：机器预筛 0 flags 不等于AI审查完成；needs_audit 图像必须有 PASS/FAIL/WAIVE 决策，并修正图号/图注错配。

## 子代理提示词建议

- B 类事实核查代理增加“报告出现的数据集编号必须在 raw、结果、图表三层追踪”的硬问题。
- C 类高风险模块代理增加 Geneformer fallback 与输入路径核验清单。
- 视觉代理输出统一使用框架 severity 值 FATAL/CRITICAL/MAJOR/WARNING/INFO，避免 MEDIUM/LOW 需要后处理。

## 无需改变的规则

- “全项目无代码”本身仍建议按框架保留为 WARNING，不应机械升级；但可作为高风险模块不可复现的支撑证据。
