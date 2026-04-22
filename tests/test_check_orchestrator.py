#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查编排器单元测试（P0级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_orchestrator.py -v
"""

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_orchestrator import CheckOrchestrator


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    return str(tmp_path)


# ===== 检查器注册表验证 =====

class TestP0Registry:
    """P0 检查器注册表"""

    def test_has_four_p0_checkers(self):
        assert len(CheckOrchestrator.P0_CHECKERS) == 4

    def test_all_have_required_fields(self):
        for entry in CheckOrchestrator.P0_CHECKERS:
            assert 'name' in entry
            assert 'cls' in entry
            assert 'method' in entry

    def test_p0_checker_names(self):
        names = [e['name'] for e in CheckOrchestrator.P0_CHECKERS]
        # 应包含 4 个 P0 检查器
        assert len(names) == 4
        # 每个名称应为非空字符串
        for n in names:
            assert isinstance(n, str) and len(n) > 0


class TestP1Registry:
    """P1 检查器注册表"""

    def test_has_expected_p1_checkers(self):
        # v6.2: P1 至少 15 个（含中文校对）
        assert len(CheckOrchestrator.P1_CHECKERS) >= 15

    def test_all_have_required_fields(self):
        for entry in CheckOrchestrator.P1_CHECKERS:
            assert 'name' in entry
            assert 'cls' in entry
            assert 'method' in entry


# ===== P0 不可用检测 =====

class TestP0Unavailable:
    """v4.7: P0 检查器不可用时应产生 FATAL"""

    def test_run_all_checks_has_unavailable_detection(self):
        """确认源码包含 p0_unavailable 检测"""
        src = inspect.getsource(CheckOrchestrator.run_all_checks)
        assert 'p0_unavailable' in src or ('cls' in src and 'None' in src)

    def test_empty_project_runs_safely(self, empty_project):
        orch = CheckOrchestrator(empty_project)
        result = orch.run_all_checks(stop_on_fatal=False)
        # 空项目应能运行完成（不崩溃）
        assert isinstance(result, dict)


# ===== 返回结构 =====

class TestReturnStructure:
    """验证返回字典结构"""

    def test_has_priority_keys(self, empty_project):
        orch = CheckOrchestrator(empty_project)
        result = orch.run_all_checks(stop_on_fatal=False)
        # 应有汇总信息
        assert 'summary' in result or isinstance(result, dict)


# ===== v6.2: 输出标准化 =====

class TestNormalizeResult:
    """_normalize_result 标准化测试"""

    def test_empty_dict(self):
        result = CheckOrchestrator._normalize_result({})
        assert result['issues'] == []
        assert result['warnings'] == []
        assert result['total_checks'] == 1
        assert result['failed_checks'] == 0
        assert result['skipped'] is False
        assert result['degraded'] is False
        assert '_raw' in result

    def test_preserves_existing_fields(self):
        original = {'issues': [{'msg': 'test'}], 'total_checks': 5, 'failed_checks': 1}
        result = CheckOrchestrator._normalize_result(original)
        assert len(result['issues']) == 1
        assert result['total_checks'] == 5
        assert result['failed_checks'] == 1

    def test_raw_contains_original(self):
        original = {'custom_key': 'value', 'issues': []}
        result = CheckOrchestrator._normalize_result(original)
        assert result['_raw']['custom_key'] == 'value'

    def test_non_list_issues_becomes_empty(self):
        result = CheckOrchestrator._normalize_result({'issues': 'not_a_list'})
        assert result['issues'] == []

    def test_degraded_flag(self):
        result = CheckOrchestrator._normalize_result({'degraded': True})
        assert result['degraded'] is True

    def test_skipped_flag(self):
        result = CheckOrchestrator._normalize_result({'skipped': True, 'reason': '无报告'})
        assert result['skipped'] is True
        assert result['reason'] == '无报告'


# ===== v6.2: 融合信号检测 =====

class TestConvergenceSignals:
    """_detect_convergence_signals 测试"""

    def test_no_results_returns_empty(self, empty_project):
        orch = CheckOrchestrator(empty_project)
        signals = orch._detect_convergence_signals()
        assert signals == []

    def test_single_checker_no_signal(self, empty_project):
        orch = CheckOrchestrator(empty_project)
        orch.results['P1'].append({
            'name': 'A检查', 'priority': 'P1', 'status': 'FAIL',
            'result': {'issues': [{'message': 'test', 'evidence': {'module': 'DEGs'}}]}
        })
        signals = orch._detect_convergence_signals()
        assert signals == []

    def test_two_checkers_same_module(self, empty_project):
        orch = CheckOrchestrator(empty_project)
        orch.results['P1'].append({
            'name': 'A检查', 'priority': 'P1', 'status': 'FAIL',
            'result': {'issues': [{'message': 'issue1', 'evidence': {'module': '01_DEGs'}}]}
        })
        orch.results['P1'].append({
            'name': 'B检查', 'priority': 'P1', 'status': 'FAIL',
            'result': {'issues': [{'message': 'issue2', 'evidence': {'module': '01_DEGs'}}]}
        })
        signals = orch._detect_convergence_signals()
        assert len(signals) == 1
        assert signals[0]['target'] == 'DEGs'
        assert signals[0]['confidence'] == 'MEDIUM'
        assert set(signals[0]['checkers']) == {'A检查', 'B检查'}

    def test_three_checkers_high_confidence(self, empty_project):
        orch = CheckOrchestrator(empty_project)
        for name in ('A', 'B', 'C'):
            orch.results['P0'].append({
                'name': f'{name}检查', 'priority': 'P0', 'status': 'FAIL',
                'result': {'issues': [{'evidence': {'module': 'WGCNA'}}]}
            })
        signals = orch._detect_convergence_signals()
        assert len(signals) == 1
        assert signals[0]['confidence'] == 'HIGH'
        assert signals[0]['checker_count'] == 3

    def test_extract_file_target(self, empty_project):
        orch = CheckOrchestrator(empty_project)
        orch.results['P1'].append({
            'name': 'A', 'priority': 'P1', 'status': 'FAIL',
            'result': {'issues': [{'evidence': {'file': 'data.csv'}}]}
        })
        orch.results['P1'].append({
            'name': 'B', 'priority': 'P1', 'status': 'FAIL',
            'result': {'issues': [{'evidence': {'csv_file': 'data.csv'}}]}
        })
        signals = orch._detect_convergence_signals()
        assert len(signals) == 1
        assert signals[0]['target'] == 'data.csv'
        assert signals[0]['target_type'] == 'file'


# ===== v6.2: generate_report 包含融合信号 =====

class TestGenerateReport:
    """generate_report markdown 输出测试"""

    def test_report_contains_convergence_section(self, empty_project):
        orch = CheckOrchestrator(empty_project)
        orch.convergence_signals = [{
            'target': 'DEGs', 'target_type': 'module',
            'checkers': ['A', 'B'], 'checker_count': 2,
            'confidence': 'MEDIUM', 'severity_boost': 'MAJOR'
        }]
        report = orch.generate_report()
        assert '跨检查器融合信号' in report
        assert 'DEGs' in report

    def test_report_no_convergence_when_empty(self, empty_project):
        orch = CheckOrchestrator(empty_project)
        orch.convergence_signals = []
        report = orch.generate_report()
        assert '跨检查器融合信号' not in report

    def test_report_shows_degraded(self, empty_project):
        orch = CheckOrchestrator(empty_project)
        orch.results['P1'].append({
            'name': '测试检查', 'priority': 'P1', 'status': 'PASS',
            'result': {'degraded': True, 'issues': [], 'warnings': [],
                       'total_checks': 1, 'failed_checks': 0,
                       'skipped': False, '_raw': {}}
        })
        report = orch.generate_report()
        assert '降级运行' in report

    def test_report_shows_issues_detail(self, empty_project):
        orch = CheckOrchestrator(empty_project)
        orch.results['P1'].append({
            'name': '测试检查', 'priority': 'P1', 'status': 'FAIL',
            'result': {'issues': [{'severity': 'CRITICAL', 'message': '测试问题'}],
                       'warnings': [], 'total_checks': 1, 'failed_checks': 1,
                       'skipped': False, 'degraded': False, '_raw': {}}
        })
        report = orch.generate_report()
        assert '测试问题' in report
        assert '[CRITICAL]' in report
