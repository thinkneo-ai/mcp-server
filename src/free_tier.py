"""
Free Tier Middleware — usage tracking and rate limiting for the ThinkNEO MCP Server.

On every tool call:
1. Check if an API key is provided
2. If no key: allow public tools with IP-based rate limit (30/hour)
3. If key provided AND registered (via /mcp/signup): check monthly usage
4. If key provided but NOT registered: treat as anonymous
5. Track usage in PostgreSQL
6. Update last_used_at for cleanup protection (hourly granularity)

SEC-01 fix: Removed auto-registration of arbitrary Bearer tokens.
Only keys created via /mcp/signup are recognized. Unknown tokens
get anonymous access to public tools with IP rate limiting.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .auth import get_bearer_token, is_authenticated
from .database import _get_conn, get_monthly_usage, hash_key, log_tool_call
from .redis_client import check_ip_rate
from .security import get_client_ip

logger = logging.getLogger(__name__)

# Public tools that work without auth and don't count against limits
PUBLIC_TOOLS = {
    "thinkneo_provider_status",
    "thinkneo_schedule_demo",
    "thinkneo_read_memory",
    "thinkneo_usage",
    "thinkneo_check",
    "thinkneo_simulate_savings",
    "thinkneo_get_trust_badge",
    "thinkneo_registry_search",
    "thinkneo_registry_get",
    "thinkneo_registry_install",
}

# Estimated cost per tool call in USD (very rough estimates)
TOOL_COST_ESTIMATES = {
    "thinkneo_check_spend": 0.005,
    "thinkneo_evaluate_guardrail": 0.003,
    "thinkneo_check_policy": 0.002,
    "thinkneo_get_budget_status": 0.003,
    "thinkneo_list_alerts": 0.003,
    "thinkneo_get_compliance_status": 0.004,
    "thinkneo_provider_status": 0.001,
    "thinkneo_schedule_demo": 0.001,
    "thinkneo_read_memory": 0.001,
    "thinkneo_write_memory": 0.002,
    "thinkneo_usage": 0.001,
    "thinkneo_check": 0.002,
    "thinkneo_route_model": 0.003,
    "thinkneo_get_savings_report": 0.002,
    "thinkneo_simulate_savings": 0.001,
    "thinkneo_evaluate_trust_score": 0.005,
    "thinkneo_get_trust_badge": 0.001,
    "thinkneo_bridge_mcp_to_a2a": 0.010,
    "thinkneo_bridge_a2a_to_mcp": 0.010,
    "thinkneo_bridge_generate_agent_card": 0.005,
    "thinkneo_bridge_list_mappings": 0.002,
    "thinkneo_start_trace": 0.002,
    "thinkneo_log_event": 0.001,
    "thinkneo_end_trace": 0.001,
    "thinkneo_get_trace": 0.002,
    "thinkneo_get_observability_dashboard": 0.003,
    "thinkneo_registry_search": 0.001,
    "thinkneo_registry_get": 0.001,
    "thinkneo_registry_publish": 0.003,
    "thinkneo_registry_review": 0.001,
    "thinkneo_registry_install": 0.001,
    "thinkneo_register_claim": 0.003,
    "thinkneo_verify_claim": 0.005,
    "thinkneo_get_proof": 0.002,
    "thinkneo_verification_dashboard": 0.003,
    "thinkneo_policy_create": 0.003,
    "thinkneo_policy_list": 0.002,
    "thinkneo_policy_evaluate": 0.004,
    "thinkneo_policy_violations": 0.002,
    "thinkneo_benchmark_report": 0.003,
    "thinkneo_benchmark_compare": 0.003,
    "thinkneo_router_explain": 0.003,
    "thinkneo_compliance_generate": 0.005,
    "thinkneo_compliance_list": 0.002,
    "thinkneo_sla_define": 0.003,
    "thinkneo_sla_status": 0.003,
    "thinkneo_sla_breaches": 0.002,
    "thinkneo_sla_dashboard": 0.003,
}

# IP rate limit for anonymous public tool access
_PUBLIC_TOOL_LIMIT_PER_HOUR = 30
_PUBLIC_TOOL_WINDOW_SECONDS = 3600


def _lookup_key(key_hash: str) -> Optional[dict]:
    """Look up an API key in the database. Returns row dict or None."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM api_keys WHERE key_hash = %s", (key_hash,))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as exc:
        logger.warning("DB key lookup failed: %s", exc)
        return None


def _touch_last_used(key_hash: str) -> None:
    """Update last_used_at if stale (>1 hour). Reduces DB write contention."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE api_keys SET last_used_at = NOW()
                    WHERE key_hash = %s
                      AND (last_used_at IS NULL OR last_used_at < NOW() - INTERVAL '1 hour')
                    """,
                    (key_hash,),
                )
    except Exception:
        pass  # Non-critical — best effort


