#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Compare structured outputs from three audit agents and generate convergence reports."""

from __future__ import annotations

import json
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

from audit_runtime import append_event, ensure_finding_key
from policy_loader import load_policy


POLICY = load_policy()
VALID_SEVERITIES = {"FATAL", "CRITICAL", "MAJOR", "WARNING", "INFO"}
VALID_DISPOSITIONS = {"保留", "撤销", "降级", "升级"}
VALID_VERDICTS = {"合格", "有条件合格", "不合格"}
VALID_SOURCE_TYPES = set(POLICY["finding_evidence_policy"]["allowed_source_types"])
REQUIRED_FINDING_FIELDS = tuple(POLICY["finding_evidence_policy"]["required_fields"])
DIMENSION_KEYS = tuple(POLICY["high_risk_module_policy"]["required_dimensions"])
SEVERITY_ORDER = {"FATAL": 5, "CRITICAL": 4, "MAJOR": 3, "WARNING": 2, "INFO": 1}
EVIDENCE_CRITICAL_FIELDS = ("source_path", "locator", "quote_or_value", "evidence")
REQUIRED_SLICE_KEYS = ("slice_id", "agent", "status", "findings", "summary")
PROFESSIONAL_POLICY = POLICY.get("professional_contract_policy", {})
SEMANTIC_MERGE_FIELDS = tuple(
    PROFESSIONAL_POLICY.get(
        "semantic_merge_tuple",
        ("module", "claim", "error_mechanism", "evidence_object", "repair_path"),
    )
)
PROTECTED_MERGE_VETOES = frozenset(PROFESSIONAL_POLICY.get("protected_merge_vetoes", ()))


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().replace("\u3000", " "))


def normalize_location(value: object) -> str:
    return normalize_text(value).lower()


def _stable_digest(parts: list[str]) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:20]


def ensure_raw_finding_id(finding: dict, agent_id: str = "") -> str:
    """Attach an immutable identity for one raw route finding.

    ``finding_key`` remains a legacy content key.  It must not be used as the
    identity of a route observation because different agents may deliberately
    report the same issue.
    """
    existing = normalize_text(finding.get("raw_finding_id"))
    if existing:
        return existing
    raw_id = "rf:" + _stable_digest(
        [
            normalize_text(agent_id),
            normalize_text(finding.get("id")),
            normalize_text(finding.get("source_type")),
            normalize_text(finding.get("source_path")),
            normalize_text(finding.get("locator")),
            normalize_text(finding.get("quote_or_value")),
        ]
    )
    finding["raw_finding_id"] = raw_id
    return raw_id


def semantic_merge_tuple(finding: dict) -> dict[str, str]:
    return {field: normalize_text(finding.get(field)).lower() for field in SEMANTIC_MERGE_FIELDS}


def build_cluster_key(finding: dict) -> str:
    """Build a semantic cluster key separate from raw identity/finding key."""
    semantic = semantic_merge_tuple(finding)
    if all(semantic.values()):
        parts = [semantic[field] for field in SEMANTIC_MERGE_FIELDS]
    else:
        parts = ["legacy", ensure_finding_key(finding)]
    cluster_key = "ck:" + _stable_digest(parts)
    finding["cluster_key"] = cluster_key
    return cluster_key


def _protected_categories(finding: dict) -> set[str]:
    values: list[object] = []
    for key in ("protected_category", "protected_categories", "merge_veto_category"):
        value = finding.get(key)
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
        elif value:
            values.append(value)
    return {
        normalize_text(value).lower()
        for value in values
        if normalize_text(value).lower() in PROTECTED_MERGE_VETOES
    }


def assess_semantic_link(left: dict, right: dict, threshold: float = 0.4) -> dict:
    """Return an auditable, candidate-only linkage assessment for two findings."""
    left_tuple = semantic_merge_tuple(left)
    right_tuple = semantic_merge_tuple(right)
    veto_codes: list[str] = []

    left_categories = _protected_categories(left)
    right_categories = _protected_categories(right)
    if (left_categories or right_categories) and left_categories != right_categories:
        veto_codes.append("protected_category_mismatch")

    for field in SEMANTIC_MERGE_FIELDS:
        if left_tuple[field] and right_tuple[field] and left_tuple[field] != right_tuple[field]:
            veto_codes.append(f"semantic_{field}_mismatch")

    similarity = compute_similarity(left, right)
    exact_finding_key = ensure_finding_key(left) == ensure_finding_key(right)
    complete_tuple = all(left_tuple.values()) and all(right_tuple.values())
    exact_semantic_tuple = complete_tuple and left_tuple == right_tuple
    linked = not veto_codes and (exact_semantic_tuple or exact_finding_key or similarity >= threshold)

    return {
        "left_raw_finding_id": normalize_text(left.get("raw_finding_id")),
        "right_raw_finding_id": normalize_text(right.get("raw_finding_id")),
        "linked": linked,
        "similarity": round(similarity, 4),
        "exact_finding_key": exact_finding_key,
        "complete_semantic_tuple": complete_tuple,
        "exact_semantic_tuple": exact_semantic_tuple,
        "veto_codes": veto_codes,
    }


