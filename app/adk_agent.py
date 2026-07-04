"""ADK wrapper for the governance core (Phase 5B).

Wraps WorkflowGovernanceAgent (Phase 5A) in a Google ADK custom agent so the
governance flow can run inside an ADK Runner, with human-in-the-loop pause
semantics carried through session state.

Design decisions, mirroring spec section 18:

  - The ADK agent is a CUSTOM BaseAgent, not an LlmAgent. The decision path is
    deterministic and needs no model, no credentials, and no cloud project to
    run — which also makes it fully testable locally. An LLM can later be
    attached for message formatting only, with no decision authority.
  - HITL flow: when the policy decision is REQUIRES_HUMAN_REVIEW, the agent
    escalates (ends its run) with status PENDING_HUMAN_REVIEW and stores the
    pending request in session state. When the human decision arrives (via
    state, e.g. from an approval UI writing "human_decision"), a re-run
    resolves to APPROVED_BY_HUMAN or REJECTED_BY_HUMAN. This is the local
    equivalent of ADK's request-input pattern: pause, wait, resume.
  - Blocked decisions escalate immediately as STOPPED; a human decision in
    state is deliberately ignored for them (no override channel).

Session state keys:

  governance_request   (in)  the WorkflowActionRequest dict to evaluate
  human_decision       (in)  optional "approve" / "reject" from the reviewer
  governance_result    (out) the full status envelope from Phase 5A
"""

from __future__ import annotations

from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from app.agent import AgentStatus, WorkflowGovernanceAgent

STATE_REQUEST_KEY = "governance_request"
STATE_HUMAN_DECISION_KEY = "human_decision"
STATE_RESULT_KEY = "governance_result"


class GovernanceADKAgent(BaseAgent):
    """ADK custom agent: orchestration only, zero decision authority."""

    def __init__(self, name: str = "workflow_governance_agent") -> None:
        super().__init__(name=name)

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        request = state.get(STATE_REQUEST_KEY)

        if request is None:
            yield self._event(
                ctx,
                text="No governance_request found in session state.",
                state_delta={STATE_RESULT_KEY: {"error": "missing_governance_request"}},
                escalate=True,
            )
            return

        human_decision = state.get(STATE_HUMAN_DECISION_KEY)

        # The deterministic core does all the work; the ADK layer only routes.
        result = WorkflowGovernanceAgent().handle_request(
            request, human_decision=human_decision
        )
        status = result["status"]

        # PENDING means "pause and wait for a human": escalate so the runner
        # stops, keep the request in state so a follow-up run (carrying
        # human_decision in state) can resume exactly where we paused.
        pause = status == AgentStatus.PENDING_HUMAN_REVIEW.value

        summary = result["decision"]["audit_summary"]
        review_msg = result["decision"].get("human_review_message")
        text = f"[{status}] {review_msg or summary}"

        yield self._event(
            ctx,
            text=text,
            state_delta={STATE_RESULT_KEY: result},
            escalate=True,  # single-decision agent: every run ends after deciding
            pause_marker=pause,
        )

    def _event(
        self,
        ctx: InvocationContext,
        text: str,
        state_delta: dict,
        escalate: bool,
        pause_marker: bool = False,
    ) -> Event:
        if pause_marker:
            state_delta = {**state_delta, "awaiting_human_review": True}
        return Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(role="model", parts=[types.Part(text=text)]),
            actions=EventActions(escalate=escalate, state_delta=state_delta),
        )
