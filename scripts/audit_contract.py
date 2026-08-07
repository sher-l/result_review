#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Validation and persistence helpers for the sealed audit decision contract."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from render_final_review_html import extract_explicit_verdict


DEFAULT_SEVERITIES = ("FATAL", "CRITICAL", "MAJOR", "WARNING", "INFO")
DEFAULT_VERDICT_RELEASE_PAIRS = {
    "合格": "ALLOW",
    "有条件合格": "CONDITIONAL",
    "不合格": "BLOCK",
}
REQUIRED_SOURCES = ("arbitration_resolution", "final_review_report")
REPORT_VERDICT_BY_CLASS = {
    "verdict-pass": "合格",
    "verdict-conditional": "有条件合格",
    "verdict-reject": "不合格",
}


def utc_offset_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write a complete JSON document and atomically replace the destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def contract_mode(policy: dict[str, Any]) -> str:
    mode = str(policy.get("mode", "enforce") or "enforce").strip().lower()
    return mode if mode in {"shadow", "enforce"} else "enforce"


def extract_report_verdict(markdown_text: str) -> str | None:
    """Return the contract-level verdict parsed from an explicit report conclusion."""
    explicit = extract_explicit_verdict(markdown_text)
    if explicit is None:
        return None
    return REPORT_VERDICT_BY_CLASS.get(explicit[0])


def _record_check(
    checks: list[dict[str, Any]],
    errors: list[str],
    *,
    name: str,
    passed: bool,
    message: str,
) -> None:
    checks.append({"name": name, "passed": passed, "message": message})
    if not passed:
        errors.append(message)


def _is_nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"Missing contract file: {path.name}"
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"Invalid JSON contract {path.name}: {exc}"
    if not isinstance(loaded, dict):
        return None, f"Contract root must be an object: {path.name}"
    return loaded, None


def _validate_source(
    review_dir: Path,
    source_name: str,
    source: Any,
    *,
    require_relative: bool,
    checks: list[dict[str, Any]],
    errors: list[str],
    input_hashes: dict[str, str],
) -> None:
    if not isinstance(source, dict):
        _record_check(
            checks,
            errors,
            name=f"source.{source_name}.object",
            passed=False,
            message=f"sources.{source_name} must be an object",
        )
        return

    raw_path = source.get("path")
    declared_hash = source.get("sha256")
    path_valid = isinstance(raw_path, str) and bool(raw_path.strip())
    if path_valid:
        relative_path = Path(raw_path)
        path_valid = not relative_path.is_absolute()
    else:
        relative_path = Path("")
    if require_relative and path_valid:
        path_valid = ".." not in relative_path.parts

    _record_check(
        checks,
        errors,
        name=f"source.{source_name}.relative_path",
        passed=path_valid,
        message=(
            f"sources.{source_name}.path is review-relative"
            if path_valid
            else f"sources.{source_name}.path must be a non-empty review-relative path"
        ),
    )
    if not path_valid:
        return

    review_root = review_dir.resolve()
    source_path = (review_root / relative_path).resolve()
    within_review = source_path.is_relative_to(review_root)
    _record_check(
        checks,
        errors,
        name=f"source.{source_name}.within_review",
        passed=within_review,
        message=(
            f"sources.{source_name}.path resolves inside review directory"
            if within_review
            else f"sources.{source_name}.path escapes review directory"
        ),
    )
    if not within_review:
        return

    exists = source_path.is_file()
    _record_check(
        checks,
        errors,
        name=f"source.{source_name}.exists",
        passed=exists,
        message=(
            f"sources.{source_name} exists"
            if exists
            else f"sources.{source_name} is not a regular file: {raw_path}"
        ),
    )
    if not exists:
        return

    actual_hash = sha256_file(source_path)
    input_hashes[source_name] = actual_hash
    hash_format_valid = (
        isinstance(declared_hash, str)
        and len(declared_hash) == 64
        and all(character in "0123456789abcdef" for character in declared_hash.lower())
    )
    hash_matches = hash_format_valid and declared_hash.lower() == actual_hash
    _record_check(
        checks,
        errors,
        name=f"source.{source_name}.sha256",
        passed=hash_matches,
        message=(
            f"sources.{source_name}.sha256 matches"
            if hash_matches
            else f"sources.{source_name}.sha256 does not match current file"
        ),
    )


