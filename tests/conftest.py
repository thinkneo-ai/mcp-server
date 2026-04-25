"""
Global test fixtures for ThinkNEO MCP Server.

Provides:
- mock_db: patches _get_conn to return a mock connection/cursor
- mock_auth / authenticated / unauthenticated: ContextVar auth control
- all_tools: registers all tools and returns the tool registry dict
- tool_fn: helper to extract a single tool function by name
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# Prevent ConnectionPool from opening real connections during tests.
# Must happen before any src.database import.
import src.database as _db_mod
_db_mod._pool = MagicMock()  # prevent lazy init from starting real pool threads
_db_mod._pool.connection.return_value = MagicMock()


# ---------------------------------------------------------------------------
# Database mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_cursor():
    """A MagicMock cursor with chainable fetchone/fetchall."""
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    return cursor


@pytest.fixture
def mock_db(mock_cursor):
    """
    Patch _get_conn everywhere it's imported so all DB calls use a mock.

    _get_conn() returns a psycopg.Connection used as:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(...)

    We mock the full chain and patch at every import site.
    """
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    cursor_ctx = MagicMock()
    cursor_ctx.__enter__ = MagicMock(return_value=mock_cursor)
    cursor_ctx.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = cursor_ctx

    # Patch at source AND every module that imports _get_conn directly
    patch_targets = [
        "src.database._get_conn",
        "src.observability._get_conn",
        "src.security._get_conn",
        "src.compliance_export._get_conn",
        "src.a2a_bridge._get_conn",
        "src.outcome_validation._get_conn",
        "src.marketplace._get_conn",
        "src.outcome_benchmarking._get_conn",
        "src.policy_engine._get_conn",
        "src.agent_sla._get_conn",
        "src.tools.value_waste_detector._get_conn",
        "src.tools.a2a_audit._get_conn",
        "src.tools.value_business_impact._get_conn",
        "src.tools.value_decision_cost._get_conn",
        "src.tools.value_baseline._get_conn",
        "src.tools.rotate_key._get_conn",
        "src.tools.a2a_flow._get_conn",
        "src.tools.value_agent_roi._get_conn",
        "src.tools.a2a_policy._get_conn",
        "src.tools.cache._get_conn",
        "src.tools.value_log_decision._get_conn",
        "src.tools.value_log_risk._get_conn",
        "src.tools.a2a_log._get_conn",
        "src.tools.trust_score._get_conn",
    ]

    patches = []
    for target in patch_targets:
        try:
            p = patch(target, return_value=mock_conn)
            p.start()
            patches.append(p)
        except (AttributeError, ModuleNotFoundError):
            pass  # Module may not have _get_conn

    yield mock_cursor

    for p in patches:
        p.stop()


# ---------------------------------------------------------------------------
# Auth mock
# ---------------------------------------------------------------------------

VALID_TEST_KEY = "test-master-key-valid"


@pytest.fixture
def set_auth_token():
    """
    Returns a callable that sets the bearer token ContextVar.
    Usage: set_auth_token("my-key") or set_auth_token() for default valid key.
    """
    from src.auth import _bearer_token

    tokens = []

    def _set(token=VALID_TEST_KEY):
        ctx = _bearer_token.set(token)
        tokens.append(ctx)
        return ctx

    yield _set

    # Reset all tokens set during the test
    for ctx in reversed(tokens):
        _bearer_token.reset(ctx)


@pytest.fixture
def authenticated(set_auth_token):
    """Set up a fully authenticated context with a valid master key."""
    with patch("src.config.get_settings") as mock_settings:
        settings = MagicMock()
        settings.valid_api_keys = {VALID_TEST_KEY}
        settings.require_auth = True
        settings.master_key = VALID_TEST_KEY
        mock_settings.return_value = settings
        set_auth_token(VALID_TEST_KEY)
        yield


@pytest.fixture
def unauthenticated():
    """Ensure no bearer token is set."""
    from src.auth import _bearer_token

    ctx = _bearer_token.set(None)
    yield
    _bearer_token.reset(ctx)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def all_tools():
    """
    Register all tools once per session and return the tool dict.
    Keys: tool name strings. Values: Tool objects with .fn attribute.

    NOTE: This uses FastMCP internals (_tool_manager._tools).
    The free-tier wrapper is NOT applied (we test tool logic directly).
    """
    from mcp.server.fastmcp import FastMCP
    from src.tools import register_all

    mcp = FastMCP("test", stateless_http=True, streamable_http_path="/mcp")

    # Patch _get_conn during registration to avoid DB connection at import time
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("src.database._get_conn", return_value=mock_conn):
        # Also patch settings for auth during registration
        with patch("src.config.get_settings") as ms:
            s = MagicMock()
            s.valid_api_keys = set()
            s.require_auth = False
            ms.return_value = s
            register_all(mcp)

    return mcp._tool_manager._tools


def tool_fn(all_tools, name: str):
    """Extract a tool function by name."""
    assert name in all_tools, f"Tool {name} not found. Available: {sorted(all_tools.keys())}"
    return all_tools[name].fn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_tool_result(result: str) -> dict:
    """Parse a tool's JSON string result into a dict."""
    parsed = json.loads(result)
    assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
    return parsed
