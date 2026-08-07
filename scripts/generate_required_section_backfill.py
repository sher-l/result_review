#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generate backfill blocks for reader-facing final report sections that are still missing.

This script reads final_report_lint.json and existing audit deliverables, then
builds a machine-readable plan for sections that can be reconstructed from
reader-facing structured artifacts. Internal convergence, mechanical-check and
high-risk-module records remain in the audit dossier and are never backfilled
into the final report.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate final_report_backfill_plan.json for missing report sections."
    )
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    parser.add_argument(
        "--output",
        "-o",
        help="Optional explicit path for final_report_backfill_plan.json",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_missing_section_ids(lint_data: dict) -> list[str]:
    missing = []
    for check in lint_data.get("checks", []):
        if check["id"].startswith("section:") and not check.get("passed", False):
            missing.append(check["id"].split(":", 1)[1])
    return missing


def extract_markdown_section(text: str, required_terms: list[str]) -> str | None:
    lines = text.splitlines()
    start_index = None
    start_level = 0

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        if all(term in stripped for term in required_terms):
            start_index = index
            start_level = len(stripped) - len(stripped.lstrip("#"))
            break

    if start_index is None:
        return None

    end_index = len(lines)
    for index in range(start_index + 1, len(lines)):
        stripped = lines[index].strip()
        if not stripped.startswith("#"):
            continue
        level = len(stripped) - len(stripped.lstrip("#"))
        if level <= start_level:
            end_index = index
            break

    body = "\n".join(lines[start_index + 1 : end_index]).strip()
    return body or None


def build_three_agent_section(review_dir: Path) -> dict | None:
    convergence_md = review_dir / "convergence_report.md"
    convergence_json = review_dir / "convergence_report.json"
    if not convergence_md.exists() or not convergence_json.exists():
        return None

    convergence_data = read_json(convergence_json)
    blocking_items = convergence_data.get("summary", {}).get("blocking_items", [])
    routes = convergence_data.get("routes", [])

    lines = [
        "## 六、三路收敛",
        "",
        "### 三路视角",
        "| 视角 | 关注点 | 初步结论 |",
        "|---|---|---|",
    ]
    for route in routes:
        lines.append(
            f"| {route.get('route', '-')} 线 | {route.get('focus', '-')} | {route.get('conclusion', '-')} |"
        )

    lines.extend(
        [
            "",
            "### 收敛结论",
        ]
    )
    if blocking_items:
        for item in blocking_items:
            lines.append(f"- {item}")
    else:
        lines.append("- 详见 convergence_report.md 的收敛记录。")

    return {
        "section_id": "three_agent_convergence",
        "target_file": str(review_dir / "final_review_report.md"),
        "insert_before_heading": "## 八、建议动作",
        "content": "\n".join(lines) + "\n",
        "reason": "Required section markers for three-agent convergence are missing, but convergence artifacts already exist.",
    }


def build_mechanical_disposition_section(review_dir: Path) -> dict | None:
    coverage_matrix = review_dir / "coverage_matrix.md"
    mechanical_json = review_dir / "mechanical_check_result.json"

    body = None
    if coverage_matrix.exists():
        body = extract_markdown_section(read_text(coverage_matrix), ["机械", "处置"])

    if not body and mechanical_json.exists():
        data = read_json(mechanical_json)
        rows = [
            "## 五、机械检查处置",
            "",
            "| 自动问题 | 严重级别 | 当前候选结论 |",
            "|---|---|---|",
        ]
        for issue in data.get("issues", [])[:8]:
            code = issue.get("code", "-")
            severity = issue.get("severity", "-")
            message = issue.get("message", "-").replace("\n", " ")
            rows.append(f"| `{code}` | {severity} | {message} |")
        body = "\n".join(rows[1:]).strip()

    if not body:
        return None

    content = "## 五、机械检查处置\n\n" + body + "\n"
    return {
        "section_id": "mechanical_disposition",
        "target_file": str(review_dir / "final_review_report.md"),
        "insert_before_heading": "## 八、建议动作",
        "content": content,
        "reason": "Required mechanical disposition section is missing, but structured mechanical artifacts already exist.",
    }


def build_high_risk_modules_section(review_dir: Path) -> dict | None:
    mechanical_json = review_dir / "mechanical_check_result.json"
    if not mechanical_json.exists():
        return None

    issues = read_json(mechanical_json).get("issues", [])

    def collect(module_terms: list[str]) -> list[dict]:
        return [
            issue
            for issue in issues
            if any(term in issue.get("message", "") or term in issue.get("detail", "") for term in module_terms)
        ]

    module_specs = [
        ("分子对接", ["分子对接", "对接", "docking"]),
        ("分子动力学", ["分子动力学", "动力学", "MD"]),
        ("虚拟敲除", ["虚拟敲除", "敲除", "knockout"]),
    ]

    lines = [
        "## 五、高风险模块复核",
        "",
        "| 模块 | 模块存在 | 证据充分 | 可复现 | 结论不过度外推 | 备注 |",
        "|---|---|---|---|---|---|",
    ]
    row_count = 0

    for display_name, terms in module_specs:
        matched = collect(terms)
        if not matched:
            continue

        evidence_sufficient = "否" if any("目录为空" in issue.get("message", "") or "无文件" in issue.get("detail", "") for issue in matched) else "部分"
        reproducible = "否" if any("未识别到" in issue.get("message", "") or "无代码" in issue.get("detail", "") for issue in matched) else "部分"
        not_overstated = "否" if any(issue.get("code") in {"MC-017", "MC-018"} for issue in matched) else "部分"
        remark = "；".join(issue.get("message", "-") for issue in matched[:2])
        lines.append(f"| {display_name} | 是 | {evidence_sufficient} | {reproducible} | {not_overstated} | {remark} |")
        row_count += 1

    if row_count == 0:
        return None

    return {
        "section_id": "high_risk_modules",
        "target_file": str(review_dir / "final_review_report.md"),
        "insert_before_heading": "## 八、建议动作",
        "content": "\n".join(lines) + "\n",
        "reason": "Required high-risk module section is missing, but mechanical checks already summarize module-level risk.",
    }


def build_plan(review_dir: Path, lint_data: dict) -> dict:
    missing_sections = extract_missing_section_ids(lint_data)
    items = []

    builders = {}

    for section_id in missing_sections:
        builder = builders.get(section_id)
        if not builder:
            continue
        item = builder(review_dir)
        if item:
            items.append(item)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "review_dir": str(review_dir),
        "source_lint_file": str(review_dir / "final_report_lint.json"),
        "backfill_item_count": len(items),
        "items": items,
    }


def main() -> int:
    args = parse_args()
    review_dir = Path(args.review_dir)
    lint_path = review_dir / "final_report_lint.json"
    if not lint_path.exists():
        raise FileNotFoundError(f"final_report_lint.json not found: {lint_path}")

    lint_data = read_json(lint_path)
    plan = build_plan(review_dir, lint_data)
    output_path = Path(args.output) if args.output else review_dir / "final_report_backfill_plan.json"
    output_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"final report backfill plan written: {output_path}")
    print(f"backfill_item_count={plan['backfill_item_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
