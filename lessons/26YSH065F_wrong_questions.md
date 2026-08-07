# 26YSH065F wrong_question_set.md

## 错题 1：高风险计算模块不能只凭最终图/表判通过
- 错误类型：GraphBAN/MD 证据链断裂
- 具体表现：GraphBAN 仅交付 SMILES-Protein-pred 表；MD 仅交付 6 个PDF图。
- 触发场景：报告声称 ZINC/Lipinski/PAINS/ADMET/GraphBAN、GROMACS 100ns、Sobtop/力场/平衡参数等复杂流程。
- 证据依据：results/03_AI 仅2个CSV+2图；results/05_MD 仅6个PDF，无脚本/参数/日志/轨迹/数值表。
- 正确标准：高风险计算链至少要有输入、参数、版本、运行日志、中间表和可复核输出；否则不得把稳定性/成药性作为强结论。
- 下次审核提醒：看到 GraphBAN、Docking、MD、100ns、ADMET 时必须建立“输入→过滤→预测/模拟→原始输出→报告结论”闭环。
- 严重程度：CRITICAL。
- 可执行规则建议：若 MD 目录只有 PDF 且无 mdp/top/tpr/xtc/log/xvg/csv，则自动标记 CRITICAL 待AI复核。

## 错题 2：方法标题中的并列方法必须逐项有交付证据
- 错误类型：GSVA 方法声明无证据。
- 具体表现：标题写“GSEA和GSVA”，但结果、代码、包清单只有 GSEA。
- 触发场景：报告方法标题包含多个方法名，结果章节只展开其中一个。
- 证据依据：report_text.txt:18-19；script/r.02_GSEA.r 未加载 GSVA/psych；mechanical MC-010。
- 正确标准：标题、方法、代码包、结果目录和图表必须逐项对应。
- 下次审核提醒：不要因 GSEA 存在就放过 GSVA。
- 严重程度：MAJOR。
- 可执行规则建议：报告含 GSVA 但包/函数/结果文件均无 GSVA/gsva/ssGSEA 时，至少 MAJOR。

## 错题 3：参考文献编号不能只检查“存在”，还要检查主题和方法匹配
- 错误类型：外项目/模板文献残留。
- 具体表现：[3] 用于 psych/Spearman 方法，却对应抗生素畜牧废水残留综述。
- 触发场景：模板化报告自动插入引用。
- 证据依据：report_text.txt:19 与 report_text.txt:74。
- 正确标准：每个方法引用应与软件包/算法/数据库主题一致。
- 下次审核提醒：至少抽查所有方法段编号对应的参考文献题名。
- 严重程度：MAJOR。
- 可执行规则建议：方法段引用的文献题名出现与项目主题无关的疾病/环境/动物等关键词时进入AI复核。
