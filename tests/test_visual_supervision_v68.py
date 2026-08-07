#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Local-only regression coverage for the v7.0 visual and supervision contracts."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path

from audit_runtime import append_event, build_case_manifest
from check_subagent_supervision import validate_summary
from policy_loader import load_policy
from sync_audit_state import policy_requires_auto_archive, visual_audit_closure_status
from visual_audit import default_review_lane, prepare_visual_audit, validate_visual_audit_result


def _complete_visual_result(result: dict) -> dict:
    result = copy.deepcopy(result)
    result["status"] = "completed"
    for asset in result["assets"]:
        if asset["format_status"] == "supported":
            asset["outcome"] = "reviewed"
            asset["reason"] = ""
            asset["review"] = {
                "status": "completed",
                "reviewer": "visual-agent",
                "completed_at": "2026-07-22T10:10:00",
                "conclusion": "Figure and project context are consistent.",
            }
        else:
            asset["derivative_evidence"].update(
                {
                    "review_status": "completed",
                    "reviewed_by": "visual-agent",
                    "reviewed_at": "2026-07-22T10:10:00",
                }
            )
    result["asset_counts"] = {
        "asset_total": len(result["assets"]),
        "reviewed": sum(item["outcome"] == "reviewed" for item in result["assets"]),
        "skipped": sum(item["outcome"] == "skipped" for item in result["assets"]),
        "unsupported": sum(item["outcome"] == "unsupported" for item in result["assets"]),
        "unaccounted": 0,
    }
    result["passed"] = True
    result["validation_errors"] = []
    return result


def test_policy_default_visual_lane_is_strict():
    assert default_review_lane() == "strict"


def _prepare_high_risk_visual(tmp_path: Path, monkeypatch) -> tuple[Path, dict]:
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    images_dir = review_dir / "images"
    images_dir.mkdir(parents=True)
    (review_dir / "case_manifest.json").write_text(
        json.dumps({"project_id": "26YHB001F"}), encoding="utf-8"
    )
    (review_dir / "report_text.txt").write_text(
        "Figure 1 ROC\n[IMAGE: roc_plot.png]\n", encoding="utf-8"
    )
    (images_dir / "roc_plot.png").write_bytes(b"rendered-roc" * 300)
    (images_dir / "roc_plot.emf").write_bytes(b"source-emf" * 100)
    monkeypatch.setattr("visual_audit.extract_image_text", lambda _path: "")
    monkeypatch.setattr("visual_audit.predict_visual_family", lambda _path: "chart_like")
    monkeypatch.setattr(
        "visual_audit.detect_font_style_mismatch",
        lambda _path: {"detected": False, "reason": "test"},
    )
    prepare_visual_audit(review_dir, review_lane="standard")
    result = json.loads((review_dir / "visual_audit_result.json").read_text(encoding="utf-8"))
    return review_dir, result


