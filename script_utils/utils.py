#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Common utility helpers."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

# ── 编码相关 ──────────────────────────────────────────────

_ENCODINGS = ('utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'latin-1')


@lru_cache(maxsize=128)
def safe_read_file(path, encodings=_ENCODINGS) -> Tuple[str, Optional[str]]:
    """尝试多种编码读取文本文件，返回 (内容, 实际编码)。

    自动将 CRLF 统一为 LF。
    若全部尝试失败，返回 ('', None)。
    """
    for enc in encodings:
        try:
            text = Path(path).read_text(encoding=enc)
            # 统一换行符
            text = text.replace('\r\n', '\n').replace('\r', '\n')
            return text, enc
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            return '', None
    return '', None


def extract_project_id(project_name, fallback_len=20):
    """Extract project ID from a project name."""
    match = re.search(r"\d+[A-Z]+\d+[A-Z]+", project_name)
    if match:
        return match.group()
    return project_name[:fallback_len]


# ── 项目结构探测 ──────────────────────────────────────────

def find_result_root(project_path) -> Optional[Path]:
    """智能查找项目的结果根目录。

    搜索优先级:
    1. project_path / '结果文件'
    2. 项目根下有 >= 3 个编号子目录 (01_xxx, 02_xxx, ...)
    3. 常见子目录 (result, Result, 结果) 下有 >= 3 个编号子目录
    4. None（未找到）
    """
    project_path = Path(project_path)
    # 优先级 1
    result_dir = project_path / '结果文件'
    if result_dir.is_dir() and any(result_dir.iterdir()):
        return result_dir
    # 优先级 2：编号目录直接在项目根下
    numbered = [d for d in project_path.iterdir()
                if d.is_dir() and re.match(r'\d{2}_', d.name)]
    if len(numbered) >= 3:
        return project_path
    # 优先级 3：常见结果子目录
    for subdir_name in ('result', 'Result', '结果'):
        subdir = project_path / subdir_name
        if subdir.is_dir():
            sub_numbered = [d for d in subdir.iterdir()
                            if d.is_dir() and re.match(r'\d{2}_', d.name)]
            if len(sub_numbered) >= 3:
                return subdir
    return None


def find_report_text(project_path) -> Optional[str]:
    """统一查找并加载报告文本。

    搜索优先级:
    1. project_path 下 report_text*.txt
    2. result_review_report/<项目编号>/ 下 report_text*.txt
    3. project_path 下 *.docx（自动提取正文）

    返回报告文本字符串，找不到返回 None。
    """
    project_path = Path(project_path).resolve()
    for txt in sorted(project_path.glob('report_text*.txt')):
        if txt.is_file() and txt.stat().st_size > 100:
            text, _ = safe_read_file(str(txt))
            if text:
                return text

    # 优先级 2：result_review_report/<项目编号>/（向上搜索最多 5 层）
    pid = extract_project_id(project_path.name)
    if pid:
        ancestor = project_path.parent
        for _ in range(5):
            review_dir = ancestor / 'result_review_report' / pid
            if review_dir.is_dir():
                for txt in sorted(review_dir.glob('report_text*.txt')):
                    if txt.is_file() and txt.stat().st_size > 100:
                        text, _ = safe_read_file(str(txt))
                        if text:
                            return text
                break  # 找到 review_dir 就不再向上
            if ancestor.parent == ancestor:
                break  # 到达根目录
            ancestor = ancestor.parent

    # 优先级 3：docx 提取（根目录 + 常见子目录）
    import zipfile
    import xml.etree.ElementTree as ET
    docx_candidates = list(project_path.glob('*.docx'))
    for subdir_name in ('result', 'Result', '结果文件', '结果'):
        subdir = project_path / subdir_name
        if subdir.is_dir():
            docx_candidates.extend(subdir.glob('*.docx'))
    # 按文件大小降序，优先取主报告
    docx_candidates.sort(key=lambda f: f.stat().st_size if f.is_file() else 0, reverse=True)
    for docx_path in docx_candidates:
        if docx_path.name.startswith('~$') or '审核' in docx_path.name:
            continue
        try:
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            with zipfile.ZipFile(docx_path) as z:
                with z.open('word/document.xml') as f:
                    tree = ET.parse(f)
            text = '\n'.join(
                ''.join(node.text or '' for node in p.findall('.//w:t', ns))
                for p in tree.findall('.//w:p', ns)
            )
            if text and len(text) > 500:
                return text
        except Exception:
            continue

    return None
