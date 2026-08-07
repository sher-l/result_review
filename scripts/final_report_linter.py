#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Lint final_review_report.md and its required companion files.

The goal is to block under-specified reports from being treated as complete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from audit_contract import extract_report_verdict
from policy_loader import load_policy
from formal_delivery import find_report_state_violations
from render_final_review_html import (
    _analysis_row_needs_issue,
    _load_project_index,
    _match_analysis_to_issues,
    count_issue_levels,
    parse_analysis_table,
    parse_issue_entries,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lint final_review_report.md and required audit deliverables."
    )
    parser.add_argument(
        "input_path",
        help="Path to result_review_report/<project_id> or directly to final_review_report.md",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Optional explicit path for final_report_lint.json",
    )
    return parser.parse_args()


def resolve_paths(input_path: str) -> tuple[Path, Path]:
    source = Path(input_path)
    if source.is_dir():
        review_dir = source
        report_path = review_dir / "final_review_report.md"
    else:
        review_dir = source.parent
        report_path = source
    if not report_path.exists():
        raise FileNotFoundError(f"final_review_report.md not found: {report_path}")
    return review_dir, report_path


def _iter_headings(text: str) -> list[tuple[int, int, str]]:
    headings = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            headings.append((line_no, len(match.group(1)), match.group(2).strip()))
    return headings


def _extract_markdown_links(text: str) -> list[tuple[int, str]]:
    links = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", line):
            target = match.group(1).strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1].strip()
            links.append((line_no, target))
    return links


