#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数字交叉验证检查器 (P1级)

自动对比报告中声称的数量与 CSV 文件实际行数：
1. GO/KEGG 通路数量
2. DEG 差异基因数量（总/上调/下调）
3. 候选基因/核心基因数量
4. ML 特征筛选数量（LASSO/SVM/Boruta）

基于 26YLM076F 审核经验：GO 通路数 383 vs 实际 409、
KEGG 通路数 5 vs 实际 18 等数字不一致是常见问题。

作者: 审核框架 v6.5
"""

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from utils import safe_read_file, find_result_root
except ImportError:
    from pathlib import Path as _P
    def safe_read_file(path, encodings=None):
        try:
            return _P(path).read_text(encoding='utf-8', errors='ignore'), 'utf-8'
        except Exception:
            return '', None
    find_result_root = None

from base_project_checker import BaseProjectChecker


class NumberCrossrefChecker(BaseProjectChecker):
    """报告数字 ↔ CSV 行数 交叉验证"""

    # 文件名模式 → 语义标签 映射
    _FILE_PATTERNS = {
        'go': [
            (re.compile(r'^GO\.csv$', re.I), 'GO total'),
            (re.compile(r'GO.*?all', re.I), 'GO total'),
            (re.compile(r'GO.*?BP', re.I), 'GO BP'),
            (re.compile(r'GO.*?CC', re.I), 'GO CC'),
            (re.compile(r'GO.*?MF', re.I), 'GO MF'),
        ],
        'kegg': [
            (re.compile(r'^KEGG\.csv$', re.I), 'KEGG'),
            (re.compile(r'KEGG.*?all', re.I), 'KEGG'),
        ],
        'deg': [
            (re.compile(r'Diff\.all', re.I), 'DEG total'),
            (re.compile(r'Diff\.up', re.I), 'DEG up'),
            (re.compile(r'Diff\.down', re.I), 'DEG down'),
            (re.compile(r'DEG.*?all', re.I), 'DEG total'),
            (re.compile(r'DEG.*?up', re.I), 'DEG up'),
            (re.compile(r'DEG.*?down', re.I), 'DEG down'),
        ],
        'gene_list': [
            (re.compile(r'CoreGenes', re.I), 'core genes'),
            (re.compile(r'CandiGenes', re.I), 'candidate genes'),
            (re.compile(r'feature_lasso', re.I), 'LASSO features'),
            (re.compile(r'feature_svm', re.I), 'SVM features'),
            (re.compile(r'features?_boruta', re.I), 'Boruta features'),
            (re.compile(r'inter.*?gene', re.I), 'intersection genes'),
        ],
    }

    # 报告中的数字提取模式（类别 → 正则列表）
    # GO/KEGG/DEG 跨度限制防止跨章节错提；ML/基因模式保留宽松跨度
    _REPORT_PATTERNS = {
        'GO total': [
            re.compile(r'共.{0,20}?(\d+)\s*条.{0,20}?(?:GO|通路|pathway)', re.I),
            re.compile(r'(\d+)\s*条.{0,20}?(?:GO|通路)', re.I),
            re.compile(r'GO.{0,40}?(\d+)\s*条', re.I),
        ],
        'GO BP': [
            re.compile(r'(?:生物过程|BP|biological process).{0,20}?(\d+)\s*条', re.I),
            re.compile(r'(\d+)\s*条.{0,20}?(?:生物过程|BP)', re.I),
        ],
        'KEGG': [
            re.compile(r'KEGG.{0,40}?(\d+)\s*条', re.I),
            re.compile(r'(\d+)\s*条.{0,20}?KEGG', re.I),
        ],
        'DEG total': [
            re.compile(r'共.{0,20}?(\d+)\s*个.{0,20}?(?:差异|DEG)', re.I),
            re.compile(r'(\d+)\s*个.{0,20}?(?:差异|DEG)', re.I),
            re.compile(r'(?:差异|DEG).{0,20}?(\d+)\s*个', re.I),
            re.compile(r'筛选.{0,20}?(\d+)\s*个.{0,20}?(?:差异|DEG)', re.I),
        ],
        'DEG up': [
            re.compile(r'(\d+)\s*个.{0,20}?(?:上调|up)', re.I),
            re.compile(r'(?:上调|up).{0,20}?(\d+)\s*个', re.I),
        ],
        'DEG down': [
            re.compile(r'(\d+)\s*个.{0,20}?(?:下调|down)', re.I),
            re.compile(r'(?:下调|down).{0,20}?(\d+)\s*个', re.I),
        ],
        'core genes': [
            re.compile(r'(\d+)\s*个.*?(?:核心|core|关键|key)', re.I),
            re.compile(r'(?:核心|core|关键|key).*?(\d+)\s*个', re.I),
        ],
        'candidate genes': [
            re.compile(r'(\d+)\s*个.*?(?:候选|candidate)', re.I),
            re.compile(r'(?:候选|candidate).*?(\d+)\s*个', re.I),
        ],
        'LASSO features': [
            re.compile(r'LASSO.*?(\d+)\s*个', re.I),
            re.compile(r'(\d+)\s*个.*?LASSO', re.I),
        ],
        'SVM features': [
            re.compile(r'SVM.*?(\d+)\s*个', re.I),
            re.compile(r'(\d+)\s*个.*?SVM', re.I),
        ],
        'Boruta features': [
            re.compile(r'Boruta.*?(\d+)\s*个', re.I),
            re.compile(r'(\d+)\s*个.*?Boruta', re.I),
        ],
    }

    def __init__(self, project_path: str, layer0_data: dict = None):
        super().__init__(project_path, layer0_data=layer0_data)

    def check_all(self) -> Dict:
        """执行数字交叉验证"""
        # 加载报告文本
        report_text = self.load_report_text()

        # 查找结果根目录
        result_root = None
        if find_result_root:
            result_root = find_result_root(self.project_path)
        if not result_root:
            return {
                'issues': [],
                'warnings': [],
                'skipped': True,
                'reason': '未找到结果目录',
            }

        # 扫描 CSV 文件，匹配文件名模式
        file_counts = self._scan_csv_counts(result_root)

        if not report_text:
            # 降级模式：无报告时列出 CSV 行数摘要供 AI核对
            if file_counts:
                self.warnings.append({
                    'severity': 'INFO',
                    'category': 'CSV行数摘要（无报告降级模式）',
                    'message': '未找到报告文本，仅列出文件行数供 AI核对',
                    'evidence': {label: {'rows': count, 'file': fpath}
                                 for label, (count, fpath) in file_counts.items()},
                })
            return {
                'issues': self.issues,
                'warnings': self.warnings,
                'skipped': False,
                'degraded': True,
                'reason': '未找到报告文本，仅输出CSV行数摘要',
                'file_counts': file_counts,
            }

        # 从报告中提取数字
        report_numbers = self._extract_report_numbers(report_text)

        # 交叉比对
        self._crossref(file_counts, report_numbers)

        # DEG 求和验证：上调 + 下调 = 总数
        self._check_deg_sum(file_counts, report_numbers)

        # 异常统计值检测：AUC=1/0, p=0.000, OR=0/Inf
        self._check_statistical_anomalies(report_text)

        # 验证集样本量检测（Iter5）
        self._check_validation_sample_size(report_text)

        # GO 子分类特殊检查：如果有 GO.csv，检查 ONTOLOGY 列
        self._check_go_subcategory(result_root, report_text)

        return {
            'issues': self.issues,
            'warnings': self.warnings,
            'total_checks': len(file_counts),
            'failed_checks': len(self.issues),
            'file_counts': file_counts,
            'report_numbers': report_numbers,
        }

    def _scan_csv_counts(self, result_root: Path) -> Dict[str, Tuple[int, str]]:
        """扫描 CSV 文件，返回 {标签: (行数, 文件路径)}

        对含 p 值列的文件，同时计算显著行数(p<0.05)并存入 _significant_counts。
        """
        counts = {}
        self._significant_counts: Dict[str, int] = {}
        for category, patterns in self._FILE_PATTERNS.items():
            for csv_file in sorted(result_root.rglob('*.csv')):
                if not csv_file.is_file() or csv_file.stat().st_size < 50:
                    continue
                for pat, label in patterns:
                    if pat.search(csv_file.name):
                        n = self._count_data_rows(csv_file)
                        if n is not None and n > 0:
                            if 'boruta' in label.lower():
                                n = self._count_boruta_confirmed(csv_file) or n
                            counts[label] = (n, str(csv_file.relative_to(self.project_path)))
                            # 尝试计算显著行数
                            sig = self._count_significant_rows(csv_file, category)
                            if sig is not None and sig != n:
                                self._significant_counts[label] = sig
                        break
        return counts

    # p 值列候选名
    _PVAL_COLUMNS = ['p.adjust', 'p_val_adj', 'padj', 'adj.P.Val', 'FDR',
                     'qvalue', 'q.value', 'pvalue', 'P.Value']

    def _count_significant_rows(self, filepath: Path, category: str) -> Optional[int]:
        """计算显著行数（p.adjust < 0.05），仅对 GO/KEGG/DEG 类文件尝试。"""
        if category not in ('go', 'kegg', 'deg'):
            return None
        try:
            text, _ = safe_read_file(str(filepath))
            if not text:
                return None
            lines = text.strip().split('\n')
            if len(lines) < 2:
                return None
            reader = csv.DictReader(lines)
            fieldnames = reader.fieldnames or []
            # 查找 p 值列
            pcol = None
            for candidate in self._PVAL_COLUMNS:
                if candidate in fieldnames:
                    pcol = candidate
                    break
            if not pcol:
                return None
            count = 0
            for row in reader:
                val = row.get(pcol, '').strip()
                try:
                    if float(val) < 0.05:
                        count += 1
                except (ValueError, TypeError):
                    continue
            return count
        except Exception:
            return None

    def _count_data_rows(self, filepath: Path) -> Optional[int]:
        """计算 CSV 数据行数（不含表头）"""
        try:
            text, _ = safe_read_file(str(filepath))
            if not text:
                return None
            lines = [l for l in text.strip().split('\n') if l.strip()]
            return max(0, len(lines) - 1)  # 减去表头
        except Exception:
            return None

    def _count_boruta_confirmed(self, filepath: Path) -> Optional[int]:
        """计算 Boruta 中 Confirmed 的基因数"""
        try:
            text, _ = safe_read_file(str(filepath))
            if not text:
                return None
            lines = text.strip().split('\n')
            if len(lines) < 2:
                return None
            # 查找 decision 列
            header = lines[0]
            reader = csv.DictReader(lines)
            count = 0
            for row in reader:
                decision = row.get('decision', row.get('Decision', ''))
                if decision.strip().lower() == 'confirmed':
                    count += 1
            return count if count > 0 else None
        except Exception:
            return None

    def _extract_report_numbers(self, report_text: str) -> Dict[str, List[int]]:
        """从报告中提取各类别的声称数字"""
        numbers = {}
        for label, patterns in self._REPORT_PATTERNS.items():
            found = []
            for pat in patterns:
                for m in pat.finditer(report_text):
                    try:
                        n = int(m.group(1).replace(',', ''))
                        if n not in found:
                            found.append(n)
                    except (ValueError, IndexError):
                        continue
            if found:
                numbers[label] = found
        return numbers

    def _crossref(self, file_counts: Dict, report_numbers: Dict):
        """交叉比对文件行数 vs 报告声称数字。

        对比逻辑（由宽到严）：
        1. 报告数字匹配 CSV 总行数（±1 容差）→ OK
        2. 报告数字匹配显著行数 p<0.05（±1 容差）→ OK
        3. 报告数字全部 < CSV 总行数 → WARNING（可能是子集/子分类）
        4. 最接近数字在 ±max(5, 10%) 容差内 → WARNING（近似不一致）
        5. 以上均不满足 → CRITICAL
        """
        sig_counts = getattr(self, '_significant_counts', {})

        for label, (actual_count, filepath) in file_counts.items():
            if label not in report_numbers:
                continue
            claimed = report_numbers[label]

            # 匹配 1: 总行数
            if actual_count in claimed or any(abs(actual_count - c) <= 1 for c in claimed):
                continue

            # 匹配 2: 显著行数（仅当 sig != total 时有区分度）
            sig = sig_counts.get(label)
            if sig is not None and sig != actual_count:
                if sig in claimed or any(abs(sig - c) <= 1 for c in claimed):
                    continue

            # 匹配 3: 报告声称数全部 < CSV 总行数 → 可能是子集/子分类
            if all(c < actual_count for c in claimed):
                detail = f'总计 {actual_count} 行'
                if sig is not None and sig != actual_count:
                    detail += f'，显著行(p<0.05) {sig} 行'
                self.warnings.append({
                    'severity': 'WARNING',
                    'category': '数字交叉验证（报告可能仅统计子集）',
                    'message': (
                        f'{label}: 报告声称 {claimed}，'
                        f'{filepath} {detail}。'
                        f'报告数字均小于文件行数，可能指筛选后子集或子分类。'
                    ),
                    'file': filepath,
                    'evidence': {
                        'label': label,
                        'claimed': claimed,
                        'actual_total': actual_count,
                        'actual_significant': sig,
                    },
                })
                continue

            # 匹配 4: 近似容差 — 最接近的 claimed 与 actual 差值在 ±max(5, 10%) 内 → WARNING
            tol = max(5, int(actual_count * 0.1))
            closest_diff = min(abs(actual_count - c) for c in claimed)
            if closest_diff <= tol:
                closest_val = min(claimed, key=lambda c: abs(actual_count - c))
                self.warnings.append({
                    'severity': 'WARNING',
                    'category': '数字交叉验证（近似不一致）',
                    'message': (
                        f'{label}: 报告声称 {closest_val}，'
                        f'{filepath} 实际为 {actual_count} 行'
                        f'（差值 {closest_diff}，在 ±{tol} 容差内）。'
                        f'可能来自不同分析阶段或筛选条件。'
                    ),
                    'file': filepath,
                    'evidence': {
                        'label': label,
                        'claimed': claimed,
                        'actual': actual_count,
                        'closest_diff': closest_diff,
                        'tolerance': tol,
                    },
                })
                continue

            # 不匹配
            self.issues.append({
                'severity': 'CRITICAL',
                'category': '数字交叉验证不一致',
                'message': (
                    f'{label}: 报告声称 {claimed}，'
                    f'但 {filepath} 实际为 {actual_count} 行'
                ),
                'file': filepath,
                'evidence': {
                    'label': label,
                    'claimed': claimed,
                    'actual': actual_count,
                },
            })

    def _check_go_subcategory(self, result_root: Path, report_text: str):
        """如果 GO.csv 含 ONTOLOGY 列，分别统计 BP/CC/MF 行数与报告对比"""
        go_files = list(result_root.rglob('GO.csv'))
        if not go_files:
            return
        go_file = go_files[0]
        try:
            text, _ = safe_read_file(str(go_file))
            if not text:
                return
            lines = text.strip().split('\n')
            reader = csv.DictReader(lines)
            sub_counts = {'BP': 0, 'CC': 0, 'MF': 0}
            for row in reader:
                ont = row.get('ONTOLOGY', row.get('ontology', '')).strip().upper()
                if ont in sub_counts:
                    sub_counts[ont] += 1
            if sum(sub_counts.values()) == 0:
                return

            # 对比报告中的 BP/CC/MF 数字
            rel_path = str(go_file.relative_to(self.project_path))
            for ont, count in sub_counts.items():
                report_label = f'GO {ont}'
                if report_label in self._REPORT_PATTERNS:
                    for pat in self._REPORT_PATTERNS[report_label]:
                        for m in pat.finditer(report_text):
                            claimed = int(m.group(1).replace(',', ''))
                            if abs(claimed - count) > 1:
                                self.issues.append({
                                    'severity': 'CRITICAL',
                                    'category': '数字交叉验证不一致',
                                    'message': (
                                        f'GO {ont}: 报告声称 {claimed} 条，'
                                        f'但 {rel_path} 中 {ont} 实际为 {count} 条'
                                    ),
                                    'file': rel_path,
                                    'evidence': {
                                        'label': f'GO {ont}',
                                        'claimed': claimed,
                                        'actual': count,
                                    },
                                })
        except Exception:
            pass

    def _check_deg_sum(self, file_counts: Dict, report_numbers: Dict):
        """验证 DEG 上调 + 下调 = 总数（文件层面 + 报告层面）"""
        # 文件层面验证
        up_count = file_counts.get('DEG up')
        down_count = file_counts.get('DEG down')
        total_count = file_counts.get('DEG total')

        if up_count and down_count and total_count:
            calc_sum = up_count[0] + down_count[0]
            actual_total = total_count[0]
            if abs(calc_sum - actual_total) > 1:
                self.issues.append({
                    'severity': 'CRITICAL',
                    'category': 'DEG求和不一致（文件层面）',
                    'message': (
                        f'DEG上调({up_count[0]}) + 下调({down_count[0]}) = '
                        f'{calc_sum}，但DEG总数文件为 {actual_total} 行'
                    ),
                    'evidence': {
                        'up': up_count[0],
                        'down': down_count[0],
                        'calculated_sum': calc_sum,
                        'actual_total': actual_total,
                    },
                })

        # 报告层面验证
        rep_up = report_numbers.get('DEG up', [])
        rep_down = report_numbers.get('DEG down', [])
        rep_total = report_numbers.get('DEG total', [])

        if rep_up and rep_down and rep_total:
            for u in rep_up:
                for d in rep_down:
                    calc = u + d
                    for t in rep_total:
                        if abs(calc - t) > 1 and abs(calc - t) > max(5, int(t * 0.02)):
                            self.issues.append({
                                'severity': 'CRITICAL',
                                'category': 'DEG求和不一致（报告层面）',
                                'message': (
                                    f'报告声称上调{u}个 + 下调{d}个 = {calc}，'
                                    f'但报告声称DEG总数为{t}个'
                                ),
                                'evidence': {
                                    'claimed_up': u,
                                    'claimed_down': d,
                                    'calculated_sum': calc,
                                    'claimed_total': t,
                                },
                            })
                            return  # 只报告一次

    # 异常统计值检测的正则模式
    _ANOMALY_PATTERNS = [
        # AUC=1 或 AUC=0（完美/无判别力）
        (re.compile(r'AUC[^\d]{0,20}?[=为:：]\s*(?:1\.0+|1(?![.\d]))\b', re.I),
         'AUC=1（完美判别，极不合理）', 'WARNING'),
        (re.compile(r'AUC[^\d]{0,20}?[=为:：]\s*0(?:\.0+)?\b', re.I),
         'AUC=0（无判别力，极不合理）', 'WARNING'),
        # AUC ≥ 0.95（但非完美1.0）— 小样本时需警惕过拟合（Iter5b）
        (re.compile(r'AUC[^\d]{0,20}?[=为:：]\s*0\.9[5-9]\d*\b', re.I),
         'AUC≥0.95（接近完美，需关注样本量和过拟合风险）', 'INFO'),
        # p=0.000 或 p=0（可能精度截断）
        (re.compile(r'[Pp]\s*[=<]\s*0\.000(?!\d)', re.I),
         'p=0.000（可能精度截断，应报告为p<0.001）', 'INFO'),
        # OR=0 或 OR=Inf
        (re.compile(r'OR[^\d]{0,10}?[=为]\s*(?:0(?:\.0+)?|Inf|∞)\b', re.I),
         'OR异常值（0或Inf），可能存在完全分离', 'WARNING'),
    ]

    def _check_statistical_anomalies(self, report_text: str):
        """检测报告中的统计异常值"""
        if not report_text:
            return
        for pat, desc, severity in self._ANOMALY_PATTERNS:
            matches = pat.findall(report_text)
            if matches:
                # 只取前3个匹配作为示例
                examples = matches[:3]
                self.warnings.append({
                    'severity': severity,
                    'category': '统计异常值',
                    'message': f'{desc}（出现{len(matches)}次）',
                    'evidence': {
                        'pattern': desc,
                        'count': len(matches),
                        'examples': examples,
                    },
                })

    # 验证集/训练集样本量检测模式（Iter5）
    _VALIDATION_SAMPLE_PATTERNS = [
        # "验证集(n=3)" "validation set (n=5)" "测试集共2例"
        re.compile(
            r'(?:验证集|测试集|validation\s*set|test\s*set)'
            r'[^。\n]{0,40}?'
            r'(?:[nN]\s*[=＝]\s*|共\s*|含\s*|包含\s*|样本\s*)'
            r'(\d+)',
            re.I
        ),
        # "n=3 for validation"
        re.compile(
            r'[nN]\s*[=＝]\s*(\d+)[^。\n]{0,30}?(?:验证|测试|validation|test)',
            re.I
        ),
    ]

    def _check_validation_sample_size(self, report_text: str):
        """检测验证集样本量过小（≤5）的情况（Iter5）"""
        if not report_text:
            return
        seen = set()
        for pat in self._VALIDATION_SAMPLE_PATTERNS:
            for m in pat.finditer(report_text):
                n = int(m.group(1))
                if n <= 5 and n not in seen:
                    seen.add(n)
                    context = report_text[max(0, m.start()-30):m.end()+30].strip()
                    self.warnings.append({
                        'severity': 'WARNING',
                        'category': '验证集样本量过小',
                        'message': f'验证集/测试集样本量仅 n={n}（≤5），统计效力不足，ROC/AUC等结果可信度存疑',
                        'evidence': {
                            'sample_size': n,
                            'context': context[:200],
                        },
                    })
