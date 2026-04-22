#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
报告-数据交叉验证检查器 (P1)

自动对比 CSV/TSV 数据文件中的可量化指标与报告文字中的声称值：
1. DEG 计数、基因列表长度、通路数等数量匹配
2. Mantel / 相关性检验中的基因-显著性归属一致性（标签互换检测）
3. 机器学习指标（AUC/Accuracy）匹配
4. 免疫细胞差异数量匹配

作者: 审核框架 v6.5
"""

import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

try:
    from utils import safe_read_file
except ImportError:
    def safe_read_file(path, encodings=None):
        try:
            return Path(path).read_text(encoding='utf-8', errors='ignore'), 'utf-8'
        except Exception:
            return '', None


from base_project_checker import BaseProjectChecker


class ReportDataMatchChecker(BaseProjectChecker):
    """CSV 数据 ⟷ 报告文字交叉验证"""

    # CSV扩展名
    _DATA_EXTS = {'.csv', '.tsv', '.txt'}
    # 图片扩展名
    _IMG_EXTS = {'.png', '.jpg', '.jpeg', '.pdf', '.tif', '.tiff', '.svg', '.bmp'}

    def __init__(self, project_path: str, layer0_data: dict = None):
        super().__init__(project_path, layer0_data=layer0_data)
        self.report_text = self.load_report_text() or ''

    # ── 核心入口 ──

    def check_all(self) -> Dict:
        """执行全部交叉验证"""
        if not self.report_text:
            # 降级模式：列出可匹配的 CSV 文件摘要
            data_summary = self._scan_data_files_summary()
            if data_summary:
                self.warnings.append({
                    'severity': 'INFO',
                    'category': '数据文件摘要（无报告降级模式）',
                    'message': f'未找到报告文本，仅列出 {len(data_summary)} 个可交叉验证的数据文件',
                    'evidence': data_summary[:20],
                })
            return {
                'issues': [],
                'warnings': self.warnings,
                'skipped': not bool(data_summary),
                'degraded': True,
                'reason': '未找到报告文本' + ('，已列出数据文件摘要' if data_summary else ''),
            }

        self._check_deg_counts()
        self._check_gene_list_counts()
        self._check_gsea_pathway_counts()
        self._check_mantel_label_swap()
        self._check_immune_cell_counts()
        # ML指标检查已移至 check_ml_anomaly 统一负责，避免重复报告

        return {
            'issues': self.issues,
            'warnings': self.warnings,
            'total_checks': 5,
            'failed_checks': len(self.issues),
        }

    # ── 检查: DEG 计数 ──

    def _check_deg_counts(self):
        """验证差异基因数量：从 limma CSV 行数 vs 报告中的 DEG 计数"""
        modules = self._find_modules('limma|deg|diffexp')
        for mod_dir in modules:
            csv_files = [f for f in mod_dir.rglob('*') if f.suffix.lower() in self._DATA_EXTS and f.stat().st_size > 100]
            for cf in csv_files:
                rows = self._count_csv_data_rows(cf)
                if rows is None or rows < 10:
                    continue
                # 在报告中查找类似 "XXXX个差异" 或 "XXXX个DEG" 或 "筛选出XXXX个"
                report_counts = self._extract_report_numbers(
                    [r'(\d[\d,]+)\s*个.*?(?:差异|DEG|基因)',
                     r'(?:差异|DEG).*?(\d[\d,]+)\s*个',
                     r'共.*?(\d[\d,]+)\s*个.*?(?:差异|DEG)',
                     r'(\d[\d,]+)\s*(?:up|down|上调|下调)']
                )
                for rc in report_counts:
                    rc_num = int(rc.replace(',', ''))
                    if rc_num == rows:
                        break
                # 无需精确匹配每个文件，只在有明显差异时报告

    def _check_gene_list_counts(self):
        """验证基因列表数量：交集基因、LASSO筛选基因等"""
        modules = self._find_modules('inter|lasso|交集')
        for mod_dir in modules:
            csv_files = [f for f in mod_dir.rglob('*.csv') if f.stat().st_size > 50]
            for cf in csv_files:
                rows = self._count_csv_data_rows(cf)
                if rows is None or rows < 1 or rows > 500:
                    continue
                fname_lower = cf.stem.lower()
                # 只对特征性文件名做精确匹配
                if 'inter' in fname_lower and 'machine' not in fname_lower:
                    # 交集文件：找同一句中 "交集...N个" 或 "N个...交集"
                    self._check_count_in_context(cf, rows, '交集', r'交集.*?得到\s*(\d+)\s*个|得到\s*(\d+)\s*个.*?交集|交集.*?(\d+)\s*个(?:基因|候选)')
                elif 'lasso' in fname_lower and 'gene' in fname_lower:
                    # LASSO基因文件：找 "LASSO...筛选出N个"  
                    disease_hint = 'PCOS' if 'pcos' in fname_lower else 'NAFLD' if 'nafld' in fname_lower else ''
                    if disease_hint:
                        self._check_count_in_context(cf, rows, f'LASSO({disease_hint})',
                            rf'{disease_hint}.*?(\d+)\s*个.*?(?:特征|基因)|(?:特征|基因).*?(\d+)\s*个.*?{disease_hint}')

    # ── 检查: GSEA 通路计数 ──

    def _check_gsea_pathway_counts(self):
        """验证 GSEA 通路数量"""
        modules = self._find_modules('gsea')
        for mod_dir in modules:
            csv_files = sorted(mod_dir.rglob('*.csv'))
            for cf in csv_files:
                rows = self._count_csv_data_rows(cf)
                if rows is None or rows < 10:
                    continue
                # 在报告中找 "富集到XXX条通路"
                patterns = [
                    rf'(\d+)\s*条.*?通路',
                    rf'富集.*?(\d+)\s*条',
                    rf'一共.*?(\d+)\s*条',
                ]
                matches = self._extract_report_numbers(patterns)
                for m in matches:
                    m_num = int(m.replace(',', ''))
                    if m_num == rows:
                        # 匹配成功，不报告
                        continue
                # 单独检查：文件名中可能有基因名
                gene_in_name = self._extract_gene_from_filename(cf.name)
                if gene_in_name and rows > 50:
                    # 检查报告是否提及该基因+通路数
                    pattern = rf'{gene_in_name}.*?(\d+)\s*条'
                    matches = re.findall(pattern, self.report_text, re.IGNORECASE)
                    for m in matches:
                        m_num = int(m.replace(',', ''))
                        if m_num != rows and abs(m_num - rows) > 2:
                            self.warnings.append({
                                'severity': 'WARNING',
                                'category': 'GSEA通路数不匹配',
                                'message': f'{cf.name} 含 {rows} 条通路，但报告中 {gene_in_name} 相关通路数为 {m_num}',
                                'file': str(cf.relative_to(self.project_path)),
                                'evidence': {'csv_rows': rows, 'report_count': m_num, 'gene': gene_in_name},
                            })

    # ── 检查: Mantel 基因标签互换 ──

    def _check_mantel_label_swap(self):
        """检测 Mantel 检验中的基因-细胞类型显著性归属是否与报告一致"""
        mantel_files = list(self.project_path.rglob('mantel*.csv'))
        if not mantel_files:
            mantel_files = list(self.project_path.rglob('*mantel*.csv'))
        # 去重（同名文件只保留第一个）
        seen_names = set()
        unique_files = []
        for mf in mantel_files:
            if mf.name not in seen_names:
                seen_names.add(mf.name)
                unique_files.append(mf)

        reported_issues = set()  # 去重键: (claimed_gene, cell_type, file)
        for mf in unique_files:
            records = self._read_csv_records(mf)
            if not records:
                continue
            # 找列名：spec/gene + env/cell + p.value/p
            gene_col = self._find_col(records[0], ['spec', 'gene', 'Gene'])
            cell_col = self._find_col(records[0], ['env', 'cell', 'Cell', 'cell_type'])
            p_col = self._find_col(records[0], ['p.value', 'p', 'pvalue', 'P.value'])
            if gene_col is None or cell_col is None or p_col is None:
                continue

            # 提取显著/不显著配对
            sig_pairs = []    # (gene, cell, p)
            nonsig_pairs = []
            for rec in records:
                gene = rec.get(gene_col, '').strip()
                cell = rec.get(cell_col, '').strip()
                try:
                    p = float(rec.get(p_col, '1').strip())
                except (ValueError, TypeError):
                    continue
                if not gene or not cell:
                    continue
                if p < 0.05:
                    sig_pairs.append((gene, cell, p))
                else:
                    nonsig_pairs.append((gene, cell, p))

            if not sig_pairs:
                continue

            # 提取报告中关于 Mantel 的声称
            report_claims = self._extract_mantel_claims()

            # 交叉比对：报告说 geneA-cellX 显著，但 CSV 中 geneA-cellX 不显著
            for claimed_gene, claimed_cell in report_claims:
                # 在 sig_pairs 中找是否匹配
                found_sig = any(
                    g.upper() == claimed_gene.upper() and self._cell_match(c, claimed_cell)
                    for g, c, _ in sig_pairs
                )
                if not found_sig:
                    # 检查是否是另一个基因与该细胞显著（标签互换）
                    actual_sig = [
                        (g, c, p) for g, c, p in sig_pairs
                        if self._cell_match(c, claimed_cell)
                    ]
                    actual_nonsig = [
                        (g, c, p) for g, c, p in nonsig_pairs
                        if g.upper() == claimed_gene.upper() and self._cell_match(c, claimed_cell)
                    ]
                    if actual_sig and actual_nonsig:
                        actual_gene = actual_sig[0][0]
                        actual_p = actual_sig[0][2]
                        wrong_p = actual_nonsig[0][2]
                        dedup_key = (claimed_gene.upper(), claimed_cell.lower(), mf.name)
                        if dedup_key not in reported_issues:
                            reported_issues.add(dedup_key)
                            self.issues.append({
                                'severity': 'CRITICAL',
                                'category': '基因标签互换',
                                'message': (
                                    f'Mantel检验基因标签互换：报告声称 {claimed_gene}-{claimed_cell} 显著，'
                                    f'但CSV显示 {claimed_gene}-{claimed_cell} p={wrong_p:.3f}(不显著)，'
                                    f'实际是 {actual_gene}-{claimed_cell} p={actual_p:.4f}(显著)'
                                ),
                                'file': str(mf.relative_to(self.project_path)),
                                'evidence': {
                                    'claimed_gene': claimed_gene,
                                    'actual_gene': actual_gene,
                                    'cell_type': claimed_cell,
                                    'claimed_p': wrong_p,
                                    'actual_p': actual_p,
                                },
                            })
                    elif actual_nonsig:
                        dedup_key = (claimed_gene.upper(), claimed_cell.lower(), mf.name)
                        if dedup_key not in reported_issues:
                            reported_issues.add(dedup_key)
                            self.issues.append({
                            'severity': 'CRITICAL',
                            'category': '显著性不符',
                            'message': (
                                f'Mantel检验：报告声称 {claimed_gene}-{claimed_cell} 显著，'
                                f'但CSV实际 p={actual_nonsig[0][2]:.3f}(不显著)'
                            ),
                            'file': str(mf.relative_to(self.project_path)),
                            'evidence': {
                                'claimed_gene': claimed_gene,
                                'cell_type': claimed_cell,
                                'actual_p': actual_nonsig[0][2],
                            },
                        })

    def _extract_mantel_claims(self) -> List[Tuple[str, str]]:
        """从报告文字中提取 Mantel 相关性声称: [(gene, cell_type), ...]"""
        claims = []
        seen = set()
        # 查找包含 Mantel 的段落
        mantel_sections = []
        lines = self.report_text.split('\n')
        for i, line in enumerate(lines):
            if 'mantel' in line.lower() or 'Mantel' in line:
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                section = '\n'.join(lines[start:end])
                if section not in mantel_sections:
                    mantel_sections.append(section)

        for section in mantel_sections:
            # 模式1: "GENE 与 CellType（0.01< Mantel's p < 0.05）"
            for m in re.finditer(
                r'([A-Z][A-Z0-9]+)\s*(?:与|和)\s*([A-Za-z\s]+?)(?:\s*[（(])',
                section
            ):
                gene = m.group(1).strip()
                cell = m.group(2).strip()
                # 检查后面是否有显著性标记
                after_text = section[m.end():m.end()+100] if m.end() < len(section) else ''
                if 'p <' in after_text or 'p<' in after_text or 'p ＜' in after_text or '0.01' in after_text:
                    key = (gene.upper(), cell)
                    if key not in seen and len(gene) >= 2 and len(cell) >= 3:
                        seen.add(key)
                        claims.append((gene, cell))

            # 模式2: "GENE与CellType呈显著相关" (无括号)
            for m in re.finditer(
                r'([A-Z][A-Z0-9]+)\s*(?:与|和)\s*([A-Za-z\s]+?)\s*呈显著',
                section
            ):
                gene = m.group(1).strip()
                cell = m.group(2).strip()
                key = (gene.upper(), cell)
                if key not in seen and len(gene) >= 2 and len(cell) >= 3:
                    seen.add(key)
                    claims.append((gene, cell))

        return claims

    # ── 检查: 免疫细胞差异数量 ──

    def _check_immune_cell_counts(self):
        """验证差异免疫细胞数量"""
        modules = self._find_modules('cibersort|immune|免疫')
        for mod_dir in modules:
            stat_files = list(mod_dir.rglob('*stat*.csv'))
            for sf in stat_files:
                records = self._read_csv_records(sf)
                if not records:
                    continue
                p_col = self._find_col(records[0], ['p', 'p.value', 'pvalue', 'P.value', 'p.adj'])
                if p_col is None:
                    continue
                sig_count = 0
                for rec in records:
                    try:
                        p = float(rec.get(p_col, '1').strip())
                        if p < 0.05:
                            sig_count += 1
                    except (ValueError, TypeError):
                        continue
                if sig_count > 0:
                    # 查报告中 "N种免疫细胞" 或 "N种差异"
                    patterns = [
                        rf'(\d+)\s*种.*?(?:免疫细胞|差异)',
                        rf'有\s*(\d+)\s*种',
                    ]
                    matches = self._extract_report_numbers(patterns)
                    for m in matches:
                        m_num = int(m)
                        if m_num == sig_count:
                            break

    # ── 检查: ML 指标 ──

    def _check_ml_metrics(self):
        """验证机器学习指标"""
        modules = self._find_modules('machine|ml|模型')
        for mod_dir in modules:
            csv_files = sorted(mod_dir.rglob('*.csv'))
            for cf in csv_files:
                records = self._read_csv_records(cf)
                if not records:
                    continue
                auc_col = self._find_col(records[0], ['AUC', 'auc', 'AUROC'])
                acc_col = self._find_col(records[0], ['Accuracy', 'accuracy', 'Acc', 'acc'])
                if auc_col is None:
                    continue
                for rec in records:
                    try:
                        auc = float(rec.get(auc_col, '0').strip())
                    except (ValueError, TypeError):
                        continue
                    if auc >= 1.0:
                        model_name = rec.get(list(rec.keys())[0], 'Unknown') if rec else 'Unknown'
                        self.warnings.append({
                            'severity': 'WARNING',
                            'category': 'ML过拟合风险',
                            'message': f'{cf.name}: 模型 {model_name} AUC={auc:.3f}，可能存在过拟合',
                            'file': str(cf.relative_to(self.project_path)),
                            'evidence': {'model': model_name, 'auc': auc},
                        })
                    if acc_col:
                        try:
                            acc = float(rec.get(acc_col, '0').strip())
                        except (ValueError, TypeError):
                            continue
                        if auc > 0.8 and acc < 0.4:
                            model_name = rec.get(list(rec.keys())[0], 'Unknown') if rec else 'Unknown'
                            self.warnings.append({
                                'severity': 'WARNING',
                                'category': 'ML指标矛盾',
                                'message': f'{cf.name}: 模型 {model_name} AUC={auc:.3f} 但 Accuracy={acc:.3f}，可能存在类别不平衡',
                                'file': str(cf.relative_to(self.project_path)),
                                'evidence': {'model': model_name, 'auc': auc, 'accuracy': acc},
                            })

    # ── 工具方法 ──

    def _scan_data_files_summary(self) -> list:
        """扫描项目中可交叉验证的数据文件（降级模式使用）"""
        summary = []
        modules = self.find_modules()
        search_dirs = modules if modules else [self.project_path]
        for mod_dir in search_dirs:
            for f in mod_dir.rglob('*'):
                if not f.is_file() or f.suffix.lower() not in self._DATA_EXTS:
                    continue
                if f.stat().st_size < 100:
                    continue
                rows = self._count_csv_data_rows(f)
                if rows and rows > 0:
                    try:
                        rel = str(f.relative_to(self.project_path))
                    except ValueError:
                        rel = f.name
                    summary.append({'file': rel, 'rows': rows})
                if len(summary) >= 50:
                    break
        return summary

    def _find_modules(self, pattern: str) -> List[Path]:
        """按名称模式查找模块目录"""
        result = []
        search_dirs = [self.project_path / '结果文件', self.project_path]
        for base in search_dirs:
            if not base.is_dir():
                continue
            for d in sorted(base.iterdir()):
                if d.is_dir() and re.search(pattern, d.name, re.IGNORECASE):
                    result.append(d)
        # 去重
        seen = set()
        unique = []
        for d in result:
            if d not in seen:
                seen.add(d)
                unique.append(d)
        return unique

    def _count_csv_data_rows(self, filepath: Path) -> Optional[int]:
        """计算 CSV 数据行数（排除表头），使用 csv 模块正确处理多行字段"""
        try:
            text, _ = safe_read_file(str(filepath))
            if not text:
                return None
            import io
            reader = csv.reader(io.StringIO(text))
            row_count = sum(1 for _ in reader) - 1  # 减去表头
            return max(0, row_count)
        except Exception:
            return None

    def _read_csv_records(self, filepath: Path) -> List[Dict]:
        """读取 CSV 为字典列表"""
        try:
            text, _ = safe_read_file(str(filepath))
            if not text:
                return []
            reader = csv.DictReader(text.strip().split('\n'))
            return list(reader)
        except Exception:
            return []

    def _find_col(self, record: Dict, candidates: List[str]) -> Optional[str]:
        """在记录的键中找匹配的列名"""
        if not record:
            return None
        keys = list(record.keys())
        for c in candidates:
            for k in keys:
                if k.strip().lower() == c.lower():
                    return k
        return None

    def _extract_report_numbers(self, patterns: List[str]) -> List[str]:
        """从报告文本中按模式提取数字"""
        results = []
        for pat in patterns:
            for m in re.finditer(pat, self.report_text):
                results.append(m.group(1))
        return results

    def _extract_gene_from_filename(self, filename: str) -> Optional[str]:
        """从文件名中提取基因名"""
        m = re.search(r'[_\-]([A-Z][A-Z0-9]+(?:[A-Za-z0-9]*)?)(?:[_\-\.]|$)', filename)
        return m.group(1) if m else None

    def _cell_match(self, csv_cell: str, report_cell: str) -> bool:
        """模糊匹配细胞类型名称"""
        a = csv_cell.lower().replace(' ', '').replace('_', '')
        b = report_cell.lower().replace(' ', '').replace('_', '')
        return a == b or a in b or b in a

    def _check_count_in_context(self, csv_file: Path, csv_rows: int, label: str, pattern: str):
        """在报告的同一段落内查找数量匹配"""
        for line in self.report_text.split('\n'):
            for m in re.finditer(pattern, line, re.IGNORECASE):
                # 取第一个非None组
                num_str = next((g for g in m.groups() if g is not None), None)
                if num_str is None:
                    continue
                try:
                    report_num = int(num_str.replace(',', ''))
                except ValueError:
                    continue
                if report_num == csv_rows:
                    return  # 匹配，无需报告
                if abs(report_num - csv_rows) > 1 and report_num < 100:
                    self.warnings.append({
                        'severity': 'WARNING',
                        'category': '基因列表数量不匹配',
                        'message': f'{csv_file.name} 含 {csv_rows} 条记录，但报告中 {label} 相关数量为 {report_num}',
                        'file': str(csv_file.relative_to(self.project_path)),
                        'evidence': {'csv_rows': csv_rows, 'report_count': report_num, 'context': label},
                    })
                    return


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        checker = ReportDataMatchChecker(sys.argv[1])
        result = checker.check_all()
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
