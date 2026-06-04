"""
Tool: thinkneo_subscribe — Initiate paid subscription via Stripe Checkout

Auth: Bearer token required (must be free-tier user)
Returns: Stripe Checkout URL to open in browser
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import get_bearer_token

logger = logging.getLogger(__name__)

ADMIN_API_BASE = "http://thinkneo-admin-api:8907"


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_subscribe",
        description=(
            "Subscribe to ThinkNEO MCP Pro ($490/mo) or Enterprise ($4999/mo). "
            "Returns a Stripe Checkout URL — open in browser to complete payment. "
            "Requires free-tier API key. After payment, run thinkneo_status to verify activation."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
    )
    def thinkneo_subscribe(
        plan: Annotated[str, Field(description="Subscription plan: 'pro' ($490/mo) or 'enterprise' ($4999/mo)")],
    ) -> str:
        token = get_bearer_token()
        if not token:
            return json.dumps({"error": "API key required. Configure: Authorization: Bearer <key>"}, indent=2)

        plan = plan.strip().lower()
        if plan == "starter": plan = "pro"  # alias
        if plan not in ("pro", "enterprise"):
            return json.dumps({"error": "plan must be 'pro' or 'enterprise'"}, indent=2)

        try:
            resp = httpx.post(
                f"{ADMIN_API_BASE}/v1/billing/saas/checkout-session",
                headers={"X-API-Key": token, "Content-Type": "application/json"},
                json={"plan": plan},
                timeout=15.0,
            )

            if resp.status_code == 401:
                return json.dumps({"error": "Invalid API key. Sign up first with thinkneo_signup."}, indent=2)
            if resp.status_code == 409:
                return json.dumps({"error": "Already on a paid tier. Use thinkneo_upgrade to change plan."}, indent=2)
            if resp.status_code != 200:
                return json.dumps({"error": f"Subscribe failed (HTTP {resp.status_code})", "detail": resp.text[:200]}, indent=2)

            data = resp.json()
            session = data.get("session") or {}
            checkout_url = session.get("url") or data.get("checkout_url")
            session_id = session.get("id") or data.get("session_id")
            price = "490" if plan == "pro" else "4999"

            return json.dumps({
                "checkout_url": checkout_url,
                "session_id": session_id,
                "plan": plan,
                "message": (
                    f"Open the checkout_url in your browser to complete the ${price}/month subscription. "
                    "After payment, run thinkneo_status to verify activation."
                ),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": "Subscribe unavailable", "detail": str(e)}, indent=2)
