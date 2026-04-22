#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Build a structured diff between two review directories for targeted re-review.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path


COMPARE_FILES = (
    "coverage_matrix.md",
    "fact_check_list.md",
    "unresolved_items.md",
    "final_review_report.md",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build rereview diff between two review directories."
    )
    parser.add_argument("old_review_dir", help="Previous review directory")
    parser.add_argument("new_review_dir", help="Current review directory")
    parser.add_argument(
        "--output",
        "-o",
        help="Optional explicit JSON output path (default: <new_review_dir>/rereview_diff.json)",
    )
    return parser.parse_args()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_verdict(text: str) -> str:
    patterns = (
        r"审核结论\s*[:：]\s*(.+)",
        r"-\s*审核结论\s*[:：]\s*(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""


def extract_bullets(text: str) -> set[str]:
    bullets = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.add(stripped[2:].strip())
        elif re.match(r"^\d+\.\s+", stripped):
            bullets.add(re.sub(r"^\d+\.\s+", "", stripped))
    return bullets


def compare_text_files(old_path: Path, new_path: Path) -> dict:
    old_text = old_path.read_text(encoding="utf-8") if old_path.exists() else ""
    new_text = new_path.read_text(encoding="utf-8") if new_path.exists() else ""
    diff_lines = list(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=str(old_path.name),
            tofile=str(new_path.name),
            n=1,
        )
    )
    old_bullets = extract_bullets(old_text)
    new_bullets = extract_bullets(new_text)
    return {
        "changed": old_text != new_text,
        "added_bullets": sorted(new_bullets - old_bullets),
        "removed_bullets": sorted(old_bullets - new_bullets),
        "diff_excerpt": diff_lines[:80],
    }


def build_diff(old_review_dir: Path, new_review_dir: Path) -> dict:
    old_files = {path.name: path for path in old_review_dir.iterdir() if path.is_file()}
    new_files = {path.name: path for path in new_review_dir.iterdir() if path.is_file()}
    all_names = sorted(set(old_files) | set(new_files))

    added_files = [name for name in all_names if name not in old_files]
    removed_files = [name for name in all_names if name not in new_files]
    changed_files = []
    unchanged_files = []

    for name in all_names:
        if name in old_files and name in new_files:
            if file_hash(old_files[name]) != file_hash(new_files[name]):
                changed_files.append(name)
            else:
                unchanged_files.append(name)

    old_final = old_review_dir / "final_review_report.md"
    new_final = new_review_dir / "final_review_report.md"
    old_final_text = old_final.read_text(encoding="utf-8") if old_final.exists() else ""
    new_final_text = new_final.read_text(encoding="utf-8") if new_final.exists() else ""

    file_diffs = {}
    for filename in COMPARE_FILES:
        file_diffs[filename] = compare_text_files(old_review_dir / filename, new_review_dir / filename)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "old_review_dir": str(old_review_dir),
        "new_review_dir": str(new_review_dir),
        "old_verdict": extract_verdict(old_final_text),
        "new_verdict": extract_verdict(new_final_text),
        "added_files": added_files,
        "removed_files": removed_files,
        "changed_files": changed_files,
        "unchanged_files": unchanged_files,
        "file_diffs": file_diffs,
    }


def render_markdown(diff: dict) -> str:
    lines = [
        "# 定向复审差异报告",
        "",
        f"- 旧目录: `{diff['old_review_dir']}`",
        f"- 新目录: `{diff['new_review_dir']}`",
        f"- 旧结论: `{diff['old_verdict'] or '未提取到'}`",
        f"- 新结论: `{diff['new_verdict'] or '未提取到'}`",
        "",
        "## 文件层差异",
        f"- 新增文件: {len(diff['added_files'])}",
        f"- 删除文件: {len(diff['removed_files'])}",
        f"- 变更文件: {len(diff['changed_files'])}",
        "",
    ]

    if diff["changed_files"]:
        lines.append("## 重点变更文件")
        for name in diff["changed_files"]:
            lines.append(f"- {name}")
        lines.append("")

    for filename, details in diff["file_diffs"].items():
        if not details["changed"]:
            continue
        lines.append(f"## {filename}")
        if details["added_bullets"]:
            lines.append("- 新增条目:")
            lines.extend(f"  - {item}" for item in details["added_bullets"][:20])
        if details["removed_bullets"]:
            lines.append("- 移除条目:")
            lines.extend(f"  - {item}" for item in details["removed_bullets"][:20])
        if details["diff_excerpt"]:
            lines.append("- Diff 摘要:")
            lines.append("```diff")
            lines.extend(details["diff_excerpt"])
            lines.append("```")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    old_review_dir = Path(args.old_review_dir)
    new_review_dir = Path(args.new_review_dir)
    if not old_review_dir.exists():
        raise FileNotFoundError(f"Old review directory does not exist: {old_review_dir}")
    if not new_review_dir.exists():
        raise FileNotFoundError(f"New review directory does not exist: {new_review_dir}")

    diff = build_diff(old_review_dir, new_review_dir)
    json_path = Path(args.output) if args.output else new_review_dir / "rereview_diff.json"
    md_path = json_path.with_suffix(".md")

    json_path.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(diff), encoding="utf-8")

    print(f"rereview diff json: {json_path}")
    print(f"rereview diff markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
