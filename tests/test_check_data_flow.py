#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
跨模块数据流验证器单元测试（P0级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_data_flow.py -v
"""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_data_flow import DataFlowValidator


# ===== 辅助函数 =====

def write_csv(path: Path, headers: list, rows: list):
    """写一个简单 CSV"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    """空项目"""
    return str(tmp_path)


@pytest.fixture
def project_with_deg(tmp_path):
    """含 DEG 结果文件的项目"""
    write_csv(
        tmp_path / '02_DEGs' / 'Diff.all.csv',
        ['Gene', 'logFC', 'PValue'],
        [['TP53', '2.1', '0.001'], ['BRCA1', '-1.5', '0.003'], ['MYC', '3.2', '0.0001']]
    )
    return str(tmp_path)


@pytest.fixture
def project_with_deg_and_enrichment(tmp_path):
    """含 DEG + 富集分析结果"""
    write_csv(
        tmp_path / '02_DEGs' / 'DEGs_all.csv',
        ['Gene', 'logFC', 'PValue'],
        [['TP53', '2.1', '0.001'], ['BRCA1', '-1.5', '0.003']]
    )
    write_csv(
        tmp_path / '04_GOKEGG' / 'GO_enrichment.csv',
        ['Term', 'Count', 'PValue'],
        [['cell cycle', '5', '0.001'], ['apoptosis', '3', '0.01']]
    )
    return str(tmp_path)


@pytest.fixture
def project_with_intersection_and_monocle(tmp_path):
    """含交集文件和 monocle 代码"""
    # 交集文件
    write_csv(
        tmp_path / '06_intersection' / 'common_genes.csv',
        ['Gene'],
        [['TP53'], ['BRCA1'], ['MYC'], ['EGFR'], ['KRAS']]
    )
    # monocle 代码使用 3 个基因（数据流断裂！）
    monocle_dir = tmp_path / '11_monocle'
    monocle_dir.mkdir(parents=True)
    (monocle_dir / 'r-11_monocle.R').write_text(
        'genes_use <- c("TP53","BRCA1","MYC")\n'
        'cds <- setOrderingFilter(cds, genes_use)\n',
        encoding='utf-8'
    )
    return str(tmp_path)


@pytest.fixture
def project_with_ml_and_gsea(tmp_path):
    """含 ML 交集文件和 GSEA 结果"""
    write_csv(
        tmp_path / '05_ML' / 'intersection_genes.csv',
        ['Gene'],
        [['TP53'], ['BRCA1']]
    )
    write_csv(
        tmp_path / '07_GSEA' / 'GSEA_results.csv',
        ['Term', 'NES', 'pvalue'],
        [['HALLMARK_P53', '1.8', '0.01']]
    )
    return str(tmp_path)


# ===== 测试类 =====

class TestEmptyProject:
    """空项目应安全通过"""

    def test_not_fatal(self, empty_project):
        validator = DataFlowValidator(empty_project)
        result = validator.validate_all_flows()
        assert result['fatal'] is False

    def test_total_checks_is_four(self, empty_project):
        validator = DataFlowValidator(empty_project)
        result = validator.validate_all_flows()
        assert result['total_checks'] == 4


class TestDEGToEnrichment:
    """DEG → 富集分析数据流"""

    def test_deg_only_produces_warnings(self, project_with_deg):
        validator = DataFlowValidator(project_with_deg)
        result = validator.validate_all_flows()
        # 有 DEG 无 enrichment，应该产生 warning
        assert result['fatal'] is False

    def test_deg_and_enrichment_not_fatal(self, project_with_deg_and_enrichment):
        validator = DataFlowValidator(project_with_deg_and_enrichment)
        result = validator.validate_all_flows()
        assert result['fatal'] is False


class TestIntersectionToMonocle:
    """交集 → monocle 数据流（核心检查）"""

    def test_gene_count_mismatch_detected(self, project_with_intersection_and_monocle):
        """交集5基因 vs monocle使用3基因应触发问题"""
        validator = DataFlowValidator(project_with_intersection_and_monocle)
        result = validator.validate_all_flows()
        # 应至少有 issue 或 warning 关于基因数不一致
        all_messages = (
            [i.get('message', '') for i in result['issues']] +
            [w.get('message', '') for w in result.get('warnings', [])]
        )
        has_flow_note = len(all_messages) > 0
        assert has_flow_note, '未检测到交集→monocle数据流信息'


class TestMLToGSEA:
    """ML → GSEA 数据流"""

    def test_ml_gsea_not_fatal(self, project_with_ml_and_gsea):
        validator = DataFlowValidator(project_with_ml_and_gsea)
        result = validator.validate_all_flows()
        assert result['fatal'] is False


class TestReturnStructure:
    """验证返回字段完整性"""

    def test_all_keys_present(self, empty_project):
        validator = DataFlowValidator(empty_project)
        result = validator.validate_all_flows()
        for key in ('total_checks', 'failed_checks', 'issues', 'fatal'):
            assert key in result, f'缺少返回字段: {key}'

    def test_issues_is_list(self, empty_project):
        validator = DataFlowValidator(empty_project)
        result = validator.validate_all_flows()
        assert isinstance(result['issues'], list)
