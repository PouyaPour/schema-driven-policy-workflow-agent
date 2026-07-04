"""Formatter immutability tests (spec 6, 19.1).

The formatter is presentation-only. These tests assert the authority boundary
structurally: decision, risk_level, reason_codes, and request_id never change;
only human_review_message and audit_summary are produced.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.message_formatter import format_decision
from app.models import Decision, DecisionType, ReasonCode, RiskLevel


def _blocked_decision() -> Decision:
    return Decision(
        decision=DecisionType.BLOCKED_BY_POLICY,
        risk_level=RiskLevel.HIGH,
        reason_codes=(ReasonCode.ACTION_BLOCKED_IN_ENVIRONMENT,),
        request_id="req_fmt_001",
    )


class TestAuthorityFieldsImmutable:
    def test_authority_fields_unchanged(self):
        original = _blocked_decision()
        formatted = format_decision(original)
        assert formatted.decision == original.decision
        assert formatted.risk_level == original.risk_level
        assert formatted.reason_codes == original.reason_codes
        assert formatted.request_id == original.request_id

    def test_original_object_untouched(self):
        # format_decision returns a NEW object; the input must be unchanged.
        original = _blocked_decision()
        format_decision(original)
        assert original.audit_summary == ""
        assert original.human_review_message is None

    def test_decision_dataclass_is_frozen(self):
        # Structural enforcement: mutation is a TypeError, not a silent bug.
        original = _blocked_decision()
        with pytest.raises(dataclasses.FrozenInstanceError):
            original.decision = DecisionType.AUTO_APPROVED  # type: ignore[misc]


class TestPresentationFields:
    def test_review_decision_gets_review_message(self, engine, valid_email_request):
        raw = engine.evaluate(valid_email_request)
        formatted = format_decision(raw)
        assert formatted.decision == DecisionType.REQUIRES_HUMAN_REVIEW
        assert formatted.human_review_message
        assert "review" in formatted.human_review_message.lower()
        assert formatted.audit_summary

    def test_auto_approval_has_no_review_message(self, engine, valid_request):
        raw = engine.evaluate(valid_request)
        formatted = format_decision(raw)
        assert formatted.decision == DecisionType.AUTO_APPROVED
        assert formatted.human_review_message is None
        assert "auto-approved" in formatted.audit_summary

    def test_blocked_decision_mentions_deny_by_default(self):
        formatted = format_decision(_blocked_decision())
        assert formatted.human_review_message is None
        assert "denies by default" in formatted.audit_summary

    def test_to_dict_shape_matches_spec(self):
        # Spec 15.1: the serialized decision object shape.
        d = format_decision(_blocked_decision()).to_dict()
        assert set(d) == {
            "request_id",
            "decision",
            "risk_level",
            "reason_codes",
            "human_review_message",
            "audit_summary",
        }
        assert isinstance(d["reason_codes"], list)
        assert all(isinstance(rc, str) for rc in d["reason_codes"])
