#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression tests for reviewed-project archive moves."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from auto_audit_pipeline import AutoAuditPipeline
from ensure_review_html import move_reviewed_project


def test_move_to_ai_reviewed_handles_nested_zip_project_dir(tmp_path):
    raw_root = tmp_path / "raw"
    project_root = raw_root / "待审核" / "26YZF051F"
    inner_project = project_root / "26YZF051F-数据分析报告"
    inner_project.mkdir(parents=True)
    (inner_project / "dummy.txt").write_text("ok", encoding="utf-8")
    source_zip = raw_root / "待审核" / "26YZF051F.zip"
    source_zip.write_text("zip", encoding="utf-8")

    pipeline = AutoAuditPipeline(str(inner_project), source_archive_path=str(source_zip))
    moved_to = pipeline.move_to_ai_reviewed()

    assert moved_to == raw_root / "已AI审核一次" / "26YZF051F"
    assert moved_to.exists()
    assert not project_root.exists()
    assert not source_zip.exists()
    assert (moved_to / "26YZF051F-数据分析报告" / "dummy.txt").exists()
    assert (raw_root / "已AI审核一次" / "26YZF051F.zip").exists()


def test_move_to_ai_reviewed_handles_nested_rar_project_dir(tmp_path):
    raw_root = tmp_path / "raw"
    project_root = raw_root / "待审核" / "26YZF051F"
    inner_project = project_root / "26YZF051F-数据分析报告"
    inner_project.mkdir(parents=True)
    (inner_project / "dummy.txt").write_text("ok", encoding="utf-8")
    source_rar = raw_root / "待审核" / "26YZF051F.rar"
    source_rar.write_text("rar", encoding="utf-8")

    pipeline = AutoAuditPipeline(str(inner_project), source_archive_path=str(source_rar))
    moved_to = pipeline.move_to_ai_reviewed()

    assert moved_to == raw_root / "已AI审核一次" / "26YZF051F"
    assert moved_to.exists()
    assert not project_root.exists()
    assert not source_rar.exists()
    assert (moved_to / "26YZF051F-数据分析报告" / "dummy.txt").exists()
    assert (raw_root / "已AI审核一次" / "26YZF051F.rar").exists()


