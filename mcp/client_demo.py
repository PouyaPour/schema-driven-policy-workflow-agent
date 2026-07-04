"""MCP client demo: connect to the governance server over stdio and call
every read-only tool.

This demonstrates the Phase 4 idea end to end: an agent-side client retrieves
workflow contracts, action contracts, and policy rules through MCP — the same
knowledge the deterministic policy engine uses — without gaining any decision
authority or side-effect capability.

Run from the repo root:

    python mcp/client_demo.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SERVER_PATH = _PROJECT_ROOT / "mcp" / "server.py"


def _print_result(title: str, result) -> None:
    print(f"\n=== {title} ===")
    for block in result.content:
        if getattr(block, "type", None) == "text":
            try:
                print(json.dumps(json.loads(block.text), indent=2))
            except (json.JSONDecodeError, TypeError):
                print(block.text)


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(_SERVER_PATH)],
        cwd=str(_PROJECT_ROOT),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Available read-only governance tools:")
            for tool in tools.tools:
                print(f"  - {tool.name}")

            _print_result(
                "get_action_contract('send_email')",
                await session.call_tool("get_action_contract", {"target_action": "send_email"}),
            )

            _print_result(
                "get_action_contract('delete_database')  [unknown -> not found]",
                await session.call_tool("get_action_contract", {"target_action": "delete_database"}),
            )

            _print_result(
                "get_workflow_contract('internal_reporting')",
                await session.call_tool("get_workflow_contract", {"workflow_id": "internal_reporting"}),
            )

            _print_result(
                "list_allowed_actions('customer_onboarding')",
                await session.call_tool("list_allowed_actions", {"workflow_id": "customer_onboarding"}),
            )

            _print_result(
                "get_policy_rules()",
                await session.call_tool("get_policy_rules", {}),
            )


if __name__ == "__main__":
    asyncio.run(main())
