#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Structured professional evidence contracts used by framework v7.0.

Validators distinguish machine-enforceable structural errors from domain
observations.  Automated domain observations are always emitted as candidates
without a severity or final disposition; arbitration remains authoritative.
"""

from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
import re
from typing import Any, Iterable

from policy_loader import load_policy


POLICY = load_policy()
PROFESSIONAL_POLICY = POLICY.get("professional_contract_policy", {})
FINAL_REPORT_BINDING_POLICY = PROFESSIONAL_POLICY.get("final_report_binding_gate", {})
HIGH_RISK_POLICY = POLICY.get("high_risk_module_policy", {})
ARBITRATION_SCHEMA_VERSION = str(PROFESSIONAL_POLICY.get("arbitration_schema_version", "2.0"))
STRUCTURED_ARTIFACTS = dict(PROFESSIONAL_POLICY.get("structured_artifacts", {}))
SEMANTIC_MERGE_TUPLE = tuple(PROFESSIONAL_POLICY.get("semantic_merge_tuple", ()))
PROTECTED_MERGE_VETOES = frozenset(PROFESSIONAL_POLICY.get("protected_merge_vetoes", ()))
HIGH_RISK_DIMENSIONS = tuple(HIGH_RISK_POLICY.get("required_dimensions", ()))
HIGH_RISK_MINIMUM_PACKAGES = dict(HIGH_RISK_POLICY.get("minimum_evidence_packages", {}))

VALID_ARBITRATION_STATUSES = {"draft", "in_review", "leader_confirmed"}
VALID_ARBITRATION_DECISIONS = {"accept", "reject", "merge", "split", "adjust"}
VALID_ACTIVITY = {"active", "commented", "unknown"}
VALID_SOURCE_STATUS = {"delivered", "reproducible_fetch", "missing", "not_required", "unknown"}
VALID_TAINT_STATUS = {"clean", "affected", "requires_rerun", "unknown", "not_applicable"}
VALID_MATCH_STATUS = {"match", "mismatch", "partial", "unknown", "not_applicable"}
VALID_LINEAGE_SCOPE = {"pre_split", "train_only", "fold_inner", "unknown", "not_applicable"}
VALID_EVIDENCE_STATUS = {"present", "missing", "unknown", "not_applicable"}
VALID_DIMENSION_STATUS = {"pass", "fail", "unknown", "not_applicable"}
VALID_FINDING_SEVERITIES = {"FATAL", "CRITICAL", "MAJOR", "WARNING", "INFO"}
_DATASET_IDENTIFIER_RE = re.compile(r"\b(?:gse|gpl|gcst|ebi-a)-?[a-z0-9]+\b", re.IGNORECASE)
_FORMAL_REPORT_ID_RE = re.compile(r"^F-\d+$", re.IGNORECASE)
_REVOKED_REPORT_ITEM_RE = re.compile(r"^#{1,6}\s+R-\d+\s+([^\s（(]+)")
_CROSSWALK_FIELD_ALIASES = {
    "核心问题": ("核心问题", "问题", "错误描述", "problem"),
    "原报告位置": ("原报告位置", "位置", "定位", "location"),
    "交付证据": ("交付证据", "证据", "evidence"),
    "修订要求": ("修订要求", "整改要求", "整改", "repair"),
    "可搜索定位": ("可搜索定位", "locator"),
}
_CROSSWALK_REQUIRED_FIELDS = tuple(
    FINAL_REPORT_BINDING_POLICY.get("crosswalk_required_fields", _CROSSWALK_FIELD_ALIASES)
)
_CROSSWALK_SUMMARY_MAX_CHARS = int(FINAL_REPORT_BINDING_POLICY.get("crosswalk_summary_max_chars", 80))
_CROSSWALK_REFERENCE_RE = re.compile(
    r"^(?:(?:请)?(?:见|参见|see|refer\s+to)\s*)?(?:本报告\s*)?F-\d+(?:\s*(?:具体错误|详情|条目))?[。.]?$",
    re.IGNORECASE,
)
_CROSSWALK_EMPTY_VALUES = {"", "-", "—", "n/a", "na", "无", "暂无", "待补充", "待定"}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _candidate(code: str, message: str, path: str, evidence_refs: Iterable[Any] = ()) -> dict:
    """Build a professional-review candidate; deliberately no severity field."""
    return {
        "type": "candidate",
        "code": code,
        "message": message,
        "path": path,
        "evidence_refs": list(evidence_refs),
        "requires_professional_review": True,
    }


def _result(contract_type: str, errors: list[str], candidates: list[dict]) -> dict:
    return {
        "contract_type": contract_type,
        "valid": not errors,
        "errors": errors,
        "candidates": candidates,
    }


def _validate_contract_header(payload: dict, errors: list[str]) -> None:
    if _text(payload.get("schema_version")) != "1.0":
        errors.append("schema_version must be 1.0")
    if not _text(payload.get("project_id")):
        errors.append("project_id missing")


def artifact_filename(contract_type: str) -> str:
    """Return the policy-owned artifact name, raising on an unknown contract."""
    if contract_type not in STRUCTURED_ARTIFACTS:
        raise KeyError(f"unknown professional contract: {contract_type}")
    return STRUCTURED_ARTIFACTS[contract_type]


def build_arbitration_resolution_v2(
    project_id: str,
    raw_dispositions: list[dict],
    canonical_findings: list[dict],
    *,
    merge_decisions: list[dict] | None = None,
    independence_decisions: list[dict] | None = None,
    inputs: list[dict] | None = None,
    status: str = "draft",
    decision_owner: str = "leader",
    unresolved_count: int = 0,
) -> dict:
    """Build, but do not professionally adjudicate, an arbitration v2 object."""
    return {
        "schema_version": ARBITRATION_SCHEMA_VERSION,
        "project_id": project_id,
        "status": status,
        "decision_owner": decision_owner,
        "inputs": deepcopy(inputs or []),
        "raw_finding_count": len(raw_dispositions),
        "raw_dispositions": deepcopy(raw_dispositions),
        "merge_decisions": deepcopy(merge_decisions or []),
        "independence_decisions": deepcopy(independence_decisions or []),
        "canonical_findings": deepcopy(canonical_findings),
        "unresolved_count": unresolved_count,
    }


def _evidence_reference_keys(finding: dict) -> set[tuple[str, str]]:
    refs = finding.get("evidence_refs", [])
    if not isinstance(refs, list):
        return set()
    def normalized_path(value: object) -> str:
        path = _text(value).lower().replace("\\", "/")
        # The same extracted report text is sometimes recorded as report_text.txt
        # and sometimes as <project_id>/report_text.txt by different audit routes.
        if path.endswith("/report_text.txt") or path == "report_text.txt":
            return "report_text.txt"
        return path

    return {
        (normalized_path(ref.get("path")), _text(ref.get("locator")).lower())
        for ref in refs
        if isinstance(ref, dict) and _text(ref.get("path")) and _text(ref.get("locator"))
    }


def _dataset_identifiers(finding: dict) -> set[str]:
    text = " ".join(
        _text(finding.get(field))
        for field in ("finding_key", "claim", "error_mechanism", "evidence_object", "repair_path", "adjudication_reason")
    )
    return {match.group(0).lower().replace("-", "") for match in _DATASET_IDENTIFIER_RE.finditer(text)}


def _normalized_semantic_value(value: object) -> str:
    """Normalize prose fields only enough for exact, schema-owned comparisons."""
    return re.sub(r"\s+", " ", _text(value).casefold()).strip()


def _duplicate_canonical_candidates(canonical_findings: list[dict]) -> list[dict]:
    """Find formal findings requiring an explicit merge or independence decision.

    A shared location does not prove duplication, but it is the mandatory
    review boundary: the leader must merge the findings or record why their
    root cause and remediation are genuinely independent.  The same boundary
    also applies when root cause and remediation match even if locators differ.
    """
    candidates: list[dict] = []
    for left_index, left in enumerate(canonical_findings):
        left_id = _text(left.get("canonical_id"))
        left_refs = _evidence_reference_keys(left)
        left_identifiers = _dataset_identifiers(left)
        if not left_id:
            continue
        for right in canonical_findings[left_index + 1 :]:
            right_id = _text(right.get("canonical_id"))
            shared_refs = left_refs & _evidence_reference_keys(right)
            shared_identifiers = left_identifiers & _dataset_identifiers(right)
            same_root_and_repair = all(
                _normalized_semantic_value(left.get(field))
                and _normalized_semantic_value(left.get(field))
                == _normalized_semantic_value(right.get(field))
                for field in ("error_mechanism", "repair_path")
            )
            if not right_id or not (shared_refs or same_root_and_repair):
                continue
            candidates.append(
                {
                    "canonical_ids": [left_id, right_id],
                    "shared_evidence_refs": [
                        {"path": path, "locator": locator}
                        for path, locator in sorted(shared_refs)
                    ],
                    "shared_dataset_identifiers": sorted(shared_identifiers),
                    "same_root_and_repair": same_root_and_repair,
                }
            )
    return candidates


def _markdown_cells(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [re.sub(r"\s+", " ", cell.strip()) for cell in cells]


def _markdown_tables(text: str) -> Iterable[tuple[list[str], list[list[str]]]]:
    """Yield simple GFM tables; formal reports use tables for their crosswalk."""
    lines = text.splitlines()
    index = 0
    while index + 1 < len(lines):
        header, separator = lines[index], lines[index + 1]
        if "|" not in header or "|" not in separator or not re.fullmatch(r"[| :\-]+", separator.strip()):
            index += 1
            continue
        columns = _markdown_cells(header)
        rows: list[list[str]] = []
        index += 2
        while index < len(lines) and "|" in lines[index] and lines[index].strip().startswith("|"):
            row = _markdown_cells(lines[index])
            if len(row) == len(columns):
                rows.append(row)
            index += 1
        yield columns, rows


def _column_index(columns: list[str], *names: str) -> int | None:
    normalized = [re.sub(r"\s+", "", column).casefold() for column in columns]
    for name in names:
        target = re.sub(r"\s+", "", name).casefold()
        if target in normalized:
            return normalized.index(target)
    return None


def _is_concrete_crosswalk_value(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", _text(value)).strip()
    return normalized.casefold() not in _CROSSWALK_EMPTY_VALUES and not _CROSSWALK_REFERENCE_RE.fullmatch(normalized)


def _report_crosswalk(report_text: str) -> tuple[dict[str, dict], dict[str, dict], list[str]]:
    """Parse the established final-report issue and analysis-point tables.

    A report may crosswalk either a raw finding key or a canonical ID to an
    F-ID.  The latter keeps the formal report bindable when a legacy
    arbitration disposition lacks an optional ``finding_key`` field.
    """
    findings: dict[str, dict] = {}
    raw_to_report: dict[str, dict] = {}
    errors: list[str] = []
    for columns, rows in _markdown_tables(report_text):
        number = _column_index(columns, "编号", "id")
        severity = _column_index(columns, "严重度", "severity")
        problem = _column_index(columns, "核心问题", "问题", "错误描述", "problem")
        location = _column_index(columns, "原报告位置", "位置", "定位", "location")
        evidence = _column_index(columns, "交付证据", "证据", "evidence")
        repair = _column_index(columns, "修订要求", "整改要求", "整改", "repair")
        if number is not None and severity is not None and problem is not None and repair is not None:
            for row in rows:
                report_id = _text(row[number]).upper()
                if not _FORMAL_REPORT_ID_RE.fullmatch(report_id):
                    continue
                if report_id in findings:
                    errors.append(f"final report repeats formal finding id: {report_id}")
                    continue
                findings[report_id] = {
                    "severity": _text(row[severity]).upper(),
                    "description": _text(row[problem]),
                    "location": _text(row[location]) if location is not None else "",
                    "evidence": _text(row[evidence]) if evidence is not None else "",
                    "repair": _text(row[repair]),
                }

        finding_key = _column_index(columns, "Canonical ID", "canonical_id", "分析点", "finding_key", "原始发现")
        mapped_id = _column_index(columns, "对应问题", "formal finding", "问题编号")
        searchable_locator = _column_index(columns, "可搜索定位", "locator")
        if finding_key is not None and mapped_id is not None:
            content_columns = {
                field: _column_index(columns, *_CROSSWALK_FIELD_ALIASES[field])
                for field in _CROSSWALK_REQUIRED_FIELDS
                if field in _CROSSWALK_FIELD_ALIASES
            }
            for field in _CROSSWALK_REQUIRED_FIELDS:
                if field not in _CROSSWALK_FIELD_ALIASES or content_columns.get(field) is None:
                    errors.append(f"final report crosswalk missing required content column: {field}")
            if searchable_locator is None:
                errors.append("final report crosswalk missing required jump column: 可搜索定位")
            for row in rows:
                raw_key = _text(row[finding_key])
                report_id = _text(row[mapped_id]).upper()
                if not raw_key or not _FORMAL_REPORT_ID_RE.fullmatch(report_id):
                    continue
                if raw_key in raw_to_report and raw_to_report[raw_key]["report_id"] != report_id:
                    errors.append(f"final report maps raw finding key to multiple formal findings: {raw_key}")
                    continue
                raw_to_report[raw_key] = {
                    "report_id": report_id,
                    "locator": _text(row[searchable_locator]) if searchable_locator is not None else "",
                    "content": {
                        field: _text(row[column]) if column is not None else ""
                        for field, column in content_columns.items()
                    },
                }
    return findings, raw_to_report, errors


def _revoked_report_keys(report_text: str) -> set[str]:
    """Return explicitly revoked raw finding keys from final-report sections."""
    lines = report_text.splitlines()
    revoked: set[str] = set()
    for index, line in enumerate(lines):
        match = _REVOKED_REPORT_ITEM_RE.match(line.strip())
        if not match:
            continue
        following = "\n".join(lines[index + 1 : index + 8])
        if "不计入正式发现" in following:
            revoked.add(match.group(1))
    return revoked


def validate_final_report_arbitration_binding(
    report_text: str,
    arbitration: dict,
    final_decision: dict | None = None,
) -> dict:
    """Fail closed unless every formal report finding is traceable to arbitration.

    A retained arbitration canonical finding is linked to an ``F-ID`` through
    its source raw finding's ``finding_key`` when available, otherwise through
    a canonical-ID crosswalk.  This preserves legacy formal Markdown reports
    while making report severity, problem text, locator/evidence and repair
    accountable to a final decision.
    """
    errors: list[str] = []
    candidates: list[dict] = []
    findings, raw_to_report, parse_errors = _report_crosswalk(report_text)
    errors.extend(parse_errors)
    if not findings:
        errors.append("final report must contain a formal finding table with F-ID, severity, problem and repair")
    if not raw_to_report:
        errors.append("final report must contain an analysis-point raw finding key to F-ID crosswalk")

    dispositions = arbitration.get("raw_dispositions", []) if isinstance(arbitration, dict) else []
    canonicals = arbitration.get("canonical_findings", []) if isinstance(arbitration, dict) else []
    if not isinstance(dispositions, list) or not isinstance(canonicals, list):
        return _result("final_report_arbitration_binding", [*errors, "arbitration requires raw_dispositions and canonical_findings lists"], candidates)
    disposition_by_raw = {
        _text(item.get("raw_finding_id")): item
        for item in dispositions
        if isinstance(item, dict) and _text(item.get("raw_finding_id"))
    }
    canonical_by_id = {
        _text(item.get("canonical_id")): item
        for item in canonicals
        if isinstance(item, dict) and _text(item.get("canonical_id"))
    }
    revoked_keys = _revoked_report_keys(report_text)
    expected_report_ids: set[str] = set()
    bindings: list[dict] = []

    for index, canonical in enumerate(canonicals):
        if not isinstance(canonical, dict):
            errors.append(f"canonical_findings[{index}] must be an object")
            continue
        canonical_id = _text(canonical.get("canonical_id")) or f"canonical_findings[{index}]"
        source_raw_ids = canonical.get("source_raw_finding_ids", [])
        if not isinstance(source_raw_ids, list) or not source_raw_ids:
            errors.append(f"{canonical_id} has no source raw finding ids for final-report binding")
            continue
        mapped: list[tuple[str, dict]] = []
        for raw_id in source_raw_ids:
            disposition = disposition_by_raw.get(_text(raw_id))
            raw_key = _text(disposition.get("finding_key")) if isinstance(disposition, dict) else ""
            if not disposition or disposition.get("decision") == "reject":
                errors.append(f"{canonical_id} is not retained by an accepted final disposition: {_text(raw_id)}")
                continue
            crosswalk_key = raw_key or canonical_id
            if crosswalk_key in revoked_keys:
                errors.append(f"revoked finding key remains in canonical formal finding: {crosswalk_key}")
                continue
            mapping = raw_to_report.get(crosswalk_key)
            if not mapping:
                errors.append(f"retained canonical finding lacks final-report crosswalk: {canonical_id} / {crosswalk_key}")
                continue
            for field in _CROSSWALK_REQUIRED_FIELDS:
                value = mapping.get("content", {}).get(field, "")
                if not _is_concrete_crosswalk_value(value):
                    errors.append(f"final-report crosswalk has non-concrete {field}: {crosswalk_key}")
                elif len(value) > _CROSSWALK_SUMMARY_MAX_CHARS:
                    errors.append(f"final-report crosswalk summary exceeds {_CROSSWALK_SUMMARY_MAX_CHARS} characters: {crosswalk_key} / {field}")
            if _text(mapping.get("locator")).upper() != mapping["report_id"]:
                errors.append(f"final-report crosswalk locator must jump to mapped formal finding: {crosswalk_key}")
            mapped.append((crosswalk_key, mapping))
        report_ids = {mapping["report_id"] for _, mapping in mapped}
        if len(report_ids) != 1:
            errors.append(f"{canonical_id} must map to exactly one formal report finding")
            continue
        report_id = next(iter(report_ids))
        expected_report_ids.add(report_id)
        report_finding = findings.get(report_id)
        if not report_finding:
            errors.append(f"final-report crosswalk references missing formal finding: {report_id}")
            continue
        if report_finding["severity"] != _text(canonical.get("severity")).upper():
            errors.append(f"final-report severity differs from retained canonical finding: {report_id}")
        for field in ("description", "repair"):
            if not report_finding[field]:
                errors.append(f"final-report {field} missing for {report_id}")
        if not report_finding["location"] and not report_finding["evidence"]:
            errors.append(f"final-report evidence locator missing for {report_id}")
        bindings.append(
            {
                "canonical_id": canonical_id,
                "report_id": report_id,
                "raw_finding_keys": [raw_key for raw_key, _ in mapped],
                "source_evidence_refs": deepcopy(canonical.get("evidence_refs", [])),
            }
        )

    for raw_key, mapping in raw_to_report.items():
        if raw_key in revoked_keys:
            errors.append(f"revoked raw finding key appears in formal report crosswalk: {raw_key}")
        if raw_key in canonical_by_id:
            continue
        if re.fullmatch(r"C-\d+", raw_key, flags=re.IGNORECASE):
            errors.append(f"formal report crosswalk has no arbitration canonical finding: {raw_key}")
            continue
        matching_dispositions = [
            item for item in disposition_by_raw.values()
            if _text(item.get("finding_key")) == raw_key
        ]
        if not matching_dispositions:
            errors.append(f"formal report crosswalk has no arbitration disposition: {raw_key}")
        elif any(item.get("decision") == "reject" for item in matching_dispositions):
            errors.append(f"rejected raw finding key appears in formal report crosswalk: {raw_key}")

    unbound_report_ids = sorted(set(findings) - expected_report_ids)
    if unbound_report_ids:
        errors.append("formal report findings lack retained canonical binding: " + ", ".join(unbound_report_ids))

    if isinstance(final_decision, dict):
        final_count, final_severity_counts = _final_decision_summary(final_decision)
        if final_count is not None and final_count != len(findings):
            errors.append("final_decision canonical count differs from final report")
        if isinstance(final_severity_counts, dict):
            report_counts: dict[str, int] = defaultdict(int)
            for item in findings.values():
                report_counts[item["severity"]] += 1
            normalized_final = {key: int(final_severity_counts.get(key, 0)) for key in VALID_FINDING_SEVERITIES}
            normalized_report = {key: int(report_counts.get(key, 0)) for key in VALID_FINDING_SEVERITIES}
            if normalized_final != normalized_report:
                errors.append("final_decision severity counts differ from final report")

    result = _result("final_report_arbitration_binding", errors, candidates)
    result["bindings"] = bindings
    return result


def _final_decision_summary(final_decision: dict) -> tuple[Any, Any]:
    summary = final_decision.get("summary", final_decision)
    count = summary.get(
        "canonical_finding_count",
        summary.get("canonical_findings_total", summary.get("total_findings")),
    )
    severity_counts = summary.get("severity_counts")
    return count, severity_counts


def validate_arbitration_resolution_v2(payload: dict, final_decision: dict | None = None) -> dict:
    errors: list[str] = []
    candidates: list[dict] = []

    if _text(payload.get("schema_version")) != ARBITRATION_SCHEMA_VERSION:
        errors.append(f"schema_version must be {ARBITRATION_SCHEMA_VERSION}")
    for key in (
        "project_id",
        "status",
        "decision_owner",
        "inputs",
        "raw_finding_count",
        "raw_dispositions",
        "merge_decisions",
        "independence_decisions",
        "canonical_findings",
        "unresolved_count",
    ):
        if key not in payload:
            errors.append(f"missing top-level field: {key}")

    status = payload.get("status")
    if status not in VALID_ARBITRATION_STATUSES:
        errors.append(f"invalid status: {status}")
    if not _text(payload.get("project_id")):
        errors.append("project_id missing")
    if not _text(payload.get("decision_owner")):
        errors.append("decision_owner missing")
    inputs = payload.get("inputs")
    if not isinstance(inputs, list):
        errors.append("inputs must be a list")
        inputs = []
    if status == "leader_confirmed" and not inputs:
        errors.append("leader_confirmed arbitration must include hashed inputs")
    for index, item in enumerate(inputs):
        if not _text(item.get("path")) or not _text(item.get("sha256")):
            errors.append(f"inputs[{index}] requires path and sha256")
    unresolved_count = payload.get("unresolved_count")
    if not isinstance(unresolved_count, int) or unresolved_count < 0:
        errors.append("unresolved_count must be a non-negative integer")
    elif status == "leader_confirmed" and unresolved_count != 0:
        errors.append("leader_confirmed arbitration must have unresolved_count=0")

    dispositions = payload.get("raw_dispositions", [])
    canonical_findings = payload.get("canonical_findings", [])
    merge_decisions = payload.get("merge_decisions", [])
    independence_decisions = payload.get("independence_decisions", [])
    if not isinstance(dispositions, list):
        errors.append("raw_dispositions must be a list")
        dispositions = []
    if not isinstance(canonical_findings, list):
        errors.append("canonical_findings must be a list")
        canonical_findings = []
    if not isinstance(merge_decisions, list):
        errors.append("merge_decisions must be a list")
        merge_decisions = []
    if not isinstance(independence_decisions, list):
        errors.append("independence_decisions must be a list")
        independence_decisions = []

    raw_ids: list[str] = []
    disposition_by_raw: dict[str, dict] = {}
    for index, item in enumerate(dispositions):
        path = f"raw_dispositions[{index}]"
        raw_id = _text(item.get("raw_finding_id"))
        decision = item.get("decision")
        canonical_ids = item.get("canonical_ids", [])
        if not raw_id:
            errors.append(f"{path}.raw_finding_id missing")
        elif raw_id in disposition_by_raw:
            errors.append(f"raw finding disposed more than once: {raw_id}")
        else:
            raw_ids.append(raw_id)
            disposition_by_raw[raw_id] = item
        if decision not in VALID_ARBITRATION_DECISIONS:
            errors.append(f"{path}.decision invalid: {decision}")
        if not isinstance(canonical_ids, list):
            errors.append(f"{path}.canonical_ids must be a list")
            canonical_ids = []
        if decision == "reject" and canonical_ids:
            errors.append(f"{path}: reject must not map to canonical findings")
        if decision in VALID_ARBITRATION_DECISIONS - {"reject"} and not canonical_ids:
            errors.append(f"{path}: {decision} must map to at least one canonical finding")
        if not _text(item.get("reason")):
            errors.append(f"{path}.reason missing")

    if payload.get("raw_finding_count") != len(raw_ids):
        errors.append("raw_finding_count does not equal uniquely disposed raw findings")

    canonical_by_id: dict[str, dict] = {}
    severity_counts: dict[str, int] = defaultdict(int)
    for index, item in enumerate(canonical_findings):
        path = f"canonical_findings[{index}]"
        canonical_id = _text(item.get("canonical_id"))
        sources = item.get("source_raw_finding_ids", [])
        if not canonical_id:
            errors.append(f"{path}.canonical_id missing")
        elif canonical_id in canonical_by_id:
            errors.append(f"duplicate canonical_id: {canonical_id}")
        else:
            canonical_by_id[canonical_id] = item
        if not isinstance(sources, list) or not sources:
            errors.append(f"{path}.source_raw_finding_ids must be a non-empty list")
            sources = []
        if status == "leader_confirmed" and not item.get("evidence_refs"):
            errors.append(f"{path}.evidence_refs must be non-empty when leader_confirmed")
        for raw_id in sources:
            if raw_id not in disposition_by_raw:
                errors.append(f"{path} references undisposed raw finding: {raw_id}")
        severity = _text(item.get("severity"))
        if severity not in VALID_FINDING_SEVERITIES:
            errors.append(f"{path}.severity invalid: {severity}")
        else:
            severity_counts[severity] += 1
        missing_semantic = [field for field in SEMANTIC_MERGE_TUPLE if not _text(item.get(field))]
        if missing_semantic:
            errors.append(f"{path} missing semantic fields: {', '.join(missing_semantic)}")

    for index, item in enumerate(dispositions):
        canonical_ids = item.get("canonical_ids", []) if isinstance(item.get("canonical_ids", []), list) else []
        raw_id = _text(item.get("raw_finding_id"))
        for canonical_id in canonical_ids:
            if canonical_id not in canonical_by_id:
                errors.append(f"raw_dispositions[{index}] maps to unknown canonical_id: {canonical_id}")
            elif raw_id not in canonical_by_id[canonical_id].get("source_raw_finding_ids", []):
                errors.append(f"raw_dispositions[{index}] mapping is absent from {canonical_id} sources")

    merge_coverage: set[str] = set()
    for index, item in enumerate(merge_decisions):
        path = f"merge_decisions[{index}]"
        members = item.get("member_raw_finding_ids", [])
        results = item.get("canonical_ids", [])
        semantic_tuple = item.get("semantic_tuple", {})
        if not isinstance(members, list) or len(members) < 2:
            errors.append(f"{path}.member_raw_finding_ids must contain at least two ids")
        for raw_id in members if isinstance(members, list) else []:
            if raw_id not in disposition_by_raw:
                errors.append(f"{path} references unknown raw finding: {raw_id}")
        if not isinstance(results, list) or not results:
            errors.append(f"{path}.canonical_ids must be a non-empty list")
        if not _text(item.get("reason")):
            errors.append(f"{path}.reason missing")
        for canonical_id in results if isinstance(results, list) else []:
            if canonical_id not in canonical_by_id:
                errors.append(f"{path} references unknown canonical_id: {canonical_id}")
            merge_coverage.add(canonical_id)
        if not isinstance(semantic_tuple, dict):
            errors.append(f"{path}.semantic_tuple must be an object")
        else:
            missing = [field for field in SEMANTIC_MERGE_TUPLE if not _text(semantic_tuple.get(field))]
            if missing:
                errors.append(f"{path}.semantic_tuple missing: {', '.join(missing)}")
        pairwise_checks = item.get("pairwise_checks")
        if not isinstance(pairwise_checks, list) or not pairwise_checks:
            errors.append(f"{path}.pairwise_checks must be non-empty")
        else:
            observed_pairs: set[frozenset[str]] = set()
            for check_index, check in enumerate(pairwise_checks):
                left = _text(check.get("left_raw_finding_id", check.get("left")))
                right = _text(check.get("right_raw_finding_id", check.get("right")))
                if left and right:
                    observed_pairs.add(frozenset((left, right)))
                if check.get("linked", check.get("compatible")) is not True:
                    errors.append(f"{path}.pairwise_checks[{check_index}] is not compatible")
                if check.get("veto_codes"):
                    errors.append(f"{path}.pairwise_checks[{check_index}] contains merge vetoes")
            expected_pairs = {
                frozenset((left, right))
                for member_index, left in enumerate(members if isinstance(members, list) else [])
                for right in members[member_index + 1 :]
            }
            if not expected_pairs.issubset(observed_pairs):
                errors.append(f"{path}.pairwise_checks does not satisfy complete-link coverage")

    for canonical_id, item in canonical_by_id.items():
        sources = item.get("source_raw_finding_ids", [])
        if isinstance(sources, list) and len(sources) > 1 and canonical_id not in merge_coverage:
            errors.append(f"multi-source canonical finding lacks merge decision: {canonical_id}")

    resolved_independent_pairs: set[frozenset[str]] = set()
    semantic_duplicate_pairs = {
        frozenset(candidate["canonical_ids"])
        for candidate in _duplicate_canonical_candidates(canonical_findings)
        if candidate["same_root_and_repair"]
    }
    for index, item in enumerate(independence_decisions):
        path = f"independence_decisions[{index}]"
        canonical_ids = item.get("canonical_ids", [])
        if not isinstance(canonical_ids, list) or len(canonical_ids) < 2:
            errors.append(f"{path}.canonical_ids must contain at least two ids")
            continue
        if any(_text(canonical_id) not in canonical_by_id for canonical_id in canonical_ids):
            errors.append(f"{path} references unknown canonical_id")
        if not _text(item.get("reason")):
            errors.append(f"{path}.reason missing")
        for left_index, left_id in enumerate(canonical_ids):
            for right_id in canonical_ids[left_index + 1 :]:
                pair = frozenset((_text(left_id), _text(right_id)))
                resolved_independent_pairs.add(pair)
                if pair not in semantic_duplicate_pairs:
                    continue
                left = canonical_by_id.get(_text(left_id), {})
                right = canonical_by_id.get(_text(right_id), {})
                dimensions = item.get("distinguishing_dimensions", [])
                if not isinstance(dimensions, list) or not dimensions:
                    errors.append(
                        f"{path} requires distinguishing_dimensions for same-root-and-repair findings"
                    )
                    continue
                allowed_dimensions = {"module", "claim", "evidence_object"}
                invalid_dimensions = [
                    _text(dimension) for dimension in dimensions
                    if _text(dimension) not in allowed_dimensions
                    or _normalized_semantic_value(left.get(_text(dimension)))
                    == _normalized_semantic_value(right.get(_text(dimension)))
                ]
                if invalid_dimensions:
                    errors.append(
                        f"{path}.distinguishing_dimensions must name differing non-root fields: "
                        + ", ".join(invalid_dimensions)
                    )
                evidence = item.get("independence_evidence_refs", [])
                if not isinstance(evidence, list):
                    errors.append(f"{path}.independence_evidence_refs must be a list")
                    continue
                evidence_by_id: dict[str, set[tuple[str, str]]] = defaultdict(set)
                for evidence_ref in evidence:
                    if not isinstance(evidence_ref, dict):
                        continue
                    evidence_id = _text(evidence_ref.get("canonical_id"))
                    reference = (
                        _text(evidence_ref.get("path")).lower().replace("\\", "/"),
                        _text(evidence_ref.get("locator")).lower(),
                    )
                    if evidence_id and all(reference):
                        evidence_by_id[evidence_id].add(reference)
                for canonical_id, canonical in ((_text(left_id), left), (_text(right_id), right)):
                    if not evidence_by_id.get(canonical_id):
                        errors.append(
                            f"{path}.independence_evidence_refs must include {canonical_id}"
                        )
                    elif not evidence_by_id[canonical_id] <= _evidence_reference_keys(canonical):
                        errors.append(
                            f"{path}.independence_evidence_refs must cite {canonical_id} evidence_refs"
                        )

    for candidate in _duplicate_canonical_candidates(canonical_findings):
        pair = frozenset(candidate["canonical_ids"])
        if pair not in resolved_independent_pairs:
            ids = ", ".join(candidate["canonical_ids"])
            refs = ", ".join(
                f"{ref['path']}:{ref['locator']}" for ref in candidate["shared_evidence_refs"]
            ) or "—"
            identifiers = ", ".join(candidate["shared_dataset_identifiers"]) or "—"
            errors.append(
                "duplicate formal finding candidate requires merge or independence decision: "
                f"{ids} (shared evidence {refs}; shared identifiers {identifiers}; "
                f"same root+repair={candidate['same_root_and_repair']})"
            )

    if final_decision is not None:
        final_count, final_severity_counts = _final_decision_summary(final_decision)
        if final_count is not None and final_count != len(canonical_by_id):
            errors.append("final_decision canonical count differs from arbitration")
        if final_severity_counts is not None:
            normalized_final = {key: int(final_severity_counts.get(key, 0)) for key in VALID_FINDING_SEVERITIES}
            normalized_arbitration = {key: int(severity_counts.get(key, 0)) for key in VALID_FINDING_SEVERITIES}
            if normalized_final != normalized_arbitration:
                errors.append("final_decision severity counts differ from arbitration")

    return _result("arbitration_resolution", errors, candidates)


def build_dataset_scope_matrix(project_id: str, datasets: list[dict]) -> dict:
    return {"schema_version": "1.0", "project_id": project_id, "datasets": deepcopy(datasets)}


def validate_dataset_scope_matrix(payload: dict) -> dict:
    errors: list[str] = []
    candidates: list[dict] = []
    _validate_contract_header(payload, errors)
    datasets = payload.get("datasets")
    if not isinstance(datasets, list):
        return _result("dataset_scope", [*errors, "datasets must be a list"], candidates)
    seen: set[str] = set()
    for index, item in enumerate(datasets):
        path = f"datasets[{index}]"
        dataset_id = _text(item.get("dataset_id"))
        if not dataset_id:
            errors.append(f"{path}.dataset_id missing")
        elif dataset_id in seen:
            errors.append(f"duplicate dataset_id: {dataset_id}")
        seen.add(dataset_id)
        for field in ("report_declaration", "source_input", "code_reads", "code_writes", "delivery_outputs", "figure_or_table_claims"):
            if field not in item:
                errors.append(f"{path}.{field} missing")
        for field in ("code_writes", "delivery_outputs", "figure_or_table_claims"):
            if field in item and not isinstance(item.get(field), list):
                errors.append(f"{path}.{field} must be a list")
        source_status = item.get("source_input", {}).get("status") if isinstance(item.get("source_input"), dict) else None
        if source_status not in VALID_SOURCE_STATUS:
            errors.append(f"{path}.source_input.status invalid: {source_status}")
        reads = item.get("code_reads", [])
        if not isinstance(reads, list):
            errors.append(f"{path}.code_reads must be a list")
            reads = []
        active_reachable = False
        for read_index, read in enumerate(reads):
            activity = read.get("activity")
            if activity not in VALID_ACTIVITY:
                errors.append(f"{path}.code_reads[{read_index}].activity invalid: {activity}")
            if activity == "unknown":
                candidates.append(_candidate("DATASET_ACTIVITY_UNKNOWN", "代码引用活动状态待人工确认", f"{path}.code_reads[{read_index}]"))
            active_reachable |= activity == "active" and read.get("reachable") is True
        report_present = bool(item.get("report_declaration", {}).get("present")) if isinstance(item.get("report_declaration"), dict) else False
        has_outputs = bool(item.get("delivery_outputs")) or bool(item.get("figure_or_table_claims"))
        if report_present and not active_reachable and not has_outputs:
            candidates.append(_candidate("DATASET_ISOLATED_DECLARATION", "报告声明未连接到活动代码或正式产物", path))
        if active_reachable and not report_present:
            candidates.append(_candidate("DATASET_ACTIVE_UNREPORTED", "活动数据输入未在报告范围中声明", path))
        if active_reachable and source_status in {"missing", "unknown"}:
            candidates.append(_candidate("DATASET_SOURCE_UNRESOLVED", "活动且可达的数据输入缺少可复核来源", path))
    return _result("dataset_scope", errors, candidates)


def build_statistical_flow_graph(project_id: str, nodes: list[dict], edges: list[dict]) -> dict:
    return {"schema_version": "1.0", "project_id": project_id, "nodes": deepcopy(nodes), "edges": deepcopy(edges)}


def _statistical_adjacency(payload: dict) -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in payload.get("edges", []):
        adjacency[_text(edge.get("from_node"))].append(_text(edge.get("to_node")))
    return adjacency


def propagate_statistical_taint(payload: dict) -> dict:
    """Mark graph reachability from explicit raw-p formal selection; no severity inference."""
    result = deepcopy(payload)
    nodes = {item.get("node_id"): item for item in result.get("nodes", []) if item.get("node_id")}
    adjacency = _statistical_adjacency(result)
    origins = [
        node_id
        for node_id, item in nodes.items()
        if item.get("selection_field") == "raw_p" and item.get("formal_selection") is True
    ]
    for origin in origins:
        queue = deque([origin])
        visited: set[str] = set()
        while queue:
            node_id = queue.popleft()
            if node_id in visited or node_id not in nodes:
                continue
            visited.add(node_id)
            nodes[node_id]["taint_status"] = "requires_rerun"
            nodes[node_id]["taint_origin"] = origin
            queue.extend(adjacency.get(node_id, []))
    return result


def validate_statistical_flow_graph(payload: dict) -> dict:
    errors: list[str] = []
    candidates: list[dict] = []
    _validate_contract_header(payload, errors)
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return _result("statistical_flow", ["nodes and edges must be lists"], candidates)
    node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        path = f"nodes[{index}]"
        node_id = _text(node.get("node_id"))
        if not node_id:
            errors.append(f"{path}.node_id missing")
        elif node_id in node_ids:
            errors.append(f"duplicate node_id: {node_id}")
        node_ids.add(node_id)
        if node.get("taint_status", "unknown") not in VALID_TAINT_STATUS:
            errors.append(f"{path}.taint_status invalid")
    for index, edge in enumerate(edges):
        for endpoint in ("from_node", "to_node"):
            node_id = _text(edge.get(endpoint))
            if node_id not in node_ids:
                errors.append(f"edges[{index}].{endpoint} references unknown node: {node_id}")
    propagated = propagate_statistical_taint(payload)
    for index, node in enumerate(propagated.get("nodes", [])):
        if node.get("taint_status") == "requires_rerun":
            candidates.append(
                _candidate(
                    "RAW_P_DOWNSTREAM_TAINT",
                    "正式 raw-p 选择或其下游产物需要专业复核与重跑确认",
                    f"nodes[{index}]",
                    node.get("evidence_refs", []),
                )
            )
    return _result("statistical_flow", errors, candidates)


def build_method_code_matrix(project_id: str, analyses: list[dict]) -> dict:
    return {"schema_version": "1.0", "project_id": project_id, "analyses": deepcopy(analyses)}


def validate_method_code_matrix(payload: dict) -> dict:
    errors: list[str] = []
    candidates: list[dict] = []
    _validate_contract_header(payload, errors)
    analyses = payload.get("analyses")
    if not isinstance(analyses, list):
        return _result("method_code", ["analyses must be a list"], candidates)
    seen: set[str] = set()
    for index, item in enumerate(analyses):
        path = f"analyses[{index}]"
        analysis_id = _text(item.get("analysis_id"))
        if not analysis_id:
            errors.append(f"{path}.analysis_id missing")
        elif analysis_id in seen:
            errors.append(f"duplicate analysis_id: {analysis_id}")
        seen.add(analysis_id)
        for field in ("report_method", "implementation", "parameters", "outputs", "match_status", "differences"):
            if field not in item:
                errors.append(f"{path}.{field} missing")
        match_status = item.get("match_status")
        if match_status not in VALID_MATCH_STATUS:
            errors.append(f"{path}.match_status invalid: {match_status}")
        elif match_status in {"mismatch", "partial", "unknown"}:
            candidates.append(_candidate("METHOD_CODE_REVIEW", "方法与活动实现需要专业一致性复核", path, item.get("evidence_refs", [])))
    return _result("method_code", errors, candidates)


def build_ml_lineage(project_id: str, analyses: list[dict]) -> dict:
    return {"schema_version": "1.0", "project_id": project_id, "analyses": deepcopy(analyses)}


def validate_ml_lineage(payload: dict) -> dict:
    errors: list[str] = []
    candidates: list[dict] = []
    _validate_contract_header(payload, errors)
    analyses = payload.get("analyses")
    if not isinstance(analyses, list):
        return _result("ml_lineage", ["analyses must be a list"], candidates)
    for index, item in enumerate(analyses):
        path = f"analyses[{index}]"
        if not _text(item.get("analysis_id")):
            errors.append(f"{path}.analysis_id missing")
        for field in ("datasets", "split_events", "feature_selection", "fits", "predictions", "metrics", "claims"):
            if field not in item:
                errors.append(f"{path}.{field} missing")
        predictions = item.get("predictions", [])
        metrics = item.get("metrics", [])
        feature_selection = item.get("feature_selection", [])
        if not all(isinstance(value, list) for value in (predictions, metrics, feature_selection)):
            errors.append(f"{path}: predictions, metrics and feature_selection must be lists")
            continue
        prediction_ids = {_text(prediction.get("prediction_id")) for prediction in predictions}
        for metric_index, metric in enumerate(metrics):
            prediction_id = _text(metric.get("prediction_id"))
            if metric.get("published", True) and prediction_id not in prediction_ids:
                errors.append(f"{path}.metrics[{metric_index}] lacks a valid prediction lineage")
            if metric.get("data_role") in {"train", "unknown"} and metric.get("published", True):
                candidates.append(_candidate("ML_METRIC_ROLE_REVIEW", "已报告指标的数据身份需要专业复核", f"{path}.metrics[{metric_index}]"))
        for selection_index, selection in enumerate(feature_selection):
            scope = selection.get("scope", "unknown")
            if scope not in VALID_LINEAGE_SCOPE:
                errors.append(f"{path}.feature_selection[{selection_index}].scope invalid: {scope}")
            elif selection.get("supervised") is True and scope in {"pre_split", "unknown"}:
                candidates.append(
                    _candidate(
                        "ML_FEATURE_SELECTION_LEAKAGE_REVIEW",
                        "监督式特征选择时点可能影响验证独立性",
                        f"{path}.feature_selection[{selection_index}]",
                    )
                )
        for prediction_index, prediction in enumerate(predictions):
            if prediction.get("data_role") == "external" and not _text(prediction.get("sample_identity_hash")):
                candidates.append(_candidate("ML_EXTERNAL_IDENTITY_UNRESOLVED", "外部验证缺少可核对的样本身份", f"{path}.predictions[{prediction_index}]"))
    return _result("ml_lineage", errors, candidates)


def build_high_risk_module_contract(project_id: str, modules: list[dict]) -> dict:
    return {"schema_version": "1.0", "project_id": project_id, "modules": deepcopy(modules)}


def validate_high_risk_module_contract(payload: dict) -> dict:
    errors: list[str] = []
    candidates: list[dict] = []
    _validate_contract_header(payload, errors)
    modules = payload.get("modules")
    if not isinstance(modules, list):
        return _result("high_risk_modules", ["modules must be a list"], candidates)
    for index, item in enumerate(modules):
        path = f"modules[{index}]"
        module_type = _text(item.get("module_type"))
        if module_type not in HIGH_RISK_MINIMUM_PACKAGES:
            errors.append(f"{path}.module_type invalid: {module_type}")
            continue
        dimensions = item.get("dimensions")
        if not isinstance(dimensions, dict):
            errors.append(f"{path}.dimensions must be an object")
            dimensions = {}
        for dimension in HIGH_RISK_DIMENSIONS:
            value = dimensions.get(dimension)
            if not isinstance(value, dict) or value.get("status") not in VALID_DIMENSION_STATUS:
                errors.append(f"{path}.dimensions.{dimension} requires a valid status object")
                continue
            if not isinstance(value.get("evidence_refs", []), list):
                errors.append(f"{path}.dimensions.{dimension}.evidence_refs must be a list")
            if value.get("status") in {"fail", "unknown"}:
                candidates.append(
                    _candidate(
                        "HIGH_RISK_DIMENSION_REVIEW",
                        f"高风险模块维度 {dimension} 为 {value.get('status')}",
                        f"{path}.dimensions.{dimension}",
                        value.get("evidence_refs", []),
                    )
                )
        package = item.get("minimum_evidence_package")
        if not isinstance(package, list):
            errors.append(f"{path}.minimum_evidence_package must be a list")
            package = []
        package_by_id = {_text(entry.get("item_id")): entry for entry in package}
        for item_id in HIGH_RISK_MINIMUM_PACKAGES[module_type]:
            entry = package_by_id.get(item_id)
            if entry is None:
                errors.append(f"{path}.minimum_evidence_package missing disposition: {item_id}")
                continue
            status = entry.get("status")
            if status not in VALID_EVIDENCE_STATUS:
                errors.append(f"{path}.minimum_evidence_package[{item_id}].status invalid")
            elif status in {"missing", "unknown"}:
                candidates.append(
                    _candidate(
                        "HIGH_RISK_EVIDENCE_REVIEW",
                        f"高风险模块证据项 {item_id} 为 {status}",
                        f"{path}.minimum_evidence_package[{item_id}]",
                        entry.get("evidence_refs", []),
                    )
                )
    return _result("high_risk_modules", errors, candidates)


def validate_professional_contract_bundle(bundle: dict) -> dict[str, dict]:
    """Validate the four policy-owned professional contracts as one bundle."""
    validators = {
        "dataset_scope": validate_dataset_scope_matrix,
        "statistical_flow": validate_statistical_flow_graph,
        "method_code": validate_method_code_matrix,
        "ml_lineage": validate_ml_lineage,
    }
    return {
        contract_type: validator(bundle.get(contract_type, {}))
        for contract_type, validator in validators.items()
    }
