#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Contract sealing and completion-notification idempotency tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import finalize_audit
import prepare_audit_finalize
import validate_audit_contract
from audit_contract import atomic_write_json, contract_mode, sha256_file, validate_review_contract


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _contract_policy(mode: str = "enforce") -> dict:
    return {
        "schema_version": "1.0",
        "mode": mode,
        "decision_json": "final_decision.json",
        "validation_json": "audit_contract_validation.json",
        "allowed_verdict_release_pairs": {
            "合格": "ALLOW",
            "有条件合格": "CONDITIONAL",
            "不合格": "BLOCK",
        },
        "required_severity_levels": ["FATAL", "CRITICAL", "MAJOR", "WARNING", "INFO"],
        "formal_completion_requires_unresolved_count": 0,
        "source_paths_must_be_review_relative": True,
        "source_hash_algorithm": "sha256",
        "shadow_exit_code_on_would_block": 0,
        "enforce_exit_code_on_block": 1,
    }


def _make_valid_review(tmp_path: Path) -> tuple[Path, dict]:
    review_dir = tmp_path / "26YTEST01F"
    arbitration_path = review_dir / "agent_results" / "arbitration" / "arbitration_resolution.json"
    report_path = review_dir / "final_review_report.md"
    arbitration_path.parent.mkdir(parents=True)
    report_path.write_text(
        "# 最终审核报告\n\n## 审核结论\n\n结论：不合格。\n",
        encoding="utf-8",
    )
    _write_json(arbitration_path, {"schema_version": "2.0", "items": []})
    decision = {
        "schema_version": "1.0",
        "project_id": review_dir.name,
        "status": "leader_confirmed",
        "confirmed_by": "leader",
        "confirmed_at": "2026-07-22T11:30:00+08:00",
        "score": 50,
        "score_scale": 100,
        "verdict": "不合格",
        "release_decision": "BLOCK",
        "severity_counts": {
            "FATAL": 1,
            "CRITICAL": 2,
            "MAJOR": 3,
            "WARNING": 4,
            "INFO": 5,
        },
        "canonical_finding_count": 15,
        "unresolved_count": 0,
        "sources": {
            "arbitration_resolution": {
                "path": "agent_results/arbitration/arbitration_resolution.json",
                "sha256": sha256_file(arbitration_path),
            },
            "final_review_report": {
                "path": "final_review_report.md",
                "sha256": sha256_file(report_path),
            },
        },
    }
    _write_json(review_dir / "final_decision.json", decision)
    return review_dir, decision


def _replace_bound_report(review_dir: Path, decision: dict, report_text: str) -> None:
    report_path = review_dir / "final_review_report.md"
    report_path.write_text(report_text, encoding="utf-8")
    decision["sources"]["final_review_report"]["sha256"] = sha256_file(report_path)
    _write_json(review_dir / "final_decision.json", decision)


def test_valid_contract_binds_both_sources_and_builds_notification_fields(tmp_path):
    review_dir, _ = _make_valid_review(tmp_path)

    result = validate_review_contract(review_dir, _contract_policy())

    assert result["contract_valid"] is True
    assert result["blocking"] is False
    verdict_check = next(
        check
        for check in result["checks"]
        if check["name"] == "source.final_review_report.verdict"
    )
    assert verdict_check["passed"] is True
    fields = finalize_audit.extract_contract_notification_fields(result["decision"])
    assert fields["audit_result"] == "不通过（50/100）"
    assert fields["issue_stats"] == "CRITICAL: 3；MAJOR: 3；WARNING: 4"


@pytest.mark.parametrize(
    "report_text",
    [
        "# 最终审核报告\n\n## 审核结论\n\n本报告确认 15 项审核发现。\n",
        "# 最终审核报告\n\n## 审核结论\n\n结论：有条件通过。\n",
        "# 最终审核报告\n\n## 审核结论\n\n结论：建议通过。\n",
    ],
    ids=["missing", "conditional", "pass"],
)
def test_enforce_blocks_missing_or_mismatched_report_verdict(tmp_path, report_text):
    review_dir, decision = _make_valid_review(tmp_path)
    _replace_bound_report(review_dir, decision, report_text)

    result = validate_review_contract(review_dir, _contract_policy("enforce"))

    verdict_check = next(
        check
        for check in result["checks"]
        if check["name"] == "source.final_review_report.verdict"
    )
    assert verdict_check["passed"] is False
    assert result["contract_valid"] is False
    assert result["would_block"] is True
    assert result["blocking"] is True


def test_contract_mode_missing_or_invalid_fails_closed():
    assert contract_mode({}) == "enforce"
    assert contract_mode({"mode": "invalid"}) == "enforce"
    assert contract_mode({"mode": "shadow"}) == "shadow"


