# 26YBB067F 可复用审核教训

- 数据集闭合：报告、代码、raw 目录中的 GSE/TCGA/OpenGWAS 编号必须三方闭合；声明的单细胞数据若未交付原始输入，不能仅凭 PDF 通过。
- 多重检验：MR/DsigDB/富集表存在 adjusted/FDR 列时，强结论不得只按 nominal p<0.05；top10 若多项 adjusted p 不显著，应降格为探索性。
- 视觉闭环：`needs_audit=true` 图件必须逐项写出 Finding/Severity；机器 flag 为 0 不代表视觉审计完成；必须核对实际图内标题、图号与报告引用。
- scRNA/拟时序：细胞数、cluster 数、注释和拟时序结论需结构化表或对象支撑，PDF 不能替代可复核证据。
- 高风险因果-药物链：MR、共定位、DsigDB/Enrichr 药物预测如支撑最终靶点，也应要求脚本、参数、输入输出和校正口径证据包。
