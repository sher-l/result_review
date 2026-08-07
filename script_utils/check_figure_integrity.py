#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图件完整性检查器（适配 check_orchestrator 注册表）

检查项目结果文件夹中的图件文件：
- 空文件 / 异常小文件 → CRITICAL
- PDF 页数为 0 → CRITICAL
- 文件名拼写错误 → WARNING
- Figure 编号不连续 → WARNING
- PNG/JPG 尺寸过小 → WARNING

作者: 审核框架 v6.5
创建日期: 2026-03-30
"""

import os
import re
import struct
import itertools
from pathlib import Path
from typing import Dict, List, Tuple
from base_project_checker import BaseProjectChecker

FIGURE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".svg", ".bmp"}
MIN_PDF_SIZE = 500
MIN_IMAGE_SIZE = 200

COMMON_TYPOS = {
    "noramal": "normal",
    "nomral": "normal",
    "norml": "normal",
    "tumer": "tumor",
    "contorl": "control",
    "cnotrol": "control",
    "differntially": "differentially",
    "volcanol": "volcano",
    "heaatmap": "heatmap",
    "survial": "survival",
    "regulaory": "regulatory",
}


class FigureIntegrityChecker(BaseProjectChecker):
    """图件完整性检查器"""

    def __init__(self, project_path: str, layer0_data: dict = None):
        super().__init__(project_path, layer0_data=layer0_data)

    def check_all(self) -> Dict:
        """执行全部图件检查，返回 orchestrator 兼容格式。"""
        issues: List[Dict] = []
        warnings: List[Dict] = []
        stats = {"total": 0, "by_type": {}}

        # 查找结果文件夹
        result_dir = self._find_result_dir()
        if result_dir is None:
            return {"issues": [], "warnings": [], "stats": stats}

        figure_files = self._collect_figure_files(result_dir)
        stats["total"] = len(figure_files)
        filenames = []

        for fpath in figure_files:
            ext = fpath.suffix.lower()
            stats["by_type"][ext] = stats["by_type"].get(ext, 0) + 1
            filenames.append(fpath.name)
            rel = self._relative_path(fpath)
            size = fpath.stat().st_size

            # 空文件
            if size == 0:
                issues.append({
                    "file": rel, "severity": "CRITICAL",
                    "message": f"空文件 (0 bytes): {rel}"
                })
                continue

            # PDF 异常小
            if ext == ".pdf" and size < MIN_PDF_SIZE:
                warnings.append({
                    "file": rel, "severity": "WARNING",
                    "message": f"PDF 异常小 ({size}B): {rel}"
                })

            # PDF 页数
            if ext == ".pdf":
                pages = self._pdf_page_count(fpath)
                if pages == 0:
                    issues.append({
                        "file": rel, "severity": "CRITICAL",
                        "message": f"PDF 页数为 0: {rel}"
                    })

            # PNG 尺寸
            if ext == ".png":
                dims = self._png_dims(fpath)
                if dims and (dims[0] < 100 or dims[1] < 100):
                    warnings.append({
                        "file": rel, "severity": "WARNING",
                        "message": f"PNG 尺寸过小 ({dims[0]}x{dims[1]}): {rel}"
                    })

            # 文件名拼写
            for typo, correct in COMMON_TYPOS.items():
                if typo in fpath.name.lower():
                    warnings.append({
                        "file": rel, "severity": "WARNING",
                        "message": f"文件名拼写错误 '{typo}'→'{correct}': {rel}"
                    })

        # Figure 编号连续性
        fig_nums = self._extract_figure_numbers(filenames)
        for i in range(len(fig_nums) - 1):
            if fig_nums[i + 1] - fig_nums[i] > 1:
                missing = list(range(fig_nums[i] + 1, fig_nums[i + 1]))
                warnings.append({
                    "file": "全局", "severity": "WARNING",
                    "message": f"Figure 编号不连续: {fig_nums[i]}→{fig_nums[i+1]}，缺 {missing}"
                })

        for warning in self._check_preferred_pdf_delivery(figure_files, result_dir):
            warnings.append(warning)

        return {"issues": issues, "warnings": warnings, "stats": stats}

    # ── 内部方法 ──

    def _find_result_dir(self) -> Path | None:
        """查找项目中的结果文件夹。优先使用基类 find_code_directory()。"""
        # 基类方法（支持 Layer 0 快速路径 + metadata）
        code_dir = self.find_code_directory()
        if code_dir is not None and code_dir.is_dir():
            return code_dir
        for name in ("结果文件", "results", "output"):
            d = self.project_path / name
            if d.is_dir():
                return d
        # 直接使用项目路径
        return self.project_path if any(
            f.suffix.lower() in FIGURE_EXTENSIONS
            for f in itertools.islice((f for f in self.project_path.rglob("*") if f.is_file()), 500)
        ) else None

    def _collect_figure_files(self, root: Path) -> List[Path]:
        files = []
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                if Path(fn).suffix.lower() in FIGURE_EXTENSIONS:
                    files.append(Path(dirpath) / fn)
        return files

    def _check_preferred_pdf_delivery(self, figure_files: List[Path], root: Path) -> List[Dict]:
        """Check figure delivery format.

        PDF-only delivery is acceptable.  PNG-only delivery is still flagged
        because PDF is the preferred review/publication artifact and is usually
        easier to render consistently across platforms.
        """
        by_stem: Dict[str, set[str]] = {}
        display_path: Dict[str, str] = {}
        for fpath in figure_files:
            ext = fpath.suffix.lower()
            if ext not in {".pdf", ".png"}:
                continue
            try:
                key = str(fpath.relative_to(root).with_suffix(""))
            except ValueError:
                key = str(fpath.with_suffix(""))
            by_stem.setdefault(key, set()).add(ext)
            display_path.setdefault(key, self._relative_path(fpath))

        warnings: List[Dict] = []
        for key, exts in sorted(by_stem.items()):
            if ".png" in exts and ".pdf" not in exts:
                warnings.append({
                    "file": display_path.get(key, f"{key}.png"),
                    "severity": "WARNING",
                    "message": "图件仅有PNG，缺少PDF交付；PDF-only 可接受，但 PNG-only 需说明或补充PDF",
                })
        return warnings

    # Backward-compatible alias for older tests/importers.
    def _check_pdf_png_dual_format(self, figure_files: List[Path], root: Path) -> List[Dict]:
        return self._check_preferred_pdf_delivery(figure_files, root)

    def _pdf_page_count(self, fp: Path) -> int | None:
        try:
            content = fp.read_bytes()
            # 仅从 /Type /Pages (根Pages节点) 所在 PDF 对象内提取 /Count，
            # 避免匹配到字体表、颜色空间等非页数的 /Count 值
            for m in re.finditer(rb'/Type\s*/Pages\b', content):
                # 定位当前对象边界：往前找 obj，往后找 endobj
                obj_start = content.rfind(b'obj', 0, m.start())
                obj_end = content.find(b'endobj', m.end())
                if obj_start < 0:
                    obj_start = max(0, m.start() - 300)
                if obj_end < 0:
                    obj_end = min(len(content), m.end() + 500)
                local = content[obj_start:obj_end]
                count_m = re.search(rb'/Count\s+(\d+)', local)
                if count_m:
                    return int(count_m.group(1))
            # 回退：逐页计数
            pages = len(re.findall(rb'/Type\s*/Page(?!s)', content))
            return pages if pages > 0 else None
        except Exception:
            return None

    def _png_dims(self, fp: Path) -> Tuple[int, int] | None:
        try:
            with open(fp, "rb") as f:
                hdr = f.read(24)
            if hdr[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack(">II", hdr[16:24])
                return (w, h)
        except Exception:
            pass
        return None

    def _extract_figure_numbers(self, names: List[str]) -> List[int]:
        nums = set()
        for n in names:
            for m in re.findall(r"[Ff]ig(?:ure)?\s*(\d+)", n):
                nums.add(int(m))
        return sorted(nums)
