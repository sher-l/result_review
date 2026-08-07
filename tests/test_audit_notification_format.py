#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression tests for formal audit completion notification formatting."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import notification_client
import send_audit_notification
import send_completion_notification
import finalize_audit
from formal_delivery import build_formal_delivery_manifest, validate_formal_delivery_manifest
from render_final_review_html import build_html
from visual_audit import build_visual_audit_result


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "notification_config.json"
    config_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "enabled_task_types": ["audit"],
                "provider": "wecom",
                "webhook_url": "https://example.invalid/webhook",
                "default_title_prefix": "报告审核",
                "wecom_file": {"enabled": False},
                "wecom_formal_audit_gate": {
                    "enabled": True,
                    "marker_keys": ["formal_audit"],
                },
                "formal_delivery_gate": {"enabled": False},
                "release_attestation_gate": {"enabled": False},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return config_path


def _formal_metadata(project_id: str, review_dir: Path, html_path: Path) -> dict[str, str]:
    return {
        "项目号": project_id,
        "审核文件": f"{project_id}-demo",
        "报告文件": html_path.name,
        "审核结果": "不通过",
        "critical": "1",
        "major": "2",
        "warning": "3",
        "formal_audit": "true",
        "审核目录": str(review_dir),
        "HTML": str(html_path),
    }


