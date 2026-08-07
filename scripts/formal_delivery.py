#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bind a formal audit report to the exact HTML artifact allowed for delivery."""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

from audit_contract import atomic_write_json, sha256_file, utc_offset_now
from html_presentation_contract import validate_html_presentation_file
from policy_loader import load_policy
from visual_audit import validate_visual_audit_result


DEFAULT_MANIFEST_FILENAME = "formal_delivery_manifest.json"
SOURCE_MARKDOWN_SHA256_COMMENT = "audit-source-markdown-sha256"
SOURCE_MARKDOWN_SHA256_RE = re.compile(
    rf"<!--\s*{SOURCE_MARKDOWN_SHA256_COMMENT}:\s*([0-9a-f]{{64}})\s*-->",
    re.IGNORECASE,
)
_GENERATED_AT_BADGE_RE = re.compile(
    r'<span class="badge">⏱ \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}</span>'
)
_GENERATED_AT_BADGE_SENTINEL = '<span class="badge">⏱ __GENERATED_AT__</span>'
DEFAULT_PROHIBITED_REPORT_STATE_PHRASES = (
    "草案",
    "复审草案",
    "审核报告（草案）",
    "待最终门禁",
    "待正式发布",
    "未发送通知",
    "未发送",
    "未归档",
    "未声明审核已完成",
)
_FORMAL_DECISION_PRESENTATION = {
    ("合格", "ALLOW"): ("verdict-pass", "合格"),
    ("有条件合格", "CONDITIONAL"): ("verdict-conditional", "有条件合格"),
    ("不合格", "BLOCK"): ("verdict-reject", "不合格"),
}
_VERDICT_CLASSES = frozenset(item[0] for item in _FORMAL_DECISION_PRESENTATION.values())
_CLASS_ATTRIBUTE_RE = re.compile(
    r"""\bclass\s*=\s*(?P<quote>["'])(?P<classes>.*?)(?P=quote)""",
    re.IGNORECASE | re.DOTALL,
)
HTML_REPORT_METADATA_ALIASES = (
    "html_report",
    "HTML",
    "html",
    "html_path",
    "HTML路径",
    "HTML报告",
    "report_html",
)
FORMAL_HTML_REPORT_METADATA_KEYS = ("html_report", "HTML")


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_html_report_metadata_path(
    metadata: dict[str, str],
    *,
    require_formal_alias: bool = True,
) -> tuple[Path | None, str]:
    """Resolve one unambiguous HTML attachment path from metadata.

    Every populated legacy alias participates in conflict detection so a
    formal gate cannot validate one path while a notification client selects
    another.  Formal delivery still requires one of its two canonical keys.
    """
    candidates: list[tuple[str, Path]] = []
    for key in HTML_REPORT_METADATA_ALIASES:
        value = str(metadata.get(key, "") or "").strip()
        if value:
            candidates.append((key, Path(value).expanduser().resolve()))

    distinct_paths = {path for _, path in candidates}
    if len(distinct_paths) > 1:
        populated_keys = ", ".join(key for key, _ in candidates)
        return None, (
            "formal delivery manifest HTML metadata aliases conflict: "
            f"{populated_keys}"
        )

    if require_formal_alias:
        formal_candidates = [
            path for key, path in candidates if key in FORMAL_HTML_REPORT_METADATA_KEYS
        ]
        if not formal_candidates:
            return None, (
                "formal delivery manifest requires review_dir, project_id, and html_report"
            )
        return formal_candidates[0], ""

    if not candidates:
        return None, "html report missing"
    return candidates[0][1], ""


def _configured_filename(config: dict, key: str, default: str) -> str:
    gate = config.get("formal_delivery_gate", {}) if isinstance(config, dict) else {}
    if not isinstance(gate, dict):
        gate = {}
    filename = str(gate.get(key, default) or default).strip()
    return filename if Path(filename).name == filename else ""


def formal_delivery_gate_enabled(config: dict) -> bool:
    gate = config.get("formal_delivery_gate", {}) if isinstance(config, dict) else {}
    return not isinstance(gate, dict) or gate.get("enabled", True) is not False


