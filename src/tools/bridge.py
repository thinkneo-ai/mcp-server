"""
Tools: MCP ↔ A2A Bridge
Four bridge tools that translate between MCP and A2A protocols.
All require authentication (Pro plan).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..a2a_bridge import (
    bridge_a2a_to_mcp,
    bridge_mcp_to_a2a,
    generate_agent_card_from_tools,
    generate_thinkneo_agent_card,
    get_active_mappings,
    get_translation_stats,
)
from ..auth import require_auth
from ._common import utcnow

logger = logging.getLogger(__name__)


def register(mcp: FastMCP) -> None:
    # -----------------------------------------------------------------------
    # Tool 1: MCP → A2A Bridge
    # -----------------------------------------------------------------------
    @mcp.tool(
        name="thinkneo_bridge_mcp_to_a2a",
        description=(
            "Bridge an MCP tool call to an A2A (Agent-to-Agent Protocol) agent. Maps MCP tool name and parameters to the A2A task format, enabling interoperability between MCP servers and A2A agents. Returns a ready-to-send A2A task object with full protocol compliance. "
            "Translates the MCP tool_name and arguments into an A2A task, sends it "
            "to the target A2A agent, waits for completion, and translates the response "
            "back to MCP format. Use this to make any MCP tool accessible to A2A agents "
            "(Google's agent ecosystem). Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False),
    )
    def thinkneo_bridge_mcp_to_a2a(
        mcp_tool_name: Annotated[
            str,
            Field(description="Name of the MCP tool to bridge (e.g. 'thinkneo_check_spend')"),
        ],
        arguments: Annotated[
            str,
            Field(
                description=(
                    "JSON string of arguments to pass to the MCP tool "
                    "(e.g. '{\"workspace\": \"prod\", \"period\": \"this-month\"}')"
                )
            ),
        ] = "{}",
        target_a2a_agent_url: Annotated[
            str,
            Field(
                description=(
                    "URL of the target A2A agent endpoint "
                    "(e.g. 'https://agent.thinkneo.ai/a2a'). "
                    "Defaults to ThinkNEO's own A2A agent."
                )
            ),
        ] = "https://agent.thinkneo.ai/a2a",
    ) -> str:
        """Bridge an MCP tool call to an A2A (Agent-to-Agent Protocol) agent. Maps MCP tool name and parameters to the A2A task format, enabling interoperability between MCP servers and A2A agents. Returns a ready-to-send A2A task object with full protocol compliance. Translates the MCP tool_name and arguments into an A2A task, sends it to the target A2A agent, waits for completion, and translates the response back to MCP format. Use this to make any MCP tool accessible to A2A agents"""
        require_auth()

        # Parse arguments
        try:
            args_dict = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError:
            return json.dumps(
                {
                    "error": "Invalid JSON in 'arguments' parameter",
                    "hint": "Provide a valid JSON object string",
                    "generated_at": utcnow(),
                },
                indent=2,
            )

        # Validate inputs
        if not mcp_tool_name or not isinstance(mcp_tool_name, str):
            return json.dumps(
                {"error": "mcp_tool_name is required", "generated_at": utcnow()},
                indent=2,
            )

        # Run the async bridge
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        lambda: asyncio.run(
                            bridge_mcp_to_a2a(mcp_tool_name, args_dict, target_a2a_agent_url)
                        )
                    ).result(timeout=35)
            else:
                result = asyncio.run(
                    bridge_mcp_to_a2a(mcp_tool_name, args_dict, target_a2a_agent_url)
                )
        except Exception as exc:
            result = {
                "error": f"Bridge execution failed: {str(exc)[:300]}",
                "generated_at": utcnow(),
            }

        result["generated_at"] = utcnow()
        return json.dumps(result, indent=2, default=str)

    # -----------------------------------------------------------------------
    # Tool 2: A2A → MCP Bridge
    # -----------------------------------------------------------------------
    @mcp.tool(
        name="thinkneo_bridge_a2a_to_mcp",
        description=(
            "Bridge an A2A (Agent-to-Agent Protocol) task to an MCP server. Receives an A2A task, identifies the best matching MCP tool on the target server, executes it, and returns the result wrapped in A2A response format. Enables A2A agents to use any MCP server transparently. "
            "Extracts the intent from the A2A task, maps it to an MCP tool, "
            "calls the tool, and wraps the result in A2A response format. "
            "Use this to let A2A agents interact with any MCP server. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False),
    )
    def thinkneo_bridge_a2a_to_mcp(
        a2a_task: Annotated[
            str,
            Field(
                description=(
                    "JSON string of the A2A task object. Must include at minimum a "
                    "'message' field with 'parts'. Example: "
                    "'{\"id\": \"task-1\", \"message\": {\"role\": \"user\", "
                    "\"parts\": [{\"type\": \"text\", \"text\": \"Check provider status\"}]}}'"
                )
            ),
        ],
        target_mcp_server_url: Annotated[
            str,
            Field(
                description=(
                    "URL of the target MCP server endpoint "
                    "(e.g. 'https://mcp.thinkneo.ai/mcp'). "
                    "Defaults to ThinkNEO's own MCP server."
                )
            ),
        ] = "https://mcp.thinkneo.ai/mcp",
    ) -> str:
        """Bridge an A2A (Agent-to-Agent Protocol) task to an MCP server. Receives an A2A task, identifies the best matching MCP tool on the target server, executes it, and returns the result wrapped in A2A response format. Enables A2A agents to use any MCP server transparently. Extracts the intent from the A2A task, maps it to an MCP tool, calls the tool, and wraps the result in A2A response format. Use this to let A2A agents interact with any MCP server."""
        require_auth()

        # Parse the A2A task
        try:
            task_dict = json.loads(a2a_task) if isinstance(a2a_task, str) else a2a_task
        except json.JSONDecodeError:
            return json.dumps(
                {
                    "error": "Invalid JSON in 'a2a_task' parameter",
                    "hint": "Provide a valid A2A task JSON object",
                    "generated_at": utcnow(),
                },
                indent=2,
            )

        if not isinstance(task_dict, dict):
            return json.dumps(
                {"error": "a2a_task must be a JSON object", "generated_at": utcnow()},
                indent=2,
            )

        # Run the async bridge
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        lambda: asyncio.run(
                            bridge_a2a_to_mcp(task_dict, target_mcp_server_url)
                        )
                    ).result(timeout=35)
            else:
                result = asyncio.run(
                    bridge_a2a_to_mcp(task_dict, target_mcp_server_url)
                )
        except Exception as exc:
            result = {
                "error": f"Bridge execution failed: {str(exc)[:300]}",
                "generated_at": utcnow(),
            }

        result["generated_at"] = utcnow()
        return json.dumps(result, indent=2, default=str)

    # -----------------------------------------------------------------------
    # Tool 3: Generate Agent Card
    # -----------------------------------------------------------------------
    @mcp.tool(
        name="thinkneo_bridge_generate_agent_card",
        description=(
            "Auto-generate an A2A Agent Card from an MCP server's tool list. "
            "Each MCP tool is converted into an A2A skill. The resulting agent.json "
            "makes the MCP server discoverable by any A2A-compatible agent in "
            "Google's agent ecosystem. Defaults to ThinkNEO's own MCP server. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
    )
    def thinkneo_bridge_generate_agent_card(
        mcp_server_url: Annotated[
            Optional[str],
            Field(
                description=(
                    "URL of the MCP server to generate an agent card for. "
                    "Defaults to ThinkNEO's own server (https://mcp.thinkneo.ai/mcp). "
                    "The server must support the tools/list method."
                )
            ),
        ] = None,
    ) -> str:
        """Auto-generate an A2A Agent Card from an MCP server's tool list. Each MCP tool is converted into an A2A skill. The resulting agent.json makes the MCP server discoverable by any A2A-compatible agent in Google's agent ecosystem. Defaults to ThinkNEO's own MCP server."""
        require_auth()

        # Default: generate ThinkNEO's own agent card
        if not mcp_server_url or mcp_server_url == "https://mcp.thinkneo.ai/mcp":
            agent_card = generate_thinkneo_agent_card()
            return json.dumps(
                {
                    "agent_card": agent_card,
                    "skills_count": len(agent_card.get("skills", [])),
                    "deploy_at": "https://mcp.thinkneo.ai/.well-known/agent.json",
                    "source": "thinkneo_builtin",
                    "generated_at": utcnow(),
                },
                indent=2,
                default=str,
            )

        # External MCP server: call tools/list to discover tools
        try:
            import httpx

            tools_list_request = {
                "jsonrpc": "2.0",
                "id": "bridge-discovery-1",
                "method": "tools/list",
                "params": {},
            }

            with httpx.Client(timeout=15) as client:
                resp = client.post(
                    mcp_server_url,
                    json=tools_list_request,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()

            # Extract tools from response
            tools = []
            result = data.get("result", {})
            if isinstance(result, dict):
                tools = result.get("tools", [])
            elif isinstance(result, list):
                tools = result

            if not tools:
                return json.dumps(
                    {
                        "error": "No tools found on the MCP server",
                        "mcp_server_url": mcp_server_url,
                        "raw_response": data,
                        "generated_at": utcnow(),
                    },
                    indent=2,
                    default=str,
                )

            # Parse server name from URL
            from urllib.parse import urlparse
            parsed = urlparse(mcp_server_url)
            server_name = parsed.hostname or "Unknown MCP Server"

            agent_card = generate_agent_card_from_tools(
                tools=tools,
                server_name=server_name,
                server_url=f"{parsed.scheme}://{parsed.netloc}",
            )

            return json.dumps(
                {
                    "agent_card": agent_card,
                    "skills_count": len(agent_card.get("skills", [])),
                    "source_tools_count": len(tools),
                    "source_mcp_server": mcp_server_url,
                    "generated_at": utcnow(),
                },
                indent=2,
                default=str,
            )

        except Exception as exc:
            return json.dumps(
                {
                    "error": f"Failed to generate agent card: {str(exc)[:300]}",
                    "mcp_server_url": mcp_server_url,
                    "generated_at": utcnow(),
                },
                indent=2,
            )

    # -----------------------------------------------------------------------
    # Tool 4: List Bridge Mappings
    # -----------------------------------------------------------------------
    @mcp.tool(
        name="thinkneo_bridge_list_mappings",
        description=(
            "List all active MCP ↔ A2A bridge mappings and translation statistics. "
            "Shows which MCP servers are mapped to which A2A agents, plus "
            "30-day translation stats (total, success rate, average latency). "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_bridge_list_mappings() -> str:
        """List all active MCP ↔ A2A bridge mappings and translation statistics. Shows which MCP servers are mapped to which A2A agents, plus 30-day translation stats (total, success rate, average latency)."""
        require_auth()

        mappings = get_active_mappings()
        stats = get_translation_stats()

        result = {
            "active_mappings": mappings,
            "mappings_count": len(mappings),
            "translation_stats_30d": stats,
            "bridge_version": "1.0.0",
            "supported_protocols": {
                "mcp": {"version": "2025-03-26", "transport": "streamable-http"},
                "a2a": {"version": "0.3.0", "transport": "jsonrpc"},
            },
            "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
            "generated_at": utcnow(),
        }

        return json.dumps(result, indent=2, default=str)
