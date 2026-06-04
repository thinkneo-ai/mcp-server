"""
Tool: thinkneo_list_alerts
Returns alerts from the live brain API.
"""
from __future__ import annotations
import json
from typing import Annotated
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from ..auth import require_auth, get_bearer_token
from ..brain_client import brain_get, is_error
from ._common import utcnow, validate_workspace

def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_list_alerts",
        description="List active alerts for budget, policy, SLA, and security from the ThinkNEO gateway.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_list_alerts(
        workspace: Annotated[str, Field(description="Workspace name or ID")] = "default",
        severity: Annotated[str, Field(description="Filter by severity: critical, high, medium, low, all")] = "all",
    ) -> str:
        """List active alerts and incidents for a workspace. Includes budget alerts, policy violations, guardrail triggers,"""
        require_auth()
        workspace = validate_workspace(workspace)
        token = get_bearer_token()

        result = {"workspace": workspace, "severity_filter": severity, "source": "live_gateway", "fetched_at": utcnow()}

        metrics = await brain_get("/v1/internal/runtime-metrics", token=token)
        if not is_error(metrics):
            rm = metrics.get("runtime_metrics", metrics)
            alerts = []
            if rm.get("finops_alerts_total", 0) > 0:
                for alert_type, count in rm.get("finops_alerts_by_type", {}).items():
                    alerts.append({"type": "finops", "subtype": alert_type, "count": count, "severity": "high"})
            if rm.get("guardrails_blocked_total", 0) > 0:
                alerts.append({"type": "guardrails", "blocked": rm["guardrails_blocked_total"], "severity": "critical"})
            if rm.get("data_security_blocked_total", 0) > 0:
                alerts.append({"type": "data_security", "blocked": rm["data_security_blocked_total"], "severity": "critical"})
            if rm.get("gateway_rate_limit_blocked", 0) > 0:
                alerts.append({"type": "rate_limit", "blocked": rm["gateway_rate_limit_blocked"], "severity": "medium"})
            if rm.get("agent_runtime_enforcement_blocked_total", 0) > 0:
                alerts.append({"type": "agent_governance", "blocked": rm["agent_runtime_enforcement_blocked_total"], "severity": "high"})
            result["alerts"] = alerts
            result["total_alerts"] = len(alerts)
            result["gateway_status"] = "operational"
        else:
            result["error"] = "Could not reach gateway"

        return json.dumps(result, indent=2)