def test_case_manifest_uses_contract_versions_and_event_task_fields(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    project_dir = tmp_path / "raw" / "26YHB001F"
    review_dir.mkdir(parents=True)
    project_dir.mkdir(parents=True)
    manifest = build_case_manifest(
        review_dir=review_dir,
        project_dir=project_dir,
        report_structure={"metadata": {}},
        project_structure={"metadata": {"project_id": "26YHB001F"}},
    )

    assert manifest["schema_version"] == "1.1"
    assert manifest["framework_version"] == "v7.1"
    assert manifest["review_lane"] == "strict"
    assert manifest["audit_contract_version"] == "1.0"
    assert manifest["paths"]["visual_audit_result"].endswith("visual_audit_result.json")
    assert manifest["paths"]["final_decision"].endswith("final_decision.json")
    assert manifest["paths"]["audit_contract_validation"].endswith(
        "audit_contract_validation.json"
    )
    assert manifest["paths"]["completion_notification_receipt"].endswith(
        "completion_notification_receipt.json"
    )
    assert manifest["paths"]["professional_dataset_scope"].endswith(
        "dataset_scope_matrix.json"
    )

    append_event(
        review_dir,
        "subagent_dispatched",
        actor="leader",
        task_id="a01",
        attempt=2,
        phase="route_a",
        agent="agent-a",
    )
    event = json.loads((review_dir / "review_event_log.jsonl").read_text(encoding="utf-8"))
    assert (event["task_id"], event["attempt"], event["phase"], event["agent"]) == (
        "a01",
        2,
        "route_a",
        "agent-a",
    )


def test_visual_closure_conserves_assets_and_requires_high_risk_derivative(tmp_path, monkeypatch):
    review_dir, prepared = _prepare_high_risk_visual(tmp_path, monkeypatch)

    initial = validate_visual_audit_result(review_dir, prepared)
    assert initial["passed"] is False
    assert initial["asset_counts"] == {
        "asset_total": 2,
        "reviewed": 0,
        "skipped": 0,
        "unsupported": 1,
        "unaccounted": 1,
    }

    waived_only = copy.deepcopy(prepared)
    unsupported = next(item for item in waived_only["assets"] if item["format_status"] == "unsupported")
    unsupported["waiver"] = {
        "reason": "cannot render",
        "approved_by": "leader",
        "approved_at": "2026-07-22T10:00:00",
    }
    waived_validation = validate_visual_audit_result(review_dir, waived_only)
    assert any(error["id"] == "visual_closure:high_risk_derivative" for error in waived_validation["errors"])

    completed = _complete_visual_result(prepared)
    validation = validate_visual_audit_result(review_dir, completed)
    assert validation["passed"] is True
    assert validation["conservation_passed"] is True

    (review_dir / "images" / "roc_plot.png").write_bytes(b"changed-render")
    stale = validate_visual_audit_result(review_dir, completed)
    assert stale["passed"] is False
    assert {error["id"] for error in stale["errors"]} >= {
        "visual_closure:source_hash",
        "visual_closure:high_risk_derivative",
    }


def test_low_risk_unsupported_asset_accepts_explicit_waiver(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    images_dir = review_dir / "images"
    images_dir.mkdir(parents=True)
    (review_dir / "case_manifest.json").write_text(
        json.dumps({"project_id": "26YHB001F"}), encoding="utf-8"
    )
    (images_dir / "decorative_logo.emf").write_bytes(b"logo-emf")
    prepare_visual_audit(review_dir, review_lane="standard")
    result = json.loads((review_dir / "visual_audit_result.json").read_text(encoding="utf-8"))
    result["status"] = "completed"
    result["asset_counts"] = {
        "asset_total": 1,
        "reviewed": 0,
        "skipped": 0,
        "unsupported": 1,
        "unaccounted": 0,
    }
    result["assets"][0]["waiver"] = {
        "reason": "Decorative logo has no analytical content.",
        "approved_by": "leader",
        "approved_at": "2026-07-22T10:00:00",
    }

    assert validate_visual_audit_result(review_dir, result)["passed"] is True


def test_strict_visual_inventory_includes_generic_delivery_figure(tmp_path, monkeypatch):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    project_dir = tmp_path / "raw" / "26YHB001F"
    review_dir.mkdir(parents=True)
    project_dir.mkdir(parents=True)
    (review_dir / "case_manifest.json").write_text(
        json.dumps({"project_id": "26YHB001F", "project_dir": str(project_dir)}),
        encoding="utf-8",
    )
    (review_dir / "project_structure.json").write_text(
        json.dumps(
            {
                "metadata": {"project_dir": str(project_dir)},
                "image_files": [
                    {"path": "result/plot_001.png"},
                    {"path": "result/plot_002.pdf"},
                    {"path": "result/plot_003.svg"},
                ],
            }
        ),
        encoding="utf-8",
    )
    generic_figure = project_dir / "result" / "plot_001.png"
    generic_figure.parent.mkdir()
    generic_figure.write_bytes(b"generic-analysis-figure" * 300)
    (project_dir / "result" / "plot_002.pdf").write_bytes(b"%PDF-1.4\n" + b"generic-pdf-figure" * 300)
    (project_dir / "result" / "plot_003.svg").write_text("<svg></svg>", encoding="utf-8")
    monkeypatch.setattr("visual_audit.extract_image_text", lambda _path: "")
    monkeypatch.setattr("visual_audit.predict_visual_family", lambda _path: "chart_like")
    monkeypatch.setattr(
        "visual_audit.detect_font_style_mismatch",
        lambda _path: {"detected": False, "reason": "test"},
    )

    prepared = prepare_visual_audit(review_dir, review_lane="strict")
    result = json.loads((review_dir / "visual_audit_result.json").read_text(encoding="utf-8"))

    assert prepared["total_images"] == 3
    by_filename = {item["filename"]: item for item in result["assets"]}
    assert set(by_filename) == {"plot_001.png", "plot_002.pdf", "plot_003.svg"}
    assert all(item["origin"] == "project_delivery_figures" for item in by_filename.values())
    assert all(item["guessed_type"] == "unknown" for item in by_filename.values())
    assert all(item["needs_audit"] is True for item in by_filename.values())
    assert all(item["outcome"] == "pending" for item in by_filename.values())
    assert by_filename["plot_002.pdf"]["format_status"] == "supported"
    assert by_filename["plot_003.svg"]["format_status"] == "supported"

    result["status"] = "completed"
    for item in result["assets"]:
        item["outcome"] = "skipped"
        item["reason"] = "not selected"
    result["asset_counts"] = {
        "asset_total": 3,
        "reviewed": 0,
        "skipped": 3,
        "unsupported": 0,
        "unaccounted": 0,
    }
    validation = validate_visual_audit_result(review_dir, result)
    assert validation["passed"] is False
    assert {error["id"] for error in validation["errors"]} >= {"visual_closure:strict_skip"}


def test_visual_closure_resolves_project_after_archive(tmp_path, monkeypatch):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    pending_root = tmp_path / "raw" / "待审核" / "26YHB001F"
    project_dir = pending_root / "delivery"
    archived_root = tmp_path / "raw" / "已AI审核一次" / "26YHB001F"
    figure = project_dir / "result" / "plot.png"
    review_dir.mkdir(parents=True)
    figure.parent.mkdir(parents=True)
    figure.write_bytes(b"archived-visual" * 300)
    (review_dir / "case_manifest.json").write_text(
        json.dumps(
            {
                "project_id": review_dir.name,
                "project_dir": str(project_dir),
                "archived_to": str(archived_root),
            }
        ),
        encoding="utf-8",
    )
    (review_dir / "project_structure.json").write_text(
        json.dumps({"metadata": {"project_dir": str(project_dir)}, "image_files": [{"path": "result/plot.png"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr("visual_audit.extract_image_text", lambda _path: "")
    monkeypatch.setattr("visual_audit.predict_visual_family", lambda _path: "chart_like")
    monkeypatch.setattr(
        "visual_audit.detect_font_style_mismatch",
        lambda _path: {"detected": False, "reason": "test"},
    )

    prepare_visual_audit(review_dir, review_lane="strict")
    prepared = json.loads((review_dir / "visual_audit_result.json").read_text(encoding="utf-8"))
    completed = _complete_visual_result(prepared)
    archived_root.parent.mkdir(parents=True)
    pending_root.rename(archived_root)

    validation = validate_visual_audit_result(review_dir, completed)
    assert validation["passed"] is True


def test_prepare_visual_audit_rejects_project_structure_path_escape(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    project_dir = tmp_path / "raw" / "26YHB001F"
    review_dir.mkdir(parents=True)
    project_dir.mkdir(parents=True)
    outside_figure = project_dir.parent / "outside.pdf"
    outside_figure.write_bytes(b"%PDF-1.4\n")
    (review_dir / "project_structure.json").write_text(
        json.dumps(
            {
                "metadata": {"project_dir": str(project_dir)},
                "image_files": [{"path": "../outside.pdf"}],
            }
        ),
        encoding="utf-8",
    )

    try:
        prepare_visual_audit(review_dir, review_lane="strict")
    except ValueError as exc:
        assert "escapes project directory" in str(exc)
    else:
        raise AssertionError("project_structure path escape was accepted")
    assert not (review_dir / "visual_audit_result.json").exists()


def test_validate_visual_audit_result_rejects_absolute_project_structure_path(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    project_dir = tmp_path / "raw" / "26YHB001F"
    review_dir.mkdir(parents=True)
    project_dir.mkdir(parents=True)
    outside_figure = tmp_path / "outside.pdf"
    outside_figure.write_bytes(b"%PDF-1.4\n")
    (review_dir / "project_structure.json").write_text(
        json.dumps(
            {
                "metadata": {"project_dir": str(project_dir)},
                "image_files": [{"path": str(outside_figure)}],
            }
        ),
        encoding="utf-8",
    )

    try:
        validate_visual_audit_result(review_dir, {})
    except ValueError as exc:
        assert "must be relative" in str(exc)
    else:
        raise AssertionError("absolute project_structure path was accepted")


def test_visual_state_enforces_incomplete_visual_review_by_default(tmp_path, monkeypatch):
    review_dir, _prepared = _prepare_high_risk_visual(tmp_path, monkeypatch)
    (review_dir / "figure_audit.md").write_text("# completed visual review\n", encoding="utf-8")

    enforce_complete, missing, enforce = visual_audit_closure_status(review_dir)
    assert enforce_complete is False
    assert missing
    assert enforce["mode"] == "enforce"
    assert enforce["would_block"] is True
    assert enforce["closure_passed"] is False


def test_auto_archive_requirement_fails_closed_when_policy_field_missing(monkeypatch):
    monkeypatch.setattr("sync_audit_state.load_policy", lambda: {})
    assert policy_requires_auto_archive() is True

    monkeypatch.setattr(
        "sync_audit_state.load_policy",
        lambda: {
            "publish_archive_policy": {"auto_archive_after_finalize": False},
            "default_execution": {"must_auto_archive_after_finalize": True},
        },
    )
    assert policy_requires_auto_archive() is True


def _supervision_summary(review_dir: Path) -> dict:
    completed = []
    for task_id in ("a01", "b01", "c01"):
        artifact = review_dir / f"{task_id}.json"
        artifact.write_text("{}", encoding="utf-8")
        completed.append(
            {
                "slice_id": task_id,
                "status": "completed",
                "artifact_path": artifact.name,
            }
        )
    return {
        "schema_version": "1.1",
        "project_id": "26YHB001F",
        "generated_at": "2026-07-22T10:00:00",
        "status": "completed",
        "passed": True,
        "leader_role": "supervisor",
        "subagent_strategy": {
            "max_subagent_minutes": 30,
            "recursive_subagents_allowed": False,
            "timeout_policy": "poll, split, and redispatch",
        },
        "max_subagent_minutes": 30,
        "recursive_subagents_allowed": False,
        "completed_subagents": completed,
        "redispatched_subagents": [],
        "failed_or_skipped_subagents": [],
        "unresolved_items": [],
        "notification_status": "not_sent",
    }


def _task_events(duration_seconds: int = 600) -> list[dict]:
    start = datetime(2026, 7, 22, 10, 0, 0)
    events = []
    for index, task_id in enumerate(("a01", "b01", "c01")):
        dispatched = start + timedelta(minutes=index)
        common = {"task_id": task_id, "phase": "audit", "agent": f"agent-{task_id}", "attempt": 1}
        events.extend(
            [
                {**common, "timestamp": dispatched.isoformat(), "event_type": "subagent_dispatched"},
                {
                    **common,
                    "timestamp": (dispatched + timedelta(seconds=60)).isoformat(),
                    "event_type": "subagent_polled",
                },
                {
                    **common,
                    "timestamp": (dispatched + timedelta(seconds=duration_seconds)).isoformat(),
                    "event_type": "subagent_completed",
                },
            ]
        )
    return events


def test_supervision_enforce_uses_real_order_duration_and_artifacts(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    review_dir.mkdir(parents=True)
    summary = _supervision_summary(review_dir)
    policy = copy.deepcopy(load_policy())
    policy["subagent_supervision_policy"]["event_validation_mode"] = "enforce"

    passed, checks = validate_summary(summary, policy, review_dir, events=_task_events())
    assert passed is True
    assert next(check for check in checks if check["id"] == "subagent_supervision:timing_coverage")["passed"]

    timed_out, timeout_checks = validate_summary(
        summary, policy, review_dir, events=_task_events(duration_seconds=1801)
    )
    assert timed_out is False
    assert not next(
        check for check in timeout_checks if check["id"] == "subagent_supervision:event_lifecycle"
    )["passed"]

    out_of_order_events = _task_events()
    out_of_order_events[1]["timestamp"] = "2026-07-22T09:59:59"
    out_of_order, order_checks = validate_summary(
        summary, policy, review_dir, events=out_of_order_events
    )
    assert out_of_order is False
    assert not next(
        check for check in order_checks if check["id"] == "subagent_supervision:event_lifecycle"
    )["passed"]

    (review_dir / "b01.json").unlink()
    missing_artifact, artifact_checks = validate_summary(summary, policy, review_dir, events=_task_events())
    assert missing_artifact is False
    assert not next(
        check for check in artifact_checks if check["id"] == "subagent_supervision:terminal_artifacts"
    )["passed"]


def test_supervision_shadow_surfaces_bad_timing_without_blocking(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB001F"
    review_dir.mkdir(parents=True)
    summary = _supervision_summary(review_dir)
    policy = copy.deepcopy(load_policy())
    policy["subagent_supervision_policy"]["event_validation_mode"] = "shadow"

    passed, checks = validate_summary(summary, policy, review_dir, events=_task_events(duration_seconds=1801))
    lifecycle = next(check for check in checks if check["id"] == "subagent_supervision:event_lifecycle")
    assert passed is True
    assert lifecycle["passed"] is False
    assert lifecycle["blocking"] is False
