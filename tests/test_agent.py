"""Tests for the local governance agent wrapper (Phase 5A).

The critical guarantees here (tests 6-9 of the plan): human approval only has
authority over REQUIRES_HUMAN_REVIEW; it can never resurrect a blocked
request, and it never mutates the original policy decision.
"""

from __future__ import annotations

import copy

import pytest

from app.agent import AgentStatus, NextStep, WorkflowGovernanceAgent


@pytest.fixture(scope="module")
def agent() -> WorkflowGovernanceAgent:
    return WorkflowGovernanceAgent()


def _unknown_action_request(base: dict) -> dict:
    req = copy.deepcopy(base)
    req["target_action"] = "delete_database"
    req["action_payload"] = {}
    return req


class TestStatusMapping:
    def test_safe_request_ready_to_execute(self, agent, valid_request):
        result = agent.handle_request(valid_request)
        assert result["status"] == AgentStatus.READY_TO_EXECUTE.value
        assert result["next_step"] == NextStep.EXECUTE_ACTION.value
        assert result["decision"]["decision"] == "AUTO_APPROVED"

    def test_blocked_request_stopped(self, agent, valid_email_request):
        valid_email_request["environment"] = "local"
        result = agent.handle_request(valid_email_request)
        assert result["status"] == AgentStatus.STOPPED.value
        assert result["next_step"] == NextStep.STOP_WORKFLOW.value
        assert result["decision"]["decision"] == "BLOCKED_BY_POLICY"

    def test_review_required_pending(self, agent, valid_email_request):
        result = agent.handle_request(valid_email_request)
        assert result["status"] == AgentStatus.PENDING_HUMAN_REVIEW.value
        assert result["next_step"] == NextStep.WAIT_FOR_HUMAN_APPROVAL.value
        assert result["decision"]["decision"] == "REQUIRES_HUMAN_REVIEW"
        assert result["decision"]["human_review_message"]

    def test_review_plus_approve(self, agent, valid_email_request):
        result = agent.handle_request(valid_email_request, human_decision="approve")
        assert result["status"] == AgentStatus.APPROVED_BY_HUMAN.value
        assert result["next_step"] == NextStep.EXECUTE_ACTION.value
        # The policy decision itself is untouched by approval.
        assert result["decision"]["decision"] == "REQUIRES_HUMAN_REVIEW"

    def test_review_plus_reject(self, agent, valid_email_request):
        result = agent.handle_request(valid_email_request, human_decision="reject")
        assert result["status"] == AgentStatus.REJECTED_BY_HUMAN.value
        assert result["next_step"] == NextStep.STOP_WORKFLOW.value
        assert result["decision"]["decision"] == "REQUIRES_HUMAN_REVIEW"


class TestHumanCannotOverrideBlocks:
    """The authority boundary of HITL: approval only exists for review states."""

    def test_approve_cannot_override_blocked_by_policy(self, agent, valid_email_request):
        valid_email_request["environment"] = "local"
        result = agent.handle_request(valid_email_request, human_decision="approve")
        assert result["status"] == AgentStatus.STOPPED.value
        assert result["next_step"] == NextStep.STOP_WORKFLOW.value
        assert result["decision"]["decision"] == "BLOCKED_BY_POLICY"

    def test_approve_cannot_override_blocked_unknown_action(self, agent, valid_request):
        req = _unknown_action_request(valid_request)
        result = agent.handle_request(req, human_decision="approve")
        assert result["status"] == AgentStatus.STOPPED.value
        assert result["decision"]["decision"] == "BLOCKED_UNKNOWN_ACTION"

    def test_approve_cannot_override_blocked_schema_invalid(self, agent, valid_request):
        valid_request["request_id"] = None
        result = agent.handle_request(valid_request, human_decision="approve")
        assert result["status"] == AgentStatus.STOPPED.value
        assert result["decision"]["decision"] == "BLOCKED_SCHEMA_INVALID"

    def test_approve_is_irrelevant_for_auto_approved(self, agent, valid_request):
        # Human input on a never-paused request changes nothing.
        result = agent.handle_request(valid_request, human_decision="approve")
        assert result["status"] == AgentStatus.READY_TO_EXECUTE.value


class TestFailClosedHumanInput:
    def test_unrecognized_human_decision_stays_pending(self, agent, valid_email_request):
        # Garbage input must never count as approval (fail-closed).
        result = agent.handle_request(valid_email_request, human_decision="maybe")
        assert result["status"] == AgentStatus.PENDING_HUMAN_REVIEW.value
        assert result["next_step"] == NextStep.WAIT_FOR_HUMAN_APPROVAL.value

    def test_uppercase_approve_not_accepted(self, agent, valid_email_request):
        # Strict matching: authority-granting input is compared exactly.
        result = agent.handle_request(valid_email_request, human_decision="APPROVE")
        assert result["status"] == AgentStatus.PENDING_HUMAN_REVIEW.value


class TestDecisionImmutability:
    def test_policy_decision_identical_across_human_outcomes(self, agent, valid_email_request):
        pending = agent.handle_request(copy.deepcopy(valid_email_request))
        approved = agent.handle_request(copy.deepcopy(valid_email_request), human_decision="approve")
        rejected = agent.handle_request(copy.deepcopy(valid_email_request), human_decision="reject")

        for key in ("decision", "risk_level", "reason_codes", "request_id"):
            assert pending["decision"][key] == approved["decision"][key] == rejected["decision"][key]