def test_shadow_reports_would_block_but_does_not_block(tmp_path):
    review_dir = tmp_path / "26YTEST02F"
    review_dir.mkdir()

    result = validate_review_contract(review_dir, _contract_policy("shadow"))

    assert result["contract_valid"] is False
    assert result["would_block"] is True
    assert result["blocking"] is False
    assert any("final_decision.json" in error for error in result["errors"])


def test_enforce_blocks_when_confirmed_report_hash_is_stale(tmp_path):
    review_dir, _ = _make_valid_review(tmp_path)
    (review_dir / "final_review_report.md").write_text("# 被修改的报告\n", encoding="utf-8")

    result = validate_review_contract(review_dir, _contract_policy("enforce"))

    assert result["contract_valid"] is False
    assert result["blocking"] is True
    assert any("sha256" in error for error in result["errors"])


def test_validator_cli_exit_codes_follow_policy_mode(tmp_path, monkeypatch):
    review_dir = tmp_path / "26YTEST03F"
    review_dir.mkdir()

    monkeypatch.setattr(
        validate_audit_contract,
        "load_policy",
        lambda: {"audit_contract_policy": _contract_policy("shadow")},
    )
    monkeypatch.setattr(sys, "argv", ["validate_audit_contract.py", str(review_dir)])
    assert validate_audit_contract.main() == 0

    monkeypatch.setattr(
        validate_audit_contract,
        "load_policy",
        lambda: {"audit_contract_policy": _contract_policy("enforce")},
    )
    assert validate_audit_contract.main() == 1


def test_atomic_json_writer_replaces_complete_document(tmp_path):
    output = tmp_path / "receipt.json"
    output.write_text('{"old": true}', encoding="utf-8")

    atomic_write_json(output, {"status": "sent", "value": 2})

    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "sent", "value": 2}
    assert not list(tmp_path.glob(".receipt.json.*.tmp"))


def test_prepare_refuses_to_mutate_after_leader_confirmation(tmp_path, monkeypatch):
    review_dir, _ = _make_valid_review(tmp_path)
    monkeypatch.setattr(prepare_audit_finalize, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        prepare_audit_finalize,
        "run_lint_step",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("sealed report was linted for mutation")),
    )
    monkeypatch.setattr(sys, "argv", ["prepare_audit_finalize.py", str(review_dir)])

    assert prepare_audit_finalize.main() == 1


def test_enforce_finalize_never_runs_mutating_repair_steps(tmp_path, monkeypatch):
    review_dir = tmp_path / "26YTEST04F"
    review_dir.mkdir()
    calls: list[str] = []

    def fake_run_step(target: Path, script_name: str) -> subprocess.CompletedProcess[str]:
        calls.append(script_name)
        if script_name == "final_report_linter.py":
            _write_json(
                review_dir / "final_report_lint.json",
                {"passed": False, "error_count": 1, "warning_count": 0},
            )
            return subprocess.CompletedProcess([script_name], 1, stdout="", stderr="")
        return subprocess.CompletedProcess([script_name], 0, stdout="", stderr="")

    monkeypatch.setattr(
        finalize_audit,
        "load_policy",
        lambda: {
            "audit_contract_policy": _contract_policy("enforce"),
            "notification_idempotency_policy": {
                "mode": "enforce",
                "pre_notification_gate_failures_are_local_only": True,
            },
        },
    )
    monkeypatch.setattr(finalize_audit, "run_step", fake_run_step)
    monkeypatch.setattr(finalize_audit, "append_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(finalize_audit, "update_case_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        finalize_audit,
        "send_notification",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("pre-gate notification sent")),
    )
    monkeypatch.setattr(sys, "argv", ["finalize_audit.py", str(review_dir)])

    assert finalize_audit.main() == 1
    assert calls == []


def test_matching_sent_receipt_skips_duplicate_send(tmp_path, monkeypatch):
    review_dir, _ = _make_valid_review(tmp_path)
    decision_sha256 = sha256_file(review_dir / "final_decision.json")
    metadata = {
        "project_id": review_dir.name,
        "audit_result": "不通过（50/100）",
        "issue_stats": "CRITICAL: 3；MAJOR: 3；WARNING: 4",
    }
    body_sha256 = finalize_audit.notification_body_sha256(review_dir, "done", metadata)
    receipt_path = review_dir / "completion_notification_receipt.json"
    _write_json(
        receipt_path,
        {
            "schema_version": "1.0",
            "status": "sent",
            "decision_sha256": decision_sha256,
            "body_sha256": body_sha256,
            "channel": "feishu",
        },
    )
    monkeypatch.setattr(
        finalize_audit,
        "send_notification",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("duplicate notification sent")),
    )

    ok, message = finalize_audit.send_completion_notification_once(
        review_dir,
        summary="done",
        metadata=metadata,
        config_arg="",
        channel="feishu",
        decision_sha256=decision_sha256,
        receipt_path=receipt_path,
        policy={
            "states": ["pending", "sent", "failed", "unknown"],
            "skip_send_when_matching_receipt_is_sent": True,
            "block_automatic_resend_when_status_unknown": True,
            "block_when_receipt_decision_hash_differs": True,
        },
    )

    assert ok is True
    assert "receipt" in message.lower()


