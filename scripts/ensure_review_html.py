#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查并自动补齐审核 HTML 报告。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable, Tuple

from audit_runtime import append_event, detect_html_path, load_case_manifest, update_case_manifest
from formal_delivery import (
    validate_html_canonical_equivalence,
    validate_html_decision_consistency,
)
from html_presentation_contract import (
    validate_html_presentation_file,
    validate_html_presentation_text,
)
from render_final_review_html import (
    build_html,
    load_final_decision,
    resolve_final_decision_path,
    resolve_paths,
)


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
_ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z"}
_PROJECT_ID_PATTERN = re.compile(r"\d+[A-Z]+\d+[A-Z]+", re.IGNORECASE)
_SOURCE_MARKDOWN_SHA256_COMMENT = "audit-source-markdown-sha256"
_SOURCE_MARKDOWN_SHA256_RE = re.compile(
    rf"<!--\s*{_SOURCE_MARKDOWN_SHA256_COMMENT}:\s*([0-9a-f]{{64}})\s*-->",
    re.IGNORECASE,
)


def _has_report(directory: Path) -> bool:
    return any((directory / name).exists() for name in _REPORT_NAMES)


def source_markdown_sha256(markdown_path: Path) -> str:
    """Return the exact source Markdown digest bound into a rendered HTML file."""
    return hashlib.sha256(markdown_path.read_bytes()).hexdigest()


def html_source_markdown_sha256(html_path: Path) -> str:
    """Read the renderer-owned source digest marker, or return an empty value."""
    match = _SOURCE_MARKDOWN_SHA256_RE.search(html_path.read_text(encoding="utf-8"))
    return match.group(1).lower() if match else ""


def html_binds_current_markdown(markdown_path: Path, html_path: Path) -> bool:
    """Only accept HTML that explicitly records the current Markdown SHA256."""
    return html_path.is_file() and html_source_markdown_sha256(html_path) == source_markdown_sha256(markdown_path)


