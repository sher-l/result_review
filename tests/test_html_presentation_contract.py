#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Reader HTML presentation contract regression tests."""

from __future__ import annotations

import json
import re
from argparse import Namespace
from collections.abc import Callable
from pathlib import Path

import pytest
from lxml import html as lxml_html

import render_final_review_html
from html_presentation_contract import (
    validate_html_presentation_file,
    validate_html_presentation_text,
)
from render_final_review_html import build_html


INVENTORY_LEGEND = (
    "标灰说明：灰色行表示该模块/目录仅交付数据表/数据文件，或仅交付图件/PDF；"
    "标灰仅提示交付类型单一，不代表问题严重度。"
)


@pytest.fixture
def canonical_reader_html(tmp_path: Path) -> str:
    """Build a contract-valid report through the canonical renderer/template."""
    (tmp_path / "project_structure.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "total_modules": 2,
                    "total_code_files": 1,
                    "total_data_files": 2,
                    "total_images": 1,
                    "total_config_files": 0,
                },
                "modules": [
                    {
                        "path": "data-only",
                        "file_counts": {
                            "total": 2,
                            "csv": 2,
                            "pdf": 0,
                            "images": 0,
                            "code": 0,
                        },
                    },
                    {
                        "path": "mixed-delivery",
                        "file_counts": {
                            "total": 3,
                            "csv": 1,
                            "pdf": 1,
                            "images": 0,
                            "code": 1,
                        },
                    },
                ],
                "code_files": [
                    {
                        "path": "scripts/check.R",
                        "language": "R",
                        "lines": 12,
                        "packages": ["stats"],
                        "io_references": ["data.csv"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    source_path = tmp_path / "final_review_report.md"
    markdown = (
        "# 26YTY001F 最终审核报告\n\n"
        "> **项目名称**：展示契约基线\n"
        "> **审核日期**：2026-07-31\n\n"
        "## 一、审核结论\n\n"
        "结论：不合格，建议退回修订后复审。\n\n"
        "## 二、提交阻断问题\n\n"
        "### P01 [FATAL] 阻断问题\n\n"
        "必须完成修订。\n\n"
        "## 三、其他已裁定问题\n\n"
        "### P02 [MAJOR] 一般问题\n\n"
        "按要求修订。\n\n"
        "## 四、复审提交要求\n\n"
        "提交完整数据、图件和代码。\n\n"
        "### 撤销裁定（保留原始记录与反证）\n\n"
        "#### R-01\n\n"
        "保留撤销依据。\n"
    )
    rendered = build_html(
        markdown,
        source_path,
        final_decision={
            "status": "leader_confirmed",
            "verdict": "不合格",
            "release_decision": "BLOCK",
        },
    )

    valid, reason = validate_html_presentation_text(rendered)
    assert valid, f"canonical renderer output must satisfy its presentation contract: {reason}"
    return rendered


def _sub_once(html_text: str, pattern: str, replacement: str) -> str:
    mutated, replacements = re.subn(
        pattern,
        replacement,
        html_text,
        count=1,
        flags=re.DOTALL,
    )
    assert replacements == 1, f"mutation precondition did not match: {pattern}"
    return mutated


def test_renderer_wraps_each_concrete_error_in_an_inner_card(tmp_path: Path) -> None:
    (tmp_path / "project_structure.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "total_modules": 1,
                    "total_code_files": 1,
                    "total_data_files": 1,
                    "total_images": 0,
                    "total_config_files": 0,
                },
                "modules": [
                    {
                        "path": "result",
                        "file_counts": {
                            "total": 2,
                            "csv": 1,
                            "pdf": 0,
                            "images": 0,
                            "code": 1,
                        },
                    }
                ],
                "code_files": [
                    {
                        "path": "scripts/check.R",
                        "language": "R",
                        "lines": 12,
                        "packages": ["stats"],
                        "io_references": ["data.csv"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    source_path = tmp_path / "final_review_report.md"
    markdown = (
        "# 26YTY002F 最终审核报告\n\n"
        "> **项目名称**：具体错误内层分组\n"
        "> **审核日期**：2026-08-05\n\n"
        "## 一、审核结论\n\n"
        "结论：不合格，建议退回修订后复审。\n\n"
        "## 二、提交阻断问题\n\n"
        "### P01 [CRITICAL] 计算验证需补证\n\n"
        "#### 具体错误 1：F-003 分子对接不可复现\n\n"
        "补交命令和参数。\n\n"
        "#### 具体错误 2：F-004 MD 无可审计交付\n\n"
        "补交轨迹和日志。\n\n"
        "#### 具体错误 3：F-006 计算结果被过度外推\n\n"
        "降级为假设生成。\n\n"
        "## 三、复审提交要求\n\n"
        "提交完整数据、图件和代码。\n"
    )

    rendered = build_html(
        markdown,
        source_path,
        final_decision={
            "status": "leader_confirmed",
            "verdict": "不合格",
            "release_decision": "BLOCK",
        },
    )
    document = lxml_html.document_fromstring(rendered)
    cards = document.xpath(
        ".//div[contains(@class, 'severity-block')]//section[@class='concrete-error-card']"
    )

    assert len(cards) == 3
    assert [card.xpath("./h4")[0].text_content().strip() for card in cards] == [
        "具体错误 1：F-003 分子对接不可复现",
        "具体错误 2：F-004 MD 无可审计交付",
        "具体错误 3：F-006 计算结果被过度外推",
    ]
    assert validate_html_presentation_text(rendered) == (True, "")


@pytest.mark.parametrize(
    ("internal_heading", "raw_finding_key"),
    [
        ("finding_key → F-ID 交叉表", "D5-DOCKING-REPRODUCIBILITY-GAP"),
        ("仲裁原始发现交叉索引", "fk:a319c6f52536edc6"),
        ("F-ID 绑定索引", "A01-F001"),
    ],
)
def test_reader_html_omits_internal_arbitration_crosswalk(
    tmp_path: Path,
    internal_heading: str,
    raw_finding_key: str,
) -> None:
    (tmp_path / "project_structure.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "total_modules": 1,
                    "total_code_files": 1,
                    "total_data_files": 1,
                    "total_images": 0,
                    "total_config_files": 0,
                },
                "modules": [
                    {
                        "path": "result",
                        "file_counts": {
                            "total": 2,
                            "csv": 1,
                            "pdf": 0,
                            "images": 0,
                            "code": 1,
                        },
                    }
                ],
                "code_files": [
                    {
                        "path": "scripts/check.R",
                        "language": "R",
                        "lines": 12,
                        "packages": ["stats"],
                        "io_references": ["data.csv"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    source_path = tmp_path / "final_review_report.md"
    markdown = (
        "# 26YTY003F 最终审核报告\n\n"
        "> **项目名称**：内部索引读者投影\n"
        "> **审核日期**：2026-08-05\n\n"
        "## 一、审核结论\n\n"
        "结论：不合格，建议退回修订后复审。\n\n"
        f"### {internal_heading}\n\n"
        "| Canonical ID | 分析点 | 对应问题 | 可搜索定位 |\n"
        "|---|---|---|---|\n"
        f"| CF-01 | {raw_finding_key} | F-01 | CF-01；A:raw:001 |\n\n"
        "## 二、提交阻断问题\n\n"
        "### P01 [MAJOR] 需补充证据\n\n"
        "请补充完整证据。\n\n"
        "## 三、复审提交要求\n\n"
        "提交完整数据、图件和代码。\n"
    )

    rendered = build_html(
        markdown,
        source_path,
        final_decision={
            "status": "leader_confirmed",
            "verdict": "不合格",
            "release_decision": "BLOCK",
        },
    )

    assert internal_heading in markdown
    assert internal_heading not in rendered
    assert raw_finding_key not in rendered
    assert validate_html_presentation_text(rendered) == (True, "")


def _replace_stylesheet(html_text: str) -> str:
    return _sub_once(
        html_text,
        r"<style>.*?</style>",
        "<style>* { display: none !important; }</style>",
    )


def _remove_javascript(html_text: str) -> str:
    return _sub_once(html_text, r"\s*<script>.*?</script>", "")


def _remove_viewport(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'\s*<meta name="viewport" content="width=device-width, initial-scale=1\.0">',
        "",
    )


def _append_override_stylesheet(html_text: str) -> str:
    return _sub_once(
        html_text,
        r"</head>",
        "<style>.hero { background: hotpink !important; }</style></head>",
    )


def _add_inline_style_override(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'<section class="hero verdict-([^\"]+)">',
        r'<section class="hero verdict-\1" style="display:none">',
    )


def _hide_inventory(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'<section class="inventory-section" id="交付文件与代码盘点">',
        '<section class="inventory-section" id="交付文件与代码盘点" hidden>',
    )


def _add_runtime_verdict_override(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'<body class="verdict-reject">',
        (
            '<body class="verdict-reject" '
            'onload="this.className=\'verdict-conditional\'">'
        ),
    )


def _set_right_to_left_page_direction(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'<body class="verdict-reject">',
        '<body class="verdict-reject" dir="rtl">',
    )


def _insert_base_url(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'(<title>)',
        '<base href="https://invalid.example/">\\1',
    )


def _make_inventory_inert(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'<section class="inventory-section" id="交付文件与代码盘点">',
        '<section class="inventory-section" id="交付文件与代码盘点" inert>',
    )


def _insert_open_dialog(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'(<h2 id="[^"]*审核结论[^"]*">)',
        '<dialog open>审核结论：有条件通过</dialog>\\1',
    )


def _insert_embedded_document(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'(<h2 id="[^"]*审核结论[^"]*">)',
        '<iframe srcdoc="&lt;h1&gt;有条件通过&lt;/h1&gt;"></iframe>\\1',
    )


def _add_legacy_presentation_attribute(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'<p class="hero-summary">',
        '<p class="hero-summary" align="right">',
    )


def _collapse_first_severity_block(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'<div class="severity-block severity-major">',
        '<div class="severity-block severity-major collapsed">',
    )


def _recolor_first_severity_block(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'<div class="severity-block severity-major">',
        '<div class="severity-block severity-info">',
    )


def _strip_first_severity_block_style(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'<div class="severity-block severity-major">',
        '<div class="plain">',
    )


def _disable_major_dashboard_card(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'(<button type="button" class="sev-card sev-major" data-severity="MAJOR")>',
        r'\1 disabled>',
    )


def _break_page_and_layout_shell(html_text: str) -> str:
    mutated = _sub_once(html_text, r'<div class="page">', '<div class="page-broken">')
    return _sub_once(
        mutated,
        r'<div class="layout">',
        '<div class="layout-broken">',
    )


def _duplicate_hero(html_text: str) -> str:
    hero = re.search(r'<section class="hero verdict-[^"]+">', html_text)
    assert hero is not None, "canonical hero opening tag is missing"
    duplicate = f"{hero.group(0)}</section>"
    return html_text[: hero.start()] + duplicate + html_text[hero.start() :]


def _swap_first_two_severity_cards(html_text: str) -> str:
    match = re.search(
        r'(?P<fatal><button[^>]+data-severity="FATAL".*?</button>)\s*'
        r'(?P<critical><button[^>]+data-severity="CRITICAL".*?</button>)',
        html_text,
        flags=re.DOTALL,
    )
    assert match is not None, "canonical severity cards are missing"
    replacement = f"{match.group('critical')}\n{match.group('fatal')}"
    return html_text[: match.start()] + replacement + html_text[match.end() :]


def _empty_inventory(html_text: str) -> str:
    empty_shell = (
        '<section class="inventory-section" id="交付文件与代码盘点">'
        "<h2>交付文件与代码盘点</h2>"
        '<p class="inventory-legend">'
        '<span class="inventory-legend-swatch" aria-hidden="true"></span>'
        f"{INVENTORY_LEGEND}"
        "</p>"
        '<details class="inventory-details" open></details>'
        "</section>"
    )
    return _sub_once(
        html_text,
        r'<section class="inventory-section" id="交付文件与代码盘点">.*?</section>',
        empty_shell,
    )


def _remove_inventory_legend_swatch(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'<span class="inventory-legend-swatch" aria-hidden="true"></span>',
        "",
    )


def _insert_idless_visible_h2(html_text: str) -> str:
    return _sub_once(
        html_text,
        r'(<h2 id="[^"]*审核结论[^"]*">)',
        r"<h2>未纳入目录的可见章节</h2><p>该章节缺少锚点。</p>\1",
    )


def _duplicate_revocation_ledger(html_text: str) -> str:
    duplicate_id = "六-撤销裁定-重复留痕"
    duplicate_title = "六、撤销裁定（重复留痕）"
    mutated = _sub_once(
        html_text,
        r'(<div class="footer">)',
        (
            f'<h2 id="{duplicate_id}">{duplicate_title}</h2>'
            "<p>重复的撤销记录。</p>"
            r"\1"
        ),
    )
    return _sub_once(
        mutated,
        r'(<aside class="sidebar" id="toc-sidebar">.*?<ul>.*?)(</ul>)',
        rf'\1<li><a href="#{duplicate_id}">{duplicate_title}</a></li>\2',
    )


def _break_continuous_section_numbering(html_text: str) -> str:
    mutated = html_text.replace(
        'id="二-提交阻断问题">二、提交阻断问题',
        'id="三-提交阻断问题">三、提交阻断问题',
        1,
    )
    assert mutated != html_text, "canonical blocking heading is missing"
    return mutated.replace(
        'href="#二-提交阻断问题">二、提交阻断问题',
        'href="#三-提交阻断问题">三、提交阻断问题',
        1,
    )


PRESENTATION_MUTATIONS: tuple[tuple[str, Callable[[str], str]], ...] = (
    ("stylesheet-replaced", _replace_stylesheet),
    ("stylesheet-appended", _append_override_stylesheet),
    ("inline-style-override-added", _add_inline_style_override),
    ("inventory-hidden", _hide_inventory),
    ("runtime-verdict-override-added", _add_runtime_verdict_override),
    ("right-to-left-page-direction-added", _set_right_to_left_page_direction),
    ("base-url-added", _insert_base_url),
    ("inventory-made-inert", _make_inventory_inert),
    ("open-dialog-added", _insert_open_dialog),
    ("embedded-document-added", _insert_embedded_document),
    ("legacy-presentation-attribute-added", _add_legacy_presentation_attribute),
    ("javascript-removed", _remove_javascript),
    ("viewport-removed", _remove_viewport),
    ("page-layout-shell-broken", _break_page_and_layout_shell),
    ("hero-duplicated", _duplicate_hero),
    ("severity-card-order-swapped", _swap_first_two_severity_cards),
    ("severity-block-collapsed", _collapse_first_severity_block),
    ("severity-block-recolored", _recolor_first_severity_block),
    ("severity-block-style-stripped", _strip_first_severity_block_style),
    ("severity-dashboard-card-disabled", _disable_major_dashboard_card),
    ("inventory-emptied", _empty_inventory),
    ("inventory-legend-swatch-removed", _remove_inventory_legend_swatch),
    ("visible-h2-without-id", _insert_idless_visible_h2),
    ("revocation-ledger-duplicated", _duplicate_revocation_ledger),
    ("section-numbering-not-continuous", _break_continuous_section_numbering),
)


def test_canonical_renderer_output_is_accepted_by_text_and_file_seams(
    canonical_reader_html: str,
    tmp_path: Path,
) -> None:
    html_path = tmp_path / "canonical_audit_report.html"
    html_path.write_text(canonical_reader_html, encoding="utf-8")

    assert validate_html_presentation_text(canonical_reader_html) == (True, "")
    assert validate_html_presentation_file(html_path) == (True, "")


def _with_adjudication_index(
    html_text: str,
    *,
    detail_heading: str,
    evidence: str = "资产 441",
) -> str:
    index_html = (
        '<details class="inventory-details adjudication-index" open>'
        "<summary>裁定标准与核定理由索引</summary>"
        '<div class="adjudication-index-body">'
        '<h3 id="裁定标准与核定理由索引">裁定标准与核定理由索引</h3>'
        "<table><thead><tr>"
        "<th>编号</th><th>核心问题</th><th>原报告位置</th><th>交付证据</th><th>修订要求</th>"
        "</tr></thead><tbody><tr>"
        f"<td>F-021</td><td>图例缺失</td><td>主报告.docx，图 3</td><td>{evidence}</td><td>补图例</td>"
        "</tr></tbody></table></div></details>"
    )
    with_index = html_text.replace(
        '<h2 id="二-提交阻断问题">',
        index_html + '<h2 id="二-提交阻断问题">',
        1,
    )
    return with_index.replace(
        "必须完成修订。</p>",
        "必须完成修订。</p>"
        '<section class="concrete-error-card">'
        f'<h4 id="具体错误-1">{detail_heading}</h4><p>详情。</p>'
        "</section>",
        1,
    )


def test_adjudication_index_requires_exact_finding_detail_anchor(
    canonical_reader_html: str,
) -> None:
    mutated = _with_adjudication_index(
        canonical_reader_html,
        detail_heading="具体错误 1：汇总问题（F-019 至 F-034）",
    )

    valid, reason = validate_html_presentation_text(mutated)

    assert valid is False
    assert "F-021" in reason


def test_contract_rejects_nonlocal_hyperlink(
    canonical_reader_html: str,
) -> None:
    mutated = canonical_reader_html.replace(
        'href="#一-审核结论"',
        'href="coverage_matrix.md"',
        1,
    )

    valid, reason = validate_html_presentation_text(mutated)

    assert valid is False
    assert "self-contained" in reason


def test_adjudication_index_requires_nonempty_reader_fields_and_accepts_complete_row(
    canonical_reader_html: str,
) -> None:
    valid_html = _with_adjudication_index(
        canonical_reader_html,
        detail_heading="具体错误 1：图例缺失（F-021）",
    )
    invalid_html = _with_adjudication_index(
        canonical_reader_html,
        detail_heading="具体错误 1：图例缺失（F-021）",
        evidence="",
    )

    assert validate_html_presentation_text(valid_html) == (True, "")
    valid, reason = validate_html_presentation_text(invalid_html)
    assert valid is False
    assert "empty required reader field" in reason


def test_contract_rejects_visible_internal_arbitration_crosswalk(
    canonical_reader_html: str,
) -> None:
    internal_crosswalk = (
        '<h3 id="仲裁原始发现交叉索引">仲裁原始发现交叉索引</h3>'
        "<table><thead><tr>"
        "<th>Canonical ID</th><th>分析点</th><th>对应问题</th><th>可搜索定位</th>"
        "</tr></thead><tbody><tr>"
        "<td>CF-01</td><td>fk:a319c6f52536edc6</td><td>F-01</td><td>A:raw:001</td>"
        "</tr></tbody></table>"
    )
    mutated = canonical_reader_html.replace(
        '<div class="footer">',
        internal_crosswalk + '<div class="footer">',
        1,
    )

    valid, reason = validate_html_presentation_text(mutated)

    assert valid is False
    assert "internal arbitration trace" in reason


def test_renderer_cli_refuses_invalid_html_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "final_review_report.md"
    output_path = tmp_path / "invalid_audit_report.html"
    source_path.write_text("# invalid fixture\n", encoding="utf-8")
    monkeypatch.setattr(
        render_final_review_html,
        "parse_args",
        lambda: Namespace(input_path=str(source_path), output=str(output_path)),
    )
    monkeypatch.setattr(render_final_review_html, "build_html", lambda *_args, **_kwargs: "<html></html>")
    monkeypatch.setattr(render_final_review_html, "load_final_decision", lambda *_args: None)

    assert render_final_review_html.main() == 1
    assert not output_path.exists()


@pytest.mark.parametrize(
    ("mutation_name", "mutate"),
    PRESENTATION_MUTATIONS,
    ids=[name for name, _mutate in PRESENTATION_MUTATIONS],
)
def test_presentation_contract_rejects_reader_visible_mutations(
    mutation_name: str,
    mutate: Callable[[str], str],
    canonical_reader_html: str,
    tmp_path: Path,
) -> None:
    mutated = mutate(canonical_reader_html)
    assert mutated != canonical_reader_html

    html_path = tmp_path / f"{mutation_name}.html"
    html_path.write_text(mutated, encoding="utf-8")
    results = {
        "text": validate_html_presentation_text(mutated),
        "file": validate_html_presentation_file(html_path),
    }
    accepted_by = [seam for seam, (valid, _reason) in results.items() if valid]

    assert not accepted_by, (
        f"presentation mutation {mutation_name!r} was accepted by "
        f"{', '.join(accepted_by)}: {results}"
    )
