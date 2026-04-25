"""
Security middleware helpers — rate limiting and IP allowlisting.

These are called from check_free_tier() to enforce per-key limits beyond
the monthly quota. Uses circuit breaker (SEC-07) to fail-fast instead of
fail-open when the database is persistently down.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

from .circuit_breaker import db_breaker
from .database import _get_conn, hash_key

logger = logging.getLogger(__name__)

# Client IP set by BearerTokenMiddleware extension (or falls back to None).
_client_ip: ContextVar[Optional[str]] = ContextVar("client_ip", default=None)


def set_client_ip(ip: Optional[str]) -> None:
    _client_ip.set(ip)


def get_client_ip() -> Optional[str]:
    return _client_ip.get()


def check_rate_limit(api_key: str, tool_name: str) -> Optional[str]:
    """
    Enforce per-minute rate limit for a key on a specific tool.
    Returns None if allowed, or a JSON error string if blocked.

    Circuit breaker: if DB is persistently down (3+ consecutive failures),
    rejects with 503 instead of allowing unlimited access.
    """
    if not api_key or api_key == "anonymous":
        return None

    # Circuit breaker check — fail fast if DB is known to be down
    if not db_breaker.allow_request():
        return json.dumps({
            "error": "service_degraded",
            "message": "Rate limiting temporarily unavailable. Please retry later.",
            "retry_after": int(db_breaker.cooldown_seconds),
        })

    key_h = hash_key(api_key)
    now = datetime.now(timezone.utc)
    minute_bucket = now.replace(second=0, microsecond=0)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT rate_limit_per_min FROM api_keys WHERE key_hash = %s",
                    (key_h,),
                )
                row = cur.fetchone()
                if not row:
                    db_breaker.record_success()
                    return None

                limit = row.get("rate_limit_per_min") or 60

                cur.execute(
                    """
                    INSERT INTO rate_limit_events (key_hash, tool_name, minute_bucket, count)
                    VALUES (%s, %s, %s, 1)
                    ON CONFLICT (key_hash, tool_name, minute_bucket) DO UPDATE
                        SET count = rate_limit_events.count + 1
                    RETURNING count
                    """,
                    (key_h, tool_name, minute_bucket),
                )
                new_count = cur.fetchone().get("count", 1)

                db_breaker.record_success()

                if new_count > limit:
                    return json.dumps({
                        "error": "rate_limit_exceeded",
                        "limit_per_min": limit,
                        "current_minute_count": new_count,
                        "tool": tool_name,
                        "message": "Rate limit exceeded. Slow down or contact hello@thinkneo.ai for higher limits.",
                        "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
                    })
    except Exception as exc:
        db_breaker.record_failure()
        logger.warning("Rate limit check failed (circuit=%s): %s", db_breaker.state.value, exc)

    return None


def check_ip_allowlist(api_key: str) -> Optional[str]:
    """
    Enforce IP allowlist if set on the key.
    Returns None if allowed, or a JSON error string if blocked.

    Circuit breaker: if DB is persistently down, allows the request
    (IP check is secondary to rate limiting).
    """
    if not api_key or api_key == "anonymous":
        return None

    client_ip = get_client_ip()
    if not client_ip:
        return None

    if not db_breaker.allow_request():
        return None  # IP check is secondary — allow on circuit open

    key_h = hash_key(api_key)
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ip_allowlist FROM api_keys WHERE key_hash = %s",
                    (key_h,),
                )
                row = cur.fetchone()
                if not row:
                    db_breaker.record_success()
                    return None
                allowlist = row.get("ip_allowlist")
                if not allowlist:
                    db_breaker.record_success()
                    return None

                db_breaker.record_success()

                if client_ip not in allowlist:
                    return json.dumps({
                        "error": "ip_not_allowed",
                        "client_ip": client_ip,
                        "message": "Your IP is not in the allowlist for this API key.",
                        "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
                    })
    except Exception as exc:
        db_breaker.record_failure()
        logger.warning("IP allowlist check failed (circuit=%s): %s", db_breaker.state.value, exc)

    return None
