# 26YHB488F wrong question set

生成时间：2026-06-29T11:36:28

## WQ-01 有效第三方 API 凭证随交付代码泄露
- 典型错误：将 OpenGWAS JWT 写进脚本并随报告包交付。
- 触发场景：GWAS/scPagwas 依赖在线接口，开发者为方便复跑把个人 token 固化到代码。
- 证据 basis：Code/01.03_scRNA_Cell_Celltype_marker.r L1749 明文 JWT；解码有效期覆盖审核日附近。
- 正确标准：交付代码不得包含明文 token/JWT；凭证必须通过环境变量或占位配置注入，正式包仅保留占位符。
- 下一次审核提醒：对 `eyJ`、token、JWT、Authorization、openGWAS 等关键词做凭证扫描。
- 严重级别：CRITICAL。
- 可执行规则建议：precheck 命中 JWT 形态字符串且非示例占位时直接升级 CRITICAL，并要求报告第一屏列出。

## WQ-02 未报告数据集残留进入核心脚本
- 典型错误：GSE150910 脚本中残留 GSE133101 富集路径，但报告数据清单没有该数据集。
- 触发场景：复用旧项目脚本时只改前半部分流程，尾部 enrich/venn 块未清理。
- 证据 basis：Code/03.01_GSE150910_Train_Plot_DEGs.r L735-L737 setwd 到 GSE133101。
- 正确标准：报告数据清单、结果目录、代码引用 GEO 必须一致；未披露 GEO 只能作为注释或历史代码且不得参与执行链。
- 下一次审核提醒：按 GEO 编号全局搜索并和 report_text 数据段、project_structure.geo_references 交叉比对。
- 严重级别：MAJOR。
- 可执行规则建议：MC-008 命中后要求子代理复核该代码块是否可达、是否写出结果、是否影响结论。

## WQ-03 外项目/外细胞体系/外物种代码块未清除
- 典型错误：IPF 人肺成纤维项目中残留 26YHB435F、Microglia/MG 和小鼠物种 10090。
- 触发场景：单细胞亚群脚本模板复用，最后的 marker/富集块未按当前细胞体系重写。
- 证据 basis：Code/01.04.02_scRNA_subCell_Celltype_marker.r L1535-L1620。
- 正确标准：脚本中的项目号、细胞类型、物种 taxid 和输出路径必须与报告体系一致。
- 下一次审核提醒：除项目号外，同时搜索 Microglia、MG_、10090、9606、setwd 等高风险残留。
- 严重级别：MAJOR。
- 可执行规则建议：外项目号 + 不同物种 taxid 同时出现时，将代码残留严重度至少设为 MAJOR。

## WQ-04 GWAS/scPagwas 只交派生图却作遗传易感性结论
- 典型错误：报告写 scPagwas TRS，但交付缺 GWAS 输入、中间文件和真实 TRS 输出。
- 触发场景：高风险模块由本地对象/在线接口跑出图后，只复制 PDF 和一个 gene_PCC 表。
- 证据 basis：report_text.txt L81-L89；01_scRNA/01_Cell/03_scPagwas 仅派生 PDF 和 gene_PCC.csv。
- 正确标准：GWAS整合必须有输入来源/版本、可复跑脚本、关键中间对象、结构化输出和统计检验。
- 下一次审核提醒：区分 scPagwas 原生 TRS 与后续 AddModuleScore 模块评分。
- 严重级别：MAJOR。
- 可执行规则建议：报告出现 GWAS/scPagwas/TRS 且缺 VCF/summary 或 scPagwas output 时自动建高风险项。

## WQ-05 “网药/中药干预机制”由 drugGenes+Venn 过度外推
- 典型错误：客户提供 drugGenes 经过 Venn 后，被包装成中药干预机制证据框架。
- 触发场景：网络药理学名词出现在题名/总结，但交付没有成分-靶点-疾病网络。
- 证据 basis：report_text.txt L15-L16、L131-L135、L175-L180；Code/04_Venn.r 只做交集。
- 正确标准：网药结论必须有成分来源、筛选阈值、靶点来源、网络/拓扑/通路或实验验证证据。
- 下一次审核提醒：题名含“网药/中药机制”时先建立证据闭环表。
- 严重级别：MAJOR。
- 可执行规则建议：若 network pharmacology 仅有 drug target list + Venn，最终报告必须下调结论强度。

## WQ-06 机器学习有效模型数和验证口径混淆
- 典型错误：报告保留“113 种”文案，但结构化结果只有 107 个有效模型，且验证队列参与最优模型选择。
- 触发场景：部分算法失败或被过滤后，报告未同步更新；为追求高 Mean_AUC 把外部队列纳入模型选择。
- 证据 basis：05_113ML/00_Model_Feature_AUC.csv 107 行；report_text.txt L39-L40、L136-L139。
- 正确标准：候选模型数、有效模型数、失败日志、选择集和最终独立验证集必须分开。
- 下一次审核提醒：核对 AUC 表行数、methods 列表、排序逻辑和验证队列角色。
- 严重级别：MAJOR。
- 可执行规则建议：模型声明数与有效结果行数不一致或验证集参与选择时自动标记统计高风险。
