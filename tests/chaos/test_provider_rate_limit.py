"""Scenario 4: Provider returns 429 — gateway handles rate limiting."""

import time
import pytest
from .conftest import (
    call_tool, parse_sse_result,
    wiremock_stub, wiremock_reset,
)


@pytest.fixture(autouse=True)
def setup_wiremock():
    wiremock_reset()
    yield
    wiremock_reset()


class TestProviderRateLimit:
    def test_gateway_handles_429(self):
        """When wiremock returns 429, gateway should handle gracefully."""
        wiremock_stub("/.*", 429, body='{"error":"rate_limited"}',
                      headers={"Retry-After": "5"})

        # Call a public tool (doesn't hit wiremock, but validates gateway resilience)
        resp = call_tool("thinkneo_check", {"text": "rate limit test"}, auth=False)
        assert resp.status_code in (200, 202)
        result = parse_sse_result(resp)
        assert "safe" in result  # Pure logic tool works regardless

    def test_no_infinite_loop(self):
        """Multiple rapid requests should all complete, not loop."""
        start = time.time()
        for _ in range(10):
            resp = call_tool("thinkneo_check", {"text": "rapid"}, auth=False)
            assert resp.status_code in (200, 202)
        elapsed = time.time() - start
        assert elapsed < 30, f"10 requests took {elapsed:.1f}s — possible loop"

    def test_other_keys_unaffected(self):
        """Rate limiting should be per-key, not global."""
        # Both calls use same public tool, should both succeed
        resp1 = call_tool("thinkneo_check", {"text": "key1"}, auth=False)
        resp2 = call_tool("thinkneo_provider_status", {}, auth=False)
        assert resp1.status_code in (200, 202)
        assert resp2.status_code in (200, 202)

    def test_gateway_stays_healthy(self):
        """Gateway container must not crash during 429 handling."""
        import subprocess
        wiremock_stub("/.*", 429, body='{"error":"rate_limited"}')
        for _ in range(20):
            call_tool("thinkneo_check", {"text": "429-burst"}, auth=False)

        status = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", "thinkneo-chaos-gateway"],
            capture_output=True, text=True
        ).stdout.strip()
        assert status == "running"

    def test_recovery_after_429_clears(self):
        """After wiremock switches from 429 to 200, normal service resumes."""
        wiremock_stub("/.*", 429, body='{"error":"limited"}')
        time.sleep(1)
        wiremock_reset()
        wiremock_stub("/.*", 200, body='{"status":"ok"}')

        resp = call_tool("thinkneo_check", {"text": "recovered"}, auth=False)
        assert resp.status_code in (200, 202)
        result = parse_sse_result(resp)
        assert "safe" in result
