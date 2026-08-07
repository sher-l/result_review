#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Finalize an audit in one deterministic command."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from archive_reviewed_project import archive_reviewed_project, precheck_archive_reviewed_project
from audit_contract import (
    atomic_write_json,
    contract_mode,
    sha256_file,
    sha256_json,
    utc_offset_now,
    validate_review_contract,
)
from formal_delivery import build_formal_delivery_manifest
from audit_runtime import append_event, detect_html_path, update_case_manifest, validate_framework_binding
from framework_health_check import assert_framework_healthy
from notification_client import default_config_path, send_notification
from policy_loader import load_policy


SCRIPT_DIR = Path(__file__).resolve().parent


def read_policy_section(policy: dict, name: str) -> dict:
    section = policy.get(name, {})
    return section if isinstance(section, dict) else {}


def has_leader_confirmed_decision(review_dir: Path, policy: dict) -> bool:
    decision_name = str(policy.get("decision_json", "final_decision.json") or "final_decision.json")
    decision_path = review_dir / decision_name
    try:
        loaded = json.loads(decision_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(loaded, dict) and loaded.get("status") == "leader_confirmed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run lint, autofix, backfill, state sync, and HTML publication as one flow."
    )
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    parser.add_argument(
        "--archive-approved",
        action="store_true",
        help="Force auto archive after successful publication.",
    )
    parser.add_argument(
        "--no-auto-archive",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--notification-config",
        default="",
        help=(
            "Deprecated and rejected for formal finalize notifications. "
            "The framework-owned notification configuration is mandatory."
        ),
    )
    parser.add_argument(
        "--notification-channel",
        choices=("default", "primary", "fallback", "feishu", "wecom"),
        default="default",
        help=(
            "Select notification channel. 'fallback'/'feishu' uses the config's "
            "fallback_notification channel directly; 'default'/'primary' keeps current behavior."
        ),
    )
    parser.add_argument(
        "--feishu-only",
        action="store_true",
        help="Shortcut for --notification-channel feishu; no Enterprise WeChat attempt is made.",
    )
    return parser.parse_args()


def run_step(review_dir: Path, script_name: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT_DIR / script_name), str(review_dir)]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )


def should_auto_archive(args: argparse.Namespace, policy: dict) -> bool:
    if args.no_auto_archive:
        raise ValueError("--no-auto-archive is no longer allowed. Finalize must move reviewed projects to raw/已AI审核一次.")
    if args.archive_approved:
        return True
    default_required = policy.get("default_execution", {}).get("must_auto_archive_after_finalize", True)
    publish_required = policy.get("publish_archive_policy", {}).get("auto_archive_after_finalize", True)
    return bool(default_required or publish_required)


def resolve_notification_config_arg(args: argparse.Namespace) -> str:
    config_arg = str(args.notification_config or "").strip()
    if config_arg:
        raise ValueError(
            "--notification-config is not permitted for finalize; "
            "formal delivery uses the framework-owned notification configuration"
        )
    channel = str(args.notification_channel or "default").strip()
    if args.feishu_only:
        channel = "feishu"

    canonical_config = str(default_config_path())
    if channel in {"default", "primary"}:
        return canonical_config
    if channel == "wecom":
        return canonical_config
    if channel in {"fallback", "feishu"}:
        return f"{canonical_config}::fallback_notification"
    return canonical_config


def notification_channel(args: argparse.Namespace) -> str:
    if args.feishu_only:
        return "feishu"
    return str(args.notification_channel or "default").strip() or "default"


def allow_notification_fallback(args: argparse.Namespace) -> bool:
    """Finalize never silently falls back to another provider."""
    return False


def read_manifest_candidates(review_dir: Path) -> list[dict]:
    candidates: list[dict] = []
    for path in (review_dir / "case_manifest.json", review_dir / "ai_execution_manifest.json"):
        if not path.exists():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            candidates.append(loaded)
    return candidates


