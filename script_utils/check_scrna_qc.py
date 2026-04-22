#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scRNA QC 单调性检查器 (P1级)

检测报告中的 QC 前后细胞数逻辑错误：
- QC后细胞数 > QC前细胞数 → CRITICAL（违反单调递减原则）
- 多样本合并后数量 > 各样本之和 → CRITICAL（数据来源不一致）

基于 26YYS083F 教训：报告声称"初始22704个细胞→过滤后保留52747个细胞"
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


from base_project_checker import BaseProjectChecker


class ScRNAQCChecker(BaseProjectChecker):
    """scRNA QC 单调性检查器"""

    # 匹配"数字+细胞"模式的正则
    CELL_COUNT_PATTERN = re.compile(
        r'(\d[\d,\.]*)\s*(?:个|cells?|nuclei|核)',
        re.IGNORECASE
    )

    # QC阶段关键词（按流程顺序）
    STAGE_PATTERNS = [
        ('initial', re.compile(r'初始|raw|原始|initial|载入|加载|load', re.IGNORECASE)),
        ('merged', re.compile(r'合并后|merge[d]?|整合后|combined', re.IGNORECASE)),
        ('filtered', re.compile(r'过滤后|filter|QC后|筛选后|保留|retain|质控后', re.IGNORECASE)),
        ('final', re.compile(r'最终|final|用于.*分析|downstream', re.IGNORECASE)),
    ]

    def __init__(self, project_path: str, layer0_data: dict = None):
        super().__init__(project_path, layer0_data=layer0_data)

    def check_all(self) -> Dict:
        """执行 scRNA QC 单调性检查"""
        report_text = self.load_report_text()
        if not report_text:
            # 降级模式：无报告时扫描 R 脚本中的 QC 过滤参数
            code_qc = self._scan_code_qc_params()
            if code_qc:
                self.warnings.append({
                    'severity': 'INFO',
                    'category': 'scRNA QC参数摘要（无报告降级模式）',
                    'message': '未找到报告文本，仅列出代码中的 QC 过滤参数供人工核对',
                    'evidence': code_qc,
                })
            return {
                'issues': self.issues,
                'cell_counts': {},
                'skipped': not bool(code_qc),
                'degraded': True,
                'reason': '未找到报告文本' + ('，已从代码提取QC参数' if code_qc else ''),
            }

        # 提取带上下文的细胞数
        counts = self._extract_cell_counts_with_context(report_text)
        if not counts:
            return {
                'issues': [],
                'cell_counts': {},
                'skipped': True,
                'reason': '报告中未找到细胞数描述'
            }

        # 单调性检查
        self._check_monotonicity(counts)

        # 检查同一句中的前后矛盾
        self._check_inline_contradictions(report_text)

        # 检查下游模块覆盖缺口
        self._check_downstream_coverage(report_text)

        return {
            'issues': self.issues,
            'cell_counts': {s: n for s, n, _ in counts},
            'fatal': False,
            'skipped': False
        }

    def _extract_cell_counts_with_context(self, text: str) -> List[Tuple[str, int, str]]:
        """提取细胞数及其所属QC阶段

        Returns: [(stage, count, context_line), ...]
        """
        results = []
        lines = text.split('\n')

        for line in lines:
            # 跳过不含细胞相关内容的行
            if not re.search(r'细胞|cell|nuclei|核', line, re.IGNORECASE):
                continue

            # 找到该行的细胞数
            for match in self.CELL_COUNT_PATTERN.finditer(line):
                num_str = match.group(1).replace(',', '').replace('.', '')
                try:
                    count = int(num_str)
                except ValueError:
                    continue
                if count < 10:  # 忽略太小的数字
                    continue

                # 判断阶段
                stage = self._classify_stage(line)
                results.append((stage, count, line.strip()))

        return results

    def _classify_stage(self, line: str) -> str:
        """根据上下文判断QC阶段"""
        for stage_name, pattern in self.STAGE_PATTERNS:
            if pattern.search(line):
                return stage_name
        return 'unknown'

    def _check_monotonicity(self, counts: List[Tuple[str, int, str]]):
        """检查QC流程的单调递减性"""
        stage_order = {'initial': 0, 'merged': 1, 'filtered': 2, 'final': 3}

        # 按阶段分组
        staged = {}
        for stage, count, ctx in counts:
            if stage in stage_order:
                if stage not in staged:
                    staged[stage] = []
                staged[stage].append((count, ctx))

        # 检查相邻阶段
        ordered_stages = sorted(staged.keys(), key=lambda s: stage_order[s])
        for i in range(len(ordered_stages) - 1):
            s1 = ordered_stages[i]
            s2 = ordered_stages[i + 1]

            # 跳过 initial → merged（合并可能增加）
            if s1 == 'initial' and s2 == 'merged':
                continue

            max_s1 = max(c for c, _ in staged[s1])
            min_s2 = min(c for c, _ in staged[s2])

            if min_s2 > max_s1:
                self.issues.append({
                    'severity': 'CRITICAL',
                    'type': 'qc_monotonicity_violation',
                    'message': f'QC单调性违反: {s1}阶段({max_s1}) → {s2}阶段({min_s2})，后者反而更大',
                    'context': {
                        'stage_before': s1,
                        'count_before': max_s1,
                        'stage_after': s2,
                        'count_after': min_s2,
                    }
                })

    def _check_inline_contradictions(self, text: str):
        """检查同一句中的数字矛盾（如"初始X个细胞→过滤后保留Y个细胞"且Y>X）"""
        # 匹配 "初始/原始 N 细胞 ... 过滤/保留 M 细胞" 模式
        pattern = re.compile(
            r'(?:初始|原始|raw)\s*(\d[\d,]*)\s*(?:个|cells?)'
            r'.*?'
            r'(?:过滤后|筛选后|保留|retain|QC后)\s*(\d[\d,]*)\s*(?:个|cells?)',
            re.IGNORECASE | re.DOTALL
        )

        for match in pattern.finditer(text):
            n_before = int(match.group(1).replace(',', ''))
            n_after = int(match.group(2).replace(',', ''))

            if n_after > n_before:
                self.issues.append({
                    'severity': 'CRITICAL',
                    'type': 'qc_count_contradiction',
                    'message': f'同段落矛盾: 初始{n_before}个细胞 → 过滤后{n_after}个细胞（增加了{n_after - n_before}）',
                    'context': {
                        'before': n_before,
                        'after': n_after,
                        'text': match.group(0)[:200]
                    }
                })

    def _check_downstream_coverage(self, report_text: str):
        """检查下游模块（scTenifoldKnk/CellChat）覆盖的细胞类型 vs 注释阶段的完整细胞类型列表"""
        # 1. 从注释模块（11_sc等）提取注释的细胞类型
        annotated_types = self._extract_annotated_cell_types(report_text)
        if not annotated_types:
            return

        # 2. 从下游模块目录中提取分析过的细胞类型
        downstream_modules = self._find_downstream_modules()
        for mod_name, mod_dir in downstream_modules:
            covered_types = self._extract_covered_cell_types(mod_dir)
            if not covered_types:
                continue
            # 比对
            missing = annotated_types - covered_types
            coverage_ratio = len(covered_types) / len(annotated_types) if annotated_types else 1.0
            if coverage_ratio < 0.5 and len(missing) >= 2:
                self.issues.append({
                    'severity': 'WARNING',
                    'type': 'downstream_coverage_gap',
                    'message': (
                        f'{mod_name} 仅覆盖 {len(covered_types)}/{len(annotated_types)} 种注释细胞类型 '
                        f'({coverage_ratio:.0%})，缺失: {", ".join(sorted(missing)[:5])}'
                    ),
                    'context': {
                        'module': mod_name,
                        'annotated': sorted(annotated_types),
                        'covered': sorted(covered_types),
                        'missing': sorted(missing),
                        'coverage_ratio': coverage_ratio,
                    }
                })

    def _extract_annotated_cell_types(self, report_text: str) -> set:
        """从报告中提取注释的细胞类型（支持中英文）"""
        cell_types = set()
        # 英文细胞类型 → 标准名映射
        known_types = [
            'Macrophage', 'Neutrophil', 'NK', 'T cell', 'B cell', 'Endothelial',
            'Granulosa', 'Stellate', 'Hepatocyte', 'Cholangiocyte', 'Lymphocyte',
            'Fibroblast', 'Epithelial', 'Monocyte', 'Dendritic', 'Plasma',
            'Smooth muscle', 'Pericyte', 'Kupffer', 'Mast',
        ]
        # 中文→英文映射，使中文报告也能被识别
        _CN_TO_EN = {
            '巨噬细胞': 'Macrophage', '中性粒细胞': 'Neutrophil',
            'NK细胞': 'NK', 'T细胞': 'T cell', 'B细胞': 'B cell',
            '内皮细胞': 'Endothelial', '颗粒细胞': 'Granulosa',
            '星状细胞': 'Stellate', '肝细胞': 'Hepatocyte',
            '胆管细胞': 'Cholangiocyte', '淋巴细胞': 'Lymphocyte',
            '成纤维细胞': 'Fibroblast', '上皮细胞': 'Epithelial',
            '单核细胞': 'Monocyte', '树突状细胞': 'Dendritic',
            '浆细胞': 'Plasma', '平滑肌细胞': 'Smooth muscle',
            '周细胞': 'Pericyte', '库普弗细胞': 'Kupffer',
            '肥大细胞': 'Mast', '自然杀伤细胞': 'NK',
        }
        # 找注释相关段落
        for line in report_text.split('\n'):
            if re.search(r'注释|annotat|细胞[类型簇]|cluster|UMAP', line, re.IGNORECASE):
                for ct in known_types:
                    if ct.lower() in line.lower():
                        cell_types.add(ct)
                for cn, en in _CN_TO_EN.items():
                    if cn in line:
                        cell_types.add(en)
        return cell_types

    def _find_downstream_modules(self):
        """查找下游分析模块（scTenifoldKnk, CellChat等）"""
        result = []
        downstream_patterns = [
            (re.compile(r'tenifold|knk|knockout', re.IGNORECASE), 'scTenifoldKnk'),
            (re.compile(r'cellchat|通讯|communication', re.IGNORECASE), 'CellChat'),
        ]
        for base in [self.project_path / '结果文件', self.project_path]:
            if not base.is_dir():
                continue
            for d in base.iterdir():
                if not d.is_dir():
                    continue
                for pat, name in downstream_patterns:
                    if pat.search(d.name):
                        result.append((name, d))
        return result

    def _extract_covered_cell_types(self, mod_dir: Path) -> set:
        """从模块目录的文件名和子目录名中提取覆盖的细胞类型"""
        covered = set()
        known_types = [
            'Macrophage', 'Neutrophil', 'NK', 'T_cell', 'Tcell', 'B_cell', 'Bcell',
            'Endothelial', 'Granulosa', 'Stellate', 'Hepatocyte', 'Cholangiocyte',
            'Lymphocyte', 'Fibroblast', 'Epithelial', 'Monocyte', 'Dendritic',
            'NK_cell', 'NKcell', 'Plasma', 'Smooth_muscle', 'Pericyte', 'Kupffer',
        ]
        from itertools import islice
        for f in islice(mod_dir.rglob('*'), 500):
            name = f.stem.lower().replace(' ', '_')
            for ct in known_types:
                if ct.lower().replace(' ', '_') in name:
                    # 标准化
                    normalized = ct.replace('_cell', '').replace('cell', '').replace('_', ' ').strip()
                    if normalized == 'NK':
                        covered.add('NK')
                    elif normalized.startswith('T'):
                        covered.add('T cell')
                    elif normalized.startswith('B'):
                        covered.add('B cell')
                    else:
                        covered.add(normalized.title())
        return covered

    def _scan_code_qc_params(self) -> list:
        """从 R 脚本中提取 scRNA QC 过滤参数（降级模式使用）"""
        qc_params = []
        # 常见 QC 过滤模式
        qc_patterns = [
            (re.compile(r'nFeature_RNA\s*[<>]=?\s*(\d+)'), 'nFeature_RNA'),
            (re.compile(r'nCount_RNA\s*[<>]=?\s*(\d+)'), 'nCount_RNA'),
            (re.compile(r'percent\.mt\s*[<>]=?\s*([\d.]+)'), 'percent.mt'),
            (re.compile(r'percent\.rb\s*[<>]=?\s*([\d.]+)'), 'percent.rb'),
            (re.compile(r'subset\(.*?nFeature.*?[<>]\s*(\d+)', re.DOTALL), 'subset_nFeature'),
        ]
        code_dir = self.find_code_directory()
        search_roots = [code_dir] if code_dir else [self.project_path]
        for root in search_roots:
            if not root or not root.is_dir():
                continue
            for script in root.rglob('*.R'):
                if 'result_review_framework' in str(script):
                    continue
                try:
                    text = script.read_text(encoding='utf-8', errors='ignore')
                except Exception:
                    continue
                for pat, label in qc_patterns:
                    for m in pat.finditer(text):
                        qc_params.append({
                            'param': label,
                            'value': m.group(1),
                            'file': self._relative_path(script),
                        })
        return qc_params
