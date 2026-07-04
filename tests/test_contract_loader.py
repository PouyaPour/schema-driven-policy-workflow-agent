"""Unit tests for contract_loader.py (read-only contract/policy access)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.contract_loader import ContractProvider


class TestWorkflowContracts:
    def test_known_workflow_loads(self, provider):
        contract = provider.get_workflow_contract("customer_onboarding")
        assert contract is not None
        assert "send_email" in contract["allowed_actions"]

    def test_unknown_workflow_returns_none(self, provider):
        assert provider.get_workflow_contract("nonexistent_workflow") is None

    def test_list_allowed_actions(self, provider):
        actions = provider.list_allowed_actions("internal_reporting")
        assert actions == ["generate_report"]

    def test_list_allowed_actions_unknown_workflow(self, provider):
        assert provider.list_allowed_actions("nonexistent_workflow") is None


class TestActionContracts:
    def test_known_action_loads(self, provider):
        contract = provider.get_action_contract("send_email")
        assert contract is not None
        assert contract["risk_level"] == "high"
        assert contract["external_side_effect"] is True

    def test_unknown_action_returns_none(self, provider):
        assert provider.get_action_contract("delete_database") is None


class TestPolicies:
    def test_policy_rules_load(self, provider):
        policies = provider.get_policy_rules()
        assert policies["defaults"]["llm_can_override_decision"] is False
        assert policies["defaults"]["unknown_action"] == "block"
        assert policies["defaults"]["unknown_workflow"] == "block"

    def test_monetary_threshold_present(self, provider):
        threshold = provider.get_policy_rules()["human_review"]["monetary_value_threshold"]
        assert threshold["amount_gte"] == 100
        assert threshold["currency"] == "USD"


class TestFailClosedLoading:
    def test_missing_file_raises(self, tmp_path: Path):
        # A governance system must refuse to start without its contracts,
        # rather than silently running with empty rules (fail-closed).
        with pytest.raises(FileNotFoundError):
            ContractProvider(workflow_contracts_path=tmp_path / "missing.yaml")
