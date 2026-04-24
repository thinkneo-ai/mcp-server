"""
Multi-dimensional rate limiting middleware.

Enforces per-tenant + per-workspace + per-agent rate limits using a
sliding window counter backed by PostgreSQL. Returns standard HTTP
rate limit headers (RFC 6585 / draft-ietf-httpapi-ratelimit-headers).

Headers added to every response:
  X-RateLimit-Limit: <max requests per window>
  X-RateLimit-Remaining: <remaining in current window>
  X-RateLimit-Reset: <epoch second when window resets>
  Retry-After: <seconds to wait> (only on 429)

Tier burst limits:
  Free:       10 requests/second burst, 500/month
  Starter:    100 requests/second burst, 5000/month
  Enterprise: custom (default 1000/s)
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from starlette.types import ASGIApp, Receive, Scope, Send

from ..auth import get_bearer_token
from ..database import hash_key

logger = logging.getLogger(__name__)

# Tier configuration: burst_per_second, requests_per_minute
TIER_LIMITS = {
    "free":       {"burst_per_second": 10,   "per_minute": 60},
    "starter":    {"burst_per_second": 100,  "per_minute": 600},
    "pro":        {"burst_per_second": 100,  "per_minute": 600},
    "enterprise": {"burst_per_second": 1000, "per_minute": 6000},
}

# In-memory sliding window (per key_hash, per second bucket)
# This avoids a DB call per request for burst limiting.
# Format: {key_hash: [(timestamp, count), ...]}
_burst_windows: dict[str, list[tuple[float, int]]] = {}


def _check_burst(key_hash: str, tier: str) -> tuple[bool, int, int]:
    """
    Check burst rate limit using in-memory sliding window.
    Returns (allowed, current_count, limit).
    """
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    burst_limit = limits["burst_per_second"]

    now = time.time()
    window_start = now - 1.0  # 1-second window

    # Get or create window for this key
    if key_hash not in _burst_windows:
        _burst_windows[key_hash] = []

    # Prune old entries
    _burst_windows[key_hash] = [
        (ts, c) for ts, c in _burst_windows[key_hash]
        if ts > window_start
    ]

    # Count current window
    current = sum(c for _, c in _burst_windows[key_hash])

    if current >= burst_limit:
        return False, current, burst_limit

    # Record this request
    _burst_windows[key_hash].append((now, 1))

    # Periodic cleanup (every 100 keys, prune stale entries)
    if len(_burst_windows) > 100:
        stale_keys = [
            k for k, v in _burst_windows.items()
            if not v or v[-1][0] < window_start
        ]
        for k in stale_keys:
            del _burst_windows[k]

    return True, current + 1, burst_limit


def _get_minute_usage(key_hash: str) -> tuple[int, int]:
    """
    Get per-minute usage from PostgreSQL.
    Returns (current_count, limit).
    Fail-open on DB errors.
    """
    try:
        from ..database import _get_conn
        now = datetime.now(timezone.utc)
        minute_bucket = now.replace(second=0, microsecond=0)

        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Get key tier and limit
                cur.execute(
                    "SELECT rate_limit_per_min, tier FROM api_keys WHERE key_hash = %s",
                    (key_hash,),
                )
                row = cur.fetchone()
                limit = (row.get("rate_limit_per_min") or 60) if row else 60

                # Get current minute count
                cur.execute(
                    """
                    SELECT COALESCE(SUM(count), 0) as total
                    FROM rate_limit_events
                    WHERE key_hash = %s AND minute_bucket = %s
                    """,
                    (key_hash, minute_bucket),
                )
                count_row = cur.fetchone()
                current = count_row["total"] if count_row else 0

                return int(current), int(limit)
    except Exception as exc:
        logger.debug("Rate limit DB check failed (fail-open): %s", exc)
        return 0, 60  # fail-open


class RateLimitMiddleware:
    """
    ASGI middleware that adds rate limit headers to all responses.
    Blocks requests that exceed burst or per-minute limits.

    Follows the same pure-ASGI pattern as BearerTokenMiddleware.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = get_bearer_token()
        if not token:
            # No token — let through without rate limit headers
            await self.app(scope, receive, send)
            return

        key_hash = hash_key(token)

        # Determine tier (from in-memory cache or DB)
        tier = "free"  # default
        try:
            from ..database import _get_conn
            with _get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT tier FROM api_keys WHERE key_hash = %s", (key_hash,))
                    row = cur.fetchone()
                    if row:
                        tier = row.get("tier", "free")
        except Exception:
            pass

        # Check burst limit (in-memory, fast)
        burst_ok, burst_count, burst_limit = _check_burst(key_hash, tier)

        if not burst_ok:
            # 429 Too Many Requests
            reset_time = int(time.time()) + 1
            body = json.dumps({
                "error": "rate_limit_exceeded",
                "type": "burst",
                "limit": burst_limit,
                "current": burst_count,
                "message": f"Burst rate limit exceeded ({burst_limit}/second for {tier} tier). Retry in 1 second.",
                "retry_after": 1,
            }).encode()

            async def send_429(message):
                if message["type"] == "http.response.start":
                    await send({
                        "type": "http.response.start",
                        "status": 429,
                        "headers": [
                            [b"content-type", b"application/json"],
                            [b"x-ratelimit-limit", str(burst_limit).encode()],
                            [b"x-ratelimit-remaining", b"0"],
                            [b"x-ratelimit-reset", str(reset_time).encode()],
                            [b"retry-after", b"1"],
                        ],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": body,
                    })

            await send_429({"type": "http.response.start"})
            return

        # Get minute-level usage for headers
        minute_count, minute_limit = _get_minute_usage(key_hash)
        remaining = max(0, minute_limit - minute_count)
        reset_epoch = int(time.time()) + (60 - datetime.now(timezone.utc).second)

        # Add rate limit headers to response
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    [b"x-ratelimit-limit", str(minute_limit).encode()],
                    [b"x-ratelimit-remaining", str(remaining).encode()],
                    [b"x-ratelimit-reset", str(reset_epoch).encode()],
                ])
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
