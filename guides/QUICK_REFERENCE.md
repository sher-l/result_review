# 审核框架 Quick Reference

> Generated from `policy/audit_policy.json + scripts/generate_policy_docs.py`
> Source of truth: `result_review_framework/policy/audit_policy.json`
> Framework version: `v7.1`
> Policy updated at: `2026-08-04`
> Do not hand-edit this file; re-run `python result_review_framework/scripts/generate_policy_docs.py`

## 主命令

| 阶段 | 命令 |
|---|---|
| Precheck | `python result_review_framework/scripts/auto_audit_pipeline.py <project_dir> --project-type <类型>`（默认 strict） |
| Guardrails | `python result_review_framework/scripts/prepare_ai_audit_guardrails.py <review_dir>` |
| Convergence | `python result_review_framework/scripts/convergence_compare.py <review_dir>` |
| Prepare Final | `python result_review_framework/scripts/prepare_audit_finalize.py <review_dir>` |
| Professional Gate | `python result_review_framework/scripts/validate_professional_contracts.py <review_dir>` |
| Contract Gate | `python result_review_framework/scripts/validate_audit_contract.py <review_dir>` |
| Finalize | `python result_review_framework/scripts/finalize_audit.py <review_dir>` |
| Archive Fallback | `python result_review_framework/scripts/archive_reviewed_project.py <review_dir> --approve` |

## Review Lane

| Lane | 规则 |
|---|---|
| `standard` | 仅高风险图件或机器预筛标红图件进入 AI复核 |
| `strict` | 所有非装饰图件都进入 AI复核 |

## 图件格式

- PDF-only 可接受，不再因缺少 PNG 单独记问题。
- PNG/JPG-only 且无 PDF 时，记录交付规范 WARNING 或说明例外。

## Sub-Agent 质量门禁

- 正式审核默认 Lead 只做监工/整合；subagent 执行分片审核并落盘证据。
- Lead 不直接吞入长报告、长日志、完整清单或大证据，避免 leader 触发 remote compact。
- Sub-Agent 聊天回传最多 5 行；完整 Markdown/JSON/长日志/大表只写文件并回路径。
- Lead 最终回复最多 8 行；正式通知不贴摘要、内部路径、workspace 或监督 JSON 元数据。
- 小切片只控上下文，不降低模型判断能力；若子代理触发 remote compact/context loss，必须继续拆分切片后重试，禁止原范围重跑。
- 正式判断型切片必须使用与主 agent 相同的模型；如主 agent 为 high reasoning，判断型子代理也必须 high；fast/mini 只做定位/清单/grep/schema。
- Lead 必须做全局一致性复核。

## 报告附页口径

- 参考文献后的公司宣传页默认视为 boilerplate，不纳入正式审核范围。
- 只有当这些内容出现在参考文献前或污染编号正文章节时，才升级为问题。

## Finding Contract

- 必填字段：finding_key, id, severity, dimension, location, description, evidence, rule, source_type, source_path, locator, quote_or_value
- `source_type` 允许值：report_text, figure, table, result_file, code, precheck
- `finding_key` 由 `dimension + rule + source_path + locator + quote_or_value` 稳定生成。
- 高等级 finding 证据不完整时，必须进入 `arbitration_queue.json`。

## 最终文件

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

## 发布/归档状态

- `publish_status`: `pending | success | failed`
- `archive_approved`: `true | false`
- `archived_at`: 必须在 `finalize_audit.py` 自动归档成功后写入。
- `--no-auto-archive`: 已禁用；使用该参数会失败。

## 错题集闭环

- 审核前读取 `lessons/LESSONS_LEARNED.md` 和 `lessons/patterns/`，把相同或相近内容列为重点复核项。
- 审核后将典型错误点、触发场景、证据依据、正确标准、下次审核提醒和规则建议沉淀到 `lessons/`。
- 错题集只提供风险提示；后续项目必须结合当前证据独立判断，不能机械套用历史结论。
- 若规则建议已明确且证据充分，直接同步更新对应 `patterns/`、索引或政策文档，不只留待办。

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

