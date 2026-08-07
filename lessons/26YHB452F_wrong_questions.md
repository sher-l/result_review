# 26YHB452F 错题集

## WQ-01 多层次题名过声明
- 典型错误：题名写 bulk/单细胞/空转，但交付只有单细胞、GWAS-scPagwas、机械力评分。
- 触发场景：标题或研究方向含“多层次/空转/空间/bulk”，目录无对应模块。
- 证据 basis：report_text.txt L7；project_structure.json modules。
- 正确标准：题名、方法、结果、交付目录必须同范围；缺模块应删除或明确未做。
- 下次提醒：先做标题-目录-代码三方范围矩阵。
- 严重度：MAJOR；可执行规则：若 title_terms - delivered_modules 非空，至少 MAJOR。

## WQ-02 统计方向被概括为“全部显著/均高于”
- 典型错误：把部分细胞/部分方向写成所有细胞 DKD 均显著高于对照。
- 触发场景：scPagwas/TRS/评分表含 higher_group/significance，但正文只写总括。
- 证据 basis：06.TRS.wilcox_results.csv；report_text.txt L58/L86。
- 正确标准：逐细胞类型报告 p 值、显著性和方向；ns 不得写显著。
- 下次提醒：所有“全部/均/显著高于”必须逐行核对结构化表。
- 严重度：MAJOR；可执行规则：all/均 + significance/higher_group 冲突时至少 MAJOR。

## WQ-03 交付 PDF 存在但代码输入链不可复现
- 典型错误：结果图存在，但关键 h5ad/VCF/RDS 或绘图脚本不可执行。
- 触发场景：代码读取的原始输入或中间对象未在交付目录出现。
- 证据 basis：script/r.04.scPagwas.R；script/r.05.scRNA.irGSEA.R。
- 正确标准：结果存在只能证明产物存在，不能替代代码复现链。
- 下次提醒：对 scPagwas、irGSEA、空间/机制类结果必须做 input-object-result 三段核对。
- 严重度：MAJOR；可执行规则：关键输入缺失且影响复现时至少 MAJOR。