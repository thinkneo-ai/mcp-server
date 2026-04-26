"""
Scenario 1: PostgreSQL goes down — gateway must degrade gracefully.

Fault: docker stop thinkneo-chaos-postgres
Expected: Public tools still work, DB tools return errors or timeout (not crashes),
          gateway auto-recovers when PG returns.

7 tests + recovery.
"""

import time
import pytest
import httpx
from .conftest import (
    call_tool, parse_sse_result,
    stop_container, start_container,
    gateway_pid, gateway_status,
)


def _safe_call(tool_name, args=None, auth=True):
    """Call tool, returning (response, None) or (None, exception) on timeout."""
    try:
        return call_tool(tool_name, args, auth=auth), None
    except (httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
        return None, exc


class TestPostgresDown:
    @pytest.fixture(autouse=True)
    def ensure_pg_running(self):
        """Restore PG after each test."""
        yield
        start_container("thinkneo-chaos-postgres")
        time.sleep(8)

    def _kill_pg(self):
        stop_container("thinkneo-chaos-postgres")
        time.sleep(3)

    # -- Public tools (no DB dependency) --

    def test_public_tool_works(self):
        """thinkneo_check (pure logic) must work when PG is down."""
        self._kill_pg()
        resp, exc = _safe_call("thinkneo_check", {"text": "hello chaos"})
        assert exc is None, f"Pure tool timed out: {exc}"
        assert resp.status_code in (200, 202)
        result = parse_sse_result(resp)
        assert "safe" in result
        assert isinstance(result["safe"], bool)

    def test_provider_status_works(self):
        """provider_status (no DB) must return valid response."""
        self._kill_pg()
        resp, exc = _safe_call("thinkneo_provider_status", {})
        assert exc is None, f"Provider status timed out: {exc}"
        assert resp.status_code in (200, 202)

    # -- DB-dependent tools (graceful degradation) --

    def test_db_read_tool_returns_error(self):
        """check_spend requires DB — should return MCP error or timeout, NOT crash."""
        self._kill_pg()
        resp, exc = _safe_call("thinkneo_check_spend", {"workspace": "test"})
        # Either: MCP returns error in content (200), or httpx times out.
        # Both are acceptable — the gateway did NOT crash.
        if exc is not None:
            # Timeout = gateway blocked on PG pool, acceptable degradation
            assert gateway_status() == "running", "Gateway crashed"
        else:
            assert resp.status_code in (200, 202)

    def test_db_write_tool_returns_error(self):
        """usage (logs to DB) should gracefully handle missing PG."""
        self._kill_pg()
        resp, exc = _safe_call("thinkneo_usage", {})
        if exc is not None:
            assert gateway_status() == "running"
        else:
            assert resp.status_code in (200, 202)

    # -- Stability --

    def test_container_stays_healthy(self):
        """Gateway must NOT crash/restart when PG goes down."""
        pid_before = gateway_pid()
        self._kill_pg()
        time.sleep(5)
        # Send a few requests — some may timeout, that's OK
        for _ in range(3):
            _safe_call("thinkneo_check", {"text": "stress"})
        pid_after = gateway_pid()
        assert pid_before == pid_after, "Gateway PID changed — container crashed"
        assert gateway_status() == "running"

    # -- Recovery --

    def test_recovery_after_pg_restart(self):
        """After PG restarts, public tools continue working, gateway is healthy."""
        self._kill_pg()

        # During outage: DB tools may timeout (expected)
        _safe_call("thinkneo_check_spend", {"workspace": "test"})

        # Restart PG
        start_container("thinkneo-chaos-postgres")
        time.sleep(15)  # Wait for PG to be ready + pool reconnect

        # Public tools always worked
        resp, exc = _safe_call("thinkneo_check", {"text": "post-recovery"})
        assert exc is None, f"Post-recovery tool timed out: {exc}"
        assert resp.status_code in (200, 202)
        result = parse_sse_result(resp)
        assert "safe" in result

    def test_no_manual_restart_needed(self):
        """Gateway PID stays the same through full PG down/up cycle."""
        pid_before = gateway_pid()

        stop_container("thinkneo-chaos-postgres")
        time.sleep(3)
        start_container("thinkneo-chaos-postgres")
        time.sleep(15)

        pid_after = gateway_pid()
        assert pid_before == pid_after, "Gateway needed restart — should auto-recover"
        assert gateway_status() == "running"
