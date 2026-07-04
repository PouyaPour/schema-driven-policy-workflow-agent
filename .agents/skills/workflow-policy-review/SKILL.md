# Workflow Policy Review Skill

Use this skill when changing workflow contracts, action contracts, policies,
the policy engine, the agent wrappers, MCP tools, or evaluation cases in the
Schema-Driven Policy Workflow Agent project.

This project is a production-oriented pre-execution governance layer. Its most
important rule is:

> The deterministic policy engine owns approval decisions. The LLM or
> formatter may explain decisions, but must never override them.

## Core Principles

1. **Policy engine is the only authority**
   - `decision`, `risk_level`, and `reason_codes` must be produced by deterministic code.
   - LLMs, formatters, ADK wrappers, and MCP tools must not mutate authority fields.

2. **Fail closed**
   - Unknown workflows are blocked.
   - Unknown actions are blocked.
   - Invalid schemas are blocked.
   - Unrecognized human input never counts as approval.
   - Missing governance files are configuration errors, not empty rule sets.

3. **Execution order is authoritative**
   - The system evaluates one layer at a time and stops at the earliest failing layer.
   - Do not collect all possible errors and then sort them.
   - If the execution order changes, update `specs/capstone-spec.md`, eval cases, and tests together.

4. **Contracts are trusted; runtime requests are untrusted**
   - Inherent action properties such as `external_side_effect` and `risk_level` must come from `schemas/action_contracts.yaml`.
   - Do not trust request payloads to declare whether an action has external side effects.

5. **Human approval is not policy override**
   - Human approval can only resume requests that already returned `REQUIRES_HUMAN_REVIEW`.
   - Human approval must never turn `BLOCKED_BY_POLICY`, `BLOCKED_UNKNOWN_ACTION`, or `BLOCKED_SCHEMA_INVALID` into executable actions.
   - Approval changes workflow status, never the policy decision object.

## Review Checklist

When adding or modifying a workflow:

- [ ] `schemas/workflow_contracts.yaml` includes the workflow.
- [ ] Allowed actions are explicit.
- [ ] Tests cover allowed and disallowed workflow/action combinations.

When adding or modifying an action:

- [ ] `schemas/action_contracts.yaml` includes the action.
- [ ] `risk_level` is set.
- [ ] `external_side_effect` is set in the contract, not read from request input.
- [ ] `required_payload_fields` are defined.
- [ ] High-risk or external-side-effect actions have review conditions.
- [ ] Unknown or unsafe actions remain denied by default.

When modifying policies:

- [ ] `policies/policies.yaml` keeps `llm_can_override_decision: false`.
- [ ] Review conditions use OR semantics unless the spec is deliberately updated.
- [ ] Monetary threshold behavior remains covered by tests if changed.
- [ ] Blocking rules are evaluated before review rules.

When modifying the policy engine:

- [ ] The evaluation order still matches `specs/capstone-spec.md` section 12.
- [ ] The earliest failing layer still wins.
- [ ] Reason codes remain stable and machine-readable.
- [ ] No free-text reason is used for decisions.
- [ ] New behavior has unit tests AND eval cases in `specs/evaluation-cases.yaml`.

When modifying the formatter or LLM layer:

- [ ] It does not change `decision`.
- [ ] It does not change `risk_level`.
- [ ] It does not add, remove, or rewrite `reason_codes`.
- [ ] It may only update presentation fields (`human_review_message`, `audit_summary`).
- [ ] Formatter immutability tests still pass.

When modifying MCP tools:

- [ ] MCP tools remain read-only.
- [ ] MCP tools do not execute emails, payments, external API calls, database writes, or deployments.
- [ ] MCP tools only expose workflow contracts, action contracts, policies, or allowed actions.
- [ ] MCP changes do not bypass the policy engine.

When modifying agent wrapper / ADK behavior:

- [ ] The wrapper calls the deterministic policy engine; it never decides.
- [ ] The wrapper maps policy decisions to workflow statuses.
- [ ] `AUTO_APPROVED` may proceed.
- [ ] `REQUIRES_HUMAN_REVIEW` may pause and later resume only after explicit approval.
- [ ] Blocked decisions always stop, regardless of any human input.
- [ ] Unrecognized human input keeps the request pending (fail-closed).

## Required Checks Before Commit

```bash
python -m pytest -q
python eval_runner.py
python mcp/client_demo.py
```

Expected:

- pytest passes with zero failures.
- eval_runner reports all evaluation cases passed with exit code 0.
- The MCP client lists the four read-only governance tools and every lookup succeeds.

## Files Usually Involved

- `specs/capstone-spec.md` (source of truth — update it first, then code)
- `specs/evaluation-cases.yaml`
- `schemas/workflow_contracts.yaml`
- `schemas/action_contracts.yaml`
- `policies/policies.yaml`
- `app/policy_engine.py`
- `app/schema_validator.py`
- `app/message_formatter.py`
- `app/agent.py`
- `app/adk_agent.py`
- `mcp/server.py`
- `tests/`
