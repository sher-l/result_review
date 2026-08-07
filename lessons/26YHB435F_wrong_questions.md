# 26YHB435F 错题集

## WQ-001 高风险脚本含外项目可执行残留
- 典型错误：只看报告结论或目录名，未扫描脚本中的 `setwd/readRDS/os.chdir` 外项目路径。
- 触发场景：scTenifoldKnk、SCENIC、DrugReflector 等长脚本后半段混入旧项目代码。
- 证据 basis：`Code/01.06_scRNA_subCell_MG_scTenifoldKnk.r` L60-L68、L148-L163 指向 16_26YBB086F/17_26YLC070F。
- 正确标准：任何可执行外项目路径残留均需至少 CRITICAL 复核；若无本项目结果目录，不得支撑本项目结论。
- 下次提醒：不要只采纳 `case_manifest.foreign_project_ids`，还要 grep 代码正文中的项目编号和绝对路径。
- 严重度：CRITICAL。
- 可执行规则建议：对 `Code/**/*` 扫描 `\d{2}_26[A-Z]{2,3}\d{3}F|26[A-Z]{2,3}\d{3}F`，命中非当前项目时进入外项目残留检查。

## WQ-002 校正后不显著被写成显著增强
- 典型错误：只看 p_val 或 pct 变化，忽略 p_val_adj 和方向。
- 触发场景：CellChat/NicheNet 通讯轴表达验证表。
- 证据 basis：Tab.8.5 Cd44/Ccr2 p_val_adj=1；Tab.8.6 Gdf15 p_val_adj=0.166975737、Itga4/Itga9 p_val_adj=1。
- 正确标准：正文“显著”必须以校正后阈值为准；方向不一致时不能支撑增强通讯轴。
- 下次提醒：逐行核对报告写入的每个配体/受体，不只核对图形。
- 严重度：CRITICAL。
- 可执行规则建议：表格中出现 `p_val_adj=1` 或 `>0.05` 且正文邻近出现“显著增强/显著上调”时标记为严重候选。

## WQ-003 Top100 药物按多 target 行计数误作化合物数
- 典型错误：同一化合物多 target 多行，MOA 统计没有按 unique compound 去重。
- 触发场景：LINCS/DrugReflector/CLUE 结果表。
- 证据 basis：`02_Drug_Result_logot_Top100.csv` 176 行但只有 100 个 unique pert_id/cmap_name。
- 正确标准：报告写“化合物数量”时必须按 unique compound 统计；按 target 行统计需明确口径。
- 下次提醒：核对文件名 Top100 与实际行数、unique 药物数。
- 严重度：MAJOR。
- 可执行规则建议：对 TopN 药物文件自动计算 rows 与 unique drug id 差异，差异>10% 时提示AI复核。

## WQ-004 RSS/轨迹等高风险结论只有图件或空表
- 典型错误：报告引用阈值和排名，但交付只有 PDF 或空 CSV。
- 触发场景：SCENIC RSS、Monocle BEAM、CytoTRACE2。
- 证据 basis：`04_RSS_Key_Genes_TFs.csv` 0 行；Pseudotime 目录无 CSV/TSV/RDS。
- 正确标准：排名、阈值、score、state 必须能追溯到结构化表或对象。
- 下次提醒：空 CSV 比缺文件更容易漏检，必须检查 shape。
- 严重度：MAJOR。
- 可执行规则建议：对关键 `RSS/BEAM/CytoTRACE/AUC/score` 文件检查非空行数；仅 PDF 时自动列入证据不足清单。
