# 26YSH012F wrong_question_set

## WQ-01 MUC16/MUC6 核心目标基因漂移
- 错误类型：核心研究对象/基因名混用。
- 具体表现：报告关注 MUC16/MUC1/CEACAM5，但 KEGG/TF 方法段写 MUC6，交付存在 MUC6_promoter.fa。
- 触发场景：相近基因名、上游 promoter/TF 文件与下游结果表来自不同对象。
- 证据依据：report_text.txt L16/L18/L20/L47；3 KEGG/KEGG_venn.csv；4 TF/MUC6_promoter.fa。
- 正确标准：方法、输入、结果图表、结构化表必须使用同一目标基因集合。
- 下次审核提醒：对 MUC1/MUC6/MUC16、S100a1/S100a11 等相近基因名必须跨文件核对。
- 严重程度：CRITICAL。
- 规则建议：新增“相近基因名漂移”检查，扫描方法段目标基因、结果表列名、文件名和FASTA header。

## WQ-02 DEG计数与结构化表数量级冲突
- 错误类型：核心统计数字错误。
- 具体表现：正文276/79/197，结构化表和火山图为3897/1907/1990。
- 触发场景：报告复用旧数字或截图更新后正文未同步。
- 证据依据：report_text.txt L62；5 DEG/DEG_Tumor VS Control_p.adjust_logFC0.585.csv。
- 正确标准：正文、图注、结构化表的阈值和计数必须一致。
- 下次审核提醒：DEG表必须按报告阈值复算行数和regulated计数。
- 严重程度：CRITICAL。
- 规则建议：将 DEG count checker 扩展到 “*_p.adjust_logFC*.csv” 文件名自动复算。

## WQ-03 药物对象“槐耳/苍耳”残留
- 错误类型：药物/疾病对象 copy-paste 残留。
- 具体表现：槐耳项目方法段写“苍耳”的靶点基因。
- 触发场景：同类中药网络药理报告复用模板。
- 证据依据：report_text.txt L7/L16。
- 正确标准：标题、方法、结果、目录中的药物对象必须一致。
- 下次审核提醒：中文药名错字/近形名需和项目题名做全文比对。
- 严重程度：CRITICAL。
- 规则建议：将项目名关键词与正文药物名做负向词残留扫描。
