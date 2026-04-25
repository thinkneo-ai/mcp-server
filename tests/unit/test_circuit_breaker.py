"""
Tests for the CircuitBreaker implementation.
Addresses SEC-07: security checks previously failed open on DB errors.
"""

import time
import pytest
from unittest.mock import patch

import sys
sys.path.insert(0, ".")

from src.circuit_breaker import CircuitBreaker, CircuitState


@pytest.fixture
def breaker():
    return CircuitBreaker("test", failure_threshold=3, cooldown_seconds=0.5, rolling_window=5.0)


class TestCircuitBreakerStates:
    def test_starts_closed(self, breaker):
        assert breaker.state == CircuitState.CLOSED

    def test_allows_requests_when_closed(self, breaker):
        assert breaker.allow_request() is True

    def test_opens_after_3_consecutive_failures(self, breaker):
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_blocks_traffic_during_open_state(self, breaker):
        for _ in range(3):
            breaker.record_failure()
        assert breaker.allow_request() is False
        assert breaker.allow_request() is False

    def test_transitions_to_half_open_after_cooldown(self, breaker):
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        time.sleep(0.6)  # cooldown is 0.5s
        assert breaker.state == CircuitState.HALF_OPEN

    def test_closes_after_half_open_success(self, breaker):
        for _ in range(3):
            breaker.record_failure()
        time.sleep(0.6)
        assert breaker.state == CircuitState.HALF_OPEN
        assert breaker.allow_request() is True  # probe allowed
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_reopens_after_half_open_failure(self, breaker):
        for _ in range(3):
            breaker.record_failure()
        time.sleep(0.6)
        assert breaker.state == CircuitState.HALF_OPEN
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_success_resets_failure_count(self, breaker):
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()
        breaker.record_failure()
        # Only 1 failure after reset, not 3
        assert breaker.state == CircuitState.CLOSED


class TestCircuitBreakerRollingWindow:
    def test_old_failures_expire(self):
        b = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=1, rolling_window=0.3)
        b.record_failure()
        b.record_failure()
        time.sleep(0.4)  # first 2 failures expire
        b.record_failure()
        # Only 1 failure in window, not 3
        assert b.state == CircuitState.CLOSED


class TestCircuitBreakerMetrics:
    def test_metrics_structure(self, breaker):
        m = breaker.get_metrics()
        assert m["name"] == "test"
        assert m["state"] == "closed"
        assert m["consecutive_failures"] == 0
        assert m["total_failures"] == 0
        assert m["total_rejected"] == 0
        assert m["transitions"] == 0

    def test_metrics_count_rejections(self, breaker):
        for _ in range(3):
            breaker.record_failure()
        breaker.allow_request()  # rejected
        breaker.allow_request()  # rejected
        m = breaker.get_metrics()
        assert m["total_rejected"] == 2
        assert m["total_failures"] == 3
        assert m["transitions"] >= 1

    def test_metrics_track_open_time(self, breaker):
        for _ in range(3):
            breaker.record_failure()
        time.sleep(0.2)
        m = breaker.get_metrics()
        assert m["time_in_open_seconds"] >= 0.1


class TestIndependentBreakers:
    def test_independent_breakers_per_service(self):
        db = CircuitBreaker("db", failure_threshold=2)
        redis = CircuitBreaker("redis", failure_threshold=2)

        db.record_failure()
        db.record_failure()
        assert db.state == CircuitState.OPEN
        assert redis.state == CircuitState.CLOSED  # independent
