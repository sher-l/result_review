from __future__ import annotations

import hashlib
import json
import re

import notification_client
import pytest
from formal_delivery import build_formal_delivery_manifest, validate_formal_delivery_manifest
from html_presentation_contract import validate_html_presentation_text
from final_report_linter import (
    build_checks,
    build_delivery_state_checks,
    build_report_depth_checks,
    summarize_checks,
)
from render_final_review_html import build_html
from visual_audit import build_visual_audit_result


def _delivery_config(*, enabled: bool = True) -> dict:
    return {"formal_delivery_gate": {"enabled": enabled}}


def _metadata(review_dir, html_path) -> dict[str, str]:
    manifest_path = review_dir / "formal_delivery_manifest.json"
    return {
        "project_id": review_dir.name,
        "review_dir": str(review_dir),
        "html_report": str(html_path),
        "formal_delivery_manifest": str(manifest_path),
        "report_file": html_path.name,
        "html_report_sha256": hashlib.sha256(html_path.read_bytes()).hexdigest(),
        "formal_delivery_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if manifest_path.is_file()
        else "",
        "project_display_name": f"{review_dir.name}-demo",
        "audit_result": "不通过（0/100）",
        "issue_stats": "CRITICAL: 1；MAJOR: 0；WARNING: 0",
        "formal_audit": "true",
    }


