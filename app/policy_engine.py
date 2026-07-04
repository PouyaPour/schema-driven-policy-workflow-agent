"""Deterministic policy engine — the only decision authority in the system.

Implements the fixed evaluation order of spec section 12.1 with early return:
the earliest failing layer wins (spec 12.2, execution order is authoritative).
No LLM is involved anywhere in this module; the engine emits authority fields
(decision, risk_level, reason_codes) and leaves presentation fields for the
formatter (spec section 6).

Layers:
  1. Base schema validation          -> BLOCKED_SCHEMA_INVALID
  2. Workflow contract lookup        -> BLOCKED_BY_POLICY / WORKFLOW_NOT_DEFINED
  3. Action contract lookup
  4. Unknown action guard            -> BLOCKED_UNKNOWN_ACTION
  5. Workflow/action permission      -> BLOCKED_BY_POLICY / ACTION_NOT_ALLOWED_FOR_WORKFLOW
  6. Action payload validation       -> BLOCKED_SCHEMA_INVALID / INVALID_ACTION_PAYLOAD
  7. Policy blocking rules           -> BLOCKED_BY_POLICY / ACTION_BLOCKED_IN_ENVIRONMENT
  8. Human review rules (OR)         -> REQUIRES_HUMAN_REVIEW
  9. Auto approval                   -> AUTO_APPROVED
"""

from __future__ import annotations

from typing import Any, Optional

from app.contract_loader import ContractProvider
from app.models import Decision, DecisionType, ReasonCode, RiskLevel
from app.schema_validator import validate_action_payload, validate_base_request


