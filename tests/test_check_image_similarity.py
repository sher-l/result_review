#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图像相似度检测器单元测试

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_image_similarity.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_image_similarity import (
    ImageSimilarityChecker,
    _dhash,
    _hamming_distance,
    _HAS_PIL,
    HASH_SIZE,
)

# 跳过整组测试如果 Pillow 不可用
pytestmark = pytest.mark.skipif(not _HAS_PIL, reason="Pillow not installed")

from PIL import Image, ImageDraw


def _make_large_image(path, color='red', extra_shape=True):
    """生成 > 1KB 的测试图片（避免被文件大小过滤器拦截）"""
    img = Image.new('RGB', (400, 400), 'white')
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 380, 380], fill=color)
    draw.ellipse([60, 60, 340, 340], fill='blue')
    draw.line([0, 0, 400, 400], fill='black', width=5)
    if extra_shape:
        draw.polygon([(200, 30), (370, 370), (30, 370)], outline='green')
    img.save(path)
    return img


# ===== dHash 算法测试 =====

class TestDHash:
    """dHash 核心算法"""

    def test_identical_images_zero_distance(self):
        img = Image.new('RGB', (100, 100), 'white')
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 50, 50], fill='red')
        h1 = _dhash(img)
        h2 = _dhash(img.copy())
        assert _hamming_distance(h1, h2) == 0

    def test_different_structure_large_distance(self):
        img1 = Image.new('RGB', (200, 200), 'white')
        d1 = ImageDraw.Draw(img1)
        d1.rectangle([20, 20, 100, 100], fill='red')
        d1.ellipse([110, 110, 190, 190], fill='blue')

        img3 = Image.new('RGB', (200, 200), 'white')
        d3 = ImageDraw.Draw(img3)
        d3.rectangle([50, 80, 180, 180], fill='green')
        d3.line([0, 0, 200, 200], fill='black', width=5)

        h1 = _dhash(img1)
        h3 = _dhash(img3)
        assert _hamming_distance(h1, h3) > 5

    def test_hash_is_integer(self):
        img = Image.new('RGB', (50, 50), 'gray')
        h = _dhash(img)
        assert isinstance(h, int)

    def test_hash_bit_length(self):
        img = Image.new('RGB', (200, 200), 'white')
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 190, 190], fill='black')
        draw.rectangle([50, 50, 150, 150], fill='white')
        h = _dhash(img)
        assert h.bit_length() <= HASH_SIZE * HASH_SIZE

    def test_solid_color_images_same_hash(self):
        """纯色图没有像素差异，dHash 全为 0"""
        red = Image.new('RGB', (100, 100), 'red')
        blue = Image.new('RGB', (100, 100), 'blue')
        assert _dhash(red) == _dhash(blue)


class TestHammingDistance:

    def test_same_value(self):
        assert _hamming_distance(0, 0) == 0
        assert _hamming_distance(0xFF, 0xFF) == 0

    def test_one_bit_difference(self):
        assert _hamming_distance(0b1000, 0b0000) == 1

    def test_all_bits_different(self):
        assert _hamming_distance(0x00, 0xFF) == 8

    def test_symmetric(self):
        assert _hamming_distance(42, 99) == _hamming_distance(99, 42)


# ===== ImageSimilarityChecker 集成测试 =====

class TestCheckerNoImages:
    """无图片场景"""

    def test_empty_project_skips(self, tmp_path):
        checker = ImageSimilarityChecker(str(tmp_path))
        result = checker.check_all()
        assert result.get('skipped') is True
        assert result['issues'] == []

    def test_single_image_skips(self, tmp_path):
        result_dir = tmp_path / '结果'
        result_dir.mkdir()
        img = Image.new('RGB', (100, 100), 'red')
        img.save(result_dir / 'fig1.png')
        checker = ImageSimilarityChecker(str(tmp_path))
        result = checker.check_all()
        assert result.get('skipped') is True

    def test_tiny_files_filtered(self, tmp_path):
        """< 1KB 的图片被过滤（图标/占位符）"""
        result_dir = tmp_path / '结果'
        result_dir.mkdir()
        for i in range(3):
            tiny = result_dir / f'icon{i}.png'
            tiny.write_bytes(b'\x89PNG' + b'\x00' * 100)
        checker = ImageSimilarityChecker(str(tmp_path))
        result = checker.check_all()
        assert result.get('skipped') is True


