#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression tests for policy-bound formal audit entrypoints."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import archive_reviewed_project
import finalize_audit
import prepare_ai_audit_guardrails
from auto_audit_pipeline import AutoAuditPipeline
from audit_runtime import current_policy_binding, validate_framework_binding


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_framework_binding_rejects_missing_or_stale_manifest_hash(tmp_path):
    review_dir = tmp_path / "26YTEST01F"
    review_dir.mkdir()
    _write_json(review_dir / "case_manifest.json", {"framework_version": "v7.0"})

    errors = validate_framework_binding(review_dir, require_ai_execution_manifest=False)

    assert any("policy_sha256" in error for error in errors)


def test_guardrail_rebuild_flag_records_explicit_policy_binding(tmp_path, monkeypatch):
    review_dir = tmp_path / "26YTEST02F"
    review_dir.mkdir()
    _write_json(review_dir / "case_manifest.json", {"project_id": review_dir.name})
    monkeypatch.setattr(prepare_ai_audit_guardrails, "load_precheck_results", lambda _path: {})
    monkeypatch.setattr(prepare_ai_audit_guardrails, "load_report_excerpt", lambda _path: "")
    monkeypatch.setattr(prepare_ai_audit_guardrails, "build_agent_prompt", lambda *args, **kwargs: "")
    monkeypatch.setattr(prepare_ai_audit_guardrails, "build_convergence_guide", lambda *args, **kwargs: "")
    monkeypatch.setattr(prepare_ai_audit_guardrails, "build_slice_manifest", lambda _path: {})
    monkeypatch.setattr(prepare_ai_audit_guardrails, "build_slice_prompt", lambda *args, **kwargs: "")
    monkeypatch.setattr(prepare_ai_audit_guardrails, "build_state", lambda _path: {})
    monkeypatch.setattr(prepare_ai_audit_guardrails, "SLICE_SPECS", [])
    monkeypatch.setattr(sys, "argv", ["prepare_ai_audit_guardrails.py", str(review_dir), "--rebuild-policy-binding"])

    assert prepare_ai_audit_guardrails.main() == 0
    manifest = json.loads((review_dir / "case_manifest.json").read_text(encoding="utf-8"))
    ai_manifest = json.loads((review_dir / "ai_execution_manifest.json").read_text(encoding="utf-8"))
    binding = current_policy_binding()

    assert manifest["policy_sha256"] == binding["policy_sha256"]
    assert manifest["policy_binding_previous"] == {"framework_version": "", "policy_sha256": ""}
    assert ai_manifest["policy_sha256"] == binding["policy_sha256"]


def test_finalize_fails_before_steps_when_policy_binding_is_invalid(tmp_path, monkeypatch):
    review_dir = tmp_path / "26YTEST03F"
    review_dir.mkdir()
    _write_json(review_dir / "case_manifest.json", {"project_id": review_dir.name})
    calls: list[str] = []
    monkeypatch.setattr(finalize_audit, "assert_framework_healthy", lambda: {})
    monkeypatch.setattr(finalize_audit, "run_step", lambda *_args: calls.append("step"))
    monkeypatch.setattr(sys, "argv", ["finalize_audit.py", str(review_dir)])

    assert finalize_audit.main() == 1
    assert calls == []


def test_finalize_fails_before_steps_when_framework_health_is_unhealthy(tmp_path, monkeypatch):
    review_dir = tmp_path / "26YTEST03G"
    review_dir.mkdir()
    calls: list[str] = []
    monkeypatch.setattr(
        finalize_audit,
        "assert_framework_healthy",
        lambda: (_ for _ in ()).throw(RuntimeError("version drift")),
    )
    monkeypatch.setattr(finalize_audit, "run_step", lambda *_args: calls.append("step"))
    monkeypatch.setattr(sys, "argv", ["finalize_audit.py", str(review_dir)])

    assert finalize_audit.main() == 1
    assert calls == []


def test_archive_normalization_checks_health_before_touching_input(tmp_path, monkeypatch):
    project_dir = tmp_path / "26YTEST03H"
    project_dir.mkdir()
    monkeypatch.setattr(
        "auto_audit_pipeline.assert_framework_healthy",
        lambda: (_ for _ in ()).throw(RuntimeError("version drift")),
    )

    try:
        AutoAuditPipeline.normalize_project_input(project_dir)
    except RuntimeError as exc:
        assert "version drift" in str(exc)
    else:
        raise AssertionError("health gate did not stop input normalization")


def test_new_pipeline_uses_strict_lane_from_canonical_policy_by_default(tmp_path, monkeypatch):
    project_dir = tmp_path / "26YTEST04F"
    project_dir.mkdir()
    monkeypatch.setattr(
        "auto_audit_pipeline.load_policy",
        lambda: {"framework_version": "v7.0", "review_lane_policy": {"default_lane": "strict"}},
    )

    pipeline = AutoAuditPipeline(str(project_dir))

    assert pipeline.review_lane == "strict"


