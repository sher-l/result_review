#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression guard: framework tests must never emit real notifications."""

from __future__ import annotations

import pytest

import notification_client


def test_webhook_send_is_blocked_before_urlopen():
    with pytest.raises(RuntimeError, match="outbound notification network disabled"):
        notification_client.send_webhook("https://example.invalid/webhook", {"text": "never send"})


def test_feishu_json_post_is_blocked_before_urlopen():
    with pytest.raises(RuntimeError, match="outbound notification network disabled"):
        notification_client._json_post("https://open.feishu.cn/never-send", {"msg": "never send"})
