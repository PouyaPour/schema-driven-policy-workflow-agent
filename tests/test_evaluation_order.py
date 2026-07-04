"""Evaluation-order precedence tests (spec 12.2-12.4).

These are the tests that PROVE the pipeline is deterministic: when a request
has several problems at once, the earliest failing layer always wins, and the
same input always yields the same single decision.
"""

from __future__ import annotations

from app.models import DecisionType, ReasonCode


class TestLayerPrecedence:
    def test_schema_invalid_beats_unknown_action(self, engine, valid_request):
        # Missing request_id AND unknown action -> schema layer wins.
        valid_request["request_id"] = None
        valid_request["target_action"] = "delete_database"
        valid_request["action_payload"] = {}
        d = engine.evaluate(valid_request)
        assert d.decision == DecisionType.BLOCKED_SCHEMA_INVALID
        assert ReasonCode.MISSING_REQUIRED_FIELD in d.reason_codes
        assert ReasonCode.TARGET_ACTION_NOT_DEFINED not in d.reason_codes

    def test_unknown_workflow_beats_unknown_action(self, engine, valid_request):
        # Workflow lookup (layer 2) runs before the unknown-action guard
        # (layer 4). Execution order is authoritative (spec 12.4).
        valid_request["workflow_id"] = "unknown_workflow"
        valid_request["target_action"] = "delete_database"
        valid_request["action_payload"] = {}
        d = engine.evaluate(valid_request)
        assert d.decision == DecisionType.BLOCKED_BY_POLICY
        assert ReasonCode.WORKFLOW_NOT_DEFINED in d.reason_codes
        assert ReasonCode.TARGET_ACTION_NOT_DEFINED not in d.reason_codes

    def test_workflow_permission_beats_invalid_payload(self, engine, valid_email_request):
        # Known action not allowed for workflow (layer 5) AND missing payload
        # field (layer 6): layer 5 wins.
        valid_email_request["workflow_id"] = "internal_reporting"
        del valid_email_request["action_payload"]["subject"]
        d = engine.evaluate(valid_email_request)
        assert d.decision == DecisionType.BLOCKED_BY_POLICY
        assert ReasonCode.ACTION_NOT_ALLOWED_FOR_WORKFLOW in d.reason_codes
        assert ReasonCode.INVALID_ACTION_PAYLOAD not in d.reason_codes

    def test_unknown_action_beats_environment_block_and_review(self, engine, valid_request):
        # Unknown action in local with PII: multiple risk signals present,
        # but the unknown-action guard (layer 4) stops evaluation first.
        valid_request["environment"] = "local"
        valid_request["target_action"] = "delete_database"
        valid_request["action_payload"] = {}
        valid_request["risk_context"]["contains_pii"] = True
        d = engine.evaluate(valid_request)
        assert d.decision == DecisionType.BLOCKED_UNKNOWN_ACTION
        assert d.reason_codes == (ReasonCode.TARGET_ACTION_NOT_DEFINED,)

    def test_environment_block_beats_review_conditions(self, engine, valid_email_request):
        # Local email with PII: blocking (layer 7) wins over review (layer 8);
        # a blocked action never reaches the review layer.
        valid_email_request["environment"] = "local"
        valid_email_request["risk_context"]["contains_pii"] = True
        d = engine.evaluate(valid_email_request)
        assert d.decision == DecisionType.BLOCKED_BY_POLICY
        assert ReasonCode.ACTION_BLOCKED_IN_ENVIRONMENT in d.reason_codes
        assert ReasonCode.CONTAINS_PII not in d.reason_codes


class TestDeterminism:
    def test_same_input_same_output(self, engine, valid_email_request):
        # The core governance property: identical requests always yield
        # identical decisions — no randomness, no drift.
        first = engine.evaluate(valid_email_request)
        second = engine.evaluate(valid_email_request)
        assert first.decision == second.decision
        assert first.risk_level == second.risk_level
        assert first.reason_codes == second.reason_codes
