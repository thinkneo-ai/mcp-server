"""
MCP ↔ A2A Bridge Engine — ThinkNEO Universal Protocol Translator

Translates between MCP (Model Context Protocol) tool calls and A2A
(Agent-to-Agent Protocol) tasks, enabling interoperability between
the two dominant AI agent communication standards.

MCP → A2A: Converts tool_name + arguments into an A2A task/send request
A2A → MCP: Converts an A2A task into an MCP tools/call request
Agent Card: Auto-generates an A2A Agent Card from MCP tools/list
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from .database import _get_conn

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

A2A_PROTOCOL_VERSION = "0.3.0"
MCP_JSONRPC_VERSION = "2.0"
BRIDGE_TIMEOUT = 30  # seconds for outbound requests
THINKNEO_MCP_URL = "https://mcp.thinkneo.ai/mcp"
THINKNEO_A2A_URL = "https://agent.thinkneo.ai/a2a"


# ---------------------------------------------------------------------------
# Translation logging
# ---------------------------------------------------------------------------

def _log_translation(
    source_protocol: str,
    target_protocol: str,
    source_request: dict,
    translated_request: dict,
    response: Optional[dict],
    latency_ms: int,
    success: bool,
    error_message: Optional[str] = None,
) -> None:
    """Persist a translation record to the bridge_translations table."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO bridge_translations
                        (source_protocol, target_protocol, source_request,
                         translated_request, response, latency_ms, success, error_message)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        source_protocol,
                        target_protocol,
                        json.dumps(source_request, default=str),
                        json.dumps(translated_request, default=str),
                        json.dumps(response, default=str) if response else None,
                        latency_ms,
                        success,
                        error_message,
                    ),
                )
    except Exception as exc:
        logger.warning("Failed to log bridge translation: %s", exc)


# ---------------------------------------------------------------------------
# MCP → A2A Translation
# ---------------------------------------------------------------------------

def mcp_tool_to_a2a_message(tool_name: str, arguments: dict) -> dict:
    """
    Convert an MCP tool call into an A2A-compatible message.

    The tool_name becomes a directive, and the arguments are serialized as
    a structured JSON message part within the A2A task.
    """
    # Build a natural-language representation + structured data
    text_content = f"Execute tool: {tool_name}"
    if arguments:
        text_content += f"\nArguments: {json.dumps(arguments, indent=2, default=str)}"

    message = {
        "role": "user",
        "parts": [
            {
                "type": "text",
                "text": text_content,
            },
            {
                "type": "data",
                "mimeType": "application/json",
                "data": {
                    "bridge_source": "mcp",
                    "tool_name": tool_name,
                    "arguments": arguments,
                },
            },
        ],
    }
    return message


def translate_mcp_to_a2a(tool_name: str, arguments: dict, task_id: Optional[str] = None) -> dict:
    """
    Translate an MCP tools/call request into a full A2A tasks/send JSON-RPC request.

    Returns the JSON-RPC request body ready to POST to an A2A agent.
    """
    if not task_id:
        task_id = str(uuid.uuid4())

    message = mcp_tool_to_a2a_message(tool_name, arguments)

    a2a_request = {
        "jsonrpc": MCP_JSONRPC_VERSION,
        "id": str(uuid.uuid4()),
        "method": "tasks/send",
        "params": {
            "id": task_id,
            "message": message,
        },
    }
    return a2a_request


def translate_a2a_response_to_mcp(a2a_response: dict) -> dict:
    """
    Convert an A2A task response back into MCP tool result format.

    Extracts text/data artifacts from the A2A response and wraps them
    as an MCP content result.
    """
    result = a2a_response.get("result", {})

    # The A2A response should contain a task with status and artifacts
    task_status = "unknown"
    content_parts = []
    raw_artifacts = []

    if isinstance(result, dict):
        status_obj = result.get("status", {})
        task_status = status_obj.get("state", "unknown") if isinstance(status_obj, dict) else str(status_obj)

        # Extract artifacts (may be None in some A2A responses)
        artifacts = result.get("artifacts") or []
        for artifact in artifacts:
            if isinstance(artifact, dict):
                raw_artifacts.append(artifact)
                parts = artifact.get("parts", [])
                for part in parts:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            content_parts.append(part.get("text", ""))
                        elif part.get("type") == "data":
                            content_parts.append(
                                json.dumps(part.get("data", {}), indent=2, default=str)
                            )

        # Also check for message in history (may be None)
        history = result.get("history") or []
        if not content_parts and history:
            for msg in history:
                if isinstance(msg, dict) and msg.get("role") == "agent":
                    for part in msg.get("parts") or []:
                        if isinstance(part, dict) and part.get("type") == "text":
                            content_parts.append(part.get("text", ""))

        # Also check status.message for content (common in failed/completed tasks)
        if not content_parts:
            status_msg = status_obj.get("message", {}) if isinstance(status_obj, dict) else {}
            if isinstance(status_msg, dict) and status_msg.get("role") == "agent":
                for part in status_msg.get("parts") or []:
                    if isinstance(part, dict) and part.get("type") == "text":
                        content_parts.append(part.get("text", ""))

    # Build MCP-style result
    mcp_result = {
        "bridge_source": "a2a",
        "task_status": task_status,
        "content": "\n".join(content_parts) if content_parts else "No content returned from A2A agent.",
        "artifacts_count": len(raw_artifacts),
    }

    return mcp_result