def _read_review_relative_source(review_dir: Path, source: Any) -> str | None:
    if not isinstance(source, dict):
        return None
    raw_path = source.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    relative_path = Path(raw_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None
    review_root = review_dir.resolve()
    source_path = (review_root / relative_path).resolve()
    if not source_path.is_relative_to(review_root) or not source_path.is_file():
        return None
    try:
        return source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def validate_review_contract(
    review_dir: Path,
    policy: dict[str, Any],
    *,
    mode: str | None = None,
) -> dict[str, Any]:
    """Validate one final decision without mutating any of its sealed sources."""
    review_dir = Path(review_dir)
    effective_mode = mode if mode in {"shadow", "enforce"} else contract_mode(policy)
    decision_name = str(policy.get("decision_json", "final_decision.json") or "final_decision.json")
    decision_path = review_dir / decision_name
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    input_hashes: dict[str, str] = {}
    decision, read_error = _read_json_object(decision_path)

    if read_error:
        _record_check(
            checks,
            errors,
            name="decision.readable",
            passed=False,
            message=read_error,
        )
    else:
        _record_check(
            checks,
            errors,
            name="decision.readable",
            passed=True,
            message=f"Loaded {decision_name}",
        )

    if decision is not None:
        expected_schema = str(policy.get("schema_version", "1.0") or "1.0")
        _record_check(
            checks,
            errors,
            name="decision.schema_version",
            passed=decision.get("schema_version") == expected_schema,
            message=(
                f"schema_version is {expected_schema}"
                if decision.get("schema_version") == expected_schema
                else f"schema_version must be {expected_schema}"
            ),
        )
        _record_check(
            checks,
            errors,
            name="decision.project_id",
            passed=decision.get("project_id") == review_dir.name,
            message=(
                "project_id matches review directory"
                if decision.get("project_id") == review_dir.name
                else f"project_id must match review directory name {review_dir.name}"
            ),
        )
        _record_check(
            checks,
            errors,
            name="decision.status",
            passed=decision.get("status") == "leader_confirmed",
            message=(
                "status is leader_confirmed"
                if decision.get("status") == "leader_confirmed"
                else "status must be leader_confirmed"
            ),
        )
        confirmed_by = decision.get("confirmed_by")
        _record_check(
            checks,
            errors,
            name="decision.confirmed_by",
            passed=isinstance(confirmed_by, str) and bool(confirmed_by.strip()),
            message=(
                "confirmed_by is present"
                if isinstance(confirmed_by, str) and bool(confirmed_by.strip())
                else "confirmed_by must be a non-empty string"
            ),
        )

        confirmed_at = decision.get("confirmed_at")
        timestamp_valid = False
        if isinstance(confirmed_at, str):
            try:
                parsed = datetime.fromisoformat(confirmed_at.replace("Z", "+00:00"))
                timestamp_valid = parsed.tzinfo is not None and parsed.utcoffset() is not None
            except ValueError:
                timestamp_valid = False
        _record_check(
            checks,
            errors,
            name="decision.confirmed_at",
            passed=timestamp_valid,
            message=(
                "confirmed_at is timezone-aware ISO 8601"
                if timestamp_valid
                else "confirmed_at must be a timezone-aware ISO 8601 timestamp"
            ),
        )

        score = decision.get("score")
        score_scale = decision.get("score_scale")
        score_valid = type(score) is int and 0 <= score <= 100 and score_scale == 100
        _record_check(
            checks,
            errors,
            name="decision.score",
            passed=score_valid,
            message=(
                "score is an integer in 0..100 with score_scale 100"
                if score_valid
                else "score must be an integer in 0..100 and score_scale must be 100"
            ),
        )

        pairs = policy.get("allowed_verdict_release_pairs", DEFAULT_VERDICT_RELEASE_PAIRS)
        if not isinstance(pairs, dict):
            pairs = DEFAULT_VERDICT_RELEASE_PAIRS
        verdict = decision.get("verdict")
        release = decision.get("release_decision")
        pair_valid = isinstance(verdict, str) and pairs.get(verdict) == release
        _record_check(
            checks,
            errors,
            name="decision.verdict_release_pair",
            passed=pair_valid,
            message=(
                "verdict and release_decision are consistent"
                if pair_valid
                else "verdict and release_decision are not an allowed pair"
            ),
        )

        required_severities = policy.get("required_severity_levels", DEFAULT_SEVERITIES)
        if not isinstance(required_severities, list) or not required_severities:
            required_severities = list(DEFAULT_SEVERITIES)
        severity_counts = decision.get("severity_counts")
        severity_valid = isinstance(severity_counts, dict) and set(severity_counts) == set(required_severities)
        if severity_valid:
            severity_valid = all(_is_nonnegative_int(severity_counts[level]) for level in required_severities)
        _record_check(
            checks,
            errors,
            name="decision.severity_counts",
            passed=severity_valid,
            message=(
                "severity_counts contains exactly the required non-negative integer levels"
                if severity_valid
                else "severity_counts must contain exactly the required non-negative integer levels"
            ),
        )

        canonical_count = decision.get("canonical_finding_count")
        count_valid = _is_nonnegative_int(canonical_count)
        if count_valid and severity_valid:
            count_valid = sum(severity_counts.values()) == canonical_count
        _record_check(
            checks,
            errors,
            name="decision.canonical_finding_count",
            passed=count_valid,
            message=(
                "canonical_finding_count equals the severity sum"
                if count_valid
                else "canonical_finding_count must be a non-negative integer equal to the severity sum"
            ),
        )

        expected_unresolved = policy.get("formal_completion_requires_unresolved_count", 0)
        unresolved_count = decision.get("unresolved_count")
        unresolved_valid = type(unresolved_count) is int and unresolved_count == expected_unresolved
        _record_check(
            checks,
            errors,
            name="decision.unresolved_count",
            passed=unresolved_valid,
            message=(
                f"unresolved_count is {expected_unresolved}"
                if unresolved_valid
                else f"unresolved_count must be {expected_unresolved} for formal completion"
            ),
        )

        sources = decision.get("sources")
        sources_object_valid = isinstance(sources, dict)
        _record_check(
            checks,
            errors,
            name="decision.sources",
            passed=sources_object_valid,
            message="sources is an object" if sources_object_valid else "sources must be an object",
        )
        if sources_object_valid:
            for source_name in REQUIRED_SOURCES:
                _validate_source(
                    review_dir,
                    source_name,
                    sources.get(source_name),
                    require_relative=bool(policy.get("source_paths_must_be_review_relative", True)),
                    checks=checks,
                    errors=errors,
                    input_hashes=input_hashes,
                )
            report_text = _read_review_relative_source(
                review_dir,
                sources.get("final_review_report"),
            )
            report_verdict = (
                extract_report_verdict(report_text)
                if report_text is not None
                else None
            )
            report_verdict_matches = (
                report_verdict is not None
                and isinstance(verdict, str)
                and report_verdict == verdict
            )
            if report_verdict is None:
                report_verdict_message = (
                    "final_review_report must state an explicit, parseable verdict "
                    "in the audit conclusion"
                )
            elif not report_verdict_matches:
                report_verdict_message = (
                    f"final_review_report verdict {report_verdict} must match "
                    f"final_decision.verdict {verdict}"
                )
            else:
                report_verdict_message = (
                    "final_review_report verdict matches final_decision.verdict"
                )
            _record_check(
                checks,
                errors,
                name="source.final_review_report.verdict",
                passed=report_verdict_matches,
                message=report_verdict_message,
            )

    contract_valid = not errors
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": utc_offset_now(),
        "mode": effective_mode,
        "contract_valid": contract_valid,
        "would_block": not contract_valid,
        "blocking": effective_mode == "enforce" and not contract_valid,
        "decision_sha256": sha256_file(decision_path) if decision_path.is_file() else "",
        "input_hashes": input_hashes,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "legacy_fallback_used": not contract_valid and effective_mode == "shadow",
    }
    if decision is not None:
        result["decision"] = decision
    return result
