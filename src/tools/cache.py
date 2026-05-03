"""
Tools: thinkneo_cache_lookup, thinkneo_cache_store, thinkneo_cache_stats
Response caching for LLM API calls — huge cost savings.
Authenticated tools (enterprise cache is a paid feature, but basic cache is free).

v1: hash-based cache (exact match). v2 will add semantic similarity via embeddings.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ._common import utcnow
from ..plans import require_plan
from ..database import _get_conn

logger = logging.getLogger(__name__)


def _cache_key(text: str, model: Optional[str] = None, namespace: str = "default") -> str:
    """Deterministic cache key from text + model + namespace."""
    h = hashlib.sha256()
    h.update(namespace.encode("utf-8"))
    h.update(b"\x00")
    h.update((model or "").encode("utf-8"))
    h.update(b"\x00")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_cache_lookup",
        description=(
            "Look up a cached LLM response by exact prompt match. Returns the cached "
            "response if found and not expired. Use before calling an expensive LLM to "
            "save cost and latency. Namespaced to prevent collisions across workspaces. "
            "Free tier: shared cache. Enterprise: private + semantic similarity matching."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_cache_lookup(
        prompt: Annotated[str, Field(description="The prompt text (exact match lookup)")],
        model: Annotated[Optional[str], Field(description="Model name (e.g. 'gpt-5')")] = None,
        namespace: Annotated[str, Field(description="Cache namespace (e.g. workspace or tenant name)")] = "default",
    ) -> str:
        """Look up a cached LLM response by exact prompt match. Returns the cached response if found and not expired. Use before calling an expensive LLM to save cost and latency. Namespaced to prevent collisions across workspaces."""
        require_plan("pro")
        key = _cache_key(prompt, model, namespace)
        try:
            with _get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT response_json, created_at, expires_at, hit_count
                        FROM cache_entries
                        WHERE cache_key = %s
                          AND (expires_at IS NULL OR expires_at > NOW())
                        """,
                        (key,),
                    )
                    row = cur.fetchone()
                    if row:
                        # Increment hit counter
                        cur.execute(
                            "UPDATE cache_entries SET hit_count = hit_count + 1 WHERE cache_key = %s",
                            (key,),
                        )
                        return json.dumps({
                            "hit": True,
                            "cache_key": key[:16] + "...",
                            "response": row["response_json"],
                            "cached_at": row["created_at"].isoformat() if row["created_at"] else None,
                            "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
                            "hit_count": row["hit_count"] + 1,
                            "namespace": namespace,
                            "model": model,
                            "tier": "free",
                            "looked_up_at": utcnow(),
                        }, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.warning("cache_lookup failed: %s", exc)

        return json.dumps({
            "hit": False,
            "cache_key": key[:16] + "...",
            "namespace": namespace,
            "model": model,
            "recommendation": "No cached entry. Call your LLM provider and use thinkneo_cache_store to save the response.",
            "looked_up_at": utcnow(),
        }, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="thinkneo_cache_store",
        description=(
            "Store an LLM response in the cache for future lookups. Set TTL in seconds "
            "(default 24h). Upsert: replaces existing entries. "
            "Use this AFTER calling an LLM provider to cache the response for future calls."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_cache_store(
        prompt: Annotated[str, Field(description="The prompt text")],
        response: Annotated[str, Field(description="The LLM response to cache")],
        model: Annotated[Optional[str], Field(description="Model name")] = None,
        namespace: Annotated[str, Field(description="Cache namespace")] = "default",
        ttl_seconds: Annotated[int, Field(description="Time-to-live in seconds (default 86400 = 24h)", ge=60, le=30 * 86400)] = 86400,
    ) -> str:
        """Store an LLM response in the cache for future lookups. Set TTL in seconds (default 24h). Upsert: replaces existing entries."""
        require_plan("pro")
        key = _cache_key(prompt, model, namespace)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        # Store response as JSON — if already valid JSON, use as-is; else wrap as {"text": ...}
        try:
            parsed = json.loads(response)
            if not isinstance(parsed, (dict, list)):
                parsed = {"text": response}
        except (json.JSONDecodeError, TypeError):
            parsed = {"text": response}

        try:
            with _get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO cache_entries (cache_key, response_json, expires_at)
                        VALUES (%s, %s::jsonb, %s)
                        ON CONFLICT (cache_key) DO UPDATE
                            SET response_json = EXCLUDED.response_json,
                                expires_at = EXCLUDED.expires_at,
                                created_at = NOW(),
                                hit_count = 0
                        """,
                        (key, json.dumps(parsed), expires_at),
                    )
            return json.dumps({
                "stored": True,
                "cache_key": key[:16] + "...",
                "namespace": namespace,
                "model": model,
                "ttl_seconds": ttl_seconds,
                "expires_at": expires_at.isoformat(),
                "stored_at": utcnow(),
            }, indent=2)
        except Exception as exc:
            logger.warning("cache_store failed: %s", exc)
            return json.dumps({
                "stored": False,
                "error": str(exc),
                "fallback": "Cache is unavailable — proceed without caching.",
            }, indent=2)

    @mcp.tool(
        name="thinkneo_cache_stats",
        description=(
            "Get cache performance stats for a namespace. Shows hit rate, entries, "
            "estimated savings. Use to optimize caching strategy."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_cache_stats(
        namespace: Annotated[str, Field(description="Cache namespace")] = "default",
    ) -> str:
        """Get cache performance stats for a namespace. Shows hit rate, entries,"""
        require_plan("pro")
        # Note: namespace isn't queryable directly from cache_key (hash), but we can report global
        try:
            with _get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT
                            COUNT(*)                               AS total_entries,
                            COALESCE(SUM(hit_count), 0)            AS total_hits,
                            COUNT(*) FILTER (WHERE expires_at > NOW() OR expires_at IS NULL) AS active,
                            COUNT(*) FILTER (WHERE expires_at <= NOW()) AS expired,
                            COALESCE(AVG(hit_count), 0)            AS avg_hits_per_entry
                        FROM cache_entries
                    """)
                    stats = cur.fetchone() or {}
            total_entries = stats.get("total_entries", 0) or 0
            total_hits = stats.get("total_hits", 0) or 0
            # Estimate savings at avg $0.01 per LLM call
            estimated_saved_usd = round(total_hits * 0.01, 4)
            return json.dumps({
                "namespace": namespace,
                "global_stats": {
                    "total_entries": total_entries,
                    "active_entries": stats.get("active", 0) or 0,
                    "expired_entries": stats.get("expired", 0) or 0,
                    "total_cache_hits": total_hits,
                    "avg_hits_per_entry": round(float(stats.get("avg_hits_per_entry", 0) or 0), 2),
                },
                "estimated_savings_usd": estimated_saved_usd,
                "note": (
                    "Cache is a ThinkNEO-wide shared store. "
                    "For per-tenant isolated caches + semantic similarity matching + "
                    "larger storage, upgrade to Enterprise."
                ),
                "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
                "generated_at": utcnow(),
            }, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, indent=2)
