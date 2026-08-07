#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Backward-compatible audit notification wrapper.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from notification_client import (
    build_body,
    load_config,
    send_notification,
    validate_notification_request,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send audit completion notification.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--status", required=True, help="completed / blocked / failed")
    parser.add_argument("--review-dir", required=True)
    parser.add_argument("--html-path", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument("--audit-file", default="", help="Original audited file/project name shown in the notification body.")
    parser.add_argument("--report-file", default="", help="Display name/path for the final audit report.")
    parser.add_argument("--audit-result", default="", help="Formal audit verdict shown in the notification body.")
    parser.add_argument("--issue-stats", default="", help="Formal issue statistics shown in the notification body.")
    parser.add_argument("--critical", default="", help="CRITICAL issue count for the fixed formal audit result line.")
    parser.add_argument("--major", default="", help="MAJOR issue count for the fixed formal audit result line.")
    parser.add_argument("--warning", default="", help="WARNING issue count for the fixed formal audit result line.")
    parser.add_argument("--config", default="")
    parser.add_argument(
        "--formal-audit",
        action="store_true",
        help="Allow Enterprise WeChat only for a real/formal audit completion notification.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.status.strip().lower() == "completed":
        print(
            "Direct audit completion notification is disabled. "
            "Use finalize_audit.py so the formal delivery manifest and receipt are bound."
        )
        return 1
    metadata = {
        "项目号": args.project_id,
        "项目编号": args.project_id,
        "project_id": args.project_id,
        "审核目录": args.review_dir,
    }
    if args.audit_file:
        metadata["审核文件"] = args.audit_file
    if args.html_path:
        metadata["HTML"] = args.html_path
    report_file = args.report_file.strip()
    if not report_file and args.html_path:
        report_file = Path(args.html_path).name
    if report_file:
        metadata["报告文件"] = report_file
    if args.audit_result:
        metadata["审核结果"] = args.audit_result
    if args.issue_stats:
        metadata["问题统计"] = args.issue_stats
    if args.critical:
        metadata["critical"] = args.critical
    if args.major:
        metadata["major"] = args.major
    if args.warning:
        metadata["warning"] = args.warning
    if args.formal_audit:
        metadata["formal_audit"] = "true"

    valid, reason = validate_notification_request("audit", args.status, metadata)
    if not valid:
        print(reason)
        return 1

    body_preview = build_body(
        task_type="audit",
        task_name=f"审核完成 {args.project_id}",
        status=args.status,
        summary=args.summary,
        metadata=metadata,
        config=load_config(args.config),
    )
    print("notification body preview:")
    print(body_preview)

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
