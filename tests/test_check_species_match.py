#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
物种匹配检查器单元测试（P0级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_species_match.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_species_match import SpeciesChecker


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    """无 .gmt 文件的空项目"""
    return str(tmp_path)


@pytest.fixture
def project_human_gmt(tmp_path):
    """包含人类 .gmt 文件的项目"""
    gmt_dir = tmp_path / 'gene_sets'
    gmt_dir.mkdir()
    gmt_file = gmt_dir / 'h.all.v7.5.symbols.gmt'
    gmt_file.write_text(
        'HALLMARK_APOPTOSIS\thttp://...\tTP53\tBCL2\tBAX\tCAPS3\n',
        encoding='utf-8'
    )
    return str(tmp_path)


@pytest.fixture
def project_mouse_gmt(tmp_path):
    """包含小鼠 .gmt 文件的项目"""
    gmt_dir = tmp_path / 'gene_sets'
    gmt_dir.mkdir()
    gmt_file = gmt_dir / 'Mm.hallmark.v7.5.symbols.gmt'
    gmt_file.write_text(
        'HALLMARK_APOPTOSIS\thttp://...\tTp53\tBcl2\tBax\n',
        encoding='utf-8'
    )
    return str(tmp_path)


@pytest.fixture
def project_human_gmt_with_human_code(tmp_path):
    """人类 .gmt + 人类数据代码"""
    gmt_dir = tmp_path / 'gene_sets'
    gmt_dir.mkdir()
    (gmt_dir / 'h.all.v7.5.symbols.gmt').write_text(
        'HALLMARK_P53\thttp://...\tTP53\tMDM2\n', encoding='utf-8'
    )
    code_dir = tmp_path / 'code'
    code_dir.mkdir()
    (code_dir / 'analysis.R').write_text(
        'gmtfile <- "gene_sets/h.all.v7.5.symbols.gmt"\n'
        'gsea_result <- GSEA(genelist, TERM2GENE = read.gmt(gmtfile))\n',
        encoding='utf-8'
    )
    return str(tmp_path)


@pytest.fixture
def project_mouse_gmt_in_human_data(tmp_path):
    """小鼠 .gmt 用于人类数据（物种不匹配）"""
    gmt_dir = tmp_path / 'gene_sets'
    gmt_dir.mkdir()
    (gmt_dir / 'Mm.c2.symbols.gmt').write_text(
        'KEGG_APOPTOSIS\thttp://...\tTp53\tBcl2\n', encoding='utf-8'
    )
    code_dir = tmp_path / 'code'
    code_dir.mkdir()
    (code_dir / 'run.R').write_text(
        'gmtfile <- "gene_sets/Mm.c2.symbols.gmt"\n',
        encoding='utf-8'
    )
    return str(tmp_path)


# ===== 测试类 =====

class TestEmptyProject:
    """无 .gmt 文件"""

    def test_no_gmt_safe(self, empty_project):
        checker = SpeciesChecker(empty_project, data_species='human')
        result = checker.check_all()
        assert len(result['gmt_files']) == 0

    def test_no_species_mismatches(self, empty_project):
        checker = SpeciesChecker(empty_project)
        result = checker.check_all()
        assert len(result['issues']) == 0


class TestHumanGMT:
    """人类基因集检测"""

    def test_detects_human_species(self, project_human_gmt):
        checker = SpeciesChecker(project_human_gmt, data_species='human')
        result = checker.check_all()
        assert len(result['gmt_files']) == 1
        assert result['gmt_files'][0]['species'] == 'human'

    def test_human_high_confidence(self, project_human_gmt):
        checker = SpeciesChecker(project_human_gmt, data_species='human')
        result = checker.check_all()
        assert result['gmt_files'][0]['confidence'] == 'high'


class TestMouseGMT:
    """小鼠基因集检测"""

    def test_detects_mouse_species(self, project_mouse_gmt):
        checker = SpeciesChecker(project_mouse_gmt, data_species='mouse')
        result = checker.check_all()
        assert len(result['gmt_files']) == 1
        assert result['gmt_files'][0]['species'] == 'mouse'


class TestSpeciesMismatch:
    """物种不匹配检测"""

    def test_mouse_gmt_with_human_data(self, project_mouse_gmt_in_human_data):
        """小鼠 .gmt 用于人类数据项目应产生 mismatch 或 warning"""
        checker = SpeciesChecker(project_mouse_gmt_in_human_data, data_species='human')
        result = checker.check_all()
        has_issue = (
            len(result['issues']) > 0 or
            len(result['warnings']) > 0 or
            len(result['code_references']) > 0
        )
        assert has_issue, '未检测到小鼠基因集用于人类数据'


class TestCodeReferences:
    """检测代码中的 .gmt 引用"""

    def test_human_gmt_reference_safe(self, project_human_gmt_with_human_code):
        checker = SpeciesChecker(project_human_gmt_with_human_code, data_species='human')
        result = checker.check_all()
        # 人类 gmt 引用于人类数据，不应报非人类引用
        non_human_refs = [r for r in result['code_references'] if r['species'] != 'human']
        assert len(non_human_refs) == 0

    def test_mouse_gmt_reference_flagged(self, project_mouse_gmt_in_human_data):
        checker = SpeciesChecker(project_mouse_gmt_in_human_data, data_species='human')
        result = checker.check_all()
        mouse_refs = [r for r in result['code_references'] if r['species'] == 'mouse']
        assert len(mouse_refs) > 0, '未检测到代码中引用的小鼠 gmt'


class TestReturnStructure:
    """验证返回字段完整性"""

    def test_all_keys_present(self, empty_project):
        checker = SpeciesChecker(empty_project)
        result = checker.check_all()
        for key in ('gmt_files', 'code_references', 'species_mismatches',
                     'warnings', 'recommendations'):
            assert key in result, f'缺少返回字段: {key}'
