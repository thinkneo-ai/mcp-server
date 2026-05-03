"""
Tools: Agent Observability — "Datadog for AI Agents"

5 MCP tools for tracing, monitoring, and auditing AI agent actions:
  - thinkneo_start_trace: Begin a new agent session trace
  - thinkneo_log_event: Log an event within a session
  - thinkneo_end_trace: End a session and get summary
  - thinkneo_get_trace: Retrieve full trace timeline
  - thinkneo_get_observability_dashboard: Aggregated dashboard data
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth, get_bearer_token
from ..observability import start_session, log_event, end_session, get_trace, get_dashboard
from .._common_obs import utcnow_obs


def register(mcp: FastMCP) -> None:

    # ------------------------------------------------------------------
    # 1. thinkneo_start_trace
    # ------------------------------------------------------------------
    @mcp.tool(
        name="thinkneo_start_trace",
        description=(
            "Start a new agent observability trace. Creates a session that tracks "
            "all tool calls, model calls, decisions, and errors for an AI agent run. "
            "Returns a session_id to use with thinkneo_log_event and thinkneo_end_trace. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    )
    def thinkneo_start_trace(
        agent_name: Annotated[str, Field(description="Name of the agent being traced (e.g., 'marketing-agent', 'support-bot')")],
        agent_type: Annotated[str, Field(description="Type of agent: 'assistant', 'autonomous', 'workflow', 'pipeline', or 'generic'")] = "generic",
        metadata: Annotated[Optional[dict], Field(description="Optional dict with additional context (e.g., {\"task\": \"email-draft\", \"user_id\": \"u123\"})")] = None,
    ) -> str:
        """Start a new agent observability trace. Creates a session that tracks all tool calls, model calls, decisions, and errors for an AI agent run. Returns a session_id to use with thinkneo_log_event and thinkneo_end_trace."""
        token = require_auth()

        meta = {}
        if metadata:
            if isinstance(metadata, dict):
                meta = metadata
            elif isinstance(metadata, str):
                try:
                    meta = json.loads(metadata)
                except json.JSONDecodeError:
                    meta = {"raw": metadata}
            else:
                meta = {"raw": str(metadata)}

        result = start_session(
            api_key=token,
            agent_name=agent_name,
            agent_type=agent_type,
            metadata=meta,
        )
        result["_hint"] = (
            "Use thinkneo_log_event with this session_id to log tool calls, "
            "model calls, and decisions. Call thinkneo_end_trace when done."
        )
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # 2. thinkneo_log_event
    # ------------------------------------------------------------------
    @mcp.tool(
        name="thinkneo_log_event",
        description=(
            "Log an event within an active agent trace. Supports event types: "
            "tool_call, model_call, decision, error, pii_access, guardrail_triggered. "
            "Returns event_id and running session cost. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    )
    def thinkneo_log_event(
        session_id: Annotated[str, Field(description="Session ID from thinkneo_start_trace")],
        event_type: Annotated[str, Field(description="Event type: 'tool_call', 'model_call', 'decision', 'error', 'pii_access', or 'guardrail_triggered'")],
        tool_name: Annotated[Optional[str], Field(description="Name of the tool called (for tool_call events)")] = None,
        model_name: Annotated[Optional[str], Field(description="Model used (for model_call events, e.g., 'gpt-4o', 'claude-sonnet-4-20250514')")] = None,
        input_summary: Annotated[Optional[str], Field(description="Brief summary of the input (max 500 chars, truncated if longer)")] = None,
        output_summary: Annotated[Optional[str], Field(description="Brief summary of the output (max 500 chars, truncated if longer)")] = None,
        cost: Annotated[float, Field(description="Estimated cost in USD for this event (e.g., 0.003 for an API call)")] = 0.0,
        latency_ms: Annotated[int, Field(description="Latency in milliseconds for this event")] = 0,
        metadata: Annotated[Optional[dict], Field(description="Optional dict with additional event context")] = None,
    ) -> str:
        """Log an event within an active agent trace. Supports event types: tool_call, model_call, decision, error, pii_access, guardrail_triggered. Returns event_id and running session cost."""
        require_auth()

        meta = {}
        if metadata:
            if isinstance(metadata, dict):
                meta = metadata
            elif isinstance(metadata, str):
                try:
                    meta = json.loads(metadata)
                except json.JSONDecodeError:
                    meta = {"raw": metadata}
            else:
                meta = {"raw": str(metadata)}

        result = log_event(
            session_id=session_id,
            event_type=event_type,
            tool_name=tool_name,
            model_name=model_name,
            input_summary=input_summary,
            output_summary=output_summary,
            cost=cost,
            latency_ms=latency_ms,
            metadata=meta,
        )
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # 3. thinkneo_end_trace
    # ------------------------------------------------------------------
    @mcp.tool(
        name="thinkneo_end_trace",
        description=(
            "End an active agent trace and get the session summary. "
            "Returns total cost, duration, tool/model call counts, and event count. "
            "Triggers post-session anomaly detection (cost spikes, error rate). "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    )
    def thinkneo_end_trace(
        session_id: Annotated[str, Field(description="Session ID from thinkneo_start_trace")],
        status: Annotated[str, Field(description="Final session status: 'success', 'failure', or 'timeout'")] = "success",
    ) -> str:
        """End an active agent trace and get the session summary. Returns total cost, duration, tool/model call counts, and event count. Triggers post-session anomaly detection (cost spikes, error rate)."""
        require_auth()

        result = end_session(
            session_id=session_id,
            status=status,
        )
        result["generated_at"] = utcnow_obs()
        result["trace_url"] = f"https://mcp.thinkneo.ai/traces/{session_id}"
        return json.dumps(result, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # 4. thinkneo_get_trace
    # ------------------------------------------------------------------
    @mcp.tool(
        name="thinkneo_get_trace",
        description=(
            "Retrieve the full trace for an agent session. Returns the complete "
            "timeline of events (tool calls, model calls, decisions, errors), "
            "session metadata, total cost, duration, and any alerts triggered. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_get_trace(
        session_id: Annotated[str, Field(description="Session ID to retrieve the trace for")],
    ) -> str:
        """Retrieve the full trace for an agent session. Returns the complete timeline of events (tool calls, model calls, decisions, errors), session metadata, total cost, duration, and any alerts triggered."""
        require_auth()

        result = get_trace(session_id=session_id)
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # 5. thinkneo_get_observability_dashboard
    # ------------------------------------------------------------------
    @mcp.tool(
        name="thinkneo_get_observability_dashboard",
        description=(
            "Get the agent observability dashboard — aggregated metrics for your "
            "AI agents. Includes total sessions, events, cost, error rate, latency, "
            "top agents, top tools, active alerts, and cost trend over time. "
            "Like Datadog, but for AI agents. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_get_observability_dashboard(
        period: Annotated[str, Field(description="Time period: '1h', '24h', '7d', or '30d'")] = "24h",
    ) -> str:
        """Get the agent observability dashboard — aggregated metrics for your AI agents. Includes total sessions, events, cost, error rate, latency, top agents, top tools, active alerts, and cost trend over time. Like Datadog, but for AI agents."""
        token = require_auth()

        valid_periods = {"1h", "24h", "7d", "30d"}
        if period not in valid_periods:
            period = "24h"

        result = get_dashboard(api_key=token, period=period)
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)
