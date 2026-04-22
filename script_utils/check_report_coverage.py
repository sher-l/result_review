#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
报告覆盖矩阵检查器 (P1级)

检测报告与实际结果之间的覆盖缺口：
1. GSE数据集：报告提及 vs 结果文件引用
2. 分析模块：实际目录 vs 报告描述
3. 核心基因：报告核心基因 vs 上游分析结果
4. 阴性结果检测：有结果文件但报告未提及

基于框架经验：选择性隐藏阴性结果是常见的报告质量问题
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


from base_project_checker import BaseProjectChecker


class ReportCoverageChecker(BaseProjectChecker):
    """报告覆盖矩阵检查器"""

    # 常见分析模块目录名到可读名的映射
    MODULE_KEYWORDS = {
        'DEG': ['差异表达', 'DEG', '差异分析', 'differential expression'],
        'Enrich': ['富集分析', '通路富集', 'GO', 'KEGG', 'enrichment'],
        'GSEA': ['GSEA', '基因集富集'],
        'GSVA': ['GSVA', '基因集变异分析'],
        'WGCNA': ['WGCNA', '加权基因共表达'],
        'Machine': ['机器学习', 'LASSO', '随机森林', 'SVM', 'XGBoost'],
        'Nomogram': ['列线图', 'Nomogram', '校准曲线', 'DCA'],
        'Cox': ['Cox', '生存分析', 'Kaplan', 'KM'],
        'PPI': ['PPI', '蛋白互作', '蛋白质互作', 'STRING'],
        'scRNA': ['单细胞', 'scRNA', 'Seurat', 'UMAP'],
        'CellChat': ['细胞通讯', 'CellChat', 'cellchat'],
        'Pseudotime': ['拟时序', '轨迹分析', 'Monocle', 'pseudotime'],
        'Spatial': ['空间转录', '空转', 'spatial'],
        'Immune': ['免疫浸润', 'CIBERSORT', 'ssGSEA', 'ESTIMATE', 'immune'],
        'Drug': ['药物敏感', 'IC50', '药物预测'],
        'MR': ['孟德尔随机化', 'Mendelian', 'MR分析'],
        'Network': ['网络药理学', '分子对接', 'docking', 'Network'],
        'miRNA': ['miRNA', 'ceRNA', 'lncRNA.*mRNA'],
        'hdWGCNA': ['hdWGCNA'],
        'HPA': ['HPA', '蛋白表达验证'],
        'Combat': ['Combat', '批次校正', 'batch'],
        'Target': ['Target', '药物靶点', 'targetprediction'],
        'Toxicity': ['Toxicity', '毒理', '毒性', 'toxicology'],
        'Correlation': ['Correlation', '相关性分析', 'cor_'],
        'SHAP': ['SHAP', 'Shapley'],
        'Annotation': ['Annotation', '细胞注释', 'cell annotation'],
        'Quantify': ['Quantify', 'AUCell', 'scQuantify', '评分量化'],
        'Expression': ['Expression', '表达验证', 'ROC', 'scExpression'],
        'MolecularDynamics': ['MolecularDynamic', 'MD模拟', '分子动力学'],
    }

    # GSE模式
    GSE_PATTERN = re.compile(r'GSE\d{3,}', re.IGNORECASE)

    def __init__(self, project_path: str, layer0_data: dict = None):
        super().__init__(project_path, layer0_data=layer0_data)

    def check_all(self) -> Dict:
        """执行覆盖矩阵检查"""
        report_text = self.load_report_text()

        # 模块覆盖
        module_gaps = self._check_module_coverage(report_text)

        # GSE覆盖
        gse_gaps = self._check_gse_coverage(report_text)

        return {
            'issues': self.issues,
            'module_gaps': module_gaps,
            'gse_gaps': gse_gaps,
            'fatal': False,
            'skipped': not bool(report_text),
        }

    def _check_module_coverage(self, report_text: Optional[str]) -> List[Dict]:
        """检查分析模块是否在报告中被提及"""
        gaps = []
        try:
            from utils import find_result_root
            result_dir = find_result_root(self.project_path)
        except ImportError:
            result_dir = self.project_path / '结果文件'
        if not result_dir or not result_dir.is_dir():
            return gaps

        existing_modules = []
        for d in sorted(result_dir.iterdir()):
            if not d.is_dir():
                continue
            # 检测属于哪个模块分类
            dir_name = d.name.lower()
            for module_key, keywords in self.MODULE_KEYWORDS.items():
                if any(kw.lower() in dir_name for kw in keywords):
                    existing_modules.append((d.name, module_key, keywords))
                    break

        if not report_text:
            # 降级模式：无报告时列出已识别模块供人工对照
            if existing_modules:
                self.warnings.append({
                    'severity': 'INFO',
                    'category': '模块清单（无报告降级模式）',
                    'message': f'未找到报告文本，仅列出已识别的 {len(existing_modules)} 个模块类型供人工对照',
                    'evidence': [{'dir': name, 'type': key} for name, key, _ in existing_modules],
                })
            return gaps

        for dir_name, module_key, keywords in existing_modules:
            # 检查报告中是否提及该模块
            mentioned = False
            for kw in keywords:
                if re.search(re.escape(kw) if '.' not in kw else kw, report_text, re.IGNORECASE):
                    mentioned = True
                    break

            if not mentioned:
                # 检查目录是否有实质内容
                module_path = result_dir / dir_name
                has_content = any(module_path.rglob('*.csv')) or \
                              any(module_path.rglob('*.pdf')) or \
                              any(module_path.rglob('*.png'))
                if has_content:
                    gaps.append({
                        'module': dir_name,
                        'category': module_key,
                        'status': 'unreported'
                    })
                    self.issues.append({
                        'severity': 'WARNING',
                        'type': 'module_unreported',
                        'message': f'模块 {dir_name} 有分析结果但报告中未检测到相关描述（可能隐藏阴性结果）'
                    })

        return gaps

    def _check_gse_coverage(self, report_text: Optional[str]) -> Dict:
        """检查GSE数据集覆盖"""
        gaps = {'in_files_not_report': [], 'in_report_not_files': []}

        # 从文件名/路径提取GSE（限制扫描范围到重点目录）
        gse_in_files: Set[str] = set()
        FOCUS_DIRS = ['结果文件', 'CODE', 'scripts', '报告']
        MAX_FILES = 2000
        scanned = 0
        for focus in FOCUS_DIRS:
            focus_path = self.project_path / focus
            if not focus_path.exists():
                continue
            for f in focus_path.rglob('*'):
                for match in self.GSE_PATTERN.finditer(f.name):
                    gse_in_files.add(match.group().upper())
                scanned += 1
                if scanned >= MAX_FILES:
                    break
            if scanned >= MAX_FILES:
                break
        # 补充顶层文件
        for f in self.project_path.iterdir():
            for match in self.GSE_PATTERN.finditer(f.name):
                gse_in_files.add(match.group().upper())

        # 从代码内容提取GSE
        code_dir = self.project_path / 'CODE'
        code_dirs = [code_dir] if code_dir.exists() else [self.project_path]
        for cdir in code_dirs:
            for ext in ('*.R', '*.r', '*.py'):
                for code_file in cdir.rglob(ext):
                    try:
                        content = code_file.read_text(encoding='utf-8', errors='ignore')
                        for match in self.GSE_PATTERN.finditer(content):
                            gse_in_files.add(match.group().upper())
                    except Exception:
                        continue

        if not report_text:
            return gaps

        # 从报告提取GSE
        gse_in_report: Set[str] = set()
        for match in self.GSE_PATTERN.finditer(report_text):
            gse_in_report.add(match.group().upper())

        # 比对
        only_files = gse_in_files - gse_in_report
        only_report = gse_in_report - gse_in_files

        for gse in only_files:
            gaps['in_files_not_report'].append(gse)
            self.issues.append({
                'severity': 'WARNING',
                'type': 'gse_unreported',
                'message': f'数据集 {gse} 在结果文件/代码中使用但报告未提及'
            })

        for gse in only_report:
            gaps['in_report_not_files'].append(gse)
            self.issues.append({
                'severity': 'INFO',
                'type': 'gse_report_only',
                'message': f'数据集 {gse} 在报告中提及但未在结果文件中找到'
            })

        return gaps
