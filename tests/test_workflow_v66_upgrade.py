#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression tests for the v6.6 workflow hardening changes."""

from __future__ import annotations

import json
import subprocess
import sys
import copy
from pathlib import Path

import pytest

import archive_reviewed_project as archive_reviewed_project_module
from archive_reviewed_project import archive_reviewed_project
from convergence_compare import classify_groups, match_findings, validate_slice_outputs
from ensure_review_html import ensure_one
import finalize_audit
from final_report_linter import _normalize_local_target, build_checks
from launch_convergence_audit import SLICE_SPECS, build_slice_manifest, build_slice_prompt
from generate_policy_docs import write_documents
from notification_client import build_body
from parse_project_structure import parse_project
from sync_audit_state import build_state
from visual_audit import prepare_visual_audit
from auto_audit_pipeline import AutoAuditPipeline
from audit_runtime import current_policy_binding


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_policy_bound_case_manifest(review_dir: Path, payload: dict) -> None:
    write_json(review_dir / "case_manifest.json", {**payload, **current_policy_binding()})


def configure_unsealed_finalize_flow(monkeypatch, review_dir: Path) -> None:
    """Isolate legacy orchestration tests from separately tested sealed gates."""
    policy = copy.deepcopy(finalize_audit.load_policy())
    policy["audit_contract_policy"]["mode"] = "shadow"
    policy["notification_idempotency_policy"]["pre_notification_gate_failures_are_local_only"] = False
    monkeypatch.setattr(finalize_audit, "load_policy", lambda: policy)
    monkeypatch.setattr(
        finalize_audit,
        "validate_and_write_contract",
        lambda _review_dir, _policy: {"blocking": False, "contract_valid": False, "decision_sha256": ""},
    )
    monkeypatch.setattr(finalize_audit, "publication_state_ready", lambda _review_dir: (True, []))

    def fake_delivery_manifest(_review_dir: Path, _html_path: Path, **_kwargs):
        manifest_path = review_dir / "formal_delivery_manifest.json"
        write_json(manifest_path, {"schema_version": "test"})
        return manifest_path, {}

    def fake_archive(target: Path, *, approve: bool = False) -> Path:
        archived_root = target.parent / "_test_archived" / target.name
        archived_root.mkdir(parents=True, exist_ok=True)
        finalize_audit.update_case_manifest(
            target,
            {
                "archive_approved": approve,
                "archived_at": "2026-08-04T00:00:00",
                "updated_at": "2026-08-04T00:00:00",
            },
        )
        return archived_root

    monkeypatch.setattr(finalize_audit, "build_formal_delivery_manifest", fake_delivery_manifest)
    monkeypatch.setattr(finalize_audit, "build_finalize_notification_metadata", lambda *_args, **_kwargs: {"formal_audit": "true"})
    monkeypatch.setattr(finalize_audit, "precheck_archive_reviewed_project", lambda _review_dir: None)
    monkeypatch.setattr(finalize_audit, "archive_reviewed_project", fake_archive)


def test_parse_project_collects_config_parameters(tmp_path):
    project_dir = tmp_path / "26YHB999F-demo"
    project_dir.mkdir()
    (project_dir / "config.yaml").write_text(
        "logFC_cutoff: 0.5\npvalue_cutoff: 0.05\nmethod: limma\n",
        encoding="utf-8",
    )
    (project_dir / "analysis.R").write_text("logFC_cutoff <- 1\n", encoding="utf-8")

    parsed = parse_project(project_dir)

    config_files = parsed["config_files"]
    assert any(item["path"] == "config.yaml" for item in config_files)
    parameter_index = parsed["parameter_index"]
    assert "logFC_threshold" in parameter_index
    assert any(entry["source"] == "config" and entry["file"] == "config.yaml" for entry in parameter_index["logFC_threshold"])
    assert any(entry["source"] == "code" and entry["file"] == "analysis.R" for entry in parameter_index["logFC_threshold"])


def test_parse_project_accepts_single_digit_modules_and_xlsx_data(tmp_path):
    project_dir = tmp_path / "25YHB539F-demo"
    module_one = project_dir / "1-survival"
    module_two = project_dir / "2-enrichment"
    module_one.mkdir(parents=True)
    module_two.mkdir(parents=True)
    (module_one / "KM.pdf").write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Pages /Count 1 >>\nendobj\n")
    (module_two / "GO_result_all.xlsx").write_bytes(b"xlsx")
    (module_two / "table.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    parsed = parse_project(project_dir)

    assert parsed["metadata"]["total_modules"] == 2
    assert parsed["metadata"]["total_data_files"] == 2
    modules = {item["path"]: item for item in parsed["modules"]}
    assert modules["1-survival"]["is_module"] is True
    assert modules["1-survival"]["file_counts"]["pdf"] == 1
    assert modules["2-enrichment"]["file_counts"]["csv"] == 2


def test_parse_project_accepts_dot_numbered_flat_modules(tmp_path):
    project_dir = tmp_path / "26YBB063F-demo"
    module_one = project_dir / "1.eQTL_POP"
    module_two = project_dir / "11.Drug"
    supplement = project_dir / "Table S"
    module_one.mkdir(parents=True)
    module_two.mkdir()
    supplement.mkdir()
    (module_one / "MR_results_0.05.csv").write_text("gene,pvalue\nA,0.01\n", encoding="utf-8")
    (module_one / "forestplot.pdf").write_bytes(b"%PDF-1.4\n")
    (module_two / "dock.png").write_bytes(b"png")
    (supplement / "Table S7.xlsx").write_bytes(b"xlsx")

    parsed = parse_project(project_dir)

    assert parsed["metadata"]["total_modules"] == 2
    modules = {item["path"]: item for item in parsed["modules"]}
    assert modules["1.eQTL_POP"]["is_module"] is True
    assert modules["1.eQTL_POP"]["file_counts"]["csv"] == 1
    assert modules["1.eQTL_POP"]["file_counts"]["pdf"] == 1
    assert modules["11.Drug"]["file_counts"]["images"] == 1
    assert modules["Table S"]["is_module"] is False
    assert modules["Table S"]["file_counts"]["csv"] == 1


def test_match_findings_prefers_finding_key_over_description_similarity():
    base = {
        "id": "A-001",
        "severity": "CRITICAL",
        "dimension": "D6",
        "location": "1.2",
        "description": "threshold mismatch in DEG step",
        "evidence": "report says 0.5 but code uses 1",
        "rule": "R06",
        "source_type": "code",
        "source_path": "script/01_DEGs.r",
        "locator": "line 38",
        "quote_or_value": "logFC_cutoff=1",
    }
    agent_results = {
        "A": [dict(base)],
        "B": [{**base, "id": "B-003", "description": "same issue phrased differently"}],
        "C": [
            {
                **base,
                "id": "C-009",
                "rule": "R03",
                "locator": "line 120",
                "quote_or_value": "FDR=0.25",
                "description": "a different finding",
            }
        ],
    }

    groups = match_findings(agent_results)
    classified = classify_groups(groups, total_agents=3)

    assert len(classified["majority"]) == 1
    majority = classified["majority"][0]
    assert majority["agents"] == {"A", "B"}
    assert majority["match_mode"] == "exact"
    assert majority["finding_key"].startswith("fk:")
    assert len(classified["single"]) == 1




def _write_empty_slice_manifest(review_dir: Path) -> None:
    manifest_dir = review_dir / "agent_prompts"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        manifest_dir / "agent_slice_manifest.json",
        {"schema_version": "1.0", "execution_model": "small_slice_subagents_then_three_route_merge", "slices": []},
    )


