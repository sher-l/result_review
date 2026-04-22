#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
跨模块数据流验证器（P0级 - FATAL）

基于项目25YLC105F的发现：monocle分析只用3个基因，而上游交集有19个基因

FATAL级标准：
- 下游分析使用的基因数 ≠ 上游输出 → FATAL，数据流断裂

作者: 审核框架 v6.5
创建日期: 2026-02-13
"""

import re
import csv
from pathlib import Path
from typing import Dict, List, Set, Optional

from base_project_checker import BaseProjectChecker
from utils import safe_read_file


class DataFlowValidator(BaseProjectChecker):
    """跨模块数据流验证器"""

    def __init__(self, project_path: str, metadata=None, layer0_data: dict = None):
        """
        初始化验证器

        参数:
            project_path: 项目根目录路径
        """
        super().__init__(project_path, metadata=metadata, layer0_data=layer0_data)
        self.issues = []

    def _find_patterns(self, patterns: List[str]) -> List[Path]:
        if self.metadata is not None:
            return self.metadata.find_by_patterns(patterns)
        # 优先在编号模块目录中搜索（利用基类 find_modules）
        modules = self.find_modules()
        if modules:
            results = []
            for mod in modules:
                for p in patterns:
                    results.extend(mod.rglob(p))
            if results:
                return results
        # 回退：全项目搜索
        return [f for p in patterns for f in self.project_path.rglob(p)]

    def check_all(self) -> Dict:
        """统一入口，委托给 validate_all_flows"""
        return self.validate_all_flows()

    def validate_all_flows(self) -> Dict:
        """
        验证所有跨模块数据流

        检查的关键数据流：
        1. DEG分析 → 富集分析
        2. ML筛选 → GSEA
        3. 交集计算 → monocle
        4. 单细胞 → 空间转录组

        返回:
            {
                'total_checks': 总检查数,
                'failed_checks': 失败检查数,
                'issues': 问题列表,
                'fatal': 是否有FATAL级问题
            }
        """
        # 自动检测并验证关键数据流
        self._validate_deg_to_enrichment()
        self._validate_ml_to_gsea()
        self._validate_intersection_to_monocle()
        self._validate_scrna_to_spatial()

        fatal = any(issue.get('severity') == 'FATAL' for issue in self.issues)

        return {
            'total_checks': 4,
            'failed_checks': len(self.issues),
            'issues': self.issues,
            'warnings': self.warnings,
            'fatal': fatal
        }

    def _read_csv_rows(self, file_path: Path) -> List[Dict[str, str]]:
        """使用标准库读取 CSV/TSV，自动检测分隔符和编码。"""
        content, _ = safe_read_file(file_path)
        if not content:
            return []

        content = content.replace('\r\n', '\n')
        sample = content[:4096]

        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            # 按扩展名回退
            dialect = csv.excel_tab if file_path.suffix.lower() in ('.tsv', '.txt') else csv.excel

        import io
        reader = csv.DictReader(io.StringIO(content), dialect=dialect)
        return list(reader)

    def _validate_deg_to_enrichment(self):
        """
        验证DEG分析 → 富集分析的数据流
        """
        # 查找DEG结果文件
        deg_files = self._find_patterns([
            '*DEG*.csv', '*DEGs*.csv', '*DEG*.tsv', '*DEGs*.tsv'
        ])

        if not deg_files:
            self.warnings.append({
                'flow': 'DEG → Enrichment',
                'severity': 'INFO',
                'message': '未找到DEG结果文件'
            })
            return

        # 查找富集分析使用的基因集
        enrichment_files = self._find_patterns(['*enrich*.csv', '*GSEA*.csv'])

        # 记录数据流
        for deg_file in deg_files:
            try:
                rows = self._read_csv_rows(deg_file)
                deg_count = len(rows)

                # 检查是否有对应的富集分析
                if enrichment_files:
                    # 基本检查：富集分析应该使用DEG结果
                    self.warnings.append({
                        'flow': 'DEG → Enrichment',
                        'severity': 'INFO',
                        'deg_file': str(deg_file.relative_to(self.project_path)),
                        'deg_count': deg_count,
                        'enrichment_files': [str(f.relative_to(self.project_path)) for f in enrichment_files],
                        'message': f'DEG文件包含{deg_count}个基因，富集分析应使用相同基因集'
                    })
            except Exception as e:
                self.warnings.append({
                    'flow': 'DEG → Enrichment',
                    'file': str(deg_file.relative_to(self.project_path)),
                    'error': str(e)
                })

    def _validate_ml_to_gsea(self):
        """
        验证ML筛选 → GSEA的数据流
        """
        # 查找ML结果文件（intersection）
        ml_files = self._find_patterns(['*common*.csv', '*intersection*.csv', '*inter*.csv'])

        for ml_file in ml_files:
            try:
                rows = self._read_csv_rows(ml_file)
                ml_count = len(rows)

                # 检查GSEA是否使用相同的基因集
                gsea_files = self._find_patterns(['*GSEA*.csv'])

                if gsea_files:
                    for gsea_file in gsea_files:
                        try:
                            gsea_rows = self._read_csv_rows(gsea_file)
                            gsea_count = len(gsea_rows)
                            # 基因数量缩减检测（Iter5b）
                            if ml_count > 0 and gsea_count > 0:
                                reduction = 1 - (gsea_count / ml_count) if gsea_count < ml_count else 0
                                if reduction >= 0.5:
                                    self.issues.append({
                                        'flow': 'ML → GSEA',
                                        'severity': 'CRITICAL',
                                        'ml_file': str(ml_file.relative_to(self.project_path)),
                                        'ml_count': ml_count,
                                        'gsea_file': str(gsea_file.relative_to(self.project_path)),
                                        'gsea_entries': gsea_count,
                                        'message': f'基因链大幅缩减: ML交集{ml_count}个 → GSEA仅{gsea_count}个（缩减{reduction*100:.0f}%）'
                                    })
                                    continue
                            self.warnings.append({
                                'flow': 'ML → GSEA',
                                'severity': 'INFO',
                                'ml_file': str(ml_file.relative_to(self.project_path)),
                                'ml_count': ml_count,
                                'gsea_file': str(gsea_file.relative_to(self.project_path)),
                                'gsea_entries': gsea_count,
                                'message': f'ML交集{ml_count}个基因，GSEA应使用相同基因集'
                            })
                        except Exception:
                            pass
            except Exception as e:
                self.warnings.append({
                    'flow': 'ML → GSEA',
                    'file': str(ml_file.relative_to(self.project_path)),
                    'error': str(e)
                })

    def _validate_intersection_to_monocle(self):
        """
        验证交集计算 → monocle的数据流

        这是25YLC105F项目发现的关键问题
        """
        # 查找交集文件
        inter_files = self._find_patterns(['*inter*.csv', '*common*.csv', '*06_inter*/*.csv'])

        # 查找monocle代码
        monocle_files = self._find_patterns(['*monocle*.r', '*monocle*.R', 'r.*1*_monocle*.r'])

        for inter_file in inter_files:
            try:
                rows = self._read_csv_rows(inter_file)

                # 假设第一列是基因名
                if rows:
                    gene_col = next(iter(rows[0].keys()))
                    inter_genes = {
                        str(row.get(gene_col, '')).strip().upper()
                        for row in rows
                        if str(row.get(gene_col, '')).strip()
                    }
                    inter_count = len(inter_genes)

                    # 检查monocle代码中使用的基因
                    for monocle_file in monocle_files:
                        monocle_genes = self._extract_monocle_genes(monocle_file)

                        if monocle_genes:
                            monocle_count = len(monocle_genes)

                            # 检查是否是子集
                            is_subset = monocle_genes.issubset(inter_genes)

                            if not is_subset:
                                # 有monocle使用的基因不在交集中
                                unexpected = monocle_genes - inter_genes
                                self.issues.append({
                                    'flow': 'Intersection → Monocle',
                                    'severity': 'FATAL',
                                    'inter_file': str(inter_file.relative_to(self.project_path)),
                                    'inter_count': inter_count,
                                    'monocle_file': str(monocle_file.relative_to(self.project_path)),
                                    'monocle_count': monocle_count,
                                    'unexpected_genes': list(unexpected),
                                    'message': f'🔴 FATAL: Monocle使用了{len(unexpected)}个不在交集的基因: {", ".join(list(unexpected)[:5])}'
                                })
                            elif monocle_count < inter_count:
                                # monocle只使用了交集的一部分
                                unused = inter_genes - monocle_genes
                                if len(unused) > 5:  # 超过5个基因差异
                                    self.issues.append({
                                        'flow': 'Intersection → Monocle',
                                        'severity': 'FATAL',
                                        'inter_file': str(inter_file.relative_to(self.project_path)),
                                        'inter_count': inter_count,
                                        'monocle_file': str(monocle_file.relative_to(self.project_path)),
                                        'monocle_count': monocle_count,
                                        'unused_genes_count': len(unused),
                                        'message': f'🔴 FATAL: 数据流断裂 - 交集有{inter_count}个基因，但monocle只使用{monocle_count}个'
                                    })
            except Exception as e:
                self.warnings.append({
                    'flow': 'Intersection → Monocle',
                    'file': str(inter_file.relative_to(self.project_path)),
                    'error': str(e)
                })

    def _validate_scrna_to_spatial(self):
        """
        验证单细胞 → 空间转录组的数据流
        """
        # 查找单细胞注释文件
        scrna_files = self._find_patterns(['*cell*type*.csv', '*annotation*.csv', '*02_sc*/*.csv'])

        # 查找空间转录组文件
        spatial_files = self._find_patterns(['*spatial*.csv', '*Spatial*.csv'])

        if scrna_files and spatial_files:
            self.warnings.append({
                'flow': 'scRNA → Spatial',
                'severity': 'INFO',
                'scrna_files': [str(f.relative_to(self.project_path)) for f in scrna_files[:3]],
                'spatial_files': [str(f.relative_to(self.project_path)) for f in spatial_files[:3]],
                'message': '检测到单细胞和空间转录组分析，需验证细胞类型映射一致性'
            })

    def _extract_monocle_genes(self, monocle_file: Path) -> Optional[Set[str]]:
        """
        从monocle代码文件中提取使用的基因

        返回: 基因集合，如果无法提取则返回None
        """
        try:
            from utils import safe_read_file
            content = safe_read_file(monocle_file)[0]

            genes = set()

            # 通用模式：支持多行 c("GENE1", "GENE2", ...) 定义
            # 匹配常见变量名赋值后的 c(...) 向量
            var_pattern = r'(?:features|gene_list|hub_genes|target_genes|genes|selected_genes)\s*(?:<-|=)\s*c\s*\((.*?)\)'
            for match in re.finditer(var_pattern, content, re.DOTALL | re.IGNORECASE):
                # 从 c() 内部提取所有带引号的基因名
                quoted = re.findall(r'["\']([^"\']+)["\']', match.group(1))
                for gene in quoted:
                    genes.add(gene.strip().upper())

            # 如果上面没匹配到，尝试更宽泛的 c("...") 模式（任意变量名）
            if not genes:
                broad_pattern = r'\b\w+\s*(?:<-|=)\s*c\s*\(((?:[^()]*?"[A-Z][A-Z0-9]+"[^()]*?)+)\)'
                for match in re.finditer(broad_pattern, content, re.DOTALL):
                    quoted = re.findall(r'"([A-Z][A-Z0-9]+)"', match.group(1))
                    for gene in quoted:
                        genes.add(gene.strip().upper())

            return genes if genes else None
        except Exception:
            return None

    def generate_report(self) -> str:
        """生成验证报告"""
        result = self.validate_all_flows()

        report_lines = [
            "# 跨模块数据流验证报告",
            "",
            f"**检查的数据流数**: {result['total_checks']}",
            f"**发现问题数**: {result['failed_checks']}",
            f"**严重性**: {'🔴 FATAL' if result['fatal'] else '✅ 通过' if result['failed_checks'] == 0 else '⚠️ 有问题'}",
            ""
        ]

        if result['issues']:
            # 按严重性分组
            fatal_issues = [i for i in result['issues'] if i.get('severity') == 'FATAL']
            other_issues = [i for i in result['issues'] if i.get('severity') != 'FATAL']

            if fatal_issues:
                report_lines.extend([
                    "## 🔴 FATAL级问题 - 数据流断裂",
                    ""
                ])
                for i, issue in enumerate(fatal_issues, 1):
                    report_lines.extend([
                        f"### 问题 {i}",
                        f"- **数据流**: {issue['flow']}",
                        f"- **上游文件**: {issue.get('inter_file', issue.get('ml_file', 'N/A'))}",
                        f"- **上游基因数**: {issue.get('inter_count', issue.get('ml_count', 'N/A'))}",
                        f"- **下游文件**: {issue.get('monocle_file', issue.get('gsea_file', 'N/A'))}",
                        f"- **下游基因数**: {issue.get('monocle_count', issue.get('gsea_entries', 'N/A'))}",
                        f"- **描述**: {issue['message']}",
                        ""
                    ])

            if other_issues:
                report_lines.extend([
                    "## 🟡 其他问题",
                    ""
                ])
                for i, issue in enumerate(other_issues, 1):
                    report_lines.extend([
                        f"### 问题 {i}",
                        f"- **数据流**: {issue['flow']}",
                        f"- **描述**: {issue['message']}",
                        ""
                    ])

        if result['warnings']:
            report_lines.extend([
                "## ⚠️ 警告",
                ""
            ])
            for i, warning in enumerate(result['warnings'], 1):
                report_lines.append(f"{i}. {warning.get('message', str(warning))}")

        if result['fatal']:
            report_lines.extend([
                "",
                "## 🔴 FATAL级问题",
                "",
                "**影响**: 数据流断裂，后续分析基于错误输入，研究结论不可靠",
                "**建议**: 确保下游分析使用完整的上游输出结果",
                ""
            ])

        return "\n".join(report_lines)

    def is_fatal(self) -> bool:
        """判断是否为FATAL级问题"""
        result = self.validate_all_flows()
        return result['fatal']


def main():
    """命令行入口"""
    import sys
    import argparse

    parser = argparse.ArgumentParser(description='跨模块数据流验证器')
    parser.add_argument('project_path', help='项目根目录路径')
    parser.add_argument('--output', help='输出报告文件路径')

    args = parser.parse_args()

    validator = DataFlowValidator(args.project_path)
    report = validator.generate_report()

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"报告已保存到: {args.output}")
    else:
        print(report)

    sys.exit(1 if validator.is_fatal() else 0)


if __name__ == '__main__':
    main()
