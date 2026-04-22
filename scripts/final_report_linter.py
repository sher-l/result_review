#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Lint final_review_report.md and its required companion files.

The goal is to block under-specified reports from being treated as complete.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from policy_loader import load_policy


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
            action = "将术语替换成框架标准表述，避免混入口径不一致或人工审核措辞。"
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


def build_checks(review_dir: Path, report_text: str, policy: dict) -> list[dict]:
    checks = []

    for filename in policy["required_final_files"]:
        path = review_dir / filename
        checks.append(
            {
                "id": f"file:{filename}",
                "passed": path.exists(),
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

    has_locator = bool(re.search(r"(位置|原报告位置|证据文件位置)\s*[:：]", report_text))
    has_evidence = bool(re.search(r"(证据|证据链|原文短句)\s*[:：]", report_text))
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
