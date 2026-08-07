# 25YHB409F wrong_question_set

## 典型错题 1：不要把自动参考文献错配候选直接升级为 CRITICAL
- 触发场景：自动检查按内部解析显示 OMIM/CTD/STRING/PubChem/CB-DOCK2 串号。
- 证据依据：Lead 复核 `report_text.txt L140-L162` 后，正文编号与参考文献条目一致。
- 正确标准：自动预检查只能作为候选；CRITICAL 必须有AI复核的原文编号、条目和上下文证据。
- 下次提醒：先核对参考文献原文行，再写最终严重度。
- 严重度：流程错题，防误报。
- 可执行规则建议：参考文献错配进入 final 前必须生成“正文编号→参考文献条目”核对表。

## 典型错题 2：高风险 MD/对接不能只看有图有表
- 触发场景：12_Docking 有结合能和 PNG/PDB，13_Dynamic 有 PDF/xvg。
- 证据依据：缺少 CB-DOCK2/Gromacs 输入、参数、日志、命令脚本；MD还缺 Il10 分支。
- 正确标准：高风险模块需模块存在、证据充分、可复现、结论不过度外推四维同时判断。
- 下次提醒：对接/MD 必查输入结构、参数、日志、脚本、轨迹/拓扑。
- 严重度：MAJOR。
- 可执行规则建议：finalizer 前检查 12_Docking/13_Dynamic 是否存在 mdp/tpr/top/log/trajectory/docking task metadata。

## 典型错题 3：比较组标签错误会污染后续网络链条
- 触发场景：PICRUSt2 报告写模型组 vs 对照组，但文件为 C VS B。
- 证据依据：`DEG_C VS B_p.adjust_logFC1.csv` 与代码 `Group %in% c('B','C')`。
- 正确标准：差异通路、共有通路、关键代谢物网络必须沿用真实比较组。
- 下次提醒：所有 DEG/通路文件名与正文比较组逐项核对。
- 严重度：MAJOR。
- 可执行规则建议：新增比较组文件名/列名/正文三方一致检查。
