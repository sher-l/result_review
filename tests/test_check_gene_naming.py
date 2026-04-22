#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
基因命名检查器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_gene_naming.py -v
"""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_gene_naming import GeneNamingChecker


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    return str(tmp_path)


@pytest.fixture
def project_with_gene_csv(tmp_path):
    """含基因CSV的项目"""
    d = tmp_path / '02_DEGs'
    d.mkdir()
    p = d / 'genes.csv'
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Gene', 'logFC'])
        w.writerow(['TP53', '2.1'])
        w.writerow(['BRCA1', '-1.5'])
        w.writerow(['HLA-A', '0.8'])
        w.writerow(['MT-ND1', '1.2'])
        w.writerow(['CD3-ZETA_1', '0.5'])
        w.writerow(['LINC01234', '0.3'])
    return str(tmp_path)


# ===== 正则模式测试 =====

class TestPatterns:
    """测试基因分类正则"""

    def test_protein_complex_hyphen_underscore(self):
        pat = GeneNamingChecker.PATTERNS['protein_complex']
        assert pat.match('CD3-ZETA_1')
        assert pat.match('TRAF_1-binding')

    def test_protein_complex_no_match_normal(self):
        pat = GeneNamingChecker.PATTERNS['protein_complex']
        assert not pat.match('BRCA1')
        assert not pat.match('TP53')
        assert not pat.match('HLA-A')  # 只有连字符没有下划线

    def test_mitochondrial(self):
        pat = GeneNamingChecker.PATTERNS['mitochondrial']
        assert pat.match('MT-ND1')
        assert pat.match('MT-CO2')
        assert not pat.match('MTS1')

    def test_hla(self):
        pat = GeneNamingChecker.PATTERNS['hla']
        assert pat.match('HLA-A')
        assert pat.match('HLA-DRB1')
        assert not pat.match('HLAA')

    def test_immunoglobulin(self):
        pat = GeneNamingChecker.PATTERNS['immunoglobulin']
        assert pat.match('IGHV1')
        assert pat.match('IGKC')
        assert not pat.match('IGF1')

    def test_lncrna_requires_digit_suffix(self):
        pat = GeneNamingChecker.PATTERNS['lncrna']
        assert pat.match('LINC01234')
        assert pat.match('MIR155')
        assert pat.match('RP11-344E13.1')
        # 不应匹配没有数字后缀的
        assert not pat.match('LINCARE')
        assert not pat.match('MIRI')
        assert not pat.match('ACTB')

    def test_lowercase(self):
        pat = GeneNamingChecker.PATTERNS['lowercase']
        assert pat.match('actb')
        assert not pat.match('ACTB')


class TestStandardizeName:
    """测试基因名标准化"""

    def test_uppercase_conversion(self, empty_project):
        checker = GeneNamingChecker(empty_project)
        assert checker._standardize_name('brca1') == 'BRCA1'

    def test_strip_whitespace(self, empty_project):
        checker = GeneNamingChecker(empty_project)
        assert checker._standardize_name(' TP53 ') == 'TP53'


class TestCheckGeneList:
    """测试 check_gene_list 方法"""

    def test_standard_genes_only(self, empty_project):
        checker = GeneNamingChecker(empty_project)
        result = checker.check_gene_list(['TP53', 'BRCA1', 'EGFR'])
        assert result['total_genes'] == 3
        assert result['standard_genes'] == 3
        assert len(result['issues']) == 0

    def test_detects_protein_complex(self, empty_project):
        checker = GeneNamingChecker(empty_project)
        result = checker.check_gene_list(['TP53', 'CD3-ZETA_1'])
        assert len(result['categories']['protein_complex']) == 1
        assert 'CD3-ZETA_1' in result['categories']['protein_complex']

    def test_detects_mitochondrial(self, empty_project):
        checker = GeneNamingChecker(empty_project)
        result = checker.check_gene_list(['MT-ND1', 'MT-CO2', 'TP53'])
        assert len(result['categories']['mitochondrial']) == 2

    def test_mixed_issues(self, empty_project):
        checker = GeneNamingChecker(empty_project)
        genes = ['TP53', 'CD3-ZETA_1', 'HLA-A', 'MT-ND1', 'LINC01234']
        result = checker.check_gene_list(genes)
        assert result['total_genes'] == 5
        # TP53 是标准基因
        assert result['standard_genes'] >= 1
