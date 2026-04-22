#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate framework docs from the canonical policy and command flow."""

from __future__ import annotations

import argparse
from pathlib import Path

from policy_loader import load_policy


DOC_ROOT = Path(__file__).resolve().parents[1]


def _banner(policy: dict, source_files: str) -> str:
    return (
        f"> Generated from `{source_files}`\n"
        f"> Source of truth: `result_review_framework/policy/audit_policy.json`\n"
        f"> Framework version: `{policy['framework_version']}`\n"
        f"> Policy updated at: `{policy['updated_at']}`\n"
        f"> Do not hand-edit this file; re-run `python result_review_framework/scripts/generate_policy_docs.py`\n"
    )


def _command_flow() -> list[tuple[str, str, str]]:
    return [
        ("Precheck", "scripts/auto_audit_pipeline.py", "Extract report/project structure, build case_manifest, run mechanical checks, prepare visual audit assets."),
        ("Guardrails", "scripts/prepare_ai_audit_guardrails.py", "Generate AI execution manifest, prompts, and audit state baseline."),
        ("Convergence", "scripts/convergence_compare.py", "Merge three agent outputs by finding_key first, then similarity fallback; emit arbitration queue."),
        ("Finalize", "scripts/finalize_audit.py", "Run lint, autofix, backfill, state sync, HTML publication, and auto archive as one entrypoint."),
        ("Archive Fallback", "scripts/archive_reviewed_project.py", "Manual fallback for already-published review dirs or when finalize was run with --no-auto-archive."),
    ]


def build_readme(policy: dict) -> str:
    lines = [
        "# 结果审核框架",
        "",
        _banner(policy, "policy/audit_policy.json + scripts/generate_policy_docs.py").rstrip(),
        "",
        "## 当前主线",
        "",
        "正式审核只认下面这条流水线：",
        "",
    ]
    for index, (title, script_name, summary) in enumerate(_command_flow(), start=1):
        lines.append(f"{index}. `{script_name}`")
        lines.append(f"   {title}: {summary}")
    lines.extend(
        [
            "",
            "## 核心约束",
            "",
            "- 统一事实底座：每个项目必须生成 `case_manifest.json`。",
            "- 统一事件留痕：每个阶段都写 `review_event_log.jsonl`。",
            "- 统一问题主键：每条 finding 必须带 `finding_key`。",
            "- 统一收敛出口：三路收敛必须产出 `convergence_report.*` 和 `arbitration_queue.json`。",
            "- 统一收口入口：最终交付通过 `finalize_audit.py` 完成，不再手工串脚本。",
            "- 默认自动归档：`finalize_audit.py` 在 HTML 发布成功后自动移动项目；如需只发布不移动，显式使用 `--no-auto-archive`。",
            "",
            "## 视觉审核",
            "",
            "- `review_lane=standard`：仅高风险图件或机器预筛标红图件进入 AI逐图复核。",
            "- `review_lane=strict`：所有非装饰图进入 AI逐图复核。",
            "- 机器预筛当前覆盖：完全重复图、OCR 检出的外项目编号、明显错图。",
            "",
            "## 必交付件",
            "",
        ]
    )
    for filename in policy["required_final_files"]:
        lines.append(f"- `{filename}`")
    lines.extend(
        [
            "- `<project_id>_audit_report.html`",
            "",
            "## 参考文档",
            "",
            "- `README.md` / `AI_INDEX.md`：入口与路径说明",
            "- `guides/QUICKSTART.md`：执行步骤",
            "- `guides/QUICK_REFERENCE.md`：速查表",
            "- `guides/IMAGE_ANALYSIS_ROADMAP.md`：视觉审核演进方向",
        ]
    )
    return "\n".join(lines) + "\n"


