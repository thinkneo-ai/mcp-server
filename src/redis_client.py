"""
Redis client — shared connection for rate limiting and caching.

Lazy singleton, fail-open on connection errors.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_redis = None
_redis_lock = threading.Lock()


def get_redis():
    """Get the shared Redis client (lazy init). Returns None if unavailable."""
    global _redis
    if _redis is not None:
        return _redis
    with _redis_lock:
        if _redis is not None:
            return _redis
        url = os.getenv("MCP_REDIS_URL", "")
        if not url:
            logger.info("MCP_REDIS_URL not set — Redis rate limiting disabled")
            return None
        try:
            import redis
            _redis = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)
            _redis.ping()
            logger.info("Redis connected: %s", url.split("@")[-1] if "@" in url else url)
            return _redis
        except Exception as exc:
            logger.warning("Redis connection failed (rate limiting degraded): %s", exc)
            _redis = None
            return None


def check_ip_rate(key_prefix: str, client_ip: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Check IP-based rate limit using Redis INCR + TTL.

    Returns (allowed: bool, current_count: int).
    Fail-open if Redis unavailable.
    """
    r = get_redis()
    if r is None:
        return True, 0  # fail-open

    cache_key = f"{key_prefix}:{client_ip}"
    try:
        pipe = r.pipeline()
        pipe.incr(cache_key)
        pipe.ttl(cache_key)
        count, ttl = pipe.execute()

        if ttl == -1:  # Key exists but no TTL (shouldn't happen, but safety)
            r.expire(cache_key, window_seconds)
        elif ttl == -2 or count == 1:  # Key is new
            r.expire(cache_key, window_seconds)

        return count <= limit, count
    except Exception as exc:
        logger.warning("Redis rate check failed (fail-open): %s", exc)
        return True, 0
