"""
Tool: thinkneo_a2a_log — live brain API.
Retrieves A2A interaction audit events from the gateway.
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
        name="thinkneo_a2a_log",
        description=(
            "Retrieve A2A (agent-to-agent) interaction logs from the live gateway. "
            "Shows which agents called which, actions performed, costs, and outcomes."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_a2a_log(
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
        limit: Annotated[int, Field(description="Max events to return")] = 50,
    ) -> str:
        require_auth()
        workspace = validate_workspace(workspace)
        token = get_bearer_token()
        params = {"limit": str(min(limit, 200)), "type": "a2a"}
        result = await brain_get("/v1/tenant/audit-events", params=params, token=token)
        if is_error(result):
            return json.dumps({"error": result.get("detail"), "workspace": workspace,
                               "generated_at": utcnow()}, indent=2)
        events = result if isinstance(result, list) else result.get("events", result.get("data", []))
        return json.dumps({"source": "live_gateway", "workspace": workspace,
                           "total_events": len(events), "events": events[:limit],
                           "generated_at": utcnow()}, indent=2)