def _build_review_case(tmp_path: Path) -> tuple[Path, Path, Path]:
    raw_root = tmp_path / "raw"
    pending_root = raw_root / "待审核" / "26YZF051F"
    project_dir = pending_root / "26YZF051F-数据分析报告"
    project_dir.mkdir(parents=True)
    (project_dir / "artifact.txt").write_text("done", encoding="utf-8")
    source_zip = raw_root / "待审核" / "26YZF051F.zip"
    source_zip.write_text("zip", encoding="utf-8")

    review_dir = tmp_path / "result_review_report" / "26YZF051F"
    review_dir.mkdir(parents=True)
    (review_dir / "final_review_report.md").write_text("# Report\n\nok\n", encoding="utf-8")
    binding = current_policy_binding()
    write_json(
        review_dir / "ai_execution_manifest.json",
        {
            "policy_version": binding["framework_version"],
            "policy_sha256": binding["policy_sha256"],
            "paths": {
                "project_dir": str(project_dir),
                "source_archive_path": str(source_zip),
            }
        },
    )
    return raw_root, project_dir, review_dir


def test_finalize_publication_gate_rejects_incomplete_visual_audit(tmp_path):
    _, _, review_dir = _build_review_case(tmp_path)
    write_json(
        review_dir / "audit_state.json",
        {
            "phases": [
                {"id": "precheck_ready", "status": "completed"},
                {
                    "id": "visual_audit_ready",
                    "status": "in_progress",
                    "closure": {"closure_passed": False, "would_block": True},
                },
                {"id": "archive_ready", "status": "blocked"},
            ],
            "visual_closure": {"closure_passed": False, "would_block": True},
        },
    )

    ready, errors = finalize_audit.publication_state_ready(review_dir)

    assert ready is False
    assert any("visual_audit_ready" in error for error in errors)
    assert any("closure_passed" in error for error in errors)


def test_finalize_publication_gate_accepts_noop_lint_remediation(tmp_path):
    _, _, review_dir = _build_review_case(tmp_path)
    write_json(
        review_dir / "audit_state.json",
        {
            "lint_passed": True,
            "phases": [
                {"id": "precheck_ready", "status": "completed"},
                {
                    "id": "visual_audit_ready",
                    "status": "completed",
                    "closure": {"closure_passed": True},
                },
                {"id": "agent_results_ready", "status": "completed"},
                {"id": "convergence_ready", "status": "completed"},
                {"id": "final_reports_ready", "status": "completed"},
                {"id": "final_report_validated", "status": "completed"},
                {"id": "autofix_plan_ready", "status": "blocked"},
                {"id": "autofix_applied", "status": "blocked"},
                {"id": "section_backfill_ready", "status": "blocked"},
                {"id": "section_backfill_applied", "status": "blocked"},
                {"id": "delivery_ready", "status": "completed"},
                {"id": "archive_ready", "status": "blocked"},
            ],
        },
    )

    ready, errors = finalize_audit.publication_state_ready(review_dir)

    assert ready is True
    assert errors == []


def test_ensure_review_html_does_not_move_project(tmp_path):
    raw_root, project_dir, review_dir = _build_review_case(tmp_path)
    (review_dir / "final_review_report.md").write_text(
        (
            "# 26YZF051F 正式审核报告\n\n"
            "## 一、审核结论\n\n结论：不合格。\n\n"
            "## 二、逐分析点审核结果\n\n"
            "| 分析点 | 审核判断 |\n|---|---|\n| A | 不通过 |\n\n"
            "## 三、提交阻断问题\n\n需整改。\n"
        ),
        encoding="utf-8",
    )
    write_json(
        review_dir / "project_structure.json",
        {
            "metadata": {},
            "modules": [
                {
                    "path": "data-only",
                    "file_counts": {
                        "total": 1,
                        "csv": 1,
                        "pdf": 0,
                        "images": 0,
                        "code": 0,
                    },
                }
            ],
            "code_files": [],
        },
    )

    status, message = ensure_one(review_dir, force=True)

    assert status == "generated", message
    assert project_dir.exists()
    assert not (raw_root / "已AI审核一次").exists()
    assert any(path.name.endswith("_audit_report.html") for path in review_dir.glob("*_audit_report.html"))


