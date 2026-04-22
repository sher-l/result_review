#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Project-level metadata cache to reduce repeated filesystem scans."""

from pathlib import Path
from typing import Dict, List, Optional
import threading


class ProjectMetadata:
    """A lightweight cache wrapper around glob/rglob queries for one project."""

    def __init__(self, project_path: str | Path):
        self.project_path = Path(project_path).resolve()
        self._rglob_cache: Dict[str, List[Path]] = {}
        self._glob_cache: Dict[str, List[Path]] = {}
        self._code_dir: Optional[Path] = None
        self._lock = threading.Lock()

    def rglob(self, pattern: str) -> List[Path]:
        """Cached recursive glob query. Returns a copy to prevent cache pollution."""
        with self._lock:
            if pattern not in self._rglob_cache:
                self._rglob_cache[pattern] = list(self.project_path.rglob(pattern))
            return list(self._rglob_cache[pattern])

    def glob(self, pattern: str) -> List[Path]:
        """Cached top-level glob query. Returns a copy to prevent cache pollution."""
        with self._lock:
            if pattern not in self._glob_cache:
                self._glob_cache[pattern] = list(self.project_path.glob(pattern))
            return list(self._glob_cache[pattern])

    def find_by_patterns(self, patterns: List[str], recursive: bool = True) -> List[Path]:
        """Collect unique files by multiple patterns while preserving order."""
        seen = set()
        out: List[Path] = []
        for pattern in patterns:
            hits = self.rglob(pattern) if recursive else self.glob(pattern)
            for path in hits:
                key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                out.append(path)
        return out

    def find_code_directory(self) -> Optional[Path]:
        """Locate code directory once.

        Searches for dedicated code directories first, then falls back to
        result/ if it contains code files directly.
        """
        with self._lock:
            if self._code_dir is not None:
                return self._code_dir
            # 优先：专用代码目录
            possible_names = ['CODE', 'code', 'Code', 'scripts', 'Scripts', 'script', 'Script']
            for name in possible_names:
                dir_path = self.project_path / name
                if dir_path.exists():
                    self._code_dir = dir_path
                    return self._code_dir
            # 回退：result/ 目录含代码文件时作为代码目录
            for name in ('result', 'Result', '结果文件', '结果'):
                dir_path = self.project_path / name
                if dir_path.is_dir() and (any(dir_path.glob('*.R')) or any(dir_path.glob('*.py'))):
                    self._code_dir = dir_path
                    return self._code_dir
            self._code_dir = None
            return self._code_dir

    def has_numbered_modules(self) -> bool:
        """Check whether project has numbered module folders like 01_xxx.

        Searches project root and common subdirectories (result/, 结果文件/).
        """
        import re

        search_dirs = [self.project_path]
        for subdir_name in ('result', 'Result', '结果文件', '结果'):
            candidate = self.project_path / subdir_name
            if candidate.is_dir():
                search_dirs.append(candidate)

        for search_dir in search_dirs:
            for d in search_dir.iterdir():
                if d.is_dir() and re.match(r'\d{2}_', d.name):
                    return True
        return False

    def find_numbered_modules(self) -> List[Path]:
        """Return numbered module directories (e.g. 01_xxx, 02-yyy).

        Searches project root and common subdirectories, returns deduplicated
        sorted list of Path objects.
        """
        import re

        search_dirs = [self.project_path]
        for subdir_name in ('result', 'Result', '结果文件', '结果'):
            candidate = self.project_path / subdir_name
            if candidate.is_dir():
                search_dirs.append(candidate)

        seen = set()
        result: List[Path] = []
        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue
            for d in sorted(search_dir.iterdir()):
                if d.is_dir() and re.match(r'\d{2}[_\-]', d.name) and d not in seen:
                    seen.add(d)
                    result.append(d)
        return result
