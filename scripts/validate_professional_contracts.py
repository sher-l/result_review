#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Validate arbitration v2 and policy-owned professional audit artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from audit_contract import atomic_write_json
from audit_runtime import append_event
from policy_loader import load_policy
from professional_audit_contracts import (
    validate_arbitration_resolution_v2,
    validate_dataset_scope_matrix,
    validate_final_report_arbitration_binding,
    validate_method_code_matrix,
    validate_ml_lineage,
    validate_statistical_flow_graph,
)


VALIDATORS = {
    "dataset_scope": validate_dataset_scope_matrix,
    "statistical_flow": validate_statistical_flow_graph,
    "method_code": validate_method_code_matrix,
    "ml_lineage": validate_ml_lineage,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate arbitration and professional structured audit contracts."
    )
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    return parser.parse_args()


def _read_object(path: Path) -> tuple[dict | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"missing {path.name}"
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"invalid {path.name}: {exc}"
    if not isinstance(payload, dict):
        return None, f"{path.name} root must be an object"
    return payload, None


def _safe_source_path(review_dir: Path, final_decision: dict | None) -> tuple[Path, str | None]:
    default = review_dir / "agent_results" / "arbitration" / "arbitration_resolution.json"
    if not isinstance(final_decision, dict):
        return default, None
    source = final_decision.get("sources", {}).get("arbitration_resolution", {})
    raw_path = source.get("path") if isinstance(source, dict) else None
    if not isinstance(raw_path, str) or not raw_path.strip():
        return default, None
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        return default, "final_decision arbitration source path must be review-relative"
    resolved = (review_dir / relative).resolve()
    if not resolved.is_relative_to(review_dir.resolve()):
        return default, "final_decision arbitration source path escapes review directory"
    return resolved, None


def _safe_final_report_path(review_dir: Path, final_decision: dict | None) -> tuple[Path, str | None]:
    default = review_dir / "final_review_report.md"
    if not isinstance(final_decision, dict):
        return default, None
    source = final_decision.get("sources", {}).get("final_review_report", {})
    raw_path = source.get("path") if isinstance(source, dict) else None
    if not isinstance(raw_path, str) or not raw_path.strip():
        return default, "final_decision final review report source path missing"
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        return default, "final_decision final review report source path must be review-relative"
    resolved = (review_dir / relative).resolve()
    if not resolved.is_relative_to(review_dir.resolve()):
        return default, "final_decision final review report source path escapes review directory"
    return resolved, None


def _mode(value: object, *, default: str = "shadow") -> str:
    normalized = str(value or default).strip().lower()
    return normalized if normalized in {"off", "shadow", "enforce"} else default


def validate_arbitration_coverage(review_dir: Path, arbitration: dict) -> list[str]:
    """Require the final resolution to disposition every converged raw finding."""
    convergence, convergence_error = _read_object(review_dir / "convergence_report.json")
    if convergence_error:
        return [f"arbitration coverage requires convergence_report.json: {convergence_error}"]

    classified = convergence.get("classified") if isinstance(convergence, dict) else None
    if not isinstance(classified, dict):
        return ["arbitration coverage requires convergence_report.json.classified"]

    expected_ids: set[str] = set()
    for groups in classified.values():
        if not isinstance(groups, list):
            return ["arbitration coverage requires classified groups to be lists"]
        for group in groups:
            raw_ids = group.get("raw_finding_ids") if isinstance(group, dict) else None
            if not isinstance(raw_ids, list) or not all(isinstance(raw_id, str) and raw_id for raw_id in raw_ids):
                return ["arbitration coverage requires each group to provide raw_finding_ids"]
            expected_ids.update(raw_ids)

    dispositions = arbitration.get("raw_dispositions") if isinstance(arbitration, dict) else None
    if not isinstance(dispositions, list):
        return ["arbitration coverage requires raw_dispositions"]
    actual_ids = {
        item.get("raw_finding_id")
        for item in dispositions
        if isinstance(item, dict) and isinstance(item.get("raw_finding_id"), str)
    }

    errors: list[str] = []
    missing = sorted(expected_ids - actual_ids)
    unexpected = sorted(actual_ids - expected_ids)
    if missing:
        errors.append(f"arbitration does not disposition convergence raw findings: {', '.join(missing)}")
    if unexpected:
        errors.append(f"arbitration dispositions are absent from convergence findings: {', '.join(unexpected)}")
    return errors


def validate_review_professional_contracts(review_dir: Path, policy: dict) -> dict:
    professional = policy.get("professional_contract_policy", {})
    if not isinstance(professional, dict):
        professional = {}
    decision_policy = policy.get("audit_contract_policy", {})
    if not isinstance(decision_policy, dict):
        decision_policy = {}
    decision_path = review_dir / str(decision_policy.get("decision_json", "final_decision.json"))
    final_decision, decision_error = _read_object(decision_path)

    checks: dict[str, dict] = {}
    arbitration_mode = _mode(
        professional.get("arbitration_mode", "enforce"),
        default="enforce",
    )
    arbitration_path, path_error = _safe_source_path(review_dir, final_decision)
    arbitration, arbitration_error = _read_object(arbitration_path)
    if arbitration_mode == "off":
        arbitration_validation = {"valid": True, "errors": [], "candidates": []}
    elif path_error or arbitration_error:
        arbitration_validation = {
            "valid": False,
            "errors": [error for error in (path_error, arbitration_error) if error],
            "candidates": [],
        }
    else:
        arbitration_validation = validate_arbitration_resolution_v2(
            arbitration or {}, final_decision=final_decision
        )
        if arbitration_mode == "enforce" and arbitration_validation.get("valid", False):
            coverage_errors = validate_arbitration_coverage(review_dir, arbitration or {})
            if coverage_errors:
                arbitration_validation = {
                    **arbitration_validation,
                    "valid": False,
                    "errors": [*arbitration_validation.get("errors", []), *coverage_errors],
                }
    checks["arbitration"] = {
        "mode": arbitration_mode,
        "path": str(arbitration_path),
        "valid": bool(arbitration_validation.get("valid")),
        "would_block": arbitration_mode != "off" and not arbitration_validation.get("valid", False),
        "blocking": arbitration_mode == "enforce" and not arbitration_validation.get("valid", False),
        "validation": arbitration_validation,
    }

    report_binding_path, report_binding_path_error = _safe_final_report_path(review_dir, final_decision)
    if arbitration_mode == "off":
        report_binding_validation = {"valid": True, "errors": [], "candidates": []}
    elif not isinstance(final_decision, dict) or final_decision.get("status") != "leader_confirmed":
        # The audit contract independently blocks an unsealed decision.  Defer
        # the report/decision binding until a source-stable final decision exists.
        report_binding_validation = {
            "valid": True,
            "errors": [],
            "candidates": [],
            "deferred": "requires leader_confirmed final_decision",
        }
    elif report_binding_path_error:
        report_binding_validation = {
            "valid": False,
            "errors": [report_binding_path_error],
            "candidates": [],
        }
    elif not arbitration_validation.get("valid", False):
        report_binding_validation = {
            "valid": False,
            "errors": ["final-report binding requires a valid arbitration resolution"],
            "candidates": [],
        }
    else:
        try:
            report_text = report_binding_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            report_binding_validation = {
                "valid": False,
                "errors": [f"missing {report_binding_path.name}"],
                "candidates": [],
            }
        except (OSError, UnicodeError) as exc:
            report_binding_validation = {
                "valid": False,
                "errors": [f"invalid {report_binding_path.name}: {exc}"],
                "candidates": [],
            }
        else:
            report_binding_validation = validate_final_report_arbitration_binding(
                report_text, arbitration or {}, final_decision=final_decision
            )
    checks["final_report_binding"] = {
        "mode": arbitration_mode,
        "path": str(report_binding_path),
        "valid": bool(report_binding_validation.get("valid")),
        "would_block": arbitration_mode != "off" and not report_binding_validation.get("valid", False),
        "blocking": arbitration_mode == "enforce" and not report_binding_validation.get("valid", False),
        "validation": report_binding_validation,
    }

    checker_modes = professional.get("checker_modes", {})
    if not isinstance(checker_modes, dict):
        checker_modes = {}
    artifacts = professional.get("structured_artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
    for contract_type, validator in VALIDATORS.items():
        mode = _mode(checker_modes.get(contract_type, "shadow"))
        filename = str(artifacts.get(contract_type, f"{contract_type}.json"))
        artifact_path = review_dir / filename
        payload, read_error = _read_object(artifact_path)
        if mode == "off":
            validation = {"valid": True, "errors": [], "candidates": []}
        elif read_error:
            validation = {"valid": False, "errors": [read_error], "candidates": []}
        else:
            validation = validator(payload or {})
        checks[contract_type] = {
            "mode": mode,
            "path": str(artifact_path),
            "valid": bool(validation.get("valid")),
            "would_block": mode != "off" and not validation.get("valid", False),
            "blocking": mode == "enforce" and not validation.get("valid", False),
            "validation": validation,
        }

    blocking = any(check["blocking"] for check in checks.values())
    would_block = any(check["would_block"] for check in checks.values())
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "review_dir": str(review_dir),
        "decision_path": str(decision_path),
        "decision_read_error": decision_error or "",
        "valid": all(check["valid"] for check in checks.values()),
        "would_block": would_block,
        "blocking": blocking,
        "checks": checks,
    }


def main() -> int:
    args = parse_args()
    review_dir = Path(args.review_dir)
    if not review_dir.is_dir():
        raise FileNotFoundError(f"Review directory does not exist: {review_dir}")
    policy = load_policy()
    professional = policy.get("professional_contract_policy", {})
    if not isinstance(professional, dict):
        professional = {}
    result = validate_review_professional_contracts(review_dir, policy)
    result_path = review_dir / str(
        professional.get("validation_json", "professional_contract_validation.json")
    )
    atomic_write_json(result_path, result)
    append_event(
        review_dir,
        "professional_contracts_validated",
        actor="validate_professional_contracts",
        status="error" if result["blocking"] else "success",
        outputs=[str(result_path)],
        details={"would_block": result["would_block"], "blocking": result["blocking"]},
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["blocking"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
