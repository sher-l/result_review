#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Prepare a final report for leader confirmation without publishing or notifying."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from audit_contract import atomic_write_json, sha256_file, utc_offset_now
from audit_runtime import append_event
from finalize_audit import run_lint_step, run_required_step
from policy_loader import load_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run mutable lint/autofix/backfill preparation. This command never publishes, "
            "notifies, or archives."
        )
    )
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    return parser.parse_args()


def _confirmed_decision_exists(review_dir: Path, decision_name: str) -> bool:
    decision_path = review_dir / decision_name
    if not decision_path.is_file():
        return False
    try:
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(decision, dict) and decision.get("status") == "leader_confirmed"


def _depth_gate_failures(lint_data: dict) -> list[str]:
    """Return content-depth blockers that must be repaired by the report author."""
    if not isinstance(lint_data, dict):
        return []
    errors = lint_data.get("errors", [])
    if not isinstance(errors, list) or not errors:
        errors = lint_data.get("checks", [])
    if not isinstance(errors, list):
        return []
    return [
        str(item.get("id", ""))
        for item in errors
        if isinstance(item, dict)
        and item.get("passed") is False
        and str(item.get("id", "")).startswith("depth:")
    ]


def main() -> int:
    args = parse_args()
    review_dir = Path(args.review_dir)
    if not review_dir.is_dir():
        raise FileNotFoundError(f"Review directory does not exist: {review_dir}")

    policy = load_policy()
    contract_policy = policy.get("audit_contract_policy", {})
    if not isinstance(contract_policy, dict):
        contract_policy = {}
    decision_name = str(contract_policy.get("decision_json", "final_decision.json") or "final_decision.json")
    if _confirmed_decision_exists(review_dir, decision_name):
        message = f"Refusing mutable preparation after leader confirmation: {decision_name}"
        print(message, file=sys.stderr)
        append_event(
            review_dir,
            "audit_finalize_prepare_blocked",
            actor="prepare_audit_finalize",
            status="error",
            details={"reason": message},
        )
        return 1

    outputs: list[str] = []
    append_event(review_dir, "audit_finalize_prepare_started", actor="prepare_audit_finalize")
    try:
        run_required_step(review_dir, "check_subagent_supervision.py", outputs)
        lint_completed, lint_data = run_lint_step(review_dir, outputs, "initial")
        lint_passed = bool(lint_data.get("passed", False))
        depth_failures = _depth_gate_failures(lint_data)

        if depth_failures:
            message = "Final report depth gate requires author evidence; automatic autofix/backfill is blocked"
            append_event(
                review_dir,
                "final_report_depth_incomplete",
                actor="prepare_audit_finalize",
                status="error",
                details={"failed_checks": depth_failures},
                outputs=outputs,
            )
            print(f"{message}: {', '.join(depth_failures)}", file=sys.stderr)
            return lint_completed.returncode or 1

        if not lint_passed:
            run_required_step(review_dir, "generate_lint_autofix_plan.py", outputs)
            run_required_step(review_dir, "apply_lint_autofix_plan.py", outputs)
            lint_completed, lint_data = run_lint_step(review_dir, outputs, "post_autofix")
            lint_passed = bool(lint_data.get("passed", False))

        if not lint_passed:
            run_required_step(review_dir, "generate_required_section_backfill.py", outputs)
            run_required_step(review_dir, "apply_required_section_backfill.py", outputs)
            lint_completed, lint_data = run_lint_step(review_dir, outputs, "final")
            lint_passed = bool(lint_data.get("passed", False))
    except RuntimeError as exc:
        append_event(
            review_dir,
            "audit_finalize_prepare_failed",
            actor="prepare_audit_finalize",
            status="error",
            details={"error": str(exc)},
            outputs=outputs,
        )
        print(str(exc), file=sys.stderr)
        return 1

    if not lint_passed:
        append_event(
            review_dir,
            "audit_finalize_prepare_failed",
            actor="prepare_audit_finalize",
            status="error",
            details={
                "failed_stage": "final_lint_gate",
                "error_count": lint_data.get("error_count", 0),
                "warning_count": lint_data.get("warning_count", 0),
            },
            outputs=outputs,
        )
        return lint_completed.returncode or 1

    report_path = review_dir / "final_review_report.md"
    result_path = review_dir / "audit_finalize_prepare_result.json"
    result = {
        "schema_version": "1.0",
        "generated_at": utc_offset_now(),
        "status": "ready_for_leader_confirmation",
        "report_path": report_path.name,
        "report_sha256": sha256_file(report_path) if report_path.is_file() else "",
        "outputs": outputs,
    }
    atomic_write_json(result_path, result)
    append_event(
        review_dir,
        "audit_finalize_prepared",
        actor="prepare_audit_finalize",
        outputs=outputs + [str(result_path)],
        details={"report_sha256": result["report_sha256"]},
    )
    print(f"Audit finalize preparation completed: {review_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
