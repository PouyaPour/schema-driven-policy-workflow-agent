"""Schema validation for the Schema-Driven Policy Workflow Agent.

Two validators, matching two distinct layers of the evaluation order:

  - validate_base_request  -> layer 1 (spec 12.1 step 1)
  - validate_action_payload -> layer 6 (spec 12.1 step 6)

Both return ValidationResult with machine-readable reason codes; free text is
never used for decisions (spec section 13).

v1 scope (spec 9.1): payload validation checks required-field PRESENCE only.
Deep type/regex/JSON-Schema validation is future work.
"""

from __future__ import annotations

from typing import Any

from app.models import (
    REQUIRED_REQUEST_FIELDS,
    VALID_ENVIRONMENTS,
    ReasonCode,
    ValidationResult,
)


def validate_base_request(request: dict[str, Any]) -> ValidationResult:
    """Layer 1: validate required top-level fields and basic field shapes.

    Untrusted input rule (spec 21.5): everything in the request is untrusted,
    so shapes are checked defensively rather than assumed.
    """
    if not isinstance(request, dict):
        return ValidationResult.invalid(ReasonCode.INVALID_FIELD_TYPE)

    # Required fields must be present and non-null (spec 7.2; request_id is
    # the idempotency-lite key and its absence is a schema failure, spec 7.3).
    for field_name in REQUIRED_REQUEST_FIELDS:
        if request.get(field_name) is None:
            return ValidationResult.invalid(ReasonCode.MISSING_REQUIRED_FIELD)

    # Basic shape checks (spec 12.1 step 1: "basic field shapes for requester
    # and risk_context").
    if not isinstance(request["request_id"], str) or not request["request_id"].strip():
        return ValidationResult.invalid(ReasonCode.INVALID_FIELD_TYPE)

    if not isinstance(request["workflow_id"], str) or not request["workflow_id"].strip():
        return ValidationResult.invalid(ReasonCode.INVALID_FIELD_TYPE)

    requester = request["requester"]
    if not isinstance(requester, dict) or requester.get("id") is None or requester.get("role") is None:
        return ValidationResult.invalid(ReasonCode.MISSING_REQUIRED_FIELD)

    if request["environment"] not in VALID_ENVIRONMENTS:
        return ValidationResult.invalid(ReasonCode.INVALID_FIELD_TYPE)

    if not isinstance(request["target_action"], str) or not request["target_action"].strip():
        return ValidationResult.invalid(ReasonCode.INVALID_FIELD_TYPE)

    if not isinstance(request["action_payload"], dict):
        return ValidationResult.invalid(ReasonCode.INVALID_FIELD_TYPE)

    risk_context = request["risk_context"]
    if not isinstance(risk_context, dict):
        return ValidationResult.invalid(ReasonCode.INVALID_FIELD_TYPE)
    if not isinstance(risk_context.get("contains_pii"), bool):
        return ValidationResult.invalid(ReasonCode.INVALID_FIELD_TYPE)
    monetary = risk_context.get("monetary_value")
    if monetary is not None:
        if not isinstance(monetary, dict):
            return ValidationResult.invalid(ReasonCode.INVALID_FIELD_TYPE)
        amount = monetary.get("amount")
        # bool is a subclass of int in Python; "amount": true must not pass.
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            return ValidationResult.invalid(ReasonCode.INVALID_FIELD_TYPE)
        currency = monetary.get("currency")
        if not isinstance(currency, str) or not currency.strip():
            return ValidationResult.invalid(ReasonCode.INVALID_FIELD_TYPE)

    return ValidationResult.valid()


def validate_action_payload(
    action_payload: dict[str, Any], action_contract: dict[str, Any]
) -> ValidationResult:
    """Layer 6: validate required payload fields for the selected action.

    v1 checks presence only (spec 9.1). A field that is present but null is
    treated as missing — a null recipient cannot receive an email.
    """
    required = action_contract.get("required_payload_fields", [])
    for field_name in required:
        if action_payload.get(field_name) is None:
            return ValidationResult.invalid(ReasonCode.INVALID_ACTION_PAYLOAD)
    return ValidationResult.valid()