class PolicyEngine:
    def __init__(self, provider: Optional[ContractProvider] = None) -> None:
        self._provider = provider or ContractProvider()

    def evaluate(self, request: dict[str, Any]) -> Decision:
        """Evaluate one WorkflowActionRequest through the fixed layer order."""

        # Layer 1 — Base schema validation. If the envelope itself is not
        # trustworthy, we never proceed into contract lookup (spec 12.4).
        base = validate_base_request(request)
        if not base.ok:
            return Decision(
                decision=DecisionType.BLOCKED_SCHEMA_INVALID,
                risk_level=RiskLevel.CRITICAL,
                reason_codes=base.reason_codes,
                request_id=_safe_request_id(request),
            )

        request_id: str = request["request_id"]
        workflow_id: str = request["workflow_id"]
        target_action: str = request["target_action"]
        environment: str = request["environment"]
        risk_context: dict[str, Any] = request["risk_context"]

        # Layer 2 — Workflow contract lookup. Unknown workflow is a policy
        # violation and is checked BEFORE the unknown-action guard (spec 12.4:
        # execution order is authoritative).
        workflow_contract = self._provider.get_workflow_contract(workflow_id)
        if workflow_contract is None:
            return Decision(
                decision=DecisionType.BLOCKED_BY_POLICY,
                risk_level=RiskLevel.CRITICAL,
                reason_codes=(ReasonCode.WORKFLOW_NOT_DEFINED,),
                request_id=request_id,
            )

        # Layers 3+4 — Action contract lookup + unknown action guard.
        # Deny by default (spec 10.1): an undefined action is never trusted.
        action_contract = self._provider.get_action_contract(target_action)
        if action_contract is None:
            return Decision(
                decision=DecisionType.BLOCKED_UNKNOWN_ACTION,
                risk_level=RiskLevel.CRITICAL,
                reason_codes=(ReasonCode.TARGET_ACTION_NOT_DEFINED,),
                request_id=request_id,
            )

        # Layer 5 — Workflow/action permission. An action can be globally
        # known yet disallowed for this workflow (spec 8.1).
        allowed_actions = workflow_contract.get("allowed_actions", [])
        if target_action not in allowed_actions:
            return Decision(
                decision=DecisionType.BLOCKED_BY_POLICY,
                risk_level=RiskLevel.CRITICAL,
                reason_codes=(ReasonCode.ACTION_NOT_ALLOWED_FOR_WORKFLOW,),
                request_id=request_id,
            )

        # Layer 6 — Action payload validation (presence only in v1, spec 9.1).
        payload = validate_action_payload(request["action_payload"], action_contract)
        if not payload.ok:
            return Decision(
                decision=DecisionType.BLOCKED_SCHEMA_INVALID,
                risk_level=RiskLevel.CRITICAL,
                reason_codes=payload.reason_codes,
                request_id=request_id,
            )

        # Layer 7 — Policy blocking rules (environment blocks). Two sources
        # can block: the global policy file and the action contract's own
        # blocked_environments. Either one is sufficient (fail-closed).
        if self._is_blocked_in_environment(target_action, environment, action_contract):
            return Decision(
                decision=DecisionType.BLOCKED_BY_POLICY,
                risk_level=RiskLevel.CRITICAL,
                reason_codes=(ReasonCode.ACTION_BLOCKED_IN_ENVIRONMENT,),
                request_id=request_id,
            )

        # Layer 8 — Human review rules with OR semantics (spec 10.2): any
        # single matching condition pauses the request for human approval.
        review_codes = self._collect_review_codes(action_contract, environment, risk_context)
        if review_codes:
            return Decision(
                decision=DecisionType.REQUIRES_HUMAN_REVIEW,
                risk_level=self._review_risk_level(review_codes),
                reason_codes=tuple(review_codes),
                request_id=request_id,
            )

        # Layer 9 — Auto approval. Only reachable when every earlier layer
        # passed with no review condition matched (spec 12.1 step 9).
        return Decision(
            decision=DecisionType.AUTO_APPROVED,
            risk_level=RiskLevel.LOW,
            reason_codes=(
                ReasonCode.LOW_RISK_ACTION,
                ReasonCode.SAFE_ENVIRONMENT,
                ReasonCode.NO_PII_DETECTED,
                ReasonCode.NO_EXTERNAL_SIDE_EFFECT,
            ),
            request_id=request_id,
        )

    # --- layer helpers -------------------------------------------------------

    def _is_blocked_in_environment(
        self, target_action: str, environment: str, action_contract: dict[str, Any]
    ) -> bool:
        # Source 1: global policy blocking rules (policies.yaml).
        policies = self._provider.get_policy_rules()
        env_block = policies.get("blocking", {}).get(environment, {})
        if target_action in env_block.get("blocked_actions", []):
            return True
        # Source 2: the action contract's own blocked_environments.
        if environment in action_contract.get("blocked_environments", []):
            return True
        # Source 3: contract allow-list — if the contract enumerates allowed
        # environments and this one is not in it, deny (fail-closed).
        allowed_envs = action_contract.get("allowed_environments")
        if allowed_envs is not None and environment not in allowed_envs:
            return True
        return False

    def _collect_review_codes(
        self,
        action_contract: dict[str, Any],
        environment: str,
        risk_context: dict[str, Any],
    ) -> list[ReasonCode]:
        """Evaluate all review conditions and return every matching code.

        Returning ALL matching codes (not just the first) makes the audit
        trail complete: a reviewer sees every reason the request paused.
        """
        codes: list[ReasonCode] = []
        policies = self._provider.get_policy_rules()
        review_cfg = policies.get("human_review", {})
        # Active conditions are the UNION of global policy conditions and the
        # action contract's own requires_human_review_when list. An action can
        # therefore add review conditions beyond the global policy; neither
        # source can remove a condition the other declares (fail-closed).
        active_conditions = set(review_cfg.get("conditions", []))
        active_conditions.update(action_contract.get("requires_human_review_when", []))

        # contains_pii — untrusted runtime signal, but it can only ESCALATE
        # (claiming PII adds review); it can never remove inherent risk.
        if "contains_pii" in active_conditions and risk_context.get("contains_pii") is True:
            codes.append(ReasonCode.CONTAINS_PII)

        # production_environment
        if "production_environment" in active_conditions and environment == "production":
            codes.append(ReasonCode.PRODUCTION_ENVIRONMENT)

        # high_risk_action — derived from the TRUSTED contract (spec 10.4):
        # high_risk_action == (action_contract.risk_level == "high")
        if "high_risk_action" in active_conditions and action_contract.get("risk_level") == "high":
            codes.append(ReasonCode.HIGH_RISK_ACTION)

        # external_side_effect — also from the trusted contract (spec 7.4).
        if "external_side_effect" in active_conditions and action_contract.get("external_side_effect") is True:
            codes.append(ReasonCode.EXTERNAL_SIDE_EFFECT)

        # monetary_value_requires_review — threshold comparison (spec 10.3).
        # v1 compares only when the currency matches the configured currency.
        if "monetary_value_requires_review" in active_conditions:
            threshold = review_cfg.get("monetary_value_threshold", {})
            monetary = risk_context.get("monetary_value")
            if (
                monetary is not None
                and monetary.get("currency") == threshold.get("currency")
                and monetary.get("amount", 0) >= threshold.get("amount_gte", float("inf"))
            ):
                codes.append(ReasonCode.MONETARY_VALUE_REQUIRES_REVIEW)

        return codes

    @staticmethod
    def _review_risk_level(review_codes: list[ReasonCode]) -> RiskLevel:
        """Map matched review conditions to a risk level (spec section 14).

        PII or a high-risk action -> high; otherwise medium.
        """
        high_signals = {ReasonCode.CONTAINS_PII, ReasonCode.HIGH_RISK_ACTION}
        if high_signals & set(review_codes):
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM


def _safe_request_id(request: Any) -> Optional[str]:
    """Extract request_id for audit if it exists and is a string, else None.

    In schema-invalid cases the request may lack a usable id (spec 15.2).
    """
    if isinstance(request, dict):
        rid = request.get("request_id")
        if isinstance(rid, str) and rid.strip():
            return rid
    return None
