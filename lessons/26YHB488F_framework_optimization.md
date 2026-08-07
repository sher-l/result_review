# 26YHB488F framework optimization notes

生成时间：2026-06-29T11:36:28

## 应收紧的框架点

1. 凭证扫描门禁：在代码预检查中加入 JWT/OpenGWAS/API token 正则；命中非占位凭证时直接建立 CRITICAL，并要求最终报告第一项披露。
2. GEO/项目号/细胞体系残留联动：MC-008 不只检查 GEO，还应联动搜索外项目号、外细胞类型、物种 taxid 和 setwd，形成“跨项目残留包”。
3. GWAS/scPagwas 高风险包：当报告出现 GWAS、scPagwas、TRS、OpenGWAS 时，强制检查 VCF/summary 输入、下载清单、scPagwas output、RDS 中间对象和结构化 TRS/统计表。
4. 网络药理学闭环检查：题名或总结出现“网药/中药干预机制”时，要求成分来源、筛选阈值、靶点来源、网络节点边、拓扑/通路结果和结论边界。
5. 单细胞关键细胞证据表：对 cell proportion、OR、Augur、milo、TRS、亚群比例等图件，要求同名或可追溯 CSV/TSV 汇总表。
6. ML 结果行数与验证角色：提取“113种”等声明，与 AUC 表有效行数、失败日志、排序字段和训练/验证角色进行一致性检查。
7. SHAP/ROC 结构化导出：报告出现 mean SHAP、AUC/CI、Wilcoxon 时，要求可机读的 SHAP value、ROC 坐标/CI、统计量和样本量表。

## 对 subagent prompt 的改进

- A 路增加“题名/总结承诺 vs 交付证据闭环”表，特别覆盖网药、GWAS、机制、诊断模型等高风险词。
- B 路视觉切片不允许 `figure_audit.md` 留有未处置的机器预筛 flag；装饰资产也要写最终处置。
- C 路代码切片增加凭证扫描、物种 taxid、外项目细胞体系和外部验证参与模型选择的固定检查。

## no-op 项

- DEG 求和自动疑点本次经 AI核验未保留：report_text.txt L124 为 4083=2527+1556。
- OMIM/TTD 参考文献自动错配疑点本次未保留：report_text.txt L33 与参考文献 L195-L197 口径一致。
- CellChat 缺目录疑点本次未保留：报告主体未将 CellChat 作为项目分析模块声明。
