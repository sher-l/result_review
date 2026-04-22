#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
中文校对检查器单元测试

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_chinese_proofreading.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_chinese_proofreading import ChineseProofreadingChecker


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    """空项目（无报告文本）"""
    return str(tmp_path)


@pytest.fixture
def project_with_report(tmp_path):
    """含报告文本的项目（通过 mock 注入）"""
    def _make(text: str) -> tuple:
        """返回 (project_path, text)"""
        return str(tmp_path), text
    return _make


def _make_checker(project_path: str, text: str) -> ChineseProofreadingChecker:
    """创建 checker 并 mock load_report_text 返回指定文本"""
    checker = ChineseProofreadingChecker(project_path)
    checker.load_report_text = lambda: text
    return checker


# ===== 基本功能 =====

class TestBasicBehavior:
    """基本行为测试"""

    def test_no_report_text_returns_skipped(self, empty_project):
        checker = ChineseProofreadingChecker(empty_project)
        result = checker.check_all()
        assert result['skipped'] is True
        assert result['issues'] == []

    def test_clean_text_returns_no_issues(self, project_with_report):
        path, text = project_with_report("免疫细胞浸润分析表明转录组数据正常。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert result['issues'] == []

    def test_return_structure(self, project_with_report):
        path, text = project_with_report("正常文本")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert 'issues' in result
        assert 'warnings' in result
        assert 'total_checks' in result
        assert 'failed_checks' in result


# ===== 缺字检测 =====

class TestMissingChars:
    """缺字检测"""

    def test_detect_missing_mian(self, project_with_report):
        """检测「疫细胞浸润」→「免疫细胞浸润」"""
        path, text = project_with_report("本研究分析了疫细胞浸润情况。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert len(result['issues']) == 1
        assert '免疫细胞浸润' in result['issues'][0]['message']

    def test_detect_missing_zhuan(self, project_with_report):
        """检测「录组」→「转录组」"""
        path, text = project_with_report("我们对录组数据进行了分析。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert len(result['issues']) == 1
        assert '转录组' in result['issues'][0]['message']

    def test_detect_missing_ji(self, project_with_report):
        """检测「因表达」→「基因表达」"""
        path, text = project_with_report("因表达水平显著下调。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert len(result['issues']) == 1
        assert '基因表达' in result['issues'][0]['message']

    def test_correct_form_present_no_issue(self, project_with_report):
        """正确形式存在于同一行时不报"""
        path, text = project_with_report("免疫细胞浸润分析中疫细胞浸润结果一致。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert result['issues'] == []

    def test_multiple_issues_on_different_lines(self, project_with_report):
        text = "疫细胞浸润分析。\n录组数据分析。"
        path, text = project_with_report(text)
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert len(result['issues']) == 2

    def test_issue_evidence_structure(self, project_with_report):
        path, text = project_with_report("疫逃逸机制研究。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert len(result['issues']) == 1
        evidence = result['issues'][0]['evidence']
        assert 'line' in evidence
        assert 'context' in evidence
        assert 'wrong' in evidence
        assert 'correct' in evidence


# ===== 排除上下文 =====

class TestExcludeContexts:
    """排除上下文测试"""

    def test_boxplot_not_flagged(self, project_with_report):
        """箱线图不应误报为缺「列」"""
        path, text = project_with_report("图1为箱线图展示各组表达差异。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert result['issues'] == []

    def test_line_chart_not_flagged(self, project_with_report):
        """折线图不应误报"""
        path, text = project_with_report("图2为折线图展示趋势变化。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert result['issues'] == []

    def test_curve_not_flagged(self, project_with_report):
        """曲线图不应误报"""
        path, text = project_with_report("生存曲线图展示OS差异。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert result['issues'] == []

    def test_breast_cancer_not_flagged(self, project_with_report):
        """乳腺癌不应误报「腺癌」"""
        path, text = project_with_report("乳腺癌患者的预后分析。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert result['issues'] == []

    def test_thyroid_cancer_not_flagged(self, project_with_report):
        """甲状腺癌不应误报"""
        path, text = project_with_report("甲状腺癌细胞系的转录组分析。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert result['issues'] == []

    def test_prostate_cancer_not_flagged(self, project_with_report):
        """前列腺癌不应误报"""
        path, text = project_with_report("前列腺癌的分子标志物研究。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert result['issues'] == []

    def test_standalone_xiantu_flagged(self, project_with_report):
        """独立的「线图」应当报错（列线图缺「列」）"""
        path, text = project_with_report("我们构建了线图预测模型。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert len(result['issues']) == 1
        assert '列线图' in result['issues'][0]['message']


# ===== 同音错字检测 =====

class TestHomophones:
    """同音错字检测"""

    def test_detect_jushi_xibao(self, project_with_report):
        """检测「局势细胞」→「巨噬细胞」"""
        path, text = project_with_report("局势细胞浸润水平较高。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert len(result['issues']) == 1
        assert '巨噬细胞' in result['issues'][0]['message']

    def test_detect_wangluo_wrong(self, project_with_report):
        """「网路药理学」→「网络药理学」"""
        path, text = project_with_report("本研究采用网路药理学方法。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert len(result['issues']) == 1
        assert '网络药理学' in result['issues'][0]['message']

    def test_detect_fenzi_duijie(self, project_with_report):
        """「分子对结」→「分子对接」"""
        path, text = project_with_report("分子对结结果显示。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert len(result['issues']) == 1
        assert '分子对接' in result['issues'][0]['message']

    def test_detect_shengcun_fenxi(self, project_with_report):
        """「生存分折」→「生存分析」"""
        path, text = project_with_report("生存分折结果如下。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert len(result['issues']) == 1
        assert '生存分析' in result['issues'][0]['message']

    def test_detect_tie_siwang(self, project_with_report):
        """「铁失亡」→「铁死亡」"""
        path, text = project_with_report("铁失亡相关基因的表达情况。")
        checker = _make_checker(path, text)
        result = checker.check_all()
        assert len(result['issues']) == 1
        assert '铁死亡' in result['issues'][0]['message']


# ===== 降级模式 =====

class TestDegradedMode:
    """无报告文本场景"""

    def test_skipped_when_no_report(self, empty_project):
        checker = ChineseProofreadingChecker(empty_project)
        result = checker.check_all()
        assert result['skipped'] is True
        assert result['issues'] == []
        assert 'reason' in result

    def test_inherits_base_project_checker(self):
        from base_project_checker import BaseProjectChecker
        assert issubclass(ChineseProofreadingChecker, BaseProjectChecker)
