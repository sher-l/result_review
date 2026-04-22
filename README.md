# 结果审核框架

> Generated from `policy/audit_policy.json + scripts/generate_policy_docs.py`
> Source of truth: `result_review_framework/policy/audit_policy.json`
> Framework version: `v6.6`
> Policy updated at: `2026-04-21`
> Do not hand-edit this file; re-run `python result_review_framework/scripts/generate_policy_docs.py`

## 当前主线

正式审核只认下面这条流水线：

1. `scripts/auto_audit_pipeline.py`
   Precheck: Extract report/project structure, build case_manifest, run mechanical checks, prepare visual audit assets.
2. `scripts/prepare_ai_audit_guardrails.py`
   Guardrails: Generate AI execution manifest, prompts, and audit state baseline.
3. `scripts/convergence_compare.py`
   Convergence: Merge three agent outputs by finding_key first, then similarity fallback; emit arbitration queue.
4. `scripts/finalize_audit.py`
   Finalize: Run lint, autofix, backfill, state sync, HTML publication, and auto archive as one entrypoint.
5. `scripts/archive_reviewed_project.py`
   Archive Fallback: Manual fallback for already-published review dirs or when finalize was run with --no-auto-archive.

## 核心约束

- 统一事实底座：每个项目必须生成 `case_manifest.json`。
- 统一事件留痕：每个阶段都写 `review_event_log.jsonl`。
- 统一问题主键：每条 finding 必须带 `finding_key`。
- 统一收敛出口：三路收敛必须产出 `convergence_report.*` 和 `arbitration_queue.json`。
- 统一收口入口：最终交付通过 `finalize_audit.py` 完成，不再手工串脚本。
- 默认自动归档：`finalize_audit.py` 在 HTML 发布成功后自动移动项目；如需只发布不移动，显式使用 `--no-auto-archive`。

## 视觉审核

- `review_lane=standard`：仅高风险图件或机器预筛标红图件进入 AI逐图复核。
- `review_lane=strict`：所有非装饰图进入 AI逐图复核。
- 机器预筛当前覆盖：完全重复图、OCR 检出的外项目编号、明显错图。

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
- `final_report_lint.json`
- `audit_state.json`
- `<project_id>_audit_report.html`

## 参考文档

- `README.md` / `AI_INDEX.md`：入口与路径说明
- `guides/QUICKSTART.md`：执行步骤
- `guides/QUICK_REFERENCE.md`：速查表
- `guides/IMAGE_ANALYSIS_ROADMAP.md`：视觉审核演进方向
