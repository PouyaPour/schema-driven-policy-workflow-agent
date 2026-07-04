"""Core data models for the Schema-Driven Policy Workflow Agent.

These are plain data structures. All validation logic lives in
schema_validator.py, and all decision logic lives in policy_engine.py.
Keeping models free of behavior keeps the authority path easy to audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DecisionType(str, Enum):
    """The five possible governance outcomes (spec section 11)."""

    AUTO_APPROVED = "AUTO_APPROVED"
    REQUIRES_HUMAN_REVIEW = "REQUIRES_HUMAN_REVIEW"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
    BLOCKED_UNKNOWN_ACTION = "BLOCKED_UNKNOWN_ACTION"
    BLOCKED_SCHEMA_INVALID = "BLOCKED_SCHEMA_INVALID"


class RiskLevel(str, Enum):
    """Risk levels used in the decision object (spec section 14)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReasonCode(str, Enum):
    """Stable, machine-readable reason codes (spec section 13).

    Categories describe the source of the evidence, not a one-to-one mapping
    to decision types (e.g. WORKFLOW_NOT_DEFINED is a contract-layer code but
    yields BLOCKED_BY_POLICY).
    """

    # schema
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_FIELD_TYPE = "INVALID_FIELD_TYPE"
    INVALID_ACTION_PAYLOAD = "INVALID_ACTION_PAYLOAD"

    # contract
    WORKFLOW_NOT_DEFINED = "WORKFLOW_NOT_DEFINED"
    TARGET_ACTION_NOT_DEFINED = "TARGET_ACTION_NOT_DEFINED"
    ACTION_NOT_ALLOWED_FOR_WORKFLOW = "ACTION_NOT_ALLOWED_FOR_WORKFLOW"

    # policy
    ACTION_BLOCKED_IN_ENVIRONMENT = "ACTION_BLOCKED_IN_ENVIRONMENT"
    PII_NOT_ALLOWED_FOR_ACTION = "PII_NOT_ALLOWED_FOR_ACTION"
    EXTERNAL_SIDE_EFFECT_BLOCKED = "EXTERNAL_SIDE_EFFECT_BLOCKED"
    PRODUCTION_ACTION_REQUIRES_REVIEW = "PRODUCTION_ACTION_REQUIRES_REVIEW"

    # review
    CONTAINS_PII = "CONTAINS_PII"
    HIGH_RISK_ACTION = "HIGH_RISK_ACTION"
    EXTERNAL_SIDE_EFFECT = "EXTERNAL_SIDE_EFFECT"
    PRODUCTION_ENVIRONMENT = "PRODUCTION_ENVIRONMENT"
    MONETARY_VALUE_REQUIRES_REVIEW = "MONETARY_VALUE_REQUIRES_REVIEW"

    # approval
    LOW_RISK_ACTION = "LOW_RISK_ACTION"
    SAFE_ENVIRONMENT = "SAFE_ENVIRONMENT"
    NO_PII_DETECTED = "NO_PII_DETECTED"
    NO_EXTERNAL_SIDE_EFFECT = "NO_EXTERNAL_SIDE_EFFECT"


VALID_ENVIRONMENTS = ("local", "staging", "production")

# Required top-level fields of a WorkflowActionRequest (spec 7.2).
REQUIRED_REQUEST_FIELDS = (
    "request_id",
    "workflow_id",
    "requester",
    "environment",
    "target_action",
    "action_payload",
    "risk_context",
)


@dataclass(frozen=True)
class Decision:
    """The result of evaluating one WorkflowActionRequest (spec section 15).

    Authority fields (decision, risk_level, reason_codes) are produced only by
    the policy engine. Presentation fields (human_review_message,
    audit_summary) may be filled by the formatter, which must never mutate the
    authority fields — this dataclass is frozen to make accidental mutation an
    error rather than a silent bug.
    """

    decision: DecisionType
    risk_level: RiskLevel
    reason_codes: tuple[ReasonCode, ...]
    request_id: Optional[str] = None
    human_review_message: Optional[str] = None
    audit_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "decision": self.decision.value,
            "risk_level": self.risk_level.value,
            "reason_codes": [rc.value for rc in self.reason_codes],
            "human_review_message": self.human_review_message,
            "audit_summary": self.audit_summary,
        }


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a validation step: either ok, or a list of reason codes."""

    ok: bool
    reason_codes: tuple[ReasonCode, ...] = field(default_factory=tuple)

    @classmethod
    def valid(cls) -> "ValidationResult":
        return cls(ok=True)

    @classmethod
    def invalid(cls, *codes: ReasonCode) -> "ValidationResult":
        return cls(ok=False, reason_codes=tuple(codes))
