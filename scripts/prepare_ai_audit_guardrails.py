#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generate machine-readable guardrails for the formal AI audit flow.

Outputs:
1. ai_execution_manifest.json
2. audit_state.json
3. agent_prompts/agent_a_prompt.md
4. agent_prompts/agent_b_prompt.md
5. agent_prompts/agent_c_prompt.md
6. agent_prompts/convergence_guide.md
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from audit_runtime import append_event, load_case_manifest
from launch_convergence_audit import (
    _AGENT_A_EMPHASIS,
    _AGENT_B_EMPHASIS,
    _AGENT_C_EMPHASIS,
    build_agent_prompt,
    build_convergence_guide,
    load_precheck_results,
    load_report_excerpt,
)
from policy_loader import load_policy, policy_path
from sync_audit_state import build_state


def build_evidence_appendix(policy: dict) -> str:
    required_fields = "\n".join(
        f"- `{field}`" for field in policy["finding_evidence_policy"]["required_fields"]
    )
    allowed_source_types = ", ".join(
        f"`{item}`" for item in policy["finding_evidence_policy"]["allowed_source_types"]
    )
    forbidden_shortcuts = "\n".join(
        f"- `{phrase}`" for phrase in policy["forbidden_shortcuts"]
    )
    return f"""

## Structured Evidence Requirement

Every finding must include these fields:
{required_fields}

Allowed `source_type` values: {allowed_source_types}

If any required field is missing, the finding is incomplete.
Do not use vague shortcut phrases without bound evidence:
{forbidden_shortcuts}
"""


def parse_args(argv: list[str]) -> tuple[Path, Path | None]:
    if len(argv) < 2:
        raise SystemExit(
            "Usage: python prepare_ai_audit_guardrails.py <review_dir> [--project-dir <project_dir>]"
        )

    review_dir = Path(argv[1])
    project_dir = None
    if "--project-dir" in argv:
        index = argv.index("--project-dir")
        if index + 1 < len(argv):
            project_dir = Path(argv[index + 1])
    return review_dir, project_dir


