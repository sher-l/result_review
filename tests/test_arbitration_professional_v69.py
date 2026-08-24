#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Focused regression tests for the v7.0 arbitration/professional contracts."""

from __future__ import annotations

import json

from convergence_compare import build_arbitration_queue, match_findings
from professional_audit_contracts import (
    HIGH_RISK_MINIMUM_PACKAGES,
    artifact_filename,
    build_arbitration_resolution_v2,
    build_dataset_scope_matrix,
    build_high_risk_module_contract,
    build_method_code_matrix,
    build_ml_lineage,
    build_statistical_flow_graph,
    propagate_statistical_taint,
    validate_arbitration_resolution_v2,
    validate_dataset_scope_matrix,
    validate_final_report_arbitration_binding,
    validate_high_risk_module_contract,
    validate_method_code_matrix,
    validate_ml_lineage,
    validate_statistical_flow_graph,
)
from validate_professional_contracts import validate_review_professional_contracts


def _finding(identifier: str, *, location: str = "1.2", **extra) -> dict:
    payload = {
        "id": identifier,
        "severity": "MAJOR",
        "dimension": "D4",
        "location": location,
        "description": f"finding {identifier}",
        "evidence": "structured evidence",
        "rule": f"R-{identifier}",
        "source_type": "code",
        "source_path": f"code/{identifier}.R",
        "locator": "line 1",
        "quote_or_value": identifier,
    }
    payload.update(extra)
    return payload


def test_match_findings_emits_raw_identity_cluster_key_and_semantic_trace():
    semantic = {
        "module": "ml",
        "claim": "external validation",
        "error_mechanism": "validation leakage",
        "evidence_object": "auc table",
        "repair_path": "rebuild split",
        "protected_category": "validation_leakage",
    }
    groups = match_findings(
        {
            "A": [_finding("A-1", location="2.1", **semantic)],
            "B": [_finding("B-1", location="9.4", **semantic)],
        }
    )

    assert len(groups) == 1
    group = groups[0]
    assert group["match_mode"] == "semantic_tuple"
    assert group["cluster_key"].startswith("ck:")
    assert len(group["pairwise_checks"]) == 1
    assert group["pairwise_checks"][0]["exact_semantic_tuple"] is True
    assert all(finding["raw_finding_id"].startswith("rf:") for finding in group["findings"].values())


def test_match_findings_protected_veto_overrides_exact_finding_key():
    shared_key = "fk:historical-collision"
    groups = match_findings(
        {
            "A": [_finding("A-1", finding_key=shared_key, protected_category="dataset_identity")],
            "B": [_finding("B-1", finding_key=shared_key, protected_category="qc_count_invariant")],
        }
    )

    assert len(groups) == 2
    assert all(len(group["agents"]) == 1 for group in groups)
    vetoes = [
        check["veto_codes"]
        for group in groups
        for rejected in group["rejected_candidates"]
        for check in rejected["checks"]
    ]
    assert any("protected_category_mismatch" in codes for codes in vetoes)


def test_match_findings_similarity_fallback_is_complete_link():
    groups = match_findings(
        {
            "A": [_finding("A", location="1.2")],
            "B": [_finding("B", location="1.2.1")],
            "C": [_finding("C", location="1.2.2")],
        },
        threshold=0.4,
    )

    assert sorted(len(group["agents"]) for group in groups) == [1, 2]
    pair_group = next(group for group in groups if len(group["agents"]) == 2)
    assert pair_group["match_mode"] == "similarity_candidate"
    assert pair_group["rejected_candidates"]


def test_arbitration_queue_keeps_complete_single_major_finding():
    finding = _finding("A-1")
    queue = build_arbitration_queue(
        {
            "consensus": [],
            "majority": [],
            "divergent": [],
            "single": [
                {
                    "finding_key": "fk:single-major",
                    "agents": {"A"},
                    "findings": {"A": finding},
                    "match_mode": "exact",
                }
            ],
        }
    )

    assert len(queue) == 1
    assert queue[0]["severity"] == "MAJOR"
    assert queue[0]["route"] == "single"


