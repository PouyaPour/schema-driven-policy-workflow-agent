"""Shared fixtures for the test suite."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from app.contract_loader import ContractProvider
from app.policy_engine import PolicyEngine


@pytest.fixture(scope="session")
def provider() -> ContractProvider:
    return ContractProvider()


@pytest.fixture(scope="session")
def engine(provider: ContractProvider) -> PolicyEngine:
    return PolicyEngine(provider)


@pytest.fixture()
def valid_request() -> dict[str, Any]:
    """A fully valid, low-risk request (spec 24.1). Tests copy and mutate it."""
    return copy.deepcopy(
        {
            "request_id": "req_test_0001",
            "workflow_id": "customer_onboarding",
            "workflow_run_id": "run_test_001",
            "requester": {"id": "user_1", "role": "operator"},
            "environment": "staging",
            "target_action": "generate_report",
            "action_payload": {"report_type": "summary", "format": "pdf"},
            "risk_context": {"contains_pii": False, "monetary_value": None},
        }
    )


@pytest.fixture()
def valid_email_request() -> dict[str, Any]:
    """A structurally valid send_email request (high-risk action)."""
    return copy.deepcopy(
        {
            "request_id": "req_test_0002",
            "workflow_id": "customer_onboarding",
            "requester": {"id": "user_1", "role": "operator"},
            "environment": "staging",
            "target_action": "send_email",
            "action_payload": {
                "recipient": "[[APPROVED_TEST_EMAIL]]",
                "subject": "Hi",
                "body": "Welcome",
            },
            "risk_context": {"contains_pii": False, "monetary_value": None},
        }
    )
