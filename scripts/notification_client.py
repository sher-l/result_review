#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Shared notification client for task completion alerts.

The primary channel remains a webhook text notification.  When configured,
the client can also upload a local HTML report as a file.  Enterprise WeChat
can send files directly through the group robot webhook key; Feishu file
sending uses the app OpenAPI.  A fallback channel can be configured so the
framework tries Enterprise WeChat first and falls back to Feishu on failure.

Enterprise WeChat is guarded as a formal-audit-only channel.  Without an
explicit formal audit marker (or the finalize workflow's archived completion
metadata), the WeCom channel is skipped before any network request is made.
"""

from __future__ import annotations

import json
import os
import socket
import base64
import hashlib
import hmac
import mimetypes
import time
from urllib.parse import parse_qs, quote_plus, urlencode, urlparse
from datetime import datetime
from pathlib import Path
from urllib import request

from release_attestation import consume_release_attestation, validate_release_attestation
from formal_delivery import (
    resolve_html_report_metadata_path,
    validate_formal_delivery_manifest,
)
from policy_loader import load_policy


TEST_NETWORK_DENY_ENV = "AUDIT_FRAMEWORK_DENY_NETWORK"


def _open_url(req: request.Request, *, timeout: int):
    """Open a notification request unless the test harness denies all egress."""
    if os.environ.get(TEST_NETWORK_DENY_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
        raise RuntimeError("outbound notification network disabled by test harness")
    return request.urlopen(req, timeout=timeout)


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "notification_config.json"


def _split_config_arg(config_arg: str = "") -> tuple[Path, str]:
    raw = str(config_arg or "").strip()
    if not raw:
        return default_config_path(), ""
    if "::" not in raw:
        return Path(raw), ""
    path_text, selector = raw.split("::", 1)
    return Path(path_text) if path_text.strip() else default_config_path(), selector.strip()


def _selected_channel_config(config: dict, selector: str = "") -> dict:
    if not selector or selector in {"default", "primary"}:
        return config
    raw = config.get(selector, {})
    if not isinstance(raw, dict):
        return {}

    merged = _merged_channel_config(config, raw)
    merged["enabled"] = True

    # A selected channel is explicit: do not silently fall back to another
    # provider, and never keep WeCom file sending enabled for non-WeCom sends.
    if selector == "fallback_notification":
        merged["fallback_notification"] = {"enabled": False}
    if str(merged.get("provider", "")).strip() != "wecom" and isinstance(merged.get("wecom_file"), dict):
        wecom_file = dict(merged["wecom_file"])
        wecom_file["enabled"] = False
        merged["wecom_file"] = wecom_file
    return merged


def load_config(config_arg: str = "") -> dict:
    config_path, selector = _split_config_arg(config_arg)
    if not config_path.exists():
        return {}
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return _selected_channel_config(config, selector)


def notifications_enabled(config: dict, task_type: str = "") -> tuple[bool, str]:
    if not config:
        return False, "config missing"
    if not config.get("enabled", False):
        return False, "disabled"
    enabled_task_types = config.get("enabled_task_types", [])
    if enabled_task_types and task_type and task_type not in enabled_task_types:
        return False, f"task_type {task_type} not enabled"
    has_webhook_url = bool(str(config.get("webhook_url", "")).strip())
    has_wecom_key = bool(str(config.get("webhook_key", "")).strip())
    if not has_webhook_url and not has_wecom_key:
        return False, "webhook_url missing"
    return True, ""


def _merged_channel_config(config: dict, override: dict) -> dict:
    merged = dict(config)
    merged.update(override)
    for key in ("extra_fields",):
        if isinstance(config.get(key), dict) or isinstance(override.get(key), dict):
            value = {}
            value.update(config.get(key, {}) if isinstance(config.get(key), dict) else {})
            value.update(override.get(key, {}) if isinstance(override.get(key), dict) else {})
            merged[key] = value
    return merged


def fallback_config(config: dict) -> dict:
    raw = config.get("fallback_notification", {})
    if not isinstance(raw, dict) or not raw.get("enabled", False):
        return {}
    merged = _merged_channel_config(config, raw)
    merged["enabled"] = True
    return merged


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "正式", "formal", "formal_audit"}


def _wecom_formal_audit_allowed(task_type: str, status: str, metadata: dict[str, str], config: dict) -> tuple[bool, str]:
    gate = config.get("wecom_formal_audit_gate", {})
    if not isinstance(gate, dict):
        gate = {}
    if _is_completed_audit(task_type, status):
        delivery_ok, delivery_reason = validate_formal_delivery_manifest(metadata, config)
        if not delivery_ok:
            return False, f"formal delivery blocked: {delivery_reason}"
    if gate.get("enabled", True) is False:
        return validate_release_attestation(metadata, config, provider="wecom")
    if not _is_completed_audit(task_type, status):
        return False, "wecom skipped: formal audit gate not satisfied"

    marker_keys = gate.get("marker_keys", ["formal_audit", "正式审核", "audit_formal_run"])
    for key in marker_keys:
        if _truthy(metadata.get(str(key), "")):
            return validate_release_attestation(metadata, config, provider="wecom")

    # The deterministic finalize workflow supplies archived completion metadata
    # only after a real review directory is finalized.  This keeps ordinary
    # framework tests and ad-hoc notification checks off WeCom while preserving
    # the formal audit completion path.
    if gate.get("allow_archived_finalize_metadata", True):
        has_html = bool(_find_html_report_path(metadata))
        has_archive = bool(_first_metadata_value(metadata, ("archived_to", "归档位置")))
        if has_html and has_archive:
            return validate_release_attestation(metadata, config, provider="wecom")
    return False, "wecom skipped: formal audit gate not satisfied"


AUDIT_COMPLETED_BODY_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("项目号", ("项目号", "项目编号", "project_id", "ProjectID")),
    ("审核文件", ("审核文件", "audit_file", "project_display_name", "project_name", "archived_name")),
    ("报告文件", ("报告文件", "report_file", "html_report_file")),
    ("审核结果", ("审核结果", "audit_result")),
)
AUDIT_COMPLETED_STATS_ALIASES: tuple[str, ...] = ("问题统计", "issue_stats", "problem_stats")
AUDIT_COMPLETED_COUNT_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("CRITICAL", ("critical", "CRITICAL", "critical_count", "critical_issues")),
    ("MAJOR", ("major", "MAJOR", "major_count", "major_issues")),
    ("WARNING", ("warning", "WARNING", "warning_count", "warning_issues")),
)


def _is_completed_audit(task_type: str, status: str) -> bool:
    return str(task_type).strip().lower() == "audit" and str(status).strip().lower() == "completed"


def _mandatory_formal_delivery_config() -> dict:
    """Return the policy-owned manifest settings for every completed audit.

    Notification transport configuration is intentionally not authoritative for
    formal delivery.  In particular, a caller-provided config must not disable
    the manifest gate before selecting a different provider.
    """
    gate: dict[str, object] = {"enabled": True}
    try:
        policy = load_policy()
        delivery_policy = policy.get("formal_delivery_policy", {})
        if isinstance(delivery_policy, dict):
            filename = str(delivery_policy.get("manifest_filename", "") or "").strip()
            if filename and Path(filename).name == filename:
                gate["manifest_filename"] = filename
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        # The validator has a safe built-in filename default.  A policy read
        # failure must never turn the mandatory gate into an allow decision.
        pass
    return {"formal_delivery_gate": gate}


def validate_completed_audit_delivery(metadata: dict[str, str]) -> tuple[bool, str]:
    """Require a current formal-delivery manifest independently of provider."""
    ok, reason = validate_formal_delivery_manifest(metadata, _mandatory_formal_delivery_config())
    if ok:
        return True, ""
    return False, f"formal delivery blocked: {reason}"


def missing_audit_completed_fields(metadata: dict[str, str]) -> list[str]:
    """Return required formal-audit body fields that are absent from metadata."""
    missing = [
        display_name
        for display_name, aliases in AUDIT_COMPLETED_BODY_FIELDS
        if not _first_metadata_value(metadata, aliases)
    ]
    if not _format_issue_stats_from_metadata(metadata):
        missing.append("CRITICAL/MAJOR/WARNING")
    return missing


def validate_notification_request(task_type: str, status: str, metadata: dict[str, str]) -> tuple[bool, str]:
    """Fail closed before any network send if the formal audit body would be incomplete."""
    if not _is_completed_audit(task_type, status):
        return True, ""
    missing = missing_audit_completed_fields(metadata)
    if missing:
        return False, (
            "audit completed notification blocked: missing required formal body fields "
            + ", ".join(missing)
        )
    return True, ""


def build_title(task_name: str, status: str, config: dict) -> str:
    prefix = str(config.get("default_title_prefix", "任务通知")).strip()
    if prefix:
        return f"[{prefix}] {task_name} - {status}"
    return f"{task_name} - {status}"


def _audit_verdict_label(raw_result: str) -> str:
    """Return the concise public verdict label for formal audit notices."""
    text = str(raw_result or "").strip()
    if not text:
        return ""
    for sep in ("（", "(", "；", ";", "，", ","):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
    return text


def _format_issue_stats_for_audit_result(raw_stats: str) -> str:
    """Normalize issue counts for the public audit-result suffix.

    Public notification text uses framework severity labels and compact counts:
    ``CRITICAL: 4；MAJOR: 9；WARNING: 3``.  Internal P0/P1/P2 labels and
    Chinese count suffixes are accepted as input but are not exposed.
    """
    text = str(raw_stats or "").strip()
    if not text:
        return ""
    level_map = {
        "P0": "CRITICAL",
        "P1": "MAJOR",
        "P2": "WARNING",
        "FATAL": "CRITICAL",
        "CRITICAL": "CRITICAL",
        "MAJOR": "MAJOR",
        "WARNING": "WARNING",
        "WARN": "WARNING",
        "INFO": "INFO",
    }
    parts = [part.strip() for part in text.replace(";", "；").split("；") if part.strip()]
    formatted: list[str] = []
    for part in parts:
        cleaned = part.replace("项", "").strip()
        normalized = cleaned.replace("：", ":")
        if ":" in normalized:
            label, count = normalized.split(":", 1)
        else:
            tokens = normalized.split()
            if len(tokens) >= 2:
                label, count = tokens[0], " ".join(tokens[1:])
            else:
                formatted.append(cleaned)
                continue
        label = level_map.get(label.strip().upper(), label.strip().upper())
        count = count.strip()
        if count:
            formatted.append(f"{label}: {count}")
    return "；".join(formatted)


def _format_issue_stats_from_metadata(metadata: dict[str, str]) -> str:
    raw_stats = _first_metadata_value(metadata, AUDIT_COMPLETED_STATS_ALIASES)
    stats = _format_issue_stats_for_audit_result(raw_stats)
    if stats:
        return stats

    counts: list[str] = []
    for label, aliases in AUDIT_COMPLETED_COUNT_FIELDS:
        count = _first_metadata_value(metadata, aliases).strip()
        if not count:
            return ""
        counts.append(f"{label}: {count.replace('项', '').strip()}")
    return "；".join(counts)


def _format_audit_result_line(raw_result: str, stats: str) -> str:
    verdict = _audit_verdict_label(raw_result)
    if verdict and stats:
        return f"审核结果: {verdict}（{stats}）"
    if verdict:
        return f"审核结果: {verdict}"
    if stats:
        return f"审核结果: {stats}"
    return ""


def build_body(task_type: str, task_name: str, status: str, summary: str,
               metadata: dict[str, str], config: dict) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if _is_completed_audit(task_type, status):
        lines = [
            f"状态: {status}",
            f"时间: {timestamp}",
        ]
        project_id = _first_metadata_value(metadata, AUDIT_COMPLETED_BODY_FIELDS[0][1])
        audit_file = _first_metadata_value(metadata, AUDIT_COMPLETED_BODY_FIELDS[1][1])
        report_file = _first_metadata_value(metadata, AUDIT_COMPLETED_BODY_FIELDS[2][1])
        audit_result = _first_metadata_value(metadata, AUDIT_COMPLETED_BODY_FIELDS[3][1])
        issue_stats = _format_issue_stats_from_metadata(metadata)
        if project_id:
            lines.append(f"项目号: {project_id}")
        if audit_file:
            lines.append(f"审核文件: {audit_file}")
        if report_file:
            lines.append(f"报告文件: {report_file}")
        result_line = _format_audit_result_line(audit_result, issue_stats)
        if result_line:
            lines.append(result_line)
        return "\n".join(lines)

    lines = [
        f"任务类型: {task_type or 'generic'}",
        f"任务名称: {task_name}",
        f"状态: {status}",
        f"时间: {timestamp}",
    ]
    if summary:
        lines.append(f"摘要: {summary}")
    merged_metadata = {}
    merged_metadata.update(config.get("extra_fields", {}))
    merged_metadata.update(metadata)
    hidden_fields = set(config.get("hidden_body_fields", []))
    for key, value in merged_metadata.items():
        if value and key not in hidden_fields:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def build_payload(provider: str, title: str, body: str, config: dict) -> dict:
    if provider == "wecom":
        return {
            "msgtype": "markdown",
            "markdown": {"content": f"**{title}**\n\n{body.replace(chr(10), chr(10) + chr(10))}"},
        }
    if provider == "dingtalk":
        return {
            "msgtype": "text",
            "text": {"content": f"{title}\n{body}"},
            "at": {
                "atMobiles": config.get("mentioned_mobile_list", []),
                "atUserIds": config.get("mentioned_list", []),
                "isAtAll": False,
            },
        }
    if provider == "feishu":
        payload = {
            "msg_type": "text",
            "content": {"text": f"{title}\n{body}"},
        }
        secret = str(config.get("secret", "")).strip()
        if secret:
            timestamp = str(int(datetime.now().timestamp()))
            string_to_sign = f"{timestamp}\n{secret}"
            sign = base64.b64encode(
                hmac.new(
                    string_to_sign.encode("utf-8"),
                    digestmod=hashlib.sha256,
                ).digest()
            ).decode("utf-8")
            payload["timestamp"] = timestamp
            payload["sign"] = sign
        return payload
    return {
        "title": title,
        "text": body,
        "provider": provider,
        "extra_fields": config.get("extra_fields", {}),
    }


def send_webhook(webhook_url: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with _open_url(req, timeout=15) as resp:
        raw = resp.read()
    if not raw:
        return {}
    try:
        result = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    errcode = result.get("errcode")
    code = result.get("code")
    if errcode not in (None, 0):
        raise RuntimeError(f"webhook failed: errcode={errcode} errmsg={result.get('errmsg')}")
    if code not in (None, 0):
        raise RuntimeError(f"webhook failed: code={code} msg={result.get('msg')}")
    return result


def _first_metadata_value(metadata: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = metadata.get(key)
        if value:
            return str(value).strip()
    return ""


def _find_html_report_path(metadata: dict[str, str]) -> Path | None:
    path, reason = resolve_html_report_metadata_path(
        metadata,
        require_formal_alias=False,
    )
    if path is not None:
        return path if path.is_file() else None
    if "aliases conflict" in reason:
        raise RuntimeError(reason)

    review_dir = _first_metadata_value(metadata, ("审核目录", "review_dir", "ReviewDir"))
    project_id = _first_metadata_value(metadata, ("项目编号", "project_id", "ProjectID"))
    if review_dir and project_id:
        candidate = Path(review_dir).expanduser() / f"{project_id}_audit_report.html"
        if candidate.is_file():
            return candidate
    return None


def _feishu_file_config(config: dict) -> dict:
    raw = config.get("feishu_app_file", {})
    return raw if isinstance(raw, dict) else {}


def _wecom_file_config(config: dict) -> dict:
    raw = config.get("wecom_file", {})
    return raw if isinstance(raw, dict) else {}


def _feishu_file_enabled(config: dict, metadata: dict[str, str]) -> tuple[bool, str]:
    file_config = _feishu_file_config(config)
    if not file_config.get("enabled", False):
        return False, "feishu app file disabled"
    if file_config.get("send_html_report", True) is False:
        return False, "send_html_report disabled"
    for key in ("app_id", "app_secret", "chat_id"):
        if not str(file_config.get(key, "")).strip():
            return False, f"feishu app file {key} missing"
    if not _find_html_report_path(metadata):
        return False, "html report missing"
    return True, ""


def _wecom_robot_key(config: dict, webhook_url: str = "") -> str:
    key = str(config.get("webhook_key", "")).strip()
    if key:
        return key
    parsed = urlparse(webhook_url or str(config.get("webhook_url", "")).strip())
    return parse_qs(parsed.query).get("key", [""])[0].strip()


def _wecom_file_enabled(config: dict, metadata: dict[str, str], webhook_url: str = "") -> tuple[bool, str]:
    file_config = _wecom_file_config(config)
    if not file_config.get("enabled", False):
        return False, "wecom file disabled"
    if file_config.get("send_html_report", True) is False:
        return False, "send_html_report disabled"
    if not _wecom_robot_key(config, webhook_url=webhook_url):
        return False, "wecom webhook key missing"
    if not _find_html_report_path(metadata):
        return False, "html report missing"
    return True, ""


def _json_post(url: str, payload: dict, headers: dict[str, str] | None = None, timeout: int = 30) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req_headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        req_headers.update(headers)
    req = request.Request(url, data=data, headers=req_headers, method="POST")
    with _open_url(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _feishu_tenant_access_token(app_id: str, app_secret: str) -> str:
    body = _json_post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
    )
    if body.get("code") != 0 or not body.get("tenant_access_token"):
        raise RuntimeError(f"tenant_access_token failed: code={body.get('code')} msg={body.get('msg')}")
    return str(body["tenant_access_token"])


def _multipart_body(
    fields: dict[str, str], file_field: str, file_path: Path, *, file_bytes: bytes | None = None
) -> tuple[bytes, str]:
    boundary = f"----auditframeworkfeishu{int(time.time())}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(
            (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                f"{value}\r\n"
            ).encode("utf-8")
        )
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    chunks.append(
        (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"{file_field}\"; filename=\"{file_path.name}\"\r\n"
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(file_bytes if file_bytes is not None else file_path.read_bytes())
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def _manifest_bound_html_bytes(
    provider: str,
    html_path: Path,
    expected_sha256: str,
) -> bytes:
    html_bytes = html_path.read_bytes()
    expected = expected_sha256.strip().lower()
    if len(expected) != 64 or hashlib.sha256(html_bytes).hexdigest() != expected:
        raise RuntimeError(
            f"{provider} file blocked: HTML bytes do not match formal delivery manifest"
        )
    return html_bytes


def _feishu_upload_file(
    token: str,
    html_path: Path,
    *,
    expected_sha256: str = "",
) -> str:
    html_bytes = _manifest_bound_html_bytes(
        "feishu",
        html_path,
        expected_sha256,
    )
    body, boundary = _multipart_body(
        {"file_type": "stream", "file_name": html_path.name},
        "file",
        html_path,
        file_bytes=html_bytes,
    )
    req = request.Request(
        "https://open.feishu.cn/open-apis/im/v1/files",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with _open_url(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    file_key = (result.get("data") or {}).get("file_key")
    if result.get("code") != 0 or not file_key:
        raise RuntimeError(f"feishu file upload failed: code={result.get('code')} msg={result.get('msg')}")
    return str(file_key)


def _wecom_upload_file(robot_key: str, html_path: Path, *, expected_sha256: str = "") -> str:
    html_bytes = _manifest_bound_html_bytes(
        "wecom",
        html_path,
        expected_sha256,
    )
    body, boundary = _multipart_body({}, "media", html_path, file_bytes=html_bytes)
    url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?" + urlencode(
        {"key": robot_key, "type": "file"}
    )
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with _open_url(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    media_id = result.get("media_id")
    if result.get("errcode") != 0 or not media_id:
        raise RuntimeError(f"wecom file upload failed: errcode={result.get('errcode')} errmsg={result.get('errmsg')}")
    return str(media_id)


def send_wecom_html_file(config: dict, metadata: dict[str, str], webhook_url: str = "") -> tuple[bool, str]:
    enabled, reason = _wecom_file_enabled(config, metadata, webhook_url=webhook_url)
    if not enabled:
        return False, f"wecom file skipped: {reason}"

    html_path = _find_html_report_path(metadata)
    if html_path is None:
        return False, "wecom file skipped: html report missing"

    resolved_webhook = webhook_url or str(config.get("webhook_url", "")).strip()
    robot_key = _wecom_robot_key(config, webhook_url=resolved_webhook)
    expected_sha256 = str(metadata.get("html_report_sha256", "")).strip()
    media_id = _wecom_upload_file(robot_key, html_path, expected_sha256=expected_sha256)
    send_webhook(resolved_webhook, {"msgtype": "file", "file": {"media_id": media_id}})
    return True, "wecom html file sent"


def _feishu_send_file_message(token: str, chat_id: str, file_key: str) -> str:
    url = "https://open.feishu.cn/open-apis/im/v1/messages?" + urlencode({"receive_id_type": "chat_id"})
    result = _json_post(
        url,
        {
            "receive_id": chat_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key}, ensure_ascii=False),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    if result.get("code") != 0:
        raise RuntimeError(f"feishu file message failed: code={result.get('code')} msg={result.get('msg')}")
    return str((result.get("data") or {}).get("message_id", ""))


def send_feishu_html_file(config: dict, metadata: dict[str, str]) -> tuple[bool, str]:
    enabled, reason = _feishu_file_enabled(config, metadata)
    if not enabled:
        return False, f"feishu file skipped: {reason}"

    file_config = _feishu_file_config(config)
    html_path = _find_html_report_path(metadata)
    if html_path is None:
        return False, "feishu file skipped: html report missing"

    token = _feishu_tenant_access_token(
        str(file_config.get("app_id", "")).strip(),
        str(file_config.get("app_secret", "")).strip(),
    )
    expected_sha256 = str(metadata.get("html_report_sha256", "")).strip()
    file_key = _feishu_upload_file(
        token,
        html_path,
        expected_sha256=expected_sha256,
    )
    message_id = _feishu_send_file_message(token, str(file_config.get("chat_id", "")).strip(), file_key)
    if message_id:
        return True, f"feishu html file sent: {message_id}"
    return True, "feishu html file sent"


def _resolve_webhook_url(provider: str, config: dict) -> str:
    webhook_url = str(config.get("webhook_url", "")).strip()
    if provider == "wecom" and not webhook_url:
        webhook_key = str(config.get("webhook_key", "")).strip()
        if webhook_key:
            webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
    if provider == "wecom":
        secret = str(config.get("secret", "")).strip()
        if secret and webhook_url:
            timestamp = str(int(datetime.now().timestamp()))
            string_to_sign = f"{timestamp}\n{secret}"
            sign = base64.b64encode(
                hmac.new(
                    secret.encode("utf-8"),
                    string_to_sign.encode("utf-8"),
                    digestmod=hashlib.sha256,
                ).digest()
            ).decode("utf-8")
            sep = "&" if "?" in webhook_url else "?"
            webhook_url = f"{webhook_url}{sep}timestamp={timestamp}&sign={quote_plus(sign)}"
    return webhook_url


def _send_channel(config: dict, task_type: str, task_name: str, status: str, summary: str,
                  metadata: dict[str, str]) -> tuple[bool, str]:
    valid, reason = validate_notification_request(task_type, status, metadata)
    if not valid:
        return False, reason
    if _is_completed_audit(task_type, status):
        delivery_ok, delivery_reason = validate_completed_audit_delivery(metadata)
        if not delivery_ok:
            return False, delivery_reason
    title = build_title(task_name, status, config)
    body = build_body(task_type, task_name, status, summary, metadata, config)
    provider = str(config.get("provider", "generic_json")).strip() or "generic_json"
    if provider == "wecom":
        allowed, gate_reason = _wecom_formal_audit_allowed(task_type, status, metadata, config)
        if not allowed:
            return False, gate_reason
        consumed, consume_reason = consume_release_attestation(metadata, config, provider="wecom")
        if not consumed:
            return False, consume_reason
    webhook_url = _resolve_webhook_url(provider, config)
    payload = build_payload(provider, title, body, config)
    send_webhook(webhook_url, payload)
    messages = [f"notification sent via {provider}"]

    if provider == "wecom":
        file_config = _wecom_file_config(config)
        if file_config.get("enabled", False):
            try:
                _, file_message = send_wecom_html_file(config, metadata, webhook_url=webhook_url)
                messages.append(file_message)
            except Exception as exc:
                messages.append(f"wecom file failed: {exc}")
                if file_config.get("fail_on_error", True):
                    return False, "; ".join(messages)

    if provider == "feishu":
        file_config = _feishu_file_config(config)
        if file_config.get("enabled", False):
            try:
                _, file_message = send_feishu_html_file(config, metadata)
                messages.append(file_message)
            except Exception as exc:
                messages.append(f"feishu file failed: {exc}")
                if file_config.get("fail_on_error", False):
                    return False, "; ".join(messages)

    return True, "; ".join(messages)


def send_notification(
    task_type: str,
    task_name: str,
    status: str,
    summary: str,
    metadata: dict[str, str] | None = None,
    config_arg: str = "",
    *,
    allow_fallback: bool = True,
) -> tuple[bool, str]:
    config = load_config(config_arg)
    enabled, reason = notifications_enabled(config, task_type=task_type)
    if not enabled:
        return False, f"notification skipped: {reason}"

    metadata = metadata or {}
    valid, reason = validate_notification_request(task_type, status, metadata)
    if not valid:
        return False, reason

    try:
        primary_ok, primary_message = _send_channel(config, task_type, task_name, status, summary, metadata)
    except Exception as exc:
        primary_ok, primary_message = False, f"primary notification failed: {exc}"
    if primary_ok:
        return True, primary_message

    # A formal-delivery or release-authorization failure is a local denial,
    # never a delivery failure.  Falling back to another provider would bypass
    # the independent publication decision.
    if str(primary_message).startswith((
        "formal delivery blocked:",
        "formal audit release blocked:",
        "wecom skipped: formal audit gate not satisfied",
    )):
        return False, primary_message

    if not allow_fallback:
        return False, primary_message

    fallback = fallback_config(config)
    if not fallback:
        return False, primary_message

    try:
        fallback_ok, fallback_message = _send_channel(fallback, task_type, task_name, status, summary, metadata)
    except Exception as exc:
        fallback_ok, fallback_message = False, f"fallback notification failed: {exc}"
    return fallback_ok, f"{primary_message}; fallback: {fallback_message}"
