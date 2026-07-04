"""Contract and policy loading for the Schema-Driven Policy Workflow Agent.

The policy engine consumes a ContractProvider, not files. In v1 the provider
reads local YAML; in Phase 4 the same interface can be backed by read-only MCP
tools without touching engine logic (spec sections 12.1 step 2-3, 17).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

# Repo root = two levels above this file (app/ -> project root).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_WORKFLOW_CONTRACTS = _PROJECT_ROOT / "schemas" / "workflow_contracts.yaml"
DEFAULT_ACTION_CONTRACTS = _PROJECT_ROOT / "schemas" / "action_contracts.yaml"
DEFAULT_POLICIES = _PROJECT_ROOT / "policies" / "policies.yaml"


class ContractProvider:
    """Read-only access to workflow contracts, action contracts, and policies.

    Lookups return None for unknown ids so that the policy engine can apply
    its own deny-by-default decisions; the provider never raises for unknown
    workflows/actions (a missing file, however, is a real configuration error
    and does raise).
    """

    def __init__(
        self,
        workflow_contracts_path: Path = DEFAULT_WORKFLOW_CONTRACTS,
        action_contracts_path: Path = DEFAULT_ACTION_CONTRACTS,
        policies_path: Path = DEFAULT_POLICIES,
    ) -> None:
        self._workflows: dict[str, Any] = _load_yaml(workflow_contracts_path)["workflows"]
        self._actions: dict[str, Any] = _load_yaml(action_contracts_path)["actions"]
        self._policies: dict[str, Any] = _load_yaml(policies_path)

    # --- workflow contracts -------------------------------------------------

    def get_workflow_contract(self, workflow_id: str) -> Optional[dict[str, Any]]:
        return self._workflows.get(workflow_id)

    def list_allowed_actions(self, workflow_id: str) -> Optional[list[str]]:
        contract = self.get_workflow_contract(workflow_id)
        if contract is None:
            return None
        return list(contract.get("allowed_actions", []))

    # --- action contracts ---------------------------------------------------

    def get_action_contract(self, target_action: str) -> Optional[dict[str, Any]]:
        return self._actions.get(target_action)

    # --- policies -----------------------------------------------------------

    def get_policy_rules(self) -> dict[str, Any]:
        return self._policies


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Required governance file not found: {path}. "
            "The system is fail-closed and cannot run without its contracts."
        )
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Governance file is not a mapping: {path}")
    return data
