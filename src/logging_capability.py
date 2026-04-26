"""
MCP Logging Capability — spec 2024-11-05.

Implements:
  - logging/setLevel: client controls minimum log level
  - notifications/message: server sends filtered log events

Per-session via ContextVar (stateless HTTP: each request gets default level).
Audit trail of level changes logged to Python logger + DB usage_log.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import LoggingLevel

from .auth import get_bearer_token
from .database import hash_key, log_tool_call

logger = logging.getLogger(__name__)

# Per-session log level (default: info)
_current_log_level: ContextVar[LoggingLevel] = ContextVar("mcp_log_level", default="info")

# MCP spec levels → Python logging levels
_LEVEL_MAP: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,       # Python has no NOTICE, map to INFO
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "alert": logging.CRITICAL,    # Python has no ALERT, map to CRITICAL
    "emergency": logging.CRITICAL,  # Python has no EMERGENCY, map to CRITICAL
}

VALID_LEVELS = set(_LEVEL_MAP.keys())


def get_current_level() -> LoggingLevel:
    """Return the current MCP log level for this session."""
    return _current_log_level.get()


def register_logging(mcp: FastMCP) -> None:
    """Register the logging/setLevel handler on the low-level server."""

    @mcp._mcp_server.set_logging_level()
    async def handle_set_level(level: LoggingLevel) -> None:
        if level not in VALID_LEVELS:
            raise ValueError(
                f"Invalid log level: {level!r}. "
                f"Valid levels: {', '.join(sorted(VALID_LEVELS))}"
            )

        old_level = _current_log_level.get()
        _current_log_level.set(level)

        # Apply to Python logging
        py_level = _LEVEL_MAP[level]
        logging.getLogger().setLevel(py_level)

        # Audit trail
        token = get_bearer_token()
        key_hash = hash_key(token) if token else "anonymous"
        logger.info(
            "Log level changed: %s → %s (by %s)",
            old_level, level, key_hash[:12] + "...",
        )
        log_tool_call(
            key_hash=key_hash,
            tool_name="logging/setLevel",
            cost_estimate=0.0,
        )
