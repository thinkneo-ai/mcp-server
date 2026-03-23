"""
Tool: thinkneo_check_spend
Returns AI spend summary for a workspace, broken down by provider/model/team.
Requires authentication.
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth
from ._common import demo_note, utcnow, validate_workspace


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_check_spend",
        description=(
            "Check AI spend summary for a workspace, team, or project. "
            "Returns cost breakdown by provider, model, and time period. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_check_spend(
        workspace: Annotated[str, Field(description="Workspace name or ID (e.g., 'prod-engineering', 'finance-team')")],
        period: Annotated[str, Field(description="Time period for the report: today, this-week, this-month, last-month, or custom")] = "this-month",
        group_by: Annotated[str, Field(description="Dimension to group costs by: provider, model, team, or project")] = "provider",
        start_date: Annotated[Optional[str], Field(description="Start date for a custom period in ISO format (YYYY-MM-DD). Only used when period='custom'")] = None,
        end_date: Annotated[Optional[str], Field(description="End date for a custom period in ISO format (YYYY-MM-DD). Only used when period='custom'")] = None,
    ) -> str:
        require_auth()
        workspace = validate_workspace(workspace)

        valid_periods = {"today", "this-week", "this-month", "last-month", "custom"}
        if period not in valid_periods:
            period = "this-month"

        valid_group_by = {"provider", "model", "team", "project"}
        if group_by not in valid_group_by:
            group_by = "provider"

        result = {
            "workspace": workspace,
            "period": period,
            "group_by": group_by,
            "total_cost_usd": 0.0,
            "currency": "USD",
            "breakdown": {},
            "top_consumers": [],
            "token_summary": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
            "request_count": 0,
            "avg_cost_per_request_usd": 0.0,
            "cost_trend": "stable",
            "budget_utilization_pct": 0.0,
            "generated_at": utcnow(),
            "dashboard_url": f"https://thinkneo.ai/workspaces/{workspace}/finops",
            "_demo": demo_note(workspace),
        }

        if period == "custom":
            result["period_range"] = {
                "start": start_date or "not-specified",
                "end": end_date or "not-specified",
            }

        return json.dumps(result, indent=2)
