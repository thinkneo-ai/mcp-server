"""
Tests for MCP logging capability (spec 2024-11-05).
"""

import asyncio
import logging
import pytest
from unittest.mock import patch

import sys
sys.path.insert(0, ".")

from src.logging_capability import (
    VALID_LEVELS,
    _current_log_level,
    _LEVEL_MAP,
    get_current_level,
    register_logging,
)


@pytest.fixture(autouse=True)
def reset_log_level():
    """Reset log level to default before each test."""
    token = _current_log_level.set("info")
    yield
    _current_log_level.reset(token)


class TestLoggingCapability:
    def test_valid_levels_complete(self):
        """All 8 MCP spec levels are recognized."""
        expected = {"debug", "info", "notice", "warning", "error", "critical", "alert", "emergency"}
        assert VALID_LEVELS == expected

    def test_default_level_is_info(self):
        """Default log level is 'info'."""
        assert get_current_level() == "info"

    def test_level_map_covers_all_valid_levels(self):
        """Every valid MCP level maps to a Python logging level."""
        for level in VALID_LEVELS:
            assert level in _LEVEL_MAP
            assert isinstance(_LEVEL_MAP[level], int)

    def test_initialize_declares_logging_capability(self):
        """After registering, the server should have a SetLevelRequest handler."""
        from mcp.server.fastmcp import FastMCP
        from mcp import types

        mcp = FastMCP("test")
        register_logging(mcp)
        assert types.SetLevelRequest in mcp._mcp_server.request_handlers

    def test_set_logging_level_changes_runtime_level(self):
        """Calling the handler sets the level and applies to Python logging."""
        from mcp.server.fastmcp import FastMCP
        from mcp import types

        mcp = FastMCP("test")
        register_logging(mcp)

        handler = mcp._mcp_server.request_handlers[types.SetLevelRequest]
        req = types.SetLevelRequest(
            method="logging/setLevel",
            params=types.SetLevelRequestParams(level="warning"),
        )

        # Verify the handler calls _current_log_level.set with "warning"
        with patch("src.logging_capability._current_log_level") as mock_cv:
            mock_cv.get.return_value = "info"
            with patch("src.logging_capability.log_tool_call"):
                asyncio.run(handler(req))
            mock_cv.set.assert_called_once_with("warning")

    def test_set_logging_level_with_invalid_level_rejected_by_schema(self):
        """Invalid level is rejected by Pydantic schema validation (before handler)."""
        from mcp import types

        with pytest.raises(Exception):
            types.SetLevelRequestParams(level="invalid_level")

    def test_audit_log_records_level_change(self):
        """Level change is logged to usage_log via log_tool_call."""
        from mcp.server.fastmcp import FastMCP
        from mcp import types

        mcp = FastMCP("test")
        register_logging(mcp)

        handler = mcp._mcp_server.request_handlers[types.SetLevelRequest]
        req = types.SetLevelRequest(
            method="logging/setLevel",
            params=types.SetLevelRequestParams(level="debug"),
        )

        with patch("src.logging_capability.log_tool_call") as mock_log:
            with patch("src.logging_capability.get_bearer_token", return_value=None):
                asyncio.run(handler(req))

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args
            assert call_kwargs[1]["tool_name"] == "logging/setLevel"

    def test_per_session_log_level_isolation(self):
        """Different ContextVar tokens give independent levels."""
        token1 = _current_log_level.set("debug")
        assert get_current_level() == "debug"

        token2 = _current_log_level.set("error")
        assert get_current_level() == "error"

        _current_log_level.reset(token2)
        assert get_current_level() == "debug"

        _current_log_level.reset(token1)
