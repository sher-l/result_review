#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
临床统计项目检查器（P1级 - CRITICAL）

针对 Logistic 回归 / 列线图 / 决策树 / ML 建模类临床数据分析项目的自动检查。
覆盖从基线统计到机器学习建模的完整流程。

典型目录结构：
  00_rawdata/          → 原始数据、缺失值统计
  01_baseline/         → 基线统计表
  02_Logistic/         → 单因素→VIF→多因素回归
  03_Nomogram/         → 列线图、校准曲线、DCA、决策树
  04_ML_Modeling/      → 多算法建模、SHAP

基于项目经验：26YSH015F（胎盘植入临床数据分析）
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Set


from base_project_checker import BaseProjectChecker


class ClinicalStatisticsChecker(BaseProjectChecker):
    """临床统计项目检查器"""

    BASELINE_PATTERNS = ['*baseline*', '*Baseline*']
    LOGISTIC_PATTERNS = ['*Logistic*', '*logistic*', '*regression*']
    NOMOGRAM_PATTERNS = ['*Nomogram*', '*nomogram*', '*nomo*']
    ML_PATTERNS = ['*ML*', '*ml_*', '*Machine*', '*machine*', '*Modeling*']

    METHOD_CODE_MAP = {
        '逐步回归': [r'step\s*\(', r'stepAIC\s*\(', r'stepwise'],
        'LASSO': [r'glmnet', r'cv\.glmnet'],
        'VIF': [r'vif\s*\(', r'car::vif'],
        'Bootstrap': [r'boot\s*\(', r'Boot\s*\(', r'bootstrap'],
    }

    SURVIVAL_TEMPLATE_KEYWORDS = [
        '死亡风险', '生存分析', 'hazard ratio', 'HR=', 'HR =',
        '不同时间尺度', '不同时间结局', 'Kaplan-Meier', 'KM曲线',
        'Cox回归', 'cox回归', 'Cox regression',
    ]

    DIRECTION_HIGH_KEYWORDS = ['更高', '更多', '更长', '升高', '增加', '增高']
    DIRECTION_LOW_KEYWORDS = ['更低', '更少', '更短', '降低', '下降', '减低']
    RISK_KEYWORDS = ['危险因素', '独立危险因素', '风险因素', '高危因素']
    PROTECTIVE_KEYWORDS = ['保护性因素', '保护因素', '独立保护性因素', '保护性关联']

    VARIABLE_ALIAS_MAP = {
        'Age': ['年龄'],
        'Length_of_stay': ['住院时间', '住院时长'],
        'RBC_units': ['输注RBC单位数', 'RBC单位数', '输血单位数', '输血量'],
        'Gestational_age_at_delivery.weeks.': ['分娩孕周', '分娩周数', '孕周'],
        'EBL.mL.': ['出血量', '术中出血量', '估计失血量'],
        'Operation_time.min.': ['手术时间', '手术时长'],
        'Number_of_fetuses': ['胎数', '胎儿数', '双胎', '多胎妊娠'],
        'Parity': ['产次'],
        'Gravidity': ['孕次'],
        'Manual_removal_of_the_placenta': ['人工剥离胎盘'],
        'Uterine_cavity_packing': ['宫腔填塞'],
        'Uterine_artery_embolization': ['子宫动脉栓塞'],
        'Intrauterine_balloon': ['宫腔水囊', '宫内球囊', '宫腔球囊'],
        'Total_hysterectomy': ['全子宫切除', '子宫全切'],
        'Pelvic_artery_ligation': ['盆腔动脉结扎'],
        'Abdominal_balloon_preset': ['腹球预置', '腹主动脉球囊预置', '腹腔球囊预置'],
        'RBC_transfusion': ['输血'],
        'ICU': ['ICU入住', '入住ICU'],
        'Previous_cesarean_section': ['既往剖宫产史', '剖宫产史', '既往剖宫产'],
        'Pregnancy_complications.Obesity.': ['肥胖'],
        'Pregnancy_complications.Malpresentation.': ['异常胎位', '胎位异常'],
        'Pregnancy_complications.Fetal_distress.': ['胎儿窘迫'],
        'Pregnancy_complications.Nuchal_cord.': ['脐带绕颈'],
        'Pregnancy_complications.Mild_preeclampsia.': ['轻度子痫前期'],
        'Pregnancy_complications.ICP.': ['妊娠期肝内胆汁淤积症', 'ICP'],
        'Pregnancy_complications.PROM.': ['胎膜早破', 'PROM'],
        'Pregnancy_complications.FGR.': ['胎儿生长受限', 'FGR'],
    }

    def __init__(self, project_path: str, layer0_data: dict = None):
        super().__init__(project_path, layer0_data=layer0_data)
        self.baseline_rows: List[Dict[str, str]] = []
        self.univariate_rows: List[Dict[str, str]] = []
        self.multivariate_rows: List[Dict[str, str]] = []

    def check_all(self) -> Dict:
        report_text = self.load_report_text()
        code_texts = self._load_code_texts()

        self._check_baseline_module()
        self._check_logistic_pipeline()
        self._check_variable_consistency()
        self._check_nomogram_module()
        self._check_ml_metrics()
        self._check_method_code_match(report_text, code_texts)
        self._check_survival_template_residue(report_text)
        self._check_baseline_directionality(report_text)
        self._check_regression_directionality(report_text, self.univariate_rows, '单因素Logistic')
        self._check_regression_directionality(report_text, self.multivariate_rows, '多因素Logistic')

        fatal = any(issue.get('severity') == 'FATAL' for issue in self.issues)
        return {
            'total_checks': 10,
            'failed_checks': len(self.issues),
            'issues': self.issues,
            'warnings': self.warnings,
            'fatal': fatal,
        }

    def _check_baseline_module(self):
        baseline_dir = self._find_module_dir(self.BASELINE_PATTERNS)
        if not baseline_dir:
            self.warnings.append({
                'severity': 'WARNING',
                'category': '基线统计',
                'message': '未找到基线统计目录（01_baseline 或类似目录）',
            })
            return

        csv_files = list(baseline_dir.rglob('*.csv'))
        if not csv_files:
            self.issues.append({
                'severity': 'CRITICAL',
                'category': '基线统计',
                'message': f'基线目录 {baseline_dir.name}/ 存在但无 CSV 文件',
            })
            return

        for path in csv_files:
            if 'baseline' in path.name.lower():
                self._validate_baseline_csv(path)
                break

    def _validate_baseline_csv(self, csv_path: Path):
        try:
            with open(csv_path, 'r', encoding='utf-8', errors='replace') as fh:
                reader = csv.reader(fh)
                header = next(reader, None)
                if header is None:
                    self.issues.append({
                        'severity': 'CRITICAL',
                        'category': '基线统计',
                        'message': f'{csv_path.name} 为空文件',
                    })
                    return
                row_count = sum(1 for _ in reader)

            header_lower = [item.lower().strip() for item in header]
            has_p = any('p' in item and ('val' in item or item == 'p') for item in header_lower)
            if not has_p:
                self.warnings.append({
                    'severity': 'WARNING',
                    'category': '基线统计',
                    'message': f'{csv_path.name} 未发现 P-value 列，可能不是标准基线统计表',
                })

            if row_count < 3:
                self.warnings.append({
                    'severity': 'WARNING',
                    'category': '基线统计',
                    'message': f'{csv_path.name} 仅有 {row_count} 行数据，变量过少',
                })

            with open(csv_path, 'r', encoding='utf-8', errors='replace') as fh:
                self.baseline_rows = list(csv.DictReader(fh))
        except Exception:
            pass

    def _check_logistic_pipeline(self):
        logistic_dir = self._find_module_dir(self.LOGISTIC_PATTERNS)
        if not logistic_dir:
            return

        files = {f.name.lower(): f for f in logistic_dir.rglob('*') if f.is_file()}
        has_univariate = any('uni' in name and ('logistic' in name or 'result' in name) for name in files)
        has_vif = any('vif' in name for name in files)
        has_multivariate = any('multi' in name and ('logistic' in name or 'result' in name) for name in files)

        for path in files.values():
            name = path.name.lower()
            if not self.univariate_rows and 'uni' in name and ('logistic' in name or 'result' in name):
                self.univariate_rows = self._load_regression_rows(path)
            if not self.multivariate_rows and 'multi' in name and ('logistic' in name or 'result' in name):
                self.multivariate_rows = self._load_regression_rows(path)

        if not has_univariate:
            self.issues.append({
                'severity': 'CRITICAL',
                'category': 'Logistic 流程',
                'message': f'{logistic_dir.name}/ 缺少单因素回归结果文件',
            })

        if not has_vif:
            self.warnings.append({
                'severity': 'WARNING',
                'category': 'Logistic 流程',
                'message': f'{logistic_dir.name}/ 未找到 VIF 筛选结果文件',
            })

        if not has_multivariate:
            self.issues.append({
                'severity': 'CRITICAL',
                'category': 'Logistic 流程',
                'message': f'{logistic_dir.name}/ 缺少多因素回归结果文件',
            })

    def _check_variable_consistency(self):
        logistic_dir = self._find_module_dir(self.LOGISTIC_PATTERNS)
        if not logistic_dir:
            return

        vif_vars = self._extract_variable_names(logistic_dir, ['factor_after_vif', 'vif_filter'])
        multi_vars = self._extract_variable_names(logistic_dir, ['factor_multivariate', 'multivariate_logistic_results_sig'])

        if vif_vars and multi_vars:
            extra_in_multi = multi_vars - vif_vars
            if extra_in_multi:
                self.warnings.append({
                    'severity': 'WARNING',
                    'category': '变量一致性',
                    'message': f'多因素回归中有 {len(extra_in_multi)} 个变量名未在 VIF 筛选文件中直接匹配（可能因 factor/dummy encoding 导致名称变化，请人工确认）: {", ".join(list(extra_in_multi)[:5])}',
                })

    def _check_nomogram_module(self):
        nomo_dir = self._find_module_dir(self.NOMOGRAM_PATTERNS)
        if not nomo_dir:
            return

        files = {f.name.lower(): f for f in nomo_dir.rglob('*') if f.is_file()}
        expected_components = {
            '列线图': ['nomo'],
            '校准曲线': ['calibration'],
            'DCA': ['dca'],
            'ROC': ['roc'],
        }

        for component_name, keywords in expected_components.items():
            found = any(any(keyword in fname for keyword in keywords) for fname in files)
            if not found:
                self.warnings.append({
                    'severity': 'WARNING',
                    'category': '列线图模块',
                    'message': f'未找到{component_name}相关文件',
                })

    def _check_ml_metrics(self):
        ml_dir = self._find_module_dir(self.ML_PATTERNS)
        if not ml_dir:
            return

        files = {f.name.lower(): f for f in ml_dir.rglob('*') if f.is_file()}
        has_train_metrics = any('train' in name and 'metric' in name for name in files)
        has_test_metrics = any('test' in name and 'metric' in name for name in files)

        if has_train_metrics and not has_test_metrics:
            self.issues.append({
                'severity': 'CRITICAL',
                'category': 'ML 建模',
                'message': '有训练集性能指标但缺少测试集性能指标',
            })
        elif not has_train_metrics and not has_test_metrics:
            has_performance = any('performance' in name for name in files)
            if not has_performance:
                self.warnings.append({
                    'severity': 'WARNING',
                    'category': 'ML 建模',
                    'message': '未找到训练/测试集性能指标文件（Performance_Metrics.csv）',
                })

        has_shap_fig = any('shap' in name and (name.endswith('.pdf') or name.endswith('.png')) for name in files)
        has_shap_csv = any('shap' in name and name.endswith('.csv') for name in files)
        if has_shap_fig and not has_shap_csv:
            self.warnings.append({
                'severity': 'WARNING',
                'category': 'ML 建模',
                'message': 'SHAP 分析仅有图件，缺少数值导出表（建议补充 SHAP values CSV）',
            })

    def _check_method_code_match(self, report_text: Optional[str], code_texts: List[str]):
        if not report_text:
            return

        all_code = '\n'.join(code_texts)
        if not all_code:
            self.warnings.append({
                'severity': 'WARNING',
                'category': '方法-代码一致性',
                'message': '未找到项目代码文件，无法验证方法描述与代码一致性',
            })
            return

        for method_claim, code_patterns in self.METHOD_CODE_MAP.items():
            if method_claim not in report_text:
                continue
            code_has_evidence = any(re.search(pattern, all_code, re.IGNORECASE) for pattern in code_patterns)
            if not code_has_evidence:
                self.issues.append({
                    'severity': 'CRITICAL',
                    'category': '方法-代码一致性',
                    'message': f'报告声称使用“{method_claim}”，但代码中未找到对应函数调用 ({", ".join(code_patterns)})',
                })

    def _check_survival_template_residue(self, report_text: Optional[str]):
        if not report_text:
            return

        found_residues = []
        lowered = report_text.lower()
        for keyword in self.SURVIVAL_TEMPLATE_KEYWORDS:
            index = lowered.find(keyword.lower())
            if index == -1:
                continue
            start = max(0, index - 30)
            end = min(len(report_text), index + len(keyword) + 30)
            context = report_text[start:end].replace('\n', ' ')
            found_residues.append((keyword, context))

        if found_residues:
            details = '; '.join(f'"{keyword}" (…{context}…) ' for keyword, context in found_residues[:3]).strip()
            self.issues.append({
                'severity': 'CRITICAL',
                'category': '模板残留',
                'message': f'报告中发现 {len(found_residues)} 处生存分析模板残留词: {details}',
            })

    def _check_baseline_directionality(self, report_text: Optional[str]):
        if not report_text or not self.baseline_rows:
            return

        seen_messages = set()
        for sentence in self._split_sentences(report_text):
            reported_direction = self._infer_reported_direction(sentence)
            if not reported_direction:
                continue
            for variable, rows in self._group_baseline_rows().items():
                aliases = self._build_aliases(variable)
                if not self._sentence_mentions_alias(sentence, aliases):
                    continue
                comparison = self._summarize_baseline_direction(variable, rows)
                if not comparison or comparison['direction'] == reported_direction:
                    continue
                message = f'报告对基线变量“{variable}”的方向描述与基线表不符：正文写为“{reported_direction}”，但基线表显示 {comparison["detail"]}'
                if message in seen_messages:
                    continue
                seen_messages.add(message)
                self.issues.append({
                    'severity': 'CRITICAL',
                    'category': '基线方向性',
                    'message': message,
                })

    def _check_regression_directionality(self, report_text: Optional[str], rows: List[Dict[str, str]], stage_label: str):
        if not report_text or not rows:
            return

        seen_messages = set()
        for sentence in self._split_sentences(report_text):
            report_is_risk = any(keyword in sentence for keyword in self.RISK_KEYWORDS) or 'OR>1' in sentence
            report_is_protective = any(keyword in sentence for keyword in self.PROTECTIVE_KEYWORDS) or 'OR<1' in sentence
            if not report_is_risk and not report_is_protective:
                continue

            for row in rows:
                variable = row.get('Raw_variable') or row.get('Variable') or ''
                aliases = self._build_aliases(variable)
                aliases.update(self._build_aliases(row.get('Variable', '')))
                if not aliases or not self._sentence_mentions_alias(sentence, aliases):
                    continue

                or_value = self._safe_float(row.get('OR'))
                if or_value is None or or_value == 1:
                    continue
                contradiction = (report_is_risk and or_value < 1) or (report_is_protective and or_value > 1)
                if not contradiction:
                    continue

                actual_direction = '危险因素' if or_value > 1 else '保护因素'
                message = f'{stage_label}中“{row.get("Variable") or variable}”的方向描述与 OR 不符：正文归类为{"危险因素" if report_is_risk else "保护因素"}，但结果表 OR={or_value:.3f}，实际应为{actual_direction}'
                if message in seen_messages:
                    continue
                seen_messages.add(message)
                self.issues.append({
                    'severity': 'CRITICAL',
                    'category': '回归方向性',
                    'message': message,
                })

    def _find_module_dir(self, patterns: List[str]) -> Optional[Path]:
        for item in sorted(self.project_path.iterdir()):
            if not item.is_dir():
                continue
            name_lower = item.name.lower()
            for pattern in patterns:
                keyword = pattern.replace('*', '').lower()
                if keyword in name_lower:
                    return item
        return None

    def _load_code_texts(self) -> List[str]:
        code_texts = []
        for pattern in ['*.r', '*.R', '*.py']:
            for code_file in self.project_path.rglob(pattern):
                try:
                    code_texts.append(code_file.read_text(encoding='utf-8', errors='replace'))
                except Exception:
                    continue
        return code_texts

    def _extract_variable_names(self, search_dir: Path, filename_hints: List[str]) -> Optional[Set[str]]:
        for path in search_dir.rglob('*.csv'):
            fname_lower = path.name.lower().replace('.', '_').replace('-', '_')
            if not any(hint in fname_lower for hint in filename_hints):
                continue
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                    reader = csv.reader(fh)
                    header = next(reader, None)
                    if not header:
                        continue
                    variables = set()
                    for row in reader:
                        if row and row[0].strip():
                            variables.add(row[0].strip())
                    if variables:
                        return variables
            except Exception:
                continue
        return None

    def _load_regression_rows(self, csv_path: Path) -> List[Dict[str, str]]:
        try:
            with open(csv_path, 'r', encoding='utf-8', errors='replace') as fh:
                return list(csv.DictReader(fh))
        except Exception:
            return []

    def _group_baseline_rows(self) -> Dict[str, List[Dict[str, str]]]:
        grouped: Dict[str, List[Dict[str, str]]] = {}
        for row in self.baseline_rows:
            variable = (row.get('Variable') or '').strip()
            if not variable:
                continue
            grouped.setdefault(variable, []).append(row)
        return grouped

    def _split_sentences(self, report_text: str) -> List[str]:
        return [part.strip() for part in re.split(r'[。；!！?？\n]+', report_text) if part.strip()]

    def _build_aliases(self, variable: str) -> Set[str]:
        aliases: Set[str] = set()
        variable = (variable or '').strip()
        if not variable:
            return aliases

        aliases.add(variable)
        normalized = variable.replace('.', ' ').replace('_', ' ')
        aliases.add(normalized)
        aliases.add(normalized.lower())
        aliases.update(self.VARIABLE_ALIAS_MAP.get(variable, []))

        raw_key = re.sub(r'(Yes|No|>=\d+|\d+)$', '', variable)
        if raw_key and raw_key != variable:
            aliases.update(self.VARIABLE_ALIAS_MAP.get(raw_key, []))
            aliases.add(raw_key)
            aliases.add(raw_key.replace('.', ' ').replace('_', ' '))
        return {alias for alias in aliases if alias}

    def _sentence_mentions_alias(self, sentence: str, aliases: Set[str]) -> bool:
        lowered = sentence.lower()
        return any(alias.lower() in lowered for alias in aliases)

    def _infer_reported_direction(self, sentence: str) -> Optional[str]:
        if any(keyword in sentence for keyword in self.DIRECTION_HIGH_KEYWORDS):
            return '更高'
        if any(keyword in sentence for keyword in self.DIRECTION_LOW_KEYWORDS):
            return '更低'
        return None

    def _summarize_baseline_direction(self, variable: str, rows: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
        if not rows or not self._is_significant(rows[0].get('P_value')):
            return None

        if all(not (row.get('Level') or '').strip() for row in rows):
            no_value = self._extract_first_number(rows[0].get('No', ''))
            yes_value = self._extract_first_number(rows[0].get('Yes', ''))
            if no_value is None or yes_value is None or yes_value == no_value:
                return None
            direction = '更高' if yes_value > no_value else '更低'
            return {'direction': direction, 'detail': f'Yes组={yes_value:.3f}，No组={no_value:.3f}，实际为{direction}'}

        ordinal_rows = []
        for row in rows:
            score = self._level_to_score(row.get('Level', ''))
            pct_no = self._extract_percent(row.get('No', ''))
            pct_yes = self._extract_percent(row.get('Yes', ''))
            if score is None or pct_no is None or pct_yes is None:
                ordinal_rows = []
                break
            ordinal_rows.append((score, pct_no, pct_yes, row.get('Level', '')))

        if ordinal_rows:
            no_mean = sum(score * pct_no for score, pct_no, _, _ in ordinal_rows) / 100.0
            yes_mean = sum(score * pct_yes for score, _, pct_yes, _ in ordinal_rows) / 100.0
            if yes_mean == no_mean:
                return None
            direction = '更高' if yes_mean > no_mean else '更低'
            highest = max(ordinal_rows, key=lambda item: item[0])
            detail = f'Yes组均值={yes_mean:.3f}，No组均值={no_mean:.3f}，最高水平({highest[3]})占比 Yes组={highest[2]:.1f}% vs No组={highest[1]:.1f}%，实际为{direction}'
            return {'direction': direction, 'detail': detail}

        positive_row = next((row for row in rows if self._is_affirmative_level(row.get('Level', ''))), None)
        if positive_row is None:
            return None
        pct_no = self._extract_percent(positive_row.get('No', ''))
        pct_yes = self._extract_percent(positive_row.get('Yes', ''))
        if pct_no is None or pct_yes is None or pct_yes == pct_no:
            return None
        direction = '更高' if pct_yes > pct_no else '更低'
        detail = f'肯定水平({positive_row.get("Level")})发生率 Yes组={pct_yes:.1f}% vs No组={pct_no:.1f}%，实际为{direction}'
        return {'direction': direction, 'detail': detail}

    def _is_significant(self, p_value: Optional[str]) -> bool:
        if p_value is None:
            return False
        value = str(p_value).strip()
        if not value or value.upper() == 'NA':
            return False
        if value.startswith('<'):
            return True
        numeric = self._safe_float(value)
        return numeric is not None and numeric < 0.05

    def _safe_float(self, value: Optional[str]) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(str(value).strip())
        except Exception:
            return None

    def _extract_first_number(self, text: str) -> Optional[float]:
        match = re.search(r'-?\d+(?:\.\d+)?', str(text))
        return float(match.group()) if match else None

    def _extract_percent(self, text: str) -> Optional[float]:
        match = re.search(r'\(([-\d.]+)%\)', str(text))
        return float(match.group(1)) if match else None

    def _level_to_score(self, level: str) -> Optional[float]:
        level = str(level).strip()
        if not level or level.upper() == 'NA':
            return None
        lowered = level.lower()
        if lowered in {'no', '否'}:
            return 0.0
        if lowered in {'yes', '是'}:
            return 1.0
        if lowered.startswith('>='):
            return self._safe_float(lowered[2:])
        if lowered.startswith('>'):
            return self._safe_float(lowered[1:])
        return self._safe_float(level)

    def _is_affirmative_level(self, level: str) -> bool:
        lowered = str(level).strip().lower()
        return lowered in {'yes', '1', 'positive', 'present', 'abnormal', 'high', '是'}
