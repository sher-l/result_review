#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图件完整性检查器单元测试（P1级）

运行方式:
  cd result_review_framework
  python -m pytest tests/test_check_figure_integrity.py -v
"""

import struct
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
from check_figure_integrity import FigureIntegrityChecker


# ===== Fixtures =====

def make_checker(path):
    """创建 checker 但跳过完整 __init__"""
    c = FigureIntegrityChecker.__new__(FigureIntegrityChecker)
    c.project_path = Path(path)
    c.issues = []
    c.warnings = []
    return c


# ===== PDF 页数测试 =====

class TestPDFPageCount:
    """PDF 页数提取"""

    def test_simple_pdf(self, tmp_path):
        pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Pages /Kids [2 0 R] /Count 3 >>\nendobj\n"
            b"2 0 obj\n<< /Type /Page /Parent 1 0 R >>\nendobj\n"
            b"%%EOF"
        )
        p = tmp_path / 'test.pdf'
        p.write_bytes(pdf)
        c = make_checker(tmp_path)
        assert c._pdf_page_count(p) == 3

    def test_ignores_font_count(self, tmp_path):
        """字体表中的 /Count 256 不应干扰页数"""
        pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Font /Count 256 >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 5 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
            b"%%EOF"
        )
        p = tmp_path / 'test.pdf'
        p.write_bytes(pdf)
        c = make_checker(tmp_path)
        assert c._pdf_page_count(p) == 5

    def test_fallback_page_counting(self, tmp_path):
        """无 /Pages 节点时回退到逐页计数"""
        pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Page >>\nendobj\n"
            b"2 0 obj\n<< /Type /Page >>\nendobj\n"
            b"%%EOF"
        )
        p = tmp_path / 'test.pdf'
        p.write_bytes(pdf)
        c = make_checker(tmp_path)
        assert c._pdf_page_count(p) == 2

    def test_empty_file_returns_none(self, tmp_path):
        p = tmp_path / 'empty.pdf'
        p.write_bytes(b'')
        c = make_checker(tmp_path)
        assert c._pdf_page_count(p) is None

    def test_nonexistent_file_returns_none(self, tmp_path):
        c = make_checker(tmp_path)
        assert c._pdf_page_count(tmp_path / 'nonexist.pdf') is None


# ===== PNG 尺寸测试 =====

class TestPNGDimensions:
    """PNG 图像尺寸提取"""

    def test_valid_png(self, tmp_path):
        # 构造最小 PNG 头
        header = b'\x89PNG\r\n\x1a\n' + b'\x00' * 8 + struct.pack('>II', 800, 600)
        p = tmp_path / 'test.png'
        p.write_bytes(header)
        c = make_checker(tmp_path)
        dims = c._png_dims(p)
        assert dims == (800, 600)

    def test_invalid_png_returns_none(self, tmp_path):
        p = tmp_path / 'bad.png'
        p.write_bytes(b'not a png')
        c = make_checker(tmp_path)
        assert c._png_dims(p) is None


# ===== 图件编号提取 =====

class TestExtractFigureNumbers:
    """从文件名提取 Figure 编号"""

    def test_standard_naming(self, tmp_path):
        c = make_checker(tmp_path)
        nums = c._extract_figure_numbers(['Fig1.png', 'Fig2.png', 'Fig3.png'])
        assert nums == [1, 2, 3]

    def test_figure_word(self, tmp_path):
        c = make_checker(tmp_path)
        nums = c._extract_figure_numbers(['Figure1.pdf', 'Figure 3.png'])
        assert 1 in nums
        assert 3 in nums

    def test_no_figure_prefix(self, tmp_path):
        c = make_checker(tmp_path)
        nums = c._extract_figure_numbers(['result.png', 'heatmap.jpg'])
        assert nums == []

    def test_mixed_naming(self, tmp_path):
        c = make_checker(tmp_path)
        nums = c._extract_figure_numbers(['fig1_volcano.png', 'Figure2_heatmap.pdf'])
        assert sorted(nums) == [1, 2]


# ===== 常量验证 =====

class TestConstants:
    """验证模块级常量"""

    def test_figure_extensions(self):
        from check_figure_integrity import FIGURE_EXTENSIONS
        assert '.pdf' in FIGURE_EXTENSIONS
        assert '.png' in FIGURE_EXTENSIONS
        assert '.svg' in FIGURE_EXTENSIONS

    def test_min_sizes(self):
        from check_figure_integrity import MIN_PDF_SIZE, MIN_IMAGE_SIZE
        assert MIN_PDF_SIZE > 0
        assert MIN_IMAGE_SIZE > 0
