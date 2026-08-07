# 26YYS124F 可复用审核教训

- F-CRIT-01 [CRITICAL]: Figure 14-2A 复用了 Figure 14-1A 的完全相同图片。证据：report_text.txt L196-L200；visual_prefilter.json images.image_053.png.flags[0]。规则建议：替换 Figure 14-2A 为 NK cells/F2R 对应真实图件，并复核 Figure 14-2 全段图文。
- F-MAJ-01 [MAJOR]: WGCNA turquoise 模块基因数 1,686 与源表 1,593 不一致。证据：report_text.txt L228；02_WGCNA/keymodgene.csv；03_candidate_intersection/04.common_genes.csv。规则建议：统一 WGCNA、候选交集、PPI 核心基因数量，并追溯后续链条。
- F-MAJ-02 [MAJOR]: 总结层关键基因筛选链条写成 36/16/3，与结构化结果 35/15/5→2 不一致。证据：report_text.txt L228；06_MachineLearn/venn.csv；07_Expression_verify/附件/06.final_genes.csv。规则建议：修正总结和流程图式叙述，区分三算法交集与最终验证基因。
- F-MAJ-03 [MAJOR]: WGCNA 软阈值选择与方法规则不自洽。证据：report_text.txt 方法/结果 WGCNA 段；02_WGCNA/附件/03.soft_threshold_fit.csv。规则建议：补充 β=5 的选择依据，或按方法规则修正为最小满足阈值 power。
- F-MAJ-04 [MAJOR]: 差异分析使用原始 P<0.05 而非 FDR，显著基因数量被放大。证据：report_text.txt L23；01_DEGs/01.DEG_all.csv；01_DEGs/01.DEG_sig.csv。规则建议：说明为何采用原始 P，或改用 FDR 并重新评估下游 WGCNA/交集/PPI/ML。
- F-MAJ-05 [MAJOR]: PPI 网络边和 CytoHubba 分数缺少结构化证据。证据：05_PPI；report_text.txt L91、L98-L99。规则建议：补交互作边表、score 表和算法排名分数，或降低 PPI 结论强度。
- F-MAJ-06 [MAJOR]: 单细胞原始对象、脚本和配置缺失，40,194 细胞分析链不可复算。证据：00_RawData/GSE248284.csv；11_QC/单细胞README.txt；11_QC-14_sctenifoldknk。规则建议：补交表达矩阵/对象、QC 参数、注释脚本和 scTenifoldKnk 配置。
- F-MAJ-07 [MAJOR]: scTenifoldKnk 高风险模块缺少运行脚本、命令、随机种子或配置。证据：14_sctenifoldknk；project_structure.json total_code_files=0。规则建议：补交 scTenifoldKnk 可执行流程和参数，或将结论降格为探索性结果。
- F-MAJ-08 [MAJOR]: TLR7 Monocytes 虚拟敲除正文基因列表与结果表不一致。证据：report_text.txt L206；14_sctenifoldknk/Figure 14-4.TLR7__Monocytes/TLR7_significant_diffRegulation.csv。规则建议：按 CSV 修正文中基因数量和名单，并核对 Figure 14-4 图注。
- F-MAJ-09 [MAJOR]: 总结把 F2R/TLR7 Monocytes 均写成 13 个显著基因，TLR7 实际为 11 个。证据：report_text.txt L228；14_sctenifoldknk/gko_combo_summary.csv。规则建议：修正总结数量，并同步更新机制段结论。
- F-MAJ-10 [MAJOR]: ROC/列线图缺少 AUC 95%CI 与外部验证，预测结论偏强。证据：07_Expression_verify/附件/04.*_auc.csv；08_Nomogram/附件/04.ROC_results.csv；report_text.txt L124。规则建议：补充 AUC 95%CI、外部验证/交叉验证，或改写为探索性预测模型。
- F-MAJ-11 [MAJOR]: “揭示机制/致病机制”表述超出观测性组学和伪敲除证据强度。证据：report title；report_text.txt L54-L55、L228。规则建议：将结论改为“提示/预测/假设生成”，避免因果机制定性。
