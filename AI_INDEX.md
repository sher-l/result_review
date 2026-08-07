# AI 使用索引

> Generated from `policy/audit_policy.json + scripts/generate_policy_docs.py`
> Source of truth: `result_review_framework/policy/audit_policy.json`
> Framework version: `v7.1`
> Policy updated at: `2026-08-04`
> Do not hand-edit this file; re-run `python result_review_framework/scripts/generate_policy_docs.py`

## AI 审核员先读什么

1. `policy/audit_policy.json`
2. `README.md`
3. `MASTER_PROMPT.md`
4. `CORE_RULES.md`

## 正式审核路径

1. `scripts/auto_audit_pipeline.py`
   Extract report/project structure, build case_manifest, run mechanical checks, prepare visual audit assets.
2. `scripts/prepare_ai_audit_guardrails.py`
   Generate AI execution manifest, prompts, and audit state baseline.
3. `agent_prompts/agent_slice_manifest.json`
   Launch small, bounded slice subagents in batches; every slice writes JSON to agent_results/slices/.
4. `scripts/convergence_compare.py`
   Validate slice JSONs, build traceable candidate clusters, and emit arbitration artifacts.
5. `scripts/prepare_audit_finalize.py`
   Run local lint/autofix/backfill before the leader seals final_decision.json; never notify or archive.
6. `scripts/validate_professional_contracts.py`
   Validate arbitration v2 and the policy-owned professional artifacts; domain observations remain candidates.
7. `scripts/validate_audit_contract.py`
   Validate the sealed decision, source hashes, counts, and mode-aware blocking.
8. `scripts/finalize_audit.py`
   Verify sealed artifacts without rewriting them, publish HTML, send at most once, and auto archive.
9. `scripts/archive_reviewed_project.py`
   Manual recovery command for already-published review dirs when archive state must be repaired.
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


## AI 输出协议

- finding 需要完整结构化字段，并且必须带 `finding_key`。
- `mechanical_check_result.json` 只能作为候选问题，不能直接当最终结论。
- 高风险模块必须拆成 4 个维度判断：`module_exists` / `evidence_sufficient` / `reproducible` / `conclusion_not_overstated`。
- `CRITICAL/FATAL` finding 如果证据字段不完整，必须进入 `arbitration_queue.json`。

## 错题集闭环

- 审核前读取 `lessons/LESSONS_LEARNED.md` 和 `lessons/patterns/`，把相同或相近内容列为重点复核项。
- 审核后将典型错误点、触发场景、证据依据、正确标准、下次审核提醒和规则建议沉淀到 `lessons/`。
- 错题集只提供风险提示；后续项目必须结合当前证据独立判断，不能机械套用历史结论。
- 若规则建议已明确且证据充分，直接同步更新对应 `patterns/`、索引或政策文档，不只留待办。

## 发布与归档

- 发布状态写入 `case_manifest.json.publish_status`。
- 归档状态写入 `case_manifest.json.archive_approved` 与 `archived_at`。
- `ensure_review_html.py` 只负责 HTML 生成，不单独承担归档。
- `finalize_audit.py` 只验证封存产物，不再自动改写最终报告；发布成功后自动调用 `archive_reviewed_project.py`。
- `archive_reviewed_project.py` 仅作为正式 finalize 后的手动回补命令；没有当前正式交付清单、学习产物和匹配的 sent 通知收据时必须拒绝归档。
