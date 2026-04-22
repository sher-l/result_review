#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
证据完整性与参数完备性检查器（P1级 - CRITICAL）

前移人工批注中高频但此前未被自动脚本显式捕获的风险：
1. 方法段缺少关键参数（如 LASSO lambda 规则）
2. 只有筛选后结果，缺少原始总表 / 中间总表
3. 表达验证、分子对接、分子动力学等模块只交图不交结构化结果
4. 图件疑似损坏或导出异常（基于文件层面做保守检查）
"""

from __future__ import annotations

import re
from itertools import islice
from pathlib import Path
from typing import Dict, List, Optional


from base_project_checker import BaseProjectChecker


class EvidenceCompletenessChecker(BaseProjectChecker):
    """证据完整性与参数完备性检查器"""

    TABULAR_SUFFIXES = {'.csv', '.tsv', '.txt', '.xlsx', '.xls'}
    IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.pdf'}
    MD_RAW_SUFFIXES = {'.xvg', '.csv', '.dat', '.xtc', '.trr', '.edr', '.gro', '.log'}
    DOCKING_STRUCTURED_SUFFIXES = {'.csv', '.tsv', '.txt', '.xlsx', '.xls', '.log', '.pdbqt', '.sdf'}

    FILTERED_NAME_HINTS = ('sel', 'selected', 'filter', 'filtered', 'final')
    RAW_NAME_HINTS = ('raw', 'all', 'total', 'original', 'full', 'complete', 'summary')

    REFERENCE_STOP_MARKERS = ('公司介绍', '服务领域', '联系我们')

    DATABASE_REFERENCE_RULES = {
        'UniProt': ('uniprot', 'universal protein knowledgebase', 'protein knowledgebase'),
        'PubChem': ('pubchem',),
        'CB-DOCK2': ('cb-dock2', 'cavity detection-guided blind docking'),
        'CTD': ('comparative toxicogenomics database', 'ctd'),
        'COREMINE': ('coremine',),
        'TCMSP': ('tcmsp', 'traditional chinese medicine systems pharmacology'),
        'DGIdb': ('dgidb', 'drug-gene interaction database'),
        # Iter5 新增：覆盖更多常见数据库
        'GEO': ('gene expression omnibus', 'geo'),
        'STRING': ('string', 'string-db', 'search tool for the retrieval of interacting genes'),
        'DAVID': ('david', 'database for annotation, visualization'),
        'GeneCards': ('genecards',),
        'OMIM': ('omim', 'online mendelian inheritance in man'),
        'DrugBank': ('drugbank',),
        'PharmGKB': ('pharmgkb', 'pharmacogenomics knowledgebase'),
        'SwissTargetPrediction': ('swisstargetprediction', 'swiss target prediction'),
        'Metascape': ('metascape',),
        'CMap': ('connectivity map', 'cmap'),
        'STITCH': ('stitch',),
        'DisGeNET': ('disgenet',),
        'TTD': ('therapeutic target database', 'ttd'),
        'BindingDB': ('bindingdb',),
    }

    def __init__(self, project_path: str, layer0_data: dict = None):
        super().__init__(project_path, layer0_data=layer0_data)

    def check_all(self) -> Dict:
        """执行所有检查。"""
        report_text = self.load_report_text() or ''

        self._check_lasso_parameter_completeness(report_text)
        self._check_reference_consistency(report_text)
        self._check_expression_module()
        self._check_filtered_only_tables()
        self._check_docking_module()
        self._check_md_module()
        self._check_report_mentions_missing_modules(report_text)
        self._check_image_only_modules()
        self._check_suspicious_binary_exports()

        fatal = any(issue.get('severity') == 'FATAL' for issue in self.issues)

        return {
            'total_checks': 8,
            'failed_checks': len(self.issues),
            'issues': self.issues,
            'warnings': self.warnings,
            'fatal': fatal,
        }

    def _check_lasso_parameter_completeness(self, report_text: str):
        if not report_text:
            self.warnings.append({
                'severity': 'WARNING',
                'category': '报告文本缺失',
                'message': '未找到可读取的报告文本，跳过方法参数完整性检查。'
            })
            return

        normalized = report_text.lower()
        mentions_lasso = any(keyword in normalized for keyword in ('lasso', 'glmnet'))
        mentions_lambda_rule = any(keyword in normalized for keyword in ('lambda.min', 'lambda.1se', '1se', 'min'))

        if mentions_lasso and not mentions_lambda_rule:
            self.issues.append({
                'severity': 'WARNING',
                'category': '方法参数不完整',
                'file': self._get_report_reference(),
                'message': '报告提到 LASSO / glmnet，但未显式写明 lambda 选择规则（如 lambda.min 或 lambda.1se）。',
                'suggestion': '在方法段补写模型选择规则及对应数值，避免人工批注重复指出参数不完整。'
            })

    # 单细胞上下文感知：如果表达模块含卡方/chi-square等单细胞统计表，认可为有效证据
    _SC_STAT_TOKENS = ('chisq', 'chi_sq', 'chiseq', 'chi_square', 'fisher', 'kruskal')

    def _check_expression_module(self):
        module_dir = self._find_module_dir(('expression', 'roc'))
        if not module_dir:
            return

        # 单细胞表达可视化模块（scExpression、sc_expression）不需要 AUC/差异统计表
        lower_name = module_dir.name.lower()
        if 'sc' in lower_name and 'expression' in lower_name:
            return

        files = list(module_dir.rglob('*'))
        tabular_files = [f for f in files if f.is_file() and f.suffix.lower() in self.TABULAR_SUFFIXES]
        image_files = [f for f in files if f.is_file() and f.suffix.lower() in self.IMAGE_SUFFIXES]

        has_auc_table = any('auc' in f.name.lower() for f in tabular_files)
        has_stat_table = any(any(token in f.name.lower() for token in ('wilcox', 'wilcoxon', 'stat', 'pvalue', 'p_value')) for f in tabular_files)
        # 单细胞项目中卡方检验等也是有效的统计表
        has_sc_stat = any(any(tok in f.name.lower() for tok in self._SC_STAT_TOKENS) for f in tabular_files)

        if has_sc_stat:
            # 存在单细胞统计检验结果（如卡方检验），不要求 AUC/Wilcoxon
            return

        if image_files and (not tabular_files or not has_auc_table or not has_stat_table):
            self.issues.append({
                'severity': 'CRITICAL',
                'category': '表达验证证据不足',
                'file': self._relative_path(module_dir),
                'message': '表达验证模块存在图件，但缺少可识别的 AUC 汇总表和 / 或差异统计表。',
                'suggestion': '补交表达量统计表、Wilcoxon 等差异检验结果表和 AUC 汇总表。',
                'evidence': {
                    'tabular_count': len(tabular_files),
                    'image_count': len(image_files),
                    'has_auc_table': has_auc_table,
                    'has_stat_table': has_stat_table,
                }
            })

    def _check_reference_consistency(self, report_text: str):
        if not report_text:
            return

        body_text, references = self._split_body_and_references(report_text)
        if not references:
            self.warnings.append({
                'severity': 'WARNING',
                'category': '参考文献区缺失',
                'message': '未能从报告文本中解析出参考文献区，跳过编号一致性检查。'
            })
            return

        for database_name, keywords in self.DATABASE_REFERENCE_RULES.items():
            citations = self._extract_database_citations(body_text, database_name)
            if citations:
                for citation in citations:
                    ref_index = citation['ref_index']
                    if ref_index < 1 or ref_index > len(references):
                        self.issues.append({
                            'severity': 'CRITICAL',
                            'category': '参考文献编号越界',
                            'file': self._get_report_reference(),
                            'message': f'正文将 {database_name} 引用为 [{ref_index}]，但参考文献区不存在该编号。',
                            'suggestion': '核对正文编号与参考文献区条目数量是否一致。',
                            'evidence': citation,
                        })
                        continue

                    ref_text = references[ref_index - 1]
                    if not self._reference_matches_keywords(ref_text, keywords):
                        candidate_indexes = self._find_matching_reference_indexes(references, keywords)
                        evidence = {
                            'database': database_name,
                            'quoted_ref_index': ref_index,
                            'quoted_ref_text': ref_text[:220],
                            'context': citation['context'][:220],
                        }
                        if candidate_indexes:
                            evidence['candidate_indexes'] = candidate_indexes
                        self.issues.append({
                            'severity': 'CRITICAL',
                            'category': '参考文献错配',
                            'file': self._get_report_reference(),
                            'message': f'正文将 {database_name} 引用为 [{ref_index}]，但该编号对应文献与 {database_name} 不匹配。',
                            'suggestion': '核对正文数据库引用编号与参考文献顺序，避免串号。',
                            'evidence': evidence,
                        })
            elif self._database_mentioned_without_citation(body_text, database_name):
                candidate_indexes = self._find_matching_reference_indexes(references, keywords)
                evidence = {'database': database_name}
                if candidate_indexes:
                    evidence['candidate_indexes'] = candidate_indexes
                self.issues.append({
                    'severity': 'MAJOR',
                    'category': '参考文献缺失',
                    'file': self._get_report_reference(),
                    'message': f'正文提到了 {database_name}，但未检测到其后的参考文献编号。',
                    'suggestion': '为该数据库补充参考文献编号，并确保参考文献区存在对应条目。',
                    'evidence': evidence,
                })

    def _check_filtered_only_tables(self):
        module_specs = [
            (('drug',), '药物预测'),
            (('cibersort', 'immune'), '免疫浸润'),
            (('network',), '网络分析'),
        ]

        for keywords, module_name in module_specs:
            module_dir = self._find_module_dir(keywords)
            if not module_dir:
                continue

            tabular_files = [f for f in module_dir.rglob('*') if f.is_file() and f.suffix.lower() in self.TABULAR_SUFFIXES]
            if not tabular_files:
                continue

            lower_names = [f.name.lower() for f in tabular_files]
            filtered_only = all(any(hint in name for hint in self.FILTERED_NAME_HINTS) for name in lower_names)
            has_raw_table = any(any(hint in name for hint in self.RAW_NAME_HINTS) for name in lower_names)

            if filtered_only and not has_raw_table:
                self.issues.append({
                    'severity': 'CRITICAL',
                    'category': '原始总表缺失',
                    'file': self._relative_path(module_dir),
                    'message': f'{module_name}模块当前仅检测到筛选后结果，未检测到原始总表或中间总表。',
                    'suggestion': '补交筛选前原始总表，或保留可追溯的中间总表以支撑筛选逻辑。',
                    'evidence': {
                        'tabular_files': [self._relative_path(f) for f in tabular_files[:10]]
                    }
                })

    def _check_docking_module(self):
        module_dir = self._find_module_dir(('docking', 'dock'))
        if not module_dir:
            return

        files = [f for f in module_dir.rglob('*') if f.is_file()]
        structured_files = [f for f in files if f.suffix.lower() in self.DOCKING_STRUCTURED_SUFFIXES]
        image_files = [f for f in files if f.suffix.lower() in self.IMAGE_SUFFIXES]
        has_box_metadata = any(any(token in f.name.lower() for token in ('box', 'center', 'cavity', 'pocket', 'grid')) for f in files)
        has_score_table = any(any(token in f.name.lower() for token in ('score', 'affinity', 'energy', 'vina', 'dock')) for f in structured_files)
        # PDB/MOL2 复合物文件视为对接结果存在的证据（分数常嵌在文件名中）
        has_docking_output = any(f.suffix.lower() in ('.pdb', '.mol2') and
                                 any(tok in f.name.lower() for tok in ('complex', 'out', 'pose', 'docked'))
                                 for f in files)

        if image_files and (not has_score_table or not has_box_metadata):
            severity = 'WARNING' if has_docking_output else 'CRITICAL'
            target = self.warnings if severity == 'WARNING' else self.issues
            target.append({
                'severity': severity,
                'category': '分子对接证据不足',
                'file': self._relative_path(module_dir),
                'message': '分子对接模块存在图件，但缺少可识别的 docking score 结果和 / 或盒子大小、空腔中心等参数记录。',
                'suggestion': '补交 docking score 表，并保留盒子大小、中心坐标、空腔编号等关键对接参数。',
                'evidence': {
                    'structured_count': len(structured_files),
                    'image_count': len(image_files),
                    'has_score_table': has_score_table,
                    'has_box_metadata': has_box_metadata,
                }
            })

    def _check_md_module(self):
        module_dir = self._find_module_dir(('md', 'moleculardynamic'))
        if not module_dir:
            return

        files = [f for f in module_dir.rglob('*') if f.is_file()]
        image_files = [f for f in files if f.suffix.lower() in self.IMAGE_SUFFIXES]
        raw_files = [f for f in files if f.suffix.lower() in self.MD_RAW_SUFFIXES]

        if image_files and not raw_files:
            self.issues.append({
                'severity': 'CRITICAL',
                'category': '分子动力学证据不足',
                'file': self._relative_path(module_dir),
                'message': '分子动力学模块存在图件，但未检测到 xvg、csv、dat、xtc 等原始轨迹或数值导出文件。',
                'suggestion': '补交 xvg / csv 等轨迹数值文件，避免只能凭图复核。',
                'evidence': {
                    'image_count': len(image_files),
                    'raw_count': len(raw_files),
                }
            })

    def _check_report_mentions_missing_modules(self, report_text: str):
        """检查报告中提到了某类模块但项目中找不到对应目录"""
        if not report_text:
            return

        # (报告关键词, 目录搜索关键词, 模块名称)
        module_specs = [
            (['分子对接', 'molecular docking', 'CB-DOCK', 'AutoDock', 'Vina'],
             ('docking', 'dock'), '分子对接'),
            (['分子动力学', 'molecular dynamics', 'GROMACS', 'RMSD', 'RMSF'],
             ('md', 'moleculardynamic', 'dynamic'), '分子动力学'),
            (['拟时序', 'pseudotime', 'Monocle', 'trajectory'],
             ('pseudotime', 'psudotime', 'trajectory', 'monocle'), '拟时序分析'),
            (['SCENIC', 'regulon', 'GRN', 'gene regulatory network', '转录调控网络'],
             ('scenic', 'regulon', 'grn'), 'SCENIC转录调控分析'),
            (['NicheNet', 'nichenet', 'ligand-receptor', '配体-受体', '细胞通讯'],
             ('nichenet', 'niche_net', 'lr_pair', 'ligand_receptor'), 'NicheNet细胞通讯分析'),
            (['CellChat', 'cellchat', '细胞间通讯'],
             ('cellchat', 'cell_chat'), 'CellChat细胞通讯分析'),
        ]

        report_lower = report_text.lower()
        for keywords, dir_keys, module_name in module_specs:
            # 检查报告是否提到该模块
            mentioned = any(kw.lower() in report_lower for kw in keywords)
            if not mentioned:
                continue
            # 检查是否存在对应目录
            module_dir = self._find_module_dir(dir_keys)
            if module_dir is None:
                self.issues.append({
                    'severity': 'CRITICAL',
                    'category': f'{module_name}目录缺失',
                    'message': f'报告中提及了{module_name}，但项目目录中未找到对应的结果文件夹',
                    'suggestion': f'补交{module_name}结果目录及其数据文件',
                })

    def _check_image_only_modules(self):
        """检查常见只有图件无结构化数据的模块（SHAP/Correlation/ssGSEA/Quantify等）"""
        # (搜索关键词, 模块显示名, 预期数据描述, 严重度)
        image_only_specs = [
            (('shap', 'shapley'), 'SHAP', 'SHAP值导出表或特征重要性数值表', 'WARNING'),
            (('correlation', 'cor_'), 'Correlation', '相关性矩阵CSV或p值表', 'WARNING'),
            (('ssgesa', 'ssgsea'), 'ssGSEA', '免疫浸润评分矩阵CSV', 'WARNING'),
            (('quantify', 'aucell', 'scquantify'), 'scQuantify', '评分量化结果CSV', 'WARNING'),
        ]
        for keywords, mod_name, expected_data, severity in image_only_specs:
            module_dir = self._find_module_dir(keywords)
            if not module_dir:
                continue
            files = list(module_dir.rglob('*'))
            image_files = [f for f in files if f.is_file() and f.suffix.lower() in self.IMAGE_SUFFIXES]
            tabular_files = [f for f in files if f.is_file() and f.suffix.lower() in self.TABULAR_SUFFIXES]
            if image_files and not tabular_files:
                self.warnings.append({
                    'severity': severity,
                    'category': f'{mod_name}模块仅有图件',
                    'file': self._relative_path(module_dir),
                    'message': f'{mod_name}模块存在 {len(image_files)} 张图件，但未检测到 {expected_data}。',
                    'suggestion': f'补交{expected_data}以便交叉验证。',
                    'evidence': {
                        'image_count': len(image_files),
                        'tabular_count': 0,
                    }
                })

    def _check_suspicious_binary_exports(self):
        suspicious_files = []
        for file_path in islice(self.project_path.rglob('*'), 10000):
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()
            if suffix not in self.IMAGE_SUFFIXES:
                continue

            try:
                size = file_path.stat().st_size
            except OSError:
                continue

            if size == 0 or (suffix in {'.png', '.jpg', '.jpeg', '.tif', '.tiff'} and size < 1024):
                suspicious_files.append(self._relative_path(file_path))

        if suspicious_files:
            self.issues.append({
                'severity': 'WARNING',
                'category': '图件导出异常',
                'message': '检测到体积异常的小图件或空文件，存在导出失败、损坏或错图风险。',
                'suggestion': '人工打开这些图件复核，必要时重新导出。',
                'evidence': {
                    'files': suspicious_files[:20]
                }
            })

    def _split_body_and_references(self, report_text: str) -> tuple[str, List[str]]:
        marker = '参考文献'
        if marker not in report_text:
            return report_text, []

        marker_index = report_text.rfind(marker)
        body_text = report_text[:marker_index]
        reference_text = report_text[marker_index + len(marker):]
        stop_position = len(reference_text)
        for stop_marker in self.REFERENCE_STOP_MARKERS:
            marker_index = reference_text.find(stop_marker)
            if marker_index != -1:
                stop_position = min(stop_position, marker_index)

        reference_block = reference_text[:stop_position]
        references = [line.strip() for line in reference_block.splitlines() if line.strip()]
        return body_text, references

    def _extract_database_citations(self, body_text: str, database_name: str) -> List[Dict]:
        citations = []
        seen = set()
        normalized_body = self._normalize_inline_whitespace(body_text)
        aliases = self._database_aliases(database_name)
        for alias in aliases:
            escaped_alias = re.escape(alias)
            # 支持单个编号 [5] 和范围/列表 [1-5] [1,2,3]
            pattern = re.compile(rf'(?P<context>{escaped_alias}[^\[\]。；;]{{0,24}})\[(?P<ref>[\d,\-\s]+)\]', re.IGNORECASE)
            for match in pattern.finditer(normalized_body):
                ref_str = match.group('ref').strip()
                # 展开范围：如 "1-5" → [1,2,3,4,5]，"1,3" → [1,3]
                ref_indexes = self._expand_ref_range(ref_str)
                for ref_index in ref_indexes:
                    key = (str(ref_index), match.group('context'))
                    if key in seen:
                        continue
                    seen.add(key)
                    citations.append({
                        'database': database_name,
                        'ref_index': ref_index,
                        'context': match.group('context').strip(),
                    })
        return citations

    @staticmethod
    def _expand_ref_range(ref_str: str) -> list:
        """展开参考文献编号范围：'1-5' → [1,2,3,4,5]，'1,3' → [1,3]，'5' → [5]"""
        indexes = []
        for part in re.split(r'[,，\s]+', ref_str):
            part = part.strip()
            if not part:
                continue
            if '-' in part:
                bounds = part.split('-', 1)
                try:
                    start, end = int(bounds[0].strip()), int(bounds[1].strip())
                    indexes.extend(range(start, end + 1))
                except (ValueError, IndexError):
                    pass
            else:
                try:
                    indexes.append(int(part))
                except ValueError:
                    pass
        return indexes

    def _database_mentioned_without_citation(self, body_text: str, database_name: str) -> bool:
        normalized_body = self._normalize_inline_whitespace(body_text)
        for alias in self._database_aliases(database_name):
            escaped_alias = re.escape(alias)
            if re.search(escaped_alias, normalized_body, re.IGNORECASE):
                return True
        return False

    def _normalize_inline_whitespace(self, text: str) -> str:
        return re.sub(r'\s+', ' ', text)

    def _database_aliases(self, database_name: str) -> List[str]:
        aliases = [database_name]
        aliases.extend(self.DATABASE_REFERENCE_RULES.get(database_name, ()))
        unique_aliases = []
        seen = set()
        for alias in aliases:
            lowered = alias.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique_aliases.append(alias)
        unique_aliases.sort(key=len, reverse=True)
        return unique_aliases

    def _reference_matches_keywords(self, ref_text: str, keywords: tuple[str, ...]) -> bool:
        lowered = ref_text.lower()
        return any(keyword.lower() in lowered for keyword in keywords)

    def _find_matching_reference_indexes(self, references: List[str], keywords: tuple[str, ...]) -> List[int]:
        matches = []
        for index, ref_text in enumerate(references, start=1):
            if self._reference_matches_keywords(ref_text, keywords):
                matches.append(index)
        return matches

    def _find_module_dir(self, keywords: tuple[str, ...]) -> Optional[Path]:
        candidates = []
        for path in islice(self.project_path.rglob('*'), 10000):
            if not path.is_dir():
                continue
            lower_name = path.name.lower()
            if any(keyword in lower_name for keyword in keywords):
                candidates.append(path)

        if not candidates:
            return None

        candidates.sort(key=lambda p: len(p.parts))
        return candidates[0]

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.project_path))
        except ValueError:
            return str(path)

    def _get_report_reference(self) -> Optional[str]:
        for docx_file in self.project_path.rglob('*.docx'):
            if not docx_file.name.startswith('~$'):
                return self._relative_path(docx_file)
        return None


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser(description='证据完整性与参数完备性检查器')
    parser.add_argument('project_path', help='项目根目录路径')
    args = parser.parse_args()

    checker = EvidenceCompletenessChecker(args.project_path)
    result = checker.check_all()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()