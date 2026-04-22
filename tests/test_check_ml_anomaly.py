#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ML 异常检测器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_ml_anomaly.py -v
"""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_ml_anomaly import MLAnomalyChecker


# ===== Fixtures =====

def write_ml_csv(path, rows, headers=None):
    """写 ML 结果 CSV"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if headers is None:
        headers = ['Model', 'AUC', 'Accuracy', 'F1']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(headers)
        for row in rows:
            w.writerow(row)


@pytest.fixture
def empty_project(tmp_path):
    return str(tmp_path)


@pytest.fixture
def project_with_normal_ml(tmp_path):
    """正常 ML 结果"""
    write_ml_csv(
        tmp_path / '07_machine' / 'result.csv',
        [
            ['RF', '0.85', '0.78', '0.80'],
            ['SVM', '0.82', '0.75', '0.77'],
            ['XGBoost', '0.88', '0.80', '0.82'],
        ]
    )
    return str(tmp_path)


@pytest.fixture
def project_with_perfect_auc(tmp_path):
    """AUC = 1.0 过拟合"""
    write_ml_csv(
        tmp_path / '07_machine' / 'result.csv',
        [
            ['RF', '1.0', '0.95', '0.93'],
            ['SVM', '0.82', '0.75', '0.77'],
        ]
    )
    return str(tmp_path)


@pytest.fixture
def project_with_paradox(tmp_path):
    """AUC 高但 Accuracy 极低"""
    write_ml_csv(
        tmp_path / '07_machine' / 'result.csv',
        [
            ['RF', '0.92', '0.35', '0.40'],
        ]
    )
    return str(tmp_path)


@pytest.fixture
def project_with_uniform_auc(tmp_path):
    """所有模型 AUC 完全相同"""
    write_ml_csv(
        tmp_path / '07_machine' / 'result.csv',
        [
            ['RF', '0.85', '0.78', '0.80'],
            ['SVM', '0.85', '0.76', '0.78'],
            ['XGBoost', '0.85', '0.80', '0.82'],
            ['LR', '0.85', '0.74', '0.76'],
        ]
    )
    return str(tmp_path)


# ===== 测试 =====

class TestEmptyProject:
    """无 ML 模块"""

    def test_skipped(self, empty_project):
        checker = MLAnomalyChecker(empty_project)
        result = checker.check_all()
        assert result.get('skipped', True) or result.get('models_scanned', 0) == 0


class TestNormalML:
    """正常 ML 结果"""

    def test_no_issues(self, project_with_normal_ml):
        checker = MLAnomalyChecker(project_with_normal_ml)
        result = checker.check_all()
        assert len(result.get('issues', [])) == 0


class TestPerfectAUC:
    """AUC = 1.0 检测"""

    def test_detects_overfitting(self, project_with_perfect_auc):
        checker = MLAnomalyChecker(project_with_perfect_auc)
        result = checker.check_all()
        # AUC=1.0 可能在 issues 或 warnings 中
        all_items = result.get('issues', []) + result.get('warnings', [])
        auc_items = [i for i in all_items if 'AUC' in i.get('message', '') or '1.0' in i.get('message', '') or '过拟合' in i.get('message', '')]
        assert len(auc_items) >= 1


class TestAUCAccuracyParadox:
    """AUC-Accuracy 矛盾检测"""

    def test_detects_paradox(self, project_with_paradox):
        checker = MLAnomalyChecker(project_with_paradox)
        result = checker.check_all()
        all_msgs = [i.get('message', '') for i in result.get('issues', []) + result.get('warnings', [])]
        # 应有关于 AUC-Accuracy 矛盾的消息
        has_paradox = any('Accuracy' in m or '矛盾' in m or 'paradox' in m.lower() for m in all_msgs)
        assert has_paradox, f'未检测到 AUC-Accuracy 矛盾，消息: {all_msgs}'


class TestUniformAUC:
    """所有 AUC 相同 → 数据泄漏风险"""

    def test_detects_uniform(self, project_with_uniform_auc):
        checker = MLAnomalyChecker(project_with_uniform_auc)
        result = checker.check_all()
        all_msgs = [i.get('message', '') for i in result.get('issues', []) + result.get('warnings', [])]
        has_uniform = any('一致' in m or 'uniform' in m.lower() or '泄漏' in m or '相同' in m for m in all_msgs)
        assert has_uniform, f'未检测到均匀 AUC，消息: {all_msgs}'


class TestModulePattern:
    """ML 模块识别模式"""

    def test_pattern_matches(self):
        import re
        pat = MLAnomalyChecker._ML_MODULE_PATTERN
        assert pat.search('07_machine')
        assert pat.search('ML_models')
        assert pat.search('机器学习')
        assert not pat.search('01_limma')


class TestReturnStructure:
    """返回结构"""

    def test_keys(self, empty_project):
        checker = MLAnomalyChecker(empty_project)
        result = checker.check_all()
        assert 'issues' in result
        # 空项目 skipped=True 时无 total_checks
        assert result.get('skipped') is True or 'total_checks' in result
