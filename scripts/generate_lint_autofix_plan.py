#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generate a machine-readable autofix plan from final_report_lint.json.

The plan does not edit files automatically. It converts safe lint findings into
explicit line-level actions so the next AI step can patch the markdown files
deterministically.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from policy_loader import load_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate lint_autofix_plan.json from final_report_lint.json"
    )
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    parser.add_argument(
        "--output",
        "-o",
        help="Optional explicit path for lint_autofix_plan.json",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_forbidden_term_map(policy: dict) -> dict[str, str]:
    mapping = {}
    for rule in policy.get("terminology_policy", {}).get("forbidden_terms", []):
        term = rule.get("term")
        replacement = rule.get("replacement", "")
        if term and replacement:
            mapping[term] = replacement
    return mapping


def parse_fix_instruction(review_dir: Path, fix: dict, forbidden_term_map: dict[str, str]) -> dict | None:
    check_id = fix.get("check_id", "")

    placeholder_match = re.match(r"^markdown:placeholder:([^:]+):(\d+):(.+)$", check_id)
    if placeholder_match:
        file_name, line_no, term = placeholder_match.groups()
        file_path = review_dir / file_name
        if file_path.exists():
            lines = file_path.read_text(encoding="utf-8").splitlines()
            idx = int(line_no) - 1
            if 0 <= idx < len(lines):
                original = lines[idx]
                updated = original.replace(term, "").strip()
                return {
                    "file": str(file_path),
                    "operation": "replace_line",
                    "line": int(line_no),
                    "original": original,
                    "replacement": updated,
                    "autofix_safe": True,
                    "reason": fix.get("message", ""),
                    "patch_hint": fix.get("patch_hint", ""),
                }

    empty_section_match = re.match(r"^markdown:empty_section:([^:]+):(\d+)$", check_id)
    if empty_section_match:
        file_name, line_no = empty_section_match.groups()
        file_path = review_dir / file_name
        if file_path.exists():
            lines = file_path.read_text(encoding="utf-8").splitlines()
            idx = int(line_no) - 1
            if 0 <= idx < len(lines):
                original = lines[idx]
                return {
                    "file": str(file_path),
                    "operation": "delete_line",
                    "line": int(line_no),
                    "original": original,
                    "replacement": "",
                    "autofix_safe": True,
                    "reason": fix.get("message", ""),
                    "patch_hint": fix.get("patch_hint", ""),
                }

    heading_jump_match = re.match(r"^markdown:heading_jump:([^:]+):(\d+)$", check_id)
    if heading_jump_match:
        file_name, line_no = heading_jump_match.groups()
        file_path = review_dir / file_name
        if file_path.exists():
            lines = file_path.read_text(encoding="utf-8").splitlines()
            idx = int(line_no) - 1
            if 0 <= idx < len(lines):
                original = lines[idx]
                heading_match = re.match(r"^(#{2,6})(\s+.+)$", original)
                if heading_match:
                    hashes, tail = heading_match.groups()
                    replacement = hashes[:-1] + tail
                    return {
                        "file": str(file_path),
                        "operation": "replace_line",
                        "line": int(line_no),
                        "original": original,
                        "replacement": replacement,
                        "autofix_safe": True,
                        "reason": fix.get("message", ""),
                        "patch_hint": fix.get("patch_hint", ""),
                    }

    terminology_match = re.match(r"^terminology:forbidden:([^:]+):(\d+):(.+)$", check_id)
    if terminology_match:
        file_name, line_no, term = terminology_match.groups()
        replacement = forbidden_term_map.get(term, "")
        file_path = review_dir / file_name
        if replacement and file_path.exists():
            lines = file_path.read_text(encoding="utf-8").splitlines()
            idx = int(line_no) - 1
            if 0 <= idx < len(lines):
                original = lines[idx]
                updated = original.replace(term, replacement)
                return {
                    "file": str(file_path),
                    "operation": "replace_line",
                    "line": int(line_no),
                    "original": original,
                    "replacement": updated,
                    "autofix_safe": True,
                    "reason": fix.get("message", ""),
                    "patch_hint": fix.get("patch_hint", ""),
                }

    return None


def build_plan(review_dir: Path, lint_data: dict, policy: dict) -> dict:
    forbidden_term_map = build_forbidden_term_map(policy)
    plan_items = []

    for fix in lint_data.get("suggested_fixes", []):
        if not fix.get("autofix_safe"):
            continue
        item = parse_fix_instruction(review_dir, fix, forbidden_term_map)
        if item:
            plan_items.append(item)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "review_dir": str(review_dir),
        "source_lint_file": str(review_dir / "final_report_lint.json"),
        "autofix_item_count": len(plan_items),
        "items": plan_items,
    }


def main() -> int:
    args = parse_args()
    review_dir = Path(args.review_dir)
    lint_path = review_dir / "final_report_lint.json"
    if not lint_path.exists():
        raise FileNotFoundError(f"final_report_lint.json not found: {lint_path}")

    lint_data = read_json(lint_path)
    policy = load_policy()
    plan = build_plan(review_dir, lint_data, policy)
    output_path = Path(args.output) if args.output else review_dir / "lint_autofix_plan.json"
    output_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"lint autofix plan written: {output_path}")
    print(f"autofix_item_count={plan['autofix_item_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
