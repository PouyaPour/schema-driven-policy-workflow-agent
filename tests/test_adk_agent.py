"""ADK integration tests (Phase 5B).

Runs GovernanceADKAgent inside ADK's InMemoryRunner — no cloud project, no
credentials, no LLM. Verifies the pause/resume HITL cycle end to end and the
no-override guarantee at the ADK layer.
"""

from __future__ import annotations

import copy

import pytest

pytest.importorskip("google.adk", reason="google-adk not installed")

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from app.adk_agent import (  # noqa: E402
    STATE_HUMAN_DECISION_KEY,
    STATE_REQUEST_KEY,
    STATE_RESULT_KEY,
    GovernanceADKAgent,
)

_APP = "governance-test-app"
_USER = "tester"


async def _run_once(runner: InMemoryRunner, session_id: str) -> list:
    message = types.Content(role="user", parts=[types.Part(text="evaluate")])
    return [
        e
        async for e in runner.run_async(
            user_id=_USER, session_id=session_id, new_message=message
        )
    ]


async def _make_session(runner: InMemoryRunner, state: dict):
    return await runner.session_service.create_session(
        app_name=_APP, user_id=_USER, state=state
    )


async def _get_result(runner: InMemoryRunner, session_id: str) -> dict:
    session = await runner.session_service.get_session(
        app_name=_APP, user_id=_USER, session_id=session_id
    )
    return session.state.get(STATE_RESULT_KEY), session.state


@pytest.fixture()
def runner() -> InMemoryRunner:
    return InMemoryRunner(agent=GovernanceADKAgent(), app_name=_APP)


@pytest.mark.asyncio
async def test_safe_request_ready_to_execute(runner, valid_request):
    session = await _make_session(runner, {STATE_REQUEST_KEY: valid_request})
    await _run_once(runner, session.id)
    result, _ = await _get_result(runner, session.id)
    assert result["status"] == "READY_TO_EXECUTE"
    assert result["decision"]["decision"] == "AUTO_APPROVED"


@pytest.mark.asyncio
async def test_blocked_request_stopped_even_with_approval_in_state(
    runner, valid_email_request
):
    # No-override guarantee at the ADK layer: approval sitting in session
    # state cannot resurrect a policy-blocked request.
    valid_email_request["environment"] = "local"
    session = await _make_session(
        runner,
        {
            STATE_REQUEST_KEY: valid_email_request,
            STATE_HUMAN_DECISION_KEY: "approve",
        },
    )
    await _run_once(runner, session.id)
    result, _ = await _get_result(runner, session.id)
    assert result["status"] == "STOPPED"
    assert result["decision"]["decision"] == "BLOCKED_BY_POLICY"


@pytest.mark.asyncio
async def test_hitl_pause_then_approve_resume_cycle(runner, valid_email_request):
    # Run 1: risky request pauses for human review.
    session = await _make_session(runner, {STATE_REQUEST_KEY: valid_email_request})
    events = await _run_once(runner, session.id)
    result, state = await _get_result(runner, session.id)

    assert result["status"] == "PENDING_HUMAN_REVIEW"
    assert state.get("awaiting_human_review") is True
    # The pause event surfaces the human-readable review message.
    texts = [
        p.text
        for e in events
        if e.content
        for p in e.content.parts
        if getattr(p, "text", None)
    ]
    assert any("PENDING_HUMAN_REVIEW" in t for t in texts)

    # A reviewer approves: the decision lands in session state (in production
    # this write comes from an authenticated approval surface).
    session2 = await _make_session(
        runner,
        {
            STATE_REQUEST_KEY: copy.deepcopy(valid_email_request),
            STATE_HUMAN_DECISION_KEY: "approve",
        },
    )
    await _run_once(runner, session2.id)
    result2, _ = await _get_result(runner, session2.id)

    assert result2["status"] == "APPROVED_BY_HUMAN"
    assert result2["next_step"] == "execute_action"
    # The policy decision is still REQUIRES_HUMAN_REVIEW — approval changed
    # the workflow status, never the authority fields.
    assert result2["decision"]["decision"] == "REQUIRES_HUMAN_REVIEW"


@pytest.mark.asyncio
async def test_hitl_reject_stops_workflow(runner, valid_email_request):
    session = await _make_session(
        runner,
        {
            STATE_REQUEST_KEY: valid_email_request,
            STATE_HUMAN_DECISION_KEY: "reject",
        },
    )
    await _run_once(runner, session.id)
    result, _ = await _get_result(runner, session.id)
    assert result["status"] == "REJECTED_BY_HUMAN"
    assert result["next_step"] == "stop_workflow"


@pytest.mark.asyncio
async def test_missing_request_reports_error(runner):
    session = await _make_session(runner, {})
    await _run_once(runner, session.id)
    result, _ = await _get_result(runner, session.id)
    assert result == {"error": "missing_governance_request"}