def compute_similarity(left: dict, right: dict) -> float:
    score = 0.0

    left_loc = normalize_location(left.get("location", ""))
    right_loc = normalize_location(right.get("location", ""))
    if left_loc and right_loc:
        if left_loc == right_loc:
            score += 0.4
        else:
            left_sections = re.findall(r"[\d]+(?:\.[\d]+)*", left_loc)
            right_sections = re.findall(r"[\d]+(?:\.[\d]+)*", right_loc)
            if left_sections and right_sections:
                left_best = max(left_sections, key=len)
                for section in right_sections:
                    if left_best == section:
                        score += 0.4
                        break
                    if left_best.startswith(section + ".") or section.startswith(left_best + "."):
                        score += 0.25
                        break
            elif left_loc in right_loc or right_loc in left_loc:
                score += 0.2

    if normalize_text(left.get("dimension")) == normalize_text(right.get("dimension")):
        score += 0.2

    if normalize_text(left.get("rule")) and normalize_text(left.get("rule")) == normalize_text(right.get("rule")):
        score += 0.2

    left_desc = set(normalize_text(left.get("description", "")).lower().split())
    right_desc = set(normalize_text(right.get("description", "")).lower().split())
    if left_desc and right_desc:
        overlap = len(left_desc & right_desc) / max(len(left_desc | right_desc), 1)
        score += 0.2 * overlap

    return score


def has_complete_high_risk_evidence(finding: dict) -> bool:
    return all(normalize_text(finding.get(field, "")) for field in EVIDENCE_CRITICAL_FIELDS)


def get_max_severity(findings: dict[str, dict]) -> str:
    current = "INFO"
    for finding in findings.values():
        severity = normalize_text(finding.get("severity", "INFO")) or "INFO"
        if SEVERITY_ORDER.get(severity, 0) > SEVERITY_ORDER.get(current, 0):
            current = severity
    return current


def pick_majority(values: list[str], default: str = "") -> str:
    if not values:
        return default
    counter: dict[str, int] = defaultdict(int)
    for value in values:
        counter[value] += 1
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def match_findings(results: dict[str, list[dict]], threshold: float = 0.4) -> list[dict]:
    flattened: list[dict] = []
    for agent_id, findings in results.items():
        for finding in findings:
            raw_finding_id = ensure_raw_finding_id(finding, agent_id)
            flattened.append(
                {
                    "agent": agent_id,
                    "finding": finding,
                    "finding_key": ensure_finding_key(finding),
                    "raw_finding_id": raw_finding_id,
                    "cluster_key": build_cluster_key(finding),
                    "matched": False,
                }
            )

    def new_group(item: dict, mode: str) -> dict:
        return {
            "finding_key": item["finding_key"],
            "cluster_key": item["cluster_key"],
            "findings": {item["agent"]: item["finding"]},
            "agents": {item["agent"]},
            "items": [item],
            "match_mode": mode,
            "pairwise_checks": [],
            "rejected_candidates": [],
        }

    def try_add(group: dict, item: dict, require_exact_key: bool = False) -> bool:
        if item["agent"] in group["agents"]:
            return False
        checks = [assess_semantic_link(member["finding"], item["finding"], threshold) for member in group["items"]]
        if require_exact_key:
            compatible = all(check["linked"] and check["exact_finding_key"] for check in checks)
        else:
            compatible = all(check["linked"] for check in checks)
        if not compatible:
            group["rejected_candidates"].append(
                {
                    "raw_finding_id": item["raw_finding_id"],
                    "checks": checks,
                }
            )
            return False
        group["findings"][item["agent"]] = item["finding"]
        group["agents"].add(item["agent"])
        group["items"].append(item)
        group["pairwise_checks"].extend(checks)
        if all(check["exact_semantic_tuple"] for check in checks):
            group["match_mode"] = "semantic_tuple"
        return True

    # Preserve the established preference for exact finding keys, but apply
    # complete-link and semantic vetoes inside each exact-key bucket.
    groups: list[dict] = []
    exact_buckets: dict[str, list[dict]] = defaultdict(list)
    for item in flattened:
        exact_buckets[item["finding_key"]].append(item)
    for bucket_items in exact_buckets.values():
        exact_groups: list[dict] = []
        for item in bucket_items:
            target = next((group for group in exact_groups if try_add(group, item, require_exact_key=True)), None)
            if target is None:
                exact_groups.append(new_group(item, "exact"))
        for group in exact_groups:
            if len(group["agents"]) > 1:
                for item in group["items"]:
                    item["matched"] = True
                groups.append(group)

    # Similarity fallback is a proposal only.  A candidate joins a cluster
    # only when it is compatible with every existing member (complete-link).
    for item in flattened:
        if item["matched"]:
            continue
        group = new_group(item, "similarity_candidate")
        item["matched"] = True
        for other in flattened:
            if other["matched"] or other is item:
                continue
            if try_add(group, other):
                other["matched"] = True
        groups.append(group)

    for group in groups:
        group.pop("items", None)

    return groups


