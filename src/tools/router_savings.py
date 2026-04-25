"""
Tool: thinkneo_get_savings_report
Returns savings report showing how much money Smart Router has saved.
Requires authentication.
"""

from __future__ import annotations

import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth
from ..database import hash_key
from ..smart_router import get_savings_report
from ._common import utcnow


_PERIOD_TO_DAYS = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
}


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_get_savings_report",
        description=(
            "Get your AI cost savings report. Shows total requests routed, original cost "
            "(what you'd have paid with premium models), actual cost, total savings, "
            "savings percentage, breakdown by task type, and model distribution. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_get_savings_report(
        period: Annotated[str, Field(
            description="Report period: '7d' (7 days), '30d' (30 days), or '90d' (90 days)"
        )] = "30d",
    ) -> str:
        token = require_auth()
        key_h = hash_key(token)

        days = _PERIOD_TO_DAYS.get(period, 30)

        report = get_savings_report(key_h, days)

        # Add metadata
        report["period"] = period
        report["generated_at"] = utcnow()
        report["dashboard_url"] = "https://thinkneo.ai/dashboard/savings"
        report["note"] = (
            "Savings are calculated by comparing the cost of the model actually used "
            "vs the premium reference model (Claude Opus 4 / GPT-4o) for each task type. "
            "Use thinkneo_route_model on every AI call to maximize savings."
        )

        return json.dumps(report, indent=2, default=str)