def _valid_arbitration() -> dict:
    semantic_tuple = {
        "module": "ml",
        "claim": "external validation",
        "error_mechanism": "validation leakage",
        "evidence_object": "auc table",
        "repair_path": "rebuild split",
    }
    return build_arbitration_resolution_v2(
        "26TEST001F",
        raw_dispositions=[
            {"raw_finding_id": "rf:a", "finding_key": "fk:a", "decision": "merge", "canonical_ids": ["CF-001"], "reason": "same issue"},
            {"raw_finding_id": "rf:b", "finding_key": "fk:b", "decision": "merge", "canonical_ids": ["CF-001"], "reason": "same issue"},
        ],
        canonical_findings=[
            {
                "canonical_id": "CF-001",
                "finding_key": "fk:a",
                "severity": "MAJOR",
                "source_raw_finding_ids": ["rf:a", "rf:b"],
                "evidence_refs": [{"path": "evidence.json", "locator": "row 1"}],
                **semantic_tuple,
            }
        ],
        merge_decisions=[
            {
                "decision_id": "MD-001",
                "member_raw_finding_ids": ["rf:a", "rf:b"],
                "canonical_ids": ["CF-001"],
                "semantic_tuple": semantic_tuple,
                "pairwise_checks": [{"left": "rf:a", "right": "rf:b", "compatible": True}],
                "reason": "same semantic issue",
            }
        ],
        inputs=[{"path": "agent_results.json", "sha256": "a" * 64}],
        status="leader_confirmed",
    )


def test_arbitration_v2_enforces_raw_mapping_and_final_decision_consistency():
    payload = _valid_arbitration()
    validation = validate_arbitration_resolution_v2(
        payload,
        final_decision={"canonical_finding_count": 1, "severity_counts": {"MAJOR": 1}},
    )
    assert validation["valid"] is True
    assert validation["candidates"] == []

    payload["raw_dispositions"].append(dict(payload["raw_dispositions"][0]))
    payload["raw_finding_count"] = 3
    payload["unresolved_count"] = 1
    invalid = validate_arbitration_resolution_v2(payload)
    assert invalid["valid"] is False
    assert any("disposed more than once" in error for error in invalid["errors"])
    assert any("unresolved_count=0" in error for error in invalid["errors"])


def test_arbitration_v2_requires_resolution_for_duplicate_formal_dataset_findings():
    semantic = {
        "module": "data",
        "claim": "GSE89408 training dataset identity",
        "error_mechanism": "dataset identifier conflict",
        "evidence_object": "report dataset source sentence",
        "repair_path": "confirm the single GEO identifier",
    }
    payload = build_arbitration_resolution_v2(
        "26TEST001F",
        raw_dispositions=[
            {"raw_finding_id": "rf:a", "decision": "accept", "canonical_ids": ["CF-001"], "reason": "source conflict"},
            {"raw_finding_id": "rf:b", "decision": "accept", "canonical_ids": ["CF-002"], "reason": "traceability impact"},
        ],
        canonical_findings=[
            {
                "canonical_id": "CF-001",
                "severity": "MAJOR",
                "source_raw_finding_ids": ["rf:a"],
                "evidence_refs": [{"path": "report_text.txt", "locator": "L13"}],
                **semantic,
            },
            {
                "canonical_id": "CF-002",
                "severity": "MAJOR",
                "source_raw_finding_ids": ["rf:b"],
                "evidence_refs": [{"path": "report_text.txt", "locator": "L12"}],
                **{**semantic, "claim": "GSE89408 training traceability"},
            },
        ],
        inputs=[{"path": "agent_results.json", "sha256": "a" * 64}],
        status="leader_confirmed",
    )

    blocked = validate_arbitration_resolution_v2(payload)
    assert blocked["valid"] is False
    assert any("duplicate formal finding candidate requires merge" in error for error in blocked["errors"])

    payload["independence_decisions"] = [
        {
            "canonical_ids": ["CF-001", "CF-002"],
            "reason": "Different source systems require separate remediation.",
            "distinguishing_dimensions": ["claim"],
            "independence_evidence_refs": [
                {"canonical_id": "CF-001", "path": "report_text.txt", "locator": "L13"},
                {"canonical_id": "CF-002", "path": "report_text.txt", "locator": "L12"},
            ],
        }
    ]
    allowed = validate_arbitration_resolution_v2(payload)
    assert allowed["valid"] is True