def prohibited_report_state_phrases(policy: dict | None = None) -> tuple[str, ...]:
    delivery_policy = policy.get("formal_delivery_policy", {}) if isinstance(policy, dict) else {}
    configured = delivery_policy.get("prohibited_report_state_phrases", []) if isinstance(delivery_policy, dict) else []
    phrases = configured if isinstance(configured, list) and configured else DEFAULT_PROHIBITED_REPORT_STATE_PHRASES
    return tuple(str(phrase).strip() for phrase in phrases if str(phrase).strip())


def find_report_state_violations(text: str, policy: dict | None = None) -> list[str]:
    return [phrase for phrase in prohibited_report_state_phrases(policy) if phrase in text]


def _html_source_markdown_sha256(html_path: Path) -> str:
    match = SOURCE_MARKDOWN_SHA256_RE.search(html_path.read_text(encoding="utf-8"))
    return match.group(1).lower() if match else ""


def _html_binds_current_markdown(report_path: Path, html_path: Path) -> bool:
    return _html_source_markdown_sha256(html_path) == sha256_file(report_path)


def _normalize_canonical_render_timestamp(html_text: str) -> tuple[str, str]:
    normalized, replacement_count = _GENERATED_AT_BADGE_RE.subn(
        _GENERATED_AT_BADGE_SENTINEL,
        html_text,
    )
    if replacement_count != 1:
        return "", (
            "canonical renderer output must contain exactly one generated-at badge"
        )
    return normalized, ""


def validate_html_canonical_equivalence(
    report_path: Path,
    html_path: Path,
    decision_path: Path | None = None,
) -> tuple[bool, str]:
    """Require delivered HTML to equal a fresh policy-owned render.

    The generated-at badge is the renderer's only intentionally variable field.
    Its exact location is normalized; every other byte of the rendered document,
    including section presence and order, must remain identical.
    """
    try:
        report_text = report_path.read_text(encoding="utf-8")
        actual_text = html_path.read_text(encoding="utf-8")
        final_decision = None
        if decision_path is not None:
            final_decision = json.loads(decision_path.read_text(encoding="utf-8"))
            if not isinstance(final_decision, dict):
                return False, "canonical renderer final decision root must be an object"

        expected_prefix = (
            f"<!-- {SOURCE_MARKDOWN_SHA256_COMMENT}: {sha256_file(report_path)} -->\n"
        )
        if not actual_text.startswith(expected_prefix):
            return False, (
                "canonical renderer source binding must be the first exact HTML line"
            )

        # Imported lazily so formal_delivery remains independent from the renderer
        # during module initialization.
        from render_final_review_html import build_html

        expected_render = (
            build_html(report_text, report_path, final_decision=final_decision)
            if final_decision is not None
            else build_html(report_text, report_path)
        )
    except Exception as exc:  # fail closed at every delivery/notification gate
        return False, f"canonical renderer could not reproduce HTML: {type(exc).__name__}: {exc}"

    actual_render = actual_text[len(expected_prefix):]
    normalized_actual, actual_reason = _normalize_canonical_render_timestamp(
        actual_render
    )
    if actual_reason:
        return False, actual_reason
    normalized_expected, expected_reason = _normalize_canonical_render_timestamp(
        expected_render
    )
    if expected_reason:
        return False, expected_reason
    if normalized_actual != normalized_expected:
        return False, (
            "canonical renderer output differs from the current Markdown, decision, "
            "policy-owned template, or inventory"
        )
    return True, ""


def _decision_filename(policy: dict | None) -> str:
    contract_policy = policy.get("audit_contract_policy", {}) if isinstance(policy, dict) else {}
    if not isinstance(contract_policy, dict):
        contract_policy = {}
    filename = str(contract_policy.get("decision_json", "final_decision.json") or "final_decision.json").strip()
    return filename if Path(filename).name == filename else ""


def _decision_binding(
    review_dir: Path,
    decision_sha256: str,
    policy: dict | None,
) -> tuple[str, Path]:
    """Resolve and validate the sealed decision bound to a formal delivery."""
    expected_hash = str(decision_sha256 or "").strip().lower()
    contract_policy = policy.get("audit_contract_policy", {}) if isinstance(policy, dict) else {}
    if not isinstance(contract_policy, dict):
        contract_policy = {}
    contract_mode = str(contract_policy.get("mode", "enforce") or "enforce").strip().lower()
    if not expected_hash:
        if contract_mode == "enforce":
            raise ValueError("formal delivery blocked: sealed final decision SHA256 is required")
        return "", review_dir / "final_decision.json"
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise ValueError("formal delivery blocked: final decision SHA256 is invalid")
    decision_name = _decision_filename(policy)
    if not decision_name:
        raise ValueError("formal delivery blocked: final decision filename must be a direct child")
    decision_path = review_dir / decision_name
    if not decision_path.is_file() or sha256_file(decision_path) != expected_hash:
        raise ValueError("formal delivery blocked: final decision is missing or does not match the sealed SHA256")
    return expected_hash, decision_path


