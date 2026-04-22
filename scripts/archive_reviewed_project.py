#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Archive a reviewed project only after publication succeeds and approval is explicit."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from audit_runtime import append_event, detect_html_path, load_case_manifest, update_case_manifest
from ensure_review_html import move_reviewed_project


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Move a reviewed project from raw/待审核 to raw/已AI审核一次 only when explicitly approved."
    )
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Mark archive_approved=true before attempting the move.",
    )
    return parser.parse_args()


def archive_reviewed_project(review_dir: Path, *, approve: bool = False) -> Path:
    manifest = load_case_manifest(review_dir)
    if not manifest:
        raise FileNotFoundError(f"case_manifest.json not found: {review_dir}")

    if approve:
        manifest = update_case_manifest(
            review_dir,
            {
                "archive_approved": True,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

    if manifest.get("publish_status") != "success":
        raise RuntimeError("Cannot archive before publish_status=success.")

    html_path = detect_html_path(review_dir)
    if not html_path.exists():
        raise RuntimeError("Cannot archive before the canonical HTML report exists.")

    if not manifest.get("archive_approved", False):
        raise RuntimeError("Cannot archive before archive_approved=true.")

    moved_to = move_reviewed_project(review_dir)
    if moved_to is None:
        raise RuntimeError("Archive move did not run. Check manifest project_dir/source archive metadata.")

    update_case_manifest(
        review_dir,
        {
            "archived_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    append_event(
        review_dir,
        "project_archived",
        actor="archive_reviewed_project",
        outputs=[str(moved_to)],
        details={"html_path": str(html_path)},
    )
    return moved_to


def main() -> int:
    args = parse_args()
    review_dir = Path(args.review_dir)
    if not review_dir.exists():
        raise FileNotFoundError(f"Review directory does not exist: {review_dir}")

    moved_to = archive_reviewed_project(review_dir, approve=args.approve)
    print(f"项目已移动到: {moved_to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