def _bound_final_report() -> str:
    return """# 最终审核报告

| 编号 | 严重度 | 核心问题 | 原报告位置 | 交付证据 | 修订要求 |
| --- | --- | --- | --- | --- | --- |
| F-01 | MAJOR | validation leakage | §1.2 | evidence.json:row 1 | rebuild split |

| 分析点 | 对应问题 | 核心问题 | 原报告位置 | 交付证据 | 修订要求 | 可搜索定位 |
| --- | --- | --- | --- | --- | --- | --- |
| fk:a | F-01 | validation leakage | §1.2 | evidence.json:row 1 | rebuild split | F-01 |
| fk:b | F-01 | validation leakage | §1.2 | evidence.json:row 1 | rebuild split | F-01 |
"""


def test_final_report_binding_requires_retained_crosswalk_and_rejects_revoked_items():
    final_decision = {
        "canonical_finding_count": 1,
        "severity_counts": {"MAJOR": 1},
    }
    valid = validate_final_report_arbitration_binding(
        _bound_final_report(), _valid_arbitration(), final_decision
    )
    assert valid["valid"] is True
    assert valid["bindings"][0]["canonical_id"] == "CF-001"
    assert valid["bindings"][0]["report_id"] == "F-01"

    severity_drift = validate_final_report_arbitration_binding(
        _bound_final_report().replace("| F-01 | MAJOR", "| F-01 | CRITICAL"),
        _valid_arbitration(),
        final_decision,
    )
    assert severity_drift["valid"] is False
    assert any("severity differs" in error for error in severity_drift["errors"])

    revoked = validate_final_report_arbitration_binding(
        _bound_final_report() + "\n#### R-01 fk:a（原 F-01）\n- 裁定：撤销；不计入正式发现。\n",
        _valid_arbitration(),
        final_decision,
    )
    assert revoked["valid"] is False
    assert any("revoked raw finding key" in error for error in revoked["errors"])


def test_final_report_binding_rejects_crosswalk_reference_placeholders():
    report = _bound_final_report().replace(
        "| fk:a | F-01 | validation leakage | §1.2 | evidence.json:row 1 | rebuild split | F-01 |",
        "| fk:a | F-01 | 见 F-01 具体错误 | 见 F-01 具体错误 | 见 F-01 具体错误 | 见 F-01 具体错误 | F-01 |",
    )

    blocked = validate_final_report_arbitration_binding(
        report,
        _valid_arbitration(),
        {"canonical_finding_count": 1, "severity_counts": {"MAJOR": 1}},
    )

    assert blocked["valid"] is False
    assert any("non-concrete 核心问题" in error for error in blocked["errors"])


def test_final_report_binding_requires_brief_summaries_and_finding_jump():
    concise = validate_final_report_arbitration_binding(
        _bound_final_report(),
        _valid_arbitration(),
        {"canonical_finding_count": 1, "severity_counts": {"MAJOR": 1}},
    )
    assert concise["valid"] is True

    verbose = validate_final_report_arbitration_binding(
        _bound_final_report().replace("validation leakage", "x" * 81),
        _valid_arbitration(),
        {"canonical_finding_count": 1, "severity_counts": {"MAJOR": 1}},
    )
    assert verbose["valid"] is False
    assert any("summary exceeds" in error for error in verbose["errors"])


def test_enforced_professional_gate_runs_final_report_binding_after_decision_seal(tmp_path):
    review_dir = tmp_path / "26TEST001F"
    arbitration_path = review_dir / "agent_results" / "arbitration" / "arbitration_resolution.json"
    arbitration_path.parent.mkdir(parents=True)
    arbitration_path.write_text(json.dumps(_valid_arbitration()), encoding="utf-8")
    (review_dir / "final_review_report.md").write_text(_bound_final_report(), encoding="utf-8")
    (review_dir / "convergence_report.json").write_text(
        json.dumps({"classified": {"single": [{"raw_finding_ids": ["rf:a", "rf:b"]}]}}),
        encoding="utf-8",
    )
    (review_dir / "final_decision.json").write_text(
        json.dumps(
            {
                "status": "leader_confirmed",
                "canonical_finding_count": 1,
                "severity_counts": {"MAJOR": 1},
                "sources": {
                    "arbitration_resolution": {"path": "agent_results/arbitration/arbitration_resolution.json"},
                    "final_review_report": {"path": "final_review_report.md"},
                },
            }
        ),
        encoding="utf-8",
    )
    policy = {
        "audit_contract_policy": {"decision_json": "final_decision.json"},
        "professional_contract_policy": {
            "arbitration_mode": "enforce",
            "checker_modes": {name: "off" for name in (
                "dataset_scope", "statistical_flow", "method_code", "ml_lineage"
            )},
            "structured_artifacts": {},
        },
    }

    valid = validate_review_professional_contracts(review_dir, policy)
    assert valid["checks"]["final_report_binding"]["valid"] is True
    assert valid["blocking"] is False

    (review_dir / "final_review_report.md").write_text(
        _bound_final_report().replace(
            "| fk:a | F-01 | validation leakage | §1.2 | evidence.json:row 1 | rebuild split | F-01 |",
            "| fk:a |  | validation leakage | §1.2 | evidence.json:row 1 | rebuild split | F-01 |",
        ),
        encoding="utf-8",
    )
    blocked = validate_review_professional_contracts(review_dir, policy)
    assert blocked["checks"]["final_report_binding"]["valid"] is False
    assert blocked["blocking"] is True


