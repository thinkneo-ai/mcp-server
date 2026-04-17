"""
Database — PostgreSQL connection pool for the ThinkNEO MCP Server free-tier system.

Uses psycopg (v3) with async connection pool.
Falls back gracefully if the database is unavailable (tools still work, just no usage tracking).
"""

from __future__ import annotations

import hashlib
import logging
import os
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Iterator, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

# Connection parameters from environment — fail loud if password is missing
_DB_HOST = os.getenv("MCP_DB_HOST", "172.17.0.1")
_DB_PORT = int(os.getenv("MCP_DB_PORT", "5432"))
_DB_NAME = os.getenv("MCP_DB_NAME", "thinkneo_mcp")
_DB_USER = os.getenv("MCP_DB_USER", "mcp_user")
_DB_PASSWORD = os.getenv("MCP_DB_PASSWORD")
if not _DB_PASSWORD:
    raise RuntimeError("MCP_DB_PASSWORD environment variable must be set")

# sslmode=prefer → attempts TLS but falls back if DB doesn't support it.
# Our DB is on the Docker bridge (172.17.0.1) so plaintext is acceptable but
# we still attempt encryption for defense in depth.
_conninfo = (
    f"host={_DB_HOST} port={_DB_PORT} dbname={_DB_NAME} "
    f"user={_DB_USER} password={_DB_PASSWORD} "
    f"sslmode=prefer connect_timeout=5"
)

# Connection pool — min 2, max 10 connections. Idle timeout 5min.
# Using pool eliminates TCP setup per query and prevents connection exhaustion.
_pool: Optional[ConnectionPool] = None


def _get_pool() -> ConnectionPool:
    """Lazy-init the connection pool on first use."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            _conninfo,
            min_size=2,
            max_size=10,
            max_idle=300,
            timeout=10,
            kwargs={"row_factory": dict_row, "autocommit": True},
            open=True,
        )
        logger.info("PostgreSQL connection pool initialized (min=2, max=10)")
    return _pool


@contextmanager
def _get_conn() -> Iterator[psycopg.Connection]:
    """Get a pooled connection. Returns it to the pool on context exit."""
    pool = _get_pool()
    with pool.connection() as conn:
        yield conn


def hash_key(api_key: str) -> str:
    """SHA-256 hash of an API key for storage."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()




def is_key_revoked(api_key: str) -> bool:
    """Check if an API key has been revoked."""
    key_h = hash_key(api_key)
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM revoked_keys WHERE key_hash = %s", (key_h,))
                return cur.fetchone() is not None
    except Exception as exc:
        logger.warning("DB is_key_revoked failed: %s", exc)
        return False

def ensure_api_key(api_key: str, email: Optional[str] = None) -> dict[str, Any]:
    """
    Ensure an API key exists in the database. If not, auto-register it as free tier.
    Returns the api_keys row as a dict.
    """
    key_h = hash_key(api_key)
    key_prefix = api_key[:8]

    # Check if key has been revoked
    if is_key_revoked(api_key):
        logger.warning("Revoked API key attempted: %s...", key_prefix)
        return {"key_hash": key_h, "tier": "revoked", "monthly_limit": 0}

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM api_keys WHERE key_hash = %s", (key_h,))
                row = cur.fetchone()
                if row:
                    return dict(row)

                # Auto-register as free tier
                cur.execute(
                    """
                    INSERT INTO api_keys (key_hash, key_prefix, email, tier, monthly_limit, plan)
                    VALUES (%s, %s, %s, 'free', 500, 'free')
                    ON CONFLICT (key_hash) DO NOTHING
                    RETURNING *
                    """,
                    (key_h, key_prefix, email),
                )
                row = cur.fetchone()
                if row:
                    logger.info("Auto-registered free-tier API key: %s...", key_prefix)
                    return dict(row)

                # Race condition — re-fetch
                cur.execute("SELECT * FROM api_keys WHERE key_hash = %s", (key_h,))
                row = cur.fetchone()
                return dict(row) if row else {"key_hash": key_h, "tier": "free", "plan": "free", "monthly_limit": 500}
    except Exception as exc:
        logger.warning("DB ensure_api_key failed: %s", exc)
        return {"key_hash": key_h, "tier": "free", "plan": "free", "monthly_limit": 500}


