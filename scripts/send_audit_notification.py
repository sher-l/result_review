#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Backward-compatible audit notification wrapper.
"""

from __future__ import annotations

import argparse

from notification_client import send_notification


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send audit completion notification.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--status", required=True, help="completed / blocked / failed")
    parser.add_argument("--review-dir", required=True)
    parser.add_argument("--html-path", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument("--config", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metadata = {
        "项目编号": args.project_id,
        "审核目录": args.review_dir,
    }
    if args.html_path:
        metadata["HTML"] = args.html_path

    ok, message = send_notification(
        task_type="audit",
        task_name=f"审核完成 {args.project_id}",
        status=args.status,
        summary=args.summary,
        metadata=metadata,
        config_arg=args.config,
    )
    print(message)
    return 0 if ok or "skipped" in message else 1


if __name__ == "__main__":
    raise SystemExit(main())
