#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模型一致性检查器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_model_consistency.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_model_consistency import ModelConsistencyChecker


# ===== Helpers =====

def write_r_script(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    return str(tmp_path)


@pytest.fixture
def project_consistent_model(tmp_path):
    """同一脚本中模型公式一致"""
    write_r_script(
        tmp_path / '06_Nomogram' / 'nomogram.R',
        '''
nom_model <- lrm(Y ~ CDH1 + DPP4 + MEG3, data=train)
cal_model <- lrm(Y ~ CDH1 + DPP4 + MEG3, data=train)
'''
    )
    return str(tmp_path)


@pytest.fixture
def project_inconsistent_model(tmp_path):
    """列线图 5 基因 vs 校准曲线 3 基因"""
    write_r_script(
        tmp_path / '06_Nomogram' / 'r-06_Nomogram.R',
        '''
nom_model <- lrm(Y ~ CDH1 + DPP4 + HOTAIR + MEG3 + PROM2, data=train)
cal_model <- lrm(Y ~ CDH1 + DPP4 + MEG3, data=train)
'''
    )
    return str(tmp_path)


@pytest.fixture
def project_single_model(tmp_path):
    """只有一个模型，不触发对比"""
    write_r_script(
        tmp_path / '06_Nomogram' / 'nomogram.R',
        'model <- glm(Y ~ A + B + C, data=train, family=binomial)\n'
    )
    return str(tmp_path)


# ===== Tests =====

class TestEmptyProject:
    def test_skipped(self, empty_project):
        checker = ModelConsistencyChecker(empty_project)
        result = checker.check_all()
        assert result.get('skipped', True) or len(result.get('issues', [])) == 0


class TestBasicInit:
    def test_layer0_data_stored(self, empty_project):
        checker = ModelConsistencyChecker(empty_project, layer0_data={'x': 1})
        assert checker._layer0_data == {'x': 1}


class TestConsistentModels:
    def test_no_issues(self, project_consistent_model):
        checker = ModelConsistencyChecker(project_consistent_model)
        result = checker.check_all()
        assert len(result.get('issues', [])) == 0


class TestInconsistentModels:
    def test_detects_variable_mismatch(self, project_inconsistent_model):
        checker = ModelConsistencyChecker(project_inconsistent_model)
        result = checker.check_all()
        all_items = result.get('issues', []) + result.get('warnings', [])
        assert len(all_items) >= 1, f'未检测到变量集不一致，结果: {result}'


class TestSingleModel:
    def test_no_comparison(self, project_single_model):
        checker = ModelConsistencyChecker(project_single_model)
        result = checker.check_all()
        # 单模型不触发对比
        assert len(result.get('issues', [])) == 0
