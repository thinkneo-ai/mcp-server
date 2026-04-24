"""
Free Tier Middleware — usage tracking and rate limiting for the ThinkNEO MCP Server.

On every tool call:
1. Check if an API key is provided
2. If no key: allow public tools unlimited (provider_status, schedule_demo, read_memory)
3. If key provided: check monthly usage against limit
4. If over limit: return friendly upgrade message
5. Auto-register new API keys on first use (free tier)
6. Track usage in PostgreSQL
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .auth import get_bearer_token, is_authenticated
from .database import ensure_api_key, get_monthly_usage, hash_key, log_tool_call

logger = logging.getLogger(__name__)

# Public tools that work without auth and don't count against limits
PUBLIC_TOOLS = {
    "thinkneo_provider_status",
    "thinkneo_schedule_demo",
    "thinkneo_read_memory",
    "thinkneo_usage",       # Usage tool itself is always accessible
    "thinkneo_check",       # Free-tier guardrail check
    "thinkneo_simulate_savings",  # Smart Router lead gen — free
    "thinkneo_get_trust_badge",      # Public trust badge lookup
    "thinkneo_registry_search",   # Marketplace — free discovery
    "thinkneo_registry_get",      # Marketplace — free details
    "thinkneo_registry_install",  # Marketplace — free install tracking
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
    # Outcome Validation Loop (2026-04-24)
    "thinkneo_register_claim": 0.003,
    "thinkneo_verify_claim": 0.005,
    "thinkneo_get_proof": 0.002,
    "thinkneo_verification_dashboard": 0.003,
}


def check_free_tier(tool_name: str) -> Optional[str]:
    """
    Check if the current request is within free-tier limits.

    Returns None if allowed, or a JSON error string if the request should be blocked.
    Also logs the tool call to the database.
    """
    token = get_bearer_token()

    # No token provided — only allow public tools, skip DB for them
    if not token:
        if tool_name in PUBLIC_TOOLS:
            log_tool_call(
                key_hash="anonymous",
                tool_name=tool_name,
                cost_estimate=TOOL_COST_ESTIMATES.get(tool_name, 0.001),
            )
            return None  # Allowed
        # Non-public tool without auth — let the existing auth system handle it
        return None

    # Token provided — check if it's already validated by the original auth system
    # (i.e. in THINKNEO_MCP_API_KEYS / THINKNEO_API_KEY env vars).
    # If so, treat as enterprise (unlimited, no free-tier limit).
    if is_authenticated():
        key_h = hash_key(token)
        log_tool_call(
            key_hash=key_h,
            tool_name=tool_name,
            cost_estimate=TOOL_COST_ESTIMATES.get(tool_name, 0.001),
        )
        return None  # Allowed — trusted key

    # Token NOT in the trusted keys list — this is a free-tier / self-registered key.
    # For non-public tools, reject (they need a trusted key).
    if tool_name not in PUBLIC_TOOLS:
        return None  # Let the original require_auth() handle the rejection

    # Public/free tool with an unknown token — auto-register and apply free-tier limits.
    key_info = ensure_api_key(token)
    key_h = hash_key(token)
    monthly_limit = key_info.get("monthly_limit", 500)
    tier = key_info.get("tier", "free")

    # Enterprise tier — unlimited
    if tier == "enterprise":
        cost = TOOL_COST_ESTIMATES.get(tool_name, 0.001)
        log_tool_call(key_hash=key_h, tool_name=tool_name, cost_estimate=cost)
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

    # Within limits — log the call
    cost = TOOL_COST_ESTIMATES.get(tool_name, 0.001)
    log_tool_call(key_hash=key_h, tool_name=tool_name, cost_estimate=cost)

    return None  # Allowed


def get_usage_footer(tool_name: str) -> Optional[dict[str, Any]]:
    """
    Generate the _usage footer to append to tool responses.
    Returns None if no token is present.
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
    current_usage = get_monthly_usage(key_h)

    # Get key info
    key_info = ensure_api_key(token)
    monthly_limit = key_info.get("monthly_limit", 500)
    tier = key_info.get("tier", "free")
    cost = TOOL_COST_ESTIMATES.get(tool_name, 0.001)

    return {
        "calls_used": current_usage,
        "calls_remaining": max(0, monthly_limit - current_usage) if tier != "enterprise" else "unlimited",
        "tier": tier,
        "monthly_limit": monthly_limit if tier != "enterprise" else "unlimited",
        "estimated_cost_usd": round(cost, 6),
        "upgrade_url": "https://thinkneo.ai/pricing",
    }
