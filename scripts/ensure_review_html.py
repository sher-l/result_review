#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查并自动补齐审核 HTML 报告。"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple

from audit_runtime import append_event, detect_html_path, load_case_manifest, update_case_manifest
from render_final_review_html import build_html, resolve_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="检查 final_review_report.md 是否存在，并自动补齐 <项目编号>_audit_report.html"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="result_review_report",
        help="单个项目审核目录、final_review_report.md 文件，或 result_review_report 根目录"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="即使 HTML 已存在且较新，也强制重新生成"
    )
    return parser.parse_args()


# 支持的审核报告文件名
_REPORT_NAMES = ('final_review_report.md', 'REVIEW_REPORT.md')


def _has_report(directory: Path) -> bool:
    return any((directory / name).exists() for name in _REPORT_NAMES)


def iter_targets(path: Path) -> Iterable[Path]:
    if path.is_file() or _has_report(path):
        yield path
        return

    if not path.exists():
        raise FileNotFoundError(f"路径不存在: {path}")

    for child in sorted(path.iterdir()):
        if child.is_dir() and _has_report(child):
            yield child


def ensure_one(target: Path, force: bool) -> Tuple[str, str]:
    markdown_path, html_path = resolve_paths(str(target), None)
    review_dir = target if target.is_dir() else target.parent
    if not markdown_path.exists():
        update_case_manifest(review_dir, {"publish_status": "failed", "updated_at": datetime.now().isoformat(timespec="seconds")})
        append_event(review_dir, "html_publish_failed", actor="ensure_review_html", status="error", details={"reason": "missing_markdown"})
        return "missing", f"缺少 final_review_report.md: {markdown_path.parent}"

    if html_path.exists() and not force and html_path.stat().st_mtime >= markdown_path.stat().st_mtime:
        update_case_manifest(review_dir, {"publish_status": "success", "updated_at": datetime.now().isoformat(timespec="seconds")})
        append_event(review_dir, "html_publish_skipped", actor="ensure_review_html", outputs=[str(html_path)])
        return "skipped", f"HTML 已存在且为最新: {html_path}"

    markdown_text = markdown_path.read_text(encoding="utf-8")
    rendered = build_html(markdown_text, markdown_path)
    html_path.write_text(rendered, encoding="utf-8")
    update_case_manifest(review_dir, {"publish_status": "success", "updated_at": datetime.now().isoformat(timespec="seconds")})
    append_event(review_dir, "html_published", actor="ensure_review_html", outputs=[str(html_path)])
    return "generated", f"HTML 已生成: {html_path}"


def resolve_pending_project_root(project_path: Path) -> Path | None:
    """定位 raw/待审核 下应整体移动的项目根目录。"""
    current = project_path
    while True:
        parent = current.parent
        if parent == current:
            return None
        if parent.name == "待审核":
            return current
        current = parent


def load_project_dir(review_dir: Path) -> Path | None:
    """从审核目录元数据中恢复原始项目目录。"""
    manifest_path = review_dir / "ai_execution_manifest.json"
    if not manifest_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    project_dir = manifest.get("paths", {}).get("project_dir", "")
    return Path(project_dir) if project_dir else None


def load_source_archive(review_dir: Path) -> Path | None:
    """从审核目录元数据中恢复原始 ZIP 路径。"""
    manifest_path = review_dir / "ai_execution_manifest.json"
    if not manifest_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    source_archive = manifest.get("paths", {}).get("source_archive_path", "")
    return Path(source_archive) if source_archive else None


def move_reviewed_project(review_dir: Path) -> Path | None:
    """HTML 交付完成后，将 raw/待审核 下的项目目录及原始 ZIP 移动到 raw/已AI审核一次。"""
    project_dir = load_project_dir(review_dir)
    if project_dir is None:
        return None

    pending_root = resolve_pending_project_root(project_dir)
    if pending_root is None or not pending_root.exists():
        return None

    raw_root = pending_root.parent.parent
    target_root = raw_root / "已AI审核一次"
    target_root.mkdir(parents=True, exist_ok=True)

    destination = target_root / pending_root.name
    if destination.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = target_root / f"{pending_root.name}_{stamp}"

    shutil.move(str(pending_root), str(destination))
    move_source_archive(review_dir, target_root)
    return destination


def move_source_archive(review_dir: Path, target_root: Path) -> Path | None:
    """如 manifest 记录了 raw/待审核 下的原始 ZIP，则一并移动。"""
    archive = load_source_archive(review_dir)
    if archive is None or not archive.exists():
        return None
    if archive.suffix.lower() != ".zip":
        return None
    if archive.parent.name != "待审核":
        return None

    destination = target_root / archive.name
    if destination.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = target_root / f"{archive.stem}_{stamp}{archive.suffix}"

    shutil.move(str(archive), str(destination))
    return destination


def main() -> int:
    args = parse_args()
    path = Path(args.path)

    generated = 0
    skipped = 0
    missing = 0

    for target in iter_targets(path):
        status, message = ensure_one(target, args.force)
        print(message)
        if status == "generated":
            generated += 1
        elif status == "skipped":
            skipped += 1
        else:
            missing += 1

    print("\n汇总:")
    print(f"  新生成: {generated}")
    print(f"  已最新跳过: {skipped}")
    print(f"  缺少最终报告: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
