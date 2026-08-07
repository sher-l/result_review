#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check the framework's own surfaced docs and entrypoints for drift."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from generate_policy_docs import write_documents
from html_presentation_contract import (
    PRESENTATION_PROFILE,
    PRESENTATION_TEMPLATE,
    validate_html_presentation_template_file,
)
from policy_loader import load_policy


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class VersionMarkerRule:
    path: str
    pattern: str
    description: str


@dataclass(frozen=True)
class ContentRule:
    path: str
    description: str
    required: str | None = None
    forbidden: str | None = None


VERSION_MARKER_RULES = [
    VersionMarkerRule("WORKFLOW.md", r"^> \*\*版本\*\*: (?P<version>v[\d.]+)$", "workflow header version"),
    VersionMarkerRule("WORKFLOW.md", r"^\*\*版本\*\*: (?P<version>v[\d.]+)$", "workflow footer version"),
    VersionMarkerRule("CHECKLIST_TEMPLATE.md", r"^# 项目检查清单模板 (?P<version>v[\d.]+)$", "checklist title version"),
    VersionMarkerRule("CHECKLIST_TEMPLATE.md", r"^\*\*模板版本\*\*: (?P<version>v[\d.]+)$", "checklist footer version"),
    VersionMarkerRule("CHECKLIST_TEMPLATE.md", r"^\*\*基于\*\*: 审核框架主线 (?P<version>v[\d.]+)$", "checklist framework version"),
    VersionMarkerRule("CONVERGENCE_REVIEW_PROTOCOL.md", r"^> \*\*版本\*\*: (?P<version>v[\d.]+)$", "convergence header version"),
    VersionMarkerRule("CONVERGENCE_REVIEW_PROTOCOL.md", r"^\*\*版本\*\*: (?P<version>v[\d.]+)$", "convergence footer version"),
    VersionMarkerRule("agent_plans/AGENT_TEAM_PLAN.md", r"^> \*\*当前主线版本\*\*：(?P<version>v[\d.]+)$", "agent plan header version"),
    VersionMarkerRule("agent_plans/AGENT_TEAM_PLAN.md", r"^\*\*版本\*\*: (?P<version>v[\d.]+)$", "agent plan footer version"),
    VersionMarkerRule("agent_plans/AGENT_TEAM_PLAN.md", r"^\*\*基于\*\*: 审核框架主线 (?P<version>v[\d.]+)$", "agent plan framework version"),
    VersionMarkerRule("KNOWN_LIMITATIONS.md", r"^> 最后更新：(?P<version>v[\d.]+)", "known limitations version"),
    VersionMarkerRule("STATISTICS_REFERENCE.md", r"^> \*\*版本\*\*: (?P<version>v[\d.]+)\s*$", "statistics header version"),
    VersionMarkerRule("STATISTICS_REFERENCE.md", r"^\*\*文档版本\*\*: (?P<version>v[\d.]+)\s*$", "statistics footer version"),
    VersionMarkerRule("script_utils/README.md", r"^> \*\*版本\*\*: (?P<version>v[\d.]+)\s*$", "script_utils readme version"),
    VersionMarkerRule("report_templates/final_review_report_template.md", r"^> \*\*审核框架\*\*：(?P<version>v[\d.]+)$", "final review template version"),
    VersionMarkerRule("report_templates/figure_audit_template.md", r"^> \*\*框架版本\*\*: (?P<version>v[\d.]+)$", "figure audit template version"),
    VersionMarkerRule("CORE_RULES.md", r"^\*(?P<version>v[\d.]+) \|", "core rules footer version"),
    VersionMarkerRule("guides/TERMINOLOGY_AUDIT_GUIDE.md", r"^\*\*版本\*\*: (?P<version>v[\d.]+)$", "terminology guide version"),
    VersionMarkerRule(
        "scripts/auto_audit_pipeline.py",
        r'^FRAMEWORK_VERSION = load_policy\(\)\.get\("framework_version", "(?P<version>v[\d.]+)"\)$',
        "auto audit fallback version",
    ),
    VersionMarkerRule(
        "script_utils/check_orchestrator.py",
        r"return policy\.get\('framework_version', '(?P<version>v[\d.]+)'\)",
        "mechanical checker fallback version",
    ),
]


