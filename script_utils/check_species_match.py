#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
物种匹配检查工具 
功能：
1. 搜索项目中所有.gmt文件
2. 检查.gmt文件物种标识
3. 检查代码中.gmt文件引用
4. 验证基因集与分析数据物种匹配

用途：Step 0 - 基因集物种验证
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime


from base_project_checker import BaseProjectChecker


class SpeciesChecker(BaseProjectChecker):
    """物种匹配检查器"""

    # 常见基因集物种标识
    SPECIES_MARKERS = {
        'human': ['Hs', 'h.all', 'human', 'Homo_sapiens', 'xCell', 'LM22', 'EPIC'],
        'mouse': ['Mm', 'mouse', 'Mus_musculus', 'mmc3', 'mm10'],
        'rat': ['Rn', 'rat', 'Rattus_norvegicus']
    }

    # 数据集编号物种判断
    DATASET_SPECIES = {
        'GSE*M': 'mouse',  # GSE + M后缀可能是小鼠
        'GSE*': 'human',   # GSE无后缀通常是人类
    }

    def __init__(self, project_path: str, data_species: str = 'unknown', layer0_data: dict = None):
        """
        Args:
            project_path: 项目路径
            data_species: 分析数据物种 ('human', 'mouse', 'rat', 'unknown')
        """
        super().__init__(project_path, layer0_data=layer0_data)
        self.data_species = data_species
        self.results = {
            'gmt_files': [],
            'code_references': [],
            'species_mismatches': [],
            'warnings': [],
            'recommendations': []
        }

    def check_all(self) -> Dict:
        """执行所有检查"""
        print("=" * 80)
        print("Step 0: 物种和质量预检 - 基因集物种验证")
        print("=" * 80)
        print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # 1. 搜索所有.gmt文件
        self._find_gmt_files()

        # 2. 检查代码中.gmt引用
        self._scan_code_references()

        # 3. 验证物种匹配
        self._verify_species_match()

        # 4. 生成建议
        self._generate_recommendations()

        # 统一返回值：映射 species_mismatches → issues 供 orchestrator 消费
        self.results['issues'] = self.results['species_mismatches']
        return self.results

    def _find_gmt_files(self):
        """搜索所有.gmt文件"""
        print("【1. 搜索.gmt文件】\n")

        gmt_files = list(self.project_path.rglob("*.gmt"))

        if not gmt_files:
            print("✓ 未找到.gmt文件")
            return

        print(f"✓ 找到 {len(gmt_files)} 个.gmt文件:\n")

        for gmt_file in gmt_files:
            relative_path = gmt_file.relative_to(self.project_path)
            print(f"  - {relative_path}")

            # 检测物种
            species = self._detect_gmt_species(gmt_file)
            print(f"    物种: {species['detected']} ({species['confidence']} 置信度)")
            print(f"    标识: {species['marker']}")

            self.results['gmt_files'].append({
                'path': str(gmt_file),
                'relative_path': str(relative_path),
                'species': species['detected'],
                'confidence': species['confidence'],
                'marker': species['marker']
            })

        print()

    def _detect_gmt_species(self, gmt_file: Path) -> Dict:
        """
        检测.gmt文件物种

        Returns:
            {'detected': 'human/mouse/rat/unknown', 'confidence': 'high/medium/low', 'marker': '标识符'}
        """
        filename = gmt_file.name.lower()

        # 检查文件名中的物种标识
        for species, markers in self.SPECIES_MARKERS.items():
            for marker in markers:
                if marker.lower() in filename:
                    return {
                        'detected': species,
                        'confidence': 'high',
                        'marker': marker
                    }

        # 检查文件内容（读取前几行）
        try:
            from utils import safe_read_file
            _text, _ = safe_read_file(gmt_file)
            first_line = _text.split('\n', 1)[0] if _text else ''

            # 检查基因名格式（人类基因名通常是大写字母）
            genes = first_line.split('\t')
            if len(genes) > 2:
                # 检查基因名格式
                gene_symbols = genes[2:10]  # 检查前几个基因
                uppercase_count = sum(1 for g in gene_symbols if g.isupper() and g.isalpha())

                if uppercase_count / len(gene_symbols) > 0.8:
                    return {
                        'detected': 'human',
                        'confidence': 'medium',
                        'marker': '基因名格式(大写)'
                    }

        except Exception as e:
            pass

        return {
            'detected': 'unknown',
            'confidence': 'low',
            'marker': '无'
        }

    def _scan_code_references(self):
        """扫描代码中的.gmt文件引用"""
        print("【2. 检查代码中的.gmt引用】\n")

        # 优先在代码目录搜索（利用基类方法）
        code_dir = self.find_code_directory()
        search_root = code_dir if code_dir else self.project_path

        code_files = []
        for ext in ['*.R', '*.py', '*.m', '*.sh']:
            code_files.extend(search_root.rglob(ext))

        if not code_files:
            print("✓ 未找到代码文件")
            return

        print(f"✓ 检查 {len(code_files)} 个代码文件:\n")

        gmt_pattern = re.compile(r'["\']([^"\']*\.gmt)["\']')

        for code_file in code_files:
            try:
                from utils import safe_read_file
                content = safe_read_file(code_file)[0]
                matches = gmt_pattern.findall(content)

                if matches:
                    relative_path = self._relative_path(code_file)
                    print(f"  - {relative_path}")

                    for gmt_ref in matches:
                        print(f"    引用: {gmt_ref}")

                        # 检测引用的.gmt文件物种
                        gmt_name = Path(gmt_ref).name.lower()

                        for species, markers in self.SPECIES_MARKERS.items():
                            for marker in markers:
                                if marker.lower() in gmt_name:
                                    if species != 'human':
                                        # 非人类基因集，可能是问题
                                        self.results['code_references'].append({
                                            'file': str(relative_path),
                                            'reference': gmt_ref,
                                            'species': species
                                        })
                                        print(f"      ⚠️ 检测到{species}基因集")

            except Exception as e:
                pass

        print()

    def _verify_species_match(self):
        """验证物种匹配"""
        print("【3. 物种匹配验证】\n")

        if self.data_species == 'unknown':
            print("⚠️ 分析数据物种未知，请手动确认")
            print("   提示: GSE* 通常是人类, GSE*M 可能是小鼠\n")
            return

        print(f"分析数据物种: {self.data_species}")
        print()

        # 检查.gmt文件物种
        for gmt_info in self.results['gmt_files']:
            gmt_species = gmt_info['species']

            if gmt_species != 'unknown' and gmt_species != self.data_species:
                mismatch = {
                    'type': 'gmt_file',
                    'file': gmt_info['relative_path'],
                    'gmt_species': gmt_species,
                    'data_species': self.data_species,
                    'severity': 'FATAL'
                }
                self.results['species_mismatches'].append(mismatch)

                print(f"🔴 FATAL: 物种不匹配")
                print(f"  文件: {gmt_info['relative_path']}")
                print(f"  基因集物种: {gmt_species}")
                print(f"  分析数据物种: {self.data_species}")
                print()

        # 检查代码引用
        for ref_info in self.results['code_references']:
            ref_species = ref_info['species']

            if ref_species != self.data_species:
                mismatch = {
                    'type': 'code_reference',
                    'file': ref_info['file'],
                    'reference': ref_info['reference'],
                    'gmt_species': ref_species,
                    'data_species': self.data_species,
                    'severity': 'FATAL'
                }
                self.results['species_mismatches'].append(mismatch)

                print(f"🔴 FATAL: 代码引用物种不匹配")
                print(f"  文件: {ref_info['file']}")
                print(f"  引用: {ref_info['reference']}")
                print(f"  基因集物种: {ref_species}")
                print(f"  分析数据物种: {self.data_species}")
                print()

        if not self.results['species_mismatches']:
            print("✓ 所有基因集物种与分析数据匹配\n")

    def _generate_recommendations(self):
        """生成处理建议"""
        print("【4. 处理建议】\n")

        if not self.results['species_mismatches']:
            print("✓ 无物种不匹配问题，可以继续后续检查\n")
            return

        print(f"发现 {len(self.results['species_mismatches'])} 个物种不匹配问题:\n")

        for i, mismatch in enumerate(self.results['species_mismatches'], 1):
            print(f"{i}. {mismatch['type']} - {mismatch.get('file', mismatch.get('reference', ''))}")
            print(f"   严重性: 🔴 FATAL")
            print(f"   建议: 替换为{self.data_species}基因集")
            print()

        self.results['recommendations'].append({
            'severity': 'FATAL',
            'message': f'发现{len(self.results["species_mismatches"])}个物种不匹配问题',
            'action': '建议替换基因集或重新分析'
        })

    def generate_report(self, output_path: str = None):
        """生成检查报告"""
        if output_path is None:
            output_path = self.project_path / "species_check_report.txt"

        output_path = Path(output_path)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("Step 0: 物种和质量预检 - 基因集物种验证报告\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"项目路径: {self.project_path}\n")
            f.write(f"分析数据物种: {self.data_species}\n\n")

            f.write("=" * 80 + "\n")
            f.write("检查结果\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"找到 .gmt 文件: {len(self.results['gmt_files'])} 个\n")
            f.write(f"代码引用: {len(self.results['code_references'])} 处\n")
            f.write(f"物种不匹配: {len(self.results['species_mismatches'])} 个\n\n")

            if self.results['species_mismatches']:
                f.write("【物种不匹配详情】\n\n")
                for i, mismatch in enumerate(self.results['species_mismatches'], 1):
                    f.write(f"{i}. {mismatch['type']}\n")
                    f.write(f"   文件/引用: {mismatch.get('file', mismatch.get('reference', ''))}\n")
                    f.write(f"   基因集物种: {mismatch['gmt_species']}\n")
                    f.write(f"   分析数据物种: {mismatch['data_species']}\n")
                    f.write(f"   严重性: {mismatch['severity']}\n\n")

            f.write("=" * 80 + "\n")
            f.write("处理建议\n")
            f.write("=" * 80 + "\n\n")

            for rec in self.results['recommendations']:
                f.write(f"- {rec['severity']}: {rec['message']}\n")
                f.write(f"  建议: {rec['action']}\n\n")

        print(f"✓ 报告已保存到: {output_path}")


def main():
    """命令行入口"""
    import sys

    if len(sys.argv) < 2:
        print("用法:")
        print("  python check_species_match.py <项目路径> [数据物种]")
        print("")
        print("参数:")
        print("  项目路径: 项目根目录")
        print("  数据物种: human | mouse | rat | unknown (默认: auto)")
        print("")
        print("示例:")
        print("  python check_species_match.py /path/to/project human")
        print("  python check_species_match.py /path/to/project mouse")
        sys.exit(1)

    project_path = sys.argv[1]
    data_species = sys.argv[2] if len(sys.argv) > 2 else 'unknown'

    checker = SpeciesChecker(project_path, data_species)
    checker.check_all()
    checker.generate_report()


if __name__ == "__main__":
    main()
