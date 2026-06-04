"""
Tool: thinkneo_a2a_flow — live brain API.
Retrieves A2A agent flow data (registry + approvals).
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
        name="thinkneo_a2a_flow",
        description=(
            "Visualize agent-to-agent communication flow. Shows registered agents, "
            "their approval status, and interaction patterns from the live gateway."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_a2a_flow(
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
    ) -> str:
        require_auth()
        workspace = validate_workspace(workspace)
        token = get_bearer_token()
        registry = await brain_get("/v1/tenant/agents/registry", token=token)
        approvals = await brain_get("/v1/tenant/agents/approvals", token=token)
        flow = {"source": "live_gateway", "workspace": workspace, "generated_at": utcnow()}
        if not is_error(registry):
            agents = registry if isinstance(registry, list) else registry.get("agents", [])
            flow["agents"] = agents
            flow["agent_count"] = len(agents)
        if not is_error(approvals):
            flow["approvals"] = approvals
        if is_error(registry) and is_error(approvals):
            flow["error"] = "Could not reach gateway"
            flow["detail"] = registry.get("detail", "")
        return json.dumps(flow, indent=2)
