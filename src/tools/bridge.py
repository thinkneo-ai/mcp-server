"""
Tools: MCP <-> A2A Bridge — live brain API.
4 tools: bridge_mcp_to_a2a, bridge_a2a_to_mcp, bridge_generate_agent_card, bridge_list_mappings.
"""
from __future__ import annotations
import json
from typing import Annotated
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from ..auth import require_auth, get_bearer_token
from ..brain_client import brain_get, is_error
from ._common import utcnow


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_bridge_mcp_to_a2a",
        description="Bridge MCP tool registry to A2A format. Shows tool-to-skill mappings.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_bridge_mcp_to_a2a(
        tool_name: Annotated[str, Field(description="MCP tool name to bridge")] = "",
    ) -> str:
        require_auth()
        token = get_bearer_token()
        result = await brain_get("/v1/agents/tools/registry", token=token)
        if is_error(result):
            return json.dumps({"error": result.get("detail"), "generated_at": utcnow()}, indent=2)
        tools = result if isinstance(result, list) else result.get("tools", [])
        if tool_name:
            tools = [t for t in tools if t.get("name") == tool_name]
        mappings = [{"mcp_tool": t.get("name"), "a2a_skill": t.get("name", "").replace("thinkneo_", ""),
                     "category": t.get("category", "general")} for t in tools]
        return json.dumps({"source": "live_gateway", "mappings": mappings, "generated_at": utcnow()}, indent=2)

    @mcp.tool(
        name="thinkneo_bridge_a2a_to_mcp",
        description="Bridge A2A agents to MCP tool format.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_bridge_a2a_to_mcp(
        agent_name: Annotated[str, Field(description="A2A agent name to map")] = "",
    ) -> str:
        require_auth()
        token = get_bearer_token()
        result = await brain_get("/v1/agents/registry", token=token)
        if is_error(result):
            return json.dumps({"error": result.get("detail"), "generated_at": utcnow()}, indent=2)
        agents = result if isinstance(result, list) else result.get("agents", [])
        if agent_name:
            agents = [a for a in agents if a.get("name") == agent_name]
        mappings = [{"a2a_agent": a.get("name"), "mcp_prefix": f"thinkneo_{a.get('name', '').replace('-', '_')}",
                     "skills": a.get("skills", [])} for a in agents]
        return json.dumps({"source": "live_gateway", "mappings": mappings, "generated_at": utcnow()}, indent=2)

    @mcp.tool(
        name="thinkneo_bridge_generate_agent_card",
        description="Generate an A2A Agent Card from registry data.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_bridge_generate_agent_card(
        agent_id: Annotated[str, Field(description="Agent ID from registry")],
    ) -> str:
        require_auth()
        token = get_bearer_token()
        result = await brain_get(f"/v1/agents/registry/{agent_id}", token=token)
        if is_error(result):
            return json.dumps({"error": result.get("detail"), "generated_at": utcnow()}, indent=2)
        card = {"name": result.get("name", agent_id), "description": result.get("description", ""),
                "url": f"https://api.thinkneo.ai/a2a/agents/{agent_id}",
                "version": result.get("version", "1.0.0"),
                "capabilities": {"streaming": False, "pushNotifications": False},
                "skills": result.get("skills", [])}
        return json.dumps({"source": "live_gateway", "agent_card": card, "generated_at": utcnow()}, indent=2)

    @mcp.tool(
        name="thinkneo_bridge_list_mappings",
        description="List all MCP <-> A2A bridge mappings for a tenant.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_bridge_list_mappings() -> str:
        require_auth()
        token = get_bearer_token()
        result = await brain_get("/v1/tenant/agents/tools/registry", token=token)
        if is_error(result):
            return json.dumps({"error": result.get("detail"), "generated_at": utcnow()}, indent=2)
        return json.dumps({"source": "live_gateway", "registry": result, "generated_at": utcnow()}, indent=2)
