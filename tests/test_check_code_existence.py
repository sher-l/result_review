#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
代码存在性检查器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_code_existence.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_code_existence import CodeExistenceChecker


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    return str(tmp_path)


@pytest.fixture
def project_with_code(tmp_path):
    """含代码文件的项目"""
    code_dir = tmp_path / 'CODE'
    code_dir.mkdir()
    (code_dir / 'r-01_limma.R').write_text('library(limma)\n', encoding='utf-8')
    (code_dir / 'r-02_GO.R').write_text('library(clusterProfiler)\n', encoding='utf-8')
    # 模块目录
    (tmp_path / '01_limma').mkdir()
    (tmp_path / '02_GO').mkdir()
    return str(tmp_path)


@pytest.fixture
def project_no_code(tmp_path):
    """无代码文件"""
    (tmp_path / '01_limma').mkdir()
    (tmp_path / '01_limma' / 'result.csv').write_text('Gene,logFC\nTP53,2.1\n', encoding='utf-8')
    return str(tmp_path)


# ===== 测试 =====

class TestEmptyProject:
    """空项目"""

    def test_return_structure(self, empty_project):
        checker = CodeExistenceChecker(empty_project)
        result = checker.check_all()
        assert 'issues' in result
        assert 'total_checks' in result
        assert result['total_checks'] == 1


class TestWithCode:
    """有代码文件"""

    def test_no_code_missing_issue(self, project_with_code):
        checker = CodeExistenceChecker(project_with_code)
        result = checker.check_all()
        # 有代码，不应有"缺代码"的 CRITICAL issue
        code_issues = [i for i in result.get('issues', []) if '代码' in i.get('message', '') or 'code' in i.get('message', '').lower()]
        assert len(code_issues) == 0


class TestNoCode:
    """无代码文件"""

    def test_detects_missing_code(self, project_no_code):
        checker = CodeExistenceChecker(project_no_code)
        result = checker.check_all()
        # 应检测到缺少代码
        assert result['failed_checks'] > 0 or len(result.get('issues', [])) > 0 or len(result.get('warnings', [])) > 0
        code_warnings = [w for w in result.get('warnings', []) if w.get('category') == '代码缺失']
        assert code_warnings
        assert code_warnings[0]['severity'] == 'WARNING'
        assert 'CRITICAL' not in {i.get('severity') for i in result.get('issues', []) if i.get('category') == '代码缺失'}


class TestImageOnlyModuleRemoved:
    """v4.7: _check_image_only_modules 已从 check_all 移除"""

    def test_not_in_check_all(self):
        import inspect
        src = inspect.getsource(CodeExistenceChecker.check_all)
        assert '_check_image_only_modules' not in src


class TestConstants:
    """常量验证"""

    def test_code_extensions(self):
        exts = CodeExistenceChecker._CODE_EXTS
        assert '.r' in exts
        assert '.py' in exts
        assert '.ipynb' in exts

    def test_module_pattern(self):
        """模块匹配模式现在在 BaseProjectChecker.find_modules() 中"""
        import re
        pat = re.compile(r'^\d{2}[_\-]')
        assert pat.match('01_limma')
        assert pat.match('10_Cibersort')
        assert not pat.match('CODE')
        assert not pat.match('report_text.txt')

    def test_vis_only_keywords(self):
        kw = CodeExistenceChecker._VIS_ONLY_KEYWORDS
        assert any('qc' in k for k in kw)
        assert any('umap' in k for k in kw)