def resolve_project_display_name(review_dir: Path, archived_to: Path | None = None) -> str:
    if archived_to is not None:
        return archived_to.name
    for manifest in read_manifest_candidates(review_dir):
        for key in ("project_display_name", "project_name", "archived_name"):
            value = str(manifest.get(key, "") or "").strip()
            if value:
                return Path(value).name
        paths = manifest.get("paths", {})
        if isinstance(paths, dict):
            project_dir = str(paths.get("project_dir", "") or "").strip()
            source_archive = str(paths.get("source_archive_path", "") or "").strip()
            if project_dir:
                project_path = Path(project_dir)
                return project_path.parent.name if project_path.parent.name != "待审核" else project_path.name
            if source_archive:
                return Path(source_archive).stem
        project_dir = str(manifest.get("project_dir", "") or "").strip()
        source_archive = str(manifest.get("source_archive_path", "") or "").strip()
        if project_dir:
            project_path = Path(project_dir)
            return project_path.parent.name if project_path.parent.name != "待审核" else project_path.name
        if source_archive:
            return Path(source_archive).stem
    return review_dir.name


def extract_audit_notification_fields(
    review_dir: Path,
    *,
    html_path: Path | None = None,
    archived_to: Path | None = None,
) -> dict[str, str]:
    fields: dict[str, str] = {
        "project_display_name": resolve_project_display_name(review_dir, archived_to=archived_to),
    }
    if html_path is not None and html_path.exists():
        fields["report_file"] = html_path.name

    report_path = review_dir / "final_review_report.md"
    if not report_path.exists():
        return fields

    text = report_path.read_text(encoding="utf-8", errors="ignore")
    score_match = re.search(r"(?:建议评分|评分|合计)[^0-9]{0,20}(\d{1,3})\s*/\s*100", text)
    score = score_match.group(1) if score_match else ""

    conclusion_block = text[:3000]
    verdict = ""
    if re.search(r"不通过|不建议|不合格", conclusion_block):
        verdict = "不通过"
    elif re.search(r"有条件通过", conclusion_block):
        verdict = "有条件通过"
    elif re.search(r"通过|合格", conclusion_block):
        verdict = "通过"
    if verdict and score:
        fields["audit_result"] = f"{verdict}（{score}/100）"
    elif verdict:
        fields["audit_result"] = verdict
    elif score:
        fields["audit_result"] = f"{score}/100"

    stats_match = re.search(
        r"严重度统计[:：]\s*CRITICAL\s*(\d+)[；;，,、\s]+MAJOR\s*(\d+)[；;，,、\s]+WARNING\s*(\d+)",
        text,
    )
    if stats_match:
        c, m, w = stats_match.groups()
        fields["issue_stats"] = f"CRITICAL: {c}；MAJOR: {m}；WARNING: {w}"
    return fields


def extract_contract_notification_fields(decision: dict) -> dict[str, str]:
    """Map a validated internal decision to the stable public notification fields."""
    verdict_map = {
        "合格": "通过",
        "有条件合格": "有条件通过",
        "不合格": "不通过",
    }
    public_verdict = verdict_map[str(decision["verdict"])]
    score = int(decision["score"])
    counts = decision["severity_counts"]
    critical_public = int(counts["FATAL"]) + int(counts["CRITICAL"])
    return {
        "audit_result": f"{public_verdict}（{score}/100）",
        "issue_stats": (
            f"CRITICAL: {critical_public}；"
            f"MAJOR: {int(counts['MAJOR'])}；"
            f"WARNING: {int(counts['WARNING'])}"
        ),
    }


def build_finalize_notification_metadata(
    review_dir: Path,
    *,
    html_path: Path | None = None,
    archived_to: Path | None = None,
    formal_audit: bool = False,
    decision: dict | None = None,
) -> dict[str, str]:
    metadata: dict[str, str] = {
        "project_id": review_dir.name,
        "review_dir": str(review_dir),
        "project_display_name": resolve_project_display_name(review_dir, archived_to=archived_to),
    }
    if html_path is not None and html_path.exists():
        metadata["html_report"] = str(html_path)
        metadata["report_file"] = html_path.name
        metadata["html_report_sha256"] = sha256_file(html_path)
    delivery_manifest = review_dir / "formal_delivery_manifest.json"
    if delivery_manifest.is_file():
        metadata["formal_delivery_manifest"] = str(delivery_manifest)
        metadata["formal_delivery_manifest_sha256"] = sha256_file(delivery_manifest)
    if archived_to is not None:
        metadata["archived_to"] = str(archived_to)
    if formal_audit:
        metadata["formal_audit"] = "true"
    if decision is not None:
        metadata.update(extract_contract_notification_fields(decision))
    else:
        metadata.update(
            extract_audit_notification_fields(
                review_dir,
                html_path=html_path,
                archived_to=archived_to,
            )
        )

    supervision_summary = review_dir / "subagent_supervision_summary.json"
    supervision_gate = review_dir / "subagent_supervision_gate.json"
    if supervision_summary.exists():
        metadata["subagent_supervision_summary"] = str(supervision_summary)
    if supervision_gate.exists():
        metadata["subagent_supervision_gate"] = str(supervision_gate)
    return metadata


