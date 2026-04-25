"""Scenario 1: PostgreSQL goes down — gateway must degrade gracefully."""

import time
import pytest
from .conftest import call_tool, parse_sse_result, stop_container, start_container


class TestPostgresDown:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        yield
        start_container("thinkneo-chaos-postgres")
        time.sleep(5)

    def test_public_tool_works_without_db(self):
        stop_container("thinkneo-chaos-postgres")
        time.sleep(3)
        resp = call_tool("thinkneo_check", {"text": "hello"}, auth=False)
        assert resp.status_code in (200, 202)
        result = parse_sse_result(resp)
        assert "safe" in result

    def test_provider_status_works_without_db(self):
        stop_container("thinkneo-chaos-postgres")
        time.sleep(3)
        resp = call_tool("thinkneo_provider_status", {}, auth=False)
        assert resp.status_code in (200, 202)

    def test_db_tool_returns_error_gracefully(self):
        stop_container("thinkneo-chaos-postgres")
        time.sleep(3)
        resp = call_tool("thinkneo_check_spend", {"workspace": "test"})
        assert resp.status_code in (200, 202)  # MCP returns error in content, not HTTP 500

    def test_container_stays_healthy(self):
        import subprocess
        pid_before = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Pid}}", "thinkneo-chaos-gateway"],
            capture_output=True, text=True
        ).stdout.strip()

        stop_container("thinkneo-chaos-postgres")
        time.sleep(5)

        pid_after = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Pid}}", "thinkneo-chaos-gateway"],
            capture_output=True, text=True
        ).stdout.strip()

        assert pid_before == pid_after, "Gateway PID changed — container crashed and restarted"

    def test_recovery_after_pg_restart(self):
        stop_container("thinkneo-chaos-postgres")
        time.sleep(3)

        # Tools fail during outage
        resp = call_tool("thinkneo_check_spend", {"workspace": "test"})
        assert resp.status_code in (200, 202)

        # Restart PG
        start_container("thinkneo-chaos-postgres")
        time.sleep(10)  # Wait for recovery

        # Public tools always worked
        resp = call_tool("thinkneo_check", {"text": "post-recovery"}, auth=False)
        assert resp.status_code in (200, 202)
        result = parse_sse_result(resp)
        assert "safe" in result

    def test_no_manual_gateway_restart_needed(self):
        import subprocess
        pid_before = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Pid}}", "thinkneo-chaos-gateway"],
            capture_output=True, text=True
        ).stdout.strip()

        stop_container("thinkneo-chaos-postgres")
        time.sleep(3)
        start_container("thinkneo-chaos-postgres")
        time.sleep(10)

        pid_after = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Pid}}", "thinkneo-chaos-gateway"],
            capture_output=True, text=True
        ).stdout.strip()

        assert pid_before == pid_after, "Gateway needed restart — should auto-recover"
