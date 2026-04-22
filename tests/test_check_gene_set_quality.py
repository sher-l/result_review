#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
基因集质量检查器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_gene_set_quality.py -v
"""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_gene_set_quality import GeneSetQualityChecker


# ===== Fixtures =====

def write_gene_csv(path, genes, col_name='Gene'):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow([col_name, 'logFC'])
        for g in genes:
            w.writerow([g, '1.0'])


@pytest.fixture
def standard_genes_csv(tmp_path):
    p = tmp_path / 'genes.csv'
    write_gene_csv(p, ['TP53', 'BRCA1', 'EGFR', 'MYC', 'KRAS'])
    return str(p)


@pytest.fixture
def mixed_genes_csv(tmp_path):
    p = tmp_path / 'genes.csv'
    write_gene_csv(p, [
        'TP53', 'BRCA1',              # 标准
        'CD3-ZETA_1', 'TRAF_1-X',     # 蛋白复合物
        'MT-ND1', 'MT-CO2',           # 线粒体
        'HLA-A', 'HLA-DRB1',          # HLA
        'IGHV1',                       # 免疫球蛋白
        'LINC01234', 'MIR155',        # lncRNA
    ])
    return str(p)


@pytest.fixture
def gene_symbol_csv(tmp_path):
    """列名为 gene_symbol 而不是 Gene"""
    p = tmp_path / 'genes.csv'
    write_gene_csv(p, ['TP53', 'BRCA1'], col_name='gene_symbol')
    return str(p)


# ===== 测试 =====

class TestLoadAndDetect:
    """基因集加载和列名检测"""

    def test_load_standard_column(self, standard_genes_csv):
        checker = GeneSetQualityChecker(standard_genes_csv)
        assert checker.load_gene_set() is True
        assert checker.df is not None
        assert len(checker.df) == 5

    def test_load_gene_symbol_column(self, gene_symbol_csv):
        checker = GeneSetQualityChecker(gene_symbol_csv)
        assert checker.load_gene_set() is True
        assert checker.df is not None
        assert len(checker.df) == 2


class TestQualityChecks:
    """基因质量检查"""

    def test_all_standard(self, standard_genes_csv):
        checker = GeneSetQualityChecker(standard_genes_csv)
        checker.load_gene_set()
        result = checker.check_quality()
        assert result['total_genes'] == 5
        assert result['standard_genes'] == 5
        assert len(result['protein_complexes']) == 0

    def test_detect_protein_complexes(self, mixed_genes_csv):
        checker = GeneSetQualityChecker(mixed_genes_csv)
        checker.load_gene_set()
        result = checker.check_quality()
        assert len(result['protein_complexes']) == 2

    def test_detect_mitochondrial(self, mixed_genes_csv):
        checker = GeneSetQualityChecker(mixed_genes_csv)
        checker.load_gene_set()
        result = checker.check_quality()
        assert len(result['mitochondrial']) == 2

    def test_detect_hla(self, mixed_genes_csv):
        checker = GeneSetQualityChecker(mixed_genes_csv)
        checker.load_gene_set()
        result = checker.check_quality()
        assert len(result['hla']) == 2

    def test_detect_immunoglobulin(self, mixed_genes_csv):
        checker = GeneSetQualityChecker(mixed_genes_csv)
        checker.load_gene_set()
        result = checker.check_quality()
        assert len(result['immunoglobulin']) == 1

    def test_detect_lncrna(self, mixed_genes_csv):
        checker = GeneSetQualityChecker(mixed_genes_csv)
        checker.load_gene_set()
        result = checker.check_quality()
        assert len(result['lncrna']) == 2

    def test_standard_genes_count(self, mixed_genes_csv):
        checker = GeneSetQualityChecker(mixed_genes_csv)
        checker.load_gene_set()
        result = checker.check_quality()
        # TP53 + BRCA1 = 2 标准基因
        assert result['standard_genes'] == 2


class TestLncRNAPatternConsistency:
    """确认 lncRNA 正则与 gene_naming 一致"""

    def test_no_false_positive_ACTB(self, tmp_path):
        p = tmp_path / 'genes.csv'
        write_gene_csv(p, ['ACTB', 'ACTA2', 'ACE'])
        checker = GeneSetQualityChecker(str(p))
        checker.load_gene_set()
        result = checker.check_quality()
        assert len(result['lncrna']) == 0

    def test_linc_requires_digit(self, tmp_path):
        p = tmp_path / 'genes.csv'
        write_gene_csv(p, ['LINCARE', 'LINC01234'])
        checker = GeneSetQualityChecker(str(p))
        checker.load_gene_set()
        result = checker.check_quality()
        assert len(result['lncrna']) == 1
        assert 'LINC01234' in result['lncrna']
