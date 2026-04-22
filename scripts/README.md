# Scripts Entry

这里只保留当前正式审核主线真正会走到的脚本路线。

## 主线

### 1. Round 0 预检
```bash
python result_review_framework/scripts/auto_audit_pipeline.py <项目路径>
```

作用：
- 提取报告文本和图片
- 解析报告结构
- 解析项目结构
- 跑 mechanical checks 和 precheck orchestrator
- 生成 `result_review_report/<项目编号>/`

### 2. 生成 AI 围栏
```bash
python result_review_framework/scripts/prepare_ai_audit_guardrails.py result_review_report/<项目编号> --project-dir <项目路径>
```

作用：
- 生成 `ai_execution_manifest.json`
- 生成 `audit_state.json`
- 生成三路 sub-agent prompts
- 把正式审核路线固定下来

### 3. 三路收敛
```bash
python result_review_framework/scripts/convergence_compare.py result_review_report/<项目编号>
```

作用：
- 汇总三路 findings
- 汇总机械检查处置
- 汇总高风险模块分层判断
- 生成 `convergence_report.json` 和 `convergence_report.md`

### 4. 最终报告门禁
```bash
python result_review_framework/scripts/final_report_linter.py result_review_report/<项目编号>
python result_review_framework/scripts/generate_lint_autofix_plan.py result_review_report/<项目编号>
python result_review_framework/scripts/apply_lint_autofix_plan.py result_review_report/<项目编号>
python result_review_framework/scripts/generate_required_section_backfill.py result_review_report/<项目编号>
python result_review_framework/scripts/apply_required_section_backfill.py result_review_report/<项目编号>
python result_review_framework/scripts/sync_audit_state.py result_review_report/<项目编号>
python result_review_framework/scripts/ensure_review_html.py result_review_report/<项目编号>
```

作用：
- 阻止缺章节、缺证据标签、缺收敛信息的最终报告
- 生成 `lint_autofix_plan.json`，把 `autofix_safe` 项转成机器可执行修复计划
- 应用 `lint_autofix_plan.json` 中的安全修复项，并输出 `lint_autofix_apply_report.json`
- 生成 `final_report_backfill_plan.json`，对缺失的必需章节做结构化回填计划
- 应用 `final_report_backfill_plan.json` 中的章节回填块，并输出 `final_report_backfill_apply_report.json`
- 刷新 `audit_state.json`
- 从 Markdown 导出 HTML
- 如果已配置 webhook，则在审核真正完成后自动发送通知

## 现在最重要的 5 个脚本
- `auto_audit_pipeline.py`
- `prepare_ai_audit_guardrails.py`
- `convergence_compare.py`
- `final_report_linter.py`
- `generate_lint_autofix_plan.py`
- `apply_lint_autofix_plan.py`
- `generate_required_section_backfill.py`
- `apply_required_section_backfill.py`

如果要改主线，优先改这 8 个。

## 策略来源

当前脚本主线统一读取：
- `../policy/audit_policy.json`

以后新增规则，优先写进 policy，再让脚本读取。

## 仍然可用但不是主入口的脚本
- `render_final_review_html.py`
- `ensure_review_html.py`
- `sync_audit_state.py`
- `build_rereview_diff.py`
- `terminology_audit.py`
- `launch_convergence_audit.py`
- `send_audit_notification.py`

这些脚本是主线上的配套件，不是新的入口。
