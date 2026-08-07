#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
边界条件测试 — 覆盖空项目、编码异常、大项目等极端场景

运行方式:
  cd result_review_framework
  python -m pytest tests/test_boundary_conditions.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))

from base_project_checker import BaseProjectChecker, strip_non_audit_appendix
from check_data_flow import DataFlowValidator
from check_figure_integrity import FigureIntegrityChecker
from check_ml_anomaly import MLAnomalyChecker
from check_model_consistency import ModelConsistencyChecker
from check_gene_naming import GeneNamingChecker
from check_project_id_consistency import ProjectIDChecker
from check_species_match import SpeciesChecker
from check_visualization_thresholds import VisualizationThresholdChecker
from check_evidence_completeness import EvidenceCompletenessChecker
from check_code_existence import CodeExistenceChecker


# ===== 空项目测试 =====

class TestEmptyProject:
    """所有 checker 对空项目（无文件/目录）不崩溃"""

    @pytest.fixture
    def empty_project(self, tmp_path):
        return str(tmp_path)

    def test_base_find_code_directory_returns_none(self, empty_project):
        checker = BaseProjectChecker(empty_project)
        assert checker.find_code_directory() is None

    def test_base_find_modules_returns_empty(self, empty_project):
        checker = BaseProjectChecker(empty_project)
        assert checker.find_modules() == []

    def test_base_load_report_text_returns_none(self, empty_project):
        checker = BaseProjectChecker(empty_project)
        result = checker.load_report_text()
        assert result is None or result == ''

    def test_strip_non_audit_appendix_after_references(self):
        text = "\n".join([
            "结果",
            "参考文献",
            "[1] reference",
            "公司介绍",
            "服务领域",
        ])
        trimmed = strip_non_audit_appendix(text)
        assert "公司介绍" not in trimmed
        assert "服务领域" not in trimmed
        assert "[1] reference" in trimmed

    def test_strip_non_audit_appendix_does_not_trim_body_mentions(self):
        text = "\n".join([
            "结果",
            "公司介绍这个变量用于实验分组说明",
            "参考文献",
            "[1] reference",
        ])
        trimmed = strip_non_audit_appendix(text)
        assert "公司介绍这个变量用于实验分组说明" in trimmed

    def test_data_flow_empty(self, empty_project):
        checker = DataFlowValidator(empty_project)
        result = checker.check_all()
        assert isinstance(result, dict)
        assert result['fatal'] is False

    def test_figure_integrity_empty(self, empty_project):
        checker = FigureIntegrityChecker(empty_project)
        result = checker.check_all()
        assert isinstance(result, dict)
        assert result['issues'] == []

    def test_ml_anomaly_empty(self, empty_project):
        checker = MLAnomalyChecker(empty_project)
        result = checker.check_all()
        assert isinstance(result, dict)
        assert result.get('skipped') is True

    def test_model_consistency_empty(self, empty_project):
        checker = ModelConsistencyChecker(empty_project)
        result = checker.check_all()
        assert isinstance(result, dict)
        assert result.get('skipped') is True

    def test_gene_naming_empty(self, empty_project):
        checker = GeneNamingChecker(empty_project)
        result = checker.check_all()
        assert isinstance(result, dict)
        assert result['total_files_checked'] == 0

    def test_project_id_empty(self, empty_project):
        checker = ProjectIDChecker(empty_project)
        result = checker.check_all()
        assert isinstance(result, dict)
        assert result['fatal'] is False

    def test_species_empty(self, empty_project):
        checker = SpeciesChecker(empty_project)
        result = checker.check_all()
        assert isinstance(result, dict)
        assert result['issues'] == []

    def test_visualization_thresholds_empty(self, empty_project):
        checker = VisualizationThresholdChecker(empty_project)
        result = checker.check_all()
        assert isinstance(result, dict)
        assert result['issues'] == []

    def test_evidence_completeness_empty(self, empty_project):
        checker = EvidenceCompletenessChecker(empty_project)
        result = checker.check_all()
        assert isinstance(result, dict)

    def test_code_existence_empty(self, empty_project):
        checker = CodeExistenceChecker(empty_project)
        result = checker.check_all()
        assert isinstance(result, dict)


# ===== 编码异常测试 =====

class TestEncodingErrors:
    """含非 UTF-8 文件时不崩溃"""

    @pytest.fixture
    def project_with_bad_encoding(self, tmp_path):
        code_dir = tmp_path / 'code'
        code_dir.mkdir()
        # 写入损坏编码的 R 文件（GBK 中文 + 错误字节）
        bad_file = code_dir / 'analysis.R'
        bad_file.write_bytes(b'setwd("26YLM076F")\ngroup <- c("\xc8\xb1\xca\xa1\0\xff\xfe")\n')
        return str(tmp_path)

    def test_project_id_survives_encoding(self, project_with_bad_encoding):
        checker = ProjectIDChecker(project_with_bad_encoding)
        result = checker.check_all()
        assert isinstance(result, dict)

    def test_visualization_thresholds_survives_encoding(self, project_with_bad_encoding):
        checker = VisualizationThresholdChecker(project_with_bad_encoding)
        result = checker.check_all()
        assert isinstance(result, dict)

    def test_model_consistency_survives_encoding(self, project_with_bad_encoding):
        checker = ModelConsistencyChecker(project_with_bad_encoding)
        result = checker.check_all()
        assert isinstance(result, dict)


