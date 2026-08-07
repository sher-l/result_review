#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Send a generic completion notification through the shared webhook client.
"""

from __future__ import annotations

import argparse

from notification_client import send_notification


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a generic task completion notification.")
    parser.add_argument("--task-type", default="generic")
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--status", required=True, help="completed / blocked / failed")
    parser.add_argument("--summary", default="")
    parser.add_argument("--config", default="")
    parser.add_argument("--html-path", default="", help="Optional local HTML report path to upload as a notification file.")
    parser.add_argument(
        "--formal-audit",
        action="store_true",
        help="Allow Enterprise WeChat only for a real/formal audit completion notification.",
    )
    parser.add_argument(
        "--meta",
        action="append",
        default=[],
        help="Metadata in key=value format. Can be repeated.",
    )
    return parser.parse_args()


def parse_meta(items: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            metadata[key] = value
    return metadata


def main() -> int:
    args = parse_args()
    if args.task_type.strip().lower() == "audit" and args.status.strip().lower() == "completed":
        print(
            "Direct audit completion notification is disabled. "
            "Use finalize_audit.py so the formal delivery manifest and receipt are bound."
        )
        return 1
    metadata = parse_meta(args.meta)
    if args.html_path:
        metadata["HTML"] = args.html_path
    if args.formal_audit:
        metadata["formal_audit"] = "true"
    ok, message = send_notification(
        task_type=args.task_type,
        task_name=args.task_name,
        status=args.status,
        summary=args.summary,
        metadata=metadata,
        config_arg=args.config,
    )
    print(message)
    return 0 if ok or "skipped" in message else 1


if __name__ == "__main__":
    raise SystemExit(main())
