#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模型一致性检查器 (P1级)

检测同一脚本或同一模块中模型定义的一致性：
1. 列线图公式 vs 校准曲线公式 vs DCA 公式 中使用的变量集是否一致
2. 同一脚本中多个 lrm()/glm()/coxph() 调用的变量集对比

基于 26YLM076F 审核经验：
- r-06_Nomogram.R 中列线图用 5 基因 (CDH1+DPP4+HOTAIR+MEG3+PROM2)
- 校准曲线却用 3 基因 (CDH1+DPP4+MEG3)
- 这种同一脚本内模型口径不一致容易漏过人工审核。

作者: 审核框架 v6.5
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    from utils import safe_read_file
except ImportError:
    from pathlib import Path as _P
    def safe_read_file(path, encodings=None):
        try:
            return _P(path).read_text(encoding='utf-8', errors='ignore'), 'utf-8'
        except Exception:
            return '', None

from base_project_checker import BaseProjectChecker


class ModelConsistencyChecker(BaseProjectChecker):
    """同一脚本/模块内模型公式一致性检查"""

    # 模型函数名 + 公式提取正则
    _MODEL_PATTERNS = [
        # R: lrm(Y ~ A + B + C, data=...)
        re.compile(r'(\w+)\s*<-\s*lrm\(\s*(\w+)\s*~\s*([^,)]+)', re.I),
        # R: glm(Y ~ A + B + C, ...)
        re.compile(r'(\w+)\s*<-\s*glm\(\s*(\w+)\s*~\s*([^,)]+)', re.I),
        # R: coxph(Surv(...) ~ A + B + C, ...)
        re.compile(r'(\w+)\s*<-\s*coxph\(\s*Surv\([^)]+\)\s*~\s*([^,)]+)', re.I),
        # R: lm(Y ~ A + B + C, ...)
        re.compile(r'(\w+)\s*<-\s*lm\(\s*(\w+)\s*~\s*([^,)]+)', re.I),
    ]

    # coxph 的特殊模式（Surv 占了第一个 group）
    _COXPH_PATTERN = re.compile(
        r'(\w+)\s*<-\s*coxph\(\s*Surv\([^)]+\)\s*~\s*([^,)]+)', re.I
    )

    def __init__(self, project_path: str, layer0_data: dict = None):
        super().__init__(project_path, layer0_data=layer0_data)

    def check_all(self) -> Dict:
        """执行模型一致性检查"""
        # 优先在代码目录中搜索 R 脚本（利用基类方法）
        code_dir = self.find_code_directory()
        search_root = code_dir if code_dir else self.project_path
        scripts = list(search_root.rglob('*.R'))
        scripts = [s for s in scripts if 'result_review_framework' not in str(s)
                    and 'check_reports' not in str(s)]

        if not scripts:
            return {
                'issues': [],
                'warnings': [],
                'skipped': True,
                'reason': '未找到 R 脚本',
            }

        for script in scripts:
            models = self._extract_models(script)
            if len(models) >= 2:
                self._check_within_script(models, script)

        return {
            'issues': self.issues,
            'warnings': self.warnings,
            'total_checks': len(scripts),
            'failed_checks': len(self.issues),
        }

    def _extract_models(self, script_path: Path) -> List[Dict]:
        """从脚本中提取所有模型定义"""
        text, _ = safe_read_file(str(script_path))
        if not text:
            return []

        models = []
        lines = text.split('\n')

        for line_num, line in enumerate(lines, 1):
            # 跳过注释
            stripped = line.strip()
            if stripped.startswith('#'):
                continue

            # 标准模型函数
            for pat in self._MODEL_PATTERNS:
                m = pat.search(line)
                if m:
                    groups = m.groups()
                    if len(groups) == 3:
                        var_name, response, predictors = groups
                    elif len(groups) == 2:
                        var_name, predictors = groups
                        response = 'Surv'
                    else:
                        continue

                    # 解析预测变量列表
                    pred_set = self._parse_predictors(predictors)

                    if pred_set:
                        models.append({
                            'var_name': var_name.strip(),
                            'function': self._detect_function(line),
                            'predictors': pred_set,
                            'raw_formula': predictors.strip(),
                            'line': line_num,
                        })
                    break  # 一行只匹配一个模型

        return models

    def _parse_predictors(self, formula: str) -> Set[str]:
        """解析公式中的预测变量"""
        # 移除 data= 部分
        formula = re.sub(r'\s*,?\s*data\s*=.*', '', formula)
        # 按 + 分割
        parts = re.split(r'\s*\+\s*', formula.strip())
        predictors = set()
        for part in parts:
            var = part.strip()
            # 排除空字符串、数字、交互项
            if var and not var.isdigit() and ':' not in var:
                # 清除可能的括号等
                var = re.sub(r'[()]', '', var).strip()
                if var and re.match(r'^[A-Za-z_][\w.]*$', var):
                    predictors.add(var)
        return predictors

    def _detect_function(self, line: str) -> str:
        """检测行中使用的模型函数"""
        for func in ['lrm', 'glm', 'coxph', 'lm', 'multinom', 'polr']:
            if func + '(' in line.lower():
                return func
        return 'unknown'

    def _check_within_script(self, models: List[Dict], script_path: Path):
        """检查同一脚本中的模型一致性"""
        if len(models) < 2:
            return

        rel_path = str(script_path.relative_to(self.project_path))

        # 逐对比较
        for i in range(len(models)):
            for j in range(i + 1, len(models)):
                m1, m2 = models[i], models[j]
                p1, p2 = m1['predictors'], m2['predictors']

                # 两个模型使用不同数量的变量
                if p1 != p2:
                    only_in_1 = p1 - p2
                    only_in_2 = p2 - p1

                    # 只有当差异显著（子集关系，且变量数差 >= 2）时报告
                    if p1.issubset(p2) or p2.issubset(p1):
                        smaller = p1 if len(p1) < len(p2) else p2
                        larger = p1 if len(p1) > len(p2) else p2
                        diff = larger - smaller
                        m_smaller = m1 if len(p1) < len(p2) else m2
                        m_larger = m1 if len(p1) > len(p2) else m2

                        if len(diff) >= 1:
                            self.issues.append({
                                'severity': 'CRITICAL',
                                'category': '模型口径不一致',
                                'message': (
                                    f'{rel_path}: '
                                    f'{m_larger["var_name"]}(L{m_larger["line"]}) '
                                    f'使用 {len(larger)} 个变量 ({", ".join(sorted(larger))}), '
                                    f'但 {m_smaller["var_name"]}(L{m_smaller["line"]}) '
                                    f'仅使用 {len(smaller)} 个变量 ({", ".join(sorted(smaller))}), '
                                    f'缺少: {", ".join(sorted(diff))}'
                                ),
                                'file': rel_path,
                                'evidence': {
                                    'model_1': {
                                        'name': m_larger['var_name'],
                                        'line': m_larger['line'],
                                        'predictors': sorted(larger),
                                    },
                                    'model_2': {
                                        'name': m_smaller['var_name'],
                                        'line': m_smaller['line'],
                                        'predictors': sorted(smaller),
                                    },
                                    'missing': sorted(diff),
                                },
                            })
                    elif only_in_1 and only_in_2:
                        # 完全不同的变量集 — 通常是独立的单变量分析（如 Nomogram 中
                        # 逐个检验 risk/Age/Gender/Stage），不属于口径不一致。
                        # 仅当两个模型都有 ≥3 个变量且完全不重叠时才报 WARNING（罕见，
                        # 可能是变量拼写差异），否则视为正常独立分析，降为 INFO。
                        if len(p1) >= 3 and len(p2) >= 3:
                            self.warnings.append({
                                'severity': 'WARNING',
                                'category': '模型变量差异',
                                'message': (
                                    f'{rel_path}: '
                                    f'{m1["var_name"]}(L{m1["line"]}) 和 '
                                    f'{m2["var_name"]}(L{m2["line"]}) '
                                    f'各有 ≥3 个变量但完全不重叠，可能存在拼写差异'
                                ),
                                'file': rel_path,
                                'evidence': {
                                    'only_in_1': sorted(only_in_1),
                                    'only_in_2': sorted(only_in_2),
                                },
                            })