def classify_groups(groups: list[dict], total_agents: int) -> dict[str, list[dict]]:
    classified = {"consensus": [], "majority": [], "single": [], "divergent": []}
    for group in groups:
        agent_count = len(group["agents"])
        severities = {finding.get("severity", "") for finding in group["findings"].values()}

        if agent_count == total_agents and len(severities) <= 1:
            classified["consensus"].append(group)
        elif agent_count == total_agents or agent_count == total_agents - 1:
            classified["majority"].append(group)
        elif agent_count == 1:
            classified["single"].append(group)
        else:
            classified["divergent"].append(group)

    return classified


def build_arbitration_queue(classified: dict[str, list[dict]]) -> list[dict]:
    """Return every finding group that needs a recorded final disposition.

    Severity controls prioritization, not whether a finding is silently removed
    from the audit trail.  A leader may reject, merge, or retain an item, but
    each raw finding must reach arbitration so that the final contract can
    account for it.
    """
    queue = []
    for route_name, route_value in (
        ("divergent", classified["divergent"]),
        ("single", classified["single"]),
        ("consensus", classified["consensus"]),
        ("majority", classified["majority"]),
    ):
        for group in route_value:
            max_severity = get_max_severity(group["findings"])
            evidence_complete = all(
                has_complete_high_risk_evidence(finding)
                for finding in group["findings"].values()
            )
            queue.append(
                {
                    "finding_key": group.get("finding_key", ""),
                    "route": route_name,
                    "severity": max_severity,
                    "agents": sorted(group["agents"]),
                    "evidence_complete": evidence_complete,
                    "match_mode": group.get("match_mode", ""),
                    "descriptions": {
                        agent_id: finding.get("description", "")
                        for agent_id, finding in group["findings"].items()
                    },
                }
            )

    return queue


def compute_metrics(classified: dict[str, list[dict]], total_groups: int) -> dict[str, float]:
    if total_groups == 0:
        return {
            "consensus_rate": 100.0,
            "majority_rate": 0.0,
            "single_rate": 0.0,
            "divergent_rate": 0.0,
        }
    return {
        "consensus_rate": round(len(classified["consensus"]) / total_groups * 100, 1),
        "majority_rate": round(len(classified["majority"]) / total_groups * 100, 1),
        "single_rate": round(len(classified["single"]) / total_groups * 100, 1),
        "divergent_rate": round(len(classified["divergent"]) / total_groups * 100, 1),
    }


