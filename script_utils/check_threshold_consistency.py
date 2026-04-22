#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
方法-代码阈值一致性检查器 (P1级)

自动对比报告方法段中声称的阈值与 R/Python 脚本中的实际赋值：
1. p 值阈值（adj.P.Val / P.thres / pvalue）
2. logFC 阈值（logFoldChange / log2FC）
3. 其他数值阈值

基于 26YLM076F 审核经验：报告写 p<0.05 但脚本实际为 P.thres<-0.001。

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


class ThresholdConsistencyChecker(BaseProjectChecker):
    """报告方法描述 ↔ 代码阈值 一致性检查"""

    # 代码中阈值变量名 → 语义标签
    _CODE_THRESHOLD_PATTERNS = [
        # p 值阈值
        (re.compile(r'(?:P\.thres|p\.thres|pvalue_threshold|p_threshold|p_cutoff)\s*<-\s*([\d.eE\-]+)'), 'p-value threshold'),
        (re.compile(r'(?:P\.thres|p\.thres|pvalue_threshold|p_threshold|p_cutoff)\s*=\s*([\d.eE\-]+)'), 'p-value threshold'),
        (re.compile(r'adj\.P\.Val\s*<\s*([\d.eE\-]+)'), 'p-value threshold'),
        (re.compile(r'pvalue\s*<\s*([\d.eE\-]+)'), 'p-value threshold'),
        (re.compile(r'p\.adjust\s*<\s*([\d.eE\-]+)'), 'p-value threshold'),
        # logFC 阈值
        (re.compile(r'(?:logFoldChange|logFC_threshold|logfc_cutoff|log2FC)\s*<-\s*([\d.]+)'), 'logFC threshold'),
        (re.compile(r'(?:logFoldChange|logFC_threshold|logfc_cutoff|log2FC)\s*=\s*([\d.]+)'), 'logFC threshold'),
        (re.compile(r'abs\(logFC\)\s*>\s*([\d.]+)'), 'logFC threshold'),
        (re.compile(r'abs\(log2FoldChange\)\s*>\s*([\d.]+)'), 'logFC threshold'),
    ]

    # 报告中阈值提取模式
    _REPORT_THRESHOLD_PATTERNS = [
        # p 值
        (re.compile(r'(?:adj\.?P\.?[Vv]al(?:ue)?|p[_\s]?value|校正后?P值?|adjusted\s*p)\s*[<＜]\s*([\d.eE\-]+)', re.I), 'p-value threshold'),
        (re.compile(r'P\s*[<＜]\s*([\d.eE\-]+)'), 'p-value threshold'),
        # logFC
        (re.compile(r'(?:\|?\s*log2?\s*FC\s*\|?|log2?FoldChange)\s*[>＞]\s*([\d.]+)', re.I), 'logFC threshold'),
        (re.compile(r'(?:绝对值|abs).*?(?:logFC|log2FC)\s*[>＞]\s*([\d.]+)', re.I), 'logFC threshold'),
        (re.compile(r'(?:logFC|log2FC).*?(?:绝对值|abs).*?[>＞]\s*([\d.]+)', re.I), 'logFC threshold'),
    ]

    def __init__(self, project_path: str, layer0_data: dict = None):
        super().__init__(project_path, layer0_data=layer0_data)

    def check_all(self) -> Dict:
        """执行阈值一致性检查"""
        # 加载报告文本
        report_text = self.load_report_text()

        # 扫描 R/Python 脚本中的阈值
        code_thresholds = self._scan_code_thresholds()
        if not code_thresholds:
            return {
                'issues': [],
                'warnings': [],
                'skipped': True,
                'reason': '未找到包含阈值定义的脚本',
            }

        if not report_text:
            # 降级模式：无报告时仍做脚本间阈值交叉比对
            self._check_cross_script_consistency(code_thresholds)
            return {
                'issues': self.issues,
                'warnings': self.warnings,
                'skipped': False,
                'degraded': True,
                'reason': '未找到报告文本，仅执行脚本间阈值一致性检查',
                'total_checks': len(code_thresholds),
                'failed_checks': len(self.issues),
                'code_thresholds': {k: [(v, f) for v, f in vs] for k, vs in code_thresholds.items()},
            }

        # 从报告中提取声称的阈值
        report_thresholds = self._extract_report_thresholds(report_text)

        # 交叉比对
        self._crossref(code_thresholds, report_thresholds)

        return {
            'issues': self.issues,
            'warnings': self.warnings,
            'total_checks': len(code_thresholds),
            'failed_checks': len(self.issues),
            'code_thresholds': {k: [(v, f) for v, f in vs] for k, vs in code_thresholds.items()},
            'report_thresholds': report_thresholds,
        }

    def _check_cross_script_consistency(self, code_thresholds: Dict[str, list]):
        """脚本间同名阈值的一致性检查（降级模式）"""
        for label, entries in code_thresholds.items():
            if len(entries) < 2:
                continue
            values = set(v for v, _ in entries)
            if len(values) > 1:
                detail = '; '.join(f'{f}: {v}' for v, f in entries)
                self.issues.append({
                    'severity': 'WARNING',
                    'category': '脚本间阈值不一致',
                    'message': f'{label} 在不同脚本中取值不同: {detail}',
                    'evidence': {'label': label, 'entries': [(v, f) for v, f in entries]},
                })

    def _scan_code_thresholds(self) -> Dict[str, List[Tuple[float, str]]]:
        """扫描 R/Python 脚本中的阈值赋值。返回 {标签: [(值, 文件)]}"""
        thresholds: Dict[str, List[Tuple[float, str]]] = {}
        scripts = list(self.project_path.rglob('*.R'))
        scripts.extend(self.project_path.rglob('*.py'))
        # 排除框架自身的脚本
        scripts = [s for s in scripts if 'result_review_framework' not in str(s)
                    and 'check_reports' not in str(s)]

        for script in scripts:
            text, _ = safe_read_file(str(script))
            if not text:
                continue
            rel_path = str(script.relative_to(self.project_path))
            for pat, label in self._CODE_THRESHOLD_PATTERNS:
                for m in pat.finditer(text):
                    try:
                        val = float(m.group(1))
                        if label not in thresholds:
                            thresholds[label] = []
                        thresholds[label].append((val, rel_path))
                    except (ValueError, IndexError):
                        continue
        return thresholds

    def _extract_report_thresholds(self, report_text: str) -> Dict[str, List[float]]:
        """从报告中提取声称的阈值"""
        thresholds: Dict[str, List[float]] = {}
        for pat, label in self._REPORT_THRESHOLD_PATTERNS:
            for m in pat.finditer(report_text):
                try:
                    val = float(m.group(1))
                    if label not in thresholds:
                        thresholds[label] = []
                    if val not in thresholds[label]:
                        thresholds[label].append(val)
                except (ValueError, IndexError):
                    continue
        return thresholds

    def _crossref(self, code_thresholds: Dict, report_thresholds: Dict):
        """交叉比对代码阈值 vs 报告声称阈值"""
        for label, code_values in code_thresholds.items():
            if label not in report_thresholds:
                continue
            report_values = report_thresholds[label]

            # 去重代码中的唯一值
            unique_code = list(set(v for v, _ in code_values))

            for code_val in unique_code:
                # 检查报告中是否有匹配
                if code_val in report_values:
                    continue
                # p 值：检查是否更宽松（如代码 0.001 vs 报告 0.05）
                if label == 'p-value threshold':
                    for report_val in report_values:
                        if report_val != code_val:
                            files = [f for v, f in code_values if v == code_val]
                            severity = 'CRITICAL'
                            direction = '更宽松' if report_val > code_val else '更严格'
                            self.issues.append({
                                'severity': severity,
                                'category': '阈值不一致',
                                'message': (
                                    f'{label}: 报告声称 {report_val}，'
                                    f'但脚本 {files[0]} 中实际为 {code_val}'
                                    f'（报告比代码{direction}）'
                                ),
                                'file': files[0],
                                'evidence': {
                                    'label': label,
                                    'code_value': code_val,
                                    'report_value': report_val,
                                },
                            })
                elif label == 'logFC threshold':
                    for report_val in report_values:
                        if abs(report_val - code_val) > 0.01:
                            files = [f for v, f in code_values if v == code_val]
                            self.issues.append({
                                'severity': 'CRITICAL',
                                'category': '阈值不一致',
                                'message': (
                                    f'{label}: 报告声称 {report_val}，'
                                    f'但脚本 {files[0]} 中实际为 {code_val}'
                                ),
                                'file': files[0],
                                'evidence': {
                                    'label': label,
                                    'code_value': code_val,
                                    'report_value': report_val,
                                },
                            })