def _write_archive_case(review_dir: Path) -> None:
    binding = current_policy_binding()
    _write_json(
        review_dir / "case_manifest.json",
        {
            "project_id": review_dir.name,
            "framework_version": binding["framework_version"],
            "policy_sha256": binding["policy_sha256"],
            "publish_status": "success",
            "archive_approved": False,
        },
    )
    _write_json(
        review_dir / "ai_execution_manifest.json",
        {
            "policy_version": binding["framework_version"],
            "policy_sha256": binding["policy_sha256"],
        },
    )
    html_path = review_dir / f"{review_dir.name}_audit_report.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    (review_dir / "wrong_question_set.md").write_text("# 错题集\n", encoding="utf-8")
    (review_dir / "framework_optimization_notes.md").write_text("# 框架优化\n", encoding="utf-8")
    delivery_manifest = review_dir / "formal_delivery_manifest.json"
    _write_json(delivery_manifest, {"schema_version": "1.0"})
    _write_json(
        review_dir / "completion_notification_receipt.json",
        {
            "status": "sent",
            "decision_sha256": "a" * 64,
            "html_report_sha256": archive_reviewed_project.sha256_file(html_path),
            "formal_delivery_manifest_sha256": archive_reviewed_project.sha256_file(delivery_manifest),
        },
    )


def _configure_archive_gate_dependencies(monkeypatch, failed_gate: str = "") -> None:
    def fail_health():
        if failed_gate == "health":
            raise RuntimeError("framework unhealthy")
        return {}

    monkeypatch.setattr(archive_reviewed_project, "assert_framework_healthy", fail_health)
    if failed_gate == "binding":
        monkeypatch.setattr(
            archive_reviewed_project,
            "validate_framework_binding",
            lambda *_args, **_kwargs: ["binding mismatch"],
        )
    monkeypatch.setattr(
        archive_reviewed_project,
        "load_policy",
        lambda: {
            "audit_contract_policy": {},
            "lesson_bank_policy": {
                "required_project_artifacts": [
                    "wrong_question_set.md",
                    "framework_optimization_notes.md",
                ]
            },
            "formal_delivery_policy": {"manifest_filename": "formal_delivery_manifest.json"},
            "notification_idempotency_policy": {
                "receipt_json": "completion_notification_receipt.json",
                "archive_requires_sent_receipt": True,
            },
        },
    )
    monkeypatch.setattr(
        archive_reviewed_project,
        "validate_review_contract",
        lambda *_args, **_kwargs: (
            {"contract_valid": False, "errors": ["contract invalid"]}
            if failed_gate == "contract"
            else {
                "contract_valid": True,
                "decision": {"status": "draft" if failed_gate == "leader" else "leader_confirmed"},
                "decision_sha256": "a" * 64,
            }
        ),
    )
    monkeypatch.setattr(
        archive_reviewed_project,
        "validate_review_professional_contracts",
        lambda *_args, **_kwargs: (
            {"blocking": True, "checks": {"arbitration": {"blocking": True}}}
            if failed_gate == "professional"
            else {"blocking": False, "checks": {}}
        ),
    )
    monkeypatch.setattr(
        archive_reviewed_project,
        "visual_audit_closure_status",
        lambda *_args, **_kwargs: (
            (False, ["visual closure missing"], {"closure_passed": False})
            if failed_gate == "visual"
            else (True, [], {"closure_passed": True})
        ),
    )
    monkeypatch.setattr(
        archive_reviewed_project,
        "validate_formal_delivery_manifest",
        lambda *_args, **_kwargs: (
            (False, "formal delivery mismatch")
            if failed_gate == "delivery"
            else (True, "")
        ),
    )


@pytest.mark.parametrize(
    "failed_gate",
    ["health", "binding", "contract", "leader", "professional", "visual", "learning", "delivery", "receipt"],
)
def test_direct_archive_fails_before_approval_or_move_when_formal_gate_is_missing(
    tmp_path, monkeypatch, failed_gate
):
    review_dir = tmp_path / "26YTEST05F"
    review_dir.mkdir()
    _write_archive_case(review_dir)
    _configure_archive_gate_dependencies(monkeypatch, failed_gate)
    if failed_gate == "learning":
        (review_dir / "wrong_question_set.md").write_text("", encoding="utf-8")
    if failed_gate == "receipt":
        _write_json(review_dir / "completion_notification_receipt.json", {"status": "failed"})
    moves: list[Path] = []
    monkeypatch.setattr(archive_reviewed_project, "move_reviewed_project", lambda _path: moves.append(_path))

    with pytest.raises(RuntimeError):
        archive_reviewed_project.archive_reviewed_project(review_dir, approve=True)

    manifest = json.loads((review_dir / "case_manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_approved"] is False
    assert moves == []


def test_direct_archive_temporary_case_passes_all_formal_prechecks_before_approval(tmp_path, monkeypatch):
    review_dir = tmp_path / "26YTEST06F"
    review_dir.mkdir()
    _write_archive_case(review_dir)
    _configure_archive_gate_dependencies(monkeypatch)
    archived_to = tmp_path / "已AI审核一次" / review_dir.name
    archived_to.mkdir(parents=True)
    monkeypatch.setattr(archive_reviewed_project, "precheck_archive_reviewed_project", lambda _path: None)
    monkeypatch.setattr(archive_reviewed_project, "infer_archived_project_path", lambda _path: None)
    monkeypatch.setattr(archive_reviewed_project, "move_reviewed_project", lambda _path: archived_to)
    monkeypatch.setattr(archive_reviewed_project, "assert_no_untracked_pending_entries", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(archive_reviewed_project, "append_event", lambda *_args, **_kwargs: None)

    moved_to = archive_reviewed_project.archive_reviewed_project(review_dir, approve=True)
    manifest = json.loads((review_dir / "case_manifest.json").read_text(encoding="utf-8"))

    assert moved_to == archived_to
    assert manifest["archive_approved"] is True
    assert manifest["archive_status"] == "success"
