#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""将 final_review_report.md 渲染为可交付的 audit_report.html。"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Mapping, Sequence

from html_presentation_contract import (
    INVENTORY_LEGEND_TEXT,
    validate_html_presentation_text,
)
from policy_loader import load_policy


TEMPLATE_PATH = Path(__file__).parent.parent / "report_templates" / "final_review_report_template.html"
POLICY_PATH = Path(__file__).parent.parent / "policy" / "audit_policy.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 final_review_report.md 渲染为 audit_report.html"
    )
    parser.add_argument("input_path", help="审核目录或 final_review_report.md 文件路径")
    parser.add_argument("--output", "-o", help="输出 HTML 文件路径（默认：审核目录/audit_report.html）")
    return parser.parse_args()


# 支持的审核报告文件名（按优先级）
_REPORT_NAMES = ('final_review_report.md', 'REVIEW_REPORT.md')


_READER_FACING_AUDIT_REFS = (
    (r"`?agent_results/score_basis_review\.md`?", "评分裁量核验记录"),
    (r"`?mechanical_check_result\.json`?", "机械核验记录"),
    (r"`?arbitration_resolution\.md`?", "审核裁决记录"),
    (r"`?project_structure\.json`?", "交付结构核验记录"),
    (r"`?visual_audit_result\.json`?", "图件核验记录"),
    (r"`?agent_results/visual_closure\.md`?", "图件核验结论"),
)
_EXTRACTION_LOCATION_DISCLAIMER_RE = re.compile(
    r"(?:。|；)?抽取元数据未提供稳定页码，故以章节(?:、图号)?和原文短句定位。"
)
_SCORE_BASIS_DISCLAIMER_RE = re.compile(
    r"（负责人按既有正式 BLOCK 审核的统一历史基线裁量给出；"
    r"该基线不是严重度自动换算公式，依据见\s*`?agent_results/score_basis_review\.md`?）"
)
_INTERNAL_EVIDENCE_ITEM_RE = re.compile(
    r"(?m)^(?P<bullet>[-*+])\s+\*\*(?:交付证据|证据文件位置)\*\*[:：](?P<body>.*)(?:\n|$)"
)
_EXTRACTED_IMAGE_REF_RE = re.compile(
    r"`?(?:images/)?image_\d+(?:\.(?:png|jpe?g|tiff?|bmp|webp))?`?",
    flags=re.IGNORECASE,
)
_REPORT_FIGURE_PREFIX_RE = re.compile(r"`?report figure\s+", flags=re.IGNORECASE)
_FIGURE_POSITION_RE = re.compile(
    r"[（(](?P<figure>Figure\s+\d+(?:\.\d+)?)\s+(?P<panel>[A-Za-z])\s+position[）)]",
    flags=re.IGNORECASE,
)
_CONCRETE_ERROR_HEADING_RE = re.compile(r"^具体错误\s*\d+\s*[：:]\s*\S")


def _drop_internal_evidence_columns(markdown_text: str) -> str:
    """Remove reader-facing table columns that only point to audit internals."""
    lines = markdown_text.splitlines()
    index = 0
    while index + 1 < len(lines):
        if not is_table_block(lines, index):
            index += 1
            continue

        header = split_table_cells(lines[index])
        hidden_columns = [
            position
            for position, cell in enumerate(header)
            if _strip_markdown_markup(cell).strip() in {"证据路径", "证据文件位置"}
        ]
        if not hidden_columns:
            index += 1
            continue

        end = index + 2
        while end < len(lines) and lines[end].strip().startswith("|"):
            end += 1
        for row_index in range(index, end):
            cells = split_table_cells(lines[row_index])
            retained = [cell for position, cell in enumerate(cells) if position not in hidden_columns]
            lines[row_index] = "| " + " | ".join(retained) + " |"
        index = end
    return "\n".join(lines)


def _reader_facing_evidence_item(match: re.Match[str]) -> str:
    """Delivery inventory is rendered as a dedicated section, not repeated in findings."""
    return ""


def _reader_hidden_internal_headings() -> tuple[str, ...]:
    policy = load_policy()
    presentation = policy.get("reader_html_presentation_policy")
    if not isinstance(presentation, dict):
        raise ValueError("reader HTML presentation policy is missing")
    configured = presentation.get("hidden_internal_heading_terms")
    if not isinstance(configured, list) or not configured or any(
        not isinstance(value, str) or not value.strip() for value in configured
    ):
        raise ValueError("reader hidden-internal-heading policy is missing or invalid")
    return tuple(value.strip() for value in configured)


def _drop_markdown_sections_by_heading(
    markdown_text: str,
    hidden_headings: Sequence[str],
) -> str:
    """Remove configured workpaper-only sections from the reader projection."""
    hidden = set(hidden_headings)
    lines = markdown_text.splitlines(keepends=True)
    retained: list[str] = []
    index = 0
    heading_re = re.compile(r"^(?P<marks>#{1,6})[ \t]+(?P<title>.*?)[ \t]*(?:\r?\n)?$")
    while index < len(lines):
        match = heading_re.match(lines[index])
        if not match:
            retained.append(lines[index])
            index += 1
            continue
        title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group("title")).strip()
        if title not in hidden:
            retained.append(lines[index])
            index += 1
            continue

        hidden_level = len(match.group("marks"))
        index += 1
        while index < len(lines):
            next_match = heading_re.match(lines[index])
            if next_match and len(next_match.group("marks")) <= hidden_level:
                break
            index += 1
    return "".join(retained)


def reader_facing_markdown(markdown_text: str) -> str:
    """Hide internal audit artifact names and extraction-process notes from delivered HTML."""
    text = _drop_markdown_sections_by_heading(
        markdown_text,
        _reader_hidden_internal_headings(),
    )
    text = _EXTRACTION_LOCATION_DISCLAIMER_RE.sub("", text)
    text = _SCORE_BASIS_DISCLAIMER_RE.sub("", text)
    text = _INTERNAL_EVIDENCE_ITEM_RE.sub(_reader_facing_evidence_item, text)
    text = _EXTRACTED_IMAGE_REF_RE.sub("相关图件", text)
    text = _drop_internal_evidence_columns(text)
    for pattern, label in _READER_FACING_AUDIT_REFS:
        text = re.sub(pattern, label, text, flags=re.IGNORECASE)
    text = _REPORT_FIGURE_PREFIX_RE.sub("图件：", text)
    return _FIGURE_POSITION_RE.sub(_reader_facing_figure_position, text)


def _reader_facing_figure_position(match: re.Match[str]) -> str:
    return f"（{match.group('figure')} {match.group('panel').upper()} 面板）"


_REVOCATION_LEDGER_RE = re.compile(
    r"^###\s+撤销裁定（保留原始记录与反证）\s*$[\s\S]*?(?=^##\s+|\Z)",
    flags=re.MULTILINE,
)


