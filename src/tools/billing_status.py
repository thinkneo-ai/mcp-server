"""
Tool: thinkneo_status — Show current subscription state

Auth: Bearer token required
Uses: GET /v1/billing/saas/status (STATUS-API path)
"""

from __future__ import annotations

import json
import logging

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..auth import get_bearer_token, is_authenticated

logger = logging.getLogger(__name__)

ADMIN_API_BASE = "http://thinkneo-admin-api:8907"


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_billing_status",
        description=(
            "Show current ThinkNEO MCP subscription tier, quota usage, billing status, "
            "and subscription period. Requires API key."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_billing_status() -> str:
        token = get_bearer_token()
        if not token:
            return json.dumps({"error": "API key required. Configure: Authorization: Bearer <key>"}, indent=2)

        # Master/enterprise keys bypass admin API billing
        if is_authenticated():
            from ..free_tier import get_usage_footer
            footer = get_usage_footer("thinkneo_billing_status") or {}
            tier = footer.get("tier", "enterprise")
            if tier == "enterprise":
                return json.dumps({
                    "tier": "enterprise",
                    "quota_used": footer.get("calls_used", 0),
                    "quota_limit": "unlimited",
                    "billing_status": "active",
                    "message": "Enterprise tier — unlimited calls, all tools enabled.",
                }, indent=2)

        try:
            resp = httpx.get(
                f"{ADMIN_API_BASE}/v1/billing/saas/status",
                headers={"X-API-Key": token},
                timeout=10.0,
            )

            if resp.status_code == 401:
                return json.dumps({"error": "Invalid API key. Sign up first with thinkneo_signup."}, indent=2)
            if resp.status_code != 200:
                return json.dumps({"error": f"Status unavailable (HTTP {resp.status_code})", "detail": resp.text[:200]}, indent=2)

            data = resp.json()
            tier = data.get("tier", "unknown")
            result = {
                "tier": tier,
                "email": data.get("email"),
                "quota_used": data.get("quota_used", 0),
                "quota_limit": data.get("quota_limit", 500),
                "billing_status": data.get("billing_status", "active" if tier == "free" else "unknown"),
                "subscription_id": data.get("subscription_id"),
                "current_period_end": data.get("current_period_end"),
                "cancel_at_period_end": data.get("cancel_at_period_end", False),
            }

            if tier == "free":
                result["message"] = (
                    f"Free tier: {result['quota_used']}/{result['quota_limit']} calls this month. "
                    "Use thinkneo_subscribe to upgrade to Pro or Enterprise."
                )
            else:
                result["message"] = (
                    f"{tier.capitalize()} tier: {result['quota_used']}/{result['quota_limit']} calls this month. "
                    f"Billing status: {result['billing_status']}."
                )
                if result["cancel_at_period_end"]:
                    result["message"] += f" Cancellation scheduled — active until {result['current_period_end']}."

            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": "Status unavailable", "detail": str(e)}, indent=2)
