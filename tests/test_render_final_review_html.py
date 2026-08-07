#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""render_final_review_html.py 单元测试。"""

import json
import re
import sys
from pathlib import Path

import pytest

# 确保 scripts/ 在导入路径中
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from render_final_review_html import (
    apply_inline_formatting,
    build_canonical_findings_html,
    build_consistency_check_html,
    build_delivery_inventory_html,
    build_html,
    collapse_adjudication_reason_index,
    remove_analysis_navigation,
    remove_issue_dashboard_source,
    build_toc,
    count_issue_levels,
    determine_verdict,
    defer_revocation_ledger,
    extract_executive_summary,
    extract_h1,
    extract_meta_fields,
    humanize_image_references,
    load_framework_version,
    parse_analysis_table,
    parse_issue_entries,
    render_markdown,
    reader_facing_markdown,
    split_table_cells,
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


class TestEvidenceGroupRendering:
    def test_expands_aggregated_insufficient_visual_evidence(self):
        markdown = (
            "- 原始 07.cds_trajectory_UMAP.png、"
            "图 2.1「图 2.1.10｜Fibroblasts拟时序轨迹分析」、"
            "图 2.1「图 2.1.11｜成纤维细胞动态表达特征」的轨迹/表达细胞覆盖或分辨率不足，"
            "图 2.5「组合模型 C-index 热图」的热图无法逐项读取；"
            "上述四项均为证据不足，须补高分辨率源图、cluster/细胞映射或数值表，不得视为通过。"
        )

        rendered = render_markdown(markdown)

        assert 'class="evidence-item-list"' in rendered
        assert rendered.count("<li>") == 5
        assert "以下 4 项证据不足" in rendered
        assert "结论与补件要求" in rendered

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

    def test_nonfragment_link_is_rendered_as_text(self):
        result = apply_inline_formatting("[text](https://example.com)")
        assert result == "text"

    def test_page_local_link_is_preserved(self):
        result = apply_inline_formatting("[目录](#一-审核结论)")
        assert 'href="#一-审核结论"' in result

    def test_local_sidecar_link_is_rendered_as_text(self):
        result = apply_inline_formatting("[覆盖矩阵](coverage_matrix.md)")
        assert result == "覆盖矩阵"

    def test_link_javascript_blocked(self):
        result = apply_inline_formatting("[xss](javascript:alert(1))")
        assert "javascript:" not in result

    def test_wildcard_path_not_italicized(self):
        result = apply_inline_formatting("TBI/GBD/*/tables/*heterogeneity.csv")
        assert "<em>" not in result

    def test_original_quote_has_grey_highlight(self):
        rendered = render_markdown('- **原文短句**：“图2.13 | LAMA2虚拟敲除结果”。')

        assert '<span class="original-quote">“图2.13 | LAMA2虚拟敲除结果”</span>' in rendered

    def test_deduplicates_search_quote_when_it_matches_original_quote(self):
        markdown = (
            "- **原报告位置**：`报告.docx`，相关结果章节；可搜索原文短句“Figure 21 子图编号错误”。\n"
            "- **原文短句**：Figure 21 子图编号错误。"
        )

        rendered = render_markdown(markdown)

        assert "可搜索原文短句" not in rendered
        assert rendered.count("Figure 21 子图编号错误") == 1
        assert "<strong>原报告位置</strong>" in rendered
        assert "<strong>原文短句</strong>" in rendered

    def test_separates_verification_conclusion_from_repeated_report_quote(self):
        markdown = (
            "- **原报告位置**：`报告.docx`，相关结果章节；"
            "可搜索原文短句“数据集GSE89408：下载GSE12452”。\n"
            "- **原文短句**：“数据集GSE89408：下载GSE12452”\n"
            "- **交付证据**：见下列证据条目。\n"
            "  - `报告.docx`（报告对应段落）：“数据集GSE89408：下载GSE12452”；"
            "核验说明：同一句中的数据集标识与下载对象不一致。\n"
            "- **修订要求**：统一数据集标识。"
        )

        rendered = render_markdown(markdown)

        assert rendered.count("数据集GSE89408：下载GSE12452") == 1
        assert "交付证据" not in rendered
        assert "核验说明" not in rendered
        assert "<strong>核验结论</strong>：同一句中的数据集标识与下载对象不一致。" in rendered

    def test_keeps_distinct_evidence_source_when_separating_verification_conclusion(self):
        markdown = (
            "- **原报告位置**：`报告.docx`，相关结果章节。\n"
            "- **原文短句**：“报告称使用人类数据库”\n"
            "- **交付证据**：见下列证据条目。\n"
            "  - `报告.docx; script.R`（报告和脚本对应段落）："
            "“报告称使用人类数据库”；核验说明：脚本未记录数据库赋值。"
        )

        rendered = render_markdown(markdown)

        assert "<strong>核验来源</strong>：<code>报告.docx; script.R</code>（报告和脚本对应段落）" in rendered
        assert "<strong>核验结论</strong>：脚本未记录数据库赋值。" in rendered

    def test_keeps_search_quote_when_it_differs_from_original_quote(self):
        markdown = (
            "- **原报告位置**：`报告.docx`；可搜索原文短句“Figure 21 图注”。\n"
            "- **原文短句**：Figure 21 子图编号错误。"
        )

        rendered = render_markdown(markdown)

        assert "可搜索原文短句" in rendered
        assert rendered.count("Figure 21") == 2


class TestReaderFacingMarkdown:
    def test_compacts_report_figure_evidence_to_title_and_panel(self, tmp_path):
        (tmp_path / "visual_audit_checklist.json").write_text(
            json.dumps(
                [
                    {
                        "filename": "image_057.png",
                        "figure_id": "Figure 21",
                        "caption": (
                            "Figure 21 空间转录组数据的非负矩阵分解（NMF）及其生物学表征。"
                            "A. NMF 数值特征。B. NMF 驱动基因图。"
                        ),
                    }
                ]
            ),
            encoding="utf-8",
        )

        humanized = humanize_image_references(
            "report figure image_057.png（Figure 21 C position）：已核验", tmp_path
        )
        rendered = reader_facing_markdown(humanized)

        assert "图件：Figure 21｜空间转录组数据的非负矩阵分解（NMF）及其生物学表征" in rendered
        assert "Figure 21 C 面板" in rendered
        assert "report figure" not in rendered
        assert "A. NMF 数值特征" not in rendered

    def test_hides_internal_audit_artifacts_and_extraction_disclaimer(self):
        markdown = (
            "- **交付证据**：`mechanical_check_result.json`、`arbitration_resolution.md`。\n"
            "- **交付证据**：`project_structure.json` 的 16 个模块；"
            "`total_code_files=0`、`total_config_files=0`，不含 `02_Spatial`。\n"
            "- **原报告位置**：原 DOCX 2.6；抽取元数据未提供稳定页码，故以章节、图号和原文短句定位。\n"
            "- 图件：`image_001.png`。\n\n"
            "| 分析点 | 证据路径 | 原报告位置 |\n"
            "|---|---|---|\n"
            "| 图号 | `visual_audit_result.json` | 原 DOCX 2.6 |"
        )

        result = reader_facing_markdown(markdown)

        assert "交付证据" not in result
        assert "交付证据" not in result
        assert "交付清单" not in result
        assert "证据路径" not in result
        assert "原 DOCX 2.6" in result
        assert ".json" not in result
        assert ".md" not in result
        assert "image_" not in result
        assert "抽取元数据未提供稳定页码" not in result


class TestTableParsing:
    def test_hides_redundant_delivery_evidence_column(self):
        markdown = (
            "| 编号 | 严重度 | 核心问题 | 原报告位置 | 交付证据 | 修订要求 |\n"
            "|---|---|---|---|---|---|\n"
            "| F-01 | MAJOR | 问题 | 报告.docx | 见本项交付证据 | 修订 |\n"
            "| F-02 | WARNING | 问题 | 报告.docx | 见本项交付证据 | 修订 |\n"
        )

        rendered = render_markdown(markdown)

        assert "<th>交付证据</th>" not in rendered
        assert "见本项交付证据" not in rendered
        assert "<th>修订要求</th>" in rendered

    def test_adjudication_reason_index_stays_neutral(self):
        markdown = (
            "| F 编号 | 裁定规则 | 核定理由 |\n"
            "|---|---|---|\n"
            "| F-12 | R03 | 故 FATAL 降为 MAJOR。 |\n"
        )

        rendered = render_markdown(markdown)

        assert '<tbody><tr><td>F-12</td>' in rendered
        assert 'class="row-fatal"' not in rendered
        assert 'class="row-major"' not in rendered

    def test_pipe_inside_code_cell_is_preserved(self):
        cells = split_table_cells("| ID | Evidence | Action |\n")
        assert cells == ["ID", "Evidence", "Action"]

        row = split_table_cells("| F-001 | `A | B | C` | fix |\n")
        assert row == ["F-001", "`A | B | C`", "fix"]

    def test_report_text_location_renders_original_excerpt(self, tmp_path):
        (tmp_path / "report_text.txt").write_text(
            "first line\noriginal sentence one\noriginal sentence two\n",
            encoding="utf-8",
        )
        md = (
            "| ID | Location | Evidence |\n"
            "|---|---|---|\n"
            "| F-001 | report_text.txt L2-L3; code.R L9 | bad |\n"
        )

        rendered = render_markdown(md, tmp_path)

        assert "原文关键句" in rendered
        assert "original sentence one" in rendered
        assert "original sentence two" in rendered
        assert "code.R L9" in rendered
        assert "report_text.txt" not in rendered

    def test_long_report_text_range_keeps_only_relevant_lines(self, tmp_path):
        (tmp_path / "report_text.txt").write_text(
            "\n".join(
                [
                    "background sentence",
                    "noise one",
                    "正文将 SPP1 模式误写为 COL3A1。",
                    "noise two",
                    "more background",
                ]
            ),
            encoding="utf-8",
        )
        md = (
            "| ID | Location | Issue |\n"
            "|---|---|---|\n"
            "| F-001 | report_text.txt L1-L5 | COL3A1 误写，SPP1 归属错误 |\n"
        )

        rendered = render_markdown(md, tmp_path)

        assert "SPP1" in rendered
        assert "误写为" in rendered
        assert "COL3A1" in rendered
        assert "source-hit" in rendered
        assert "noise one" not in rendered
        assert "noise two" not in rendered
        assert "已折叠" not in rendered

    def test_report_text_reference_in_any_table_cell_renders_excerpt(self, tmp_path):
        (tmp_path / "report_text.txt").write_text(
            "first line\nsource evidence\n",
            encoding="utf-8",
        )
        md = (
            "| ID | Evidence |\n"
            "|---|---|\n"
            "| F-001 | `report_text.txt` L2 |\n"
        )

        rendered = render_markdown(md, tmp_path)

        assert "source evidence" in rendered
        assert "report_text.txt" not in rendered

    def test_report_text_reference_in_list_item_renders_excerpt(self, tmp_path):
        (tmp_path / "report_text.txt").write_text(
            "first line\nlist source\n",
            encoding="utf-8",
        )
        md = "- 位置：报告 1.1；`report_text.txt` L2。"

        rendered = render_markdown(md, tmp_path)

        assert "list source" in rendered
        assert "报告 1.1" in rendered
        assert "report_text.txt" not in rendered

    def test_list_location_uses_sibling_issue_context(self, tmp_path):
        (tmp_path / "report_text.txt").write_text(
            "\n".join(["heading", "noise", "COL3A1 wrong sentence", "noise two"]),
            encoding="utf-8",
        )
        md = (
            "- 位置：`report_text.txt` L1-L4。\n"
            "- 原文短句：COL3A1 误写。\n"
        )

        rendered = render_markdown(md, tmp_path)

        assert "COL3A1" in rendered
        assert "wrong" in rendered
        assert "source-hit" in rendered
        assert "noise two" not in rendered

    def test_issue_excerpt_prioritizes_original_short_sentence_over_evidence_paths(self, tmp_path):
        (tmp_path / "report_text.txt").write_text(
            "\n".join(
                [
                    "Methyl 4-hydroxybenzoate 的3D结构从PubChem数据库获得，并以SDF格式存储。",
                    "结果文件见文件夹11_Docking",
                ]
            ),
            encoding="utf-8",
        )
        md = (
            "- 位置：`report_text.txt` L1-L2。\n"
            "- 原文短句：报告声明对 Methyl 4-hydroxybenzoate 与特征靶点进行分子对接。\n"
            "- 证据：result/11_Docking/gene_infor.xlsx。\n"
        )

        rendered = render_markdown(md, tmp_path)
        excerpt = re.search(r'<div class="source-excerpt">([\s\S]*?)</div>', rendered).group(1)
        excerpt_text = re.sub(r"<[^>]+>", "", excerpt)

        assert "Methyl 4-hydroxybenzoate" in excerpt_text
        assert "hydroxybenzoate" in excerpt
        assert "Docking" not in excerpt

    def test_section_number_keywords_can_locate_missing_heading_pair(self, tmp_path):
        (tmp_path / "report_text.txt").write_text(
            "\n".join(["2.8 GSEA 分析", "正文内容", "2.10 化合物-特征靶点网络"]),
            encoding="utf-8",
        )
        md = (
            "- 位置：`report_text.txt` L1-L3。\n"
            "- 原文短句：结果章节从 2.8 GSEA 分析直接进入 2.10 化合物-特征靶点网络。\n"
        )

        rendered = render_markdown(md, tmp_path)

        assert '<mark class="source-hit">2.8</mark>' in rendered
        assert '<mark class="source-hit">2.10</mark>' in rendered
        assert "正文内容" not in rendered
        assert "已折叠" not in rendered

    def test_status_rows_get_problem_classes(self):
        md = (
            "| 分析点 | 证据充分性 | 审核结论 |\n"
            "|---|---|---|\n"
            "| 分子对接 | 不充分 | 不通过 |\n"
            "| ROC验证 | 部分充分 | 有问题 |\n"
            "| GSEA | 充分 | 通过 |\n"
        )

        rendered = render_markdown(md)

        assert 'class="row-fail"' in rendered
        assert 'class="row-problem"' in rendered

    def test_negated_gap_does_not_mark_passing_row_as_problem(self):
        md = (
            "| 分析点 | 证据充分性 | 审核结论 | 问题说明 |\n"
            "|---|---|---|---|\n"
            "| GSEA | 充分 | 通过 | 未发现影响结论的证据缺口。 |\n"
        )

        rendered = render_markdown(md)

        assert 'class="row-problem"' not in rendered

    def test_analysis_point_cell_shows_folder_and_inferred_code(self, tmp_path):
        (tmp_path / "project_structure.json").write_text(
            json.dumps(
                {
                    "modules": [{"path": "result/05_machine_learning"}],
                    "code_files": [{"path": "script/r.05.machine_learning.R"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        md = (
            "| 分析点 | 结果文件证据 | 审核结论 |\n"
            "|---|---|---|\n"
            "| 机器学习 | `05_machine_learning` | 有问题 |\n"
        )

        rendered = render_markdown(md, tmp_path)

        assert 'class="analysis-point-cell"' in rendered
        assert "result/05_machine_learning" in rendered
        assert "script/r.05.machine_learning.R" in rendered

    def test_analysis_point_cell_uses_explicit_code_and_result_folder(self, tmp_path):
        (tmp_path / "project_structure.json").write_text(
            json.dumps(
                {
                    "modules": [{"path": "04_scRNA"}],
                    "code_files": [{"path": "r.06_scRNA.r"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        md = (
            "| 分析点 | 位置: | 证据: |\n"
            "|---|---|---|\n"
            "| 单细胞注释 | r.06_scRNA.r L231-L244 | 04_scRNA 图件存在 |\n"
        )

        rendered = render_markdown(md, tmp_path)

        assert "04_scRNA" in rendered
        assert "r.06_scRNA.r" in rendered

    def test_analysis_point_cell_infers_folder_from_explicit_code(self, tmp_path):
        (tmp_path / "project_structure.json").write_text(
            json.dumps(
                {
                    "modules": [{"path": "00_rawdata"}],
                    "code_files": [{"path": "r.00_rawdata.r"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        md = (
            "| 分析点 | 位置: | 证据: |\n"
            "|---|---|---|\n"
            "| 数据来源 | r.00_rawdata.r L1-L3 | 脚本包含未报告数据集 |\n"
        )

        rendered = render_markdown(md, tmp_path)

        assert "00_rawdata" in rendered
        assert "r.00_rawdata.r" in rendered

    def test_analysis_point_cell_infers_rawdata_folder_from_title(self, tmp_path):
        (tmp_path / "project_structure.json").write_text(
            json.dumps(
                {
                    "modules": [{"path": "result/00_rawdata"}],
                    "code_files": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        md = (
            "| 分析点 | 结果文件证据 | 审核结论 |\n"
            "|---|---|---|\n"
            "| 数据集与分组 | 原文行号 | 通过 |\n"
        )

        rendered = render_markdown(md, tmp_path)

        assert "result/00_rawdata" in rendered
        assert "未见交付脚本" in rendered

    def test_analysis_point_cell_marks_missing_code(self, tmp_path):
        (tmp_path / "project_structure.json").write_text(
            json.dumps(
                {
                    "modules": [{"path": "result/12_MD"}],
                    "code_files": [{"path": "script/r.09_GSEA.R"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        md = (
            "| 分析点 | 结果文件证据 | 审核结论 |\n"
            "|---|---|---|\n"
            "| 分子动力学 | `12_MD` | 不通过 |\n"
        )

        rendered = render_markdown(md, tmp_path)

        assert "result/12_MD" in rendered
        assert "未见交付脚本" in rendered

    def test_analysis_table_splits_each_point_into_evidence_and_decision_rows(self, tmp_path):
        (tmp_path / "project_structure.json").write_text(
            json.dumps(
                {
                    "modules": [{"path": "result/05_machine_learning"}],
                    "code_files": [{"path": "script/r.05.machine_learning.R"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        md = (
            "| 分析点 | 结果文件证据 | 证据充分性 | 审核结论 | 问题说明 |\n"
            "|---|---|---|---|---|\n"
            "| 机器学习 | `05_machine_learning` | 部分充分 | 有问题 | SVM-RFE 描述不一致。 |\n"
        )

        rendered = render_markdown(md, tmp_path)

        assert 'class="analysis-split-table"' in rendered
        assert 'rowspan="2"' in rendered
        assert "位置 / 证据" in rendered
        assert "判断 / 处置" in rendered
        assert "结果文件证据" in rendered
        assert "证据充分性" in rendered
        assert "问题说明" in rendered

    def test_generic_review_result_heading_is_renamed_for_html(self):
        md = "# T\n\n## 审核结果表\n\n正文"

        rendered = render_markdown(md)
        toc = build_toc(md)

        assert "核心问题清单与整改建议" in rendered
        assert "核心问题清单与整改建议" in toc
        assert "<h2 id=\"审核结果表\">" not in rendered

    def test_delivery_inventory_html_summarizes_project_structure(self, tmp_path):
        (tmp_path / "project_structure.json").write_text(
            json.dumps(
                {
                    "metadata": {
                        "total_modules": 2,
                        "total_code_files": 1,
                        "total_data_files": 3,
                        "total_images": 4,
                        "total_config_files": 0,
                    },
                    "modules": [
                        {
                            "path": "result/00_rawdata",
                            "is_module": True,
                            "file_counts": {
                                "total": 5,
                                "csv": 3,
                                "pdf": 1,
                                "images": 1,
                                "code": 0,
                            },
                        },
                        {
                            "path": "result/reference_only",
                            "is_module": False,
                            "file_counts": {
                                "total": 8,
                                "csv": 0,
                                "pdf": 8,
                                "images": 0,
                                "code": 0,
                            },
                        }
                    ],
                    "code_files": [
                        {
                            "path": "script/r.00_rawdata.R",
                            "language": "R",
                            "lines": 123,
                            "packages": ["readr"],
                            "io_references": [{"path": "x.csv"}],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        rendered = build_delivery_inventory_html(tmp_path)

        assert "交付文件与代码盘点" in rendered
        assert "模块文件总数" in rendered
        assert (
            '<span class="inventory-value">5</span>'
            '<span class="inventory-label">模块文件总数</span>'
        ) in rendered
        assert "result/00_rawdata" in rendered
        assert "result/reference_only" in rendered
        assert "script/r.00_rawdata.R" in rendered
        assert "123" in rendered
        assert "图件/PDF文件" in rendered
        assert "PDF图件" in rendered
        assert ".json" not in rendered
        assert '<details class="inventory-details" open><summary>模块文件计数</summary>' in rendered
        assert '<details class="inventory-details"><summary>代码文件清单</summary>' in rendered

    def test_delivery_inventory_html_renders_non_module_rows_with_counts(self, tmp_path):
        (tmp_path / "project_structure.json").write_text(
            json.dumps(
                {
                    "metadata": {
                        "total_modules": 0,
                        "total_code_files": 0,
                        "total_data_files": 1,
                        "total_images": 1,
                        "total_config_files": 0,
                    },
                    "modules": [
                        {
                            "path": "1.eQTL_POP",
                            "is_module": False,
                            "file_counts": {
                                "total": 3,
                                "csv": 1,
                                "pdf": 1,
                                "images": 0,
                                "code": 0,
                            },
                        }
                    ],
                    "code_files": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        rendered = build_delivery_inventory_html(tmp_path)

        assert "1.eQTL_POP" in rendered
        assert "<td>3</td>" in rendered
        assert "<td>1</td>" in rendered

    def test_delivery_inventory_html_greys_single_kind_rows(self, tmp_path):
        (tmp_path / "project_structure.json").write_text(
            json.dumps(
                {
                    "metadata": {},
                    "modules": [
                        {"path": "data-only", "file_counts": {"total": 2, "csv": 2, "pdf": 0, "images": 0, "code": 0}},
                        {"path": "figure-only", "file_counts": {"total": 3, "csv": 0, "pdf": 1, "images": 2, "code": 0}},
                        {"path": "mixed", "file_counts": {"total": 2, "csv": 1, "pdf": 1, "images": 0, "code": 0}},
                        {"path": "data-and-code", "file_counts": {"total": 2, "csv": 1, "pdf": 0, "images": 0, "code": 1}},
                    ],
                    "code_files": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        rendered = build_delivery_inventory_html(tmp_path)

        assert '<tr class="inventory-row-single-kind"><td><code>data-only</code>' in rendered
        assert '<tr class="inventory-row-single-kind"><td><code>figure-only</code>' in rendered
        assert rendered.count('class="inventory-row-single-kind"') == 2
        legend = (
            "标灰说明：灰色行表示该模块/目录仅交付数据表/数据文件，或仅交付图件/PDF；"
            "标灰仅提示交付类型单一，不代表问题严重度。"
        )
        assert rendered.count(legend) == 1
        assert rendered.index('class="inventory-legend"') < rendered.index(
            '<details class="inventory-details" open><summary>模块文件计数</summary>'
        )

    def test_mixed_location_evidence_paragraph_is_not_collapsed_to_location_card(self, tmp_path):
        (tmp_path / "report_text.txt").write_text("RMSD 维持在 0.25 nm\n", encoding="utf-8")
        md = (
            "位置：report_text.txt L1；`images/image_047.png`。  \n"
            "证据：报告写 0.25 nm，但图中约 0.85-1.05 nm。  \n"
            "整改：补交 MD 原始文件。"
        )

        rendered = render_markdown(md, tmp_path)

        assert 'class="location-cell"' not in rendered
        assert "images/image_047.png" in rendered
        assert "报告写 0.25 nm" in rendered

    def test_parse_analysis_table_finds_unnumbered_analysis_section(self):
        md = (
            "# T\n\n"
            "## 逐分析点审核结果\n\n"
            "| 分析点 | 结果文件证据 | 证据充分性 | 审核结论 | 问题说明 |\n"
            "|---|---|---|---|---|\n"
            "| ROC验证 | `07_gene.ROC` | 部分充分 | 有问题 | 验证集标签写为 Train |\n"
        )

        rows = parse_analysis_table(md)

        assert len(rows) == 1
        assert rows[0]["分析点"] == "ROC验证"

    def test_parse_issue_entries_from_core_issue_table(self):
        md = (
            "## 核心问题清单与整改建议\n\n"
            "| 编号 | 级别 | 核心问题 | 位置 | 关键证据 | 整改建议 |\n"
            "|---|---|---|---|---|---|\n"
            "| F-001 | MAJOR | SVM-RFE 方法描述不一致 | r.05.R L1 | 代码未使用 SVM-RFE | 修正文稿 |\n"
        )

        issues = parse_issue_entries(md)

        assert len(issues) == 1
        assert issues[0]["id"] == "F-001"
        assert issues[0]["severity"] == "MAJOR"
        assert "SVM-RFE" in issues[0]["title"]

    def test_consistency_check_maps_analysis_issue_to_core_list(self):
        md = (
            "# T\n\n"
            "## 逐分析点审核结果\n\n"
            "| 分析点 | 结果文件证据 | 证据充分性 | 审核结论 | 问题说明 |\n"
            "|---|---|---|---|---|\n"
            "| 机器学习 | `05_machine_learning` | 部分充分 | 有问题 | SVM-RFE 方法描述与代码实现不一致 |\n\n"
            "## 核心问题清单与整改建议\n\n"
            "| 编号 | 级别 | 核心问题 | 位置 | 关键证据 | 整改建议 |\n"
            "|---|---|---|---|---|---|\n"
            "| F-001 | MAJOR | SVM-RFE 方法描述不一致 | r.05.R L1 | 代码未使用 SVM-RFE | 修正文稿 |\n"
        )

        rendered = build_consistency_check_html(md)

        assert "分析点与问题清单一致性检查" in rendered
        assert "已进入问题清单" in rendered
        assert "F-001" in rendered
        assert "未进入问题清单" not in rendered

    def test_consistency_check_uses_explicit_issue_ids(self):
        md = (
            "# T\n\n"
            "## 逐分析点审核结果\n\n"
            "| 分析点 | 证据充分性 | 对应问题 | 结论 |\n"
            "|---|---|---|---|\n"
            "| 图件交付格式 | 部分充分 | F-10 | 仅有PNG，缺少PDF交付 |\n\n"
            "## 主要问题清单\n\n"
            "### F-10 结果图缺少PDF交付\n\n"
            "严重度: WARNING\n\n"
            "证据: 16个位图结果图件，0个PDF。\n"
        )

        rendered = build_consistency_check_html(md)

        assert "F-10" in rendered
        assert "已进入问题清单" in rendered
        assert "未进入问题清单" not in rendered
        assert "未对应分析点" not in rendered

    def test_consistency_check_exposes_both_direction_gaps(self):
        md = (
            "# T\n\n"
            "## 逐分析点审核结果\n\n"
            "| 分析点 | 结果文件证据 | 证据充分性 | 审核结论 | 问题说明 |\n"
            "|---|---|---|---|---|\n"
            "| ROC验证 | `07_gene.ROC` | 部分充分 | 有问题 | 验证集标签写为 Train |\n\n"
            "## 核心问题清单与整改建议\n\n"
            "| 编号 | 级别 | 核心问题 | 位置 | 关键证据 | 整改建议 |\n"
            "|---|---|---|---|---|---|\n"
            "| F-009 | MAJOR | 分子对接配体名错误 | `11_Docking` | 结合能为空 | 补齐证据 |\n"
        )

        rendered = build_consistency_check_html(md)

        assert "未进入问题清单" in rendered
        assert "未对应分析点" in rendered
        assert "ROC验证" in rendered
        assert "F-009" in rendered

    def test_consistency_check_hides_report_text_filename(self, tmp_path):
        (tmp_path / "report_text.txt").write_text("bad\nTable 0 疾病名称写错\n", encoding="utf-8")
        md = (
            "# T\n\n"
            "## 逐分析点审核结果\n\n"
            "| 分析点 | 审核结果 | 位置: | 证据: | 处置 |\n"
            "|---|---|---|---|---|\n"
            "| 数据来源 | 不通过 | report_text.txt L2 | Table 0 疾病名称写错 | 修正 |\n\n"
            "## 核心问题清单与整改建议\n\n"
            "| 编号 | 级别 | 核心问题 | 位置 | 关键证据 | 整改建议 |\n"
            "|---|---|---|---|---|---|\n"
            "| F-001 | MAJOR | Table 0 疾病名称残留 | report_text.txt L2 | 疾病名称写错 | 修正 |\n"
        )

        rendered = build_consistency_check_html(md, tmp_path)

        assert "report_text.txt" not in rendered
        assert "reporttext" not in rendered
        assert "原文见正文证据" in rendered


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

    def test_counts_severity_inside_prefixed_finding_headings(self):
        md = (
            "### P01 [FATAL] 阻断问题\n"
            "### P02（MAJOR）一般问题\n"
        )

        counts = count_issue_levels(md)

        assert counts["FATAL"] == 1
        assert counts["MAJOR"] == 1

    def test_authoritative_finding_table_wins_over_grouped_finding_headings(self):
        md = (
            "| 编号 | 严重度 | 核心问题 | 交付证据 | 修订要求 |\n"
            "|---|---|---|---|---|\n"
            "| F-001 | MAJOR | 问题1 | a | x |\n"
            "| F-002 | MAJOR | 问题2 | b | y |\n"
            "| F-003 | MAJOR | 问题3 | c | z |\n\n"
            "### P01-001（MAJOR）分组问题块一\n\n"
            "### P01-002（MAJOR）分组问题块二\n"
        )

        counts = count_issue_levels(md)

        assert counts["MAJOR"] == 3

    def test_counts_table_severity_cells_when_no_detail_headings(self):
        md = (
            "| ID | Severity | Issue |\n"
            "|---|---|---|\n"
            "| F-001 | CRITICAL | bad |\n"
            "| F-002 | MAJOR | risky |\n"
            "| F-003 | WARNING | note |\n"
        )
        counts = count_issue_levels(md)
        assert counts["CRITICAL"] == 1
        assert counts["MAJOR"] == 1
        assert counts["WARNING"] == 1

    def test_counts_final_report_severity_labels(self):
        md = (
            "## 主要问题清单\n\n"
            "### F-01 生存分析证据链不足\n\n"
            "严重度: CRITICAL\n\n"
            "### F-02 缺少PDF图件\n\n"
            "严重度: WARNING\n\n"
        )
        counts = count_issue_levels(md)
        assert counts["CRITICAL"] == 1
        assert counts["WARNING"] == 1

    def test_counts_final_f_heading_with_level_labels(self):
        md = (
            "## 核心问题清单\n\n"
            "### F-01 分子对接模块未交付\n\n"
            "级别: CRITICAL\n\n"
            "位置: `report_text.txt` L160-L163\n\n"
            "### F-02 列线图统计冲突\n\n"
            "级别: MAJOR\n\n"
            "位置: `10_Nomogram/04.ROC_results.csv`\n\n"
            "### F-03 目录引用不一致\n\n"
            "级别: WARNING\n\n"
        )
        counts = count_issue_levels(md)
        assert counts["CRITICAL"] == 1
        assert counts["MAJOR"] == 1
        assert counts["WARNING"] == 1

    def test_parse_issue_entries_from_final_f_headings(self):
        md = (
            "## 主要问题清单\n\n"
            "### F-10 结果图缺少PDF交付\n\n"
            "严重度: WARNING\n\n"
            "证据: 16个位图结果图件，0个PDF。\n"
        )
        issues = parse_issue_entries(md)
        assert len(issues) == 1
        assert issues[0]["id"] == "F-10"
        assert issues[0]["severity"] == "WARNING"
        assert issues[0]["title"] == "结果图缺少PDF交付"

    def test_does_not_count_auxiliary_severity_tables(self):
        md = (
            "| ID | Severity | Issue |\n"
            "|---|---|---|\n"
            "| F-001 | CRITICAL | bad |\n\n"
            "| Check | Original Severity | Final Severity |\n"
            "|---|---|---|\n"
            "| MC-001 | FATAL | INFO |\n"
        )
        counts = count_issue_levels(md)
        assert counts["FATAL"] == 0
        assert counts["CRITICAL"] == 1
        assert counts["INFO"] == 0


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

    def test_explicit_reject_conclusion_section(self):
        md = "## 审核结论\n\n结论：不合格，建议退回修订后复审。\n"
        cls, text = determine_verdict({"FATAL": 0, "CRITICAL": 0, "MAJOR": 0, "WARNING": 0, "INFO": 0}, md)
        assert cls == "verdict-reject"
        assert text == "不合格，建议退回修订后复审"


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


class TestExecutiveSummary:
    def test_framework_version_comes_from_authoritative_policy(self):
        assert load_framework_version() == "v7.1"

    def test_extracts_preferred_conclusion_section(self):
        md = "# Report\n\n## Conclusion\n\nThis is the short delivery summary.\n\n## Details\n\nNoise"
        assert extract_executive_summary(md) == "This is the short delivery summary."

    def test_build_html_includes_hero_summary_and_dashboard(self):
        md = (
            "# 26YTY007F Final Report\n\n"
            "## Conclusion\n\nNeeds revision before delivery.\n\n"
            "## Findings\n\n"
            "| ID | Severity | Issue |\n"
            "|---|---|---|\n"
            "| F-001 | CRITICAL | bad |\n"
        )
        rendered = build_html(md, Path("26YTY007F/final_review_report.md"))
        assert 'class="hero-summary"' in rendered
        assert "Needs revision before delivery." in rendered
        assert 'class="severity-dashboard"' in rendered
        assert "<span class=\"sev-count\">1</span>" in rendered
        assert rendered.count("<h1") == 1
        assert rendered.count("v7.1") == 2

    def test_build_html_uses_sealed_final_decision_over_severity_fallback(self):
        md = (
            "# 26YTY007F Final Report\n\n"
            "## Findings\n\n"
            "| ID | Severity | Issue |\n"
            "|---|---|---|\n"
            "| F-001 | MAJOR | bad |\n"
        )
        final_decision = {
            "status": "leader_confirmed",
            "verdict": "不合格",
            "release_decision": "BLOCK",
        }

        rendered = build_html(
            md,
            Path("26YTY007F/final_review_report.md"),
            final_decision=final_decision,
        )

        assert '<body class="verdict-reject">' in rendered
        assert '<div class="verdict-banner verdict-reject">' in rendered
        assert "<span>审核结论：不合格</span>" in rendered

    def test_revocation_ledger_is_promoted_and_deferred_to_the_end(self):
        md = (
            "# Report\n\n"
            "## 一、审核结论\n\nConclusion.\n\n"
            "### 撤销裁定（保留原始记录与反证）\n\n"
            "#### R-01\n\n撤销理由。\n\n"
            "## 二、复审提交要求\n\nRequirements.\n"
        )

        result = defer_revocation_ledger(md)

        assert result.find("复审提交要求") < result.find("## 六、撤销裁定（保留原始记录与反证）")
        assert result.count("撤销裁定（保留原始记录与反证）") == 1

    def test_severity_dashboard_has_keyboard_operable_jump_controls(self):
        md = (
            "# Report\\n\\n"
            "## Conclusion\\n\\nNeeds revision.\\n\\n"
            "## Findings\\n\\n"
            "### [CRITICAL] critical item\\n\\nDetails.\\n\\n"
            "### [MAJOR] major item\\n\\nDetails.\\n\\n"
            "### [WARNING] warning item\\n\\nDetails.\\n\\n"
            "### [INFO] info item\\n\\nDetails.\\n"
        )

        rendered = build_html(md, Path("report/final_review_report.md"))

        for severity in ("FATAL", "CRITICAL", "MAJOR", "WARNING", "INFO"):
            assert f'<button type="button" class="sev-card sev-{severity.lower()}" data-severity="{severity}">' in rendered
        assert "var severityCards = document.querySelectorAll('.sev-card[data-severity]');" in rendered
        assert "window.location.hash = encodeURIComponent(target.id);" in rendered

    def test_adjudication_index_finding_id_targets_detail_heading(self):
        md = (
            "# Report\n\n"
            "## 一、审核结论\n\nNeeds revision.\n\n"
            "## 二、逐分析点审核结果\n\n"
            "### 裁定标准与核定理由索引\n\n"
            "| F 编号 | 审核结果 | 错误点 |\n"
            "|---|---|---|\n"
            "| F-01 | 需修订（MAJOR） | 模块问题 |\n\n"
            "## 三、提交阻断问题\n\n"
            "### P01 [MAJOR] module issue\n\n"
            "#### 具体错误 1：F-01 A01-F001\n\nDetails.\n"
        )

        rendered = build_html(md, Path("report/final_review_report.md"))

        assert '<details class="inventory-details adjudication-index" open>' in rendered
        assert "<td>F-01</td>" in rendered
        assert "具体错误 1：F-01 A01-F001" in rendered
        assert "var allFindingDetails = contentEl.querySelectorAll('h4[id]');" in rendered
        assert "var issuePattern = new RegExp('\\\\b' + issueId + '\\\\b', 'i');" in rendered


class TestCanonicalFindingsPresentation:
    def test_renders_sealed_findings_and_humanizes_image_reference(self, tmp_path):
        arbitration_dir = tmp_path / "agent_results" / "arbitration"
        arbitration_dir.mkdir(parents=True)
        (arbitration_dir / "arbitration_resolution.json").write_text(
            json.dumps(
                {
                    "canonical_findings": [
                        {
                            "canonical_id": "ADJ-07",
                            "severity": "MAJOR",
                            "module": "10_DockMD",
                            "claim": "图像 image_089.png—image_096.png 可作为独立证据。",
                            "error_mechanism": "面板存在未说明的重复。",
                            "evidence_object": "图像哈希与报告图题。",
                            "repair_path": "重导出图件并说明面板。",
                            "description": "对接图面板重复。",
                        }
                    ],
                    "raw_dispositions": [
                        {
                            "raw_finding_id": "rf:A:ADJ-07",
                            "decision": "retain",
                            "canonical_ids": ["ADJ-07"],
                            "reason": "证据完整，保留为正式问题。",
                        },
                        {
                            "raw_finding_id": "rf:B:ADJ-07",
                            "decision": "merge",
                            "canonical_ids": ["ADJ-07"],
                            "reason": "与 ADJ-07 指向同一图件问题。",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (tmp_path / "visual_audit_checklist.json").write_text(
            json.dumps(
                {
                    "checklist": [
                        {
                            "filename": "image_089.png",
                            "figure_id": "Fig. 16.2",
                            "caption": "DGKD 分子对接模式图",
                        },
                        {
                            "filename": "image_096.png",
                            "figure_id": "Fig. 16.3",
                            "caption": "PGM2L1 分子对接模式图",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        rendered = build_canonical_findings_html(tmp_path)

        assert "正式裁定详情" in rendered
        assert "ADJ-07" in rendered
        assert "image_089.png" not in rendered
        assert "Fig. 16.2" in rendered
        assert "Fig. 16.3" in rendered
        assert "原始发现处置台账（2 条）" in rendered
        assert "rf:A:ADJ-07" in rendered
        assert "证据完整，保留为正式问题。" in rendered

    def test_build_html_humanizes_main_report_image_reference(self, tmp_path):
        (tmp_path / "visual_audit_checklist.json").write_text(
            json.dumps(
                {
                    "checklist": [
                        {
                            "filename": "image_089.png",
                            "figure_id": "Fig. 16.2",
                            "caption": "DGKD 分子对接模式图",
                        },
                        {
                            "filename": "image_096.png",
                            "figure_id": "Fig. 16.3",
                            "caption": "PGM2L1 分子对接模式图",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        markdown_path = tmp_path / "final_review_report.md"
        markdown = (
            "# 26YTY007F 最终审核报告\n\n"
            "## 审核结论\n\n不合格。\n\n"
            "## 提交阻断问题\n\n"
            "### P01 [MAJOR] 对接图件重复\n\n"
            "证据位置：`image_089.png`—`image_096.png`\n"
        )

        rendered = build_html(markdown, markdown_path)

        assert "image_089.png" not in rendered
        assert "Fig. 16.2" in rendered
        assert "Fig. 16.3" in rendered

    def test_humanizes_fenced_images_directory_reference_without_breaking_table_cells(self, tmp_path):
        (tmp_path / "visual_audit_checklist.json").write_text(
            json.dumps(
                {
                    "checklist": [
                        {
                            "filename": "image_013.png",
                            "figure_id": "Figure. 3",
                            "caption": "TCGA差异表达分析及核心靶点筛选",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        markdown = (
            "| 编号 | 严重度 | 核心问题 | 原报告位置 | 交付证据 | 修订要求 |\n"
            "|---|---|---|---|---|---|\n"
            "| F-021 | MAJOR | Venn 无集合标签 | `images/image_013.png` | 资产 441 | 补图例 |\n"
        )

        rendered = render_markdown(humanize_image_references(markdown, tmp_path))

        assert "images/image_013.png" not in rendered
        assert "<code>" not in rendered
        assert rendered.count("<td") == 6
        assert "资产 441" in rendered
        assert "补图例" in rendered


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

    def test_moves_analysis_results_before_submission_blockers(self):
        content = (
            '<h2 id="一-审核结论">一、审核结论</h2><p>结论</p>'
            '<h2 id="二-提交阻断问题">二、提交阻断问题</h2><p>阻断</p>'
            '<h2 id="三-其他已裁定问题">三、其他已裁定问题</h2><p>其他</p>'
            '<h2 id="四-逐分析点审核结果">四、逐分析点审核结果</h2><p>展开</p>'
            '<h2 id="五-未决项">五、未决项</h2><p>未决</p>'
        )

        result = reorder_sections(content)

        assert result.find("逐分析点审核结果") < result.find("提交阻断问题") < result.find("其他已裁定问题")
        assert 'id="二-逐分析点审核结果"' in result
        assert 'id="四-其他已裁定问题"' in result

    def test_analysis_navigation_is_removed_from_reader_html(self):
        content = (
            '<h2 id="一-审核结论">一、审核结论</h2><p>结论</p>'
            '<h2 id="二-逐分析点审核结果">二、逐分析点审核结果</h2><table><tr><td>导航</td></tr></table>'
            '<h3 id="裁定标准与核定理由索引">裁定标准与核定理由索引</h3><p>索引</p>'
            '<h2 id="三-提交阻断问题">三、提交阻断问题</h2><p>阻断</p>'
        )

        result = remove_analysis_navigation(content)

        assert "逐分析点审核结果" not in result
        assert "导航" not in result
        assert "裁定标准与核定理由索引" in result
        assert 'id="三-提交阻断问题"' in result

    def test_analysis_navigation_removes_internal_finding_id_binding_index(self):
        content = (
            '<h2 id="一-审核结论">一、审核结论</h2><p>结论</p>'
            '<h2 id="二-逐分析点审核结果">二、逐分析点审核结果</h2><table><tr><td>导航</td></tr></table>'
            '<h3 id="f-id-绑定索引">F-ID 绑定索引</h3><p>F-01 → A01-F001</p>'
            '<h2 id="三-提交阻断问题">三、提交阻断问题</h2><p>阻断</p>'
        )

        result = remove_analysis_navigation(content)

        assert "逐分析点审核结果" not in result
        assert "导航" not in result
        assert "F-ID 绑定索引" not in result
        assert "F-01 → A01-F001" not in result
        assert 'id="三-提交阻断问题"' in result

    def test_issue_dashboard_source_is_removed_from_reader_html(self):
        content = (
            '<h2 id="二-问题清单">二、问题清单</h2>'
            '<h3 id="问题清单与严重度仪表盘来源">问题清单与严重度仪表盘来源</h3>'
            '<table><tr><td>来源表</td></tr></table>'
            '<h3 id="裁定索引">裁定索引</h3><p>后续内容</p>'
        )

        result = remove_issue_dashboard_source(content)

        assert "问题清单与严重度仪表盘来源" not in result
        assert "来源表" not in result
        assert 'id="裁定索引"' in result

    def test_adjudication_reason_index_is_expanded_by_default(self):
        content = (
            '<h2 id="二-问题清单">二、问题清单</h2>'
            '<h3 id="裁定标准与核定理由索引">裁定标准与核定理由索引</h3>'
            '<table><thead><tr><th>F 编号</th><th>裁定规则</th><th>核定理由</th></tr></thead>'
            '<tbody><tr><td>F-01</td><td>R02</td><td>核定理由</td></tr></tbody></table>'
            '<h2 id="三-后续">三、后续</h2><p>后续内容</p>'
        )

        result = collapse_adjudication_reason_index(content)

        assert '<details class="inventory-details adjudication-index" open>' in result
        assert 'data-default-collapsed="true"' not in result
        assert '<summary>裁定标准与核定理由索引</summary>' in result
        assert 'id="裁定标准与核定理由索引"' in result
        assert "<th>审核结果</th><th>错误点</th>" in result
        assert result.find("核定理由") < result.find("三、后续")

    def test_build_html_places_expanded_adjudication_navigation_before_blockers(self, tmp_path):
        source = tmp_path / "final_review_report.md"
        source.write_text(
            "# 26YLM139F 最终审核报告\n\n"
            "## 一、审核结论\n\n结论。\n\n"
            "## 二、提交阻断问题\n\n阻断依据。\n\n"
            "## 三、其他已裁定问题\n\n其他依据。\n\n"
            "## 四、逐分析点审核结果\n\n"
            "| 分析点 | 审核判断 |\n|---|---|\n| 分析 A | 通过 |\n\n"
            "### 裁定标准与核定理由索引\n\n"
            "| F 编号 | 裁定规则 | 核定理由 |\n|---|---|---|\n"
            "| F-01 | R02 | 已核定 |\n",
            encoding="utf-8",
        )

        result = build_html(source.read_text(encoding="utf-8"), source)
        main_content = result.split('<main class="content">', 1)[1]
        blocker_heading = re.search(
            r'<h2 id="[^"]*提交阻断问题[^"]*">[^<]*提交阻断问题[^<]*</h2>',
            main_content,
        )

        assert "逐分析点审核结果" not in main_content
        assert '<details class="inventory-details adjudication-index" open>' in main_content
        assert blocker_heading is not None
        assert main_content.find('<details class="inventory-details adjudication-index" open>') < blocker_heading.start()

    def test_build_html_renumbers_visible_headings_and_toc_after_hidden_navigation(self, tmp_path):
        source = tmp_path / "final_review_report.md"
        source.write_text(
            "# 26YLM139F 最终审核报告\n\n"
            "## 一、审核结论\n\n结论。\n\n"
            "## 二、逐分析点审核结果\n\n"
            "| 分析点 | 审核判断 |\n|---|---|\n| 分析 A | 通过 |\n\n"
            "### 裁定标准与核定理由索引\n\n"
            "| F 编号 | 裁定规则 | 核定理由 |\n|---|---|---|\n"
            "| F-01 | R02 | 已核定 |\n\n"
            "## 三、提交阻断问题\n\n阻断依据。\n\n"
            "## 四、其他已裁定问题\n\n其他依据。\n\n"
            "## 五、复审提交要求\n\n提交要求。\n",
            encoding="utf-8",
        )

        result = build_html(source.read_text(encoding="utf-8"), source)
        main_content = result.split('<main class="content">', 1)[1].split(
            '<div class="footer">', 1
        )[0]
        sidebar = result.split('<aside class="sidebar" id="toc-sidebar">', 1)[1].split(
            "</aside>", 1
        )[0]
        body_headings = re.findall(r'<h2 id="([^"]+)">([^<]+)</h2>', main_content)
        toc_entries = re.findall(r'<a href="#([^"]+)">([^<]+)</a>', sidebar)

        assert body_headings == [
            ("一-审核结论", "一、审核结论"),
            ("二-提交阻断问题", "二、提交阻断问题"),
            ("三-其他已裁定问题", "三、其他已裁定问题"),
            ("四-复审提交要求", "四、复审提交要求"),
        ]
        assert toc_entries == body_headings
        assert "逐分析点审核结果" not in main_content
        assert "裁定标准与核定理由索引" in main_content
        assert main_content.find("裁定标准与核定理由索引") < main_content.find(
            "二、提交阻断问题"
        )


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

    def test_analysis_results_are_omitted_from_toc(self):
        md = (
            "## 一、审核结论\n"
            "## 二、提交阻断问题\n"
            "## 三、其他已裁定问题\n"
            "## 四、逐分析点审核结果\n"
        )

        toc = build_toc(md)

        assert "逐分析点审核结果" not in toc
        assert toc.find("提交阻断问题") < toc.find("其他已裁定问题")
