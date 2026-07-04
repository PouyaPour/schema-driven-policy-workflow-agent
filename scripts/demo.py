#!/usr/bin/env python3
"""Run every sample request in examples/ through the governance agent.

This is the "clone and see it work" entry point:

    python scripts/demo.py

For the review-required example it also demonstrates the HITL cycle: the
same request is shown pending, then approved, then rejected — while the
policy decision itself stays REQUIRES_HUMAN_REVIEW throughout (human input
changes workflow status, never the policy decision).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from app.agent import WorkflowGovernanceAgent  # noqa: E402

EXAMPLES_DIR = _PROJECT_ROOT / "examples"


def show(title: str, result: dict) -> None:
    decision = result["decision"]
    print(f"\n--- {title} ---")
    print(f"status      : {result['status']}")
    print(f"next_step   : {result['next_step']}")
    print(f"decision    : {decision['decision']}  (risk: {decision['risk_level']})")
    print(f"reasons     : {', '.join(decision['reason_codes'])}")
    print(f"audit       : {decision['audit_summary']}")
    if decision.get("human_review_message"):
        print(f"review msg  : {decision['human_review_message']}")


def main() -> None:
    agent = WorkflowGovernanceAgent()

    for path in sorted(EXAMPLES_DIR.glob("*.json")):
        request = json.loads(path.read_text(encoding="utf-8"))
        show(path.stem, agent.handle_request(request))

        # For the review-required example, walk the full HITL cycle.
        if path.stem == "review_required_email":
            show(f"{path.stem}  + human approve", agent.handle_request(request, human_decision="approve"))
            show(f"{path.stem}  + human reject", agent.handle_request(request, human_decision="reject"))

    print(
        "\nNote: in every human-review outcome above, the policy decision stayed"
        " REQUIRES_HUMAN_REVIEW — approval changes workflow status, never the"
        " policy decision."
    )


if __name__ == "__main__":
    main()
