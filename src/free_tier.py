"""
Free Tier Middleware — plan-based paywall + usage tracking for ThinkNEO MCP Server.

Plan enforcement:
  FREE  → only FREE_PLAN_TOOLS (5 tools), 500 calls/month
  PRO   → all tools, 5000 calls/month
  ENTERPRISE → all tools, unlimited

On every tool call:
1. No token → allow only PUBLIC_TOOLS (anonymous)
2. Token → check revocation, IP allowlist, rate limit
3. Check plan → block Pro tools on Free plan with clear upgrade message
4. Check monthly usage → block if over limit
5. Log usage
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .auth import get_bearer_token
from .database import ensure_api_key, get_monthly_usage, hash_key, is_key_revoked, log_tool_call
from .security import check_rate_limit, check_ip_allowlist

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plan definitions
# ---------------------------------------------------------------------------

# Tools available on the FREE plan (no payment required)
FREE_PLAN_TOOLS = {
    "thinkneo_check",                   # Prompt safety check
    "thinkneo_provider_status",         # Provider health
    "thinkneo_read_memory",             # Memory read
    "thinkneo_usage",                   # Usage stats
    "thinkneo_write_memory",            # Memory write
}

# Tools that work without any authentication (anonymous users)
PUBLIC_TOOLS = {
    "thinkneo_provider_status",
    "thinkneo_read_memory",
    "thinkneo_usage",
    "thinkneo_check",
}

# All Pro-only tools (require Pro or Enterprise plan)
PRO_TOOLS = {
    "thinkneo_check_spend",
    "thinkneo_evaluate_guardrail",
    "thinkneo_check_policy",
    "thinkneo_get_budget_status",
    "thinkneo_list_alerts",
    "thinkneo_get_compliance_status",
    "thinkneo_scan_secrets",
    "thinkneo_detect_injection",
    "thinkneo_compare_models",
    "thinkneo_optimize_prompt",
    "thinkneo_estimate_tokens",
    "thinkneo_check_pii_international",
    "thinkneo_cache_lookup",
    "thinkneo_cache_store",
    "thinkneo_cache_stats",
    "thinkneo_rotate_key",
    "thinkneo_schedule_demo",
}

# Monthly call limits by plan
PLAN_LIMITS = {
    "free": 500,
    "pro": 5000,
    "enterprise": None,  # unlimited
}

# Cost estimates per tool call (USD)
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
    "thinkneo_scan_secrets": 0.002,
    "thinkneo_detect_injection": 0.002,
    "thinkneo_compare_models": 0.001,
    "thinkneo_optimize_prompt": 0.002,
    "thinkneo_estimate_tokens": 0.001,
    "thinkneo_check_pii_international": 0.002,
    "thinkneo_cache_lookup": 0.0005,
    "thinkneo_cache_store": 0.001,
    "thinkneo_cache_stats": 0.0005,
    "thinkneo_rotate_key": 0.005,
}


def _plan_upgrade_error(tool_name: str, current_plan: str) -> str:
    """Return a clear JSON error for plan-blocked tools."""
    return json.dumps({
        "error": "plan_upgrade_required",
        "code": -32001,
        "tool": tool_name,
        "current_plan": current_plan,
        "required_plan": "pro",
        "message": (
            f"The tool '{tool_name}' requires a Pro or Enterprise plan. "
            f"Your current plan is '{current_plan}'. "
            "Upgrade at https://thinkneo.ai/pricing to unlock all 22 tools, "
            "5,000 calls/month, response caching, and priority support."
        ),
        "upgrade_url": "https://thinkneo.ai/pricing",
        "free_tools": sorted(FREE_PLAN_TOOLS),
        "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
    }, indent=2)


def check_free_tier(tool_name: str) -> Optional[str]:
    """
    Check plan-based access + usage limits.
    Returns None if allowed, or a JSON error string if blocked.
    """
    token = get_bearer_token()

    # ── No token: anonymous access ──────────────────────────────────
    if not token:
        if tool_name in PUBLIC_TOOLS:
            log_tool_call(
                key_hash="anonymous",
                tool_name=tool_name,
                cost_estimate=TOOL_COST_ESTIMATES.get(tool_name, 0.001),
            )
            return None  # allowed
        # Non-public tool without token — auth system will handle 401
        return None

    # ── Token provided: full validation pipeline ────────────────────

    # 1. Revocation check
    if is_key_revoked(token):
        return json.dumps({
            "error": "api_key_revoked",
            "message": "This API key has been revoked. Contact hello@thinkneo.ai for a new key.",
            "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
        }, indent=2)

    # 2. IP allowlist check
    ip_block = check_ip_allowlist(token)
    if ip_block:
        return ip_block

    # 3. Rate limit check
    rate_block = check_rate_limit(token, tool_name)
    if rate_block:
        return rate_block

    # 4. Resolve key info (auto-register if new)
    key_info = ensure_api_key(token)
    key_h = hash_key(token)
    plan = key_info.get("plan") or key_info.get("tier") or "free"

    # 5. ── PLAN-BASED TOOL ACCESS CONTROL (PAYWALL) ─────────────────
    if plan == "free" and tool_name not in FREE_PLAN_TOOLS:
        # Log the blocked attempt for analytics
        log_tool_call(key_hash=key_h, tool_name=f"BLOCKED:{tool_name}", cost_estimate=0)
        return _plan_upgrade_error(tool_name, plan)

    # 6. Monthly usage check
    monthly_limit = PLAN_LIMITS.get(plan)
    if monthly_limit is not None:  # None = unlimited (enterprise)
        current_usage = get_monthly_usage(key_h)
        if current_usage >= monthly_limit:
            return json.dumps({
                "error": "monthly_limit_reached",
                "plan": plan,
                "monthly_limit": monthly_limit,
                "calls_used": current_usage,
                "message": (
                    f"You've reached your {plan} plan limit of {monthly_limit} calls/month. "
                    + ("Upgrade to Pro for 5,000 calls/month: https://thinkneo.ai/pricing"
                       if plan == "free" else
                       "Contact hello@thinkneo.ai for Enterprise (unlimited).")
                ),
                "upgrade_url": "https://thinkneo.ai/pricing",
                "reset": "Limits reset on the 1st of each month.",
                "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
            }, indent=2)

    # 7. Allowed — log the call
    cost = TOOL_COST_ESTIMATES.get(tool_name, 0.001)
    log_tool_call(key_hash=key_h, tool_name=tool_name, cost_estimate=cost)
    return None


def get_usage_footer(tool_name: str) -> Optional[dict[str, Any]]:
    """Generate the _usage footer appended to tool responses."""
    token = get_bearer_token()

    if not token:
        return {
            "calls_used": 0,
            "calls_remaining": "unlimited (anonymous)",
            "plan": "anonymous",
            "monthly_limit": "N/A",
            "estimated_cost_usd": 0.0,
            "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
        }

    key_h = hash_key(token)
    key_info = ensure_api_key(token)
    plan = key_info.get("plan") or key_info.get("tier") or "free"
    monthly_limit = PLAN_LIMITS.get(plan)
    current_usage = get_monthly_usage(key_h)
    cost = TOOL_COST_ESTIMATES.get(tool_name, 0.001)

    return {
        "calls_used": current_usage,
        "calls_remaining": (
            max(0, monthly_limit - current_usage)
            if monthly_limit is not None
            else "unlimited"
        ),
        "plan": plan,
        "monthly_limit": monthly_limit if monthly_limit is not None else "unlimited",
        "estimated_cost_usd": round(cost, 6),
        "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
    }
