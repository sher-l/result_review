#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Shared notification client for webhook-based task completion alerts.
"""

from __future__ import annotations

import json
import socket
import base64
import hashlib
import hmac
from urllib.parse import quote_plus
from datetime import datetime
from pathlib import Path
from urllib import request


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "notification_config.json"


def load_config(config_arg: str = "") -> dict:
    config_path = Path(config_arg) if config_arg else default_config_path()
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


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


def build_title(task_name: str, status: str, config: dict) -> str:
    prefix = str(config.get("default_title_prefix", "任务通知")).strip()
    if prefix:
        return f"[{prefix}] {task_name} - {status}"
    return f"{task_name} - {status}"


def build_body(task_type: str, task_name: str, status: str, summary: str,
               metadata: dict[str, str], config: dict) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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


def send_webhook(webhook_url: str, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=15) as resp:
        _ = resp.read()


def send_notification(task_type: str, task_name: str, status: str, summary: str,
                      metadata: dict[str, str] | None = None, config_arg: str = "") -> tuple[bool, str]:
    config = load_config(config_arg)
    enabled, reason = notifications_enabled(config, task_type=task_type)
    if not enabled:
        return False, f"notification skipped: {reason}"

    title = build_title(task_name, status, config)
    body = build_body(task_type, task_name, status, summary, metadata or {}, config)
    provider = str(config.get("provider", "generic_json")).strip() or "generic_json"
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
    payload = build_payload(provider, title, body, config)
    send_webhook(webhook_url, payload)
    return True, f"notification sent via {provider}"
