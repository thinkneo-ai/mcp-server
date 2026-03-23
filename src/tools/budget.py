"""
Tool: thinkneo_get_budget_status
Returns current budget utilization and enforcement status for a workspace.
Requires authentication.
"""

from __future__ import annotations

import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth
from ._common import demo_note, utcnow, validate_workspace


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_get_budget_status",
        description=(
            "Get current budget utilization and enforcement status for a workspace. "
            "Shows spend vs limit, alert thresholds, and projected overage. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    def thinkneo_get_budget_status(
        workspace: Annotated[str, Field(description="Workspace name or ID to retrieve current budget status for")],
    ) -> str:
        require_auth()
        workspace = validate_workspace(workspace)

        result = {
            "workspace": workspace,
            "budget": {
                "period": "this-month",
                "limit_usd": None,
                "spent_usd": 0.0,
                "remaining_usd": None,
                "utilization_pct": 0.0,
                "enforcement_mode": "monitor",
                "status": "under-limit",
            },
            "alerts": {
                "warning_threshold_pct": 80,
                "critical_threshold_pct": 95,
                "current_alert_level": "none",
                "alerts_active": 0,
            },
            "projection": {
                "days_remaining_in_period": 10,
                "projected_month_end_spend_usd": 0.0,
                "projected_overage_usd": 0.0,
                "on_track": True,
            },
            "enforcement": {
                "mode": "monitor",
                "action_on_limit": "alert",
                "hard_stop_enabled": False,
            },
            "evaluated_at": utcnow(),
            "dashboard_url": f"https://thinkneo.ai/workspaces/{workspace}/budget",
            "_demo": demo_note(workspace),
        }

        return json.dumps(result, indent=2)
