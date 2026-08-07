# 26YBB028F wrong_question_set

| 典型错误 | 触发场景 | 证据依据 | 正确标准 | 下次审核提醒 | 严重度 | 可执行规则建议 |
|---|---|---|---|---|---|---|
| 项目单号与当前审核对象不一致 | 报告复用模板或跨项目复制 | report_text.txt L6 写 26YSH028F，当前为 26YBB028F | 报告、文件名、manifest、结果路径必须同一项目编号 | 首先全文检索非当前项目 ID | FATAL | 若正文或页眉出现外来项目编号，自动 FATAL 并加入仲裁队列 |
| MD xvg 头部暴露外来 Working dir | 复用其他项目 MD 后处理输出 | xvg L7 指向 26YSH028F-HSP90AA1/MD_run | 高风险模拟输出必须为当前项目专属并可追溯 | 检查 xvg/pdb/log 头部路径 | FATAL | 对 .xvg/.log/.pdb 头部路径执行项目 ID 一致性扫描 |
| 高风险模块只交图件不交运行链条 | 对接、MD、虚拟敲除 | total_code_files=0，缺 mdp/top/tpr/xtc/log 和 scTenifoldKnk 输入 | 高风险结论必须有脚本、参数、输入、日志和结构化输出 | 不把“有结果图”当作可复现 | FATAL | 若 docking/MD/knockout 命中但缺脚本/参数/输入，至少 CRITICAL；叠加外来路径升 FATAL |
| 病原术语误写为病毒 | 细菌感染单细胞项目 | A. pleuropneumoniae 被写作病毒 | 胸膜肺炎放线杆菌应表述为细菌/病原菌 | 审核题名、摘要、结果解释一致性 | MAJOR | 建立常见病原中文/拉丁名术语表 |
| GeneRatio 被电子表格日期化 | Excel 打开富集 CSV 后保存 | 5月9日、4月9日 | 富集比例应保持 5/9 等分数字符串 | 读取 CSV 原始字段而非截图 | MAJOR | 检测 GeneRatio 日期格式并提示重新导出 |



# 26YBB028F framework_optimization_notes

## 应收紧的策略

1. 项目身份扫描应覆盖正文、页眉页脚、docx XML、xvg/log/pdb 头部路径和所有结果目录路径；命中外来项目编号时直接进入 FATAL 仲裁。
2. 高风险模块策略应把 docking、MD、scTenifoldKnk 拆成独立门禁：脚本/参数/输入/日志/结构化输出至少五类证据，缺失两类以上不得给通过结论。
3. 视觉审核提示词需强制核对图号-文件名-正文引用-图注四元一致，特别是多面板图 C/D、E/H 的重复标注。
4. 统计审核提示词需强制要求 AUC、t 检验、多重校正、效应量和样本量的结构化证据，不接受仅 PDF 图件支持关键选择。
5. 术语审核需加入常见病原类型词典，避免将 Actinobacillus pleuropneumoniae 写作病毒。

## 本次无需新增依赖

以上优化均可通过现有文本/路径扫描、subagent prompt 收紧和 linter 规则增强实现，无需新增第三方依赖。