def _slugify_heading(title: str) -> str:
    slug = title.strip().lower()
    slug = re.sub(r"[^\w\s\-一-龥]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    return slug.strip("-")


def _load_link_cache(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_link_cache(cache_path: Path, cache_data: dict) -> None:
    cache_path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")


def _check_external_url(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, "Malformed external URL"
    try:
        request = Request(url, method="HEAD", headers={"User-Agent": "audit-framework-link-check"})
        with urlopen(request, timeout=6) as response:
            status = getattr(response, "status", 200)
        if 200 <= status < 400:
            return True, f"reachable ({status})"
        return False, f"unreachable ({status})"
    except Exception as exc:  # pragma: no cover - network variability
        return False, f"request failed: {exc.__class__.__name__}"


def _normalize_local_target(target: str) -> str:
    trimmed = target.strip()
    if re.match(r"^/[A-Za-z]:[\\/]", trimmed):
        trimmed = trimmed[1:]
    if re.match(r"^[A-Za-z]:[\\/]", trimmed):
        return re.sub(r":\d+$", "", trimmed)
    return re.sub(r":\d+$", "", trimmed)


def _should_ignore_warning(check_id: str, policy: dict) -> bool:
    prefixes = policy.get("lint_policy", {}).get("ignored_warning_prefixes", [])
    return any(check_id.startswith(prefix) for prefix in prefixes)


def _effective_severity(check_id: str, severity: str, policy: dict) -> str:
    prefixes = policy.get("lint_policy", {}).get("warning_prefixes_as_errors", [])
    if severity == "warning" and any(check_id.startswith(prefix) for prefix in prefixes):
        return "error"
    return severity


def _build_suggested_fixes(checks: list[dict]) -> list[dict]:
    suggestions = []
    seen = set()
    for check in checks:
        if check.get("passed"):
            continue
        check_id = check["id"]
        if check_id in seen:
            continue
        seen.add(check_id)

        autofix_safe = False
        patch_hint = ""

        if check_id.startswith("markdown:placeholder:"):
            action = "删除占位词，补成正式结论或证据描述。"
            autofix_safe = True
            patch_hint = "移除占位词后补一条完整句子，不要只留空白。"
        elif check_id.startswith("markdown:empty_section:"):
            action = "给该标题补正文内容，或删除空标题。"
            autofix_safe = True
            patch_hint = "如果该标题只是占位，直接删掉；如果需要保留，至少补 1 段正文。"
        elif check_id.startswith("markdown:heading_jump:"):
            action = "补齐中间层级标题，或把当前标题降到相邻层级。"
            autofix_safe = True
            patch_hint = "优先把跳级标题降一级，避免引入新的空标题。"
        elif check_id.startswith("markdown:internal_link:"):
            action = "修正锚点目标，确保链接到实际存在的标题。"
            patch_hint = "把锚点改成标题 slug，或删除失效内部链接。"
        elif check_id.startswith("markdown:local_link:"):
            action = "修正本地路径，或删除失效链接。"
            patch_hint = "优先改成本地真实存在的绝对路径。"
        elif check_id.startswith("markdown:external_link:"):
            action = "确认外链是否仍有效；若属于允许忽略的域名，加入 lint_policy.ignore_external_url_patterns。"
            patch_hint = "如果外链长期不稳定，配置 ignore_external_url_patterns 而不是每次手工忽略。"
        elif check_id.startswith("terminology:"):
            action = "将术语替换成框架标准表述，避免混入口径不一致或非AI审核措辞。"
            autofix_safe = True
            patch_hint = "按 terminology_policy 里的 replacement 统一替换。"
        elif check_id.startswith("forbidden:"):
            action = "把模糊表述改成逐条证据陈述，不要只写总评。"
        elif check_id.startswith("section:"):
            action = "补齐该必需章节，并写成结构化内容。"
        elif check_id.startswith("evidence:"):
            action = "为核心问题补充位置标签和证据字段。"
        elif check_id == "code_risk:declared":
            action = "在最终报告里明确写出代码不可复现风险。"
        elif check_id.startswith("consistency:"):
            action = "把逐分析点异常补入主要问题清单，并在逐分析点表中写明对应 F 编号。"
            patch_hint = "优先新增“对应问题”列，用 F-xx 精确映射，避免只靠文本相似度。"
        elif check_id.startswith("markdown:h1_count:"):
            action = "只保留一个一级标题，其余标题降级。"
        else:
            action = "根据该检查项补齐内容或修正格式。"

        suggestions.append(
            {
                "check_id": check_id,
                "severity": check["severity"],
                "suggested_action": action,
                "autofix_safe": autofix_safe,
                "patch_hint": patch_hint,
                "message": check["message"],
            }
        )
    return suggestions


def build_terminology_style_checks(review_dir: Path, policy: dict) -> list[dict]:
    checks = []
    terminology_policy = policy.get("terminology_policy", {})
    target_files = [
        review_dir / filename
        for filename in policy["required_final_files"]
        if filename.endswith(".md") and (review_dir / filename).exists()
    ]

    for md_path in target_files:
        text = md_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        relative_name = md_path.name

        for rule in terminology_policy.get("forbidden_terms", []):
            term = rule.get("term")
            if not term:
                continue
            replacement = rule.get("replacement", "")
            severity = rule.get("severity", "warning")
            for line_no, line in enumerate(lines, start=1):
                if term in line:
                    checks.append(
                        {
                            "id": f"terminology:forbidden:{relative_name}:{line_no}:{term}",
                            "passed": False,
                            "severity": severity,
                            "message": (
                                f"{relative_name} uses forbidden audit term '{term}' at line {line_no}."
                                + (f" Prefer '{replacement}'." if replacement else "")
                            ),
                        }
                    )

        for rule in terminology_policy.get("required_any_terms", []):
            scope = rule.get("scope")
            if scope and scope != relative_name:
                continue
            required_terms = rule.get("terms", [])
            if required_terms and not any(term in text for term in required_terms):
                checks.append(
                    {
                        "id": f"terminology:required_any:{relative_name}:{'-'.join(required_terms)}",
                        "passed": False,
                        "severity": rule.get("severity", "warning"),
                        "message": f"{relative_name} should contain at least one preferred audit term: {', '.join(required_terms)}",
                    }
                )

    return checks


def build_delivery_state_checks(report_text: str, policy: dict) -> list[dict]:
    """Reject pre-release lifecycle assertions from a report meant for formal delivery."""
    delivery_policy = policy.get("formal_delivery_policy")
    if not isinstance(delivery_policy, dict):
        return [
            {
                "id": "policy:formal_delivery_policy",
                "passed": False,
                "severity": "error",
                "message": "formal_delivery_policy is missing or invalid; final delivery checks cannot be disabled implicitly.",
            }
        ]
    if delivery_policy.get("enabled", True) is False:
        return [
            {
                "id": "policy:formal_delivery_policy:disabled",
                "passed": False,
                "severity": "error",
                "message": "formal_delivery_policy is disabled; v7 formal reports require delivery-state checks.",
            }
        ]
    return [
        {
            "id": f"delivery_state:pre_release_text:{phrase}",
            "passed": False,
            "severity": "error",
            "message": f"Final report contains prohibited pre-release lifecycle text: {phrase}",
        }
        for phrase in find_report_state_violations(report_text, policy)
    ]


def build_markdown_quality_checks(review_dir: Path, policy: dict) -> list[dict]:
    checks = []
    lint_policy = policy.get("lint_policy", {})
    placeholder_terms = lint_policy.get(
        "placeholder_terms",
        ["TODO", "TBD", "FIXME", "待补", "待补充", "占位", "xxx", "XXX"],
    )
    md_files = [
        review_dir / filename
        for filename in policy["required_final_files"]
        if filename.endswith(".md") and (review_dir / filename).exists()
    ]
    cache_path = review_dir / "lint_link_cache.json"
    external_cache = _load_link_cache(cache_path)
    cache_ttl_days = lint_policy.get("external_link_cache_ttl_days", 7)
    cache_updated = False
    now = datetime.now()

    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        headings = _iter_headings(text)
        anchors = {_slugify_heading(title) for _, _, title in headings}
        relative_name = md_path.name

        if headings:
            h1_count = sum(1 for _, level, _ in headings if level == 1)
            checks.append(
                {
                    "id": f"markdown:h1_count:{relative_name}",
                    "passed": h1_count <= 1,
                    "severity": "error",
                    "message": f"{relative_name} contains at most one level-1 heading.",
                }
            )
            for index in range(1, len(headings)):
                prev_line, prev_level, _ = headings[index - 1]
                curr_line, curr_level, curr_title = headings[index]
                if curr_level - prev_level > 1:
                    checks.append(
                        {
                            "id": f"markdown:heading_jump:{relative_name}:{curr_line}",
                            "passed": False,
                            "severity": "warning",
                            "message": (
                                f"{relative_name} heading level jumps from H{prev_level} at line {prev_line} "
                                f"to H{curr_level} at line {curr_line}: {curr_title}"
                            ),
                        }
                    )
                next_heading = headings[index + 1] if index + 1 < len(headings) else None
                next_heading_line = next_heading[0] if next_heading else None
                next_heading_level = next_heading[1] if next_heading else None
                section_body = lines[curr_line: next_heading_line - 1 if next_heading_line else None]
                has_direct_body = any(line.strip() for line in section_body)
                has_child_sections = next_heading_level is not None and next_heading_level > curr_level
                if not has_direct_body and not has_child_sections:
                    checks.append(
                        {
                            "id": f"markdown:empty_section:{relative_name}:{curr_line}",
                            "passed": False,
                            "severity": "warning",
                            "message": f"{relative_name} heading at line {curr_line} has no body content: {curr_title}",
                        }
                    )

        for line_no, line in enumerate(text.splitlines(), start=1):
            for term in placeholder_terms:
                if term in line:
                    checks.append(
                        {
                            "id": f"markdown:placeholder:{relative_name}:{line_no}:{term}",
                            "passed": False,
                            "severity": "warning",
                            "message": f"{relative_name} contains placeholder-like text '{term}' at line {line_no}.",
                        }
                    )

        for line_no, target in _extract_markdown_links(text):
            if target.startswith("mailto:"):
                continue
            if target.startswith("#"):
                anchor = _slugify_heading(target[1:])
                checks.append(
                    {
                        "id": f"markdown:internal_link:{relative_name}:{line_no}",
                        "passed": anchor in anchors,
                        "severity": "warning",
                        "message": f"{relative_name} internal anchor exists at line {line_no}: {target}",
                    }
                )
                continue
            if target.startswith("http://") or target.startswith("https://"):
                if lint_policy.get("check_external_links", True):
                    ignore_patterns = lint_policy.get("ignore_external_url_patterns", [])
                    if any(pattern in target for pattern in ignore_patterns):
                        continue
                    cached = external_cache.get(target)
                    if cached:
                        checked_at = cached.get("checked_at")
                        age_ok = False
                        if checked_at:
                            try:
                                age_ok = (now - datetime.fromisoformat(checked_at)).days < cache_ttl_days
                            except ValueError:
                                age_ok = False
                        if age_ok:
                            passed = cached.get("passed", False)
                            detail = f"{cached.get('detail', 'cached')} [cached]"
                        else:
                            passed, detail = _check_external_url(target)
                            external_cache[target] = {
                                "passed": passed,
                                "detail": detail,
                                "checked_at": now.isoformat(timespec="seconds"),
                            }
                            cache_updated = True
                    else:
                        passed, detail = _check_external_url(target)
                        external_cache[target] = {
                            "passed": passed,
                            "detail": detail,
                            "checked_at": now.isoformat(timespec="seconds"),
                        }
                        cache_updated = True
                    checks.append(
                        {
                            "id": f"markdown:external_link:{relative_name}:{line_no}",
                            "passed": passed,
                            "severity": "warning",
                            "message": f"{relative_name} external link check at line {line_no}: {target} ({detail})",
                        }
                    )
                continue

            if lint_policy.get("check_local_links", True):
                cleaned_target = _normalize_local_target(target)
                local_path = Path(cleaned_target)
                if not local_path.is_absolute():
                    local_path = (review_dir / cleaned_target).resolve()
                checks.append(
                    {
                        "id": f"markdown:local_link:{relative_name}:{line_no}",
                        "passed": local_path.exists(),
                        "severity": "error",
                        "message": f"{relative_name} local link target exists at line {line_no}: {target}",
                    }
                )

    if cache_updated:
        _save_link_cache(cache_path, external_cache)

    return checks


def build_analysis_issue_consistency_checks(review_dir: Path, report_text: str) -> list[dict]:
    """Block final reports where analysis-table problems are not in the issue list."""
    checks: list[dict] = []
    analysis_rows = parse_analysis_table(report_text)
    issues = parse_issue_entries(report_text)
    if not analysis_rows and not issues:
        return checks

    project_index = _load_project_index(review_dir)
    actionable_rows = [row for row in analysis_rows if _analysis_row_needs_issue(row)]

    matched_issue_ids: set[str] = set()
    unmapped_rows: list[str] = []
    for row in actionable_rows:
        matches = _match_analysis_to_issues(row, issues, project_index)
        matched_issue_ids.update(issue["id"] for issue in matches)
        if not matches:
            title = next((value for key, value in row.items() if "分析点" in key), "")
            unmapped_rows.append(title or "未命名分析点")

    orphan_issues = [issue for issue in issues if issue["id"] not in matched_issue_ids]

    checks.append(
        {
            "id": "consistency:analysis_rows_mapped",
            "passed": not unmapped_rows,
            "severity": "error",
            "message": (
                "Actionable analysis rows are mapped into the main issue list."
                if not unmapped_rows
                else "Analysis rows not mapped to issues: " + "；".join(unmapped_rows)
            ),
        }
    )
    checks.append(
        {
            "id": "consistency:issues_mapped",
            "passed": not orphan_issues,
            "severity": "error",
            "message": (
                "Main issue list entries map back to analysis rows."
                if not orphan_issues
                else "Issue entries not mapped to analysis rows: "
                + "；".join(f"{issue['id']} {issue.get('title', '')}" for issue in orphan_issues)
            ),
        }
    )
    return checks


def _section_body(markdown_text: str, heading_marker: str) -> str:
    """Return the body of the first H2 section containing ``heading_marker``."""
    pattern = re.compile(
        rf"^##\s+[^\n]*{re.escape(heading_marker)}[^\n]*\n([\s\S]*?)(?=^##\s+|\Z)",
        flags=re.MULTILINE,
    )
    match = pattern.search(markdown_text)
    return match.group(1).strip() if match else ""


def _core_issue_blocks(section_text: str) -> list[dict[str, str]]:
    pattern = re.compile(
        r"^###\s+(P(?:0?1)-\d+)\s+\[(FATAL|CRITICAL|MAJOR|WARNING)\]\s+(.+?)\s*$"
        r"([\s\S]*?)(?=^###\s+P(?:0?1)-\d+\s+\[|\Z)",
        flags=re.MULTILINE,
    )
    return [
        {"id": match.group(1), "severity": match.group(2), "title": match.group(3).strip(), "body": match.group(4)}
        for match in pattern.finditer(section_text)
    ]


def _secondary_issue_blocks(section_text: str) -> list[dict[str, str]]:
    """Return concise but evidence-bearing non-blocking issue blocks."""
    pattern = re.compile(
        r"^###\s+(S-\d+)\s+\[(FATAL|CRITICAL|MAJOR|WARNING|INFO)\]\s+(.+?)\s*$"
        r"([\s\S]*?)(?=^###\s+S-\d+\s+\[|\Z)",
        flags=re.MULTILINE,
    )
    return [
        {"id": match.group(1), "severity": match.group(2), "title": match.group(3).strip(), "body": match.group(4)}
        for match in pattern.finditer(section_text)
    ]


def _child_error_blocks(section_text: str, heading_prefix: str) -> list[dict[str, str]]:
    """Return independently actionable errors nested beneath one report issue."""
    pattern = re.compile(
        rf"^####\s+{re.escape(heading_prefix)}\s*(\d+)\s*[：:]\s*(.+?)\s*$"
        rf"([\s\S]*?)(?=^####\s+{re.escape(heading_prefix)}\s*\d+\s*[：:]|^###\s+|\Z)",
        flags=re.MULTILINE,
    )
    return [
        {"number": match.group(1), "title": match.group(2).strip(), "body": match.group(3)}
        for match in pattern.finditer(section_text)
    ]


def _has_nonempty_label(body: str, label: str) -> bool:
    return bool(
        re.search(
            rf"(?:^|\n)[^\S\r\n]*(?:-[^\S\r\n]*)?\*\*{re.escape(label)}\*\*"
            r"[^\S\r\n]*[:：][^\S\r\n]*\S[^\r\n]*",
            body,
        )
    )


def _has_reader_docx_locator(body: str) -> bool:
    location_match = re.search(r"\*\*原报告位置\*\*\s*[:：]\s*([^\n]+)", body)
    if not location_match:
        return False
    location = location_match.group(1)
    return bool(re.search(r"\.docx?\b", location, flags=re.IGNORECASE)) and bool(
        re.search(r"[>＞]|第\s*\d+\s*页|图\s*\d+|表\s*\d+|[“\"《]", location)
    )


def _indexed_finding_ids_without_detail_headings(
    report_text: str,
    heading_prefix: str,
) -> list[str]:
    """Return index finding IDs not named exactly in a concrete-error heading."""
    detail_headings = re.findall(
        rf"^####\s+{re.escape(heading_prefix)}\s*\d+\s*[：:]\s*(.+?)\s*$",
        report_text,
        flags=re.MULTILINE,
    )
    detailed_ids = {
        finding_id.upper()
        for heading in detail_headings
        for finding_id in re.findall(r"\bF-\d+\b", heading, flags=re.IGNORECASE)
    }
    indexed_ids = {
        str(entry.get("id") or "").upper()
        for entry in parse_issue_entries(report_text)
        if re.fullmatch(r"F-\d+", str(entry.get("id") or ""), flags=re.IGNORECASE)
    }
    return sorted(indexed_ids - detailed_ids)


def build_report_depth_checks(report_text: str, policy: dict) -> list[dict]:
    """Enforce a concise, evidence-backed core section before finalization."""
    depth_policy = policy.get("final_report_depth_policy")
    if not isinstance(depth_policy, dict):
        return [
            {
                "id": "policy:final_report_depth_policy",
                "passed": False,
                "severity": "error",
                "message": "final_report_depth_policy is missing or invalid; report-depth checks cannot be skipped.",
            }
        ]
    if depth_policy.get("enabled", True) is False:
        return [
            {
                "id": "policy:final_report_depth_policy:disabled",
                "passed": False,
                "severity": "error",
                "message": "final_report_depth_policy is disabled; v7 final reports require depth checks.",
            }
        ]

    core_marker = str(depth_policy.get("core_section_marker", "提交阻断问题"))
    secondary_marker = str(depth_policy.get("secondary_section_marker", "其他问题与说明"))
    core_section = _section_body(report_text, core_marker)
    secondary_section = _section_body(report_text, secondary_marker)
    blocks = _core_issue_blocks(core_section)
    secondary_blocks = _secondary_issue_blocks(secondary_section)
    max_issues = _coerce_int(depth_policy.get("max_core_issues", 5), 5)
    required_labels = [str(label).strip() for label in depth_policy.get("required_issue_labels", []) if str(label).strip()]
    child_required_labels = [
        str(label).strip() for label in depth_policy.get("child_required_labels", required_labels) if str(label).strip()
    ]
    child_heading_prefix = str(depth_policy.get("child_error_heading_prefix", "具体错误")).strip()
    require_child_errors = bool(depth_policy.get("require_child_errors", False))
    require_indexed_finding_detail_coverage = bool(
        depth_policy.get("require_indexed_finding_detail_coverage", False)
    )
    impact_max_sentences = _coerce_int(depth_policy.get("impact_max_sentences", 0), 0)
    checks = [
        {
            "id": "depth:core_section_present",
            "passed": bool(core_section),
            "severity": "error",
            "message": f"Final report contains the '{core_marker}' section.",
        },
        {
            "id": "depth:core_issue_limit",
            "passed": len(blocks) <= max_issues,
            "severity": "error",
            "message": f"Core issue count is <= {max_issues}; found {len(blocks)}.",
        },
    ]
    if depth_policy.get("secondary_section_required", False):
        checks.append(
            {
                "id": "depth:secondary_section_present",
                "passed": bool(secondary_section),
                "severity": "error",
                "message": f"Final report contains the '{secondary_marker}' section for non-core findings.",
            }
        )
    if depth_policy.get("secondary_issue_requires_detail_when_present", False):
        has_secondary_finding_ref = bool(re.search(r"\bARB-\d+\b", secondary_section, flags=re.IGNORECASE))
        checks.append(
            {
                "id": "depth:secondary_issue_detail_format",
                "passed": not has_secondary_finding_ref or bool(secondary_blocks),
                "severity": "error",
                "message": "Non-blocking ARB findings use S- numbered issue blocks instead of a one-line summary table.",
            }
        )
    if _report_claims_reject_verdict(report_text):
        minimum = _coerce_int(depth_policy.get("minimum_core_issues_for_reject", 1), 1)
        checks.append(
            {
                "id": "depth:reject_has_core_issue",
                "passed": len(blocks) >= minimum,
                "severity": "error",
                "message": f"Reject verdict has at least {minimum} evidence-backed core issue(s).",
            }
        )

    if require_indexed_finding_detail_coverage:
        missing_finding_ids = _indexed_finding_ids_without_detail_headings(
            report_text,
            child_heading_prefix,
        )
        checks.append(
            {
                "id": "depth:indexed_findings_have_detail_heading",
                "passed": not missing_finding_ids,
                "severity": "error",
                "message": (
                    "Every indexed F finding is named exactly in a concrete-error heading."
                    if not missing_finding_ids
                    else "Indexed F findings missing concrete-error headings: "
                    + ", ".join(missing_finding_ids)
                ),
            }
        )

    issue_groups = [("core", block) for block in blocks] + [("secondary", block) for block in secondary_blocks]
    for issue_kind, block in issue_groups:
        body = block["body"]
        child_errors = _child_error_blocks(body, child_heading_prefix)
        if require_child_errors:
            checks.append(
                {
                    "id": f"depth:{issue_kind}_issue_child_errors:{block['id']}",
                    "passed": bool(child_errors),
                    "severity": "error",
                    "message": f"{issue_kind.title()} issue {block['id']} is split into independently actionable '{child_heading_prefix}' blocks.",
                }
            )
        for child in child_errors:
            child_id = f"{block['id']}.{child['number']}"
            child_body = child["body"]
            for label in child_required_labels:
                checks.append(
                    {
                        "id": f"depth:{issue_kind}_child_field:{child_id}:{label}",
                        "passed": _has_nonempty_label(child_body, label),
                        "severity": "error",
                        "message": f"Actionable error {child_id} includes a non-empty '{label}' field.",
                    }
                )
            checks.append(
                {
                    "id": f"depth:{issue_kind}_child_docx_locator:{child_id}",
                    "passed": _has_reader_docx_locator(child_body),
                    "severity": "error",
                    "message": f"Actionable error {child_id} gives a searchable DOCX filename plus section/figure or verified page locator.",
                }
            )
        if impact_max_sentences > 0:
            impact_match = re.search(r"\*\*影响\*\*\s*[:：]\s*([^\n]+)", body)
            impact_text = impact_match.group(1).strip() if impact_match else ""
            sentence_count = len(re.findall(r"[。！？]", impact_text))
            checks.append(
                {
                    "id": f"depth:core_issue_impact_concise:{block['id']}",
                    "passed": bool(impact_text) and sentence_count <= impact_max_sentences,
                    "severity": "error",
                    "message": f"Core issue {block['id']} keeps '影响' within {impact_max_sentences} sentence(s).",
                }
            )
    internal_ref_pattern = re.compile(r"(?:^|[\s`])(?:[^\s`]+[\\/])?report_text\.txt`?\s*[:：]?\s*L?\s*\d+", re.IGNORECASE)
    checks.append(
        {
            "id": "depth:reader_report_no_internal_text_locator",
            "passed": not bool(internal_ref_pattern.search(report_text)),
            "severity": "error",
            "message": "Reader-facing final report does not expose report_text.txt line locators; use original DOCX filename, section/figure and searchable quote instead.",
        }
    )
    return checks


def build_reader_facing_report_checks(report_text: str, policy: dict) -> list[dict]:
    """Keep internal audit dossiers out of the reader-facing final report."""
    presentation_policy = policy.get("final_report_presentation_policy", {})
    forbidden_terms = [
        str(term).strip()
        for term in presentation_policy.get("forbidden_heading_terms", [])
        if str(term).strip()
    ]
    checks = []
    for line_no, _level, heading in _iter_headings(report_text):
        for term in forbidden_terms:
            if term in heading:
                checks.append(
                    {
                        "id": f"presentation:internal_heading:{line_no}:{term}",
                        "passed": False,
                        "severity": "error",
                        "message": f"Final report heading at line {line_no} exposes internal audit material: {term}.",
                    }
                )
    return checks


SEVERITY_LEVELS = {"FATAL", "CRITICAL", "MAJOR", "WARNING", "INFO"}


def _normalize_issue_severity(value: object) -> str:
    normalized = re.sub(r"[^A-Z]", "", str(value or "").upper())
    return normalized if normalized in SEVERITY_LEVELS else ""


def _issue_count_map_from_entries(issues: list[dict]) -> dict[str, int]:
    counts = {key: 0 for key in SEVERITY_LEVELS}
    seen: set[str] = set()
    for index, issue in enumerate(issues, start=1):
        severity = _normalize_issue_severity(issue.get("severity"))
        if not severity:
            continue
        issue_id = str(issue.get("id") or "").strip().upper()
        title = str(issue.get("title") or "").strip()
        key = issue_id or f"{index}:{title}"
        if key in seen:
            continue
        seen.add(key)
        counts[severity] += 1
    return counts


def _report_claims_reject_verdict(report_text: str) -> bool:
    return bool(
        re.search(
            r"(\u4e0d\u5408\u683c|\u4e0d\u5efa\u8bae\u63d0\u4ea4|\u9000\u56de\u4fee\u8ba2|\u9000\u56de)",
            report_text,
        )
    )


def build_issue_severity_count_checks(report_text: str) -> list[dict]:
    """Ensure the HTML dashboard cannot show zero issues for a blocking report."""
    issue_counts = count_issue_levels(report_text)
    issue_total = sum(issue_counts.values())
    issues = parse_issue_entries(report_text)
    parsed_counts = _issue_count_map_from_entries(issues)
    parsed_total = sum(parsed_counts.values())

    checks = [
        {
            "id": "severity:issue_entries_counted",
            "passed": parsed_total == 0 or issue_counts == parsed_counts,
            "severity": "error",
            "message": (
                "Issue severity dashboard counts match parsed issue entries."
                if parsed_total == 0 or issue_counts == parsed_counts
                else f"Issue severity dashboard counts {issue_counts} do not match parsed issue entries {parsed_counts}."
            ),
        },
        {
            "id": "severity:reject_verdict_has_issue_counts",
            "passed": not _report_claims_reject_verdict(report_text) or issue_total > 0,
            "severity": "error",
            "message": (
                "Reject verdict has non-zero issue counts."
                if not _report_claims_reject_verdict(report_text) or issue_total > 0
                else "Report says reject/not qualified, but rendered issue severity counts would all be zero."
            ),
        },
    ]
    return checks


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_subagent_supervision_checks(review_dir: Path, policy: dict) -> list[dict]:
    supervision_policy = policy.get("subagent_supervision_policy", {})
    if not supervision_policy.get("enabled", True):
        return []

    summary_name = supervision_policy.get("summary_json", "subagent_supervision_summary.json")
    summary_path = review_dir / summary_name
    checks = [
        {
            "id": "subagent_supervision:summary_present",
            "passed": summary_path.exists(),
            "severity": "error",
            "message": f"Subagent supervision summary present: {summary_name}",
        }
    ]
    if not summary_path.exists():
        return checks

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        checks.append(
            {
                "id": "subagent_supervision:summary_json_valid",
                "passed": False,
                "severity": "error",
                "message": f"Subagent supervision summary is valid JSON: {exc}",
            }
        )
        return checks

    required_fields = supervision_policy.get("required_fields", [])
    for field in required_fields:
        checks.append(
            {
                "id": f"subagent_supervision:field:{field}",
                "passed": field in summary,
                "severity": "error",
                "message": f"Subagent supervision summary includes required field: {field}",
            }
        )

    strategy = summary.get("subagent_strategy", {})
    if not isinstance(strategy, dict):
        strategy = {}
    completed = summary.get("completed_subagents", [])
    if not isinstance(completed, list):
        completed = []
    min_completed = _coerce_int(supervision_policy.get("minimum_completed_subagents", 3), 3)
    max_minutes = _coerce_int(supervision_policy.get("max_subagent_minutes", 30), 30)

    checks.extend(
        [
            {
                "id": "subagent_supervision:passed",
                "passed": summary.get("passed") is True,
                "severity": "error",
                "message": "Subagent supervision summary explicitly marks the gate as passed.",
            },
            {
                "id": "subagent_supervision:leader_supervises",
                "passed": str(summary.get("leader_role", "")).lower() in {"supervisor", "dispatcher", "monitor"},
                "severity": "error",
                "message": "Leader role is recorded as supervisor/dispatcher/monitor, not primary reviewer.",
            },
            {
                "id": "subagent_supervision:minimum_completed_subagents",
                "passed": len(completed) >= min_completed,
                "severity": "error",
                "message": f"At least {min_completed} completed first-level subagent slices are recorded.",
            },
            {
                "id": "subagent_supervision:no_recursive_subagents",
                "passed": strategy.get("recursive_subagents_allowed") is False
                and summary.get("recursive_subagents_allowed", False) is False,
                "severity": "error",
                "message": "Recursive subagent delegation is disabled for normal audit work.",
            },
            {
                "id": "subagent_supervision:max_30_minutes",
                "passed": _coerce_int(strategy.get("max_subagent_minutes", summary.get("max_subagent_minutes")), max_minutes + 1) <= max_minutes,
                "severity": "error",
                "message": f"Subagent slice timeout is recorded as <= {max_minutes} minutes.",
            },
            {
                "id": "subagent_supervision:timeout_policy",
                "passed": bool(strategy.get("timeout_policy") or summary.get("timeout_policy")),
                "severity": "error",
                "message": "Timeout/stall polling and redispatch policy is recorded.",
            },
        ]
    )
    return checks


def build_checks(review_dir: Path, report_text: str, policy: dict) -> list[dict]:
    checks = []
    checks.extend(build_reader_facing_report_checks(report_text, policy))
    explicit_verdict = extract_report_verdict(report_text)
    checks.append(
        {
            "id": "verdict:explicit_conclusion",
            "passed": explicit_verdict is not None,
            "severity": "error",
            "message": (
                "Final report states an explicit, parseable audit verdict."
                if explicit_verdict is not None
                else "Final report must state an explicit, parseable verdict in the audit conclusion."
            ),
        }
    )

    for filename in policy["required_final_files"]:
        path = review_dir / filename
        passed = True if filename == "final_report_lint.json" else path.exists()
        checks.append(
            {
                "id": f"file:{filename}",
                "passed": passed,
                "severity": "error",
                "message": f"Required file present: {filename}",
            }
        )

    for check_id, keywords in policy["required_final_sections"].items():
        passed = all(keyword in report_text for keyword in keywords)
        checks.append(
            {
                "id": f"section:{check_id}",
                "passed": passed,
                "severity": "error",
                "message": f"Final report contains required section markers: {', '.join(keywords)}",
            }
        )

    normalized_report_text = report_text.replace("**", "")
    has_locator = bool(re.search(r"(位置|原报告位置|证据文件位置|证据)\s*[:：]", normalized_report_text))
    has_evidence = bool(re.search(r"(证据|证据链|原文短句)\s*[:：]", normalized_report_text))
    checks.append(
        {
            "id": "evidence:locator",
            "passed": has_locator,
            "severity": "error",
            "message": "Final report includes explicit locator labels for findings.",
        }
    )
    checks.append(
        {
            "id": "evidence:quoted_support",
            "passed": has_evidence,
            "severity": "error",
            "message": "Final report includes explicit evidence labels for findings.",
        }
    )

    project_structure_path = review_dir / "project_structure.json"
    if project_structure_path.exists():
        try:
            project_structure = json.loads(project_structure_path.read_text(encoding="utf-8"))
            total_code_files = project_structure.get("metadata", {}).get("total_code_files", 0)
        except json.JSONDecodeError:
            total_code_files = None
        if total_code_files == 0:
            checks.append(
                {
                    "id": "code_risk:declared",
                    "passed": "代码不可复现" in report_text,
                    "severity": "error",
                    "message": "If no code was delivered, the final report must explicitly mention code irreproducibility risk.",
                }
            )

    for phrase in policy["forbidden_shortcuts"]:
        checks.append(
            {
                "id": f"forbidden:{phrase}",
                "passed": phrase not in report_text,
                "severity": "warning",
                "message": f"Avoid vague filler phrase without structured evidence: {phrase}",
            }
        )

    checks.extend(build_markdown_quality_checks(review_dir, policy))
    checks.extend(build_terminology_style_checks(review_dir, policy))
    checks.extend(build_delivery_state_checks(report_text, policy))
    checks.extend(build_subagent_supervision_checks(review_dir, policy))
    checks.extend(build_issue_severity_count_checks(report_text))
    checks.extend(build_analysis_issue_consistency_checks(review_dir, report_text))
    checks.extend(build_report_depth_checks(report_text, policy))

    return checks


def summarize_checks(checks: list[dict], policy: dict) -> dict:
    normalized_checks = []
    for check in checks:
        normalized = dict(check)
        normalized["severity"] = _effective_severity(check["id"], check["severity"], policy)
        normalized_checks.append(normalized)

    ignored_warnings = [
        check for check in normalized_checks
        if check["severity"] == "warning" and not check["passed"] and _should_ignore_warning(check["id"], policy)
    ]
    active_checks = [
        check for check in normalized_checks
        if not (check["severity"] == "warning" and not check["passed"] and _should_ignore_warning(check["id"], policy))
    ]
    errors = [check for check in active_checks if check["severity"] == "error" and not check["passed"]]
    warnings = [check for check in active_checks if check["severity"] == "warning" and not check["passed"]]
    return {
        "passed": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "checks": normalized_checks,
        "errors": errors,
        "warnings": warnings,
        "ignored_warning_count": len(ignored_warnings),
        "ignored_warnings": ignored_warnings,
    }


def main() -> int:
    args = parse_args()
    review_dir, report_path = resolve_paths(args.input_path)
    report_text = report_path.read_text(encoding="utf-8")
    policy = load_policy()

    checks = build_checks(review_dir, report_text, policy)
    summary = summarize_checks(checks, policy)
    link_cache_path = review_dir / "lint_link_cache.json"
    link_cache = _load_link_cache(link_cache_path)
    current_run_cached_hits = sum(
        1
        for check in summary["checks"]
        if check["id"].startswith("markdown:external_link:") and "[cached]" in check["message"]
    )
    current_run_live_checks = sum(
        1
        for check in summary["checks"]
        if check["id"].startswith("markdown:external_link:") and "[cached]" not in check["message"]
    )
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "review_dir": str(review_dir),
        "report_path": str(report_path),
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "passed": summary["passed"],
        "error_count": summary["error_count"],
        "warning_count": summary["warning_count"],
        "ignored_warning_count": summary["ignored_warning_count"],
        "checks": summary["checks"],
        "ignored_warnings": summary["ignored_warnings"],
        "lint_cache_stats": {
            "cache_file": str(link_cache_path),
            "cache_entry_count": len(link_cache),
            "current_run_cached_hits": current_run_cached_hits,
            "current_run_live_checks": current_run_live_checks,
        },
        "suggested_fixes": _build_suggested_fixes(summary["errors"] + summary["warnings"]),
    }

    output_path = Path(args.output) if args.output else review_dir / "final_report_lint.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"final report lint written: {output_path}")
    print(f"passed={summary['passed']} errors={summary['error_count']} warnings={summary['warning_count']}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
