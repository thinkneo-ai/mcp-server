"""
Tool: thinkneo_cancel — Cancel subscription at period end

Auth: Bearer token required
Uses: POST /v1/billing/saas/cancel
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
        name="thinkneo_cancel",
        description=(
            "Cancel ThinkNEO MCP subscription at the end of the current billing period. "
            "Subscription remains active until period end, then reverts to free tier. "
            "Requires API key with active paid subscription."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True),
    )
    def thinkneo_cancel() -> str:
        token = get_bearer_token()
        if not token:
            return json.dumps({"error": "API key required. Configure: Authorization: Bearer <key>"}, indent=2)

        # Enterprise keys dont have Stripe subscriptions
        if is_authenticated():
            return json.dumps({
                "status": "not_applicable",
                "message": "Enterprise accounts are managed directly. Contact hello@thinkneo.ai for changes.",
                "tier": "enterprise",
            }, indent=2)

        try:
            resp = httpx.post(
                f"{ADMIN_API_BASE}/v1/billing/saas/cancel",
                headers={"X-API-Key": token, "Content-Type": "application/json"},
                json={},
                timeout=15.0,
            )

            if resp.status_code == 401:
                return json.dumps({"error": "Invalid API key."}, indent=2)
            if resp.status_code == 400:
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                return json.dumps({"error": data.get("error", "No active subscription to cancel.")}, indent=2)
            if resp.status_code != 200:
                return json.dumps({"error": f"Cancellation failed (HTTP {resp.status_code})", "detail": resp.text[:200]}, indent=2)

            data = resp.json()
            return json.dumps({
                "status": "cancelled",
                "message": "Subscription will end at the current billing period. You retain access until then.",
                "cancel_at_period_end": True,
                "current_period_end": data.get("current_period_end"),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": "Cancellation failed", "detail": str(e)}, indent=2)
