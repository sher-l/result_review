#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Gate audit finalization on recorded subagent supervision evidence."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from audit_runtime import append_event, infer_project_id
from policy_loader import load_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that formal audit work was dispatched, polled, and integrated through bounded subagents."
    )
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    return parser.parse_args()


def _policy(policy: dict) -> dict:
    return policy.get("subagent_supervision_policy", {})


def _summary_path(review_dir: Path, policy: dict) -> Path:
    filename = _policy(policy).get("summary_json", "subagent_supervision_summary.json")
    return review_dir / filename


def _coerce_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_strategy(summary: dict) -> dict:
    strategy = summary.get("subagent_strategy", {})
    return strategy if isinstance(strategy, dict) else {}


def _parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def load_task_events(path: Path) -> tuple[list[dict], list[str]]:
    if not path.exists():
        return [], [f"missing {path.name}"]
    events: list[dict] = []
    errors: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc}")
            continue
        if not isinstance(event, dict):
            errors.append(f"line {line_number}: event must be an object")
            continue
        event["_line_number"] = line_number
        events.append(event)
    return events, errors


def _task_id(item: dict) -> str:
    for field in ("task_id", "slice_id", "subagent", "agent"):
        value = str(item.get(field, "")).strip()
        if value:
            return value
    return ""


def _artifact_value(item: dict) -> str:
    for field in ("artifact_path", "output", "output_artifact"):
        value = str(item.get(field, "")).strip()
        if value:
            return value
    return ""


def _resolve_artifact(review_dir: Path, raw_path: str) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    candidates = [path] if path.is_absolute() else [review_dir / path, review_dir.parents[1] / path, path]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _event_check(check_id: str, passed: bool, message: str, *, blocking: bool) -> dict:
    return {"id": check_id, "passed": passed, "message": message, "blocking": blocking, "source": "event_log"}


