# 26YBB119F wrong_question_set

| 典型错误 | 触发场景 | 证据依据 | 正确标准 | 下一次审核提醒 | 严重度 | 可执行规则建议 |
|---|---|---|---|---|---|---|
| 将训练集完美 AUC/敏感性/特异性外推为临床应用价值 | 列线图或分类模型 AUC=1，OR CI 0-Inf，缺外部验证 | report_text.txt L150-L158；11_Nomogram CSV | 完美训练集指标必须视为过拟合高风险，不能宣称临床价值 | 遇到 AUC=1 或 CI 无限先触发高风险阻断 | CRITICAL | 若 AUC=1 且无 validation/CV/external 字样，生成 CRITICAL 候选 |
| 总结段引入结果文件不存在的通路或细胞类型 | GSEA 文件为 KEGG，但总结写 GO term；免疫表未含 Treg | report_text.txt L216；08_GSEA；09_Immune_Infiltration | 总结必须可追溯到正文和结果表 | 对总结段逐句回溯结果表 | MAJOR | 对总结段术语建立结果文件词典匹配 |
| 只交付图片而缺结构化表格 | PPI、ML、ROC、KM、scRNA 表达均以 PDF 为主 | 多模块缺 summary/score/stat 表 | 关键结论需机器可核查表格支撑 | 图片不能替代表格证据 | MAJOR | 对每类模块定义 minimum_table_set |
| 癌症项目中 Tumor/Cancer 被机械误判为模板残留 | 项目本身为 ICC/癌症 | MC-006；report_text tumor/cancer 上下文 | 机械命中需结合项目类型和上下文 AI处置 | 不直接按词命中升级 | INFO | 若 project_type=癌症，Tumor/Cancer 命中进入上下文处置而非直接 CRITICAL |
| 虚拟敲除从计算模拟外推到机制和靶点开发 | scTenifoldKnk 有输出但无独立扰动验证 | report_text.txt L191-L217；14_sctenifoldknk | 计算扰动仅能提出假设 | 检查是否有实验/独立队列/脚本/随机种子 | MAJOR | 虚拟敲除结论含“靶点开发/机制/TME”且缺验证时升级 |
