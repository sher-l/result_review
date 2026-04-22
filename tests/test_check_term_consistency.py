#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
术语主题一致性检查器单元测试（P0级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_term_consistency.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_term_consistency import TermConsistencyChecker, TERM_DATABASE


# ===== Fixtures =====

@pytest.fixture
def kidney_stone_clean(tmp_path):
    """肾结石项目，使用正确术语"""
    code_dir = tmp_path / 'project_code'
    code_dir.mkdir()

    (code_dir / 'r-01_DEGs.R').write_text(
        'group <- factor(c("Disease","Control","Disease","Control"))\n'
        'plaque_data <- read.csv("Randall_plaque.csv")\n',
        encoding='utf-8'
    )
    return tmp_path, code_dir


@pytest.fixture
def kidney_stone_with_tumor(tmp_path):
    """肾结石项目，包含癌症术语（FATAL）"""
    code_dir = tmp_path / 'project_code'
    code_dir.mkdir()

    (code_dir / 'r-01_DEGs.R').write_text(
        'group <- factor(c("Tumor","Normal","Tumor","Normal"))\n'
        'deg_results <- FindMarkers(obj, ident.1 = "Tumor")\n',
        encoding='utf-8'
    )
    return tmp_path, code_dir


@pytest.fixture
def cardio_clean(tmp_path):
    """心血管项目，使用正确术语"""
    code_dir = tmp_path / 'project_code'
    code_dir.mkdir()

    (code_dir / 'analysis.R').write_text(
        'group <- c("Case","Control","Case","Control")\n'
        'cardiac_data <- load("Myocardial_data.RData")\n',
        encoding='utf-8'
    )
    return tmp_path, code_dir


@pytest.fixture
def cardio_with_tumor(tmp_path):
    """心血管项目，包含癌症术语（FATAL）"""
    code_dir = tmp_path / 'project_code'
    code_dir.mkdir()

    (code_dir / 'analysis.R').write_text(
        'group <- c("Tumor","Normal","Tumor","Normal")\n',
        encoding='utf-8'
    )
    return tmp_path, code_dir


@pytest.fixture
def empty_code_dir(tmp_path):
    """空的代码目录"""
    code_dir = tmp_path / 'code'
    code_dir.mkdir()
    return tmp_path, code_dir


# ===== 测试类 =====

class TestSupportedTypes:
    """测试支持的项目类型"""

    def test_known_types(self):
        for ptype in TERM_DATABASE:
            checker = TermConsistencyChecker('/tmp/fake', ptype)
            assert checker.project_type == ptype

    def test_unknown_type_skips_gracefully(self, tmp_path):
        """未知类型不崩溃，check_code_files 返回 skipped"""
        checker = TermConsistencyChecker(str(tmp_path), '天文学')
        result = checker.check_code_files()
        assert result.get('skipped') is True
        assert result['fatal'] is False


class TestKidneyStoneTerm:
    """肾结石项目术语检查"""

    def test_correct_terms_no_fatal(self, kidney_stone_clean):
        proj, code_dir = kidney_stone_clean
        checker = TermConsistencyChecker(str(proj), '肾结石')
        result = checker.check_code_files(str(code_dir))
        assert result['fatal'] is False
        assert len(result['issues']) == 0

    def test_tumor_term_is_fatal(self, kidney_stone_with_tumor):
        proj, code_dir = kidney_stone_with_tumor
        checker = TermConsistencyChecker(str(proj), '肾结石')
        result = checker.check_code_files(str(code_dir))
        assert result['fatal'] is True
        fatal_entries = [e for e in result['issues'] if e.get('severity') == 'FATAL']
        assert len(fatal_entries) > 0

    def test_wrong_term_names(self, kidney_stone_with_tumor):
        proj, code_dir = kidney_stone_with_tumor
        checker = TermConsistencyChecker(str(proj), '肾结石')
        result = checker.check_code_files(str(code_dir))
        wrong_terms = [e.get('term') for e in result['issues']]
        assert any(t in ('Tumor', 'Normal') for t in wrong_terms)


