"""
Circuit Breaker — Fail-fast protection for external dependencies.

Prevents cascading failures when a dependency (PostgreSQL, Redis, HTTP)
is down. Instead of hammering a dead service and accumulating timeouts,
the breaker opens after N consecutive failures and returns 503 immediately
for a cooldown period before probing again.

States:
    CLOSED   → Normal operation. Failures increment counter.
    OPEN     → Dependency assumed down. All calls rejected immediately.
    HALF_OPEN → Cooldown elapsed. One probe call allowed.
                If probe succeeds → CLOSED. If probe fails → OPEN again.

Addresses SEC-07: Rate limiting and security checks previously failed
open on DB errors, allowing bypass. Now fails fast with circuit breaker.
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe circuit breaker for a single dependency.

    Args:
        name: Human-readable name (e.g. "postgresql", "redis").
        failure_threshold: Consecutive failures before opening. Default: 3.
        cooldown_seconds: Time in OPEN state before trying HALF_OPEN. Default: 30.
        rolling_window: Discard failure counts older than this. Default: 60s.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        rolling_window: float = 60.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.rolling_window = rolling_window

        self._state = CircuitState.CLOSED
        self._failure_timestamps: list[float] = []
        self._last_failure_time: float = 0.0
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

        # Metrics
        self._transitions: int = 0
        self._total_failures: int = 0
        self._total_rejected: int = 0
        self._time_in_open: float = 0.0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._check_state()

    def _check_state(self) -> CircuitState:
        """Check and possibly transition state. Must be called under lock."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.cooldown_seconds:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    def _transition(self, new_state: CircuitState) -> None:
        """Transition to a new state. Must be called under lock."""
        old = self._state
        if old == new_state:
            return
        if old == CircuitState.OPEN:
            self._time_in_open += time.monotonic() - self._opened_at
        self._state = new_state
        self._transitions += 1
        if new_state == CircuitState.OPEN:
            self._opened_at = time.monotonic()
        logger.warning(
            "Circuit breaker [%s]: %s → %s (failures=%d, transitions=%d)",
            self.name, old.value, new_state.value,
            len(self._failure_timestamps), self._transitions,
        )

    def allow_request(self) -> bool:
        """Check if a request should be allowed through.

        Returns True if allowed, False if the circuit is OPEN and the
        request should be rejected immediately.
        """
        with self._lock:
            state = self._check_state()
            if state == CircuitState.CLOSED:
                return True
            if state == CircuitState.HALF_OPEN:
                return True  # Allow the probe
            # OPEN
            self._total_rejected += 1
            return False

    def record_success(self) -> None:
        """Record a successful call. Resets failure counter."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._transition(CircuitState.CLOSED)
            self._failure_timestamps.clear()

    def record_failure(self) -> None:
        """Record a failed call. May open the circuit."""
        with self._lock:
            now = time.monotonic()
            self._total_failures += 1
            self._last_failure_time = now

            # Prune old failures outside rolling window
            cutoff = now - self.rolling_window
            self._failure_timestamps = [
                t for t in self._failure_timestamps if t > cutoff
            ]
            self._failure_timestamps.append(now)

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — reopen
                self._transition(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if len(self._failure_timestamps) >= self.failure_threshold:
                    self._transition(CircuitState.OPEN)

    def get_metrics(self) -> dict[str, Any]:
        """Return current metrics for monitoring."""
        with self._lock:
            state = self._check_state()
            open_time = self._time_in_open
            if state == CircuitState.OPEN:
                open_time += time.monotonic() - self._opened_at
            return {
                "name": self.name,
                "state": state.value,
                "consecutive_failures": len(self._failure_timestamps),
                "total_failures": self._total_failures,
                "total_rejected": self._total_rejected,
                "transitions": self._transitions,
                "time_in_open_seconds": round(open_time, 1),
            }


# ---------------------------------------------------------------------------
# Global breakers (one per dependency)
# ---------------------------------------------------------------------------

db_breaker = CircuitBreaker("postgresql", failure_threshold=3, cooldown_seconds=30)