def notification_body_sha256(review_dir: Path, summary: str, metadata: dict[str, str]) -> str:
    return sha256_json(
        {
            "task_type": "audit",
            "task_name": f"audit {review_dir.name}",
            "status": "completed",
            "summary": summary,
            "metadata": metadata,
        }
    )


def _read_receipt(receipt_path: Path) -> tuple[dict | None, str | None]:
    if not receipt_path.exists():
        return None, None
    try:
        loaded = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"Unreadable completion notification receipt: {exc}"
    if not isinstance(loaded, dict):
        return None, "Completion notification receipt root must be an object"
    return loaded, None


def _is_known_local_preflight_receipt_error(receipt: dict, review_dir: Path) -> bool:
    """Recognize the v6.9 relative-path preflight defect without widening retries.

    This error was raised while formal-delivery validation enumerated the visual
    closure, before `_send_channel` reaches `send_webhook`.  Only that exact
    local condition may be reclassified from unknown to failed.
    """
    error = str(receipt.get("error") or receipt.get("message") or "")
    expected_asset = str((review_dir.resolve() / "visual_audit_result.json"))
    return (
        error.startswith("primary notification failed: ")
        and expected_asset in error
        and "visual_audit_result.json' is not in the subpath of" in error
    )


def send_completion_notification_once(
    review_dir: Path,
    *,
    summary: str,
    metadata: dict[str, str],
    config_arg: str,
    channel: str,
    decision_sha256: str,
    receipt_path: Path,
    policy: dict,
    allow_fallback: bool = False,
) -> tuple[bool, str]:
    """Send once per sealed decision/body/channel and atomically record the outcome."""
    body_sha256 = notification_body_sha256(review_dir, summary, metadata)
    identity = {
        "decision_sha256": decision_sha256,
        "body_sha256": body_sha256,
        "channel": channel,
    }
    for key in ("html_report_sha256", "formal_delivery_manifest_sha256"):
        value = str(metadata.get(key, "")).strip()
        if value:
            identity[key] = value
    existing, receipt_error = _read_receipt(receipt_path)
    if receipt_error:
        unknown = {
            "schema_version": "1.0",
            "status": "unknown",
            **identity,
            "updated_at": utc_offset_now(),
            "error": receipt_error,
        }
        atomic_write_json(receipt_path, unknown)
        return False, receipt_error

    if existing is not None:
        status = str(existing.get("status", "unknown"))
        allowed_states = policy.get("states", ["pending", "sent", "failed", "unknown"])
        if not isinstance(allowed_states, list) or status not in allowed_states:
            existing["status"] = "unknown"
            existing["updated_at"] = utc_offset_now()
            existing["error"] = f"Unsupported prior receipt status: {status}"
            atomic_write_json(receipt_path, existing)
            return False, "Completion notification receipt status is invalid; automatic resend blocked"
        same_decision = existing.get("decision_sha256") == decision_sha256
        same_identity = all(existing.get(key) == value for key, value in identity.items())
        if status == "sent" and same_identity and policy.get("skip_send_when_matching_receipt_is_sent", True):
            message = "Completion notification skipped: matching sent receipt"
            append_event(
                review_dir,
                "notification_reused",
                actor="finalize_audit",
                status="success",
                details={**identity, "receipt": str(receipt_path)},
            )
            return True, message
        if not same_decision and policy.get("block_when_receipt_decision_hash_differs", True):
            return False, "Completion notification receipt decision hash differs; automatic resend blocked"
        if status == "unknown" and _is_known_local_preflight_receipt_error(existing, review_dir):
            existing["status"] = "failed"
            existing["updated_at"] = utc_offset_now()
            existing["recovery"] = "reclassified_known_local_formal_delivery_preflight_error"
            atomic_write_json(receipt_path, existing)
            append_event(
                review_dir,
                "notification_receipt_reclassified",
                actor="finalize_audit",
                status="success",
                details={"reason": existing["recovery"], "receipt": str(receipt_path)},
            )
            status = "failed"
        if status in {"pending", "unknown"} and policy.get("block_automatic_resend_when_status_unknown", True):
            if status == "pending":
                existing["status"] = "unknown"
                existing["updated_at"] = utc_offset_now()
                existing["error"] = "Previous send stopped while pending; delivery state is unknown"
                atomic_write_json(receipt_path, existing)
            return False, "Completion notification delivery state is unknown; automatic resend blocked"
        if status == "sent":
            return False, "A sent completion receipt exists with different body or channel; automatic resend blocked"

    attempts = int(existing.get("attempt_count", 0)) + 1 if isinstance(existing, dict) else 1
    pending = {
        "schema_version": "1.0",
        "status": "pending",
        **identity,
        "attempt_count": attempts,
        "updated_at": utc_offset_now(),
    }
    try:
        atomic_write_json(receipt_path, pending)
    except OSError as exc:
        return False, f"Cannot persist pending completion receipt; notification not sent: {exc}"
    try:
        ok, message = send_notification(
            task_type="audit",
            task_name=f"audit {review_dir.name}",
            status="completed",
            summary=summary,
            metadata=metadata,
            config_arg=config_arg,
            allow_fallback=allow_fallback,
        )
    except Exception as exc:
        unknown = {
            **pending,
            "status": "unknown",
            "updated_at": utc_offset_now(),
            "error": str(exc),
        }
        atomic_write_json(receipt_path, unknown)
        append_event(
            review_dir,
            "notification_attempted",
            actor="finalize_audit",
            status="error",
            details={"notification_status": "completed", "error": str(exc), **identity},
        )
        return False, str(exc)

    message_text = str(message or "")
    ambiguous_failure = (
        not ok
        and (
            "primary notification failed" in message_text.lower()
            or "fallback notification failed" in message_text.lower()
            or "notification sent via" in message_text.lower()
        )
    )
    terminal = {
        **pending,
        "status": "sent" if ok else ("unknown" if ambiguous_failure else "failed"),
        "updated_at": utc_offset_now(),
        "message": message,
    }
    if ok:
        terminal["sent_at"] = utc_offset_now()
    try:
        atomic_write_json(receipt_path, terminal)
    except OSError as exc:
        return False, f"Notification returned but terminal receipt could not be persisted: {exc}"
    append_event(
        review_dir,
        "notification_attempted",
        actor="finalize_audit",
        status="success" if ok else "error",
        details={"message": message, "notification_status": "completed", **identity},
    )
    if message:
        print(message)
    return ok, message


