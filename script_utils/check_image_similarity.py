#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""图像相似度检测器 — 基于感知哈希 (dHash) 检测项目内重复/高度相似的图片。

v6.5 Phase 1: 仅使用 Pillow，无额外重依赖。
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
from itertools import combinations

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from base_project_checker import BaseProjectChecker

# 支持的图片后缀
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif', '.webp'}

# dHash 尺寸（8x9 → 64 bit hash）
HASH_SIZE = 8


def _dhash(image: "Image.Image", hash_size: int = HASH_SIZE) -> int:
    """计算 difference hash (dHash)。

    将图片缩放到 (hash_size+1, hash_size) 灰度，
    逐行比较相邻像素亮度差异生成 hash_size*hash_size bit 指纹。
    """
    resized = image.convert('L').resize((hash_size + 1, hash_size), Image.LANCZOS)
    if hasattr(resized, 'get_flattened_data'):
        pixels = list(resized.get_flattened_data())
    else:
        pixels = list(resized.getdata())
    width = hash_size + 1
    hash_val = 0
    for row in range(hash_size):
        for col in range(hash_size):
            offset = row * width + col
            if pixels[offset] < pixels[offset + 1]:
                hash_val |= 1 << (row * hash_size + col)
    return hash_val


def _hamming_distance(h1: int, h2: int) -> int:
    """两个整数哈希之间的 Hamming 距离。"""
    return bin(h1 ^ h2).count('1')


class ImageSimilarityChecker(BaseProjectChecker):
    """检测项目内重复或高度相似的图片文件。

    使用 dHash（差分感知哈希），对项目结果目录中所有图片
    进行两两比较，找出 Hamming 距离 ≤ 阈值的图片对。

    - 完全相同（距离 = 0）→ CRITICAL（可能为错误复用）
    - 高度相似（距离 ≤ 5）→ WARNING（需 AI确认）
    """

    # 阈值配置
    EXACT_THRESHOLD = 0      # Hamming 距离 = 0 → 完全相同
    SIMILAR_THRESHOLD = 5    # Hamming 距离 ≤ 5 → 高度相似
    MAX_FILES = 500          # 防止超大项目 OOM

    def check_all(self) -> Dict:
        if not _HAS_PIL:
            return {
                'issues': [],
                'warnings': [{'message': '未安装 Pillow，跳过图像相似度检测', 'severity': 'INFO'}],
                'skipped': True,
            }

        image_files = self._collect_image_files()
        if len(image_files) < 2:
            return {
                'issues': [],
                'warnings': [],
                'skipped': True,
            }

        hashes = self._compute_hashes(image_files)
        issues, warnings = self._find_duplicates(hashes)

        return {
            'issues': issues,
            'warnings': warnings,
            'total_checks': len(hashes),
            'failed_checks': len(issues),
        }

    def _collect_image_files(self) -> List[Path]:
        """收集项目目录下所有图片文件（递归）。"""
        result_root = self._find_result_root()
        if not result_root:
            return []

        files = []
        for ext in IMAGE_EXTENSIONS:
            files.extend(result_root.rglob(f'*{ext}'))
        # 过滤太小的文件（图标/占位符）
        files = [f for f in files if f.stat().st_size > 1024]
        # 限制数量
        if len(files) > self.MAX_FILES:
            files = sorted(files, key=lambda f: f.stat().st_size, reverse=True)[:self.MAX_FILES]
        return sorted(files)

    def _find_result_root(self) -> Optional[Path]:
        """定位结果文件根目录。"""
        candidates = ['结果', 'result', 'Result', 'results', 'Results', 'output', 'Output']
        for name in candidates:
            p = self.project_path / name
            if p.is_dir():
                return p
        # 兜底：直接用项目根目录
        return self.project_path

    def _compute_hashes(self, files: List[Path]) -> List[Tuple[Path, int]]:
        """为每张图片计算 dHash。损坏/无法打开的文件静默跳过。"""
        hashes = []
        for f in files:
            try:
                with Image.open(f) as img:
                    h = _dhash(img)
                    hashes.append((f, h))
            except Exception:
                pass
        return hashes

    def _find_duplicates(self, hashes: List[Tuple[Path, int]]) -> Tuple[List[Dict], List[Dict]]:
        """两两比较，找出相似图片对。"""
        issues = []
        warnings = []

        for (path_a, hash_a), (path_b, hash_b) in combinations(hashes, 2):
            dist = _hamming_distance(hash_a, hash_b)

            if dist <= self.EXACT_THRESHOLD:
                rel_a = self._relative_path(path_a)
                rel_b = self._relative_path(path_b)
                issues.append({
                    'type': 'IMAGE_DUPLICATE',
                    'severity': 'CRITICAL',
                    'message': f'图片完全相同（可能错误复用）: {rel_a} ↔ {rel_b}',
                    'details': {
                        'file_a': str(rel_a),
                        'file_b': str(rel_b),
                        'hamming_distance': dist,
                    },
                })
            elif dist <= self.SIMILAR_THRESHOLD:
                rel_a = self._relative_path(path_a)
                rel_b = self._relative_path(path_b)
                warnings.append({
                    'type': 'IMAGE_SIMILAR',
                    'severity': 'WARNING',
                    'message': f'图片高度相似（需 AI确认）: {rel_a} ↔ {rel_b}',
                    'details': {
                        'file_a': str(rel_a),
                        'file_b': str(rel_b),
                        'hamming_distance': dist,
                    },
                })

        return issues, warnings
