#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression tests for the v6.6 workflow hardening changes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from archive_reviewed_project import archive_reviewed_project
from convergence_compare import classify_groups, match_findings
from ensure_review_html import ensure_one
import finalize_audit
from generate_policy_docs import write_documents
from parse_project_structure import parse_project
from visual_audit import prepare_visual_audit


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
    write_json(
        review_dir / "ai_execution_manifest.json",
        {
            "paths": {
                "project_dir": str(project_dir),
                "source_archive_path": str(source_zip),
            }
        },
    )
    return raw_root, project_dir, review_dir


def test_ensure_review_html_does_not_move_project(tmp_path):
    raw_root, project_dir, review_dir = _build_review_case(tmp_path)

    status, _ = ensure_one(review_dir, force=True)

    assert status == "generated"
    assert project_dir.exists()
    assert not (raw_root / "已AI审核一次").exists()
    assert any(path.name.endswith("_audit_report.html") for path in review_dir.glob("*_audit_report.html"))


def test_archive_reviewed_project_requires_publish_success_and_explicit_approval(tmp_path):
    raw_root, project_dir, review_dir = _build_review_case(tmp_path)
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


def test_finalize_audit_auto_archives_by_default(tmp_path, monkeypatch):
    _, _, review_dir = _build_review_case(tmp_path)
    html_path = review_dir / "26YZF051F_audit_report.html"
    write_json(
        review_dir / "case_manifest.json",
        {
            "project_id": "26YZF051F",
            "publish_status": "pending",
            "archive_approved": False,
        },
    )

    calls: list[tuple[Path, bool]] = []

    def fake_run_step(target: Path, script_name: str) -> subprocess.CompletedProcess[str]:
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
        archived_root = tmp_path / "raw" / "已审核一次" / "26YZF051F"
        archived_root.mkdir(parents=True, exist_ok=True)
        return archived_root

    monkeypatch.setattr(finalize_audit, "run_step", fake_run_step)
    monkeypatch.setattr(finalize_audit, "archive_reviewed_project", fake_archive)
    monkeypatch.setattr(sys, "argv", ["finalize_audit.py", str(review_dir)])

    assert finalize_audit.main() == 0
    manifest = json.loads((review_dir / "case_manifest.json").read_text(encoding="utf-8"))

    assert calls == [(review_dir, True)]
    assert manifest["publish_status"] == "success"
    assert manifest["archive_approved"] is True
    assert manifest["archived_at"] == "2026-04-21T00:00:00"


def test_finalize_audit_no_auto_archive_skips_move(tmp_path, monkeypatch):
    _, _, review_dir = _build_review_case(tmp_path)
    html_path = review_dir / "26YZF051F_audit_report.html"
    write_json(
        review_dir / "case_manifest.json",
        {
            "project_id": "26YZF051F",
            "publish_status": "pending",
            "archive_approved": False,
        },
    )

    def fake_run_step(target: Path, script_name: str) -> subprocess.CompletedProcess[str]:
        if script_name == "ensure_review_html.py":
            html_path.write_text("<html></html>", encoding="utf-8")
        if script_name == "sync_audit_state.py":
            (review_dir / "audit_state.json").write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess([script_name], 0, stdout="", stderr="")

    def fail_archive(target: Path, *, approve: bool = False) -> Path:
        raise AssertionError("archive_reviewed_project should not be called when --no-auto-archive is set")

    monkeypatch.setattr(finalize_audit, "run_step", fake_run_step)
    monkeypatch.setattr(finalize_audit, "archive_reviewed_project", fail_archive)
    monkeypatch.setattr(sys, "argv", ["finalize_audit.py", str(review_dir), "--no-auto-archive"])

    assert finalize_audit.main() == 0
    manifest = json.loads((review_dir / "case_manifest.json").read_text(encoding="utf-8"))

    assert manifest["publish_status"] == "success"
    assert manifest["archive_approved"] is False


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


def test_generated_docs_match_committed_files():
    assert write_documents(check_only=True) == []
