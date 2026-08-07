#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Archive a reviewed project only after publication succeeds and approval is explicit."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from audit_contract import sha256_file, validate_review_contract
from audit_runtime import (
    append_event,
    detect_html_path,
    load_case_manifest,
    update_case_manifest,
    validate_framework_binding,
)
from ensure_review_html import assert_no_untracked_pending_entries, move_reviewed_project
from ensure_review_html import load_project_dir, load_source_archive, resolve_pending_project_root
from framework_health_check import assert_framework_healthy
from formal_delivery import validate_formal_delivery_manifest
from policy_loader import load_policy
from sync_audit_state import visual_audit_closure_status
from validate_professional_contracts import validate_review_professional_contracts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Move a reviewed project from raw/待审核 to raw/已AI审核一次 only when explicitly approved."
    )
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Mark archive_approved=true before attempting the move.",
    )
    return parser.parse_args()


def infer_archived_project_path(review_dir: Path) -> Path | None:
    """Return an existing archive destination for an already-archived review."""
    manifest = load_case_manifest(review_dir)
    archived_to = str(manifest.get("archived_to", "") or "").strip()
    if archived_to:
        archived_path = Path(archived_to)
        if archived_path.exists():
            return archived_path

    project_dir = load_project_dir(review_dir)
    source_archive = load_source_archive(review_dir)
    candidates: list[Path] = []

    # A re-audit can legitimately start from a project that was already moved
    # into the reviewed root.  Treat that exact existing path as the archive
    # destination rather than attempting a second move from raw/待审核.
    for path in (project_dir, source_archive):
        if path is not None and path.exists() and any(parent.name == "已AI审核一次" for parent in (path, *path.parents)):
            return path

    if project_dir is not None:
        pending_root = resolve_pending_project_root(project_dir)
        if pending_root is not None:
            candidates.append(pending_root.parent.parent / "已AI审核一次" / pending_root.name)

    if source_archive is not None:
        raw_root = source_archive.parent.parent if source_archive.parent.name == "待审核" else None
        if raw_root is not None:
            candidates.append(raw_root / "已AI审核一次" / source_archive.stem)

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def precheck_archive_reviewed_project(review_dir: Path) -> Path | None:
    """Fail before notification when the archive source/target cannot be resolved."""
    html_path = detect_html_path(review_dir)
    if not html_path.exists():
        raise RuntimeError("Cannot archive before the canonical HTML report exists.")

    project_dir = load_project_dir(review_dir)
    source_archive = load_source_archive(review_dir)
    pending_root = resolve_pending_project_root(project_dir) if project_dir is not None else None
    allowed_entries = [entry for entry in (pending_root, source_archive) if entry is not None]

    already_archived = infer_archived_project_path(review_dir)
    if already_archived is not None:
        assert_no_untracked_pending_entries(review_dir, project_dir)
        return already_archived

    assert_no_untracked_pending_entries(
        review_dir,
        project_dir,
        allowed_entries=allowed_entries,
    )

    if project_dir is not None:
        if pending_root is not None and pending_root.exists():
            return pending_root

    if source_archive is not None and source_archive.exists():
        return source_archive

    raise RuntimeError("Archive precheck failed: pending project/source archive not found and no archived destination exists.")


def _required_direct_child(review_dir: Path, raw_name: object, *, label: str) -> Path:
    name = str(raw_name or "").strip()
    if not name or Path(name).name != name:
        raise RuntimeError(f"Cannot archive: {label} filename must be a direct child of the review directory.")
    return review_dir / name


