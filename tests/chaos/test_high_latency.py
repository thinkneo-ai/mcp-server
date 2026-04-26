"""
Scenario 5: High latency — toxiproxy adds 5s latency to provider proxy.

Fault: 5s latency injected on provider path
Expected: Pure-logic tools unaffected (P95 < 2s), concurrent requests all complete,
          no hangs, recovery is automatic.

5 tests + recovery.
"""

import asyncio
import time
import pytest
import httpx
from .conftest import (
    call_tool, parse_sse_result,
    toxiproxy_create_proxy, toxiproxy_add_toxic, toxiproxy_remove_all_toxics,
    wiremock_stub, wiremock_reset,
    gateway_status,
    GATEWAY_URL, AUTH_HEADERS,
)


@pytest.fixture(autouse=True)
def setup_latency_proxy():
    """Create a separate latency proxy and wiremock 200 stub."""
    toxiproxy_create_proxy("latency_proxy", "0.0.0.0:18082", "thinkneo-chaos-wiremock:8080")
    wiremock_stub("/.*", 200, body='{"status":"ok"}')
    yield
    toxiproxy_remove_all_toxics("latency_proxy")
    wiremock_reset()


class TestHighLatency:
    def test_fast_tools_unaffected(self):
        """Pure-logic tools must maintain P95 < 2s despite proxy latency."""
        toxiproxy_add_toxic("latency_proxy", "latency", {"latency": 5000})

        latencies = []
        for _ in range(10):
            start = time.perf_counter()
            resp = call_tool("thinkneo_check", {"text": "latency test"}, auth=True)
            latencies.append((time.perf_counter() - start) * 1000)
            assert resp.status_code in (200, 202)

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]
        print(f"  LATENCY P95: {p95:.0f}ms (threshold: 2000ms)")
        assert p95 < 2000, f"P95={p95:.0f}ms exceeds 2000ms"

    def test_concurrent_requests_complete(self):
        """10 parallel requests should all complete even with 5s latency."""
        toxiproxy_add_toxic("latency_proxy", "latency", {"latency": 5000})

        async def _run():
            async with httpx.AsyncClient(timeout=30) as client:
                tasks = [
                    client.post(
                        f"{GATEWAY_URL}/mcp",
                        json={
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "id": str(i),
                            "params": {
                                "name": "thinkneo_check",
                                "arguments": {"text": f"concurrent-{i}"},
                            },
                        },
                        headers=AUTH_HEADERS,
                    )
                    for i in range(10)
                ]
                return await asyncio.gather(*tasks, return_exceptions=True)

        responses = asyncio.run(_run())
        successes = [
            r for r in responses
            if not isinstance(r, Exception) and r.status_code in (200, 202)
        ]
        assert len(successes) == 10, f"Only {len(successes)}/10 succeeded"

    def test_gateway_does_not_hang(self):
        """No single request should hang > 30s."""
        toxiproxy_add_toxic("latency_proxy", "latency", {"latency": 5000})

        start = time.time()
        resp = call_tool("thinkneo_check", {"text": "no-hang"}, auth=True)
        elapsed = time.time() - start

        assert resp.status_code in (200, 202)
        assert elapsed < 30, f"Request took {elapsed:.1f}s — possible hang"

    def test_no_crash_under_sustained_latency(self):
        """Gateway stays healthy after sustained high-latency period."""
        toxiproxy_add_toxic("latency_proxy", "latency", {"latency": 5000})

        for _ in range(5):
            call_tool("thinkneo_check", {"text": "sustained"}, auth=True)

        assert gateway_status() == "running", "Gateway crashed under sustained latency"

    def test_recovery_after_latency_removed(self):
        """Latency returns to normal after toxic removed."""
        toxiproxy_add_toxic("latency_proxy", "latency", {"latency": 5000})
        time.sleep(1)
        toxiproxy_remove_all_toxics("latency_proxy")

        start = time.perf_counter()
        resp = call_tool("thinkneo_check", {"text": "recovered"}, auth=True)
        elapsed = (time.perf_counter() - start) * 1000

        assert resp.status_code in (200, 202)
        assert elapsed < 2000, f"Post-recovery latency {elapsed:.0f}ms still high"
