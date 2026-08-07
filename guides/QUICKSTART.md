# 审核框架 Quickstart

> Generated from `policy/audit_policy.json + scripts/generate_policy_docs.py`
> Source of truth: `result_review_framework/policy/audit_policy.json`
> Framework version: `v7.1`
> Policy updated at: `2026-08-04`
> Do not hand-edit this file; re-run `python result_review_framework/scripts/generate_policy_docs.py`

## 1. 运行预检查

```powershell
python result_review_framework/scripts/auto_audit_pipeline.py "raw/待审核/<项目目录>" --project-type <类型>
```

输出：`report_text.txt`、`report_structure.json`、`project_structure.json`、`mechanical_check_result.json`、`case_manifest.json`、`visual_audit_checklist.json`、`visual_prefilter.json`。

## 2. 生成 AI 围栏

```powershell
python result_review_framework/scripts/prepare_ai_audit_guardrails.py result_review_report/<项目编号>
```

输出：`ai_execution_manifest.json`、`audit_state.json`、`agent_prompts/*`。

## 3. 收集三路 agent 结果并收敛

先读取 `agent_prompts/agent_slice_manifest.json`，按 `agent_prompts/slices/*.md` 分批启动小切片 subagent（每批 2-4 个）。

硬要求：
- Lead 是监工/整合者，不是全文审核执行者；不得在主线程直接展开长报告、长日志、完整清单或大证据。
- 正式审核证据由 subagent 落盘，Lead 只读取短状态、证据路径、计数和最终必要片段，防止 leader 上下文被塞满。
- Sub-Agent 聊天回传最多 5 行：状态、输出路径、发现数量、最高严重度、阻断项；完整报告、JSON、长日志或大表只写文件。
- Lead 最终回复最多 8 行；正式审核完成通知只保留状态、时间、项目、报告文件、审核结果和问题统计。
- 不要 fork/copy leader 的完整上下文给子代理。
- 小切片不等于弱模型：正式判断型切片必须使用与主 agent 相同的模型；如主 agent 为 high reasoning，判断型子代理也必须 high。
- fast/mini 只用于文件定位、清单、schema、grep；不得单独裁定严重度、统计适用性、高风险模块或最终仲裁。
- 每个判断型切片必须保留重叠上下文：摘要/结论、Figure/Table 索引、机械检查摘要、case_manifest、相邻依赖模块。
- 每个切片只读自己的 prompt、指定路径和必要局部证据；若触发 remote compact/context loss，必须按章节、模块、图号范围、文件组或问题簇继续拆分后重试。
- 每个切片必须把完整 JSON 写入 `agent_results/slices/`，聊天只返回状态、路径、数量和 blocker。
- 每批完成后将状态写入 `review_event_log.jsonl`，并更新项目内 `subagent_supervision_summary.json`。

切片全部落盘后，Lead 先复核覆盖缺口、slice 冲突、跨模块链条断裂、局部通过但整体不成立、未分配高风险模块，再运行收敛：

```powershell
python result_review_framework/scripts/convergence_compare.py result_review_report/<项目编号>
```

输出：`convergence_report.json`、`convergence_report.md`、`arbitration_queue.json`。

## 4. 准备、封存并完成最终交付

```powershell
python result_review_framework/scripts/prepare_audit_finalize.py result_review_report/<项目编号>
# Lead 确认并写入 final_decision.json 后：
python result_review_framework/scripts/validate_professional_contracts.py result_review_report/<项目编号>
python result_review_framework/scripts/validate_audit_contract.py result_review_report/<项目编号>
python result_review_framework/scripts/finalize_audit.py result_review_report/<项目编号>
```

输出：`final_review_report.md`、`final_decision.json`、`professional_contract_validation.json`、`audit_contract_validation.json`、`completion_notification_receipt.json`、`audit_state.json`、`<项目编号>_audit_report.html`，并默认移动项目到已审核目录。

## 5. 归档硬门禁

`finalize_audit.py` 不再支持只发布不移动。HTML 发布成功后必须自动移动到 `raw/已AI审核一次`，否则本次 finalize 失败。

## 6. 错题集闭环

- 审核前读取 `lessons/LESSONS_LEARNED.md` 和 `lessons/patterns/`，将相同或相近历史错误列为重点复核项。
- 审核后把本次典型错误点、触发场景、证据依据、正确标准、下次审核提醒和规则建议写回 `lessons/`。
- 规则建议若已明确且证据充分，直接同步到对应 `patterns/`、索引或政策文档；证据不足才标注待复核。
- 历史错题只提示风险；必须结合当前项目证据独立判断，不能机械套用历史结论。

## 7. 代码交付严重度口径

- 单纯未交付代码 / 未发现代码文件 / 代码不可复现风险只按 WARNING 记录。
- 不得仅因无代码升级为 CRITICAL，也不得把无代码作为唯一不通过原因。
- 错误项目路径、方法参数矛盾、核心统计错误、结论无证据或数据链断裂按实质问题独立升级。

## 关键规则

- 默认 `strict` lane；只有显式选择时才切换其他 lane。
- 不要在封存后修改报告；修复必须通过 `prepare_audit_finalize.py` 在 `final_decision.json` 确认前完成。
- 旧项目若缺少 policy SHA，只能显式运行 `prepare_ai_audit_guardrails.py <review_dir> --rebuild-policy-binding` 后重新生成围栏；不得自动补写或静默换版。
- HTML 生成失败时，不允许归档。
- finalize 成功必须同时满足 `publish_status=success` 且 `archived_at` 已写入。
- 不允许使用 `--no-auto-archive`；如归档失败，修正 manifest/源路径后重跑 `finalize_audit.py` 或 `archive_reviewed_project.py --approve`。
- 参考文献后的公司宣传页默认不纳入正式审核；不要因为宣传附页里的“分子对接/分子动力学”等词触发问题。
