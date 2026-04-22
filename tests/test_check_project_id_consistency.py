#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
项目编号一致性检查器单元测试（P0级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_project_id_consistency.py -v
"""

import sys
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_project_id_consistency import ProjectIDChecker


# ===== Fixtures =====

@pytest.fixture
def project_with_correct_id(tmp_path):
    """项目编号正确的项目"""
    proj = tmp_path / '26YLM076F'
    proj.mkdir()
    code_dir = proj / 'CODE'
    code_dir.mkdir()

    r_file = code_dir / 'r-01_Rawdata.R'
    r_file.write_text(
        'setwd("D:/projects/26YLM076F/01_Rawdata")\n'
        'data <- read.csv("GSE49972.csv")\n'
        '# 项目 26YLM076F 数据处理\n',
        encoding='utf-8'
    )
    return str(proj)


@pytest.fixture
def project_with_wrong_setwd(tmp_path):
    """setwd 中使用了错误编号"""
    proj = tmp_path / '26YLM076F'
    proj.mkdir()
    code_dir = proj / 'CODE'
    code_dir.mkdir()

    r_file = code_dir / 'r-01_Rawdata.R'
    r_file.write_text(
        'setwd("D:/projects/25YLC105F/01_Rawdata")\n'
        'data <- read.csv("GSE49972.csv")\n',
        encoding='utf-8'
    )
    return str(proj)


@pytest.fixture
def project_with_wrong_mention(tmp_path):
    """代码中提及了其他项目编号"""
    proj = tmp_path / '26YLM076F'
    proj.mkdir()
    code_dir = proj / 'CODE'
    code_dir.mkdir()

    r_file = code_dir / 'analysis.R'
    r_file.write_text(
        'setwd("D:/projects/26YLM076F/data")\n'
        '# 注意：这段代码复制自 25YHB656F\n'
        'x <- 42\n',
        encoding='utf-8'
    )
    return str(proj)


@pytest.fixture
def project_no_code_dir(tmp_path):
    """无代码目录 — 只有根目录"""
    proj = tmp_path / '26YLM076F'
    proj.mkdir()
    return str(proj)


@pytest.fixture
def project_explicit_id(tmp_path):
    """使用显式 project_id 参数"""
    proj = tmp_path / 'some_folder'
    proj.mkdir()
    code_dir = proj / 'CODE'
    code_dir.mkdir()

    r_file = code_dir / 'run.R'
    r_file.write_text(
        'setwd("D:/26YBB010F/data")\n',
        encoding='utf-8'
    )
    return str(proj)


# ===== 测试类 =====

class TestProjectIDExtraction:
    """测试项目编号自动提取"""

    def test_extract_from_folder_name(self, project_with_correct_id):
        checker = ProjectIDChecker(project_with_correct_id)
        assert checker.project_id == '26YLM076F'

    def test_explicit_project_id(self, project_explicit_id):
        checker = ProjectIDChecker(project_explicit_id, project_id='26YBB010F')
        assert checker.project_id == '26YBB010F'


class TestCorrectProject:
    """项目编号全部正确的情况"""

    def test_no_errors(self, project_with_correct_id):
        checker = ProjectIDChecker(project_with_correct_id)
        result = checker.check_all_files()
        assert result['fatal'] is False
        assert len(result['issues']) == 0

    def test_returns_project_id(self, project_with_correct_id):
        checker = ProjectIDChecker(project_with_correct_id)
        result = checker.check_all_files()
        assert result['project_id'] == '26YLM076F'

    def test_file_count(self, project_with_correct_id):
        checker = ProjectIDChecker(project_with_correct_id)
        result = checker.check_all_files()
        assert result['total_files'] >= 1


class TestWrongSetwd:
    """setwd 路径中使用错误编号"""

    def test_fatal_on_wrong_setwd(self, project_with_wrong_setwd):
        checker = ProjectIDChecker(project_with_wrong_setwd)
        result = checker.check_all_files()
        assert result['fatal'] is True
        assert result['error_files'] >= 1

    def test_error_contains_wrong_id(self, project_with_wrong_setwd):
        checker = ProjectIDChecker(project_with_wrong_setwd)
        result = checker.check_all_files()
        wrong_ids = [e.get('wrong_id') for e in result['issues']]
        assert '25YLC105F' in wrong_ids


class TestWrongMention:
    """代码中提及其他项目编号"""

    def test_fatal_on_wrong_mention(self, project_with_wrong_mention):
        checker = ProjectIDChecker(project_with_wrong_mention)
        result = checker.check_all_files()
        assert result['fatal'] is True

    def test_detects_copied_id(self, project_with_wrong_mention):
        checker = ProjectIDChecker(project_with_wrong_mention)
        result = checker.check_all_files()
        wrong_ids = [e.get('wrong_id') for e in result['issues']]
        assert '25YHB656F' in wrong_ids


class TestNoCodeDir:
    """无代码目录"""

    def test_no_code_dir_not_fatal(self, project_no_code_dir):
        checker = ProjectIDChecker(project_no_code_dir)
        result = checker.check_all_files()
        assert result['fatal'] is False

    def test_no_code_dir_zero_files(self, project_no_code_dir):
        checker = ProjectIDChecker(project_no_code_dir)
        result = checker.check_all_files()
        assert result['total_files'] == 0


class TestReturnStructure:
    """验证返回结构完整性"""

    def test_all_keys_present(self, project_with_correct_id):
        checker = ProjectIDChecker(project_with_correct_id)
        result = checker.check_all_files()
        for key in ('project_id', 'total_files', 'error_files', 'issues', 'fatal'):
            assert key in result, f'缺少返回字段: {key}'