def send_finalize_notification(
    review_dir: Path,
    *,
    status: str,
    summary: str,
    config_arg: str = "",
    html_path: Path | None = None,
    archived_to: Path | None = None,
    allow_fallback: bool = True,
    formal_audit: bool = False,
) -> tuple[bool, str]:
    metadata = build_finalize_notification_metadata(
        review_dir,
        html_path=html_path,
        archived_to=archived_to,
        formal_audit=formal_audit,
    )

    try:
        ok, message = send_notification(
            task_type="audit",
            task_name=f"audit {review_dir.name}",
            status=status,
            summary=summary,
            metadata=metadata,
            config_arg=config_arg,
            allow_fallback=allow_fallback,
        )
        append_event(
            review_dir,
            "notification_attempted",
            actor="finalize_audit",
            status="success" if ok or "skipped" in message else "error",
            details={"message": message, "notification_status": status},
        )
        if message:
            print(message)
        return ok, message
    except Exception as exc:
        append_event(
            review_dir,
            "notification_attempted",
            actor="finalize_audit",
            status="error",
            details={"notification_status": status, "error": str(exc)},
        )
        print(f"Notification error: {exc}", file=sys.stderr)
        return False, str(exc)


def finalize_failed(
    review_dir: Path,
    *,
    summary: str,
    details: dict,
    notification_config_arg: str = "",
    failed_script: str | None = None,
    returncode: int = 1,
    html_path: Path | None = None,
    archived_to: Path | None = None,
    notify_failure: bool = True,
    allow_fallback: bool = True,
) -> int:
    update_case_manifest(
        review_dir,
        {
            "publish_status": "failed",
            "archive_approved": False,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    if notify_failure:
        send_finalize_notification(
            review_dir,
            status="failed",
            summary=summary,
            config_arg=notification_config_arg,
            html_path=html_path,
            archived_to=archived_to,
            allow_fallback=allow_fallback,
        )
    append_event(
        review_dir,
        "finalize_failed",
        actor="finalize_audit",
        status="error",
        details=details | ({"failed_script": failed_script} if failed_script else {}),
    )
    return returncode


def finalize_archive_failed(
    review_dir: Path,
    *,
    summary: str,
    details: dict,
    failed_script: str | None = None,
    returncode: int = 1,
) -> int:
    """Record a local post-notification archive/sync failure without external sends."""
    update_case_manifest(
        review_dir,
        {
            "publish_status": "success",
            "archive_status": "failed",
            "archive_approved": False,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    append_event(
        review_dir,
        "finalize_failed",
        actor="finalize_audit",
        status="error",
        details=details | {
            "summary": summary,
            "external_notification_suppressed": True,
        } | ({"failed_script": failed_script} if failed_script else {}),
    )
    return returncode


def run_required_step(review_dir: Path, script_name: str, outputs: list[str]) -> subprocess.CompletedProcess[str]:
    completed = run_step(review_dir, script_name)
    if completed.stdout.strip():
        print(completed.stdout.strip())
    if completed.returncode == 0:
        outputs.append(script_name)
        return completed
    raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"{script_name} failed")


def run_lint_step(review_dir: Path, outputs: list[str], label: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    lint_path = review_dir / "final_report_lint.json"
    if lint_path.exists():
        lint_path.unlink()

    completed = run_step(review_dir, "final_report_linter.py")
    if completed.stdout.strip():
        print(completed.stdout.strip())
    outputs.append(f"final_report_linter.py:{label}")

    if not lint_path.exists():
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "final_report_lint.json missing after lint run")

    lint_data = json.loads(lint_path.read_text(encoding="utf-8"))
    return completed, lint_data


def validate_and_write_contract(review_dir: Path, policy: dict) -> dict:
    result = validate_review_contract(review_dir, policy)
    validation_name = str(policy.get("validation_json", "audit_contract_validation.json") or "audit_contract_validation.json")
    atomic_write_json(review_dir / validation_name, result)
    return result


def publication_state_ready(review_dir: Path) -> tuple[bool, list[str]]:
    """Check publication prerequisites after the HTML step but before notification.

    ``audit_state.all_completed`` intentionally remains false until publication
    succeeds, so it cannot be used as this pre-publication gate.  Instead,
    require every phase except archival to be complete and require a valid
    visual closure explicitly.
    """
    state_path = review_dir / "audit_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False, ["audit_state.json is missing after state synchronization"]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return False, [f"audit_state.json is unreadable: {exc}"]
    if not isinstance(state, dict):
        return False, ["audit_state.json root must be an object"]

    phases = state.get("phases")
    if not isinstance(phases, list):
        return False, ["audit_state.json.phases must be a list"]

    errors: list[str] = []
    visual_phase: dict | None = None
    no_op_remediation_phases = {
        "autofix_plan_ready",
        "autofix_applied",
        "section_backfill_ready",
        "section_backfill_applied",
    }
    lint_passed = state.get("lint_passed") is True
    for phase in phases:
        if not isinstance(phase, dict):
            errors.append("audit_state.json contains an invalid phase entry")
            continue
        phase_id = str(phase.get("id", "") or "")
        if phase_id == "archive_ready":
            continue
        if lint_passed and phase_id in no_op_remediation_phases:
            continue
        if phase.get("status") != "completed":
            errors.append(f"publication prerequisite is incomplete: {phase_id or 'unnamed phase'}")
        if phase_id == "visual_audit_ready":
            visual_phase = phase

    if visual_phase is None:
        errors.append("audit_state.json is missing visual_audit_ready")
    else:
        closure = visual_phase.get("closure")
        if not isinstance(closure, dict) or closure.get("closure_passed") is not True:
            errors.append("visual_audit_ready closure_passed must be true before publication")

    return not errors, errors


def main() -> int:
    args = parse_args()
    review_dir = Path(args.review_dir)
    if not review_dir.exists():
        raise FileNotFoundError(f"Review directory does not exist: {review_dir}")
    try:
        notification_config_arg = resolve_notification_config_arg(args)
    except ValueError as exc:
        print(f"Finalize blocked before mutation: {exc}", file=sys.stderr)
        return 1
    try:
        assert_framework_healthy()
        binding_errors = validate_framework_binding(
            review_dir,
            require_ai_execution_manifest=True,
        )
    except RuntimeError as exc:
        print(f"Finalize blocked before mutation: {exc}", file=sys.stderr)
        return 1
    if binding_errors:
        print(
            "Finalize blocked before mutation: policy binding gate failed: " + "; ".join(binding_errors),
            file=sys.stderr,
        )
        return 1
    policy = load_policy()
    audit_contract_policy = read_policy_section(policy, "audit_contract_policy")
    idempotency_policy = read_policy_section(policy, "notification_idempotency_policy")
    sealed_mode = contract_mode(audit_contract_policy)
    confirmed_decision_present = has_leader_confirmed_decision(review_dir, audit_contract_policy)
    pre_notification_local_only = sealed_mode == "enforce" or bool(
        idempotency_policy.get("pre_notification_gate_failures_are_local_only", False)
    )
    auto_archive = should_auto_archive(args, policy)
    notification_allow_fallback = allow_notification_fallback(args)
    if not auto_archive:
        raise RuntimeError("Finalize policy requires automatic archive; refusing to complete without moving the reviewed project.")
    append_event(
        review_dir,
        "finalize_started",
        actor="finalize_audit",
        details={
            "auto_archive": auto_archive,
            "archive_required": True,
            "archive_approved_flag": args.archive_approved,
            "notification_channel": "feishu" if args.feishu_only else args.notification_channel,
            "notification_config_arg": notification_config_arg,
            "notification_allow_fallback": notification_allow_fallback,
            "audit_contract_mode": sealed_mode,
        },
    )
    outputs = []
    contract_result: dict = {}
    decision: dict | None = None
    try:
        run_required_step(review_dir, "check_subagent_supervision.py", outputs)
        run_required_step(review_dir, "validate_professional_contracts.py", outputs)

        lint_completed, lint_data = run_lint_step(review_dir, outputs, "initial")
        lint_passed = bool(lint_data.get("passed", False))

        if not lint_passed and sealed_mode != "enforce" and not confirmed_decision_present:
            run_required_step(review_dir, "generate_lint_autofix_plan.py", outputs)
            run_required_step(review_dir, "apply_lint_autofix_plan.py", outputs)

            lint_completed, lint_data = run_lint_step(review_dir, outputs, "post_autofix")
            lint_passed = bool(lint_data.get("passed", False))

            if not lint_passed:
                run_required_step(review_dir, "generate_required_section_backfill.py", outputs)
                run_required_step(review_dir, "apply_required_section_backfill.py", outputs)

                lint_completed, lint_data = run_lint_step(review_dir, outputs, "final")
                lint_passed = bool(lint_data.get("passed", False))

        if not lint_passed:
            return finalize_failed(
                review_dir,
                summary=(
                    "Finalize failed: sealed final report lint failed; run prepare_audit_finalize.py before confirmation"
                    if sealed_mode == "enforce" or confirmed_decision_present
                    else "Finalize failed: final report lint still failing after autofix/backfill"
                ),
                details={
                    "failed_stage": "final_lint_gate",
                    "error_count": lint_data.get("error_count", 0),
                    "warning_count": lint_data.get("warning_count", 0),
                    "sealed_finalize": sealed_mode == "enforce" or confirmed_decision_present,
                },
                notification_config_arg=notification_config_arg,
                allow_fallback=notification_allow_fallback,
                failed_script="final_report_linter.py",
                returncode=lint_completed.returncode or 1,
                notify_failure=not pre_notification_local_only,
            )

        contract_result = validate_and_write_contract(review_dir, audit_contract_policy)
        validation_name = str(
            audit_contract_policy.get("validation_json", "audit_contract_validation.json")
            or "audit_contract_validation.json"
        )
        outputs.append(validation_name)
        if contract_result.get("blocking", False):
            return finalize_failed(
                review_dir,
                summary="Finalize failed: sealed audit decision contract is invalid",
                details={
                    "failed_stage": "audit_contract_gate",
                    "errors": contract_result.get("errors", []),
                    "validation": str(review_dir / validation_name),
                },
                notification_config_arg=notification_config_arg,
                allow_fallback=notification_allow_fallback,
                failed_script="validate_audit_contract.py",
                notify_failure=False,
            )
        if contract_result.get("contract_valid", False):
            loaded_decision = contract_result.get("decision")
            if isinstance(loaded_decision, dict):
                decision = loaded_decision

        run_required_step(review_dir, "sync_audit_state.py", outputs)
        run_required_step(review_dir, "ensure_review_html.py", outputs)
        run_required_step(review_dir, "sync_audit_state.py", outputs)

        publication_ready, publication_errors = publication_state_ready(review_dir)
        if not publication_ready:
            return finalize_failed(
                review_dir,
                summary="Finalize blocked: audit prerequisites are incomplete",
                details={
                    "failed_stage": "publication_readiness_gate",
                    "errors": publication_errors,
                },
                notification_config_arg=notification_config_arg,
                allow_fallback=notification_allow_fallback,
                failed_script="sync_audit_state.py",
                notify_failure=False,
            )

        if decision is not None:
            contract_result = validate_and_write_contract(review_dir, audit_contract_policy)
            if not contract_result.get("contract_valid", False):
                return finalize_failed(
                    review_dir,
                    summary="Finalize failed: sealed sources changed during publication",
                    details={
                        "failed_stage": "sealed_source_recheck",
                        "errors": contract_result.get("errors", []),
                    },
                    notification_config_arg=notification_config_arg,
                    allow_fallback=notification_allow_fallback,
                    failed_script="validate_audit_contract.py",
                    notify_failure=False,
                )
    except RuntimeError as exc:
        message = str(exc)
        if message:
            print(message, file=sys.stderr)
        return finalize_failed(
            review_dir,
            summary=f"Finalize failed: {message}",
            details={"error": message},
            notification_config_arg=notification_config_arg,
            allow_fallback=notification_allow_fallback,
            notify_failure=not pre_notification_local_only,
        )

    html_path = detect_html_path(review_dir)
    publish_status = "success" if html_path.exists() else "failed"
    update_case_manifest(
        review_dir,
        {
            "publish_status": publish_status,
            "archive_approved": False,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )

    if publish_status != "success":
        return finalize_failed(
            review_dir,
            summary="Finalize failed: HTML report missing after publication step",
            details={"failed_stage": "html_publish", "html_exists": False},
            notification_config_arg=notification_config_arg,
            allow_fallback=notification_allow_fallback,
            notify_failure=not pre_notification_local_only,
        )

    try:
        delivery_manifest_path, _ = build_formal_delivery_manifest(
            review_dir,
            html_path,
            decision_sha256=str(contract_result.get("decision_sha256", "")),
            policy=policy,
        )
        outputs.append(delivery_manifest_path.name)
        append_event(
            review_dir,
            "formal_delivery_manifest_created",
            actor="finalize_audit",
            outputs=[str(delivery_manifest_path)],
        )
    except (OSError, UnicodeError, ValueError) as exc:
        return finalize_failed(
            review_dir,
            summary=f"Finalize blocked: formal delivery consistency gate failed: {exc}",
            html_path=html_path,
            details={"failed_stage": "formal_delivery_consistency_gate", "error": str(exc)},
            notification_config_arg=notification_config_arg,
            allow_fallback=notification_allow_fallback,
            failed_script="formal_delivery_manifest",
            notify_failure=False,
        )

    archive_precheck_path: Path | None = None
    if auto_archive:
        try:
            archive_precheck_path = precheck_archive_reviewed_project(review_dir)
            append_event(
                review_dir,
                "archive_precheck_passed",
                actor="finalize_audit",
                outputs=[str(archive_precheck_path)],
            )
        except Exception as exc:
            return finalize_failed(
                review_dir,
                summary=f"Finalize archive precheck failed: {exc}",
                html_path=html_path if html_path.exists() else None,
                details={"failed_stage": "archive_precheck", "error": str(exc)},
                notification_config_arg=notification_config_arg,
                notify_failure=False,
                allow_fallback=notification_allow_fallback,
            )

    notification_summary = "Audit finalize completed with HTML published; archive pending."
    if decision is not None:
        metadata = build_finalize_notification_metadata(
            review_dir,
            html_path=html_path if html_path.exists() else None,
            formal_audit=True,
            decision=decision,
        )
        receipt_name = str(
            idempotency_policy.get("receipt_json", "completion_notification_receipt.json")
            or "completion_notification_receipt.json"
        )
        receipt_path = review_dir / receipt_name
        notification_ok, notification_message = send_completion_notification_once(
            review_dir,
            summary=notification_summary,
            metadata=metadata,
            config_arg=notification_config_arg,
            channel=notification_channel(args),
            decision_sha256=str(contract_result.get("decision_sha256", "")),
            receipt_path=receipt_path,
            policy=idempotency_policy,
            allow_fallback=notification_allow_fallback,
        )
        outputs.append(receipt_name)
    else:
        # Unsealed/shadow audits still need the same durable, idempotent
        # completion receipt. An empty decision hash explicitly records that
        # no final_decision.json was available; body/channel identity still
        # prevents a second send for the same completed notification.
        metadata = build_finalize_notification_metadata(
            review_dir,
            html_path=html_path if html_path.exists() else None,
            formal_audit=True,
        )
        receipt_name = str(
            idempotency_policy.get("receipt_json", "completion_notification_receipt.json")
            or "completion_notification_receipt.json"
        )
        receipt_path = review_dir / receipt_name
        notification_ok, notification_message = send_completion_notification_once(
            review_dir,
            summary=notification_summary,
            metadata=metadata,
            config_arg=notification_config_arg,
            channel=notification_channel(args),
            decision_sha256="",
            receipt_path=receipt_path,
            policy=idempotency_policy,
            allow_fallback=notification_allow_fallback,
        )
        outputs.append(receipt_name)
    if not notification_ok:
        receipt_status = "failed"
        if decision is not None:
            receipt, _ = _read_receipt(receipt_path)
            if isinstance(receipt, dict):
                receipt_status = str(receipt.get("status", "failed"))
        update_case_manifest(
            review_dir,
            {
                "notification_status": receipt_status,
                "notification_channel": notification_channel(args),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        append_event(
            review_dir,
            "finalize_failed",
            actor="finalize_audit",
            status="error",
            details={
                "failed_stage": "completion_notification",
                "message": notification_message,
                "notification_channel": notification_channel(args),
            },
        )
        return 1

    update_case_manifest(
        review_dir,
        {
            "notification_status": "sent",
            "notification_channel": notification_channel(args),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )

    if decision is not None and idempotency_policy.get("archive_requires_sent_receipt", True):
        receipt, receipt_error = _read_receipt(receipt_path)
        if receipt_error or not isinstance(receipt, dict) or receipt.get("status") != "sent":
            return finalize_archive_failed(
                review_dir,
                summary="Finalize archive blocked: completion notification has no sent receipt",
                details={
                    "failed_stage": "notification_receipt_gate",
                    "receipt": str(receipt_path),
                    "receipt_error": receipt_error or "",
                    "receipt_status": receipt.get("status", "missing") if isinstance(receipt, dict) else "missing",
                },
            )

    archived_to: Path | None = None
    if publish_status == "success" and auto_archive:
        try:
            archived_to = archive_reviewed_project(review_dir, approve=True)
            print(f"Archived reviewed project: {archived_to}")
            outputs.extend(["archive_reviewed_project.py", str(archived_to)])
        except Exception as exc:
            update_case_manifest(
                review_dir,
                {
                    "archive_approved": False,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            sync_completed = run_step(review_dir, "sync_audit_state.py")
            if sync_completed.stdout.strip():
                print(sync_completed.stdout.strip())
            if sync_completed.stderr.strip():
                print(sync_completed.stderr.strip(), file=sys.stderr)
            return finalize_archive_failed(
                review_dir,
                summary=f"Finalize auto archive failed: {exc}",
                details={"failed_stage": "auto_archive", "error": str(exc)},
            )

        sync_completed = run_step(review_dir, "sync_audit_state.py")
        if sync_completed.stdout.strip():
            print(sync_completed.stdout.strip())
        if sync_completed.returncode != 0:
            if sync_completed.stderr.strip():
                print(sync_completed.stderr.strip(), file=sys.stderr)
            return finalize_archive_failed(
                review_dir,
                summary="Finalize post-archive state sync failed",
                details={"failed_stage": "post_archive_sync"},
                failed_script="sync_audit_state.py",
                returncode=sync_completed.returncode,
            )

    append_event(
        review_dir,
        "finalize_completed",
        actor="finalize_audit",
        outputs=outputs + ([str(html_path)] if html_path.exists() else []),
        details={
            "auto_archive": auto_archive,
            "archived": archived_to is not None,
            "archive_precheck_path": str(archive_precheck_path) if archive_precheck_path is not None else "",
            "html_exists": html_path.exists(),
            "notification_channel": "feishu" if args.feishu_only else args.notification_channel,
            "notification_config_arg": notification_config_arg,
            "notification_sent_before_archive": True,
            "notification_allow_fallback": notification_allow_fallback,
        },
    )
    print(f"Finalize completed: {review_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