def build_manifest(review_dir: Path, project_dir: Path | None, precheck: dict) -> dict:
    policy = load_policy()
    prompt_dir = review_dir / "agent_prompts"
    results_dir = review_dir / "agent_results"
    case_manifest = load_case_manifest(review_dir)
    review_lane = case_manifest.get("review_lane", "standard")

    return {
        "schema_version": "1.4",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": policy.get("mode", "formal_audit"),
        "policy_version": policy.get("framework_version", ""),
        "review_lane": review_lane,
        "publish_status": case_manifest.get("publish_status", "pending"),
        "archive_approved": bool(case_manifest.get("archive_approved", False)),
        "default_policy": policy["default_execution"],
        "paths": {
            "review_dir": str(review_dir),
            "project_dir": str(project_dir) if project_dir else "",
            "case_manifest": str(review_dir / "case_manifest.json"),
            "review_event_log": str(review_dir / "review_event_log.jsonl"),
            "prompt_dir": str(prompt_dir),
            "agent_results_dir": str(results_dir),
            "policy_file": str(policy_path()),
            "report_text": str(review_dir / "report_text.txt"),
            "figure_audit": str(review_dir / "figure_audit.md"),
            "mechanical_check_result": str(review_dir / "mechanical_check_result.json"),
            "convergence_report_json": str(review_dir / "convergence_report.json"),
            "convergence_report_md": str(review_dir / "convergence_report.md"),
            "final_review_report": str(review_dir / "final_review_report.md"),
            "final_report_lint": str(review_dir / "final_report_lint.json"),
            "lint_autofix_plan": str(review_dir / "lint_autofix_plan.json"),
            "lint_autofix_apply_report": str(review_dir / "lint_autofix_apply_report.json"),
            "final_report_backfill_plan": str(review_dir / "final_report_backfill_plan.json"),
            "final_report_backfill_apply_report": str(review_dir / "final_report_backfill_apply_report.json"),
            "audit_state": str(review_dir / "audit_state.json"),
            "rereview_diff_json": str(review_dir / "rereview_diff.json"),
        },
        "route": [
            {
                "step": 1,
                "name": "read_precheck_outputs",
                "required": True,
                "gate": ", ".join(policy["required_precheck_files"]) + " exist",
                "do": [
                    "Read policy/audit_policy.json first and treat it as the canonical rule source",
                    "Read report_text.txt",
                    "Read project_structure.json",
                    "Read report_structure.json",
                    "Read mechanical_check_result.json",
                    "Read audit_state.json to confirm the current phase",
                ],
                "do_not_skip": "Do not launch subagents before reading the precheck outputs and current state.",
            },
            {
                "step": 2,
                "name": "complete_visual_audit",
                "required": True,
                "gate": "figure_audit.md exists or can be completed now",
                "do": [
                    "Read visual_prefilter.json first and resolve all high-risk flags",
                    "If review_lane=strict, complete full figure-by-figure audit",
                    "If review_lane=standard, explicitly mark sampled or waived low-risk figures",
                ],
                "tool": "Use Layer 2 visual audit workflow",
                "do_not_skip": "Do not leave visual prefilter flags unresolved.",
            },
            {
                "step": 3,
                "name": "launch_three_subagents",
                "required": True,
                "gate": "formal audit is in progress",
                "do": [
                    "Launch Agent A, Agent B, and Agent C in parallel",
                    "Keep each subagent independent until convergence stage",
                    "Require every finding to include structured evidence fields",
                ],
                "inputs": [
                    str(prompt_dir / "agent_a_prompt.md"),
                    str(prompt_dir / "agent_b_prompt.md"),
                    str(prompt_dir / "agent_c_prompt.md"),
                ],
                "do_not_skip": "If the user says start audit / audit next / re-review, three subagents are mandatory by default.",
            },
            {
                "step": 4,
                "name": "persist_agent_outputs",
                "required": True,
                "gate": "each agent has returned structured output",
                "outputs": [
                    str(results_dir / "agent_a_result.json"),
                    str(results_dir / "agent_b_result.json"),
                    str(results_dir / "agent_c_result.json"),
                ],
                "do_not_skip": "Do not leave subagent results only in chat transcripts.",
            },
            {
                "step": 5,
                "name": "convergence_and_disposition",
                "required": True,
                "gate": "three agent result files are present",
                "tool": "python result_review_framework/scripts/convergence_compare.py <review_dir>",
                "do": [
                    "Summarize consensus, majority, single-party, and divergent findings",
                    "Aggregate mechanical_dispositions across all agents",
                    "Aggregate high_risk_modules across all agents",
                ],
                "outputs": [
                    str(review_dir / "convergence_report.json"),
                    str(review_dir / "convergence_report.md"),
                ],
                "do_not_skip": "Do not copy mechanical precheck issues directly into the final report without disposition.",
            },
            {
                "step": 6,
                "name": "write_final_reports",
                "required": True,
                "gate": "convergence_report.json and convergence_report.md exist",
                "outputs": [
                    str(review_dir / "coverage_matrix.md"),
                    str(review_dir / "fact_check_list.md"),
                    str(review_dir / "unresolved_items.md"),
                    str(review_dir / "final_review_report.md"),
                ],
                "do_not_skip": "final_review_report.md must include the required sections defined in the canonical policy.",
            },
            {
                "step": 7,
                "name": "finalize_and_publish",
                "required": True,
                "gate": "final_review_report.md exists",
                "tool": "python result_review_framework/scripts/finalize_audit.py <review_dir>",
                "outputs": [
                    str(review_dir / "final_report_lint.json"),
                    str(review_dir / "audit_state.json"),
                    str(review_dir / f"{review_dir.name}_audit_report.html"),
                ],
                "do": [
                    "Run lint, autofix, backfill, state sync, and HTML publication as one deterministic flow",
                    "Keep archive approval separate from publication success",
                ],
                "do_not_skip": "Do not archive the project from inside HTML publication.",
            },
        ],
        "subagents": {
            "A": {
                "focus": "coverage completeness and evidence sufficiency",
                "prompt_file": str(prompt_dir / "agent_a_prompt.md"),
                "result_file": str(results_dir / "agent_a_result.json"),
            },
            "B": {
                "focus": "fact correctness and text/table/figure consistency",
                "prompt_file": str(prompt_dir / "agent_b_prompt.md"),
                "result_file": str(results_dir / "agent_b_result.json"),
            },
            "C": {
                "focus": "method-code consistency, statistics, and high-risk modules",
                "prompt_file": str(prompt_dir / "agent_c_prompt.md"),
                "result_file": str(results_dir / "agent_c_result.json"),
            },
        },
        "mechanical_check_policy": {
            "all_codes_must_have_disposition": policy["mechanical_check_policy"][
                "all_codes_must_have_disposition"
            ],
            "special_rules": policy["mechanical_check_policy"]["special_rules"],
        },
        "high_risk_module_policy": {
            "required_dimensions": policy["high_risk_module_policy"]["required_dimensions"],
            "target_modules": policy["high_risk_module_policy"]["target_modules"],
            "minimum_evidence_packages": policy["high_risk_module_policy"][
                "minimum_evidence_packages"
            ],
        },
        "finding_evidence_policy": policy["finding_evidence_policy"],
        "rereview_policy": {
            "build_diff_when_previous_review_exists": policy["rereview_policy"][
                "must_build_rereview_diff"
            ],
            "tool": "python result_review_framework/scripts/build_rereview_diff.py <old_review_dir> <new_review_dir>",
        },
        "required_final_files": policy["required_final_files"] + ["<project_id>_audit_report.html"],
        "canonical_entrypoints": policy["canonical_entrypoints"],
        "reference_only_docs": policy["reference_only_docs"],
        "precheck_snapshot": precheck,
    }


