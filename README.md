# 结果审核框架

> Generated from `policy/audit_policy.json + scripts/generate_policy_docs.py`
> Source of truth: `result_review_framework/policy/audit_policy.json`
> Framework version: `v7.1`
> Policy updated at: `2026-08-04`
> Do not hand-edit this file; re-run `python result_review_framework/scripts/generate_policy_docs.py`

## 当前主线

正式审核只认下面这条流水线：

1. `scripts/auto_audit_pipeline.py`
   Precheck: Extract report/project structure, build case_manifest, run mechanical checks, prepare visual audit assets.
2. `scripts/prepare_ai_audit_guardrails.py`
   Guardrails: Generate AI execution manifest, prompts, and audit state baseline.
3. `agent_prompts/agent_slice_manifest.json`
   Slice Agents: Launch small, bounded slice subagents in batches; every slice writes JSON to agent_results/slices/.
4. `scripts/convergence_compare.py`
   Convergence: Validate slice JSONs, build traceable candidate clusters, and emit arbitration artifacts.
5. `scripts/prepare_audit_finalize.py`
   Prepare Final: Run local lint/autofix/backfill before the leader seals final_decision.json; never notify or archive.
6. `scripts/validate_professional_contracts.py`
   Professional Gate: Validate arbitration v2 and the policy-owned professional artifacts; domain observations remain candidates.
7. `scripts/validate_audit_contract.py`
   Contract Gate: Validate the sealed decision, source hashes, counts, and mode-aware blocking.
8. `scripts/finalize_audit.py`
   Finalize: Verify sealed artifacts without rewriting them, publish HTML, send at most once, and auto archive.
9. `scripts/archive_reviewed_project.py`
   Archive Fallback: Manual recovery command for already-published review dirs when archive state must be repaired.
## 报告附页口径

- 参考文献后的公司宣传页默认视为交付 boilerplate，不纳入正式审核范围。
- 默认识别标记：公司介绍 / 服务领域 / 联系我们
- 只有当这些内容出现在参考文献前的正式正文中，或污染编号章节时，才升级为实质问题。

## 图件交付格式

- 结果图件可以仅交付可渲染 PDF；不再因缺少 PNG 单独记问题。仅有 PNG/JPG 等位图且无 PDF 时记录 WARNING 或说明例外。文件不可渲染、损坏、错图或影响复核时仍按内容问题升级。若同一图件同时存在可读的 PDF、PPTX 或 SVG，单个派生 PNG 异常不得被表述为“图件/流程图不可读”；只有交付规范明确要求该派生格式时，才可单列为格式兼容性问题。

## 代码交付严重度口径

- 单纯未交付代码 / 未发现代码文件 / 代码不可复现风险：`WARNING`。
- 不得仅因无代码把问题升级为 CRITICAL，也不得把无代码作为唯一不通过原因。
- 若同时存在错误项目路径、方法参数矛盾、核心统计错误、结论无证据或数据链断裂，应按这些实质问题独立升级。

## 结构化完成契约

- `final_decision.json` 是分数、结论和发布决定的唯一来源；当前门禁模式：`enforce`。
- `prepare_audit_finalize.py` 只能在封存前修复报告；正式 finalize 不得改写已确认 source。
- 视觉闭环写入 `visual_audit_result.json`，所有范围内资产必须守恒且无未入账项。
- `formal_delivery_manifest.json` 必须绑定封存后的 `final_decision.json`、最终 Markdown、HTML 与视觉闭环；任一文件缺失、变化或未完成都不得发送或归档。
- 完成通知收据写入 `completion_notification_receipt.json`；匹配的 sent 收据禁止重复发送。
- `case_manifest.json` 与 `ai_execution_manifest.json` 必须绑定当前 policy 原始字节的 `sha256`；禁止静默换版。
- 测试、回归、shadow replay、smoke 和 dry-run 禁止任何真实通知网络调用。
- 专业契约产物：`dataset_scope_matrix.json`、`statistical_flow_graph.json`、`method_code_matrix.json`、`ml_lineage.json`。
- 专业契约验证写入 `professional_contract_validation.json`；shadow 只暴露 would-block，enforce 才阻断。
- `leader_confirmed` 后，每个正式 F-ID 必须唯一绑定 retained canonical finding；reject/revoked 原始发现不得进入正式问题链。
- 相同 `error_mechanism + repair_path` 即使定位不同也必须归并；保留为独立问题时必须提交差异维度和双方独立证据。
- 旧项目迁移只能显式使用 `--rebuild-policy-binding`，并保留旧版本与旧 SHA 记录。
- 专业机械检查只生成 candidate；严重度、实际污染和科学结论由仲裁决定。