def aggregate_mechanical_dispositions(mechanical_results: dict[str, list[dict]]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for agent_id, items in mechanical_results.items():
        for item in items:
            code = normalize_text(item.get("code", ""))
            if not code:
                continue
            bucket = grouped.setdefault(code, {"code": code, "auto_severity": item.get("auto_severity", ""), "by_agent": {}})
            if not bucket["auto_severity"] and item.get("auto_severity"):
                bucket["auto_severity"] = item.get("auto_severity")
            bucket["by_agent"][agent_id] = {
                "disposition": item.get("disposition", ""),
                "final_severity": item.get("final_severity", ""),
                "reason": item.get("reason", ""),
            }

    summary = []
    for code in sorted(grouped):
        bucket = grouped[code]
        by_agent = bucket["by_agent"]
        dispositions = [entry["disposition"] for entry in by_agent.values() if entry.get("disposition")]
        final_severities = [entry["final_severity"] for entry in by_agent.values() if entry.get("final_severity")]
        distinct_dispositions = set(dispositions)
        support_count = len(by_agent)

        if support_count == 3 and len(distinct_dispositions) == 1 and dispositions:
            agreement = "consensus"
        elif support_count >= 2 and dispositions:
            agreement = "majority" if len(distinct_dispositions) <= 2 else "split"
        else:
            agreement = "single"

        recommended_final_severity = "INFO"
        if final_severities:
            recommended_final_severity = sorted(
                final_severities,
                key=lambda severity: (-SEVERITY_ORDER.get(severity, 0), severity),
            )[0]

        summary.append(
            {
                "code": code,
                "auto_severity": bucket["auto_severity"],
                "recommended_disposition": pick_majority(dispositions, default=""),
                "recommended_final_severity": recommended_final_severity,
                "agreement": agreement,
                "support_count": support_count,
                "missing_agents": sorted(set("ABC") - set(by_agent)),
                "by_agent": by_agent,
            }
        )
    return summary


def aggregate_high_risk_modules(high_risk_results: dict[str, list[dict]]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for agent_id, items in high_risk_results.items():
        for item in items:
            module = normalize_text(item.get("module", ""))
            if not module:
                continue
            bucket = grouped.setdefault(module, {"module": module, "by_agent": {}})
            bucket["by_agent"][agent_id] = item

    summary = []
    for module in sorted(grouped):
        bucket = grouped[module]
        by_agent = bucket["by_agent"]
        dimension_summary = {}
        for key in DIMENSION_KEYS:
            values = [entry.get(key) for entry in by_agent.values() if entry.get(key) is not None]
            if not values:
                continue
            true_count = sum(1 for value in values if bool(value))
            false_count = sum(1 for value in values if not bool(value))
            if true_count == len(values):
                agreement = "consensus_true"
                recommended = True
            elif false_count == len(values):
                agreement = "consensus_false"
                recommended = False
            elif true_count > false_count:
                agreement = "majority_true"
                recommended = True
            elif false_count > true_count:
                agreement = "majority_false"
                recommended = False
            else:
                agreement = "split"
                recommended = None
            dimension_summary[key] = {
                "recommended": recommended,
                "agreement": agreement,
                "true_count": true_count,
                "false_count": false_count,
            }

        summary.append({"module": module, "dimension_summary": dimension_summary, "by_agent": by_agent})
    return summary


def format_dimension(entry: dict | None) -> str:
    if not entry:
        return "-"
    if entry["recommended"] is True:
        state = "yes"
    elif entry["recommended"] is False:
        state = "no"
    else:
        state = "undecided"
    return f"{state} ({entry['agreement']})"


def generate_markdown_report(
    classified: dict[str, list[dict]],
    metrics: dict[str, float],
    summaries: dict[str, dict],
    mechanical_summary: list[dict],
    high_risk_summary: list[dict],
    arbitration_queue: list[dict],
) -> str:
    lines = [
        "# Three-Agent Convergence Report",
        "",
        "## Metrics",
        "| Metric | Value |",
        "|---|---|",
        f"| Consensus Rate | {metrics['consensus_rate']}% |",
        f"| Majority Rate | {metrics['majority_rate']}% |",
        f"| Single Rate | {metrics['single_rate']}% |",
        f"| Divergent Rate | {metrics['divergent_rate']}% |",
        f"| Converged | {'yes' if metrics['consensus_rate'] >= 95 and metrics['divergent_rate'] < 5 else 'no'} |",
        "",
        "## Agent Summary",
        "| Agent | Total | FATAL | CRITICAL | MAJOR | WARNING | INFO | Score | Verdict |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for agent_id in ("A", "B", "C"):
        summary = summaries.get(agent_id, {})
        lines.append(
            f"| {agent_id} | {summary.get('total_findings', '?')} | "
            f"{summary.get('fatal', '?')} | {summary.get('critical', '?')} | "
            f"{summary.get('major', '?')} | {summary.get('warning', '?')} | "
            f"{summary.get('info', '?')} | {summary.get('suggested_score', '?')} | "
            f"{summary.get('verdict', '?')} |"
        )

    def add_groups(title: str, prefix: str, groups: list[dict], detail_mode: str) -> None:
        if not groups:
            return
        lines.extend(["", f"## {title}"])
        for index, group in enumerate(groups, start=1):
            sample = list(group["findings"].values())[0]
            lines.append(f"### {prefix}{index:03d}: [{get_max_severity(group['findings'])}] {sample.get('description', '')}")
            lines.append(f"- finding_key: {group.get('finding_key', '')}")
            lines.append(f"- match_mode: {group.get('match_mode', '')}")
            lines.append(f"- agents: {', '.join(sorted(group['agents']))}")
            if detail_mode != "single":
                missing_agents = ", ".join(sorted(set("ABC") - set(group["agents"]))) or "-"
                lines.append(f"- missing_agents: {missing_agents}")
            if detail_mode == "single":
                lines.append(f"- location: {sample.get('location', '')}")
                lines.append(f"- evidence: {sample.get('evidence', '')}")
            else:
                for agent_id, finding in sorted(group["findings"].items()):
                    lines.append(f"- Agent {agent_id}: {finding.get('severity', '')} | {finding.get('description', '')}")
            lines.append("")

    add_groups("Consensus Findings", "C", classified["consensus"], "group")
    add_groups("Majority Findings", "M", classified["majority"], "group")
    add_groups("Single-Agent Findings", "S", classified["single"], "single")
    add_groups("Divergent Findings", "D", classified["divergent"], "group")

    if mechanical_summary:
        lines.extend(
            [
                "## Mechanical Disposition Summary",
                "| Code | Auto Severity | Recommended Disposition | Recommended Final Severity | Agreement | Missing Agents |",
                "|---|---|---|---|---|---|",
            ]
        )
        for item in mechanical_summary:
            lines.append(
                f"| {item['code']} | {item['auto_severity']} | {item['recommended_disposition']} | "
                f"{item['recommended_final_severity']} | {item['agreement']} | "
                f"{', '.join(item['missing_agents']) or '-'} |"
            )
        lines.append("")

    if high_risk_summary:
        lines.extend(
            [
                "## High Risk Module Summary",
                "| Module | Exists | Evidence Sufficient | Reproducible | Conclusion Not Overstated |",
                "|---|---|---|---|---|",
            ]
        )
        for item in high_risk_summary:
            dims = item["dimension_summary"]
            lines.append(
                f"| {item['module']} | "
                f"{format_dimension(dims.get('module_exists'))} | "
                f"{format_dimension(dims.get('evidence_sufficient'))} | "
                f"{format_dimension(dims.get('reproducible'))} | "
                f"{format_dimension(dims.get('conclusion_not_overstated'))} |"
            )
        lines.append("")

    if arbitration_queue:
        lines.extend(
            [
                "## Arbitration Queue",
                "| Finding Key | Route | Severity | Agents | Evidence Complete | Match Mode |",
                "|---|---|---|---|---|---|",
            ]
        )
        for item in arbitration_queue:
            lines.append(
                f"| {item['finding_key']} | {item['route']} | {item['severity']} | "
                f"{', '.join(item['agents'])} | {'yes' if item['evidence_complete'] else 'no'} | "
                f"{item.get('match_mode', '')} |"
            )
        lines.append("")

    lines.append("## Next Step")
    if metrics["consensus_rate"] >= 95 and metrics["divergent_rate"] < 5:
        lines.append("Convergence is sufficient for final adjudication.")
    else:
        lines.append("Another review round or explicit arbitration is recommended before final adjudication.")

    return "\n".join(lines)


def build_json_report(
    metrics: dict[str, float],
    convergence_status: bool,
    summaries: dict[str, dict],
    classified: dict[str, list[dict]],
    mechanical_summary: list[dict],
    high_risk_summary: list[dict],
    arbitration_queue: list[dict],
) -> dict:
    return {
        "metrics": metrics,
        "converged": convergence_status,
        "summaries": summaries,
        "mechanical_dispositions_summary": mechanical_summary,
        "high_risk_modules_summary": high_risk_summary,
        "arbitration_queue": arbitration_queue,
        "classified": {
            group_type: [
                {
                    "finding_key": group.get("finding_key", ""),
                    "cluster_key": group.get("cluster_key", ""),
                    "agents": sorted(group["agents"]),
                    "severity": get_max_severity(group["findings"]),
                    "match_mode": group.get("match_mode", ""),
                    "raw_finding_ids": sorted(
                        normalize_text(finding.get("raw_finding_id"))
                        for finding in group["findings"].values()
                    ),
                    "semantic_merge_tuple": semantic_merge_tuple(next(iter(group["findings"].values()))),
                    "pairwise_checks": group.get("pairwise_checks", []),
                    "rejected_candidates": group.get("rejected_candidates", []),
                    "findings_by_agent": {
                        agent_id: {
                            "severity": finding.get("severity", ""),
                            "description": finding.get("description", ""),
                            "location": finding.get("location", ""),
                        }
                        for agent_id, finding in group["findings"].items()
                    },
                }
                for group in groups
            ]
            for group_type, groups in classified.items()
        },
    }


def validate_agent_result(data: dict, agent_id: str) -> list[str]:
    errors = []

    summary = data.get("summary", {})
    for key in ("total_findings", "fatal", "critical", "major", "warning", "info", "suggested_score"):
        value = summary.get(key)
        if value is not None and not isinstance(value, (int, float)):
            try:
                summary[key] = int(value)
                errors.append(f"Agent {agent_id}: summary.{key} converted to int")
            except (TypeError, ValueError):
                summary[key] = 0
                errors.append(f"Agent {agent_id}: summary.{key} reset to 0")

    score = summary.get("suggested_score", 0)
    if isinstance(score, (int, float)) and not (0 <= score <= 100):
        summary["suggested_score"] = max(0, min(100, int(score)))
        errors.append(f"Agent {agent_id}: suggested_score clipped into 0-100")

    verdict = normalize_text(summary.get("verdict", ""))
    if verdict and verdict not in VALID_VERDICTS:
        errors.append(f"Agent {agent_id}: verdict '{verdict}' not in allowed set")

    for index, finding in enumerate(data.get("findings", [])):
        ensure_finding_key(finding)
        ensure_raw_finding_id(finding, agent_id)
        build_cluster_key(finding)
        for key in REQUIRED_FINDING_FIELDS:
            value = finding.get(key, "")
            if not isinstance(value, str):
                finding[key] = str(value)
                value = finding[key]
            if not normalize_text(value):
                errors.append(f"Agent {agent_id}: findings[{index}].{key} missing")
        severity = normalize_text(finding.get("severity", ""))
        if severity and severity not in VALID_SEVERITIES:
            errors.append(f"Agent {agent_id}: findings[{index}].severity invalid")
        source_type = normalize_text(finding.get("source_type", ""))
        if source_type and source_type not in VALID_SOURCE_TYPES:
            errors.append(f"Agent {agent_id}: findings[{index}].source_type invalid")

    for index, item in enumerate(data.get("mechanical_dispositions", [])):
        code = item.get("code", "")
        if code and not isinstance(code, str):
            item["code"] = str(code)
        if item.get("disposition") and item["disposition"] not in VALID_DISPOSITIONS:
            errors.append(f"Agent {agent_id}: mechanical_dispositions[{index}].disposition invalid")
        if item.get("final_severity") and item["final_severity"] not in VALID_SEVERITIES:
            errors.append(f"Agent {agent_id}: mechanical_dispositions[{index}].final_severity invalid")

    for index, item in enumerate(data.get("high_risk_modules", [])):
        module = item.get("module", "")
        if module and not isinstance(module, str):
            item["module"] = str(module)
        for key in DIMENSION_KEYS:
            value = item.get(key)
            if value in ("true", "false"):
                item[key] = value == "true"
            elif value not in (None, True, False):
                errors.append(f"Agent {agent_id}: high_risk_modules[{index}].{key} invalid")

    return errors


def load_agent_payload(result_path: Path, agent_id: str) -> dict | None:
    if not result_path.exists():
        print(f"[WARN] Missing Agent {agent_id} result: {result_path}")
        return None
    try:
        data = json.loads(result_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Agent {agent_id} JSON parse failed: {exc}")
        return None

    errors = validate_agent_result(data, agent_id)
    if errors:
        print(f"[WARN] Agent {agent_id} payload had format issues:")
        for error in errors:
            print(f"  - {error}")
    return data


def validate_slice_outputs(review_dir: Path) -> list[str]:
    """Validate small-slice subagent artifacts before route convergence.

    If a slice manifest exists, convergence must not silently proceed from
    three hand-written route JSON files while slice JSONs are missing.  This
    catches the compact-risk failure mode where subagent work only survives in
    chat transcripts or one oversized agent result.
    """
    manifest_path = review_dir / "agent_prompts" / "agent_slice_manifest.json"
    if not manifest_path.exists():
        return []

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return [f"agent_slice_manifest.json parse failed: {exc}"]

    errors: list[str] = []
    for index, item in enumerate(manifest.get("slices", [])):
        result_value = item.get("result_file", "")
        if not result_value:
            errors.append(f"slices[{index}] missing result_file")
            continue
        result_path = Path(result_value)
        if not result_path.is_absolute() and not result_path.exists():
            result_path = review_dir / result_path
        if not result_path.exists():
            errors.append(f"missing slice result: {result_path}")
            continue
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            errors.append(f"slice JSON parse failed: {result_path}: {exc}")
            continue
        for key in REQUIRED_SLICE_KEYS:
            if key not in payload:
                errors.append(f"slice missing key {key}: {result_path}")
        if payload.get("status") not in ("completed", "blocked"):
            errors.append(f"slice status invalid: {result_path}: {payload.get('status')}")
        expected_agent = item.get("agent")
        if expected_agent and payload.get("agent") != expected_agent:
            errors.append(
                f"slice agent mismatch: {result_path}: expected {expected_agent}, got {payload.get('agent')}"
            )
    return errors


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python convergence_compare.py <review_dir>")
        raise SystemExit(1)

    review_dir = Path(sys.argv[1])
    results_dir = review_dir / "agent_results"

    slice_errors = validate_slice_outputs(review_dir)
    if slice_errors:
        print("[ERROR] Small-slice subagent artifacts are incomplete; refusing convergence:")
        for error in slice_errors:
            print(f"  - {error}")
        raise SystemExit(2)

    findings_by_agent: dict[str, list[dict]] = {}
    summaries: dict[str, dict] = {}
    mechanical_by_agent: dict[str, list[dict]] = {}
    high_risk_by_agent: dict[str, list[dict]] = {}

    for agent_id in ("A", "B", "C"):
        payload = load_agent_payload(results_dir / f"agent_{agent_id.lower()}_result.json", agent_id)
        if payload is None:
            continue
        findings_by_agent[agent_id] = payload.get("findings", [])
        summaries[agent_id] = payload.get("summary", {})
        mechanical_by_agent[agent_id] = payload.get("mechanical_dispositions", [])
        high_risk_by_agent[agent_id] = payload.get("high_risk_modules", [])

    if len(findings_by_agent) < 2:
        raise SystemExit("Error: at least two agent results are required.")

    groups = match_findings(findings_by_agent)
    classified = classify_groups(groups, total_agents=len(findings_by_agent))
    metrics = compute_metrics(classified, len(groups))
    mechanical_summary = aggregate_mechanical_dispositions(mechanical_by_agent)
    high_risk_summary = aggregate_high_risk_modules(high_risk_by_agent)
    arbitration_queue = build_arbitration_queue(classified)
    converged = metrics["consensus_rate"] >= 95 and metrics["divergent_rate"] < 5

    report = build_json_report(
        metrics=metrics,
        convergence_status=converged,
        summaries=summaries,
        classified=classified,
        mechanical_summary=mechanical_summary,
        high_risk_summary=high_risk_summary,
        arbitration_queue=arbitration_queue,
    )

    json_path = review_dir / "convergence_report.json"
    md_path = review_dir / "convergence_report.md"
    arbitration_path = review_dir / "arbitration_queue.json"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        generate_markdown_report(
            classified=classified,
            metrics=metrics,
            summaries=summaries,
            mechanical_summary=mechanical_summary,
            high_risk_summary=high_risk_summary,
            arbitration_queue=arbitration_queue,
        ),
        encoding="utf-8",
    )
    arbitration_path.write_text(json.dumps(arbitration_queue, ensure_ascii=False, indent=2), encoding="utf-8")

    append_event(
        review_dir,
        "convergence_completed",
        actor="convergence_compare",
        outputs=[str(json_path), str(md_path), str(arbitration_path)],
        details={"converged": converged, "arbitration_items": len(arbitration_queue)},
    )

    print(f"convergence json: {json_path}")
    print(f"convergence markdown: {md_path}")
    print(f"arbitration queue: {arbitration_path}")
    print(f"converged={converged}")


if __name__ == "__main__":
    main()
