# 26YYH097F 可复用错题规则镜像

> 来源：`result_review_report/26YYH097F/wrong_question_set.md`  
> 生成日期：2026-07-22  
> 本文件镜像15条可复用教训，供后续审核规则、检查器与subagent prompt收紧。项目最终口径仍为25条canonical（CRITICAL 2、MAJOR 12、WARNING 11）、50/100、`BLOCK`。

| ID | 典型错误 | 触发场景 | 证据依据 | 正确标准 | 下次审核提醒 | 严重度 | 可执行规则建议 |
|---|---|---|---|---|---|---|---|
| WQ-01 | 数据来源ID孤立声明，或活动源输入未交付 | GEO/TCGA/空间转录组ID、外部下载转本地读取 | CF-001：GSE174554仅L11出现；CF-004：GSE251778/GSE271789活动输入缺失 | 建立报告声明—样本表—源文件/下载校验—活动代码—结果五点链 | 先区分活动读取、注释示例、孤立声明，再逐ID核对 | MAJOR；不得仅因重复命中升级CRITICAL | `RULE-DATASET-CHAIN`：输出五列布尔矩阵，孤立声明/活动输入缺失进入人工复核 |
| WQ-02 | 把注释、死代码、外项目残留直接判为结果污染 | 注释路径、`rm(list=ls())`后对象未重建、无输出块 | CF-002：25YLM302F路径注释，RIOK2块不可执行且无输出；GSE135251/绝对路径机械候选驳回 | 按活动性、依赖可达、输出存在、报告使用四步判定 | 外项目命中读取上下文并追踪输出，注释与活动分开计数 | 本项目WARNING；纯注释INFO/驳回 | `RULE-RESIDUE-ACTIVITY`：标记commented/active/unknown及输出可达性，commented禁止自动MAJOR/CRITICAL |
| WQ-03 | 因目录别名/分段布局误判模块缺失，或报告写错目录指针 | 中英文别名、编号目录、单细胞多阶段目录 | CF-003：20_ReactomeGSA应为20_Annotation；富集/ML/scRNA缺失候选均被真实目录否定 | 模块存在性按语义、内容、代码、结果综合判断；导航路径逐字一致 | 先建真实目录与一对多别名映射再查缺失 | 路径错误WARNING；实际存在的缺失候选驳回 | `RULE-MODULE-ALIAS`：支持别名和一对多映射，另做路径精确检查 |
| WQ-04 | 核心分析只交图片，不交结构化对象 | scRNA QC、PCA/UMAP、注释、表达 | CF-005：16-20及22主要为图/PDF，缺QC表、坐标、注释映射、表达矩阵/Seurat对象 | 每阶段至少交付可机读输入索引、参数、关键表和输出对象 | 不以“图能打开”代替数据流可复核 | MAJOR | `RULE-STRUCTURED-MINIMUM`：按阶段设必需文件类型；仅图件标记“存在但证据不足” |
| WQ-05 | 多体系MD重复计罚，或只按“缺源码”低估证据缺口 | 多个体系共用100 ns流程并报告精确指标 | CF-006：两套MD各仅9 PNG+9 PDF，无轨迹、数值、拓扑、配置、命令 | 共同根因合并一次；交付结构/拓扑、轨迹/能量、配置、命令、结构化指标 | 区分共同流程根因与体系特异错误 | MAJOR；本项目由机械WARNING上调 | `RULE-MD-DELIVERY`：逐体系清单后按共同根因去重，关键原始链全缺至少进入MAJOR复核 |
| WQ-06 | 把局部可核数值与端到端不可复现混为一体 | AI/GraphBAN候选表存在但缺模型与源库信息 | CF-007：175行、143唯一SMILES、阈值得2条可核；模型/权重/ZINC ID/聚合规则缺失 | 分段评价source、inference、aggregation、filter | 明确每段证据的起止边界 | 本项目WARNING，因143→2成立而降级 | `RULE-AI-STAGE-EVIDENCE`：固定四阶段状态并按关键缺失和结论依赖分级 |
| WQ-07 | 对接存在性、执行复现、图示追溯、结论外推误并 | 网页工具对接有图/结构/分数但元数据不全 | CF-008：执行元数据不足；CF-017：图内无身份/score但外部可映射；CF-025：结论外推 | 四维独立回答Exists/Evidence/Reproducible/Not-overstated | 按原始结果→任务参数→图内标识→结论措辞顺序审核 | 执行/图示WARNING；外推MAJOR | `RULE-DOCKING-4D`：四维独立建项，禁止一维替代其他维 |
| WQ-08 | 报告阈值、代码/数据和派生结论不闭环 | PPI、GSVA、理化性质等数字规则 | CF-009：>0.4却有0.395边；CF-010：HBD/TPSA/logP/PPB矛盾；CF-018：P<0.05与BH adjP+|t|不一致 | report/code/data三方同阈值并能重算派生计数 | 优先查不等号、单位、百分比、小数边界和组合条件 | 本项目均MAJOR | `RULE-THRESHOLD-TRIANGULATION`：抽取三元组并重算边界；同一表段按共同根因合并 |
| WQ-09 | “总数+枚举”不一致 | 模型、特征、图例、分组清单 | CF-011：正文9种、图注10种，实际仍枚举9项 | 总数等于去重枚举数并与图例/结果对应 | 统一解析中文数字、阿拉伯数字与分隔符 | WARNING，不与验证身份合并 | `RULE-COUNT-ENUM`：解析计数句式并输出缺失/重复项 |
| WQ-10 | 统计术语、方法原理或细胞身份错误翻译 | 英文缩写、细胞注释中文化、方法原理改写 | CF-012：NS/NES；CF-020：LogNormalize原理；CF-013：pDC/Plasma/B cells跨谱系错译 | 术语与活动实现一致；细胞身份由英文标签、marker和组织语境共同确认 | 建双语词表，抽查marker，对易混缩写全文一致性检查 | 细胞身份CRITICAL；一般术语WARNING | `RULE-TERM-IDENTITY`：精确词典+marker校验；跨谱系替换触发CRITICAL人工确认 |
| WQ-11 | QC后数量反增且被图文重复采信 | 过滤、去重、样本排除等单调步骤 | CF-014：181393→197202，反增15809，图文均标After QC | 纯过滤满足after≤before；否则解释非过滤操作并给样本级对账 | 不以多处一致代替逻辑约束检查 | CRITICAL硬触发 | `RULE-QC-MONOTONICITY`：抽取before/after和操作类型，纯过滤反增立即触发人工确认 |
| WQ-12 | 聚合图支持“显著”、图不可读、或追溯缺陷边界被夸大 | 细胞比例、拟时序、多面板、对接构象图 | CF-015：无样本统计；CF-016：关键标签不可读；CF-017：图内无标识但外部可映射 | 显著性需样本级统计；原图可读；同时检查图内和外部映射 | 必须打开原图，分开记录统计、可读性、身份映射 | 过度推断MAJOR；可读/标识WARNING | `RULE-VISUAL-CLAIM`：检查sample-level、error/p、native readability、embedded identity、external mapping |
| WQ-13 | 报告方法名、活动函数、参数和结构化输出不一致 | 免疫浸润、表达检验、ROC/列线图 | CF-019：CIBERSORTx vs CIBERSORT/perm=0；CF-023：Wilcoxon vs t.test；CF-024：关键统计量未导出 | 方法—函数—参数—输出四联一致，关键统计量可机读并含N/CI/数据身份 | 只追踪活动调用，检查保存语句而非内存对象 | 工具身份MAJOR；检验/导出WARNING | `RULE-METHOD-OUTPUT`：建立四联表，任一断裂进入人工复核 |
| WQ-14 | 训练CV被称独立验证，或拆分前选特征 | 模型比较、特征选择、列线图、外部验证 | CF-021：九模型仅train CV，留出集仅glmBoost，特征预拆分；CF-022：同一GSE38958拟合评估 | 区分训练CV/内部留出/外部验证；特征选择封装在训练内；指标绑定数据身份 | 沿预测对象追踪数据分区，不信变量名或图题 | MAJOR | `RULE-VALIDATION-LINEAGE`：输出model→fit data→feature scope→prediction data→metric血缘 |
| WQ-15 | 计算预测外推真实亲和力/实验依据 | 对接、MD、AI筛选总结段 | CF-025：无体内外实验、Kd/Ki/IC50、对照、重复MD/自由能，却称亲和力和实验依据 | 仅称计算预测/候选假设；真实亲和力和实验依据需相应实验证据或充分验证的自由能体系 | 单独审摘要/总结动词强度；执行齐全也不能越级 | MAJOR | `RULE-COMPUTE-CLAIM-LEVEL`：扫描强结论词并要求实验/自由能/重复证据，缺失则降格措辞并复核 |

## 镜像校验

- 学习条目：15/15。
- 每条均包含：典型错误、触发场景、证据依据、正确标准、下次审核提醒、严重度、可执行规则建议。
- 覆盖canonical：25/25；机械处置边界已纳入WQ-02、WQ-03、WQ-05。
- 本镜像不改变仲裁：CRITICAL 2、MAJOR 12、WARNING 11；50/100；`BLOCK`。
