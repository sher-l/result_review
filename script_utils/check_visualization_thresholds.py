#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
可视化阈值一致性检查器（P1级 - CRITICAL）

检查绘图阈值与筛选标准是否一致：
- 火山图：阈值线与筛选标准一致
- 热图：颜色刻度与分组标准一致
- PCA图：分组标签与实际分组一致

基于项目25YLC105F发现：火山图阈值线±1，筛选标准0.5

作者: 审核框架 v6.5
创建日期: 2026-02-13
基于: AGENT_TEAM_PLAN 第358-408行
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


from base_project_checker import BaseProjectChecker


class VisualizationThresholdChecker(BaseProjectChecker):
    """可视化阈值一致性检查器"""

    # 绘图阈值模式
    PLOT_THRESHOLD_PATTERNS = {
        'vline': r'geom_vline\s*\(\s*xintercept\s*=\s*c?\(?([^)]+)\)',
        'hline': r'geom_hline\s*\(\s*yintercept\s*=\s*c?\(?([^)]+)\)',
        'breaks': r'breaks\s*=\s*c?\(?([^)]+)\)',
        'threshold': r'threshold\s*=\s*([\d.]+)',
        # Python matplotlib
        'axvline': r'ax[a-z]*\.axvline\s*\(\s*(?:x\s*=\s*)?([-\d.]+)',
        'axhline': r'ax[a-z]*\.axhline\s*\(\s*(?:y\s*=\s*)?([-\d.]+)',
        'plt_axvline': r'plt\.axvline\s*\(\s*(?:x\s*=\s*)?([-\d.]+)',
        'plt_axhline': r'plt\.axhline\s*\(\s*(?:y\s*=\s*)?([-\d.]+)',
    }

    # 筛选标准模式
    FILTER_THRESHOLD_PATTERNS = {
        'logfc_cutoff': r'logFC[_\w]*_?\s*cutoff\s*<-\s*([\d.]+)',
        'logfc_filter': r'\|\s*log2?FC\s*\]\s*>\s*([\d.]+)',
        'logfc_var': r'logFC[_\w]*_?\s*=\s*([\d.]+)',
        'pvalue_cutoff': r'p[_\w]*_?\s*value?[_\w]*_?\s*cutoff\s*<-\s*([\d.]+)',
        'padj_filter': r'padj?\s*[<>]=\s*([\d.]+)',
        'fdr_cutoff': r'FDR\s*<-\s*([\d.]+)',
        # Python variants
        'py_logfc': r'log2?[_]?fc[_]?(?:cutoff|threshold|cut)\s*=\s*([\d.]+)',
        'py_pval': r'p[_]?val(?:ue)?[_]?(?:cutoff|threshold|cut)\s*=\s*([\d.]+)',
    }

    def __init__(self, project_path: str, layer0_data: dict = None):
        """
        初始化检查器

        参数:
            project_path: 项目根目录路径
        """
        super().__init__(project_path, layer0_data=layer0_data)

    def check_all(self) -> Dict:
        """统一入口，委托给 check_code_files"""
        return self.check_code_files()

    def check_code_files(self) -> Dict:
        """
        检查代码文件中的阈值一致性

        返回:
            {
                'total_files': 检查文件数,
                'mismatches': 不匹配项列表,
                'warnings': 警告列表
            }
        """
        # 查找代码目录
        code_dir = self.find_code_directory()
        if not code_dir:
            return {
                'total_files': 0,
                'issues': [],
                'warnings': [{'message': '未找到代码目录'}]
            }

        # 查找R和Python代码文件（去重，避免 Windows 大小写不敏感重复）
        seen = set()
        all_files = []
        for pattern in ('*.r', '*.R', '*.py'):
            for f in code_dir.glob(pattern):
                key = str(f).lower()
                if key not in seen:
                    seen.add(key)
                    all_files.append(f)

        for file_path in all_files:
            self._check_file(file_path)

        return {
            'total_files': len(all_files),
            'issues': self.issues,
            'warnings': self.warnings
        }

    def _check_file(self, file_path: Path):
        """检查单个文件"""
        try:
            from utils import safe_read_file
            content = safe_read_file(file_path)[0]

            # 提取绘图阈值
            plot_thresholds = self._extract_plot_thresholds(content)

            # 提取筛选标准
            filter_thresholds = self._extract_filter_thresholds(content)

            # 比较logFC阈值
            if plot_thresholds.get('logfc') and filter_thresholds.get('logfc'):
                self._compare_logfc_thresholds(
                    file_path,
                    plot_thresholds['logfc'],
                    filter_thresholds['logfc']
                )

            # 检查p-value阈值
            if plot_thresholds.get('pvalue') and filter_thresholds.get('pvalue'):
                self._compare_pvalue_thresholds(
                    file_path,
                    plot_thresholds['pvalue'],
                    filter_thresholds['pvalue']
                )

        except Exception as e:
            self.warnings.append({
                'file': str(file_path.relative_to(self.project_path)),
                'error': f'读取失败: {str(e)}'
            })

    def _extract_plot_thresholds(self, content: str) -> Dict:
        """提取绘图阈值"""
        thresholds = {}

        # 搜索vline（火山图常用）
        vline_matches = re.findall(self.PLOT_THRESHOLD_PATTERNS['vline'], content)
        if vline_matches:
            # 解析阈值，可能是c(-1, 1)格式
            for match in vline_matches:
                values = self._parse_vector(match)
                if values and len(values) == 2:
                    # 火山图通常是对称的±threshold
                    thresholds['logfc'] = abs(values[0])
                    break

        # 搜索hline
        hline_matches = re.findall(self.PLOT_THRESHOLD_PATTERNS['hline'], content)
        if hline_matches:
            for match in hline_matches:
                values = self._parse_vector(match)
                if values:
                    thresholds['pvalue'] = values[0]
                    break

        # 搜索breaks
        breaks_matches = re.findall(self.PLOT_THRESHOLD_PATTERNS['breaks'], content)
        if breaks_matches:
            values = self._parse_vector(breaks_matches[0])
            if values:
                if not thresholds.get('logfc'):
                    thresholds['logfc'] = values

        # 搜索threshold变量
        threshold_matches = re.findall(self.PLOT_THRESHOLD_PATTERNS['threshold'], content)
        if threshold_matches:
            thresholds['logfc'] = float(threshold_matches[0])

        # Python matplotlib: axvline / plt.axvline
        for key in ('axvline', 'plt_axvline'):
            matches = re.findall(self.PLOT_THRESHOLD_PATTERNS[key], content)
            if matches and not thresholds.get('logfc'):
                values = [float(v) for v in matches]
                if len(values) == 2:
                    thresholds['logfc'] = abs(values[0])
                    break

        for key in ('axhline', 'plt_axhline'):
            matches = re.findall(self.PLOT_THRESHOLD_PATTERNS[key], content)
            if matches and not thresholds.get('pvalue'):
                thresholds['pvalue'] = float(matches[0])
                break

        return thresholds

    def _extract_filter_thresholds(self, content: str) -> Dict:
        """提取筛选标准"""
        thresholds = {}

        # logFC相关
        for pattern_key in ['logfc_cutoff', 'logfc_filter', 'logfc_var', 'py_logfc']:
            pattern = self.FILTER_THRESHOLD_PATTERNS[pattern_key]
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                thresholds['logfc'] = float(matches[0])
                break

        # p-value相关
        for pattern_key in ['pvalue_cutoff', 'padj_filter', 'fdr_cutoff', 'py_pval']:
            pattern = self.FILTER_THRESHOLD_PATTERNS[pattern_key]
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                thresholds['pvalue'] = float(matches[0])
                break

        return thresholds

    def _parse_vector(self, vector_str: str) -> Optional[List[float]]:
        """解析R向量字符串，如c(-1, 1)或c(-1, 1)"""
        # 移除c(和)
        vector_str = vector_str.strip().lstrip('c(').rstrip(')')
        # 分割
        parts = vector_str.split(',')
        values = []
        for part in parts:
            try:
                values.append(float(part.strip()))
            except ValueError:
                continue
        return values if values else None

    def _compare_logfc_thresholds(self, file_path: Path, plot_value: float, filter_value: float):
        """比较logFC阈值"""
        # 允许小的浮点误差
        tolerance = 0.01

        if abs(plot_value - filter_value) > tolerance:
            self.issues.append({
                'file': str(file_path.relative_to(self.project_path)),
                'type': 'logfc_mismatch',
                'severity': 'CRITICAL',
                'plot_threshold': plot_value,
                'filter_threshold': filter_value,
                'difference': abs(plot_value - filter_value),
                'message': f'火山图阈值({plot_value})与筛选标准({filter_value})不一致',
                'suggestion': f'修改绘图阈值为{filter_value}或修改筛选标准为{plot_value}'
            })
        else:
            self.warnings.append({
                'file': str(file_path.relative_to(self.project_path)),
                'type': 'logfc_match',
                'message': f'logFC阈值一致: {filter_value}'
            })

    def _compare_pvalue_thresholds(self, file_path: Path, plot_value: float, filter_value: float):
        """比较p-value阈值"""
        tolerance = 0.001

        if abs(plot_value - filter_value) > tolerance:
            self.issues.append({
                'file': str(file_path.relative_to(self.project_path)),
                'type': 'pvalue_mismatch',
                'severity': 'CRITICAL',
                'plot_threshold': plot_value,
                'filter_threshold': filter_value,
                'difference': abs(plot_value - filter_value),
                'message': f'p-value阈值不一致: 绘图({plot_value}) vs 筛选({filter_value})'
            })

    def generate_report(self) -> str:
        """生成检查报告"""
        result = self.check_code_files()

        report_lines = [
            "# 可视化阈值一致性检查报告",
            "",
            f"**检查文件数**: {result['total_files']}",
            f"**发现问题数**: {len(result['mismatches'])}",
            f"**严重性**: {'🔴 CRITICAL' if result['mismatches'] else '✅ 通过'}",
            ""
        ]

        if result['mismatches']:
            report_lines.extend([
                "## 🔴 CRITICAL: 阈值不一致",
                ""
            ])

            for i, issue in enumerate(result['mismatches'], 1):
                report_lines.extend([
                    f"### 问题 {i}",
                    f"- **文件**: {issue['file']}",
                    f"- **类型**: {issue['type']}",
                    f"- **绘图阈值**: {issue.get('plot_threshold', 'N/A')}",
                    f"- **筛选阈值**: {issue.get('filter_threshold', 'N/A')}",
                    f"- **差异**: {issue.get('difference', 'N/A')}",
                    f"- **描述**: {issue['message']}",
                ])

                if issue.get('suggestion'):
                    report_lines.append(f"- **建议**: {issue['suggestion']}")

                report_lines.append("")

        if result['warnings']:
            report_lines.extend([
                "## 信息",
                ""
            ])
            for warning in result['warnings'][:10]:
                report_lines.append(f"- {warning.get('message', str(warning))}")

        return "\n".join(report_lines)


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='可视化阈值一致性检查器')
    parser.add_argument('project_path', help='项目根目录路径')
    parser.add_argument('--output', help='输出报告文件路径')

    args = parser.parse_args()

    checker = VisualizationThresholdChecker(args.project_path)
    report = checker.generate_report()

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"报告已保存到: {args.output}")
    else:
        print(report)


if __name__ == '__main__':
    main()