def test_mismatched_receipt_blocks_automatic_resend(tmp_path, monkeypatch):
    review_dir, _ = _make_valid_review(tmp_path)
    receipt_path = review_dir / "completion_notification_receipt.json"
    _write_json(
        receipt_path,
        {
            "schema_version": "1.0",
            "status": "sent",
            "decision_sha256": "0" * 64,
            "body_sha256": "1" * 64,
            "channel": "feishu",
        },
    )
    monkeypatch.setattr(
        finalize_audit,
        "send_notification",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("mismatched receipt resent")),
    )

    ok, message = finalize_audit.send_completion_notification_once(
        review_dir,
        summary="done",
        metadata={"project_id": review_dir.name},
        config_arg="",
        channel="feishu",
        decision_sha256=sha256_file(review_dir / "final_decision.json"),
        receipt_path=receipt_path,
        policy={
            "states": ["pending", "sent", "failed", "unknown"],
            "skip_send_when_matching_receipt_is_sent": True,
            "block_automatic_resend_when_status_unknown": True,
            "block_when_receipt_decision_hash_differs": True,
        },
    )

    assert ok is False
    assert "decision" in message.lower()


def test_failed_receipt_retries_and_transitions_to_sent(tmp_path, monkeypatch):
    review_dir, _ = _make_valid_review(tmp_path)
    receipt_path = review_dir / "completion_notification_receipt.json"
    outcomes = iter([(False, "temporary failure"), (True, "sent")])
    monkeypatch.setattr(finalize_audit, "send_notification", lambda **kwargs: next(outcomes))
    monkeypatch.setattr(finalize_audit, "append_event", lambda *args, **kwargs: None)
    kwargs = {
        "summary": "done",
        "metadata": {"project_id": review_dir.name},
        "config_arg": "",
        "channel": "feishu",
        "decision_sha256": sha256_file(review_dir / "final_decision.json"),
        "receipt_path": receipt_path,
        "policy": {
            "skip_send_when_matching_receipt_is_sent": True,
            "block_automatic_resend_when_status_unknown": True,
            "block_when_receipt_decision_hash_differs": True,
        },
    }

    send_result = finalize_audit.send_completion_notification_once(review_dir, **kwargs)
    assert send_result[0] is False
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["status"] == "failed"
    assert finalize_audit.send_completion_notification_once(review_dir, **kwargs)[0] is True
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "sent"
    assert receipt["attempt_count"] == 2


def test_known_local_preflight_unknown_receipt_recovers_to_one_send(tmp_path, monkeypatch):
    review_dir, _ = _make_valid_review(tmp_path)
    receipt_path = review_dir / "completion_notification_receipt.json"
    decision_sha256 = sha256_file(review_dir / "final_decision.json")
    metadata = {"project_id": review_dir.name}
    _write_json(
        receipt_path,
        {
            "schema_version": "1.0",
            "status": "unknown",
            "decision_sha256": decision_sha256,
            "body_sha256": finalize_audit.notification_body_sha256(review_dir, "done", metadata),
            "channel": "wecom",
            "attempt_count": 1,
            "error": (
                "primary notification failed: "
                f"'{review_dir.resolve() / 'visual_audit_result.json'}' is not in the subpath of "
                f"'{review_dir}'"
            ),
        },
    )
    sent: list[dict] = []
    monkeypatch.setattr(finalize_audit, "send_notification", lambda **kwargs: sent.append(kwargs) or (True, "sent"))
    monkeypatch.setattr(finalize_audit, "append_event", lambda *args, **kwargs: None)

    ok, _ = finalize_audit.send_completion_notification_once(
        review_dir,
        summary="done",
        metadata=metadata,
        config_arg="",
        channel="wecom",
        decision_sha256=decision_sha256,
        receipt_path=receipt_path,
        policy={
            "states": ["pending", "sent", "failed", "unknown"],
            "skip_send_when_matching_receipt_is_sent": True,
            "block_automatic_resend_when_status_unknown": True,
            "block_when_receipt_decision_hash_differs": True,
        },
    )

    assert ok is True
    assert len(sent) == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "sent"
    assert receipt["attempt_count"] == 2
