# 26YYS133F wrong_question_set

> 目的：沉淀本轮最容易复犯的错误，供下次审核直接对照。

| 典型错误 | 触发场景 | 证据依据 | 正确标准 | 下一次审核提醒 | 严重度 | 可执行规则建议 |
|---|---|---|---|---|---|---|
| 图号残留/章节映射错误 | 正文与图注出现“图2.12.4A/B”与“图2.1.4A-B”混写 | report_text.txt L45；report_structure.json figure_mismatches | 同一图组编号必须在正文、图注、图索引中保持唯一且一致 | 每次改图后必须做图号前缀回读与章节映射检查 | MAJOR | 把图号一致性作为机械预检项，发现前缀错位即阻断收敛 |
| 方法-代码阈值不一致 | FindAllMarkers 阈值在报告与代码不一致 | report_text.txt L16/L58；scRNA.r L398-L401 | 方法描述必须与代码中的 min.pct / logfc.threshold 完全一致 | 每次输出方法段前先从代码反向抄录参数 | MAJOR | 把阈值对账加入“方法-代码一致性”硬规则 |
| 样本数写错或筛选口径未披露 | 报告写 4 vs 4，但代码实际筛到 10 个 GSM | report_text.txt L12；scRNA.r L13-L18,L47-L49,L69-L73 | 样本数必须以实际筛选后的交付数据为准，并说明过滤前后口径 | 在写结果段前列出“原始样本-入组样本-剔除样本”三列 | MAJOR | 把样本数对账作为统计段落的必查项 |
| 细胞级统计替代供体级统计 | 单细胞逐细胞 Wilcoxon 直接支撑疾病结论 | report_text.txt L12,L18,L76,L81,L104；scRNA.r L708-L733,L746-L747 | 疾病组比较必须控制供体内相关性，优先 pseudobulk / 混合模型 | 遇到病例/对照分析先问“独立统计单位是什么” | CRITICAL | 把供体级统计作为单细胞临床结论的硬门槛 |
| 虚拟敲除复现链断裂 | scTenifoldKnk 缺少中间对象、diffReg 表、运行锁定文件 | scRNA.r L750-L801；project_structure.json；文件系统缺失检查 | 关键分析必须能从中间对象重跑到结果图 | 发布前检查 RDS/RData/CSV/命令记录是否齐全 | CRITICAL | 把“可复跑对象清单”加入高风险模块的必交付项 |
| 富集分析 provenance 缺失 | 只见 xlsx/图件，不见生成脚本与参数锁定 | report_text.txt §2.3.2；scRNA.r  grep clusterProfiler 结果 | 富集分析必须附输入基因集、函数调用、参数与输出表 | 检查是否存在 clusterProfiler/enrichGO/enrichKEGG/bitr | MAJOR | 把富集分析纳入“输入-参数-输出”三段式证据链 |
| 结构化统计表缺失 | 只给图，不给 p 值、效应量、样本量或 ROC/AUC 表 | report_text.txt L76-L104；scRNA.r L729-L747,L804-L812 | 关键结论必须附结构化统计表，不能只留图 | 在结论段前强制检查“表格是否可机读导出” | MAJOR | 把结构化结果表设为临床/机制结论的最低交付标准 |
| 参考文献域外残留 | 用牙龈/牙周疾病文献支撑 GEO 下载/Seurat 方法 | report_text.txt L12,L16,L106-L107 | 引用必须与本项目疾病体系、方法与数据来源相匹配 | 做参考文献抽检，凡跨项目残留必须替换 | MAJOR | 把“外项目残留”作为参考文献硬过滤项 |
| 结论外推过度 | 把单次虚拟敲除结果直接写成诊断/治疗候选 | report_text.txt conclusion and §2.3 narrative | 结论强度必须与证据强度匹配，不能超出可复现结果 | 写结论时区分“探索性发现”和“临床可用性” | MAJOR | 把结论分级写法纳入模板约束 |
| QC 参数披露不完整 | 代码多了 nCount_RNA > 200，下限未在方法中披露 | report_text.txt QC 段；scRNA.r subset 条件 | 所有过滤阈值必须在方法中完整披露 | 检查代码中的 subset/筛选条件是否都被写入方法 | WARNING | 把 QC 阈值完整披露加入方法段的最后自检 |
