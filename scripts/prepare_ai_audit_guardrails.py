#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generate machine-readable guardrails for the formal AI audit flow.

Outputs:
1. ai_execution_manifest.json
2. audit_state.json
3. agent_prompts/agent_slice_manifest.json
4. agent_prompts/slices/*.md
5. agent_prompts/agent_a_prompt.md
6. agent_prompts/agent_b_prompt.md
7. agent_prompts/agent_c_prompt.md
8. agent_prompts/convergence_guide.md
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from audit_runtime import (
    append_event,
    load_case_manifest,
    current_policy_binding,
    rebuild_case_manifest_policy_binding,
    validate_framework_binding,
)
from launch_convergence_audit import (
    _AGENT_A_EMPHASIS,
    _AGENT_B_EMPHASIS,
    _AGENT_C_EMPHASIS,
    SLICE_SPECS,
    build_agent_prompt,
    build_convergence_guide,
    build_slice_manifest,
    build_slice_prompt,
    load_precheck_results,
    load_report_excerpt,
    slice_output_path,
    slice_prompt_path,
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
    appendix_policy = policy.get("report_appendix_policy", {})
    appendix_lines = ""
    if appendix_policy:
        markers = ", ".join(
            f"`{item}`" for item in appendix_policy.get("boilerplate_markers", [])
        )
        appendix_lines = f"""

## Report Appendix Policy

- Boilerplate company promo pages after the references section are out of formal audit scope by default.
- Default markers: {markers}
- Only escalate if the promo content appears before references or contaminates numbered body sections.
"""
    return f"""

## Structured Evidence Requirement

Every finding must include these fields:
{required_fields}

Allowed `source_type` values: {allowed_source_types}

If any required field is missing, the finding is incomplete.
Do not use vague shortcut phrases without bound evidence:
{forbidden_shortcuts}
{appendix_lines}
"""


def parse_args(argv: list[str]) -> tuple[Path, Path | None, bool]:
    if len(argv) < 2:
        raise SystemExit(
            "Usage: python prepare_ai_audit_guardrails.py <review_dir> "
            "[--project-dir <project_dir>] [--rebuild-policy-binding]"
        )

    review_dir = Path(argv[1])
    project_dir = None
    rebuild_policy_binding = "--rebuild-policy-binding" in argv
    if "--project-dir" in argv:
        index = argv.index("--project-dir")
        if index + 1 < len(argv):
            project_dir = Path(argv[index + 1])
    return review_dir, project_dir, rebuild_policy_binding


def build_manifest(review_dir: Path, project_dir: Path | None, precheck: dict) -> dict:
    policy = load_policy()
    policy_binding = current_policy_binding()
    prompt_dir = review_dir / "agent_prompts"
    results_dir = review_dir / "agent_results"
    slice_prompt_dir = prompt_dir / "slices"
    slice_results_dir = results_dir / "slices"
    case_manifest = load_case_manifest(review_dir)
    default_lane = str(
        policy.get("review_lane_policy", {}).get("default_lane", "strict") or "strict"
    )
    review_lane = case_manifest.get("review_lane", default_lane)

    return {
        "schema_version": "1.4",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": policy.get("mode", "formal_audit"),
        "policy_version": policy.get("framework_version", ""),
        "policy_sha256": policy_binding["policy_sha256"],
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
            "slice_prompt_dir": str(slice_prompt_dir),
            "agent_results_dir": str(results_dir),
            "slice_results_dir": str(slice_results_dir),
            "agent_slice_manifest": str(prompt_dir / "agent_slice_manifest.json"),
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
                    "Confirm report_text.txt exists and read only summary/needed local line ranges in leader context",
                    "Read project_structure.json summary fields/path index; do not paste the full JSON into leader chat",
                    "Read report_structure.json summary fields/Figure-Table index",
                    "Read mechanical_check_result.json summary and codes requiring disposition",
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
                "name": "launch_small_slice_subagents",
                "required": True,
                "gate": "formal audit is in progress",
                "do": [
                    "Read agent_slice_manifest.json first",
                    "Launch small slice subagents in batches; max 4 concurrent slice agents",
                    "Lead is supervisor/integrator only: do not expand long reports, long logs, full inventories, or large evidence in the leader context",
                    "Use the same model as the main/Lead agent for formal judgement slices (and the same reasoning effort when known); fast/mini/explore only for file mapping, inventories, schema checks, or grep-like lookup",
                    "Do not downshift severity judgement, cross-module consistency, statistical validity, high-risk module assessment, or final arbitration to weak models",
                    "Do not fork/copy the full leader context into slice agents",
                    "Require each slice agent to write its full JSON result to agent_results/slices/",
                    "Keep each slice independent until route-level merge",
                    "Preserve overlap context for judgement slices: report summary, conclusions, Figure/Table index, mechanical summary, case_manifest, and neighboring module dependencies",
                    "High-risk module slices must keep module-level context and must not be split too narrowly by single file",
                    "Write batch progress to review_event_log.jsonl and update the project-local subagent_supervision_summary.json after each batch",
                    "Require every finding to include structured evidence fields",
                ],
                "inputs": [
                    str(prompt_dir / "agent_slice_manifest.json"),
                    str(slice_prompt_dir),
                ],
                "do_not_skip": "If the user says start audit / audit next / re-review, small-slice subagents are mandatory by default; do not launch one large subagent per route.",
            },
            {
                "step": 4,
                "name": "merge_slice_outputs_to_three_routes",
                "required": True,
                "gate": "all required slice result files are present",
                "do": [
                    "Use agent_a_prompt.md, agent_b_prompt.md, and agent_c_prompt.md only as merge prompts",
                    "Merge slice JSON files into the three convergence input JSON files",
                    "Do not re-open and fully audit report_text.txt during merge",
                    "Flag slice conflicts, missing overlap context, and local-pass/global-fail risks for Lead arbitration",
                ],
                "outputs": [
                    str(results_dir / "agent_a_result.json"),
                    str(results_dir / "agent_b_result.json"),
                    str(results_dir / "agent_c_result.json"),
                ],
                "slice_outputs": [str(slice_output_path(review_dir, spec)) for spec in SLICE_SPECS],
                "do_not_skip": "Do not leave subagent results only in chat transcripts; every slice must have a persisted JSON artifact.",
            },
            {
                "step": 5,
                "name": "convergence_and_disposition",
                "required": True,
                "gate": "three merged agent result files are present and slice JSON validation passed",
                "tool": "python result_review_framework/scripts/convergence_compare.py <review_dir>",
                "do": [
                    "Summarize consensus, majority, single-party, and divergent findings",
                    "Lead must perform global consistency review: coverage gaps, conflicting slice findings, broken cross-module dependencies, local-pass/global-fail cases, and unassigned high-risk modules",
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
                "do_not_skip": "final_review_report.md must start with no more than five evidence-backed submission-blocking issues; each requires evidence, impact, and an acceptance-ready remediation. Put non-core findings in the compact secondary section instead of repeating checklist prose.",
            },
            {
                "step": 7,
                "name": "prepare_and_seal_final",
                "required": True,
                "gate": "final_review_report.md exists",
                "tool": "python result_review_framework/scripts/prepare_audit_finalize.py <review_dir>",
                "outputs": [
                    str(review_dir / "final_report_lint.json"),
                    str(review_dir / "final_decision.json"),
                ],
                "do": [
                    "Run lint/autofix/backfill before leader confirmation",
                    "Leader confirms score, verdict, counts, and source hashes in final_decision.json",
                ],
                "do_not_skip": "Do not notify, archive, or modify the report after final_decision.json is confirmed.",
            },
            {
                "step": 8,
                "name": "validate_publish_notify_archive",
                "required": True,
                "gate": "final_decision.json is leader_confirmed and source hashes match",
                "tool": "python result_review_framework/scripts/finalize_audit.py <review_dir>",
                "outputs": [
                    str(review_dir / "professional_contract_validation.json"),
                    str(review_dir / "audit_contract_validation.json"),
                    str(review_dir / "audit_state.json"),
                    str(review_dir / f"{review_dir.name}_audit_report.html"),
                ],
                "do": [
                    "Validate arbitration v2 and professional structured artifacts before the sealed decision gate",
                    "Verify sealed artifacts without rewriting them",
                    "Run all local gates before any notification or archive action",
                    "Use the notification receipt to prevent automatic duplicate sends",
                ],
                "do_not_skip": "Gate failures stay local; tests and shadow replays must never send external notifications.",
            },
        ],
        "subagent_compact_policy": {
            "mode": "small_slice_subagents_then_three_route_merge",
            "max_parallel_slice_agents": 4,
            "must_persist_slice_results": True,
            "must_not_fork_full_context": True,
            "must_checkpoint_between_batches": True,
            "chat_output": "short_status_only",
            "model_quality": policy.get("subagent_compact_policy", {}).get("model_quality_policy", {}),
            "overlap_and_global_review": policy.get("subagent_compact_policy", {}).get("overlap_and_global_review", {}),
            "rationale": "Avoid remote compact failures by preventing any single subagent from auditing the full project; if a subagent still compacts, split the work further before retrying, while preserving the same model as the Lead agent for judgement slices.",
        },
        "subagents": {
            "A": {
                "focus": "coverage completeness and evidence sufficiency",
                "merge_prompt_file": str(prompt_dir / "agent_a_prompt.md"),
                "result_file": str(results_dir / "agent_a_result.json"),
                "slice_prompts": [
                    str(slice_prompt_path(review_dir, spec)) for spec in SLICE_SPECS if spec["agent"] == "A"
                ],
                "slice_results": [
                    str(slice_output_path(review_dir, spec)) for spec in SLICE_SPECS if spec["agent"] == "A"
                ],
            },
            "B": {
                "focus": "fact correctness and text/table/figure consistency",
                "merge_prompt_file": str(prompt_dir / "agent_b_prompt.md"),
                "result_file": str(results_dir / "agent_b_result.json"),
                "slice_prompts": [
                    str(slice_prompt_path(review_dir, spec)) for spec in SLICE_SPECS if spec["agent"] == "B"
                ],
                "slice_results": [
                    str(slice_output_path(review_dir, spec)) for spec in SLICE_SPECS if spec["agent"] == "B"
                ],
            },
            "C": {
                "focus": "method-code consistency, statistics, and high-risk modules",
                "merge_prompt_file": str(prompt_dir / "agent_c_prompt.md"),
                "result_file": str(results_dir / "agent_c_result.json"),
                "slice_prompts": [
                    str(slice_prompt_path(review_dir, spec)) for spec in SLICE_SPECS if spec["agent"] == "C"
                ],
                "slice_results": [
                    str(slice_output_path(review_dir, spec)) for spec in SLICE_SPECS if spec["agent"] == "C"
                ],
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
        "report_appendix_policy": policy.get("report_appendix_policy", {}),
        "finding_evidence_policy": policy["finding_evidence_policy"],
        "audit_contract_policy": policy.get("audit_contract_policy", {}),
        "notification_idempotency_policy": policy.get("notification_idempotency_policy", {}),
        "visual_closure_policy": policy.get("visual_closure_policy", {}),
        "professional_contract_policy": policy.get("professional_contract_policy", {}),
        "rereview_policy": {
            "build_diff_when_previous_review_exists": policy["rereview_policy"][
                "must_build_rereview_diff"
            ],
            "tool": "python result_review_framework/scripts/build_rereview_diff.py <old_review_dir> <new_review_dir>",
        },
        "required_final_files": policy["required_final_files"] + ["<project_id>_audit_report.html"],
        "mode_aware_final_files": [
            policy.get("audit_contract_policy", {}).get("decision_json", "final_decision.json"),
            policy.get("audit_contract_policy", {}).get("validation_json", "audit_contract_validation.json"),
            policy.get("visual_closure_policy", {}).get("result_json", "visual_audit_result.json"),
            policy.get("notification_idempotency_policy", {}).get("receipt_json", "completion_notification_receipt.json"),
        ],
        "canonical_entrypoints": policy["canonical_entrypoints"],
        "reference_only_docs": policy["reference_only_docs"],
        "precheck_snapshot": precheck,
    }


def main() -> int:
    review_dir, project_dir, rebuild_policy_binding = parse_args(sys.argv)
    if not review_dir.exists():
        raise FileNotFoundError(f"Review directory does not exist: {review_dir}")

    if rebuild_policy_binding:
        rebuild_case_manifest_policy_binding(review_dir)
    binding_errors = validate_framework_binding(
        review_dir,
        require_ai_execution_manifest=False,
    )
    if binding_errors:
        raise RuntimeError(
            "Policy binding gate failed; rerun canonical precheck for a new review, "
            "or use --rebuild-policy-binding before explicitly regenerating guardrails: "
            + "; ".join(binding_errors)
        )

    policy = load_policy()
    prompt_dir = review_dir / "agent_prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "slices").mkdir(parents=True, exist_ok=True)
    (review_dir / "agent_results").mkdir(parents=True, exist_ok=True)
    (review_dir / "agent_results" / "slices").mkdir(parents=True, exist_ok=True)

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

    for spec in SLICE_SPECS:
        slice_prompt_path(review_dir, spec).write_text(
            build_slice_prompt(spec, review_dir, project_dir, precheck, report_excerpt),
            encoding="utf-8",
        )

    slice_manifest_path = prompt_dir / "agent_slice_manifest.json"
    slice_manifest_path.write_text(
        json.dumps(build_slice_manifest(review_dir), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

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
        details={"review_lane": manifest["review_lane"]},
    )

    print(f"AI guardrail manifest generated: {manifest_path}")
    print(f"Audit state generated: {state_path}")
    print(f"Agent prompts generated: {prompt_dir}")
    print(f"Small-slice prompts generated: {prompt_dir / 'slices'}")
    print(f"Small-slice manifest generated: {slice_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
