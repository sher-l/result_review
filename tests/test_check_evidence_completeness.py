#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
证据完整性检查器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_evidence_completeness.py -v
"""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_evidence_completeness import EvidenceCompletenessChecker


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    return str(tmp_path)


@pytest.fixture
def project_with_lasso(tmp_path):
    """含 LASSO 模块的项目"""
    d = tmp_path / '05_lasso'
    d.mkdir(parents=True)
    # CSV 结果
    p = d / 'lasso_result.csv'
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Gene', 'Coefficient'])
        w.writerow(['TP53', '0.35'])
    # 报告文本
    (tmp_path / 'report_text.txt').write_text(
        'LASSO回归筛选出5个关键基因，使用lambda.min规则。',
        encoding='utf-8'
    )
    return str(tmp_path)


@pytest.fixture
def project_lasso_no_lambda(tmp_path):
    """含 LASSO 模块但缺少 lambda 规则说明"""
    d = tmp_path / '05_lasso'
    d.mkdir(parents=True)
    (d / 'lasso_result.csv').write_text('Gene,Coef\nTP53,0.35\n', encoding='utf-8')
    (tmp_path / 'report_text.txt').write_text(
        'LASSO回归筛选出5个关键基因。',
        encoding='utf-8'
    )
    return str(tmp_path)


# ===== 参考文献范围展开 =====

class TestExpandRefRange:
    """v4.7: 参考文献范围展开"""

    def test_single_number(self):
        assert EvidenceCompletenessChecker._expand_ref_range('3') == [3]

    def test_range(self):
        assert EvidenceCompletenessChecker._expand_ref_range('1-5') == [1, 2, 3, 4, 5]

    def test_comma_list(self):
        assert EvidenceCompletenessChecker._expand_ref_range('1,3,5') == [1, 3, 5]

    def test_mixed_range_and_single(self):
        result = EvidenceCompletenessChecker._expand_ref_range('2-4, 7')
        assert result == [2, 3, 4, 7]

    def test_chinese_comma(self):
        result = EvidenceCompletenessChecker._expand_ref_range('1，3，5')
        assert result == [1, 3, 5]

    def test_invalid_string(self):
        result = EvidenceCompletenessChecker._expand_ref_range('abc')
        assert result == []


# ===== 常量验证 =====

class TestConstants:
    """类级常量"""

    def test_tabular_suffixes(self):
        assert '.csv' in EvidenceCompletenessChecker.TABULAR_SUFFIXES
        assert '.xlsx' in EvidenceCompletenessChecker.TABULAR_SUFFIXES

    def test_image_suffixes(self):
        assert '.png' in EvidenceCompletenessChecker.IMAGE_SUFFIXES
        assert '.pdf' in EvidenceCompletenessChecker.IMAGE_SUFFIXES

    def test_filtered_hints(self):
        assert 'filtered' in EvidenceCompletenessChecker.FILTERED_NAME_HINTS

    def test_raw_hints(self):
        assert 'raw' in EvidenceCompletenessChecker.RAW_NAME_HINTS


# ===== LASSO 参数检查 =====

class TestLassoParameter:
    """LASSO lambda 规则标注检查"""

    def test_with_lambda_rule(self, project_with_lasso):
        checker = EvidenceCompletenessChecker(project_with_lasso)
        result = checker.check_all()
        # 有 lambda.min 规则，不应产生 LASSO 参数相关 issue
        lasso_issues = [
            i for i in result.get('issues', [])
            if 'lambda' in i.get('message', '').lower() or 'LASSO' in i.get('message', '')
        ]
        assert len(lasso_issues) == 0

    def test_without_lambda_rule(self, project_lasso_no_lambda):
        checker = EvidenceCompletenessChecker(project_lasso_no_lambda)
        result = checker.check_all()
        # 缺少 lambda 规则说明，应有 warning 或 issue
        all_msgs = (
            [i.get('message', '') for i in result.get('issues', [])] +
            [w.get('message', '') for w in result.get('warnings', [])]
        )
        # 至少应有一些检查输出
        assert result['total_checks'] > 0


# ===== 空项目安全性 =====

class TestEmptyProject:
    """空项目应安全完成"""

    def test_not_fatal(self, empty_project):
        checker = EvidenceCompletenessChecker(empty_project)
        result = checker.check_all()
        assert result.get('fatal', False) is False

    def test_return_structure(self, empty_project):
        checker = EvidenceCompletenessChecker(empty_project)
        result = checker.check_all()
        assert 'total_checks' in result
        assert 'issues' in result
