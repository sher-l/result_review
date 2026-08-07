# 26YZF059F wrong_question_set.md

| 典型错误 | 触发场景 | 证据 basis | 正确标准 | 下次审核提醒 | 严重性 | 可执行规则建议 |
|---|---|---|---|---|---|---|
| 未交付外部验证集却写入方法和结论 | 报告声明 GSE122063 独立验证，结果目录无原始/中间数据 | final_review_report.md F-01；A/B/C 均发现 | 每个验证集必须有数据、分组、预处理和结果输出可追溯 | 搜索 GEO 编号在 raw、结果和图表三处是否闭环 | CRITICAL | 若报告GEO编号未在交付目录出现且用于核心结论，自动进入高风险队列 |
| 单细胞主线转向依据缺少数据 | 用 GSE157827 解释 B 细胞不足但未交付 | final_review_report.md F-03 | 决策依据数据集必须交付输入或评估表 | 主线改变理由要查数据集覆盖 | MAJOR | 主线决策语句出现数据集编号时强制路径追踪 |
| AI/深度学习扰动结果使用 fallback 仍强解释 | Geneformer 8/8 fallback 且输入路径疑似非目标细胞 | final_review_report.md F-02 | fallback、输入细胞类型、显著性和效应量必须披露 | 不可把微小无显著性 shift 写成稳健状态迁移 | CRITICAL | Geneformer结果若 used_fallback 全为 true 或 final_input_data_file 非目标细胞名，强制人工仲裁 |
| 只交付图件不交付核心统计表 | WGCNA、ROC、列线图仅图示 | final_review_report.md F-04/F-05 | 支撑核心结论的数值必须有结构化表 | 图上数值不能替代表格和脚本 | MAJOR | 对 AUC/HL/MAE/moduleTraitCor 等关键词要求 CSV/TSV 证据 |
| 高风险计算模块缺少参数日志 | 对接/MD 有图片和结果但无 config/log/trajectory | final_review_report.md F-08 | 对接/MD需软件、版本、参数、输入、日志、轨迹/拓扑 | 不能把结果图等同为可复现 | MAJOR | 对 docking/MD 目录强制检查 log/config/mdp/tpr/top/xtc 等 |
| MR工具变量数量混用口径 | 报告写有效IV，交付文件按阶段不一致 | final_review_report.md F-06 | 分清clumped、harmonised、method-specific nsnp | MR结论必须逐基因覆盖 | MAJOR | MR发现“有效IV”时强制与 clumped 和 res-result nsnp 对表 |