async def bridge_mcp_to_a2a(
    tool_name: str,
    arguments: dict,
    target_a2a_url: str,
    auth_token: Optional[str] = None,
) -> dict:
    """
    Full bridge: MCP tool call → A2A task/send → wait for response → translate back.

    Returns a dict with 'result' and 'translation_metadata'.
    """
    start = time.monotonic()
    a2a_request = translate_mcp_to_a2a(tool_name, arguments)
    task_id = a2a_request["params"]["id"]

    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    response_data = None
    error_msg = None
    success = False

    try:
        async with httpx.AsyncClient(timeout=BRIDGE_TIMEOUT) as client:
            # Send the task
            resp = await client.post(
                target_a2a_url,
                json=a2a_request,
                headers=headers,
            )
            resp.raise_for_status()
            response_data = resp.json()

            # Check if the task is completed or still working
            result = response_data.get("result", {})
            task_state = "unknown"
            if isinstance(result, dict):
                status = result.get("status", {})
                task_state = status.get("state", "unknown") if isinstance(status, dict) else str(status)

            # If the task is still working, poll for completion
            if task_state in ("working", "submitted"):
                get_request = {
                    "jsonrpc": MCP_JSONRPC_VERSION,
                    "id": str(uuid.uuid4()),
                    "method": "tasks/get",
                    "params": {"id": task_id},
                }

                # Poll up to 10 times with 1s intervals
                for _ in range(10):
                    await _async_sleep(1.0)
                    poll_resp = await client.post(
                        target_a2a_url,
                        json=get_request,
                        headers=headers,
                    )
                    poll_resp.raise_for_status()
                    response_data = poll_resp.json()
                    poll_result = response_data.get("result", {})
                    if isinstance(poll_result, dict):
                        poll_status = poll_result.get("status", {})
                        task_state = poll_status.get("state", "unknown") if isinstance(poll_status, dict) else str(poll_status)
                        if task_state in ("completed", "failed", "canceled"):
                            break

            # Translate A2A response → MCP result
            mcp_result = translate_a2a_response_to_mcp(response_data)
            success = True

    except httpx.HTTPStatusError as exc:
        error_msg = f"A2A agent returned HTTP {exc.response.status_code}: {exc.response.text[:500]}"
        mcp_result = {"error": error_msg}
    except httpx.RequestError as exc:
        error_msg = f"Failed to reach A2A agent at {target_a2a_url}: {str(exc)[:300]}"
        mcp_result = {"error": error_msg}
    except Exception as exc:
        error_msg = f"Bridge translation error: {str(exc)[:300]}"
        mcp_result = {"error": error_msg}

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Log the translation
    _log_translation(
        source_protocol="mcp",
        target_protocol="a2a",
        source_request={"tool_name": tool_name, "arguments": arguments},
        translated_request=a2a_request,
        response=response_data,
        latency_ms=elapsed_ms,
        success=success,
        error_message=error_msg,
    )

    return {
        "result": mcp_result,
        "translation_metadata": {
            "direction": "mcp_to_a2a",
            "source_tool": tool_name,
            "target_agent_url": target_a2a_url,
            "task_id": task_id,
            "latency_ms": elapsed_ms,
            "success": success,
            "error": error_msg,
        },
    }


# ---------------------------------------------------------------------------
# A2A → MCP Translation
# ---------------------------------------------------------------------------

