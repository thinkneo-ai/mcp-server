"""Tests for auth rule pack."""

from __future__ import annotations

import pytest

from src.thinkshield.rules.auth import RULES
from tests.thinkshield.conftest import make_request


def _get_rule(rule_id: str):
    return next(r for r in RULES if r.rule_id == rule_id)


class TestEmptyBearer:
    rule = _get_rule("auth.empty_bearer")

    def test_bearer_only(self):
        req = make_request(headers={"authorization": "Bearer ", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_bearer_no_space(self):
        req = make_request(headers={"authorization": "Bearer", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_empty_value(self):
        req = make_request(headers={"authorization": "", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_no_header(self):
        """No Authorization header at all should NOT trigger."""
        req = make_request(headers={"host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is None

    def test_valid_bearer(self):
        req = make_request(headers={"authorization": "Bearer tn_live_abc123def456", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is None

    def test_basic_auth(self):
        """Basic auth is not Bearer — should NOT trigger."""
        req = make_request(headers={"authorization": "Basic dXNlcjpwYXNz", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is None


class TestMalformedBearer:
    rule = _get_rule("auth.malformed_bearer")

    def test_short_token(self):
        req = make_request(headers={"authorization": "Bearer abc", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_token_with_spaces(self):
        req = make_request(headers={"authorization": "Bearer token with spaces", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_control_chars(self):
        req = make_request(headers={"authorization": "Bearer token\x00value", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_valid_token(self):
        req = make_request(headers={"authorization": "Bearer tn_live_abc123def456789", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is None

    def test_no_auth_header(self):
        req = make_request(headers={"host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is None

    def test_long_valid_token(self):
        req = make_request(headers={"authorization": "Bearer " + "a" * 64, "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is None


class TestTokenProbe:
    rule = _get_rule("auth.token_probe")

    def test_admin_token(self):
        req = make_request(headers={"authorization": "Bearer admin", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_test_token(self):
        req = make_request(headers={"authorization": "Bearer test", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_password_token(self):
        req = make_request(headers={"authorization": "Bearer password", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_legitimate_token(self):
        req = make_request(headers={"authorization": "Bearer tn_live_sdf8923jhkdf", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is None

    def test_no_auth(self):
        req = make_request(headers={"host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is None

    def test_uuid_token(self):
        """UUID-style tokens are legitimate, not test tokens."""
        req = make_request(headers={"authorization": "Bearer 550e8400-e29b-41d4-a716-446655440000", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is None


class TestCredentialStuffing:
    rule = _get_rule("auth.credential_stuffing_pattern")

    def test_hex_hash_32(self):
        req = make_request(headers={"authorization": "Bearer " + "a" * 32, "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_hex_hash_64(self):
        req = make_request(headers={"authorization": "Bearer " + "abcdef0123456789" * 4, "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_hex_hash_128(self):
        req = make_request(headers={"authorization": "Bearer " + "f" * 128, "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_normal_api_key(self):
        """API keys with non-hex chars are NOT raw hashes."""
        req = make_request(headers={"authorization": "Bearer tn_live_sdf8923jhkdf", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is None

    def test_short_hex(self):
        """Short hex strings (< 32 chars) should NOT trigger."""
        req = make_request(headers={"authorization": "Bearer abcdef01", "host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is None

    def test_no_auth(self):
        req = make_request(headers={"host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is None
