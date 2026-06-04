"""
Tool: thinkneo_upgrade — Change subscription plan

Auth: Bearer token required
Uses: POST /v1/billing/saas/upgrade
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
        name="thinkneo_upgrade",
        description=(
            "Upgrade ThinkNEO MCP subscription. "
            "Free → Pro/Enterprise: creates new Stripe Checkout session. "
            "Pro → Enterprise: in-place upgrade with proration. "
            "Requires API key."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
    )
    def thinkneo_upgrade(
        new_plan: Annotated[str, Field(description="Target plan: 'pro' ($490/mo) or 'enterprise' ($4999/mo)")],
    ) -> str:
        token = get_bearer_token()
        if not token:
            return json.dumps({"error": "API key required. Configure: Authorization: Bearer <key>"}, indent=2)

        new_plan = new_plan.strip().lower()
        if new_plan not in ("pro", "enterprise"):
            return json.dumps({"error": "new_plan must be 'pro' or 'enterprise'"}, indent=2)

        try:
            resp = httpx.post(
                f"{ADMIN_API_BASE}/v1/billing/saas/upgrade",
                headers={"X-API-Key": token, "Content-Type": "application/json"},
                json={"new_plan": new_plan},
                timeout=15.0,
            )

            if resp.status_code == 401:
                return json.dumps({"error": "Invalid API key."}, indent=2)
            if resp.status_code == 409:
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                return json.dumps({"error": data.get("detail", "Already on this tier.")}, indent=2)
            if resp.status_code == 400:
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                return json.dumps({"error": data.get("detail", "Upgrade not possible.")}, indent=2)
            if resp.status_code != 200:
                return json.dumps({"error": f"Upgrade failed (HTTP {resp.status_code})", "detail": resp.text[:200]}, indent=2)

            data = resp.json()
            action = data.get("action", "unknown")

            if action == "checkout_created":
                session = data.get("session") or {}
                return json.dumps({
                    "action": "checkout_created",
                    "checkout_url": session.get("url"),
                    "session_id": session.get("id"),
                    "message": f"Open the checkout_url in your browser to upgrade to {new_plan}. After payment, run thinkneo_billing_status to verify.",
                }, indent=2)
            elif action == "subscription_modified":
                return json.dumps({
                    "action": "subscription_modified",
                    "subscription_id": data.get("subscription_id"),
                    "new_plan": new_plan,
                    "message": data.get("message", f"Upgraded to {new_plan} with proration."),
                }, indent=2)
            else:
                return json.dumps(data, indent=2)
        except Exception as e:
            return json.dumps({"error": "Upgrade unavailable", "detail": str(e)}, indent=2)
