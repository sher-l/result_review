#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Shared base class for project-level checkers."""

import re
import json
from pathlib import Path
from typing import Optional, List


REPORT_REFERENCE_MARKERS = ('参考文献', 'References')
REPORT_APPENDIX_STOP_MARKERS = ('公司介绍', '服务领域', '联系我们')


def strip_non_audit_appendix(report_text: Optional[str]) -> Optional[str]:
    """Strip default company promo pages that appear after references."""
    if not report_text:
        return report_text

    reference_index = -1
    reference_marker = ''
    for marker in REPORT_REFERENCE_MARKERS:
        idx = report_text.rfind(marker)
        if idx > reference_index:
            reference_index = idx
            reference_marker = marker

    if reference_index == -1:
        return report_text

    search_start = reference_index + len(reference_marker)
    stop_positions = []
    for marker in REPORT_APPENDIX_STOP_MARKERS:
        idx = report_text.find(marker, search_start)
        if idx != -1:
            stop_positions.append(idx)

    if not stop_positions:
        return report_text

    return report_text[:min(stop_positions)].rstrip()


class BaseProjectChecker:
    """Provide shared project initialization and helper methods."""

    def __init__(self, project_path: str, metadata=None, layer0_data: dict = None):
        self.project_path = Path(project_path).resolve()
        self.metadata = metadata
        self.issues = []
        self.warnings = []
        # Layer 0 预解析数据（由 CheckOrchestrator 注入）
        self._layer0_data = layer0_data or {}
        # 报告文本缓存（由 CheckOrchestrator 注入，避免多 checker 重复解析 docx）
        self._cached_report_text: Optional[str] = None

    @property
    def report_structure(self) -> dict:
        """Layer 0: report_structure.json 的解析结果"""
        return self._layer0_data.get('report_structure', {})

    @property
    def project_structure(self) -> dict:
        """Layer 0: project_structure.json 的解析结果"""
        return self._layer0_data.get('project_structure', {})

    def find_code_directory(self) -> Optional[Path]:
        """Locate code directory in a consistent way.
        
        优先 metadata → Layer 0 code_files → 文件系统候选目录。
        """
        if self.metadata is not None:
            return self.metadata.find_code_directory()

        # Layer 0 快速路径：从 project_structure.code_files 推断代码目录
        code_files = self.project_structure.get('code_files', [])
        if code_files:
            from collections import Counter
            parents = Counter()
            for cf in code_files:
                p = Path(cf.get('path', ''))
                if p.parts:
                    parents[p.parts[0]] += 1
            if parents:
                top_dir = parents.most_common(1)[0][0]
                candidate = self.project_path / top_dir
                if candidate.is_dir():
                    return candidate

        candidates = ['CODE', 'code', 'Code', 'scripts', 'Scripts', 'script', 'Script']
        for name in candidates:
            dir_path = self.project_path / name
            if dir_path.is_dir():
                return dir_path
        # fallback: result/ 或 Result/ 下有代码文件
        for subdir_name in ('result', 'Result', '结果文件', '结果'):
            dir_path = self.project_path / subdir_name
            if dir_path.is_dir() and (any(dir_path.glob('*.R')) or any(dir_path.glob('*.py'))):
                return dir_path
        return None

    def load_report_text(self) -> Optional[str]:
        """加载报告文本（优先使用缓存，否则调用 utils.find_report_text）"""
        if self._cached_report_text is not None:
            return strip_non_audit_appendix(self._cached_report_text)
        from utils import find_report_text
        return strip_non_audit_appendix(find_report_text(self.project_path))

    def find_modules(self, pattern: str = r'^\d{2}[_\-]') -> List[Path]:
        """查找编号模块目录。

        优先使用 Layer 0 预解析的模块列表（如可用），否则走文件系统扫描。
        返回去重保序的 Path 列表。
        """
        if self.metadata is not None:
            mods = self.metadata.find_numbered_modules()
            if mods:
                return mods

        # Layer 0 快速路径：project_structure.modules
        ps_modules = self.project_structure.get('modules', [])
        if ps_modules:
            pattern_re = re.compile(pattern)
            result = []
            for mod in ps_modules:
                if not mod.get('is_module'):
                    continue
                mod_path = self.project_path / mod['path']
                if mod_path.is_dir() and pattern_re.match(mod_path.name):
                    result.append(mod_path)
            if result:
                return list(dict.fromkeys(result))

        # 文件系统扫描兜底
        pattern_re = re.compile(pattern)
        result = []
        search_bases = [
            self.project_path / '结果文件',
            self.project_path / 'result',
            self.project_path / 'Result',
            self.project_path / '结果',
            self.project_path,
        ]
        for base in search_bases:
            if not base.is_dir():
                continue
            for d in sorted(base.iterdir()):
                if d.is_dir() and pattern_re.match(d.name):
                    result.append(d)
        # 保序去重
        return list(dict.fromkeys(result))

    def _relative_path(self, path: Path) -> str:
        """将绝对路径转为相对于项目根的路径字符串。"""
        try:
            return str(path.relative_to(self.project_path))
        except ValueError:
            return str(path)
