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
AI_EXECUTION_MANIFEST_NAME = "ai_execution_manifest.json"


def current_policy_binding() -> dict[str, str]:
    """Identify the exact canonical policy used to start a formal audit."""
    from policy_loader import policy_path

    policy_file = policy_path()
    policy_bytes = policy_file.read_bytes()
    policy = json.loads(policy_bytes.decode("utf-8"))
    return {
        "framework_version": str(policy.get("framework_version", "") or ""),
        "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
    }


def validate_framework_binding(
    review_dir: Path,
    *,
    require_ai_execution_manifest: bool,
) -> list[str]:
    """Return binding errors without changing a review directory.

    A policy version alone is insufficient because policy content can change
    without a version bump.  Missing fields are failures rather than being
    backfilled here, so legacy reviews require an explicit rebuild step.
    """
    expected = current_policy_binding()
    errors: list[str] = []

    case_manifest = load_case_manifest(review_dir)
    if not case_manifest:
        errors.append("case_manifest.json is missing or unreadable")
    else:
        for field, expected_value in expected.items():
            actual = str(case_manifest.get(field, "") or "")
            if not actual:
                errors.append(
                    f"case_manifest.json is missing {field}; rerun canonical precheck or explicitly rebuild the policy binding"
                )
            elif actual != expected_value:
                errors.append(
                    f"case_manifest.json {field} does not match the current canonical policy"
                )

    if require_ai_execution_manifest:
        ai_manifest = read_json(review_dir / AI_EXECUTION_MANIFEST_NAME)
        if not ai_manifest:
            errors.append("ai_execution_manifest.json is missing or unreadable")
        else:
            expected_fields = {
                "policy_version": expected["framework_version"],
                "policy_sha256": expected["policy_sha256"],
            }
            for field, expected_value in expected_fields.items():
                actual = str(ai_manifest.get(field, "") or "")
                if not actual:
                    errors.append(
                        f"ai_execution_manifest.json is missing {field}; rerun guardrail generation explicitly"
                    )
                elif actual != expected_value:
                    errors.append(
                        f"ai_execution_manifest.json {field} does not match the current canonical policy"
                    )
    return errors


def rebuild_case_manifest_policy_binding(review_dir: Path) -> dict:
    """Explicitly bind a legacy case to the current policy before regeneration."""
    path = review_dir / CASE_MANIFEST_NAME
    data = read_json(path)
    if not data:
        raise RuntimeError("Cannot rebuild policy binding: case_manifest.json is missing or unreadable")

    previous = {
        "framework_version": data.get("framework_version", ""),
        "policy_sha256": data.get("policy_sha256", ""),
    }
    data.update(current_policy_binding())
    data["policy_binding_rebuilt_at"] = datetime.now().isoformat(timespec="seconds")
    data["policy_binding_previous"] = previous
    write_json(path, data)
    return data


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
    task_id: str = "",
    attempt: int | None = None,
    phase: str = "",
    agent: str = "",
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    details: dict | None = None,
) -> Path:
    event = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "event_type": event_type,
        "status": status,
        "actor": actor,
        "task_id": normalize_text(task_id),
        "attempt": attempt,
        "phase": normalize_text(phase),
        "agent": normalize_text(agent) or normalize_text(actor),
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
    try:
        from policy_loader import load_policy

        policy = load_policy()
    except (ImportError, OSError, ValueError, json.JSONDecodeError):
        policy = {}
    contract_policy = policy.get("audit_contract_policy", {})
    if not isinstance(contract_policy, dict):
        contract_policy = {}
    notification_policy = policy.get("notification_idempotency_policy", {})
    if not isinstance(notification_policy, dict):
        notification_policy = {}
    professional_policy = policy.get("professional_contract_policy", {})
    if not isinstance(professional_policy, dict):
        professional_policy = {}
    data.setdefault("schema_version", str(contract_policy.get("manifest_schema_version", "1.1")))
    data.setdefault("audit_contract_version", str(contract_policy.get("audit_contract_version", "1.0")))
    paths = data.setdefault("paths", {})
    if isinstance(paths, dict):
        paths.setdefault(
            "final_decision",
            str(review_dir / str(contract_policy.get("decision_json", "final_decision.json"))),
        )
        paths.setdefault(
            "audit_contract_validation",
            str(review_dir / str(contract_policy.get("validation_json", "audit_contract_validation.json"))),
        )
        paths.setdefault(
            "completion_notification_receipt",
            str(review_dir / str(notification_policy.get("receipt_json", "completion_notification_receipt.json"))),
        )
        paths.setdefault(
            "professional_contract_validation",
            str(
                review_dir
                / str(
                    professional_policy.get(
                        "validation_json", "professional_contract_validation.json"
                    )
                )
            ),
        )
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
    review_lane: str | None = None,
    docx_only: bool = False,
) -> dict:
    try:
        from policy_loader import load_policy

        policy = load_policy()
    except (ImportError, OSError, ValueError, json.JSONDecodeError):
        policy = {}
    contract_policy = policy.get("audit_contract_policy", {})
    if not isinstance(contract_policy, dict):
        contract_policy = {}
    notification_policy = policy.get("notification_idempotency_policy", {})
    if not isinstance(notification_policy, dict):
        notification_policy = {}
    professional_policy = policy.get("professional_contract_policy", {})
    if not isinstance(professional_policy, dict):
        professional_policy = {}
    structured_artifacts = professional_policy.get("structured_artifacts", {})
    if not isinstance(structured_artifacts, dict):
        structured_artifacts = {}
    configured_lane = str(
        policy.get("review_lane_policy", {}).get("default_lane", "strict") or "strict"
    )
    review_lane = str(review_lane or configured_lane)
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
    policy_binding = current_policy_binding()
    return {
        "schema_version": str(contract_policy.get("manifest_schema_version", "1.1")),
        "framework_version": policy_binding["framework_version"],
        "policy_sha256": policy_binding["policy_sha256"],
        "audit_contract_version": str(contract_policy.get("audit_contract_version", "1.0")),
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
            "visual_audit_result": str(review_dir / "visual_audit_result.json"),
            "convergence_report": str(review_dir / "convergence_report.json"),
            "audit_state": str(review_dir / "audit_state.json"),
            "final_review_report": str(review_dir / "final_review_report.md"),
            "final_report_lint": str(review_dir / "final_report_lint.json"),
            "subagent_supervision_summary": str(review_dir / "subagent_supervision_summary.json"),
            "subagent_supervision_gate": str(review_dir / "subagent_supervision_gate.json"),
            "review_event_log": str(review_dir / EVENT_LOG_NAME),
            "arbitration_resolution": str(
                review_dir / "agent_results" / "arbitration" / "arbitration_resolution.json"
            ),
            "final_decision": str(
                review_dir / str(contract_policy.get("decision_json", "final_decision.json"))
            ),
            "audit_contract_validation": str(
                review_dir
                / str(contract_policy.get("validation_json", "audit_contract_validation.json"))
            ),
            "completion_notification_receipt": str(
                review_dir
                / str(notification_policy.get("receipt_json", "completion_notification_receipt.json"))
            ),
            "professional_contract_validation": str(
                review_dir
                / str(
                    professional_policy.get(
                        "validation_json", "professional_contract_validation.json"
                    )
                )
            ),
            **{
                f"professional_{contract_type}": str(review_dir / str(filename))
                for contract_type, filename in structured_artifacts.items()
            },
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
