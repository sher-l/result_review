#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
代码文件存在性检查器 (P1)

检查项目是否提供了分析代码/脚本文件。
同时检测每个模块中图件与数据表的比例（有图无CSV警告）。

作者: 审核框架 v6.5
"""

from pathlib import Path
from typing import Dict, List
from itertools import islice
from base_project_checker import BaseProjectChecker


class CodeExistenceChecker(BaseProjectChecker):
    """分析代码存在性 + 有图无数据表检测"""

    _CODE_EXTS = {'.r', '.rmd', '.py', '.ipynb', '.qmd', '.sh', '.rscript'}
    _DATA_EXTS = {'.csv', '.tsv', '.txt', '.xlsx', '.xls', '.rds', '.rdata'}
    _IMG_EXTS = {'.png', '.jpg', '.jpeg', '.pdf', '.tif', '.tiff', '.svg', '.bmp'}

    def __init__(self, project_path: str, layer0_data: dict = None):
        super().__init__(project_path, layer0_data=layer0_data)

    def check_all(self) -> Dict:
        """执行全部检查"""
        self._check_code_files()
        # 有图无CSV检查已移至 check_figure_data_match 统一负责，避免重复报告

        return {
            'issues': self.issues,
            'warnings': self.warnings,
            'total_checks': 1,
            'failed_checks': len(self.issues),
        }

    def _check_code_files(self):
        """检查是否存在分析脚本/代码"""
        code_dirs = ['CODE', 'code', 'scripts', 'Scripts', 'src']
        found_code = []

        # 检查专用代码目录
        for base in [self.project_path / '结果文件', self.project_path]:
            if not base.is_dir():
                continue
            for cd in code_dirs:
                code_path = base / cd
                if code_path.is_dir():
                    files = list(islice(code_path.rglob('*'), 200))
                    code_files = [f for f in files if f.is_file() and f.suffix.lower() in self._CODE_EXTS]
                    found_code.extend(code_files)

        # 扫描各模块中的代码文件
        modules = self.find_modules()
        for mod in modules:
            for f in islice(mod.rglob('*'), 500):
                if f.is_file() and f.suffix.lower() in self._CODE_EXTS:
                    found_code.append(f)

        if not found_code:
            self.warnings.append({
                'severity': 'INFO',
                'category': '代码缺失',
                'message': '项目中未发现分析代码文件（.R/.py/.Rmd/.ipynb等），无法评估可复现性',
                'evidence': {'searched_dirs': code_dirs},
            })
        else:
            by_ext = {}
            for f in found_code:
                ext = f.suffix.lower()
                by_ext[ext] = by_ext.get(ext, 0) + 1

    # 可视化模块白名单：这些模块天然只有图件，不需要 CSV
    _VIS_ONLY_KEYWORDS = ('qc', 'umap', 'pca', 'tsne', 'subtypes', 'subtype', 'dimplot')

    def _check_image_only_modules(self):
        """检测有图件但无数据表的模块"""
        modules = self.find_modules()
        for mod in modules:
            mod_lower = mod.name.lower()
            if any(kw in mod_lower for kw in self._VIS_ONLY_KEYWORDS):
                continue  # 可视化模块跳过
            all_files = [f for f in islice(mod.rglob('*'), 500) if f.is_file()]
            img_count = sum(1 for f in all_files if f.suffix.lower() in self._IMG_EXTS)
            data_count = sum(1 for f in all_files
                            if f.suffix.lower() in self._DATA_EXTS
                            and f.stat().st_size > 100)
            # 排除 .rds 和 .rdata 因为是二进制不可审
            csv_count = sum(1 for f in all_files
                           if f.suffix.lower() in {'.csv', '.tsv'}
                           and f.stat().st_size > 100)

            if img_count >= 3 and csv_count == 0:
                # 有多张图但没有CSV — 可能缺少数据表
                mod_name = mod.name
                try:
                    mod_rel = str(mod.relative_to(self.project_path))
                except ValueError:
                    mod_rel = mod.name
                self.issues.append({
                    'severity': 'WARNING',
                    'category': '有图无数据表',
                    'message': (
                        f'模块 {mod_name} 含 {img_count} 张图件但 0 个CSV/TSV数据表，'
                        f'无法独立验证统计结果'
                    ),
                    'file': mod_rel,
                    'evidence': {
                        'module': mod_name,
                        'image_count': img_count,
                        'csv_count': csv_count,
                        'data_count': data_count,
                    },
                })


if __name__ == '__main__':
    import sys, json
    if len(sys.argv) > 1:
        checker = CodeExistenceChecker(sys.argv[1])
        print(json.dumps(checker.check_all(), indent=2, ensure_ascii=False, default=str))