# ===== 大项目（多模块）模拟 =====

class TestLargeProject:
    """含大量模块目录时不崩溃、不严重变慢"""

    @pytest.fixture
    def large_project(self, tmp_path):
        result_dir = tmp_path / '结果文件'
        result_dir.mkdir()
        # 创建 50 个编号模块（远超常见的 10-15 个）
        for i in range(1, 51):
            mod = result_dir / f'{i:02d}_module_{i}'
            mod.mkdir()
            # 每个模块放一个 R 文件和 CSV
            (mod / f'script_{i}.R').write_text(
                f'setwd("test")\nresult <- read.csv("data.csv")\n',
                encoding='utf-8'
            )
            (mod / f'output_{i}.csv').write_text(
                'gene,logFC,pvalue\nBRCA1,2.5,0.001\nTP53,-1.8,0.01\n',
                encoding='utf-8'
            )
        return str(tmp_path)

    def test_base_find_modules_all(self, large_project):
        checker = BaseProjectChecker(large_project)
        modules = checker.find_modules()
        assert len(modules) == 50

    def test_data_flow_large(self, large_project):
        checker = DataFlowValidator(large_project)
        result = checker.check_all()
        assert isinstance(result, dict)

    def test_gene_naming_large(self, large_project):
        checker = GeneNamingChecker(large_project)
        result = checker.check_all()
        assert isinstance(result, dict)

    def test_ml_anomaly_large(self, large_project):
        checker = MLAnomalyChecker(large_project)
        result = checker.check_all()
        assert isinstance(result, dict)

    def test_evidence_completeness_large(self, large_project):
        checker = EvidenceCompletenessChecker(large_project)
        result = checker.check_all()
        assert isinstance(result, dict)


# ===== Layer 0 快速路径测试 =====

class TestLayer0FastPath:
    """测试 Layer 0 数据加速基类方法"""

    @pytest.fixture
    def project_with_layer0(self, tmp_path):
        # 创建真实目录
        code_dir = tmp_path / '结果文件'
        code_dir.mkdir()
        mod1 = code_dir / '01_DEGs'
        mod1.mkdir()
        (mod1 / 'deg.R').write_text('# DEG script', encoding='utf-8')
        mod2 = code_dir / '02_Enrich'
        mod2.mkdir()

        layer0 = {
            'project_structure': {
                'code_files': [
                    {'path': '结果文件/01_DEGs/deg.R', 'size': 100},
                ],
                'modules': [
                    {'path': '结果文件/01_DEGs', 'is_module': True},
                    {'path': '结果文件/02_Enrich', 'is_module': True},
                    {'path': '结果文件', 'is_module': False},
                ],
            },
            'report_structure': {},
        }
        return str(tmp_path), layer0

    def test_find_code_directory_via_layer0(self, project_with_layer0):
        path, layer0 = project_with_layer0
        checker = BaseProjectChecker(path, layer0_data=layer0)
        code_dir = checker.find_code_directory()
        assert code_dir is not None
        assert '结果文件' in str(code_dir)

    def test_find_modules_via_layer0(self, project_with_layer0):
        path, layer0 = project_with_layer0
        checker = BaseProjectChecker(path, layer0_data=layer0)
        modules = checker.find_modules()
        assert len(modules) == 2
        names = [m.name for m in modules]
        assert '01_DEGs' in names
        assert '02_Enrich' in names


# ===== 统一返回值约定测试 =====

class TestUnifiedReturnValues:
    """所有注册 checker 返回值都包含 issues 键"""

    CHECKER_CLASSES = [
        DataFlowValidator,
        FigureIntegrityChecker,
        MLAnomalyChecker,
        ModelConsistencyChecker,
        GeneNamingChecker,
        ProjectIDChecker,
        SpeciesChecker,
        VisualizationThresholdChecker,
        EvidenceCompletenessChecker,
        CodeExistenceChecker,
    ]

    @pytest.fixture
    def empty_project(self, tmp_path):
        return str(tmp_path)

    @pytest.mark.parametrize('cls', CHECKER_CLASSES, ids=lambda c: c.__name__)
    def test_has_issues_key(self, empty_project, cls):
        """每个 checker 的 check_all() 返回值必须包含 issues 键"""
        checker = cls(empty_project)
        result = checker.check_all()
        assert 'issues' in result, f'{cls.__name__}.check_all() 缺少 issues 键'
        assert isinstance(result['issues'], list), f'{cls.__name__} issues 应为 list'
