"""
Scenario 3: Provider timeout — toxiproxy injects 30s latency.

Fault: toxiproxy adds 30s latency between gateway and mock provider
Expected: Gateway times out gracefully (not hang), pure-logic tools unaffected,
          recovery is automatic once latency removed.

5 tests + recovery.
"""

import time
import pytest
from .conftest import (
    call_tool, parse_sse_result,
    toxiproxy_create_proxy, toxiproxy_add_toxic, toxiproxy_remove_all_toxics,
    wiremock_stub, wiremock_reset,
    gateway_status,
)


@pytest.fixture(autouse=True)
def setup_provider_proxy():
    """Create provider proxy and wiremock 200 stub, clean up after."""
    toxiproxy_create_proxy("provider_proxy", "0.0.0.0:18082", "thinkneo-chaos-wiremock:8080")
    wiremock_stub("/.*", 200, body='{"status":"ok","response":"mock provider"}')
    yield
    toxiproxy_remove_all_toxics("provider_proxy")
    wiremock_reset()


class TestProviderTimeout:
    def test_pure_tools_fast_despite_provider_latency(self):
        """thinkneo_check (pure logic, no external I/O) must be fast."""
        toxiproxy_add_toxic("provider_proxy", "latency", {"latency": 30000})

        start = time.time()
        resp = call_tool("thinkneo_check", {"text": "timeout test"}, auth=True)
        elapsed = time.time() - start

        assert resp.status_code in (200, 202)
        result = parse_sse_result(resp)
        assert "safe" in result
        assert elapsed < 10, f"Pure tool took {elapsed:.1f}s — should be < 10s"

    def test_provider_status_fast(self):
        """provider_status (static data) unaffected by proxy latency."""
        toxiproxy_add_toxic("provider_proxy", "latency", {"latency": 30000})

        start = time.time()
        resp = call_tool("thinkneo_provider_status", {}, auth=True)
        elapsed = time.time() - start

        assert resp.status_code in (200, 202)
        assert elapsed < 5, f"Provider status took {elapsed:.1f}s"

    def test_simulate_savings_unaffected(self):
        """Smart Router (local logic) unaffected by proxy latency."""
        toxiproxy_add_toxic("provider_proxy", "latency", {"latency": 30000})

        start = time.time()
        resp = call_tool("thinkneo_simulate_savings", {"monthly_ai_spend": 5000}, auth=True)
        elapsed = time.time() - start

        assert resp.status_code in (200, 202)
        assert elapsed < 5

    def test_no_container_crash_under_timeout(self):
        """Gateway must not crash during sustained timeout injection."""
        toxiproxy_add_toxic("provider_proxy", "latency", {"latency": 30000})

        for _ in range(5):
            call_tool("thinkneo_check", {"text": "stress"}, auth=True)

        assert gateway_status() == "running", "Gateway crashed under timeout"

    def test_recovery_after_latency_removed(self):
        """After removing latency toxic, responses return to normal."""
        toxiproxy_add_toxic("provider_proxy", "latency", {"latency": 30000})
        time.sleep(1)
        toxiproxy_remove_all_toxics("provider_proxy")

        start = time.time()
        resp = call_tool("thinkneo_check", {"text": "recovered"}, auth=True)
        elapsed = time.time() - start

        assert resp.status_code in (200, 202)
        assert elapsed < 3, f"Post-recovery took {elapsed:.1f}s"
