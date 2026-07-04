"""Message formatter — presentation layer only, no decision authority.

Spec section 6: the formatter (deterministic here, LLM-backed later) may only
produce human_review_message and audit_summary. It must never mutate
decision, risk_level, or reason_codes.

Enforcement is structural, not just contractual: Decision is a frozen
dataclass, so this module cannot mutate authority fields — it builds a NEW
Decision carrying the same authority fields plus presentation text. The
formatter-immutability eval case (spec 19.1) asserts exactly this invariant.

When an LLM formatter is added in Phase 5, it replaces only the sentence
generation below; the same construction pattern guarantees the invariant.
"""

from __future__ import annotations

from dataclasses import replace

from app.models import Decision, DecisionType, ReasonCode

# Human-readable fragments per reason code, used to compose sentences.
_REASON_TEXT: dict[ReasonCode, str] = {
    ReasonCode.MISSING_REQUIRED_FIELD: "a required field is missing from the request",
    ReasonCode.INVALID_FIELD_TYPE: "a request field has an invalid type or value",
    ReasonCode.INVALID_ACTION_PAYLOAD: "the action payload is missing required fields",
    ReasonCode.WORKFLOW_NOT_DEFINED: "the workflow is not registered in the governance contracts",
    ReasonCode.TARGET_ACTION_NOT_DEFINED: "the target action is not defined in the action contract registry",
    ReasonCode.ACTION_NOT_ALLOWED_FOR_WORKFLOW: "the action is not allowed for this workflow",
    ReasonCode.ACTION_BLOCKED_IN_ENVIRONMENT: "the action is blocked in this environment",
    ReasonCode.CONTAINS_PII: "the request contains PII",
    ReasonCode.HIGH_RISK_ACTION: "the action is classified as high risk",
    ReasonCode.EXTERNAL_SIDE_EFFECT: "the action has an external side effect",
    ReasonCode.PRODUCTION_ENVIRONMENT: "the request targets the production environment",
    ReasonCode.MONETARY_VALUE_REQUIRES_REVIEW: "the monetary value meets the review threshold",
    ReasonCode.LOW_RISK_ACTION: "the action is low risk",
    ReasonCode.SAFE_ENVIRONMENT: "the environment is safe for auto-approval",
    ReasonCode.NO_PII_DETECTED: "no PII was detected",
    ReasonCode.NO_EXTERNAL_SIDE_EFFECT: "the action has no external side effect",
    ReasonCode.PII_NOT_ALLOWED_FOR_ACTION: "PII is not allowed for this action",
    ReasonCode.EXTERNAL_SIDE_EFFECT_BLOCKED: "external side effects are blocked",
    ReasonCode.PRODUCTION_ACTION_REQUIRES_REVIEW: "production actions require review",
}


def format_decision(decision: Decision) -> Decision:
    """Return a new Decision with presentation fields filled in.

    Authority fields (decision, risk_level, reason_codes, request_id) are
    copied unchanged; dataclasses.replace on a frozen dataclass guarantees
    the originals were not mutated.
    """
    reasons_text = _join_reasons(decision.reason_codes)

    if decision.decision == DecisionType.AUTO_APPROVED:
        audit = f"The request was auto-approved because {reasons_text}."
        review_msg = None
    elif decision.decision == DecisionType.REQUIRES_HUMAN_REVIEW:
        audit = "The request was paused for human review based on deterministic policy rules."
        review_msg = f"This request requires review because {reasons_text}."
    else:
        # All blocked states.
        audit = f"The request was blocked because {reasons_text}. The system denies by default."
        review_msg = None

    return replace(decision, human_review_message=review_msg, audit_summary=audit)


def _join_reasons(codes: tuple[ReasonCode, ...]) -> str:
    parts = [_REASON_TEXT.get(code, code.value.lower().replace("_", " ")) for code in codes]
    if not parts:
        return "no reasons were recorded"
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]
