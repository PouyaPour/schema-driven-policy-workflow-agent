# Capstone Submission Summary

## Project

**Schema-Driven Policy Workflow Agent**

## One-line Summary

A production-oriented agentic workflow governance layer that validates
workflow action requests before execution using schema contracts,
deterministic policy rules, read-only MCP contract lookup, human-in-the-loop
review, and evaluation cases, while keeping the LLM outside the approval
authority path.

## Problem

Agentic systems can select and execute actions quickly, but production
workflows need guardrails before execution. A workflow action may be
incomplete, unknown, disallowed for a workflow, risky, or require human
approval.

This project adds a deterministic pre-execution governance layer between
action selection and action execution.

## What the System Does

For each `WorkflowActionRequest`, the system decides exactly one of:

- `AUTO_APPROVED`
- `REQUIRES_HUMAN_REVIEW`
- `BLOCKED_BY_POLICY`
- `BLOCKED_UNKNOWN_ACTION`
- `BLOCKED_SCHEMA_INVALID`

The pipeline is deterministic and fail-closed. The earliest failing layer wins.

## Key Design Choices

### 1. Deterministic authority

The policy engine owns approval decisions. The LLM cannot approve, reject,
block, or override decisions. This is enforced structurally: the decision
object is a frozen dataclass, and formatter-immutability tests assert that
`decision`, `risk_level`, and `reason_codes` survive formatting unchanged.

### 2. Schema and contracts as source of truth

Workflow and action contracts define allowed actions, required payload
fields, risk levels, and external side effects. Inherent action properties
are trusted only from contracts, never from runtime input.

### 3. Deny by default

Unknown workflows, unknown actions, and invalid schemas are blocked by
default. Unrecognized human input keeps a request pending instead of
counting as approval.

### 4. Human-in-the-loop for risky valid requests

Risky but valid requests pause for human approval. Human approval can resume
review-required requests, but it cannot override blocked policy decisions —
approval changes the workflow status, never the policy decision object.

### 5. Read-only MCP

MCP exposes workflow contracts, action contracts, policies, and allowed
actions as read-only tools, wrapping the same provider the engine uses (one
source of truth, two access paths). It does not execute business actions or
mutate external systems.

## Course Concepts Demonstrated

- Spec-driven development (the spec is the repo's source of truth)
- Agentic workflow governance
- MCP-backed context access
- Agent skill for workflow policy review
- Deterministic policy engine with stable machine-readable reason codes
- Human-in-the-loop review with pause/resume semantics
- Deny-by-default security guardrails
- Evaluation cases and tests (behavior verified from the same YAML the
  eval runner and pytest both read)
- ADK agent wrapper (custom `BaseAgent`, runs and is tested locally with no
  model or credentials) with session-state HITL

## How to Run

```bash
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"

python -m pytest -q
python eval_runner.py
python mcp/client_demo.py
```

Expected:

- The full test suite passes; see the CI badge for the current result.
- eval_runner reports all evaluation cases passed with exit code 0.
- The MCP client lists four read-only governance tools and every lookup succeeds.

## Demo Scenarios

1. Safe report generation in staging → `AUTO_APPROVED`
2. Report with PII → `REQUIRES_HUMAN_REVIEW`
3. Local email → `BLOCKED_BY_POLICY`
4. Unknown action → `BLOCKED_UNKNOWN_ACTION`
5. Missing request id → `BLOCKED_SCHEMA_INVALID`
6. High-risk email without PII → `REQUIRES_HUMAN_REVIEW`
7. Unknown workflow + unknown action → unknown workflow wins, because the
   execution order is authoritative
8. Blocked request + human "approve" → still `STOPPED`; approval has no
   authority over policy blocks

## Safety Notes

- No real emails are sent.
- No real payments are executed.
- No external API mutation happens in v1.
- MCP tools are read-only.
- Human approval does not override blocked decisions.
- The LLM or formatter cannot mutate authority fields.

## Future Work

- Real Agent Runtime deployment
- Authenticated approval dashboard
- Notification integrations
- Full idempotency / duplicate detection store
- Role-based approval routing
- Runtime placeholder resolver
- Spec-to-evaluation generation