CONTENT_RULES = [
    ContentRule(
        "WORKFLOW.md",
        description="workflow final delivery uses finalize_audit.py",
        required="python result_review_framework/scripts/finalize_audit.py result_review_report/<项目编号>",
    ),
    ContentRule(
        "agent_plans/AGENT_TEAM_PLAN.md",
        description="agent team plan final delivery uses finalize_audit.py",
        required="finalize_audit.py",
    ),
    ContentRule(
        "agent_plans/AGENT_TEAM_PLAN.md",
        description="agent team plan includes guardrail generation before subagents",
        required="prepare_ai_audit_guardrails.py",
    ),
    ContentRule(
        "agent_plans/AGENT_TEAM_PLAN.md",
        description="agent team plan requires small-slice JSON outputs",
        required="agent_results/slices/*.json",
    ),
    ContentRule(
        "agent_plans/AGENT_TEAM_PLAN.md",
        description="agent team plan no longer describes subagents as full-stack auditors",
        forbidden="全栈审核",
    ),
    ContentRule(
        "agent_plans/AGENT_TEAM_PLAN.md",
        description="agent team plan no longer launches three large subagents",
        forbidden="再同时调用 3 个 Sub-Agent",
    ),
    ContentRule(
        "CONVERGENCE_REVIEW_PROTOCOL.md",
        description="convergence protocol rejects large full-project subagents",
        required="禁止**同时启动 3 个“大而全”的独立 Sub-Agent",
    ),
    ContentRule(
        "CONVERGENCE_REVIEW_PROTOCOL.md",
        description="convergence protocol no longer calls each subagent full-stack",
        forbidden="每个 Sub-Agent 是**全栈审核员**",
    ),
    ContentRule(
        "guides/QUICKSTART.md",
        description="quickstart instructs reading the slice manifest",
        required="agent_slice_manifest.json",
    ),
    ContentRule(
        "guides/QUICKSTART.md",
        description="quickstart instructs slice result persistence",
        required="agent_results/slices/",
    ),
    ContentRule(
        "scripts/convergence_compare.py",
        description="convergence gate validates slice outputs",
        required="validate_slice_outputs",
    ),
    ContentRule(
        "policy/audit_policy.json",
        description="policy states small slices must not reduce judgement model strength",
        required="切小片只为控制上下文，不允许降低正式审核判断能力",
    ),
    ContentRule(
        "scripts/launch_convergence_audit.py",
        description="slice prompts include model quality protocol",
        required="_MODEL_QUALITY_PROTOCOL",
    ),
    ContentRule(
        "scripts/launch_convergence_audit.py",
        description="slice manifest exposes model_quality metadata",
        required="model_quality",
    ),
    ContentRule(
        "scripts/prepare_ai_audit_guardrails.py",
        description="guardrails prohibit downshifting judgement slices",
        required="Do not downshift severity judgement",
    ),
    ContentRule(
        "guides/QUICKSTART.md",
        description="quickstart distinguishes small slices from weak models",
        required="小切片不等于弱模型",
    ),
    ContentRule(
        "guides/QUICKSTART.md",
        description="quickstart requires lead global consistency review",
        required="局部通过但整体不成立",
    ),
    ContentRule(
        "guides/QUICKSTART.md",
        description="quickstart does not override the strict default lane",
        forbidden="--review-lane standard",
    ),
    ContentRule(
        "guides/QUICKSTART.md",
        description="quickstart states the canonical strict default lane",
        required="默认 `strict`",
    ),
    ContentRule(
        "report_templates/project_config_template.json",
        description="legacy project config is machine-marked reference-only",
        required='"_framework_version": "legacy-v3.0"',
    ),
    ContentRule(
        "report_templates/project_config_template.json",
        description="legacy project config forbids new-project use",
        required="禁止用于新项目",
    ),
    ContentRule(
        "agent_plans/AGENT_TEAM_PLAN.md",
        description="agent team plan does not advertise render_final_review_html.py as the main final delivery step",
        forbidden="render_final_review_html.py",
    ),
    ContentRule(
        "scripts/README.md",
        description="scripts readme canonical closeout uses finalize_audit.py",
        required="python result_review_framework/scripts/finalize_audit.py result_review_report/<项目编号>",
    ),
    ContentRule(
        "scripts/README.md",
        description="scripts readme documents framework_health_check.py",
        required="framework_health_check.py",
    ),
    ContentRule(
        "scripts/notification_client.py",
        description="all completed-audit providers use the mandatory formal-delivery gate",
        required="delivery_ok, delivery_reason = validate_completed_audit_delivery(metadata)",
    ),
    ContentRule(
        "scripts/notification_client.py",
        description="formal-delivery denial cannot fall back to another provider",
        required='"formal delivery blocked:",',
    ),
    ContentRule(
        "scripts/send_audit_notification.py",
        description="direct audit completion wrapper is disabled",
        required="Direct audit completion notification is disabled.",
    ),
    ContentRule(
        "scripts/send_completion_notification.py",
        description="generic notification wrapper cannot send audit completion",
        required="Direct audit completion notification is disabled.",
    ),
    ContentRule(
        "scripts/finalize_audit.py",
        description="formal finalize rejects caller-owned notification configuration",
        required="--notification-config is not permitted for finalize",
    ),
    ContentRule(
        "scripts/sync_audit_state.py",
        description="missing visual-closure mode fails closed as enforce",
        required='mode = closure_policy.get("mode", "enforce")',
    ),
    ContentRule(
        "scripts/visual_audit.py",
        description="visual-audit result validation defaults to enforce",
        required='"mode": closure_policy.get("mode", "enforce")',
    ),
    ContentRule(
        "scripts/final_report_linter.py",
        description="missing formal-delivery policy cannot disable report-state checks",
        required="formal_delivery_policy is missing or invalid; final delivery checks cannot be disabled implicitly.",
    ),
    ContentRule(
        "scripts/final_report_linter.py",
        description="missing report-depth policy cannot skip report-depth checks",
        required="final_report_depth_policy is missing or invalid; report-depth checks cannot be skipped.",
    ),
    ContentRule(
        "scripts/audit_contract.py",
        description="missing or invalid final-decision contract mode fails closed",
        required='policy.get("mode", "enforce") or "enforce"',
    ),
    ContentRule(
        "scripts/validate_professional_contracts.py",
        description="missing arbitration mode fails closed as enforce",
        required='professional.get("arbitration_mode", "enforce")',
    ),
    ContentRule(
        "scripts/render_final_review_html.py",
        description="adjudication index remains expanded by default",
        required="'<details class=\"inventory-details adjudication-index\" open>'",
    ),
    ContentRule(
        "scripts/render_final_review_html.py",
        description="single-kind delivery rows expose the CSS class that provides the grey cue",
        required="row_class = ' class=\"inventory-row-single-kind\"'",
    ),
    ContentRule(
        "scripts/render_final_review_html.py",
        description="delivery inventory renders the shared grey-row legend",
        required="INVENTORY_LEGEND_TEXT",
    ),
    ContentRule(
        "report_templates/final_review_report_template.html",
        description="reader HTML declares the current presentation profile",
        required=f'<meta name="rrf-presentation-profile" content="{PRESENTATION_PROFILE}">',
    ),
    ContentRule(
        "scripts/ensure_review_html.py",
        description="cached HTML must pass the reader presentation contract before skip",
        required="validate_html_presentation_file(html_path)",
    ),
    ContentRule(
        "scripts/formal_delivery.py",
        description="formal delivery binds the sealed final decision",
        required='manifest["artifacts"]["final_decision"] = {',
    ),
    ContentRule(
        "scripts/formal_delivery.py",
        description="formal delivery revalidates the reader presentation contract",
        required="validate_html_presentation_file",
    ),
    ContentRule(
        "scripts/archive_reviewed_project.py",
        description="direct archive validates all formal gates before approval",
        required="validate_formal_archive_gates(review_dir)",
    ),
    ContentRule(
        "scripts/sync_audit_state.py",
        description="missing auto-archive policy cannot silently disable required archive",
        required='default_execution.get("must_auto_archive_after_finalize", True)',
    ),
]


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def evaluate_version_rule(root: Path, expected_version: str, rule: VersionMarkerRule) -> dict:
    file_path = root / rule.path
    if not file_path.exists():
        return {
            "id": f"version:{rule.path}:{rule.description}",
            "path": rule.path,
            "description": rule.description,
            "passed": False,
            "message": f"Missing file: {rule.path}",
        }

    text = file_path.read_text(encoding="utf-8")
    match = re.search(rule.pattern, text, flags=re.MULTILINE)
    if not match:
        return {
            "id": f"version:{rule.path}:{rule.description}",
            "path": rule.path,
            "description": rule.description,
            "passed": False,
            "message": f"Marker not found for {rule.description}",
        }

    actual_version = match.group("version")
    passed = actual_version == expected_version
    return {
        "id": f"version:{rule.path}:{rule.description}",
        "path": rule.path,
        "description": rule.description,
        "passed": passed,
        "actual": actual_version,
        "expected": expected_version,
        "message": (
            f"{rule.description} matches {expected_version}"
            if passed
            else f"{rule.description} uses {actual_version}, expected {expected_version}"
        ),
    }


