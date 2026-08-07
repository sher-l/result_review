#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Verify an externally issued, one-time audit publication attestation.

The audit workspace can verify a signed release decision but must never create
one.  The corresponding private key belongs to an independent release signer;
only its public key is configured here.  This keeps a completed-looking report
from being sufficient authority to notify Enterprise WeChat by itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_ARTIFACTS = {
    "final_decision": "final_decision.json",
    "arbitration_resolution": "agent_results/arbitration/arbitration_resolution.json",
    "visual_audit_result": "visual_audit_result.json",
    "final_review_report": "final_review_report.md",
}


def _metadata_value(metadata: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = str(metadata.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _parse_timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _safe_artifact_path(review_dir: Path, relative_path: object) -> Path | None:
    raw = str(relative_path or "").strip()
    if not raw or Path(raw).is_absolute():
        return None
    candidate = (review_dir / raw).resolve()
    return candidate if _within(review_dir, candidate) else None


def _configured_filename(gate: dict, key: str, default: str) -> str:
    name = str(gate.get(key, default) or default).strip()
    # Only a direct child of review_dir is allowed for authority artifacts.
    return name if Path(name).name == name else ""


def _verify_signature(attestation: Path, signature: Path, public_key: Path) -> tuple[bool, str]:
    openssl = shutil.which("openssl")
    if not openssl:
        return False, "openssl unavailable for release-attestation verification"
    try:
        completed = subprocess.run(
            [openssl, "dgst", "-sha256", "-verify", str(public_key), "-signature", str(signature), str(attestation)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"release-attestation signature verification failed: {exc}"
    if completed.returncode != 0:
        return False, "release-attestation signature is invalid"
    return True, ""


def release_attestation_required(config: dict, provider: str) -> bool:
    gate = config.get("release_attestation_gate", {})
    if not isinstance(gate, dict) or gate.get("enabled", True) is False:
        return False
    providers = gate.get("required_providers", ["wecom"])
    if not isinstance(providers, list):
        providers = ["wecom"]
    return str(provider).strip().lower() in {str(item).strip().lower() for item in providers}


def validate_release_attestation(metadata: dict[str, str], config: dict, *, provider: str) -> tuple[bool, str]:
    """Validate an external release signature and the report artifacts it binds.

    A disabled gate is deliberately supported for isolated legacy test configs;
    the shipped configuration enables it for Enterprise WeChat and fails closed
    until an external public-key path and signed attestation are supplied.
    """
    if not release_attestation_required(config, provider):
        return True, ""

    gate = config.get("release_attestation_gate", {})
    review_text = _metadata_value(metadata, "审核目录", "review_dir")
    project_id = _metadata_value(metadata, "项目号", "项目编号", "project_id")
    if not review_text or not project_id:
        return False, "formal audit release blocked: review directory or project id missing"
    review_dir = Path(review_text)
    if not review_dir.is_dir():
        return False, "formal audit release blocked: review directory missing"

    attestation_name = _configured_filename(gate, "attestation_filename", "release_attestation.json")
    signature_name = _configured_filename(gate, "signature_filename", "release_attestation.sig")
    key_text = str(gate.get("public_key_path", "") or "").strip()
    if not attestation_name or not signature_name or not key_text:
        return False, "formal audit release blocked: independent signer configuration missing"
    public_key = Path(key_text)
    if not public_key.is_absolute() or not public_key.is_file():
        return False, "formal audit release blocked: independent signer public key unavailable"

    attestation_path = review_dir / attestation_name
    signature_path = review_dir / signature_name
    if not attestation_path.is_file() or not signature_path.is_file():
        return False, "formal audit release blocked: signed release attestation missing"
    signature_ok, signature_reason = _verify_signature(attestation_path, signature_path, public_key)
    if not signature_ok:
        return False, f"formal audit release blocked: {signature_reason}"

    try:
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False, "formal audit release blocked: release attestation is unreadable"
    if not isinstance(attestation, dict) or str(attestation.get("schema_version", "")) != "1.0":
        return False, "formal audit release blocked: release attestation schema invalid"
    if str(attestation.get("project_id", "")).strip() != project_id:
        return False, "formal audit release blocked: attestation project id mismatch"
    if not str(attestation.get("nonce", "")).strip():
        return False, "formal audit release blocked: attestation nonce missing"

    issued_at = _parse_timestamp(attestation.get("issued_at"))
    expires_at = _parse_timestamp(attestation.get("expires_at"))
    now = datetime.now(timezone.utc)
    try:
        max_age = int(gate.get("max_age_seconds", 900) or 900)
    except (TypeError, ValueError):
        return False, "formal audit release blocked: attestation age policy invalid"
    if max_age <= 0:
        return False, "formal audit release blocked: attestation age policy invalid"
    if issued_at is None or expires_at is None or issued_at > now or expires_at <= now:
        return False, "formal audit release blocked: attestation is not currently valid"
    if expires_at <= issued_at or (now - issued_at).total_seconds() > max_age:
        return False, "formal audit release blocked: attestation expired or too old"

    artifacts = attestation.get("artifacts")
    if not isinstance(artifacts, dict):
        return False, "formal audit release blocked: attestation artifacts missing"
    required = dict(REQUIRED_ARTIFACTS)
    html_text = _metadata_value(metadata, "HTML", "html_path", "html_report", "报告路径")
    if html_text:
        html_path = Path(html_text)
        if not html_path.is_file() or not _within(review_dir, html_path):
            return False, "formal audit release blocked: HTML report is outside review directory"
        required["html_report"] = str(html_path.resolve().relative_to(review_dir.resolve()))

    for name, expected_relative in required.items():
        record = artifacts.get(name)
        if not isinstance(record, dict):
            return False, f"formal audit release blocked: artifact {name} missing"
        actual_path = _safe_artifact_path(review_dir, record.get("path"))
        if actual_path is None or str(actual_path.relative_to(review_dir.resolve())) != expected_relative:
            return False, f"formal audit release blocked: artifact {name} path mismatch"
        expected_hash = str(record.get("sha256", "")).strip().lower()
        if len(expected_hash) != 64 or any(ch not in "0123456789abcdef" for ch in expected_hash):
            return False, f"formal audit release blocked: artifact {name} hash invalid"
        if not actual_path.is_file() or _sha256(actual_path) != expected_hash:
            return False, f"formal audit release blocked: artifact {name} changed after signing"
    return True, ""


def consume_release_attestation(metadata: dict[str, str], config: dict, *, provider: str) -> tuple[bool, str]:
    """Atomically consume a verified attestation before a network send.

    Delivery ambiguity deliberately consumes the authority as well: callers
    must obtain a newly signed release instead of attempting an automatic
    resend with the same approval.
    """
    if not release_attestation_required(config, provider):
        return True, ""
    valid, reason = validate_release_attestation(metadata, config, provider=provider)
    if not valid:
        return False, reason
    gate = config.get("release_attestation_gate", {})
    review_dir = Path(_metadata_value(metadata, "审核目录", "review_dir"))
    attestation_name = _configured_filename(gate, "attestation_filename", "release_attestation.json")
    attestation_path = review_dir / attestation_name
    attestation_sha256 = _sha256(attestation_path)
    consumption_dir = review_dir / ".release_attestation_consumptions"
    try:
        consumption_dir.mkdir(mode=0o700, exist_ok=True)
    except OSError as exc:
        return False, f"formal audit release blocked: cannot create attestation consumption record: {exc}"
    consumption_path = consumption_dir / f"{attestation_sha256}.json"
    record = {
        "schema_version": "1.0",
        "attestation_sha256": attestation_sha256,
        "consumed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        descriptor = os.open(str(consumption_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False, "formal audit release blocked: release attestation was already consumed"
    except OSError as exc:
        return False, f"formal audit release blocked: cannot record attestation consumption: {exc}"
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
    except OSError as exc:
        return False, f"formal audit release blocked: cannot record attestation consumption: {exc}"
    return True, ""
