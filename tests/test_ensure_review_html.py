#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression tests for ensure_review_html helper behavior."""

from __future__ import annotations

import json
import os
from argparse import Namespace
from pathlib import Path

import pytest

import ensure_review_html

from ensure_review_html import (
    ensure_one,
    html_binds_current_markdown,
    iter_targets,
    source_markdown_sha256,
)


@pytest.mark.parametrize("failure_status", ["missing", "failed"])
def test_cli_returns_nonzero_when_any_target_is_missing_or_failed(
    tmp_path,
    monkeypatch,
    failure_status,
):
    targets = [Path("successful-review"), Path("failed-review")]
    results = iter(
        [
            ("generated", "HTML 已生成"),
            (failure_status, "HTML 交付失败"),
        ]
    )
    monkeypatch.setattr(
        ensure_review_html,
        "parse_args",
        lambda: Namespace(path=str(tmp_path), force=False),
    )
    monkeypatch.setattr(ensure_review_html, "iter_targets", lambda _path: targets)
    monkeypatch.setattr(
        ensure_review_html,
        "ensure_one",
        lambda _target, _force: next(results),
    )

    assert ensure_review_html.main() != 0


def test_iter_targets_discovers_review_dirs_under_root(tmp_path):
    root = tmp_path / "result_review_report"
    review_a = root / "26YHB001F"
    review_b = root / "26YHB002F"
    ignored = root / "misc"
    review_a.mkdir(parents=True)
    review_b.mkdir(parents=True)
    ignored.mkdir(parents=True)
    (review_a / "final_review_report.md").write_text("# A\n", encoding="utf-8")
    (review_b / "REVIEW_REPORT.md").write_text("# B\n", encoding="utf-8")

    targets = list(iter_targets(root))

    assert targets == [review_a, review_b]