def evaluate_content_rule(root: Path, rule: ContentRule) -> dict:
    file_path = root / rule.path
    if not file_path.exists():
        return {
            "id": f"content:{rule.path}:{rule.description}",
            "path": rule.path,
            "description": rule.description,
            "passed": False,
            "message": f"Missing file: {rule.path}",
        }

    text = file_path.read_text(encoding="utf-8")
    if rule.required is not None:
        passed = rule.required in text
        return {
            "id": f"content:{rule.path}:{rule.description}",
            "path": rule.path,
            "description": rule.description,
            "passed": passed,
            "message": (
                f"{rule.description} is present"
                if passed
                else f"Missing required content in {rule.path}: {rule.required}"
            ),
        }

    if rule.forbidden is not None:
        passed = rule.forbidden not in text
        return {
            "id": f"content:{rule.path}:{rule.description}",
            "path": rule.path,
            "description": rule.description,
            "passed": passed,
            "message": (
                f"{rule.description} is clean"
                if passed
                else f"Forbidden content still present in {rule.path}: {rule.forbidden}"
            ),
        }

    raise ValueError(f"Content rule must define required or forbidden content: {rule}")


def evaluate_presentation_template(root: Path) -> dict:
    """Bind framework health to the immutable reader-v3 template baseline."""
    template_path = root / PRESENTATION_TEMPLATE
    passed, reason = validate_html_presentation_template_file(template_path)
    return {
        "id": "presentation:reader-template-baseline",
        "path": PRESENTATION_TEMPLATE,
        "description": f"reader HTML template matches {PRESENTATION_PROFILE}",
        "passed": passed,
        "message": (
            f"reader HTML template matches approved {PRESENTATION_PROFILE} baseline"
            if passed
            else reason
        ),
    }


