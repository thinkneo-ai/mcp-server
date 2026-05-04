"""Tests for recon rule pack."""

from __future__ import annotations

import pytest

from src.thinkshield.rules.recon import RULES
from tests.thinkshield.conftest import make_request


def _get_rule(rule_id: str):
    return next(r for r in RULES if r.rule_id == rule_id)


class TestPathProbe:
    rule = _get_rule("recon.path_probe")

    def test_dot_env(self):
        req = make_request(method="GET", path="/.env")
        assert self.rule.evaluate(req) is not None

    def test_git_config(self):
        req = make_request(method="GET", path="/.git/config")
        assert self.rule.evaluate(req) is not None

    def test_wp_admin(self):
        req = make_request(method="GET", path="/wp-admin")
        assert self.rule.evaluate(req) is not None

    def test_normal_mcp_path(self):
        req = make_request(path="/mcp")
        assert self.rule.evaluate(req) is None

    def test_normal_docs_path(self):
        req = make_request(path="/mcp/docs")
        assert self.rule.evaluate(req) is None

    def test_normal_root(self):
        req = make_request(path="/")
        assert self.rule.evaluate(req) is None


class TestToolEnumeration:
    rule = _get_rule("recon.tool_enumeration")

    def test_tools_list(self):
        req = make_request(body=b'{"jsonrpc":"2.0","method":"tools/list"}')
        assert self.rule.evaluate(req) is not None

    def test_resources_list(self):
        req = make_request(body=b'{"jsonrpc":"2.0","method":"resources/list"}')
        assert self.rule.evaluate(req) is not None

    def test_prompts_list(self):
        req = make_request(body=b'{"jsonrpc":"2.0","method":"prompts/list"}')
        assert self.rule.evaluate(req) is not None

    def test_normal_tool_call(self):
        req = make_request(body=b'{"jsonrpc":"2.0","method":"tools/call","params":{"name":"thinkneo_check"}}')
        assert self.rule.evaluate(req) is None

    def test_empty_body(self):
        req = make_request(body=b"")
        assert self.rule.evaluate(req) is None

    def test_normal_text_with_tools_word(self):
        req = make_request(body=b"I need tools for data analysis")
        assert self.rule.evaluate(req) is None


class TestMethodProbe:
    rule = _get_rule("recon.method_probe")

    def test_trace(self):
        req = make_request(method="TRACE")
        assert self.rule.evaluate(req) is not None

    def test_propfind(self):
        req = make_request(method="PROPFIND")
        assert self.rule.evaluate(req) is not None

    def test_connect(self):
        req = make_request(method="CONNECT")
        assert self.rule.evaluate(req) is not None

    def test_normal_post(self):
        req = make_request(method="POST")
        assert self.rule.evaluate(req) is None

    def test_normal_get(self):
        req = make_request(method="GET")
        assert self.rule.evaluate(req) is None

    def test_normal_options(self):
        req = make_request(method="OPTIONS")
        assert self.rule.evaluate(req) is None


class TestFingerprintProbe:
    rule = _get_rule("recon.fingerprint_probe")

    def test_metrics(self):
        req = make_request(path="/metrics")
        assert self.rule.evaluate(req) is not None

    def test_prometheus(self):
        req = make_request(path="/prometheus")
        assert self.rule.evaluate(req) is not None

    def test_healthz(self):
        req = make_request(path="/healthz")
        assert self.rule.evaluate(req) is not None

    def test_agent_json_allowed(self):
        """/.well-known/agent.json is a legitimate MCP path."""
        req = make_request(path="/.well-known/agent.json")
        assert self.rule.evaluate(req) is None

    def test_normal_path(self):
        req = make_request(path="/mcp")
        assert self.rule.evaluate(req) is None

    def test_normal_docs(self):
        req = make_request(path="/mcp/docs")
        assert self.rule.evaluate(req) is None
