#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
基因命名规范化检查器（P1级 - CRITICAL）

检查基因名称格式和质量：
- 标准格式：大写字母，无符号
- 蛋白复合物检测：同时包含-和_
- 非标准基因名：线粒体、HLA、免疫球蛋白、lncRNA

作者: 审核框架 v6.5
创建日期: 2026-02-13
基于: WORKFLOW.md 第99-149行
"""

import re
import pandas as pd
from pathlib import Path
from typing import Dict, List, Set, Tuple

from base_project_checker import BaseProjectChecker


class GeneNamingChecker(BaseProjectChecker):
    """基因命名规范化检查器"""

    # 非标准基因模式
    PATTERNS = {
        'protein_complex': re.compile(r'.*-.*_.*|.*_.*-.*'),  # 同时包含-和_（双向），与gene_set_quality统一
        'mitochondrial': re.compile(r'^MT-'),        # 线粒体基因，如MT-ND1
        'hla': re.compile(r'^HLA-'),                 # HLA基因，如HLA-A
        'immunoglobulin': re.compile(r'^IG[KHVL]'),  # 免疫球蛋白
        'lncrna': re.compile(r'^(LINC\d|MIR\d|RP11-)'),  # lncRNA/miRNA，需数字后缀避免误匹配
        'lowercase': re.compile(r'^[a-z]'),          # 小写开头
    }

    # 基因名中的问题符号
    PROBLEMATIC_SYMBOLS = ['-', '_', r'\.', ' ']

    # 基因列自动检测：已知列名候选
    GENE_COLUMN_CANDIDATES = [
        'gene_name', 'gene_symbol', 'Gene', 'gene', 'GENE',
        'Gene.symbol', 'Symbol', 'symbol', 'gene_id', 'GeneName',
        'Feature', 'feature', 'SYMBOL',
    ]

    # 基因名基本模式——用于判断一个值是否"看起来像基因名"
    _GENE_LIKE_RE = re.compile(r'^[A-Z][A-Za-z0-9][-A-Za-z0-9.]*$')

    def __init__(self, project_path: str, metadata=None, layer0_data: dict = None):
        """
        初始化检查器

        参数:
            project_path: 项目根目录路径
        """
        super().__init__(project_path, metadata=metadata, layer0_data=layer0_data)
        self.issues = []

    def check_gene_list(self, gene_list: List[str], source: str = "未知来源") -> Dict:
        """
        检查基因列表的命名规范

        参数:
            gene_list: 基因名称列表
            source: 数据来源描述

        返回:
            {
                'total_genes': 总基因数,
                'standard_genes': 标准基因数,
                'non_standard': 各类非标准基因统计,
                'issues': 问题列表
            }
        """
        # 标准化基因名
        standardized = [self._standardize_name(g) for g in gene_list]

        # 分类统计
        categories = {
            'protein_complex': [],
            'mitochondrial': [],
            'hla': [],
            'immunoglobulin': [],
            'lncrna': [],
            'lowercase': [],
            'has_symbols': [],
            'standard': []
        }

        for i, gene in enumerate(standardized):
            original = gene_list[i]

            # 检查各类非标准基因
            if self.PATTERNS['protein_complex'].match(gene):
                categories['protein_complex'].append(original)

            elif self.PATTERNS['mitochondrial'].match(gene):
                categories['mitochondrial'].append(original)

            elif self.PATTERNS['hla'].match(gene):
                categories['hla'].append(original)

            elif self.PATTERNS['immunoglobulin'].match(gene):
                categories['immunoglobulin'].append(original)

            elif self.PATTERNS['lncrna'].match(gene):
                categories['lncrna'].append(original)

            elif self.PATTERNS['lowercase'].match(gene):
                categories['lowercase'].append(original)

            elif any(sym in gene for sym in ['-', '_']):
                # 合法 HGNC 基因名常含连字符（如 KRTAP3-2, NKX6-2, HOXA-AS1）
                # 只记录到分类，不再逐个生成 issue（避免嘈音爆炸）
                categories['has_symbols'].append(original)

            elif ' ' in gene:
                # 含空格的值（如 "Activated B cell"）跳过，不计入任何分类
                pass

            else:
                categories['standard'].append(original)

        total_genes = len(gene_list)
        standard_count = len(categories['standard'])
        non_standard_count = total_genes - standard_count

        # 对 has_symbols 做聚合报告（仅一条汇总，避免千级噪音）
        if categories['has_symbols']:
            samples = categories['has_symbols'][:5]
            self.issues.append({
                'category': 'has_symbols',
                'source': source,
                'severity': 'INFO',
                'message': f"发现{len(categories['has_symbols'])}个含连字符/下划线的基因名（多数为合法HGNC命名），示例: {', '.join(samples)}"
            })

        # 对各特殊类别做聚合报告（每类一条汇总，避免千级噪音）
        # protein_complex 和 lowercase 也采用聚合模式（Iter5b）
        _agg_config = [
            ('protein_complex', '蛋白复合物基因', '需确认是否为复合物命名', 'CRITICAL'),
            ('lowercase', '小写开头基因名', '应为大写', 'WARNING'),
            ('mitochondrial', '线粒体基因', '需确认是否保留', 'WARNING'),
            ('hla', 'HLA基因', '需确认是否保留', 'WARNING'),
            ('immunoglobulin', '免疫球蛋白基因', '需确认是否保留', 'WARNING'),
            ('lncrna', 'lncRNA/miRNA', '需确认是否应该分析', 'WARNING'),
        ]
        for cat_key, cat_label, cat_advice, sev in _agg_config:
            if categories[cat_key]:
                samples = categories[cat_key][:5]
                target = self.issues if sev == 'CRITICAL' else self.warnings
                target.append({
                    'category': cat_key,
                    'source': source,
                    'severity': sev,
                    'message': f"发现{len(categories[cat_key])}个{cat_label}（{cat_advice}），示例: {', '.join(samples)}"
                })

        return {
            'source': source,
            'total_genes': total_genes,
            'standard_genes': standard_count,
            'non_standard_count': non_standard_count,
            'standard_rate': f"{(standard_count/total_genes*100):.1f}%" if total_genes > 0 else "N/A",
            'categories': {
                'protein_complex': categories['protein_complex'],
                'mitochondrial': categories['mitochondrial'],
                'hla': categories['hla'],
                'immunoglobulin': categories['immunoglobulin'],
                'lncrna': categories['lncrna'],
                'lowercase': categories['lowercase'],
                'has_symbols': categories['has_symbols']
            },
            'issues': self.issues,
            'warnings': self.warnings
        }

    def _detect_gene_column(self, df) -> str | None:
        """自动检测 DataFrame 中的基因列"""
        # 优先匹配已知列名
        for candidate in self.GENE_COLUMN_CANDIDATES:
            if candidate in df.columns:
                return candidate
        # 回退：检测第一列是否 ≥50% 像基因名
        first_col = df.columns[0]
        values = df[first_col].dropna().astype(str)
        if len(values) == 0:
            return None
        gene_like = sum(1 for v in values if self._GENE_LIKE_RE.match(v))
        if gene_like / len(values) >= 0.5:
            return first_col
        return None

    def check_csv_file(self, csv_file: Path, gene_column: str = None) -> Dict:
        """
        检查CSV文件中的基因名称

        参数:
            csv_file: CSV文件路径
            gene_column: 基因列名（如果为None，自动检测）

        返回:
            检查结果字典
        """
        try:
            df = pd.read_csv(csv_file)

            # 确定基因列
            if gene_column is None:
                gene_column = self._detect_gene_column(df)
                if gene_column is None:
                    return {
                        'source': str(csv_file),
                        'skipped': True,
                        'message': '未检测到基因列，跳过'
                    }

            if gene_column not in df.columns:
                return {
                    'source': str(csv_file),
                    'error': f'未找到基因列: {gene_column}'
                }

            gene_list = df[gene_column].dropna().astype(str).tolist()

            return self.check_gene_list(
                gene_list,
                source=f"文件: {csv_file.name}, 列: {gene_column}"
            )

        except Exception as e:
            return {
                'source': str(csv_file),
                'error': f'读取失败: {str(e)}'
            }

    def check_all(self) -> Dict:
        """统一入口，委托给 check_all_gene_files"""
        return self.check_all_gene_files()

    def check_all_gene_files(self) -> Dict:
        """
        检查项目中所有可能的基因文件

        返回:
            汇总检查结果
        """
        # 查找常见的基因文件
        patterns = [
            '*gene*.csv',
            '*ERG*.csv',
            '*DEG*.csv',
            '*final*.csv',
            '*intersection*.csv',
            '*common*.csv',
            '*inter*.csv'
        ]

        all_results = []

        # 优先在编号模块目录中搜索（利用基类 find_modules），回退到全项目
        modules = self.find_modules()
        search_roots = modules if modules else [self.project_path]

        for pattern in patterns:
            if self.metadata is not None:
                files = self.metadata.rglob(pattern)
            else:
                files = []
                for root in search_roots:
                    files.extend(root.rglob(pattern))
            for file in files:
                result = self.check_csv_file(file)
                all_results.append(result)

        # 汇总统计
        return {
            'total_files_checked': len(all_results),
            'results': all_results,
            'summary': self._summarize_results(all_results),
            'issues': self.issues,
            'warnings': self.warnings,
        }

    def _summarize_results(self, results: List[Dict]) -> Dict:
        """汇总多个检查结果"""
        summary = {
            'protein_complex': [],
            'mitochondrial': [],
            'hla': [],
            'immunoglobulin': [],
            'lncrna': [],
            'lowercase': [],
            'has_symbols': [],
            'standard': []
        }

        for result in results:
            if 'categories' in result:
                for category, genes in result['categories'].items():
                    if genes:
                        summary[category].extend(genes)

        # 去重
        for category in summary:
            summary[category] = list(set(summary[category]))

        return summary

    def _standardize_name(self, gene_name: str) -> str:
        """标准化基因名"""
        return str(gene_name).upper().strip()

    def generate_report(self) -> str:
        """生成检查报告"""
        result = self.check_all_gene_files()

        report_lines = [
            "# 基因命名规范化检查报告",
            "",
            f"**检查文件数**: {result['total_files_checked']}",
            "",
            "## 非标准基因分类统计",
            ""
        ]

        summary = result['summary']

        # 蛋白复合物（CRITICAL）
        if summary['protein_complex']:
            report_lines.extend([
                "### 🔴 CRITICAL: 蛋白复合物基因",
                "",
                "**建议**: 必须删除，这些是蛋白复合物而非单个基因",
                "",
                f"数量: {len(summary['protein_complex'])}",
                f"基因: {', '.join(summary['protein_complex'][:10])}",
                f"{'...' if len(summary['protein_complex']) > 10 else ''}",
                ""
            ])

        # 其他非标准基因
        other_categories = {
            '线粒体基因': summary['mitochondrial'],
            'HLA基因': summary['hla'],
            '免疫球蛋白': summary['immunoglobulin'],
            'lncRNA/miRNA': summary['lncrna'],
            '小写开头': summary['lowercase']
        }

        for category_name, genes in other_categories.items():
            if genes:
                report_lines.extend([
                    f"### ⚠️ {category_name}",
                    "",
                    "**建议**: 需确认是否保留",
                    "",
                    f"数量: {len(genes)}",
                    f"基因: {', '.join(genes[:10])}",
                    f"{'...' if len(genes) > 10 else ''}",
                    ""
                ])

        # 各文件详情
        if result['results']:
            report_lines.extend([
                "## 各文件检查详情",
                ""
            ])

            for file_result in result['results']:
                if 'error' in file_result:
                    report_lines.append(f"### {file_result['source']}")
                    report_lines.append(f"❌ 错误: {file_result['error']}")
                    report_lines.append("")

                elif 'issues' in file_result and file_result['issues']:
                    source = file_result['source']
                    total = file_result['total_genes']
                    standard = file_result['standard_genes']
                    rate = file_result['standard_rate']

                    report_lines.extend([
                        f"### {source}",
                        f"- **总基因数**: {total}",
                        f"- **标准基因数**: {standard} ({rate})",
                        f"- **非标准基因数**: {total - standard}",
                        ""
                    ])

        return "\n".join(report_lines)


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='基因命名规范化检查器')
    parser.add_argument('project_path', help='项目根目录路径')
    parser.add_argument('--file', help='指定要检查的CSV文件')
    parser.add_argument('--column', help='基因列名（默认使用第一列）')
    parser.add_argument('--output', help='输出报告文件路径')

    args = parser.parse_args()

    checker = GeneNamingChecker(args.project_path)

    if args.file:
        # 检查单个文件
        result = checker.check_csv_file(Path(args.file), args.column)
        print(f"\n检查文件: {args.file}")
        print(f"总基因数: {result.get('total_genes', 0)}")
        print(f"标准基因数: {result.get('standard_genes', 0)}")
        print(f"标准率: {result.get('standard_rate', 'N/A')}")
    else:
        # 检查所有文件
        report = checker.generate_report()

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"报告已保存到: {args.output}")
        else:
            print(report)


if __name__ == '__main__':
    main()
