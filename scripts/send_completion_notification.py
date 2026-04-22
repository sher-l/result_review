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
    ok, message = send_notification(
        task_type=args.task_type,
        task_name=args.task_name,
        status=args.status,
        summary=args.summary,
        metadata=parse_meta(args.meta),
        config_arg=args.config,
    )
    print(message)
    return 0 if ok or "skipped" in message else 1


if __name__ == "__main__":
    raise SystemExit(main())
