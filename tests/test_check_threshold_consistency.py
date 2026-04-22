#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
阈值一致性检查器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_threshold_consistency.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_threshold_consistency import ThresholdConsistencyChecker


# ===== Helpers =====

def write_report(tmp_path, text):
    (tmp_path / 'report_text.txt').write_text(text, encoding='utf-8')


def write_r_script(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    return str(tmp_path)


@pytest.fixture
def project_consistent(tmp_path):
    """报告阈值与代码一致"""
    write_report(tmp_path, '本研究以adj.P.Val < 0.05和|log2FC| > 1作为差异基因筛选标准，对转录组数据进行差异表达分析，使用limma包进行统计检验。')
    write_r_script(
        tmp_path / '01_DEGs' / 'degs.R',
        'P.thres <- 0.05\nlogFoldChange <- 1\n'
    )
    return str(tmp_path)


@pytest.fixture
def project_inconsistent(tmp_path):
    """报告写 p<0.05 但代码用 0.001"""
    write_report(tmp_path, '本研究以adj.P.Val < 0.05和|log2FC| > 1作为差异基因筛选标准，对转录组数据进行差异表达分析，使用limma包进行统计检验。')
    write_r_script(
        tmp_path / '01_DEGs' / 'degs.R',
        'P.thres <- 0.001\nlogFoldChange <- 1\n'
    )
    return str(tmp_path)


@pytest.fixture
def project_no_scripts(tmp_path):
    """有报告但无代码"""
    write_report(tmp_path, '本研究以adj.P.Val < 0.05作为差异基因筛选标准，对转录组数据进行差异表达分析，使用limma包进行统计检验。')
    return str(tmp_path)


# ===== Tests =====

class TestEmptyProject:
    def test_skipped(self, empty_project):
        checker = ThresholdConsistencyChecker(empty_project)
        result = checker.check_all()
        assert result.get('skipped', True)


class TestBasicInit:
    def test_layer0_data_stored(self, empty_project):
        checker = ThresholdConsistencyChecker(empty_project, layer0_data={'k': 'v'})
        assert checker._layer0_data == {'k': 'v'}


class TestNoScripts:
    def test_skipped(self, project_no_scripts):
        checker = ThresholdConsistencyChecker(project_no_scripts)
        result = checker.check_all()
        assert result.get('skipped', True)


class TestConsistentThresholds:
    def test_no_issues(self, project_consistent):
        checker = ThresholdConsistencyChecker(project_consistent)
        result = checker.check_all()
        assert len(result.get('issues', [])) == 0


class TestInconsistentThresholds:
    def test_detects_mismatch(self, project_inconsistent):
        checker = ThresholdConsistencyChecker(project_inconsistent)
        result = checker.check_all()
        all_items = result.get('issues', []) + result.get('warnings', [])
        # 应检测到 p 值不一致（0.05 vs 0.001）
        p_items = [i for i in all_items if 'p' in i.get('message', '').lower() or '阈值' in i.get('message', '')]
        assert len(p_items) >= 1, f'未检测到阈值不一致，消息: {[i.get("message") for i in all_items]}'
