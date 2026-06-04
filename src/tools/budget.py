"""
Tool: thinkneo_get_budget_status
Returns budget status from live gateway FinOps endpoints.
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
        name="thinkneo_get_budget_status",
        description="Check AI budget status including spend vs limit, forecast, and chargeback data from the ThinkNEO gateway.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_get_budget_status(
        workspace: Annotated[str, Field(description="Workspace name or ID")] = "default",
    ) -> str:
        """Get current budget utilization and enforcement status for a workspace. Shows spend vs limit, alert thresholds, and projected overage."""
        require_auth()
        workspace = validate_workspace(workspace)
        token = get_bearer_token()

        result = {"workspace": workspace, "source": "live_gateway", "fetched_at": utcnow()}

        showback = await brain_get("/v1/tenant/finops/showback", token=token)
        if not is_error(showback):
            result["showback"] = showback

        chargeback = await brain_get("/v1/tenant/finops/chargeback", token=token)
        if not is_error(chargeback):
            result["chargeback"] = chargeback

        forecast = await brain_get("/v1/tenant/finops/forecast", token=token)
        if not is_error(forecast):
            result["forecast"] = forecast

        if all(is_error(x) for x in [showback, chargeback, forecast]):
            result["error"] = "Could not reach FinOps endpoints"

        return json.dumps(result, indent=2)
