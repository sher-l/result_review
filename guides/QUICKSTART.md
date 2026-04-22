# 审核框架 Quickstart

> Generated from `policy/audit_policy.json + scripts/generate_policy_docs.py`
> Source of truth: `result_review_framework/policy/audit_policy.json`
> Framework version: `v6.6`
> Policy updated at: `2026-04-21`
> Do not hand-edit this file; re-run `python result_review_framework/scripts/generate_policy_docs.py`

## 1. 运行预检查

```powershell
python result_review_framework/scripts/auto_audit_pipeline.py "raw/待审核/<项目目录>" --project-type <类型> --review-lane standard
```

输出：`report_text.txt`、`report_structure.json`、`project_structure.json`、`mechanical_check_result.json`、`case_manifest.json`、`visual_audit_checklist.json`、`visual_prefilter.json`。

## 2. 生成 AI 围栏

```powershell
python result_review_framework/scripts/prepare_ai_audit_guardrails.py result_review_report/<项目编号>
```

输出：`ai_execution_manifest.json`、`audit_state.json`、`agent_prompts/*`。

## 3. 收集三路 agent 结果并收敛

```powershell
python result_review_framework/scripts/convergence_compare.py result_review_report/<项目编号>
```

输出：`convergence_report.json`、`convergence_report.md`、`arbitration_queue.json`。

## 4. 一次性完成最终交付和归档

```powershell
python result_review_framework/scripts/finalize_audit.py result_review_report/<项目编号>
```

输出：`final_review_report.md`、`final_report_lint.json`、`audit_state.json`、`<项目编号>_audit_report.html`，并默认移动项目到已审核目录。

## 5. 如需只发布不移动，显式关闭自动归档

```powershell
python result_review_framework/scripts/finalize_audit.py result_review_report/<项目编号> --no-auto-archive
```

## 关键规则

- 默认用 `standard` lane；高争议或强监管项目改用 `strict`。
- 不要手工串 `linter -> autofix -> backfill -> html`，直接跑 `finalize_audit.py`。
- HTML 生成失败时，不允许归档。
- 默认归档仍需满足 `publish_status=success`。
- 如果只想生成 HTML 不移动项目，使用 `--no-auto-archive`。