## Sub-Agent 质量门禁

- 正式审核默认采用“Lead 监工/整合 + Sub-Agent 分片审核”模式；Lead 不直接吞入长报告、长日志、完整文件清单或大证据。
- Sub-Agent 必须把完整证据落盘，Lead 只读取短状态、证据路径、计数和最终必要片段，避免 leader 触发 remote compact。
- Sub-Agent 聊天回传最多 5 行，只允许状态、输出路径、发现数量、最高严重度和阻断项；完整 Markdown/JSON/长日志/大表必须落盘，不得贴回主线程。
- Lead 最终回复最多 8 行；正式审核完成通知只保留状态、时间、项目、报告文件、审核结果和问题统计，不贴任务类型、任务名称、摘要、workspace、内部路径或监督 JSON 元数据。
- 小切片只用于控制上下文和防 remote compact，不允许降低正式审核判断能力；若子代理触发 remote compact/context loss，必须继续拆分切片后重试，禁止原范围重跑。
- 正式判断型切片必须使用与主 agent 相同的模型；如主 agent 为 high reasoning，判断型子代理也必须 high；fast/mini 只用于文件定位、清单、schema、grep 类任务。
- 严重度、跨模块一致性、统计适用性、高风险模块和最终仲裁不得由弱模型单独裁定。
- 判断型切片必须保留重叠上下文：摘要/结论、Figure/Table 索引、机械检查摘要、case_manifest、相邻依赖模块。
- Lead 最终必须复核覆盖缺口、slice 冲突、跨模块链条断裂、局部通过但整体不成立、未分配高风险模块。


## 核心约束

- 统一事实底座：每个项目必须生成 `case_manifest.json`。
- 统一事件留痕：每个阶段都写 `review_event_log.jsonl`。
- 统一问题主键：每条 finding 必须带 `finding_key`。
- 统一收敛出口：三路收敛必须产出 `convergence_report.*` 和 `arbitration_queue.json`。
- 统一收口：先通过 `prepare_audit_finalize.py` 完成本地修复并由 Lead 封存 `final_decision.json`，再运行 `finalize_audit.py`。
- 强制自动归档：`finalize_audit.py` 在 HTML 发布成功后必须移动项目到 `raw/已AI审核一次`；不再支持 `--no-auto-archive`，归档失败则 finalize 失败。

## 错题集闭环

- 审核前必须读取 `lessons/LESSONS_LEARNED.md` 和 `lessons/patterns/`，把命中的相同或相近内容列为重点复核项。
- 审核后必须把本次典型错误点沉淀到 `lessons/`；建议更新位置：LESSONS_LEARNED.md、LESSONS_LEARNED_<项目编号>.md、patterns/*.md。
- 单条错题至少记录：错误类型 / 具体表现 / 触发场景 / 证据依据 / 正确标准 / 下次审核提醒 / 严重程度 / 规则建议。
- 后续审核其他项目时，错题集只作为风险提示；必须结合当前项目证据独立核验，不能机械套用历史结论。
- 错题集中的规则建议如果已可执行，必须直接更新对应模式库、索引或政策文档；证据不足时才标注待复核。

## 视觉审核

- 当前默认：`review_lane=strict`。
- `review_lane=standard`：仅高风险图件或机器预筛标红图件进入 AI逐图复核。
- `review_lane=strict`：所有非装饰图进入 AI逐图复核。
- 图件交付格式：PDF-only 可接受；PNG/JPG-only 且无 PDF 时才按格式缺失提示。
- 机器预筛当前覆盖：完全重复图、OCR 检出的外项目编号、明显错图、疑似字体风格不一致。

## 必交付件

- `case_manifest.json`
- `review_event_log.jsonl`
- `coverage_matrix.md`
- `fact_check_list.md`
- `unresolved_items.md`
- `convergence_report.json`
- `convergence_report.md`
- `arbitration_queue.json`
- `final_review_report.md`
- `subagent_supervision_summary.json`
- `subagent_supervision_gate.json`
- `wrong_question_set.md`
- `framework_optimization_notes.md`
- `final_report_lint.json`
- `audit_state.json`
- `<project_id>_audit_report.html`

## 参考文档

- `README.md` / `AI_INDEX.md`：入口与路径说明
- `guides/QUICKSTART.md`：执行步骤
- `guides/QUICK_REFERENCE.md`：速查表
- `guides/IMAGE_ANALYSIS_ROADMAP.md`：视觉审核演进方向
