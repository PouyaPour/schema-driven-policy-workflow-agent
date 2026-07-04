"""Read-only MCP server for the Schema-Driven Policy Workflow Agent.

Exposes governance knowledge (workflow contracts, action contracts, policy
rules) to agents over the Model Context Protocol. Spec section 17:

  - MCP tools in v1 MUST be read-only.
  - They provide schema/contract/policy CONTEXT; they never execute business
    actions (no email, no payments, no writes, no deploys).

Architectural note: this server wraps the exact same ContractProvider that the
policy engine uses. MCP is an access layer over one source of truth, not a
second copy of the rules. The deterministic engine remains the only decision
authority — an agent reading contracts through MCP still cannot approve or
block anything by itself.

Run (stdio transport, the default for local MCP clients):

    python mcp/server.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Allow running as a script from the repo root or the mcp/ directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app.contract_loader import ContractProvider  # noqa: E402

server = FastMCP(
    name="workflow-governance",
    instructions=(
        "Read-only governance knowledge for workflow action requests: "
        "workflow contracts, action contracts, and policy rules. "
        "This server never executes actions and cannot approve or block "
        "requests; decisions belong to the deterministic policy engine."
    ),
)

_provider = ContractProvider()


@server.tool()
def get_workflow_contract(workflow_id: str) -> dict[str, Any]:
    """Return the contract for a workflow (its allowed actions), or a
    not-found marker if the workflow is not registered.

    Unknown workflows are denied by default by the policy engine
    (BLOCKED_BY_POLICY / WORKFLOW_NOT_DEFINED)."""
    contract = _provider.get_workflow_contract(workflow_id)
    if contract is None:
        return {"found": False, "workflow_id": workflow_id}
    return {"found": True, "workflow_id": workflow_id, "contract": contract}


@server.tool()
def get_action_contract(target_action: str) -> dict[str, Any]:
    """Return the contract for an action: risk_level, external_side_effect,
    required_payload_fields, environment rules, and review conditions.

    Unknown actions are denied by default by the policy engine
    (BLOCKED_UNKNOWN_ACTION / TARGET_ACTION_NOT_DEFINED)."""
    contract = _provider.get_action_contract(target_action)
    if contract is None:
        return {"found": False, "target_action": target_action}
    return {"found": True, "target_action": target_action, "contract": contract}


@server.tool()
def get_policy_rules() -> dict[str, Any]:
    """Return the full deterministic policy rules (defaults, auto-approval
    criteria, blocking rules, human-review conditions, monetary threshold).

    Note defaults.llm_can_override_decision is false: no reader of these
    rules gains decision authority."""
    return _provider.get_policy_rules()


@server.tool()
def list_allowed_actions(workflow_id: str) -> dict[str, Any]:
    """Return the list of actions a workflow is allowed to execute, or a
    not-found marker for unknown workflows."""
    actions = _provider.list_allowed_actions(workflow_id)
    if actions is None:
        return {"found": False, "workflow_id": workflow_id, "allowed_actions": []}
    return {"found": True, "workflow_id": workflow_id, "allowed_actions": actions}


if __name__ == "__main__":
    server.run()  # stdio transport by default