def _read_json_object(path: Path, *, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot archive: {label} is missing or unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Cannot archive: {label} root must be an object.")
    return payload


def validate_formal_archive_gates(review_dir: Path) -> None:
    """Run the formal, read-only audit gates required by the direct archive CLI."""
    assert_framework_healthy()

    binding_errors = validate_framework_binding(review_dir, require_ai_execution_manifest=True)
    if binding_errors:
        raise RuntimeError("Cannot archive with invalid policy binding: " + "; ".join(binding_errors))

    policy = load_policy()
    contract_policy = policy.get("audit_contract_policy", {})
    if not isinstance(contract_policy, dict):
        contract_policy = {}
    contract = validate_review_contract(review_dir, contract_policy)
    decision = contract.get("decision", {})
    if not contract.get("contract_valid", False) or not isinstance(decision, dict):
        errors = contract.get("errors", [])
        detail = "; ".join(str(error) for error in errors) or "final decision contract is invalid"
        raise RuntimeError(f"Cannot archive before the final audit contract is valid: {detail}")
    if decision.get("status") != "leader_confirmed":
        raise RuntimeError("Cannot archive before final_decision.status=leader_confirmed.")
    decision_sha256 = str(contract.get("decision_sha256", "")).strip().lower()
    if len(decision_sha256) != 64:
        raise RuntimeError("Cannot archive before the sealed final decision SHA256 is available.")

    professional = validate_review_professional_contracts(review_dir, policy)
    if professional.get("blocking", True):
        failed_checks = [
            name
            for name, check in professional.get("checks", {}).items()
            if isinstance(check, dict) and check.get("blocking", False)
        ]
        detail = ", ".join(failed_checks) or "professional contract validation failed"
        raise RuntimeError(f"Cannot archive before professional audit contracts pass: {detail}")

    _legacy_passed, visual_errors, visual_closure = visual_audit_closure_status(review_dir)
    if not visual_closure.get("closure_passed", False):
        detail = "; ".join(str(error) for error in visual_errors) or "visual audit closure is incomplete"
        raise RuntimeError(f"Cannot archive before visual audit closure passes: {detail}")

    lesson_policy = policy.get("lesson_bank_policy", {})
    if not isinstance(lesson_policy, dict):
        lesson_policy = {}
    required_learning = lesson_policy.get(
        "required_project_artifacts",
        ["wrong_question_set.md", "framework_optimization_notes.md"],
    )
    if not isinstance(required_learning, list) or not required_learning:
        required_learning = ["wrong_question_set.md", "framework_optimization_notes.md"]
    for raw_name in required_learning:
        learning_path = _required_direct_child(
            review_dir,
            raw_name,
            label="post-audit learning artifact",
        )
        if not learning_path.is_file() or not learning_path.read_text(encoding="utf-8").strip():
            raise RuntimeError(
                f"Cannot archive before the post-audit learning artifact exists and is non-empty: {learning_path.name}"
            )

    delivery_policy = policy.get("formal_delivery_policy", {})
    if not isinstance(delivery_policy, dict):
        delivery_policy = {}
    delivery_manifest = _required_direct_child(
        review_dir,
        delivery_policy.get("manifest_filename", "formal_delivery_manifest.json"),
        label="formal delivery manifest",
    )
    html_path = detect_html_path(review_dir)
    if not html_path.is_file():
        raise RuntimeError("Cannot archive before the canonical HTML report exists.")
    delivery_metadata = {
        "project_id": review_dir.name,
        "review_dir": str(review_dir),
        "html_report": str(html_path),
        "formal_delivery_manifest": str(delivery_manifest),
        "html_report_sha256": sha256_file(html_path),
        "formal_delivery_manifest_sha256": sha256_file(delivery_manifest)
        if delivery_manifest.is_file()
        else "",
    }
    delivery_ok, delivery_reason = validate_formal_delivery_manifest(
        delivery_metadata,
        {
            "formal_delivery_gate": {
                "enabled": True,
                "manifest_filename": delivery_manifest.name,
            }
        },
    )
    if not delivery_ok:
        raise RuntimeError(f"Cannot archive before formal delivery binding passes: {delivery_reason}")

    idempotency_policy = policy.get("notification_idempotency_policy", {})
    if not isinstance(idempotency_policy, dict):
        idempotency_policy = {}
    if idempotency_policy.get("archive_requires_sent_receipt", True):
        receipt_path = _required_direct_child(
            review_dir,
            idempotency_policy.get("receipt_json", "completion_notification_receipt.json"),
            label="completion notification receipt",
        )
        receipt = _read_json_object(receipt_path, label="completion notification receipt")
        if receipt.get("status") != "sent":
            raise RuntimeError("Cannot archive before completion notification receipt status=sent.")
        if str(receipt.get("decision_sha256", "")).strip().lower() != decision_sha256:
            raise RuntimeError("Cannot archive: completion notification receipt decision SHA256 is stale.")
        if str(receipt.get("html_report_sha256", "")).strip().lower() != sha256_file(html_path):
            raise RuntimeError("Cannot archive: completion notification receipt HTML SHA256 is stale.")
        if (
            str(receipt.get("formal_delivery_manifest_sha256", "")).strip().lower()
            != sha256_file(delivery_manifest)
        ):
            raise RuntimeError("Cannot archive: completion notification receipt formal delivery manifest SHA256 is stale.")


def archive_reviewed_project(review_dir: Path, *, approve: bool = False) -> Path:
    # Direct CLI use must not be able to turn approval into a side effect before
    # the same formal audit gates have passed.  All gates above are read-only.
    validate_formal_archive_gates(review_dir)

    manifest = load_case_manifest(review_dir)
    if not manifest:
        raise FileNotFoundError(f"case_manifest.json not found: {review_dir}")
    project_dir = load_project_dir(review_dir)

    if approve:
        manifest = update_case_manifest(
            review_dir,
            {
                "archive_approved": True,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

    if manifest.get("publish_status") != "success":
        raise RuntimeError("Cannot archive before publish_status=success.")

    html_path = detect_html_path(review_dir)
    if not html_path.exists():
        raise RuntimeError("Cannot archive before the canonical HTML report exists.")

    if not manifest.get("archive_approved", False):
        raise RuntimeError("Cannot archive before archive_approved=true.")

    # This function is also a CLI entry point. Re-run the pre-notification
    # residual check here so direct invocations cannot bypass the same gate.
    precheck_archive_reviewed_project(review_dir)

    already_archived = infer_archived_project_path(review_dir)
    if already_archived is not None:
        update_case_manifest(
            review_dir,
            {
                "archived_to": str(already_archived),
                "archived_at": str(manifest.get("archived_at") or datetime.now().isoformat(timespec="seconds")),
                "archive_status": "success",
                "archive_approved": True,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        append_event(
            review_dir,
            "project_archive_already_done",
            actor="archive_reviewed_project",
            outputs=[str(already_archived)],
            details={"html_path": str(html_path)},
        )
        return already_archived

    moved_to = move_reviewed_project(review_dir)
    if moved_to is None:
        already_archived = infer_archived_project_path(review_dir)
        if already_archived is None:
            raise RuntimeError("Archive move did not run. Check manifest project_dir/source archive metadata.")
        moved_to = already_archived

    assert_no_untracked_pending_entries(review_dir, project_dir)

    update_case_manifest(
        review_dir,
        {
            "archived_at": datetime.now().isoformat(timespec="seconds"),
            "archived_to": str(moved_to),
            "archive_status": "success",
            "archive_approved": True,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    append_event(
        review_dir,
        "project_archived",
        actor="archive_reviewed_project",
        outputs=[str(moved_to)],
        details={"html_path": str(html_path)},
    )
    return moved_to


def main() -> int:
    args = parse_args()
    review_dir = Path(args.review_dir)
    if not review_dir.exists():
        raise FileNotFoundError(f"Review directory does not exist: {review_dir}")

    moved_to = archive_reviewed_project(review_dir, approve=args.approve)
    print(f"项目已移动到: {moved_to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
