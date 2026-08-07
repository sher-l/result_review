# 26YBB096F wrong_question_set

| 错题 | 触发场景 | 证据依据 | 正确标准 | 下次审核提醒 | 严重程度 | 可执行规则建议 |
|---|---|---|---|---|---|---|
| Cox结果p值与CI逻辑矛盾仍被用于列线图 | 预后模型/列线图报告 | muti_cox.result.xls 三变量 p.val 完全相同且 CI 跨 1 | 多因素 Cox p、HR、CI 必须同源自洽；CI 跨 1 不得宣称独立显著 | C02 必须逐行核对 HR/CI/p 的数学一致性 | CRITICAL | 增加 Cox 表 p/CI 自洽检查 |
| 差异药物数量未按结构化表核对 | oncoPredict 药敏段 | 报告102种，表 P<0.05=16、FDR=0 | 数量结论必须从统计表按阈值复算 | 药敏结论同时核对 nominal p 与 FDR | MAJOR | 药敏模块增加 P/FDR 计数规则 |
| scRNA 模块对象名从 M2_like 漂移到 M2/Macrophage | NicheNet/beyondcell | 报告目标细胞与代码参数不一致 | 下游对象必须与报告细胞类型一致 | 细胞类型名做精确和近似匹配双检 | MAJOR | 增加 receiver_celltype/object 名称一致性检查 |
| 外源数据集代码块未声明 | 多GEO单细胞脚本 | GSE131907_Lung_Cancer 未在报告/rawdata声明 | 所有活动读取数据集必须在报告和数据清单中出现 | B03/C01 必查 GSE 全量列表 | MAJOR | 代码GSE集合-报告GSE集合差异自动输出 |
