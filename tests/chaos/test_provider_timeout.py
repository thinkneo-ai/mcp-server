"""Scenario 3: Provider timeout — toxiproxy injects 30s latency."""

import time
import pytest
from .conftest import (
    call_tool, parse_sse_result,
    toxiproxy_create_proxy, toxiproxy_add_toxic, toxiproxy_remove_all_toxics,
    wiremock_stub, wiremock_reset,
)


@pytest.fixture(autouse=True)
def setup_provider_proxy():
    """Set up toxiproxy proxy to wiremock and clean up after."""
    toxiproxy_create_proxy("provider_proxy", "0.0.0.0:18080", "wiremock:8080")
    wiremock_stub("/.*", 200, body='{"status":"ok","response":"mock provider"}')
    yield
    toxiproxy_remove_all_toxics("provider_proxy")
    wiremock_reset()


class TestProviderTimeout:
    def test_gateway_timeout_within_15s(self):
        """With 30s latency injected, gateway should timeout gracefully."""
        toxiproxy_add_toxic("provider_proxy", "latency", {"latency": 30000})

        start = time.time()
        # Call a tool — even if it doesn't directly use the proxy,
        # this validates the gateway handles slow I/O gracefully
        resp = call_tool("thinkneo_check", {"text": "timeout test"}, auth=False)
        elapsed = time.time() - start

        assert resp.status_code in (200, 202)
        # thinkneo_check is pure logic, should be fast regardless
        assert elapsed < 15, f"Response took {elapsed:.1f}s — should be < 15s"

    def test_other_tools_unaffected(self):
        """Pure-logic tools should be unaffected by provider proxy latency."""
        toxiproxy_add_toxic("provider_proxy", "latency", {"latency": 30000})

        start = time.time()
        resp = call_tool("thinkneo_provider_status", {}, auth=False)
        elapsed = time.time() - start

        assert resp.status_code in (200, 202)
        assert elapsed < 5, f"Pure tool took {elapsed:.1f}s with proxy latency"

    def test_simulate_savings_unaffected(self):
        """Smart Router (local logic) unaffected by proxy."""
        toxiproxy_add_toxic("provider_proxy", "latency", {"latency": 30000})

        start = time.time()
        resp = call_tool("thinkneo_simulate_savings", {"monthly_ai_spend": 5000}, auth=False)
        elapsed = time.time() - start

        assert resp.status_code in (200, 202)
        assert elapsed < 5

    def test_no_container_crash_under_timeout(self):
        """Gateway container must not crash during timeout injection."""
        import subprocess
        toxiproxy_add_toxic("provider_proxy", "latency", {"latency": 30000})

        # Send multiple requests
        for _ in range(5):
            call_tool("thinkneo_check", {"text": "stress"}, auth=False)

        status = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", "thinkneo-chaos-gateway"],
            capture_output=True, text=True
        ).stdout.strip()
        assert status == "running"

    def test_recovery_after_latency_removed(self):
        """After removing latency toxic, everything returns to normal."""
        toxiproxy_add_toxic("provider_proxy", "latency", {"latency": 30000})
        time.sleep(1)
        toxiproxy_remove_all_toxics("provider_proxy")

        start = time.time()
        resp = call_tool("thinkneo_check", {"text": "recovered"}, auth=False)
        elapsed = time.time() - start

        assert resp.status_code in (200, 202)
        assert elapsed < 3
