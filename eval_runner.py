#!/usr/bin/env python3
"""Standalone evaluation runner for the Schema-Driven Policy Workflow Agent.

Reads specs/evaluation-cases.yaml, runs every behavioral case through the
deterministic PolicyEngine and every formatter-immutability case through the
message formatter, and prints a pass/fail summary.

Usage:
    python eval_runner.py            # summary
    python eval_runner.py --verbose  # also print each decision object

Exit code is 0 only when every case passes, so this can gate CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from app.message_formatter import format_decision
from app.models import Decision, DecisionType, ReasonCode, RiskLevel
from app.policy_engine import PolicyEngine

CASES_PATH = Path(__file__).resolve().parent / "specs" / "evaluation-cases.yaml"

PASS = "\u2705"
FAIL = "\u274c"


def run(verbose: bool = False) -> int:
    with open(CASES_PATH, "r", encoding="utf-8") as fh:
        cases = yaml.safe_load(fh)["eval_cases"]

    engine = PolicyEngine()
    passed = 0
    failed = 0

    for case in cases:
        name = case["name"]

        if case.get("type") == "formatter_immutability":
            ok, detail = _run_formatter_case(case)
        else:
            ok, detail = _run_behavior_case(case, engine, verbose)

        if ok:
            passed += 1
            print(f"{PASS} {name}")
        else:
            failed += 1
            print(f"{FAIL} {name}")
            print(f"   {detail}")

        if verbose and detail and ok:
            print(f"   {detail}")

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def _run_behavior_case(case: dict, engine: PolicyEngine, verbose: bool) -> tuple[bool, str]:
    decision = format_decision(engine.evaluate(case["input"]))
    got_codes = [rc.value for rc in decision.reason_codes]

    exp_decision = case["expected_decision"]
    exp_code = case["must_include_reason_code"]

    if decision.decision.value != exp_decision:
        return False, f"expected {exp_decision}, got {decision.decision.value} with {got_codes}"
    if exp_code not in got_codes:
        return False, f"expected reason code {exp_code}, got {got_codes}"

    detail = json.dumps(decision.to_dict(), indent=2) if verbose else ""
    return True, detail


def _run_formatter_case(case: dict) -> tuple[bool, str]:
    fd = case["finalized_decision"]
    original = Decision(
        decision=DecisionType(fd["decision"]),
        risk_level=RiskLevel(fd["risk_level"]),
        reason_codes=tuple(ReasonCode(rc) for rc in fd["reason_codes"]),
        request_id=fd["request_id"],
    )
    formatted = format_decision(original)
    for field_name in case["invariant_fields"]:
        if getattr(formatted, field_name) != getattr(original, field_name):
            return False, f"formatter mutated authority field '{field_name}'"
    if not formatted.audit_summary:
        return False, "formatter did not produce an audit_summary"
    return True, ""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="print each decision object")
    args = parser.parse_args()
    sys.exit(run(verbose=args.verbose))
