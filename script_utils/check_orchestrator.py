#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一检查调度器（审核框架 v6.5核心）

协调所有检查器，按优先级自动执行并汇总全部问题：
- P0级检查（最高优先级）
- P1级检查（严重问题）
- 其他检查

作者: 审核框架 v6.5
创建日期: 2026-02-13
"""

from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import json
import importlib
import inspect
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from project_metadata import ProjectMetadata


# 导入各个检查器。逐个导入，避免单个依赖缺失导致整组检查器失效。
ProjectIDChecker = None
TermConsistencyChecker = None
DataFlowValidator = None
SpeciesChecker = None
EvidenceCompletenessChecker = None
ClinicalStatisticsChecker = None
GeneNamingChecker = None
VisualizationThresholdChecker = None
GeneSetQualityProjectChecker = None
FigureIntegrityChecker = None
ScRNAQCChecker = None
ReportCoverageChecker = None
ReportDataMatchChecker = None
MLAnomalyChecker = None
CodeExistenceChecker = None
FigureDataMatchChecker = None
NumberCrossrefChecker = None
ThresholdConsistencyChecker = None
ModelConsistencyChecker = None
ChineseProofreadingChecker = None
ImageSimilarityChecker = None

CHECKER_IMPORT_SPECS = [
    ('check_project_id_consistency', 'ProjectIDChecker', '项目编号检查器'),
    ('check_term_consistency', 'TermConsistencyChecker', '术语检查器'),
    ('check_data_flow', 'DataFlowValidator', '数据流检查器'),
    ('check_evidence_completeness', 'EvidenceCompletenessChecker', '证据完整性检查器'),
    ('check_clinical_statistics', 'ClinicalStatisticsChecker', '临床统计检查器'),
    ('check_species_match', 'SpeciesChecker', '物种匹配检查器'),
    ('check_gene_naming', 'GeneNamingChecker', '基因命名检查器'),
    ('check_visualization_thresholds', 'VisualizationThresholdChecker', '可视化阈值检查器'),
    ('check_gene_set_quality', 'GeneSetQualityProjectChecker', '基因集质量检查器'),
    ('check_figure_integrity', 'FigureIntegrityChecker', '图件完整性检查器'),
    ('check_scrna_qc', 'ScRNAQCChecker', 'scRNA QC检查器'),
    ('check_report_coverage', 'ReportCoverageChecker', '报告覆盖矩阵检查器'),
    ('check_report_data_match', 'ReportDataMatchChecker', '报告-数据交叉验证检查器'),
    ('check_ml_anomaly', 'MLAnomalyChecker', 'ML异常检测器'),
    ('check_code_existence', 'CodeExistenceChecker', '代码存在性检查器'),
    ('check_figure_data_match', 'FigureDataMatchChecker', '图件-数据匹配检查器'),
    ('check_number_crossref', 'NumberCrossrefChecker', '数字交叉验证检查器'),
    ('check_threshold_consistency', 'ThresholdConsistencyChecker', '阈值一致性检查器'),
    ('check_model_consistency', 'ModelConsistencyChecker', '模型一致性检查器'),
    ('check_chinese_proofreading', 'ChineseProofreadingChecker', '中文校对检查器'),
    ('check_image_similarity', 'ImageSimilarityChecker', '图像相似度检查器'),
]


def _safe_import_checker(module_name: str, class_name: str, display_name: str):
    try:
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
    except Exception as e:
        print(f"警告: 无法导入{display_name}: {e}")
        return None


_imported = {
    cls_name: _safe_import_checker(mod_name, cls_name, display_name)
    for mod_name, cls_name, display_name in CHECKER_IMPORT_SPECS
}

ProjectIDChecker = _imported['ProjectIDChecker']
TermConsistencyChecker = _imported['TermConsistencyChecker']
DataFlowValidator = _imported['DataFlowValidator']
SpeciesChecker = _imported['SpeciesChecker']
EvidenceCompletenessChecker = _imported['EvidenceCompletenessChecker']
ClinicalStatisticsChecker = _imported['ClinicalStatisticsChecker']
GeneNamingChecker = _imported['GeneNamingChecker']
VisualizationThresholdChecker = _imported['VisualizationThresholdChecker']
GeneSetQualityProjectChecker = _imported['GeneSetQualityProjectChecker']
FigureIntegrityChecker = _imported['FigureIntegrityChecker']
ScRNAQCChecker = _imported['ScRNAQCChecker']
ReportCoverageChecker = _imported['ReportCoverageChecker']
ReportDataMatchChecker = _imported['ReportDataMatchChecker']
MLAnomalyChecker = _imported['MLAnomalyChecker']
CodeExistenceChecker = _imported['CodeExistenceChecker']
FigureDataMatchChecker = _imported['FigureDataMatchChecker']
NumberCrossrefChecker = _imported['NumberCrossrefChecker']
ThresholdConsistencyChecker = _imported['ThresholdConsistencyChecker']
ModelConsistencyChecker = _imported['ModelConsistencyChecker']
ChineseProofreadingChecker = _imported['ChineseProofreadingChecker']
ImageSimilarityChecker = _imported['ImageSimilarityChecker']


class CheckOrchestrator:
    """统一检查调度器 - 按优先级协调所有检查"""

    # ── 检查器注册表 ──
    # 每条记录: name, cls, method, fail_key, count_key, 以及可选标志
    # 新增检查器只需在此追加一行即可
    P0_CHECKERS = [
        {'name': '项目编号一致性检查',   'cls': ProjectIDChecker,
         'method': 'check_all',          'fail_key': 'fatal', 'count_key': 'issues'},
        {'name': '术语主题一致性检查',   'cls': TermConsistencyChecker,
         'method': 'check_all',          'fail_key': 'fatal', 'count_key': 'issues',
         'needs_project_type': True},
        {'name': '跨模块数据流验证',     'cls': DataFlowValidator,
         'method': 'check_all',          'fail_key': 'fatal', 'count_key': 'issues'},
        {'name': '物种匹配检查',         'cls': SpeciesChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues'},
    ]

    P1_CHECKERS = [
        {'name': '证据完整性与参数完备性检查', 'cls': EvidenceCompletenessChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues'},
        {'name': '临床统计项目检查',     'cls': ClinicalStatisticsChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues',
         'silent_if_empty': True},
        {'name': '基因命名一致性检查',   'cls': GeneNamingChecker,
         'method': 'check_all',            'fail_key': 'issues', 'count_key': 'issues'},
        {'name': '可视化阈值一致性检查', 'cls': VisualizationThresholdChecker,
         'method': 'check_all',          'fail_key': 'issues', 'count_key': 'issues'},
        {'name': '图件完整性检查',       'cls': FigureIntegrityChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues'},
        {'name': '基因集质量检查',       'cls': GeneSetQualityProjectChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues',
         'silent_if_empty': True},
        {'name': 'scRNA QC单调性检查',  'cls': ScRNAQCChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues',
         'silent_if_empty': True},
        {'name': '报告覆盖矩阵检查',   'cls': ReportCoverageChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues',
         'silent_if_empty': True},
        {'name': '报告-数据交叉验证',   'cls': ReportDataMatchChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues',
         'silent_if_empty': True},
        {'name': 'ML异常检测',          'cls': MLAnomalyChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues',
         'silent_if_empty': True},
        {'name': '代码存在性检查',           'cls': CodeExistenceChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues',
         'silent_if_empty': True},
        {'name': '图件-数据匹配检查',   'cls': FigureDataMatchChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues',
         'silent_if_empty': True},
        {'name': '数字交叉验证',         'cls': NumberCrossrefChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues',
         'silent_if_empty': True},
        {'name': '方法-代码阈值一致性', 'cls': ThresholdConsistencyChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues',
         'silent_if_empty': True},
        {'name': '模型口径一致性检查',   'cls': ModelConsistencyChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues',
         'silent_if_empty': True},
        {'name': '中文术语校对',         'cls': ChineseProofreadingChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues',
         'silent_if_empty': True},
        {'name': '图像相似度检测',       'cls': ImageSimilarityChecker,
         'method': 'check_all',         'fail_key': 'issues', 'count_key': 'issues',
         'silent_if_empty': True},
    ]

    # 检查优先级定义
    PRIORITY_LEVELS = {
        'P0': 'FATAL',      # 最高优先级问题
        'P1': 'CRITICAL',    # 严重但可继续
        'P2': 'WARNING',      # 警告
        'P3': 'INFO'          # 信息
    }

    def __init__(self, project_path: str, project_type: str = None, parallel_p1: bool = True, max_workers: int = 4, review_dir: str = None):
        """
        初始化调度器

        参数:
            project_path: 项目根目录路径
            project_type: 项目疾病类型（用于术语检查）
            review_dir: 审核输出目录（含 Layer 0 JSON），如不提供则不注入 Layer 0 数据
        """
        self.project_path = Path(project_path).resolve()
        self.project_type = project_type
        self.parallel_p1 = parallel_p1
        self.max_workers = max_workers
        self.review_dir = Path(review_dir).resolve() if review_dir else None
        self.results = {
            'P0': [],  # FATAL级检查结果
            'P1': [],  # CRITICAL级检查结果
            'P2': [],  # WARNING级检查结果
            'P3': []   # INFO级检查结果
        }
        self._result_lock = threading.Lock()
        self.check_start_time = datetime.now()
        self.fatal_triggered = False
        self.metadata = ProjectMetadata(self.project_path)
        # 加载 Layer 0 预解析数据
        self._layer0_data = self._load_layer0_data()
        # 缓存报告文本（避免多个 checker 重复解析 docx）
        self._report_text = self._load_report_text()

    def _load_layer0_data(self) -> dict:
        """加载 Layer 0 预解析 JSON（report_structure + project_structure），供检查器使用。"""
        data = {}
        if not self.review_dir:
            return data
        for key, filename in [('report_structure', 'report_structure.json'),
                              ('project_structure', 'project_structure.json')]:
            path = self.review_dir / filename
            if path.exists():
                try:
                    data[key] = json.loads(path.read_text(encoding='utf-8'))
                    print(f"  ✅ Layer 0 数据已加载: {filename}")
                except Exception as e:
                    print(f"  ⚠️ Layer 0 {filename} 加载失败: {e}")
        return data

    def _load_report_text(self) -> str | None:
        """缓存加载报告文本，避免多个 checker 重复解析 docx。"""
        from utils import find_report_text
        return find_report_text(self.project_path)

    def run_all_checks(self, stop_on_fatal: bool = True) -> Dict:
        """
        按优先级执行所有检查

        参数:
            stop_on_fatal: 兼容旧参数，当前默认不中断并继续汇总全部问题

        返回:
            {
                'total_checks': 总检查数,
                'failed_checks': 失败检查数,
                'fatal_triggered': 是否触发FATAL,
                'results': 各级别结果,
                'summary': 汇总信息
            }
        """
        print(f"\n{'='*60}")
        print(f"开始自动化检查流程")
        print(f"项目路径: {self.project_path}")
        print(f"项目类型: {self.project_type or '自动检测'}")
        print(f"P1并行执行: {'开启' if self.parallel_p1 else '关闭'} (max_workers={self.max_workers})")
        print(f"开始时间: {self.check_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        # ===== 结构预验证 =====
        result_dir = self.project_path / '结果文件'
        has_results = result_dir.is_dir() and any(result_dir.iterdir())
        # 兼容 result/ 等英文目录名
        if not has_results:
            for alt_name in ('result', 'Result', '结果'):
                alt_dir = self.project_path / alt_name
                if alt_dir.is_dir() and any(alt_dir.iterdir()):
                    has_results = True
                    break
        # 兼容无 结果文件/ 的项目：检查是否有编号模块 (00_xxx, 01_xxx ...)
        if not has_results:
            has_numbered_modules = self.metadata.has_numbered_modules()
            if has_numbered_modules:
                has_results = True
                print("ℹ️ 未找到 '结果文件/' 但检测到编号模块目录，将正常执行P1检查")
        if not has_results:
            print("⚠️ 未找到 '结果文件/' 目录或目录为空，部分P1检查将自动跳过")
            self._skip_p1_if_empty = True
        else:
            self._skip_p1_if_empty = False

        # ===== P0级检查（最高优先级） =====
        print("🔴 [P0/FATAL] 开始最高优先级预检查...")
        if stop_on_fatal:
            print("  ℹ️ 已请求stop_on_fatal，但当前框架采用全量审核模式，不会提前停止")

        p0_fatal = False
        p0_unavailable = []
        for i, spec in enumerate(self.P0_CHECKERS, 1):
            if spec['cls'] is None:
                p0_unavailable.append(spec['name'])
            if self._run_checker(spec, 'P0', i, len(self.P0_CHECKERS)):
                p0_fatal = True
        print(f"  └─ P0检查完成")

        # P0 检查器不可用时：记录 FATAL 级错误，确保不会无声跳过
        if p0_unavailable:
            for name in p0_unavailable:
                self.results['P0'].append({
                    'name': name, 'priority': 'P0',
                    'result': {'fatal': True, 'issues': [{
                        'severity': 'FATAL',
                        'message': f'P0检查器 {name} 导入失败，无法执行该关键检查。请检查依赖是否安装完整。'
                    }]},
                    'status': 'FAIL'
                })
            p0_fatal = True
            print(f"\n  ⚠️ {len(p0_unavailable)} 个P0检查器不可用: {', '.join(p0_unavailable)}")
            print("  ⚠️ 这些关键检查被跳过，结果可能不完整！")

        if p0_fatal:
            self.fatal_triggered = True
            print("\n" + "!"*60)
            print("🔴 已发现FATAL级问题：继续执行后续检查以汇总全部问题")
            print("建议：逐项证据复核时优先处理这些问题，但不要中断当前审查流程")
            print("!"*60 + "\n")

        # ===== P1级检查（CRITICAL） =====
        print("\n🟡 [P1/CRITICAL] 开始CRITICAL级检查...")
        if getattr(self, '_skip_p1_if_empty', False):
            print("  ⊘ 项目结构不完整，跳过P1检查")
            self.results['P1'].append({
                'name': '结构预验证', 'priority': 'P1',
                'result': {'skipped': True, 'reason': '结果文件目录缺失或为空'},
                'status': 'SKIP'
            })
        else:
            if self.parallel_p1 and len(self.P1_CHECKERS) > 1:
                # 并行执行，每个 checker 的输出缓冲到列表，最后按顺序打印
                buffers = {}  # idx -> list[str]
                def _run_buffered(spec, idx, total):
                    buf = []
                    try:
                        self._run_checker(spec, 'P1', idx, total, _print_buffer=buf)
                    except Exception as e:
                        name = spec['name']
                        buf.append(f"  ├─ 检查{idx}: {name}...")
                        buf.append(f"  │  ⚠️ 并行执行异常: {e}")
                        self._append_result('P1', {
                            'name': name, 'priority': 'P1',
                            'error': f'并行执行异常: {e}', 'status': 'ERROR'
                        })
                    buffers[idx] = buf

                with ThreadPoolExecutor(max_workers=max(1, self.max_workers)) as executor:
                    futures = [
                        executor.submit(_run_buffered, spec, i, len(self.P1_CHECKERS))
                        for i, spec in enumerate(self.P1_CHECKERS, 1)
                    ]
                    for f in futures:
                        f.result()
                # 按注册顺序输出
                for idx in sorted(buffers):
                    for line in buffers[idx]:
                        print(line)
            else:
                for i, spec in enumerate(self.P1_CHECKERS, 1):
                    self._run_checker(spec, 'P1', i, len(self.P1_CHECKERS))

        # 基因集质量检查已统一纳入 P1_CHECKERS 注册表（GeneSetQualityProjectChecker）

        print("  └─ P1检查完成")

        # ===== 跨 checker 融合信号检测 (#4) =====
        convergence_signals = self._detect_convergence_signals()
        if convergence_signals:
            self.convergence_signals = convergence_signals
            print(f"\n🔗 [融合信号] 检测到 {len(convergence_signals)} 个跨检查器关联：")
            for sig in convergence_signals:
                conf_icon = '🔴' if sig['confidence'] == 'HIGH' else '🟡'
                print(f"  {conf_icon} {sig['target']} — {sig['checker_count']}个检查器独立标记 ({', '.join(sig['checkers'])})")
        else:
            self.convergence_signals = []

        # ===== P2/P3级检查 =====
        print("\n🟢 [P2-P3] 开始其他检查...")
        print("  └─ 其他检查完成（待实现）")

        # 生成汇总
        return self._generate_summary()

    # ── 通用检查器执行器 ──

    def _append_result(self, priority: str, item: dict):
        """线程安全地追加检查结果。"""
        with self._result_lock:
            self.results[priority].append(item)

    def _run_checker(self, spec: Dict, priority: str, idx: int, total: int,
                     _print_buffer: list | None = None) -> bool:
        """执行单个检查器。返回 True 表示发现 FAIL/FATAL。
        
        _print_buffer: 如非 None，print 内容追加到此列表而非直接输出（用于并行模式）。
        """
        _p = (lambda msg: _print_buffer.append(msg)) if _print_buffer is not None else print
        name = spec['name']
        cls = spec['cls']

        _p(f"  ├─ 检查{idx}: {name}...")

        # 需要项目类型但未提供 → 跳过
        if spec.get('needs_project_type') and not self.project_type:
            _p("  │  ⊘ 跳过（未指定项目类型）")
            return False

        # 检查器不可用
        if cls is None:
            self._append_result(priority, {
                'name': name, 'priority': priority,
                'error': f'{name}不可用', 'status': 'ERROR'
            })
            _p("  │  ⚠️ 检查器不可用")
            return False

        try:
            init_sig = inspect.signature(cls.__init__)
            kwargs = {}
            if 'metadata' in init_sig.parameters:
                kwargs['metadata'] = self.metadata
            if 'layer0_data' in init_sig.parameters:
                kwargs['layer0_data'] = self._layer0_data

            # 初始化（术语检查器需要 project_type）
            if spec.get('needs_project_type'):
                checker = cls(str(self.project_path), self.project_type, **kwargs)
            else:
                checker = cls(str(self.project_path), **kwargs)

            # 注入缓存的报告文本（避免每个 checker 重复解析 docx）
            if hasattr(checker, '_cached_report_text') and self._report_text is not None:
                checker._cached_report_text = self._report_text

            # 执行
            result = getattr(checker, spec['method'])()

            if not isinstance(result, dict):
                _p(f"  │  ⚠️ 检查器返回格式错误（期望 dict，得到 {type(result).__name__}）")
                self._append_result(priority, {
                    'name': name, 'priority': priority,
                    'error': f'返回值类型错误: {type(result).__name__}',
                    'status': 'ERROR'
                })
                return False

            # ── 输出标准化（#7）：统一 6 个必接字段 ──
            result = self._normalize_result(result)

            # 判断 FAIL
            fail_value = result.get(spec['fail_key']) or []
            is_fail = bool(fail_value)
            # 优先使用 count_key 获取准确计数；仅当 count_key 缺失时回退到 fail_value
            count_key = spec.get('count_key', spec['fail_key'])
            count_value = result.get(count_key)
            if count_value is None:
                count_value = fail_value
            count = len(count_value) if isinstance(count_value, (list, dict)) else (1 if count_value else 0)

            # 静默跳过：无发现的可选检查器（如临床统计对非临床项目）
            if spec.get('silent_if_empty') and not is_fail:
                if not result.get('warnings'):
                    status = 'SKIP' if result.get('skipped') else 'PASS'
                    self._append_result(priority, {
                        'name': name, 'priority': priority,
                        'result': result, 'status': status
                    })
                    if result.get('skipped'):
                        _p("  │  ⊘ 未检测到相关模块")
                    else:
                        _p("  │  ✅ 通过")
                    return False

            self._append_result(priority, {
                'name': name, 'priority': priority,
                'result': result, 'status': 'FAIL' if is_fail else 'PASS'
            })

            if is_fail:
                label = 'FATAL' if priority == 'P0' else '⚠️'
                _p(f"  │  ❌ {label}: 发现{count}处问题")
                return True
            else:
                _p(f"  │  ✅ 通过")
                return False

        except Exception as e:
            _p(f"  │  ⚠️ 检查失败: {e}")
            self._append_result(priority, {
                'name': name, 'priority': priority,
                'error': str(e), 'status': 'ERROR'
            })
            return False

    # ── 输出标准化 (#7) ──

    @staticmethod
    def _normalize_result(result: dict) -> dict:
        """将各 checker 的原始输出统一为标准 6 字段结构。

        标准字段：issues, warnings, total_checks, failed_checks, skipped, degraded
        原始输出保留在 _raw 中以便调试。
        """
        raw = dict(result)  # 浅拷贝保留原始
        issues = result.get('issues', [])
        if not isinstance(issues, list):
            issues = []
        warnings = result.get('warnings', [])
        if not isinstance(warnings, list):
            warnings = []
        total = result.get('total_checks', 1)
        failed = result.get('failed_checks', len(issues))
        skipped = bool(result.get('skipped', False))
        degraded = bool(result.get('degraded', False))

        result['issues'] = issues
        result['warnings'] = warnings
        result['total_checks'] = total
        result['failed_checks'] = failed
        result['skipped'] = skipped
        result['degraded'] = degraded
        result['_raw'] = raw
        return result

    # ── 跨 checker 融合信号检测 (#4) ──

    def _detect_convergence_signals(self) -> List[dict]:
        """扫描 P0+P1 所有 issues，检测同一模块/文件被多个 checker 独立标记的情况。

        注意：当前仅扫描 P0 和 P1 级别。P2/P3 级别尚未实现检查器，
        若未来启用需在下方 prio 循环中增加对应级别。

        返回融合信号列表，每条包含：
        - target: 被关联的模块名或文件名
        - target_type: 'module' | 'file'
        - checkers: 独立标记该目标的 checker 名称列表
        - confidence: 'HIGH' (≥3) | 'MEDIUM' (2)
        - severity_boost: 建议升级的严重度
        """
        # 收集所有 issue 中可提取的模块名/文件名
        target_checker_map: Dict[str, set] = {}  # target -> set of checker names

        for prio in ('P0', 'P1'):
            for entry in self.results.get(prio, []):
                checker_name = entry.get('name', '')
                result = entry.get('result', {})
                if not isinstance(result, dict):
                    continue
                issues = result.get('issues', [])
                if not isinstance(issues, list):
                    continue
                for issue in issues:
                    if not isinstance(issue, dict):
                        continue
                    targets = self._extract_targets_from_issue(issue)
                    for t in targets:
                        if t not in target_checker_map:
                            target_checker_map[t] = set()
                        target_checker_map[t].add(checker_name)

        signals = []
        for target, checkers in target_checker_map.items():
            if len(checkers) < 2:
                continue
            checker_list = sorted(checkers)
            confidence = 'HIGH' if len(checkers) >= 3 else 'MEDIUM'
            signals.append({
                'target': target,
                'target_type': 'module' if '/' not in target and '\\' not in target and '.' not in target else 'file',
                'checkers': checker_list,
                'checker_count': len(checker_list),
                'confidence': confidence,
                'severity_boost': 'CRITICAL' if confidence == 'HIGH' else 'MAJOR',
            })

        # 按 checker_count 降序
        signals.sort(key=lambda s: s['checker_count'], reverse=True)
        return signals

    @staticmethod
    def _extract_targets_from_issue(issue: dict) -> List[str]:
        """从单条 issue 中提取可用于关联的模块名或文件名。"""
        targets = []
        evidence = issue.get('evidence', {})
        if isinstance(evidence, dict):
            # 模块名
            for key in ('module', 'module_name', 'module_dir'):
                val = evidence.get(key)
                if val and isinstance(val, str):
                    # 标准化模块名：去掉编号前缀 00_, 01_ 等
                    clean = re.sub(r'^\d+[_\-]', '', val)
                    targets.append(clean)
            # 文件名
            for key in ('file', 'filename', 'csv_file', 'script'):
                val = evidence.get(key)
                if val and isinstance(val, str):
                    targets.append(val)

        # 直接在 issue 级别的 file/module
        for key in ('file', 'module'):
            val = issue.get(key)
            if val and isinstance(val, str):
                clean = re.sub(r'^\d+[_\-]', '', val) if key == 'module' else val
                targets.append(clean)

        return targets

    def _generate_summary(self) -> Dict:
        """生成检查汇总"""
        check_end_time = datetime.now()
        duration = (check_end_time - self.check_start_time).total_seconds()

        # 统计各级别结果
        summary = {
            'project_path': str(self.project_path),
            'project_type': self.project_type,
            'start_time': self.check_start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': check_end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'duration_seconds': duration,
            'fatal_triggered': self.fatal_triggered,
            'total_checks': sum(len(results) for results in self.results.values()),
            'by_priority': {}
        }

        for priority, results in self.results.items():
            passed = sum(1 for r in results if r.get('status') == 'PASS')
            failed = sum(1 for r in results if r.get('status') == 'FAIL')
            errors = sum(1 for r in results if r.get('status') == 'ERROR')

            summary['by_priority'][priority] = {
                'total': len(results),
                'passed': passed,
                'failed': failed,
                'errors': errors
            }

        has_p0_failures = summary['by_priority']['P0']['failed'] > 0 or summary['by_priority']['P0']['errors'] > 0
        has_p1_failures = summary['by_priority']['P1']['failed'] > 0 or summary['by_priority']['P1']['errors'] > 0

        # 总体状态
        if self.fatal_triggered:
            summary['overall_status'] = 'REVIEW_REQUIRED'
            summary['overall_color'] = 'red'
            summary['can_proceed'] = True
        elif has_p0_failures or has_p1_failures:
            summary['overall_status'] = 'REVIEW_REQUIRED'
            summary['overall_color'] = 'orange'
            summary['can_proceed'] = True
        else:
            summary['overall_status'] = 'PASSED'
            summary['overall_color'] = 'green'
            summary['can_proceed'] = True

        # 融合信号
        summary['convergence_signals'] = getattr(self, 'convergence_signals', [])

        return summary

    def generate_report(self, output_format: str = 'markdown') -> str:
        """
        生成检查报告

        参数:
            output_format: 输出格式 ('markdown' 或 'json')

        返回:
            报告内容字符串
        """
        summary = self._generate_summary()

        if output_format == 'json':
            return json.dumps({
                'summary': summary,
                'results': self.results
            }, ensure_ascii=False, indent=2)

        # Markdown格式报告
        report_lines = [
            "# 自动化检查报告",
            "",
            f"**项目路径**: {summary['project_path']}",
            f"**项目类型**: {summary['project_type'] or '未指定'}",
            f"**检查时间**: {summary['start_time']} - {summary['end_time']}",
            f"**耗时**: {summary['duration_seconds']:.1f}秒",
            "",
            "## 总体状态",
            "",
        ]

        status_icons = {
            'PASSED': '✅',
            'FAILED': '❌',
            'FATAL': '🔴',
            'REVIEW_REQUIRED': '⚠️'
        }
        icon = status_icons.get(summary['overall_status'], '❓')

        report_lines.extend([
            f"{icon} **状态**: {summary['overall_status']}",
            "",
            f"**是否可以继续逐项证据复核**: {'是' if summary['can_proceed'] else '否'}",
            ""
        ])

        # 各级别检查结果
        report_lines.extend([
            "## 检查结果详情",
            ""
        ])

        for priority in ['P0', 'P1', 'P2', 'P3']:
            if not self.results[priority]:
                continue

            priority_name = self.PRIORITY_LEVELS.get(priority, priority)
            report_lines.extend([
                f"### {priority}级 - {priority_name}",
                ""
            ])

            for check in self.results[priority]:
                name = check['name']
                status = check.get('status', 'UNKNOWN')
                status_icon = {'PASS': '✅', 'FAIL': '❌', 'SKIP': '⊘', 'ERROR': '⚠️'}.get(status, '❓')

                report_lines.extend([
                    f"#### {name}",
                    f"- **状态**: {status_icon} {status}",
                ])

                if 'error' in check:
                    report_lines.append(f"- **错误**: {check['error']}")
                elif 'result' in check:
                    result = check['result']

                    # (#3) degraded / skipped 标记
                    if result.get('degraded'):
                        report_lines.append("- **模式**: ⚡ 降级运行（无报告文本）")
                    if result.get('skipped'):
                        reason = result.get('reason', '')
                        report_lines.append(f"- **跳过原因**: {reason}" if reason else "- **已跳过**")

                    # fatal 标记
                    if result.get('fatal'):
                        report_lines.append("- **FATAL**: ❌ 是")

                    # (#2) 通用统计：使用标准化字段
                    total = result.get('total_checks', 0)
                    failed = result.get('failed_checks', 0)
                    if total:
                        report_lines.append(f"- **检查项**: {failed}/{total} 项失败")

                    # 通用 issues 渲染
                    issues = result.get('issues', [])
                    if issues and isinstance(issues, list):
                        report_lines.append(f"- **问题数**: {len(issues)}")
                        for issue in issues[:10]:
                            if isinstance(issue, dict):
                                msg = issue.get('message', issue.get('description', str(issue)))
                                sev = issue.get('severity', '')
                                sev_prefix = f"[{sev}] " if sev else ''
                                report_lines.append(f"  - {sev_prefix}{msg}")
                            else:
                                report_lines.append(f"  - {issue}")
                        if len(issues) > 10:
                            report_lines.append(f"  - ... 及其余 {len(issues) - 10} 条")

                    # 通用 warnings 渲染
                    warnings = result.get('warnings', [])
                    if warnings and isinstance(warnings, list):
                        report_lines.append(f"- **警告数**: {len(warnings)}")
                        for w in warnings[:5]:
                            if isinstance(w, dict):
                                msg = w.get('message', str(w))
                                report_lines.append(f"  - {msg}")
                            else:
                                report_lines.append(f"  - {w}")
                        if len(warnings) > 5:
                            report_lines.append(f"  - ... 及其余 {len(warnings) - 5} 条")

                    # 兼容非标准键（errors / mismatches 等旧格式）
                    for alt_key in ('errors', 'mismatches', 'species_mismatches'):
                        alt_items = result.get(alt_key, [])
                        if alt_items and isinstance(alt_items, list):
                            report_lines.append(f"- **{alt_key}**: {len(alt_items)} 条")
                            for item in alt_items[:5]:
                                if isinstance(item, dict):
                                    msg = item.get('message', item.get('description', item.get('term', str(item))))
                                    report_lines.append(f"  - {msg}")
                            if len(alt_items) > 5:
                                report_lines.append(f"  - ... 及其余 {len(alt_items) - 5} 条")

                report_lines.append("")

        # (#1) 跨检查器融合信号
        convergence_signals = getattr(self, 'convergence_signals', [])
        if convergence_signals:
            report_lines.extend([
                "## 🔗 跨检查器融合信号",
                "",
                f"共检测到 {len(convergence_signals)} 个跨检查器关联目标：",
                "",
                "| 目标 | 类型 | 关联检查器数 | 置信度 | 检查器 |",
                "|------|------|-------------|--------|--------|",
            ])
            for sig in convergence_signals:
                conf_icon = '🔴' if sig['confidence'] == 'HIGH' else '🟡'
                report_lines.append(
                    f"| {sig['target']} | {sig['target_type']} | {sig['checker_count']} "
                    f"| {conf_icon} {sig['confidence']} | {', '.join(sig['checkers'])} |"
                )
            report_lines.append("")

        # 建议部分
        if summary['fatal_triggered']:
            report_lines.extend([
                "## 🔴 FATAL级问题提醒",
                "",
                "发现FATAL级问题，但本轮自动检查已继续完成，建议：",
                "1. 在逐项证据复核中优先核对所有FATAL级问题",
                "2. 将FATAL问题放入最终审核报告顶部",
                "3. 如修正后需要，可重新运行自动化检查进行回归比对",
                ""
            ])

        return "\n".join(report_lines)

    def save_report(self, output_path: str, output_format: str = 'markdown'):
        """保存报告到文件"""
        report = self.generate_report(output_format)
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"\n报告已保存到: {output_file}")


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description='统一检查调度器 - 审核框架 v6.5',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础检查
  python check_orchestrator.py /path/to/project

  # 指定项目类型
  python check_orchestrator.py /path/to/project --project-type 肾结石

  # 输出到文件
  python check_orchestrator.py /path/to/project --output report.md

  # JSON格式
  python check_orchestrator.py /path/to/project --format json --output result.json
        """
    )

    parser.add_argument('project_path', help='项目根目录路径')
    parser.add_argument('--project-type', help='项目疾病类型（用于术语检查）')
    parser.add_argument('--output', '-o', help='输出报告文件路径')
    parser.add_argument('--format', '-f', choices=['markdown', 'json'],
                      default='markdown', help='输出格式（默认: markdown）')
    parser.add_argument('--continue-on-fatal', action='store_true',
                      help='发现FATAL级问题后继续检查（不推荐）')

    args = parser.parse_args()

    # 创建调度器
    orchestrator = CheckOrchestrator(args.project_path, args.project_type)

    # 执行检查
    summary = orchestrator.run_all_checks(stop_on_fatal=not args.continue_on_fatal)

    # 生成报告
    if args.output:
        orchestrator.save_report(args.output, args.format)
    else:
        print("\n" + "="*60)
        print("检查报告")
        print("="*60)
        print(orchestrator.generate_report(args.format))

    # 返回退出码
    import sys
    sys.exit(0 if summary['can_proceed'] else 1)


if __name__ == '__main__':
    main()
