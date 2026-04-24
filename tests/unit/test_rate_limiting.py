"""
Unit tests for multi-dimensional rate limiting.

Tests burst limiting, per-minute limits, tier configuration,
HTTP headers, and graceful degradation.
"""

import json
import time
import pytest
from unittest.mock import patch, MagicMock
from src.middleware.rate_limit import (
    _check_burst, _burst_windows, _get_minute_usage,
    TIER_LIMITS, RateLimitMiddleware,
)


@pytest.fixture(autouse=True)
def clear_burst_windows():
    """Clear in-memory burst windows between tests."""
    _burst_windows.clear()
    yield
    _burst_windows.clear()


class TestTierConfiguration:
    def test_free_tier_limits(self):
        assert TIER_LIMITS["free"]["burst_per_second"] == 10
        assert TIER_LIMITS["free"]["per_minute"] == 60

    def test_starter_tier_limits(self):
        assert TIER_LIMITS["starter"]["burst_per_second"] == 100
        assert TIER_LIMITS["starter"]["per_minute"] == 600

    def test_enterprise_tier_limits(self):
        assert TIER_LIMITS["enterprise"]["burst_per_second"] == 1000
        assert TIER_LIMITS["enterprise"]["per_minute"] == 6000

    def test_all_tiers_defined(self):
        for tier in ("free", "starter", "pro", "enterprise"):
            assert tier in TIER_LIMITS
            assert "burst_per_second" in TIER_LIMITS[tier]
            assert "per_minute" in TIER_LIMITS[tier]


class TestBurstLimiting:
    def test_first_request_allowed(self):
        allowed, count, limit = _check_burst("key-1", "free")
        assert allowed is True
        assert count == 1
        assert limit == 10

    def test_under_limit_allowed(self):
        for i in range(9):
            allowed, _, _ = _check_burst("key-2", "free")
            assert allowed is True

    def test_at_limit_blocked(self):
        for _ in range(10):
            _check_burst("key-3", "free")
        allowed, count, limit = _check_burst("key-3", "free")
        assert allowed is False
        assert count >= 10

    def test_enterprise_higher_burst(self):
        for _ in range(50):
            allowed, _, _ = _check_burst("key-ent", "enterprise")
            assert allowed is True

    def test_different_keys_independent(self):
        for _ in range(10):
            _check_burst("key-a", "free")
        # key-a is at limit, but key-b should be fine
        allowed, _, _ = _check_burst("key-b", "free")
        assert allowed is True

    def test_window_resets_after_1_second(self):
        for _ in range(10):
            _check_burst("key-reset", "free")

        # Simulate window expiry by clearing old entries
        _burst_windows["key-reset"] = [
            (time.time() - 2.0, 10)  # 2 seconds ago — expired
        ]
        allowed, count, _ = _check_burst("key-reset", "free")
        assert allowed is True
        assert count == 1  # fresh window

    def test_unknown_tier_defaults_to_free(self):
        allowed, _, limit = _check_burst("key-unknown", "nonexistent_tier")
        assert allowed is True
        assert limit == 10  # free tier default


class TestMinuteUsage:
    def test_returns_zero_on_db_error(self):
        """Fail-open: returns (0, 60) when DB is unavailable."""
        with patch("src.database._get_conn", side_effect=Exception("DB down")):
            count, limit = _get_minute_usage("somehash")
        assert count == 0
        assert limit == 60


class TestRateLimitMiddleware:
    def test_passes_through_non_http(self):
        """Non-HTTP scopes pass through without rate limiting."""
        import asyncio
        called = []

        async def mock_app(scope, receive, send):
            called.append(True)

        middleware = RateLimitMiddleware(mock_app)

        async def run():
            await middleware({"type": "lifespan"}, MagicMock(), MagicMock())
            assert len(called) == 1

        asyncio.get_event_loop().run_until_complete(run())

    def test_passes_through_without_token(self):
        """Requests without bearer token pass through without headers."""
        import asyncio
        called = []

        async def mock_app(scope, receive, send):
            called.append(True)

        middleware = RateLimitMiddleware(mock_app)

        async def run():
            with patch("src.middleware.rate_limit.get_bearer_token", return_value=None):
                await middleware(
                    {"type": "http", "method": "POST", "path": "/mcp", "headers": []},
                    MagicMock(), MagicMock()
                )
            assert len(called) == 1

        asyncio.get_event_loop().run_until_complete(run())
