#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Synchronize audit_state.json from the files currently present in a review directory.

This script turns the audit workflow into a machine-readable state machine so that
agents can determine the next mandatory step without guessing.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from audit_runtime import detect_html_path, infer_project_id, load_case_manifest, read_json

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synchronize audit_state.json for a review directory."
    )
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    parser.add_argument(
        "--output",
        "-o",
        help="Optional explicit path for audit_state.json (default: <review_dir>/audit_state.json)",
    )
    return parser.parse_args()

def check_outputs(paths: list[Path]) -> tuple[bool, list[str]]:
    missing = [str(path) for path in paths if not path.exists()]
    return not missing, missing


def build_phase_definitions(review_dir: Path) -> list[dict]:
    agent_results = review_dir / "agent_results"
    html_path = detect_html_path(review_dir)
    return [
        {
            "id": "precheck_ready",
            "title": "Precheck Ready",
            "required_outputs": [
                review_dir / "report_text.txt",
                review_dir / "report_structure.json",
                review_dir / "project_structure.json",
                review_dir / "mechanical_check_result.json",
                review_dir / "case_manifest.json",
                review_dir / "ai_execution_manifest.json",
            ],
            "tool": "python result_review_framework/scripts/auto_audit_pipeline.py <project_dir>",
        },
        {
            "id": "visual_audit_ready",
            "title": "Visual Audit Ready",
            "required_outputs": [
                review_dir / "figure_audit.md",
            ],
            "tool": "Complete Layer 2 full visual audit",
        },
        {
            "id": "agent_results_ready",
            "title": "Three Agent Results Ready",
            "required_outputs": [
                agent_results / "agent_a_result.json",
                agent_results / "agent_b_result.json",
                agent_results / "agent_c_result.json",
            ],
            "tool": "Run three subagents using agent_prompts/",
        },
        {
            "id": "convergence_ready",
            "title": "Convergence Ready",
            "required_outputs": [
                review_dir / "convergence_report.json",
                review_dir / "convergence_report.md",
            ],
            "tool": "python result_review_framework/scripts/convergence_compare.py <review_dir>",
        },
        {
            "id": "final_reports_ready",
            "title": "Final Reports Ready",
            "required_outputs": [
                review_dir / "coverage_matrix.md",
                review_dir / "fact_check_list.md",
                review_dir / "unresolved_items.md",
                review_dir / "final_review_report.md",
            ],
            "tool": "Write the markdown deliverables",
        },
        {
            "id": "final_report_validated",
            "title": "Final Report Validated",
            "required_outputs": [
                review_dir / "final_report_lint.json",
            ],
            "tool": "python result_review_framework/scripts/final_report_linter.py <review_dir>",
        },
        {
            "id": "autofix_plan_ready",
            "title": "Autofix Plan Ready",
            "required_outputs": [
                review_dir / "lint_autofix_plan.json",
            ],
            "tool": "python result_review_framework/scripts/generate_lint_autofix_plan.py <review_dir>",
        },
        {
            "id": "autofix_applied",
            "title": "Autofix Applied",
            "required_outputs": [
                review_dir / "lint_autofix_apply_report.json",
            ],
            "tool": "python result_review_framework/scripts/apply_lint_autofix_plan.py <review_dir>",
        },
        {
            "id": "section_backfill_ready",
            "title": "Section Backfill Ready",
            "required_outputs": [
                review_dir / "final_report_backfill_plan.json",
            ],
            "tool": "python result_review_framework/scripts/generate_required_section_backfill.py <review_dir>",
        },
        {
            "id": "section_backfill_applied",
            "title": "Section Backfill Applied",
            "required_outputs": [
                review_dir / "final_report_backfill_apply_report.json",
            ],
            "tool": "python result_review_framework/scripts/apply_required_section_backfill.py <review_dir>",
        },
        {
            "id": "delivery_ready",
            "title": "HTML Delivery Ready",
            "required_outputs": [
                html_path,
            ],
            "tool": "python result_review_framework/scripts/ensure_review_html.py <review_dir>",
        },
        {
            "id": "archive_ready",
            "title": "Archive Ready",
            "required_outputs": [],
            "tool": "python result_review_framework/scripts/archive_reviewed_project.py <review_dir>",
        },
    ]


def lint_phase_completed(review_dir: Path) -> tuple[bool, list[str], dict]:
    lint_path = review_dir / "final_report_lint.json"
    if not lint_path.exists():
        return False, [str(lint_path)], {}
    lint_data = read_json(lint_path)
    if not lint_data.get("passed", False):
        return False, ["final_report_lint.json exists but did not pass"], lint_data
    return True, [], lint_data


def build_state(review_dir: Path) -> dict:
    phases = build_phase_definitions(review_dir)
    case_manifest = load_case_manifest(review_dir)
    publish_status = case_manifest.get("publish_status", "pending")
    archive_approved = bool(case_manifest.get("archive_approved", False))
    state_phases = []
    previous_complete = True
    current_phase = "completed"
    lint_data = {}

    for phase in phases:
        if phase["id"] == "final_report_validated":
            complete, missing, lint_data = lint_phase_completed(review_dir)
        elif phase["id"] == "archive_ready":
            archived = bool(case_manifest.get("archived_at"))
            if archive_approved:
                complete = archived
                missing = [] if archived else ["archive approval exists but archive has not been executed"]
            else:
                complete = True
                missing = []
        else:
            complete, missing = check_outputs(phase["required_outputs"])

        if complete:
            status = "completed"
        elif previous_complete and current_phase == "completed":
            status = "in_progress"
            current_phase = phase["id"]
            previous_complete = False
        else:
            status = "blocked"
            previous_complete = False

        state_phases.append(
            {
                "id": phase["id"],
                "title": phase["title"],
                "status": status,
                "tool": phase["tool"],
                "required_outputs": [str(path) for path in phase["required_outputs"]],
                "missing_outputs": missing,
            }
        )

    all_completed = all(phase["status"] == "completed" for phase in state_phases)
    if all_completed:
        current_phase = "completed"
    if publish_status != "success":
        all_completed = False

    blocked_reason = ""
    for phase in state_phases:
        if phase["status"] == "in_progress" and phase["missing_outputs"]:
            blocked_reason = f"{phase['id']} missing outputs"
            break

    return {
        "schema_version": "1.1",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "review_dir": str(review_dir),
        "project_id": infer_project_id(review_dir),
        "review_lane": case_manifest.get("review_lane", "standard"),
        "current_phase": current_phase,
        "all_completed": all_completed,
        "blocked_reason": blocked_reason,
        "lint_passed": lint_data.get("passed", False),
        "publish_status": publish_status,
        "archive_approved": archive_approved,
        "archived_at": case_manifest.get("archived_at", ""),
        "phases": state_phases,
        "steps": state_phases,
    }


def main() -> int:
    args = parse_args()
    review_dir = Path(args.review_dir)
    if not review_dir.exists():
        raise FileNotFoundError(f"Review directory does not exist: {review_dir}")

    state = build_state(review_dir)
    output_path = Path(args.output) if args.output else review_dir / "audit_state.json"
    output_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"audit_state.json synchronized: {output_path}")
    print(f"Current phase: {state['current_phase']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