def build_ai_index(policy: dict) -> str:
    commands = _command_flow()
    lines = [
        "# AI 使用索引",
        "",
        _banner(policy, "policy/audit_policy.json + scripts/generate_policy_docs.py").rstrip(),
        "",
        "## AI 审核员先读什么",
        "",
        "1. `policy/audit_policy.json`",
        "2. `README.md`",
        "3. `MASTER_PROMPT.md`",
        "4. `CORE_RULES.md`",
        "",
        "## 正式审核路径",
        "",
    ]
    for index, (_, script_name, summary) in enumerate(commands, start=1):
        lines.append(f"{index}. `{script_name}`")
        lines.append(f"   {summary}")
    lines.extend(
        [
            "",
            "## AI 输出协议",
            "",
            "- finding 需要完整结构化字段，并且必须带 `finding_key`。",
            "- `mechanical_check_result.json` 只能作为候选问题，不能直接当最终结论。",
            "- 高风险模块必须拆成 4 个维度判断：`module_exists` / `evidence_sufficient` / `reproducible` / `conclusion_not_overstated`。",
            "- `CRITICAL/FATAL` finding 如果证据字段不完整，必须进入 `arbitration_queue.json`。",
            "",
            "## 发布与归档",
            "",
            "- 发布状态写入 `case_manifest.json.publish_status`。",
            "- 归档状态写入 `case_manifest.json.archive_approved` 与 `archived_at`。",
            "- `ensure_review_html.py` 只负责 HTML 生成，不单独承担归档。",
            "- `finalize_audit.py` 默认会在发布成功后自动调用 `archive_reviewed_project.py`。",
            "- `archive_reviewed_project.py` 仍保留为手动回补命令。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_quickstart(policy: dict) -> str:
    lines = [
        "# 审核框架 Quickstart",
        "",
        _banner(policy, "policy/audit_policy.json + scripts/generate_policy_docs.py").rstrip(),
        "",
        "## 1. 运行预检查",
        "",
        "```powershell",
        "python result_review_framework/scripts/auto_audit_pipeline.py \"raw/待审核/<项目目录>\" --project-type <类型> --review-lane standard",
        "```",
        "",
        "输出：`report_text.txt`、`report_structure.json`、`project_structure.json`、`mechanical_check_result.json`、`case_manifest.json`、`visual_audit_checklist.json`、`visual_prefilter.json`。",
        "",
        "## 2. 生成 AI 围栏",
        "",
        "```powershell",
        "python result_review_framework/scripts/prepare_ai_audit_guardrails.py result_review_report/<项目编号>",
        "```",
        "",
        "输出：`ai_execution_manifest.json`、`audit_state.json`、`agent_prompts/*`。",
        "",
        "## 3. 收集三路 agent 结果并收敛",
        "",
        "```powershell",
        "python result_review_framework/scripts/convergence_compare.py result_review_report/<项目编号>",
        "```",
        "",
        "输出：`convergence_report.json`、`convergence_report.md`、`arbitration_queue.json`。",
        "",
        "## 4. 一次性完成最终交付和归档",
        "",
        "```powershell",
        "python result_review_framework/scripts/finalize_audit.py result_review_report/<项目编号>",
        "```",
        "",
        "输出：`final_review_report.md`、`final_report_lint.json`、`audit_state.json`、`<项目编号>_audit_report.html`，并默认移动项目到已审核目录。",
        "",
        "## 5. 如需只发布不移动，显式关闭自动归档",
        "",
        "```powershell",
        "python result_review_framework/scripts/finalize_audit.py result_review_report/<项目编号> --no-auto-archive",
        "```",
        "",
        "## 关键规则",
        "",
        "- 默认用 `standard` lane；高争议或强监管项目改用 `strict`。",
        "- 不要手工串 `linter -> autofix -> backfill -> html`，直接跑 `finalize_audit.py`。",
        "- HTML 生成失败时，不允许归档。",
        "- 默认归档仍需满足 `publish_status=success`。",
        "- 如果只想生成 HTML 不移动项目，使用 `--no-auto-archive`。",
    ]
    return "\n".join(lines) + "\n"


def build_quick_reference(policy: dict) -> str:
    required_fields = ", ".join(policy["finding_evidence_policy"]["required_fields"])
    source_types = ", ".join(policy["finding_evidence_policy"]["allowed_source_types"])
    lines = [
        "# 审核框架 Quick Reference",
        "",
        _banner(policy, "policy/audit_policy.json + scripts/generate_policy_docs.py").rstrip(),
        "",
        "## 主命令",
        "",
        "| 阶段 | 命令 |",
        "|---|---|",
        "| Precheck | `python result_review_framework/scripts/auto_audit_pipeline.py <project_dir> --project-type <类型> --review-lane <standard|strict>` |",
        "| Guardrails | `python result_review_framework/scripts/prepare_ai_audit_guardrails.py <review_dir>` |",
        "| Convergence | `python result_review_framework/scripts/convergence_compare.py <review_dir>` |",
        "| Finalize | `python result_review_framework/scripts/finalize_audit.py <review_dir>` |",
        "| Archive Fallback | `python result_review_framework/scripts/archive_reviewed_project.py <review_dir> --approve` |",
        "",
        "## Review Lane",
        "",
        "| Lane | 规则 |",
        "|---|---|",
        "| `standard` | 仅高风险图件或机器预筛标红图件进入 AI复核 |",
        "| `strict` | 所有非装饰图件都进入 AI复核 |",
        "",
        "## Finding Contract",
        "",
        f"- 必填字段：{required_fields}",
        f"- `source_type` 允许值：{source_types}",
        "- `finding_key` 由 `dimension + rule + source_path + locator + quote_or_value` 稳定生成。",
        "- 高等级 finding 证据不完整时，必须进入 `arbitration_queue.json`。",
        "",
        "## 最终文件",
        "",
    ]
    for filename in policy["required_final_files"]:
        lines.append(f"- `{filename}`")
    lines.extend(
        [
            "- `<project_id>_audit_report.html`",
            "",
            "## 发布/归档状态",
            "",
            "- `publish_status`: `pending | success | failed`",
            "- `archive_approved`: `true | false`",
            "- `archived_at`: 默认在 `finalize_audit.py` 自动归档成功后写入。",
            "- `--no-auto-archive`: 只生成 HTML 和状态，不移动原始项目。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_image_analysis_roadmap(policy: dict) -> str:
    lines = [
        "# 图像审核路线图",
        "",
        _banner(policy, "policy/audit_policy.json + scripts/generate_policy_docs.py").rstrip(),
        "",
        "## 当前已实现",
        "",
        "- `visual_prefilter.json`：视觉预筛结构化产物。",
        "- 完全重复图检测：基于文件 SHA1。",
        "- OCR 项目编号失配检测：可选依赖 `pytesseract`。",
        "- 明显错图检测：用轻量视觉家族分类拦截“图表位被文字页替代”类错误。",
        "- `review_lane`：`standard` / `strict` 双车道。",
        "",
        "## 下一阶段建议",
        "",
        "1. 感知哈希或向量相似度，覆盖裁剪后重复图。",
        "2. 图注 OCR 与正文自动对齐，提升跨项目污染检出率。",
        "3. 图表类型识别从规则法升级为轻量模型。",
        "4. 把 `visual_prefilter` 风险标签回灌到 mechanical checks 和最终报告模板。",
        "",
        "## 使用原则",
        "",
        "- 机器预筛只负责排序和标红，不直接替代最终裁定。",
        "- `strict` 项目仍保留全量 AI看图。",
    ]
    return "\n".join(lines) + "\n"


def build_documents(policy: dict) -> dict[Path, str]:
    return {
        DOC_ROOT / "README.md": build_readme(policy),
        DOC_ROOT / "AI_INDEX.md": build_ai_index(policy),
        DOC_ROOT / "guides" / "QUICKSTART.md": build_quickstart(policy),
        DOC_ROOT / "guides" / "QUICK_REFERENCE.md": build_quick_reference(policy),
        DOC_ROOT / "guides" / "IMAGE_ANALYSIS_ROADMAP.md": build_image_analysis_roadmap(policy),
    }


def write_documents(check_only: bool = False) -> list[Path]:
    policy = load_policy()
    documents = build_documents(policy)
    mismatches = []
    for path, content in documents.items():
        if check_only:
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            if existing != content:
                mismatches.append(path)
            continue
        path.write_text(content, encoding="utf-8")
    return mismatches


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate policy-derived framework docs.")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if generated docs differ from files on disk.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mismatches = write_documents(check_only=args.check)
    if args.check and mismatches:
        for path in mismatches:
            print(f"Doc drift: {path}")
        return 1
    if not args.check:
        for path in build_documents(load_policy()):
            print(f"Updated: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
