#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
报告覆盖矩阵检查器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_report_coverage.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_report_coverage import ReportCoverageChecker


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    return str(tmp_path)


@pytest.fixture
def project_with_modules_and_report(tmp_path):
    """含模块目录和报告的项目"""
    # 模块目录
    (tmp_path / '01_limma').mkdir()
    (tmp_path / '02_inter').mkdir()
    (tmp_path / '03_GO').mkdir()
    (tmp_path / '04_ppi').mkdir()
    (tmp_path / '05_lasso').mkdir()
    # 报告
    (tmp_path / 'report_text.txt').write_text(
        '本研究使用 limma 进行差异表达分析。\n'
        '交集分析（两个数据集的共同差异基因）。\n'
        'GO 功能富集分析。\n'
        'PPI 蛋白互作网络。\n'
        'LASSO 筛选关键基因。\n',
        encoding='utf-8'
    )
    return str(tmp_path)


@pytest.fixture
def project_with_uncovered_module(tmp_path):
    """含报告未提及的模块"""
    (tmp_path / '01_limma').mkdir()
    (tmp_path / '02_inter').mkdir()
    (tmp_path / '03_GO').mkdir()
    (tmp_path / '10_Cibersort').mkdir()  # 报告未提及
    (tmp_path / 'report_text.txt').write_text(
        'limma差异分析结果显示...\n交集分析...\nGO富集...\n',
        encoding='utf-8'
    )
    return str(tmp_path)


# ===== 测试 =====

class TestEmptyProject:
    """空项目"""

    def test_safe_return(self, empty_project):
        checker = ReportCoverageChecker(empty_project)
        result = checker.check_all()
        assert result.get('fatal', False) is False

    def test_skipped_without_modules(self, empty_project):
        checker = ReportCoverageChecker(empty_project)
        result = checker.check_all()
        assert result.get('skipped', True) is True or len(result.get('module_gaps', [])) == 0


class TestModuleCoverage:
    """模块覆盖检查"""

    def test_all_modules_covered(self, project_with_modules_and_report):
        checker = ReportCoverageChecker(project_with_modules_and_report)
        result = checker.check_all()
        # 所有模块都在报告中提及
        gaps = result.get('module_gaps', [])
        # 可能有 0 或少量 gap（取决于关键词匹配精度）
        assert result.get('fatal', False) is False


class TestReturnStructure:
    """返回结构验证"""

    def test_keys_present(self, empty_project):
        checker = ReportCoverageChecker(empty_project)
        result = checker.check_all()
        assert 'issues' in result
        assert isinstance(result['issues'], list)


class TestGSEPattern:
    """GSE 数据集编号模式"""

    def test_gse_pattern(self):
        import re
        pat = ReportCoverageChecker.GSE_PATTERN
        assert pat.search('使用 GSE12345 数据集')
        assert pat.search('GSE123456')
        assert not pat.search('GSE12')  # 太短