def main() -> int:
    review_dir, project_dir = parse_args(sys.argv)
    if not review_dir.exists():
        raise FileNotFoundError(f"Review directory does not exist: {review_dir}")

    policy = load_policy()
    prompt_dir = review_dir / "agent_prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "agent_results").mkdir(parents=True, exist_ok=True)

    precheck = load_precheck_results(review_dir)
    report_excerpt = load_report_excerpt(review_dir)

    prompts = {
        "agent_a_prompt.md": build_agent_prompt(
            "A", _AGENT_A_EMPHASIS, review_dir, project_dir, precheck, report_excerpt
        ) + build_evidence_appendix(policy),
        "agent_b_prompt.md": build_agent_prompt(
            "B", _AGENT_B_EMPHASIS, review_dir, project_dir, precheck, report_excerpt
        ) + build_evidence_appendix(policy),
        "agent_c_prompt.md": build_agent_prompt(
            "C", _AGENT_C_EMPHASIS, review_dir, project_dir, precheck, report_excerpt
        ) + build_evidence_appendix(policy),
        "convergence_guide.md": build_convergence_guide(review_dir, precheck),
    }

    for name, content in prompts.items():
        (prompt_dir / name).write_text(content, encoding="utf-8")

    manifest = build_manifest(review_dir, project_dir, precheck)
    manifest_path = review_dir / "ai_execution_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    state = build_state(review_dir)
    state_path = review_dir / "audit_state.json"
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    append_event(
        review_dir,
        "ai_guardrails_generated",
        actor="prepare_ai_audit_guardrails",
        outputs=[str(manifest_path), str(state_path)],
        details={"review_lane": manifest.get("review_lane", "standard")},
    )

    print(f"AI guardrail manifest generated: {manifest_path}")
    print(f"Audit state generated: {state_path}")
    print(f"Agent prompts generated: {prompt_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