def test_archive_reviewed_project_requires_publish_success_and_explicit_approval(tmp_path, monkeypatch):
    raw_root, project_dir, review_dir = _build_review_case(tmp_path)
    monkeypatch.setattr(archive_reviewed_project_module, "validate_formal_archive_gates", lambda _review_dir: None)
    html_path = review_dir / "26YZF051F_audit_report.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    write_json(
        review_dir / "case_manifest.json",
        {
            "project_id": "26YZF051F",
            "publish_status": "pending",
            "archive_approved": False,
        },
    )

    with pytest.raises(RuntimeError, match="publish_status=success"):
        archive_reviewed_project(review_dir)

    write_json(
        review_dir / "case_manifest.json",
        {
            "project_id": "26YZF051F",
            "publish_status": "success",
            "archive_approved": False,
        },
    )
    with pytest.raises(RuntimeError, match="archive_approved=true"):
        archive_reviewed_project(review_dir)

    moved_to = archive_reviewed_project(review_dir, approve=True)
    updated_manifest = json.loads((review_dir / "case_manifest.json").read_text(encoding="utf-8"))

    assert moved_to.exists()
    assert not project_dir.exists()
    assert updated_manifest["archive_approved"] is True
    assert updated_manifest["archived_at"]
    assert not (raw_root / "待审核" / "26YZF051F.zip").exists()


def test_archive_reviewed_project_is_idempotent_when_already_archived(tmp_path, monkeypatch):
    raw_root, project_dir, review_dir = _build_review_case(tmp_path)
    monkeypatch.setattr(archive_reviewed_project_module, "validate_formal_archive_gates", lambda _review_dir: None)
    html_path = review_dir / "26YZF051F_audit_report.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    pending_root = raw_root / "待审核" / "26YZF051F"
    archived_root = raw_root / "已AI审核一次"
    archived_root.mkdir(parents=True)
    archived_project = archived_root / pending_root.name
    pending_root.rename(archived_project)
    (raw_root / "待审核" / "26YZF051F.zip").rename(archived_root / "26YZF051F.zip")
    write_json(
        review_dir / "case_manifest.json",
        {
            "project_id": "26YZF051F",
            "publish_status": "success",
            "archive_approved": True,
            "archived_at": "2026-04-21T00:00:00",
        },
    )

    moved_to = archive_reviewed_project(review_dir, approve=True)
    updated_manifest = json.loads((review_dir / "case_manifest.json").read_text(encoding="utf-8"))

    assert moved_to == archived_project
    assert archived_project.exists()
    assert not pending_root.exists()
    assert updated_manifest["archived_to"] == str(archived_project)


def test_finalize_audit_auto_archives_by_default(tmp_path, monkeypatch):
    _, _, review_dir = _build_review_case(tmp_path)
    html_path = review_dir / "26YZF051F_audit_report.html"
    write_policy_bound_case_manifest(
        review_dir,
        {
            "project_id": "26YZF051F",
            "publish_status": "pending",
            "archive_approved": False,
        },
    )

    calls: list[tuple[Path, bool]] = []

    def fake_run_step(target: Path, script_name: str) -> subprocess.CompletedProcess[str]:
        if script_name == "final_report_linter.py":
            (review_dir / "final_report_lint.json").write_text(
                json.dumps({"passed": True, "error_count": 0, "warning_count": 0}),
                encoding="utf-8",
            )
        if script_name == "ensure_review_html.py":
            html_path.write_text("<html></html>", encoding="utf-8")
        if script_name == "sync_audit_state.py":
            (review_dir / "audit_state.json").write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess([script_name], 0, stdout="", stderr="")

    def fake_archive(target: Path, *, approve: bool = False) -> Path:
        calls.append((target, approve))
        finalize_audit.update_case_manifest(
            target,
            {"archive_approved": True, "archived_at": "2026-04-21T00:00:00", "updated_at": "2026-04-21T00:00:00"},
        )
        archived_root = tmp_path / "archived" / "26YZF051F"
        archived_root.mkdir(parents=True, exist_ok=True)
        return archived_root

    def fake_send_notification(**_kwargs):
        return True, "notification sent via fake"

    configure_unsealed_finalize_flow(monkeypatch, review_dir)
    monkeypatch.setattr(finalize_audit, "run_step", fake_run_step)
    monkeypatch.setattr(finalize_audit, "archive_reviewed_project", fake_archive)
    monkeypatch.setattr(finalize_audit, "send_notification", fake_send_notification)
    monkeypatch.setattr(sys, "argv", ["finalize_audit.py", str(review_dir)])

    assert finalize_audit.main() == 0
    manifest = json.loads((review_dir / "case_manifest.json").read_text(encoding="utf-8"))

    assert calls == [(review_dir, True)]
    assert manifest["publish_status"] == "success"
    assert manifest["archive_approved"] is True
    assert manifest["archived_at"] == "2026-04-21T00:00:00"