def _with_source_markdown_sha256(rendered: str, markdown_sha256: str) -> str:
    return f"<!-- {_SOURCE_MARKDOWN_SHA256_COMMENT}: {markdown_sha256} -->\n{rendered}"


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
    review_dir = target if target.is_dir() else target.parent

    try:
        markdown_path, html_path = resolve_paths(str(target), None)
    except FileNotFoundError:
        update_case_manifest(review_dir, {"publish_status": "failed", "updated_at": datetime.now().isoformat(timespec="seconds")})
        append_event(review_dir, "html_publish_failed", actor="ensure_review_html", status="error", details={"reason": "missing_markdown"})
        return "missing", f"缺少最终审核报告: {review_dir}"

    markdown_sha256 = source_markdown_sha256(markdown_path)
    final_decision = load_final_decision(markdown_path)
    html_matches_source = html_binds_current_markdown(markdown_path, html_path)
    html_matches_decision = True
    html_matches_presentation = False
    html_matches_canonical = False
    if html_path.is_file():
        html_matches_presentation, _ = validate_html_presentation_file(html_path)
    if html_path.is_file() and final_decision is not None:
        html_matches_decision, _ = validate_html_decision_consistency(
            html_path,
            resolve_final_decision_path(markdown_path),
        )
    if (
        html_path.is_file()
        and not force
        and html_matches_source
        and html_matches_decision
        and html_matches_presentation
    ):
        html_matches_canonical, _ = validate_html_canonical_equivalence(
            markdown_path,
            html_path,
            resolve_final_decision_path(markdown_path)
            if final_decision is not None
            else None,
        )
    if (
        html_path.exists()
        and not force
        and html_matches_source
        and html_matches_decision
        and html_matches_presentation
        and html_matches_canonical
    ):
        update_case_manifest(review_dir, {"publish_status": "success", "updated_at": datetime.now().isoformat(timespec="seconds")})
        append_event(
            review_dir,
            "html_publish_skipped",
            actor="ensure_review_html",
            outputs=[str(html_path)],
            details={"markdown_sha256": markdown_sha256},
        )
        return "skipped", f"HTML 已绑定当前 Markdown: {html_path}"

    markdown_text = markdown_path.read_text(encoding="utf-8")
    rendered = (
        build_html(markdown_text, markdown_path, final_decision=final_decision)
        if final_decision is not None
        else build_html(markdown_text, markdown_path)
    )
    presentation_ok, presentation_reason = validate_html_presentation_text(rendered)
    if not presentation_ok:
        update_case_manifest(
            review_dir,
            {
                "publish_status": "failed",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        append_event(
            review_dir,
            "html_publish_failed",
            actor="ensure_review_html",
            status="error",
            details={
                "reason": "presentation_contract",
                "message": presentation_reason,
            },
        )
        return "failed", f"HTML 展示契约未通过: {presentation_reason}"
    html_path.write_text(_with_source_markdown_sha256(rendered, markdown_sha256), encoding="utf-8")
    update_case_manifest(review_dir, {"publish_status": "success", "updated_at": datetime.now().isoformat(timespec="seconds")})
    append_event(
        review_dir,
        "html_published",
        actor="ensure_review_html",
        outputs=[str(html_path)],
        details={"markdown_sha256": markdown_sha256},
    )
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
    manifests: list[dict] = []
    if manifest_path.exists():
        try:
            manifests.append(json.loads(manifest_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    case_manifest = load_case_manifest(review_dir)
    if case_manifest:
        manifests.append(case_manifest)

    for manifest in manifests:
        project_dir = manifest.get("paths", {}).get("project_dir", "") or manifest.get("project_dir", "")
        if project_dir:
            return Path(project_dir)
    return None


def load_source_archive(review_dir: Path) -> Path | None:
    """从审核目录元数据中恢复原始 ZIP 路径。"""
    manifest_path = review_dir / "ai_execution_manifest.json"
    manifests: list[dict] = []
    if manifest_path.exists():
        try:
            manifests.append(json.loads(manifest_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    case_manifest = load_case_manifest(review_dir)
    if case_manifest:
        manifests.append(case_manifest)

    for manifest in manifests:
        source_archive = manifest.get("paths", {}).get("source_archive_path", "") or manifest.get("source_archive_path", "")
        if source_archive:
            return Path(source_archive)
    return None


def move_reviewed_project(review_dir: Path) -> Path | None:
    """HTML 交付完成后，将 raw/待审核 下的项目目录及原始 ZIP 移动到 raw/已AI审核一次。"""
    project_dir = load_project_dir(review_dir)
    if project_dir is None:
        moved_entries = move_pending_entries_for_review(review_dir, None)
        return moved_entries[0] if moved_entries else None

    pending_root = resolve_pending_project_root(project_dir)
    if pending_root is None or not pending_root.exists():
        moved_archives = move_pending_entries_for_review(review_dir, project_dir)
        cleanup_extracted_project_cache(project_dir)
        return moved_archives[0] if moved_archives else None

    raw_root = pending_root.parent.parent
    target_root = raw_root / "已AI审核一次"
    target_root.mkdir(parents=True, exist_ok=True)

    destination = target_root / pending_root.name
    if destination.exists():
        if pending_root.is_dir() and destination.is_dir() and directory_tree_covered(pending_root, destination):
            move_source_archive(review_dir, target_root, pending_root)
            shutil.rmtree(pending_root)
            return destination
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            destination = target_root / f"{pending_root.name}_{stamp}"

    pending_root.rename(destination)
    move_source_archive(review_dir, target_root, pending_root)
    return destination


def resolve_workspace_raw_root(review_dir: Path) -> Path | None:
    """Find the workspace raw directory from a result_review_report child."""
    current = review_dir.resolve()
    for parent in [current, *current.parents]:
        raw_root = parent / "raw"
        if raw_root.is_dir():
            return raw_root
        if parent.name == "result_review_report":
            sibling_raw = parent.parent / "raw"
            if sibling_raw.is_dir():
                return sibling_raw
    return None


def move_path_to_target(path: Path, target_root: Path) -> Path:
    """Move a pending file or directory into the reviewed-project archive root."""
    destination = target_root / path.name
    if destination.exists():
        if path.is_dir() and destination.is_dir() and directory_tree_covered(path, destination):
            shutil.rmtree(path)
            return destination
        if path.is_file() and destination.is_file() and destination.stat().st_size == path.stat().st_size:
            path.unlink()
            return destination
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if path.is_file():
            destination = target_root / f"{path.stem}_{stamp}{path.suffix}"
        else:
            destination = target_root / f"{path.name}_{stamp}"

    path.rename(destination)
    return destination


def candidate_stems_for_review(review_dir: Path, project_dir: Path | None) -> set[str]:
    """Build safe lookup stems for pending raw entries."""
    manifest = load_case_manifest(review_dir)
    stems = {review_dir.name}
    if manifest.get("project_id"):
        stems.add(str(manifest["project_id"]))
    if project_dir is not None:
        stems.add(project_dir.name)
        stems.add(project_dir.parent.name)
    return {stem for stem in stems if stem and len(stem) >= 6}


def review_project_ids(review_dir: Path, project_dir: Path | None) -> set[str]:
    """Return project-id tokens used to identify only this review's pending entries."""
    values = set(candidate_stems_for_review(review_dir, project_dir))
    source_archive = load_source_archive(review_dir)
    if source_archive is not None:
        values.add(source_archive.stem)

    project_ids: set[str] = set()
    for value in values:
        project_ids.update(match.group().upper() for match in _PROJECT_ID_PATTERN.finditer(value))
    return project_ids


def _entry_matches_project_id(entry: Path, project_ids: set[str]) -> bool:
    name = entry.name.upper()
    return any(
        re.search(rf"(?<![A-Z0-9]){re.escape(project_id)}(?![A-Z0-9])", name)
        for project_id in project_ids
    )


def pending_entries_for_review(review_dir: Path, project_dir: Path | None, pending_dir: Path) -> list[Path]:
    """Return direct pending entries belonging to this review, without moving them."""
    if not pending_dir.is_dir():
        return []
    project_ids = review_project_ids(review_dir, project_dir)
    if not project_ids:
        return []
    return sorted(
        (
            entry for entry in pending_dir.iterdir()
            if (entry.is_dir() or entry.suffix.lower() in _ARCHIVE_SUFFIXES)
            and _entry_matches_project_id(entry, project_ids)
        ),
        key=lambda entry: entry.name,
    )


def assert_no_untracked_pending_entries(
    review_dir: Path,
    project_dir: Path | None,
    *,
    allowed_entries: Iterable[Path] = (),
) -> list[Path]:
    """Block finalization if a project has untracked sibling entries in raw/待审核."""
    raw_root = find_raw_root(project_dir) if project_dir is not None else None
    source_archive = load_source_archive(review_dir)
    if raw_root is None and source_archive is not None and source_archive.parent.name == "待审核":
        raw_root = source_archive.parent.parent
    if raw_root is None:
        raw_root = resolve_workspace_raw_root(review_dir)
    if raw_root is None:
        return []

    pending_dir = raw_root / "待审核"
    allowed = {entry.resolve() for entry in allowed_entries if entry.exists()}
    entries = pending_entries_for_review(review_dir, project_dir, pending_dir)
    unexpected = [entry for entry in entries if entry.resolve() not in allowed]
    if unexpected:
        rendered = ", ".join(str(entry) for entry in unexpected)
        raise RuntimeError(
            "Archive gate blocked: untracked pending entries for this project remain in raw/待审核: "
            f"{rendered}"
        )
    return entries


def iter_pending_entries_for_review(review_dir: Path, project_dir: Path | None, pending_dir: Path) -> list[Path]:
    """Find raw/待审核 files or directories that belong to the current review."""
    candidates: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path | None) -> None:
        if path is None or not path.exists() or path.parent != pending_dir:
            return
        if path.is_file() and path.suffix.lower() not in _ARCHIVE_SUFFIXES:
            return
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        candidates.append(path)

    add(load_source_archive(review_dir))
    for stem in candidate_stems_for_review(review_dir, project_dir):
        add(pending_dir / stem)
        for suffix in _ARCHIVE_SUFFIXES:
            add(pending_dir / f"{stem}{suffix}")
        for match in pending_dir.glob(f"*{stem}*"):
            add(match)

    candidates.sort(key=lambda path: (0 if path.is_dir() else 1, path.name))
    return candidates


def move_pending_entries_for_review(review_dir: Path, project_dir: Path | None) -> list[Path]:
    """Fallback archive path: move matching raw/待审核 entries by review/project id."""
    raw_root = find_raw_root(project_dir) if project_dir is not None else None
    if raw_root is None:
        raw_root = resolve_workspace_raw_root(review_dir)
    if raw_root is None:
        return []

    pending_dir = raw_root / "待审核"
    if not pending_dir.exists():
        return []

    target_root = raw_root / "已AI审核一次"
    target_root.mkdir(parents=True, exist_ok=True)

    moved: list[Path] = []
    for entry in iter_pending_entries_for_review(review_dir, project_dir, pending_dir):
        moved.append(move_path_to_target(entry, target_root))
    return moved


def resolve_extracted_cache_root(project_dir: Path) -> Path | None:
    """Return the top-level raw/zip_extracted cache directory for an audited project."""
    current = project_dir
    while True:
        parent = current.parent
        if parent == current:
            return None
        if parent.name == "zip_extracted" and parent.parent.name == "raw":
            return current
        current = parent


def cleanup_extracted_project_cache(project_dir: Path) -> Path | None:
    """Remove the raw/zip_extracted cache after the original archive has been moved."""
    cache_root = resolve_extracted_cache_root(project_dir)
    if cache_root is None or not cache_root.exists():
        return None
    raw_root = cache_root.parent.parent
    if cache_root.parent != raw_root / "zip_extracted":
        return None
    shutil.rmtree(cache_root)
    return cache_root


def find_raw_root(path: Path) -> Path | None:
    """Find the nearest ancestor named raw."""
    current = path if path.is_dir() else path.parent
    while True:
        if current.name == "raw":
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def move_pending_archives_for_extracted_project(review_dir: Path, project_dir: Path) -> list[Path]:
    """Move raw/待审核 archives when the audited project lives under raw/zip_extracted."""
    raw_root = find_raw_root(project_dir)
    if raw_root is None:
        return []
    pending_dir = raw_root / "待审核"
    if not pending_dir.exists():
        return []

    target_root = raw_root / "已AI审核一次"
    target_root.mkdir(parents=True, exist_ok=True)

    candidates: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path | None) -> None:
        if path is None:
            return
        if not path.exists() or path.parent != pending_dir or path.suffix.lower() not in _ARCHIVE_SUFFIXES:
            return
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        candidates.append(path)

    add(load_source_archive(review_dir))
    stems = {review_dir.name, project_dir.name, project_dir.parent.name}
    for stem in stems:
        for suffix in _ARCHIVE_SUFFIXES:
            add(pending_dir / f"{stem}{suffix}")
            for match in pending_dir.glob(f"*{stem}*{suffix}"):
                add(match)

    moved: list[Path] = []
    for archive in candidates:
        destination = target_root / archive.name
        if destination.exists():
            if destination.is_file() and destination.stat().st_size == archive.stat().st_size:
                archive.unlink()
                moved.append(destination)
                continue
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            destination = target_root / f"{archive.stem}_{stamp}{archive.suffix}"
        archive.rename(destination)
        moved.append(destination)
    return moved


def directory_tree_covered(source: Path, destination: Path) -> bool:
    """Return true when every remaining source file already exists at destination."""
    for source_file in source.rglob("*"):
        if not source_file.is_file():
            continue
        relative = source_file.relative_to(source)
        destination_file = destination / relative
        if not destination_file.exists() or not destination_file.is_file():
            return False
        if destination_file.stat().st_size != source_file.stat().st_size:
            return False
    return True


def iter_source_archive_candidates(review_dir: Path, pending_root: Path) -> list[Path]:
    """Find original archive siblings even when the manifest points at an extracted folder."""
    pending_dir = pending_root.parent
    candidates: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path | None) -> None:
        if path is None:
            return
        resolved = path.resolve()
        if resolved in seen:
            return
        if path.exists() and path.parent == pending_dir and path.suffix.lower() in _ARCHIVE_SUFFIXES:
            seen.add(resolved)
            candidates.append(path)

    add(load_source_archive(review_dir))

    stems = {pending_root.name, review_dir.name}
    for stem in stems:
        for suffix in _ARCHIVE_SUFFIXES:
            add(pending_dir / f"{stem}{suffix}")
            for match in pending_dir.glob(f"*{stem}*{suffix}"):
                add(match)

    return candidates


def move_source_archive(review_dir: Path, target_root: Path, pending_root: Path) -> list[Path]:
    """Move raw/待审核 sibling archives recorded by manifest or inferred by project id."""
    moved: list[Path] = []
    for archive in iter_source_archive_candidates(review_dir, pending_root):
        destination = target_root / archive.name
        if destination.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            destination = target_root / f"{archive.stem}_{stamp}{archive.suffix}"

        archive.rename(destination)
        moved.append(destination)
    return moved


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
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
