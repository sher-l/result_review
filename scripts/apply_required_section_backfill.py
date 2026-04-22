#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Apply final_report_backfill_plan.json to final_review_report.md.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply final_report_backfill_plan.json to final_review_report.md"
    )
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    parser.add_argument(
        "--output",
        "-o",
        help="Optional explicit path for final_report_backfill_apply_report.json",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_item(item: dict) -> dict:
    target = Path(item["target_file"])
    result = dict(item)

    if not target.exists():
        result["status"] = "conflict"
        result["detail"] = "target file missing"
        return result

    original_text = target.read_text(encoding="utf-8")
    content = item["content"].rstrip() + "\n\n"
    if content.strip() in original_text:
        result["status"] = "already_applied"
        result["detail"] = "content already present"
        return result

    marker = item.get("insert_before_heading", "")
    if marker and marker in original_text:
        updated_text = original_text.replace(marker, content + marker, 1)
        detail = f"inserted before heading: {marker}"
    else:
        updated_text = original_text.rstrip() + "\n\n" + content
        detail = "appended to file end"

    target.write_text(updated_text, encoding="utf-8")
    result["status"] = "applied"
    result["detail"] = detail
    return result


def build_report(review_dir: Path, plan: dict) -> dict:
    results = [apply_item(item) for item in plan.get("items", [])]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "review_dir": str(review_dir),
        "source_plan_file": str(review_dir / "final_report_backfill_plan.json"),
        "applied_count": sum(1 for item in results if item["status"] == "applied"),
        "already_applied_count": sum(1 for item in results if item["status"] == "already_applied"),
        "conflict_count": sum(1 for item in results if item["status"] == "conflict"),
        "items": results,
    }


def main() -> int:
    args = parse_args()
    review_dir = Path(args.review_dir)
    plan_path = review_dir / "final_report_backfill_plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"final_report_backfill_plan.json not found: {plan_path}")

    plan = read_json(plan_path)
    report = build_report(review_dir, plan)
    output_path = Path(args.output) if args.output else review_dir / "final_report_backfill_apply_report.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"final report backfill apply report written: {output_path}")
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
