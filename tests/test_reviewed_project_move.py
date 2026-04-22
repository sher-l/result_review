#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""审核完成后自动移动到 raw/已AI审核一次 的回归测试。"""

import json
import sys
from pathlib import Path

# 确保 scripts/ 在导入路径中
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
