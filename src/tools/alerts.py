"""
Tool: thinkneo_list_alerts
Lists active alerts and incidents for a workspace.
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
        name="thinkneo_list_alerts",
        description=(
            "List active alerts and incidents for a workspace. "
            "Includes budget alerts, policy violations, guardrail triggers, "
            "and provider issues. Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_list_alerts(
        workspace: Annotated[str, Field(description="Workspace name or ID to list active alerts for")],
        severity: Annotated[str, Field(description="Filter alerts by severity level: critical, warning, info, or all")] = "all",
        limit: Annotated[int, Field(description="Maximum number of alerts to return (1–100)", ge=1, le=100)] = 20,
    ) -> str:
        """List active alerts and incidents for a workspace. Includes budget alerts, policy violations, guardrail triggers,"""
        require_auth()
        workspace = validate_workspace(workspace)

        if severity not in ("critical", "warning", "info", "all"):
            severity = "all"

        limit = max(1, min(100, int(limit)))

        result = {
            "workspace": workspace,
            "severity_filter": severity,
            "alerts": [],
            "summary": {
                "total_active": 0,
                "critical": 0,
                "warning": 0,
                "info": 0,
            },
            "returned": 0,
            "limit": limit,
            "fetched_at": utcnow(),
            "alerts_url": f"https://thinkneo.ai/workspaces/{workspace}/alerts",
            "_demo": demo_note(workspace),
        }

        return json.dumps(result, indent=2)