def validate_task_events(
    review_dir: Path,
    summary: dict,
    policy: dict,
    events: Iterable[dict] | None = None,
) -> tuple[list[dict], dict]:
    supervision_policy = _policy(policy)
    mode = str(supervision_policy.get("event_validation_mode", "shadow")).lower()
    blocking = mode == "enforce"
    if mode == "off":
        return [], {"mode": mode, "timing_coverage": 0.0, "task_count": 0}

    event_path = review_dir / supervision_policy.get("event_log_jsonl", "review_event_log.jsonl")
    load_errors: list[str] = []
    if events is None:
        loaded_events, load_errors = load_task_events(event_path)
    else:
        loaded_events = [dict(event) for event in events]

    required_types = set(
        supervision_policy.get(
            "required_task_event_types",
            [
                "subagent_dispatched",
                "subagent_polled",
                "subagent_completed",
                "subagent_redispatched",
                "subagent_failed",
            ],
        )
    )
    required_fields = supervision_policy.get("required_task_event_fields", ["task_id", "phase", "agent", "attempt"])
    task_events = [event for event in loaded_events if event.get("event_type") in required_types]
    checks = [
        _event_check(
            "subagent_supervision:event_log_readable",
            not load_errors,
            "; ".join(load_errors) if load_errors else f"Task event log is readable: {event_path.name}.",
            blocking=blocking,
        )
    ]

    missing_field_events = []
    grouped: dict[tuple[str, int], list[dict]] = {}
    for event in task_events:
        missing = [field for field in required_fields if event.get(field) in {None, ""}]
        try:
            attempt = int(event.get("attempt"))
        except (TypeError, ValueError):
            attempt = 0
        if attempt < 1 and "attempt" not in missing:
            missing.append("attempt")
        timestamp = _parse_timestamp(event.get("timestamp"))
        if timestamp is None:
            missing.append("timestamp")
        if missing:
            missing_field_events.append(
                f"line {event.get('_line_number', '?')} {event.get('event_type', '?')}: {','.join(sorted(set(missing)))}"
            )
            continue
        grouped.setdefault((str(event["task_id"]), attempt), []).append({**event, "_timestamp": timestamp})

    checks.append(
        _event_check(
            "subagent_supervision:event_fields",
            not missing_field_events,
            "; ".join(missing_field_events) if missing_field_events else "All task events contain task_id/phase/agent/attempt/timestamp.",
            blocking=blocking,
        )
    )

    max_seconds = _coerce_int(supervision_policy.get("max_subagent_seconds", 1800), 1800)
    completed = _coerce_list(summary.get("completed_subagents"))
    completed_task_ids = {_task_id(item) for item in completed if isinstance(item, dict)}
    valid_timing_tasks = 0
    lifecycle_durations: dict[str, float] = {}
    lifecycle_errors: list[str] = []
    artifact_errors: list[str] = []

    for item in completed:
        if not isinstance(item, dict):
            lifecycle_errors.append("completed_subagents contains a non-object item")
            continue
        task_id = _task_id(item)
        artifact = _artifact_value(item)
        if not task_id:
            lifecycle_errors.append("completed subagent item has no task_id/slice_id")
            continue
        if supervision_policy.get("require_terminal_artifact_exists", True) and _resolve_artifact(review_dir, artifact) is None:
            artifact_errors.append(f"{task_id}: terminal artifact does not exist: {artifact or '[missing path]'}")

        attempts = sorted(attempt for event_task, attempt in grouped if event_task == task_id)
        completed_attempts = []
        for attempt in attempts:
            lifecycle = sorted(grouped[(task_id, attempt)], key=lambda event: (event["_timestamp"], event.get("_line_number", 0)))
            dispatched = [event for event in lifecycle if event["event_type"] == "subagent_dispatched"]
            polls = [event for event in lifecycle if event["event_type"] == "subagent_polled"]
            terminals = [
                event for event in lifecycle if event["event_type"] in {"subagent_completed", "subagent_failed"}
            ]
            if len(dispatched) != 1 or len(terminals) != 1:
                lifecycle_errors.append(
                    f"{task_id} attempt {attempt}: expected exactly one dispatch and one terminal event"
                )
                continue
            terminal = terminals[0]
            start = dispatched[0]["_timestamp"]
            end = terminal["_timestamp"]
            ordered_polls = [poll for poll in polls if start <= poll["_timestamp"] <= end]
            if not polls or len(ordered_polls) != len(polls):
                lifecycle_errors.append(f"{task_id} attempt {attempt}: poll evidence is missing or out of order")
                continue
            duration = (end - start).total_seconds()
            if duration < 0 or duration > max_seconds:
                lifecycle_errors.append(
                    f"{task_id} attempt {attempt}: duration {duration:.0f}s is outside 0..{max_seconds}s"
                )
                continue
            if terminal["event_type"] == "subagent_completed":
                completed_attempts.append((attempt, duration))

        if completed_attempts:
            final_attempt, duration = completed_attempts[-1]
            later_attempts = [attempt for attempt in attempts if attempt > final_attempt]
            if later_attempts:
                lifecycle_errors.append(f"{task_id}: events continue after completed attempt {final_attempt}")
            else:
                valid_timing_tasks += 1
                lifecycle_durations[task_id] = duration
        else:
            lifecycle_errors.append(f"{task_id}: no valid completed attempt lifecycle")

        for previous_attempt, next_attempt in zip(attempts, attempts[1:]):
            previous_events = grouped[(task_id, previous_attempt)]
            next_events = grouped[(task_id, next_attempt)]
            previous_terminal = next(
                (event for event in previous_events if event["event_type"] == "subagent_failed"), None
            )
            redispatch = next(
                (
                    event
                    for event in previous_events + next_events
                    if event["event_type"] == "subagent_redispatched"
                ),
                None,
            )
            next_dispatch = next(
                (event for event in next_events if event["event_type"] == "subagent_dispatched"), None
            )
            if previous_terminal is None or redispatch is None or next_dispatch is None or not (
                previous_terminal["_timestamp"] <= redispatch["_timestamp"] <= next_dispatch["_timestamp"]
            ):
                lifecycle_errors.append(
                    f"{task_id}: redispatch order from attempt {previous_attempt} to {next_attempt} is invalid"
                )

    for (task_id, attempt), task_attempt_events in grouped.items():
        if task_id in completed_task_ids:
            continue
        lifecycle = sorted(
            task_attempt_events, key=lambda event: (event["_timestamp"], event.get("_line_number", 0))
        )
        dispatched = [event for event in lifecycle if event["event_type"] == "subagent_dispatched"]
        polls = [event for event in lifecycle if event["event_type"] == "subagent_polled"]
        terminals = [
            event for event in lifecycle if event["event_type"] in {"subagent_completed", "subagent_failed"}
        ]
        if len(dispatched) != 1 or len(terminals) != 1 or not polls:
            lifecycle_errors.append(
                f"{task_id} attempt {attempt}: incomplete dispatch/poll/terminal lifecycle"
            )
            continue
        start = dispatched[0]["_timestamp"]
        end = terminals[0]["_timestamp"]
        duration = (end - start).total_seconds()
        if duration < 0 or duration > max_seconds or any(
            not start <= poll["_timestamp"] <= end for poll in polls
        ):
            lifecycle_errors.append(
                f"{task_id} attempt {attempt}: event order or duration exceeds {max_seconds}s"
            )

    for item in _coerce_list(summary.get("redispatched_subagents")):
        if not isinstance(item, dict):
            lifecycle_errors.append("redispatched_subagents contains a non-object item")
            continue
        task_id = _task_id(item)
        if not task_id or not any(
            event.get("event_type") == "subagent_redispatched" and event.get("task_id") == task_id
            for event in task_events
        ):
            lifecycle_errors.append(f"{task_id or '[unknown task]'}: redispatch event evidence is missing")

    required_coverage = float(supervision_policy.get("required_timing_coverage", 1.0))
    timing_coverage = valid_timing_tasks / len(completed) if completed else 0.0
    checks.extend(
        [
            _event_check(
                "subagent_supervision:event_lifecycle",
                not lifecycle_errors,
                "; ".join(lifecycle_errors) if lifecycle_errors else "Dispatch, poll, terminal, and redispatch order is valid.",
                blocking=blocking,
            ),
            _event_check(
                "subagent_supervision:terminal_artifacts",
                not artifact_errors,
                "; ".join(artifact_errors) if artifact_errors else "All completed task artifacts exist.",
                blocking=blocking,
            ),
            _event_check(
                "subagent_supervision:timing_coverage",
                timing_coverage >= required_coverage,
                f"Measured timing coverage is {timing_coverage:.1%}; required {required_coverage:.1%}.",
                blocking=blocking,
            ),
        ]
    )
    return checks, {
        "mode": mode,
        "event_log": str(event_path),
        "task_event_count": len(task_events),
        "completed_task_count": len(completed),
        "timing_coverage": timing_coverage,
        "max_subagent_seconds": max_seconds,
        "durations_seconds": lifecycle_durations,
    }


