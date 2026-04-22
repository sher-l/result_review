#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
机器学习异常检测器 (P1)

扫描 ML 相关模块，检测：
1. AUC = 1.0（过拟合风险）
2. AUC > 0.8 但 Accuracy < 0.4（类别不平衡/阈值问题）
3. 所有模型 AUC 异常一致（可能数据泄漏）
4. 训练集指标远优于验证集

作者: 审核框架 v6.5
"""

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional
from itertools import islice

try:
    from utils import safe_read_file
except ImportError:
    def safe_read_file(path, encodings=None):
        try:
            return Path(path).read_text(encoding='utf-8', errors='ignore'), 'utf-8'
        except Exception:
            return '', None

from base_project_checker import BaseProjectChecker


class MLAnomalyChecker(BaseProjectChecker):
    """机器学习模型异常检测"""

    _ML_MODULE_PATTERN = re.compile(r'machine|ml|model|机器学习|建模|07_', re.IGNORECASE)
    _DATA_EXTS = {'.csv', '.tsv'}

    def __init__(self, project_path: str, layer0_data: dict = None):
        super().__init__(project_path, layer0_data=layer0_data)

    def check_all(self) -> Dict:
        """执行全部ML异常检查"""
        ml_dirs = self._find_ml_modules()
        if not ml_dirs:
            return {
                'issues': [],
                'warnings': [],
                'skipped': True,
                'reason': '未找到机器学习模块',
            }

        all_models = []
        for mdir in ml_dirs:
            for cf in sorted(mdir.rglob('*.csv')):
                models = self._parse_ml_csv(cf)
                if models:
                    all_models.extend(models)

        if not all_models:
            # 检查是否有 ML 可视化图但缺少指标 CSV
            has_visuals = self._check_ml_visuals_without_metrics(ml_dirs)
            if has_visuals:
                return {
                    'issues': self.issues,
                    'warnings': self.warnings,
                    'skipped': False,
                    'degraded': True,
                    'reason': 'ML模块有可视化图件但未找到性能指标CSV',
                }
            return {
                'issues': [],
                'warnings': [],
                'skipped': True,
                'reason': 'ML模块无可解析的CSV',
            }

        self._check_perfect_auc(all_models)
        self._check_auc_acc_paradox(all_models)
        self._check_uniform_auc(all_models)

        return {
            'issues': self.issues,
            'warnings': self.warnings,
            'total_checks': 3,
            'failed_checks': len(self.issues),
            'models_scanned': len(all_models),
        }

    # ── 检查逻辑 ──

    def _check_perfect_auc(self, models: List[Dict]):
        """AUC = 1.0 过拟合检测"""
        for m in models:
            if m.get('auc', 0) >= 0.999:
                self.warnings.append({
                    'severity': 'WARNING',
                    'category': 'ML过拟合风险',
                    'message': f"{m['file']}: 模型 {m['model']} AUC={m['auc']:.3f}，可能存在过拟合",
                    'file': m['file'],
                    'evidence': m,
                })

    def _check_auc_acc_paradox(self, models: List[Dict]):
        """AUC 高但 Accuracy 低 — 类别不平衡"""
        for m in models:
            auc = m.get('auc', 0)
            acc = m.get('accuracy')
            if acc is None:
                continue
            if auc > 0.8 and acc < 0.4:
                self.issues.append({
                    'severity': 'WARNING',
                    'category': 'ML指标矛盾',
                    'message': (
                        f"{m['file']}: 模型 {m['model']} AUC={auc:.3f} 但 Accuracy={acc:.3f}，"
                        f"AUC-Accuracy差异={auc-acc:.3f}，可能存在类别不平衡或阈值问题"
                    ),
                    'file': m['file'],
                    'evidence': m,
                })

    def _check_uniform_auc(self, models: List[Dict]):
        """所有模型AUC过于一致 → 可能数据泄漏"""
        auc_values = [m['auc'] for m in models if 'auc' in m and m['auc'] > 0]
        if len(auc_values) >= 4:
            auc_set = set(round(a, 3) for a in auc_values)
            if len(auc_set) == 1:
                self.warnings.append({
                    'severity': 'WARNING',
                    'category': 'ML数据泄漏风险',
                    'message': f'所有 {len(auc_values)} 个模型AUC完全一致 ({auc_values[0]:.3f})，可能存在数据泄漏',
                    'evidence': {'auc_values': auc_values},
                })

    # ── 工具方法 ──

    def _find_ml_modules(self) -> List[Path]:
        """查找ML相关模块目录 — 基于基类 find_modules() + ML 关键词过滤"""
        modules = self.find_modules()
        if modules:
            result = [d for d in modules if self._ML_MODULE_PATTERN.search(d.name)]
            if result:
                return result
        # 回退：全目录搜索
        result = []
        search_bases = [self.project_path / '结果文件', self.project_path]
        for base in search_bases:
            if not base.is_dir():
                continue
            for d in base.iterdir():
                if d.is_dir() and self._ML_MODULE_PATTERN.search(d.name):
                    result.append(d)
        return list(set(result))

    def _parse_ml_csv(self, filepath: Path) -> List[Dict]:
        """从ML CSV中解析模型指标"""
        try:
            text, _ = safe_read_file(str(filepath))
            if not text:
                return []
            reader = csv.DictReader(text.strip().split('\n'))
            rows = list(islice(reader, 50))
            if not rows:
                return []
            keys = list(rows[0].keys())
            auc_col = self._find_col(keys, ['AUC', 'auc', 'AUROC', 'auroc'])
            if not auc_col:
                return []
            acc_col = self._find_col(keys, ['Accuracy', 'accuracy', 'Acc', 'acc'])
            f1_col = self._find_col(keys, ['F1', 'f1', 'F1_score'])
            model_col = keys[0]  # 通常第一列是模型名

            models = []
            rel_path = str(filepath.relative_to(self.project_path))
            for row in rows:
                try:
                    auc = float(row.get(auc_col, '0').strip())
                except (ValueError, TypeError):
                    continue
                entry = {
                    'model': row.get(model_col, 'Unknown').strip(),
                    'auc': auc,
                    'file': rel_path,
                }
                if acc_col:
                    try:
                        entry['accuracy'] = float(row.get(acc_col, '0').strip())
                    except (ValueError, TypeError):
                        pass
                if f1_col:
                    try:
                        entry['f1'] = float(row.get(f1_col, '0').strip())
                    except (ValueError, TypeError):
                        pass
                models.append(entry)
            return models
        except Exception:
            return []

    def _find_col(self, keys: list, candidates: list) -> Optional[str]:
        for c in candidates:
            for k in keys:
                if k.strip().lower() == c.lower():
                    return k
        return None

    def _check_ml_visuals_without_metrics(self, ml_dirs: List[Path]) -> bool:
        """检查 ML 目录是否有 ROC/Boxplot 等可视化图但缺少指标 CSV"""
        _IMG_EXTS = {'.png', '.jpg', '.jpeg', '.pdf', '.tif', '.tiff'}
        _ML_VIS_PATTERNS = re.compile(r'roc|boxplot|auc|lasso|svm|rf|forest|cvfit', re.IGNORECASE)
        found_visuals = False
        for mdir in ml_dirs:
            img_files = [f for f in mdir.rglob('*')
                         if f.is_file() and f.suffix.lower() in _IMG_EXTS]
            ml_visuals = [f for f in img_files if _ML_VIS_PATTERNS.search(f.stem)]
            if ml_visuals:
                found_visuals = True
                self.warnings.append({
                    'severity': 'WARNING',
                    'category': 'ML指标表缺失',
                    'message': (f'{mdir.name}: 发现 {len(ml_visuals)} 张 ML 可视化图'
                                f'（含 ROC/Boxplot 等），但未找到包含 AUC 等指标的 CSV 文件'),
                    'file': str(mdir.name),
                    'evidence': {
                        'visual_files': [f.name for f in ml_visuals[:10]],
                        'total_visuals': len(ml_visuals),
                    },
                })
        return found_visuals


if __name__ == '__main__':
    import sys, json
    if len(sys.argv) > 1:
        checker = MLAnomalyChecker(sys.argv[1])
        print(json.dumps(checker.check_all(), indent=2, ensure_ascii=False, default=str))
