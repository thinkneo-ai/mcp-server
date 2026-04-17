"""
Security middleware helpers — rate limiting and IP allowlisting.

These are called from check_free_tier() to enforce per-key limits beyond
the monthly quota. Fail-open on DB errors to avoid blocking legit traffic
when the database is temporarily unavailable.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

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
    Fail-open on DB errors.
    """
    if not api_key or api_key == "anonymous":
        return None

    key_h = hash_key(api_key)
    now = datetime.now(timezone.utc)
    minute_bucket = now.replace(second=0, microsecond=0)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Get the key's limit
                cur.execute(
                    "SELECT rate_limit_per_min FROM api_keys WHERE key_hash = %s",
                    (key_h,),
                )
                row = cur.fetchone()
                if not row:
                    return None  # Key not registered — let ensure_api_key handle it
                limit = row.get("rate_limit_per_min") or 60  # default 60/min

                # Upsert per-minute counter
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

                if new_count > limit:
                    return (
                        '{"error": "rate_limit_exceeded", '
                        f'"limit_per_min": {limit}, '
                        f'"current_minute_count": {new_count}, '
                        f'"tool": "{tool_name}", '
                        '"message": "Rate limit exceeded. Slow down or contact hello@thinkneo.ai for higher limits.", '
                        '"docs_url": "https://mcp.thinkneo.ai/mcp/docs"}'
                    )
    except Exception as exc:
        logger.warning("Rate limit check failed (fail-open): %s", exc)

    return None


def check_ip_allowlist(api_key: str) -> Optional[str]:
    """
    Enforce IP allowlist if set on the key.
    Returns None if allowed, or a JSON error string if blocked.
    Fail-open on DB errors or missing client IP.
    """
    if not api_key or api_key == "anonymous":
        return None

    client_ip = get_client_ip()
    if not client_ip:
        return None  # No IP info — can't enforce

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
                    return None
                allowlist = row.get("ip_allowlist")
                if not allowlist:
                    return None  # No allowlist → all IPs allowed

                if client_ip not in allowlist:
                    return (
                        '{"error": "ip_not_allowed", '
                        f'"client_ip": "{client_ip}", '
                        '"message": "Your IP is not in the allowlist for this API key.", '
                        '"docs_url": "https://mcp.thinkneo.ai/mcp/docs"}'
                    )
    except Exception as exc:
        logger.warning("IP allowlist check failed (fail-open): %s", exc)

    return None
