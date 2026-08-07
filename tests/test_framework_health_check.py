#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression tests for framework self-health drift checks."""

from __future__ import annotations

from pathlib import Path

from framework_health_check import (
    ContentRule,
    VersionMarkerRule,
    evaluate_content_rule,
    evaluate_presentation_template,
    evaluate_version_rule,
    run_health_check,
)


FRAMEWORK_ROOT = Path(__file__).resolve().parents[1]


def test_framework_health_check_passes_for_repo():
    report = run_health_check()

    assert report["passed"] is True
    assert report["generated_doc_drift"] == []


def test_evaluate_version_rule_detects_version_drift(tmp_path):
    target = tmp_path / "WORKFLOW.md"
    target.write_text("> **版本**: v6.5\n", encoding="utf-8")

    check = evaluate_version_rule(
        tmp_path,
        "v6.6",
        VersionMarkerRule("WORKFLOW.md", r"^> \*\*版本\*\*: (?P<version>v[\d.]+)$", "workflow header version"),
    )

    assert check["passed"] is False
    assert check["actual"] == "v6.5"
    assert check["expected"] == "v6.6"


def test_evaluate_content_rule_detects_forbidden_legacy_command(tmp_path):
    target = tmp_path / "AGENT_TEAM_PLAN.md"
    target.write_text("render_final_review_html.py\n", encoding="utf-8")

    check = evaluate_content_rule(
        tmp_path,
        ContentRule(
            "AGENT_TEAM_PLAN.md",
            description="legacy html renderer should not be the main final step",
            forbidden="render_final_review_html.py",
        ),
    )

    assert check["passed"] is False
    assert "Forbidden content still present" in check["message"]


def test_framework_health_detects_reader_template_asset_drift(tmp_path):
    target = tmp_path / "report_templates" / "final_review_report_template.html"
    target.parent.mkdir(parents=True)
    template = (
        FRAMEWORK_ROOT / "report_templates" / "final_review_report_template.html"
    ).read_text(encoding="utf-8")
    target.write_text(
        template.replace("background: #d1fae5;", "background: hotpink;", 1),
        encoding="utf-8",
    )

    check = evaluate_presentation_template(tmp_path)

    assert check["passed"] is False
    assert "reader-v3" in check["message"]