def validate_summary(
    summary: dict,
    policy: dict,
    review_dir: Path | None = None,
    events: Iterable[dict] | None = None,
) -> tuple[bool, list[dict]]:
    supervision_policy = _policy(policy)
    required_fields = supervision_policy.get("required_fields", [])
    min_completed = _coerce_int(supervision_policy.get("minimum_completed_subagents", 3), 3)
    max_minutes = _coerce_int(supervision_policy.get("max_subagent_minutes", 30), 30)

    checks: list[dict] = []
    for field in required_fields:
        checks.append(
            {
                "id": f"subagent_supervision:field:{field}",
                "passed": field in summary,
                "message": f"Required subagent supervision field present: {field}",
            }
        )

    completed = _coerce_list(summary.get("completed_subagents"))
    redispatched = _coerce_list(summary.get("redispatched_subagents"))
    failed_or_skipped = _coerce_list(summary.get("failed_or_skipped_subagents"))
    strategy = _extract_strategy(summary)

    checks.extend(
        [
            {
                "id": "subagent_supervision:passed",
                "passed": summary.get("passed") is True,
                "message": "Subagent supervision summary explicitly passed.",
            },
            {
                "id": "subagent_supervision:leader_role",
                "passed": str(summary.get("leader_role", "")).lower() in {"supervisor", "dispatcher", "monitor"},
                "message": "Leader role is supervisor/dispatcher/monitor rather than primary reviewer.",
            },
            {
                "id": "subagent_supervision:minimum_completed_subagents",
                "passed": len(completed) >= min_completed,
                "message": f"At least {min_completed} completed first-level subagent slices are recorded.",
            },
            {
                "id": "subagent_supervision:no_recursive_subagents",
                "passed": strategy.get("recursive_subagents_allowed") is False
                and summary.get("recursive_subagents_allowed", False) is False,
                "message": "Recursive subagent delegation is disabled for normal audit work.",
            },
            {
                "id": "subagent_supervision:max_minutes",
                "passed": _coerce_int(strategy.get("max_subagent_minutes", summary.get("max_subagent_minutes")), max_minutes + 1) <= max_minutes,
                "message": f"Each subagent slice has a hard stop at or below {max_minutes} minutes.",
            },
            {
                "id": "subagent_supervision:timeout_policy",
                "passed": bool(strategy.get("timeout_policy") or summary.get("timeout_policy")),
                "message": "Timeout/stall handling and redispatch policy are recorded.",
            },
            {
                "id": "subagent_supervision:dispatch_evidence",
                "passed": bool(completed or redispatched or failed_or_skipped),
                "message": "Subagent dispatch/polling outcome evidence is present.",
            },
        ]
    )

    if review_dir is not None:
        event_checks, _ = validate_task_events(review_dir, summary, policy, events=events)
        checks.extend(event_checks)

    failures = [check for check in checks if not check["passed"] and check.get("blocking", True)]
    return not failures, checks


