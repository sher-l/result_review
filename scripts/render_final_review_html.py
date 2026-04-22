#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""将 final_review_report.md 渲染为可交付的 audit_report.html。"""

from __future__ import annotations

import argparse
import html
import re
from datetime import datetime
from pathlib import Path
from typing import List, Sequence


TEMPLATE_PATH = Path(__file__).parent.parent / "report_templates" / "final_review_report_template.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 final_review_report.md 渲染为 audit_report.html"
    )
    parser.add_argument("input_path", help="审核目录或 final_review_report.md 文件路径")
    parser.add_argument("--output", "-o", help="输出 HTML 文件路径（默认：审核目录/audit_report.html）")
    return parser.parse_args()


# 支持的审核报告文件名（按优先级）
_REPORT_NAMES = ('final_review_report.md', 'REVIEW_REPORT.md')


def _derive_project_id(path: Path) -> str:
    """从路径推断项目编号。"""
    pattern = r"\b\d{2}[A-Z]{3}\d{3}[A-Z]?\b"
    for candidate in [path, *list(path.parents)[:4]]:
        m = re.search(pattern, candidate.name)
        if m:
            return m.group(0)
    return path.name


def resolve_paths(input_path: str, output_path: str | None) -> tuple[Path, Path]:
    source = Path(input_path)
    if source.is_dir():
        markdown_path = None
        for name in _REPORT_NAMES:
            candidate = source / name
            if candidate.exists():
                markdown_path = candidate
                break
        if markdown_path is None:
            markdown_path = source / _REPORT_NAMES[0]  # 用于错误消息
        project_id = _derive_project_id(source)
        default_html = source / f"{project_id}_audit_report.html"
        html_path = Path(output_path) if output_path else default_html
    else:
        markdown_path = source
        project_id = _derive_project_id(source.parent)
        default_html = source.with_name(f"{project_id}_audit_report.html")
        html_path = Path(output_path) if output_path else default_html

    if not markdown_path.exists():
        raise FileNotFoundError(f"未找到最终审核报告: {markdown_path}")

    return markdown_path, html_path


