#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
可视化阈值一致性检查器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_visualization_thresholds.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_visualization_thresholds import VisualizationThresholdChecker


# ===== Fixtures =====

@pytest.fixture
def checker(tmp_path):
    return VisualizationThresholdChecker(str(tmp_path))


# ===== 阈值提取测试 =====

class TestExtractPlotThresholds:
    """测试绘图阈值提取"""

    def test_geom_vline_symmetric(self, checker):
        code = 'geom_vline(xintercept = c(-1, 1), linetype = "dashed")'
        result = checker._extract_plot_thresholds(code)
        assert result.get('logfc') == 1.0

    def test_geom_hline(self, checker):
        code = 'geom_hline(yintercept = c(1.3))'
        result = checker._extract_plot_thresholds(code)
        assert result.get('pvalue') == 1.3

    def test_plt_axvline(self, checker):
        code = 'plt.axvline(x=-1.5)\nplt.axvline(x=1.5)'
        result = checker._extract_plot_thresholds(code)
        assert result.get('logfc') == 1.5

    def test_threshold_variable(self, checker):
        code = 'threshold = 2.0'
        result = checker._extract_plot_thresholds(code)
        assert result.get('logfc') == 2.0

    def test_no_thresholds(self, checker):
        code = 'plot(x, y)\nprint("hello")'
        result = checker._extract_plot_thresholds(code)
        assert not result


class TestExtractFilterThresholds:
    """测试筛选标准提取"""

    def test_logfc_cutoff_r(self, checker):
        code = 'logFC_cutoff <- 1.0'
        result = checker._extract_filter_thresholds(code)
        assert result.get('logfc') == 1.0

    def test_logfc_python(self, checker):
        code = 'log2fc_cutoff = 0.585'
        result = checker._extract_filter_thresholds(code)
        assert result.get('logfc') == 0.585

    def test_pvalue_cutoff_r(self, checker):
        code = 'pvalue_cutoff <- 0.05'
        result = checker._extract_filter_thresholds(code)
        assert result.get('pvalue') == 0.05

    def test_padj_filter(self, checker):
        # 正则要求 <= 或 >= 运算符
        code = 'padj <= 0.01'
        result = checker._extract_filter_thresholds(code)
        assert result.get('pvalue') == 0.01


class TestParseVector:
    """测试 R 向量解析"""

    def test_simple_vector(self, checker):
        assert checker._parse_vector('c(-1, 1)') == [-1.0, 1.0]

    def test_single_value(self, checker):
        assert checker._parse_vector('0.05') == [0.05]

    def test_decimal_vector(self, checker):
        result = checker._parse_vector('-0.585, 0.585')
        assert len(result) == 2
        assert abs(result[0] - (-0.585)) < 1e-6

    def test_empty_string(self, checker):
        assert checker._parse_vector('') is None


class TestThresholdComparison:
    """测试阈值比较"""

    def test_mismatch_detected(self, tmp_path):
        checker = VisualizationThresholdChecker(str(tmp_path))
        fake_file = tmp_path / 'test.R'
        fake_file.write_text('# test', encoding='utf-8')
        checker._compare_logfc_thresholds(fake_file, 1.0, 0.5)
        assert len(checker.issues) == 1
        assert checker.issues[0]['type'] == 'logfc_mismatch'

    def test_match_no_issue(self, tmp_path):
        checker = VisualizationThresholdChecker(str(tmp_path))
        fake_file = tmp_path / 'test.R'
        fake_file.write_text('# test', encoding='utf-8')
        checker._compare_logfc_thresholds(fake_file, 1.0, 1.0)
        assert len(checker.issues) == 0

    def test_pvalue_mismatch(self, tmp_path):
        checker = VisualizationThresholdChecker(str(tmp_path))
        fake_file = tmp_path / 'test.R'
        fake_file.write_text('# test', encoding='utf-8')
        checker._compare_pvalue_thresholds(fake_file, 0.05, 0.01)
        assert len(checker.issues) == 1


class TestNoCodeDirectory:
    """无代码目录时应安全返回"""

    def test_empty_project(self, tmp_path):
        checker = VisualizationThresholdChecker(str(tmp_path))
        result = checker.check_code_files()
        assert result['total_files'] == 0
        assert len(result['warnings']) == 1