def translate_a2a_to_mcp(a2a_task: dict) -> dict:
    """
    Translate an A2A task into an MCP tools/call JSON-RPC request.

    Extracts the intent from the A2A task message and maps it to
    an MCP tool name + arguments.
    """
    # Extract the message from the task
    message = a2a_task.get("message", {})
    parts = message.get("parts", []) if isinstance(message, dict) else []

    tool_name = None
    arguments = {}
    raw_text = ""

    for part in parts:
        if not isinstance(part, dict):
            continue

        # Check for structured bridge data first
        if part.get("type") == "data":
            data = part.get("data", {})
            if isinstance(data, dict) and data.get("bridge_source") == "mcp":
                tool_name = data.get("tool_name")
                arguments = data.get("arguments", {})
                break

        # Fall back to text extraction
        if part.get("type") == "text":
            raw_text += part.get("text", "") + "\n"

    # If no structured data, try to extract tool info from text
    if not tool_name and raw_text:
        tool_name, arguments = _extract_tool_from_text(raw_text)

    if not tool_name:
        tool_name = "thinkneo_provider_status"  # safe default
        arguments = {}

    mcp_request = {
        "jsonrpc": MCP_JSONRPC_VERSION,
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    return mcp_request


def _extract_tool_from_text(text: str) -> tuple[Optional[str], dict]:
    """
    Best-effort extraction of MCP tool name and arguments from A2A message text.

    Looks for patterns like "Execute tool: tool_name" or tries to match
    keywords to known ThinkNEO tools.
    """
    import re

    # Pattern 1: "Execute tool: <tool_name>"
    match = re.search(r"Execute tool:\s*(\w+)", text, re.IGNORECASE)
    if match:
        tool_name = match.group(1)
        # Try to extract arguments from JSON block
        args_match = re.search(r"Arguments:\s*(\{.*?\})", text, re.DOTALL)
        arguments = {}
        if args_match:
            try:
                arguments = json.loads(args_match.group(1))
            except json.JSONDecodeError:
                pass
        return tool_name, arguments

    # Pattern 2: Keyword matching to known tools
    text_lower = text.lower()
    keyword_map = {
        "spend": ("thinkneo_check_spend", {"workspace": "default", "period": "this-month"}),
        "cost": ("thinkneo_check_spend", {"workspace": "default", "period": "this-month"}),
        "guardrail": ("thinkneo_evaluate_guardrail", {"workspace": "default", "prompt": text[:500]}),
        "safety": ("thinkneo_check", {"prompt": text[:500]}),
        "injection": ("thinkneo_check", {"prompt": text[:500]}),
        "policy": ("thinkneo_check_policy", {"workspace": "default"}),
        "budget": ("thinkneo_get_budget_status", {"workspace": "default"}),
        "compliance": ("thinkneo_get_compliance_status", {"workspace": "default"}),
        "alert": ("thinkneo_list_alerts", {"workspace": "default"}),
        "provider": ("thinkneo_provider_status", {}),
        "status": ("thinkneo_provider_status", {}),
        "demo": ("thinkneo_schedule_demo", {}),
        "usage": ("thinkneo_usage", {}),
    }

    for keyword, (tool, args) in keyword_map.items():
        if keyword in text_lower:
            return tool, args

    return None, {}


def wrap_mcp_result_as_a2a_response(
    task_id: str,
    mcp_result: str,
    original_method: str = "tasks/send",
) -> dict:
    """
    Wrap an MCP tool result as a valid A2A task response.
    """
    # Parse MCP result if it's JSON
    content_text = mcp_result
    try:
        parsed = json.loads(mcp_result)
        if isinstance(parsed, dict):
            content_text = json.dumps(parsed, indent=2, default=str)
    except (json.JSONDecodeError, TypeError):
        pass

    task = {
        "id": task_id,
        "status": {
            "state": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        "artifacts": [
            {
                "parts": [
                    {
                        "type": "text",
                        "text": content_text,
                    },
                    {
                        "type": "data",
                        "mimeType": "application/json",
                        "data": {
                            "bridge_source": "mcp",
                            "original_tool_result": content_text,
                        },
                    },
                ],
            }
        ],
    }

    return {
        "jsonrpc": MCP_JSONRPC_VERSION,
        "id": str(uuid.uuid4()),
        "result": task,
    }


async def bridge_a2a_to_mcp(
    a2a_task: dict,
    target_mcp_url: str,
    auth_token: Optional[str] = None,
) -> dict:
    """
    Full bridge: A2A task → MCP tools/call → wait for response → wrap as A2A response.

    Returns an A2A-formatted response.
    """
    start = time.monotonic()
    mcp_request = translate_a2a_to_mcp(a2a_task)
    task_id = a2a_task.get("id", str(uuid.uuid4()))

    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    response_data = None
    error_msg = None
    success = False
    a2a_response = None

    try:
        async with httpx.AsyncClient(timeout=BRIDGE_TIMEOUT) as client:
            resp = await client.post(
                target_mcp_url,
                json=mcp_request,
                headers=headers,
            )
            resp.raise_for_status()
            response_data = resp.json()

            # Extract the tool result from MCP response
            mcp_result_content = ""
            if isinstance(response_data, dict):
                result = response_data.get("result", {})
                if isinstance(result, dict):
                    content = result.get("content", [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                mcp_result_content += item.get("text", "")
                    elif isinstance(content, str):
                        mcp_result_content = content
                elif isinstance(result, str):
                    mcp_result_content = result

            if not mcp_result_content:
                mcp_result_content = json.dumps(response_data, indent=2, default=str)

            # Wrap as A2A response
            a2a_response = wrap_mcp_result_as_a2a_response(task_id, mcp_result_content)
            success = True

    except httpx.HTTPStatusError as exc:
        error_msg = f"MCP server returned HTTP {exc.response.status_code}: {exc.response.text[:500]}"
        a2a_response = _a2a_error_response(task_id, error_msg)
    except httpx.RequestError as exc:
        error_msg = f"Failed to reach MCP server at {target_mcp_url}: {str(exc)[:300]}"
        a2a_response = _a2a_error_response(task_id, error_msg)
    except Exception as exc:
        error_msg = f"Bridge translation error: {str(exc)[:300]}"
        a2a_response = _a2a_error_response(task_id, error_msg)

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Log the translation
    _log_translation(
        source_protocol="a2a",
        target_protocol="mcp",
        source_request=a2a_task,
        translated_request=mcp_request,
        response=response_data,
        latency_ms=elapsed_ms,
        success=success,
        error_message=error_msg,
    )

    return a2a_response


def _a2a_error_response(task_id: str, error_msg: str) -> dict:
    """Build an A2A-formatted error response."""
    return {
        "jsonrpc": MCP_JSONRPC_VERSION,
        "id": str(uuid.uuid4()),
        "result": {
            "id": task_id,
            "status": {
                "state": "failed",
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "message": {"role": "agent", "parts": [{"type": "text", "text": error_msg}]},
            },
            "artifacts": [],
        },
    }


# ---------------------------------------------------------------------------
# Agent Card Generation
# ---------------------------------------------------------------------------

def generate_agent_card_from_tools(
    tools: List[dict],
    server_name: str = "ThinkNEO Control Plane",
    server_url: str = "https://mcp.thinkneo.ai",
    a2a_endpoint: Optional[str] = None,
) -> dict:
    """
    Generate a complete A2A Agent Card from a list of MCP tool definitions.

    Each MCP tool becomes an A2A skill. The card follows the A2A v0.3.0 spec.
    """
    if not a2a_endpoint:
        a2a_endpoint = f"{server_url}/a2a"

    skills = []
    for tool in tools:
        tool_name = tool.get("name", "unknown")
        tool_desc = tool.get("description", "")
        tool_schema = tool.get("inputSchema", {})

        # Generate example prompts from tool description and parameters
        examples = []
        properties = tool_schema.get("properties", {})
        if properties:
            param_names = list(properties.keys())[:3]
            examples.append(f"Use {tool_name} with {', '.join(param_names)}")

        # Extract tags from tool name
        tags = [t for t in tool_name.replace("thinkneo_", "").split("_") if t]
        tags.extend(["mcp-bridge", "auto-generated"])

        skill = {
            "id": tool_name,
            "name": _tool_name_to_display(tool_name),
            "description": tool_desc or f"MCP tool: {tool_name}",
            "tags": tags,
            "examples": examples or [f"Call {tool_name}"],
            "inputModes": ["text/plain", "application/json"],
            "outputModes": ["text/plain", "application/json"],
        }
        skills.append(skill)

    agent_card = {
        "protocolVersion": A2A_PROTOCOL_VERSION,
        "name": f"{server_name} (MCP Bridge)",
        "description": (
            f"Auto-generated A2A Agent Card for {server_name}. "
            f"This agent exposes {len(tools)} MCP tools as A2A skills via the "
            f"ThinkNEO MCP-to-A2A Bridge. Any A2A-compatible agent can discover "
            f"and interact with these tools through the standard A2A protocol."
        ),
        "url": a2a_endpoint,
        "preferredTransport": "JSONRPC",
        "version": "1.0.0",
        "supportedInterfaces": [
            {
                "url": a2a_endpoint,
                "protocolBinding": "jsonrpc",
                "protocolVersion": A2A_PROTOCOL_VERSION,
            }
        ],
        "provider": {
            "organization": "ThinkNEO",
            "url": "https://thinkneo.ai",
        },
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False,
        },
        "authentication": {
            "schemes": ["bearer"],
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": skills,
    }

    return agent_card


def _tool_name_to_display(tool_name: str) -> str:
    """Convert a snake_case tool name to a human-readable display name."""
    name = tool_name.replace("thinkneo_", "").replace("_", " ")
    return name.title()


# ---------------------------------------------------------------------------
# ThinkNEO Agent Card (self-referencing)
# ---------------------------------------------------------------------------

def generate_thinkneo_agent_card() -> dict:
    """
    Generate ThinkNEO's own A2A Agent Card from its MCP tools.

    This is the card that gets served at /.well-known/agent.json,
    making ThinkNEO discoverable by any A2A-compatible agent.
    """
    # Define all current MCP tools with their metadata
    thinkneo_tools = [
        {
            "name": "thinkneo_check",
            "description": "Free prompt safety check — detects injection attempts and PII exposure in prompts before sending them to AI providers.",
            "inputSchema": {"properties": {"prompt": {"type": "string"}}},
        },
        {
            "name": "thinkneo_usage",
            "description": "Check your ThinkNEO usage stats — calls today/week/month, limits, cost estimates, and top tools used.",
            "inputSchema": {"properties": {}},
        },
        {
            "name": "thinkneo_provider_status",
            "description": "Real-time health status of AI providers (OpenAI, Anthropic, Google, Mistral, etc.) monitored by ThinkNEO.",
            "inputSchema": {"properties": {}},
        },
        {
            "name": "thinkneo_schedule_demo",
            "description": "Book a demo with the ThinkNEO team. Collects contact info and schedules a walkthrough.",
            "inputSchema": {"properties": {"name": {"type": "string"}, "email": {"type": "string"}}},
        },
        {
            "name": "thinkneo_read_memory",
            "description": "Read Claude Code project memory files — access project context, preferences, and reference notes.",
            "inputSchema": {"properties": {"filename": {"type": "string"}}},
        },
        {
            "name": "thinkneo_write_memory",
            "description": "Write or update project memory files for persistent context across sessions.",
            "inputSchema": {"properties": {"filename": {"type": "string"}, "content": {"type": "string"}}},
        },
        {
            "name": "thinkneo_check_spend",
            "description": "AI cost breakdown by provider, model, team, or project. Requires authentication.",
            "inputSchema": {"properties": {"workspace": {"type": "string"}, "period": {"type": "string"}}},
        },
        {
            "name": "thinkneo_evaluate_guardrail",
            "description": "Pre-flight prompt safety evaluation against workspace guardrail policies.",
            "inputSchema": {"properties": {"workspace": {"type": "string"}, "prompt": {"type": "string"}}},
        },
        {
            "name": "thinkneo_check_policy",
            "description": "Verify if a model, provider, or action is allowed by workspace policy.",
            "inputSchema": {"properties": {"workspace": {"type": "string"}}},
        },
        {
            "name": "thinkneo_get_budget_status",
            "description": "Budget utilization and enforcement status for a workspace.",
            "inputSchema": {"properties": {"workspace": {"type": "string"}}},
        },
        {
            "name": "thinkneo_list_alerts",
            "description": "Active alerts and incidents for a workspace.",
            "inputSchema": {"properties": {"workspace": {"type": "string"}}},
        },
        {
            "name": "thinkneo_get_compliance_status",
            "description": "SOC2, GDPR, and HIPAA compliance readiness status for a workspace.",
            "inputSchema": {"properties": {"workspace": {"type": "string"}}},
        },
        {
            "name": "thinkneo_detect_secrets",
            "description": "Scan text for leaked API keys, tokens, and credentials from 15+ providers.",
            "inputSchema": {"properties": {"text": {"type": "string"}}},
        },
        {
            "name": "thinkneo_detect_injection",
            "description": "Advanced prompt injection detection with multi-layer analysis.",
            "inputSchema": {"properties": {"prompt": {"type": "string"}}},
        },
        {
            "name": "thinkneo_compare_models",
            "description": "Compare AI models across providers on cost, speed, quality, and context window.",
            "inputSchema": {"properties": {"models": {"type": "array"}}},
        },
        {
            "name": "thinkneo_optimize_prompt",
            "description": "Optimize prompts for cost, quality, and safety with provider-specific recommendations.",
            "inputSchema": {"properties": {"prompt": {"type": "string"}}},
        },
        {
            "name": "thinkneo_count_tokens",
            "description": "Count tokens for a prompt across multiple models and estimate costs.",
            "inputSchema": {"properties": {"text": {"type": "string"}}},
        },
        {
            "name": "thinkneo_detect_pii",
            "description": "Detect PII across 20+ international categories (GDPR, LGPD, PIPL, etc.).",
            "inputSchema": {"properties": {"text": {"type": "string"}}},
        },
        {
            "name": "thinkneo_cache_prompt",
            "description": "Cache and retrieve prompt responses to reduce costs and latency.",
            "inputSchema": {"properties": {"prompt": {"type": "string"}}},
        },
        {
            "name": "thinkneo_rotate_key",
            "description": "Rotate an API key — generates a new key and revokes the old one.",
            "inputSchema": {"properties": {}},
        },
        {
            "name": "thinkneo_bridge_mcp_to_a2a",
            "description": "Bridge an MCP tool call to an A2A agent — translates protocols bidirectionally.",
            "inputSchema": {"properties": {"mcp_tool_name": {"type": "string"}, "arguments": {"type": "object"}, "target_a2a_agent_url": {"type": "string"}}},
        },
        {
            "name": "thinkneo_bridge_a2a_to_mcp",
            "description": "Bridge an A2A task to an MCP server — translates protocols bidirectionally.",
            "inputSchema": {"properties": {"a2a_task": {"type": "object"}, "target_mcp_server_url": {"type": "string"}}},
        },
        {
            "name": "thinkneo_bridge_generate_agent_card",
            "description": "Auto-generate an A2A Agent Card from any MCP server's tool list.",
            "inputSchema": {"properties": {"mcp_server_url": {"type": "string"}}},
        },
        {
            "name": "thinkneo_bridge_list_mappings",
            "description": "List active MCP↔A2A bridge mappings.",
            "inputSchema": {"properties": {}},
        },
    ]

    return generate_agent_card_from_tools(
        tools=thinkneo_tools,
        server_name="ThinkNEO Control Plane",
        server_url="https://mcp.thinkneo.ai",
        a2a_endpoint="https://mcp.thinkneo.ai/a2a",
    )


# ---------------------------------------------------------------------------
# Bridge Mappings CRUD
# ---------------------------------------------------------------------------

def get_active_mappings() -> List[dict]:
    """Return all active bridge mappings from the database."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, mcp_server_url, a2a_agent_url, mapping_config, created_at, active
                    FROM bridge_mappings
                    WHERE active = TRUE
                    ORDER BY created_at DESC
                    """
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": r["id"],
                        "mcp_server_url": r["mcp_server_url"],
                        "a2a_agent_url": r["a2a_agent_url"],
                        "mapping_config": r["mapping_config"],
                        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                        "active": r["active"],
                    }
                    for r in rows
                ]
    except Exception as exc:
        logger.warning("Failed to get bridge mappings: %s", exc)
        return []


def get_translation_stats() -> dict:
    """Return summary stats for bridge translations."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE success) as successful,
                        COUNT(*) FILTER (WHERE NOT success) as failed,
                        ROUND(AVG(latency_ms)) as avg_latency_ms,
                        COUNT(*) FILTER (WHERE source_protocol = 'mcp') as mcp_to_a2a,
                        COUNT(*) FILTER (WHERE source_protocol = 'a2a') as a2a_to_mcp
                    FROM bridge_translations
                    WHERE created_at >= NOW() - INTERVAL '30 days'
                    """
                )
                row = cur.fetchone()
                if row:
                    return {
                        "total_translations_30d": row["total"],
                        "successful": row["successful"],
                        "failed": row["failed"],
                        "avg_latency_ms": int(row["avg_latency_ms"]) if row["avg_latency_ms"] else 0,
                        "mcp_to_a2a": row["mcp_to_a2a"],
                        "a2a_to_mcp": row["a2a_to_mcp"],
                    }
                return {}
    except Exception as exc:
        logger.warning("Failed to get translation stats: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _async_sleep(seconds: float) -> None:
    """Async sleep wrapper."""
    import asyncio
    await asyncio.sleep(seconds)