def get_monthly_usage(key_hash: str) -> int:
    """Get the number of tool calls this month for a given key hash."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND called_at >= date_trunc('month', NOW())
                    """,
                    (key_hash,),
                )
                row = cur.fetchone()
                return row["cnt"] if row else 0
    except Exception as exc:
        logger.warning("DB get_monthly_usage failed: %s", exc)
        return 0


def log_tool_call(
    key_hash: str,
    tool_name: str,
    ip: Optional[str] = None,
    region: Optional[str] = None,
    cost_estimate: float = 0.0,
) -> None:
    """Log a tool call to the usage_log table."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO usage_log (key_hash, tool_name, ip, region, cost_estimate_usd)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (key_hash, tool_name, ip, region, cost_estimate),
                )
    except Exception as exc:
        logger.warning("DB log_tool_call failed: %s", exc)


def get_usage_stats(key_hash: str) -> dict[str, Any]:
    """
    Get comprehensive usage stats for an API key.
    Returns calls today/week/month, top tools, estimated cost.
    """
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Calls today
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt, COALESCE(SUM(cost_estimate_usd), 0) as cost
                    FROM usage_log
                    WHERE key_hash = %s AND called_at >= date_trunc('day', NOW())
                    """,
                    (key_hash,),
                )
                today = cur.fetchone()

                # Calls this week
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt, COALESCE(SUM(cost_estimate_usd), 0) as cost
                    FROM usage_log
                    WHERE key_hash = %s AND called_at >= date_trunc('week', NOW())
                    """,
                    (key_hash,),
                )
                week = cur.fetchone()

                # Calls this month
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt, COALESCE(SUM(cost_estimate_usd), 0) as cost
                    FROM usage_log
                    WHERE key_hash = %s AND called_at >= date_trunc('month', NOW())
                    """,
                    (key_hash,),
                )
                month = cur.fetchone()

                # Top tools this month
                cur.execute(
                    """
                    SELECT tool_name, COUNT(*) as cnt
                    FROM usage_log
                    WHERE key_hash = %s AND called_at >= date_trunc('month', NOW())
                    GROUP BY tool_name
                    ORDER BY cnt DESC
                    LIMIT 10
                    """,
                    (key_hash,),
                )
                top_tools = [{"tool": r["tool_name"], "count": r["cnt"]} for r in cur.fetchall()]

                # Get key info
                cur.execute("SELECT * FROM api_keys WHERE key_hash = %s", (key_hash,))
                key_info = cur.fetchone()

                monthly_limit = key_info["monthly_limit"] if key_info else 500
                tier = key_info["tier"] if key_info else "free"
                calls_this_month = month["cnt"] if month else 0

                return {
                    "calls_today": today["cnt"] if today else 0,
                    "calls_this_week": week["cnt"] if week else 0,
                    "calls_this_month": calls_this_month,
                    "monthly_limit": monthly_limit,
                    "calls_remaining": max(0, monthly_limit - calls_this_month),
                    "top_tools": top_tools,
                    "estimated_cost_usd": float(month["cost"]) if month else 0.0,
                    "tier": tier,
                    "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
                }
    except Exception as exc:
        logger.warning("DB get_usage_stats failed: %s", exc)
        return {
            "calls_today": 0,
            "calls_this_week": 0,
            "calls_this_month": 0,
            "monthly_limit": 500,
            "calls_remaining": 500,
            "top_tools": [],
            "estimated_cost_usd": 0.0,
            "tier": "free",
            "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
            "_note": "Usage stats temporarily unavailable",
        }


def db_healthy() -> bool:
    """Quick health check for the database connection."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
    except Exception:
        return False
