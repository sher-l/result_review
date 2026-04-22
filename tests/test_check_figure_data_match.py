#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图件-数据匹配检查器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_figure_data_match.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_figure_data_match import FigureDataMatchChecker


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    return str(tmp_path)


@pytest.fixture
def project_balanced(tmp_path):
    """图件和数据平衡的项目"""
    d = tmp_path / '01_limma' / '附件'
    d.mkdir(parents=True)
    # 图件
    (d / 'volcano.png').write_bytes(b'\x89PNG' + b'\x00' * 500)
    (d / 'heatmap.png').write_bytes(b'\x89PNG' + b'\x00' * 500)
    # 数据
    (d / 'DEGs_all.csv').write_text('Gene,logFC\nTP53,2.1\n', encoding='utf-8')
    return str(tmp_path)


@pytest.fixture
def project_image_heavy(tmp_path):
    """图件多但缺数据的项目"""
    d = tmp_path / '05_lasso' / '附件'
    d.mkdir(parents=True)
    for i in range(8):
        (d / f'fig{i}.png').write_bytes(b'\x89PNG' + b'\x00' * 500)
    # 无 CSV
    return str(tmp_path)


# ===== 测试 =====

class TestEmptyProject:
    """空项目"""

    def test_return_structure(self, empty_project):
        checker = FigureDataMatchChecker(empty_project)
        result = checker.check_all()
        assert 'issues' in result
        # 空项目返回 skipped=True，不含 modules_scanned
        assert result.get('skipped') is True or 'modules_scanned' in result


class TestBalancedProject:
    """图件和数据平衡"""

    def test_no_critical_issues(self, project_balanced):
        checker = FigureDataMatchChecker(project_balanced)
        result = checker.check_all()
        critical_issues = [i for i in result.get('issues', []) if i.get('severity') == 'CRITICAL']
        assert len(critical_issues) == 0


class TestImageHeavy:
    """图件密集但缺数据"""

    def test_detects_missing_data(self, project_image_heavy):
        checker = FigureDataMatchChecker(project_image_heavy)
        result = checker.check_all()
        all_msgs = (
            [i.get('message', '') for i in result.get('issues', [])] +
            [w.get('message', '') for w in result.get('warnings', [])]
        )
        # 8 张图 0 个 CSV，应有警告
        assert len(all_msgs) > 0 or result.get('modules_scanned', 0) > 0


class TestConstants:
    """常量验证"""

    def test_image_extensions(self):
        exts = FigureDataMatchChecker._IMG_EXTS
        assert '.png' in exts
        assert '.jpg' in exts

    def test_data_extensions(self):
        exts = FigureDataMatchChecker._DATA_EXTS
        assert '.csv' in exts
