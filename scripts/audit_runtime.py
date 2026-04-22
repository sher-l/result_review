#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Shared runtime helpers for the audit workflow."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable


PROJECT_ID_PATTERN = re.compile(r"\b\d{2}[A-Z]{3}\d{3}[A-Z]?\b")
EVENT_LOG_NAME = "review_event_log.jsonl"
CASE_MANIFEST_NAME = "case_manifest.json"


def infer_project_id(path: Path | str) -> str:
    path_obj = Path(path)
    for candidate in [path_obj, *list(path_obj.parents)[:4]]:
        match = PROJECT_ID_PATTERN.search(candidate.name)
        if match:
            return match.group(0)
    return path_obj.name


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def detect_html_path(review_dir: Path) -> Path:
    project_id = infer_project_id(review_dir)
    candidate = review_dir / f"{project_id}_audit_report.html"
    if candidate.exists():
        return candidate
    html_files = sorted(review_dir.glob("*_audit_report.html"))
    if html_files:
        return html_files[0]
    return candidate


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_pathish(value: object) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    return text.replace("\\", "/").lower()


def stable_hash(parts: Iterable[object], length: int = 12) -> str:
    joined = "||".join(normalize_text(part) for part in parts)
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()
    return digest[:length]


def build_finding_key(finding: dict) -> str:
    dimension = normalize_text(finding.get("dimension"))
    rule = normalize_text(finding.get("rule"))
    source_path = normalize_pathish(finding.get("source_path"))
    locator = normalize_text(finding.get("locator"))
    quote_or_value = normalize_text(finding.get("quote_or_value"))
    source_type = normalize_text(finding.get("source_type"))
    if not any([dimension, rule, source_path, locator, quote_or_value, source_type]):
        # fall back to the most human-visible fields if agent output is weak
        fallback = stable_hash(
            [
                finding.get("severity", ""),
                finding.get("location", ""),
                finding.get("description", ""),
                finding.get("evidence", ""),
            ],
            length=16,
        )
        return f"fk:{fallback}"
    base = stable_hash(
        [dimension, rule, source_type, source_path, locator, quote_or_value],
        length=16,
    )
    return f"fk:{base}"


def ensure_finding_key(finding: dict) -> str:
    key = normalize_text(finding.get("finding_key"))
    if key:
        finding["finding_key"] = key
        return key
    key = build_finding_key(finding)
    finding["finding_key"] = key
    return key


def append_event(
    review_dir: Path,
    event_type: str,
    *,
    status: str = "success",
    actor: str = "system",
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    details: dict | None = None,
) -> Path:
    event = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "event_type": event_type,
        "status": status,
        "actor": actor,
        "inputs": inputs or [],
        "outputs": outputs or [],
        "details": details or {},
    }
    path = review_dir / EVENT_LOG_NAME
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False))
        fh.write("\n")
    return path


def load_case_manifest(review_dir: Path) -> dict:
    return read_json(review_dir / CASE_MANIFEST_NAME)


def update_case_manifest(review_dir: Path, updates: dict) -> dict:
    path = review_dir / CASE_MANIFEST_NAME
    data = read_json(path)
    data.update(updates)
    data.setdefault("updated_at", datetime.now().isoformat(timespec="seconds"))
    write_json(path, data)
    return data


def build_case_manifest(
    *,
    review_dir: Path,
    project_dir: Path,
    report_structure: dict,
    project_structure: dict,
    source_archive_path: Path | None = None,
    review_lane: str = "standard",
    docx_only: bool = False,
) -> dict:
    metadata = project_structure.get("metadata", {})
    project_id = metadata.get("project_id") or infer_project_id(project_dir)
    datasets = [item.get("id", "") for item in project_structure.get("geo_references", []) if item.get("id")]
    foreign_ids = [
        item.get("id", "")
        for item in project_structure.get("project_id_references", [])
        if item.get("is_foreign")
    ]
    modules = [
        {
            "name": item.get("name", ""),
            "path": item.get("path", ""),
            "number": item.get("number"),
            "is_module": bool(item.get("is_module")),
            "file_counts": item.get("file_counts", {}),
        }
        for item in project_structure.get("modules", [])
    ]
    canonical_html = detect_html_path(review_dir)
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "project_id": project_id,
        "project_dir": str(project_dir),
        "review_dir": str(review_dir),
        "source_archive_path": str(source_archive_path) if source_archive_path else "",
        "review_lane": review_lane,
        "docx_only": docx_only,
        "publish_status": "pending",
        "archive_approved": False,
        "archived_at": "",
        "paths": {
            "report_text": str(review_dir / "report_text.txt"),
            "report_structure": str(review_dir / "report_structure.json"),
            "project_structure": str(review_dir / "project_structure.json"),
            "mechanical_check_result": str(review_dir / "mechanical_check_result.json"),
            "figure_audit": str(review_dir / "figure_audit.md"),
            "visual_prefilter": str(review_dir / "visual_prefilter.json"),
            "convergence_report": str(review_dir / "convergence_report.json"),
            "audit_state": str(review_dir / "audit_state.json"),
            "final_review_report": str(review_dir / "final_review_report.md"),
            "final_report_lint": str(review_dir / "final_report_lint.json"),
            "review_event_log": str(review_dir / EVENT_LOG_NAME),
            "html_report": str(canonical_html),
        },
        "report_summary": {
            "total_sections": report_structure.get("metadata", {}).get("total_sections", 0),
            "total_figures": report_structure.get("metadata", {}).get("total_figures", 0),
            "total_genes": report_structure.get("metadata", {}).get("total_genes", 0),
        },
        "project_summary": {
            "delivery_layout": metadata.get("delivery_layout", ""),
            "delivery_result_roots": metadata.get("delivery_result_roots", []),
            "delivery_code_roots": metadata.get("delivery_code_roots", []),
            "delivery_attachment_roots": metadata.get("delivery_attachment_roots", []),
            "total_modules": metadata.get("total_modules", 0),
            "total_code_files": metadata.get("total_code_files", 0),
            "total_config_files": metadata.get("total_config_files", 0),
            "total_data_files": metadata.get("total_data_files", 0),
            "total_images": metadata.get("total_images", 0),
            "all_packages": metadata.get("all_packages", []),
        },
        "datasets": datasets,
        "foreign_project_ids": foreign_ids,
        "modules": modules,
        "parameter_index": project_structure.get("parameter_index", {}),
        "config_files": project_structure.get("config_files", []),
    }

