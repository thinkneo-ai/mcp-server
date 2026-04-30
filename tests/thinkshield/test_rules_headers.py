"""Tests for headers rule pack."""

from __future__ import annotations

import pytest

from src.thinkshield.rules.headers import RULES
from tests.thinkshield.conftest import make_request


def _get_rule(rule_id: str):
    return next(r for r in RULES if r.rule_id == rule_id)


class TestAttackToolUA:
    rule = _get_rule("headers.attack_tool_ua")

    def test_sqlmap(self):
        req = make_request(user_agent="sqlmap/1.6.4#stable")
        assert self.rule.evaluate(req) is not None

    def test_nikto(self):
        req = make_request(user_agent="Nikto/2.1.6")
        assert self.rule.evaluate(req) is not None

    def test_nuclei(self):
        req = make_request(user_agent="nuclei/2.9.4")
        assert self.rule.evaluate(req) is not None

    def test_normal_browser(self):
        req = make_request(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        assert self.rule.evaluate(req) is None

    def test_normal_claude(self):
        req = make_request(user_agent="Claude/3.5")
        assert self.rule.evaluate(req) is None

    def test_normal_curl(self):
        """curl is a legitimate MCP client."""
        req = make_request(user_agent="curl/8.4.0")
        assert self.rule.evaluate(req) is None


class TestEmptyUA:
    rule = _get_rule("headers.empty_ua")

    def test_empty_ua_post(self):
        req = make_request(method="POST", user_agent="", headers={"host": "mcp.thinkneo.ai"})
        assert self.rule.evaluate(req) is not None

    def test_none_ua_post(self):
        req = make_request(method="POST", user_agent=None, headers={"host": "mcp.thinkneo.ai"})
        assert self.rule.evaluate(req) is not None

    def test_whitespace_ua_post(self):
        req = make_request(method="POST", user_agent="  ", headers={"host": "mcp.thinkneo.ai", "user-agent": "  "})
        assert self.rule.evaluate(req) is not None

    def test_normal_ua_post(self):
        req = make_request(method="POST", user_agent="MCP-Client/1.0")
        assert self.rule.evaluate(req) is None

    def test_empty_ua_get(self):
        """GET with empty UA should NOT trigger (only POST is suspicious)."""
        req = make_request(method="GET", user_agent="", headers={"host": "mcp.thinkneo.ai"})
        assert self.rule.evaluate(req) is None

    def test_empty_ua_options(self):
        req = make_request(method="OPTIONS", user_agent="", headers={"host": "mcp.thinkneo.ai"})
        assert self.rule.evaluate(req) is None


class TestSuspiciousUA:
    rule = _get_rule("headers.suspicious_ua")

    def test_python_requests_no_auth(self):
        req = make_request(user_agent="python-requests/2.28.1", key_hash=None)
        assert self.rule.evaluate(req) is not None

    def test_aiohttp_no_auth(self):
        req = make_request(user_agent="aiohttp/3.8.4", key_hash=None)
        assert self.rule.evaluate(req) is not None

    def test_go_http_no_auth(self):
        req = make_request(user_agent="Go-http-client/2.0", key_hash=None)
        assert self.rule.evaluate(req) is not None

    def test_python_requests_with_auth(self):
        """Automation with auth is legitimate — should NOT trigger."""
        req = make_request(user_agent="python-requests/2.28.1", key_hash="tn_live_valid")
        assert self.rule.evaluate(req) is None

    def test_curl_no_auth(self):
        """curl is NOT in the suspicious_ua list (it's common for MCP)."""
        req = make_request(user_agent="curl/8.4.0", key_hash=None)
        assert self.rule.evaluate(req) is None

    def test_browser_no_auth(self):
        req = make_request(user_agent="Mozilla/5.0", key_hash=None)
        assert self.rule.evaluate(req) is None


class TestHostMismatch:
    rule = _get_rule("headers.host_mismatch")

    def test_unknown_host(self):
        req = make_request(headers={"host": "evil.example.com", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_random_domain(self):
        req = make_request(headers={"host": "attacker-1.example.net", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_typosquat(self):
        req = make_request(headers={"host": "mcp.thinkne0.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is not None

    def test_expected_host(self):
        req = make_request(headers={"host": "mcp.thinkneo.ai", "user-agent": "test"})
        assert self.rule.evaluate(req) is None

    def test_localhost(self):
        req = make_request(headers={"host": "localhost:8081", "user-agent": "test"})
        assert self.rule.evaluate(req) is None

    def test_ip_address(self):
        """Direct IP access is allowed."""
        req = make_request(headers={"host": "161.35.12.205:8081", "user-agent": "test"})
        assert self.rule.evaluate(req) is None

    def test_tailscale_ip(self):
        """Tailscale IPs (100.x.x.x) are allowed."""
        req = make_request(headers={"host": "100.75.242.28:8081", "user-agent": "test"})
        assert self.rule.evaluate(req) is None

    def test_no_host_header(self):
        req = make_request(headers={"user-agent": "test"})
        assert self.rule.evaluate(req) is None
