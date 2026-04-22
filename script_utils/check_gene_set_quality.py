#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
基因集质量检查工具 
功能：
1. 检测蛋白复合物基因（包含连字符和下划线）
2. 分类统计非标准基因名（MT-, HLA-, IG*, lncRNA）
3. 基因命名格式验证
4. 生成质量检查报告

用途：Step 0 - 基因集物种和质量预检

注意：本检查器不继承 BaseProjectChecker，不注册在 orchestrator registry 中。
它接受单个基因集文件路径（非项目路径），在 Layer 0 或手动场景下单独调用。
"""

import pandas as pd
import re
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime


class GeneSetQualityChecker:
    """基因集质量检查器"""

    def __init__(self, gene_set_path: str, layer0_data: dict = None):
        """
        Args:
            gene_set_path: 基因集CSV文件路径
        """
        self.gene_set_path = Path(gene_set_path)
        self._layer0_data = layer0_data or {}
        self.df = None
        self.results = {
            'total_genes': 0,
            'standard_genes': 0,
            'protein_complexes': [],
            'mitochondrial': [],
            'hla': [],
            'immunoglobulin': [],
            'lncrna': [],
            'other_nonstandard': []
        }

    # 常见基因列名候选
    GENE_COLUMN_CANDIDATES = [
        'gene_name', 'gene_symbol', 'Gene', 'gene', 'GENE',
        'Gene.symbol', 'Symbol', 'symbol', 'gene_id', 'GeneName'
    ]

    def _detect_gene_column(self) -> str:
        """自动检测基因列名，返回匹配的列名或None"""
        if self.df is None:
            return None
        for candidate in self.GENE_COLUMN_CANDIDATES:
            if candidate in self.df.columns:
                return candidate
        # 回退：尝试第一列（很多基因列表第一列就是基因名）
        first_col = self.df.columns[0]
        sample = self.df[first_col].dropna().head(20).astype(str)
        gene_like = sample.str.match(r'^[A-Z][A-Za-z0-9-]+$', na=False).sum()
        if gene_like >= len(sample) * 0.5:
            return first_col
        return None

    def load_gene_set(self, gene_column: str = None) -> bool:
        """
        加载基因集文件

        Args:
            gene_column: 基因名列名，None则自动检测

        Returns:
            是否成功加载
        """
        if not self.gene_set_path.exists():
            print(f"✗ 文件不存在: {self.gene_set_path}")
            return False

        try:
            self.df = pd.read_csv(self.gene_set_path)

            if gene_column is None:
                gene_column = self._detect_gene_column()
                if gene_column is None:
                    print(f"✗ 无法自动检测基因列")
                    print(f"  可用列: {self.df.columns.tolist()}")
                    return False
                print(f"  自动检测基因列: '{gene_column}'")

            if gene_column not in self.df.columns:
                print(f"✗ 基因列 '{gene_column}' 不存在于文件中")
                print(f"  可用列: {self.df.columns.tolist()}")
                return False

            self._gene_column = gene_column
            self.results['total_genes'] = len(self.df)
            print(f"✓ 成功加载基因集: {self.results['total_genes']} 个基因")
            return True

        except Exception as e:
            print(f"✗ 读取文件失败: {str(e)}")
            return False

    def check_quality(self, gene_column: str = None) -> Dict:
        """
        执行质量检查

        Args:
            gene_column: 基因名列名，None则自动检测

        Returns:
            检查结果字典
        """
        if self.df is None:
            if not self.load_gene_set(gene_column):
                return self.results

        col = gene_column or getattr(self, '_gene_column', None) or self._detect_gene_column()
        if col is None or col not in self.df.columns:
            print(f"✗ 无法定位基因列")
            return self.results

        genes = self.df[col].dropna().astype(str)
        self.results['total_genes'] = len(genes)

        print(f"\n开始检查 {self.results['total_genes']} 个基因...")

        # 1. 检测蛋白复合物
        self._detect_protein_complexes(genes)

        # 2. 检测线粒体基因
        self._detect_mitochondrial(genes)

        # 3. 检测HLA基因
        self._detect_hla(genes)

        # 4. 检测免疫球蛋白
        self._detect_immunoglobulin(genes)

        # 5. 检测lncRNA
        self._detect_lncrna(genes)

        # 6. 统计标准基因
        self._count_standard_genes(genes)

        return self.results

    def _detect_protein_complexes(self, genes: pd.Series):
        """检测蛋白复合物（包含连字符和下划线）"""
        pattern = re.compile(r'.*-.*_.*|.*_.*-.*')
        matches = genes[genes.str.match(pattern, na=False)]

        self.results['protein_complexes'] = matches.tolist()

        if len(matches) > 0:
            print(f"\n🔴 发现 {len(matches)} 个蛋白复合物基因 (必须删除)")
            for gene in matches.head(10):  # 只显示前10个
                print(f"  - {gene}")
            if len(matches) > 10:
                print(f"  ... 还有 {len(matches) - 10} 个")

    def _detect_mitochondrial(self, genes: pd.Series):
        """检测线粒体基因"""
        pattern = re.compile(r'^MT-')
        matches = genes[genes.str.match(pattern, na=False)]

        self.results['mitochondrial'] = matches.tolist()

        if len(matches) > 0:
            print(f"\n⚠ 发现 {len(matches)} 个线粒体基因 (需确认是否保留)")
            print(f"  示例: {', '.join(matches.head(5).tolist())}")

    def _detect_hla(self, genes: pd.Series):
        """检测HLA基因"""
        pattern = re.compile(r'^HLA-')
        matches = genes[genes.str.match(pattern, na=False)]

        self.results['hla'] = matches.tolist()

        if len(matches) > 0:
            print(f"\n⚠ 发现 {len(matches)} 个HLA基因 (需确认是否保留)")
            print(f"  示例: {', '.join(matches.head(5).tolist())}")

    def _detect_immunoglobulin(self, genes: pd.Series):
        """检测免疫球蛋白基因"""
        pattern = re.compile(r'^IG[A-Z]')
        matches = genes[genes.str.match(pattern, na=False)]

        self.results['immunoglobulin'] = matches.tolist()

        if len(matches) > 0:
            print(f"\n⚠ 发现 {len(matches)} 个免疫球蛋白基因 (需确认是否保留)")
            print(f"  示例: {', '.join(matches.head(5).tolist())}")

    def _detect_lncrna(self, genes: pd.Series):
        """检测lncRNA — 与 GeneNamingChecker 的 lncrna 正则保持统一"""
        pattern = re.compile(r'^(LINC\d|MIR\d|RP11-)')
        matches = genes[genes.str.match(pattern, na=False)]

        self.results['lncrna'] = matches.tolist()

        if len(matches) > 0:
            print(f"\n⚠ 发现 {len(matches)} 个lncRNA (需确认是否应该分析)")
            print(f"  示例: {', '.join(matches.head(5).tolist())}")

    def _count_standard_genes(self, genes: pd.Series):
        """统计标准基因"""
        # 排除所有非标准基因
        nonstandard = set(
            self.results['protein_complexes'] +
            self.results['mitochondrial'] +
            self.results['hla'] +
            self.results['immunoglobulin'] +
            self.results['lncrna']
        )

        standard = genes[~genes.isin(nonstandard)]
        self.results['standard_genes'] = len(standard)

        print(f"\n✓ 标准基因名: {self.results['standard_genes']} 个")

    def generate_report(self, output_path: str = None):
        """
        生成质量检查报告

        Args:
            output_path: 输出文件路径
        """
        if output_path is None:
            output_path = self.gene_set_path.parent / f"{self.gene_set_path.stem}_quality_report.txt"

        output_path = Path(output_path)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("基因集质量检查报告\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"检查文件: {self.gene_set_path.name}\n\n")

            f.write("=" * 80 + "\n")
            f.write("检查结果汇总\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"总基因数: {self.results['total_genes']}\n")
            f.write(f"标准基因名: {self.results['standard_genes']} ({self.results['standard_genes']/self.results['total_genes']*100:.1f}%)\n\n")

            # 蛋白复合物
            f.write("【蛋白复合物】🔴 必须删除\n")
            f.write("-" * 80 + "\n")
            f.write(f"数量: {len(self.results['protein_complexes'])}\n")
            if self.results['protein_complexes']:
                f.write(f"列表:\n")
                for gene in self.results['protein_complexes']:
                    f.write(f"  - {gene}\n")
            f.write("\n")

            # 其他非标准基因
            f.write("【非标准基因名】⚠️ 需确认\n")
            f.write("-" * 80 + "\n")
            f.write(f"线粒体基因 (MT-): {len(self.results['mitochondrial'])} 个\n")
            f.write(f"HLA基因 (HLA-): {len(self.results['hla'])} 个\n")
            f.write(f"免疫球蛋白 (IG*): {len(self.results['immunoglobulin'])} 个\n")
            f.write(f"lncRNA (LINC*, MIR*): {len(self.results['lncrna'])} 个\n\n")

            # 建议
            f.write("=" * 80 + "\n")
            f.write("处理建议\n")
            f.write("=" * 80 + "\n\n")

            if len(self.results['protein_complexes']) > 0:
                f.write("1. 🔴 FATAL: 发现蛋白复合物基因，建议从基因集中删除\n")
                f.write(f"   - 删除这 {len(self.results['protein_complexes'])} 个基因\n\n")

            nonstandard_count = (
                len(self.results['mitochondrial']) +
                len(self.results['hla']) +
                len(self.results['immunoglobulin']) +
                len(self.results['lncrna'])
            )

            if nonstandard_count > 0:
                f.write("2. ⚠️ WARNING: 非标准基因名数量较多，建议确认:\n")
                f.write(f"   - 线粒体基因: 是否保留线粒体功能分析\n")
                f.write(f"   - HLA基因: 是否保留免疫相关分析\n")
                f.write(f"   - 免疫球蛋白: 是否保留免疫相关分析\n")
                f.write(f"   - lncRNA: 确认是否应该分析lncRNA（还是只分析蛋白编码基因）\n\n")

            if self.results['standard_genes'] / self.results['total_genes'] < 0.8:
                f.write("3. ⚠️ WARNING: 标准基因名占比低于80%，建议全面检查基因集来源和质量\n\n")

        print(f"\n✓ 报告已保存到: {output_path}")


class GeneSetQualityProjectChecker:
    """项目级基因集质量检查器包装器。

    继承 BaseProjectChecker 的接口约定（接受 project_path，返回 check_all() 结果字典），
    内部复用 GeneSetQualityChecker 对逐个基因集文件进行检查。

    这使得该检查器可以和其他检查器一样被 CheckOrchestrator 注册表统一调度。
    """

    def __init__(self, project_path: str, metadata=None, layer0_data: dict = None):
        self.project_path = Path(project_path).resolve()
        self.metadata = metadata
        self._layer0_data = layer0_data or {}
        self.issues = []
        self.warnings = []
        self._cached_report_text = None

    def check_all(self) -> dict:
        """扫描项目中的基因集文件并逐个检查质量。"""
        gene_set_files = []
        if self.metadata is not None:
            gene_set_files = self.metadata.find_by_patterns([
                '*gene*.csv', '*ERG*.csv', '*final_*.csv'
            ])
        if not gene_set_files:
            return {
                'skipped': True,
                'issues': [],
                'warnings': [],
                'total_checks': 0,
                'failed_checks': 0,
            }

        files_to_check = gene_set_files[:5]
        all_issues = []
        for gsf in files_to_check:
            try:
                gs = GeneSetQualityChecker(str(gsf), layer0_data=self._layer0_data)
                gs_result = gs.check_quality()
                if gs_result.get('protein_complexes'):
                    all_issues.append({
                        'severity': 'CRITICAL',
                        'module': str(gsf.name),
                        'message': f"基因集 {gsf.name} 含 {len(gs_result['protein_complexes'])} 个蛋白复合物基因",
                        'details': gs_result['protein_complexes'][:10],
                    })
            except Exception as e:
                self.warnings.append(f"检查 {gsf.name} 失败: {e}")

        return {
            'issues': all_issues,
            'warnings': self.warnings,
            'total_checks': len(files_to_check),
            'failed_checks': len(all_issues),
            'skipped': False,
        }


def main():
    """命令行入口"""
    import sys

    if len(sys.argv) < 2:
        print("用法:")
        print("  python check_gene_set_quality.py <基因集CSV文件> [基因列名]")
        print("")
        print("示例:")
        print("  python check_gene_set_quality.py final_ERGs.csv")
        print("  python check_gene_set_quality.py final_ERGs.csv gene_symbol")
        sys.exit(1)

    gene_set_path = sys.argv[1]
    gene_column = sys.argv[2] if len(sys.argv) > 2 else 'gene_name'

    checker = GeneSetQualityChecker(gene_set_path)
    checker.check_quality(gene_column)
    checker.generate_report()


if __name__ == "__main__":
    main()