def test_ensure_review_html_can_move_reviewed_project_from_manifest(tmp_path):
    raw_root = tmp_path / "raw"
    project_root = raw_root / "待审核" / "26YZF051F"
    inner_project = project_root / "26YZF051F-数据分析报告"
    inner_project.mkdir(parents=True)
    (inner_project / "artifact.txt").write_text("done", encoding="utf-8")
    source_zip = raw_root / "待审核" / "26YZF051F.zip"
    source_zip.write_text("zip", encoding="utf-8")

    review_dir = tmp_path / "result_review_report" / "26YZF051F"
    review_dir.mkdir(parents=True)
    manifest = {
        "paths": {
            "project_dir": str(inner_project),
            "source_archive_path": str(source_zip),
        }
    }
    (review_dir / "ai_execution_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    moved_to = move_reviewed_project(review_dir)

    assert moved_to == raw_root / "已AI审核一次" / "26YZF051F"
    assert moved_to.exists()
    assert not project_root.exists()
    assert not source_zip.exists()
    assert (moved_to / "26YZF051F-数据分析报告" / "artifact.txt").exists()
    assert (raw_root / "已AI审核一次" / "26YZF051F.zip").exists()


def test_move_reviewed_project_falls_back_to_raw_pending_by_project_id(tmp_path):
    raw_root = tmp_path / "raw"
    pending_dir = raw_root / "待审核"
    pending_project = pending_dir / "26YYS103F_分析报告-孟德尔随机化-dlh-20260427"
    pending_project.mkdir(parents=True)
    (pending_project / "artifact.txt").write_text("done", encoding="utf-8")
    source_zip = pending_dir / "26YYS103F_分析报告-孟德尔随机化-dlh-20260427.zip"
    source_zip.write_text("zip", encoding="utf-8")

    tmp_project = tmp_path / "tmp" / "audit_work" / "26YYS103F"
    tmp_project.mkdir(parents=True)
    review_dir = tmp_path / "result_review_report" / "26YYS103F"
    review_dir.mkdir(parents=True)
    (review_dir / "ai_execution_manifest.json").write_text(
        json.dumps(
            {
                "paths": {
                    "project_dir": str(tmp_project),
                    "source_archive_path": str(tmp_project),
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (review_dir / "case_manifest.json").write_text(
        json.dumps({"project_id": "26YYS103F"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    moved_to = move_reviewed_project(review_dir)

    target_root = raw_root / "已AI审核一次"
    assert moved_to == target_root / pending_project.name
    assert moved_to.exists()
    assert (moved_to / "artifact.txt").exists()
    assert (target_root / source_zip.name).exists()
    assert not pending_project.exists()
    assert not source_zip.exists()


def test_ensure_review_html_moves_rar_source_archive_from_manifest(tmp_path):
    raw_root = tmp_path / "raw"
    project_root = raw_root / "待审核" / "26YZF051F"
    inner_project = project_root / "26YZF051F-数据分析报告"
    inner_project.mkdir(parents=True)
    (inner_project / "artifact.txt").write_text("done", encoding="utf-8")
    source_rar = raw_root / "待审核" / "26YZF051F.rar"
    source_rar.write_text("rar", encoding="utf-8")

    review_dir = tmp_path / "result_review_report" / "26YZF051F"
    review_dir.mkdir(parents=True)
    manifest = {
        "paths": {
            "project_dir": str(inner_project),
            "source_archive_path": str(source_rar),
        }
    }
    (review_dir / "ai_execution_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    moved_to = move_reviewed_project(review_dir)

    assert moved_to == raw_root / "已AI审核一次" / "26YZF051F"
    assert moved_to.exists()
    assert not project_root.exists()
    assert not source_rar.exists()
    assert (moved_to / "26YZF051F-数据分析报告" / "artifact.txt").exists()
    assert (raw_root / "已AI审核一次" / "26YZF051F.rar").exists()


def test_ensure_review_html_infers_sibling_archive_when_manifest_points_to_folder(tmp_path):
    raw_root = tmp_path / "raw"
    pending_root = raw_root / "待审核" / "26YHB261F"
    inner_project = pending_root / "26YHB261F-分析数据报告"
    inner_project.mkdir(parents=True)
    (inner_project / "artifact.txt").write_text("done", encoding="utf-8")
    source_rar = raw_root / "待审核" / "26YHB261F-分析数据报告-CWX-2026424.rar"
    source_rar.write_text("rar", encoding="utf-8")

    review_dir = tmp_path / "result_review_report" / "26YHB261F"
    review_dir.mkdir(parents=True)
    manifest = {
        "paths": {
            "project_dir": str(inner_project),
            "source_archive_path": str(inner_project),
        }
    }
    (review_dir / "ai_execution_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    moved_to = move_reviewed_project(review_dir)

    assert moved_to == raw_root / "已AI审核一次" / "26YHB261F"
    assert moved_to.exists()
    assert not pending_root.exists()
    assert not source_rar.exists()
    assert (moved_to / "26YHB261F-分析数据报告" / "artifact.txt").exists()
    assert (raw_root / "已AI审核一次" / source_rar.name).exists()


def test_ensure_review_html_moves_zip_and_removes_extracted_cache(tmp_path):
    raw_root = tmp_path / "raw"
    extracted_root = raw_root / "zip_extracted" / "26YHB539F-demo"
    inner_project = extracted_root / "26YHB539F-demo"
    inner_project.mkdir(parents=True)
    (inner_project / "artifact.txt").write_text("done", encoding="utf-8")
    source_zip = raw_root / "待审核" / "26YHB539F-demo.zip"
    source_zip.parent.mkdir(parents=True)
    source_zip.write_text("zip", encoding="utf-8")

    review_dir = tmp_path / "result_review_report" / "26YHB539F"
    review_dir.mkdir(parents=True)
    manifest = {
        "paths": {
            "project_dir": str(inner_project),
            "source_archive_path": str(inner_project),
        }
    }
    (review_dir / "ai_execution_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    moved_to = move_reviewed_project(review_dir)

    assert moved_to == raw_root / "已AI审核一次" / source_zip.name
    assert moved_to.exists()
    assert not source_zip.exists()
    assert not extracted_root.exists()


def test_ensure_review_html_removes_duplicate_pending_residual_when_destination_exists(tmp_path):
    raw_root = tmp_path / "raw"
    pending_root = raw_root / "待审核" / "26YHB261F"
    inner_project = pending_root / "26YHB261F-分析数据报告"
    inner_project.mkdir(parents=True)
    (inner_project / "artifact.txt").write_text("done", encoding="utf-8")

    destination = raw_root / "已AI审核一次" / "26YHB261F"
    destination_inner = destination / "26YHB261F-分析数据报告"
    destination_inner.mkdir(parents=True)
    (destination_inner / "artifact.txt").write_text("done", encoding="utf-8")

    review_dir = tmp_path / "result_review_report" / "26YHB261F"
    review_dir.mkdir(parents=True)
    manifest = {
        "paths": {
            "project_dir": str(inner_project),
            "source_archive_path": str(inner_project),
        }
    }
    (review_dir / "ai_execution_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    moved_to = move_reviewed_project(review_dir)

    assert moved_to == destination
    assert destination.exists()
    assert not pending_root.exists()
    assert (destination_inner / "artifact.txt").exists()


def test_normalize_project_input_extracts_rar_archives(tmp_path, monkeypatch):
    workspace_root = tmp_path
    archive_path = workspace_root / "sample.rar"
    archive_path.write_text("rar", encoding="utf-8")
    target_root = workspace_root / "raw" / "待审核" / "26YZF051F"

    def fake_extract(command, capture_output, text, encoding, errors, timeout):
        assert command[1] == "x"
        staging_dir = Path(next(argument[2:] for argument in command if argument.startswith("-o")))
        extracted = staging_dir / "26YZF051F-数据分析报告"
        extracted.mkdir(parents=True, exist_ok=True)
        (extracted / "artifact.txt").write_text("done", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("auto_audit_pipeline.extract_project_id", lambda stem: "26YZF051F")
    monkeypatch.setattr("auto_audit_pipeline.shutil.which", lambda name: "7z")
    monkeypatch.setattr("auto_audit_pipeline.subprocess.run", fake_extract)
    monkeypatch.setattr("auto_audit_pipeline.Path.resolve", lambda self: workspace_root / "result_review_framework" / "scripts" / "auto_audit_pipeline.py")

    normalized = AutoAuditPipeline.normalize_project_input(archive_path)

    assert normalized == target_root / "26YZF051F-数据分析报告"
    assert (normalized / "artifact.txt").exists()
