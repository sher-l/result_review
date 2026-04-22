#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CSV-报告交叉验证检查器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_report_data_match.py -v
"""

import csv
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_report_data_match import ReportDataMatchChecker


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    return str(tmp_path)


@pytest.fixture
def project_with_deg_report(tmp_path):
    """DEG CSV + 报告"""
    d = tmp_path / '01_limma'
    d.mkdir()
    p = d / 'DEGs_all.csv'
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Gene', 'logFC', 'PValue'])
        for i in range(150):
            w.writerow([f'GENE{i}', f'{i * 0.1}', '0.001'])
    (tmp_path / 'report_text.txt').write_text(
        '差异表达分析共筛选出150个差异表达基因（DEGs）。'
        '其中上调基因75个，下调基因75个。结果通过火山图和热图展示，'
        '并进一步进行GO和KEGG富集分析验证差异基因的生物学功能。',
        encoding='utf-8'
    )
    return str(tmp_path)


# ===== CSV 行计数 =====

class TestCSVRowCounting:
    """v4.7: 使用 csv.reader 替代 split"""

    def test_simple_csv(self, tmp_path):
        p = tmp_path / 'test.csv'
        p.write_text('Gene,logFC\nTP53,2.1\nBRCA1,-1.5\n', encoding='utf-8')
        checker = ReportDataMatchChecker(str(tmp_path))
        count = checker._count_csv_data_rows(p)
        assert count == 2  # 不含表头

    def test_multiline_quoted_field(self, tmp_path):
        """引号内换行不应多计一行"""
        p = tmp_path / 'test.csv'
        content = '"Gene","Desc"\n"TP53","tumor\nprotein"\n"BRCA1","breast\ncancer"\n'
        p.write_text(content, encoding='utf-8')
        checker = ReportDataMatchChecker(str(tmp_path))
        count = checker._count_csv_data_rows(p)
        assert count == 2  # 2 行数据

    def test_empty_csv(self, tmp_path):
        p = tmp_path / 'test.csv'
        p.write_text('Gene,logFC\n', encoding='utf-8')
        checker = ReportDataMatchChecker(str(tmp_path))
        count = checker._count_csv_data_rows(p)
        assert count == 0


# ===== ML 指标去重 =====

class TestMLMetricsRemoved:
    """v4.7: _check_ml_metrics 已从 check_all 移除"""

    def test_check_all_no_ml_metrics(self):
        import inspect
        src = inspect.getsource(ReportDataMatchChecker.check_all)
        assert '_check_ml_metrics' not in src

    def test_total_checks_is_five(self, project_with_deg_report):
        checker = ReportDataMatchChecker(project_with_deg_report)
        result = checker.check_all()
        assert result['total_checks'] == 5


# ===== 空项目安全性 =====

class TestEmptyProject:
    """空项目"""

    def test_not_fatal(self, empty_project):
        checker = ReportDataMatchChecker(empty_project)
        result = checker.check_all()
        # 空项目可能 skipped 或无 fatal
        assert result.get('skipped', True) or not result.get('fatal', False)

    def test_return_structure(self, empty_project):
        checker = ReportDataMatchChecker(empty_project)
        result = checker.check_all()
        assert 'issues' in result
        # 空项目 skipped=True 时无 total_checks
        assert result.get('skipped') is True or 'total_checks' in result
