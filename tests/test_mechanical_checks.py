#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from mechanical_checks import check_high_risk_module_consistency


def test_mc016_ignores_company_promo_appendix_after_references(tmp_path):
    report_lines = [
        "结果",
        "参考文献",
        "[1] something",
        "公司介绍",
        "服务领域",
        "热点涵盖：分子对接及分子动力学模拟等",
    ]
    structure = {"image_markers": []}
    proj_struct = {"code_files": []}

    issues = check_high_risk_module_consistency(report_lines, structure, proj_struct, tmp_path)

    assert issues == []


def test_mc016_still_flags_real_body_docking_claim(tmp_path):
    report_lines = [
        "2.10 分子对接",
        "我们进行了分子对接分析。",
        "参考文献",
        "[1] something",
    ]
    structure = {"image_markers": []}
    proj_struct = {"code_files": []}

    issues = check_high_risk_module_consistency(report_lines, structure, proj_struct, tmp_path)

    assert any(issue.get("code") == "MC-016" for issue in issues)


def test_mc016_missing_high_risk_script_is_warning(tmp_path):
    report_lines = [
        "2.10 分子对接",
        "我们进行了分子对接分析。",
    ]
    structure = {"image_markers": [{"line": 2}]}
    proj_struct = {"code_files": []}

    issues = check_high_risk_module_consistency(report_lines, structure, proj_struct, tmp_path)

    matching = [issue for issue in issues if "未识别到对接脚本" in issue.get("message", "")]
    assert matching
    assert all(issue.get("severity") == "WARNING" for issue in matching)
