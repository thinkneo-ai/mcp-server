"""Smoke tests — validate that test fixtures and tool registration work."""

import json
import pytest
from tests.conftest import parse_tool_result, tool_fn


class TestFixtureSmoke:
    def test_all_tools_registered(self, all_tools):
        """Verify tools are registered and count is reasonable."""
        assert len(all_tools) >= 72, f"Expected >=50 tools, got {len(all_tools)}"

    def test_tool_has_fn(self, all_tools):
        """Every tool has a callable .fn attribute."""
        for name, tool in all_tools.items():
            assert callable(tool.fn), f"{name} has non-callable fn"

    def test_tool_has_description(self, all_tools):
        """Every tool has a non-empty description."""
        for name, tool in all_tools.items():
            assert tool.description, f"{name} has empty description"


class TestAuthFixtures:
    def test_authenticated_allows_require_auth(self, authenticated):
        from src.auth import require_auth
        token = require_auth()
        assert token is not None

    def test_unauthenticated_blocks_require_auth(self, unauthenticated):
        from src.auth import require_auth
        with pytest.raises(ValueError, match="Authentication required"):
            require_auth()


class TestPureToolSmoke:
    def test_thinkneo_check_runs(self, all_tools):
        """thinkneo_check should work without auth or DB."""
        fn = tool_fn(all_tools, "thinkneo_check")
        result = parse_tool_result(fn(text="Hello world"))
        assert "safe" in result
        assert result["safe"] is True

    def test_thinkneo_provider_status_runs(self, all_tools):
        fn = tool_fn(all_tools, "thinkneo_provider_status")
        result = parse_tool_result(fn())
        assert "providers" in result

    def test_thinkneo_simulate_savings_runs(self, all_tools):
        fn = tool_fn(all_tools, "thinkneo_simulate_savings")
        result = parse_tool_result(fn(monthly_ai_spend=5000.0))
        assert "estimated_monthly_savings" in result
