#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""图件完整性自动检查器 
扫描项目结果文件夹中的所有图件(PDF/PNG/JPG/TIFF)，检查：
1. 文件大小（空文件/异常小文件）
2. PDF页数和基本元数据
3. 图片分辨率（PNG/JPG/TIFF）
4. 文件名拼写异常（常见typo检测）
5. Figure编号连续性
6. 汇总报告输出

用法：
    python check_figure_integrity.py <项目结果文件夹路径>
    python check_figure_integrity.py <项目结果文件夹路径> --output report.md
"""

from __future__ import annotations

import argparse
import os
import re
import struct
from pathlib import Path
from typing import Dict, List, Tuple

# 常见文件名拼写错误
COMMON_TYPOS = {
    "noramal": "normal",
    "nomral": "normal",
    "norml": "normal",
    "tumer": "tumor",
    "tumour": "tumour",  # 英式拼写，不算错
    "contorl": "control",
    "cnotrol": "control",
    "differentially": None,  # 正确
    "differntially": "differentially",
    "volcanol": "volcano",
    "heaatmap": "heatmap",
    "heatmap": None,
    "survial": "survival",
    "regulaory": "regulatory",
}

# 图件文件扩展名
FIGURE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".svg", ".bmp"}

# PDF最小合理大小(bytes) - 小于此值可能是空PDF
MIN_PDF_SIZE = 500
# 图片最小合理大小(bytes)
MIN_IMAGE_SIZE = 200


def get_pdf_page_count(filepath: Path) -> int | None:
    """从PDF文件中提取页数（不依赖外部库）。"""
    try:
        with open(filepath, "rb") as f:
            content = f.read()
        # 搜索 /Type /Page 出现次数（粗略估计）
        # 更准确的方法是找 /Count
        count_matches = re.findall(rb"/Count\s+(\d+)", content)
        if count_matches:
            return max(int(c) for c in count_matches)
        # 备选：计算 /Type /Page（非 /Pages）
        pages = len(re.findall(rb"/Type\s*/Page(?!s)", content))
        return pages if pages > 0 else None
    except Exception:
        return None


def get_png_dimensions(filepath: Path) -> Tuple[int, int] | None:
    """从PNG文件头提取宽高。"""
    try:
        with open(filepath, "rb") as f:
            header = f.read(24)
            if header[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack(">II", header[16:24])
                return (w, h)
    except Exception:
        pass
    return None


def get_jpg_dimensions(filepath: Path) -> Tuple[int, int] | None:
    """从JPEG文件提取宽高。"""
    try:
        with open(filepath, "rb") as f:
            f.read(2)  # SOI marker
            while True:
                marker = f.read(2)
                if len(marker) < 2:
                    break
                if marker[0] != 0xFF:
                    break
                if marker[1] in (0xC0, 0xC1, 0xC2):
                    f.read(3)  # length + precision
                    h, w = struct.unpack(">HH", f.read(4))
                    return (w, h)
                else:
                    length = struct.unpack(">H", f.read(2))[0]
                    f.read(length - 2)
    except Exception:
        pass
    return None


def check_filename_typos(filename: str) -> List[str]:
    """检查文件名中的常见拼写错误。"""
    issues = []
    name_lower = filename.lower()
    for typo, correct in COMMON_TYPOS.items():
        if correct is not None and typo in name_lower:
            issues.append(f"文件名拼写错误: '{typo}' → 应为 '{correct}'")
    return issues


def extract_figure_numbers(filenames: List[str]) -> List[int]:
    """从文件名中提取Figure编号。"""
    numbers = set()
    for name in filenames:
        matches = re.findall(r"[Ff]igure\s*(\d+)", name)
        if not matches:
            matches = re.findall(r"[Ff]ig\.?\s*(\d+)", name)
        for m in matches:
            numbers.add(int(m))
    return sorted(numbers)


def check_figure_numbering(numbers: List[int]) -> List[str]:
    """检查Figure编号连续性。"""
    issues = []
    if not numbers:
        return issues
    for i in range(len(numbers) - 1):
        if numbers[i + 1] - numbers[i] > 1:
            missing = list(range(numbers[i] + 1, numbers[i + 1]))
            issues.append(f"Figure编号不连续: {numbers[i]}→{numbers[i+1]}，缺少 {missing}")
    # 检查重复（不会有，因为用了set）
    return issues


def scan_figures(project_path: Path) -> Dict:
    """扫描项目中所有图件文件并进行检查。"""
    results = {
        "total_files": 0,
        "by_type": {},
        "issues": [],
        "warnings": [],
        "files": [],
        "figure_numbers": [],
    }

    all_figure_files = []
    for root, dirs, files in os.walk(project_path):
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext in FIGURE_EXTENSIONS:
                fpath = Path(root) / fname
                all_figure_files.append(fpath)

    results["total_files"] = len(all_figure_files)

    all_filenames = []
    for fpath in all_figure_files:
        file_info = {
            "path": str(fpath.relative_to(project_path)),
            "name": fpath.name,
            "size": fpath.stat().st_size,
            "ext": fpath.suffix.lower(),
            "issues": [],
        }
        all_filenames.append(fpath.name)

        # 统计类型
        ext = fpath.suffix.lower()
        results["by_type"][ext] = results["by_type"].get(ext, 0) + 1

        # 检查文件大小
        size = fpath.stat().st_size
        if size == 0:
            file_info["issues"].append("🔴 空文件 (0 bytes)")
            results["issues"].append(f"🔴 空文件: {file_info['path']}")
        elif ext == ".pdf" and size < MIN_PDF_SIZE:
            file_info["issues"].append(f"⚠️ PDF文件异常小 ({size} bytes)")
            results["warnings"].append(f"⚠️ PDF异常小: {file_info['path']} ({size}B)")
        elif ext in (".png", ".jpg", ".jpeg") and size < MIN_IMAGE_SIZE:
            file_info["issues"].append(f"⚠️ 图片异常小 ({size} bytes)")
            results["warnings"].append(f"⚠️ 图片异常小: {file_info['path']} ({size}B)")

        # PDF页数
        if ext == ".pdf" and size > 0:
            pages = get_pdf_page_count(fpath)
            if pages is not None:
                file_info["pages"] = pages
                if pages == 0:
                    file_info["issues"].append("🔴 PDF页数为0")
                    results["issues"].append(f"🔴 PDF 0页: {file_info['path']}")

        # PNG尺寸
        if ext == ".png" and size > 0:
            dims = get_png_dimensions(fpath)
            if dims:
                file_info["dimensions"] = f"{dims[0]}x{dims[1]}"
                if dims[0] < 100 or dims[1] < 100:
                    file_info["issues"].append(f"⚠️ 图片尺寸过小 ({dims[0]}x{dims[1]})")
                    results["warnings"].append(f"⚠️ 尺寸过小: {file_info['path']} ({dims[0]}x{dims[1]})")

        # JPG尺寸
        if ext in (".jpg", ".jpeg") and size > 0:
            dims = get_jpg_dimensions(fpath)
            if dims:
                file_info["dimensions"] = f"{dims[0]}x{dims[1]}"

        # 文件名拼写
        typos = check_filename_typos(fpath.name)
        for t in typos:
            file_info["issues"].append(f"🟡 {t}")
            results["warnings"].append(f"🟡 {file_info['path']}: {t}")

        results["files"].append(file_info)

    # Figure编号连续性
    fig_numbers = extract_figure_numbers(all_filenames)
    results["figure_numbers"] = fig_numbers
    numbering_issues = check_figure_numbering(fig_numbers)
    for issue in numbering_issues:
        results["warnings"].append(f"🟡 {issue}")

    return results


def format_report(results: Dict, project_path: Path) -> str:
    """生成Markdown格式的检查报告。"""
    lines = []
    lines.append(f"# 图件完整性检查报告")
    lines.append(f"")
    lines.append(f"> 项目路径: `{project_path}`")
    lines.append(f"> 图件总数: {results['total_files']}")
    lines.append(f"")

    # 类型统计
    lines.append("## 文件类型统计")
    lines.append("")
    lines.append("| 类型 | 数量 |")
    lines.append("|------|------|")
    for ext, count in sorted(results["by_type"].items()):
        lines.append(f"| {ext} | {count} |")
    lines.append("")

    # Figure编号
    if results["figure_numbers"]:
        lines.append(f"## Figure编号: {results['figure_numbers'][0]}-{results['figure_numbers'][-1]}")
        lines.append("")

    # 问题汇总
    if results["issues"]:
        lines.append("## 🔴 严重问题")
        lines.append("")
        for issue in results["issues"]:
            lines.append(f"- {issue}")
        lines.append("")

    if results["warnings"]:
        lines.append("## ⚠️ 警告")
        lines.append("")
        for warning in results["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")

    if not results["issues"] and not results["warnings"]:
        lines.append("## ✅ 未发现问题")
        lines.append("")

    # 详细文件列表（仅有问题的）
    problem_files = [f for f in results["files"] if f["issues"]]
    if problem_files:
        lines.append("## 问题文件详情")
        lines.append("")
        for f in problem_files:
            lines.append(f"### {f['path']}")
            lines.append(f"- 大小: {f['size']} bytes")
            if "pages" in f:
                lines.append(f"- PDF页数: {f['pages']}")
            if "dimensions" in f:
                lines.append(f"- 尺寸: {f['dimensions']}")
            for issue in f["issues"]:
                lines.append(f"- {issue}")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="扫描项目结果文件夹中的图件，检查完整性和基本质量"
    )
    parser.add_argument("path", help="项目结果文件夹路径")
    parser.add_argument("--output", "-o", help="输出报告路径（默认输出到终端）")
    args = parser.parse_args()

    project_path = Path(args.path).resolve()
    if not project_path.exists():
        print(f"错误: 路径不存在: {project_path}")
        return 1

    # 扫描
    results = scan_figures(project_path)

    # 格式化报告
    report = format_report(results, project_path)

    # 终端摘要
    print(f"图件完整性检查: {project_path.name}")
    print(f"  总计: {results['total_files']} 个图件")
    print(f"  类型: {', '.join(f'{ext}({n})' for ext, n in sorted(results['by_type'].items()))}")
    if results["figure_numbers"]:
        print(f"  Figure编号: {results['figure_numbers'][0]}-{results['figure_numbers'][-1]}")
    print(f"  🔴 严重: {len(results['issues'])}")
    print(f"  ⚠️ 警告: {len(results['warnings'])}")

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"\n报告已写入: {output_path}")
    else:
        print(f"\n{report}")

    return 1 if results["issues"] else 0


if __name__ == "__main__":
    exit(main())
