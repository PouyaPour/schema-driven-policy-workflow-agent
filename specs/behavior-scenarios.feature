Feature: Workflow action governance
  As a pre-execution governance layer
  I want to evaluate every action request deterministically and fail-closed
  So that approval decisions are reproducible, auditable, and safe

  Background:
    Given the action registry defines generate_report, send_email, and external_api_call
    And the workflow registry defines customer_onboarding, internal_reporting, and incident_escalation
    And the policy engine is the only authority for decisions
    And the LLM cannot override any decision

  Scenario: Low-risk action is auto-approved
    Given a valid request for generate_report in customer_onboarding in staging
    And the request contains no PII and no monetary value
    When the governance pipeline evaluates the request
    Then the decision is AUTO_APPROVED
    And the reason codes include LOW_RISK_ACTION

  Scenario: PII triggers human review via OR semantics
    Given a valid request for generate_report in staging
    And the request contains PII
    When the governance pipeline evaluates the request
    Then the decision is REQUIRES_HUMAN_REVIEW
    And the reason codes include CONTAINS_PII

  Scenario: Production external action requires review
    Given a valid request for external_api_call in production
    When the governance pipeline evaluates the request
    Then the decision is REQUIRES_HUMAN_REVIEW
    And the reason codes include PRODUCTION_ENVIRONMENT

  Scenario: Monetary value over threshold requires review
    Given a valid request for generate_report in staging
    And the request has a monetary value of 250 USD
    When the governance pipeline evaluates the request
    Then the decision is REQUIRES_HUMAN_REVIEW
    And the reason codes include MONETARY_VALUE_REQUIRES_REVIEW

  Scenario: Action blocked in environment
    Given a valid request for send_email in local
    When the governance pipeline evaluates the request
    Then the decision is BLOCKED_BY_POLICY
    And the reason codes include ACTION_BLOCKED_IN_ENVIRONMENT

  Scenario: Known action not allowed for the workflow
    Given a valid request for send_email in internal_reporting
    When the governance pipeline evaluates the request
    Then the decision is BLOCKED_BY_POLICY
    And the reason codes include ACTION_NOT_ALLOWED_FOR_WORKFLOW

  Scenario: Unknown action is denied by default
    Given a valid request whose target_action is not in the registry
    When the governance pipeline evaluates the request
    Then the decision is BLOCKED_UNKNOWN_ACTION
    And the reason codes include TARGET_ACTION_NOT_DEFINED

  Scenario: Missing request_id fails base schema validation
    Given a request with no request_id
    When the governance pipeline evaluates the request
    Then the decision is BLOCKED_SCHEMA_INVALID
    And the reason codes include MISSING_REQUIRED_FIELD

  Scenario: Missing required payload field fails validation
    Given a request for send_email with no subject in staging
    When the governance pipeline evaluates the request
    Then the decision is BLOCKED_SCHEMA_INVALID
    And the reason codes include INVALID_ACTION_PAYLOAD

  Scenario: Earliest failing layer wins
    Given a request that is missing request_id and targets an unknown action
    When the governance pipeline evaluates the request
    Then the decision is BLOCKED_SCHEMA_INVALID
    And the decision is not BLOCKED_UNKNOWN_ACTION

  Scenario: Unknown workflow is checked before unknown action
    Given a request with an unknown workflow and an unknown action
    When the governance pipeline evaluates the request
    Then the decision is BLOCKED_BY_POLICY
    And the reason codes include WORKFLOW_NOT_DEFINED

  Scenario: LLM only formats presentation output
    Given a finalized decision with reason codes
    When the formatter produces a human_review_message and audit_summary
    Then the decision, risk_level, and reason_codes are unchanged