def apply_inline_formatting(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    # 单星斜体（在粗体处理之后，避免与 ** 冲突）
    escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)
    # Severity 关键词加彩色标签
    _sev_colors = {"FATAL": "sev-tag-fatal", "CRITICAL": "sev-tag-critical",
                   "MAJOR": "sev-tag-major", "WARNING": "sev-tag-warning", "INFO": "sev-tag-info"}
    for kw, cls in _sev_colors.items():
        escaped = re.sub(rf'\b({kw})\b', rf'<span class="{cls}">\1</span>', escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    # 链接：过滤 javascript: 等危险协议
    link_pattern = re.compile(r"\[([^\[\]]+)\]\(((?:[^()]|\([^)]*\))+)\)")

    def _safe_link(m):
        label, url = m.group(1), m.group(2)
        if re.match(r'(?:javascript|data|vbscript):', url, re.IGNORECASE):
            return label
        return f'<a href="{html.escape(url, quote=True)}">{label}</a>'
    escaped = link_pattern.sub(_safe_link, escaped)
    return escaped


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "section"


def is_table_block(lines: Sequence[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return lines[index].strip().startswith("|") and re.match(r"^\|?[\s:-]+\|[\s|:-]*$", lines[index + 1].strip()) is not None


def parse_table_row(line: str) -> List[str]:
    # 先将转义管道符 \| 替换为占位符，split 后再还原
    _PIPE_PLACEHOLDER = "\x00PIPE\x00"
    escaped = line.strip().strip("|").replace("\\|", _PIPE_PLACEHOLDER)
    cells = [cell.strip().replace(_PIPE_PLACEHOLDER, "|") for cell in escaped.split("|")]
    return [apply_inline_formatting(cell) for cell in cells]


def render_table(lines: Sequence[str], start: int) -> tuple[str, int]:
    header = parse_table_row(lines[start])
    body_rows: List[List[str]] = []
    index = start + 2
    while index < len(lines) and lines[index].strip().startswith("|"):
        body_rows.append(parse_table_row(lines[index]))
        index += 1

    parts = ["<div class=\"table-wrap\"><table>", "<thead><tr>"]
    parts.extend(f"<th>{cell}</th>" for cell in header)
    parts.append("</tr></thead><tbody>")
    for row in body_rows:
        parts.append("<tr>")
        parts.extend(f"<td>{cell}</td>" for cell in row)
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts), index


_LABEL_CLASSES = {
    "位置": "label-context",
    "原文": "label-error",
    "问题": "label-error",
    "错误": "label-error",
    "冲突": "label-error",
    "核心矛盾": "label-error",
    "应为": "label-fix",
    "修正": "label-fix",
    "建议": "label-fix",
    "方向": "label-fix",
    "代码证实": "label-evidence",
    "证据": "label-evidence",
    "验证": "label-evidence",
    "性质": "label-context",
    "方法段": "label-context",
    "结果段": "label-context",
    "实际文件": "label-context",
}
_LABEL_RE = re.compile(r'^\*{0,2}(' + '|'.join(re.escape(k) for k in _LABEL_CLASSES) + r')[^*]*\*{0,2}[：:]')


def _classify_li(text: str) -> str:
    """根据列表项关键词前缀返回 CSS class。"""
    m = _LABEL_RE.search(text)
    if m:
        return _LABEL_CLASSES.get(m.group(1), "")
    return ""


def render_list(lines: Sequence[str], start: int, ordered: bool) -> tuple[str, int]:
    tag = "ol" if ordered else "ul"
    pattern = r"^\d+\.\s+" if ordered else r"^[-*+]\s+"
    items: List[str] = []
    index = start
    while index < len(lines):
        stripped = lines[index].strip()
        if not re.match(pattern, stripped):
            break
        item_text = re.sub(pattern, "", stripped, count=1)
        css_class = _classify_li(item_text)
        cls_attr = f' class="{css_class}"' if css_class else ""
        items.append(f"<li{cls_attr}>{apply_inline_formatting(item_text)}</li>")
        index += 1
    return f"<{tag}>" + "".join(items) + f"</{tag}>", index


def render_markdown(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    html_parts: List[str] = []
    paragraph_buffer: List[str] = []
    in_code_block = False
    code_lines: List[str] = []
    code_language = ""
    severity_class = ""
    index = 0

    _HIGHLIGHT_P_RE = re.compile(
        r'但存在(?:问题|缺陷|不足)|主要集中在|需(?:修正|要修改|改进)|(?:问题|缺陷)主要|(?:核心|严重)问题'
    )

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if paragraph_buffer:
            # 支持 Markdown 硬换行：行尾两个以上空格 → <br>
            parts = []
            for part in paragraph_buffer:
                stripped = part.rstrip()
                if part.endswith("  ") or part.endswith("  \n"):
                    parts.append(apply_inline_formatting(stripped) + "<br>")
                elif stripped:
                    parts.append(apply_inline_formatting(stripped))
            text = " ".join(parts)
            if text:
                cls = ' class="highlight-issue"' if _HIGHLIGHT_P_RE.search(text) else ""
                html_parts.append(f"<p{cls}>{text}</p>")
            paragraph_buffer = []

    def flush_severity_block() -> None:
        nonlocal severity_class
        if severity_class:
            html_parts.append("</div>")
            severity_class = ""

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        # 跳过 H1 下方的引用块元数据（已合并到 hero 区域）和分隔符
        if stripped.startswith(">") or stripped == "---":
            index += 1
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            if in_code_block:
                code_html = html.escape("\n".join(code_lines))
                html_parts.append(
                    f"<pre class=\"code-block\"><code class=\"language-{html.escape(code_language)}\">{code_html}</code></pre>"
                )
                in_code_block = False
                code_lines = []
                code_language = ""
            else:
                in_code_block = True
                code_language = stripped[3:].strip()
            index += 1
            continue

        if in_code_block:
            code_lines.append(line)
            index += 1
            continue

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        if is_table_block(lines, index):
            flush_paragraph()
            table_html, index = render_table(lines, index)
            html_parts.append(table_html)
            continue

        if re.match(r"^#{1,6}\s+", stripped):
            flush_paragraph()
            level = len(stripped) - len(stripped.lstrip("#"))
            heading_text = stripped[level:].strip()
            sev_match = re.search(r'\b(FATAL|CRITICAL|MAJOR|WARNING|INFO)\b', heading_text)
            if level <= 2:
                flush_severity_block()
            elif level == 3 and sev_match:
                flush_severity_block()
                sev = sev_match.group(1).lower()
                html_parts.append(f'<div class="severity-block severity-{sev}">')
                severity_class = sev
            html_parts.append(
                f"<h{level} id=\"{slugify(heading_text)}\">{apply_inline_formatting(heading_text)}</h{level}>"
            )
            index += 1
            continue

        if re.match(r"^\d+\.\s+", stripped):
            flush_paragraph()
            list_html, index = render_list(lines, index, ordered=True)
            html_parts.append(list_html)
            continue

        if re.match(r"^[-*+]\s+", stripped):
            flush_paragraph()
            list_html, index = render_list(lines, index, ordered=False)
            html_parts.append(list_html)
            continue

        paragraph_buffer.append(line)
        index += 1

    flush_paragraph()
    flush_severity_block()
    return "\n".join(html_parts)


def extract_h1(markdown_text: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown_text, flags=re.MULTILINE)
    return match.group(1).strip() if match else "最终审核报告"


def extract_section(markdown_text: str, heading_prefix: str) -> str:
    pattern = rf"^##\s+{re.escape(heading_prefix)}.*?$([\s\S]*?)(?=^##\s+|\Z)"
    match = re.search(pattern, markdown_text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def count_issue_levels(markdown_text: str) -> dict[str, int]:
    counts = {key: 0 for key in ["FATAL", "CRITICAL", "MAJOR", "WARNING", "INFO"]}
    for match in re.finditer(
        r"^###\s+(?:[\U0001f000-\U0001ffff\u2600-\u27bf\ufe0f]*\s*)?(FATAL|CRITICAL|MAJOR|WARNING|INFO)\b",
        markdown_text,
        flags=re.MULTILINE,
    ):
        counts[match.group(1)] += 1
    return counts


def parse_analysis_table(markdown_text: str) -> list[dict[str, str]]:
    section = extract_section(markdown_text, "五、逐分析点审核结果表")
    lines = [line for line in section.splitlines() if line.strip().startswith("|")]
    if len(lines) < 3:
        return []

    headers = [cell.strip() for cell in lines[0].strip().strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells)))
    return rows


_CN_NUMERALS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
                "十一", "十二", "十三", "十四", "十五"]
_CN_NUM_RE = re.compile(r'[一二三四五六七八九十]+(?:十[一二三四五六七八九])?')


def _renumber_cn(text: str, idx: int) -> str:
    """将文本中的中文序号替换为 idx 对应的中文数字（1-based）。"""
    if idx < 1 or idx > len(_CN_NUMERALS):
        return text
    return _CN_NUM_RE.sub(_CN_NUMERALS[idx - 1], text, count=1)


def _reorder_and_renumber(items: list, get_title) -> list:
    """将"问题详述"移到"执行摘要"后面并重编号。items 是 list，get_title 返回标题字符串。"""
    detail_idx = None
    summary_idx = None
    for i, item in enumerate(items):
        title = get_title(item)
        if '问题详述' in title:
            detail_idx = i
        if '执行摘要' in title:
            summary_idx = i
    if detail_idx is not None and summary_idx is not None and detail_idx > summary_idx + 1:
        detail_item = items.pop(detail_idx)
        items.insert(summary_idx + 1, detail_item)
    return items


def build_toc(markdown_text: str) -> str:
    raw_titles: List[str] = []
    for line in markdown_text.splitlines():
        if not line.startswith("## "):
            continue
        raw_titles.append(line[3:].strip())
    _reorder_and_renumber(raw_titles, lambda t: t)
    li_items = []
    for i, title in enumerate(raw_titles):
        new_title = _renumber_cn(title, i + 1)
        li_items.append(f'<li><a href="#{slugify(new_title)}">{html.escape(new_title)}</a></li>')
    return "<ul>" + "".join(li_items) + "</ul>"


def extract_conclusion_summary(markdown_text: str) -> str:
    section = extract_section(markdown_text, "一、审核结论")
    sentences = [line.strip() for line in section.splitlines() if line.strip()]
    return sentences[0] if sentences else "请结合正文查看完整审核结论。"


def load_template() -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"未找到 HTML 模板: {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def render_template(template: str, context: dict[str, str]) -> str:
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def extract_explicit_verdict(markdown_text: str) -> tuple[str, str] | None:
    """优先从“审核结论”字段读取明确结论。"""
    match = re.search(r"^[>\-\*\s`]*审核结论[：:]\s*(.+)$", markdown_text, flags=re.MULTILINE)
    if not match:
        return None
    verdict_text = re.sub(r"[*`_~]", "", match.group(1)).strip()
    verdict_text = verdict_text.splitlines()[0].strip()
    if "不建议提交" in verdict_text or "不建议" in verdict_text:
        return "verdict-reject", "不建议提交"
    if "有条件通过" in verdict_text or "整改后提交" in verdict_text or "整改后复审" in verdict_text:
        return "verdict-conditional", "有条件通过"
    if "建议通过" in verdict_text or "可以提交" in verdict_text or "通过" in verdict_text:
        return "verdict-pass", "建议通过"
    return None


def determine_verdict(issue_counts: dict[str, int], markdown_text: str = "") -> tuple[str, str]:
    """根据明确审核结论或问题计数返回 (verdict_class, verdict_text)。"""
    explicit = extract_explicit_verdict(markdown_text)
    if explicit is not None:
        return explicit
    if issue_counts["FATAL"] > 0:
        return "verdict-reject", "不建议提交"
    if issue_counts["CRITICAL"] > 0:
        return "verdict-conditional", "有条件通过"
    if issue_counts["MAJOR"] > 0:
        return "verdict-conditional", "有条件通过"
    return "verdict-pass", "建议通过"


def reorder_sections(content_html: str) -> str:
    """将"问题详述"章节移到"执行摘要"后面，并重编中文序号。"""
    parts = re.split(r'(?=<h2\s)', content_html)
    _reorder_and_renumber(parts, lambda p: p[:200])
    # 对每个 h2 part 重编号 (更新显示文字和 id)
    for i, part in enumerate(parts):
        if not part.startswith('<h2'):
            continue
        h2_match = re.match(r'<h2 id="([^"]*)">(.*?)</h2>', part)
        if not h2_match or i < 1:
            continue
        old_text = h2_match.group(2)
        new_text = _CN_NUM_RE.sub(_CN_NUMERALS[i - 1] if i <= len(_CN_NUMERALS) else old_text, old_text, count=1)
        new_id = slugify(new_text)
        new_h2 = f'<h2 id="{new_id}">{new_text}</h2>'
        parts[i] = part[:h2_match.start()] + new_h2 + part[h2_match.end():]
    return "".join(parts)


def extract_meta_fields(markdown_text: str) -> dict[str, str]:
    """从 H1 后的引用块提取项目元数据。"""
    fields: dict[str, str] = {}
    for m in re.finditer(r'>\s*\*{0,2}(.+?)\*{0,2}\s*[：:]\s*(.+)', markdown_text):
        key = m.group(1).strip().strip('*')
        val = m.group(2).strip()
        fields[key] = val
    return fields


def build_html(markdown_text: str, source_path: Path) -> str:
    title = extract_h1(markdown_text)
    project_id_match = re.search(r"\b\d{2}[A-Z]{3}\d{3}[A-Z]?\b", title)
    project_id = project_id_match.group(0) if project_id_match else source_path.parent.name
    issue_counts = count_issue_levels(markdown_text)
    analysis_rows = parse_analysis_table(markdown_text)
    issue_total = sum(issue_counts.values())
    severe_total = issue_counts["FATAL"] + issue_counts["CRITICAL"]
    moderate_total = issue_counts["MAJOR"] + issue_counts["WARNING"]
    verdict_class, verdict_text = determine_verdict(issue_counts, markdown_text)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = extract_meta_fields(markdown_text)
    template = load_template()
    context = {
        "PROJECT_ID": html.escape(project_id),
        "TITLE": html.escape(title),
        "PROJECT_NAME": html.escape(meta.get("项目名称", "")),
        "AUDIT_DATE": html.escape(meta.get("审核日期", "")),
        "AUDIT_VERSION": html.escape(meta.get("审核版本", "") or meta.get("审核方式", "") or meta.get("审核范围", "")),
        "GENERATED_AT": html.escape(generated_at),
        "SEVERE_TOTAL": str(severe_total),
        "MODERATE_TOTAL": str(moderate_total),
        "INFO_COUNT": str(issue_counts["INFO"]),
        "ANALYSIS_COUNT": str(len(analysis_rows)),
        "TOC_HTML": build_toc(markdown_text),
        "ISSUE_TOTAL": str(issue_total),
        "FATAL_COUNT": str(issue_counts["FATAL"]),
        "CRITICAL_COUNT": str(issue_counts["CRITICAL"]),
        "MAJOR_COUNT": str(issue_counts["MAJOR"]),
        "WARNING_COUNT": str(issue_counts["WARNING"]),
        "MAJOR_WARNING_COUNT": str(issue_counts["MAJOR"] + issue_counts["WARNING"]),
        "VERDICT_CLASS": verdict_class,
        "VERDICT_TEXT": html.escape(verdict_text),
        "CONTENT_HTML": reorder_sections(render_markdown(markdown_text)),
    }
    return render_template(template, context)


def main() -> int:
    args = parse_args()
    markdown_path, html_path = resolve_paths(args.input_path, args.output)
    markdown_text = markdown_path.read_text(encoding="utf-8")
    rendered = build_html(markdown_text, markdown_path)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(rendered, encoding="utf-8")
    print(f"HTML报告已生成: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
