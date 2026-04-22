#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Shared loader for the canonical audit policy.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


def policy_path() -> Path:
    return Path(__file__).resolve().parents[1] / "policy" / "audit_policy.json"


@lru_cache(maxsize=1)
def load_policy() -> dict:
    path = policy_path()
    return json.loads(path.read_text(encoding="utf-8"))
