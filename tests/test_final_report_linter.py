#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Focused regression tests for final-report verdict linting."""

from __future__ import annotations

from final_report_linter import build_checks, build_report_depth_checks, summarize_checks


def _minimal_policy() -> dict:
    return {
        "required_final_files": [],
        "required_final_sections": {"audit_conclusion": ["审核结论"]},
        "forbidden_shortcuts": [],
        "formal_delivery_policy": {"enabled": True},
        "final_report_depth_policy": {"enabled": True},
        "subagent_supervision_policy": {"enabled": False},
    }


def test_audit_conclusion_heading_without_explicit_verdict_blocks_lint(tmp_path):
    report_text = (
        "# 最终审核报告\n\n"
        "## 审核结论\n\n"
        "本报告确认 15 项审核发现，详见下文。\n"
    )

    checks = build_checks(tmp_path, report_text, _minimal_policy())
    verdict_check = next(
        check for check in checks if check["id"] == "verdict:explicit_conclusion"
    )
    summary = summarize_checks(checks, _minimal_policy())

    assert verdict_check["passed"] is False
    assert verdict_check["severity"] == "error"
    assert summary["passed"] is False


def test_indexed_finding_without_exact_concrete_error_heading_blocks_depth_gate():
    policy = {
        "final_report_depth_policy": {
            "enabled": True,
            "require_indexed_finding_detail_coverage": True,
            "child_heading_prefix": "具体错误",
        }
    }
    report_text = (
        "## 提交阻断问题\n\n"
        "| 编号 | 严重度 | 核心问题 | 原报告位置 | 交付证据 | 修订要求 |\n"
        "|---|---|---|---|---|---|\n"
        "| F-021 | MAJOR | 图例缺失 | 主报告.docx，图 3 | 图件 | 补图例 |\n\n"
        "### P01 [MAJOR] 图件问题\n\n"
        "#### 具体错误 1：其他图件问题（F-020）\n\n"
        "- **错误点**：图例缺失。\n"
        "- **原报告位置**：主报告.docx，图 3，“无图例”。\n"
        "- **原文短句**：“无图例”。\n"
        "- **交付证据**：图件。\n"
        "- **修订要求**：补图例。\n"
    )

    checks = build_report_depth_checks(report_text, policy)
    coverage = next(
        check
        for check in checks
        if check["id"] == "depth:indexed_findings_have_detail_heading"
    )

    assert coverage["passed"] is False
    assert "F-021" in coverage["message"]
