#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""render_final_review_html.py 单元测试。"""

import sys
from pathlib import Path

import pytest

# 确保 scripts/ 在导入路径中
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from render_final_review_html import (
    apply_inline_formatting,
    build_toc,
    count_issue_levels,
    determine_verdict,
    extract_h1,
    extract_meta_fields,
    reorder_sections,
    slugify,
)


# ── apply_inline_formatting ──────────────────────────────────


class TestApplyInlineFormatting:
    def test_bold(self):
        assert "<strong>abc</strong>" in apply_inline_formatting("**abc**")

    def test_code(self):
        assert "<code>x</code>" in apply_inline_formatting("`x`")

    def test_sev_tag_critical(self):
        result = apply_inline_formatting("4 项 CRITICAL 级问题")
        assert 'class="sev-tag-critical"' in result
        assert "CRITICAL" in result

    def test_sev_tag_all_levels(self):
        for level in ("FATAL", "CRITICAL", "MAJOR", "WARNING", "INFO"):
            result = apply_inline_formatting(f"包含 {level} 关键词")
            assert f'sev-tag-{level.lower()}' in result, f"{level} 未被标记"

    def test_sev_tag_no_double_wrap(self):
        result = apply_inline_formatting("CRITICAL CRITICAL")
        assert result.count("sev-tag-critical") == 2  # 两个独立 span
        assert "sev-tag-critical\"><span" not in result  # 无嵌套

    def test_sev_tag_inside_bold(self):
        result = apply_inline_formatting("**FATAL 问题**")
        assert "<strong>" in result
        assert "sev-tag-fatal" in result

    def test_html_escape(self):
        result = apply_inline_formatting("<script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_link_safe(self):
        result = apply_inline_formatting("[text](https://example.com)")
        assert 'href="https://example.com"' in result

    def test_link_javascript_blocked(self):
        result = apply_inline_formatting("[xss](javascript:alert(1))")
        assert "javascript:" not in result


# ── slugify ──────────────────────────────────────────────────


class TestSlugify:
    def test_chinese(self):
        assert slugify("一、审核结论") == "一-审核结论"

    def test_english(self):
        assert slugify("Hello World") == "hello-world"

    def test_empty(self):
        assert slugify("") == "section"

    def test_special_chars(self):
        assert slugify("test@#$%foo") == "test-foo"


# ── extract_h1 ──────────────────────────────────────────────


class TestExtractH1:
    def test_normal(self):
        assert extract_h1("# 审核报告\n\n正文") == "审核报告"

    def test_missing(self):
        assert extract_h1("无标题文档") == "最终审核报告"


# ── count_issue_levels ───────────────────────────────────────


class TestCountIssueLevels:
    def test_all_levels(self):
        md = "### 🔴 FATAL xxx\n### CRITICAL yyy\n### MAJOR aaa\n### ⚠️ WARNING bbb\n### INFO ccc\n"
        counts = count_issue_levels(md)
        assert counts["FATAL"] == 1
        assert counts["CRITICAL"] == 1
        assert counts["MAJOR"] == 1
        assert counts["WARNING"] == 1
        assert counts["INFO"] == 1

    def test_empty(self):
        counts = count_issue_levels("no issues here")
        assert all(v == 0 for v in counts.values())


# ── determine_verdict ────────────────────────────────────────


class TestDetermineVerdict:
    def test_pass(self):
        cls, text = determine_verdict({"FATAL": 0, "CRITICAL": 0, "MAJOR": 0, "WARNING": 0, "INFO": 0})
        assert cls == "verdict-pass"

    def test_conditional(self):
        cls, text = determine_verdict({"FATAL": 0, "CRITICAL": 1, "MAJOR": 0, "WARNING": 0, "INFO": 0})
        assert cls == "verdict-conditional"

    def test_reject(self):
        cls, text = determine_verdict({"FATAL": 1, "CRITICAL": 0, "MAJOR": 0, "WARNING": 0, "INFO": 0})
        assert cls == "verdict-reject"


# ── extract_meta_fields ──────────────────────────────────────


class TestExtractMetaFields:
    def test_basic(self):
        md = "> **项目名称**：测试项目\n> **审核日期**：2026-04-07\n"
        fields = extract_meta_fields(md)
        assert fields["项目名称"] == "测试项目"
        assert fields["审核日期"] == "2026-04-07"

    def test_colon_variants(self):
        md = "> 项目编号: 26YHB087F\n"
        fields = extract_meta_fields(md)
        assert fields["项目编号"] == "26YHB087F"

    def test_empty(self):
        assert extract_meta_fields("no meta") == {}


# ── reorder_sections ─────────────────────────────────────────


class TestReorderSections:
    def test_moves_detail_after_summary(self):
        content = (
            '<h2 id="一-审核结论">一、审核结论</h2><p>结论</p>'
            '<h2 id="二-执行摘要">二、执行摘要</h2><p>摘要</p>'
            '<h2 id="三-方法论">三、方法论</h2><p>方法</p>'
            '<h2 id="四-问题详述">四、问题详述</h2><p>问题</p>'
        )
        result = reorder_sections(content)
        summary_pos = result.find("执行摘要")
        detail_pos = result.find("问题详述")
        method_pos = result.find("方法论")
        assert summary_pos < detail_pos < method_pos

    def test_no_crash_without_detail(self):
        content = '<h2 id="一-结论">一、结论</h2><p>ok</p>'
        reorder_sections(content)  # 不应崩溃

    def test_renumbers_chinese(self):
        content = (
            '<h2 id="一-审核结论">一、审核结论</h2><p>结论</p>'
            '<h2 id="二-执行摘要">二、执行摘要</h2><p>摘要</p>'
            '<h2 id="四-问题详述">四、问题详述</h2><p>问题</p>'
            '<h2 id="三-方法论">三、方法论</h2><p>方法</p>'
        )
        result = reorder_sections(content)
        # 重排后"问题详述"在第三位，"方法论"在第四位
        assert "三、问题详述" in result
        assert "四、方法论" in result


# ── build_toc ────────────────────────────────────────────────


class TestBuildToc:
    def test_basic(self):
        md = "## 一、结论\n\n## 二、摘要\n"
        toc = build_toc(md)
        assert "<ul>" in toc
        assert "结论" in toc
        assert "摘要" in toc

    def test_toc_has_links(self):
        md = "## 一、审核结论\n"
        toc = build_toc(md)
        assert "<a href=" in toc

    def test_reorder_in_toc(self):
        md = "## 一、审核结论\n## 二、执行摘要\n## 三、方法论\n## 四、问题详述\n"
        toc = build_toc(md)
        summary_pos = toc.find("执行摘要")
        detail_pos = toc.find("问题详述")
        method_pos = toc.find("方法论")
        assert summary_pos < detail_pos < method_pos