class TestCheckerDuplicateDetection:
    """重复检测"""

    def _create_structured_image(self, path: Path, seed_color='red', rect=(20, 20, 80, 80)):
        img = Image.new('RGB', (200, 200), 'white')
        draw = ImageDraw.Draw(img)
        draw.rectangle(rect, fill=seed_color)
        img.save(path)

    def test_exact_duplicates_found(self, tmp_path):
        result_dir = tmp_path / '结果'
        result_dir.mkdir()
        img = Image.new('RGB', (200, 200), 'white')
        draw = ImageDraw.Draw(img)
        draw.rectangle([30, 30, 170, 170], fill='red')
        draw.ellipse([50, 50, 150, 150], fill='blue')
        img.save(result_dir / 'fig1.png')
        img.save(result_dir / 'fig2.png')

        checker = ImageSimilarityChecker(str(tmp_path))
        result = checker.check_all()
        assert len(result['issues']) >= 1
        assert result['issues'][0]['type'] == 'IMAGE_DUPLICATE'
        assert result['issues'][0]['severity'] == 'CRITICAL'

    def test_completely_different_images_no_issues(self, tmp_path):
        result_dir = tmp_path / '结果'
        result_dir.mkdir()

        img1 = Image.new('RGB', (200, 200), 'white')
        d1 = ImageDraw.Draw(img1)
        d1.rectangle([10, 10, 60, 60], fill='red')
        img1.save(result_dir / 'fig_volcano.png')

        img2 = Image.new('RGB', (200, 200), 'black')
        d2 = ImageDraw.Draw(img2)
        d2.ellipse([100, 100, 190, 190], fill='yellow')
        d2.line([0, 0, 200, 200], fill='green', width=8)
        img2.save(result_dir / 'fig_heatmap.png')

        checker = ImageSimilarityChecker(str(tmp_path))
        result = checker.check_all()
        assert len(result['issues']) == 0

    def test_similar_images_warning(self, tmp_path):
        """轻微修改的图片应产生 WARNING"""
        result_dir = tmp_path / '结果'
        result_dir.mkdir()

        img1 = Image.new('RGB', (200, 200), 'white')
        d1 = ImageDraw.Draw(img1)
        d1.rectangle([20, 20, 180, 180], fill='red')
        d1.ellipse([40, 40, 160, 160], fill='blue')
        img1.save(result_dir / 'fig1.png')

        # 轻微修改（移动几个像素）
        img2 = Image.new('RGB', (200, 200), 'white')
        d2 = ImageDraw.Draw(img2)
        d2.rectangle([22, 22, 182, 182], fill='red')
        d2.ellipse([42, 42, 162, 162], fill='blue')
        img2.save(result_dir / 'fig2.png')

        checker = ImageSimilarityChecker(str(tmp_path))
        result = checker.check_all()
        # 轻微修改可能触发 CRITICAL（distance=0）或 WARNING（distance<=5）
        total_findings = len(result['issues']) + len(result.get('warnings', []))
        assert total_findings >= 1

    def test_returns_correct_structure(self, tmp_path):
        result_dir = tmp_path / '结果'
        result_dir.mkdir()
        _make_large_image(result_dir / 'fig1.png')
        _make_large_image(result_dir / 'fig2.png')

        checker = ImageSimilarityChecker(str(tmp_path))
        result = checker.check_all()
        assert 'issues' in result
        assert 'warnings' in result
        assert 'total_checks' in result
        assert 'failed_checks' in result

    def test_subdirectory_scanning(self, tmp_path):
        """递归扫描子目录"""
        result_dir = tmp_path / '结果' / '01_DEGs' / 'figures'
        result_dir.mkdir(parents=True)
        _make_large_image(result_dir / 'volcano.png')
        _make_large_image(result_dir / 'volcano_copy.png')

        checker = ImageSimilarityChecker(str(tmp_path))
        result = checker.check_all()
        assert len(result['issues']) >= 1


class TestCheckerEdgeCases:
    """边界场景"""

    def test_corrupted_image_skipped(self, tmp_path):
        """损坏图片不崩溃"""
        result_dir = tmp_path / '结果'
        result_dir.mkdir()
        # 写入非法 PNG
        corrupt = result_dir / 'corrupt.png'
        corrupt.write_bytes(b'\x89PNG\r\n\x1a\n' + b'garbage' * 200)
        # 正常图片
        img = Image.new('RGB', (200, 200), 'red')
        draw = ImageDraw.Draw(img)
        draw.rectangle([30, 30, 170, 170], fill='blue')
        img.save(result_dir / 'normal.png')

        checker = ImageSimilarityChecker(str(tmp_path))
        result = checker.check_all()
        # 不应崩溃
        assert isinstance(result, dict)

    def test_multiple_formats(self, tmp_path):
        """支持 PNG/JPEG/BMP 等多格式"""
        result_dir = tmp_path / '结果'
        result_dir.mkdir()
        _make_large_image(result_dir / 'fig.png')
        _make_large_image(result_dir / 'fig.jpg')
        _make_large_image(result_dir / 'fig.bmp')

        checker = ImageSimilarityChecker(str(tmp_path))
        result = checker.check_all()
        assert result['total_checks'] == 3

    def test_fallback_to_project_root(self, tmp_path):
        """无结果目录时回退到项目根"""
        _make_large_image(tmp_path / 'fig1.png')
        _make_large_image(tmp_path / 'fig2.png')

        checker = ImageSimilarityChecker(str(tmp_path))
        result = checker.check_all()
        assert len(result['issues']) >= 1


class TestCheckerPillowMissing:
    """Pillow 不可用时的降级行为"""

    def test_graceful_degradation(self, tmp_path):
        with patch('check_image_similarity._HAS_PIL', False):
            checker = ImageSimilarityChecker(str(tmp_path))
            result = checker.check_all()
            assert result.get('skipped') is True
            assert result['issues'] == []
            assert len(result['warnings']) == 1