class TestCardioTerm:
    """心血管项目术语检查"""

    def test_correct_terms_no_fatal(self, cardio_clean):
        proj, code_dir = cardio_clean
        checker = TermConsistencyChecker(str(proj), '心血管')
        result = checker.check_code_files(str(code_dir))
        assert result['fatal'] is False

    def test_tumor_term_is_fatal(self, cardio_with_tumor):
        proj, code_dir = cardio_with_tumor
        checker = TermConsistencyChecker(str(proj), '心血管')
        result = checker.check_code_files(str(code_dir))
        assert result['fatal'] is True


class TestIBDTerm:
    """IBD 项目术语检查"""

    def test_correct_ibd_terms(self, tmp_path):
        code_dir = tmp_path / 'code'
        code_dir.mkdir()
        (code_dir / 'analysis.R').write_text(
            'group <- factor(c("Disease","Control","Inflamed","Non-inflamed"))\n'
            'uc_data <- read.csv("UC_DEGs.csv")\n',
            encoding='utf-8'
        )
        checker = TermConsistencyChecker(str(tmp_path), 'IBD')
        result = checker.check_code_files(str(code_dir))
        assert result['fatal'] is False

    def test_tumor_in_ibd_fatal(self, tmp_path):
        code_dir = tmp_path / 'code'
        code_dir.mkdir()
        (code_dir / 'run.R').write_text(
            'group <- c("Tumor","Normal")\n',
            encoding='utf-8'
        )
        checker = TermConsistencyChecker(str(tmp_path), 'IBD')
        result = checker.check_code_files(str(code_dir))
        assert result['fatal'] is True
        fatal_entries = [e for e in result['issues'] if e.get('severity') == 'FATAL']
        assert len(fatal_entries) > 0

    def test_cancer_in_ibd_fatal(self, tmp_path):
        code_dir = tmp_path / 'code'
        code_dir.mkdir()
        (code_dir / 'run.R').write_text(
            'group <- ifelse(sample_type == "Cancer", "case", "ctrl")\n',
            encoding='utf-8'
        )
        checker = TermConsistencyChecker(str(tmp_path), 'IBD')
        result = checker.check_code_files(str(code_dir))
        assert result['fatal'] is True


class TestEmptyProject:
    """空项目 / 无代码文件"""

    def test_empty_dir_not_fatal(self, empty_code_dir):
        proj, code_dir = empty_code_dir
        checker = TermConsistencyChecker(str(proj), '癌症')
        result = checker.check_code_files(str(code_dir))
        assert result['fatal'] is False
        assert result['total_files'] == 0

    def test_nonexistent_dir_not_fatal(self, tmp_path):
        checker = TermConsistencyChecker(str(tmp_path), '癌症')
        result = checker.check_code_files(str(tmp_path / 'nonexistent'))
        assert result['fatal'] is False


class TestReportText:
    """测试 check_report_text 方法"""

    def test_clean_text_no_fatal(self):
        checker = TermConsistencyChecker('/tmp/fake', '肾结石')
        result = checker.check_report_text(
            '本研究分析了 Disease 与 Control 组的 Randall plaque 差异表达基因。'
        )
        assert result['fatal'] is False

    def test_report_with_tumor_fatal(self):
        checker = TermConsistencyChecker('/tmp/fake', '肾结石')
        result = checker.check_report_text(
            '差异表达分析发现 Tumor 与 Normal 之间有显著差异。'
        )
        assert result['fatal'] is True


class TestReturnStructure:
    """验证返回字段完整性"""

    def test_check_code_files_keys(self, kidney_stone_clean):
        proj, code_dir = kidney_stone_clean
        checker = TermConsistencyChecker(str(proj), '肾结石')
        result = checker.check_code_files(str(code_dir))
        for key in ('project_type', 'total_files', 'error_files', 'issues', 'fatal'):
            assert key in result, f'缺少返回字段: {key}'

    def test_check_report_text_keys(self):
        checker = TermConsistencyChecker('/tmp/fake', '癌症')
        result = checker.check_report_text('test text')
        for key in ('project_type', 'issues', 'fatal'):
            assert key in result, f'缺少返回字段: {key}'
