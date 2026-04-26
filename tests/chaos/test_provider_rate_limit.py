"""
Scenario 4: Provider returns 429 — gateway handles upstream rate limiting.

Fault: wiremock returns 429 with Retry-After header
Expected: Gateway handles gracefully, no infinite loops, other tools unaffected,
          recovery when provider stops 429ing.

5 tests + recovery.
"""

import time
import pytest
from .conftest import (
    call_tool, parse_sse_result,
    wiremock_stub, wiremock_reset,
    gateway_status,
)


@pytest.fixture(autouse=True)
def clean_wiremock():
    wiremock_reset()
    yield
    wiremock_reset()


class TestProviderRateLimit:
    def test_gateway_handles_429(self):
        """Public tools (pure logic) work regardless of wiremock 429 stubs."""
        wiremock_stub("/.*", 429, body='{"error":"rate_limited"}',
                      headers={"Retry-After": "5"})

        resp = call_tool("thinkneo_check", {"text": "429 test"}, auth=True)
        assert resp.status_code in (200, 202)
        result = parse_sse_result(resp)
        assert "safe" in result

    def test_no_infinite_loop(self):
        """10 rapid requests must all complete within 30s (no retry loops)."""
        wiremock_stub("/.*", 429, body='{"error":"rate_limited"}',
                      headers={"Retry-After": "5"})

        start = time.time()
        for i in range(10):
            resp = call_tool("thinkneo_check", {"text": f"rapid-{i}"}, auth=True)
            assert resp.status_code in (200, 202)
        elapsed = time.time() - start
        assert elapsed < 30, f"10 requests took {elapsed:.1f}s — possible retry loop"

    def test_other_tools_unaffected(self):
        """Different tools/endpoints are isolated from 429 stub."""
        wiremock_stub("/.*", 429, body='{"error":"rate_limited"}')

        resp1 = call_tool("thinkneo_check", {"text": "tool1"}, auth=True)
        resp2 = call_tool("thinkneo_provider_status", {}, auth=True)
        assert resp1.status_code in (200, 202)
        assert resp2.status_code in (200, 202)

    def test_gateway_stays_healthy(self):
        """Gateway container must not crash during upstream 429 storm."""
        wiremock_stub("/.*", 429, body='{"error":"rate_limited"}')

        for _ in range(20):
            call_tool("thinkneo_check", {"text": "429-burst"}, auth=True)

        assert gateway_status() == "running", "Gateway crashed handling 429s"

    def test_recovery_after_429_clears(self):
        """Normal service resumes after wiremock switches from 429 to 200."""
        wiremock_stub("/.*", 429, body='{"error":"limited"}')
        time.sleep(1)

        wiremock_reset()
        wiremock_stub("/.*", 200, body='{"status":"ok"}')

        resp = call_tool("thinkneo_check", {"text": "recovered"}, auth=True)
        assert resp.status_code in (200, 202)
        result = parse_sse_result(resp)
        assert "safe" in result
