# AI 使用索引

> Generated from `policy/audit_policy.json + scripts/generate_policy_docs.py`
> Source of truth: `result_review_framework/policy/audit_policy.json`
> Framework version: `v6.6`
> Policy updated at: `2026-04-21`
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
3. `scripts/convergence_compare.py`
   Merge three agent outputs by finding_key first, then similarity fallback; emit arbitration queue.
4. `scripts/finalize_audit.py`
   Run lint, autofix, backfill, state sync, HTML publication, and auto archive as one entrypoint.
5. `scripts/archive_reviewed_project.py`
   Manual fallback for already-published review dirs or when finalize was run with --no-auto-archive.

## AI 输出协议

- finding 需要完整结构化字段，并且必须带 `finding_key`。
- `mechanical_check_result.json` 只能作为候选问题，不能直接当最终结论。
- 高风险模块必须拆成 4 个维度判断：`module_exists` / `evidence_sufficient` / `reproducible` / `conclusion_not_overstated`。
- `CRITICAL/FATAL` finding 如果证据字段不完整，必须进入 `arbitration_queue.json`。

## 发布与归档

- 发布状态写入 `case_manifest.json.publish_status`。
- 归档状态写入 `case_manifest.json.archive_approved` 与 `archived_at`。
- `ensure_review_html.py` 只负责 HTML 生成，不单独承担归档。
- `finalize_audit.py` 默认会在发布成功后自动调用 `archive_reviewed_project.py`。
- `archive_reviewed_project.py` 仍保留为手动回补命令。
