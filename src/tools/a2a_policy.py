"""
Tool: thinkneo_a2a_policy — live brain API.
Retrieves A2A policies from the optimization engine.
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
        name="thinkneo_a2a_policy",
        description=(
            "Retrieve A2A interaction policies from the live gateway. "
            "Shows allowed actions, rate limits, cost caps, and approval requirements."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_a2a_policy(
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
    ) -> str:
        require_auth()
        workspace = validate_workspace(workspace)
        token = get_bearer_token()
        result = await brain_get("/v1/optimization/policies", token=token)
        if is_error(result):
            return json.dumps({"error": result.get("detail"), "workspace": workspace,
                               "generated_at": utcnow()}, indent=2)
        policies = result if isinstance(result, list) else result.get("policies", [])
        a2a = [p for p in policies if "a2a" in str(p.get("type", "")).lower()
               or "agent" in str(p.get("type", "")).lower()]
        return json.dumps({"source": "live_gateway", "workspace": workspace,
                           "total_policies": len(a2a), "policies": a2a,
                           "generated_at": utcnow()}, indent=2)
