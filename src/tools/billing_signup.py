"""
Tool: thinkneo_signup — MCP A2A self-service onboarding

Behavior (SIGNUP-B idempotent):
- If caller has valid Bearer token: returns current account info (no duplicate creation)
- If no token or invalid token: creates new free-tier account with provided email
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
MCP_SELF_BASE = "http://localhost:8081"


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_signup",
        description=(
            "Sign up for ThinkNEO MCP free tier or retrieve current account if already authenticated. "
            "Idempotent: existing valid token returns current account info, no duplicate created. "
            "After signup, configure your MCP client with: Authorization: Bearer <api_key>"
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True),
    )
    def thinkneo_signup(
        email: Annotated[str, Field(description="Email address for billing notifications and account recovery")],
    ) -> str:
        existing_token = get_bearer_token()

        # SIGNUP-B: if existing valid token, return current account info
        if existing_token:
            try:
                resp = httpx.get(
                    f"{ADMIN_API_BASE}/v1/billing/saas/status",
                    headers={"X-API-Key": existing_token},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return json.dumps({
                        "api_key": existing_token,
                        "tier": data.get("tier", "unknown"),
                        "email": data.get("email"),
                        "message": "Account already exists. Use thinkneo_status for full details.",
                        "is_existing_account": True,
                    }, indent=2)
                # 401 = invalid token → fall through to new signup
            except Exception:
                pass

        # New signup via existing /mcp/signup/submit endpoint
        email = email.strip().lower()
        if not email or "@" not in email:
            return json.dumps({"error": "Valid email address required."}, indent=2)

        try:
            resp = httpx.post(
                f"{MCP_SELF_BASE}/mcp/signup/submit",
                json={"email": email},
                timeout=15.0,
            )
            data = resp.json()

            if data.get("ok"):
                return json.dumps({
                    "api_key": data.get("api_key"),
                    "tier": "free",
                    "email": email,
                    "message": (
                        "Account created! Configure your MCP client with: "
                        "Authorization: Bearer " + str(data.get("api_key", "<key>"))
                    ),
                    "is_existing_account": False,
                    "email_sent": data.get("email_sent", False),
                }, indent=2)
            else:
                return json.dumps({
                    "error": data.get("error", "Signup failed"),
                    "message": "If you already signed up, provide your API key as Authorization: Bearer <key>.",
                }, indent=2)
        except Exception as e:
            return json.dumps({"error": "Signup unavailable", "detail": str(e)}, indent=2)
