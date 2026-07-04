"""Local governance agent wrapper (Phase 5A).

WorkflowGovernanceAgent orchestrates the flow around the deterministic core;
it is NOT a decision-maker. Spec section 18 applies to any wrapper (local or
ADK): the wrapper may orchestrate, call the engine, pause for human review,
and format output — it may never override the policy engine.

Pipeline:

    request
      -> PolicyEngine.evaluate()          (authority)
      -> format_decision()                (presentation)
      -> map decision to workflow status  (orchestration)
      -> optionally apply human decision  (only on REQUIRES_HUMAN_REVIEW)

Authority rules enforced here:

  - A human decision affects ONLY requests whose policy decision is
    REQUIRES_HUMAN_REVIEW. Blocked decisions stay STOPPED no matter what a
    human says: HITL is a checkpoint for risky-but-valid requests, not an
    override channel for policy violations.
  - The original policy decision object is never mutated. Human approval
    changes the WORKFLOW STATUS, not the decision.
  - An unrecognized human_decision value is fail-closed: the request stays
    PENDING_HUMAN_REVIEW rather than being treated as approved.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from app.message_formatter import format_decision
from app.models import Decision, DecisionType
from app.policy_engine import PolicyEngine


class AgentStatus(str, Enum):
    """Workflow status derived from (policy decision, human decision)."""

    READY_TO_EXECUTE = "READY_TO_EXECUTE"
    STOPPED = "STOPPED"
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
    APPROVED_BY_HUMAN = "APPROVED_BY_HUMAN"
    REJECTED_BY_HUMAN = "REJECTED_BY_HUMAN"


class HumanDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class NextStep(str, Enum):
    EXECUTE_ACTION = "execute_action"
    STOP_WORKFLOW = "stop_workflow"
    WAIT_FOR_HUMAN_APPROVAL = "wait_for_human_approval"


_BLOCKED_DECISIONS = frozenset(
    {
        DecisionType.BLOCKED_BY_POLICY,
        DecisionType.BLOCKED_UNKNOWN_ACTION,
        DecisionType.BLOCKED_SCHEMA_INVALID,
    }
)


class WorkflowGovernanceAgent:
    """Thin orchestration layer over the deterministic governance core."""

    def __init__(self, engine: Optional[PolicyEngine] = None) -> None:
        self._engine = engine or PolicyEngine()

    def handle_request(
        self,
        request: dict[str, Any],
        human_decision: Optional[str] = None,
    ) -> dict[str, Any]:
        """Evaluate a request and return the workflow status envelope.

        `human_decision` may be provided when a prior evaluation returned
        REQUIRES_HUMAN_REVIEW (in a real system this arrives later, from an
        authenticated approval surface; here it is a parameter for the local
        simulation). It is ignored for every non-review decision.
        """
        decision = format_decision(self._engine.evaluate(request))
        status, next_step = self._resolve_status(decision, human_decision)
        return {
            "status": status.value,
            "next_step": next_step.value,
            "decision": decision.to_dict(),
        }

    # --- status mapping -------------------------------------------------------

    @staticmethod
    def _resolve_status(
        decision: Decision, human_decision: Optional[str]
    ) -> tuple[AgentStatus, NextStep]:
        # Blocked states are terminal. Human input is deliberately ignored:
        # approval authority over policy violations does not exist (spec 6.2,
        # "Approve a blocked request" is forbidden for every non-engine actor).
        if decision.decision in _BLOCKED_DECISIONS:
            return AgentStatus.STOPPED, NextStep.STOP_WORKFLOW

        if decision.decision == DecisionType.AUTO_APPROVED:
            # Human input is irrelevant here too: the request never paused.
            return AgentStatus.READY_TO_EXECUTE, NextStep.EXECUTE_ACTION

        # REQUIRES_HUMAN_REVIEW — the only state where a human has authority.
        if human_decision == HumanDecision.APPROVE.value:
            return AgentStatus.APPROVED_BY_HUMAN, NextStep.EXECUTE_ACTION
        if human_decision == HumanDecision.REJECT.value:
            return AgentStatus.REJECTED_BY_HUMAN, NextStep.STOP_WORKFLOW

        # No human decision yet, or an unrecognized value: fail-closed, keep
        # waiting. Garbage input must never count as approval.
        return AgentStatus.PENDING_HUMAN_REVIEW, NextStep.WAIT_FOR_HUMAN_APPROVAL