def test_professional_review_gate_surfaces_shadow_and_blocks_enforce(tmp_path):
    review_dir = tmp_path / "26TEST001F"
    arbitration_path = review_dir / "agent_results" / "arbitration" / "arbitration_resolution.json"
    arbitration_path.parent.mkdir(parents=True)
    arbitration_path.write_text(
        json.dumps(_valid_arbitration(), ensure_ascii=False), encoding="utf-8"
    )
    (review_dir / "final_decision.json").write_text(
        json.dumps(
            {
                "canonical_finding_count": 1,
                "severity_counts": {"MAJOR": 1},
                "sources": {
                    "arbitration_resolution": {
                        "path": "agent_results/arbitration/arbitration_resolution.json"
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy = {
        "audit_contract_policy": {"decision_json": "final_decision.json"},
        "professional_contract_policy": {
            "arbitration_mode": "shadow",
            "checker_modes": {name: "shadow" for name in (
                "dataset_scope", "statistical_flow", "method_code", "ml_lineage"
            )},
            "structured_artifacts": {
                "dataset_scope": "dataset_scope_matrix.json",
                "statistical_flow": "statistical_flow_graph.json",
                "method_code": "method_code_matrix.json",
                "ml_lineage": "ml_lineage.json",
            },
        },
    }

    shadow = validate_review_professional_contracts(review_dir, policy)
    assert shadow["checks"]["arbitration"]["valid"] is True
    assert shadow["would_block"] is True
    assert shadow["blocking"] is False

    policy["professional_contract_policy"]["checker_modes"]["dataset_scope"] = "enforce"
    enforce = validate_review_professional_contracts(review_dir, policy)
    assert enforce["blocking"] is True


def test_missing_or_invalid_arbitration_mode_fails_closed(tmp_path):
    review_dir = tmp_path / "26TEST001F"
    review_dir.mkdir()

    for professional in ({}, {"arbitration_mode": "invalid"}):
        result = validate_review_professional_contracts(
            review_dir,
            {
                "professional_contract_policy": professional,
                "audit_contract_policy": {},
            },
        )
        assert result["checks"]["arbitration"]["mode"] == "enforce"
        assert result["checks"]["arbitration"]["blocking"] is True
        assert result["blocking"] is True


def test_enforced_arbitration_requires_every_convergence_raw_finding(tmp_path):
    review_dir = tmp_path / "26TEST001F"
    arbitration_path = review_dir / "agent_results" / "arbitration" / "arbitration_resolution.json"
    arbitration_path.parent.mkdir(parents=True)
    arbitration_path.write_text(
        json.dumps(_valid_arbitration(), ensure_ascii=False), encoding="utf-8"
    )
    (review_dir / "convergence_report.json").write_text(
        json.dumps(
            {
                "classified": {
                    "single": [
                        {"raw_finding_ids": ["rf:a", "rf:b", "rf:missing"]}
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy = {
        "audit_contract_policy": {"decision_json": "final_decision.json"},
        "professional_contract_policy": {
            "arbitration_mode": "enforce",
            "checker_modes": {name: "off" for name in (
                "dataset_scope", "statistical_flow", "method_code", "ml_lineage"
            )},
            "structured_artifacts": {},
        },
    }

    result = validate_review_professional_contracts(review_dir, policy)

    assert result["blocking"] is True
    assert "rf:missing" in result["checks"]["arbitration"]["validation"]["errors"][0]


def test_dataset_contract_separates_structural_errors_from_professional_candidates():
    payload = build_dataset_scope_matrix(
        "26TEST001F",
        [
            {
                "dataset_id": "GSE000001",
                "report_declaration": {"present": True, "refs": ["report:L10"]},
                "source_input": {"status": "missing", "refs": []},
                "code_reads": [],
                "code_writes": [],
                "delivery_outputs": [],
                "figure_or_table_claims": [],
            }
        ],
    )
    validation = validate_dataset_scope_matrix(payload)

    assert validation["valid"] is True
    assert [item["code"] for item in validation["candidates"]] == ["DATASET_ISOLATED_DECLARATION"]
    assert all("severity" not in item for item in validation["candidates"])
    assert artifact_filename("dataset_scope") == "dataset_scope_matrix.json"


def test_statistical_flow_propagates_rerun_state_but_only_emits_candidates():
    payload = build_statistical_flow_graph(
        "26TEST001F",
        nodes=[
            {"node_id": "deg", "selection_field": "raw_p", "formal_selection": True, "taint_status": "unknown"},
            {"node_id": "gsea", "selection_field": "not_applicable", "taint_status": "unknown"},
        ],
        edges=[{"from_node": "deg", "to_node": "gsea", "transformation": "gene list"}],
    )
    propagated = propagate_statistical_taint(payload)
    validation = validate_statistical_flow_graph(payload)

    assert {node["taint_status"] for node in propagated["nodes"]} == {"requires_rerun"}
    assert validation["valid"] is True
    assert len(validation["candidates"]) == 2
    assert all("severity" not in item for item in validation["candidates"])


def test_method_and_ml_contracts_emit_candidates_without_final_judgment():
    method = build_method_code_matrix(
        "26TEST001F",
        [
            {
                "analysis_id": "correlation",
                "report_method": {"name": "Spearman"},
                "implementation": {"function": "cor", "method": "pearson"},
                "parameters": {},
                "outputs": [],
                "match_status": "mismatch",
                "differences": ["method"],
            }
        ],
    )
    ml = build_ml_lineage(
        "26TEST001F",
        [
            {
                "analysis_id": "model",
                "datasets": [{"dataset_id": "GSE000001", "role": "development"}],
                "split_events": [{"split_id": "split-1", "method": "holdout", "seed": 1}],
                "predictions": [{"prediction_id": "pred-1", "data_role": "holdout", "sample_identity_hash": "sha256:x"}],
                "metrics": [{"metric": "AUC", "prediction_id": "pred-1", "data_role": "holdout", "published": True}],
                "feature_selection": [{"scope": "pre_split", "supervised": True}],
                "fits": [{"fit_id": "fit-1", "split_id": "split-1"}],
                "claims": [{"claim_id": "claim-1", "metric": "AUC"}],
            }
        ],
    )

    method_validation = validate_method_code_matrix(method)
    ml_validation = validate_ml_lineage(ml)
    assert method_validation["valid"] is True
    assert ml_validation["valid"] is True
    assert method_validation["candidates"][0]["code"] == "METHOD_CODE_REVIEW"
    assert ml_validation["candidates"][0]["code"] == "ML_FEATURE_SELECTION_LEAKAGE_REVIEW"
    assert all("severity" not in item for item in method_validation["candidates"] + ml_validation["candidates"])


def test_graphban_schema_comes_from_policy_and_missing_evidence_is_candidate_only():
    required = HIGH_RISK_MINIMUM_PACKAGES["graphban_virtual_screening"]
    package = [
        {"item_id": item_id, "status": "missing" if item_id == "checkpoint_or_weights" else "present", "evidence_refs": []}
        for item_id in required
    ]
    dimensions = {
        key: {"status": "unknown", "evidence_refs": [], "reason": "pending professional review"}
        for key in ("module_exists", "evidence_sufficient", "reproducible", "conclusion_not_overstated")
    }
    payload = build_high_risk_module_contract(
        "26TEST001F",
        [{"module_id": "graphban-1", "module_type": "graphban_virtual_screening", "dimensions": dimensions, "minimum_evidence_package": package}],
    )
    validation = validate_high_risk_module_contract(payload)

    assert validation["valid"] is True
    codes = {item["code"] for item in validation["candidates"]}
    assert codes == {"HIGH_RISK_DIMENSION_REVIEW", "HIGH_RISK_EVIDENCE_REVIEW"}
    assert all("severity" not in item for item in validation["candidates"])