def _write_bound_html(report_path, html_path, body="正式复审报告") -> None:
    project_id = report_path.parent.name
    markdown = (
        f"# {project_id} 正式复审报告\n\n"
        f"> **项目名称**：{project_id}-demo\n"
        "> **审核日期**：2026-07-31\n\n"
        "## 一、审核结论\n\n"
        f"{body}。结论：不合格。\n\n"
        "## 二、提交阻断问题\n\n"
        "### P01 [CRITICAL] 阻断问题\n\n"
        "必须修订后重新提交审核。\n"
    )
    report_path.write_text(markdown, encoding="utf-8")
    (report_path.parent / "project_structure.json").write_text(
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


def _remove_inventory_legend(html_text: str) -> str:
    mutated, replacements = re.subn(
        r'<p class="inventory-legend">.*?</p>',
        "",
        html_text,
        count=1,
        flags=re.DOTALL,
    )
    assert replacements == 1
    return mutated


def _write_closed_visual_result(review_dir) -> None:
    result = build_visual_audit_result(review_dir, [], [], review_lane="strict")
    (review_dir / "visual_audit_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_final_decision(review_dir) -> str:
    decision_path = review_dir / "final_decision.json"
    decision_path.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "status": "leader_confirmed",
                "verdict": "不合格",
                "release_decision": "BLOCK",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return hashlib.sha256(decision_path.read_bytes()).hexdigest()


def test_linter_blocks_pre_release_state_text(tmp_path):
    report = "# 正式复审报告（草案）\n\n本报告为复审草案，状态为待最终门禁与正式发布。未发送通知、未归档。\n"
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    checks = build_checks(
        review_dir,
        report,
        {
            "required_final_files": [],
            "required_final_sections": {},
            "forbidden_shortcuts": [],
            "lint_policy": {"check_external_links": False, "check_local_links": False},
            "formal_delivery_policy": {"enabled": True},
        },
    )
    summary = summarize_checks(checks, {"lint_policy": {}})
    assert summary["passed"] is False
    assert any(check["id"].startswith("delivery_state:") for check in summary["errors"])


def test_linter_policy_sections_fail_closed_when_missing_or_disabled():
    missing_delivery = build_delivery_state_checks("# 正式复审报告", {})
    missing_depth = build_report_depth_checks("# 正式复审报告", {})
    disabled_delivery = build_delivery_state_checks(
        "# 正式复审报告",
        {"formal_delivery_policy": {"enabled": False}},
    )
    disabled_depth = build_report_depth_checks(
        "# 正式复审报告",
        {"final_report_depth_policy": {"enabled": False}},
    )

    for checks, expected_id in (
        (missing_delivery, "policy:formal_delivery_policy"),
        (missing_depth, "policy:final_report_depth_policy"),
        (disabled_delivery, "policy:formal_delivery_policy:disabled"),
        (disabled_depth, "policy:final_report_depth_policy:disabled"),
    ):
        assert checks
        assert checks[0]["id"] == expected_id
        assert checks[0]["severity"] == "error"
        assert checks[0]["passed"] is False


def test_manifest_binds_exact_html_and_rejects_tampering(tmp_path):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    report_path.write_text("# 正式复审报告\n\n审核结论。\n", encoding="utf-8")
    _write_bound_html(report_path, html_path)
    _write_closed_visual_result(review_dir)
    decision_sha256 = _write_final_decision(review_dir)
    manifest_path, manifest = build_formal_delivery_manifest(
        review_dir,
        html_path,
        decision_sha256=decision_sha256,
    )
    assert manifest_path.exists()
    assert manifest["artifacts"]["final_decision"]["sha256"] == decision_sha256
    assert [item["path"] for item in manifest["visual_closure_artifacts"]] == [
        "visual_audit_result.json"
    ]
    metadata = _metadata(review_dir, html_path)
    assert validate_formal_delivery_manifest(metadata, _delivery_config()) == (True, "")

    html_path.write_text("<html><body>已被篡改</body></html>", encoding="utf-8")
    ok, reason = validate_formal_delivery_manifest(metadata, _delivery_config())
    assert ok is False
    assert "hash mismatch: html_report" in reason


def test_manifest_rejects_html_verdict_that_conflicts_with_sealed_decision(tmp_path):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    report_path.write_text("# 正式复审报告\n\n审核结论。\n", encoding="utf-8")
    report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
    html_path.write_text(
        (
            f"<!-- audit-source-markdown-sha256: {report_sha256} -->\n"
            '<html><body class="verdict-conditional">'
            '<div class="verdict-banner verdict-conditional">'
            "<span>审核结论：有条件合格</span>"
            "</div></body></html>"
        ),
        encoding="utf-8",
    )
    _write_closed_visual_result(review_dir)
    decision_sha256 = _write_final_decision(review_dir)

    try:
        build_formal_delivery_manifest(
            review_dir,
            html_path,
            decision_sha256=decision_sha256,
        )
    except ValueError as exc:
        assert "HTML verdict" in str(exc)
    else:
        raise AssertionError("HTML verdict conflict was accepted for formal delivery")

    assert not (review_dir / "formal_delivery_manifest.json").exists()


def test_manifest_rejects_html_without_reader_presentation_contract(tmp_path):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    report_path.write_text("# 正式复审报告\n\n审核结论。\n", encoding="utf-8")
    report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
    html_path.write_text(
        (
            f"<!-- audit-source-markdown-sha256: {report_sha256} -->\n"
            '<html><body class="verdict-reject">'
            '<div class="verdict-banner verdict-reject">'
            "<span>审核结论：不合格</span>"
            "</div></body></html>"
        ),
        encoding="utf-8",
    )
    _write_closed_visual_result(review_dir)
    decision_sha256 = _write_final_decision(review_dir)

    try:
        build_formal_delivery_manifest(
            review_dir,
            html_path,
            decision_sha256=decision_sha256,
        )
    except ValueError as exc:
        assert "HTML presentation contract" in str(exc)
    else:
        raise AssertionError("incomplete reader presentation was accepted for formal delivery")

    assert not (review_dir / "formal_delivery_manifest.json").exists()


def test_manifest_rejects_reader_html_without_inventory_legend(tmp_path):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    report_path.write_text("# 正式复审报告\n\n审核结论。\n", encoding="utf-8")
    _write_bound_html(report_path, html_path)
    html_path.write_text(
        _remove_inventory_legend(html_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    _write_closed_visual_result(review_dir)
    decision_sha256 = _write_final_decision(review_dir)

    try:
        build_formal_delivery_manifest(
            review_dir,
            html_path,
            decision_sha256=decision_sha256,
        )
    except ValueError as exc:
        assert "inventory grey-row legend" in str(exc)
    else:
        raise AssertionError("reader HTML without the grey-row legend was accepted")

    assert not (review_dir / "formal_delivery_manifest.json").exists()


def test_manifest_rejects_reader_html_missing_a_canonical_finding(tmp_path):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    _write_bound_html(report_path, html_path)
    markdown = report_path.read_text(encoding="utf-8") + (
        "\n### P02 [CRITICAL] 第二个阻断问题\n\n"
        "第二个问题也必须修订。\n"
    )
    report_path.write_text(markdown, encoding="utf-8")
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
    html_text = html_path.read_text(encoding="utf-8")
    blocks = list(
        re.finditer(
            r'<div class="severity-block severity-critical">.*?</div>',
            html_text,
            flags=re.DOTALL,
        )
    )
    assert len(blocks) == 2
    removed = html_text[: blocks[1].start()] + html_text[blocks[1].end() :]
    assert validate_html_presentation_text(removed) == (True, "")
    html_path.write_text(removed, encoding="utf-8")
    _write_closed_visual_result(review_dir)
    decision_sha256 = _write_final_decision(review_dir)

    with pytest.raises(ValueError, match="canonical renderer"):
        build_formal_delivery_manifest(
            review_dir,
            html_path,
            decision_sha256=decision_sha256,
        )

    assert not (review_dir / "formal_delivery_manifest.json").exists()


def test_manifest_validation_rejects_contract_valid_noncanonical_html_before_notification(
    tmp_path,
):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    _write_bound_html(report_path, html_path)
    markdown = report_path.read_text(encoding="utf-8") + (
        "\n### P02 [CRITICAL] 第二个阻断问题\n\n"
        "第二个问题也必须修订。\n"
    )
    report_path.write_text(markdown, encoding="utf-8")
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
    _write_closed_visual_result(review_dir)
    decision_sha256 = _write_final_decision(review_dir)
    manifest_path, manifest = build_formal_delivery_manifest(
        review_dir,
        html_path,
        decision_sha256=decision_sha256,
    )

    html_text = html_path.read_text(encoding="utf-8")
    blocks = list(
        re.finditer(
            r'<div class="severity-block severity-critical">.*?</div>',
            html_text,
            flags=re.DOTALL,
        )
    )
    assert len(blocks) == 2
    removed = html_text[: blocks[1].start()] + html_text[blocks[1].end() :]
    assert validate_html_presentation_text(removed) == (True, "")
    html_path.write_text(removed, encoding="utf-8")
    manifest["artifacts"]["html_report"]["sha256"] = hashlib.sha256(
        html_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    ok, reason = validate_formal_delivery_manifest(
        _metadata(review_dir, html_path),
        _delivery_config(),
    )

    assert ok is False
    assert "canonical renderer" in reason


def test_manifest_validation_rechecks_html_verdict_before_notification(tmp_path):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    report_path.write_text("# 正式复审报告\n\n审核结论。\n", encoding="utf-8")
    _write_bound_html(report_path, html_path)
    _write_closed_visual_result(review_dir)
    decision_sha256 = _write_final_decision(review_dir)
    manifest_path, manifest = build_formal_delivery_manifest(
        review_dir,
        html_path,
        decision_sha256=decision_sha256,
    )

    report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
    html_path.write_text(
        (
            f"<!-- audit-source-markdown-sha256: {report_sha256} -->\n"
            '<html><body class="verdict-conditional">'
            '<div class="verdict-banner verdict-conditional">'
            "<span>审核结论：有条件合格</span>"
            "</div></body></html>"
        ),
        encoding="utf-8",
    )
    manifest["artifacts"]["html_report"]["sha256"] = hashlib.sha256(
        html_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ok, reason = validate_formal_delivery_manifest(
        _metadata(review_dir, html_path),
        _delivery_config(),
    )

    assert ok is False
    assert "HTML verdict" in reason


def test_manifest_validation_rechecks_presentation_before_notification(tmp_path):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    report_path.write_text("# 正式复审报告\n\n审核结论。\n", encoding="utf-8")
    _write_bound_html(report_path, html_path)
    _write_closed_visual_result(review_dir)
    decision_sha256 = _write_final_decision(review_dir)
    manifest_path, manifest = build_formal_delivery_manifest(
        review_dir,
        html_path,
        decision_sha256=decision_sha256,
    )

    html_path.write_text(
        _remove_inventory_legend(html_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    manifest["artifacts"]["html_report"]["sha256"] = hashlib.sha256(
        html_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ok, reason = validate_formal_delivery_manifest(
        _metadata(review_dir, html_path),
        _delivery_config(),
    )

    assert ok is False
    assert "inventory grey-row legend" in reason


def test_manifest_binds_visual_closure_artifacts_and_rejects_changed_evidence(tmp_path):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    visual_result = review_dir / "visual_audit_result.json"
    visual_inventory = review_dir / "visual_inventory.json"
    report_path.write_text("# 正式复审报告\n\n审核结论。\n", encoding="utf-8")
    _write_bound_html(report_path, html_path)
    _write_closed_visual_result(review_dir)
    visual_inventory.write_text('{"assets": []}', encoding="utf-8")
    decision_sha256 = _write_final_decision(review_dir)

    _, manifest = build_formal_delivery_manifest(
        review_dir,
        html_path,
        decision_sha256=decision_sha256,
    )
    assert {item["path"] for item in manifest["visual_closure_artifacts"]} == {
        "visual_audit_result.json",
        "visual_inventory.json",
    }
    metadata = _metadata(review_dir, html_path)
    assert validate_formal_delivery_manifest(metadata, _delivery_config()) == (True, "")

    visual_inventory.write_text('{"assets": ["changed"]}', encoding="utf-8")
    ok, reason = validate_formal_delivery_manifest(metadata, _delivery_config())
    assert ok is False
    assert "visual closure artifact hash mismatch: visual_inventory.json" in reason


def test_manifest_rejects_html_without_current_markdown_hash(tmp_path):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    report_path.write_text("# 正式复审报告\n", encoding="utf-8")
    html_path.write_text("<html><body>unbound</body></html>", encoding="utf-8")

    try:
        build_formal_delivery_manifest(review_dir, html_path)
    except ValueError as exc:
        assert "source Markdown SHA256" in str(exc)
    else:
        raise AssertionError("unbound HTML was accepted for formal delivery")


def test_manifest_rejects_missing_or_open_visual_closure(tmp_path):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    report_path.write_text("# 正式复审报告\n", encoding="utf-8")
    _write_bound_html(report_path, html_path)
    decision_sha256 = _write_final_decision(review_dir)

    try:
        build_formal_delivery_manifest(review_dir, html_path, decision_sha256=decision_sha256)
    except ValueError as exc:
        assert "exactly one visual audit result" in str(exc)
    else:
        raise AssertionError("missing visual audit result was accepted for formal delivery")

    result = build_visual_audit_result(review_dir, [], [], review_lane="strict")
    result["status"] = "prepared"
    (review_dir / "visual_audit_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        build_formal_delivery_manifest(review_dir, html_path, decision_sha256=decision_sha256)
    except ValueError as exc:
        assert "visual audit result is not closed" in str(exc)
    else:
        raise AssertionError("open visual audit result was accepted for formal delivery")


def test_manifest_rejects_final_decision_changed_after_sealing(tmp_path):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    report_path.write_text("# 正式复审报告\n\n审核结论。\n", encoding="utf-8")
    _write_bound_html(report_path, html_path)
    _write_closed_visual_result(review_dir)
    decision_sha256 = _write_final_decision(review_dir)
    build_formal_delivery_manifest(review_dir, html_path, decision_sha256=decision_sha256)
    metadata = _metadata(review_dir, html_path)
    assert validate_formal_delivery_manifest(metadata, _delivery_config()) == (True, "")

    (review_dir / "final_decision.json").write_text('{"status":"changed"}', encoding="utf-8")
    ok, reason = validate_formal_delivery_manifest(metadata, _delivery_config())
    assert ok is False
    assert "hash mismatch: final_decision" in reason


def test_wecom_blocks_before_network_without_delivery_manifest(tmp_path, monkeypatch):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    config_path = tmp_path / "notification.json"
    config_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "enabled_task_types": ["audit"],
                "provider": "wecom",
                "webhook_url": "https://example.invalid/webhook",
                "wecom_file": {"enabled": False},
                "wecom_formal_audit_gate": {"enabled": True, "marker_keys": ["formal_audit"]},
                "formal_delivery_gate": {"enabled": True},
                "release_attestation_gate": {"enabled": False},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(notification_client, "send_webhook", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network must not run")))
    metadata = _metadata(review_dir, html_path)
    ok, reason = notification_client.send_notification(
        task_type="audit", task_name="audit", status="completed", summary="done", metadata=metadata, config_arg=str(config_path)
    )
    assert ok is False
    assert reason.startswith("formal delivery blocked:")


def test_wecom_upload_refuses_bytes_changed_after_manifest(tmp_path):
    html_path = tmp_path / "report.html"
    html_path.write_text("before", encoding="utf-8")
    expected_sha256 = hashlib.sha256(html_path.read_bytes()).hexdigest()
    html_path.write_text("after", encoding="utf-8")

    try:
        notification_client._wecom_upload_file("not-used", html_path, expected_sha256=expected_sha256)
    except RuntimeError as exc:
        assert "do not match formal delivery manifest" in str(exc)
    else:  # pragma: no cover - the network must not be reached for a bad hash
        raise AssertionError("changed HTML was not blocked before upload")


def test_formal_delivery_rejects_conflicting_html_metadata_aliases(tmp_path):
    review_dir = tmp_path / "26YDELIVERY"
    review_dir.mkdir()
    report_path = review_dir / "final_review_report.md"
    html_path = review_dir / "26YDELIVERY_audit_report.html"
    other_html_path = review_dir / "other_audit_report.html"
    report_path.write_text("# 正式复审报告\n\n审核结论。\n", encoding="utf-8")
    _write_bound_html(report_path, html_path)
    other_html_path.write_bytes(html_path.read_bytes())
    _write_closed_visual_result(review_dir)
    decision_sha256 = _write_final_decision(review_dir)
    build_formal_delivery_manifest(
        review_dir,
        html_path,
        decision_sha256=decision_sha256,
    )
    metadata = _metadata(review_dir, html_path)
    metadata["HTML"] = str(other_html_path)

    ok, reason = validate_formal_delivery_manifest(metadata, _delivery_config())

    assert ok is False
    assert "HTML metadata aliases conflict" in reason


def test_notification_html_path_resolver_rejects_conflicting_aliases(tmp_path):
    html_path = tmp_path / "report.html"
    other_html_path = tmp_path / "other.html"
    html_path.write_text("first", encoding="utf-8")
    other_html_path.write_text("second", encoding="utf-8")

    with pytest.raises(RuntimeError, match="HTML metadata aliases conflict"):
        notification_client._find_html_report_path(
            {"html_report": str(html_path), "HTML": str(other_html_path)}
        )


def test_feishu_upload_refuses_bytes_changed_after_manifest(tmp_path):
    html_path = tmp_path / "report.html"
    html_path.write_text("before", encoding="utf-8")
    expected_sha256 = hashlib.sha256(html_path.read_bytes()).hexdigest()
    html_path.write_text("after", encoding="utf-8")

    with pytest.raises(RuntimeError, match="do not match formal delivery manifest"):
        notification_client._feishu_upload_file(
            "not-used",
            html_path,
            expected_sha256=expected_sha256,
        )


def test_feishu_upload_uses_manifest_verified_byte_snapshot(tmp_path, monkeypatch):
    html_path = tmp_path / "report.html"
    html_path.write_bytes(b"manifest-bound-bytes")
    expected_sha256 = hashlib.sha256(html_path.read_bytes()).hexdigest()
    captured: dict[str, bytes] = {}

    def fake_multipart(fields, file_field, file_path, *, file_bytes=None):
        assert fields["file_name"] == html_path.name
        assert file_field == "file"
        assert file_path == html_path
        assert file_bytes == b"manifest-bound-bytes"
        html_path.write_bytes(b"changed-after-snapshot")
        return b"multipart:" + file_bytes, "test-boundary"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"code": 0, "data": {"file_key": "file-key"}}'

    def fake_open_url(req, *, timeout):
        assert timeout == 60
        captured["body"] = req.data
        return FakeResponse()

    monkeypatch.setattr(notification_client, "_multipart_body", fake_multipart)
    monkeypatch.setattr(notification_client, "_open_url", fake_open_url)

    file_key = notification_client._feishu_upload_file(
        "token",
        html_path,
        expected_sha256=expected_sha256,
    )

    assert file_key == "file-key"
    assert captured["body"] == b"multipart:manifest-bound-bytes"
    assert html_path.read_bytes() == b"changed-after-snapshot"