def check_free_tier(tool_name: str) -> Optional[str]:
    """
    Check if the current request is within free-tier limits.

    Returns None if allowed, or a JSON error string if the request should be blocked.
    """
    token = get_bearer_token()

    # ── No token: anonymous access to public tools with IP rate limit ──
    if not token:
        if tool_name in PUBLIC_TOOLS:
            # IP-based rate limit for anonymous callers
            client_ip = get_client_ip() or "unknown"
            allowed, count = check_ip_rate(
                "publicrl", client_ip,
                _PUBLIC_TOOL_LIMIT_PER_HOUR, _PUBLIC_TOOL_WINDOW_SECONDS,
            )
            if not allowed:
                return json.dumps({
                    "error": "rate_limit_exceeded",
                    "message": f"Anonymous rate limit: {_PUBLIC_TOOL_LIMIT_PER_HOUR}/hour. "
                               "Sign up at https://mcp.thinkneo.ai/mcp/signup for 500/month free.",
                    "limit": _PUBLIC_TOOL_LIMIT_PER_HOUR,
                    "current": count,
                    "retry_after": 60,
                    "signup_url": "https://mcp.thinkneo.ai/mcp/signup",
                })
            log_tool_call(
                key_hash="anonymous",
                tool_name=tool_name,
                cost_estimate=TOOL_COST_ESTIMATES.get(tool_name, 0.001),
            )
            return None  # Allowed
        return None  # Non-public tool without auth — require_auth() handles

    # ── Token provided: check if it's a trusted master key ──
    if is_authenticated():
        key_h = hash_key(token)
        log_tool_call(
            key_hash=key_h,
            tool_name=tool_name,
            cost_estimate=TOOL_COST_ESTIMATES.get(tool_name, 0.001),
        )
        _touch_last_used(key_h)
        return None  # Allowed — trusted key

    # ── Token provided but NOT a master key ──
    # Look up in DB (only signup-created keys will exist)
    key_h = hash_key(token)
    key_info = _lookup_key(key_h)

    if not key_info:
        # Unknown token — NOT auto-registered (SEC-01 fix).
        # For public tools: treat as anonymous with IP rate limit.
        if tool_name in PUBLIC_TOOLS:
            client_ip = get_client_ip() or "unknown"
            allowed, count = check_ip_rate(
                "publicrl", client_ip,
                _PUBLIC_TOOL_LIMIT_PER_HOUR, _PUBLIC_TOOL_WINDOW_SECONDS,
            )
            if not allowed:
                return json.dumps({
                    "error": "rate_limit_exceeded",
                    "message": f"Anonymous rate limit: {_PUBLIC_TOOL_LIMIT_PER_HOUR}/hour. "
                               "Sign up at https://mcp.thinkneo.ai/mcp/signup for 500/month free.",
                    "limit": _PUBLIC_TOOL_LIMIT_PER_HOUR,
                    "current": count,
                    "retry_after": 60,
                    "signup_url": "https://mcp.thinkneo.ai/mcp/signup",
                })
            log_tool_call(
                key_hash="anonymous",
                tool_name=tool_name,
                cost_estimate=TOOL_COST_ESTIMATES.get(tool_name, 0.001),
            )
            return None  # Allowed as anonymous
        # Non-public tool with unknown token — require_auth() handles
        return None

    # ── Known key (from /mcp/signup) — apply free-tier limits ──
    tier = key_info.get("tier", "free")
    monthly_limit = key_info.get("monthly_limit", 500)

    # Enterprise tier — unlimited
    if tier == "enterprise":
        cost = TOOL_COST_ESTIMATES.get(tool_name, 0.001)
        log_tool_call(key_hash=key_h, tool_name=tool_name, cost_estimate=cost)
        _touch_last_used(key_h)
        return None

    # Check monthly usage
    current_usage = get_monthly_usage(key_h)

    if current_usage >= monthly_limit:
        return json.dumps({
            "error": "Monthly usage limit reached",
            "tier": tier,
            "monthly_limit": monthly_limit,
            "calls_used": current_usage,
            "message": (
                f"You've reached your {tier} tier limit of {monthly_limit} calls/month. "
                "Upgrade your plan for higher limits and premium features."
            ),
            "upgrade_url": "https://thinkneo.ai/pricing",
            "contact": "hello@thinkneo.ai",
            "reset": "Limits reset on the 1st of each month.",
        }, indent=2)

    # Within limits — log and allow
    cost = TOOL_COST_ESTIMATES.get(tool_name, 0.001)
    log_tool_call(key_hash=key_h, tool_name=tool_name, cost_estimate=cost)
    _touch_last_used(key_h)

    return None  # Allowed


def get_usage_footer(tool_name: str) -> Optional[dict[str, Any]]:
    """
    Generate the _usage footer to append to tool responses.
    """
    token = get_bearer_token()

    if not token:
        return {
            "calls_used": 0,
            "calls_remaining": "unlimited (public tool)",
            "tier": "anonymous",
            "monthly_limit": "N/A",
            "estimated_cost_usd": 0.0,
            "upgrade_url": "https://thinkneo.ai/pricing",
        }

    key_h = hash_key(token)

    # Check if key exists in DB (NO auto-registration — SEC-01 fix)
    key_info = _lookup_key(key_h)

    if not key_info:
        # Unknown token — return anonymous stats without registering
        return {
            "calls_used": 0,
            "calls_remaining": "unlimited (public tool)",
            "tier": "anonymous",
            "monthly_limit": "N/A",
            "estimated_cost_usd": 0.0,
            "upgrade_url": "https://thinkneo.ai/pricing",
            "note": "Unrecognized API key. Sign up at https://mcp.thinkneo.ai/mcp/signup for tracked usage.",
        }

    monthly_limit = key_info.get("monthly_limit", 500)
    tier = key_info.get("tier", "free")
    current_usage = get_monthly_usage(key_h)
    cost = TOOL_COST_ESTIMATES.get(tool_name, 0.001)

    return {
        "calls_used": current_usage,
        "calls_remaining": max(0, monthly_limit - current_usage) if tier != "enterprise" else "unlimited",
        "tier": tier,
        "monthly_limit": monthly_limit if tier != "enterprise" else "unlimited",
        "estimated_cost_usd": round(cost, 6),
        "upgrade_url": "https://thinkneo.ai/pricing",
    }
