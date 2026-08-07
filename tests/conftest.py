#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""全局测试 fixtures

cd result_review_framework
python -m pytest tests/ -v
"""

import socket
import sys
from pathlib import Path

import pytest

# 统一 sys.path 设置
sys.path.insert(0, str(Path(__file__).parent.parent / 'script_utils'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))


@pytest.fixture(autouse=True)
def deny_all_outbound_network(monkeypatch):
    """Regression tests are local-only; any socket or notification egress fails."""
    monkeypatch.setenv("AUDIT_FRAMEWORK_DENY_NETWORK", "1")

    def blocked(*_args, **_kwargs):
        raise AssertionError("outbound network is forbidden during audit framework tests")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def empty_project(tmp_path):
    """空项目目录"""
    return str(tmp_path)


@pytest.fixture
def project_with_result_dir(tmp_path):
    """含结果目录的项目"""
    proj = tmp_path / '26YTEST01F'
    proj.mkdir()
    result_dir = proj / '结果'
    result_dir.mkdir()
    return proj


@pytest.fixture
def project_with_code(tmp_path):
    """含代码目录的项目"""
    proj = tmp_path / '26YTEST02F'
    proj.mkdir()
    code_dir = proj / 'CODE'
    code_dir.mkdir()
    return proj
