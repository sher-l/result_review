#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图件-数据匹配检查器 (P1)

基础版：检查每个模块的图件数量与数据文件数量比例，
识别异常模式（如大量图件但完全没有支撑数据表）。

进阶版（需图像库）：对比图中可读取的数值与CSV数据。

作者: 审核框架 v6.5
"""

import re
from pathlib import Path
from typing import Dict, List
from itertools import islice
from base_project_checker import BaseProjectChecker


class FigureDataMatchChecker(BaseProjectChecker):
    """图件-数据文件匹配检查"""

    _IMG_EXTS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.svg', '.bmp'}
    _PDF_EXT = {'.pdf'}
    _DATA_EXTS = {'.csv', '.tsv'}
    _BINARY_DATA = {'.rds', '.rdata', '.h5', '.h5ad', '.h5seurat'}

    # 通常应该有CSV的模块类型
    _EXPECT_CSV_PATTERNS = {
        'limma|deg|diff': '差异分析应提供CSV结果表',
        'lasso': 'LASSO筛选应提供特征基因CSV',
        'machine|ml|model': '机器学习应提供模型指标CSV',
        'cibersort|immune': '免疫浸润应提供CIBERSORT结果CSV',
        'gsea': 'GSEA应提供富集结果CSV',
        'cellchat|通讯': 'CellChat应提供信号通路CSV',
        'inter|交集': '基因交集应提供基因列表CSV',
        'go|kegg|enrich': '富集分析应提供富集结果CSV',
        'ppi': 'PPI分析应提供网络节点CSV',
        'cox|survival': '生存分析应提供Cox回归结果CSV',
    }

    def __init__(self, project_path: str, layer0_data: dict = None):
        super().__init__(project_path, layer0_data=layer0_data)

    def check_all(self) -> Dict:
        """执行全部检查"""
        modules = self.find_modules()
        if not modules:
            return {
                'issues': [],
                'warnings': [],
                'skipped': True,
                'reason': '未找到编号模块目录',
            }

        for mod in modules:
            self._check_module(mod)

        return {
            'issues': self.issues,
            'warnings': self.warnings,
            'total_checks': len(modules),
            'failed_checks': len(self.issues),
            'modules_scanned': len(modules),
        }

    def _check_module(self, mod_dir: Path):
        """检查单个模块的图件-数据比例"""
        all_files = [f for f in islice(mod_dir.rglob('*'), 500) if f.is_file()]

        img_count = sum(1 for f in all_files if f.suffix.lower() in self._IMG_EXTS)
        pdf_count = sum(1 for f in all_files if f.suffix.lower() in self._PDF_EXT)
        csv_count = sum(1 for f in all_files
                        if f.suffix.lower() in self._DATA_EXTS
                        and f.stat().st_size > 100)
        binary_count = sum(1 for f in all_files if f.suffix.lower() in self._BINARY_DATA)

        total_visual = img_count + pdf_count
        mod_name = mod_dir.name
        try:
            mod_rel = str(mod_dir.relative_to(self.project_path))
        except ValueError:
            mod_rel = mod_name

        # 检查1: 图件多但无CSV（严格版 — 只看 CSV/TSV）
        if total_visual >= 5 and csv_count == 0:
            # 检查这个模块类型是否预期有CSV
            expected_msg = self._module_should_have_csv(mod_name)
            if expected_msg:
                self.issues.append({
                    'severity': 'WARNING',
                    'category': '有图无数据表',
                    'message': f'{mod_name}: {total_visual}张图件但0个CSV — {expected_msg}',
                    'file': mod_rel,
                    'evidence': {
                        'images': img_count, 'pdfs': pdf_count,
                        'csvs': csv_count, 'binary': binary_count,
                    },
                })
            elif binary_count == 0:
                # 完全没有任何数据文件
                self.warnings.append({
                    'severity': 'INFO',
                    'category': '数据文件缺失',
                    'message': f'{mod_name}: {total_visual}张图件，无CSV也无二进制数据文件',
                    'file': mod_rel,
                    'evidence': {
                        'images': img_count, 'pdfs': pdf_count,
                        'csvs': csv_count, 'binary': binary_count,
                    },
                })

        # 检查2: CSV比图件多很多（可能是原始数据目录 — INFO级）
        if csv_count > 20 and total_visual == 0:
            self.warnings.append({
                'severity': 'INFO',
                'category': '无可视化',
                'message': f'{mod_name}: {csv_count}个CSV但无图件（可能是原始数据目录）',
                'file': mod_rel,
            })

    def _module_should_have_csv(self, mod_name: str) -> str:
        """判断该模块类型是否预期应有CSV，返回提示信息或空字符串"""
        for pattern, msg in self._EXPECT_CSV_PATTERNS.items():
            if re.search(pattern, mod_name, re.IGNORECASE):
                return msg
        return ''


if __name__ == '__main__':
    import sys, json
    if len(sys.argv) > 1:
        checker = FigureDataMatchChecker(sys.argv[1])
        print(json.dumps(checker.check_all(), indent=2, ensure_ascii=False, default=str))
