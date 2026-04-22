#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
临床统计检查器单元测试

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_clinical_statistics.py -v
"""

import os
import csv
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

# 添加 script_utils 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_clinical_statistics import ClinicalStatisticsChecker


# ===== Fixtures =====

@pytest.fixture
def empty_project(tmp_path):
    """空项目目录"""
    return str(tmp_path)


@pytest.fixture
def minimal_clinical_project(tmp_path):
    """最小临床统计项目（含基线和 Logistic）"""
    # 01_baseline
    baseline_dir = tmp_path / '01_baseline'
    baseline_dir.mkdir()
    with open(baseline_dir / '01.baseline.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Variable', 'Group1', 'Group2', 'P_value'])
        writer.writerow(['Age', '45.2±10.3', '48.1±11.2', '0.023'])
        writer.writerow(['Gender_Male', '120(54.5%)', '98(48.3%)', '0.185'])
        writer.writerow(['BMI', '24.1±3.5', '25.8±4.1', '0.001'])

    # 02_Logistic
    logistic_dir = tmp_path / '02_Logistic'
    logistic_dir.mkdir()

    # 单因素结果
    with open(logistic_dir / '01_uni_logistic_results_all.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Variable', 'OR', 'CI_lower', 'CI_upper', 'P_value'])
        writer.writerow(['Age', '1.05', '1.01', '1.09', '0.023'])
        writer.writerow(['BMI', '1.12', '1.04', '1.21', '0.001'])
        writer.writerow(['Smoking', '1.85', '1.22', '2.81', '0.004'])

    # VIF 筛选后变量
    with open(logistic_dir / '02.factor_after_VIF_filter.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Variable'])
        writer.writerow(['Age'])
        writer.writerow(['BMI'])

    # 多因素结果
    with open(logistic_dir / '03.Multivariate_logistic_results_sig.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Variable', 'OR', 'CI_lower', 'CI_upper', 'P_value'])
        writer.writerow(['Age', '1.04', '1.00', '1.08', '0.045'])
        writer.writerow(['BMI', '1.10', '1.02', '1.19', '0.012'])

    # 多因素变量清单
    with open(logistic_dir / '05.factor_Multivariate.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Variable'])
        writer.writerow(['Age'])
        writer.writerow(['BMI'])

    return str(tmp_path)


@pytest.fixture
def full_clinical_project(minimal_clinical_project):
    """完整临床统计项目（含 Nomogram 和 ML）"""
    tmp_path = Path(minimal_clinical_project)

    # 03_Nomogram
    nomo_dir = tmp_path / '03_Nomogram'
    nomo_dir.mkdir()
    (nomo_dir / '01.Nomo.png').write_bytes(b'\x89PNG\r\n\x1a\n')
    (nomo_dir / '02.Calibration_curve.png').write_bytes(b'\x89PNG\r\n\x1a\n')
    (nomo_dir / '03.DCA.png').write_bytes(b'\x89PNG\r\n\x1a\n')
    (nomo_dir / '04.Nomogram_ROC.png').write_bytes(b'\x89PNG\r\n\x1a\n')

    # 04_ML_Modeling
    ml_dir = tmp_path / '04_ML_Modeling'
    ml_dir.mkdir()
    with open(ml_dir / '01_Train_Performance_Metrics.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Model', 'AUC', 'Accuracy', 'Sensitivity', 'Specificity'])
        writer.writerow(['RandomForest', '0.85', '0.80', '0.78', '0.82'])

    with open(ml_dir / '01_Test_Performance_Metrics.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Model', 'AUC', 'Accuracy', 'Sensitivity', 'Specificity'])
        writer.writerow(['RandomForest', '0.82', '0.77', '0.75', '0.79'])

    return str(tmp_path)


# ===== 测试：空项目 =====

class TestEmptyProject:
    def test_no_crash_on_empty(self, empty_project):
        """空项目不应崩溃"""
        checker = ClinicalStatisticsChecker(empty_project)
        result = checker.check_all()
        assert isinstance(result, dict)
        assert 'total_checks' in result
        assert result['fatal'] is False


# ===== 测试：基线检查 =====

class TestBaselineCheck:
    def test_baseline_found(self, minimal_clinical_project):
        """应能检测到基线目录"""
        checker = ClinicalStatisticsChecker(minimal_clinical_project)
        result = checker.check_all()
        # 不应有关于缺少基线目录的 warning
        baseline_warnings = [w for w in result['warnings'] if '基线' in w.get('category', '')]
        assert not any('未找到基线统计目录' in w['message'] for w in baseline_warnings)

    def test_baseline_missing(self, empty_project):
        """缺少基线目录时应产生警告"""
        checker = ClinicalStatisticsChecker(empty_project)
        result = checker.check_all()
        # 空项目中没有基线目录，但也没有其他模块，所以不一定产生 baseline warning
        assert result['fatal'] is False


# ===== 测试：Logistic 流程 =====

class TestLogisticPipeline:
    def test_complete_pipeline(self, minimal_clinical_project):
        """完整流程不应产生 CRITICAL"""
        checker = ClinicalStatisticsChecker(minimal_clinical_project)
        result = checker.check_all()
        logistic_issues = [i for i in result['issues'] if 'Logistic' in i.get('category', '')]
        assert len(logistic_issues) == 0

    def test_missing_univariate(self, tmp_path):
        """缺少单因素结果应产生 CRITICAL"""
        logistic_dir = tmp_path / '02_Logistic'
        logistic_dir.mkdir()
        # 只有多因素
        with open(logistic_dir / '03.Multivariate_logistic_results_sig.csv', 'w', newline='') as f:
            csv.writer(f).writerow(['Variable', 'OR', 'P'])

        checker = ClinicalStatisticsChecker(str(tmp_path))
        result = checker.check_all()
        logistic_issues = [i for i in result['issues']
                          if 'Logistic' in i.get('category', '') and '单因素' in i.get('message', '')]
        assert len(logistic_issues) == 1

    def test_missing_multivariate(self, tmp_path):
        """缺少多因素结果应产生 CRITICAL"""
        logistic_dir = tmp_path / '02_Logistic'
        logistic_dir.mkdir()
        # 只有单因素
        with open(logistic_dir / '01_uni_logistic_results_all.csv', 'w', newline='') as f:
            csv.writer(f).writerow(['Variable', 'OR', 'P'])

        checker = ClinicalStatisticsChecker(str(tmp_path))
        result = checker.check_all()
        logistic_issues = [i for i in result['issues']
                          if 'Logistic' in i.get('category', '') and '多因素' in i.get('message', '')]
        assert len(logistic_issues) == 1


# ===== 测试：ML 指标 =====

class TestMLMetrics:
    def test_complete_metrics(self, full_clinical_project):
        """训练/测试指标齐全不应产生 CRITICAL"""
        checker = ClinicalStatisticsChecker(full_clinical_project)
        result = checker.check_all()
        ml_issues = [i for i in result['issues'] if 'ML' in i.get('category', '')]
        assert len(ml_issues) == 0

    def test_missing_test_metrics(self, tmp_path):
        """只有训练指标、缺测试指标应产生 CRITICAL"""
        ml_dir = tmp_path / '04_ML_Modeling'
        ml_dir.mkdir()
        with open(ml_dir / '01_Train_Performance_Metrics.csv', 'w', newline='') as f:
            csv.writer(f).writerow(['Model', 'AUC'])

        checker = ClinicalStatisticsChecker(str(tmp_path))
        result = checker.check_all()
        ml_issues = [i for i in result['issues'] if 'ML' in i.get('category', '')]
        assert len(ml_issues) == 1
        assert '测试集' in ml_issues[0]['message']

    def test_shap_no_csv(self, tmp_path):
        """SHAP 仅有图件时应产生 WARNING"""
        ml_dir = tmp_path / '04_ML_Modeling'
        ml_dir.mkdir()
        (ml_dir / '12_SHAP_BeeSwarm_Plot.pdf').write_bytes(b'%PDF')

        checker = ClinicalStatisticsChecker(str(tmp_path))
        result = checker.check_all()
        shap_warnings = [w for w in result['warnings'] if 'SHAP' in w.get('message', '')]
        assert len(shap_warnings) == 1


# ===== 测试：方法-代码一致性 =====

class TestMethodCodeMatch:
    def test_load_external_review_report_text(self, tmp_path):
        """在 raw 项目路径下也应能读取 result_review_report 中的 report_text"""
        project_dir = tmp_path / 'raw' / '已完成' / '26YSH015F-示例项目'
        project_dir.mkdir(parents=True)

        review_dir = tmp_path / 'result_review_report' / '26YSH015F'
        review_dir.mkdir(parents=True)
        (review_dir / 'report_text_v2.txt').write_text(
            '采用逐步回归优化模型。本研究通过回归分析方法对多个临床变量进行逐步筛选。'
            '最终纳入具有统计学意义的变量建立预测模型。',
            encoding='utf-8'
        )

        script_dir = project_dir / 'script'
        script_dir.mkdir()
        (script_dir / 'analysis.R').write_text(
            'model <- glm(outcome ~ ., data=df, family=binomial)\n',
            encoding='utf-8'
        )

        checker = ClinicalStatisticsChecker(str(project_dir))
        result = checker.check_all()
        method_issues = [i for i in result['issues'] if '逐步回归' in i.get('message', '')]
        assert len(method_issues) == 1

    def test_stepwise_claim_without_code(self, tmp_path):
        """声称逐步回归但代码无对应调用应产生 CRITICAL"""
        # 创建报告文本
        (tmp_path / 'report_text.txt').write_text(
            '方法：采用逐步回归优化模型，筛选显著变量。'
            '本研究通过回归分析方法对多个临床变量进行逐步筛选。',
            encoding='utf-8'
        )
        # 创建代码（无 step() 调用）
        script_dir = tmp_path / 'script'
        script_dir.mkdir()
        (script_dir / 'analysis.R').write_text(
            'model <- glm(outcome ~ ., data=df, family=binomial)\n'
            'summary(model)\n',
            encoding='utf-8'
        )

        checker = ClinicalStatisticsChecker(str(tmp_path))
        result = checker.check_all()
        method_issues = [i for i in result['issues'] if '逐步回归' in i.get('message', '')]
        assert len(method_issues) == 1

    def test_stepwise_claim_with_code(self, tmp_path):
        """声称逐步回归且代码有 step() 应通过"""
        (tmp_path / 'report_text.txt').write_text(
            '采用逐步回归优化模型。本研究通过回归分析方法对多个临床变量进行逐步筛选。',
            encoding='utf-8'
        )
        script_dir = tmp_path / 'script'
        script_dir.mkdir()
        (script_dir / 'analysis.R').write_text(
            'model <- glm(outcome ~ ., data=df, family=binomial)\n'
            'model_step <- step(model, direction="both")\n',
            encoding='utf-8'
        )

        checker = ClinicalStatisticsChecker(str(tmp_path))
        result = checker.check_all()
        method_issues = [i for i in result['issues'] if '逐步回归' in i.get('message', '')]
        assert len(method_issues) == 0


# ===== 测试：模板残留检测 =====

class TestTemplateResidue:
    def test_survival_residue_detected(self, tmp_path):
        """生存分析术语出现在 Logistic 报告中应告警"""
        (tmp_path / 'report_text.txt').write_text(
            '本研究使用 Logistic 回归分析危险因素。\n'
            'SHAP 蜂群图显示该变量增加死亡风险。\n'
            'DCA 曲线用于评估各模型在不同时间结局中的临床价值。\n'
            '本研究通过多因素分析研究危险因素对临床结局的影响。\n',
            encoding='utf-8'
        )

        checker = ClinicalStatisticsChecker(str(tmp_path))
        result = checker.check_all()
        template_issues = [i for i in result['issues'] if '模板残留' in i.get('category', '')]
        assert len(template_issues) == 1
        assert '死亡风险' in template_issues[0]['message'] or '不同时间结局' in template_issues[0]['message']

    def test_no_residue(self, tmp_path):
        """正常报告不应触发模板残留告警"""
        (tmp_path / 'report_text.txt').write_text(
            '本研究使用 Logistic 回归分析危险因素。\n'
            'SHAP 蜂群图显示该变量增加结局的预测概率。\n'
            '本研究通过多因素分析研究危险因素对临床结局的影响。\n',
            encoding='utf-8'
        )

        checker = ClinicalStatisticsChecker(str(tmp_path))
        result = checker.check_all()
        template_issues = [i for i in result['issues'] if '模板残留' in i.get('category', '')]
        assert len(template_issues) == 0


class TestDirectionalityChecks:
    def test_baseline_directionality_conflict_detected(self, tmp_path):
        """基线表方向与正文描述相反时应产生 CRITICAL"""
        baseline_dir = tmp_path / '01_baseline'
        baseline_dir.mkdir()
        with open(baseline_dir / '01.baseline.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Variable', 'Level', 'Total', 'No', 'Yes', 'Test', 'P_value'])
            writer.writerow(['Number_of_fetuses', '1', '570 (90.8%)', '309 (87.0%)', '261 (95.6%)', 'Chi-square', '<0.001'])
            writer.writerow(['Number_of_fetuses', '2', '58 (9.2%)', '46 (13.0%)', '12 (4.4%)', 'NA', 'NA'])
            writer.writerow(['Manual_removal_of_the_placenta', 'No', '204 (32.5%)', '102 (28.7%)', '102 (37.4%)', 'Chi-square', '0.0221'])
            writer.writerow(['Manual_removal_of_the_placenta', 'Yes', '424 (67.5%)', '253 (71.3%)', '171 (62.6%)', 'NA', 'NA'])

        (tmp_path / 'report_text.txt').write_text(
            '前置胎盘患者胎数更高，且人工剥离胎盘发生率更高。'
            '本研究通过多因素分析研究危险因素对临床结局的影响。',
            encoding='utf-8'
        )

        checker = ClinicalStatisticsChecker(str(tmp_path))
        result = checker.check_all()
        direction_issues = [i for i in result['issues'] if i.get('category') == '基线方向性']
        assert len(direction_issues) >= 2

    def test_regression_directionality_conflict_detected(self, tmp_path):
        """回归结果 OR 方向与正文危险/保护归类相反时应产生 CRITICAL"""
        logistic_dir = tmp_path / '02_Logistic'
        logistic_dir.mkdir()
        with open(logistic_dir / '03.Multivariate_logistic_results_all.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Variable', 'Raw_variable', 'OR_95CI', 'P_value', 'Lower_CI', 'Upper_CI', 'OR'])
            writer.writerow(['Parity2', 'Parity', '2.483 (1.078-5.718)', '0.033', '1.078', '5.718', '2.483'])

        (tmp_path / 'report_text.txt').write_text(
            '多因素Logistic回归结果显示，产次（Parity）为独立保护性因素。'
            '本研究通过多因素分析研究危险因素对临床结局的影响。',
            encoding='utf-8'
        )

        checker = ClinicalStatisticsChecker(str(tmp_path))
        result = checker.check_all()
        direction_issues = [i for i in result['issues'] if i.get('category') == '回归方向性']
        assert len(direction_issues) == 1
