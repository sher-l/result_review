#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fail-closed contract for the reader-facing formal audit HTML."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from lxml import etree
from lxml import html as lxml_html

from policy_loader import load_policy


PRESENTATION_PROFILE = "reader-v3"
PRESENTATION_BASELINE_ID = (
    "framework-concrete-error-cards-and-reader-projection-20260805"
)
PRESENTATION_TEMPLATE = "report_templates/final_review_report_template.html"
EXPECTED_TEMPLATE_SHA256_LF = (
    "2190850fe4cff64c16dfd40e9f30acd391f87105fe7cfb04bd774942e20e8734"
)
EXPECTED_STYLESHEET_SHA256_LF = (
    "9ba9edea2c5adf01da4fc4886d707302ba98356d09d5b2052e54070e4aa8f325"
)
EXPECTED_SCRIPT_SHA256_LF = (
    "9f54e1bf32825828406be42339eeaf4afc2e1dfc1527d83c4b4f9467b740dbd1"
)
INVENTORY_LEGEND_TEXT = (
    "标灰说明：灰色行表示该模块/目录仅交付数据表/数据文件，或仅交付图件/PDF；"
    "标灰仅提示交付类型单一，不代表问题严重度。"
)
HIDDEN_INTERNAL_HEADING_TERMS = (
    "finding_key → F-ID 交叉表",
    "仲裁原始发现交叉索引",
    "F-ID 绑定索引",
)

_VERDICT_TEXTS = {
    "verdict-pass": {"审核结论：合格", "审核结论：建议通过"},
    "verdict-conditional": {"审核结论：有条件合格", "审核结论：有条件通过"},
    "verdict-reject": {"审核结论：不合格", "审核结论：不建议提交"},
}
_VERDICT_CLASSES = frozenset(_VERDICT_TEXTS)
_SEVERITIES = ("FATAL", "CRITICAL", "MAJOR", "WARNING", "INFO")
_INVENTORY_CARDS = (
    ("模块文件总数", "按交付模块合计"),
    ("分析模块", "按交付目录识别"),
    ("代码文件", "R/Python 等脚本"),
    ("数据文件", "csv/xlsx/rds 等"),
    ("图件/PDF文件", "pdf/png/jpg 等"),
    ("配置文件", "配置/环境文件"),
)
_MODULE_HEADERS = ("模块/目录", "总文件", "数据", "PDF图件", "位图", "代码")
_CODE_HEADERS = ("脚本", "语言", "行数", "包数量", "输入/输出引用")
_SEVERITY_TAG_CLASSES = frozenset(f"sev-tag-{level.lower()}" for level in _SEVERITIES)
_SEVERITY_BLOCK_CLASSES = frozenset(
    f"severity-{level.lower()}" for level in _SEVERITIES
)
_DANGEROUS_READER_ATTRIBUTES = frozenset(
    {
        "align",
        "aria-disabled",
        "autofocus",
        "background",
        "bgcolor",
        "border",
        "cellpadding",
        "cellspacing",
        "color",
        "contenteditable",
        "dir",
        "disabled",
        "face",
        "height",
        "hidden",
        "inert",
        "nowrap",
        "popover",
        "size",
        "style",
        "valign",
        "width",
    }
)
_DISALLOWED_READER_TAGS = frozenset(
    {
        "applet",
        "audio",
        "base",
        "canvas",
        "dialog",
        "embed",
        "form",
        "iframe",
        "input",
        "marquee",
        "object",
        "portal",
        "select",
        "svg",
        "textarea",
        "video",
    }
)
_SECTION_ROLES = (
    ("conclusion", "审核结论"),
    ("blockers", "提交阻断问题"),
    ("secondary", "其他已裁定问题"),
    ("resubmit", "复审提交要求"),
    ("revocation", "撤销裁定"),
)
_CN_NUMERALS = (
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "十一", "十二", "十三", "十四", "十五",
)
_FINDING_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(F-\d+)(?![A-Za-z0-9_-])",
    flags=re.IGNORECASE,
)
_CONCRETE_ERROR_HEADING_RE = re.compile(r"^具体错误\s*\d+\s*[：:]\s*\S")


