"""
Tool: thinkneo_check_spend
Returns AI spend summary from the live brain API gateway.
"""
from __future__ import annotations
import json
from typing import Annotated, Optional
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from ..auth import require_auth, get_bearer_token
from ..brain_client import brain_get, is_error
from ._common import utcnow, validate_workspace

def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_check_spend",
        description=(
            "Check AI spend summary for a workspace, team, or project. "
            "Returns real cost breakdown by provider, model, and time period "
            "from the ThinkNEO AI gateway."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_check_spend(
        workspace: Annotated[str, Field(description="Workspace name or ID")] = "default",
        period: Annotated[str, Field(description="Time period: today, this-week, this-month, last-month")] = "this-month",
        group_by: Annotated[str, Field(description="Group costs by: provider, model, team, or project")] = "provider",
    ) -> str:
        """Check AI spend summary for a workspace, team, or project. Returns cost breakdown by provider, model, and time period."""
        require_auth()
        workspace = validate_workspace(workspace)
        token = get_bearer_token()

        # Try tenant finops showback endpoint first
        params = {}
        if period == "today":
            params["range"] = "1d"
        elif period == "this-week":
            params["range"] = "7d"
        elif period == "last-month":
            params["range"] = "30d"
        else:
            params["range"] = "30d"

        showback = await brain_get("/v1/tenant/finops/showback", params=params, token=token)

        if not is_error(showback):
            return json.dumps({
                "workspace": workspace,
                "period": period,
                "source": "live_gateway",
                "data": showback,
                "generated_at": utcnow(),
                "dashboard_url": f"https://thinkneo.ai/app/dashboard/",
            }, indent=2)

        # Fallback: usage events aggregate
        usage = await brain_get("/v1/tenant/usage-events", params={"limit": "100"}, token=token)

        if not is_error(usage):
            events = usage if isinstance(usage, list) else usage.get("events", usage.get("data", []))
            total_cost = sum(float(e.get("amount_usd", 0) or e.get("cost_usd", 0) or 0) for e in events if isinstance(e, dict))
            total_tokens = sum(int(e.get("total_tokens", 0) or 0) for e in events if isinstance(e, dict))
            return json.dumps({
                "workspace": workspace,
                "period": period,
                "source": "live_gateway",
                "total_cost_usd": round(total_cost, 4),
                "total_tokens": total_tokens,
                "request_count": len(events) if isinstance(events, list) else 0,
                "generated_at": utcnow(),
            }, indent=2)

        # Both failed — return error with context
        return json.dumps({
            "workspace": workspace,
            "period": period,
            "source": "gateway_unavailable",
            "error": showback.get("detail", "Could not reach brain API"),
            "note": "Ensure your API key has tenant access. Contact hello@thinkneo.ai for setup.",
            "generated_at": utcnow(),
        }, indent=2)
