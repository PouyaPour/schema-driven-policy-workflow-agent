"""Unit tests for schema_validator.py (evaluation-order layers 1 and 6)."""

from __future__ import annotations

from app.models import ReasonCode
from app.schema_validator import validate_action_payload, validate_base_request


class TestBaseRequestValidation:
    def test_valid_request_passes(self, valid_request):
        result = validate_base_request(valid_request)
        assert result.ok
        assert result.reason_codes == ()

    def test_missing_request_id(self, valid_request):
        valid_request["request_id"] = None
        result = validate_base_request(valid_request)
        assert not result.ok
        assert ReasonCode.MISSING_REQUIRED_FIELD in result.reason_codes

    def test_absent_request_id_key(self, valid_request):
        del valid_request["request_id"]
        result = validate_base_request(valid_request)
        assert not result.ok
        assert ReasonCode.MISSING_REQUIRED_FIELD in result.reason_codes

    def test_empty_string_request_id_is_invalid_type(self, valid_request):
        valid_request["request_id"] = "   "
        result = validate_base_request(valid_request)
        assert not result.ok
        assert ReasonCode.INVALID_FIELD_TYPE in result.reason_codes

    def test_invalid_environment(self, valid_request):
        valid_request["environment"] = "sandbox"
        result = validate_base_request(valid_request)
        assert not result.ok
        assert ReasonCode.INVALID_FIELD_TYPE in result.reason_codes

    def test_requester_missing_role(self, valid_request):
        valid_request["requester"] = {"id": "user_1"}
        result = validate_base_request(valid_request)
        assert not result.ok
        assert ReasonCode.MISSING_REQUIRED_FIELD in result.reason_codes

    def test_contains_pii_must_be_boolean(self, valid_request):
        valid_request["risk_context"]["contains_pii"] = "no"
        result = validate_base_request(valid_request)
        assert not result.ok
        assert ReasonCode.INVALID_FIELD_TYPE in result.reason_codes

    def test_monetary_value_bad_amount(self, valid_request):
        valid_request["risk_context"]["monetary_value"] = {"amount": "100", "currency": "USD"}
        result = validate_base_request(valid_request)
        assert not result.ok
        assert ReasonCode.INVALID_FIELD_TYPE in result.reason_codes

    def test_monetary_value_boolean_amount_rejected(self, valid_request):
        # bool is a subclass of int in Python; it must still be rejected.
        valid_request["risk_context"]["monetary_value"] = {"amount": True, "currency": "USD"}
        result = validate_base_request(valid_request)
        assert not result.ok
        assert ReasonCode.INVALID_FIELD_TYPE in result.reason_codes

    def test_monetary_value_missing_currency(self, valid_request):
        valid_request["risk_context"]["monetary_value"] = {"amount": 100}
        result = validate_base_request(valid_request)
        assert not result.ok
        assert ReasonCode.INVALID_FIELD_TYPE in result.reason_codes

    def test_monetary_value_empty_currency_rejected(self, valid_request):
        valid_request["risk_context"]["monetary_value"] = {"amount": 100, "currency": "  "}
        result = validate_base_request(valid_request)
        assert not result.ok
        assert ReasonCode.INVALID_FIELD_TYPE in result.reason_codes

    def test_monetary_value_null_is_allowed(self, valid_request):
        valid_request["risk_context"]["monetary_value"] = None
        assert validate_base_request(valid_request).ok

    def test_non_dict_request(self):
        result = validate_base_request("not a dict")  # type: ignore[arg-type]
        assert not result.ok
        assert ReasonCode.INVALID_FIELD_TYPE in result.reason_codes


class TestActionPayloadValidation:
    EMAIL_CONTRACT = {
        "required_payload_fields": ["recipient", "subject", "body"],
    }

    def test_complete_payload_passes(self):
        payload = {"recipient": "a@b.test", "subject": "Hi", "body": "Welcome"}
        assert validate_action_payload(payload, self.EMAIL_CONTRACT).ok

    def test_missing_subject(self):
        payload = {"recipient": "a@b.test", "body": "Welcome"}
        result = validate_action_payload(payload, self.EMAIL_CONTRACT)
        assert not result.ok
        assert ReasonCode.INVALID_ACTION_PAYLOAD in result.reason_codes

    def test_null_field_treated_as_missing(self):
        payload = {"recipient": None, "subject": "Hi", "body": "Welcome"}
        result = validate_action_payload(payload, self.EMAIL_CONTRACT)
        assert not result.ok
        assert ReasonCode.INVALID_ACTION_PAYLOAD in result.reason_codes

    def test_contract_with_no_required_fields(self):
        assert validate_action_payload({}, {"required_payload_fields": []}).ok