def test_finalize_audit_sends_completion_notification(tmp_path, monkeypatch):
    _, _, review_dir = _build_review_case(tmp_path)
    html_path = review_dir / "26YZF051F_audit_report.html"
    write_policy_bound_case_manifest(
        review_dir,
        {
            "project_id": "26YZF051F",
            "publish_status": "pending",
            "archive_approved": False,
        },
    )

    events: list[str] = []
    notifications: list[tuple[str, str, bool, bool]] = []

    def fake_run_step(target: Path, script_name: str) -> subprocess.CompletedProcess[str]:
        if script_name == "final_report_linter.py":
            (review_dir / "final_report_lint.json").write_text(
                json.dumps({"passed": True, "error_count": 0, "warning_count": 0}),
                encoding="utf-8",
            )
        if script_name == "ensure_review_html.py":
            html_path.write_text("<html></html>", encoding="utf-8")
        if script_name == "sync_audit_state.py":
            (review_dir / "audit_state.json").write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess([script_name], 0, stdout="", stderr="")

    def fake_archive(target: Path, *, approve: bool = False) -> Path:
        events.append("archive")
        finalize_audit.update_case_manifest(
            target,
            {"archive_approved": True, "archived_at": "2026-04-21T00:00:00", "updated_at": "2026-04-21T00:00:00"},
        )
        archived_root = tmp_path / "archived" / "26YZF051F"
        archived_root.mkdir(parents=True, exist_ok=True)
        return archived_root

    def fake_send_notification(
        *,
        task_type: str,
        task_name: str,
        status: str,
        summary: str,
        metadata: dict,
        config_arg: str = "",
        allow_fallback: bool = True,
    ):
        events.append("notify")
        notifications.append((status, summary, metadata.get("formal_audit") == "true", allow_fallback))
        return True, "notification sent via fake"

    configure_unsealed_finalize_flow(monkeypatch, review_dir)
    monkeypatch.setattr(finalize_audit, "run_step", fake_run_step)
    monkeypatch.setattr(finalize_audit, "archive_reviewed_project", fake_archive)
    monkeypatch.setattr(finalize_audit, "send_notification", fake_send_notification)
    monkeypatch.setattr(sys, "argv", ["finalize_audit.py", str(review_dir), "--notification-channel", "wecom"])

    assert finalize_audit.main() == 0
    assert events == ["notify", "archive"]
    assert notifications == [("completed", "Audit finalize completed with HTML published; archive pending.", True, False)]
    receipt = json.loads((review_dir / "completion_notification_receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "sent"
    assert receipt["decision_sha256"] == ""
    assert receipt["channel"] == "wecom"


def test_finalize_audit_fails_when_html_is_missing_after_publish_step(tmp_path, monkeypatch):
    _, _, review_dir = _build_review_case(tmp_path)
    write_policy_bound_case_manifest(
        review_dir,
        {
            "project_id": "26YZF051F",
            "publish_status": "pending",
            "archive_approved": False,
        },
    )

    notifications: list[tuple[str, str]] = []

    def fake_run_step(target: Path, script_name: str) -> subprocess.CompletedProcess[str]:
        if script_name == "final_report_linter.py":
            (review_dir / "final_report_lint.json").write_text(
                json.dumps({"passed": True, "error_count": 0, "warning_count": 0}),
                encoding="utf-8",
            )
        if script_name == "sync_audit_state.py":
            (review_dir / "audit_state.json").write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess([script_name], 0, stdout="", stderr="")

    def fake_send_notification(*, task_type: str, task_name: str, status: str, summary: str, metadata: dict, config_arg: str = "", allow_fallback: bool = True):
        notifications.append((status, summary))
        return True, "notification sent via fake"

    configure_unsealed_finalize_flow(monkeypatch, review_dir)
    monkeypatch.setattr(finalize_audit, "run_step", fake_run_step)
    monkeypatch.setattr(finalize_audit, "send_notification", fake_send_notification)
    monkeypatch.setattr(sys, "argv", ["finalize_audit.py", str(review_dir)])

    assert finalize_audit.main() == 1
    assert notifications == [("failed", "Finalize failed: HTML report missing after publication step")]


def test_finalize_audit_rejects_no_auto_archive(tmp_path, monkeypatch):
    _, _, review_dir = _build_review_case(tmp_path)
    write_policy_bound_case_manifest(
        review_dir,
        {
            "project_id": "26YZF051F",
            "publish_status": "pending",
            "archive_approved": False,
        },
    )

    configure_unsealed_finalize_flow(monkeypatch, review_dir)
    monkeypatch.setattr(sys, "argv", ["finalize_audit.py", str(review_dir), "--no-auto-archive"])

    with pytest.raises(ValueError, match="no longer allowed"):
        finalize_audit.main()


def test_finalize_audit_continues_after_initial_lint_failures(tmp_path, monkeypatch):
    _, _, review_dir = _build_review_case(tmp_path)
    html_path = review_dir / "26YZF051F_audit_report.html"
    write_policy_bound_case_manifest(
        review_dir,
        {
            "project_id": "26YZF051F",
            "publish_status": "pending",
            "archive_approved": False,
        },
    )

    calls: list[str] = []
    lint_runs = 0

    def fake_run_step(target: Path, script_name: str) -> subprocess.CompletedProcess[str]:
        nonlocal lint_runs
        calls.append(script_name)
        if script_name == "final_report_linter.py":
            lint_runs += 1
            lint_payload = {
                1: {"passed": False, "error_count": 2, "warning_count": 0},
                2: {"passed": False, "error_count": 1, "warning_count": 0},
                3: {"passed": True, "error_count": 0, "warning_count": 0},
            }[lint_runs]
            (review_dir / "final_report_lint.json").write_text(json.dumps(lint_payload), encoding="utf-8")
            return subprocess.CompletedProcess([script_name], 0 if lint_payload["passed"] else 1, stdout="", stderr="")
        if script_name == "generate_lint_autofix_plan.py":
            (review_dir / "lint_autofix_plan.json").write_text("{}", encoding="utf-8")
        elif script_name == "apply_lint_autofix_plan.py":
            (review_dir / "lint_autofix_apply_report.json").write_text("{}", encoding="utf-8")
        elif script_name == "generate_required_section_backfill.py":
            (review_dir / "final_report_backfill_plan.json").write_text("{}", encoding="utf-8")
        elif script_name == "apply_required_section_backfill.py":
            (review_dir / "final_report_backfill_apply_report.json").write_text("{}", encoding="utf-8")
        elif script_name == "ensure_review_html.py":
            html_path.write_text("<html></html>", encoding="utf-8")
        elif script_name == "sync_audit_state.py":
            (review_dir / "audit_state.json").write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess([script_name], 0, stdout="", stderr="")

    def fake_send_notification(*, task_type: str, task_name: str, status: str, summary: str, metadata: dict, config_arg: str = "", allow_fallback: bool = True):
        return True, "notification sent via fake"

    configure_unsealed_finalize_flow(monkeypatch, review_dir)
    monkeypatch.setattr(finalize_audit, "run_step", fake_run_step)
    monkeypatch.setattr(finalize_audit, "send_notification", fake_send_notification)
    monkeypatch.setattr(sys, "argv", ["finalize_audit.py", str(review_dir)])

    assert finalize_audit.main() == 0
    manifest = json.loads((review_dir / "case_manifest.json").read_text(encoding="utf-8"))

    assert calls == [
        "check_subagent_supervision.py",
        "validate_professional_contracts.py",
        "final_report_linter.py",
        "generate_lint_autofix_plan.py",
        "apply_lint_autofix_plan.py",
        "final_report_linter.py",
        "generate_required_section_backfill.py",
        "apply_required_section_backfill.py",
        "final_report_linter.py",
        "sync_audit_state.py",
        "ensure_review_html.py",
        "sync_audit_state.py",
        "sync_audit_state.py",
    ]
    assert manifest["publish_status"] == "success"
    assert manifest["archive_approved"] is True


def test_audit_completed_notification_body_is_compact():
    body = build_body(
        "audit",
        "audit 26YZF040F",
        "completed",
        "Audit finalize completed and project archived.",
        {
            "workspace": "报告审核",
            "project_id": "26YZF040F",
            "review_dir": "result_review_report/26YZF040F",
            "html_report": "result_review_report/26YZF040F/26YZF040F_audit_report.html",
            "archived_to": "raw/已AI审核一次/26YZF040F-demo",
            "subagent_supervision_summary": "result_review_report/26YZF040F/subagent_supervision_summary.json",
            "project_display_name": "26YZF040F-demo",
            "report_file": "26YZF040F_audit_report.html",
            "audit_result": "不通过（45/100）",
            "issue_stats": "CRITICAL 3 / MAJOR 7 / WARNING 2",
        },
        {},
    )

    assert "任务类型" not in body
    assert "任务名称" not in body
    assert "摘要" not in body
    assert "workspace" not in body
    assert "review_dir" not in body
    assert "subagent_supervision" not in body
    assert "状态: completed" in body
    assert "项目号: 26YZF040F" in body
    assert "审核文件: 26YZF040F-demo" in body
    assert "报告文件: 26YZF040F_audit_report.html" in body
    assert "审核结果: 不通过（CRITICAL: 3 / MAJOR 7 / WARNING 2）" in body
    assert "问题统计" not in body


def test_extract_audit_notification_fields_from_final_report(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YZF040F"
    review_dir.mkdir(parents=True)
    html_path = review_dir / "26YZF040F_audit_report.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    (review_dir / "final_review_report.md").write_text(
        "\n".join(
            [
                "## 一、审核结论",
                "**AI裁定：不通过当前版，不建议作为正式可交付分析报告提交。**",
                "建议评分：**45/100**。",
                "严重度统计：CRITICAL 3；MAJOR 7；WARNING 2；INFO 0。",
            ]
        ),
        encoding="utf-8",
    )

    fields = finalize_audit.extract_audit_notification_fields(
        review_dir,
        html_path=html_path,
        archived_to=tmp_path / "raw" / "已AI审核一次" / "26YZF040F-demo",
    )

    assert fields["project_display_name"] == "26YZF040F-demo"
    assert fields["report_file"] == "26YZF040F_audit_report.html"
    assert fields["audit_result"] == "不通过（45/100）"
    assert fields["issue_stats"] == "CRITICAL: 3；MAJOR: 7；WARNING: 2"


def test_finalize_audit_fails_when_final_lint_still_fails(tmp_path, monkeypatch):
    _, _, review_dir = _build_review_case(tmp_path)
    write_policy_bound_case_manifest(
        review_dir,
        {
            "project_id": "26YZF051F",
            "publish_status": "pending",
            "archive_approved": False,
        },
    )

    calls: list[str] = []
    notifications: list[tuple[str, str]] = []

    def fake_run_step(target: Path, script_name: str) -> subprocess.CompletedProcess[str]:
        calls.append(script_name)
        if script_name == "final_report_linter.py":
            (review_dir / "final_report_lint.json").write_text(
                json.dumps({"passed": False, "error_count": 1, "warning_count": 0}),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess([script_name], 1, stdout="", stderr="")
        if script_name == "generate_lint_autofix_plan.py":
            (review_dir / "lint_autofix_plan.json").write_text("{}", encoding="utf-8")
        elif script_name == "apply_lint_autofix_plan.py":
            (review_dir / "lint_autofix_apply_report.json").write_text("{}", encoding="utf-8")
        elif script_name == "generate_required_section_backfill.py":
            (review_dir / "final_report_backfill_plan.json").write_text("{}", encoding="utf-8")
        elif script_name == "apply_required_section_backfill.py":
            (review_dir / "final_report_backfill_apply_report.json").write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess([script_name], 0, stdout="", stderr="")

    def fake_send_notification(*, task_type: str, task_name: str, status: str, summary: str, metadata: dict, config_arg: str = "", allow_fallback: bool = True):
        notifications.append((status, summary))
        return True, "notification sent via fake"

    configure_unsealed_finalize_flow(monkeypatch, review_dir)
    monkeypatch.setattr(finalize_audit, "run_step", fake_run_step)
    monkeypatch.setattr(finalize_audit, "send_notification", fake_send_notification)
    monkeypatch.setattr(sys, "argv", ["finalize_audit.py", str(review_dir)])

    assert finalize_audit.main() == 1
    manifest = json.loads((review_dir / "case_manifest.json").read_text(encoding="utf-8"))

    assert calls == [
        "check_subagent_supervision.py",
        "validate_professional_contracts.py",
        "final_report_linter.py",
        "generate_lint_autofix_plan.py",
        "apply_lint_autofix_plan.py",
        "final_report_linter.py",
        "generate_required_section_backfill.py",
        "apply_required_section_backfill.py",
        "final_report_linter.py",
    ]
    assert manifest["publish_status"] == "failed"
    assert notifications == [("failed", "Finalize failed: final report lint still failing after autofix/backfill")]


def test_build_checks_treats_current_lint_output_as_present(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    review_dir.mkdir(parents=True)
    for filename in [
        "case_manifest.json",
        "review_event_log.jsonl",
        "coverage_matrix.md",
        "fact_check_list.md",
        "unresolved_items.md",
        "convergence_report.json",
        "convergence_report.md",
        "arbitration_queue.json",
        "final_review_report.md",
        "audit_state.json",
    ]:
        (review_dir / filename).write_text("ok", encoding="utf-8")

    from policy_loader import load_policy

    report_text = "审核结论\n逐分析点审核结果\n三路\n收敛\n机械\n处置\n高风险模块\n位置：a\n证据：b\n"
    checks = build_checks(review_dir, report_text, load_policy())
    lint_check = next(item for item in checks if item["id"] == "file:final_report_lint.json")
    assert lint_check["passed"] is True


def test_build_checks_blocks_unmapped_analysis_rows(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    review_dir.mkdir(parents=True)
    for filename in [
        "case_manifest.json",
        "review_event_log.jsonl",
        "coverage_matrix.md",
        "fact_check_list.md",
        "unresolved_items.md",
        "convergence_report.json",
        "convergence_report.md",
        "arbitration_queue.json",
        "final_review_report.md",
        "audit_state.json",
    ]:
        (review_dir / filename).write_text("ok", encoding="utf-8")

    from policy_loader import load_policy

    report_text = (
        "审核结论\n逐分析点审核结果\n三路\n收敛\n机械\n处置\n高风险模块\n位置：a\n证据：b\n"
        "| 分析点 | 证据充分性 | 结论 |\n"
        "|---|---|---|\n"
        "| 图件交付格式 | 部分充分 | 仅有PNG，缺少PDF |\n\n"
        "## 主要问题清单\n\n"
        "### F-10 结果图缺少PDF交付\n\n"
        "严重度: WARNING\n"
    )
    checks = build_checks(review_dir, report_text, load_policy())
    consistency = {item["id"]: item for item in checks if item["id"].startswith("consistency:")}

    assert consistency["consistency:analysis_rows_mapped"]["passed"] is False
    assert consistency["consistency:issues_mapped"]["passed"] is False


def test_build_checks_passes_explicit_analysis_issue_mapping(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    review_dir.mkdir(parents=True)
    for filename in [
        "case_manifest.json",
        "review_event_log.jsonl",
        "coverage_matrix.md",
        "fact_check_list.md",
        "unresolved_items.md",
        "convergence_report.json",
        "convergence_report.md",
        "arbitration_queue.json",
        "final_review_report.md",
        "audit_state.json",
    ]:
        (review_dir / filename).write_text("ok", encoding="utf-8")

    from policy_loader import load_policy

    report_text = (
        "审核结论\n逐分析点审核结果\n三路\n收敛\n机械\n处置\n高风险模块\n位置：a\n证据：b\n"
        "| 分析点 | 证据充分性 | 对应问题 | 结论 |\n"
        "|---|---|---|---|\n"
        "| 图件交付格式 | 部分充分 | F-10 | 仅有PNG，缺少PDF |\n\n"
        "## 主要问题清单\n\n"
        "### F-10 结果图缺少PDF交付\n\n"
        "严重度: WARNING\n"
    )
    checks = build_checks(review_dir, report_text, load_policy())
    consistency = {item["id"]: item for item in checks if item["id"].startswith("consistency:")}

    assert consistency["consistency:analysis_rows_mapped"]["passed"] is True
    assert consistency["consistency:issues_mapped"]["passed"] is True


def test_build_checks_blocks_reject_verdict_with_zero_issue_counts(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    review_dir.mkdir(parents=True)
    for filename in [
        "case_manifest.json",
        "review_event_log.jsonl",
        "coverage_matrix.md",
        "fact_check_list.md",
        "unresolved_items.md",
        "convergence_report.json",
        "convergence_report.md",
        "arbitration_queue.json",
        "final_review_report.md",
        "audit_state.json",
    ]:
        (review_dir / filename).write_text("ok", encoding="utf-8")

    from policy_loader import load_policy

    report_text = (
        "审核结论\n"
        "AI复核结论：不合格，不建议提交。\n"
        "逐分析点审核结果\n三路\n收敛\n机械\n处置\n高风险模块\n"
        "位置: report_text.txt L1\n"
        "证据: 报告明确需要退回。\n"
    )
    checks = build_checks(review_dir, report_text, load_policy())
    severity_checks = {item["id"]: item for item in checks if item["id"].startswith("severity:")}

    assert severity_checks["severity:reject_verdict_has_issue_counts"]["passed"] is False




def test_slice_manifest_declares_model_quality_gate(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"

    manifest = build_slice_manifest(review_dir)

    assert manifest["model_quality"]["formal_judgement_slices_require"] == "same_model_as_lead_agent_required"
    assert "severity_judgement" in manifest["model_quality"]["must_not_downshift_for"]
    assert manifest["model_quality"]["lead_global_review_required"] is True


def test_slice_prompt_states_small_slice_does_not_mean_weak_model(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    spec = SLICE_SPECS[0]

    prompt = build_slice_prompt(spec, review_dir, None, {}, "report excerpt")

    assert "小切片只用于控制上下文" in prompt
    assert "正式判断型 Sub-Agent 必须使用与主 agent 相同的模型" in prompt
    assert "fast/mini 模型只可用于文件定位" in prompt
    assert "触发 remote compact/context loss" in prompt
    assert "聊天最多返回 5 行" in prompt
    assert "不要贴完整报告、完整 JSON、长日志、大表或内部归档路径" in prompt
    assert "Lead 必须再做全局一致性复核" in prompt


def test_validate_slice_outputs_blocks_missing_slice_json(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    manifest_dir = review_dir / "agent_prompts"
    manifest_dir.mkdir(parents=True)
    write_json(
        manifest_dir / "agent_slice_manifest.json",
        {
            "slices": [
                {
                    "id": "a01",
                    "agent": "A",
                    "result_file": str(review_dir / "agent_results" / "slices" / "agent_a_a01_result.json"),
                }
            ]
        },
    )

    errors = validate_slice_outputs(review_dir)

    assert errors
    assert "missing slice result" in errors[0]


def test_validate_slice_outputs_accepts_completed_slice_json(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    manifest_dir = review_dir / "agent_prompts"
    result_dir = review_dir / "agent_results" / "slices"
    manifest_dir.mkdir(parents=True)
    result_dir.mkdir(parents=True)
    result_path = result_dir / "agent_a_a01_result.json"
    write_json(
        result_path,
        {
            "slice_id": "a01",
            "agent": "A",
            "status": "completed",
            "findings": [],
            "summary": {"total_findings": 0},
        },
    )
    write_json(
        manifest_dir / "agent_slice_manifest.json",
        {
            "slices": [
                {
                    "id": "a01",
                    "agent": "A",
                    "result_file": str(result_path),
                }
            ]
        },
    )

    assert validate_slice_outputs(review_dir) == []


def test_normalize_local_target_handles_windows_markdown_drive_prefix():
    assert _normalize_local_target("/D:/IKL/BaiduSyncdisk/report/file.md:12") == "D:/IKL/BaiduSyncdisk/report/file.md"


def test_visual_audit_phase_not_complete_while_todo_placeholders_remain(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    review_dir.mkdir(parents=True)
    for name in [
        "report_text.txt",
        "report_structure.json",
        "project_structure.json",
        "mechanical_check_result.json",
        "case_manifest.json",
        "ai_execution_manifest.json",
    ]:
        (review_dir / name).write_text("{}", encoding="utf-8")
    (review_dir / "figure_audit.md").write_text("# Figure Audit\n\n- Finding: TODO\n", encoding="utf-8")

    state = build_state(review_dir)
    visual = next(item for item in state["phases"] if item["id"] == "visual_audit_ready")

    assert visual["status"] == "in_progress"
    assert any("TODO" in item for item in visual["missing_outputs"])


def test_sync_audit_state_advances_to_autofix_when_lint_exists_but_failed(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB010F"
    agent_results = review_dir / "agent_results"
    agent_results.mkdir(parents=True)
    _write_empty_slice_manifest(review_dir)
    for name in [
        "report_text.txt",
        "report_structure.json",
        "project_structure.json",
        "mechanical_check_result.json",
        "case_manifest.json",
        "ai_execution_manifest.json",
        "figure_audit.md",
        "convergence_report.json",
        "convergence_report.md",
        "coverage_matrix.md",
        "fact_check_list.md",
        "unresolved_items.md",
        "final_review_report.md",
    ]:
        (review_dir / name).write_text("{}", encoding="utf-8")
    for name in ["agent_a_result.json", "agent_b_result.json", "agent_c_result.json"]:
        (agent_results / name).write_text("{}", encoding="utf-8")
    (review_dir / "case_manifest.json").write_text(
        json.dumps({"project_id": "26YHB010F", "publish_status": "pending", "archive_approved": False}),
        encoding="utf-8",
    )
    (review_dir / "final_report_lint.json").write_text(
        json.dumps({"passed": False, "error_count": 2, "warning_count": 0}),
        encoding="utf-8",
    )
    prepare_visual_audit(review_dir, review_lane="strict")

    state = build_state(review_dir)
    lint_phase = next(item for item in state["phases"] if item["id"] == "final_report_validated")
    autofix_phase = next(item for item in state["phases"] if item["id"] == "autofix_plan_ready")

    assert lint_phase["status"] == "completed"
    assert state["current_phase"] == "autofix_plan_ready"
    assert autofix_phase["status"] == "in_progress"
    assert state["lint_passed"] is False


def test_sync_audit_state_requires_archive_when_auto_archive_policy_is_enabled(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB010F"
    agent_results = review_dir / "agent_results"
    agent_results.mkdir(parents=True)
    _write_empty_slice_manifest(review_dir)
    for name in [
        "report_text.txt",
        "report_structure.json",
        "project_structure.json",
        "mechanical_check_result.json",
        "case_manifest.json",
        "ai_execution_manifest.json",
        "figure_audit.md",
        "convergence_report.json",
        "convergence_report.md",
        "coverage_matrix.md",
        "fact_check_list.md",
        "unresolved_items.md",
        "final_review_report.md",
        "lint_autofix_plan.json",
        "lint_autofix_apply_report.json",
        "final_report_backfill_plan.json",
        "final_report_backfill_apply_report.json",
        "26YHB010F_audit_report.html",
    ]:
        (review_dir / name).write_text("{}", encoding="utf-8")
    for name in ["agent_a_result.json", "agent_b_result.json", "agent_c_result.json"]:
        (agent_results / name).write_text("{}", encoding="utf-8")
    write_json(
        review_dir / "case_manifest.json",
        {
            "project_id": "26YHB010F",
            "publish_status": "success",
            "archive_approved": False,
            "archived_at": "",
        },
    )
    write_json(review_dir / "final_report_lint.json", {"passed": True, "error_count": 0, "warning_count": 0})
    prepare_visual_audit(review_dir, review_lane="strict")

    state = build_state(review_dir)
    archive_phase = next(item for item in state["phases"] if item["id"] == "archive_ready")

    assert state["auto_archive_required"] is True
    assert state["all_completed"] is False
    assert state["current_phase"] == "archive_ready"
    assert archive_phase["status"] == "in_progress"
    assert archive_phase["missing_outputs"] == ["auto archive is required but archived_at is empty"]


def test_auto_audit_pipeline_does_not_treat_generic_single_cell_phrase_as_cancer(tmp_path):
    project_dir = tmp_path / "26YBB019F-感染+免疫基因+转录组+单细胞联合分析"
    project_dir.mkdir()

    pipeline = AutoAuditPipeline(str(project_dir))

    assert pipeline.project_type != "癌症"


def test_visual_audit_standard_lane_uses_machine_prefilter_and_high_risk_rules(tmp_path, monkeypatch):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    images_dir = review_dir / "images"
    images_dir.mkdir(parents=True)
    write_json(review_dir / "case_manifest.json", {"project_id": "26YHB001F"})
    write_json(review_dir / "report_structure.json", {"sections": [{"id": "1", "title": "Results", "line": 1}]})
    (review_dir / "report_text.txt").write_text(
        "\n".join(
            [
                "1 Results",
                "Figure 1 workflow",
                "[IMAGE: image_1.png]",
                "Figure 2 volcano",
                "[IMAGE: image_2.png]",
                "Figure 3 single cell umap",
                "[IMAGE: image_3.png]",
            ]
        ),
        encoding="utf-8",
    )
    payload = b"same-image-payload" * 200
    (images_dir / "image_1.png").write_bytes(payload)
    (images_dir / "image_2.png").write_bytes(payload)
    (images_dir / "image_3.png").write_bytes(b"single-cell" * 300)

    monkeypatch.setattr("visual_audit.extract_image_text", lambda path: "26ZZZ999F" if path.name == "image_2.png" else "")
    monkeypatch.setattr("visual_audit.predict_visual_family", lambda path: "text_page" if path.name == "image_2.png" else "chart_like")

    result = prepare_visual_audit(review_dir, review_lane="standard")
    checklist = json.loads((review_dir / "visual_audit_checklist.json").read_text(encoding="utf-8"))
    prefilter = json.loads((review_dir / "visual_prefilter.json").read_text(encoding="utf-8"))

    item1 = next(item for item in checklist if item["filename"] == "image_1.png")
    item2 = next(item for item in checklist if item["filename"] == "image_2.png")
    item3 = next(item for item in checklist if item["filename"] == "image_3.png")

    assert prefilter["summary"]["duplicate_image"] == 1
    assert prefilter["summary"]["project_id_mismatch"] == 1
    assert prefilter["summary"]["obvious_wrong_figure"] == 1
    assert item1["needs_audit"] is False
    assert item2["needs_audit"] is True
    assert item3["needs_audit"] is True
    assert result["machine_prefilter_summary"]["flagged_images"] >= 1


def test_visual_audit_font_style_mismatch_flag_forces_review_in_standard_lane(tmp_path, monkeypatch):
    review_dir = tmp_path / "result_review_report" / "26YHB002F"
    images_dir = review_dir / "images"
    images_dir.mkdir(parents=True)
    write_json(review_dir / "case_manifest.json", {"project_id": "26YHB002F"})
    write_json(review_dir / "report_structure.json", {"sections": [{"id": "1", "title": "Results", "line": 1}]})
    (review_dir / "report_text.txt").write_text(
        "\n".join(
            [
                "1 Results",
                "Figure 1 volcano",
                "[IMAGE: image_1.png]",
                "Figure 2 volcano",
                "[IMAGE: image_2.png]",
            ]
        ),
        encoding="utf-8",
    )
    (images_dir / "image_1.png").write_bytes(b"font-mismatch" * 300)
    (images_dir / "image_2.png").write_bytes(b"plain-chart" * 300)

    monkeypatch.setattr("visual_audit.extract_image_text", lambda path: "")
    monkeypatch.setattr("visual_audit.predict_visual_family", lambda path: "chart_like")
    monkeypatch.setattr(
        "visual_audit.detect_font_style_mismatch",
        lambda path: {"detected": path.name == "image_1.png", "clusters": [3, 2], "reason": "multiple_font_style_clusters"},
    )

    result = prepare_visual_audit(review_dir, review_lane="standard")
    checklist = json.loads((review_dir / "visual_audit_checklist.json").read_text(encoding="utf-8"))
    prefilter = json.loads((review_dir / "visual_prefilter.json").read_text(encoding="utf-8"))

    item1 = next(item for item in checklist if item["filename"] == "image_1.png")
    item2 = next(item for item in checklist if item["filename"] == "image_2.png")

    assert prefilter["summary"]["font_style_mismatch"] == 1
    assert any(flag["type"] == "font_style_mismatch" for flag in item1["machine_flags"])
    assert item1["needs_audit"] is True
    assert item2["needs_audit"] is False
    assert result["machine_prefilter_summary"]["font_style_mismatch"] == 1


def test_generated_docs_match_committed_files():
    assert write_documents(check_only=True) == []


def test_lesson_bank_policy_is_required_and_generated_docs_surface_it():
    from generate_policy_docs import build_ai_index, build_quick_reference, build_quickstart, build_readme
    from policy_loader import load_policy

    policy = load_policy()
    lesson_policy = policy["lesson_bank_policy"]

    assert policy["default_execution"]["must_read_lesson_bank_before_audit"] is True
    assert policy["default_execution"]["must_update_lesson_bank_after_audit"] is True
    assert lesson_policy["canonical_dir"] == "lessons/"
    assert "LESSONS_LEARNED.md" in lesson_policy["read_before_audit"]
    for field in [
        "错误类型",
        "具体表现",
        "触发场景",
        "证据依据",
        "正确标准",
        "下次审核提醒",
        "严重程度",
        "规则建议",
    ]:
        assert field in lesson_policy["required_entry_fields"]
    assert lesson_policy["rule_suggestion_policy"]["apply_when_actionable"] is True
    assert policy["code_delivery_policy"]["standalone_no_code_severity"] == "WARNING"
    compact_policy = policy["subagent_compact_policy"]
    assert compact_policy["subagent_chat_return_budget"]["max_lines"] == 5
    assert compact_policy["leader_final_reply_budget"]["max_lines"] == 8
    assert "full_notification_metadata" in compact_policy["subagent_chat_return_budget"]["must_not_include"]
    assert "workspace" in compact_policy["leader_final_reply_budget"]["must_not_include"]

    generated_docs = "\n".join(
        [
            build_readme(policy),
            build_ai_index(policy),
            build_quickstart(policy),
            build_quick_reference(policy),
        ]
    )
    assert "错题集闭环" in generated_docs
    assert "规则建议" in generated_docs
    assert "重点复核" in generated_docs
    assert "不能机械套用" in generated_docs
    assert "代码交付严重度口径" in generated_docs
    assert "聊天回传最多 5 行" in generated_docs
    assert "最终回复最多 8 行" in generated_docs
