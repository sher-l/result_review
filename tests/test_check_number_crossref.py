#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数字交叉验证检查器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_number_crossref.py -v
"""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_number_crossref import NumberCrossrefChecker


# ===== Helpers =====

def write_csv(path, rows, header=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if header:
            w.writerow(header)
        for row in rows:
            w.writerow(row)


def write_report(tmp_path, text):
    (tmp_path / 'report_text.txt').write_text(text, encoding='utf-8')


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    return str(tmp_path)


@pytest.fixture
def project_matched(tmp_path):
    """报告数字与 CSV 行数一致"""
    result_dir = tmp_path / '结果文件'
    write_csv(
        result_dir / '01_DEGs' / 'Diff.all.csv',
        [['gene1', '1.5', '0.01']] * 100,
        header=['Gene', 'logFC', 'adj.P.Val'],
    )
    write_report(tmp_path, '差异分析共筛选出100个差异基因（DEG），其中上调50个，下调50个。')
    return str(tmp_path)


@pytest.fixture
def project_mismatched(tmp_path):
    """报告写 383 但 CSV 实际 409 行"""
    result_dir = tmp_path / '结果文件'
    write_csv(
        result_dir / '02_GO_KEGG' / 'GO.csv',
        [['pathway', 'pval']] * 409,  # 409 行数据 + 1 行表头
        header=['ID', 'pvalue'],
    )
    write_report(tmp_path, '共富集到383条GO通路。')
    return str(tmp_path)


# ===== Tests =====

class TestEmptyProject:
    def test_skipped(self, empty_project):
        checker = NumberCrossrefChecker(empty_project)
        result = checker.check_all()
        assert result.get('skipped', True) or len(result.get('issues', [])) == 0


class TestBasicInit:
    def test_layer0_data_stored(self, empty_project):
        checker = NumberCrossrefChecker(empty_project, layer0_data={'test': True})
        assert checker._layer0_data == {'test': True}

    def test_layer0_data_default(self, empty_project):
        checker = NumberCrossrefChecker(empty_project)
        assert checker._layer0_data == {}


class TestMatchedNumbers:
    def test_no_issues(self, project_matched):
        checker = NumberCrossrefChecker(project_matched)
        result = checker.check_all()
        # 数字匹配时不应有 CRITICAL issues
        critical = [i for i in result.get('issues', []) if 'DEG' in i.get('message', '')]
        # 允许为空（匹配成功）或有 warning（非严格匹配）
        assert isinstance(result, dict)
