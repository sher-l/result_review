# 26YBB037F 错题集

| 错误类型 | 具体表现 | 触发场景 | 证据依据 | 正确标准 | 下次审核提醒 | 严重程度 | 可执行规则建议 |
|---|---|---|---|---|---|---|---|
| 未声明数据集进入可执行脚本 | GSE226391 在 scRNA 处理脚本中读取并保存对象，但报告只声明 GSE176078/GSE203612 | 多单细胞队列项目 | script/r.02_scRNA.data.processing.R L27-L76；report_text.txt L23-L26 | 所有被代码读取/处理的数据集必须在报告、raw/source、结果中闭合 | 提取所有 GSE，区分执行代码与注释，执行代码未声明至少 MAJOR | MAJOR | GSE矩阵增加 executable_code_only 列并升级 |
| 空间转录组只有 PDF 图支撑强机制 | RCTD/MISTy/PSTS/Moran 等只交付 PDF，缺 spot 级矩阵、统计表和脚本 | 空转+单细胞联合机制报告 | result/Spatial Transcriptomics；C03-F001~F004 | 空间推断需交付输入对象、参数、矩阵/统计表、脚本 | 看到 RCTD/MISTy/stLearn/Cottrazm 必查结构化输出 | MAJOR | 对空间高风险方法定义 minimum_table_set |
| 验证集参与选模后仍称外部验证 | GSE58812/GSE42568 参与 C-index 排序选模，又作为验证集 | 101ML 生存模型 | r.11_101ML.R L230-L258；03.cindex_mat.csv | 外部验证不能参与模型选择或 cutoff 优化 | 检查 best_model 选择是否读取验证集矩阵 | MAJOR | 搜索 Validation_list 与 C-index 排序同现并触发复核 |
| CytoTRACE方向反读 | ABHD17A+ 同时被称高分化和高发育潜能/分化早期 | 单细胞轨迹/干性解释 | B02-F01；Figure5G/H | CytoTRACE potency 高通常对应低分化/高干性，需统一术语 | 图例颜色和正文方向逐句对照 | MAJOR | 对 CytoTRACE/伪时序图强制图例-正文方向核对 |
| 方法算法名称漂移 | 报告写 ssGSEA，代码用 GSVA::gsva | 通路评分模块 | r.01_KM.COX.GSVA.R L646-L680 | 方法段应与实际函数/参数一致 | 不接受同类方法名互换 | MAJOR | 检测 ssGSEA/GSVA 方法词与函数调用一致性 |