def test_ensure_one_handles_missing_report_gracefully(tmp_path):
    review_dir = tmp_path / "result_review_report" / "26YHB003F"
    review_dir.mkdir(parents=True)
    (review_dir / "case_manifest.json").write_text(
        json.dumps({"project_id": "26YHB003F"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    status, message = ensure_one(review_dir, force=False)
    manifest = json.loads((review_dir / "case_manifest.json").read_text(encoding="utf-8"))

    assert status == "missing"
    assert "缺少最终审核报告" in message
    assert manifest["publish_status"] == "failed"


def test_ensure_one_regenerates_html_when_newer_html_has_no_source_hash(tmp_path, monkeypatch):
    review_dir = tmp_path / "26YHTML"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YHTML_audit_report.html"
    report_path.write_text("# 正式复审报告\n", encoding="utf-8")
    html_path.write_text("<html>old but newer</html>", encoding="utf-8")
    os.utime(html_path, (report_path.stat().st_atime + 10, report_path.stat().st_mtime + 10))
    monkeypatch.setattr("ensure_review_html.build_html", lambda *_args: "<html>rendered</html>")
    monkeypatch.setattr(
        "ensure_review_html.validate_html_presentation_text",
        lambda *_args: (True, ""),
    )

    status, _ = ensure_one(review_dir, force=False)

    assert status == "generated"
    assert html_binds_current_markdown(report_path, html_path)
    assert "rendered" in html_path.read_text(encoding="utf-8")


def test_ensure_one_skips_only_html_bound_to_current_markdown(tmp_path, monkeypatch):
    review_dir = tmp_path / "26YHTML"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    report_path.write_text("# 正式复审报告\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        "ensure_review_html.build_html",
        lambda *_args: calls.append("rendered") or "<html>rendered</html>",
    )
    monkeypatch.setattr(
        "ensure_review_html.validate_html_presentation_text",
        lambda *_args: (True, ""),
    )
    monkeypatch.setattr(
        "ensure_review_html.validate_html_presentation_file",
        lambda *_args: (True, ""),
    )
    monkeypatch.setattr(
        "ensure_review_html.validate_html_canonical_equivalence",
        lambda *_args: (True, ""),
    )

    assert ensure_one(review_dir, force=False)[0] == "generated"
    assert ensure_one(review_dir, force=False)[0] == "skipped"
    assert calls == ["rendered"]


def test_ensure_one_renders_sealed_final_decision_instead_of_severity_fallback(
    tmp_path,
    monkeypatch,
):
    review_dir = tmp_path / "26YHTML"
    review_dir.mkdir()
    (review_dir / "final_review_report.md").write_text(
        (
            "# 26YHTML 正式复审报告\n\n"
            "## 问题清单\n\n"
            "| ID | Severity | Issue |\n"
            "|---|---|---|\n"
            "| F-001 | MAJOR | bad |\n"
        ),
        encoding="utf-8",
    )
    (review_dir / "final_decision.json").write_text(
        json.dumps(
            {
                "status": "leader_confirmed",
                "verdict": "不合格",
                "release_decision": "BLOCK",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ensure_review_html.validate_html_presentation_text",
        lambda *_args: (True, ""),
    )

    status, _ = ensure_one(review_dir, force=False)

    rendered = (review_dir / "26YHTML_audit_report.html").read_text(encoding="utf-8")
    assert status == "generated"
    assert '<body class="verdict-reject">' in rendered
    assert '<div class="verdict-banner verdict-reject">' in rendered
    assert "<span>审核结论：不合格</span>" in rendered


def test_ensure_one_full_contract_uses_block_decision_when_report_has_no_explicit_verdict(
    tmp_path,
):
    review_dir = tmp_path / "26YHTML"
    review_dir.mkdir()
    (review_dir / "final_review_report.md").write_text(
        (
            "# 26YHTML 正式复审报告\n\n"
            "> **项目名称**：结论绑定回归\n"
            "> **审核日期**：2026-07-31\n\n"
            "## 一、审核结论\n\n"
            "本节仅说明整改范围，正式结论以负责人裁决为准。\n\n"
            "## 二、提交阻断问题\n\n"
            "### P01 [MAJOR] 需整改问题\n\n"
            "补齐结构化证据后重新提交审核。\n"
        ),
        encoding="utf-8",
    )
    (review_dir / "project_structure.json").write_text(
        json.dumps(
            {
                "metadata": {"total_modules": 1, "total_data_files": 1},
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
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (review_dir / "final_decision.json").write_text(
        json.dumps(
            {
                "status": "leader_confirmed",
                "verdict": "不合格",
                "release_decision": "BLOCK",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    status, _ = ensure_one(review_dir, force=False)
    html_path = review_dir / "26YHTML_audit_report.html"
    rendered = html_path.read_text(encoding="utf-8")

    assert status == "generated"
    assert ensure_review_html.validate_html_presentation_file(html_path) == (True, "")
    assert '<body class="verdict-reject">' in rendered
    assert "<span>审核结论：不合格</span>" in rendered


def test_ensure_one_regenerates_bound_html_when_visual_verdict_conflicts(
    tmp_path,
    monkeypatch,
):
    review_dir = tmp_path / "26YHTML"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YHTML_audit_report.html"
    report_path.write_text("# 26YHTML 正式复审报告\n\n## 问题清单\n", encoding="utf-8")
    (review_dir / "final_decision.json").write_text(
        json.dumps(
            {
                "status": "leader_confirmed",
                "verdict": "不合格",
                "release_decision": "BLOCK",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    html_path.write_text(
        (
            f"<!-- audit-source-markdown-sha256: {source_markdown_sha256(report_path)} -->\n"
            '<html><body class="verdict-conditional">'
            '<div class="verdict-banner verdict-conditional">'
            "<span>审核结论：有条件合格</span>"
            "</div></body></html>"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ensure_review_html.validate_html_presentation_text",
        lambda *_args: (True, ""),
    )

    status, _ = ensure_one(review_dir, force=False)

    rendered = html_path.read_text(encoding="utf-8")
    assert status == "generated"
    assert '<body class="verdict-reject">' in rendered
    assert "<span>审核结论：不合格</span>" in rendered


def test_ensure_one_regenerates_bound_html_when_presentation_contract_is_stale(tmp_path):
    review_dir = tmp_path / "26YHTML"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YHTML_audit_report.html"
    report_path.write_text(
        (
            "# 26YHTML 正式复审报告\n\n"
            "## 一、审核结论\n\n结论：不合格。\n\n"
            "## 二、逐分析点审核结果\n\n"
            "| 分析点 | 审核判断 |\n|---|---|\n| A | 不通过 |\n\n"
            "## 三、提交阻断问题\n\n需整改。\n"
        ),
        encoding="utf-8",
    )
    (review_dir / "project_structure.json").write_text(
        json.dumps(
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
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (review_dir / "final_decision.json").write_text(
        json.dumps(
            {
                "status": "leader_confirmed",
                "verdict": "不合格",
                "release_decision": "BLOCK",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    html_path.write_text(
        (
            f"<!-- audit-source-markdown-sha256: {source_markdown_sha256(report_path)} -->\n"
            '<html><body class="verdict-reject">'
            '<div class="verdict-banner verdict-reject">'
            "<span>审核结论：不合格</span>"
            "</div></body></html>"
        ),
        encoding="utf-8",
    )

    status, _ = ensure_one(review_dir, force=False)

    rendered = html_path.read_text(encoding="utf-8")
    assert status == "generated"
    assert '<meta name="rrf-presentation-profile" content="reader-v3">' in rendered
    assert "标灰说明：灰色行表示该模块/目录仅交付数据表/数据文件" in rendered


def test_ensure_one_regenerates_contract_valid_html_with_missing_source_content(tmp_path):
    review_dir = tmp_path / "26YHTML"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YHTML_audit_report.html"
    required_sentence = "这条证据和整改要求不得从 HTML 中丢失。"
    report_path.write_text(
        (
            "# 26YHTML 正式复审报告\n\n"
            "> **项目名称**：内容等价门禁回归\n"
            "> **审核日期**：2026-07-31\n\n"
            "## 一、审核结论\n\n"
            "结论：不合格。\n\n"
            "## 二、提交阻断问题\n\n"
            "### P01 [CRITICAL] 阻断问题\n\n"
            f"{required_sentence}\n"
        ),
        encoding="utf-8",
    )
    (review_dir / "project_structure.json").write_text(
        json.dumps(
            {
                "metadata": {"total_modules": 1, "total_data_files": 1},
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
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (review_dir / "final_decision.json").write_text(
        json.dumps(
            {
                "status": "leader_confirmed",
                "verdict": "不合格",
                "release_decision": "BLOCK",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert ensure_one(review_dir, force=False)[0] == "generated"
    canonical = html_path.read_text(encoding="utf-8")
    assert required_sentence in canonical
    mutated = canonical.replace(required_sentence, "", 1)
    assert mutated != canonical
    html_path.write_text(mutated, encoding="utf-8")
    assert ensure_review_html.validate_html_presentation_file(html_path) == (True, "")

    status, _ = ensure_one(review_dir, force=False)

    assert status == "generated"
    assert required_sentence in html_path.read_text(encoding="utf-8")
