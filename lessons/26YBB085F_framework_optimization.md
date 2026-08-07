# 26YBB085F 审核框架优化建议

生成时间：2026-05-22T15:26:24

## 本案暴露的框架短板

1. visual_prefilter 的 project_id_mismatch 未捕捉报告正文首页的 26YBB087F。
2. 重复图检测已有信号，但未自动升级“同图不同对象/不同标题”的语义风险。
3. 机械检查把 GSE206528 误归为“报告/rawdata均未提及”，实际应是“报告提及但原始输入缺失”。
4. convergence_compare 低收敛时能产出仲裁队列，但最终报告仍需要人工式整合；可生成更好的 route-level 汇总草稿。
5. finalize 通知字段对严重度统计格式敏感，FATAL 进入统计前缀时会阻止正式通知。
6. audit_state 将 no-op autofix/backfill 文件视为阶段必要产物，lint 已通过时仍需生成空计划才能 completed。
7. figure_audit.md 模板 模板占位 若视觉分片已覆盖，仍会阻塞状态机。

## 建议优化 1：项目号一致性规则升级

- 新规则：扫描 report_text、顶层文件名、脚本 setwd/绝对路径、case_manifest、通知元数据中的项目号。
- 触发条件：出现非当前项目号，且位于封面/脚本路径/顶层交付文件名。
- 建议严重度：FATAL。
- 自动处置：写入 mechanical_check_result，且必须进入 final_review_report 核心问题。

## 建议优化 2：高风险模块空目录与强结论联动

- 新规则：当 report_text 出现 Docking、molecular dynamics、GROMACS、RMSD、RMSF、Rg、binding energy 等词，且对应模块文件数为 0 或仅有占位脚本。
- 建议严重度：CRITICAL/FATAL；若同时存在定量结论则 FATAL。
- 自动输出：高风险模块表中 module_exists/evidence_sufficient/reproducible/conclusion_not_overstated 四维布尔。

## 建议优化 3：重复图语义升级

- 新规则：重复图片 hash 相同且相邻图题中的基因/药物/细胞类型不同，自动生成“重复图/错图” finding。
- 建议严重度：CRITICAL。
- 补充字段：duplicate_hash、image_paths、caption_entities、entity_conflict=true。

## 建议优化 4：数据集提及与原始输入闭环分层

- 当前误区：只判断报告是否提及 GEO。
- 新分类：
  - A：报告未提及但 rawdata 出现。
  - B：报告提及但 rawdata 缺失。
  - C：报告与 rawdata 均出现但脚本输入缺失。
  - D：报告、rawdata、脚本输入三者闭环。
- 本案应归 B/C，而不是“未报告”。

## 建议优化 5：ML 标签顺序审计模板化

- 新规则：对 R/Python 中手写 group/label/factor/class 赋值做静态检查；与 group 文件行数、表达矩阵列数和样本顺序交叉核对。
- 高风险模式：rep(0,n)/rep(1,n) 与 group 文件顺序不一致；训练/验证标签未分开；SVM/LASSO/RF 复用同一错误标签。
- 建议严重度：CRITICAL。

## 建议优化 6：最终通知字段预检

- 新脚本建议：preflight_audit_notification_fields.py。
- 检查项：项目号、审核文件、报告文件、审核结果、CRITICAL/MAJOR/WARNING 三项统计均可解析。
- 运行时机：final_report_linter 之后、ensure_review_html 之前。
- 失败输出：明确指出是哪一行格式不可解析，避免归档后通知阻塞。

## 建议优化 7：已通过 lint 时自动生成 no-op 阶段记录

- 现象：lint passed=True，但 audit_state 仍阻塞在 autofix_plan_ready/backfill。
- 优化：sync_audit_state 若检测 lint passed=True 且 no-op 文件缺失，可自动写入空计划/空应用记录，或将这些阶段标记为 skipped。
- 预期效果：减少 finalize 后仍需手动补 no-op 文件的流程摩擦。

## 建议优化 8：figure_audit.md 与视觉分片联动

- 现象：视觉分片已完成，但 figure_audit.md 仍有模板 模板占位，状态机认为视觉未完成。
- 优化：如果 agent_b_b02_result.json 已完成且 final_review_report 已纳入视觉问题，自动替换 figure_audit 模板占位 为“由视觉分片覆盖”的闭环说明。
- 预期效果：避免模板占位误阻塞 completed 状态。

## 建议加入框架回归用例

- 用例 1：报告封面项目号与目录项目号不一致，期望 FATAL。
- 用例 2：Docking/MD 目录为空但报告有 GROMACS 结论，期望阻断。
- 用例 3：三张相同图片对应不同 caption entity，期望 CRITICAL。
- 用例 4：报告提及 GSE206528 但 rawdata 缺少 GSE206528_RAW，期望“原始输入缺失”而非“未报告”。
- 用例 5：严重度统计包含 FATAL 但缺 CRITICAL/MAJOR/WARNING 可解析字段，期望通知预检失败并给出修复建议。

## 优先级

- P0：项目号一致性、Docking/MD 空目录强结论、通知字段预检。
- P1：重复图语义升级、数据集闭环分层、ML 标签顺序审计。
- P2：no-op 阶段记录自动化、figure_audit 模板占位 自动闭环。

## 本案状态参照

- lint passed：True，errors=0，warnings=0。
- audit_state：current_phase=completed，all_completed=True。
- convergence：{'consensus_rate': 2.7, 'majority_rate': 13.5, 'single_rate': 83.8, 'divergent_rate': 0.0}。