def _write_current_formal_delivery(review_dir: Path, project_id: str) -> tuple[Path, dict[str, str]]:
    assert review_dir.name == project_id, "formal review directory must be named with the project id"
    review_dir.mkdir(parents=True, exist_ok=True)
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / f"{project_id}_audit_report.html"
    markdown = (
        f"# {project_id} 正式复审报告\n\n"
        f"> **项目名称**：{project_id}-demo\n"
        "> **审核日期**：2026-07-31\n\n"
        "## 一、审核结论\n\n"
        "结论：不合格。\n\n"
        "## 二、提交阻断问题\n\n"
        "### P01 [CRITICAL] 阻断问题\n\n"
        "必须修订后重新提交审核。\n"
    )
    report_path.write_text(markdown, encoding="utf-8")
    (review_dir / "project_structure.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "total_modules": 1,
                    "total_code_files": 0,
                    "total_data_files": 1,
                    "total_images": 0,
                    "total_config_files": 0,
                },
                "modules": [
                    {
                        "path": "data-only",
                        "file_counts": {
                            "total": 1,
                            "csv": 1,
                            "pdf": 0,
                            "images": 0,
                            "code": 0,
                        },
                    }
                ],
                "code_files": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    decision_path = review_dir / "final_decision.json"
    decision_path.write_text(
        (
            '{"status": "leader_confirmed", "verdict": "不合格", '
            '"release_decision": "BLOCK"}\n'
        ),
        encoding="utf-8",
    )
    report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
    rendered = build_html(
        markdown,
        report_path,
        final_decision={
            "status": "leader_confirmed",
            "verdict": "不合格",
            "release_decision": "BLOCK",
        },
    )
    html_path.write_text(
        f"<!-- audit-source-markdown-sha256: {report_sha256} -->\n{rendered}",
        encoding="utf-8",
    )
    visual_result = build_visual_audit_result(review_dir, [], [], review_lane="strict")
    (review_dir / "visual_audit_result.json").write_text(
        json.dumps(visual_result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest_path, _ = build_formal_delivery_manifest(
        review_dir,
        html_path,
        decision_sha256=hashlib.sha256(decision_path.read_bytes()).hexdigest(),
    )
    metadata = _formal_metadata(project_id, review_dir, html_path)
    metadata.update(
        {
            "formal_delivery_manifest": str(manifest_path),
            "formal_delivery_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "html_report_sha256": hashlib.sha256(html_path.read_bytes()).hexdigest(),
        }
    )
    return html_path, metadata


def test_formal_delivery_manifest_accepts_relative_review_metadata(tmp_path, monkeypatch):
    """Finalize metadata may be relative when its CLI argument is relative."""
    monkeypatch.chdir(tmp_path)
    review_dir = Path("26YYH068F")
    html_path, metadata = _write_current_formal_delivery(review_dir, review_dir.name)

    assert metadata["审核目录"] == str(review_dir)
    assert metadata["HTML"] == str(html_path)
    ok, reason = validate_formal_delivery_manifest(
        metadata,
        {"formal_delivery_gate": {"enabled": True}},
    )

    assert ok is True, reason


def _write_signed_release_attestation(tmp_path: Path, project_id: str, *, expires_at: datetime | None = None) -> tuple[Path, Path, dict[str, str]]:
    review_dir = tmp_path / project_id
    arbitration_dir = review_dir / "agent_results" / "arbitration"
    arbitration_dir.mkdir(parents=True)
    artifacts = {
        "final_decision": review_dir / "final_decision.json",
        "arbitration_resolution": arbitration_dir / "arbitration_resolution.json",
        "visual_audit_result": review_dir / "visual_audit_result.json",
        "final_review_report": review_dir / "final_review_report.md",
        "html_report": review_dir / f"{project_id}_audit_report.html",
    }
    for name, path in artifacts.items():
        path.write_text(f"{name} evidence", encoding="utf-8")
    _, metadata = _write_current_formal_delivery(review_dir, project_id)
    now = datetime.now(timezone.utc)
    payload = {
        "schema_version": "1.0",
        "project_id": project_id,
        "issued_at": (now - timedelta(seconds=1)).isoformat(),
        "expires_at": (expires_at or now + timedelta(minutes=5)).isoformat(),
        "nonce": "release-test-nonce",
        "artifacts": {
            name: {
                "path": str(path.relative_to(review_dir)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for name, path in artifacts.items()
        },
    }
    attestation = review_dir / "release_attestation.json"
    signature = review_dir / "release_attestation.sig"
    private_key = tmp_path / "signer-private.pem"
    public_key = tmp_path / "signer-public.pem"
    attestation.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(private_key)], check=True, capture_output=True)
    subprocess.run(["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)], check=True, capture_output=True)
    subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(private_key), "-out", str(signature), str(attestation)], check=True, capture_output=True)
    return review_dir, public_key, metadata


def _enable_release_gate(config_path: Path, public_key: Path | None) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["release_attestation_gate"] = {
        "enabled": True,
        "required_providers": ["wecom"],
        "public_key_path": str(public_key) if public_key else "",
        "max_age_seconds": 900,
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")


def test_completed_audit_blocks_before_network_when_formal_fields_missing(tmp_path, monkeypatch):
    config_path = _write_config(tmp_path)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("network send must not be attempted for incomplete formal audit metadata")

    monkeypatch.setattr(notification_client, "send_webhook", fail_if_called)

    ok, message = notification_client.send_notification(
        task_type="audit",
        task_name="审核完成 26YYH067F",
        status="completed",
        summary="正式审核完成：不通过",
        metadata={
            "项目号": "26YYH067F",
            "审核文件": "26YYH067F-数据分析报告-腹主动脉瘤scPagwas单细胞分析-CWX-20260521",
            "报告文件": "26YYH067F_audit_report.html",
            "formal_audit": "true",
        },
        config_arg=str(config_path),
    )

    assert ok is False
    assert "missing required formal body fields" in message
    assert "审核结果" in message
    assert "CRITICAL/MAJOR/WARNING" in message


def test_completed_audit_manifest_gate_is_provider_independent_and_never_falls_back(tmp_path, monkeypatch):
    attempted: list[str] = []

    def fail_if_called(webhook_url, _payload):
        attempted.append(webhook_url)
        raise AssertionError("formal delivery failure must not reach any provider")

    monkeypatch.setattr(notification_client, "send_webhook", fail_if_called)
    metadata = {
        "项目号": "26YYH067F",
        "审核文件": "26YYH067F-demo",
        "报告文件": "26YYH067F_audit_report.html",
        "审核结果": "不通过",
        "critical": "1",
        "major": "2",
        "warning": "3",
        "审核目录": str(tmp_path / "missing-review"),
        "HTML": str(tmp_path / "missing-review" / "26YYH067F_audit_report.html"),
    }
    for provider in ("wecom", "feishu", "generic_json"):
        config_path = tmp_path / f"{provider}.json"
        config_path.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "enabled_task_types": ["audit"],
                    "provider": provider,
                    "webhook_url": f"https://{provider}.invalid/webhook",
                    "wecom_file": {"enabled": False},
                    "wecom_formal_audit_gate": {"enabled": True, "marker_keys": ["formal_audit"]},
                    "formal_delivery_gate": {"enabled": False},
                    "release_attestation_gate": {"enabled": False},
                    "fallback_notification": {
                        "enabled": True,
                        "provider": "feishu",
                        "webhook_url": "https://fallback.invalid/webhook",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        ok, message = notification_client.send_notification(
            task_type="audit",
            task_name="审核完成 26YYH067F",
            status=" COMPLETED ",
            summary="正式审核完成",
            metadata=metadata,
            config_arg=str(config_path),
        )
        assert ok is False
        assert message.startswith("formal delivery blocked:")
    assert attempted == []


def test_finalize_rejects_external_notification_config():
    args = SimpleNamespace(
        notification_config="/tmp/untrusted-notification-config.json",
        notification_channel="default",
        feishu_only=False,
    )
    try:
        finalize_audit.resolve_notification_config_arg(args)
    except ValueError as exc:
        assert "not permitted for finalize" in str(exc)
    else:
        raise AssertionError("finalize accepted an external notification config")


def test_completed_audit_release_gate_blocks_without_external_signer(tmp_path, monkeypatch):
    config_path = _write_config(tmp_path)
    review_dir = tmp_path / "26YYH067F"
    _, metadata = _write_current_formal_delivery(review_dir, "26YYH067F")
    _enable_release_gate(config_path, None)
    monkeypatch.setattr(notification_client, "send_webhook", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network must not run")))

    ok, message = notification_client.send_notification(
        task_type="audit", task_name="audit", status="completed", summary="done",
        metadata=metadata, config_arg=str(config_path),
    )

    assert ok is False
    assert message == "formal audit release blocked: independent signer configuration missing"


def test_release_gate_denial_never_falls_back_to_feishu(tmp_path, monkeypatch):
    config_path = _write_config(tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["fallback_notification"] = {
        "enabled": True,
        "provider": "feishu",
        "webhook_url": "https://fallback.invalid/webhook",
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    review_dir = tmp_path / "26YYH067F"
    _, metadata = _write_current_formal_delivery(review_dir, "26YYH067F")
    _enable_release_gate(config_path, None)
    monkeypatch.setattr(notification_client, "send_webhook", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fallback network must not run")))

    ok, message = notification_client.send_notification(
        task_type="audit", task_name="audit", status="completed", summary="done",
        metadata=metadata, config_arg=str(config_path),
    )

    assert ok is False
    assert "independent signer configuration missing" in message


def test_completed_audit_release_gate_accepts_valid_external_signature(tmp_path, monkeypatch):
    config_path = _write_config(tmp_path)
    review_dir, public_key, metadata = _write_signed_release_attestation(tmp_path, "26YYH067F")
    _enable_release_gate(config_path, public_key)
    sent: list[dict] = []
    monkeypatch.setattr(notification_client, "send_webhook", lambda _url, payload: sent.append(payload) or {})

    ok, message = notification_client.send_notification(
        task_type="audit", task_name="audit", status="completed", summary="done",
        metadata=metadata, config_arg=str(config_path),
    )

    assert ok is True
    assert message == "notification sent via wecom"
    assert len(sent) == 1

    ok, message = notification_client.send_notification(
        task_type="audit", task_name="audit", status="completed", summary="done",
        metadata=metadata, config_arg=str(config_path),
    )
    assert ok is False
    assert "already consumed" in message
    assert len(sent) == 1


def test_completed_audit_release_gate_blocks_expired_or_changed_artifact(tmp_path, monkeypatch):
    config_path = _write_config(tmp_path)
    review_dir, public_key, metadata = _write_signed_release_attestation(
        tmp_path, "26YYH067F", expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    _enable_release_gate(config_path, public_key)
    monkeypatch.setattr(notification_client, "send_webhook", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network must not run")))

    ok, message = notification_client.send_notification(
        task_type="audit", task_name="audit", status="completed", summary="done",
        metadata=metadata, config_arg=str(config_path),
    )
    assert ok is False
    assert "not currently valid" in message

    # Alter a bound artifact after signing.  The provider-independent manifest
    # gate now rejects this before the provider-specific signature check.
    review_dir, public_key, metadata = _write_signed_release_attestation(tmp_path / "changed", "26YYH067F")
    _enable_release_gate(config_path, public_key)
    (review_dir / "final_review_report.md").write_text("changed after signing", encoding="utf-8")
    ok, message = notification_client.send_notification(
        task_type="audit", task_name="audit", status="completed", summary="done",
        metadata=metadata, config_arg=str(config_path),
    )
    assert ok is False
    assert "formal delivery manifest artifact hash mismatch: final_review_report" in message


def test_completed_audit_body_uses_only_required_formal_fields(tmp_path, monkeypatch):
    config_path = _write_config(tmp_path)
    sent_payloads: list[dict] = []
    html_path, metadata = _write_current_formal_delivery(tmp_path / "26YYH067F", "26YYH067F")
    metadata.update(
        {
            "项目号": "26YYH067F",
            "审核文件": "26YYH067F-数据分析报告-腹主动脉瘤scPagwas单细胞分析-CWX-20260521",
            "报告文件": html_path.name,
            "审核结果": "不通过（P0；需重大修订后重新提交审核）",
            "critical": "4",
            "major": "9",
            "warning": "3",
        }
    )

    def capture_send(_webhook_url, payload):
        sent_payloads.append(payload)
        return {}

    monkeypatch.setattr(notification_client, "send_webhook", capture_send)

    ok, message = notification_client.send_notification(
        task_type="audit",
        task_name="审核完成 26YYH067F",
        status="completed",
        summary="这段摘要不应进入正式通知正文",
        metadata=metadata,
        config_arg=str(config_path),
    )

    assert ok is True
    assert message == "notification sent via wecom"
    assert len(sent_payloads) == 1
    content = sent_payloads[0]["markdown"]["content"]
    assert "状态: completed" in content
    assert "项目号: 26YYH067F" in content
    assert "审核文件: 26YYH067F-数据分析报告-腹主动脉瘤scPagwas单细胞分析-CWX-20260521" in content
    assert "报告文件: 26YYH067F_audit_report.html" in content
    assert "项目: 26YYH067F" not in content
    assert "审核结果: 不通过（CRITICAL: 4；MAJOR: 9；WARNING: 3）" in content
    assert "问题统计" not in content
    assert "P0" not in content
    assert "需重大修订" not in content
    assert "任务类型" not in content
    assert "任务名称" not in content
    assert "摘要" not in content


def test_send_notification_can_disable_implicit_fallback(tmp_path, monkeypatch):
    config_path = tmp_path / "notification_config.json"
    config_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "enabled_task_types": ["audit"],
                "provider": "wecom",
                "webhook_url": "https://primary.invalid/webhook",
                "wecom_file": {"enabled": False},
                "wecom_formal_audit_gate": {"enabled": True, "marker_keys": ["formal_audit"]},
                "release_attestation_gate": {"enabled": False},
                "fallback_notification": {
                    "enabled": True,
                    "provider": "feishu",
                    "webhook_url": "https://fallback.invalid/webhook",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    attempted_urls: list[str] = []

    def fail_primary(webhook_url, _payload):
        attempted_urls.append(webhook_url)
        raise RuntimeError("primary unavailable")

    monkeypatch.setattr(notification_client, "send_webhook", fail_primary)
    html_path, metadata = _write_current_formal_delivery(tmp_path / "26YYH067F", "26YYH067F")
    metadata.update(
        {
            "审核文件": "26YYH067F-demo",
            "报告文件": html_path.name,
            "审核结果": "不通过（45/100）",
            "critical": "1",
            "major": "2",
            "warning": "3",
        }
    )

    ok, message = notification_client.send_notification(
        task_type="audit",
        task_name="审核完成 26YYH067F",
        status="completed",
        summary="正式审核完成",
        metadata=metadata,
        config_arg=str(config_path),
        allow_fallback=False,
    )

    assert ok is False
    assert "primary notification failed" in message
    assert attempted_urls == ["https://primary.invalid/webhook"]


def test_wrapper_refuses_direct_completed_audit_before_metadata_validation(tmp_path, monkeypatch, capsys):
    html_path = tmp_path / "26YYH067F_audit_report.html"
    html_path.write_text("<html></html>", encoding="utf-8")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("wrapper must fail before send_notification when fields are missing")

    monkeypatch.setattr(send_audit_notification, "send_notification", fail_if_called)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "send_audit_notification.py",
            "--project-id",
            "26YYH067F",
            "--status",
            "completed",
            "--review-dir",
            str(tmp_path),
            "--html-path",
            str(html_path),
            "--formal-audit",
        ],
    )

    assert send_audit_notification.main() == 1
    out = capsys.readouterr().out
    assert "Direct audit completion notification is disabled" in out


def test_wrapper_refuses_direct_completed_audit_even_with_formal_fields(tmp_path, monkeypatch, capsys):
    html_path = tmp_path / "26YYH067F_audit_report.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    captured: dict[str, object] = {}

    def capture_send(**kwargs):
        captured.update(kwargs)
        raise AssertionError("direct completed audit wrapper must not call the notification client")

    monkeypatch.setattr(send_audit_notification, "send_notification", capture_send)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "send_audit_notification.py",
            "--project-id",
            "26YYH067F",
            "--status",
            "completed",
            "--review-dir",
            str(tmp_path),
            "--html-path",
            str(html_path),
            "--audit-file",
            "26YYH067F-数据分析报告-腹主动脉瘤scPagwas单细胞分析-CWX-20260521",
            "--audit-result",
            "不通过（P0；需重大修订后重新提交审核）",
            "--critical",
            "4",
            "--major",
            "9",
            "--warning",
            "3",
            "--formal-audit",
        ],
    )

    assert send_audit_notification.main() == 1
    assert captured == {}
    out = capsys.readouterr().out
    assert "Direct audit completion notification is disabled" in out


def test_generic_wrapper_refuses_direct_completed_audit(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        send_completion_notification,
        "send_notification",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("direct completed audit wrapper must not send")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "send_completion_notification.py",
            "--task-type",
            "audit",
            "--task-name",
            "审核完成 26YYH067F",
            "--status",
            "completed",
            "--meta",
            f"审核目录={tmp_path}",
        ],
    )

    assert send_completion_notification.main() == 1
    assert "Direct audit completion notification is disabled" in capsys.readouterr().out
