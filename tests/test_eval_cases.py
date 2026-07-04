"""Behavioral evaluation tests: run every case in specs/evaluation-cases.yaml.

Unit tests verify components; these verify AGENT BEHAVIOR against the spec's
own evaluation cases (spec 19-20). The YAML file is the shared source: the
eval runner, this test module, and any future CI all read the same cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.message_formatter import format_decision
from app.models import Decision, DecisionType, ReasonCode, RiskLevel
from app.policy_engine import PolicyEngine

_CASES_PATH = Path(__file__).resolve().parent.parent / "specs" / "evaluation-cases.yaml"


def _load_cases() -> list[dict]:
    with open(_CASES_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)["eval_cases"]


_ALL_CASES = _load_cases()
_BEHAVIOR_CASES = [c for c in _ALL_CASES if c.get("type") != "formatter_immutability"]
_FORMATTER_CASES = [c for c in _ALL_CASES if c.get("type") == "formatter_immutability"]


@pytest.mark.parametrize("case", _BEHAVIOR_CASES, ids=lambda c: c["name"])
def test_behavior_case(case, engine: PolicyEngine):
    decision = engine.evaluate(case["input"])
    got_codes = [rc.value for rc in decision.reason_codes]

    assert decision.decision.value == case["expected_decision"], (
        f"{case['name']}: expected {case['expected_decision']}, "
        f"got {decision.decision.value} with {got_codes}"
    )
    assert case["must_include_reason_code"] in got_codes, (
        f"{case['name']}: expected reason code {case['must_include_reason_code']}, "
        f"got {got_codes}"
    )


@pytest.mark.parametrize("case", _FORMATTER_CASES, ids=lambda c: c["name"])
def test_formatter_immutability_case(case):
    fd = case["finalized_decision"]
    original = Decision(
        decision=DecisionType(fd["decision"]),
        risk_level=RiskLevel(fd["risk_level"]),
        reason_codes=tuple(ReasonCode(rc) for rc in fd["reason_codes"]),
        request_id=fd["request_id"],
    )
    formatted = format_decision(original)
    for field_name in case["invariant_fields"]:
        assert getattr(formatted, field_name) == getattr(original, field_name), (
            f"{case['name']}: formatter mutated authority field '{field_name}'"
        )
    # And presentation was actually produced.
    assert formatted.audit_summary
