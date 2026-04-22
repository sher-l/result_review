#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scRNA QC 单调性检查器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_scrna_qc.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_scrna_qc import ScRNAQCChecker


# ===== Fixtures =====

def make_checker(tmp_path, report_text=None):
    """创建 checker 并可选地写入 report_text.txt"""
    if report_text:
        (tmp_path / 'report_text.txt').write_text(report_text, encoding='utf-8')
    c = ScRNAQCChecker(str(tmp_path))
    return c


# ===== 阶段分类测试 =====

class TestStageClassification:
    """QC 阶段分类"""

    def test_initial_stage(self, tmp_path):
        c = make_checker(tmp_path)
        assert c._classify_stage('初始数据包含 10000 个细胞') in ('initial', 'merged')

    def test_filtered_stage(self, tmp_path):
        c = make_checker(tmp_path)
        assert c._classify_stage('质控过滤后剩余 8000 cells') == 'filtered'

    def test_final_stage(self, tmp_path):
        c = make_checker(tmp_path)
        result = c._classify_stage('最终聚类得到 7500 个 cells')
        # "最终" should map to final or filtered
        assert result in ('final', 'filtered')


# ===== 细胞数提取测试 =====

class TestCellCountExtraction:
    """细胞数提取"""

    def test_chinese_cell_unit(self, tmp_path):
        c = make_checker(tmp_path)
        text = '共 15,234 个细胞通过质控'
        counts = c._extract_cell_counts_with_context(text)
        # 应至少提取到一个计数
        assert len(counts) >= 1

    def test_english_cells(self, tmp_path):
        c = make_checker(tmp_path)
        text = 'After filtering, 8000 cells remained'
        counts = c._extract_cell_counts_with_context(text)
        assert len(counts) >= 1


# ===== 单调性检查 =====

class TestMonotonicity:
    """QC 前后细胞数应单调递减"""

    def test_valid_decreasing(self, tmp_path):
        c = make_checker(tmp_path)
        # _check_monotonicity 接受 3-tuple: (stage, count, context)
        counts = [
            ('initial', 10000, '初始数据包含 10000 个细胞'),
            ('filtered', 8000, '质控后保留 8000 个细胞'),
            ('final', 7500, '最终 7500 个细胞'),
        ]
        c._check_monotonicity(counts)
        # 单调递减无问题
        issue_msgs = [i.get('message', '') for i in c.issues]
        mono_issues = [m for m in issue_msgs if '单调' in m or 'monoton' in m.lower()]
        assert len(mono_issues) == 0

    def test_increasing_triggers_issue(self, tmp_path):
        c = make_checker(tmp_path)
        counts = [
            ('initial', 5000, '初始 5000 个细胞'),
            ('filtered', 8000, '过滤后 8000 个细胞'),  # 异常增长
        ]
        c._check_monotonicity(counts)
        # 应触发问题
        assert len(c.issues) > 0


# ===== 中文细胞类型映射 =====

class TestChineseCellTypeMapping:
    """v4.7 新增：中文→英文细胞类型映射"""

    def test_cn_to_en_dict_exists(self):
        import inspect
        src = inspect.getsource(ScRNAQCChecker)
        assert '_CN_TO_EN' in src

    def test_common_types_covered(self):
        """验证常见中文细胞类型在映射表中"""
        src_code = ScRNAQCChecker.__dict__
        # 在类属性或方法源码中搜索
        import inspect
        src = inspect.getsource(ScRNAQCChecker)
        for cn in ['巨噬细胞', 'T细胞', 'B细胞', 'NK细胞', '成纤维细胞', '内皮细胞']:
            assert cn in src, f'缺少映射: {cn}'


# ===== 空项目安全性 =====

class TestEmptyProject:
    """无报告时应安全跳过"""

    def test_skipped_without_report(self, tmp_path):
        c = ScRNAQCChecker(str(tmp_path))
        result = c.check_all()
        assert result.get('skipped') is True or result.get('fatal') is False
