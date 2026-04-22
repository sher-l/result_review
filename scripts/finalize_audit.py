#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Finalize an audit in one deterministic command."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from archive_reviewed_project import archive_reviewed_project
from audit_runtime import append_event, detect_html_path, update_case_manifest
from policy_loader import load_policy


SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run lint, autofix, backfill, state sync, and HTML publication as one flow."
    )
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    parser.add_argument(
        "--archive-approved",
        action="store_true",
        help="Force auto archive after successful publication.",
    )
    parser.add_argument(
        "--no-auto-archive",
        action="store_true",
        help="Publish HTML and state only; do not move the reviewed project after finalize.",
    )
    return parser.parse_args()


def run_step(review_dir: Path, script_name: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT_DIR / script_name), str(review_dir)]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )


def should_auto_archive(args: argparse.Namespace, policy: dict) -> bool:
    if args.no_auto_archive:
        return False
    if args.archive_approved:
        return True
    return bool(policy.get("publish_archive_policy", {}).get("auto_archive_after_finalize", False))


def main() -> int:
    args = parse_args()
    review_dir = Path(args.review_dir)
    if not review_dir.exists():
        raise FileNotFoundError(f"Review directory does not exist: {review_dir}")
    if args.archive_approved and args.no_auto_archive:
        raise ValueError("Cannot combine --archive-approved and --no-auto-archive.")

    policy = load_policy()
    auto_archive = should_auto_archive(args, policy)
    append_event(review_dir, "finalize_started", actor="finalize_audit")
    step_order = [
        "final_report_linter.py",
        "generate_lint_autofix_plan.py",
        "apply_lint_autofix_plan.py",
        "final_report_linter.py",
        "generate_required_section_backfill.py",
        "apply_required_section_backfill.py",
        "final_report_linter.py",
        "sync_audit_state.py",
        "ensure_review_html.py",
        "sync_audit_state.py",
    ]

    outputs = []
    for script_name in step_order:
        completed = run_step(review_dir, script_name)
        if completed.stdout.strip():
            print(completed.stdout.strip())
        if completed.returncode != 0:
            if completed.stderr.strip():
                print(completed.stderr.strip(), file=sys.stderr)
            update_case_manifest(
                review_dir,
                {
                    "publish_status": "failed",
                    "archive_approved": False,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            append_event(
                review_dir,
                "finalize_failed",
                actor="finalize_audit",
                status="error",
                details={"failed_script": script_name, "stderr": completed.stderr.strip()},
            )
            return completed.returncode
        outputs.append(script_name)

    html_path = detect_html_path(review_dir)
    publish_status = "success" if html_path.exists() else "failed"
    update_case_manifest(
        review_dir,
        {
            "publish_status": publish_status,
            "archive_approved": False,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )

    archived_to: Path | None = None
    if publish_status == "success" and auto_archive:
        try:
            archived_to = archive_reviewed_project(review_dir, approve=True)
            print(f"Archived reviewed project: {archived_to}")
            outputs.extend(["archive_reviewed_project.py", str(archived_to)])
        except Exception as exc:
            update_case_manifest(
                review_dir,
                {
                    "archive_approved": False,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            sync_completed = run_step(review_dir, "sync_audit_state.py")
            if sync_completed.stdout.strip():
                print(sync_completed.stdout.strip())
            if sync_completed.stderr.strip():
                print(sync_completed.stderr.strip(), file=sys.stderr)
            append_event(
                review_dir,
                "finalize_failed",
                actor="finalize_audit",
                status="error",
                details={"failed_stage": "auto_archive", "error": str(exc)},
            )
            return 1

        sync_completed = run_step(review_dir, "sync_audit_state.py")
        if sync_completed.stdout.strip():
            print(sync_completed.stdout.strip())
        if sync_completed.returncode != 0:
            if sync_completed.stderr.strip():
                print(sync_completed.stderr.strip(), file=sys.stderr)
            append_event(
                review_dir,
                "finalize_failed",
                actor="finalize_audit",
                status="error",
                details={"failed_script": "sync_audit_state.py", "failed_stage": "post_archive_sync"},
            )
            return sync_completed.returncode

    append_event(
        review_dir,
        "finalize_completed",
        actor="finalize_audit",
        outputs=outputs + ([str(html_path)] if html_path.exists() else []),
        details={
            "auto_archive": auto_archive,
            "archived": archived_to is not None,
            "html_exists": html_path.exists(),
        },
    )
    print(f"Finalize completed: {review_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