def run_health_check(root: Path | None = None, *, include_generated_docs: bool = True) -> dict:
    root = root or ROOT
    policy = load_policy()
    expected_version = policy.get("framework_version", "")

    generated_doc_drift: list[str] = []
    if include_generated_docs and root == ROOT:
        generated_doc_drift = [_rel(path, root) for path in write_documents(check_only=True)]

    checks = [
        *[evaluate_version_rule(root, expected_version, rule) for rule in VERSION_MARKER_RULES],
        *[evaluate_content_rule(root, rule) for rule in CONTENT_RULES],
        evaluate_presentation_template(root),
    ]
    passed = not generated_doc_drift and all(check["passed"] for check in checks)
    return {
        "passed": passed,
        "framework_version": expected_version,
        "generated_doc_drift": generated_doc_drift,
        "checks": checks,
    }


def assert_framework_healthy() -> dict:
    """Return the canonical health report or stop a formal workflow early.

    Entry points use this before creating review artifacts.  Keeping the gate
    here makes the checked surface identical to the standalone health command
    and, importantly, keeps it read-only.
    """
    report = run_health_check()
    if report["passed"]:
        return report

    failures = [
        f"{check.get('path', 'unknown')}: {check.get('message', 'failed')}"
        for check in report["checks"]
        if not check.get("passed", False)
    ]
    failures.extend(f"generated document drift: {path}" for path in report["generated_doc_drift"])
    detail = "; ".join(failures[:3])
    if len(failures) > 3:
        detail += f"; and {len(failures) - 3} more"
    raise RuntimeError(
        "Framework health gate failed; synchronize the canonical framework before starting or finalizing an audit"
        + (f": {detail}" if detail else "")
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check the framework itself for surfaced doc/version drift."
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Optional JSON output path for the health report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_health_check()

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Framework health report written to: {output_path}")

    if report["generated_doc_drift"]:
        print("Generated-doc drift:")
        for path in report["generated_doc_drift"]:
            print(f"  - {path}")

    failing_checks = [check for check in report["checks"] if not check["passed"]]
    if failing_checks:
        print("Framework drift findings:")
        for check in failing_checks:
            print(f"  - [{check['path']}] {check['message']}")
        return 1

    print(f"Framework health check passed for version {report['framework_version']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
