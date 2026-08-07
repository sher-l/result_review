#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Validate a review's sealed final decision contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_contract import atomic_write_json, contract_mode, validate_review_contract
from policy_loader import load_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate final_decision and its sealed source hashes.")
    parser.add_argument("review_dir", help="Path to result_review_report/<project_id>")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    review_dir = Path(args.review_dir)
    if not review_dir.is_dir():
        raise FileNotFoundError(f"Review directory does not exist: {review_dir}")

    policy = load_policy().get("audit_contract_policy", {})
    if not isinstance(policy, dict):
        policy = {}
    result = validate_review_contract(review_dir, policy)
    validation_name = str(policy.get("validation_json", "audit_contract_validation.json") or "audit_contract_validation.json")
    validation_path = review_dir / validation_name
    atomic_write_json(validation_path, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["blocking"]:
        return int(policy.get("enforce_exit_code_on_block", 1) or 1)
    return int(policy.get("shadow_exit_code_on_would_block", 0) or 0) if not result["contract_valid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
