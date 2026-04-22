#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Apply safe markdown fixes from lint_autofix_plan.json.

This script only performs deterministic line-based edits that were marked
autofix-safe by the lint pipeline. It writes a structured apply report so the
workflow can track which changes were applied, skipped, or conflicted.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply lint_autofix_plan.json to markdown files in a review directory."
    )
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    parser.add_argument(
        "--output",
        "-o",
        help="Optional explicit path for lint_autofix_apply_report.json",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def group_items_by_file(items: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        grouped.setdefault(item["file"], []).append(item)
    return grouped


def apply_file_items(file_path: Path, items: list[dict], review_dir: Path) -> list[dict]:
    lines = file_path.read_text(encoding="utf-8").splitlines()
    results = []

    for item in sorted(items, key=lambda current: current["line"], reverse=True):
        line_no = item["line"]
        idx = line_no - 1
        status = "skipped"
        detail = ""

        if not str(file_path.resolve()).startswith(str(review_dir.resolve())):
            status = "conflict"
            detail = "target file outside review directory"
        elif idx < 0 or idx >= len(lines):
            status = "conflict"
            detail = "line out of range"
        elif lines[idx] == item["replacement"]:
            status = "already_applied"
            detail = "line already matches replacement"
        elif lines[idx] != item["original"]:
            status = "conflict"
            detail = "current line does not match expected original"
        elif item["operation"] == "replace_line":
            lines[idx] = item["replacement"]
            status = "applied"
            detail = "line replaced"
        elif item["operation"] == "delete_line":
            del lines[idx]
            status = "applied"
            detail = "line deleted"
        else:
            status = "conflict"
            detail = f"unsupported operation: {item['operation']}"

        result = dict(item)
        result["status"] = status
        result["detail"] = detail
        results.append(result)

    if any(result["status"] == "applied" for result in results):
        file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return list(reversed(results))


def build_report(review_dir: Path, plan: dict) -> dict:
    items = plan.get("items", [])
    grouped = group_items_by_file(items)
    applied_results = []

    for file_name, file_items in grouped.items():
        file_path = Path(file_name)
        if not file_path.exists():
            for item in file_items:
                missing = dict(item)
                missing["status"] = "conflict"
                missing["detail"] = "target file missing"
                applied_results.append(missing)
            continue
        applied_results.extend(apply_file_items(file_path, file_items, review_dir))

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "review_dir": str(review_dir),
        "source_plan_file": str(review_dir / "lint_autofix_plan.json"),
        "applied_count": sum(1 for item in applied_results if item["status"] == "applied"),
        "already_applied_count": sum(1 for item in applied_results if item["status"] == "already_applied"),
        "conflict_count": sum(1 for item in applied_results if item["status"] == "conflict"),
        "items": applied_results,
    }


def main() -> int:
    args = parse_args()
    review_dir = Path(args.review_dir)
    plan_path = review_dir / "lint_autofix_plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"lint_autofix_plan.json not found: {plan_path}")

    plan = read_json(plan_path)
    report = build_report(review_dir, plan)
    output_path = Path(args.output) if args.output else review_dir / "lint_autofix_apply_report.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"lint autofix apply report written: {output_path}")
    print(
        "applied={applied} already_applied={already} conflicts={conflicts}".format(
            applied=report["applied_count"],
            already=report["already_applied_count"],
            conflicts=report["conflict_count"],
        )
    )
    return 0 if report["conflict_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