def defer_revocation_ledger(markdown_text: str) -> str:
    """将撤销裁定作为末尾留痕章节，避免打断正式发现的阅读顺序。"""
    match = _REVOCATION_LEDGER_RE.search(markdown_text)
    if not match:
        return markdown_text
    ledger = re.sub(r"^###\s+", "## 六、", match.group(0), count=1).strip()
    remaining = (markdown_text[:match.start()] + markdown_text[match.end():]).rstrip()
    return f"{remaining}\n\n{ledger}\n"


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
    escaped = re.sub(r"(?<![\w/])\*(?![\s*/])([^*\n]+?)(?<![\s*/])\*(?![\w/])", r"<em>\1</em>", escaped)
    # Severity 关键词加彩色标签
    _sev_colors = {"FATAL": "sev-tag-fatal", "CRITICAL": "sev-tag-critical",
                   "MAJOR": "sev-tag-major", "WARNING": "sev-tag-warning", "INFO": "sev-tag-info"}
    for kw, cls in _sev_colors.items():
        escaped = re.sub(rf'\b({kw})\b', rf'<span class="{cls}">\1</span>', escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    # 正式交付 HTML 必须自包含：仅允许同页锚点，避免读者侧依赖未交付的
    # Markdown/JSON 或任何外部资源。
    link_pattern = re.compile(r"\[([^\[\]]+)\]\(((?:[^()]|\([^)]*\))+)\)")

    def _safe_link(m):
        label, url = m.group(1), m.group(2)
        if not url.strip().startswith("#"):
            return label
        return f'<a href="{html.escape(url, quote=True)}">{label}</a>'
    escaped = link_pattern.sub(_safe_link, escaped)
    return escaped


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "section"


def _display_heading_text(text: str, level: int) -> str:
    plain = _strip_markdown_markup(text).strip()
    if level == 2 and plain == "审核结果表":
        return "核心问题清单与整改建议"
    return text


def is_table_block(lines: Sequence[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return lines[index].strip().startswith("|") and re.match(r"^\|?[\s:-]+\|[\s|:-]*$", lines[index + 1].strip()) is not None


def split_table_cells(line: str) -> List[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]

    cells: List[str] = []
    buf: List[str] = []
    in_code = False
    escaped = False
    for ch in text:
        if escaped:
            buf.append(ch if ch == "|" else "\\" + ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "`":
            in_code = not in_code
            buf.append(ch)
            continue
        if ch == "|" and not in_code:
            cells.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    if escaped:
        buf.append("\\")
    cells.append("".join(buf).strip())
    return cells


def _fit_table_cells(cells: List[str], expected: int) -> List[str]:
    if expected <= 0:
        return cells
    if len(cells) > expected:
        return cells[: expected - 1] + [" | ".join(cells[expected - 1:])]
    if len(cells) < expected:
        return cells + [""] * (expected - len(cells))
    return cells


def parse_table_row(line: str) -> List[str]:
    # 先将转义管道符 \| 替换为占位符，split 后再还原
    return [apply_inline_formatting(cell) for cell in split_table_cells(line)]


_REPORT_TEXT_REF_RE = re.compile(
    r"`?(?:[^\s`|;；，、]*[\\/])?report_text\.txt`?\s+"
    r"((?:L\s*\d+(?:\s*-\s*L?\s*\d+)?\s*(?:[,，、]\s*)?)*)",
    flags=re.IGNORECASE,
)
_LINE_RANGE_RE = re.compile(r"L\s*(\d+)(?:\s*-\s*L?\s*(\d+))?", flags=re.IGNORECASE)
_CODE_REF_RE = re.compile(
    r"\b(?:[\w.-]+[\\/])*[\w.-]+\.(?:r|R|py|Rmd|qmd|ipynb)\b"
)
_MODULE_TOKEN_RE = re.compile(
    r"(?<![\w.])((?:result[\\/])?\d{2}(?:[_\-.][A-Za-z0-9][A-Za-z0-9_.-]*|[A-Za-z][A-Za-z0-9_.-]*)(?:[\\/][^\s`|;；，、]*)?)"
)


def _is_location_header(text: str) -> bool:
    normalized = _strip_markdown_markup(text).strip().strip(":：").lower()
    return "位置" in normalized or "location" in normalized


def _load_report_text_lines(source_dir: Path | None) -> list[str] | None:
    if source_dir is None:
        return None
    report_text_path = source_dir / "report_text.txt"
    if not report_text_path.exists():
        return None
    try:
        return report_text_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return report_text_path.read_text(encoding="utf-8-sig").splitlines()


def _normalize_ref_path(path: str) -> str:
    normalized = re.sub(r"[*`~]", "", path).replace("\\", "/")
    normalized = re.sub(r"/+", "/", normalized)
    return normalized.strip(" `\"'；;，,、。.")


def _load_project_index(source_dir: Path | None) -> dict[str, list[str]]:
    data = _load_project_structure(source_dir)
    if not data:
        return {"modules": [], "codes": []}

    modules: list[str] = []
    for module in data.get("modules", []):
        path = _normalize_ref_path(str(module.get("path") or module.get("name") or ""))
        if path and path not in modules:
            modules.append(path)

    codes: list[str] = []
    for code_file in data.get("code_files", []):
        path = _normalize_ref_path(str(code_file.get("path") or ""))
        if path and path not in codes:
            codes.append(path)

    return {"modules": modules, "codes": codes}


def _load_project_structure(source_dir: Path | None) -> dict | None:
    if source_dir is None:
        return None
    project_structure_path = source_dir / "project_structure.json"
    if not project_structure_path.exists():
        return None
    try:
        return json.loads(project_structure_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


_IMAGE_TOKEN_PATTERN = (
    r"`?(?:images/)?image_\d+(?:\.(?:png|jpe?g|tiff?|bmp|webp))?`?"
)
_IMAGE_TOKEN_RE = re.compile(_IMAGE_TOKEN_PATTERN, flags=re.IGNORECASE)
_IMAGE_RANGE_RE = re.compile(
    _IMAGE_TOKEN_PATTERN
    + r"\s*(?:—|－|至|到|-)\s*"
    + _IMAGE_TOKEN_PATTERN,
    flags=re.IGNORECASE,
)


def _load_json_object(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_framework_version() -> str:
    """Read the delivery-facing framework version from the authoritative policy."""
    policy = _load_json_object(POLICY_PATH)
    version = str((policy or {}).get("framework_version") or "未标注版本").strip()
    return version or "未标注版本"


def _figure_title(item: dict) -> str:
    """Return a reader-facing figure title without exposing extraction filenames."""
    figure_id = str(item.get("figure_id") or "").strip()
    for ref in item.get("report_refs") or []:
        context = str(ref.get("context") or "")
        if not context or not figure_id:
            continue
        match = re.search(rf"(?m)^{re.escape(figure_id)}\s+([^\n]+)", context)
        if match:
            return match.group(1).strip()

    caption = re.sub(r"\s+", " ", str(item.get("caption") or "")).strip()
    if caption:
        return caption[:72].rstrip("，；。 ") + ("…" if len(caption) > 72 else "")
    return ""


def _short_figure_title(title: str, figure_id: str = "", limit: int = 48) -> str:
    """Use only the identifying title sentence in delivery-facing figure references."""
    compact_title = re.sub(r"\s+", " ", title).strip()
    if figure_id:
        compact_title = re.sub(rf"^{re.escape(figure_id)}\s*[：:.]?\s*", "", compact_title)
    first_sentence = re.split(r"[。；;]", compact_title, maxsplit=1)[0]
    return first_sentence[:limit].rstrip("，；。 ") + ("…" if len(first_sentence) > limit else "")


def _load_visual_figure_index(source_dir: Path | None) -> dict[str, str]:
    if source_dir is None:
        return {}
    try:
        payload = json.loads((source_dir / "visual_audit_checklist.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    items = payload if isinstance(payload, list) else payload.get("checklist", payload.get("images", []))
    if not isinstance(items, list):
        return {}

    report_lines = _load_report_text_lines(source_dir) or []
    report_titles: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        figure_id = str(item.get("figure_id") or "").strip()
        if not figure_id or figure_id in report_titles:
            continue
        title_pattern = re.compile(rf"^\s*{re.escape(figure_id)}\s+(.+)$")
        for line in report_lines:
            match = title_pattern.match(line)
            if match:
                report_titles[figure_id] = match.group(1).strip()
                break

    index: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").lower()
        figure_id = str(item.get("figure_id") or "").strip()
        if not filename or not figure_id:
            continue
        title = report_titles.get(figure_id) or _figure_title(item)
        short_title = _short_figure_title(title, figure_id)
        index[filename] = f"{figure_id}｜{short_title}" if short_title else figure_id
    return index


def humanize_image_references(text: str, source_dir: Path | None) -> str:
    """Replace DOCX extraction filenames with report figure labels for recipients."""
    figure_index = _load_visual_figure_index(source_dir)
    if not figure_index:
        return text

    def label_for_token(token: str) -> str:
        filename = re.sub(r"`", "", token).replace("\\", "/").rsplit("/", 1)[-1].lower()
        if "." not in filename:
            filename += ".png"
        return figure_index.get(filename, "报告图件（未建立图号映射）")

    def replace_range(match: re.Match) -> str:
        labels: list[str] = []
        for token_match in _IMAGE_TOKEN_RE.finditer(match.group(0)):
            label = label_for_token(token_match.group(0))
            if label not in labels:
                labels.append(label)
        return "、".join(labels)

    display_text = _IMAGE_RANGE_RE.sub(replace_range, text)
    return _IMAGE_TOKEN_RE.sub(lambda match: label_for_token(match.group(0)), display_text)


def build_canonical_findings_html(source_dir: Path | None) -> str:
    """Render sealed findings and every raw-finding disposition."""
    if source_dir is None:
        return ""
    payload = _load_json_object(source_dir / "agent_results" / "arbitration" / "arbitration_resolution.json")
    if not payload:
        return ""
    findings = payload.get("canonical_findings")
    if not isinstance(findings, list) or not findings:
        return ""

    cards: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_id = str(finding.get("canonical_id") or "未编号")
        severity = str(finding.get("severity") or "INFO").upper()
        module = str(finding.get("module") or "未标注模块")
        claim = humanize_image_references(str(finding.get("claim") or ""), source_dir)
        mechanism = humanize_image_references(str(finding.get("error_mechanism") or ""), source_dir)
        evidence = humanize_image_references(str(finding.get("evidence_object") or ""), source_dir)
        repair = humanize_image_references(str(finding.get("repair_path") or ""), source_dir)
        description = humanize_image_references(str(finding.get("description") or ""), source_dir)
        cards.append(
            '<details class="finding-card" open>'
            '<summary>'
            f'<span class="finding-id">{html.escape(finding_id)}</span>'
            f'<span class="sev-tag-{html.escape(severity.lower())}">{html.escape(severity)}</span>'
            f'<span>{html.escape(module)}</span>'
            '</summary>'
            '<dl class="finding-fields">'
            f'<dt>被审核主张</dt><dd>{apply_inline_formatting(claim)}</dd>'
            f'<dt>问题机制</dt><dd>{apply_inline_formatting(mechanism)}</dd>'
            f'<dt>证据依据</dt><dd>{apply_inline_formatting(evidence)}</dd>'
            f'<dt>整改要求</dt><dd>{apply_inline_formatting(repair)}</dd>'
            f'<dt>裁定说明</dt><dd>{apply_inline_formatting(description)}</dd>'
            '</dl>'
            '</details>'
        )

    if not cards:
        return ""
    dispositions = payload.get("raw_dispositions")
    disposition_rows: list[str] = []
    if isinstance(dispositions, list):
        for item in dispositions:
            if not isinstance(item, dict):
                continue
            raw_finding_id = str(item.get("raw_finding_id") or "未编号")
            decision = str(item.get("decision") or "未标注")
            canonical_ids = item.get("canonical_ids")
            mapped_ids = ", ".join(str(value) for value in canonical_ids) if isinstance(canonical_ids, list) else ""
            reason = str(item.get("reason") or "未说明")
            disposition_rows.append(
                "<tr>"
                f"<td><code>{html.escape(raw_finding_id)}</code></td>"
                f"<td>{html.escape(decision)}</td>"
                f"<td>{html.escape(mapped_ids or '—')}</td>"
                f"<td>{apply_inline_formatting(reason)}</td>"
                "</tr>"
            )
    ledger_html = ""
    if disposition_rows:
        ledger_html = (
            '<section class="raw-disposition-ledger">'
            f"<h3>原始发现处置台账（{len(disposition_rows)} 条）</h3>"
            "<table><thead><tr><th>原始发现</th><th>处置</th><th>正式问题映射</th><th>裁定理由</th>"
            "</tr></thead><tbody>"
            f"{''.join(disposition_rows)}"
            "</tbody></table></section>"
        )
    return (
        '<section class="findings-section" id="正式裁定详情">'
        '<h2>正式裁定详情</h2>'
        f'<p class="findings-desc">以下 {len(cards)} 项为正式裁定；其后的台账逐条列出全部原始发现的保留、合并或撤销理由。</p>'
        f'<div class="findings-list">{"".join(cards)}</div>'
        f"{ledger_html}"
        '</section>'
    )


def _extract_report_text_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for ref_match in _REPORT_TEXT_REF_RE.finditer(text):
        for line_match in _LINE_RANGE_RE.finditer(ref_match.group(1)):
            start = int(line_match.group(1))
            end = int(line_match.group(2) or start)
            if start > end:
                start, end = end, start
            ranges.append((start, end))
    return ranges


def _strip_report_text_refs(text: str) -> str:
    stripped = _REPORT_TEXT_REF_RE.sub("", text)
    stripped = re.sub(r"\s*[;；]\s*", "；", stripped)
    stripped = re.sub(r"\s*[,，、]\s*", "，", stripped)
    stripped = stripped.strip(" ；;，,、。.")
    stripped = re.sub(r"(?:证据文件位置|原报告位置|位置)\s*[:：]\s*$", "", stripped)
    return stripped.strip(" ；;，,、。.")


def _remaining_ref_label(text: str) -> str:
    plain = _strip_markdown_markup(text)
    if re.search(r"[/\\]|\b[\w.-]+\.(?:r|R|py|csv|tsv|xlsx|xls|json|md|txt)\b|^r\.", plain):
        return "文件"
    return "定位"


def _is_issue_context(context_text: str) -> bool:
    plain = _strip_markdown_markup(context_text)
    return bool(
        re.search(
            r"(原文短句|不通过|不充分|有问题|误写|错误|不一致|缺少|为空|残留|错配|需修|未形成|无法支撑)",
            plain,
        )
    )


def _source_heading(context_text: str) -> str:
    if _is_issue_context(context_text):
        return "原文错句"
    return "原文关键句"


_KEYWORD_RE = re.compile(
    r"\d+(?:\.\d+)+|[A-Za-z0-9][A-Za-z0-9_.+-]*[A-Za-z][A-Za-z0-9_.+-]*|[\u4e00-\u9fff]{2,}"
)
_EXCERPT_STOPWORDS = {
    "report",
    "text",
    "txt",
    "结果",
    "文件",
    "证据",
    "位置",
    "报告",
    "正文",
    "问题",
    "通过",
    "充分",
    "覆盖",
    "部分",
    "分析",
    "存在",
    "显示",
    "进行",
    "本项目",
    "本研究",
    "原文短句",
    "快速检索词",
}


def _keyword_source(text: str) -> str:
    plain = _strip_report_text_refs(_strip_markdown_markup(text))
    focused_parts: list[str] = []
    for label in ("原文短句", "问题说明", "错误说明", "核心矛盾"):
        pattern = (
            rf"{label}\s*[:：]\s*(.*?)(?=\s+(?:原文短句|问题说明|错误说明|核心矛盾|"
            r"证据文件位置|证据|快速检索词|原报告位置|位置|应为|修正|建议|性质|方法段|结果段)\s*[:：]|$)"
        )
        focused_parts.extend(match.group(1) for match in re.finditer(pattern, plain))
    return " ".join(focused_parts) or plain


def _context_keywords(text: str) -> set[str]:
    plain = _keyword_source(text)
    keywords: set[str] = set()
    for match in _KEYWORD_RE.finditer(plain):
        token = match.group(0).strip("._-+").lower()
        if len(token) < 2 or token in _EXCERPT_STOPWORDS:
            continue
        if re.fullmatch(r"l\d+", token):
            continue
        keywords.add(token)
    return keywords


def _select_excerpt_line_numbers(
    ranges: Sequence[tuple[int, int]],
    report_lines: Sequence[str],
    context_text: str = "",
    limit: int | None = None,
) -> tuple[list[int], int]:
    candidates: list[tuple[int, int]] = []
    seen: set[int] = set()
    keywords = _context_keywords(context_text)
    if limit is None:
        limit = 2
    for start, end in ranges:
        for line_no in range(start, end + 1):
            if line_no in seen or line_no < 1 or line_no > len(report_lines):
                continue
            seen.add(line_no)
            line = report_lines[line_no - 1].strip()
            if not line:
                continue
            lower_line = line.lower()
            score = sum(1 + min(len(keyword) // 5, 3) for keyword in keywords if keyword in lower_line)
            candidates.append((line_no, score))

    if not candidates:
        return [], 0

    positive_candidates = [candidate for candidate in candidates if candidate[1] > 0]
    if positive_candidates:
        selected = sorted(positive_candidates, key=lambda item: (-item[1], item[0]))[:limit]
        selected_numbers = sorted(line_no for line_no, _ in selected)
    else:
        selected_numbers = [line_no for line_no, _ in candidates[:limit]]
    return selected_numbers, max(0, len(candidates) - len(selected_numbers))


def _best_keyword_span(text: str, keywords: set[str]) -> tuple[int, int] | None:
    lower_text = text.lower()
    matches: list[tuple[int, int, int, int]] = []
    for keyword in keywords:
        index = lower_text.find(keyword)
        if index >= 0:
            is_section_no = 1 if re.fullmatch(r"\d+(?:\.\d+)+", keyword) else 0
            matches.append((index, index + len(keyword), len(keyword), is_section_no))
    if not matches:
        return None
    start, end, _, _ = sorted(matches, key=lambda item: (-item[3], -item[2], item[0]))[0]
    return start, end


def _snippet_around_keyword(text: str, keywords: set[str], radius: int = 6, max_chars: int = 36) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""

    span = _best_keyword_span(compact, keywords)
    if span is None:
        snippet = compact[:max_chars].rstrip()
        if len(compact) > max_chars:
            snippet += "…"
        return html.escape(snippet)

    hit_start, hit_end = span
    start = max(0, hit_start - radius)
    end = min(len(compact), hit_end + radius)
    if end - start > max_chars:
        center = (hit_start + hit_end) // 2
        start = max(0, center - max_chars // 2)
        end = min(len(compact), start + max_chars)
        start = max(0, end - max_chars)
    if (
        start > 0
        and re.match(r"[A-Za-z0-9]", compact[start])
        and re.match(r"[A-Za-z0-9]", compact[start - 1])
    ):
        boundary = max(compact.rfind(" ", 0, start), compact.rfind("(", 0, start), compact.rfind("（", 0, start))
        if boundary >= 0 and start - boundary <= 10:
            start = boundary + 1
        elif boundary < 0 and start <= 10:
            start = 0

    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(compact) else ""
    before = html.escape(compact[start:hit_start])
    hit = html.escape(compact[hit_start:hit_end])
    after = html.escape(compact[hit_end:end])
    return f'{prefix}{before}<mark class="source-hit">{hit}</mark>{after}{suffix}'


def _render_report_text_excerpts(
    ranges: Sequence[tuple[int, int]], report_lines: Sequence[str], context_text: str = ""
) -> str:
    line_numbers, _omitted = _select_excerpt_line_numbers(ranges, report_lines, context_text)
    keywords = _context_keywords(context_text)
    parts = ['<div class="source-excerpt">']
    for line_no in line_numbers:
        line_text = _snippet_around_keyword(report_lines[line_no - 1], keywords)
        parts.append(
            '<div class="source-line">'
            f'<span class="source-line-no">L{line_no}</span>'
            f'<span class="source-line-text">{line_text}</span>'
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _format_location_cell(
    cell: str, report_lines: Sequence[str] | None, context_text: str = ""
) -> str:
    ranges = _extract_report_text_ranges(cell)
    if not ranges or report_lines is None:
        return apply_inline_formatting(cell)

    remaining_refs = _strip_report_text_refs(cell)
    excerpt_html = _render_report_text_excerpts(ranges, report_lines, context_text or cell)
    if 'class="source-line"' not in excerpt_html:
        return apply_inline_formatting(cell)

    parts = ['<div class="location-cell">']
    parts.append(f'<div class="source-heading">{_source_heading(context_text or cell)}</div>')
    parts.append(excerpt_html)
    if remaining_refs:
        ref_label = _remaining_ref_label(remaining_refs)
        display_refs = remaining_refs
        if ref_label == "定位":
            display_refs = re.sub(
                r"^(?:证据文件位置|原报告位置|位置)\s*[:：]\s*", "", display_refs
            ).strip(" ；;，,、。.")
        if not display_refs:
            parts.append("</div>")
            return "".join(parts)
        parts.append(
            f'<div class="file-ref"><span>{ref_label}</span>'
            f"{apply_inline_formatting(display_refs)}</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _should_format_report_text_location(text: str) -> bool:
    """Avoid turning mixed finding paragraphs into a location card.

    Table "位置" cells usually contain only locators and file references. Detailed
    finding paragraphs often combine locator, evidence, and remediation labels in
    one Markdown paragraph; formatting those as location cells makes the evidence
    text collapse into the file-ref area.
    """
    plain = _strip_markdown_markup(text)
    has_locator_label = bool(re.search(r"(?:^|\s)(?:位置|原报告位置|证据文件位置)\s*[:：]", plain))
    has_followup_label = bool(re.search(r"(?:证据|复核证据|整改|整改建议|建议)\s*[:：]", plain))
    return not (has_locator_label and has_followup_label)


def _format_cell(
    cell: str, report_lines: Sequence[str] | None, context_text: str = ""
) -> str:
    if (
        report_lines is not None
        and _extract_report_text_ranges(cell)
        and _should_format_report_text_location(cell)
    ):
        return _format_location_cell(cell, report_lines, context_text)
    return apply_inline_formatting(cell)


def _dedupe_refs(refs: Sequence[str], limit: int = 3) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        normalized = _normalize_ref_path(ref)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
        if len(deduped) >= limit:
            break
    return deduped


def _module_ref_key(ref: str) -> str:
    normalized = _normalize_ref_path(ref)
    if normalized.lower().startswith("result/"):
        normalized = normalized.split("/", 1)[1]
    return normalized.split("/", 1)[0].lower()


def _dedupe_module_refs(refs: Sequence[str], limit: int = 3) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    file_ext_re = re.compile(r"\.(?:csv|tsv|xlsx?|pdf|png|jpg|jpeg|r|py|txt|json)$", re.IGNORECASE)
    for ref in refs:
        normalized = _normalize_ref_path(ref)
        if not normalized:
            continue
        if "/" not in normalized and file_ext_re.search(normalized):
            continue
        key = _module_ref_key(normalized)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
        if len(deduped) >= limit:
            break
    return deduped


def _ref_number(ref: str) -> int | None:
    match = re.search(r"(?:^|/|[._-])(\d{2})(?=[._A-Za-z-])", _normalize_ref_path(ref))
    return int(match.group(1)) if match else None


def _ref_tokens(ref: str) -> set[str]:
    text = re.sub(r"^(?:result/)?(?:r[._-])?\d{2}[_ .-]?", "", _normalize_ref_path(ref).lower())
    stop_tokens = {"gene", "genes", "result", "script", "figure", "table", "附件"}
    return {
        token
        for token in re.split(r"[^a-z0-9]+", text)
        if len(token) >= 3 and not token.isdigit() and token not in stop_tokens
    }


def _extract_code_refs(text: str) -> list[str]:
    plain = re.sub(r"[*`~]", "", text)
    return _dedupe_refs(match.group(0) for match in _CODE_REF_RE.finditer(plain))


def _extract_module_refs(text: str, project_index: dict[str, list[str]]) -> list[str]:
    plain = _normalize_ref_path(text)
    refs: list[str] = []
    plain_lower = plain.lower()
    for module_path in project_index.get("modules", []):
        module = _normalize_ref_path(module_path)
        if not module:
            continue
        candidates = {module, module.split("/")[-1]}
        for candidate in candidates:
            if not candidate:
                continue
            pattern = rf"(?<![\w.]){re.escape(candidate.lower())}(?=$|[/\s；;，、|])"
            if re.search(pattern, plain_lower):
                refs.append(module)
                break

    for match in _MODULE_TOKEN_RE.finditer(plain):
        token = match.group(1)
        if "report_text.txt" in token.lower():
            continue
        parts = token.split("/")
        if parts and parts[0].lower() == "result" and len(parts) > 1:
            token = "result/" + parts[1]
        elif parts:
            token = parts[0]
        refs.append(token)
    return _dedupe_module_refs(refs)


def _infer_module_refs(
    explicit_code_refs: Sequence[str], row_text: str, project_index: dict[str, list[str]]
) -> list[str]:
    if not explicit_code_refs:
        return []
    code_numbers = {_ref_number(ref) for ref in explicit_code_refs}
    code_numbers.discard(None)
    code_tokens = set().union(*(_ref_tokens(ref) for ref in explicit_code_refs))
    row_tokens = _ref_tokens(row_text)

    scored: list[tuple[int, int, str]] = []
    number_fallbacks: list[str] = []
    for module_path in project_index.get("modules", []):
        module = _normalize_ref_path(module_path)
        module_number = _ref_number(module)
        module_tokens = _ref_tokens(module)
        if module_number in code_numbers:
            number_fallbacks.append(module)
        token_score = len(module_tokens.intersection(code_tokens | row_tokens))
        if token_score:
            scored.append((-token_score, len(module), module))
    if scored:
        return _dedupe_module_refs([module for _, _, module in sorted(scored)[:1]])
    return _dedupe_module_refs(number_fallbacks[:1])


def _infer_module_refs_from_title(title: str, project_index: dict[str, list[str]]) -> list[str]:
    title_plain = _strip_markdown_markup(title).lower()
    rules = [
        (("数据集", "数据来源", "分组"), ("rawdata",)),
        (("差异",), ("deg", "deseq")),
        (("富集",), ("enrichment",)),
        (("ppi", "mcode"), ("ppi",)),
        (("机器学习",), ("machine_learning",)),
        (("表达", "预后"), ("expression", "cox")),
        (("roc",), ("roc",)),
        (("免疫",), ("immune",)),
        (("gsea",), ("gsea",)),
        (("网络构建", "化合物-靶点网络"), ("network", "ligand")),
        (("对接",), ("docking",)),
        (("动力学", "md"), ("md",)),
    ]
    wanted: tuple[str, ...] = ()
    for title_terms, module_terms in rules:
        if any(term in title_plain for term in title_terms):
            wanted = module_terms
            break
    if not wanted:
        return []

    refs = [
        module
        for module in project_index.get("modules", [])
        if any(term in _normalize_ref_path(module).lower() for term in wanted)
    ]
    return _dedupe_module_refs(refs[:2])


def _infer_code_refs(
    module_refs: Sequence[str],
    explicit_code_refs: Sequence[str],
    project_index: dict[str, list[str]],
    row_text: str = "",
) -> list[str]:
    if explicit_code_refs:
        return _dedupe_refs(explicit_code_refs)

    refs = list(explicit_code_refs)
    codes = project_index.get("codes", [])
    row_tokens = _ref_tokens(row_text)

    for module_ref in module_refs:
        module_number = _ref_number(module_ref)
        module_tokens = _ref_tokens(module_ref)
        number_matches: list[str] = []
        token_matches: list[str] = []
        for code in codes:
            code_norm = _normalize_ref_path(code)
            code_name = code_norm.split("/")[-1].lower()
            code_number = _ref_number(code_name)
            code_tokens = _ref_tokens(code_name)
            token_hit = bool(code_tokens.intersection(module_tokens | row_tokens))
            if code_number == module_number and token_hit:
                number_matches.append(code_norm)
            elif token_hit and code_tokens.intersection(module_tokens):
                token_matches.append(code_norm)
        refs.extend(number_matches or token_matches)
    return _dedupe_refs(refs)


def _format_ref_chips(label: str, refs: Sequence[str]) -> str:
    if not refs:
        return ""
    chips = "".join(f"<code>{html.escape(ref)}</code>" for ref in refs)
    return f'<div class="analysis-meta-line"><span>{label}</span>{chips}</div>'


def _format_analysis_point_cell(
    cell: str, raw_row: Sequence[str], project_index: dict[str, list[str]] | None
) -> str:
    title = apply_inline_formatting(cell)
    if not project_index:
        return title

    row_text = " ".join(raw_row)
    module_refs = _extract_module_refs(row_text, project_index)
    explicit_code_refs = _extract_code_refs(row_text)
    if not module_refs:
        module_refs = _infer_module_refs(explicit_code_refs, row_text, project_index)
    if not module_refs:
        module_refs = _infer_module_refs_from_title(cell, project_index)
    code_refs = _infer_code_refs(module_refs, explicit_code_refs, project_index, row_text)
    if not module_refs and not code_refs:
        return title

    parts = ['<div class="analysis-point-cell">', f'<div class="analysis-point-title">{title}</div>']
    parts.append(_format_ref_chips("文件夹", module_refs))
    parts.append(_format_ref_chips("代码", code_refs))
    if not code_refs:
        parts.append('<div class="analysis-meta-line muted"><span>代码</span>未见交付脚本</div>')
    parts.append("</div>")
    return "".join(parts)


def _table_row_class(row: Sequence[str]) -> str:
    joined = " ".join(row)
    for level in ("fatal", "critical", "major", "warning", "info"):
        if f"sev-tag-{level}" in joined:
            return f' class="row-{level}"'
    plain = re.sub(r"<[^>]+>", "", html.unescape(joined))
    if re.search(r"(不通过|不充分|未覆盖|不足)", plain):
        return ' class="row-fail"'
    if re.search(r"(有问题|部分充分|需修|待修|不一致)", plain):
        return ' class="row-problem"'
    return ""


def _header_key(text: str) -> str:
    return _strip_markdown_markup(text).strip().strip(":：").lower()


def _is_analysis_header(text: str) -> bool:
    return _header_key(text) == "分析点"


def _is_adjudication_reason_index(raw_header: Sequence[str]) -> bool:
    """裁定理由索引仅用于说明规则，不应从理由措辞推断严重度底色。"""
    header_keys = {_header_key(cell) for cell in raw_header}
    return "裁定规则" in header_keys and "核定理由" in header_keys


def _analysis_split_groups(raw_header: Sequence[str], analysis_col: int | None) -> tuple[list[int], list[int]]:
    if analysis_col is None:
        return [], []
    decision_terms = ("审核结果", "报告覆盖", "覆盖状态", "证据充分", "审核结论", "问题说明", "处置", "裁定", "判定")
    evidence_cols: list[int] = []
    decision_cols: list[int] = []
    for idx, header in enumerate(raw_header):
        if idx == analysis_col:
            continue
        key = _header_key(header)
        if any(term in key for term in decision_terms):
            decision_cols.append(idx)
        elif key in {"位置", "location", "证据", "evidence"} or "结果文件" in key:
            evidence_cols.append(idx)
    return evidence_cols, decision_cols


def _should_render_analysis_split(raw_header: Sequence[str], analysis_col: int | None) -> bool:
    evidence_cols, decision_cols = _analysis_split_groups(raw_header, analysis_col)
    return bool(evidence_cols and decision_cols)


def _tr_class_attr(base_attr: str, *extras: str) -> str:
    classes: list[str] = []
    match = re.search(r'class="([^"]+)"', base_attr)
    if match:
        classes.extend(match.group(1).split())
    for extra in extras:
        classes.extend(part for part in extra.split() if part)
    if not classes:
        return ""
    return f' class="{" ".join(dict.fromkeys(classes))}"'


def _format_analysis_fields(
    raw_header: Sequence[str],
    formatted_row: Sequence[str],
    columns: Sequence[int],
) -> str:
    fields: list[str] = []
    for col in columns:
        if col >= len(formatted_row):
            continue
        value = formatted_row[col]
        plain_value = re.sub(r"<[^>]+>", "", html.unescape(value)).strip()
        if not plain_value:
            continue
        label = html.escape(_strip_markdown_markup(raw_header[col]).strip().strip(":："))
        fields.append(
            '<div class="analysis-field">'
            f"<span>{label}</span>"
            f'<div class="analysis-field-body">{value}</div>'
            "</div>"
        )
    return "".join(fields) or '<span class="muted">未填写</span>'


def _render_analysis_split_table(
    raw_header: Sequence[str],
    raw_rows: Sequence[Sequence[str]],
    report_lines: Sequence[str] | None,
    project_index: dict[str, list[str]] | None,
    analysis_col: int,
) -> str:
    evidence_cols, decision_cols = _analysis_split_groups(raw_header, analysis_col)
    parts = [
        '<div class="table-wrap analysis-split-wrap"><table class="analysis-split-table">',
        "<thead><tr><th>分析点</th><th>类别</th><th>内容</th></tr></thead><tbody>",
    ]
    for raw_row in raw_rows:
        row_context = " | ".join(raw_row)
        formatted_row: list[str] = []
        for col, cell in enumerate(raw_row):
            if col == analysis_col:
                formatted_row.append(_format_analysis_point_cell(cell, raw_row, project_index))
            else:
                formatted_row.append(_format_cell(cell, report_lines, row_context))
        row_class = _table_row_class(formatted_row)
        analysis_cell = formatted_row[analysis_col]
        evidence_html = _format_analysis_fields(raw_header, formatted_row, evidence_cols)
        decision_html = _format_analysis_fields(raw_header, formatted_row, decision_cols)
        parts.append(f"<tr{_tr_class_attr(row_class, 'analysis-split-main')}>")
        parts.append(f'<td class="analysis-split-point" rowspan="2">{analysis_cell}</td>')
        parts.append('<td class="analysis-split-label">位置 / 证据</td>')
        parts.append(f'<td class="analysis-split-content">{evidence_html}</td>')
        parts.append("</tr>")
        parts.append(f"<tr{_tr_class_attr(row_class, 'analysis-split-sub')}>")
        parts.append('<td class="analysis-split-label">判断 / 处置</td>')
        parts.append(f'<td class="analysis-split-content">{decision_html}</td>')
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def _redundant_delivery_evidence_column(
    raw_header: Sequence[str], raw_rows: Sequence[Sequence[str]]
) -> int | None:
    """读者表中整列均为占位语时，移除没有信息量的“交付证据”列。"""
    for index, header in enumerate(raw_header):
        if _header_key(header) != "交付证据":
            continue
        values = [
            _strip_markdown_markup(row[index]).strip().rstrip("。.")
            for row in raw_rows
            if index < len(row)
        ]
        if values and all(value == "见本项交付证据" for value in values):
            return index
    return None


def render_table(
    lines: Sequence[str],
    start: int,
    report_lines: Sequence[str] | None = None,
    project_index: dict[str, list[str]] | None = None,
) -> tuple[str, int]:
    raw_header = split_table_cells(lines[start])
    raw_rows: list[list[str]] = []
    index = start + 2
    while index < len(lines) and lines[index].strip().startswith("|"):
        raw_row = _fit_table_cells(split_table_cells(lines[index]), len(raw_header))
        raw_rows.append(raw_row)
        index += 1

    redundant_col = _redundant_delivery_evidence_column(raw_header, raw_rows)
    if redundant_col is not None:
        raw_header = [cell for col, cell in enumerate(raw_header) if col != redundant_col]
        raw_rows = [
            [cell for col, cell in enumerate(row) if col != redundant_col]
            for row in raw_rows
        ]

    header = [apply_inline_formatting(cell) for cell in raw_header]
    location_columns = {idx for idx, cell in enumerate(raw_header) if _is_location_header(cell)}
    analysis_col = next(
        (
            idx
            for idx, cell in enumerate(raw_header)
            if _is_analysis_header(cell)
        ),
        None,
    )

    if _should_render_analysis_split(raw_header, analysis_col):
        return (
            _render_analysis_split_table(raw_header, raw_rows, report_lines, project_index, analysis_col or 0),
            index,
        )

    body_rows: List[List[str]] = []
    for raw_row in raw_rows:
        row_context = " | ".join(raw_row)
        formatted_row: list[str] = []
        for col, cell in enumerate(raw_row):
            if col == analysis_col:
                formatted_row.append(_format_analysis_point_cell(cell, raw_row, project_index))
            else:
                formatted_row.append(_format_cell(cell, report_lines, row_context))
        body_rows.append(formatted_row)

    parts = ["<div class=\"table-wrap\"><table>", "<thead><tr>"]
    parts.extend(f"<th>{cell}</th>" for cell in header)
    parts.append("</tr></thead><tbody>")
    neutral_reason_index = _is_adjudication_reason_index(raw_header)
    for row in body_rows:
        row_class = "" if neutral_reason_index else _table_row_class(row)
        parts.append(f"<tr{row_class}>")
        for col, cell in enumerate(row):
            cell_class = (
                ' class="location-cell-td"'
                if col in location_columns or 'class="location-cell"' in cell
                else ""
            )
            parts.append(f"<td{cell_class}>{cell}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts), index


_LABEL_CLASSES = {
    "位置": "label-context",
    "原报告位置": "label-context",
    "原文": "label-error",
    "原文短句": "label-error",
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
    "交付证据": "label-evidence",
    "核验来源": "label-evidence",
    "核验结论": "label-evidence",
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


_ORIGINAL_QUOTE_RE = re.compile(r"“([^”\n]+)”")
_SEARCH_QUOTE_FRAGMENT_RE = re.compile(
    r"\s*[；;]\s*可搜索原文短句[“\"](?P<quote>.+)[”\"](?:[。.]|$)\s*$"
)
_VERIFICATION_NOTE_RE = re.compile(
    r"^(?P<source>.+?)[；;]\s*核验说明\s*[:：]\s*(?P<conclusion>.+)$"
)
_GENERIC_DELIVERY_EVIDENCE_RE = re.compile(
    r"^\*{0,2}交付证据\*{0,2}\s*[:：]\s*见下列证据条目[。.]?\s*$"
)
_CODE_PATH_RE = re.compile(r"`([^`]+)`")
_VISUAL_EVIDENCE_REF_RE = re.compile(
    r"原始\s+(?:`[^`]+`|[A-Za-z0-9_.-]+)|图\s*\d+(?:\.\d+)*「[^」]+」"
)
_INSUFFICIENT_EVIDENCE_GROUP_RE = re.compile(
    r"^(?P<evidence>.+?)；(?P<resolution>上述(?P<count>[一二三四五六七八九十\d]+)项均为证据不足，.+)$"
)
_CN_COUNT_VALUES = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _format_original_quote_item(item_text: str, rendered: str) -> str:
    """Visually separate quoted source text from the audit interpretation."""
    plain = _strip_markdown_markup(item_text).strip()
    if not plain.startswith(("原文短句：", "原文短句:", "原文：", "原文:")):
        return rendered
    return _ORIGINAL_QUOTE_RE.sub(r'<span class="original-quote">“\1”</span>', rendered)


def _normalized_quote(text: str) -> str:
    return re.sub(r"\s+", "", text).strip("“”\"'。.!！?？")


def _original_quote_text(item_text: str) -> str | None:
    plain = _strip_markdown_markup(item_text).strip()
    match = re.match(r"^(?:原文短句|原文)\s*[:：]\s*(.+)$", plain)
    return _normalized_quote(match.group(1)) if match else None


def _search_quote_match(item_text: str) -> re.Match[str] | None:
    plain = _strip_markdown_markup(item_text).strip()
    if not plain.startswith(("原报告位置", "位置")):
        return None
    return _SEARCH_QUOTE_FRAGMENT_RE.search(item_text)


def _deduplicate_location_search_quotes(raw_items: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """保留独立原文短句，移除同文的“位置”项内搜索短句。"""
    deduplicated = list(raw_items)
    for index, (_, item_text) in enumerate(deduplicated):
        original_quote = _original_quote_text(item_text)
        if not original_quote:
            continue
        for previous_index in range(index - 1, -1, -1):
            previous_class, previous_text = deduplicated[previous_index]
            search_match = _search_quote_match(previous_text)
            if not search_match:
                continue
            if _normalized_quote(search_match.group("quote")) == original_quote:
                location_text = previous_text[:search_match.start()].rstrip(" ；;，,、。.")
                deduplicated[previous_index] = (previous_class, f"{location_text}。")
            break
    return deduplicated


def _remove_repeated_original_quote(source_text: str, original_quote: str) -> str:
    """Remove the report quote already shown in the dedicated original-quote field."""
    def replace(match: re.Match[str]) -> str:
        return "" if _normalized_quote(match.group(1)) == original_quote else match.group(0)

    stripped = _ORIGINAL_QUOTE_RE.sub(replace, source_text)
    stripped = re.sub(r"[：:]\s*[；;]\s*$", "", stripped)
    stripped = re.sub(r"[：:]\s*$", "", stripped)
    return stripped.strip(" ；;，,、。.")


def _code_paths(text: str) -> set[str]:
    return {path.strip() for path in _CODE_PATH_RE.findall(text) if path.strip()}


def _is_distinct_evidence_source(source_text: str, location_text: str) -> bool:
    """Keep evidence only when it adds a source beyond the report locator."""
    source_paths = _code_paths(source_text)
    location_paths = _code_paths(location_text)
    if source_paths:
        return not source_paths.issubset(location_paths)
    return bool(source_text)


def _labeled_raw_item(label: str, text: str) -> tuple[str, str]:
    css_class = _LABEL_CLASSES[label]
    return f' class="{css_class}"', f"**{label}**：{text}"


def _separate_verification_conclusions(
    raw_items: Sequence[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Split embedded verification notes into reader-facing source and conclusion fields.

    Audit exports often repeat the dedicated original quote in a nested delivery
    evidence item before appending ``核验说明``.  The quote is already displayed
    above, so retain only a distinct evidence source (when one exists) and make
    the reviewer reasoning an explicit ``核验结论`` field.
    """
    original_quote = next(
        (quote for _, item_text in raw_items if (quote := _original_quote_text(item_text))),
        None,
    )
    if not original_quote:
        return list(raw_items)

    location_text = next(
        (item_text for _, item_text in raw_items if _search_quote_match(item_text) is not None),
        "",
    )
    if not location_text:
        location_text = next(
            (
                item_text
                for _, item_text in raw_items
                if _strip_markdown_markup(item_text).strip().startswith(("原报告位置", "位置"))
            ),
            "",
        )

    normalized: list[tuple[str, str]] = []
    transformed = False
    for cls_attr, item_text in raw_items:
        plain = _strip_markdown_markup(item_text).strip()
        note_match = _VERIFICATION_NOTE_RE.match(item_text.strip())
        if not note_match:
            normalized.append((cls_attr, item_text))
            continue

        evidence_source = _remove_repeated_original_quote(
            note_match.group("source"), original_quote
        )
        if _is_distinct_evidence_source(evidence_source, location_text):
            normalized.append(_labeled_raw_item("核验来源", evidence_source))
        normalized.append(_labeled_raw_item("核验结论", note_match.group("conclusion").strip()))
        transformed = True

    if not transformed:
        return normalized
    return [
        item
        for item in normalized
        if not _GENERIC_DELIVERY_EVIDENCE_RE.match(_strip_markdown_markup(item[1]).strip())
    ]


def _render_insufficient_evidence_group(
    item_text: str, report_lines: Sequence[str] | None, list_context: str
) -> str | None:
    """将“上述 N 项均为证据不足”的聚合条目展开为逐项可读清单。"""
    match = _INSUFFICIENT_EVIDENCE_GROUP_RE.match(item_text.strip())
    if not match:
        return None

    count_text = match.group("count")
    expected_count = int(count_text) if count_text.isdigit() else _CN_COUNT_VALUES.get(count_text)
    evidence_text = match.group("evidence")
    references = list(_VISUAL_EVIDENCE_REF_RE.finditer(evidence_text))
    if not expected_count or len(references) != expected_count:
        return None

    shared_detail = evidence_text[references[-2].end():references[-1].start()]
    last_detail = evidence_text[references[-1].end():]
    shared_detail = shared_detail.strip("、， ").removeprefix("的").strip()
    last_detail = last_detail.strip("、， ").removeprefix("的").strip()
    if not shared_detail or not last_detail:
        return None

    expanded_items: list[str] = []
    for index, reference in enumerate(references):
        detail = shared_detail if index < len(references) - 1 else last_detail
        expanded_text = f"{reference.group(0)}：{detail}"
        expanded_items.append(
            f"<li>{_format_cell(expanded_text, report_lines, list_context)}</li>"
        )

    resolution = _format_cell(match.group("resolution"), report_lines, list_context)
    return (
        f'<div class="evidence-group"><strong>以下 {expected_count} 项证据不足：</strong>'
        f'<ul class="evidence-item-list">{"".join(expanded_items)}</ul>'
        f'<div class="evidence-group-resolution"><strong>结论与补件要求：</strong>{resolution}</div>'
        "</div>"
    )


def render_list(
    lines: Sequence[str], start: int, ordered: bool, report_lines: Sequence[str] | None = None
) -> tuple[str, int]:
    tag = "ol" if ordered else "ul"
    pattern = r"^\d+\.\s+" if ordered else r"^[-*+]\s+"
    raw_items: list[tuple[str, str]] = []
    index = start
    while index < len(lines):
        stripped = lines[index].strip()
        if not re.match(pattern, stripped):
            break
        item_text = re.sub(pattern, "", stripped, count=1)
        css_class = _classify_li(item_text)
        cls_attr = f' class="{css_class}"' if css_class else ""
        raw_items.append((cls_attr, item_text))
        index += 1

    raw_items = _deduplicate_location_search_quotes(raw_items)
    raw_items = _separate_verification_conclusions(raw_items)
    list_context = " ".join(item_text for _, item_text in raw_items)
    items = []
    for cls_attr, item_text in raw_items:
        rendered = _render_insufficient_evidence_group(item_text, report_lines, list_context)
        if rendered is None:
            rendered = _format_cell(item_text, report_lines, list_context)
            rendered = _format_original_quote_item(item_text, rendered)
        items.append(f"<li{cls_attr}>{rendered}</li>")
    return f"<{tag}>" + "".join(items) + f"</{tag}>", index


def render_markdown(markdown_text: str, source_dir: Path | None = None) -> str:
    lines = markdown_text.splitlines()
    report_lines = _load_report_text_lines(source_dir)
    project_index = _load_project_index(source_dir)
    html_parts: List[str] = []
    paragraph_buffer: List[str] = []
    in_code_block = False
    code_lines: List[str] = []
    code_language = ""
    severity_class = ""
    finding_card_open = False
    index = 0

    _HIGHLIGHT_P_RE = re.compile(
        r'但存在(?:问题|缺陷|不足)|主要集中在|需(?:修正|要修改|改进)|(?:问题|缺陷)主要|(?:核心|严重)问题'
    )

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if paragraph_buffer:
            # 支持 Markdown 硬换行：行尾两个以上空格 → <br>
            raw_parts = []
            formatted_parts = []
            for part in paragraph_buffer:
                stripped = part.rstrip()
                if part.endswith("  ") or part.endswith("  \n"):
                    raw_parts.append(stripped)
                    formatted_parts.append(apply_inline_formatting(stripped) + "<br>")
                elif stripped:
                    raw_parts.append(stripped)
                    formatted_parts.append(apply_inline_formatting(stripped))
            raw_text = " ".join(raw_parts)
            text = (
                _format_cell(raw_text, report_lines, raw_text)
                if report_lines is not None and _extract_report_text_ranges(raw_text)
                else " ".join(formatted_parts)
            )
            if text:
                cls = ' class="highlight-issue"' if _HIGHLIGHT_P_RE.search(text) else ""
                if 'class="location-cell"' in text:
                    html_parts.append(text)
                else:
                    html_parts.append(f"<p{cls}>{text}</p>")
            paragraph_buffer = []

    def flush_finding_card() -> None:
        nonlocal finding_card_open
        if finding_card_open:
            html_parts.append("</section>")
            finding_card_open = False

    def flush_severity_block() -> None:
        nonlocal severity_class
        flush_finding_card()
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
            table_html, index = render_table(lines, index, report_lines, project_index)
            html_parts.append(table_html)
            continue

        if re.match(r"^#{1,6}\s+", stripped):
            flush_paragraph()
            level = len(stripped) - len(stripped.lstrip("#"))
            heading_text = _display_heading_text(stripped[level:].strip(), level)
            if finding_card_open and level <= 4:
                flush_finding_card()
            if level == 1:
                index += 1
                continue
            sev_match = re.search(r'\b(FATAL|CRITICAL|MAJOR|WARNING|INFO)\b', heading_text)
            if level <= 2:
                flush_severity_block()
            elif level == 3 and sev_match:
                flush_severity_block()
                sev = sev_match.group(1).lower()
                html_parts.append(f'<div class="severity-block severity-{sev}">')
                severity_class = sev
            if (
                level == 4
                and severity_class
                and _CONCRETE_ERROR_HEADING_RE.match(heading_text)
            ):
                html_parts.append('<section class="concrete-error-card">')
                finding_card_open = True
            html_parts.append(
                f"<h{level} id=\"{slugify(heading_text)}\">{apply_inline_formatting(heading_text)}</h{level}>"
            )
            index += 1
            continue

        if re.match(r"^\d+\.\s+", stripped):
            flush_paragraph()
            list_html, index = render_list(lines, index, ordered=True, report_lines=report_lines)
            html_parts.append(list_html)
            continue

        if re.match(r"^[-*+]\s+", stripped):
            flush_paragraph()
            list_html, index = render_list(lines, index, ordered=False, report_lines=report_lines)
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


SEVERITY_LEVELS = ("FATAL", "CRITICAL", "MAJOR", "WARNING", "INFO")


def _empty_issue_counts() -> dict[str, int]:
    return {key: 0 for key in SEVERITY_LEVELS}


def _normalize_issue_severity(value: str) -> str:
    normalized = re.sub(r"[^A-Z]", "", _strip_markdown_markup(str(value)).upper())
    return normalized if normalized in SEVERITY_LEVELS else ""


def _count_issue_entries(markdown_text: str) -> dict[str, int]:
    counts = _empty_issue_counts()
    seen: set[str] = set()
    for index, issue in enumerate(parse_issue_entries(markdown_text), start=1):
        severity = _normalize_issue_severity(issue.get("severity", ""))
        if not severity:
            severity = _normalize_issue_severity(_issue_severity_from_text(issue.get("text", "")))
        if not severity:
            continue
        issue_id = _strip_markdown_markup(issue.get("id", "")).strip().upper()
        key = issue_id or f"{index}:{_strip_markdown_markup(issue.get('title', '')).strip()}"
        if key in seen:
            continue
        seen.add(key)
        counts[severity] += 1
    return counts


def count_issue_levels(markdown_text: str) -> dict[str, int]:
    # A canonical F-item table is the authoritative finding set. Reader-facing
    # P01 group headings summarize those findings and must not replace or
    # under-count the dashboard totals.
    counts = _count_issue_entries(markdown_text)
    if any(counts.values()):
        return counts

    counts = _empty_issue_counts()
    for match in re.finditer(
        r"^###\s+[^\n]*?\b(FATAL|CRITICAL|MAJOR|WARNING|INFO)\b",
        markdown_text,
        flags=re.MULTILINE,
    ):
        counts[match.group(1)] += 1
    if any(counts.values()):
        return counts

    for match in re.finditer(
        r"^\s*(?:[-*]\s*)?(?:\*\*)?(?:\u7ea7\u522b|\u4e25\u91cd\u7ea7\u522b|\u4e25\u91cd\u5ea6|Severity|Level)(?:\*\*)?\s*[:：]?\s*(FATAL|CRITICAL|MAJOR|WARNING|INFO)\b",
        markdown_text,
        flags=re.MULTILINE | re.IGNORECASE,
    ):
        counts[match.group(1).upper()] += 1
    if any(counts.values()):
        return counts

    for match in re.finditer(
        r"^\s*(?:-\s*)?严重度\s*[:：]\s*(FATAL|CRITICAL|MAJOR|WARNING|INFO)\b",
        markdown_text,
        flags=re.MULTILINE | re.IGNORECASE,
    ):
        counts[match.group(1).upper()] += 1
    if any(counts.values()):
        return counts

    lines = markdown_text.splitlines()
    index = 0
    severity_headers = {"severity", "严重级别", "严重程度", "问题级别", "级别", "等级"}
    while index < len(lines):
        if not is_table_block(lines, index):
            index += 1
            continue

        headers = [_strip_markdown_markup(cell).strip().lower() for cell in split_table_cells(lines[index])]
        severity_col = None
        for col, header in enumerate(headers):
            if header in severity_headers:
                severity_col = col
                break

        index += 2
        while index < len(lines) and lines[index].strip().startswith("|"):
            if severity_col is not None:
                cells = split_table_cells(lines[index])
                if severity_col < len(cells):
                    normalized = _normalize_issue_severity(cells[severity_col])
                    if normalized in counts:
                        counts[normalized] += 1
            index += 1
    return counts


def _iter_markdown_tables(markdown_text: str) -> Sequence[tuple[list[str], list[list[str]]]]:
    tables: list[tuple[list[str], list[list[str]]]] = []
    lines = markdown_text.splitlines()
    index = 0
    while index < len(lines):
        if not is_table_block(lines, index):
            index += 1
            continue
        headers = [cell.strip() for cell in split_table_cells(lines[index])]
        rows: list[list[str]] = []
        index += 2
        while index < len(lines) and lines[index].strip().startswith("|"):
            rows.append(_fit_table_cells(split_table_cells(lines[index]), len(headers)))
            index += 1
        tables.append((headers, rows))
    return tables


def parse_analysis_table(markdown_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for headers, table_rows in _iter_markdown_tables(markdown_text):
        if not any(_is_analysis_header(header) for header in headers):
            continue
        for cells in table_rows:
            rows.append(dict(zip(headers, cells)))
    return rows


def _compact_plain(text: str, limit: int = 140) -> str:
    plain = re.sub(r"[*`~]", "", re.sub(r"\s+", " ", text)).strip()
    if len(plain) <= limit:
        return plain
    cut = plain[:limit]
    for mark in ("。", "；", "，", ". ", "; ", ", ", " "):
        pos = cut.rfind(mark)
        if pos >= int(limit * 0.55):
            return cut[:pos].rstrip() + "..."
    return cut.rstrip() + "..."


def _text_for_matching(text: str) -> str:
    text = _strip_markdown_markup(text).replace("\\", "/").lower()
    return re.sub(r"\s+", " ", text)


def _issue_severity_from_text(text: str) -> str:
    match = re.search(r"\b(FATAL|CRITICAL|MAJOR|WARNING|INFO)\b", text, flags=re.IGNORECASE)
    return match.group(1).upper() if match else ""


def _find_header_index(headers: Sequence[str], *keywords: str) -> int | None:
    for idx, header in enumerate(headers):
        key = _header_key(header)
        if any(keyword.lower() in key for keyword in keywords):
            return idx
    return None


def _is_issue_table(headers: Sequence[str]) -> bool:
    normalized = [_header_key(header) for header in headers]
    has_id_or_severity = any(
        key in {"编号", "id", "问题编号", "canonical", "级别", "严重级别", "严重度", "severity"}
        or "级别" in key
        for key in normalized
    )
    has_problem = any("问题" in key or "缺陷" in key or "核心" in key for key in normalized)
    has_action_or_evidence = any(
        "整改" in key or "建议" in key or "证据" in key or "位置" in key for key in normalized
    )
    return has_id_or_severity and has_problem and has_action_or_evidence


def parse_issue_entries(markdown_text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen_keys: set[str] = set()

    for headers, rows in _iter_markdown_tables(markdown_text):
        if not _is_issue_table(headers):
            continue
        id_col = _find_header_index(headers, "编号", "id", "canonical")
        severity_col = _find_header_index(headers, "级别", "严重度", "severity")
        title_col = _find_header_index(headers, "核心问题", "问题", "缺陷")
        location_col = _find_header_index(headers, "位置", "location")
        evidence_col = _find_header_index(headers, "证据", "evidence")
        action_col = _find_header_index(headers, "整改", "建议", "处置")

        for idx, cells in enumerate(rows, start=1):
            row_text = " | ".join(cells)
            issue_id = cells[id_col].strip() if id_col is not None and id_col < len(cells) else ""
            if not issue_id:
                found_id = re.search(r"\bF-\d+\b", row_text, flags=re.IGNORECASE)
                issue_id = found_id.group(0).upper() if found_id else f"T-{idx:03d}"
            severity = (
                cells[severity_col].strip()
                if severity_col is not None and severity_col < len(cells)
                else _issue_severity_from_text(row_text)
            )
            title = cells[title_col].strip() if title_col is not None and title_col < len(cells) else row_text
            location = cells[location_col].strip() if location_col is not None and location_col < len(cells) else ""
            evidence = cells[evidence_col].strip() if evidence_col is not None and evidence_col < len(cells) else ""
            action = cells[action_col].strip() if action_col is not None and action_col < len(cells) else ""
            key = f"{issue_id}|{title}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            entries.append(
                {
                    "id": issue_id,
                    "severity": severity,
                    "title": title,
                    "location": location,
                    "evidence": evidence,
                    "action": action,
                    "text": row_text,
                    "source": "table",
                }
            )

    # A detailed issue table is the authoritative source for severity counts.
    # Core P01/P1 blocks are reader-facing summaries of that table and must not
    # inflate the dashboard by being counted a second time.
    if not entries:
        core_issue_pattern = re.compile(
            r"^###\s+(P(?:0?1)-\d+)\s+\[(FATAL|CRITICAL|MAJOR|WARNING|INFO)\]\s+(.+?)\s*$"
            r"([\s\S]*?)(?=^##\s+|^###\s+|\Z)",
            flags=re.MULTILINE,
        )
        for match in core_issue_pattern.finditer(markdown_text):
            issue_id = match.group(1).upper()
            severity = match.group(2)
            title = match.group(3).strip()
            body = match.group(4).strip()
            key = f"{issue_id}|{title}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            entries.append(
                {
                    "id": issue_id,
                    "severity": severity,
                    "title": title,
                    "location": "",
                    "evidence": "",
                    "action": "",
                    "text": f"{title} {body}",
                    "source": "core_issue",
                }
            )

    secondary_issue_pattern = re.compile(
        r"^###\s+(S-\d+)\s+\[(FATAL|CRITICAL|MAJOR|WARNING|INFO)\]\s+(.+?)\s*$"
        r"([\s\S]*?)(?=^##\s+|^###\s+|\Z)",
        flags=re.MULTILINE,
    )
    for match in secondary_issue_pattern.finditer(markdown_text):
        issue_id = match.group(1).upper()
        severity = match.group(2)
        title = match.group(3).strip()
        body = match.group(4).strip()
        key = f"{issue_id}|{title}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        entries.append(
            {
                "id": issue_id,
                "severity": severity,
                "title": title,
                "location": "",
                "evidence": "",
                "action": "",
                "text": f"{title} {body}",
                "source": "secondary_issue",
            }
        )

    detail_pattern = re.compile(
        r"^###\s+(?:(\d+)\.\s+)?\[(FATAL|CRITICAL|MAJOR|WARNING|INFO)\]\s+(.+?)\s*$"
        r"([\s\S]*?)(?=^##\s+|^###\s+|\Z)",
        flags=re.MULTILINE,
    )
    for idx, match in enumerate(detail_pattern.finditer(markdown_text), start=1):
        number = match.group(1) or str(idx)
        severity = match.group(2)
        title = match.group(3).strip()
        body = match.group(4).strip()
        issue_id = f"D-{int(number):03d}" if number.isdigit() else f"D-{idx:03d}"
        key = f"{issue_id}|{title}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        entries.append(
            {
                "id": issue_id,
                "severity": severity,
                "title": title,
                "location": "",
                "evidence": "",
                "action": "",
                "text": f"{title} {body}",
                "source": "detail",
            }
        )

    final_issue_pattern = re.compile(
        r"^###\s+(F-\d+)\s+(.+?)\s*$"
        r"([\s\S]*?)(?=^##\s+|^###\s+|\Z)",
        flags=re.MULTILINE | re.IGNORECASE,
    )
    for idx, match in enumerate(final_issue_pattern.finditer(markdown_text), start=1):
        issue_id = match.group(1).upper()
        title = match.group(2).strip()
        body = match.group(3).strip()
        severity = _issue_severity_from_text(body)
        key = f"{issue_id}|{title}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        entries.append(
            {
                "id": issue_id,
                "severity": severity,
                "title": title,
                "location": "",
                "evidence": "",
                "action": "",
                "text": f"{title} {body}",
                "source": "final_issue",
            }
        )
    return entries


_ACTIONABLE_ANALYSIS_RE = re.compile(
    r"(不通过|有问题|不充分|部分充分|部分通过|未覆盖|不足|不一致|错误|错写|残留|不可复现|空目录|"
    r"绝对路径|未报告|缺失|未闭环|未映射|不符|矛盾|伪计数|不显著|超出|不可作为|需修|待修|重跑|删除无关|修订|修正|改为|统一|排查)"
)


def _analysis_row_needs_issue(row: dict[str, str]) -> bool:
    text = " | ".join(row.values())
    if not _ACTIONABLE_ANALYSIS_RE.search(text):
        return False
    if re.search(r"(无需处理|无需按|未发现影响结论|未发现证据缺口)", text) and not re.search(
        r"(不通过|有问题|不充分|错写|错误|不可复现|空目录|绝对路径|未报告|残留)", text
    ):
        return False
    return True


def _extract_consistency_refs(
    text: str,
    project_index: dict[str, list[str]] | None = None,
) -> set[str]:
    refs = {_normalize_ref_path(ref).lower() for ref in _extract_code_refs(text)}
    if project_index:
        refs.update(_normalize_ref_path(ref).lower() for ref in _extract_module_refs(text, project_index))
    for match in _MODULE_TOKEN_RE.finditer(text):
        ref = _normalize_ref_path(match.group(1)).lower()
        if "/" in ref or re.match(r"\d{2}[_\-.]", ref):
            refs.add(ref)
    for match in re.finditer(r"\b(?:F-\d+|P(?:0?1)-\d+|S-\d+|ARB-\d+|GSE\d+|TCGA-[A-Z]+|CGGA\d+|[A-Z0-9]{2,}[_-][A-Z0-9_/-]+)\b", text):
        refs.add(match.group(0).lower())
    return {ref for ref in refs if len(ref) >= 2}


def _analysis_aliases(title: str, row_text: str) -> set[str]:
    title_for_alias = title.lower()
    aliases: set[str] = set()
    title_plain = _text_for_matching(title)
    if len(title_plain) >= 2:
        aliases.add(title_plain)

    mapping = [
        (("数据", "分组", "rawdata"), {"rawdata", "table 0", "数据集", "疾病名称", "tcga", "gse", "hcc"}),
        (("cox", "预后", "定量表达"), {"cox", "cgga", "cdda", "km", "生存", "figure 4", "图号"}),
        (("差异表达", "deg"), {"差异表达", "wilcoxon", "high vs low", "自证"}),
        (("go", "kegg", "富集"), {"go", "kegg", "富集", "p.adjust", "count"}),
        (("gsea", "hallmark"), {"gsea", "hallmark", "pvalue", "p.adjust", "通路"}),
        (("单细胞", "scrna", "聚类"), {"scrna", "resolution", "聚类", "亚群", "umap"}),
        (("a+", "肿瘤细胞"), {"a_pos", "k-means", "findclusters", "关键亚群", "c1-c8", "亚群"}),
        (("空间", "rctd", "strna"), {"strna", "rctd", "hcc_4t", "hcc_1t", "空间"}),
        (("虚拟敲除", "sctenifold"), {"sctenifold", "18_sctenifoldknk", "绝对路径", "knk"}),
        (("网络",), {"network", "19_network"}),
        (("机器学习", "svm", "rfe"), {"svm", "rfe", "machine_learning", "caret"}),
        (("roc", "auc"), {"roc", "auc", "train", "验证集"}),
        (("免疫", "infiltration"), {"免疫", "immune", "infiltration"}),
        (("分子对接", "docking"), {"docking", "gene_infor", "结合能", "配体"}),
        (("分子动力学", "md"), {"12_md", "md", "动力学", "空目录"}),
        (("引用", "参考文献", "方法包"), {"survival", "gsva", "dorothea", "stutility", "aucell", "参考文献"}),
        (("章节", "报告结构"), {"结果章节编号不连续", "2.8", "2.9", "2.10"}),
    ]
    for needles, values in mapping:
        if any(needle in title_for_alias for needle in needles):
            aliases.update(value.lower() for value in values)
    return aliases


def _match_analysis_to_issues(
    row: dict[str, str],
    issues: Sequence[dict[str, str]],
    project_index: dict[str, list[str]] | None,
) -> list[dict[str, str]]:
    title = next((value for key, value in row.items() if _is_analysis_header(key)), "")
    row_text = " | ".join(row.values())
    row_match_text = _text_for_matching(row_text)
    row_refs = _extract_consistency_refs(row_text, project_index)
    explicit_issue_ids = {
        ref.upper()
        for ref in row_refs
        if re.fullmatch(r"(?:f-\d+|p(?:0?1)-\d+|s-\d+)", ref, flags=re.IGNORECASE)
    }
    aliases = _analysis_aliases(title, row_text)

    matches: list[dict[str, str]] = []
    for issue in issues:
        if explicit_issue_ids:
            issue_text = " ".join(
                issue.get(key, "")
                for key in ("id", "severity", "title", "location", "evidence", "action", "text")
            )
            issue_refs = {
                ref.upper()
                for ref in _extract_consistency_refs(issue_text, project_index)
            }
            if issue.get("id", "").upper() in explicit_issue_ids or issue_refs.intersection(explicit_issue_ids):
                matches.append(issue)
            continue
        issue_text = " ".join(
            issue.get(key, "")
            for key in ("id", "severity", "title", "location", "evidence", "action", "text")
        )
        issue_match_text = _text_for_matching(issue_text)
        issue_refs = _extract_consistency_refs(issue_text, project_index)
        shared_refs = row_refs.intersection(issue_refs)
        alias_hit = any(alias and alias in issue_match_text for alias in aliases)
        title_hit = bool(title and _text_for_matching(title) in issue_match_text)
        reverse_title_hit = bool(issue.get("title") and _text_for_matching(issue["title"]) in row_match_text)
        if shared_refs or alias_hit or title_hit or reverse_title_hit:
            matches.append(issue)
    return matches


def _format_consistency_text(
    text: str,
    report_lines: Sequence[str] | None,
    context_text: str = "",
    limit: int = 150,
) -> str:
    text_without_report_refs = _REPORT_TEXT_REF_RE.sub("原文见正文证据", text)
    compact = _compact_plain(text_without_report_refs, limit)
    if not compact:
        return '<span class="muted">未填写</span>'
    return apply_inline_formatting(compact)


def _consistency_card(label: str, value: int, cls: str = "") -> str:
    class_attr = f" consistency-card-{cls}" if cls else ""
    return (
        f'<div class="consistency-card{class_attr}">'
        f'<span class="consistency-value">{value}</span>'
        f'<span class="consistency-label">{html.escape(label)}</span>'
        "</div>"
    )


def build_consistency_check_html(markdown_text: str, source_dir: Path | None = None) -> str:
    analysis_rows = parse_analysis_table(markdown_text)
    issues = parse_issue_entries(markdown_text)
    if not analysis_rows and not issues:
        return ""

    report_lines = _load_report_text_lines(source_dir)
    project_index = _load_project_index(source_dir)
    actionable_rows = [row for row in analysis_rows if _analysis_row_needs_issue(row)]

    row_matches: list[tuple[dict[str, str], list[dict[str, str]]]] = []
    matched_issue_ids: set[str] = set()
    for row in actionable_rows:
        matches = _match_analysis_to_issues(row, issues, project_index)
        row_matches.append((row, matches))
        matched_issue_ids.update(issue["id"] for issue in matches)

    analysis_gap_count = sum(1 for _, matches in row_matches if not matches)
    issue_gap_entries = [issue for issue in issues if issue["id"] not in matched_issue_ids]

    cards = [
        _consistency_card("需映射分析点", len(actionable_rows)),
        _consistency_card("已映射分析点", len(actionable_rows) - analysis_gap_count, "ok"),
        _consistency_card("分析点漏入清单", analysis_gap_count, "gap" if analysis_gap_count else "ok"),
        _consistency_card("清单未落分析点", len(issue_gap_entries), "gap" if issue_gap_entries else "ok"),
    ]

    analysis_rows_html: list[str] = []
    for row, matches in row_matches:
        title = next((value for key, value in row.items() if _is_analysis_header(key)), "未命名分析点")
        row_text = " | ".join(row.values())
        mapped = "、".join(
            f'<span class="consistency-issue-id">{html.escape(issue["id"])}</span> {html.escape(_compact_plain(issue["title"], 40))}'
            for issue in matches
        )
        status_cls = "ok" if matches else "gap"
        status = "已进入问题清单" if matches else "未进入问题清单"
        mapped_html = mapped or '<span class="muted">未匹配到问题项</span>'
        analysis_rows_html.append(
            f'<tr class="consistency-{status_cls}">'
            f"<td>{html.escape(_compact_plain(title, 60))}</td>"
            f"<td>{_format_consistency_text(row_text, report_lines, row_text)}</td>"
            f"<td>{mapped_html}</td>"
            f'<td><span class="consistency-status consistency-status-{status_cls}">{status}</span></td>'
            "</tr>"
        )

    if analysis_rows_html:
        analysis_table = (
            '<div class="consistency-table-wrap"><table class="consistency-table">'
            "<thead><tr><th>逐分析点发现</th><th>核心判断</th><th>问题清单映射</th><th>状态</th></tr></thead>"
            f"<tbody>{''.join(analysis_rows_html)}</tbody></table></div>"
        )
    else:
        analysis_table = '<div class="consistency-empty">逐分析点表中未识别到需要进入问题清单的异常判断。</div>'

    issue_gap_rows: list[str] = []
    for issue in issue_gap_entries:
        issue_text = " ".join(
            issue.get(key, "")
            for key in ("title", "location", "evidence", "action", "text")
        )
        issue_gap_rows.append(
            '<tr class="consistency-gap">'
            f'<td><span class="consistency-issue-id">{html.escape(issue["id"])}</span></td>'
            f"<td>{html.escape(issue.get('severity', ''))}</td>"
            f"<td>{html.escape(_compact_plain(issue.get('title', ''), 80))}</td>"
            f"<td>{_format_consistency_text(issue_text, report_lines, issue_text)}</td>"
            '<td><span class="consistency-status consistency-status-gap">未对应分析点</span></td>'
            "</tr>"
        )

    if issue_gap_rows:
        issue_table = (
            '<details class="consistency-details" open><summary>问题清单未对应分析点</summary>'
            '<div class="consistency-table-wrap"><table class="consistency-table">'
            "<thead><tr><th>ID</th><th>级别</th><th>问题</th><th>关键内容</th><th>状态</th></tr></thead>"
            f"<tbody>{''.join(issue_gap_rows)}</tbody></table></div></details>"
        )
    else:
        issue_table = '<div class="consistency-empty">核心问题清单均已匹配到逐分析点记录。</div>'

    return (
        '<section class="consistency-section" id="分析点与问题清单一致性检查">'
        "<h2>分析点与问题清单一致性检查</h2>"
        '<p class="consistency-desc">自动比对“逐分析点审核结果”和“核心问题清单与整改建议”。'
        "凡是逐分析点表中已经判断为异常的内容，应进入问题清单；凡是问题清单中的问题，也应能回到对应分析点。</p>"
        f'<div class="consistency-grid">{"".join(cards)}</div>'
        "<h3>逐分析点异常是否进入问题清单</h3>"
        f"{analysis_table}"
        f"{issue_table}"
        "</section>"
    )


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _inventory_card(label: str, value: int | str, note: str = "") -> str:
    return (
        '<div class="inventory-card">'
        f'<span class="inventory-value">{html.escape(str(value))}</span>'
        f'<span class="inventory-label">{html.escape(label)}</span>'
        f'<span class="inventory-note">{html.escape(note)}</span>'
        "</div>"
    )


def _module_file_total(modules: Sequence[dict]) -> int:
    return sum(_safe_int(module.get("file_counts", {}).get("total")) for module in modules)


def build_delivery_inventory_html(source_dir: Path | None) -> str:
    data = _load_project_structure(source_dir)
    if not data:
        return ""

    metadata = data.get("metadata", {})
    all_modules = data.get("modules", [])
    modules = [module for module in all_modules if module.get("is_module", True)]
    inventory_modules = [module for module in all_modules if module.get("file_counts")]
    if not inventory_modules:
        inventory_modules = modules or all_modules
    code_files = data.get("code_files", [])
    module_total = _safe_int(metadata.get("total_modules"), len(modules)) or len(modules) or len(inventory_modules)
    code_total = _safe_int(metadata.get("total_code_files"), len(code_files)) or len(code_files)
    data_total = _safe_int(metadata.get("total_data_files"))
    image_total = _safe_int(metadata.get("total_images"))
    config_total = _safe_int(metadata.get("total_config_files"))
    # “模块文件总数”只统计明确识别出的分析模块；非模块目录仍保留在下方
    # 盘点表中，避免公司附页、说明目录等抬高模块卡片数字。
    file_total = _module_file_total(modules or inventory_modules)

    cards = [
        _inventory_card("模块文件总数", file_total, "按交付模块合计"),
        _inventory_card("分析模块", module_total, "按交付目录识别"),
        _inventory_card("代码文件", code_total, "R/Python 等脚本"),
        _inventory_card("数据文件", data_total, "csv/xlsx/rds 等"),
        _inventory_card("图件/PDF文件", image_total, "pdf/png/jpg 等"),
        _inventory_card("配置文件", config_total, "配置/环境文件"),
    ]

    module_rows: list[str] = []
    for module in inventory_modules:
        counts = module.get("file_counts", {})
        path = _normalize_ref_path(str(module.get("path") or module.get("name") or ""))
        total = _safe_int(counts.get("total"))
        data = _safe_int(counts.get("csv"))
        figures = _safe_int(counts.get("pdf")) + _safe_int(counts.get("images"))
        row_class = ' class="inventory-row-single-kind"' if total > 0 and total in (data, figures) else ""
        module_rows.append(
            f"<tr{row_class}>"
            f"<td><code>{html.escape(path)}</code></td>"
            f"<td>{total}</td>"
            f"<td>{data}</td>"
            f"<td>{_safe_int(counts.get('pdf'))}</td>"
            f"<td>{_safe_int(counts.get('images'))}</td>"
            f"<td>{_safe_int(counts.get('code'))}</td>"
            "</tr>"
        )

    code_rows: list[str] = []
    for code_file in code_files:
        path = _normalize_ref_path(str(code_file.get("path") or ""))
        package_count = len(code_file.get("packages") or [])
        io_count = len(code_file.get("io_references") or [])
        code_rows.append(
            "<tr>"
            f"<td><code>{html.escape(path)}</code></td>"
            f"<td>{html.escape(str(code_file.get('language') or ''))}</td>"
            f"<td>{_safe_int(code_file.get('lines'))}</td>"
            f"<td>{package_count}</td>"
            f"<td>{io_count}</td>"
            "</tr>"
        )

    module_table = (
        '<details class="inventory-details" open><summary>模块文件计数</summary>'
        '<div class="inventory-table-wrap"><table class="inventory-table">'
        "<thead><tr><th>模块/目录</th><th>总文件</th><th>数据</th><th>PDF图件</th><th>位图</th><th>代码</th></tr></thead>"
        f"<tbody>{''.join(module_rows)}</tbody></table></div></details>"
    )
    code_table = (
        '<details class="inventory-details"><summary>代码文件清单</summary>'
        '<div class="inventory-table-wrap"><table class="inventory-table">'
        "<thead><tr><th>脚本</th><th>语言</th><th>行数</th><th>包数量</th><th>输入/输出引用</th></tr></thead>"
        f"<tbody>{''.join(code_rows)}</tbody></table></div></details>"
        if code_rows
        else '<div class="inventory-empty">当前交付未提供可核验代码文件。</div>'
    )

    return (
        '<section class="inventory-section" id="交付文件与代码盘点">'
        "<h2>交付文件与代码盘点</h2>"
        '<p class="inventory-desc">按当前交付目录统计，用于概览文件、模块和脚本数量。</p>'
        f'<div class="inventory-grid">{"".join(cards)}</div>'
        '<p class="inventory-legend">'
        '<span class="inventory-legend-swatch" aria-hidden="true"></span>'
        f"{html.escape(INVENTORY_LEGEND_TEXT)}"
        "</p>"
        f"{module_table}"
        f"{code_table}"
        "</section>"
    )


_CN_NUMERALS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
                "十一", "十二", "十三", "十四", "十五"]
_CN_NUM_RE = re.compile(r'[一二三四五六七八九十]+(?:十[一二三四五六七八九])?')


def _renumber_cn(text: str, idx: int) -> str:
    """将文本中的中文序号替换为 idx 对应的中文数字（1-based）。"""
    if idx < 1 or idx > len(_CN_NUMERALS):
        return text
    return _CN_NUM_RE.sub(_CN_NUMERALS[idx - 1], text, count=1)


def _reorder_and_renumber(items: list, get_title) -> list:
    """按读者阅读路径调整章节顺序。items 是 list，get_title 返回标题字符串。"""

    def move_before(section_title: str, anchor_title: str) -> None:
        section_idx = None
        anchor_idx = None
        for i, item in enumerate(items):
            title = get_title(item)
            if section_title in title:
                section_idx = i
            if anchor_title in title:
                anchor_idx = i
        if section_idx is not None and anchor_idx is not None and section_idx > anchor_idx:
            section_item = items.pop(section_idx)
            items.insert(anchor_idx, section_item)

    def move_after(section_title: str, anchor_title: str) -> None:
        section_idx = None
        anchor_idx = None
        for i, item in enumerate(items):
            title = get_title(item)
            if section_title in title:
                section_idx = i
            if anchor_title in title:
                anchor_idx = i
        if section_idx is not None and anchor_idx is not None and section_idx > anchor_idx + 1:
            section_item = items.pop(section_idx)
            items.insert(anchor_idx + 1, section_item)

    # 历史报告：先给出摘要，再展开问题。
    move_after("问题详述", "执行摘要")
    # 逐分析点结果只承担导航/索引角色，应先于需优先阅读的阻断问题展示。
    move_before("逐分析点审核结果", "提交阻断问题")
    return items


def build_toc(markdown_text: str) -> str:
    raw_titles: List[str] = []
    has_adjudication_index = "裁定标准与核定理由索引" in markdown_text
    for line in markdown_text.splitlines():
        if not line.startswith("## "):
            continue
        title = _display_heading_text(line[3:].strip(), 2)
        if has_adjudication_index and "逐分析点审核结果" in title:
            continue
        raw_titles.append(title)
    _reorder_and_renumber(raw_titles, lambda t: t)
    li_items = []
    for i, title in enumerate(raw_titles):
        new_title = _renumber_cn(title, i + 1)
        li_items.append(f'<li><a href="#{slugify(new_title)}">{html.escape(new_title)}</a></li>')
    return "<ul>" + "".join(li_items) + "</ul>"


def _build_toc_from_content(content_html: str) -> str:
    """Build navigation from the final visible report headings and exact IDs."""
    li_items: list[str] = []
    for heading_id, heading_html in re.findall(
        r'<h2\b[^>]*\bid="([^"]+)"[^>]*>(.*?)</h2>',
        content_html,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        heading_text = re.sub(r"<[^>]+>", "", html.unescape(heading_html))
        heading_text = re.sub(r"\s+", " ", heading_text).strip()
        li_items.append(
            f'<li><a href="#{html.escape(heading_id, quote=True)}">'
            f"{html.escape(heading_text)}</a></li>"
        )
    return "<ul>" + "".join(li_items) + "</ul>"


def extract_conclusion_summary(markdown_text: str) -> str:
    section = extract_section(markdown_text, "一、审核结论")
    sentences = [line.strip() for line in section.splitlines() if line.strip()]
    return sentences[0] if sentences else "请结合正文查看完整审核结论。"


def _truncate_summary(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for mark in ("。", "；", "，", ". ", "; ", ", "):
        pos = cut.rfind(mark)
        if pos >= int(limit * 0.55):
            return cut[: pos + len(mark)].strip()
    return cut.rstrip() + "..."


def _plain_summary_line(line: str) -> str:
    line = re.sub(r"^[-*+]\s+", "", line.strip())
    line = re.sub(r"^\d+\.\s+", "", line)
    line = re.sub(r"^[>\s]+", "", line)
    line = _strip_markdown_markup(line)
    line = re.sub(r"\[([^\[\]]+)\]\((?:[^()]|\([^)]*\))+\)", r"\1", line)
    return line.strip(" ：:")


def _first_summary_from_block(block: str) -> str:
    paragraph: List[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            if paragraph:
                break
            continue
        if line.startswith("#") or line.startswith("|") or re.match(r"^-{3,}$", line):
            continue
        if re.match(r"^[-*+]\s+", line):
            return _truncate_summary(_plain_summary_line(line))
        paragraph.append(line)
    return _truncate_summary(_plain_summary_line(" ".join(paragraph))) if paragraph else ""


def extract_executive_summary(markdown_text: str) -> str:
    section_pattern = re.compile(r"^##\s+(.+?)\s*$([\s\S]*?)(?=^##\s+|\Z)", flags=re.MULTILINE)
    preferred_keywords = ("审核结论", "结论先行", "最终建议", "审查结论", "Conclusion", "Verdict")
    for match in section_pattern.finditer(markdown_text):
        title = _strip_markdown_markup(match.group(1))
        if any(keyword.lower() in title.lower() for keyword in preferred_keywords):
            summary = _first_summary_from_block(match.group(2))
            if summary:
                return summary

    body = re.sub(r"^#\s+.+$", "", markdown_text, count=1, flags=re.MULTILINE)
    return _first_summary_from_block(body)


def load_template() -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"未找到 HTML 模板: {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def render_template(template: str, context: dict[str, str]) -> str:
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def render_badges(items: Sequence[tuple[str, str]]) -> str:
    badges = []
    for icon, value in items:
        value = value.strip()
        if value:
            badges.append(f'<span class="badge">{icon} {html.escape(value)}</span>')
    return "".join(badges)


def _strip_markdown_markup(text: str) -> str:
    return re.sub(r"[*`_~]", "", text).strip()


def _classify_verdict_text(verdict_text: str) -> tuple[str, str] | None:
    text = _strip_markdown_markup(verdict_text)
    if not text:
        return None

    reject_terms = (
        "不合格",
        "不具备提交条件",
        "不具备提交资格",
        "不建议通过",
        "不建议提交",
        "不建议放行",
        "暂不建议放行",
        "不予放行",
        "暂缓放行",
        "不得放行",
        "不通过",
        "退回",
    )
    conditional_terms = ("有条件合格", "有条件通过", "整改后提交", "整改后复审")
    pass_terms = ("建议通过", "可以提交", "通过", "合格")

    if any(term in text for term in reject_terms):
        if "复审" in text or "退回" in text:
            return "verdict-reject", "不合格，建议退回修订后复审"
        return "verdict-reject", "不合格"
    if any(term in text for term in conditional_terms):
        return "verdict-conditional", "有条件通过"
    if any(term in text for term in pass_terms):
        return "verdict-pass", "建议通过"
    return None


def _iter_conclusion_candidates(markdown_text: str) -> list[str]:
    candidates: list[str] = []
    line_pattern = re.compile(r"^[>\-\*\s`]*(?:审核结论|最终结论|结论)[：:]\s*(.+)$", flags=re.MULTILINE)
    candidates.extend(match.group(1).strip() for match in line_pattern.finditer(markdown_text))

    section_match = re.search(
        r"^##\s*.*审核结论\s*$([\s\S]*?)(?=^##\s+|\Z)",
        markdown_text,
        flags=re.MULTILINE,
    )
    if section_match:
        for line in section_match.group(1).splitlines():
            line = _strip_markdown_markup(line)
            if not line or line.startswith("|") or re.match(r"^-{3,}$", line):
                continue
            candidates.append(line)
            break
    return candidates


def extract_explicit_verdict(markdown_text: str) -> tuple[str, str] | None:
    for candidate in _iter_conclusion_candidates(markdown_text):
        explicit = _classify_verdict_text(candidate)
        if explicit is not None:
            return explicit
    return None


def determine_verdict(issue_counts: dict[str, int], markdown_text: str = "") -> tuple[str, str]:
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


_FINAL_DECISION_PRESENTATION = {
    ("合格", "ALLOW"): ("verdict-pass", "合格"),
    ("有条件合格", "CONDITIONAL"): ("verdict-conditional", "有条件合格"),
    ("不合格", "BLOCK"): ("verdict-reject", "不合格"),
}


def _verdict_from_final_decision(final_decision: Mapping[str, object]) -> tuple[str, str]:
    if final_decision.get("status") != "leader_confirmed":
        raise ValueError("final decision status must be leader_confirmed")
    pair = (
        str(final_decision.get("verdict", "")).strip(),
        str(final_decision.get("release_decision", "")).strip(),
    )
    try:
        return _FINAL_DECISION_PRESENTATION[pair]
    except KeyError as exc:
        raise ValueError("final decision verdict/release_decision pair is invalid") from exc


def resolve_final_decision_path(source_path: Path) -> Path:
    """Resolve the policy-owned decision path beside a report."""
    policy = _load_json_object(POLICY_PATH) or {}
    contract_policy = policy.get("audit_contract_policy", {})
    if not isinstance(contract_policy, dict):
        contract_policy = {}
    filename = str(contract_policy.get("decision_json", "final_decision.json")).strip()
    if not filename or Path(filename).name != filename:
        raise ValueError("final decision filename must be a direct child")
    return source_path.parent / filename


def load_final_decision(source_path: Path) -> dict[str, object] | None:
    """Load the policy-owned sealed decision beside a report, when one exists."""
    decision_path = resolve_final_decision_path(source_path)
    if not decision_path.is_file():
        return None
    try:
        payload = json.loads(decision_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"final decision is unreadable: {decision_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("final decision root must be an object")
    _verdict_from_final_decision(payload)
    return payload


def reorder_sections(content_html: str) -> str:
    """按读者阅读路径重排 H2 章节，并重编中文序号。"""
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


def remove_analysis_navigation(content_html: str) -> str:
    """移除与正式问题清单重复的逐分析点导航章节。"""
    parts = re.split(r'(?=<h2\s)', content_html)
    for index, part in enumerate(parts):
        if not part.startswith("<h2") or "逐分析点审核结果" not in part[:300]:
            continue
        # 裁定理由索引在历史报告中仍归属于本 H2；仅保留该读者可用索引。
        # F-ID/finding_key 等绑定索引属于内部仲裁留痕，必须随导航移除。
        nested_parts = re.split(r'(?=<h3\s)', part)
        keep_at = next(
            (
                nested_index
                for nested_index, nested_part in enumerate(nested_parts)
                if nested_part.startswith("<h3")
                and "裁定标准与核定理由索引" in nested_part[:300]
            ),
            None,
        )
        if keep_at is not None:
            parts[index] = "".join(nested_parts[keep_at:])
        break
    return "".join(parts)


def remove_issue_dashboard_source(content_html: str) -> str:
    """移除与正式问题清单重复的仪表盘来源表。"""
    parts = re.split(r'(?=<h[23]\s)', content_html)
    for index, part in enumerate(parts):
        if not part.startswith("<h3") or "问题清单与严重度仪表盘来源" not in part[:300]:
            continue
        parts[index] = ""
        break
    return "".join(parts)


def _dashboard_severity_map(content_html: str) -> dict[str, str]:
    """从内部仪表盘来源表提取 F 编号的正式严重度。"""
    for part in re.split(r'(?=<h[23]\s)', content_html):
        if not part.startswith("<h3") or "问题清单与严重度仪表盘来源" not in part[:300]:
            continue
        severities: dict[str, str] = {}
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", part, flags=re.DOTALL):
            cells = re.findall(r"<td(?:\s[^>]*)?>(.*?)</td>", row, flags=re.DOTALL)
            if len(cells) < 2:
                continue
            issue_match = re.search(r"\bF-\d+\b", re.sub(r"<[^>]+>", "", cells[0]).upper())
            severity = _normalize_issue_severity(re.sub(r"<[^>]+>", "", cells[1]))
            if issue_match and severity:
                severities[issue_match.group(0)] = severity
        return severities
    return {}


def _dashboard_issue_description_map(content_html: str) -> dict[str, str]:
    """从内部仪表盘来源表提取 F 编号对应的正式错误点描述。"""
    for part in re.split(r'(?=<h[23]\s)', content_html):
        if not part.startswith("<h3") or "问题清单与严重度仪表盘来源" not in part[:300]:
            continue
        descriptions: dict[str, str] = {}
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", part, flags=re.DOTALL):
            cells = re.findall(r"<td(?:\s[^>]*)?>(.*?)</td>", row, flags=re.DOTALL)
            if len(cells) < 3:
                continue
            issue_match = re.search(r"\bF-\d+\b", re.sub(r"<[^>]+>", "", cells[0]).upper())
            if issue_match:
                descriptions[issue_match.group(0)] = cells[2]
        return descriptions
    return {}


def _add_result_column_to_adjudication_index(
    index_html: str,
    severities: Mapping[str, str],
    descriptions: Mapping[str, str],
) -> str:
    """将索引改为“错误点—审核结果—核定理由”的读者导航。"""
    table_match = re.search(r"<table>.*?</table>", index_html, flags=re.DOTALL)
    if not table_match:
        return index_html

    def add_cell(match: re.Match[str]) -> str:
        attrs, row = match.group(1), match.group(2)
        cells = re.findall(r"<t[hd](?:\s[^>]*)?>.*?</t[hd]>", row, flags=re.DOTALL)
        if not cells:
            return match.group(0)
        if cells[0].startswith("<th"):
            if len(cells) > 1:
                cells[1] = "<th>错误点</th>"
            cells.insert(1, "<th>审核结果</th>")
        else:
            issue_match = re.search(r"\bF-\d+\b", re.sub(r"<[^>]+>", "", cells[0]).upper())
            if issue_match is None:
                issue_match = next(
                    (
                        re.search(r"\bF-\d+\b", re.sub(r"<[^>]+>", "", cell).upper())
                        for cell in cells[1:]
                        if re.search(r"\bF-\d+\b", re.sub(r"<[^>]+>", "", cell).upper())
                    ),
                    None,
                )
            issue_id = issue_match.group(0) if issue_match else ""
            severity = severities.get(issue_id)
            result = (
                f'需修订（<span class="sev-tag-{severity.lower()}">{severity}</span>）'
                if severity else "—"
            )
            if len(cells) > 1:
                cells[1] = f"<td>{descriptions.get(issue_id, '—')}</td>"
            cells.insert(1, f"<td>{result}</td>")
        return f"<tr{attrs}>{''.join(cells)}</tr>"

    table_html = re.sub(r"<tr([^>]*)>(.*?)</tr>", add_cell, table_match.group(0), flags=re.DOTALL)
    return index_html[:table_match.start()] + table_html + index_html[table_match.end():]


def collapse_adjudication_reason_index(
    content_html: str,
    severities: Mapping[str, str] | None = None,
    descriptions: Mapping[str, str] | None = None,
) -> str:
    """将裁定理由索引渲染为与模块文件计数一致的默认展开层。"""
    parts = re.split(r'(?=<h[23]\s)', content_html)
    for index, part in enumerate(parts):
        if not part.startswith("<h3") or "裁定标准与核定理由索引" not in part[:300]:
            continue
        part = _add_result_column_to_adjudication_index(part, severities or {}, descriptions or {})
        parts[index] = (
            '<details class="inventory-details adjudication-index" open>'
            '<summary>裁定标准与核定理由索引</summary>'
            f'<div class="adjudication-index-body">{part}</div>'
            '</details>'
        )
        break
    return "".join(parts)


def extract_meta_fields(markdown_text: str) -> dict[str, str]:
    """从 H1 后的引用块提取项目元数据。"""
    fields: dict[str, str] = {}
    for m in re.finditer(r'>\s*\*{0,2}(.+?)\*{0,2}\s*[：:]\s*(.+)', markdown_text):
        key = m.group(1).strip().strip('*')
        val = m.group(2).strip()
        fields[key] = val
    return fields


def build_html(
    markdown_text: str,
    source_path: Path,
    *,
    final_decision: Mapping[str, object] | None = None,
) -> str:
    display_markdown = reader_facing_markdown(
        humanize_image_references(markdown_text, source_path.parent)
    )
    display_markdown = defer_revocation_ledger(display_markdown)
    content_html = reorder_sections(render_markdown(display_markdown, source_path.parent))
    dashboard_severities = _dashboard_severity_map(content_html)
    dashboard_descriptions = _dashboard_issue_description_map(content_html)
    content_html = reorder_sections(
        remove_issue_dashboard_source(remove_analysis_navigation(content_html))
    )
    title = extract_h1(display_markdown)
    project_id_match = re.search(r"\b\d{2}[A-Z]{3}\d{3}[A-Z]?\b", title)
    project_id = project_id_match.group(0) if project_id_match else source_path.parent.name
    issue_counts = count_issue_levels(display_markdown)
    analysis_rows = parse_analysis_table(display_markdown)
    issue_total = sum(issue_counts.values())
    severe_total = issue_counts["FATAL"] + issue_counts["CRITICAL"]
    moderate_total = issue_counts["MAJOR"] + issue_counts["WARNING"]
    verdict_class, verdict_text = (
        _verdict_from_final_decision(final_decision)
        if final_decision is not None
        else determine_verdict(issue_counts, display_markdown)
    )
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = extract_meta_fields(display_markdown)
    audit_date = meta.get("审核日期", "")
    audit_version = meta.get("审核版本", "") or meta.get("审核方式", "") or meta.get("审核范围", "")
    executive_summary = extract_executive_summary(display_markdown)
    template = load_template()
    context = {
        "FRAMEWORK_VERSION": html.escape(load_framework_version()),
        "PROJECT_ID": html.escape(project_id),
        "TITLE": html.escape(title),
        "PROJECT_NAME": html.escape(meta.get("项目名称", "")),
        "META_BADGES_HTML": render_badges(
            [
                ("📋", project_id),
                ("🗓", audit_date),
                ("📝", audit_version),
                ("⏱", generated_at),
            ]
        ),
        "GENERATED_AT": html.escape(generated_at),
        "EXECUTIVE_SUMMARY": html.escape(executive_summary),
        "SEVERE_TOTAL": str(severe_total),
        "MODERATE_TOTAL": str(moderate_total),
        "INFO_COUNT": str(issue_counts["INFO"]),
        "ANALYSIS_COUNT": str(len(analysis_rows)),
        "TOC_HTML": _build_toc_from_content(content_html),
        "ISSUE_TOTAL": str(issue_total),
        "FATAL_COUNT": str(issue_counts["FATAL"]),
        "CRITICAL_COUNT": str(issue_counts["CRITICAL"]),
        "MAJOR_COUNT": str(issue_counts["MAJOR"]),
        "WARNING_COUNT": str(issue_counts["WARNING"]),
        "MAJOR_WARNING_COUNT": str(issue_counts["MAJOR"] + issue_counts["WARNING"]),
        "VERDICT_CLASS": verdict_class,
        "VERDICT_TEXT": html.escape(verdict_text),
        "CONTENT_HTML": (
            build_delivery_inventory_html(source_path.parent)
            + collapse_adjudication_reason_index(
                content_html, dashboard_severities, dashboard_descriptions
            )
        ),
    }
    return render_template(template, context)


def main() -> int:
    args = parse_args()
    markdown_path, html_path = resolve_paths(args.input_path, args.output)
    markdown_text = markdown_path.read_text(encoding="utf-8")
    final_decision = load_final_decision(markdown_path)
    rendered = (
        build_html(markdown_text, markdown_path, final_decision=final_decision)
        if final_decision is not None
        else build_html(markdown_text, markdown_path)
    )
    presentation_ok, presentation_reason = validate_html_presentation_text(rendered)
    if not presentation_ok:
        print(
            f"HTML 展示契约未通过，未写入输出文件: {presentation_reason}",
            file=sys.stderr,
        )
        return 1
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(rendered, encoding="utf-8")
    print(f"HTML报告已生成: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
