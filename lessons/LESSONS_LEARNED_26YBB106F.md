# 26YBB106F 框架级复用教训

> 生成时间：2026-07-02T17:00:19
> 项目：单细胞+转录组+激酶-谷氨酰胺代谢+结直肠癌
> 审核结论：不建议提交

## WQ-001 跨疾病模板残留污染核心方法

- 错误类型：Copy-paste residue / 外项目疾病残留。
- 具体表现：结直肠癌项目 WGCNA 方法段写入“急性心肌梗死矩阵TOP10000基因”。
- 触发场景：报告同一句先写 GSE156915 训练集，随后出现其他疾病矩阵来源；机械检查 MC-006 与 A/B/C 多切片均命中。
- 证据依据：`report_text.txt` L31；`mechanical_check_result.json` MC-006；`agent_results/slices/agent_a_a01_result.json`、`agent_b_b01_result.json`、`agent_b_b03_result.json`、`agent_c_c02_result.json`。
- 正确标准：核心方法段的数据来源必须与项目疾病、Table 1 数据集和结果文件一致；外疾病名进入方法输入描述时按 CRITICAL 以上处理。
- 下次审核提醒：全文检索疾病名、GSE、TCGA 缩写和“TOP10000矩阵”等模板短语；命中后必须判断是否污染核心数据来源。
- 严重程度：CRITICAL。
- 可执行规则建议：在复制粘贴残留检查中将“急性心肌梗死/心肌梗死矩阵/TOP10000基因”与非心血管项目的共现列为高风险命中。

## WQ-002 高风险 MD 模块只有后处理图，缺少原始运行包

- 错误类型：高风险计算证据链断裂。
- 具体表现：报告声称 Gromacs 2022、100 ns、AMBER99SB-ILDN、sobtop、TIP3P、NVT/NPT，并给出稳定性/FEL 结论；交付仅 9 个 Matplotlib PDF。
- 触发场景：分子动力学报告写完整模拟参数但目录缺 `mdp/top/itp/gro/pdb/tpr/xtc/trr/edr/log/xvg`、命令、配体参数。
- 证据依据：`report_text.txt` L49-L52、L184-L210；`project_structure.json` 模块11；`agent_c_c03_result.json`。
- 正确标准：100 ns MD 结论至少应有参数文件、拓扑/结构、轨迹或可复核导出、日志和分析脚本；只有 PDF 不足以支撑强稳定性结论。
- 下次审核提醒：不要把“图能打开”当作 MD 通过；优先查运行包和轨迹链路。
- 严重程度：CRITICAL。
- 可执行规则建议：MD 模块若只有 PDF 且无轨迹/参数/日志，自动进入高风险仲裁。

## WQ-003 对接结合能表不足且图文残基不一致

- 错误类型：分子对接证据不足 + 图文事实冲突。
- 具体表现：分子对接仅有三列表和展示 PDF，缺 receptor/ligand 输入、pose、grid、平台原始输出；图10C正文称 NEK2 ARG-296，但图片标注为 LEU-82/LYS-37/VAL-85 等。
- 触发场景：报告给结合能阈值和氢键残基，却没有原始 pose 或日志；图中文字与报告残基不一致。
- 证据依据：`report_text.txt` L168-L182；`10-分子对接/分子对接.xlsx`；`result_review_report/26YBB106F/images/image_050.png`；`agent_b_b02_result.json`、`agent_c_c03_result.json`。
- 正确标准：对接结论需能追溯输入结构、参数、pose 与原始评分；残基描述必须与图件一致。
- 下次审核提醒：对接不是只核对结合能表；必须抽查图中残基标签。
- 严重程度：CRITICAL。
- 可执行规则建议：图注/正文出现“残基”时抽样 OCR 或视觉核对 residue label。

## WQ-004 inferCNV 恶性和侵袭性结论过度外推

- 错误类型：统计/生物学结论过强。
- 具体表现：报告称所有上皮亚群均为恶性，cluster1/3/4/5 更侵袭；但 `cnv_scores_summary.csv` 仅给 summary，cluster3/5 均值低于部分其他簇，缺阈值、p值和侵袭性证据。
- 触发场景：从 CNV 热图或 summary 直接推断恶性/侵袭性，不提供阈值、参考细胞、统计检验或外部验证。
- 证据依据：`report_text.txt` L280；`21-拷贝数变异的推断/cnv_scores_summary.csv`；`agent_b_b01_result.json`、`agent_c_c03_result.json`。
- 正确标准：inferCNV 可作为恶性推断线索，但“所有都是恶性”“更具侵袭性”需阈值、统计和独立生物学证据支撑。
- 下次审核提醒：区分“CNV score 较高”与“侵袭性表型”；后者不能从图色直接推出。
- 严重程度：CRITICAL。
- 可执行规则建议：凡出现“侵袭性/恶性表型”需强制查结构化 score、阈值和统计检验。

## WQ-005 验证集 AUC 结论段反写

- 错误类型：数值事实/结论摘要不一致。
- 具体表现：验证章节承认 1 年 AUC 不达标，结论却写 1、3、5 年 AUC 均 >0.6。
- 触发场景：正文局部描述与最终结论摘要不一致；图中 AUC=0.512 被总结段覆盖。
- 证据依据：`report_text.txt` L254、L303；`18-验证预后模型/GSE72969_ROC_plot_test.pdf`；`agent_b_b01_result.json`、`agent_c_c02_result.json`。
- 正确标准：最终结论必须保留验证集不足，不得把局部达标扩写为全部达标。
- 下次审核提醒：审核最终结论段时回查每个关键数值，尤其外部验证 AUC/C-index/CI。
- 严重程度：MAJOR。
- 可执行规则建议：对“均大于/全部/所有”类总结词做数值反查。


## 框架优化摘要

# 26YBB106F 框架优化记录

> 生成时间：2026-07-02T17:00:19

## 本次应强化的框架点

1. **复制粘贴残留检查**：非心血管/非AMI项目中出现“急性心肌梗死矩阵TOP10000基因”应作为核心方法污染高风险项，而不是普通文本残留。建议强化 `copy_paste_residue` 模式和 MC-006 词库。
2. **MD 高风险模块证据门槛**：报告声明 Gromacs/100 ns/力场/水模型/NVT/NPT 时，必须检查 `mdp/top/itp/gro/pdb/tpr/xtc/trr/edr/log/xvg` 或等价原始运行包；仅 PDF 默认为证据不足。
3. **对接图文一致性**：结合能表不足以通过，应抽查残基标签与正文是否一致。
4. **inferCNV 结论强度**：恶性/侵袭性表述需阈值、统计检验或外部证据；仅 summary/热图应降格。
5. **结论段数值反查**：最终结论中的“均>阈值/全部显著”等需与图表和结构化结果逐项一致。

## 已执行动作

- 项目内写入 `wrong_question_set.md`，覆盖典型错误、证据、正确标准和规则建议。
- 项目内写入本文件，明确需强化的检查器/提示词。
- 框架级复用教训写入 `result_review_framework/lessons/LESSONS_LEARNED_26YBB106F.md`。

## 暂不改动项

- 未直接修改 `policy/audit_policy.json` 或检查器代码；本次为正式审核任务，避免扩大为框架维护变更。
- 对 `patterns/*.md` 暂不做自动规则化改写；建议框架维护时把上述 5 条合并进对应模式库。
