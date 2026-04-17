"""
Tool: thinkneo_usage
Returns usage stats for the current API key: calls today/week/month, top tools, estimated cost.
Public tool — works with or without authentication (returns anonymous stats without key).
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..auth import get_bearer_token
from ..database import get_usage_stats, hash_key, ensure_api_key
from ._common import utcnow


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_usage",
        description=(
            "Returns usage statistics for your ThinkNEO API key. "
            "Shows calls today, this week, this month, monthly limit, "
            "remaining calls, top tools used, estimated cost, and current tier. "
            "Works without authentication (returns general info)."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_usage() -> str:
        token = get_bearer_token()

        if not token:
            result = {
                "authenticated": False,
                "tier": "anonymous",
                "message": (
                    "No API key provided. Public tools (provider_status, schedule_demo, "
                    "read_memory, thinkneo_check) are available without authentication. "
                    "For usage tracking and access to all 12 tools, provide an API key."
                ),
                "free_tier": {
                    "monthly_limit": 500,
                    "price": "Free",
                    "features": [
                        "500 tool calls per month",
                        "All 12 tools available",
                        "Usage tracking and stats",
                        "Prompt safety checks",
                    ],
                },
                "tiers": {
                    "free": {"calls": 500, "price": "Free"},

                    "enterprise": {"calls": "Unlimited", "price": "Custom"},
                },
                "docs": "https://mcp.thinkneo.ai/mcp/docs",
                "fetched_at": utcnow(),
            }
            return json.dumps(result, indent=2)

        # Authenticated — get real stats
        key_h = hash_key(token)
        key_info = ensure_api_key(token)
        stats = get_usage_stats(key_h)

        result = {
            "authenticated": True,
            "key_prefix": token[:8] + "...",
            **stats,
            "tiers": {
                "free": {"calls": 500, "price": "Free"},

                "enterprise": {"calls": "Unlimited", "price": "Custom"},
            },
            "fetched_at": utcnow(),
        }

        return json.dumps(result, indent=2)