def _tag_class_tokens(html_text: str, tag_name: str) -> tuple[set[str], re.Match[str] | None]:
    tag_pattern = re.compile(
        rf"<{re.escape(tag_name)}\b(?P<attrs>[^>]*)>",
        re.IGNORECASE | re.DOTALL,
    )
    for tag_match in tag_pattern.finditer(html_text):
        class_match = _CLASS_ATTRIBUTE_RE.search(tag_match.group("attrs"))
        if class_match:
            return set(class_match.group("classes").split()), tag_match
    return set(), None


def _verdict_banner(html_text: str) -> tuple[set[str], str] | None:
    opening_pattern = re.compile(
        r"<(?P<tag>div|section)\b(?P<attrs>[^>]*)>",
        re.IGNORECASE | re.DOTALL,
    )
    for opening_match in opening_pattern.finditer(html_text):
        class_match = _CLASS_ATTRIBUTE_RE.search(opening_match.group("attrs"))
        classes = set(class_match.group("classes").split()) if class_match else set()
        if "verdict-banner" not in classes:
            continue
        closing_match = re.search(
            rf"</{re.escape(opening_match.group('tag'))}\s*>",
            html_text[opening_match.end():],
            re.IGNORECASE,
        )
        if closing_match is None:
            return classes, ""
        content = html_text[
            opening_match.end(): opening_match.end() + closing_match.start()
        ]
        visible_text = re.sub(r"<[^>]+>", " ", unescape(content))
        return classes, re.sub(r"\s+", " ", visible_text).strip()
    return None


def validate_html_decision_consistency(
    html_path: Path,
    decision_path: Path,
) -> tuple[bool, str]:
    """Validate the visible HTML verdict against the sealed decision."""
    try:
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        html_text = html_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False, "HTML verdict consistency inputs are missing or unreadable"
    if not isinstance(decision, dict) or decision.get("status") != "leader_confirmed":
        return False, "HTML verdict cannot bind a non-confirmed final decision"
    pair = (
        str(decision.get("verdict", "")).strip(),
        str(decision.get("release_decision", "")).strip(),
    )
    presentation = _FORMAL_DECISION_PRESENTATION.get(pair)
    if presentation is None:
        return False, "HTML verdict cannot bind an invalid verdict/release_decision pair"
    expected_class, expected_text = presentation

    body_classes, body_match = _tag_class_tokens(html_text, "body")
    if body_match is None or body_classes.intersection(_VERDICT_CLASSES) != {expected_class}:
        return False, f"HTML verdict body class must be {expected_class}"

    banner = _verdict_banner(html_text)
    if banner is None:
        return False, "HTML verdict banner is missing"
    banner_classes, banner_text = banner
    if banner_classes.intersection(_VERDICT_CLASSES) != {expected_class}:
        return False, f"HTML verdict banner class must be {expected_class}"
    if re.fullmatch(
        rf"审核结论\s*[：:]\s*{re.escape(expected_text)}",
        banner_text,
    ) is None:
        return False, f"HTML verdict banner text must be 审核结论：{expected_text}"
    return True, ""


def _visual_closure_artifacts(review_dir: Path, policy: dict | None) -> list[dict[str, str]]:
    """Discover only policy-owned visual closure outputs inside this review directory."""
    closure_policy = policy.get("visual_closure_policy", {}) if isinstance(policy, dict) else {}
    if not isinstance(closure_policy, dict):
        closure_policy = {}
    configured_paths = [
        ("visual_audit_result", closure_policy.get("result_json", "visual_audit_result.json")),
        ("visual_inventory", closure_policy.get("inventory_json", "")),
    ]
    # Older reviews may retain a standalone inventory even when the active policy embeds
    # inventory in visual_audit_result.json. Bind it when present without broad traversal.
    configured_paths.append(("visual_inventory", "visual_inventory.json"))

    discovered: dict[str, dict[str, str]] = {}
    for artifact_type, raw_path in configured_paths:
        relative_path = str(raw_path or "").strip()
        if not relative_path:
            continue
        candidate = (review_dir / relative_path).resolve()
        if not _within(review_dir, candidate) or not candidate.is_file():
            continue
        normalized_path = str(candidate.relative_to(review_dir))
        discovered[normalized_path] = {
            "type": artifact_type,
            "path": normalized_path,
            "sha256": sha256_file(candidate),
        }
    return [discovered[path] for path in sorted(discovered)]


