# 审核框架 Quick Reference

> Generated from `policy/audit_policy.json + scripts/generate_policy_docs.py`
> Source of truth: `result_review_framework/policy/audit_policy.json`
> Framework version: `v6.6`
> Policy updated at: `2026-04-21`
> Do not hand-edit this file; re-run `python result_review_framework/scripts/generate_policy_docs.py`

## 主命令

| 阶段 | 命令 |
|---|---|
| Precheck | `python result_review_framework/scripts/auto_audit_pipeline.py <project_dir> --project-type <类型> --review-lane <standard|strict>` |
| Guardrails | `python result_review_framework/scripts/prepare_ai_audit_guardrails.py <review_dir>` |
| Convergence | `python result_review_framework/scripts/convergence_compare.py <review_dir>` |
| Finalize | `python result_review_framework/scripts/finalize_audit.py <review_dir>` |
| Archive Fallback | `python result_review_framework/scripts/archive_reviewed_project.py <review_dir> --approve` |

## Review Lane

| Lane | 规则 |
|---|---|
| `standard` | 仅高风险图件或机器预筛标红图件进入 AI复核 |
| `strict` | 所有非装饰图件都进入 AI复核 |

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
- `final_report_lint.json`
- `audit_state.json`
- `<project_id>_audit_report.html`

## 发布/归档状态

- `publish_status`: `pending | success | failed`
- `archive_approved`: `true | false`
- `archived_at`: 默认在 `finalize_audit.py` 自动归档成功后写入。
- `--no-auto-archive`: 只生成 HTML 和状态，不移动原始项目。