def build_missing_summary(review_dir: Path, policy: dict, reason: str) -> dict:
    supervision_policy = _policy(policy)
    max_minutes = _coerce_int(supervision_policy.get("max_subagent_minutes", 30), 30)
    return {
        "schema_version": "1.0",
        "project_id": infer_project_id(review_dir),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "missing",
        "passed": False,
        "leader_role": "supervisor",
        "subagent_strategy": {
            "subagent_first_required": True,
            "default_initial_concurrency": supervision_policy.get("default_initial_concurrency", "4-6"),
            "max_subagent_minutes": max_minutes,
            "recursive_subagents_allowed": False,
            "timeout_policy": "poll subagents; split and redispatch any slice that stalls, hits remote compact, or exceeds 30 minutes",
        },
        "max_subagent_minutes": max_minutes,
        "recursive_subagents_allowed": False,
        "completed_subagents": [],
        "redispatched_subagents": [],
        "failed_or_skipped_subagents": [{"reason": reason}],
        "unresolved_items": [reason],
        "notification_status": "not_ready",
    }


def main() -> int:
    args = parse_args()
    review_dir = Path(args.review_dir)
    if not review_dir.exists():
        raise FileNotFoundError(f"Review directory does not exist: {review_dir}")

    policy = load_policy()
    supervision_policy = _policy(policy)
    if not supervision_policy.get("enabled", True):
        print("subagent supervision gate disabled by policy")
        return 0

    summary_path = _summary_path(review_dir, policy)
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            summary = build_missing_summary(review_dir, policy, f"invalid JSON in {summary_path.name}: {exc}")
    else:
        summary = build_missing_summary(review_dir, policy, f"missing {summary_path.name}")
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    passed, checks = validate_summary(summary, policy, review_dir=review_dir)
    _, event_diagnostics = validate_task_events(review_dir, summary, policy)
    blocking_errors = [check for check in checks if not check["passed"] and check.get("blocking", True)]
    warnings = [check for check in checks if not check["passed"] and not check.get("blocking", True)]
    gate_result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "review_dir": str(review_dir),
        "summary_path": str(summary_path),
        "passed": passed,
        "checks": checks,
        "errors": blocking_errors,
        "warnings": warnings,
        "event_validation": event_diagnostics,
    }
    gate_path = review_dir / supervision_policy.get("gate_json", "subagent_supervision_gate.json")
    gate_path.write_text(json.dumps(gate_result, ensure_ascii=False, indent=2), encoding="utf-8")

    append_event(
        review_dir,
        "subagent_supervision_gate",
        actor="check_subagent_supervision",
        status="success" if passed else "error",
        details={
            "summary_path": str(summary_path),
            "gate_path": str(gate_path),
            "error_count": len(gate_result["errors"]),
        },
    )

    if passed:
        print(f"subagent supervision gate passed: {summary_path}")
        return 0

    print(f"subagent supervision gate failed: {summary_path}", file=sys.stderr)
    for error in gate_result["errors"]:
        print(f"- {error['id']}: {error['message']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