def _validate_visual_closure_artifacts(
    review_dir: Path,
    recorded: object,
    policy: dict | None,
) -> tuple[bool, str]:
    if not isinstance(recorded, list):
        return False, "formal delivery manifest visual closure artifacts are missing"
    current = _visual_closure_artifacts(review_dir, policy)
    current_by_path = {artifact["path"]: artifact for artifact in current}
    recorded_by_path: dict[str, dict] = {}
    for artifact in recorded:
        if not isinstance(artifact, dict):
            return False, "formal delivery manifest visual closure artifact is invalid"
        relative_path = str(artifact.get("path", "")).strip()
        expected_hash = str(artifact.get("sha256", "")).strip().lower()
        candidate = (review_dir / relative_path).resolve()
        if (
            not relative_path
            or not _within(review_dir, candidate)
            or relative_path in recorded_by_path
            or len(expected_hash) != 64
        ):
            return False, "formal delivery manifest visual closure artifact is invalid"
        recorded_by_path[relative_path] = artifact
    # The active policy may have configured an additional inventory path at manifest
    # creation time. Every recorded artifact is re-hashed below; current default paths
    # are additionally required so a newly introduced standard closure file cannot be
    # silently omitted from an older manifest.
    if not set(current_by_path).issubset(recorded_by_path):
        return False, "formal delivery manifest visual closure artifact set mismatch"
    for relative_path, recorded_artifact in recorded_by_path.items():
        candidate = (review_dir / relative_path).resolve()
        current_artifact = current_by_path.get(relative_path)
        expected_type = current_artifact["type"] if current_artifact else str(recorded_artifact.get("type", "")).strip()
        if not candidate.is_file() or not expected_type:
            return False, f"formal delivery manifest visual closure artifact is missing: {relative_path}"
        recorded_artifact = recorded_by_path[relative_path]
        if (
            str(recorded_artifact.get("type", "")).strip() != expected_type
            or str(recorded_artifact.get("sha256", "")).strip().lower() != sha256_file(candidate)
        ):
            return False, f"formal delivery manifest visual closure artifact hash mismatch: {relative_path}"

    result_artifacts = [
        artifact
        for artifact in recorded_by_path.values()
        if str(artifact.get("type", "")).strip() == "visual_audit_result"
    ]
    if len(result_artifacts) != 1:
        return False, "formal delivery manifest must bind exactly one visual audit result"
    visual_result_path = (review_dir / str(result_artifacts[0].get("path", ""))).resolve()
    try:
        visual_result = json.loads(visual_result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False, "formal delivery visual audit result is missing or unreadable"
    if not isinstance(visual_result, dict):
        return False, "formal delivery visual audit result root must be an object"
    try:
        visual_validation = validate_visual_audit_result(
            review_dir,
            visual_result,
            policy or load_policy(),
        )
    except (OSError, UnicodeError, ValueError) as exc:
        return False, f"formal delivery visual audit result cannot be revalidated: {exc}"
    if not visual_validation.get("passed", False):
        errors = visual_validation.get("errors", [])
        first_error = errors[0].get("message", "") if errors and isinstance(errors[0], dict) else ""
        return False, "formal delivery visual audit result is not closed" + (
            f": {first_error}" if first_error else ""
        )
    return True, ""


def build_formal_delivery_manifest(
    review_dir: Path,
    html_path: Path,
    *,
    decision_sha256: str = "",
    policy: dict | None = None,
) -> tuple[Path, dict]:
    """Write a manifest only for a semantically final, local report/HTML pair."""
    review_dir = review_dir.resolve()
    effective_policy = policy if isinstance(policy, dict) else load_policy()
    report_path = review_dir / "final_review_report.md"
    if not report_path.is_file() or not html_path.is_file():
        raise ValueError("formal delivery blocked: final Markdown or HTML report is missing")
    if not _within(review_dir, html_path):
        raise ValueError("formal delivery blocked: HTML report is outside review directory")
    if not _html_binds_current_markdown(report_path, html_path):
        raise ValueError("formal delivery blocked: HTML source Markdown SHA256 is absent or does not match current report")

    violations = find_report_state_violations(report_path.read_text(encoding="utf-8"), effective_policy)
    if violations:
        raise ValueError("formal delivery blocked: report contains pre-release state text: " + "、".join(violations))
    html_violations = find_report_state_violations(html_path.read_text(encoding="utf-8"), effective_policy)
    if html_violations:
        raise ValueError("formal delivery blocked: HTML contains pre-release state text: " + "、".join(html_violations))

    delivery_policy = effective_policy.get("formal_delivery_policy", {})
    manifest_name = str(delivery_policy.get("manifest_filename", DEFAULT_MANIFEST_FILENAME) or DEFAULT_MANIFEST_FILENAME)
    if Path(manifest_name).name != manifest_name:
        raise ValueError("formal delivery blocked: manifest filename must be a direct child")
    manifest_path = review_dir / manifest_name
    sealed_decision_sha256, decision_path = _decision_binding(
        review_dir,
        decision_sha256,
        effective_policy,
    )
    if sealed_decision_sha256:
        verdict_ok, verdict_reason = validate_html_decision_consistency(
            html_path,
            decision_path,
        )
        if not verdict_ok:
            raise ValueError(f"formal delivery blocked: {verdict_reason}")
    presentation_ok, presentation_reason = validate_html_presentation_file(html_path)
    if not presentation_ok:
        raise ValueError(
            f"formal delivery blocked: HTML presentation contract: {presentation_reason}"
        )
    canonical_ok, canonical_reason = validate_html_canonical_equivalence(
        report_path,
        html_path,
        decision_path if sealed_decision_sha256 else None,
    )
    if not canonical_ok:
        raise ValueError(
            f"formal delivery blocked: HTML canonical renderer: {canonical_reason}"
        )
    visual_closure_artifacts = _visual_closure_artifacts(review_dir, effective_policy)
    visual_ok, visual_reason = _validate_visual_closure_artifacts(
        review_dir,
        visual_closure_artifacts,
        effective_policy,
    )
    if not visual_ok:
        raise ValueError(f"formal delivery blocked: {visual_reason}")

    manifest = {
        "schema_version": "1.0",
        "delivery_state": "formal_delivery_ready",
        "project_id": review_dir.name,
        "created_at": utc_offset_now(),
        "decision_sha256": sealed_decision_sha256,
        "visual_closure_artifacts": visual_closure_artifacts,
        "artifacts": {
            "final_review_report": {
                "path": "final_review_report.md",
                "sha256": sha256_file(report_path),
            },
            "html_report": {
                "path": str(html_path.resolve().relative_to(review_dir)),
                "sha256": sha256_file(html_path),
            },
        },
    }
    if sealed_decision_sha256:
        manifest["artifacts"]["final_decision"] = {
            "path": str(decision_path.resolve().relative_to(review_dir)),
            "sha256": sealed_decision_sha256,
        }
    atomic_write_json(manifest_path, manifest)
    return manifest_path, manifest


def validate_formal_delivery_manifest(metadata: dict[str, str], config: dict) -> tuple[bool, str]:
    """Fail closed before WeCom delivery unless the sent HTML matches its manifest."""
    if not formal_delivery_gate_enabled(config):
        return True, ""
    review_text = str(metadata.get("review_dir") or metadata.get("审核目录") or "").strip()
    project_id = str(metadata.get("project_id") or metadata.get("项目号") or metadata.get("项目编号") or "").strip()
    html_path, html_path_reason = resolve_html_report_metadata_path(metadata)
    if not review_text or not project_id:
        return False, "formal delivery manifest requires review_dir, project_id, and html_report"
    if html_path is None:
        return False, html_path_reason
    # Finalize accepts relative CLI paths. Normalize them before revalidating
    # visual assets, whose persisted paths are always absolute.
    review_dir = Path(review_text).resolve()
    if not review_dir.is_dir() or not html_path.is_file() or not _within(review_dir, html_path):
        return False, "formal delivery manifest review directory or HTML path is invalid"

    manifest_name = _configured_filename(config, "manifest_filename", DEFAULT_MANIFEST_FILENAME)
    if not manifest_name:
        return False, "formal delivery manifest filename is invalid"
    manifest_path = review_dir / manifest_name
    supplied_path = str(metadata.get("formal_delivery_manifest", "")).strip()
    if supplied_path and Path(supplied_path).resolve() != manifest_path.resolve():
        return False, "formal delivery manifest path does not match the review directory"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False, "formal delivery manifest is missing or unreadable"
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0":
        return False, "formal delivery manifest schema is invalid"
    if manifest.get("delivery_state") != "formal_delivery_ready" or manifest.get("project_id") != project_id:
        return False, "formal delivery manifest state or project id is invalid"
    policy = load_policy()
    visual_ok, visual_reason = _validate_visual_closure_artifacts(
        review_dir,
        manifest.get("visual_closure_artifacts"),
        policy,
    )
    if not visual_ok:
        return False, visual_reason

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return False, "formal delivery manifest artifacts are missing"
    expected = {
        "final_review_report": (review_dir / "final_review_report.md"),
        "html_report": html_path,
    }
    decision_sha256 = str(manifest.get("decision_sha256", "")).strip().lower()
    contract_policy = policy.get("audit_contract_policy", {})
    if not isinstance(contract_policy, dict):
        contract_policy = {}
    contract_mode = str(contract_policy.get("mode", "enforce") or "enforce").strip().lower()
    if not decision_sha256 and contract_mode == "enforce":
        return False, "formal delivery manifest sealed final decision SHA256 is missing"
    if decision_sha256:
        decision_name = _decision_filename(policy)
        if not decision_name:
            return False, "formal delivery manifest final decision filename is invalid"
        expected["final_decision"] = review_dir / decision_name
    for name, expected_path in expected.items():
        record = artifacts.get(name)
        if not isinstance(record, dict):
            return False, f"formal delivery manifest artifact is missing: {name}"
        relative_path = str(record.get("path", "")).strip()
        candidate = (review_dir / relative_path).resolve()
        if not relative_path or not _within(review_dir, candidate) or candidate != expected_path.resolve():
            return False, f"formal delivery manifest artifact path mismatch: {name}"
        expected_hash = str(record.get("sha256", "")).strip().lower()
        if len(expected_hash) != 64 or sha256_file(expected_path) != expected_hash:
            return False, f"formal delivery manifest artifact hash mismatch: {name}"
        if name == "html_report" and str(metadata.get("html_report_sha256", "")).strip().lower() != expected_hash:
            return False, "formal delivery manifest HTML hash is absent or does not match the manifest"
        if name == "final_decision" and expected_hash != decision_sha256:
            return False, "formal delivery manifest final decision hash does not match decision_sha256"

    if decision_sha256:
        verdict_ok, verdict_reason = validate_html_decision_consistency(
            expected["html_report"],
            expected["final_decision"],
        )
        if not verdict_ok:
            return False, verdict_reason
    presentation_ok, presentation_reason = validate_html_presentation_file(
        expected["html_report"]
    )
    if not presentation_ok:
        return False, f"HTML presentation contract: {presentation_reason}"
    canonical_ok, canonical_reason = validate_html_canonical_equivalence(
        expected["final_review_report"],
        expected["html_report"],
        expected.get("final_decision"),
    )
    if not canonical_ok:
        return False, f"HTML canonical renderer: {canonical_reason}"

    supplied_manifest_hash = str(metadata.get("formal_delivery_manifest_sha256", "")).strip().lower()
    if supplied_manifest_hash != sha256_file(manifest_path):
        return False, "formal delivery manifest hash is absent or does not match the manifest"

    report_text = expected["final_review_report"].read_text(encoding="utf-8")
    html_text_content = expected["html_report"].read_text(encoding="utf-8")
    if not _html_binds_current_markdown(expected["final_review_report"], expected["html_report"]):
        return False, "formal delivery manifest HTML source Markdown SHA256 is absent or does not match current report"
    violations = find_report_state_violations(report_text) + find_report_state_violations(html_text_content)
    if violations:
        return False, "formal delivery manifest contains pre-release state text: " + "、".join(sorted(set(violations)))
    return True, ""
