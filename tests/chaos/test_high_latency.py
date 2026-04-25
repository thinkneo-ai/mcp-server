"""Scenario 5: High latency — toxiproxy adds 5s latency."""

import asyncio
import time
import pytest
import httpx
from .conftest import (
    call_tool, parse_sse_result,
    toxiproxy_create_proxy, toxiproxy_add_toxic, toxiproxy_remove_all_toxics,
    wiremock_stub, wiremock_reset,
    GATEWAY_URL, PUBLIC_HEADERS,
)


@pytest.fixture(autouse=True)
def setup_latency():
    toxiproxy_create_proxy("latency_proxy", "0.0.0.0:18080", "wiremock:8080")
    wiremock_stub("/.*", 200, body='{"status":"ok"}')
    yield
    toxiproxy_remove_all_toxics("latency_proxy")
    wiremock_reset()


class TestHighLatency:
    def test_fast_tools_unaffected(self):
        """Pure-logic tools (no external I/O) should maintain P95 < 2s."""
        toxiproxy_add_toxic("latency_proxy", "latency", {"latency": 5000})

        latencies = []
        for _ in range(10):
            start = time.perf_counter()
            resp = call_tool("thinkneo_check", {"text": "latency test"}, auth=False)
            latencies.append((time.perf_counter() - start) * 1000)
            assert resp.status_code in (200, 202)

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]
        print(f"  LATENCY P95: {p95:.0f}ms (threshold: 2000ms)")
        assert p95 < 2000, f"P95={p95:.0f}ms exceeds 2000ms"

    def test_concurrent_requests_complete(self):
        """10 parallel requests should all complete even with latency."""
        toxiproxy_add_toxic("latency_proxy", "latency", {"latency": 5000})

        async def run_concurrent():
            async with httpx.AsyncClient(timeout=30) as client:
                tasks = []
                for i in range(10):
                    tasks.append(client.post(
                        f"{GATEWAY_URL}/mcp",
                        json={
                            "jsonrpc": "2.0", "method": "tools/call", "id": str(i),
                            "params": {"name": "thinkneo_check", "arguments": {"text": f"concurrent-{i}"}},
                        },
                        headers=PUBLIC_HEADERS,
                    ))
                responses = await asyncio.gather(*tasks, return_exceptions=True)
            return responses

        responses = asyncio.run(run_concurrent())
        successes = [r for r in responses if not isinstance(r, Exception) and r.status_code in (200, 202)]
        assert len(successes) == 10, f"Only {len(successes)}/10 succeeded"

    def test_gateway_does_not_hang(self):
        """No request should hang > 30s, even with latency injection."""
        toxiproxy_add_toxic("latency_proxy", "latency", {"latency": 5000})

        start = time.time()
        resp = call_tool("thinkneo_check", {"text": "no-hang"}, auth=False)
        elapsed = time.time() - start

        assert resp.status_code in (200, 202)
        assert elapsed < 30, f"Request took {elapsed:.1f}s — possible hang"

    def test_no_crash_under_sustained_latency(self):
        """Gateway stays healthy after sustained high-latency period."""
        import subprocess
        toxiproxy_add_toxic("latency_proxy", "latency", {"latency": 5000})

        for _ in range(5):
            call_tool("thinkneo_check", {"text": "sustained"}, auth=False)

        status = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", "thinkneo-chaos-gateway"],
            capture_output=True, text=True
        ).stdout.strip()
        assert status == "running"

    def test_recovery_after_latency_removed(self):
        """Latency returns to normal after toxic removed."""
        toxiproxy_add_toxic("latency_proxy", "latency", {"latency": 5000})
        time.sleep(1)
        toxiproxy_remove_all_toxics("latency_proxy")

        start = time.perf_counter()
        resp = call_tool("thinkneo_check", {"text": "recovered"}, auth=False)
        elapsed = (time.perf_counter() - start) * 1000

        assert resp.status_code in (200, 202)
        assert elapsed < 2000, f"Post-recovery latency {elapsed:.0f}ms still high"
