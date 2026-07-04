"""Unit tests for policy_engine.py — one test per governance behavior."""

from __future__ import annotations

from app.models import DecisionType, ReasonCode, RiskLevel


class TestAutoApproval:
    def test_safe_report_auto_approved(self, engine, valid_request):
        d = engine.evaluate(valid_request)
        assert d.decision == DecisionType.AUTO_APPROVED
        assert d.risk_level == RiskLevel.LOW
        assert ReasonCode.LOW_RISK_ACTION in d.reason_codes
        assert d.request_id == valid_request["request_id"]


class TestHumanReview:
    def test_pii_report_requires_review(self, engine, valid_request):
        valid_request["risk_context"]["contains_pii"] = True
        d = engine.evaluate(valid_request)
        assert d.decision == DecisionType.REQUIRES_HUMAN_REVIEW
        assert ReasonCode.CONTAINS_PII in d.reason_codes
        assert d.risk_level == RiskLevel.HIGH  # PII is a high signal

    def test_monetary_over_threshold_requires_review(self, engine, valid_request):
        valid_request["risk_context"]["monetary_value"] = {"amount": 250, "currency": "USD"}
        d = engine.evaluate(valid_request)
        assert d.decision == DecisionType.REQUIRES_HUMAN_REVIEW
        assert ReasonCode.MONETARY_VALUE_REQUIRES_REVIEW in d.reason_codes

    def test_monetary_under_threshold_auto_approves(self, engine, valid_request):
        valid_request["risk_context"]["monetary_value"] = {"amount": 40, "currency": "USD"}
        d = engine.evaluate(valid_request)
        assert d.decision == DecisionType.AUTO_APPROVED

    def test_monetary_other_currency_not_compared_in_v1(self, engine, valid_request):
        # Spec 10.3: v1 compares only when currency matches the threshold currency.
        valid_request["risk_context"]["monetary_value"] = {"amount": 9999, "currency": "EUR"}
        d = engine.evaluate(valid_request)
        assert d.decision == DecisionType.AUTO_APPROVED

    def test_high_risk_email_without_pii_requires_review(self, engine, valid_email_request):
        # Spec 10.4: high_risk_action == (contract.risk_level == "high").
        d = engine.evaluate(valid_email_request)
        assert d.decision == DecisionType.REQUIRES_HUMAN_REVIEW
        assert ReasonCode.HIGH_RISK_ACTION in d.reason_codes
        assert d.risk_level == RiskLevel.HIGH

    def test_review_collects_all_matching_codes(self, engine, valid_email_request):
        # Complete audit trail: every matched condition is reported.
        valid_email_request["environment"] = "production"
        valid_email_request["risk_context"]["contains_pii"] = True
        d = engine.evaluate(valid_email_request)
        assert d.decision == DecisionType.REQUIRES_HUMAN_REVIEW
        got = set(d.reason_codes)
        assert {
            ReasonCode.CONTAINS_PII,
            ReasonCode.PRODUCTION_ENVIRONMENT,
            ReasonCode.HIGH_RISK_ACTION,
            ReasonCode.EXTERNAL_SIDE_EFFECT,
        } <= got

    def test_production_report_requires_review(self, engine, valid_request):
        valid_request["environment"] = "production"
        d = engine.evaluate(valid_request)
        assert d.decision == DecisionType.REQUIRES_HUMAN_REVIEW
        assert ReasonCode.PRODUCTION_ENVIRONMENT in d.reason_codes


class TestPolicyBlocking:
    def test_local_email_blocked(self, engine, valid_email_request):
        valid_email_request["environment"] = "local"
        d = engine.evaluate(valid_email_request)
        assert d.decision == DecisionType.BLOCKED_BY_POLICY
        assert ReasonCode.ACTION_BLOCKED_IN_ENVIRONMENT in d.reason_codes
        assert d.risk_level == RiskLevel.CRITICAL

    def test_known_action_not_allowed_for_workflow(self, engine, valid_email_request):
        # send_email is known globally but internal_reporting only allows reports.
        valid_email_request["workflow_id"] = "internal_reporting"
        d = engine.evaluate(valid_email_request)
        assert d.decision == DecisionType.BLOCKED_BY_POLICY
        assert ReasonCode.ACTION_NOT_ALLOWED_FOR_WORKFLOW in d.reason_codes

    def test_unknown_workflow_blocked(self, engine, valid_request):
        valid_request["workflow_id"] = "totally_unknown_workflow"
        d = engine.evaluate(valid_request)
        assert d.decision == DecisionType.BLOCKED_BY_POLICY
        assert ReasonCode.WORKFLOW_NOT_DEFINED in d.reason_codes


class TestUnknownAction:
    def test_unknown_action_blocked(self, engine, valid_request):
        valid_request["target_action"] = "delete_database"
        valid_request["action_payload"] = {}
        d = engine.evaluate(valid_request)
        assert d.decision == DecisionType.BLOCKED_UNKNOWN_ACTION
        assert ReasonCode.TARGET_ACTION_NOT_DEFINED in d.reason_codes
        assert d.risk_level == RiskLevel.CRITICAL


class TestSchemaInvalid:
    def test_missing_request_id(self, engine, valid_request):
        valid_request["request_id"] = None
        d = engine.evaluate(valid_request)
        assert d.decision == DecisionType.BLOCKED_SCHEMA_INVALID
        assert ReasonCode.MISSING_REQUIRED_FIELD in d.reason_codes
        assert d.request_id is None  # spec 15.2: may be null when unusable

    def test_missing_payload_field(self, engine, valid_email_request):
        del valid_email_request["action_payload"]["subject"]
        d = engine.evaluate(valid_email_request)
        assert d.decision == DecisionType.BLOCKED_SCHEMA_INVALID
        assert ReasonCode.INVALID_ACTION_PAYLOAD in d.reason_codes