class _ContractError(ValueError):
    """Internal validation failure with a reader-safe reason."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _classes(element: etree._Element) -> set[str]:
    return set((element.get("class") or "").split())


def _text(element: etree._Element) -> str:
    return re.sub(r"\s+", " ", element.text_content()).strip()


def _element_children(element: etree._Element) -> list[etree._Element]:
    return [child for child in element if isinstance(child.tag, str)]


def _elements_with_class(
    root: etree._Element,
    tag: str,
    class_name: str,
) -> list[etree._Element]:
    return [
        element
        for element in root.iter(tag)
        if class_name in _classes(element)
    ]


def _one(elements: Iterable[etree._Element], label: str) -> etree._Element:
    values = list(elements)
    if len(values) != 1:
        raise _ContractError(f"{label} must appear exactly once")
    return values[0]


def _require_element(
    element: etree._Element,
    *,
    tag: str,
    classes: set[str] | None = None,
    element_id: str | None = None,
    label: str,
) -> None:
    if str(element.tag).lower() != tag:
        raise _ContractError(f"{label} must be a {tag} element")
    if classes is not None and _classes(element) != classes:
        raise _ContractError(f"{label} has changed CSS classes")
    if element_id is not None and element.get("id") != element_id:
        raise _ContractError(f"{label} has changed id")


def _presentation_policy() -> dict:
    try:
        policy = load_policy()
    except (OSError, UnicodeError, ValueError) as exc:
        raise _ContractError("reader presentation policy is unreadable") from exc
    configured = policy.get("reader_html_presentation_policy")
    if not isinstance(configured, dict):
        raise _ContractError("reader presentation policy is missing")

    expected = {
        "mode": "enforce",
        "profile": PRESENTATION_PROFILE,
        "baseline_id": PRESENTATION_BASELINE_ID,
        "template": PRESENTATION_TEMPLATE,
        "template_sha256_lf": EXPECTED_TEMPLATE_SHA256_LF,
        "stylesheet_sha256_lf": EXPECTED_STYLESHEET_SHA256_LF,
        "script_sha256_lf": EXPECTED_SCRIPT_SHA256_LF,
        "hash_normalization": "UTF-8 text with LF newlines",
        "required_inventory_legend": INVENTORY_LEGEND_TEXT,
        "hidden_internal_heading_terms": list(HIDDEN_INTERNAL_HEADING_TERMS),
    }
    for field, expected_value in expected.items():
        if configured.get(field) != expected_value:
            raise _ContractError(
                f"reader presentation policy field {field} does not match {PRESENTATION_PROFILE}"
            )
    return configured


def _parse_document(html_text: str) -> etree._Element:
    if not html_text.strip():
        raise _ContractError("HTML presentation input is empty")
    try:
        # libxml2 versions bundled with supported Python runtimes may report
        # HTML5 sectioning tags (section/main/aside/details) as "unknown" when
        # recover=False.  Parse them into a real DOM, then fail closed on the
        # exact topology below instead of relying on libxml2's HTML4 vocabulary.
        parser = lxml_html.HTMLParser(recover=True, no_network=True)
        document = lxml_html.document_fromstring(html_text, parser=parser)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError) as exc:
        raise _ContractError("HTML presentation input is malformed") from exc
    if str(document.tag).lower() != "html":
        raise _ContractError("HTML document root must be html")
    return document


def _validate_assets(document: etree._Element) -> None:
    head = _one(document.xpath("./head"), "head")
    body = _one(document.xpath("./body"), "body")

    for element in document.iter():
        if not isinstance(element.tag, str):
            continue
        tag_name = str(element.tag).lower()
        if tag_name in _DISALLOWED_READER_TAGS:
            raise _ContractError(f"reader HTML contains disallowed {tag_name} content")
        attributes = {str(name).lower(): value for name, value in element.attrib.items()}
        dangerous = sorted(set(attributes).intersection(_DANGEROUS_READER_ATTRIBUTES))
        if dangerous:
            raise _ContractError(
                "reader HTML contains a presentation override attribute: "
                + ", ".join(dangerous)
            )
        for name, value in attributes.items():
            if not name.startswith("on"):
                continue
            is_canonical_sidebar_close = (
                tag_name == "button"
                and _classes(element) == {"sidebar-close"}
                and name == "onclick"
                and value
                == "document.getElementById('toc-sidebar').classList.remove('open')"
            )
            if not is_canonical_sidebar_close:
                raise _ContractError("inline event handlers are not allowed in reader HTML")

    head_children = _element_children(head)
    if [str(child.tag).lower() for child in head_children] != [
        "meta",
        "meta",
        "meta",
        "title",
        "style",
    ]:
        raise _ContractError(
            "head must contain only charset, viewport, profile, title, and stylesheet in order"
        )

    charset = _one(document.xpath(".//meta[@charset]"), "UTF-8 charset meta")
    if (
        charset is not head_children[0]
        or dict(charset.attrib) != {"charset": "UTF-8"}
    ):
        raise _ContractError("charset meta must be UTF-8 and live in head")

    viewport = _one(
        document.xpath('.//meta[@name="viewport"]'),
        "viewport meta",
    )
    if viewport is not head_children[1] or dict(viewport.attrib) != {
        "name": "viewport",
        "content": "width=device-width, initial-scale=1.0",
    }:
        raise _ContractError("viewport meta is missing or changed")

    profile = _one(
        document.xpath('.//meta[@name="rrf-presentation-profile"]'),
        "presentation profile meta",
    )
    if profile is not head_children[2] or dict(profile.attrib) != {
        "name": "rrf-presentation-profile",
        "content": PRESENTATION_PROFILE,
    }:
        raise _ContractError(f"presentation profile must be {PRESENTATION_PROFILE}")

    title = head_children[3]
    if title.attrib:
        raise _ContractError("document title attributes are not allowed")

    styles = document.xpath(".//style")
    style = _one(styles, "embedded stylesheet")
    if style is not head_children[4] or style.attrib or _element_children(style):
        raise _ContractError("embedded stylesheet must be one plain style element in head")
    if document.xpath(
        './/link[contains(concat(" ", normalize-space(@rel), " "), " stylesheet ")]'
    ):
        raise _ContractError("external or additional stylesheets are not allowed")
    if _sha256_text(style.text or "") != EXPECTED_STYLESHEET_SHA256_LF:
        raise _ContractError(
            f"stylesheet does not match the approved {PRESENTATION_PROFILE} baseline"
        )

    scripts = document.xpath(".//script")
    script = _one(scripts, "reader interaction script")
    if script.getparent() is not body or script.get("src") or _element_children(script):
        raise _ContractError("reader script must be one embedded script at body level")
    if _sha256_text(script.text or "") != EXPECTED_SCRIPT_SHA256_LF:
        raise _ContractError(
            f"reader script does not match the approved {PRESENTATION_PROFILE} baseline"
        )


def _validate_standalone_references(document: etree._Element) -> None:
    """Reject links and resources that would make the delivered HTML depend on sidecars."""
    for element in document.xpath(".//*[@src]"):
        raise _ContractError(
            "reader HTML must be self-contained; external or local src resources are not allowed"
        )
    for element in document.xpath(".//*[@href]"):
        href = (element.get("href") or "").strip()
        if str(element.tag).lower() != "a" or not href.startswith("#"):
            raise _ContractError(
                "reader HTML must be self-contained; hyperlinks may only target page-local anchors"
            )


def _validate_severity_dashboard(dashboard: etree._Element) -> dict[str, int]:
    buttons = _element_children(dashboard)
    if len(buttons) != len(_SEVERITIES):
        raise _ContractError("severity dashboard must contain exactly five cards")
    counts: dict[str, int] = {}
    for button, severity in zip(buttons, _SEVERITIES):
        _require_element(
            button,
            tag="button",
            classes={"sev-card", f"sev-{severity.lower()}"},
            label=f"{severity} severity card",
        )
        if dict(button.attrib) != {
            "type": "button",
            "class": f"sev-card sev-{severity.lower()}",
            "data-severity": severity,
        }:
            raise _ContractError("severity dashboard card order or attributes changed")
        spans = _element_children(button)
        if len(spans) != 2:
            raise _ContractError(f"{severity} severity card is incomplete")
        _require_element(
            spans[0], tag="span", classes={"sev-count"}, label=f"{severity} count"
        )
        _require_element(
            spans[1], tag="span", classes={"sev-label"}, label=f"{severity} label"
        )
        if not re.fullmatch(r"\d+", _text(spans[0])) or _text(spans[1]) != severity:
            raise _ContractError(f"{severity} severity card content is invalid")
        counts[severity] = int(_text(spans[0]))
    return counts


def _validate_finding_presentation(
    main: etree._Element,
    dashboard_counts: dict[str, int],
) -> None:
    blocks = [
        element
        for element in main.iter("div")
        if "severity-block" in _classes(element)
    ]
    blocks_by_severity = {severity: [] for severity in _SEVERITIES}
    validated_headings: set[etree._Element] = set()
    validated_concrete_headings: set[etree._Element] = set()
    validated_finding_cards: set[etree._Element] = set()
    for block in blocks:
        severity_classes = {
            class_name
            for class_name in _classes(block)
            if class_name in _SEVERITY_BLOCK_CLASSES
        }
        if len(severity_classes) != 1:
            raise _ContractError("finding severity block has no unique severity class")
        severity_class = next(iter(severity_classes))
        severity = severity_class.removeprefix("severity-").upper()
        if severity not in _SEVERITIES or _classes(block) != {
            "severity-block",
            severity_class,
        }:
            raise _ContractError("finding severity block classes changed")
        if dict(block.attrib) != {
            "class": f"severity-block {severity_class}"
        }:
            raise _ContractError("finding severity block attributes changed")
        children = _element_children(block)
        if not children or children[0].tag != "h3":
            raise _ContractError("finding severity block must begin with its H3 title")
        heading = children[0]
        if not (heading.get("id") or "").strip():
            raise _ContractError("finding severity title must have an anchor")
        tag_class = f"sev-tag-{severity.lower()}"
        severity_tags = [
            element
            for element in heading.iter("span")
            if _classes(element).intersection(_SEVERITY_TAG_CLASSES)
        ]
        if (
            len(severity_tags) != 1
            or _classes(severity_tags[0]) != {tag_class}
            or _text(severity_tags[0]) != severity
        ):
            raise _ContractError("finding title and severity block presentation disagree")
        blocks_by_severity[severity].append(block)
        validated_headings.add(heading)

        finding_cards = [
            child
            for child in children[1:]
            if child.tag == "section" and "concrete-error-card" in _classes(child)
        ]
        for card in finding_cards:
            if _classes(card) != {"concrete-error-card"} or dict(card.attrib) != {
                "class": "concrete-error-card"
            }:
                raise _ContractError("concrete finding card attributes changed")
            card_children = _element_children(card)
            if not card_children or card_children[0].tag != "h4":
                raise _ContractError("concrete finding card must begin with its H4 title")
            concrete_heading = card_children[0]
            if not _CONCRETE_ERROR_HEADING_RE.match(_text(concrete_heading)):
                raise _ContractError(
                    "concrete-error-card is reserved for numbered concrete errors"
                )
            if not (concrete_heading.get("id") or "").strip():
                raise _ContractError("concrete finding title must have an anchor")
            if len(card_children) < 2 or _text(card) == _text(concrete_heading):
                raise _ContractError("concrete finding card has no visible finding detail")
            validated_concrete_headings.add(concrete_heading)
            validated_finding_cards.add(card)

    tagged_headings = {
        heading
        for heading in main.iter("h3")
        if any(
            _classes(element).intersection(_SEVERITY_TAG_CLASSES)
            for element in heading.iter("span")
        )
    }
    if tagged_headings != validated_headings:
        raise _ContractError(
            "every reader-visible severity finding must use its approved severity block"
        )
    concrete_headings = {
        heading
        for heading in main.iter("h4")
        if _CONCRETE_ERROR_HEADING_RE.match(_text(heading))
    }
    if concrete_headings != validated_concrete_headings:
        raise _ContractError(
            "every numbered concrete error must use its own approved finding card"
        )
    finding_cards = {
        element
        for element in main.iter("section")
        if "concrete-error-card" in _classes(element)
    }
    if finding_cards != validated_finding_cards:
        raise _ContractError("finding cards must be direct children of severity blocks")
    for severity in _SEVERITIES:
        if bool(dashboard_counts[severity]) != bool(blocks_by_severity[severity]):
            raise _ContractError(
                f"{severity} dashboard availability and finding blocks disagree"
            )


def _validate_internal_trace_projection(main: etree._Element) -> None:
    visible_internal_headings = sorted(
        {
            _text(heading)
            for level in range(1, 7)
            for heading in main.iter(f"h{level}")
            if _text(heading) in HIDDEN_INTERNAL_HEADING_TERMS
        }
    )
    if visible_internal_headings:
        raise _ContractError(
            "reader HTML exposes an internal arbitration trace heading: "
            + ", ".join(visible_internal_headings)
        )

    for table in main.iter("table"):
        headers = {_text(cell) for cell in table.xpath("./thead/tr/th")}
        if {"分析点", "对应问题", "可搜索定位"}.issubset(headers):
            raise _ContractError(
                "reader HTML exposes an internal arbitration trace crosswalk"
            )


def _validate_shell(document: etree._Element) -> tuple[etree._Element, etree._Element]:
    if document.get("lang") != "zh-CN":
        raise _ContractError("reader document language must be zh-CN")
    head = _one(document.xpath("./head"), "head")
    title = _one(head.xpath("./title"), "document title")
    if not _text(title):
        raise _ContractError("document title is empty")
    body = _one(document.xpath("./body"), "body")
    verdict_classes = _classes(body).intersection(_VERDICT_CLASSES)
    if len(verdict_classes) != 1 or _classes(body) != verdict_classes:
        raise _ContractError("body must use exactly one verdict class")
    verdict_class = next(iter(verdict_classes))

    body_children = _element_children(body)
    if len(body_children) != 4:
        raise _ContractError("body must contain page, two controls, and the reader script")
    page, toc_toggle, back_top, script = body_children
    _require_element(page, tag="div", classes={"page"}, label="page shell")
    _require_element(
        toc_toggle,
        tag="button",
        classes={"toc-toggle"},
        element_id="toc-toggle",
        label="TOC toggle",
    )
    _require_element(
        back_top,
        tag="button",
        classes={"back-top"},
        element_id="back-top",
        label="back-to-top control",
    )
    _require_element(script, tag="script", classes=set(), label="reader script")
    if (
        toc_toggle.get("type") != "button"
        or toc_toggle.get("aria-controls") != "toc-sidebar"
        or toc_toggle.get("aria-expanded") != "false"
        or not toc_toggle.get("aria-label")
        or back_top.get("type") != "button"
        or not back_top.get("aria-label")
    ):
        raise _ContractError("floating reader controls are incomplete")

    if len(_elements_with_class(document, "div", "page")) != 1:
        raise _ContractError("page shell must appear exactly once")
    page_children = _element_children(page)
    if len(page_children) != 2:
        raise _ContractError("page shell must contain hero followed by main layout")
    hero, layout = page_children
    _require_element(
        hero,
        tag="section",
        classes={"hero", verdict_class},
        label="hero",
    )
    _require_element(layout, tag="div", classes={"layout"}, label="main layout")
    if len(_elements_with_class(document, "section", "hero")) != 1:
        raise _ContractError("hero must appear exactly once")
    if len(_elements_with_class(document, "div", "layout")) != 1:
        raise _ContractError("main layout must appear exactly once")

    hero_children = _element_children(hero)
    if len(hero_children) != 1:
        raise _ContractError("hero must contain one hero-top block")
    hero_top = hero_children[0]
    _require_element(hero_top, tag="div", classes={"hero-top"}, label="hero top")
    top_children = _element_children(hero_top)
    if len(top_children) != 7:
        raise _ContractError("hero top has missing or reordered reader components")
    brand, heading, subtitle, badges, banner, summary, dashboard = top_children
    _require_element(brand, tag="div", classes={"hero-brand"}, label="hero brand")
    _require_element(heading, tag="h1", classes=set(), label="hero title")
    _require_element(subtitle, tag="p", classes={"hero-subtitle"}, label="project subtitle")
    _require_element(badges, tag="div", classes={"badge-row"}, label="metadata badges")
    _require_element(
        banner,
        tag="div",
        classes={"verdict-banner", verdict_class},
        label="verdict banner",
    )
    _require_element(summary, tag="p", classes={"hero-summary"}, label="hero summary")
    _require_element(
        dashboard,
        tag="div",
        classes={"severity-dashboard"},
        label="severity dashboard",
    )
    if not _text(brand) or not _text(heading) or not _text(summary):
        raise _ContractError("hero brand, title, and summary must be non-empty")
    badge_children = _element_children(badges)
    if not badge_children or any(
        child.tag != "span" or _classes(child) != {"badge"} or not _text(child)
        for child in badge_children
    ):
        raise _ContractError("metadata badge row is empty or malformed")
    banner_children = _element_children(banner)
    if len(banner_children) != 2:
        raise _ContractError("verdict banner is incomplete")
    _require_element(
        banner_children[0],
        tag="span",
        classes={"verdict-icon"},
        label="verdict icon",
    )
    _require_element(
        banner_children[1], tag="span", classes=set(), label="verdict text"
    )
    if _text(banner_children[1]) not in _VERDICT_TEXTS[verdict_class]:
        raise _ContractError("verdict class and reader-visible verdict text disagree")
    dashboard_counts = _validate_severity_dashboard(dashboard)

    layout_children = _element_children(layout)
    if len(layout_children) != 2:
        raise _ContractError("main layout must contain sidebar followed by content")
    sidebar, main = layout_children
    _require_element(
        sidebar,
        tag="aside",
        classes={"sidebar"},
        element_id="toc-sidebar",
        label="sidebar TOC",
    )
    _require_element(main, tag="main", classes={"content"}, label="main content")
    if len(document.xpath('.//aside[@id="toc-sidebar"]')) != 1:
        raise _ContractError("sidebar TOC must appear exactly once")
    if len(_elements_with_class(document, "main", "content")) != 1:
        raise _ContractError("main content must appear exactly once")
    _validate_finding_presentation(main, dashboard_counts)

    sidebar_children = _element_children(sidebar)
    if len(sidebar_children) != 2:
        raise _ContractError("sidebar must contain its header and one TOC list")
    sidebar_head, toc_list = sidebar_children
    _require_element(
        sidebar_head, tag="div", classes={"sidebar-head"}, label="sidebar header"
    )
    _require_element(toc_list, tag="ul", classes=set(), label="sidebar TOC list")
    sidebar_head_children = _element_children(sidebar_head)
    if len(sidebar_head_children) != 2:
        raise _ContractError("sidebar header is incomplete")
    _require_element(
        sidebar_head_children[0], tag="h2", classes=set(), label="sidebar title"
    )
    _require_element(
        sidebar_head_children[1],
        tag="button",
        classes={"sidebar-close"},
        label="sidebar close control",
    )
    if _text(sidebar_head_children[0]) != "📑 目录导航":
        raise _ContractError("sidebar title changed")
    if (
        sidebar_head_children[1].get("type") != "button"
        or sidebar_head_children[1].get("onclick")
        != "document.getElementById('toc-sidebar').classList.remove('open')"
    ):
        raise _ContractError("sidebar close control is incomplete")
    return sidebar, main


def _validate_inventory_table(
    details: etree._Element,
    *,
    summary_text: str,
    headers: tuple[str, ...],
) -> list[etree._Element]:
    children = _element_children(details)
    if len(children) != 2:
        raise _ContractError(f"{summary_text} table wrapper is incomplete")
    summary, wrapper = children
    _require_element(summary, tag="summary", classes=set(), label=f"{summary_text} summary")
    _require_element(
        wrapper,
        tag="div",
        classes={"inventory-table-wrap"},
        label=f"{summary_text} table wrapper",
    )
    if _text(summary) != summary_text:
        raise _ContractError(f"{summary_text} summary text changed")
    table = _one(wrapper.xpath("./table"), f"{summary_text} table")
    _require_element(
        table, tag="table", classes={"inventory-table"}, label=f"{summary_text} table"
    )
    actual_headers = [_text(cell) for cell in table.xpath("./thead/tr/th")]
    if tuple(actual_headers) != headers:
        raise _ContractError(f"{summary_text} table columns are missing or reordered")
    rows = table.xpath("./tbody/tr")
    if not rows:
        raise _ContractError(f"{summary_text} table has no delivery rows")
    return rows


def _validate_inventory(main: etree._Element) -> etree._Element:
    inventories = document_inventories = [
        element
        for element in main.getroottree().getroot().iter("section")
        if element.get("id") == "交付文件与代码盘点"
        and "inventory-section" in _classes(element)
    ]
    if len(document_inventories) != 1:
        raise _ContractError("delivery inventory must appear exactly once")
    inventory = inventories[0]
    main_children = _element_children(main)
    if not main_children or main_children[0] is not inventory:
        raise _ContractError("delivery inventory must be the first main-content component")
    _require_element(
        inventory,
        tag="section",
        classes={"inventory-section"},
        element_id="交付文件与代码盘点",
        label="delivery inventory",
    )
    children = _element_children(inventory)
    legends = [
        child
        for child in children
        if child.tag == "p" and _classes(child) == {"inventory-legend"}
    ]
    if len(legends) != 1:
        raise _ContractError("inventory grey-row legend must appear exactly once")
    if len(children) != 6:
        raise _ContractError("delivery inventory is incomplete or reordered")
    heading, description, grid, legend, module_details, code_delivery = children
    _require_element(heading, tag="h2", classes=set(), label="inventory heading")
    _require_element(
        description,
        tag="p",
        classes={"inventory-desc"},
        label="inventory description",
    )
    _require_element(grid, tag="div", classes={"inventory-grid"}, label="inventory cards")
    _require_element(
        legend,
        tag="p",
        classes={"inventory-legend"},
        label="inventory grey-row legend",
    )
    _require_element(
        module_details,
        tag="details",
        classes={"inventory-details"},
        label="module inventory details",
    )
    if _text(heading) != "交付文件与代码盘点" or heading.get("id"):
        raise _ContractError("inventory heading text or anchor changed")
    if _text(description) != "按当前交付目录统计，用于概览文件、模块和脚本数量。":
        raise _ContractError("inventory description changed")

    cards = _element_children(grid)
    if len(cards) != len(_INVENTORY_CARDS):
        raise _ContractError("delivery inventory must contain exactly six summary cards")
    for card, (expected_label, expected_note) in zip(cards, _INVENTORY_CARDS):
        _require_element(card, tag="div", classes={"inventory-card"}, label=expected_label)
        card_children = _element_children(card)
        if len(card_children) != 3:
            raise _ContractError(f"inventory card {expected_label} is incomplete")
        value, label, note = card_children
        _require_element(value, tag="span", classes={"inventory-value"}, label="card value")
        _require_element(label, tag="span", classes={"inventory-label"}, label="card label")
        _require_element(note, tag="span", classes={"inventory-note"}, label="card note")
        if (
            not re.fullmatch(r"\d+", _text(value))
            or _text(label) != expected_label
            or _text(note) != expected_note
        ):
            raise _ContractError(f"inventory card {expected_label} content changed")

    swatches = _element_children(legend)
    if len(swatches) != 1:
        raise _ContractError("inventory grey-row legend swatch is missing")
    _require_element(
        swatches[0],
        tag="span",
        classes={"inventory-legend-swatch"},
        label="inventory legend swatch",
    )
    if swatches[0].get("aria-hidden") != "true" or _text(legend) != INVENTORY_LEGEND_TEXT:
        raise _ContractError("inventory grey-row legend text or swatch changed")

    if "open" not in module_details.attrib:
        raise _ContractError("module inventory details must be expanded by default")
    module_rows = _validate_inventory_table(
        module_details,
        summary_text="模块文件计数",
        headers=_MODULE_HEADERS,
    )
    for row in module_rows:
        cells = row.xpath("./td")
        if len(cells) != len(_MODULE_HEADERS) or not _text(cells[0]):
            raise _ContractError("module inventory row is incomplete")
        numeric = [_text(cell) for cell in cells[1:]]
        if any(not re.fullmatch(r"\d+", value) for value in numeric):
            raise _ContractError("module inventory counts must be non-negative integers")
        total, data_count, pdf_count, image_count, _code_count = map(int, numeric)
        should_be_grey = total > 0 and total in (
            data_count,
            pdf_count + image_count,
        )
        expected_classes = {"inventory-row-single-kind"} if should_be_grey else set()
        if _classes(row) != expected_classes:
            raise _ContractError(
                "single-kind delivery rows must use the approved grey-row cue exactly"
            )

    if code_delivery.tag == "details":
        _require_element(
            code_delivery,
            tag="details",
            classes={"inventory-details"},
            label="code inventory details",
        )
        if "open" in code_delivery.attrib:
            raise _ContractError("code inventory details must be collapsed by default")
        code_rows = _validate_inventory_table(
            code_delivery,
            summary_text="代码文件清单",
            headers=_CODE_HEADERS,
        )
        for row in code_rows:
            cells = row.xpath("./td")
            if (
                len(cells) != len(_CODE_HEADERS)
                or not _text(cells[0])
                or not _text(cells[1])
                or any(not re.fullmatch(r"\d+", _text(cell)) for cell in cells[2:])
            ):
                raise _ContractError("code inventory row is incomplete")
    else:
        _require_element(
            code_delivery,
            tag="div",
            classes={"inventory-empty"},
            label="empty code inventory notice",
        )
        if _text(code_delivery) != "当前交付未提供可核验代码文件。":
            raise _ContractError("empty code inventory notice changed")
    return inventory


def _validate_adjudication_finding_routes(body: etree._Element) -> None:
    """Require every adjudication-row finding to retain readable fields and an H4 target."""
    required_headers = ("核心问题", "原报告位置", "交付证据", "修订要求")
    finding_ids: set[str] = set()
    for table in body.xpath(".//table"):
        headers = [_text(cell) for cell in table.xpath("./thead/tr/th")]
        rows = table.xpath("./tbody/tr")
        table_finding_ids = {
            match.group(1).upper()
            for row in rows
            for match in _FINDING_ID_RE.finditer(_text(row))
        }
        if not table_finding_ids:
            continue
        missing_headers = [header for header in required_headers if header not in headers]
        if missing_headers:
            raise _ContractError(
                "adjudication index is missing required columns: "
                + ", ".join(missing_headers)
            )
        header_indexes = {header: headers.index(header) for header in required_headers}
        for row in rows:
            cells = row.xpath("./td")
            row_finding_ids = [
                match.group(1) for match in _FINDING_ID_RE.finditer(_text(row))
            ]
            if not row_finding_ids:
                continue
            finding_id = row_finding_ids[0].upper()
            if any(index >= len(cells) or not _text(cells[index]) for index in header_indexes.values()):
                raise _ContractError(
                    f"adjudication index row {finding_id} has an empty required reader field"
                )
        finding_ids.update(table_finding_ids)

    detail_headings = [_text(heading) for heading in body.getroottree().xpath(".//main//h4[@id]")]
    missing_targets = [
        finding_id
        for finding_id in sorted(finding_ids)
        if not any(
            re.search(
                rf"(?<![A-Za-z0-9_-]){re.escape(finding_id)}(?![A-Za-z0-9_-])",
                heading,
                flags=re.IGNORECASE,
            )
            for heading in detail_headings
        )
    ]
    if missing_targets:
        raise _ContractError(
            "adjudication findings missing exact concrete-error anchors: "
            + ", ".join(missing_targets)
        )


def _validate_toc_and_report(
    document: etree._Element,
    sidebar: etree._Element,
    main: etree._Element,
    inventory: etree._Element,
) -> None:
    main_children = _element_children(main)
    footers = _elements_with_class(document, "div", "footer")
    footer = _one(footers, "reader footer")
    if not main_children or main_children[-1] is not footer:
        raise _ContractError("reader footer must be the final main-content component")
    _require_element(footer, tag="div", classes={"footer"}, label="reader footer")
    if not re.search(r"由 result_review_framework v[\d.]+ 自动生成", _text(footer)):
        raise _ContractError("reader footer is empty or changed")

    inventory_headings = inventory.xpath(".//h2")
    if len(inventory_headings) != 1:
        raise _ContractError("inventory must contain exactly one non-TOC H2 heading")
    report_headings = [child for child in main_children if child.tag == "h2"]
    all_main_headings = main.xpath(".//h2")
    if all_main_headings != [inventory_headings[0], *report_headings]:
        raise _ContractError("all reader report H2 headings must be direct main-content sections")
    if len(report_headings) < 2:
        raise _ContractError("reader report must include conclusion and blocking sections")

    heading_entries: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for index, heading in enumerate(report_headings):
        heading_id = (heading.get("id") or "").strip()
        heading_text = _text(heading)
        if not heading_id or not heading_text:
            raise _ContractError("every visible reader H2 must have a non-empty anchor and title")
        if heading_id in seen_ids:
            raise _ContractError("reader report contains duplicate H2 anchors")
        seen_ids.add(heading_id)
        if index >= len(_CN_NUMERALS):
            raise _ContractError("reader report has more numbered sections than supported")
        numeral = _CN_NUMERALS[index]
        if not heading_text.startswith(f"{numeral}、") or not heading_id.startswith(
            f"{numeral}-"
        ):
            raise _ContractError("reader H2 numbering must be continuous and match its anchor")
        heading_entries.append((heading_id, heading_text))

    document_ids = [
        (element.get("id") or "").strip()
        for element in document.xpath('.//*[@id]')
        if (element.get("id") or "").strip()
    ]
    if len(document_ids) != len(set(document_ids)):
        raise _ContractError("reader HTML contains duplicate element ids")

    toc_list = _element_children(sidebar)[1]
    toc_items = _element_children(toc_list)
    toc_entries: list[tuple[str, str]] = []
    for item in toc_items:
        _require_element(item, tag="li", classes=set(), label="TOC item")
        anchors = _element_children(item)
        if len(anchors) != 1:
            raise _ContractError("each TOC item must contain one link")
        anchor = anchors[0]
        _require_element(anchor, tag="a", classes=set(), label="TOC link")
        href = anchor.get("href") or ""
        if not href.startswith("#") or not _text(anchor):
            raise _ContractError("TOC link is missing its anchor or title")
        toc_entries.append((href[1:], _text(anchor)))
    if toc_entries != heading_entries:
        raise _ContractError("sidebar TOC must exactly match visible reader H2 order")

    roles: list[str] = []
    for _heading_id, heading_text in heading_entries:
        matches = [role for role, marker in _SECTION_ROLES if marker in heading_text]
        if len(matches) != 1:
            raise _ContractError("reader report contains an unknown or ambiguous H2 section")
        roles.append(matches[0])
    if roles[:2] != ["conclusion", "blockers"]:
        raise _ContractError("reader report must begin with conclusion then blocking issues")
    if len(roles) != len(set(roles)):
        raise _ContractError("reader report contains a duplicated canonical section")
    role_order = [role for role, _marker in _SECTION_ROLES]
    if roles != sorted(roles, key=role_order.index):
        raise _ContractError("reader report sections are out of canonical order")
    if "revocation" in roles and roles[-1] != "revocation":
        raise _ContractError("revocation ledger must be the final visible H2 section")
    if any("逐分析点审核结果" in text for _heading_id, text in heading_entries):
        raise _ContractError("analysis navigation section must remain hidden in reader HTML")

    heading_positions = [main_children.index(heading) for heading in report_headings]
    footer_position = main_children.index(footer)
    for index, start in enumerate(heading_positions):
        end = heading_positions[index + 1] if index + 1 < len(heading_positions) else footer_position
        payload = main_children[start + 1 : end]
        if not payload or not any(_text(element) for element in payload):
            raise _ContractError(
                f"reader section {heading_entries[index][1]} has no visible content"
            )

    adjudications = _elements_with_class(document, "details", "adjudication-index")
    has_adjudication_text = "裁定标准与核定理由索引" in _text(main)
    if has_adjudication_text:
        adjudication = _one(adjudications, "adjudication index")
        _require_element(
            adjudication,
            tag="details",
            classes={"inventory-details", "adjudication-index"},
            label="adjudication index",
        )
        if adjudication.getparent() is not main or "open" not in adjudication.attrib:
            raise _ContractError("adjudication index must be expanded at main-content level")
        adjudication_children = _element_children(adjudication)
        if len(adjudication_children) != 2:
            raise _ContractError("adjudication index is incomplete")
        summary, body = adjudication_children
        _require_element(summary, tag="summary", classes=set(), label="adjudication summary")
        _require_element(
            body,
            tag="div",
            classes={"adjudication-index-body"},
            label="adjudication body",
        )
        if _text(summary) != "裁定标准与核定理由索引" or not _text(body):
            raise _ContractError("adjudication index content is empty or changed")
        _validate_adjudication_finding_routes(body)
        blocker_heading = report_headings[roles.index("blockers")]
        if main_children.index(adjudication) > main_children.index(blocker_heading):
            raise _ContractError("adjudication index must appear before blocking issues")
    elif adjudications:
        raise _ContractError("adjudication index shell is present without its reader title")


def validate_html_presentation_assets_text(html_text: str) -> tuple[bool, str]:
    """Validate the policy-owned profile and exact reader assets only."""
    try:
        _presentation_policy()
        document = _parse_document(html_text)
        _validate_assets(document)
    except _ContractError as exc:
        return False, str(exc)
    return True, ""


def validate_html_presentation_template_text(html_text: str) -> tuple[bool, str]:
    """Validate the immutable reader-v3 template baseline used by framework health."""
    try:
        _presentation_policy()
        if _sha256_text(html_text) != EXPECTED_TEMPLATE_SHA256_LF:
            raise _ContractError(
                f"HTML template does not match the approved {PRESENTATION_PROFILE} baseline"
            )
        document = _parse_document(html_text)
        _validate_assets(document)
        required_placeholders = (
            "{{VERDICT_CLASS}}",
            "{{CONTENT_HTML}}",
            "{{TOC_HTML}}",
            "{{FRAMEWORK_VERSION}}",
        )
        if any(placeholder not in html_text for placeholder in required_placeholders):
            raise _ContractError("HTML template is missing a required reader placeholder")
    except _ContractError as exc:
        return False, str(exc)
    return True, ""


def validate_html_presentation_template_file(
    template_path: Path,
) -> tuple[bool, str]:
    try:
        html_text = template_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False, "HTML presentation template is missing or unreadable"
    return validate_html_presentation_template_text(html_text)


def validate_html_presentation_text(html_text: str) -> tuple[bool, str]:
    """Validate exact assets, real DOM topology, and reader-visible content order."""
    try:
        _presentation_policy()
        document = _parse_document(html_text)
        _validate_assets(document)
        _validate_standalone_references(document)
        sidebar, main = _validate_shell(document)
        inventory = _validate_inventory(main)
        _validate_internal_trace_projection(main)
        _validate_toc_and_report(document, sidebar, main, inventory)
    except _ContractError as exc:
        return False, str(exc)
    return True, ""


def validate_html_presentation_file(html_path: Path) -> tuple[bool, str]:
    try:
        html_text = html_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False, "HTML presentation input is missing or unreadable"
    return validate_html_presentation_text(html_text)
