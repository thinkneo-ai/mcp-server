"""
Unit tests for log redaction — verifies PII and secrets never appear in logs.
"""

import os
import pytest
from unittest.mock import patch
from src.logging.redaction import redact, redact_dict, is_redaction_enabled


class TestRedactionEnabled:
    def test_enabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_redaction_enabled() is True

    def test_disabled_with_false(self):
        with patch.dict(os.environ, {"LOG_REDACTION": "false"}):
            assert is_redaction_enabled() is False

    def test_disabled_with_zero(self):
        with patch.dict(os.environ, {"LOG_REDACTION": "0"}):
            assert is_redaction_enabled() is False

    def test_raw_text_when_disabled(self):
        with patch.dict(os.environ, {"LOG_REDACTION": "false"}):
            assert redact("password = secret123") == "password = secret123"


class TestPIIRedaction:
    def test_credit_card_redacted(self):
        result = redact("Card: 4111 1111 1111 1111")
        assert "4111" not in result
        assert "[REDACTED-PII-CREDIT-CARD]" in result

    def test_ssn_redacted(self):
        result = redact("SSN: 123-45-6789")
        assert "123-45-6789" not in result
        assert "[REDACTED-PII-SSN]" in result

    def test_cpf_redacted(self):
        result = redact("CPF: 529.982.247-25")
        assert "529.982.247-25" not in result
        assert "[REDACTED-PII-CPF]" in result

    def test_email_redacted(self):
        result = redact("Contact: john@example.com")
        assert "john@example.com" not in result
        assert "[REDACTED-PII-EMAIL]" in result

    def test_phone_redacted(self):
        result = redact("Call +1-555-123-4567")
        assert "555-123-4567" not in result
        assert "[REDACTED-PII-PHONE]" in result

    def test_multiple_pii_in_one_string(self):
        text = "Email: john@test.com, SSN: 123-45-6789, Card: 4111111111111111"
        result = redact(text)
        assert "john@test.com" not in result
        assert "123-45-6789" not in result
        assert "4111111111111111" not in result
        assert result.count("[REDACTED-") >= 3


class TestSecretRedaction:
    def test_password_redacted(self):
        result = redact('password = "super_secret_123"')
        assert "super_secret_123" not in result
        assert "[REDACTED-SECRET-PASSWORD]" in result

    def test_api_key_redacted(self):
        result = redact("api_key = sk-proj-abc123xyz456def789ghijklmnop")
        assert "abc123xyz456" not in result
        assert "[REDACTED-SECRET-API-KEY]" in result

    def test_github_token_redacted(self):
        result = redact("ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789")  # exactly 36 chars after ghp_
        assert "aBcDeFg" not in result
        assert "[REDACTED-SECRET-" in result

    def test_aws_key_redacted(self):
        result = redact("AWS_KEY=AKIAIOSFODNN7EXAMPLE")
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[REDACTED-SECRET-AWS-KEY]" in result

    def test_private_key_redacted(self):
        result = redact("-----BEGIN RSA PRIVATE KEY-----")
        assert "PRIVATE KEY" not in result
        assert "[REDACTED-SECRET-PRIVATE-KEY]" in result

    def test_resend_key_redacted(self):
        result = redact("key = re_FAKE_TEST_KEY_NOT_REAL_00000000000")
        assert "re_FAKE_TEST" not in result
        assert "[REDACTED-SECRET-" in result


class TestCleanTextNotRedacted:
    def test_normal_text_unchanged(self):
        text = "The quick brown fox jumps over the lazy dog."
        assert redact(text) == text

    def test_business_text_unchanged(self):
        text = "Please summarize the quarterly earnings report for Q3."
        assert redact(text) == text

    def test_code_without_secrets_unchanged(self):
        text = "def hello_world():\n    return 'Hello, World!'"
        assert redact(text) == text

    def test_numbers_not_mistaken_for_cards(self):
        text = "Order #12345 was shipped."
        assert "[REDACTED-PII-CREDIT-CARD]" not in redact(text)


class TestRedactDict:
    def test_redacts_string_values(self):
        d = {"user": "john@test.com", "count": 42}
        result = redact_dict(d)
        assert "john@test.com" not in result["user"]
        assert result["count"] == 42

    def test_nested_dict(self):
        d = {"config": {"db_password": "password = secret123"}}
        result = redact_dict(d)
        assert "secret123" not in str(result)

    def test_list_values(self):
        d = {"emails": ["a@test.com", "b@test.com"]}
        result = redact_dict(d)
        assert all("[REDACTED-PII-EMAIL]" in v for v in result["emails"])

    def test_max_depth_prevents_infinite_recursion(self):
        # Deep nesting should not crash
        d = {"a": {"b": {"c": {"d": {"e": {"f": "password = deep"}}}}}}
        result = redact_dict(d, max_depth=3)
        assert isinstance(result, dict)
